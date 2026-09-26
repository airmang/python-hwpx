# SPDX-License-Identifier: Apache-2.0
"""How a table shares out its width and height among its cells.

The bodies of ``HwpxOxmlTable.set_column_widths``, ``equalize_column_widths`` and
``equalize_row_heights``. They live here so that ``table.py`` stays inside the owner-file
line budget; the table methods keep their documentation and delegate.
"""

from __future__ import annotations

from math import lcm
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from ._document_primitives import _HP, _distribute_size

if TYPE_CHECKING:
    from .table import HwpxOxmlTable, HwpxOxmlTableCell, HwpxTableGridPosition

__all__ = ["equalize_column_widths", "equalize_row_heights", "set_column_widths"]


def set_column_widths(table: "HwpxOxmlTable", weights: Sequence[int | float]) -> None:
    if len(weights) != table.column_count:
        raise ValueError("column width weights must match table column count")
    numeric_weights = [max(float(weight), 0.0) for weight in weights]
    if not any(numeric_weights):
        raise ValueError("at least one column width weight must be positive")

    sz = table.element.find(f"{_HP}sz")
    if sz is not None and sz.get("width", "").isdigit():
        total_width = int(sz.get("width", "0"))
    else:
        total_width = sum(table.cell(0, col).width for col in range(table.column_count))
    weight_total = sum(numeric_weights)
    column_widths: list[int] = []
    allocated = 0
    for index, weight in enumerate(numeric_weights):
        if index == len(numeric_weights) - 1:
            width = max(total_width - allocated, 0)
        else:
            width = round(total_width * weight / weight_total)
            allocated += width
        column_widths.append(width)

    updated_cells: set[int] = set()
    for entry in table.iter_grid():
        marker = id(entry.cell.element)
        if marker in updated_cells:
            continue
        updated_cells.add(marker)
        start_row, start_col = entry.cell.address
        span_row, span_col = entry.cell.span
        if span_row <= 0 or span_col <= 0:
            continue
        width = sum(column_widths[start_col:start_col + span_col])
        entry.cell.set_size(width=width)


def _rows_of_cells(entries: Iterator["HwpxTableGridPosition"], row_count: int) -> list[list["HwpxOxmlTableCell"]]:
    """The distinct cells crossing each row, left to right; a merged cell once per row it spans."""

    rows: list[list["HwpxOxmlTableCell"]] = [[] for _ in range(row_count)]
    for entry in entries:
        cells = rows[entry.row]
        if not cells or cells[-1].element is not entry.cell.element:
            cells.append(entry.cell)
    return [cells for cells in rows if cells]


def _equal_cell_edges(
    rows: list[list["HwpxOxmlTableCell"]], total: int
) -> tuple[dict[int, tuple[int, int]], dict[int, "HwpxOxmlTableCell"]]:
    """Left and right edge of every cell when each row splits *total* evenly among its cells."""

    from ..errors import HwpxValueError

    edges: dict[int, tuple[int, int]] = {}
    anchors: dict[int, "HwpxOxmlTableCell"] = {}
    for cells in rows:
        width = total // len(cells)
        for index, cell in enumerate(cells):
            span = (index * width, (index + 1) * width)
            if edges.setdefault(id(cell.element), span) != span:
                row_index, col_index = cell.address
                raise HwpxValueError(
                    f"cell ({row_index}, {col_index}) spans rows that would give it different widths",
                    context={"row": row_index, "column": col_index},
                    suggestion="split the merged cell first, or set widths with set_column_widths()",
                )
            anchors[id(cell.element)] = cell
    return edges, anchors


def _place_cell(cell: "HwpxOxmlTableCell", first_column: int, end_column: int, width: int) -> None:
    addr = cell._addr_element()
    if addr is not None:
        addr.set("colAddr", str(first_column))
    cell.set_span(cell.span[0], end_column - first_column)
    if cell.width != width:
        cell.set_size(width=width)
        cell._clear_own_layout_caches()


def _follow_covering_cells(
    table: "HwpxOxmlTable",
    grid: dict[tuple[int, int], "HwpxTableGridPosition"],
    edges: dict[int, tuple[int, int]],
    column: dict[int, int],
) -> None:
    """Move each zero-size placeholder inside a merged area to the new column of the cell covering it."""

    for row in table.rows:
        for placeholder in row.cells:
            if id(placeholder.element) in edges:
                continue
            covering = grid.get(placeholder.address)
            addr = placeholder._addr_element()
            if covering is not None and addr is not None and id(covering.cell.element) in edges:
                addr.set("colAddr", str(column[edges[id(covering.cell.element)][0]]))


