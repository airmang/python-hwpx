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


@pytest.mark.parametrize(("zone", "rows", "to", "expected", "order"), [
    ("A1:A3", 0, 2, (0, 2), ["1", "0", "2", "3"]),      # reordered inside a zone over all three
    ("A1:A2", 0, 2, (0, 1), ["1", "0", "2", "3"]),      # two rows swapped inside their zone
    ("A1:A3", [1, 2], 0, (0, 2), ["1", "2", "0", "3"]),  # a block moved to the zone's top
    ("A2:A4", 3, 1, (1, 3), ["0", "3", "1", "2"]),      # the zone's last row to its first
])
def test_rows_reordered_inside_one_zone_keep_it_whole(zone: str, rows, to: int, expected, order) -> None:
    document, table = _table(4)
    table.add_cell_zone(zone, border_fill_id_ref=1)
    table.move_rows(rows, to=to)
    reopened = HwpxDocument.open(document.to_bytes()).tables[0]
    [moved] = reopened.cell_zones
    assert (moved.row, moved.end_row) == expected
    assert [reopened.cell(i, 0).text for i in range(4)] == order


@pytest.mark.parametrize(("zone", "rows", "to"), [
    ("A2:A3", 0, 2),   # a row moved into the zone's middle
    ("A3:A4", 3, 0),   # one of its rows taken out
    ("A1:A3", [1, 2], 4),
])
def test_a_zone_whose_rows_would_no_longer_be_one_run_is_refused(zone: str, rows, to: int) -> None:
    document, table = _table(4)
    table.add_cell_zone(zone, border_fill_id_ref=1)
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        table.move_rows(rows, to=to)
    assert refused.value.code == "table-rows-split-cell-zone"
    assert document.to_bytes() == before


@pytest.mark.parametrize(("zone", "rows", "to", "covered"), [
    ("A3:A4", 3, 0, ["2", "3"]),        # copies in front of the zone push it down
    ("A1:A3", 0, 2, ["0", "1", "0", "2"]),  # copies inside it: the zone grows over them, as insert_rows grows it
    ("A1:A2", 3, 2, ["0", "1"]),        # copies just after it: the zone stays
    ("A2", 0, 0, ["1"]),               # the zone keeps its row, not the copy now standing there
])
def test_copied_rows_move_the_zones_after_them(zone: str, rows, to: int, covered: list[str]) -> None:
    document, table = _table(4)
    table.add_cell_zone(zone, border_fill_id_ref=1)
    table.copy_rows(rows, to=to)
    reopened = HwpxDocument.open(document.to_bytes()).tables[0]
    [kept] = reopened.cell_zones
    assert [reopened.cell(i, 0).text for i in range(kept.row, kept.end_row + 1)] == covered
