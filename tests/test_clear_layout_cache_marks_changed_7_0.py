# SPDX-License-Identifier: Apache-2.0
"""``Paragraph.clear_layout_cache()`` is the call after editing a paragraph through ``.element``.

It drops the line layout caches (the paragraph's and its holders') and marks the paragraph's part
changed, so the edit is saved. Before 7.0 it marked the part only when a cache went, and an
``.element`` edit of a paragraph without a cache was silently not saved: a part nothing marked is
written as it was read.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _open(name: str) -> HwpxDocument:
    return HwpxDocument.open((FIXTURES / f"{name}.hwpx").read_bytes())


def _first_text_node(paragraph):
    return next(node for node in paragraph.element.iter(f"{HP}t") if node.text)


def test_an_element_edit_of_a_paragraph_without_a_cache_is_saved() -> None:
    doc = _open("list_number_level1")  # Hancom saved these paragraphs without a layout cache
    paragraph = next(p for p in doc.paragraphs if p.text)
    assert paragraph.element.find(f"{HP}linesegarray") is None
    _first_text_node(paragraph).text = "XML로 고친 글"

    assert paragraph.clear_layout_cache() == 0

    reopened = HwpxDocument.open(doc.to_bytes())
    assert "XML로 고친 글" in [p.text for p in reopened.paragraphs]
    assert reopened.validate().ok


def test_an_element_edit_of_a_cached_paragraph_drops_the_cache_and_is_saved() -> None:
    doc = _open("pages_number_in_its_own_16pt_shape")
    paragraph = next(p for p in doc.paragraphs if p.text and p.element.find(f"{HP}linesegarray") is not None)
    _first_text_node(paragraph).text = "□ 바꾼 표시"

    assert paragraph.clear_layout_cache() == 1

    reopened = HwpxDocument.open(doc.to_bytes())
    edited = next(p for p in reopened.paragraphs if p.text.startswith("□ 바꾼 표시"))
    assert edited.element.find(f"{HP}linesegarray") is None


def test_a_cell_paragraph_edit_drops_the_table_paragraphs_cache_too() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).paragraphs[0].text = "칸"
    reopened = HwpxDocument.open(doc.to_bytes())
    holder = next(p for p in reopened.paragraphs if p.tables)
    cell_paragraph = holder.tables[0].cell(0, 0).paragraphs[0]
    for target in (holder, cell_paragraph):  # as Hancom saves them: each with its cache
        target.element.append(target.element.makeelement(f"{HP}linesegarray", {}))
    _first_text_node(cell_paragraph).text = "XML로 고친 칸"

    assert cell_paragraph.clear_layout_cache() == 2

    again = HwpxDocument.open(reopened.to_bytes())
    assert next(p for p in again.paragraphs if p.tables).tables[0].cell(0, 0).text == "XML로 고친 칸"


def test_other_sections_stay_as_they_were_read() -> None:
    source = (FIXTURES / "pages_endnotes_at_each_sections_end.hwpx").read_bytes()
    doc = HwpxDocument.open(source)
    paragraph = next(p for p in doc.sections[0].paragraphs if p.text)
    _first_text_node(paragraph).text = "첫 구역만 고침"

    paragraph.clear_layout_cache()

    saved = doc.to_bytes()
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(saved)) as after:
        assert before.read("Contents/section1.xml") == after.read("Contents/section1.xml")
        assert before.read("Contents/section0.xml") != after.read("Contents/section0.xml")
