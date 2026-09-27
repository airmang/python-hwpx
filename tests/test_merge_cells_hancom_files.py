# SPDX-License-Identifier: Apache-2.0
"""``merge_cells`` against the same merges made and saved in Hancom.

The two files in ``fixtures/hancom_saved`` are tables Hancom made, filled (each cell holds
``R<row>C<col>``), merged and saved; author, version and dates are removed. Hancom keeps the
covered cells' paragraphs in reading order and drops the rows a merge leaves without cells, so
merging A1:C2 of 3x3 leaves two rows and merging a whole 2x2 table leaves one cell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _table(document: HwpxDocument):
    return next(table for paragraph in document.paragraphs for table in paragraph.tables)


def _cells(table) -> list[tuple[tuple[int, int], tuple[int, int], list[str]]]:
    """Each cell's address, span and paragraph texts, row by row."""
    return [(cell.address, cell.span, [p.text for p in cell.paragraphs]) for row in table.rows for cell in row.cells]


@pytest.mark.parametrize(
    ("fixture", "rows", "cols", "cells"),
    [("merge_3x3_a1c2.hwpx", 3, 3, "A1:C2"), ("merge_2x2_whole.hwpx", 2, 2, "A1:B2")],
)
def test_merge_cells_leaves_the_table_hancom_saves(fixture: str, rows: int, cols: int, cells: str) -> None:
    hancom = _table(HwpxDocument.open(FIXTURES / fixture))
    table = HwpxDocument.new().add_table(rows, cols)
    for row in range(rows):
        for col in range(cols):
            table.cell(row, col).text = f"R{row}C{col}"

    merged = table.merge_cells(cells)

    assert (table.row_count, table.column_count) == (hancom.row_count, hancom.column_count)
    assert _cells(table) == _cells(hancom)
    # the merged cell is as tall as the rows it covers (the tables' default widths differ)
    assert merged.height == hancom.cell(0, 0).height
