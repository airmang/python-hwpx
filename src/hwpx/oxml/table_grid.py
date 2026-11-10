# SPDX-License-Identifier: Apache-2.0
"""What a table's built cell grid was built from, to tell whether the table changed since.

``HwpxOxmlTable`` keeps one built grid and asks here whether it still describes the table's XML.
"""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from ._document_primitives import _HP

__all__ = ["TableGridCache"]

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