def _zone_moves(
    table: "HwpxOxmlTable",
    anchors: dict[int, "HwpxOxmlTableCell"],
    edges: dict[int, tuple[int, int]],
    column: dict[int, int],
) -> list[tuple[Any, int, int]]:
    """The new ``startColAddr``/``endColAddr`` of each ``hp:cellzone``, so that it
    covers the same cells on the new column grid. A zone whose cells no longer
    form a rectangle there is refused, and the table is left as it is."""

    from ..errors import HwpxValueError

    zones = table.element.findall(f"{_HP}cellzoneList/{_HP}cellzone")
    if not zones:
        return []
    cells = []  # (marker, first row, last row, old first col, old last col, new first col, new last col)
    for marker, cell in anchors.items():
        row, col = cell.address
        row_span, col_span = cell.span
        left, right = edges[marker]
        cells.append((marker, row, row + row_span - 1, col, col + col_span - 1, column[left], column[right] - 1))
    moves = []
    for zone in zones:
        top, first, bottom, last = (int(zone.get(name) or 0) for name in
                                    ("startRowAddr", "startColAddr", "endRowAddr", "endColAddr"))
        rows = [c for c in cells if c[1] <= bottom and c[2] >= top]
        inside = {c[0] for c in rows if c[3] <= last and c[4] >= first}
        new_first = min((c[5] for c in rows if c[0] in inside), default=0)
        new_last = max((c[6] for c in rows if c[0] in inside), default=-1)
        if not inside or {c[0] for c in rows if c[5] <= new_last and c[6] >= new_first} != inside:
            raise HwpxValueError(
                f"cell zone ({top}, {first})-({bottom}, {last}) cannot cover the same cells on the new column grid",
                code="table-cell-zone-grid-mismatch",
                context={"startRowAddr": top, "startColAddr": first, "endRowAddr": bottom, "endColAddr": last},
                suggestion="remove or narrow the cell zone first, or set widths with set_column_widths()",
            )
        moves.append((zone, new_first, new_last))
    return moves


def equalize_column_widths(table: "HwpxOxmlTable") -> None:
    grid = table._build_cell_grid()
    rows = _rows_of_cells(table.iter_grid(), table.row_count)
    if not rows:
        return
    sz = table.element.find(f"{_HP}sz")
    total = max(sum(cell.width for cell in cells) for cells in rows)
    if total <= 0 and sz is not None and sz.get("width", "").isdigit():
        total = int(sz.get("width", "0"))
    if total <= 0:
        return
    step = lcm(*(len(cells) for cells in rows))
    total = -(-total // step) * step
    edges, anchors = _equal_cell_edges(rows, total)

    bounds = sorted({edge for span in edges.values() for edge in span})
    column = {edge: index for index, edge in enumerate(bounds)}
    zones = _zone_moves(table, anchors, edges, column)
    _follow_covering_cells(table, grid, edges, column)
    for marker, (left, right) in edges.items():
        _place_cell(anchors[marker], column[left], column[right], right - left)
    for zone, first, last in zones:
        zone.set("startColAddr", str(first))
        zone.set("endColAddr", str(last))
    table.element.set("colCnt", str(len(bounds) - 1))
    if sz is not None:
        sz.set("width", str(total))
    table.mark_dirty()


def equalize_row_heights(table: "HwpxOxmlTable") -> None:
    sz = table.element.find(f"{_HP}sz")
    if sz is not None and sz.get("height", "").isdigit():
        total_height = int(sz.get("height", "0"))
    else:
        total_height = sum(table.cell(row, 0).height for row in range(table.row_count))
    row_heights = _distribute_size(max(total_height, 0), table.row_count)

    updated_cells: set[int] = set()
    for entry in table.iter_grid():
        marker = id(entry.cell.element)
        if marker in updated_cells:
            continue
        updated_cells.add(marker)
        start_row, start_col = entry.cell.address
        span_row, span_col = entry.cell.span
        if span_row <= 0 or span_col <= 0:
            continue
        height = sum(row_heights[start_row:start_row + span_row])
        entry.cell.set_size(height=height)
