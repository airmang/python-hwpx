# SPDX-License-Identifier: Apache-2.0
"""How a table shares out its width and height among its cells, and a cell's inner margins.

The bodies of ``HwpxOxmlTable.set_column_widths``, ``equalize_column_widths`` and
``equalize_row_heights``, and of ``HwpxOxmlTableCell.margins`` / ``set_margins``. They
live here so that ``table.py`` stays inside the owner-file line budget; the table methods
keep their documentation and delegate, and the two cell members are these functions
assigned as class attributes.
"""

from __future__ import annotations

from dataclasses import replace
from math import lcm
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from ..objects.results import CellMargins
from ._document_primitives import (
    _HP,
    _clear_paragraph_layout_cache,
    _distribute_size,
    _element_local_name,
)

if TYPE_CHECKING:
    from .table import HwpxOxmlTable, HwpxOxmlTableCell, HwpxTableGridPosition

__all__ = [
    "cell_margins",
    "equalize_column_widths",
    "equalize_row_heights",
    "set_cell_margins",
    "set_column_widths",
]

_MARGIN_SIDES = ("left", "right", "top", "bottom")


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


def _is_blank_placeholder(cell: "HwpxOxmlTableCell") -> bool:
    return cell.width == 0 and cell.height == 0 and not any(t.text for t in cell.element.iter(f"{_HP}t"))


def _follow_covering_cells(
    table: "HwpxOxmlTable",
    grid: dict[tuple[int, int], "HwpxTableGridPosition"],
    edges: dict[int, tuple[int, int]],
    column: dict[int, int],
) -> None:
    """Give each zero-size placeholder inside a merged area its own new column under the cell covering it.

    The placeholders of one row under one covering cell take that cell's new columns left to right
    (in the covering cell's own row, the columns after its first one). A blank placeholder left
    without a column there is removed: Hancom writes no cell under a merged cell at all.
    """

    groups: dict[tuple[int, int], list[tuple[Any, "HwpxOxmlTableCell", "HwpxOxmlTableCell", Any]]] = {}
    for row in table.rows:
        for placeholder in row.cells:
            addr = placeholder._addr_element()
            if id(placeholder.element) in edges or addr is None:
                continue
            covering = grid.get(placeholder.address)
            if covering is not None and id(covering.cell.element) in edges:
                key = (id(row.element), id(covering.cell.element))
                groups.setdefault(key, []).append((row.element, covering.cell, placeholder, addr))
    for members in groups.values():
        row_element, covering_cell, first_placeholder, _addr = members[0]
        left, right = edges[id(covering_cell.element)]
        first, end = column[left], column[right]
        if first_placeholder.address[0] == covering_cell.address[0]:
            first += 1
        members.sort(key=lambda member: member[2].address[1])
        for index, (_row, _covering, placeholder, addr) in enumerate(members):
            if first + index < end:
                addr.set("colAddr", str(first + index))
            elif _is_blank_placeholder(placeholder):
                row_element.remove(placeholder.element)
            else:
                addr.set("colAddr", str(end - 1))


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


def cell_margins(cell: "HwpxOxmlTableCell") -> CellMargins:
    """The inner margins Hancom lays this cell out with, in HWPUNIT.

    The table's ``hp:inMargin`` applies unless the cell's ``hasMargin`` is
    on (``"1"``/``"true"``); then the cell's own ``hp:cellMargin`` does.
    A missing ``hasMargin`` is off: the OWPML schema declares it
    ``xs:boolean`` with ``default="false"`` on ``hp:tc`` (ParaList XML
    schema, ``DevDoc/OWPML SCHEMA/ParaList XML schema.xml``).

    When the chosen element is missing the other one is used: a cell with
    ``hasMargin`` on but no ``hp:cellMargin`` reads the table's
    ``hp:inMargin``, and a table without ``hp:inMargin`` reads the cell's
    ``hp:cellMargin``. A cell with neither reads as zero margins.
    """
    own = cell.element.find(f"{_HP}cellMargin")
    inherited = cell.table.element.find(f"{_HP}inMargin")
    if (cell.element.get("hasMargin") or "").strip().lower() in {"1", "true"}:
        source = own if own is not None else inherited
    else:
        source = inherited if inherited is not None else own
    if source is None:
        return CellMargins(0, 0, 0, 0)
    return CellMargins(*(int(source.get(side, "0") or 0) for side in _MARGIN_SIDES))


def set_cell_margins(
    cell: "HwpxOxmlTableCell",
    *,
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
) -> CellMargins:
    """Give this cell its own inner margins and return them.

    Sides left as ``None`` keep their current effective value (see
    :attr:`margins`). All four are written to the cell's ``hp:cellMargin``
    and ``hasMargin`` is turned on, so the table margin no longer applies.
    When the effective margins change, the cached line layout
    (``hp:linesegarray``) of the paragraphs directly in this cell's
    ``hp:subList`` is dropped so Hancom re-breaks their lines; nested
    tables keep theirs, since their own cell widths do not change. With no
    arguments nothing changes. A value that is not an ``int`` in
    ``0 <= value < 2**31`` is refused before anything changes.
    """
    from ..errors import HwpxValueError

    requested = {"left": left, "right": right, "top": top, "bottom": bottom}
    given = {side: value for side, value in requested.items() if value is not None}
    for side, value in given.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
            raise HwpxValueError(
                f"cell margin {side} must be an int in 0 <= value < 2**31 (HWPUNIT), got {value!r}",
                code="cell-margin-value",
                context={"side": side, "value": repr(value)},
                suggestion="Pass a non-negative int in HWPUNIT (1 mm = 283.465 HWPUNIT).",
            )
    before = cell_margins(cell)
    if not given:
        return before
    margins = replace(before, **given)
    own = cell.element.find(f"{_HP}cellMargin")
    if own is None:
        own = cell.element.makeelement(f"{_HP}cellMargin", {})
        preceding = [
            index
            for index, child in enumerate(cell.element)
            if _element_local_name(child) in {"subList", "cellAddr", "cellSpan", "cellSz"}
        ]
        cell.element.insert(preceding[-1] + 1 if preceding else len(cell.element), own)
    for side in _MARGIN_SIDES:
        own.set(side, str(getattr(margins, side)))
    cell.element.set("hasMargin", "1")
    sublist = cell.element.find(f"{_HP}subList")
    if margins != before and sublist is not None:
        for paragraph in sublist.findall(f"{_HP}p"):
            _clear_paragraph_layout_cache(paragraph)
    cell.table.mark_dirty()
    return margins
