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
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, overload

from ..objects.results import CellMargins
from ._document_primitives import (
    _HP,
    _clear_paragraph_layout_cache,
    _default_cell_inner_margin_attributes,
    _distribute_size,
    _element_local_name,
)

if TYPE_CHECKING:
    from .table import HwpxOxmlTable, HwpxOxmlTableCell, HwpxTableGridPosition

__all__ = [
    "cell_margins",
    "cell_margins_of",
    "equalize_column_widths",
    "equalize_row_heights",
    "set_cell_margins",
    "effective_cell_margin_source",
    "set_column_widths",
    "grid_widths_of",
    "COLUMN_FLOOR_EXTRA",
    "NEW_TABLE_COLUMN_FLOOR",
    "new_table_width",
    "validate_table_size",
]

_MARGIN_SIDES = ("left", "right", "top", "bottom")
_GRID_TR, _GRID_TC, _GRID_ADDR, _GRID_SPAN, _GRID_SIZE = (
    f"{_HP}{name}" for name in ("tr", "tc", "cellAddr", "cellSpan", "cellSz")
)

#: Hancom draws a table column at least its cells' left and right margins and this wide, the table as much
#: wider (it keeps the narrower width written in the cells).
COLUMN_FLOOR_EXTRA = 283
#: The floor of a new table's column: its cells take the new table's margins (510 left and right).
NEW_TABLE_COLUMN_FLOOR = sum(
    int(_default_cell_inner_margin_attributes()[side]) for side in ("left", "right")
) + COLUMN_FLOOR_EXTRA


#: The most rows or columns one cell may cover: HWP 5.0 keeps a table's row and column counts in 16 bits.
MAX_CELL_SPAN = 65_535
#: The most grid positions the cells of one table may cover together. The largest table among 12,369
#: in 3,269 documents (the fixtures and the documents they were checked against) covers 812.
MAX_TABLE_GRID_POSITIONS = 1_000_000


class GridPositions:
    """Counts the grid positions the cells of one table cover as they are laid out.

    A file gives a cell's span and a table's row and column counts as numbers, and laying a table
    out takes memory for every position those numbers cover: a few bytes of XML can name billions.
    The cell that takes its table past :data:`MAX_TABLE_GRID_POSITIONS` is refused
    (``table-grid-too-large``) before anything is allocated for it."""

    __slots__ = ("left",)

    def __init__(self) -> None:
        self.left = MAX_TABLE_GRID_POSITIONS

    def take(self, rows: int, columns: int) -> None:
        if rows <= 0 or columns <= 0:
            return  # covers nothing
        if rows > MAX_CELL_SPAN or columns > MAX_CELL_SPAN or rows * columns > self.left:
            raise _grid_too_large(rows, columns)
        self.left -= rows * columns


def _grid_too_large(rows: object, columns: object) -> Exception:
    from ..errors import HwpxValueError

    return HwpxValueError(
        f"the table's cells cover more than {MAX_TABLE_GRID_POSITIONS:,} grid positions "
        f"(a cell or the table is given as {rows} rows by {columns} columns)",
        code="table-grid-too-large",
        context={"rows": str(rows)[:40], "columns": str(columns)[:40], "limit": MAX_TABLE_GRID_POSITIONS},
        suggestion="The table's rowSpan/colSpan or rowCnt/colCnt values do not describe a real table.",
    )


def declared_count(value: str) -> int:
    """A table's ``rowCnt`` or ``colCnt`` as a number: at most :data:`MAX_CELL_SPAN`, so that nothing
    sized by it (a list of column widths, a grid) is sized by whatever number the file gives."""

    digits = value.lstrip("0") or "0"  # "0000002" is 2
    if len(digits) > 5 or int(digits) > MAX_CELL_SPAN:
        raise _grid_too_large(value[:40], value[:40])
    return int(digits)


def check_grid(rows: int, columns: int) -> None:
    """Refuse a grid of *rows* by *columns* past :data:`MAX_TABLE_GRID_POSITIONS` before it is laid out."""

    if rows * columns > MAX_TABLE_GRID_POSITIONS:
        raise _grid_too_large(rows, columns)


