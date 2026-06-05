"""report_template.hwpx 기반 보고서 렌더링.

template 안의 placeholder들 (사용자가 정리한 새 양식):
  paragraph 단위 (인덱스로 접근 가능)
    13  날짜              "2026-05-11"
    23  관제센터          "○○시 CCTV 통합관제센터"
    24  부서명             "[ AI 관제팀 ]"
    30  헤더              "1. 기본 정보"            (유지)
    31  본문              "-보고 일자 ..."
    32  본문              "-보고 대상 시간 ..."
    33  본문              "-전체 CCTV ..."
    34  헤더              "2. 일일 탐지 현황"        (유지)
    35  본문              "전체 탐지 알림 ..."
    36  헤더              "3. 주요 탐지 이벤트"      (유지)
    37  본문              "1) ... 2) ... 3) ..."
    38  헤더              "4. 금일 관제 요약"        (유지)
    39  본문              "오늘 CCTV 활동은 ..."
    40  헤더              "배경"                    (유지)
    41  본문              "주요 detected 이벤트는 ..."
    43  본문              "[CAM-12] A fire ..."  (visual summary 합본)
    44  헤더              "5. 특이사항 및 확인 필요 사항" (유지)
    45  본문              "특수 주의사항은 ..."

  표 / 도형 안 (paragraph 0, 4, 26, 27 내부 nested 노드 — 내용 비의존 치환)
    표 1×1 sec/p[0]   "○○시 CCTV 통합관제센터"  (정확 일치 → 관제센터명)
    표 5×1 sec/p[4]   제목(정확 일치), "일일 보고 (" 접두 일치 → 날짜 자막
    도형 sec/p[26]    제목(정확 일치)
    표 1×1 sec/p[27]  개요 박스 본문 t 전부 → daily (현재 텍스트와 무관)

  헤더 paragraph(30/34/36/38/40/44)는 그대로 두고 매핑하지 않는다.
  blank/채워진 양식 모두에서 동작하도록 _replace_nested가 직전 데이터에 의존하지 않음.
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

_TITLE = "CCTV AI 탐지 일일 보고서"

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


def _iter_t(paragraph_element):
    for el in paragraph_element.iter():
        if etree.QName(el).localname == "t" and el.text and el.text.strip():
            yield el


def _replace_nested(section_element, *, center_name, title, date_subtitle, daily):
    """표/도형 안 t 노드를 내용 비의존(prefix·위치 기반)으로 치환.

    빈 양식·채워진 양식 어느 쪽이든 동작하도록, 직전 실행 데이터에 의존하지 않는다.
      - 제목 자막  : "CCTV AI 탐지 일일 보고서" 정확 일치 → title
      - 관제센터    : "○○시 CCTV 통합관제센터" 정확 일치 → center_name
      - 날짜 자막   : "일일 보고 (" 로 시작하는 t → date_subtitle
      - 개요 박스   : paragraph 27 내부 본문 t 전부 → daily
    """
    paragraphs = list(section_element)
    for p_idx in (0, 4, 26):
        if p_idx >= len(paragraphs):
            continue
        for el in _iter_t(paragraphs[p_idx]):
            if el.text == title:
                el.text = title
            elif el.text == "○○시 CCTV 통합관제센터":
                el.text = center_name
            elif el.text.startswith("일일 보고 ("):
                el.text = date_subtitle

    # 개요 박스(paragraph 27): 현재 텍스트와 무관하게 본문 t를 daily로 교체
    if 27 < len(paragraphs):
        for el in _iter_t(paragraphs[27]):
            el.text = daily


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

    # 1) paragraph 단위 텍스트 치환 (paragraph.text 세터는 자동 mark_dirty)
    paragraph_replacements: dict[int, str] = {
        13: info["report_date"],
        23: info["center_name"],
        # 24는 "[ AI 관제팀 ]" 그대로 유지 - 매핑 안 함
        35: _format_stats_line(summary),
        37: _format_main_events_line(main_events),
        39: daily,
        41: main_desc,
        43: _format_visual_summary(main_events),
        45: _format_special_block(text_ko),
    }

    for idx, new_text in paragraph_replacements.items():
        if idx < len(section.paragraphs):
            section.paragraphs[idx].text = new_text

    # 1-1) 기본 정보(31/32/33)는 항목별 줄바꿈(<hp:lineBreak/>)으로 채운다
    for idx, lines in ((31, basic1), (32, basic2), (33, basic3)):
        if idx < len(section.paragraphs):
            _set_multiline(section.paragraphs[idx], lines)

    # 2) 표/도형 안 nested t 노드 치환 (lxml 직접 수정 → mark_dirty 필요)
    _replace_nested(
        section.element,
        center_name=info["center_name"],
        title=_TITLE,
        date_subtitle=f"일일 보고 ({info['report_date']})",
        daily=daily,
    )

    section.mark_dirty()
    doc.save_to_path(output_path)
    return output_path
