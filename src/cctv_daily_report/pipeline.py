"""전체 파이프라인 오케스트레이션 (feature_docs §8)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import config
from .event_selector import pick_main
from .mock_data import CctvEvent, build_mock_dataset
from .renderer import render
from .sources import EventSource, MockEventSource
from .statistics import aggregate
from .summarizer import generate_en_block, rule_based_fallback
from .text_utils import clean_block, strip_emoji
from .translator import to_korean
from .vlm import summarize_event


def _build_main_events_payload(
    main_events: list[CctvEvent],
    visual_summaries: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in main_events:
        vs = visual_summaries.get(ev.event_id, {})
        out.append(
            {
                "event_id": ev.event_id,
                "time": ev.event_time,
                "camera_id": ev.camera_id,
                "camera_name": ev.camera_name,
                "category": ev.category,
                "confidence": ev.confidence,
                "status": ev.status,
                "clip_url": ev.clip_url,
                "visual_summary": vs.get("visual_summary", ""),
                "visual_verification": vs.get("visual_verification", "unclear"),
            }
        )
    return out


def run_report(
    report_date: str | None = None,
    output_dir: Path | None = None,
    skip_vlm: bool = False,
    skip_llm: bool = False,
    source: EventSource | None = None,
) -> Path:
    """end-to-end. 생성된 HWPX 파일 경로 반환.

    source 미지정 시 MockEventSource(하드코딩 mock)를 사용한다.
    실데이터 연동 시 EventSource 구현체를 주입한다.
    """
    report_date = report_date or config.today_iso()
    source = source or MockEventSource()
    print(f"[1/7] load dataset for {report_date} via {type(source).__name__}")
    info, events = source.load(report_date)

    print("[2/7] aggregate statistics")
    event_summary = aggregate(events)

    print("[3/7] select main events")
    main_events = pick_main(events, max_n=config.MAX_MAIN_EVENTS)
    print(f"      picked {len(main_events)} main events: " + ", ".join(e.event_id for e in main_events))

    print("[4/7] VLM visual summary")
    visual_summaries: dict[str, dict[str, str]] = {}
    if skip_vlm:
        for ev in main_events:
            visual_summaries[ev.event_id] = {
                "event_id": ev.event_id,
                "visual_summary": "(VLM skipped)",
                "visual_verification": "unclear",
            }
    else:
        for ev in main_events:
            vs = summarize_event(ev)
            visual_summaries[ev.event_id] = vs
            print(f"      {ev.event_id}: {vs['visual_summary'][:80]!r}")

    main_events_payload = _build_main_events_payload(main_events, visual_summaries)

    report_payload: dict[str, Any] = {
        "report_info": {
            "report_date": info.report_date,
            "center_name": info.center_name,
            "start_time": info.start_time,
            "end_time": info.end_time,
            "generated_at": info.generated_at,
        },
        "camera_info": {
            "total_cctv_count": info.total_cctv_count,
            "analyzed_cctv_count": info.analyzed_cctv_count,
        },
        "event_summary": event_summary,
        "main_events": main_events_payload,
        "repeated_cameras": event_summary["repeated_cameras"],
    }

    print("[5/7] LLM English summary")
    if skip_llm:
        report_text_en = rule_based_fallback(report_payload)
    else:
        report_text_en = generate_en_block(report_payload)
    report_text_en = clean_block(report_text_en)
    for k, v in report_text_en.items():
        print(f"      EN/{k}: {v[:100]!r}")

    print("[6/7] translate to Korean")
    if skip_llm:
        report_text_ko = dict(report_text_en)
    else:
        report_text_ko = to_korean(report_text_en)
    report_text_ko = clean_block(report_text_ko)
    for k, v in report_text_ko.items():
        print(f"      KO/{k}: {v[:100]!r}")

    # main_events_payload 안의 visual_summary도 이모지 정리
    for ev in main_events_payload:
        ev["visual_summary"] = strip_emoji(ev.get("visual_summary", ""))

    print("[7/7] render HWPX")
    render_data = {
        "report_info": report_payload["report_info"],
        "camera_info": report_payload["camera_info"],
        "event_summary": report_payload["event_summary"],
        "main_events": main_events_payload,
        "report_text_en": report_text_en,
        "report_text_ko": report_text_ko,
    }
    out_dir = Path(output_dir) if output_dir else config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"CCTV_AI_Daily_Report_{report_date.replace('-', '')}.hwpx"
    final = render(config.TEMPLATE_PATH, output_path, render_data)
    print(f"      saved: {final}")
    return final


def dump_payload(report_date: str | None = None) -> dict[str, Any]:
    """디버그/테스트용: VLM·LLM 호출 없이 mock + 통계만 만들어 반환."""
    report_date = report_date or config.today_iso()
    info, events = build_mock_dataset(report_date)
    main_events = pick_main(events, max_n=config.MAX_MAIN_EVENTS)
    return {
        "info": asdict(info),
        "event_summary": aggregate(events),
        "main_events": [asdict(e) for e in main_events],
    }
