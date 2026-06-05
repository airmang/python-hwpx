"""max_tokens 별 응답시간 / 추론시간 측정.

각 후보 max_tokens 에 대해 동일 페이로드로 sequential N회 호출하여
지연(min/avg/max), 응답 길이, 마침표 종결 비율, length-truncated 비율
을 보고한다.

Usage:
    python tests/bench_max_tokens.py
    python tests/bench_max_tokens.py --tokens 32 64 96 128 192 --repeat 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

import httpx

from _common import DEFAULT_MODEL, DEFAULT_VLLM_URL, extract_summary, make_payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_VLLM_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--tokens", type=int, nargs="+",
                   default=[32, 64, 96, 128, 192, 256])
    p.add_argument("--repeat", type=int, default=3,
                   help="각 max_tokens 별 sequential 호출 수")
    p.add_argument("--max-words", type=int, default=40)
    p.add_argument("--request-timeout", type=float, default=120.0)
    p.add_argument("--no-append", action="store_true",
                   help="result.md 에 결과를 append 하지 않음 (드라이런)")
    return p.parse_args()


def run(args: argparse.Namespace) -> list[dict]:
    print(f"[max_tokens] url        : {args.url}")
    print(f"[max_tokens] model      : {args.model}")
    print(f"[max_tokens] candidates : {args.tokens}")
    print(f"[max_tokens] repeat     : {args.repeat}")
    print()

    header = ("max_tokens", "avg_ms", "min_ms", "max_ms", "avg_words",
              "terminated", "truncated", "errors")
    print("{:>10} {:>8} {:>8} {:>8} {:>9} {:>10} {:>9} {:>7}".format(*header))
    print("-" * 78)

    rows: list[dict] = []
    with httpx.Client(timeout=args.request_timeout) as client:
        for cap in args.tokens:
            payload = make_payload(
                model=args.model, max_tokens=cap, max_words=args.max_words,
            )
            latencies: list[float] = []
            words: list[int] = []
            chars: list[int] = []
            term, trunc, err = 0, 0, 0
            for _ in range(args.repeat):
                started = time.monotonic()
                try:
                    r = client.post(args.url, json=payload)
                except httpx.HTTPError as exc:
                    err += 1
                    print(f"  [warn] HTTP 오류 max_tokens={cap}: {exc}",
                          file=sys.stderr)
                    continue
                el = time.monotonic() - started
                if r.status_code != 200:
                    err += 1
                    print(f"  [warn] status={r.status_code} max_tokens={cap}",
                          file=sys.stderr)
                    continue
                data = r.json()
                summary = extract_summary(data)
                latencies.append(el)
                words.append(len(summary.split()))
                chars.append(len(summary))
                if summary.rstrip().endswith((".", "!", "?")):
                    term += 1
                if data.get("choices", [{}])[0].get("finish_reason") == "length":
                    trunc += 1

            row = {
                "max_tokens": cap,
                "avg_ms": (statistics.mean(latencies) * 1000) if latencies else 0.0,
                "min_ms": (min(latencies) * 1000) if latencies else 0.0,
                "max_ms": (max(latencies) * 1000) if latencies else 0.0,
                "avg_words": (statistics.mean(words)) if words else 0.0,
                "avg_chars": (statistics.mean(chars)) if chars else 0.0,
                "terminated": f"{term}/{args.repeat}",
                "truncated": f"{trunc}/{args.repeat}",
                "errors": err,
            }
            rows.append(row)

            if latencies:
                print("{:>10} {:>8.0f} {:>8.0f} {:>8.0f} {:>9.1f} "
                      "{:>10} {:>9} {:>7}".format(
                          row["max_tokens"], row["avg_ms"], row["min_ms"],
                          row["max_ms"], row["avg_words"],
                          row["terminated"], row["truncated"], row["errors"],
                      ))
            else:
                print(f"{cap:>10}    -- {args.repeat}회 모두 실패 --")

    print()
    print("[hint] truncated 가 0/N 이고 terminated 가 N/N 이 되는 "
          "최소 max_tokens 가 적정 상한.")
    return rows


def main() -> int:
    args = parse_args()
    rows = run(args)
    if not args.no_append:
        from _common import write_to_result
        from _result import render_max_tokens
        write_to_result("max_tokens_sweep", render_max_tokens(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
