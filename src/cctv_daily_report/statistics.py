"""이벤트 리스트 → feature_docs §4 형태의 event_summary dict."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .mock_data import CctvEvent


def aggregate(events: list[CctvEvent]) -> dict[str, Any]:
    by_category: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    camera_counts: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"camera_name": "", "event_count": 0, "categories": Counter()}
    )

    for ev in events:
        by_category[ev.category] += 1
        by_status[ev.status] += 1
        slot = camera_counts[ev.camera_id]
        slot["camera_name"] = ev.camera_name
        slot["event_count"] += 1
        slot["categories"][ev.category] += 1

    repeated = []
    for cam_id, slot in camera_counts.items():
        if slot["event_count"] >= 3:
            main_cat = slot["categories"].most_common(1)[0][0]
            repeated.append(
                {
                    "camera_id": cam_id,
                    "camera_name": slot["camera_name"],
                    "event_count": slot["event_count"],
                    "main_category": main_cat,
                }
            )
    repeated.sort(key=lambda r: r["event_count"], reverse=True)

    top_category = by_category.most_common(1)[0][0] if by_category else "etc"

    return {
        "total_event_count": len(events),
        "confirmed_alarm_count": by_status.get("confirmed", 0),
        "need_review_event_count": by_status.get("need_review", 0),
        "false_positive_count": by_status.get("false_positive", 0),
        "event_counts": {
            "fire": by_category.get("fire", 0),
            "smoke": by_category.get("smoke", 0),
            "falldown": by_category.get("falldown", 0),
            "etc": by_category.get("etc", 0),
        },
        "main_event_category": top_category,
        "repeated_cameras": repeated,
    }
