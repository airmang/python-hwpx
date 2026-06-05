"""feature_docs §4/§9/§12에 명시된 예시 JSON 기반 mock 데이터셋.

실제 시스템에서는 DB·이벤트 로그 조회로 대체한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from . import config

EventCategory = Literal["fire", "smoke", "falldown", "etc"]
EventStatus = Literal["confirmed", "need_review", "false_positive"]


@dataclass(frozen=True)
class CctvEvent:
    event_id: str
    report_date: str
    camera_id: str
    camera_name: str
    event_time: str
    category: EventCategory
    confidence: float
    status: EventStatus
    clip_url: str
    frame_url: str


@dataclass(frozen=True)
class ReportInfo:
    report_date: str
    center_name: str
    start_time: str
    end_time: str
    generated_at: str
    total_cctv_count: int
    analyzed_cctv_count: int


def build_mock_dataset(report_date: str | None = None) -> tuple[ReportInfo, list[CctvEvent]]:
    report_date = report_date or config.today_iso()
    date_tag = report_date.replace("-", "")

    def evt_id(n: int) -> str:
        return f"EVT-{date_tag}-{n:04d}"

    info = ReportInfo(
        report_date=report_date,
        center_name="○○시 CCTV 통합관제센터",
        start_time=f"{report_date} 00:00:00",
        end_time=f"{report_date} 23:59:59",
        generated_at=f"{report_date} 23:59:59",
        total_cctv_count=120,
        analyzed_cctv_count=80,
    )

    events: list[CctvEvent] = []

    # 대표 이벤트 (§9 예시) — CAM-03 본관 출입구, 쓰러짐, need_review, 신뢰도 0.91
    events.append(
        CctvEvent(
            event_id=evt_id(1),
            report_date=report_date,
            camera_id="CAM-03",
            camera_name="본관 출입구",
            event_time=f"{report_date} 14:23:10",
            category="falldown",
            confidence=0.91,
            status="need_review",
            clip_url=f"clips/{evt_id(1)}.mp4",
            frame_url=f"frames/{evt_id(1)}.jpg",
        )
    )

    # 화재 1건 — confirmed
    events.append(
        CctvEvent(
            event_id=evt_id(2),
            report_date=report_date,
            camera_id="CAM-12",
            camera_name="후문 주차장",
            event_time=f"{report_date} 03:11:42",
            category="fire",
            confidence=0.87,
            status="confirmed",
            clip_url=f"clips/{evt_id(2)}.mp4",
            frame_url=f"frames/{evt_id(2)}.jpg",
        )
    )

    # 연기 4건
    smoke_specs = [
        ("CAM-05", "지하주차장 B1", "08:42:13", 0.78, "confirmed"),
        ("CAM-05", "지하주차장 B1", "08:43:09", 0.71, "false_positive"),
        ("CAM-21", "외부 흡연구역", "12:15:55", 0.65, "false_positive"),
        ("CAM-21", "외부 흡연구역", "12:18:02", 0.62, "false_positive"),
    ]
    for i, (cam_id, cam_name, hms, conf, status) in enumerate(smoke_specs, start=3):
        events.append(
            CctvEvent(
                event_id=evt_id(i),
                report_date=report_date,
                camera_id=cam_id,
                camera_name=cam_name,
                event_time=f"{report_date} {hms}",
                category="smoke",
                confidence=conf,
                status=status,  # type: ignore[arg-type]
                clip_url=f"clips/{evt_id(i)}.mp4",
                frame_url=f"frames/{evt_id(i)}.jpg",
            )
        )

    # 쓰러짐 12건 추가 (총 13건). CAM-08 1층 로비에서 7건 반복.
    falldown_specs = [
        ("CAM-08", "1층 로비", "09:01:11", 0.82, "confirmed"),
        ("CAM-08", "1층 로비", "09:04:33", 0.79, "confirmed"),
        ("CAM-08", "1층 로비", "09:08:51", 0.74, "false_positive"),
        ("CAM-08", "1층 로비", "10:22:01", 0.71, "false_positive"),
        ("CAM-08", "1층 로비", "11:15:47", 0.69, "false_positive"),
        ("CAM-08", "1층 로비", "13:02:18", 0.66, "false_positive"),
        ("CAM-08", "1층 로비", "15:44:09", 0.63, "false_positive"),
        ("CAM-14", "체육관 입구", "10:55:33", 0.88, "confirmed"),
        ("CAM-19", "운동장 동측", "16:11:24", 0.81, "need_review"),
        ("CAM-22", "노인복지관 1층", "17:32:50", 0.75, "need_review"),
        ("CAM-27", "도서관 계단", "18:21:17", 0.61, "false_positive"),
        ("CAM-31", "구내식당", "19:09:02", 0.58, "false_positive"),
    ]
    for i, (cam_id, cam_name, hms, conf, status) in enumerate(falldown_specs, start=7):
        events.append(
            CctvEvent(
                event_id=evt_id(i),
                report_date=report_date,
                camera_id=cam_id,
                camera_name=cam_name,
                event_time=f"{report_date} {hms}",
                category="falldown",
                confidence=conf,
                status=status,  # type: ignore[arg-type]
                clip_url=f"clips/{evt_id(i)}.mp4",
                frame_url=f"frames/{evt_id(i)}.jpg",
            )
        )

    # 합계 검증: fire 1, smoke 4, falldown 13, etc 0 → 총 18
    assert len(events) == 18, len(events)
    return info, events
