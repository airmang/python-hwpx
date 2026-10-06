"""Deleting rows or columns moves the table's cell zones (``hp:cellzone``) with their cells.

A zone gives the cells it covers a border fill, and Hangul draws it: a zone left where it was after the
rows above it went would draw its borders on other cells. A zone keeps the lines it covers that stay,
moved back over the deleted ones before it, and goes when none of them stays; the zone list goes with
its last zone, as OWPML wants at least one in it.
"""

from __future__ import annotations

import re

from hwpx.table_patch import _delete_columns, _delete_rows

ZONE = re.compile(r'startRowAddr="(\d+)" startColAddr="(\d+)" endRowAddr="(\d+)" endColAddr="(\d+)"')


def _table(zones: list[tuple[int, int, int, int]], rows: int = 4, cols: int = 4) -> str:
    listed = "".join(
        f'<hp:cellzone startRowAddr="{r0}" startColAddr="{c0}" endRowAddr="{r1}" endColAddr="{c1}" '
        f'borderFillIDRef="{7 + index}"/>'
        for index, (r0, c0, r1, c1) in enumerate(zones)
    )
    cells = "".join(
        "<hp:tr>" + "".join(
            f'<hp:tc borderFillIDRef="3"><hp:subList><hp:p id="{10 * row + col + 1}"><hp:run charPrIDRef="0">'
            f"<hp:t>{row}{col}</hp:t></hp:run></hp:p></hp:subList>"
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="1000" height="500"/></hp:tc>'
            for col in range(cols)
        ) + "</hp:tr>"
        for row in range(rows)
    )
    zone_list = f"<hp:cellzoneList>{listed}</hp:cellzoneList>" if zones else ""
    return (
        f'<hp:tbl rowCnt="{rows}" colCnt="{cols}"><hp:sz width="{1000 * cols}" height="{500 * rows}"/>'
        f"{zone_list}{cells}</hp:tbl>"
    )


def _zones(table: str) -> list[tuple[int, ...]]:
    return [tuple(int(value) for value in found) for found in ZONE.findall(table)]


def test_deleting_rows_moves_shrinks_and_drops_zones() -> None:
    table = _table([(0, 0, 0, 3), (1, 0, 2, 0), (2, 1, 3, 1), (3, 2, 3, 3)])

    after = _delete_rows(table, [1])

    assert _zones(after) == [(0, 0, 0, 3), (1, 0, 1, 0), (1, 1, 2, 1), (2, 2, 2, 3)]
    assert _zones(_delete_rows(table, [1, 2])) == [(0, 0, 0, 3), (1, 1, 1, 1), (1, 2, 1, 3)]


def test_deleting_columns_moves_shrinks_and_drops_zones() -> None:
    table = _table([(0, 0, 3, 0), (0, 1, 0, 2), (1, 2, 1, 3), (2, 3, 3, 3)])

    assert _zones(_delete_columns(table, [1])) == [(0, 0, 3, 0), (0, 1, 0, 1), (1, 1, 1, 2), (2, 2, 3, 2)]
    assert _zones(_delete_columns(table, [3])) == [(0, 0, 3, 0), (0, 1, 0, 2), (1, 2, 1, 2)]


def test_the_zone_list_goes_with_its_last_zone() -> None:
    table = _table([(1, 0, 1, 3)])

    after = _delete_rows(table, [1])

    assert "cellzone" not in after
    assert 'rowCnt="3"' in after


def test_a_table_without_zones_is_unchanged_but_for_the_deleted_lines() -> None:
    table = _table([])

    assert "cellzone" not in _delete_rows(table, [0])
    assert "cellzone" not in _delete_columns(table, [0])
