# SPDX-License-Identifier: Apache-2.0
"""The empty first line of ``HwpxDocument.new()`` keeps its element when a paragraph takes it.

A paragraph object taken before the first ``add_paragraph`` (``first = doc.paragraphs[0]``)
used to point at an element removed from the document: text written through it vanished.
"""
from __future__ import annotations

import io

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    return HwpxDocument.open(buffer.getvalue())


def test_text_written_through_a_held_first_paragraph_is_saved() -> None:
    doc = HwpxDocument.new()
    first = doc.paragraphs[0]
    doc.add_paragraph("본문 첫 줄")
    first.text = "제목"
    doc.add_paragraph("둘째 줄")
    assert [p.text for p in _reopened(doc).paragraphs] == ["제목", "둘째 줄"]


def test_the_added_paragraph_and_the_held_one_are_the_same_element() -> None:
    doc = HwpxDocument.new()
    held = doc.paragraphs[0]
    added = doc.add_paragraph("첫 줄")
    assert added.element is held.element
    assert doc.paragraphs[0].element is held.element
    assert len(doc.sections[0].element.findall(f"{HP}p")) == 1


def test_the_added_paragraphs_shape_and_style_move_in() -> None:
    doc = HwpxDocument.new()
    held = doc.paragraphs[0]
    added = doc.add_paragraph("가운데", para_pr_id_ref=3, style=2, char_pr_id_ref=1)
    assert held.element.get("paraPrIDRef") == "3"
    assert held.element.get("styleIDRef") == "2"
    assert added.element.find(f"{HP}run/{HP}t") is not None
    text_run = next(run for run in held.element.findall(f"{HP}run") if run.find(f"{HP}t") is not None)
    assert text_run.get("charPrIDRef") == "1"


def test_the_section_settings_stay_first_and_the_line_cache_goes() -> None:
    doc = HwpxDocument.new()
    held = doc.paragraphs[0]
    doc.add_paragraph("첫 줄")
    first_run = held.element.find(f"{HP}run")
    assert first_run.find(f"{HP}secPr") is not None
    assert held.element.find(f"{HP}linesegarray") is None
    assert _reopened(doc).validate().ok


def test_a_heading_binds_its_outline_level_on_the_kept_element() -> None:
    doc = HwpxDocument.new()
    held = doc.paragraphs[0]
    heading = doc.add_heading("제목", 1)
    assert heading.element is held.element
    style = doc.styles.resolve("개요 1")
    assert held.element.get("styleIDRef") == str(style.id)
    assert held.element.get("paraPrIDRef") == heading.element.get("paraPrIDRef")
    again = _reopened(doc)
    assert again.paragraphs[0].text == "제목"
    assert again.paragraphs[0].element.get("styleIDRef") == str(style.id)