def validate_table_size(rows: object, cols: object) -> tuple[int, int]:
    """*rows* and *cols* of a new table, checked to be ints of at least 1 (``bool`` refused):
    ``table-size-invalid``, a ``TypeError`` for a wrong type and a ``ValueError`` for less than 1."""

    from ..errors import HwpxTypeError, HwpxValueError

    for name, value in (("rows", rows), ("cols", cols)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise HwpxTypeError(
                f"{name} must be an int, got {type(value).__name__} {value!r}",
                code="table-size-invalid",
                context={"name": name, "value": repr(value)},
                suggestion="Pass the row and column counts as ints, e.g. add_table(2, 3).",
            )
        if value < 1:
            raise HwpxValueError(
                f"{name} must be at least 1, got {value}",
                code="table-size-invalid",
                context={"name": name, "value": value},
                suggestion="A table has at least one row and one column.",
            )
    return rows, cols  # type: ignore[return-value]


@overload
def new_table_width(width: None, cols: int) -> None: ...
@overload
def new_table_width(width: int, cols: int) -> int: ...
def new_table_width(width: object, cols: int) -> int | None:
    """The width a new table of *cols* columns is written at for *width* (``None`` when not given): at least
    :data:`NEW_TABLE_COLUMN_FLOOR` a column, as Hancom draws it. A width that is not an int in
    ``0 < width < 2**31`` is refused."""

    from ..errors import HwpxValueError

    if width is None:
        return None
    if isinstance(width, bool) or not isinstance(width, int) or not 0 < width < 2**31:
        raise HwpxValueError(
            f"width must be an int in 0 < width < 2**31 (HWPUNIT); got {width!r}",
            code="table-width-value",
            context={"value": repr(width)},
            suggestion="Pass the table's width in HWP units, or leave it out to fit the text width.",
        )
    return max(width, cols * NEW_TABLE_COLUMN_FLOOR)


def whole_number(value: Any, *, floats: bool = False) -> int | None:
    """*value* as an ``int`` when it is a whole number: an integer of any kind (``numpy.int64``), or a
    ``Decimal``, a ``Fraction`` or a zero-dimensional array with a whole value -- and a float with one
    when *floats*. ``None`` for anything else (a bool of any kind, a str, NaN); it does not raise."""

    import numbers

    if isinstance(value, bool) or type(value).__name__ in ("bool_", "bool"):
        return None
    if isinstance(value, (str, bytes)) or (
            isinstance(value, numbers.Complex) and not isinstance(value, numbers.Real)):
        return None  # text, and a complex number
    if not floats and isinstance(value, numbers.Real) and not isinstance(value, numbers.Rational):
        return None  # a float (1440.0) is not a height
    # Whatever else counts as a whole number: Decimal("1440"), Fraction(1440), a zero-dimensional
    # array holding one. What cannot be read as a number, or is not whole, is not one.
    number: Any = value
    try:
        whole = int(number)  # a duration (numpy.timedelta64 of days) refuses this
        if isinstance(value, numbers.Integral):
            return whole
        return whole if bool(number == whole) and not isinstance(whole, bool) else None
    except Exception:  # noqa: BLE001 - any refusal of the value's own arithmetic means "not a number"
        return None


def check_new_table_height(height: object) -> int | None:
    """A new table's *height* (``None`` when not given) checked before anything is written, as an
    ``int``: a whole number in ``0 <= height < 2**31``. Anything else was added to the row heights and
    failed there, after the table's border definition (and, in a cell, its paragraph) had been made; a
    ``Decimal("2.00")`` was written as it stood, and the height then could not be read."""

    from ..errors import HwpxValueError

    if height is None:
        return None
    whole = whole_number(height)
    if whole is None or not 0 <= whole < 2**31:
        raise HwpxValueError(
            f"height must be an int in 0 <= height < 2**31 (HWPUNIT); got {height!r}",
            code="table-height-value",
            context={"value": repr(height)},
            suggestion="Pass the table's height in HWP units, or leave it out for the default row height.",
        )
    return whole


def _column_floors(table: "HwpxOxmlTable") -> list[int]:
    """The narrowest Hancom draws each grid column: the widest left and right margins and
    :data:`COLUMN_FLOOR_EXTRA` of its cells one column wide."""

    floors = [0] * table.column_count
    for entry in table.iter_grid():
        if entry.is_anchor and entry.span[1] == 1:
            margins = cell_margins_of(entry.cell.element, table.element)
            sides = 0 if margins is None else margins.left + margins.right
            floors[entry.column] = max(floors[entry.column], sides + COLUMN_FLOOR_EXTRA)
    return floors


def _keeping_nested_fit(edit: Any) -> Any:
    """*edit* (a width edit of a table) refused, the table left as it was, when it leaves a cell
    narrower than the table nested in it (its width plus the cell's side margins) unless the cell
    was already that narrow -- as the byte edits refuse it (:func:`hwpx.table_patch._check_nested_fit`)."""

    from copy import deepcopy
    from functools import wraps

    @wraps(edit)
    def run(table: "HwpxOxmlTable", *args: Any) -> None:
        from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

        from ..table_patch import TableStructureError, _check_nested_fit

        element = table.element
        if element.find(f".//{_HP}tbl") is None:
            return edit(table, *args)
        saved = deepcopy(element)
        before = etree.tostring(element, encoding="unicode", with_tail=False)
        edit(table, *args)
        try:
            _check_nested_fit(before, etree.tostring(element, encoding="unicode", with_tail=False))
        except TableStructureError:
            for child in list(element):
                element.remove(child)
            element.attrib.clear()
            element.attrib.update(saved.attrib)
            element.text = saved.text
            element.extend(list(saved))
            raise
        return None

    return run


@_keeping_nested_fit
def set_column_widths(table: "HwpxOxmlTable", weights: Sequence[int | float]) -> None:
    from ..errors import HwpxValueError

    def refuse(message: str) -> HwpxValueError:
        return HwpxValueError(
            message,
            code="table-column-width-value",
            context={"weights": repr(weights), "columns": table.column_count},
            suggestion=f"Pass {table.column_count} numbers, one per column, at least one of them positive.",
        )

    if isinstance(weights, (str, bytes)) or not isinstance(weights, Sequence):
        raise refuse("column width weights must be a sequence of numbers")
    if len(weights) != table.column_count:
        raise refuse("column width weights must match table column count")
    if any(isinstance(weight, bool) or not isinstance(weight, (int, float)) for weight in weights):
        raise refuse("column width weights must be numbers")
    numeric_weights = [max(float(weight), 0.0) for weight in weights]
    if not any(numeric_weights):
        raise refuse("at least one column width weight must be positive")

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
    # A column narrower than its floor is drawn at the floor and the table that much wider: written so too.
    column_widths = [max(width, floor) for width, floor in zip(column_widths, _column_floors(table))]
    if sz is not None and sum(column_widths) > total_width:
        sz.set("width", str(sum(column_widths)))

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


@_keeping_nested_fit
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


def set_row_heights(table: "HwpxOxmlTable", heights: "Sequence[int]") -> None:
    """Give each row of *table* its height (HWPUNIT) and the table their sum.

    Hancom draws a row at least this tall and taller when its text needs it.
    A cell over several rows takes the sum of their heights.
    """
    from ..errors import HwpxValueError

    values = list(heights)
    if len(values) != table.row_count or any(
        isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**31 for value in values
    ):
        raise HwpxValueError(
            f"heights must be {table.row_count} positive ints (HWPUNIT), one per row; got {values!r}",
            code="table-row-heights-value",
            context={"rows": table.row_count, "heights": [repr(value) for value in values]},
            suggestion="Pass one height in HWP units for each row of the table (1 mm is about 283).",
        )
    seen: set[int] = set()
    for entry in table.iter_grid():
        marker = id(entry.cell.element)
        if marker in seen:
            continue
        seen.add(marker)
        start_row, _start_col = entry.cell.address
        span_row, _span_col = entry.cell.span
        entry.cell.set_size(height=sum(values[start_row:start_row + max(span_row, 1)]))
    sz = table.element.find(f"{_HP}sz")
    if sz is not None:
        sz.set("height", str(sum(values)))
    table.mark_dirty()


def effective_cell_margin_source(
    has_margin: str | None,
    own: Mapping[str, Any] | Any | None,
    inherited: Mapping[str, Any] | Any | None,
) -> Any | None:
    """Pick the margin record a cell is laid out with -- the one rule every reader uses.

    *has_margin* is the cell's ``hasMargin`` attribute, *own* its
    ``hp:cellMargin`` and *inherited* the table's ``hp:inMargin`` (elements
    or attribute mappings; ``None`` when absent). The table margin applies
    unless ``hasMargin`` is on (``"1"``/``"true"``). A missing ``hasMargin``
    is off: the OWPML schema declares it ``xs:boolean`` with
    ``default="false"`` on ``hp:tc`` (``owpml-paralist.xsd``). When the
    chosen record is missing the other one is used; ``None`` when both are.
    """
    if (has_margin or "").strip().lower() in {"1", "true"}:
        return own if own is not None else inherited
    return inherited if inherited is not None else own


def _margin_child(element: Any, local_name: str) -> Any | None:
    if element is None:
        return None
    for child in element:
        if _element_local_name(child) == local_name:
            return child
    return None


def cell_margins_of(cell_element: Any, table_element: Any | None) -> CellMargins | None:
    """The effective inner margins of a raw ``hp:tc`` element, in HWPUNIT.

    For readers that hold elements rather than :class:`HwpxOxmlTableCell`
    (form fit, the layout preview, the template analyzer). *table_element*
    is the ``hp:tbl`` that owns the cell; without it only the cell's own
    ``hp:cellMargin`` can be read. ``None`` when neither margin element
    exists. Children are matched by local name, so stdlib and lxml trees
    both work.
    """
    source = effective_cell_margin_source(
        cell_element.get("hasMargin"),
        _margin_child(cell_element, "cellMargin"),
        _margin_child(table_element, "inMargin"),
    )
    if source is None:
        return None
    return CellMargins(*(_margin_value(source.get(side)) for side in _MARGIN_SIDES))


def grid_widths_of(table_element: Any) -> dict[Any, int]:
    """Each ``hp:tc`` of a raw ``hp:tbl`` element and its width on the table's column grid, as Hancom lays its
    text out (the page estimate and form fit read it). From the left, each column starts at the farthest of the
    ends its cells to the left reach (a cell's start plus its ``hp:cellSz`` width and the table's cell spacing):
    a column is as wide as its widest cell of its own, and a merged cell wider than its columns widens the last
    of them. A cell reaches from its first column's start to its last column's end, wider than its own width
    when another row's cells push those ends apart. Empty for a table whose cells give no column starts to
    stand on."""

    return {cell: width for cell, (_, width) in _grid_extents_of(table_element).items()}


def _grid_extents_of(table_element: Any) -> dict[Any, tuple[int, int]]:
    """Each cell's origin and width on the grid used by :func:`grid_widths_of`."""

    spacing = int(table_element.get("cellSpacing", 0) or 0)
    places: dict[Any, tuple[int, int, int]] = {}  # cell: (first column, column after its last, width)
    for tc in (tc for tr in table_element if tr.tag == _GRID_TR for tc in tr if tc.tag == _GRID_TC):
        # Each cell's children read in one pass, the first of each kind kept (what ``find`` gives).
        address = span = size = None
        for child in tc:
            tag = child.tag
            if tag == _GRID_ADDR:
                address = child if address is None else address
            elif tag == _GRID_SPAN:
                span = child if span is None else span
            elif tag == _GRID_SIZE:
                size = child if size is None else size
        if address is None:
            return {}
        first = int(address.get("colAddr", 0))
        places[tc] = (first, first + (1 if span is None else int(span.get("colSpan", 1))),
                      int(size.get("width", 0)))  # type: ignore[union-attr]  # no hp:cellSz fails as before
    # The cells ending at each column end, gathered once: the cells are walked once, not once per column end.
    ending: dict[int, list[tuple[int, int]]] = {}
    for first, stop, width in places.values():
        ending.setdefault(stop, []).append((first, width))
    starts = {0: 0}
    for end in sorted(ending):
        reach = [starts[first] + width + spacing for first, width in ending[end] if first in starts]
        if not reach:
            return {}
        starts[end] = max(reach)
    return {tc: (starts[first], starts[stop] - starts[first] - spacing)
            for tc, (first, stop, _) in places.items() if first in starts}


def _margin_value(raw: str | None) -> int:
    try:
        return int(raw or 0)
    except ValueError:
        return 0


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
    ``hp:cellMargin``. A cell with neither reads as zero margins. The rule
    itself is :func:`effective_cell_margin_source`, shared with every other
    reader of cell margins in the engine.
    """
    margins = cell_margins_of(cell.element, cell.table.element)
    return margins if margins is not None else CellMargins(0, 0, 0, 0)


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


def table_out_margins(table: "HwpxOxmlTable") -> CellMargins:
    """The table's outer margins (``hp:outMargin``: the room kept around it), in HWPUNIT; zeros when it has none."""

    own = table.element.find(f"{_HP}outMargin")
    if own is None:
        return CellMargins(0, 0, 0, 0)
    return CellMargins(*(_margin_value(own.get(side)) for side in _MARGIN_SIDES))


def set_table_out_margins(
    table: "HwpxOxmlTable",
    *,
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
) -> CellMargins:
    """Set the table's outer margins (``hp:outMargin``, the room between the table and the text
    around it) and return them, as :meth:`HwpxOxmlTableCell.set_margins` sets a cell's.

    Sides left as ``None`` keep their current value. Values are ints in ``0 <= value < 2**31``
    (HWPUNIT, 1 mm = 283.465), checked before anything changes (``table-margin-value``). The
    table's paragraph loses its line layout cache when they change. With no arguments nothing
    changes.
    """
    from ..errors import HwpxValueError

    given = {side: value for side, value in {"left": left, "right": right, "top": top, "bottom": bottom}.items()
             if value is not None}
    for side, value in given.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
            raise HwpxValueError(
                f"table margin {side} must be an int in 0 <= value < 2**31 (HWPUNIT), got {value!r}",
                code="table-margin-value",
                context={"side": side, "value": repr(value)},
                suggestion="Pass a non-negative int in HWPUNIT (1 mm = 283.465 HWPUNIT).",
            )
    before = table_out_margins(table)
    margins = replace(before, **given)
    if not given or margins == before and table.element.find(f"{_HP}outMargin") is not None:
        return before
    own = table.element.find(f"{_HP}outMargin")
    if own is None:
        own = table.element.makeelement(f"{_HP}outMargin", {})
        names = [_element_local_name(child) for child in table.element]
        index = names.index("inMargin") if "inMargin" in names else (names.index("pos") + 1 if "pos" in names else 0)
        table.element.insert(index, own)
    for side in _MARGIN_SIDES:
        own.set(side, str(getattr(margins, side)))
    _clear_paragraph_layout_cache(table.paragraph.element)
    table.mark_dirty()
    return margins


def table_in_margins(table: "HwpxOxmlTable") -> CellMargins:
    """The table's default inner cell margins (``hp:inMargin``), in HWPUNIT; zeros when it has none.
    A cell whose ``hasMargin`` is off is laid out with these (see :attr:`HwpxOxmlTableCell.margins`)."""

    own = table.element.find(f"{_HP}inMargin")
    if own is None:
        return CellMargins(0, 0, 0, 0)
    return CellMargins(*(_margin_value(own.get(side)) for side in _MARGIN_SIDES))


def checked_in_margins(in_margins: "CellMargins | None") -> "CellMargins | None":
    """``add_table(in_margins=)`` checked before the table is made: a :class:`CellMargins` of ints in
    ``0 <= value < 2**31`` (``table-margin-value``)."""

    from ..errors import HwpxValueError

    if in_margins is None:
        return None
    if not isinstance(in_margins, CellMargins) or any(
            isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 2**31
            for v in (in_margins.left, in_margins.right, in_margins.top, in_margins.bottom)):
        raise HwpxValueError(
            f"in_margins must be a CellMargins of ints in 0 <= value < 2**31 (HWPUNIT), got {in_margins!r}",
            code="table-margin-value",
            context={"value": repr(in_margins)},
            suggestion="Pass hwpx.objects.CellMargins(left, right, top, bottom) in HWPUNIT.",
        )
    return in_margins


def with_in_margins(table: "HwpxOxmlTable", margins: "CellMargins | None") -> "HwpxOxmlTable":
    """*table* with the inner margins *margins* set (``add_table(in_margins=)``), when given."""

    if margins is not None:
        table.set_in_margins(left=margins.left, right=margins.right, top=margins.top, bottom=margins.bottom)
    return table


def set_table_in_margins(
    table: "HwpxOxmlTable",
    *,
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
) -> CellMargins:
    """Set the table's default inner cell margins (``hp:inMargin``) and return them, as
    :meth:`set_out_margins` sets the outer ones.

    Sides left as ``None`` keep their value; values are ints in ``0 <= value < 2**31`` (HWPUNIT),
    checked first (``table-margin-value``). Cells with margins of their own (``hasMargin``) keep
    them. A cell laid out with the table's (``hasMargin`` off) gets the same values in its
    ``hp:cellMargin``, as Hancom writes such cells (18,345 of the 18,628 in the 1,257 Hancom-saved
    fixtures). When they change, the paragraphs of the cells laid out with them and the paragraph
    holding the table lose their line layout cache.
    """
    from ..errors import HwpxValueError

    given = {side: value for side, value in {"left": left, "right": right, "top": top, "bottom": bottom}.items()
             if value is not None}
    for side, value in given.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**31:
            raise HwpxValueError(
                f"table inner margin {side} must be an int in 0 <= value < 2**31 (HWPUNIT), got {value!r}",
                code="table-margin-value",
                context={"side": side, "value": repr(value)},
                suggestion="Pass a non-negative int in HWPUNIT (1 mm = 283.465 HWPUNIT).",
            )
    before = table_in_margins(table)
    margins = replace(before, **given)
    if not given or margins == before and table.element.find(f"{_HP}inMargin") is not None:
        return before
    own = table.element.find(f"{_HP}inMargin")
    if own is None:
        own = table.element.makeelement(f"{_HP}inMargin", {})
        names = [_element_local_name(child) for child in table.element]
        index = next((i for i, name in enumerate(names) if name in {"cellzoneList", "tr", "label"}), len(names))
        table.element.insert(index, own)
    for side in _MARGIN_SIDES:
        own.set(side, str(getattr(margins, side)))
    for row in table.element.findall(f"{_HP}tr"):
        for cell in row.findall(f"{_HP}tc"):
            if (cell.get("hasMargin") or "").strip().lower() not in {"1", "true"}:
                cell_margin = cell.find(f"{_HP}cellMargin")
                if cell_margin is not None:
                    for side in _MARGIN_SIDES:
                        cell_margin.set(side, str(getattr(margins, side)))
                for paragraph in cell.findall(f"{_HP}subList/{_HP}p"):
                    _clear_paragraph_layout_cache(paragraph)
    _clear_paragraph_layout_cache(table.paragraph.element)
    table.mark_dirty()
    return margins


def _grid_edges(table: "HwpxOxmlTable", axis: str) -> list[int] | None:
    """The edges of the table's grid lines along *axis* (``"col"`` or ``"row"``), from 0: each line
    at the farthest end the cells before it reach (start plus ``hp:cellSz`` size and the cell
    spacing). ``None`` when the cells leave a grid line unreached."""

    size_name, span_name = ("width", "colSpan") if axis == "col" else ("height", "rowSpan")
    count = table.column_count if axis == "col" else table.row_count
    spacing = int(table.element.get("cellSpacing", 0) or 0)
    places: list[tuple[int, int, int]] = []
    for row in table.element.findall(f"{_HP}tr"):
        for tc in row.findall(f"{_HP}tc"):
            address, span, size = (tc.find(f"{_HP}{name}") for name in ("cellAddr", "cellSpan", "cellSz"))
            if address is None or size is None:
                return None
            first = int(address.get(f"{axis}Addr", 0) or 0)
            stop = first + max(1, int((span.get(span_name) if span is not None else None) or 1))
            places.append((first, stop, int(size.get(size_name, 0) or 0)))
    edges = {0: 0}
    for end in range(1, count + 1):
        reach = [edges[first] + size + spacing for first, stop, size in places if stop == end and first in edges]
        if not reach:
            return None
        edges[end] = max(reach)
    return [edges[index] for index in range(count + 1)]


def _grid_sizes(table: "HwpxOxmlTable", axis: str) -> tuple[int, ...]:
    edges = _grid_edges(table, axis)
    count = table.column_count if axis == "col" else table.row_count
    if edges is None:  # an unreadable grid: the table's own size shared out evenly
        sz = table.element.find(f"{_HP}sz")
        total = int((sz.get("width" if axis == "col" else "height") if sz is not None else None) or 0)
        return tuple(_distribute_size(max(total, 0), count))
    spacing = int(table.element.get("cellSpacing", 0) or 0)
    return tuple(max(edges[i + 1] - edges[i] - spacing, 0) for i in range(count))


def column_widths(table: "HwpxOxmlTable") -> tuple[int, ...]:
    """Each grid column's width in HWPUNIT, left to right, read from the cells' ``hp:cellSz`` as
    Hancom lays the grid out (a merged cell wider than its columns widens the last of them)."""

    return _grid_sizes(table, "col")


def row_heights(table: "HwpxOxmlTable") -> tuple[int, ...]:
    """Each row's stored height in HWPUNIT, top to bottom, read from the cells' ``hp:cellSz``
    (Hancom draws a row taller when its text needs it)."""

    return _grid_sizes(table, "row")


def table_width(table: "HwpxOxmlTable") -> int:
    """The table's width in HWPUNIT (``hp:sz/@width``)."""

    sz = table.element.find(f"{_HP}sz")
    return _margin_value(sz.get("width") if sz is not None else None)


def _size_value(value: object, argument: str, code: str) -> int:
    from ..errors import HwpxValueError

    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**31:
        raise HwpxValueError(
            f"{argument} must be an int in 0 < {argument} < 2**31 (HWPUNIT); got {value!r}",
            code=code,
            context={"argument": argument, "value": repr(value)},
            suggestion="Pass a length in HWP units (1 mm is about 283).",
        )
    return value


def _line_index(table: "HwpxOxmlTable", value: object, axis: str) -> int:
    from .utils import HwpxIndexError

    count = table.column_count if axis == "col" else table.row_count
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < count:
        raise HwpxIndexError(
            f"{axis} {value!r} is outside the table (0..{count - 1})",
            code="table-cell-not-found",
            context={axis: repr(value), "count": count},
            suggestion=f"Pass a {'column' if axis == 'col' else 'row'} index in 0..{count - 1}.",
        )
    return value


def _resize_line(table: "HwpxOxmlTable", axis: str, index: int, delta: int) -> None:
    """Grow (shrink) every cell crossing grid line *index* along *axis* by *delta*, and the table."""

    size_name = "width" if axis == "col" else "height"
    seen: set[int] = set()
    for entry in table.iter_grid():
        cell = entry.cell
        if id(cell.element) in seen:
            continue
        first = entry.anchor[1] if axis == "col" else entry.anchor[0]
        span = entry.span[1] if axis == "col" else entry.span[0]
        if first <= index < first + max(span, 1):
            seen.add(id(cell.element))
            current = cell.width if axis == "col" else cell.height
            cell.set_size(**{size_name: max(current + delta, 0)})
            cell._clear_own_layout_caches()
    sz = table.element.find(f"{_HP}sz")
    if sz is not None:
        sz.set(size_name, str(max(_margin_value(sz.get(size_name)) + delta, 0)))
    _clear_paragraph_layout_cache(table.paragraph.element)
    table.mark_dirty()


@_keeping_nested_fit
def set_column_width(table: "HwpxOxmlTable", col: int, width: int) -> None:
    """Give grid column *col* the width *width* (HWPUNIT): every cell crossing it grows or shrinks by
    the difference, and so does the table (the other columns keep theirs). A width below the
    narrowest Hancom draws the column (its cells' side margins plus 283) is refused
    (``table-column-width-value``), as is one leaving a nested table wider than its cell."""

    from ..errors import HwpxValueError

    col = _line_index(table, col, "col")
    width = _size_value(width, "width", "table-column-width-value")
    floor = _column_floors(table)[col]
    if width < floor:
        raise HwpxValueError(
            f"column {col} cannot be narrower than {floor} (its cells' side margins plus {COLUMN_FLOOR_EXTRA})",
            code="table-column-width-value",
            context={"col": col, "width": width, "floor": floor},
            suggestion=f"Pass at least {floor}, or narrow the cells' margins first.",
        )
    delta = width - column_widths(table)[col]
    if delta:
        _resize_line(table, "col", col, delta)


def set_row_height(table: "HwpxOxmlTable", row: int, height: int) -> None:
    """Give row *row* the stored height *height* (HWPUNIT): every cell crossing it grows or shrinks
    by the difference, and so does the table. Hancom still draws the row taller when its text
    needs it (``table-row-height-value`` for a height that is not a positive int)."""

    row = _line_index(table, row, "row")
    height = _size_value(height, "height", "table-row-height-value")
    delta = height - row_heights(table)[row]
    if delta:
        _resize_line(table, "row", row, delta)


def _scale_columns(table: "HwpxOxmlTable", width: int, current: tuple[int, ...]) -> None:
    sz = table.element.find(f"{_HP}sz")
    if sz is None:
        sz = table.element.makeelement(f"{_HP}sz", {"width": "0", "widthRelTo": "ABSOLUTE", "height": "0",
                                                     "heightRelTo": "ABSOLUTE", "protect": "0"})
        table.element.insert(0, sz)
    before = sz.get("width")
    sz.set("width", str(width))
    try:  # set_column_widths shares the new width out, or leaves the cells as they were and refuses
        set_column_widths(table, list(current) if any(current) else [1] * len(current))
    except Exception:
        sz = table.element.find(f"{_HP}sz")
        if sz is not None and before is not None:
            sz.set("width", before)
        raise
    for paragraph in table.element.iter(f"{_HP}p"):
        _clear_paragraph_layout_cache(paragraph)
    _clear_paragraph_layout_cache(table.paragraph.element)
    table.mark_dirty()


def set_table_width(table: "HwpxOxmlTable", width: int, *, proportional: bool = True) -> None:
    """Make the table *width* wide (HWPUNIT). With *proportional* every column keeps its share of
    the width (none narrower than Hancom draws it); without, the last column takes the
    difference. ``table-width-value`` for a width that is not a positive int."""

    width = _size_value(width, "width", "table-width-value")
    current = column_widths(table)
    total = sum(current)
    if width == table_width(table) and width == total:
        return
    if proportional:
        _scale_columns(table, width, current)
    else:
        last = len(current) - 1
        set_column_width(table, last, current[last] + width - total)


#: A SQUEEZE line up to this share of the cell's line width still reads in Hancom.
SQUEEZE_READABLE_RATIO = 1.1


def squeezes_readably(cell: "HwpxOxmlTableCell", value: str) -> bool:
    """Whether each line of *value* is at most 1.1 times *cell*'s line width at
    the cell's character shape (``False`` when that cannot be measured).

    Hancom keeps a SQUEEZE cell's text on one line and narrows only the spacing
    between its characters: up to 1.1 times the line width the text still reads,
    beyond it the characters touch and overlap.
    """
    from hwpx.form_fit.measure import char_advance, text_style_from_refs

    try:
        document = cell.table.paragraph.section.document
        char_ref = cell._first_run_char_pr_id_ref()
        char_style = document.char_property(char_ref) if document is not None else None
        if char_style is None:
            return False
        margins = cell_margins(cell)
        width = cell.width - margins.left - margins.right
        paragraphs = cell.paragraphs
        style = text_style_from_refs(document, paragraphs[0].para_pr_id_ref if paragraphs else None, [char_ref])
        font_pt = int(char_style.attributes.get("height", "1000")) / 100
    except Exception:  # pragma: no cover - defensive: an unreadable cell is not squeezed
        return False
    if width <= 0:
        return False
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return all(sum(char_advance(ch, font_pt, style) for ch in line) <= SQUEEZE_READABLE_RATIO * width for line in lines)
