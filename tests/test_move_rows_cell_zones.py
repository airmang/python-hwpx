"""A cell zone (hp:cellzone) follows the rows table.move_rows moves, as it does when rows are deleted; a
zone that would come apart is refused (exec7/rv-ranges)."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError


def _table(rows: int):
    document = HwpxDocument.new()
    table = document.add_table(rows, 1)
    for index in range(rows):
        table.cell(index, 0).text = str(index)
    return document, table


@pytest.mark.parametrize(("zone", "rows", "to", "expected"), [
    ("A1", 0, 2, (1, 1)),        # the first row to the end
    ("A3", 2, 0, (0, 0)),        # the last row to the front
    ("A2", 0, 3, (0, 0)),        # a row that does not move shifts up
    ("A1:A2", [0, 1], 3, (1, 2)),  # a zone over the whole moved block
])
def test_a_cell_zone_follows_its_rows(zone: str, rows, to: int, expected: tuple[int, int]) -> None:
    document, table = _table(3)
    table.add_cell_zone(zone, border_fill_id_ref=1)
    table.move_rows(rows, to=to)
    [moved] = HwpxDocument.open(document.to_bytes()).tables[0].cell_zones
    assert (moved.row, moved.end_row) == expected


def test_a_zone_over_moved_and_staying_rows_is_refused() -> None:
    document, table = _table(3)
    table.add_cell_zone("A1:A2", border_fill_id_ref=1)
    with pytest.raises(HwpxValueError) as refused:
        table.move_rows(0, to=3)
    assert refused.value.code == "table-rows-split-cell-zone"
    assert [table.cell(i, 0).text for i in range(3)] == ["0", "1", "2"]
