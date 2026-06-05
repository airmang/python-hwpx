"""영문 보고 문장 → 한국어 변환.

동일 vLLM 서버를 텍스트 전용으로 호출. 실패 시 영문 원문 반환.
"""

from __future__ import annotations

import json
import re

from .vllm_client import VllmError, post_text

_SYSTEM = (
    "You are a professional Korean translator for public-sector CCTV "
    "surveillance reports. Translate English sentences into formal, natural "
    "Korean used by Korean government control centers. Preserve all numbers, "
    "IDs, camera names, times and event categories verbatim. Output strict "
    "JSON only — no markdown, no code fences, no English explanation."
)

_PROMPT = """Translate each value of the following JSON into formal natural
Korean for a Korean CCTV daily detection report. Keep keys unchanged.

Korean terminology rules (MANDATORY — use these exact words):
- "fall" / "fall_down" / "falldown" -> "쓰러짐"
- "fire" -> "화재"
- "smoke" -> "연기"
- "confirmed" / "confirmed alarm" -> "확정"
- "need_review" / "needs review" -> "확인 필요"
- "false positive" -> "오탐 의심"
- "event" -> "이벤트" (NOT "사건")
- "camera" -> "카메라"
- "operator review" -> "운영자 검토"
- "gym entrance" -> "체육관 입구" (NEVER "기숙사")
- "parking lot" -> "주차장"
- "main entrance" / "본관 출입구" -> "본관 출입구"

Sentence rules:
- Output should read like a Korean government report (deferential, factual)
- Keep camera IDs (CAM-XX) verbatim
- Keep event IDs (EVT-XXXXXXXX-XXXX) verbatim
- Do NOT translate Korean words that already appear in the input

Input JSON:
{input_json}

Respond with the SAME JSON shape, values replaced by Korean translations.
"""


def _parse_json(text: str) -> dict[str, str] | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {k: str(v).strip() for k, v in data.items() if isinstance(v, str)}


def to_korean(en_block: dict[str, str]) -> dict[str, str]:
    prompt = _PROMPT.format(input_json=json.dumps(en_block, ensure_ascii=False, indent=2))
    try:
        raw = post_text(prompt, max_tokens=1024, temperature=0.0, system=_SYSTEM)
    except VllmError as exc:
        print(f"[translator] call failed: {exc} — returning English originals")
        return dict(en_block)

    parsed = _parse_json(raw)
    if parsed is None:
        print("[translator] JSON parse failed — returning English originals")
        print(f"[translator] raw response head: {raw[:200]!r}")
        return dict(en_block)

    # 누락된 키는 영문 원문으로 보강
    merged = dict(en_block)
    for key, value in parsed.items():
        if value:
            merged[key] = value
    return merged
