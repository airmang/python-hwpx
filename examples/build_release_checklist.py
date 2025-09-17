#!/usr/bin/env python
"""Generate an HWPX document exercising memo and style-editing features."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HH = f"{{{HH_NS}}}"
HPX_SOURCE = Path(__file__).with_name("FormattingShowcase.hwpx")
OUTPUT_PATH = Path(__file__).with_name("ReleaseChecklist.hwpx")


def ensure_memo_shapes(header: "HwpxOxmlHeader") -> None:
    """Add a pair of memo shape definitions if they are missing."""

    ref_list = header.element.find(f"{HH}refList")
    if ref_list is None:
        ref_list = ET.SubElement(header.element, f"{HH}refList")

    memo_props = ref_list.find(f"{HH}memoProperties")
    if memo_props is None:
        memo_props = ET.SubElement(ref_list, f"{HH}memoProperties", {"itemCnt": "0"})

    desired_shapes = {
        "0": {
            "width": "14000",
            "lineWidth": "0.6mm",
            "lineType": "SOLID",
            "lineColor": "#4F81BD",
            "fillColor": "#EEF4FB",
            "activeColor": "#DDE8F7",
            "memoType": "NORMAL",
        },
        "5": {
            "width": "16000",
            "lineWidth": "0.6mm",
            "lineType": "DOT",
            "lineColor": "#C0504D",
            "fillColor": "#FDE9E9",
            "activeColor": "#F6D8D8",
            "memoType": "NORMAL",
        },
    }

    updated = False
    for memo_id, attrs in desired_shapes.items():
        existing = memo_props.find(f"{HH}memoPr[@id='{memo_id}']")
        if existing is not None:
            continue
        ET.SubElement(memo_props, f"{HH}memoPr", {"id": memo_id, **attrs})
        updated = True

    if updated:
        count = len(list(memo_props.findall(f"{HH}memoPr")))
        memo_props.set("itemCnt", str(count))
        header.mark_dirty()


def ensure_underlined_char_property(header: "HwpxOxmlHeader") -> str:
    """Clone an existing character property and make it underlined."""

    ref_list = header.element.find(f"{HH}refList")
    if ref_list is None:
        raise RuntimeError("header is missing <refList>")

    char_props = ref_list.find(f"{HH}charProperties")
    if char_props is None:
        raise RuntimeError("header does not expose charProperties")

    underline_id = "50"
    existing = char_props.find(f"{HH}charPr[@id='{underline_id}']")
    if existing is not None:
        return underline_id

    base = char_props.find(f"{HH}charPr[@id='10']")
    if base is None:
        raise RuntimeError("cannot find base charPr with id=10 to clone")

    underlined = deepcopy(base)
    underlined.set("id", underline_id)
    underlined.set("textColor", "#1F4E79")

    underline = underlined.find(f"{HH}underline")
    if underline is None:
        underline = ET.SubElement(underlined, f"{HH}underline")
    underline.set("type", "SOLID")
    underline.set("color", "#1F4E79")

    char_props.append(underlined)
    char_props.set("itemCnt", str(len(list(char_props))))
    header.mark_dirty()

    return underline_id



def build_checklist(document: HwpxDocument, underline_char_id: str) -> None:
    """Populate the document with paragraphs, memos, and style edits."""

    section = document.sections[0]

    _heading = document.add_paragraph(
        "릴리스 최종 점검",
        section=section,
        para_pr_id_ref=1,
        style_id_ref=1,
    )
    _intro = document.add_paragraph(
        "메모와 스타일 편집 기능이 적용된 QA 확인용 문서입니다.",
        section=section,
        char_pr_id_ref=0,
    )

    todo = document.add_paragraph(
        "TODO: 통합 테스트 결과 정리",
        section=section,
        char_pr_id_ref=10,
    )
    signoff = document.add_paragraph(
        "Draft: 문서 배포 전 QA 서명을 수집하세요.",
        section=section,
        char_pr_id_ref=underline_char_id,
    )

    document.add_memo_with_anchor(
        "데이터 차트 수치를 2024년 4분기 기준으로 갱신하세요.",
        paragraph=todo,
        memo_shape_id_ref="0",
        memo_id="release-memo-1",
        char_pr_id_ref="10",
        attributes={"author": "PM", "visible": "always"},
        field_id="7001",
        created="2024-12-02 09:00:00",
        number=1,
        anchor_char_pr_id_ref="10",
    )

    document.add_memo_with_anchor(
        "QA 서명은 12월 15일까지 완료되어야 합니다.",
        paragraph=signoff,
        memo_shape_id_ref="5",
        memo_id="release-memo-2",
        char_pr_id_ref=underline_char_id,
        attributes={"author": "QA Lead", "priority": "high"},
        field_id="7002",
        created="2024-12-02 09:30:00",
        number=2,
        anchor_char_pr_id_ref=underline_char_id,
    )

    # Apply style-aware replacements to verify the transformation APIs.
    document.replace_text_in_runs("TODO", "DONE", text_color="#C00000")
    document.replace_text_in_runs("Draft: ", "", underline_type="SOLID")


def main() -> None:
    document = HwpxDocument.open(HPX_SOURCE)
    header = document.headers[0]

    ensure_memo_shapes(header)
    underline_char_id = ensure_underlined_char_property(header)

    # Refresh cached style information after mutating the header.
    document.oxml.invalidate_char_property_cache()

    build_checklist(document, underline_char_id)

    document.save(OUTPUT_PATH)
    print(f"Generated {OUTPUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
