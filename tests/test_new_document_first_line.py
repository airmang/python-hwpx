# SPDX-License-Identifier: Apache-2.0
"""A document from ``HwpxDocument.new()`` starts with what is added first (7.0)."""
from __future__ import annotations

import io

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    return HwpxDocument.open(buffer.getvalue())


def _texts(doc: HwpxDocument) -> list[str]:
    return [paragraph.text for paragraph in doc.paragraphs]


def test_the_first_paragraph_added_takes_the_empty_first_line() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("첫 줄")
    doc.add_paragraph("둘째 줄")
    assert _texts(doc) == ["첫 줄", "둘째 줄"]
    assert doc.paragraphs[0].element is first.element
    assert _texts(_reopened(doc)) == ["첫 줄", "둘째 줄"]


def test_the_section_settings_move_to_that_paragraph() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 줄")
    section = doc.sections[0].element
    paragraphs = section.findall(f"{HP}p")
    assert len(paragraphs) == 1
    assert len(list(section.iter(f"{HP}secPr"))) == 1
    first_run = paragraphs[0].find(f"{HP}run")
    assert first_run.find(f"{HP}secPr") is not None  # the settings stay first in the document
    assert _reopened(doc).validate().ok


def test_a_heading_takes_the_first_line_too() -> None:
    doc = HwpxDocument.new()
    doc.add_heading("제목", 1)
    doc.add_paragraph("본문")
    assert _texts(doc) == ["제목", "본문"]


def test_a_header_set_first_does_not_keep_the_line_empty() -> None:
    doc = HwpxDocument.new()
    doc.page.set_header(text="머리말")
    doc.page.set_page_number()
    doc.add_paragraph("본문")
    again = _reopened(doc)
    assert _texts(again) == ["본문"]
    assert [place.paragraph.text for place in again.text.paragraphs(where="header")] == ["머리말"]


def test_an_object_added_first_comes_after_the_empty_line() -> None:
    doc = HwpxDocument.new()
    doc.add_table(1, 1)
    doc.add_paragraph("표 뒤")
    assert _texts(doc)[0] == ""
    assert _texts(doc)[-1] == "표 뒤"


def test_a_first_line_written_by_hand_is_left_alone() -> None:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "직접 쓴 첫 줄"
    doc.add_paragraph("둘째 줄")
    assert _texts(doc) == ["직접 쓴 첫 줄", "둘째 줄"]


def test_empty_first_line_keeps_the_6x_behaviour() -> None:
    doc = HwpxDocument.new(empty_first_line=True)
    doc.add_paragraph("첫 줄")
    assert _texts(doc) == ["", "첫 줄"]


def test_an_opened_document_is_never_changed_this_way() -> None:
    buffer = io.BytesIO()
    HwpxDocument.new().save_to_stream(buffer)
    doc = HwpxDocument.open(buffer.getvalue())
    doc.add_paragraph("더한 줄")
    assert _texts(doc) == ["", "더한 줄"]


def test_only_the_first_section_and_only_once() -> None:
    doc = HwpxDocument.new()
    second = doc.add_section()
    doc.add_paragraph("둘째 구역", section=second)
    doc.add_paragraph("첫 구역에 나중에", section=doc.sections[0])
    assert [paragraph.text for paragraph in doc.sections[0].paragraphs] == ["", "첫 구역에 나중에"]
