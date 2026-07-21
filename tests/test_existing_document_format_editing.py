from __future__ import annotations

import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety


HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = f"{{{HH_NS}}}"
HP = f"{{{HP_NS}}}"


def _mm(value: float) -> int:
    return round(value * 7200 / 25.4)


def _local_name(element: ET.Element) -> str:
    if "}" in element.tag:
        return element.tag.split("}", 1)[1]
    return element.tag


def _descendants(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [
        child
        for child in element.iter()
        if child is not element and _local_name(child) == local_name
    ]


def _para_pr_for_paragraph(document: HwpxDocument, paragraph_index: int) -> ET.Element:
    paragraph = document.paragraphs[paragraph_index]
    para_pr_id = paragraph.para_pr_id_ref
    assert para_pr_id is not None
    para_pr = document.headers[0].element.find(f".//{HH}paraPr[@id='{para_pr_id}']")
    assert para_pr is not None
    return para_pr


def test_set_paragraph_format_uses_human_units_and_survives_save(tmp_path) -> None:
    document = HwpxDocument.new()
    paragraph_index = len(document.paragraphs)
    document.add_paragraph("줄간격 160% 확인")

    result = document.set_paragraph_format(
        paragraph_index=paragraph_index,
        alignment="center",
        line_spacing_percent=160,
        indent_left_mm=10,
        first_line_indent_mm=-3,
        spacing_before_pt=6,
        spacing_after_pt=3,
    )

    assert result["formatted"] == 1
    para_pr = _para_pr_for_paragraph(document, paragraph_index)
    align = para_pr.find(f"{HH}align")
    assert align is not None
    assert align.get("horizontal") == "CENTER"
    line_spacings = _descendants(para_pr, "lineSpacing")
    assert line_spacings
    assert {line_spacing.get("value") for line_spacing in line_spacings} == {"160"}

    margins = _descendants(para_pr, "margin")
    assert margins
    left_values: set[str] = set()
    intent_values: set[str] = set()
    prev_values: set[str] = set()
    next_values: set[str] = set()
    for margin in margins:
        for child in margin:
            value = child.get("value") if child.get("value") is not None else (child.text or "")
            if _local_name(child) == "left":
                left_values.add(value)
            if _local_name(child) == "intent":
                intent_values.add(value)
            if _local_name(child) == "prev":
                prev_values.add(value)
            if _local_name(child) == "next":
                next_values.add(value)
    assert str(_mm(10)) in left_values
    assert str(_mm(-3)) in intent_values
    assert "600" in prev_values
    assert "300" in next_values

    target = tmp_path / "paragraph-format.hwpx"
    document.save_to_path(target)
    assert validate_editor_open_safety(target).ok
    reopened = HwpxDocument.open(target)
    reopened_pr = _para_pr_for_paragraph(reopened, paragraph_index)
    assert reopened_pr.find(f"{HH}align").get("horizontal") == "CENTER"


def test_set_page_setup_header_footer_and_page_number_are_open_safe(tmp_path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")

    page = document.set_page_setup(
        paper_size="A4",
        orientation="landscape",
        margin_left_mm=20,
        margin_right_mm=15,
        margin_top_mm=12,
        margin_bottom_mm=12,
    )
    assert page["pageSize"]["width"] == _mm(297)
    assert page["pageSize"]["height"] == _mm(210)
    assert page["margins"]["left"] == _mm(20)

    header = document.set_header_footer(kind="header", text="Confidential")
    footer = document.set_page_number(target="footer", format="page/total", prefix="Page ")
    assert header.text == "Confidential"
    assert footer.element.find(f".//{HP}ctrl/{HP}pageNum") is not None
    assert "/" in footer.text

    target = tmp_path / "page-setup.hwpx"
    document.save_to_path(target)
    assert validate_editor_open_safety(target).ok
    reopened = HwpxDocument.open(target)
    size = reopened.sections[0].properties.page_size
    margins = reopened.sections[0].properties.page_margins
    assert size.width == _mm(297)
    assert size.height == _mm(210)
    assert margins.left == _mm(20)
    assert reopened.sections[0].properties.get_header().text == "Confidential"


def test_set_list_format_applies_bullet_and_numbered_properties() -> None:
    document = HwpxDocument.new()
    bullet_index = len(document.paragraphs)
    document.add_paragraph("불릿 항목")
    number_index = len(document.paragraphs)
    document.add_paragraph("번호 항목")

    bullet_result = document.set_list_format(
        paragraph_index=bullet_index,
        kind="bullet",
        bullet_char="※",
    )
    number_result = document.set_list_format(
        paragraph_index=number_index,
        kind="number",
        number_format="roman",
        start=3,
    )

    assert bullet_result["formatted"] == 1
    assert number_result["formatted"] == 1
    bullet_pr = _para_pr_for_paragraph(document, bullet_index)
    number_pr = _para_pr_for_paragraph(document, number_index)
    bullet_heading = bullet_pr.find(f"{HH}heading")
    number_heading = number_pr.find(f"{HH}heading")
    assert bullet_heading is not None
    assert bullet_heading.get("type") == "BULLET"
    assert number_heading is not None
    assert number_heading.get("type") == "NUMBER"

    assert document.headers[0].element.find(f".//{HH}bullet[@char='※']") is not None
    numbering_id = number_heading.get("idRef")
    para_head = document.headers[0].element.find(
        f".//{HH}numbering[@id='{numbering_id}']/{HH}paraHead"
    )
    assert para_head is not None
    assert para_head.get("numFormat") == "ROMAN"
    assert para_head.get("start") == "3"
