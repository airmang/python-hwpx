"""``table.insert_rows``/``insert_columns`` put in empty rows and columns by default, as Hangul does.

Owner decision 2026-11-16: 6.x copied the reference row's content by default (a row inserted under a
heading row repeated the heading). Hangul's own row and column insertion leaves the new cells empty:
the Hangul-saved files ``tests/fixtures/hancom_saved/table_insert_row_*``/``table_insert_column_*`` are
3x3 tables whose reference cells hold text ("r1c0" ...) and whose inserted cells hold none. The new
cells keep the reference cell's format -- cell properties, border and fill, margins, size, sub-list
attributes and the first paragraph's paragraph and character shape -- and hold one empty paragraph
without a line layout cache. ``copy_content=True`` keeps the 6.x copy; the 6.x ``blank=`` names it.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxTypeError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _table(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))


def _cells_at(table: etree._Element, *, row: int | None = None, col: int | None = None) -> list[etree._Element]:
    found = []
    for tc in table.iter(HP + "tc"):
        if next(tc.iterancestors(HP + "tbl")) is not table:
            continue
        address = tc.find(HP + "cellAddr")
        if (row is None or address.get("rowAddr") == str(row)) and (col is None or address.get("colAddr") == str(col)):
            found.append(tc)
    return found


def _shape(tc: etree._Element) -> str:
    """The cell's XML without what Hangul writes and we leave to it: paragraph ids, the line layout cache, and
    the form of an empty run (Hangul writes ``<hp:run charPrIDRef="1"/>``, or no run for character shape 0)."""

    xml = etree.tostring(tc, encoding="unicode")
    xml = re.sub(r'\sxmlns:\w+="[^"]*"', "", xml)
    xml = re.sub(r'(<hp:p\b[^>]*?)\sid="\d+"', r"\1", xml)
    xml = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", xml, flags=re.S)
    xml = re.sub(r'<hp:run charPrIDRef="(\d+)"><hp:t/></hp:run>', r'<hp:run charPrIDRef="\1"/>', xml)
    return xml.replace('<hp:run charPrIDRef="0"/>', "")


ROW_CASES = [
    # (base, Hangul's result, reference row, side, the new row)
    ("table_insert_row_formats_row1_base", "table_insert_row_formats_row1_below", 1, "below", 2),
    ("table_insert_row_formats_row1_base", "table_insert_row_formats_row1_above", 1, "above", 1),
    ("table_insert_row_base", "table_insert_row_below_count1", 1, "below", 2),
    ("table_insert_row_tall_row1_base", "table_insert_row_tall_row1_below", 1, "below", 2),
    ("table_insert_row_vmerge_c1r01_base", "table_insert_row_vmerge_c1r01_from00_below", 0, "below", 1),
    ("table_insert_row_hmerge_r1c01_base", "table_insert_row_hmerge_r1c01_from12_above", 1, "above", 1),
]


@pytest.mark.parametrize(("base", "hancom", "ref", "side", "new"), ROW_CASES)
def test_a_default_row_is_the_empty_row_hangul_inserts(base: str, hancom: str, ref: int, side: str, new: int) -> None:
    document = HwpxDocument.open(str(FIXTURES / f"{base}.hwpx"))
    table = document.tables.all[0]
    assert all(cell.text for cell in table.rows[ref].cells)  # the reference row holds text

    table.insert_rows(ref, side=side)

    ours, theirs = _table(document.to_bytes()), _table((FIXTURES / f"{hancom}.hwpx").read_bytes())
    mine, hangul = _cells_at(ours, row=new), _cells_at(theirs, row=new)
    assert [_shape(tc) for tc in mine] == [_shape(tc) for tc in hangul]
    assert all(not "".join(t.text or "" for t in tc.iter(HP + "t")) for tc in mine)
    assert all(tc.find(f".//{HP}linesegarray") is None for tc in mine)


@pytest.mark.parametrize(("base", "hancom"), [
    ("table_insert_column_formats_base", "table_insert_column_formats_side1"),
    ("table_insert_column_base", "table_insert_column_side1_count1"),
])
def test_a_default_column_is_the_empty_column_hangul_inserts(base: str, hancom: str) -> None:
    document = HwpxDocument.open(str(FIXTURES / f"{base}.hwpx"))
    document.tables.all[0].insert_columns(1)

    ours, theirs = _table(document.to_bytes()), _table((FIXTURES / f"{hancom}.hwpx").read_bytes())
    assert [_shape(tc) for tc in _cells_at(ours, col=2)] == [_shape(tc) for tc in _cells_at(theirs, col=2)]


def _heading_table() -> tuple[HwpxDocument, object]:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3)
    for col in range(3):
        table.cell(0, col).text = f"제목{col}"
        table.cell(1, col).text = f"값{col}"
    table.cell(1, 0).paragraphs[0].add_rectangle(width=2000, height=1000)
    return document, table


def test_a_row_under_the_heading_row_does_not_repeat_the_heading() -> None:
    document, table = _heading_table()
    table.insert_rows(0, 2)
    assert [[table.cell(row, col).text for col in range(3)] for row in range(4)] == [
        ["제목0", "제목1", "제목2"], ["", "", ""], ["", "", ""], ["값0", "값1", "값2"],
    ]
    table.insert_rows(3)  # the row holding a rectangle: no copy of it
    assert len(list(table.element.iter(HP + "rect"))) == 1
    reopened = HwpxDocument.open(document.to_bytes())
    reopened.validate()
    assert reopened.tables[0].row_count == 6


@pytest.mark.parametrize("namespace", [False, True])
def test_copy_content_keeps_the_6x_copy(namespace: bool) -> None:
    document, table = _heading_table()
    if namespace:
        document.tables.insert_rows(table, 1, copy_content=True)
        document.tables.insert_columns(table, 0, copy_content=True)
    else:
        table.insert_rows(1, copy_content=True)
        table.insert_columns(0, copy_content=True)
    assert [table.cell(2, col).text for col in range(4)] == ["값0", "값0", "값1", "값2"]
    assert len(list(table.element.iter(HP + "rect"))) == 4  # row 1's and its copies in the new row and column
    HwpxDocument.open(document.to_bytes()).validate()


def test_the_namespace_inserts_empty_rows_and_columns_too() -> None:
    document, table = _heading_table()
    document.tables.insert_rows(table, 0)
    document.tables.insert_columns(table, 0, side="left")
    assert [table.cell(1, col).text for col in range(4)] == ["", "", "", ""]
    assert [table.cell(row, 0).text for row in range(4)] == ["", "", "", ""]
    assert table.cell(0, 1).text == "제목0"


def test_a_row_inserted_across_a_merged_cell_grows_it_either_way() -> None:
    shapes = {}
    for copy in (False, True):
        document = HwpxDocument.new()
        table = document.add_table(rows=4, cols=3)
        for row in range(4):
            for col in range(3):
                table.cell(row, col).text = f"r{row}c{col}"
        table.merge_cells("A1:A3")  # rows 0-2 of column 0
        table.merge_cells("B4:C4")  # row 3, columns 1-2
        table.insert_rows(1, copy_content=copy)  # across the vertical merge
        table.insert_rows(4, side="above", copy_content=copy)  # beside the horizontal merge
        assert table.cell(0, 0).span == (4, 1)
        assert table.cell(5, 1).span == (1, 2)
        shapes[copy] = [(cell.address, cell.span) for row in table.rows for cell in row.cells]
        texts = {cell.address: cell.text for row in table.rows for cell in row.cells}
        assert texts[(2, 1)] == ("r1c1" if copy else "")
        assert texts[(4, 1)] == ("r3c1\nr3c2" if copy else "")  # above row 3: from its (merged) cells
        assert texts[(0, 0)].startswith("r0c0")
        HwpxDocument.open(document.to_bytes()).validate()
    assert shapes[False] == shapes[True]


def test_inserted_rows_hold_no_line_layout_cache_and_their_holder_loses_its_own() -> None:
    document = HwpxDocument.open(str(FIXTURES / "table_insert_row_formats_row1_base.hwpx"))
    table = document.tables.all[0]
    assert table.paragraph.element.find(HP + "linesegarray") is not None
    table.insert_rows(1, 2)
    saved = _table(document.to_bytes())
    new = _cells_at(saved, row=2) + _cells_at(saved, row=3)
    assert len(new) == 6
    assert all(tc.find(f".//{HP}linesegarray") is None for tc in new)
    assert table.paragraph.element.find(HP + "linesegarray") is None


@pytest.mark.parametrize("call", [
    lambda d, t: t.insert_rows(0, blank=True),
    lambda d, t: t.insert_columns(0, blank=False),
    lambda d, t: d.tables.insert_rows(t, 0, blank=True),
    lambda d, t: d.tables.insert_columns(t, 0, blank=False),
])
def test_the_6x_blank_argument_names_copy_content(call) -> None:
    document, table = _heading_table()
    before = document.to_bytes()
    with pytest.raises(HwpxTypeError) as caught:
        call(document, table)
    assert caught.value.code == "hwpx-argument-removed"
    assert caught.value.context["replacement"] == "copy_content"
    assert "copy_content=True" in str(caught.value)
    assert document.to_bytes() == before
