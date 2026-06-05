"""단발 호출로 vLLM 서버 정상성 확인.

prompts.build_chat_payload 로 만든 페이로드 1건을 보내고 응답을 검사한다.

Usage:
    python tests/sanity_check.py
    python tests/sanity_check.py --url http://10.0.0.5:8000/v1/chat/completions \\
                                 --model my-model --max-tokens 96
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

from _common import (
    DEFAULT_MODEL,
    DEFAULT_MODELS_URL,
    DEFAULT_VLLM_URL,
    extract_summary,
    make_payload,
)


def wait_ready(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5.0)
            if r.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(2)
    raise SystemExit(
        f"vLLM /v1/models 가 {timeout:.0f}초 안에 응답하지 않음: {last}"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_VLLM_URL)
    p.add_argument("--models-url", default=DEFAULT_MODELS_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-tokens", type=int, default=96)
    p.add_argument("--max-words", type=int, default=40)
    p.add_argument("--ready-timeout", type=float, default=10.0,
                   help="/v1/models 가 200을 줄 때까지 대기할 최대 시간(초)")
    p.add_argument("--request-timeout", type=float, default=120.0)
    return p.parse_args()


def run(args: argparse.Namespace) -> dict:
    """결과 dict를 반환. run_all.py가 이 함수를 직접 호출한다."""
    print(f"[sanity] readiness 체크: {args.models_url}")
    wait_ready(args.models_url, timeout=args.ready_timeout)
    print("[sanity] vLLM ready.")

    payload = make_payload(
        model=args.model,
        max_tokens=args.max_tokens,
        max_words=args.max_words,
    )

    started = time.monotonic()
    try:
        r = httpx.post(args.url, json=payload, timeout=args.request_timeout)
    except httpx.HTTPError as exc:
        print(f"[sanity] HTTP 오류: {exc}", file=sys.stderr)
        return {"ok": False, "elapsed": time.monotonic() - started, "error": str(exc)}

    elapsed = time.monotonic() - started

    if r.status_code != 200:
        print(f"[sanity] non-200: {r.status_code} {r.text[:500]}", file=sys.stderr)
        return {
            "ok": False, "elapsed": elapsed, "status": r.status_code,
            "error": r.text[:500],
        }

    summary = extract_summary(r.json())
    word_count = len(summary.split())
    sentence_count = sum(summary.count(c) for c in ".!?") or 1
    ends_term = summary.rstrip().endswith((".", "!", "?"))

    print()
    print(f"[sanity] elapsed   : {elapsed:.2f}s")
    print(f"[sanity] words     : {word_count}")
    print(f"[sanity] sentences : {sentence_count}")
    print(f"[sanity] terminator: {'ok' if ends_term else 'missing'}")
    print(f"[sanity] under {args.max_words}: "
          f"{'yes' if word_count <= args.max_words else 'OVER'}")
    print()
    print("[summary]")
    print(summary)

    return {
        "ok": True,
        "elapsed": elapsed,
        "words": word_count,
        "sentences": sentence_count,
        "terminated": ends_term,
        "under_max_words": word_count <= args.max_words,
        "summary": summary,
    }


def main() -> int:
    args = parse_args()
    res = run(args)
    return 0 if res["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
