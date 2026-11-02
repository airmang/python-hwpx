# SPDX-License-Identifier: Apache-2.0
"""Row, column, cell and table edits on a table whose cells hold tables."""
from __future__ import annotations

import re

import pytest

from hwpx.document import HwpxDocument
from hwpx.table_patch import apply_table_ops, build_grid, iter_table_spans, section_parts

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _source(depth=2):
    document = HwpxDocument.new()
    outer = document.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            outer.cell(row, col).text = f"outer:{row}:{col}"
    inner = outer.cell(1, 1).add_table(2, 2)
    for row in range(2):
        for col in range(2):
            inner.cell(row, col).text = f"inner:{row}:{col}"
    if depth == 3:
        inner.cell(1, 1).add_table(1, 1).cell(0, 0).text = "deepest"
    return document.to_bytes()


def _tables(data):
    section = section_parts(data)["Contents/section0.xml"]
    return [section[start:end] for start, end in iter_table_spans(section)]


def _apply(source, *ops):
    result = apply_table_ops(source, [dict(op, table_index=op.get("table_index", 0)) for op in ops])
    return result


def _outer_texts(data):
    with HwpxDocument.open(data) as document:
        table = document.tables[0]
        return {(cell.address[0], cell.address[1]): cell for cell in []} or [
            [table.cell(r, c).text.split("\n")[0] for c in range(table.column_count)] for r in range(table.row_count)
        ]


def _assert_nested_kept(source, result, copies=1):
    assert not result.skipped, [s.reason for s in result.skipped]
    nested = _tables(source)[1]
    after = _tables(result.data)
    assert sum(t == nested for t in after) == copies
    for table in after:
        assert build_grid(table)[1].ok
    with HwpxDocument.open(result.data):
        pass


@pytest.mark.parametrize("op, layout", [
    ({"op": "delete_row", "row": 0}, [["outer:1:0", "outer:1:1", "outer:1:2"], ["outer:2:0", "outer:2:1", "outer:2:2"]]),
    ({"op": "delete_column", "col": 2}, [["outer:0:0", "outer:0:1"], ["outer:1:0", "outer:1:1"], ["outer:2:0", "outer:2:1"]]),
    ({"op": "reorder_rows", "order": [1, 0, 2]}, [["outer:1:0", "outer:1:1", "outer:1:2"], ["outer:0:0", "outer:0:1", "outer:0:2"], ["outer:2:0", "outer:2:1", "outer:2:2"]]),
    ({"op": "insert_row_by_clone", "ref_row": 0}, None),
    ({"op": "insert_column_by_clone", "ref_col": 0}, None),
    ({"op": "insert_row_by_clone", "ref_row": 1, "blank": True}, None),
    ({"op": "insert_column_by_clone", "ref_col": 1, "blank": True}, None),
    ({"op": "set_row_heights", "heights": {1: 5000}}, None),
    ({"op": "autofit_columns"}, None),
    ({"op": "split_cell", "row": 1, "col": 1, "rows": 2}, None),
])
def test_structure_edit_keeps_the_nested_table_byte_for_byte(op, layout):
    source = _source()
    result = _apply(source, op)
    _assert_nested_kept(source, result)
    if layout is not None:
        assert _outer_texts(result.data) == layout


def test_deleting_the_row_of_the_holding_cell_drops_its_nested_table():
    source = _source()
    result = _apply(source, {"op": "delete_row", "row": 1})
    assert not result.skipped
    assert len(_tables(result.data)) == 1
    assert _outer_texts(result.data) == [["outer:0:0", "outer:0:1", "outer:0:2"], ["outer:2:0", "outer:2:1", "outer:2:2"]]


@pytest.mark.parametrize("op, new_cell", [
    ({"op": "insert_row_by_clone", "ref_row": 1, "count": 2}, [(2, 1), (3, 1)]),
    ({"op": "insert_column_by_clone", "ref_col": 1}, [(1, 2)]),
])
@pytest.mark.parametrize("depth", [2, 3])
def test_cloning_a_holding_cell_copies_its_nested_table_with_fresh_ids(op, new_cell, depth):
    source = _source(depth=depth)
    result = _apply(source, op)
    _assert_nested_kept(source, result)
    section = section_parts(result.data)["Contents/section0.xml"].decode("utf-8")
    paragraph_ids = re.findall(r'<hp:p\b[^>]*\bid="(\d+)"', section)
    table_ids = re.findall(r'<hp:tbl\b[^>]*\bid="(\d+)"', section)
    assert len(table_ids) == len(set(table_ids)) == len(_tables(source)) * (1 + len(new_cell)) - len(new_cell)
    assert len(paragraph_ids) == len(set(paragraph_ids))
    with HwpxDocument.open(result.data) as document:
        table = document.tables[0]
        for row, col in [(1, 1), *new_cell]:
            inner = table.cell(row, col).tables[0]
            assert [inner.cell(r, c).text for r in range(2) for c in range(2)][:3] == ["inner:0:0", "inner:0:1", "inner:1:0"]
            if depth == 3:
                assert inner.cell(1, 1).tables[0].cell(0, 0).text == "deepest"


