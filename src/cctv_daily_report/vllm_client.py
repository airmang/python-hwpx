"""vLLM /v1/chat/completions 단일 호출 지점.

VLM(이미지+텍스트)·LLM(텍스트 전용)·번역기 모두 이 함수를 통해 호출한다.
재시도 정책은 단순화: 429/503 한 번만 짧게 재시도.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import TIMEOUT_SECONDS, VLLM_BASE_URL, VLLM_MODEL


class VllmError(RuntimeError):
    pass


def post_chat_payload(payload: dict[str, Any]) -> str:
    """완성된 chat payload(dict)를 POST하고 텍스트만 추출.

    payload는 build_chat_payload(...)의 결과나 직접 구성한 messages dict.
    model 필드가 없으면 기본값 채워준다.
    """
    payload = dict(payload)
    payload.setdefault("model", VLLM_MODEL)

    url = f"{VLLM_BASE_URL}/v1/chat/completions"
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            r = httpx.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last_err = exc
            time.sleep(1.0)
            continue
        if r.status_code in (429, 503) and attempt == 0:
            time.sleep(2.0)
            continue
        if r.status_code != 200:
            raise VllmError(f"vLLM returned {r.status_code}: {r.text[:300]}")
        try:
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise VllmError(f"vLLM response parsing failed: {exc}") from exc
    raise VllmError(f"vLLM request failed after retries: {last_err}")


def post_text(
    prompt: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
    system: str | None = None,
) -> str:
    """이미지 없는 단순 텍스트 chat completion."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": VLLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    return post_chat_payload(payload)
