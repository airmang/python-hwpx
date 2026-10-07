# SPDX-License-Identifier: Apache-2.0
"""Rows and columns inserted and deleted, and cells split, in a table of the object model.

:class:`~hwpx.oxml.table.HwpxOxmlTable` takes these methods from :class:`TableStructureEdits`, kept
here so that ``table.py`` stays inside the owner-file line budget. Each runs the edit of
:func:`hwpx.table_patch.apply_table_ops` of the same kind on the table's XML, so both follow the same
rules -- those of Hancom's own row and column insertion and deletion and cell split -- and puts the
result back into the table's element. Cells and rows taken from the table before an edit no longer
belong to it: take them again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ._document_primitives import _HP, _clear_paragraph_layout_cache

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph

__all__ = ["TableStructureEdits"]


def _whole(value: object, name: str) -> int:
    from ..table_patch import TableStructureError

    if isinstance(value, bool) or not isinstance(value, int):
        raise TableStructureError(f"{name} must be an int, got {value!r}")
    return value


def _lines(value: int | Iterable[int], name: str) -> list[int]:
    lines = [value] if isinstance(value, int) else list(value)
    if not lines:
        from ..table_patch import TableStructureError

        raise TableStructureError(f"{name} names no row or column")
    return [_whole(line, name) for line in lines]


class TableStructureEdits:
    """Row and column insertion and deletion and cell splits of a table, as Hancom makes them."""

    element: Any
    paragraph: "HwpxOxmlParagraph"

    def insert_rows(self, ref_row: int, count: int = 1, *, side: str = "below", blank: bool = False) -> None:
        """Insert *count* rows below (*side* ``"above"``: above) physical row *ref_row*, cloning it.

        Each new row is as high as *ref_row*, and each new cell takes the format of the cell of the
        same column in *ref_row* and, unless *blank*, its text; with *blank* it holds one empty
        paragraph of that format, as Hancom inserts it. A cell merged across the new rows grows over
        them, and next to a merged cell that ends (above: starts) at *ref_row* each new row gets an
        empty cell of its format. A table holding a table is refused
        (:class:`hwpx.table_patch.TableStructureError`).
        """

        self._restructure({
            "op": "insert_row_by_clone", "ref_row": _whole(ref_row, "ref_row"),
            "count": _whole(count, "count"), "side": side, "blank": bool(blank),
        })

    def insert_columns(self, ref_col: int, count: int = 1, *, side: str = "right", blank: bool = False) -> None:
        """Insert *count* columns right (*side* ``"left"``: left) of grid column *ref_col*, cloning it.

        Each new column is as wide as *ref_col* and the table grows by it, as Hancom widens it. Each
        new cell takes the format of the cell of the same row in *ref_col* and, unless *blank*, its
        text. A cell merged across the new columns grows over them, and next to a merged cell that
        ends (left: starts) at *ref_col* each new column gets an empty cell of its format. Cell zones
        move with their columns.
        """

        self._restructure({
            "op": "insert_column_by_clone", "ref_col": _whole(ref_col, "ref_col"),
            "count": _whole(count, "count"), "side": side, "blank": bool(blank),
        })

    def delete_rows(self, rows: int | Iterable[int]) -> None:
        """Delete the physical rows *rows* (one index or several).

        A cell merged across a deleted row loses that row; one starting there moves into the next row,
        content kept. Deleting every row is refused: delete the table instead. Cell zones move with
        their rows.
        """

        self._restructure({"op": "delete_row", "rows": _lines(rows, "rows")})

    def delete_columns(self, cols: int | Iterable[int]) -> None:
        """Delete the grid columns *cols* (one index or several), sharing their width out among the
        columns left so that the table keeps its width.

        A cell merged across a deleted column loses that column. Deleting every column is refused:
        delete the table instead. Cell zones move with their columns.
        """

        self._restructure({"op": "delete_column", "cols": _lines(cols, "cols")})

    def split_cell(self, row: int, col: int, *, rows: int = 1, cols: int = 1) -> None:
        """Split the cell at (*row*, *col*) into *rows* x *cols* cells (2..63 each), as Hancom does.

        Into columns the cell's width is shared out evenly, the last part taking what is left over,
        and the cells across the new grid lines keep their width. Into rows the parts take the rows
        the cell covers when they divide evenly, else one row each and new rows after its last, which
        the cells beside that row grow over; the parts share out its stored height evenly. The content
        stays in the first part.
        """

        self._restructure({
            "op": "split_cell", "row": _whole(row, "row"), "col": _whole(col, "col"),
            "rows": _whole(rows, "rows"), "cols": _whole(cols, "cols"),
        })

    def _restructure(self, op: dict[str, Any]) -> None:
        from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

        from ..table_patch import TableStructureError, _restructure_table

        element = self.element
        if element.prefix != "hp":
            raise TableStructureError("structure edits read a table whose paragraph namespace is prefixed hp")
        section = self.paragraph.section
        sections = section.document.sections if section.document is not None else [section]
        used = {
            int(found)
            for part in sections
            for paragraph in part.element.iter(f"{_HP}p")
            if (found := paragraph.get("id") or "").isdigit()
        }
        xml = etree.tostring(element, encoding="unicode", with_tail=False)
        new = etree.fromstring(_restructure_table(xml, op, used_ids=used))
        for child in list(element):
            element.remove(child)
        element.attrib.clear()
        element.attrib.update(new.attrib)
        element.text = new.text
        element.extend(list(new))
        _clear_paragraph_layout_cache(self.paragraph.element)  # its line held the table as it was
        section.mark_dirty()
