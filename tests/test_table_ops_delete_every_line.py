"""Deleting every row or every column of a table is refused, as Hangul refuses it.

Hangul does not delete the only column of a one-column table or the only row of a one-row table: the table
stays as it was. ``delete_column`` used to stop on a ``ZeroDivisionError`` there, and ``delete_row`` refused
it for an unrelated reason (the grid it left). Both now point to ``delete_table``.
"""

from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.table_patch import apply_table_ops


def _document(rows: int, cols: int) -> bytes:
    document = HwpxDocument.new()
    table = document.add_table(rows=rows, cols=cols)
    table.cell(0, 0).text = "a"
    return document.to_bytes()


@pytest.mark.parametrize(
    ("rows", "cols", "op"),
    [
        (2, 1, {"op": "delete_column", "col": 0}),
        (2, 3, {"op": "delete_column", "cols": [0, 1, 2]}),
        (1, 2, {"op": "delete_row", "row": 0}),
        (3, 2, {"op": "delete_row", "rows": [2, 0, 1]}),
    ],
)
def test_deleting_every_row_or_column_is_refused(rows: int, cols: int, op: dict) -> None:
    data = _document(rows, cols)

    result = apply_table_ops(data, [{**op, "table_index": 0}])

    assert not result.ok
    assert result.data == data
    assert "would leave no table" in result.skipped[0].reason and "delete_table" in result.skipped[0].reason


def test_deleting_all_but_one_still_works() -> None:
    assert apply_table_ops(_document(2, 3), [{"op": "delete_column", "cols": [0, 1], "table_index": 0}]).ok
    assert apply_table_ops(_document(3, 2), [{"op": "delete_row", "rows": [0, 1], "table_index": 0}]).ok
