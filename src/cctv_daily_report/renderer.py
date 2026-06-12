"""토큰 기반 HWPX 보고서 렌더링.

베이스 템플릿(report_template_blank.hwpx)에 박힌 {{token}}을 찾아 값으로 치환한다.
문단 인덱스에 의존하지 않으므로 템플릿에 문단이 추가/삭제/이동돼도 토큰만 있으면 동작한다.

토큰 종류
  단일 라인 토큰 (substring 치환, 본문+표/도형 어디서든)
    {{report_date}}              보고 일자       (p13, 날짜 자막 "일일 보고 (...)")
    {{center_name}}              관제센터명      (p23, 표지 표)
    {{event_stats}}              일일 탐지 통계 한 줄
    {{main_events}}              주요 이벤트 1~3 한 줄
    {{daily_summary}}            금일 관제 요약  (본문 + 개요 박스)
    {{main_event_description}}   주요 이벤트 설명
    {{visual_summary}}           VLM 시각 요약 합본
    {{special_note}}             특이사항 + 확인 필요

  다중 라인 토큰 (문단 전체가 토큰과 일치하면 <hp:lineBreak/>로 채움)
    {{basic_info_1}}             보고 일자 / 관제센터
    {{basic_info_2}}             보고 대상 시간
    {{basic_info_3}}             전체 CCTV / 분석 대상 CCTV / 보고서 생성

제목("CCTV AI 탐지 일일 보고서")·부서명("[ AI 관제팀 ]")·섹션 헤더는 템플릿에
literal로 남겨 두고 토큰화하지 않는다(보고서마다 바뀌지 않음).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx import HwpxDocument
from lxml import etree

from .text_utils import strip_emoji

_CATEGORY_KO = {"fire": "화재", "smoke": "연기", "falldown": "쓰러짐", "etc": "기타"}
_STATUS_KO = {
    "confirmed": "확정",
    "need_review": "확인 필요",
    "false_positive": "오탐 의심",
}

# HWPML paragraph 네임스페이스 (hp 접두사)
_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _set_multiline(paragraph, lines: list[str]) -> None:
    """문단을 여러 줄로 채운다. 줄 구분은 <hp:lineBreak/> (Hancom 정식 표현).

    paragraph.text 세터로 첫 줄을 넣어 run/charPr 스타일을 보존한 뒤, 첫 t 노드
    안에 <hp:lineBreak/> + tail 텍스트를 덧붙여 나머지 줄을 표현한다.
    """
    if not lines:
        paragraph.text = ""
        return
    paragraph.text = lines[0]  # 스타일 보존 + run 정리 + mark_dirty
    if len(lines) == 1:
        return
    t_el = next(
        (el for el in paragraph.element.iter() if etree.QName(el).localname == "t"),
        None,
    )
    if t_el is None:
        return
    for line in lines[1:]:
        lb = t_el.makeelement(f"{{{_HP_NS}}}lineBreak", {})
        lb.tail = line
        t_el.append(lb)


def _format_basic_lines(
    info: dict[str, Any], cam: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    return (
        [
            f"- 보고 일자 : {info['report_date']}",
            f"- 관제센터 : {info['center_name']}",
        ],
        [
            f"- 보고 대상 시간 : {info['start_time']} ~ {info['end_time']}",
        ],
        [
            f"- 전체 CCTV : {cam['total_cctv_count']}대",
            f"- 분석 대상 CCTV : {cam['analyzed_cctv_count']}대",
            f"- 보고서 생성 : {info['generated_at']}",
        ],
    )


def _format_stats_line(summary: dict[str, Any]) -> str:
    c = summary["event_counts"]
    return (
        f"전체 탐지 알림 {summary['total_event_count']}건 "
        f"(확정 {summary['confirmed_alarm_count']}, "
        f"확인 필요 {summary['need_review_event_count']}, "
        f"오탐 의심 {summary['false_positive_count']})  "
        f"화재 {c['fire']}, 연기 {c['smoke']}, 쓰러짐 {c['falldown']}, 기타 {c['etc']}"
    )


def _format_main_events_line(main_events: list[dict[str, Any]]) -> str:
    if not main_events:
        return "주요 탐지 이벤트 없음"
    parts: list[str] = []
    for idx, ev in enumerate(main_events, start=1):
        time_only = ev["time"].split(" ", 1)[-1] if " " in ev["time"] else ev["time"]
        cat_ko = _CATEGORY_KO.get(ev["category"], ev["category"])
        status_ko = _STATUS_KO.get(ev["status"], ev["status"])
        parts.append(
            f"{idx}) {time_only} {ev['camera_id']} {ev['camera_name']} - "
            f"{cat_ko} ({status_ko}, 신뢰도 {ev['confidence']:.2f})"
        )
    return "    ".join(parts)


def _format_visual_summary(main_events: list[dict[str, Any]]) -> str:
    parts = []
    for ev in main_events:
        vs = strip_emoji(ev.get("visual_summary", ""))
        if vs:
            parts.append(f"[{ev['camera_id']}] {vs}")
    return "  ".join(parts) if parts else "대표 프레임 시각 요약 없음"


def _format_special_block(text_ko: dict[str, str]) -> str:
    special = strip_emoji(text_ko.get("special_note", "")).strip()
    review = strip_emoji(text_ko.get("review_note", "")).strip()
    if special and review:
        return f"{special}    {review}"
    return special or review or "특이사항 없음"


def _replace_single_tokens(section_element, replacements: dict[str, str]) -> None:
    """모든 t 노드에서 {{token}} 부분문자열을 값으로 치환 (인덱스 비의존).

    토큰이 본문·표·도형 어디에 있든, 한 t 안에 다른 텍스트와 섞여 있든
    (예: "일일 보고 ({{report_date}})") 동작한다.
    """
    for el in section_element.iter():
        if etree.QName(el).localname != "t" or not el.text:
            continue
        text = el.text
        for token, value in replacements.items():
            if token in text:
                text = text.replace(token, value)
        if text != el.text:
            el.text = text


def render(
    template_path: str | Path, output_path: str | Path, render_data: dict[str, Any]
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    info = render_data["report_info"]
    cam = render_data["camera_info"]
    summary = render_data["event_summary"]
    main_events = render_data["main_events"]
    text_ko = render_data["report_text_ko"]

    daily = strip_emoji(text_ko.get("daily_summary", "")) or "관제 요약 정보 없음"
    main_desc = strip_emoji(text_ko.get("main_event_description", "")) or "주요 이벤트 설명 정보 없음"
    basic1, basic2, basic3 = _format_basic_lines(info, cam)

    doc = HwpxDocument.open(template_path)
    section = doc.sections[0]

    # 1) 줄바꿈이 필요한 다중 라인 토큰: 문단 텍스트가 토큰과 정확히 일치하면
    #    <hp:lineBreak/>로 채운다. (인덱스가 아니라 토큰으로 문단을 찾는다)
    multiline_tokens: dict[str, list[str]] = {
        "{{basic_info_1}}": basic1,
        "{{basic_info_2}}": basic2,
        "{{basic_info_3}}": basic3,
    }
    for paragraph in section.paragraphs:
        lines = multiline_tokens.get(paragraph.text.strip())
        if lines is not None:
            _set_multiline(paragraph, lines)

    # 2) 단일 라인 토큰: 모든 t 노드에서 substring 치환 (본문+표/도형 일괄)
    single_tokens: dict[str, str] = {
        "{{report_date}}": info["report_date"],
        "{{center_name}}": info["center_name"],
        "{{event_stats}}": _format_stats_line(summary),
        "{{main_events}}": _format_main_events_line(main_events),
        "{{daily_summary}}": daily,
        "{{main_event_description}}": main_desc,
        "{{visual_summary}}": _format_visual_summary(main_events),
        "{{special_note}}": _format_special_block(text_ko),
    }
    _replace_single_tokens(section.element, single_tokens)

    section.mark_dirty()
    doc.save_to_path(output_path)
    return output_path
