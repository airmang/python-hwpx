"""동시성 sweep 벤치 (asyncio).

--concurrency-list 의 각 단계에서 prompts.build_chat_payload 페이로드로
요청을 발사하고, 동시에 nvidia-smi 폴링으로 VRAM 변동을 측정한다.

각 단계별로 보고:
  - 처리량 (req/s), latency p50/p95/p99/mean
  - VRAM avg / peak (MiB)
  - 에러 수

이 sweep을 1, 2, 4, 8, 16 ... 으로 늘려가며 추론시간과 VRAM이
어떻게 변하는지 한 번에 비교 가능.

Usage:
    python tests/bench_concurrency.py
    python tests/bench_concurrency.py --concurrency-list 1 2 4 8 16 \\
                                      --per-step-multiplier 20
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from typing import Any

import httpx

from _common import DEFAULT_MODEL, DEFAULT_VLLM_URL, extract_summary, make_payload
from _vram import VramMonitor, summarize


async def _one(client: httpx.AsyncClient, url: str, payload: dict,
               sem: asyncio.Semaphore, timeout: float) -> dict[str, Any]:
    async with sem:
        started = time.monotonic()
        try:
            r = await client.post(url, json=payload, timeout=timeout)
            elapsed = time.monotonic() - started
            if r.status_code != 200:
                return {
                    "ok": False, "elapsed": elapsed,
                    "status": r.status_code, "error": r.text[:200],
                }
            try:
                extract_summary(r.json())
            except Exception as exc:  # noqa: BLE001
                return {
                    "ok": False, "elapsed": elapsed,
                    "status": r.status_code, "error": f"parse: {exc}",
                }
            return {"ok": True, "elapsed": elapsed, "status": 200}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False, "elapsed": time.monotonic() - started,
                "status": 0, "error": str(exc)[:200],
            }


async def _run_level(
    *,
    url: str,
    payload: dict,
    concurrency: int,
    total: int,
    request_timeout: float,
    gpu_index: int,
    vram_interval: float,
) -> dict:
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    monitor = VramMonitor(interval=vram_interval, gpu_index=gpu_index)
    monitor.start()

    started = time.monotonic()
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [
            asyncio.create_task(
                _one(client, url, payload, sem, request_timeout)
            )
            for _ in range(total)
        ]
        results = await asyncio.gather(*tasks)
    wall = time.monotonic() - started

    monitor.stop()
    vram = summarize(monitor.samples)

    oks = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    latencies = sorted(r["elapsed"] for r in oks)

    def pct(p: float) -> float:
        if not latencies:
            return float("nan")
        idx = max(0, min(len(latencies) - 1,
                         int(round(p / 100 * (len(latencies) - 1)))))
        return latencies[idx]

    return {
        "concurrency": concurrency,
        "total": total,
        "success": len(oks),
        "fail": len(fails),
        "wall_s": wall,
        "throughput_rps": len(oks) / wall if wall > 0 else 0.0,
        "p50_ms": pct(50) * 1000 if latencies else 0.0,
        "p95_ms": pct(95) * 1000 if latencies else 0.0,
        "p99_ms": pct(99) * 1000 if latencies else 0.0,
        "mean_ms": (statistics.mean(latencies) * 1000) if latencies else 0.0,
        "max_ms": (max(latencies) * 1000) if latencies else 0.0,
        "vram_avg_mib": vram["used_avg"],
        "vram_peak_mib": vram["used_peak"],
        "vram_total_mib": vram["total"],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_VLLM_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--concurrency-list", type=int, nargs="+",
                   default=[1, 2, 4, 8, 16])
    p.add_argument("--per-step-multiplier", type=int, default=20,
                   help="단계별 total = concurrency * 이 값")
    p.add_argument("--max-tokens", type=int, default=96)
    p.add_argument("--gpu-index", type=int, default=0)
    p.add_argument("--vram-interval", type=float, default=0.5,
                   help="VRAM 폴링 간격(초)")
    p.add_argument("--request-timeout", type=float, default=120.0)
    p.add_argument("--cooldown", type=float, default=3.0,
                   help="단계 사이 휴식(초). 0이면 즉시 다음 단계.")
    p.add_argument("--no-append", action="store_true",
                   help="result.md 에 결과를 append 하지 않음 (드라이런)")
    return p.parse_args()


def _print_table(rows: list[dict]) -> None:
    print()
    print(f"{'c':>3} {'total':>6} {'ok':>6} {'rps':>7} "
          f"{'p50ms':>7} {'p95ms':>7} {'p99ms':>7} {'mean':>7} "
          f"{'vram_avg':>9} {'vram_peak':>10}")
    print("-" * 78)
    for r in rows:
        print(f"{r['concurrency']:>3} {r['total']:>6} "
              f"{r['success']:>6} {r['throughput_rps']:>7.2f} "
              f"{r['p50_ms']:>7.0f} {r['p95_ms']:>7.0f} "
              f"{r['p99_ms']:>7.0f} {r['mean_ms']:>7.0f} "
              f"{r['vram_avg_mib']:>9.0f} {r['vram_peak_mib']:>10.0f}")


async def run(args: argparse.Namespace) -> list[dict]:
    payload = make_payload(model=args.model, max_tokens=args.max_tokens)

    print(f"[bench] url        : {args.url}")
    print(f"[bench] model      : {args.model}")
    print(f"[bench] sweep      : {args.concurrency_list}")
    print(f"[bench] multiplier : {args.per_step_multiplier} (total = c * x)")

    rows: list[dict] = []
    for idx, c in enumerate(args.concurrency_list):
        total = c * args.per_step_multiplier
        print(f"\n[bench] >>> concurrency={c} total={total}")
        row = await _run_level(
            url=args.url,
            payload=payload,
            concurrency=c,
            total=total,
            request_timeout=args.request_timeout,
            gpu_index=args.gpu_index,
            vram_interval=args.vram_interval,
        )
        rows.append(row)
        print(f"     ok={row['success']}/{row['total']} "
              f"rps={row['throughput_rps']:.2f} "
              f"p95={row['p95_ms']:.0f}ms "
              f"vram_peak={row['vram_peak_mib']:.0f} MiB")

        if args.cooldown > 0 and idx != len(args.concurrency_list) - 1:
            await asyncio.sleep(args.cooldown)

    _print_table(rows)
    return rows


def main() -> int:
    args = parse_args()
    rows = asyncio.run(run(args))
    if not args.no_append:
        from _common import write_to_result
        from _result import render_concurrency
        write_to_result("concurrency_sweep", render_concurrency(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
