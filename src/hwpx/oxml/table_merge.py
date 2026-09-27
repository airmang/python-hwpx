# SPDX-License-Identifier: Apache-2.0
"""What a cell merge leaves behind in a table's grid.

``HwpxOxmlTable.merge_cells`` calls :func:`collapse_merged_grid` once the merged cell
spans its rectangle. It lives here so that ``table.py`` stays inside the owner-file
line budget.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ._document_primitives import _HP

__all__ = ["collapse_merged_grid"]


def _own_cells(table: ET.Element) -> list[tuple[ET.Element, ET.Element]]:
    """(hp:cellAddr, hp:cellSpan) of the table's own cells (not those of tables inside it)."""
    found = []
    for tc in table.findall(f"{_HP}tr/{_HP}tc"):
        addr, span = tc.find(f"{_HP}cellAddr"), tc.find(f"{_HP}cellSpan")
        if addr is not None and span is not None:
            found.append((addr, span))
    return found


def _shift_cell_zones(table: ET.Element, axis: str, removed: int) -> None:
    """Move the ``hp:cellzone`` rows or columns (*axis* "Row" or "Col") past *removed* back by one."""
    for zone in table.findall(f"{_HP}cellzoneList/{_HP}cellzone"):
        start, end = int(zone.get(f"start{axis}Addr") or 0), int(zone.get(f"end{axis}Addr") or 0)
        start = start - 1 if start > removed else start
        end = max(end - 1 if end >= removed and end > 0 else end, start)
        zone.set(f"start{axis}Addr", str(start))
        zone.set(f"end{axis}Addr", str(end))


def _drop_empty_row(table: ET.Element) -> bool:
    """Remove one ``hp:tr`` left without cells; the cells across it span one row less."""
    rows = table.findall(f"{_HP}tr")
    empty = next((index for index, row in enumerate(rows) if row.find(f"{_HP}tc") is None), None)
    if empty is None:
        return False
    table.remove(rows[empty])
    for addr, span in _own_cells(table):
        row, row_span = int(addr.get("rowAddr") or 0), int(span.get("rowSpan") or 1)
        if row < empty < row + row_span:
            span.set("rowSpan", str(row_span - 1))
        elif row > empty:
            addr.set("rowAddr", str(row - 1))
    table.set("rowCnt", str(len(rows) - 1))
    _shift_cell_zones(table, "Row", empty)
    return True


def _drop_unused_column(table: ET.Element) -> bool:
    """Remove one column boundary no cell starts at; the cells across it span one column less."""
    cells = _own_cells(table)
    starts = {int(addr.get("colAddr") or 0) for addr, _span in cells}
    count = int(table.get("colCnt") or 0)
    unused = next((column for column in range(1, count) if column not in starts), None)
    if unused is None:
        return False
    for addr, span in cells:
        column, col_span = int(addr.get("colAddr") or 0), int(span.get("colSpan") or 1)
        if column < unused < column + col_span:
            span.set("colSpan", str(col_span - 1))
        elif column > unused:
            addr.set("colAddr", str(column - 1))
    table.set("colCnt", str(count - 1))
    _shift_cell_zones(table, "Col", unused)
    return True


def collapse_merged_grid(table: ET.Element) -> None:
    """After a merge, drop the rows it left without cells and the columns no cell
    starts at, as Hancom does (it does not open a table with an empty ``hp:tr``).
    Cell sizes stay, so the merged cell keeps the height and width of what it covers."""
    while _drop_empty_row(table):
        pass
    while _drop_unused_column(table):
        pass
