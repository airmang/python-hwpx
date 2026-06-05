"""영문 4종 보고 문장 생성 (feature_docs §13/§14 영문판).

LLM 응답이 JSON 파싱 실패하면 rule-based fallback 사용.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import MAX_TOKENS_LLM
from .vllm_client import VllmError, post_text

_KEYS = ("daily_summary", "main_event_description", "special_note", "review_note")

_SYSTEM = (
    "You are an assistant producing concise, formal English sentences for a "
    "public-sector daily CCTV AI detection report. Output strict JSON only."
)

_PROMPT = """Generate report sentences in English based on the input JSON below.

Targets to write:
1. daily_summary       : 1-3 sentences summarising today's detection activity.
2. main_event_description : 1-3 sentences describing the main detected event(s).
3. special_note        : 1-3 sentences flagging anomalies or repeated cameras.
4. review_note         : 1 sentence about the need (or not) for operator review.

Rules:
- Use only data from the input. Do not invent numbers, IDs, or times.
- Reuse camera IDs, names, categories, and times verbatim.
- Each value must be a single string (newlines allowed inside).
- If main_events is empty, say "No detection events occurred today.".
- If repeated_cameras is empty, say "No notable repeated cameras.".
- If need_review count is 0, set review_note to "No additional review required.".
- For events whose visual_verification is "unclear", note that the
  representative frame requires additional review.

Input data:
{input_json}

Respond with EXACTLY this JSON shape and nothing else:
{{
  "daily_summary": "...",
  "main_event_description": "...",
  "special_note": "...",
  "review_note": "..."
}}
"""


def _build_payload(report_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_info": report_payload["report_info"],
        "camera_info": report_payload["camera_info"],
        "event_summary": report_payload["event_summary"],
        "main_events": report_payload["main_events"],
        "repeated_cameras": report_payload["repeated_cameras"],
    }


def _parse_json_block(text: str) -> dict[str, str] | None:
    text = text.strip()
    # 모델이 ``` 코드펜스를 감싸는 경우 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 첫 { ... 마지막 } 범위 시도
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for key in _KEYS:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out if len(out) == len(_KEYS) else None


def rule_based_fallback(report_payload: dict[str, Any]) -> dict[str, str]:
    summary = report_payload["event_summary"]
    total = summary["total_event_count"]
    confirmed = summary["confirmed_alarm_count"]
    need_review = summary["need_review_event_count"]
    fp = summary["false_positive_count"]
    counts = summary["event_counts"]
    main_category = summary.get("main_event_category", "etc")

    if total == 0:
        return {
            "daily_summary": "No detection events occurred today.",
            "main_event_description": "No main events to describe today.",
            "special_note": "No notable findings today.",
            "review_note": "No additional review required.",
        }

    daily = (
        f"A total of {total} detection alerts occurred today, of which "
        f"{confirmed} were confirmed, {need_review} require review, and "
        f"{fp} were suspected false positives. "
        f"The most frequent category was {main_category} "
        f"(fire {counts['fire']}, smoke {counts['smoke']}, "
        f"falldown {counts['falldown']}, etc {counts['etc']})."
    )

    main_events = report_payload.get("main_events", [])
    if main_events:
        descriptions = []
        for ev in main_events[:3]:
            descriptions.append(
                f"Camera {ev['camera_id']} ({ev['camera_name']}) raised a "
                f"{ev['category']} event at {ev['time']} with status "
                f"{ev['status']}; visual summary: {ev.get('visual_summary', 'n/a')}"
            )
        main_event_description = " ".join(descriptions)
    else:
        main_event_description = "No main events to describe today."

    repeated = report_payload.get("repeated_cameras", [])
    if repeated:
        rep = repeated[0]
        special = (
            f"Camera {rep['camera_id']} ({rep['camera_name']}) triggered "
            f"{rep['event_count']} {rep['main_category']} events repeatedly, "
            "warranting on-site verification of ROI and camera angle."
        )
    else:
        special = "No notable repeated cameras."

    review = (
        f"{need_review} events require operator review."
        if need_review
        else "No additional review required."
    )

    return {
        "daily_summary": daily,
        "main_event_description": main_event_description,
        "special_note": special,
        "review_note": review,
    }


def generate_en_block(report_payload: dict[str, Any]) -> dict[str, str]:
    payload_for_prompt = _build_payload(report_payload)
    prompt = _PROMPT.format(input_json=json.dumps(payload_for_prompt, ensure_ascii=False, indent=2))

    try:
        raw = post_text(prompt, max_tokens=MAX_TOKENS_LLM, temperature=0.0, system=_SYSTEM)
    except VllmError as exc:
        print(f"[summarizer] LLM call failed: {exc} — falling back to rule-based")
        return rule_based_fallback(report_payload)

    parsed = _parse_json_block(raw)
    if parsed is None:
        print("[summarizer] JSON parse failed — falling back to rule-based")
        print(f"[summarizer] raw response head: {raw[:200]!r}")
        return rule_based_fallback(report_payload)
    return parsed
