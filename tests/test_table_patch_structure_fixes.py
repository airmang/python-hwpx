"""table_patch structure ops on tables that real documents often have.

- a table in a paragraph that also holds the section setup (``hp:secPr`` with
  ``hp:pagePr`` / ``hp:pageBorderFill`` before the table),
- a table with a nested table (autofit refuses like the other structure edits),
- a row whose right-hand column is covered by a cell merged down from above,
- deleting the top row of a vertical merge.
"""

from __future__ import annotations

import io

from hwpx.document import HwpxDocument
from hwpx.table_patch import apply_table_ops


def _fill(table, rows: int, cols: int) -> None:
    for row in range(rows):
        for col in range(cols):
            table.cell(row, col).text = f"r{row}c{col}"


def _first_paragraph_table(rows: int = 4, cols: int = 2) -> bytes:
    """A table in the section's first paragraph, after its ``hp:secPr``."""
    doc = HwpxDocument.new()
    _fill(doc.paragraphs[0].add_table(rows, cols), rows, cols)
    doc.add_paragraph("after the table")
    return doc.to_bytes()


def _reopen(result) -> HwpxDocument:
    assert not result.skipped, [skip.reason for skip in result.skipped]
    return HwpxDocument.open(io.BytesIO(result.data))


def test_split_table_in_the_section_setup_paragraph() -> None:
    result = apply_table_ops(_first_paragraph_table(), [{"op": "split_table", "table_index": 0, "split_row": 2}])

    tables = _reopen(result).tables.all
    assert [(t.row_count, t.column_count) for t in tables] == [(2, 2), (2, 2)]
    assert tables[1].cell(0, 0).text == "r2c0"


def test_delete_and_clone_table_in_the_section_setup_paragraph() -> None:
    source = _first_paragraph_table()

    deleted = _reopen(apply_table_ops(source, [{"op": "delete_table", "table_index": 0}]))
    cloned = _reopen(apply_table_ops(source, [{"op": "clone_table", "table_index": 0}]))

    assert deleted.tables.all == []
    assert "after the table" in deleted.text.plain()
    assert [t.row_count for t in cloned.tables.all] == [4, 4]


def test_merge_table_after_a_table_in_the_section_setup_paragraph() -> None:
    doc = HwpxDocument.new()
    _fill(doc.paragraphs[0].add_table(2, 2), 2, 2)
    _fill(doc.add_table(3, 2), 3, 2)

    result = apply_table_ops(doc.to_bytes(), [{"op": "merge_table", "table_index": 0}])

    tables = _reopen(result).tables.all
    assert [(t.row_count, t.column_count) for t in tables] == [(5, 2)]


def test_autofit_refuses_a_table_with_a_nested_table() -> None:
    # the nested table is narrower than the outer one
    doc = HwpxDocument.new()
    table = doc.add_table(2, 6)
    _fill(table, 2, 6)
    _fill(table.cell(0, 0).add_table(1, 4), 1, 4)

    result = apply_table_ops(doc.to_bytes(), [{"op": "autofit_columns", "table_index": 0}])

    assert [skip.reason for skip in result.skipped] == [
        "autofit_columns: nested tables are unsupported for structure edits"
    ]


def test_delete_column_when_rows_below_a_merge_miss_the_last_column() -> None:
    # row 0: A1:B1 merged + C1; column C merged down over all three rows, so
    # rows 1 and 2 hold one-column cells for A and B only
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    doc.tables.merge_cells(table, "A1:B1")
    doc.tables.merge_cells(table, "C1:C3")

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_column", "table_index": 0, "col": 2}])

    (after,) = _reopen(result).tables.all
    assert (after.row_count, after.column_count) == (3, 2)
    assert after.cell(1, 1).text == "r1c1"


def test_delete_row_moves_a_vertical_merge_down() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    merged = doc.tables.merge_cells(table, "A1:A2")
    merged.text = "merged"
    height = merged.height

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_row", "table_index": 0, "row": 0}])

    (after,) = _reopen(result).tables.all
    assert (after.row_count, after.column_count) == (2, 3)
    cell = after.cell(0, 0)
    assert cell.text == "merged"
    assert cell.address == (0, 0)
    assert cell.span == (1, 1)
    assert cell.height < height
    assert [after.cell(0, col).text for col in (1, 2)] == ["r1c1", "r1c2"]
    assert [after.cell(1, col).text for col in range(3)] == ["r2c0", "r2c1", "r2c2"]


def test_delete_row_below_the_top_of_a_merge_still_shrinks_it() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    doc.tables.merge_cells(table, "A1:A2").text = "merged"

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_row", "table_index": 0, "row": 1}])

    (after,) = _reopen(result).tables.all
    assert after.row_count == 2
    assert after.cell(0, 0).text == "merged"
    assert after.cell(0, 0).span == (1, 1)
