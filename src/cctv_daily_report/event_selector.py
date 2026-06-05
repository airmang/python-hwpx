"""주요 이벤트 선정 — feature_docs §5 정책."""

from __future__ import annotations

from .mock_data import CctvEvent

_STATUS_PRIORITY = {"confirmed": 0, "need_review": 1, "false_positive": 2}
_CATEGORY_PRIORITY = {"fire": 0, "smoke": 1, "falldown": 2, "etc": 3}


def _sort_key(ev: CctvEvent) -> tuple[int, int, float]:
    return (
        _STATUS_PRIORITY.get(ev.status, 9),
        _CATEGORY_PRIORITY.get(ev.category, 9),
        -ev.confidence,
    )


def pick_main(events: list[CctvEvent], max_n: int = 3) -> list[CctvEvent]:
    """동일 CCTV는 1건만 대표로 남기고 우선순위 정렬 후 상위 max_n 반환."""
    ordered = sorted(events, key=_sort_key)
    seen_cameras: set[str] = set()
    chosen: list[CctvEvent] = []
    for ev in ordered:
        if ev.camera_id in seen_cameras:
            continue
        seen_cameras.add(ev.camera_id)
        chosen.append(ev)
        if len(chosen) >= max_n:
            break
    return chosen