def test_cloning_a_nested_table_copies_its_bookmark_and_rectangle_as_hancom_pastes_them():
    document = HwpxDocument.new()
    outer = document.add_table(2, 2)
    inner = outer.cell(1, 1).add_table(1, 1)
    inner.cell(0, 0).paragraphs[0].add_bookmark("mark")
    inner.cell(0, 0).paragraphs[0].add_rectangle(width=1000, height=500)
    source = document.to_bytes()
    result = _apply(source, {"op": "insert_row_by_clone", "ref_row": 1})
    assert result.ok, result.skipped
    with HwpxDocument.open(result.data) as reopened:
        copies = [reopened.tables[0].cell(row, 1).tables[0].cell(0, 0) for row in (1, 2)]
        rects = [next(cell.element.iter(f"{_HP}rect")) for cell in copies]
        assert len({rect.get(name) for rect in rects for name in ("id", "instid")}) == 3
        assert [next(cell.element.iter(f"{_HP}bookmark")).get("name") for cell in copies] == ["mark", "mark"]


def test_blank_clone_of_a_holding_row_adds_empty_cells_without_the_nested_table():
    source = _source()
    result = _apply(source, {"op": "insert_row_by_clone", "ref_row": 1, "blank": True})
    _assert_nested_kept(source, result)
    with HwpxDocument.open(result.data) as document:
        table = document.tables[0]
        assert table.row_count == 4
        assert table.cell(2, 1).text == "" and not table.cell(2, 1).tables
        assert table.cell(1, 1).tables


def test_a_holding_cell_never_becomes_narrower_than_its_nested_table():
    source = _source()
    with HwpxDocument.open(source) as document:
        widths = [document.tables[0].cell(0, c).width for c in range(3)]
    narrow = {0: widths[0] + widths[1] - 500, 1: 500, 2: widths[2]}
    result = _apply(source, {"op": "set_column_widths", "widths": narrow})
    assert result.data == source and "narrower" in result.skipped[0].reason
    wide = {0: widths[0] - 500, 1: widths[1] + 500, 2: widths[2]}
    _assert_nested_kept(source, _apply(source, {"op": "set_column_widths", "widths": wide}))
    split = _apply(source, {"op": "split_cell", "row": 1, "col": 1, "cols": 2})
    assert split.data == source and "narrower" in split.skipped[0].reason


def test_autofit_holds_a_column_at_its_nested_table_width():
    document = HwpxDocument.new()
    table = document.add_table(2, 6)
    for row in range(2):
        for col in range(6):
            table.cell(row, col).text = "긴 내용 " * 6 if col == 5 else f"{row}{col}"
    table.cell(0, 0).add_table(1, 4)
    source = document.to_bytes()
    result = _apply(source, {"op": "autofit_columns"})
    _assert_nested_kept(source, result)
    with HwpxDocument.open(source) as before, HwpxDocument.open(result.data) as after:
        assert after.tables[0].cell(0, 0).width >= before.tables[0].cell(0, 0).width
        assert after.tables[0].cell(0, 5).width > before.tables[0].cell(0, 5).width


def test_edits_on_a_middle_table_keep_the_deepest_one():
    source = _source(depth=3)
    result = _apply(source, {"op": "insert_row_by_clone", "ref_row": 0, "table_index": 1})
    assert not result.skipped
    tables = _tables(result.data)
    assert _tables(source)[2] in tables
    with HwpxDocument.open(result.data) as document:
        inner = document.tables[0].cell(1, 1).tables[0]
        assert inner.row_count == 3
        assert inner.cell(2, 1).tables[0].cell(0, 0).text == "deepest"


def test_split_and_merge_table_carry_nested_tables():
    source = _source()
    nested = _tables(source)[1]
    split = _apply(source, {"op": "split_table", "split_row": 1})
    assert not split.skipped
    tables = _tables(split.data)
    assert len(tables) == 3 and nested in tables
    with HwpxDocument.open(split.data) as document:
        assert [t.row_count for t in document.tables] == [1, 2]
        assert document.tables[1].cell(0, 1).tables
    merged = _apply(split.data, {"op": "merge_table"})
    assert not merged.skipped, [s.reason for s in merged.skipped]
    with HwpxDocument.open(merged.data) as document:
        assert len(document.tables) == 1 and document.tables[0].row_count == 3
        assert document.tables[0].cell(1, 1).tables[0].cell(1, 1).text == "inner:1:1"
    assert nested in _tables(merged.data)
