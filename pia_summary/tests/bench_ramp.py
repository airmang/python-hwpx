"""램프 (ramp-up) 부하 테스트: 동시 요청 수를 점증시키며 한계점을 탐지.

각 단계마다 step_duration 동안 해당 동시성으로 지속 부하를 가한 뒤,
다음 단계로 동시성을 곱(혹은 더해) 늘린다. 다음 조건 중 하나라도
만족하면 break.

  - 에러율 > --err-threshold (%)
  - p95 지연 > --p95-threshold-ms

마지막으로 정상 동작한 동시성을 last_safe 로 보고한다.

본 벤치는 ramp-up stress / saturation point 탐지가 목적이다. 시간 경과에
따른 메모리 누수 / latency drift 같은 진짜 aging 검출용은 아님.

Usage:
    python tests/bench_ramp.py
    python tests/bench_ramp.py --start 1 --step 2 --max 64 \\
                               --step-duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

import httpx

from _common import DEFAULT_MODEL, DEFAULT_VLLM_URL, extract_summary, make_payload
from _vram import VramMonitor, summarize


async def _worker(
    client: httpx.AsyncClient,
    url: str,
    payload: dict,
    stop_at: float,
    request_timeout: float,
    results: list,
) -> None:
    while time.monotonic() < stop_at:
        started = time.monotonic()
        try:
            r = await client.post(url, json=payload, timeout=request_timeout)
            el = time.monotonic() - started
            if r.status_code == 200:
                try:
                    extract_summary(r.json())
                    results.append(("ok", el))
                except Exception:  # noqa: BLE001
                    results.append(("parse_err", el))
            else:
                results.append((f"http_{r.status_code}", el))
        except Exception:  # noqa: BLE001
            results.append(("exc", time.monotonic() - started))


async def _run_step(
    *,
    url: str,
    payload: dict,
    concurrency: int,
    duration: float,
    request_timeout: float,
    gpu_index: int,
    vram_interval: float,
) -> dict:
    monitor = VramMonitor(interval=vram_interval, gpu_index=gpu_index)
    monitor.start()

    results: list = []
    stop_at = time.monotonic() + duration
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    async with httpx.AsyncClient(limits=limits) as client:
        workers = [
            asyncio.create_task(
                _worker(client, url, payload, stop_at, request_timeout, results)
            )
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers, return_exceptions=True)

    monitor.stop()
    vram = summarize(monitor.samples)

    oks = [r for r in results if r[0] == "ok"]
    fails = [r for r in results if r[0] != "ok"]
    latencies = sorted(r[1] for r in oks)

    def pct(p: float) -> float:
        if not latencies:
            return float("nan")
        idx = max(0, min(len(latencies) - 1,
                         int(round(p / 100 * (len(latencies) - 1)))))
        return latencies[idx]

    return {
        "concurrency": concurrency,
        "duration_s": duration,
        "total": len(results),
        "success": len(oks),
        "fail": len(fails),
        "error_rate_pct": (len(fails) / len(results) * 100) if results else 0.0,
        "throughput_rps": len(oks) / duration if duration else 0.0,
        "p50_ms": pct(50) * 1000 if latencies else 0.0,
        "p95_ms": pct(95) * 1000 if latencies else 0.0,
        "p99_ms": pct(99) * 1000 if latencies else 0.0,
        "mean_ms": statistics.mean(latencies) * 1000 if latencies else 0.0,
        "max_ms": max(latencies) * 1000 if latencies else 0.0,
        "vram_avg_mib": vram["used_avg"],
        "vram_peak_mib": vram["used_peak"],
        "vram_total_mib": vram["total"],
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_VLLM_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--start", type=int, default=1,
                   help="시작 동시성")
    p.add_argument("--step", type=int, default=2,
                   help="단계마다 동시성에 곱할 배수 (>=2면 곱셈, 1이면 +1 증가)")
    p.add_argument("--max", type=int, default=64,
                   help="이 동시성을 초과하면 종료")
    p.add_argument("--step-duration", type=float, default=30.0,
                   help="각 단계 부하 인가 시간(초)")
    p.add_argument("--max-tokens", type=int, default=96)
    p.add_argument("--err-threshold", type=float, default=2.0,
                   help="이 % 이상 에러 시 break")
    p.add_argument("--p95-threshold-ms", type=float, default=10000.0,
                   help="p95이 이 ms 이상이면 break")
    p.add_argument("--gpu-index", type=int, default=0)
    p.add_argument("--vram-interval", type=float, default=0.5)
    p.add_argument("--cooldown", type=float, default=3.0)
    p.add_argument("--request-timeout", type=float, default=120.0)
    p.add_argument("--no-append", action="store_true",
                   help="result.md 에 결과를 append 하지 않음 (드라이런)")
    return p.parse_args()


async def run(args: argparse.Namespace) -> dict:
    payload = make_payload(model=args.model, max_tokens=args.max_tokens)

    print(f"[ramp] url       : {args.url}")
    print(f"[ramp] model     : {args.model}")
    print(f"[ramp] start     : {args.start}")
    print(f"[ramp] step      : x{args.step}" if args.step >= 2 else f"[ramp] step      : +{args.step}")
    print(f"[ramp] max       : {args.max}")
    print(f"[ramp] duration  : {args.step_duration:.0f}s/step")
    print(f"[ramp] thresholds: err>{args.err_threshold}% or p95>{args.p95_threshold_ms:.0f}ms")

    rows: list[dict] = []
    last_safe: int | None = None
    breaker: dict | None = None
    c = args.start
    while c <= args.max:
        print(f"\n[ramp] >>> concurrency={c} duration={args.step_duration:.0f}s")
        row = await _run_step(
            url=args.url,
            payload=payload,
            concurrency=c,
            duration=args.step_duration,
            request_timeout=args.request_timeout,
            gpu_index=args.gpu_index,
            vram_interval=args.vram_interval,
        )
        rows.append(row)
        print(f"     ok={row['success']}/{row['total']} "
              f"err%={row['error_rate_pct']:.2f} "
              f"rps={row['throughput_rps']:.2f} "
              f"p95={row['p95_ms']:.0f}ms "
              f"vram_peak={row['vram_peak_mib']:.0f} MiB")

        bad_err = row["error_rate_pct"] > args.err_threshold
        bad_p95 = row["p95_ms"] > args.p95_threshold_ms
        if bad_err or bad_p95:
            reason = (
                f"err {row['error_rate_pct']:.2f}% > {args.err_threshold}%"
                if bad_err
                else f"p95 {row['p95_ms']:.0f}ms > {args.p95_threshold_ms:.0f}ms"
            )
            breaker = {"concurrency": c, "reason": reason}
            print(f"\n[ramp] breakpoint: c={c} ({reason})")
            break

        last_safe = c
        if c >= args.max:
            break
        if args.cooldown > 0:
            await asyncio.sleep(args.cooldown)
        c = c * args.step if args.step >= 2 else c + args.step

    summary = {
        "rows": rows,
        "last_safe_concurrency": last_safe,
        "breakpoint": breaker,
    }

    print()
    if breaker is None:
        print(f"[ramp] breakpoint 미발생. --max ({args.max}) 까지 안전.")
    else:
        print(f"[ramp] last_safe_concurrency = {last_safe}, "
              f"breakpoint = c{breaker['concurrency']} ({breaker['reason']})")
    return summary


def main() -> int:
    args = parse_args()
    res = asyncio.run(run(args))
    if not args.no_append:
        from _common import write_to_result
        from _result import render_ramp
        write_to_result("ramp", render_ramp(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
