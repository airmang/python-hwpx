# SPDX-License-Identifier: Apache-2.0
"""``set_column_widths([1] * n)`` splits a table width evenly across its grid columns.

This is the split ``equalize_column_widths()`` made before it followed Hancom's
per-row rule, and the call its docstring points to for callers that need it: the
table width ``W`` is kept, the first ``n - 1`` columns get Python ``round(W / n)``
(round half to even) and the last column takes the remainder. A downstream
typesetting engine compares its output byte for byte, so the split is pinned.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def _row_widths(table, row: int = 0) -> list[int]:
    return [table.cell(row, c).width for c in range(table.column_count)]


def _uniform(table) -> None:
    table.set_column_widths([1] * table.column_count)


def test_uniform_weights_give_the_remainder_to_the_last_column() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=7, width=50460)

    _uniform(table)

    assert _row_widths(table, 0) == [7209] * 6 + [7206]
    assert _row_widths(table, 1) == [7209] * 6 + [7206]
    assert table.element.find(f"{HP}sz").get("width") == "50460"


def test_uniform_weights_round_half_to_even() -> None:
    # 2609 / 2 = 1304.5 rounds to 1304 (each column above its 1303 floor)
    document = HwpxDocument.new()
    table = document.add_table(rows=1, cols=2, width=2609)
    assert _row_widths(table) == [1305, 1304]

    _uniform(table)

    assert _row_widths(table) == [1304, 1305]


def test_uniform_weights_give_a_merged_cell_the_sum_of_its_columns() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=7, width=50460)
    table.merge_cells("A1:C1")

    _uniform(table)

    assert table.cell(0, 0).width == 3 * 7209
    assert _row_widths(table, 1) == [7209] * 6 + [7206]


def test_uniform_weights_fall_back_to_the_row_zero_sum_without_a_table_width() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=1, cols=2, width=2609)
    table.element.find(f"{HP}sz").attrib.pop("width")

    _uniform(table)

    assert _row_widths(table) == [1304, 1305]
