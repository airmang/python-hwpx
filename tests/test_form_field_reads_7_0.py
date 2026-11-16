# SPDX-License-Identifier: Apache-2.0
"""``FormField.paragraph``, ``end_location`` and ``text_elements`` (7.0).

A 누름틀 read from the document says which paragraph holds it, where its end is and which ``<hp:t>``
hold its text -- what the automation package's blueprint read from the engine's private field
matcher (``_iter_form_field_matches``: ``_paragraph``, ``_end_run_index``, ``_text_nodes``). The
fixtures are files Hancom saved.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.model import Paragraph

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _open(name: str) -> HwpxDocument:
    return HwpxDocument.open((FIXTURES / f"{name}.hwpx").read_bytes())


def _field(doc: HwpxDocument, name: str):
    return next(field for field in doc.fields.all if field.name == name)


def _text(node) -> str:
    parts = [node.text or ""]
    for child in node:
        parts.append("\n" if child.tag == f"{HP}lineBreak" else "\t" if child.tag == f"{HP}tab" else "")
        parts.append(child.tail or "")
    return "".join(parts)


def _control_at(paragraph, location):
    return list(paragraph.runs[location.run_index].element)[location.child_index]


def test_the_paragraph_holding_the_begin() -> None:
    doc = _open("form_fields_spanning_after")
    body = _field(doc, "본문")
    cell = _field(doc, "칸")

    assert isinstance(body.paragraph, Paragraph)
    assert body.paragraph.element is doc.sections[0].paragraphs[body.location.paragraph_index_in_section].element
    assert body.element in list(_control_at(body.paragraph, body.location))
    assert cell.location.paragraph_index_in_section == -1  # a table cell's paragraph
    assert cell.element in list(_control_at(cell.paragraph, cell.location))
    assert "칸 앞" in cell.paragraph.text


def test_the_end_in_the_begins_paragraph() -> None:
    doc = _open("field_value_shape_saved")

    for field in doc.fields.all:
        end = field.end_location
        assert end is not None and field.has_end
        assert (end.section_index, end.paragraph_index) == (field.location.section_index, field.location.paragraph_index)
        ends = list(_control_at(field.paragraph, end).iter(f"{HP}fieldEnd"))
        assert ends and ends[0].get("beginIDRef") == field.element.get("id")
    blue = _field(doc, "파랑")
    assert blue.end_location.run_index == 2  # the end sits two runs after the begin's


def test_the_end_of_a_field_running_over_paragraphs() -> None:
    doc = _open("form_fields_spanning_before")
    body = _field(doc, "본문")
    end = body.end_location

    assert end is not None and end.paragraph_index > body.location.paragraph_index
    holder = doc.sections[0].paragraphs[end.paragraph_index_in_section]
    ends = list(_control_at(holder, end).iter(f"{HP}fieldEnd"))
    assert ends and ends[0].get("beginIDRef") == body.element.get("id")
    cell = _field(doc, "칸")
    assert cell.end_location is not None and cell.end_location.paragraph_index_in_section == -1
    assert cell.end_location.paragraph_index > cell.location.paragraph_index


def test_a_field_without_an_end() -> None:
    field = _field(_open("form_field_no_end_after"), "본문")

    assert field.has_end is False
    assert field.end_location is None
    assert [node.text for node in field.text_elements] == ["첫 줄"]


def test_the_text_elements_hold_the_value() -> None:
    doc = _open("form_field_line_break")
    field = _field(doc, "주소")

    assert all(node.tag == f"{HP}t" for node in field.text_elements)
    assert "".join(_text(node) for node in field.text_elements) == field.value == "서울\n종로구"


def test_an_outer_field_holds_the_inner_fields_text() -> None:
    doc = _open("nested_field_saved")
    outer, inner = _field(doc, "바깥"), _field(doc, "안쪽")

    assert "".join(_text(node) for node in outer.text_elements) == outer.value
    assert inner.text_elements[0] in outer.text_elements


def test_the_text_elements_of_a_field_running_over_paragraphs_follow_on() -> None:
    field = _field(_open("form_fields_spanning_before"), "칸")

    assert [_text(node) for node in field.text_elements] == ["칸 첫 줄", "칸 가운데", "칸 끝 앞"]
    assert field.value == "칸 첫 줄\n칸 가운데\n칸 끝 앞"


def test_an_edit_of_the_text_elements_is_saved_after_clear_layout_cache() -> None:
    doc = _open("field_value_shape_saved")
    field = _field(doc, "같음")

    field.text_elements[0].text = "XML로 쓴 값"
    field.paragraph.clear_layout_cache()

    reopened = HwpxDocument.open(doc.to_bytes())
    assert _field(reopened, "같음").value == "XML로 쓴 값"
    assert reopened.validate().ok


def test_a_filled_field_read_again_names_its_new_text() -> None:
    doc = _open("field_value_shape_saved")
    field = _field(doc, "파랑")

    field.value = "새 파랑"

    again = _field(doc, "파랑")
    assert "".join(_text(node) for node in again.text_elements) == "새 파랑"
    assert again.end_location is not None
    renamed = _field(doc, "굵게")
    renamed.name = "더 굵게"
    assert renamed.paragraph is not None and renamed.end_location is not None
