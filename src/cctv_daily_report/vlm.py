"""이벤트별 영문 visual_summary 생성 (feature_docs §6, §11).

pia_summary.prompts.build_chat_payload를 그대로 재사용한다.
"""

from __future__ import annotations

import sys
from typing import Any

from .config import MAX_TOKENS_VLM, PIA_SUMMARY_DIR, VLLM_MODEL
from .images import dummy_jpeg_b64
from .mock_data import CctvEvent
from .vllm_client import VllmError, post_chat_payload


def _load_build_chat_payload():
    """pia_summary.prompts.build_chat_payload를 지연 로딩한다.

    pia_summary는 site-packages에 없는 외부 폴더라 sys.path 등록이 필요한데,
    import-time 부작용을 피하려고 실제 VLM 호출 시점에만 경로를 등록한다.
    """
    if str(PIA_SUMMARY_DIR) not in sys.path:
        sys.path.insert(0, str(PIA_SUMMARY_DIR))
    from prompts import build_chat_payload

    return build_chat_payload


def _event_metadata(ev: CctvEvent) -> dict[str, Any]:
    return {
        "event_id": ev.event_id,
        "camera_id": ev.camera_id,
        "camera_name": ev.camera_name,
        "detected_category": ev.category,
        "event_start_time": ev.event_time,
        "event_status": ev.status,
        "confidence": f"{ev.confidence:.2f}",
    }


def summarize_event(ev: CctvEvent) -> dict[str, str]:
    """feature_docs §11 형태의 dict 반환."""
    thumb = dummy_jpeg_b64(ev.event_id)
    if thumb is None:
        return {
            "event_id": ev.event_id,
            "visual_summary": "Representative frame unavailable.",
            "visual_verification": "unclear",
        }

    build_chat_payload = _load_build_chat_payload()
    payload = build_chat_payload(
        thumb,
        _event_metadata(ev),
        model=VLLM_MODEL,
        max_tokens=MAX_TOKENS_VLM,
        temperature=0.0,
        max_words=40,
    )
    try:
        text = post_chat_payload(payload)
    except VllmError as exc:
        print(f"[vlm] failed for {ev.event_id}: {exc}")
        return {
            "event_id": ev.event_id,
            "visual_summary": "Visual analysis unavailable.",
            "visual_verification": "unclear",
        }

    return {
        "event_id": ev.event_id,
        "visual_summary": text,
        "visual_verification": "confirmed",
    }
