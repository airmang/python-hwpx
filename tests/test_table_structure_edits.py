"""Row, column and cell structure edits on the table object (``Table.insert_rows`` and the rest).

They run the edits of ``hwpx.table_patch.apply_table_ops`` on the table's XML, so they follow the same
rules: the Hangul-saved files ``tests/fixtures/hancom_saved/table_insert_*`` and ``table_split_cell_*``
(3x3 tables made by Hangul and the same tables after Hangul inserted rows or columns or split a cell) are
matched here through the object model, as the byte path matches them in ``test_insert_column_by_clone``,
``test_insert_row_sides`` and ``test_split_cell``.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.table_patch import TableStructureError, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


@pytest.mark.parametrize("row,col", [(0, 2), (0, -1), (0, 4), (-1, 0), (4, 0)])
def test_row_only_split_requires_an_exact_anchor_without_mutation(row: int, col: int) -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=4, cols=4)
    table.merge_cells("B1:C1")
    before = document.to_bytes()
    with pytest.raises(TableStructureError, match="no cell starts"):
        table.split_cell(row, col, rows=2)
    assert document.to_bytes() == before


@pytest.mark.parametrize("axis", ["rows", "columns"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_native_content_clones_are_refused_but_blank_insertion_preserves_objects(axis: str, side: str) -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).paragraphs[0].add_rectangle(width=2000, height=1000)
    before = document.to_bytes()
    insert = table.insert_rows if axis == "rows" else table.insert_columns
    position = {("rows", "before"): "above", ("rows", "after"): "below",
                ("columns", "before"): "left", ("columns", "after"): "right"}[(axis, side)]

    with pytest.raises(TableStructureError, match="local identities or references"):
        insert(0, 2, side=position)
    assert document.to_bytes() == before
    insert(0, 2, side=position, blank=True)
    rectangles = list(table.element.iter(HP + "rect"))
    assert len(rectangles) == 1
    assert etree.tostring(rectangles[0]) == etree.tostring(next(_table(before).iter(HP + "rect")))
    reopened = HwpxDocument.open(document.to_bytes())
    assert len(list(reopened.tables.all[0].element.iter(HP + "rect"))) == 1


def _table(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))


def _shapes(data: bytes, *, heights: bool = True, spanned_widths: bool = True) -> list[list[tuple]]:
    """Each row's cells as (row, col, rowSpan, colSpan, width, height, border fill, paragraph shape,
    character shape of the first paragraph (0 without a run), text)."""
    rows = []
    for tr in _table(data).findall(HP + "tr"):
        cells = []
        for tc in tr.findall(HP + "tc"):
            addr, span, size = tc.find(HP + "cellAddr"), tc.find(HP + "cellSpan"), tc.find(HP + "cellSz")
            paragraph = tc.find(HP + "subList").find(HP + "p")
            run = paragraph.find(HP + "run")
            col_span = int(span.get("colSpan"))
            cells.append((
                int(addr.get("rowAddr")), int(addr.get("colAddr")), int(span.get("rowSpan")), col_span,
                int(size.get("width")) if spanned_widths or col_span == 1 else None,
                int(size.get("height")) if heights else None,
                tc.get("borderFillIDRef"), paragraph.get("paraPrIDRef"),
                run.get("charPrIDRef") if run is not None else "0",
                "".join(t.text or "" for t in tc.iter(HP + "t")),
            ))
        rows.append(cells)
    return rows


def _edited(fixture: str, edit) -> bytes:
    document = HwpxDocument.open(str(FIXTURES / f"{fixture}.hwpx"))
    edit(document.tables.all[0])
    return document.to_bytes()


CASES = [
    # (base, Hangul's result, edit, compare heights, compare widths of cells over several columns)
    ("table_insert_column_base", "table_insert_column_side1_count3",
     lambda t: t.insert_columns(1, 3, blank=True), True, True),
    ("table_insert_column_base", "table_insert_column_side0_count1",
     lambda t: t.insert_columns(1, side="left", blank=True), True, True),
    ("table_insert_column_merge_r0c12_base", "table_insert_column_merge_r0c12_side1",
     lambda t: t.insert_columns(1, blank=True), True, False),
    ("table_insert_column_vmerge_c1r01_base", "table_insert_column_vmerge_c1r01_side1",
     lambda t: t.insert_columns(1, blank=True), True, True),
    ("table_insert_column_formats_base", "table_insert_column_formats_side1",
     lambda t: t.insert_columns(1, blank=True), True, True),
    ("table_insert_row_base", "table_insert_row_above_count1",
     lambda t: t.insert_rows(1, side="above", blank=True), True, True),
    ("table_insert_row_tall_row1_base", "table_insert_row_tall_row1_below",
     lambda t: t.insert_rows(1, blank=True), True, True),
    ("table_insert_row_vmerge_c1r01_base", "table_insert_row_vmerge_c1r01_from00_below",
     lambda t: t.insert_rows(0, blank=True), True, True),
    ("table_insert_row_hmerge_r1c01_base", "table_insert_row_hmerge_r1c01_from12_above",
     lambda t: t.insert_rows(1, side="above", blank=True), True, True),
    ("table_insert_row_formats_row1_base", "table_insert_row_formats_row1_below",
     lambda t: t.insert_rows(1, blank=True), True, True),
    ("table_split_cell_base", "table_split_cell_c3", lambda t: t.split_cell(1, 1, cols=3), True, True),
    ("table_split_cell_merge_r0c12_base", "table_split_cell_merge_r0c12_c3",
     lambda t: t.split_cell(0, 1, cols=3), True, True),
    ("table_split_cell_tall_row1_base", "table_split_cell_tall_row1_r2_distribute",
     lambda t: t.split_cell(1, 1, rows=2), True, True),
    ("table_split_cell_base", "table_split_cell_r2c2", lambda t: t.split_cell(1, 1, rows=2, cols=2), False, True),
    ("table_split_cell_vmerge_c1r01_base", "table_split_cell_vmerge_c1r01_r3",
     lambda t: t.split_cell(0, 1, rows=3), False, True),
]


@pytest.mark.parametrize(("base", "hancom", "edit", "heights", "spanned_widths"), CASES)
def test_object_edits_make_what_hancom_makes(base: str, hancom: str, edit, heights: bool, spanned_widths: bool) -> None:
    data = _edited(base, edit)

    expected = (FIXTURES / f"{hancom}.hwpx").read_bytes()
    options = {"heights": heights, "spanned_widths": spanned_widths}
    assert _shapes(data, **options) == _shapes(expected, **options)
    assert _table(data).get("rowCnt") == _table(expected).get("rowCnt")
    assert _table(data).get("colCnt") == _table(expected).get("colCnt")
    assert _table(data).find(HP + "sz").get("width") == _table(expected).find(HP + "sz").get("width")


def _merged_document() -> HwpxDocument:
    document = HwpxDocument.new()
    table = document.add_table(rows=4, cols=4)
    for row in range(4):
        for col in range(4):
            table.cell(row, col).text = f"r{row}c{col}"
    table.merge_cells("B1:C1")
    table.merge_cells("A2:A3")
    return document


@pytest.mark.parametrize(
    ("edit", "op"),
    [
        (lambda t: t.insert_rows(1, 2), {"op": "insert_row_by_clone", "ref_row": 1, "count": 2}),
        (lambda t: t.insert_rows(2, side="above", blank=True),
         {"op": "insert_row_by_clone", "ref_row": 2, "side": "above", "blank": True}),
        (lambda t: t.insert_columns(1), {"op": "insert_column_by_clone", "ref_col": 1}),
        (lambda t: t.insert_columns(0, 2, side="left", blank=True),
         {"op": "insert_column_by_clone", "ref_col": 0, "count": 2, "side": "left", "blank": True}),
        (lambda t: t.delete_rows([1, 3]), {"op": "delete_row", "rows": [1, 3]}),
        (lambda t: t.delete_columns(2), {"op": "delete_column", "cols": [2]}),
        (lambda t: t.split_cell(3, 3, rows=2, cols=3), {"op": "split_cell", "row": 3, "col": 3, "rows": 2, "cols": 3}),
    ],
)
def test_object_edits_match_apply_table_ops(edit, op: dict) -> None:
    source = _merged_document().to_bytes()
    document = HwpxDocument.open(source)
    edit(document.tables.all[0])

    by_bytes = apply_table_ops(source, [{**op, "table_index": 0}])

    assert by_bytes.ok, by_bytes.skipped
    assert _shapes(document.to_bytes()) == _shapes(by_bytes.data)


def test_the_table_reads_its_new_shape_and_the_namespace_edits_it_too() -> None:
    document = _merged_document()
    table = document.tables.all[0]

    table.insert_columns(3, blank=True)
    document.tables.insert_rows(table, 0, side="above", blank=True)
    document.tables.split_cell(table, 4, 0, cols=2)
    document.tables.delete_columns(table, [5])
    document.tables.delete_rows(table, 4)

    assert (table.row_count, table.column_count) == (4, 5)
    assert table.cell(1, 0).text == "r0c0"
    assert table.cell(0, 0).text == ""
    reopened = HwpxDocument.open(document.to_bytes()).tables.all[0]
    assert (reopened.row_count, reopened.column_count) == (4, 5)


def test_new_paragraph_ids_are_unused_anywhere_in_the_document() -> None:
    document = _merged_document()
    document.add_section()
    document.add_paragraph("second section", section_index=1)
    table = document.tables.all[0]

    table.insert_rows(0, 3)
    table.insert_columns(0, 2)
    table.split_cell(0, 0, rows=2, cols=2)

    data = document.to_bytes()
    ids: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"Contents/section\d+\.xml", name):
                ids += re.findall(r'<hp:p\b[^>]*\bid="(\d+)"', archive.read(name).decode("utf-8"))
    assert len(ids) == len(set(ids))


def test_the_paragraph_holding_the_table_loses_its_line_cache() -> None:
    document = HwpxDocument.open(str(FIXTURES / "table_split_cell_base.hwpx"))
    table = document.tables.all[0]
    holder = table.paragraph.element
    assert holder.find(HP + "linesegarray") is not None

    table.split_cell(1, 1, cols=2)

    assert holder.find(HP + "linesegarray") is None


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda t: t.insert_rows(True), "ref_row must be an int"),
        (lambda t: t.insert_columns("1"), "ref_col must be an int"),
        (lambda t: t.delete_rows([]), "names no row"),
        (lambda t: t.delete_rows([0, 1, 2, 3]), "deleting every row"),
        (lambda t: t.delete_columns(range(4)), "deleting every column"),
        (lambda t: t.split_cell(0, 2, cols=2), "no cell starts"),
        (lambda t: t.insert_rows(0, side="left"), "side must be"),
    ],
)
def test_refused_edits_leave_the_table_as_it_was(edit, message: str) -> None:
    document = _merged_document()
    table = document.tables.all[0]
    before = etree.tostring(table.element)

    with pytest.raises(TableStructureError, match=message):
        edit(table)

    assert etree.tostring(table.element) == before


def test_a_table_holding_a_table_is_refused() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).add_table(1, 1)

    with pytest.raises(TableStructureError, match="nested"):
        table.insert_rows(0)
