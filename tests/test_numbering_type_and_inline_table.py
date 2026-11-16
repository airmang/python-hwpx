"""``obj.numbering_type`` / ``table.numbering_type`` are written as given; a table set inline or
floating drops the line layout cache of the paragraph holding it."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    return reopened


@pytest.mark.parametrize("value", ["NONE", "PICTURE", "TABLE", "EQUATION"])
def test_a_shape_counts_in_the_numbering_it_is_given(value: str) -> None:
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_ellipse(2000, 2000, treat_as_char=True)
    shape.numbering_type = value
    assert shape.element.get("numberingType") == value
    reopened = _reopened(doc)
    assert [s.numbering_type for s in reopened.paragraphs[-1].shapes] == [value]


def test_a_table_is_taken_out_of_table_numbering() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    assert table.numbering_type == "TABLE"
    table.numbering_type = "NONE"
    assert _reopened(doc).tables.all[0].numbering_type == "NONE"


@pytest.mark.parametrize("value", ["picture", "FIGURE", "", None, 1])
def test_other_values_are_refused(value: object) -> None:
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_rectangle(1000, 1000)
    before = shape.numbering_type
    with pytest.raises(HwpxValueError) as caught:
        shape.numbering_type = value  # type: ignore[assignment]
    assert caught.value.code == "shape-numbering-type-value"
    assert shape.numbering_type == before  # unchanged


def test_setting_numbering_type_drops_the_holding_paragraphs_cache() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_table_cell_picture_first.hwpx")
    table = doc.tables.all[0]
    holder = table.paragraph
    assert holder.element.find(f"{HP}linesegarray") is not None  # Hancom saved one
    table.numbering_type = "NONE" if table.numbering_type != "NONE" else "TABLE"
    assert holder.element.find(f"{HP}linesegarray") is None
    _reopened(doc)


def test_setting_the_same_numbering_type_changes_nothing() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_table_cell_picture_first.hwpx")
    table = doc.tables.all[0]
    table.numbering_type = table.numbering_type
    assert table.paragraph.element.find(f"{HP}linesegarray") is not None
    assert not table.paragraph.section.dirty


def test_an_inline_table_made_floating_drops_the_holding_paragraphs_cache() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_table_cell_picture_first.hwpx")
    table = doc.tables.all[0]
    holder = table.paragraph.element
    assert holder.find(f"{HP}linesegarray") is not None
    table.set_treat_as_char(not table.treat_as_char)
    assert holder.find(f"{HP}linesegarray") is None
    _reopened(doc)


def test_a_new_table_in_a_cell_is_made_inline_and_unsplit_in_two_lines() -> None:
    doc = HwpxDocument.new()
    outer = doc.add_table(1, 1)
    inner = outer.cell(0, 0).paragraphs[0].add_table(2, 2)
    inner.set_treat_as_char(True)
    inner.page_split = "NONE"
    equation = outer.cell(0, 0).paragraphs[0].add_equation("a over b")
    reopened = _reopened(doc)
    nested = reopened.tables.all[0].cell(0, 0).tables[0]
    assert (nested.treat_as_char, nested.page_split) == (True, "NONE")
    assert type(equation).__name__ == "HwpxOxmlEquation"
