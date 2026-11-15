# SPDX-License-Identifier: Apache-2.0
"""What a cell merge leaves behind in a table's grid.

``HwpxOxmlTable.merge_cells`` calls :func:`collapse_merged_grid` once the merged cell
spans its rectangle. It lives here so that ``table.py`` stays inside the owner-file
line budget.

:class:`TableGridCache` is here for the same reason: ``HwpxOxmlTable`` keeps one built cell
grid and asks it whether the grid still describes the table's XML.
"""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from ._document_primitives import _HP

__all__ = ["TableGridCache", "collapse_merged_grid", "cell_out_of_range", "check_merge_range"]


def cell_out_of_range(row: int, col: int, rows: int, cols: int) -> Exception:
    """The error for cell coordinates outside a *rows* x *cols* table (an ``IndexError`` too)."""

    from .utils import HwpxIndexError

    return HwpxIndexError(
        "cell coordinates (%d, %d) exceed table bounds %dx%d" % (row, col, rows, cols),
        code="table-cell-not-found",
        context={"row": row, "col": col, "rows": rows, "cols": cols},
        suggestion=f"이 표의 칸 좌표는 행 0..{rows - 1}, 열 0..{cols - 1} 입니다.",
    )


def check_merge_range(start_row: int, start_col: int, end_row: int, end_col: int, rows: int, cols: int) -> None:
    """Refuse a merge rectangle that is reversed (``ValueError``) or outside a *rows* x *cols* table
    (``IndexError``), as typed errors (``table-merge-range-invalid``)."""

    from ..errors import HwpxValueError
    from .utils import HwpxIndexError

    context = {"start": [start_row, start_col], "end": [end_row, end_col], "rows": rows, "cols": cols}
    if start_row > end_row or start_col > end_col:
        raise HwpxValueError(
            "merge coordinates must describe a valid rectangle",
            code="table-merge-range-invalid",
            context=context,
            suggestion="시작 칸(위·왼쪽)을 먼저, 끝 칸(아래·오른쪽)을 나중에 주세요: merge_cells(0, 0, 1, 1).",
        )
    if start_row < 0 or start_col < 0 or end_row >= rows or end_col >= cols:
        raise HwpxIndexError(
            "merge coordinates exceed table bounds",
            code="table-merge-range-invalid",
            context=context,
            suggestion=f"이 표의 칸 좌표는 행 0..{rows - 1}, 열 0..{cols - 1} 입니다.",
        )


def bad_spreadsheet_range(value: object) -> Exception:
    """The error for a merge range that is not ``"A1:B2"``-shaped (a ``ValueError`` too)."""

    from ..errors import HwpxValueError

    return HwpxValueError(
        f"invalid spreadsheet range: {value!r}",
        code="table-merge-range-invalid",
        context={"range": repr(value)},
        suggestion='범위는 "A1:B2" 꼴로 주세요(열 글자 + 1부터 세는 행 번호).',
    )


def cell_remove_refused() -> Exception:
    """The refusal of ``cell.remove()``: one cell out of the grid leaves a hole."""

    from ..errors import HwpxValueError

    return HwpxValueError(
        "표 칸 하나만 지우면 표 격자에 구멍이 나 한/글이 표를 그리지 못합니다.",
        code="table-cell-remove-unsupported",
        suggestion="행이나 열을 통째로 지우려면 table.delete_rows()/table.delete_columns(), "
        "옆 칸과 합치려면 table.merge_cells(), 내용만 비우려면 cell.text = \"\" 를 쓰세요.",
    )


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

_TC_ADDR = f"{_HP}cellAddr"
_TC_SPAN = f"{_HP}cellSpan"
_TC_SIZE = f"{_HP}cellSz"


def _cell_grid_signature(cell_element: ET.Element) -> tuple[Any, Any, Any]:
    """The raw attributes of one ``hp:tc`` that decide where it sits in the grid."""

    addr = cell_element.find(_TC_ADDR)
    span = cell_element.find(_TC_SPAN)
    size = cell_element.find(_TC_SIZE)
    return (
        None if addr is None else (addr.get("rowAddr"), addr.get("colAddr")),
        None if span is None else (span.get("rowSpan"), span.get("colSpan")),
        None if size is None else (size.get("width"), size.get("height")),
    )


def _is_zero_single_cell(signature: tuple[Any, Any, Any]) -> bool:
    """Whether the grid builder may treat the cell as a deactivated placeholder (then its text matters)."""

    _, span, size = signature
    try:
        if span is not None and (int(span[0] or 1), int(span[1] or 1)) != (1, 1):
            return False
        if size is not None and (int(size[0] or 0) != 0 or int(size[1] or 0) != 0):
            return False
    except (TypeError, ValueError):
        return True
    return True


class TableGridCache:
    """One built grid with what it was built from, to tell whether the table changed since.

    ``rows``/``row_lengths``/``cells`` are the table's ``hp:tr`` elements, their child counts and,
    per physical cell, its element, row and raw address/span/size attributes (plus whether it holds
    text when it is a zero-sized 1x1 cell, the one case where text changes the grid).
    """

    __slots__ = ("mapping", "rows", "row_lengths", "cells", "by_cell", "fast")

    def __init__(self, mapping: dict[tuple[int, int], Any], table_element: ET.Element):
        self.mapping = mapping
        self.rows, self.row_lengths, self.cells, text_matters = self._snapshot(table_element)
        self.by_cell = {id(cell): (row, signature) for cell, row, signature, _ in self.cells}
        # Coordinate lookups check only the table's shape and the cell they return.  That is not enough
        # when text decides the grid, or without ``getparent`` (a plain ElementTree element).
        self.fast = not text_matters and hasattr(table_element, "getparent")

    @staticmethod
    def _snapshot(table_element: ET.Element) -> tuple[list[ET.Element], list[int], list[tuple[Any, ...]], bool]:
        rows = table_element.findall(f"{_HP}tr")
        cells: list[tuple[Any, ...]] = []
        text_matters = False
        for row in rows:
            for cell in row.findall(f"{_HP}tc"):
                signature = _cell_grid_signature(cell)
                has_text: bool | None = None
                if _is_zero_single_cell(signature):
                    text_matters = True
                    has_text = any(node.text for node in cell.findall(f".//{_HP}t"))
                cells.append((cell, row, signature, has_text))
        return rows, [len(row) for row in rows], cells, text_matters

    def same_shape(self, table_element: ET.Element) -> bool:
        rows = table_element.findall(f"{_HP}tr")
        return rows == self.rows and [len(row) for row in rows] == self.row_lengths

    def cell_unchanged(self, cell_element: ET.Element) -> bool:
        known = self.by_cell.get(id(cell_element))
        if known is None:
            return False
        row, signature = known
        return cell_element.getparent() is row and _cell_grid_signature(cell_element) == signature  # type: ignore[attr-defined]

    def still_valid(self, table_element: ET.Element) -> bool:
        rows, row_lengths, cells, _ = self._snapshot(table_element)
        return rows == self.rows and row_lengths == self.row_lengths and cells == self.cells
