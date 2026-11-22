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

from typing import TYPE_CHECKING, Any, Iterable, Mapping

from ._document_primitives import _HP, _clear_paragraph_layout_cache

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph
    from .table import HwpxOxmlTable, HwpxOxmlTableRow

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


def _offset(self: Any) -> "int | None":
    """Where it stands in its paragraph's text: the number of characters before it, counted as
    ``paragraph.text`` counts (``None`` when it is in no run of a paragraph). It takes no character, so it
    stands after character ``offset - 1`` and before character ``offset``; ``move_to(paragraph,
    offset=obj.offset)`` puts it back where it is."""

    from .text_offsets import placed_offset

    return placed_offset(self)


class TableStructureEdits:
    """Row and column insertion and deletion and cell splits of a table, as Hancom makes them."""

    element: Any
    paragraph: "HwpxOxmlParagraph"
    _section: Any  # the section a table taken out of its paragraph was built with

    offset = property(_offset)

    def insert_rows(self, ref_row: int, count: int = 1, *, side: str = "below", copy_content: bool = False) -> None:
        """Insert *count* empty rows below (*side* ``"above"``: above) physical row *ref_row*, as Hancom
        inserts rows.

        Each new row is as high as *ref_row*, and each new cell takes the format of the cell of the
        same column in *ref_row* (cell properties, border and fill, margins, size, and its first
        paragraph's paragraph and character shape) and holds one empty paragraph of that format, with
        no line layout cache. With *copy_content* each new cell holds a copy of that cell's content
        instead (text, objects, fields; a nested table with fresh numbers). A cell merged across the
        new rows grows over them, and next to a merged cell that ends (above: starts) at *ref_row* each
        new row gets an empty cell of its format either way.
        """

        self._restructure({
            "op": "insert_row_by_clone", "ref_row": _whole(ref_row, "ref_row"),
            "count": _whole(count, "count"), "side": side, "blank": not copy_content,
        })

    def insert_columns(self, ref_col: int, count: int = 1, *, side: str = "right", copy_content: bool = False) -> None:
        """Insert *count* empty columns right (*side* ``"left"``: left) of grid column *ref_col*, as
        Hancom inserts columns.

        Each new column is as wide as *ref_col* and the table grows by it, as Hancom widens it. Each
        new cell takes the format of the cell of the same row in *ref_col* and holds one empty
        paragraph of that format; with *copy_content* it holds a copy of that cell's content instead.
        A cell merged across the new columns grows over them, and next to a merged cell that ends
        (left: starts) at *ref_col* each new column gets an empty cell of its format. Cell zones move
        with their columns.
        """

        self._restructure({
            "op": "insert_column_by_clone", "ref_col": _whole(ref_col, "ref_col"),
            "count": _whole(count, "count"), "side": side, "blank": not copy_content,
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

    def move_rows(
        self, rows: int | Iterable[int], *, to: int, source: "HwpxOxmlTable | None" = None
    ) -> "tuple[HwpxOxmlTableRow, ...]":
        """Move the physical rows *rows* (one row number or a run of them, as :meth:`delete_rows` takes) in
        front of row *to* -- counted before the move; the row count puts them at the end -- and return them,
        where they stand now. Every cell's ``rowAddr`` and the row count are numbered again; the cells keep
        their ids and content. A merged cell reaching across the rows' top or bottom or the place they go to
        is refused (``table-rows-merge-crossed``) before anything changes; rows not next to each other or out
        of range, ``table-rows-invalid``. Rows move within their table: *source* other than this table is
        refused (``table-rows-move-other-table``) -- no Hancom-saved document shows rows moved into another
        table; :meth:`copy_rows` with *source* and :meth:`delete_rows` do it in two steps."""

        from .note_authoring import renumber_notes_holding
        from .table_rows import move_rows

        moved = move_rows(self, rows, to, source)
        renumber_notes_holding(self.paragraph.section if self.paragraph is not None else self._section,
                               (self.element,))  # the rows' notes stand elsewhere in the order now
        return moved

    def copy_rows(
        self, rows: int | Iterable[int], *, to: int, source: "HwpxOxmlTable | None" = None
    ) -> "tuple[HwpxOxmlTableRow, ...]":
        """Put a copy of the rows *rows* of *source* (``None``: this table; another table of the same document,
        of the same columns) in front of row *to* of this table. The copies' paragraphs, objects and fields
        get fresh ids, as ``copy_after`` gives a table's copy; the table grows by their height, as
        :meth:`insert_rows` grows it. Refused as :meth:`move_rows` refuses, and a source of other columns
        (``table-columns-differ``) or of another document (``table-rows-other-document``). Returns the new
        rows, where they stand."""

        from .note_authoring import renumber_notes_holding
        from .table_rows import copy_rows

        copies = copy_rows(self, rows, to, source)
        renumber_notes_holding(self.paragraph.section if self.paragraph is not None else self._section,
                               (self.element,))  # copied rows repeated their notes' numbers
        return copies

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

    def remove(self, *, remove_orphaned: bool = True) -> None:
        """Take this table out of its paragraph, as Hancom deletes a table.

        The paragraph that held it stays (an empty line when it held nothing else) and loses its
        line layout cache. A run left empty goes. The images the pictures in its cells showed leave
        the package with it when nothing else points at them (*remove_orphaned*, as ``obj.remove()``
        takes it). A second call does nothing; the table object should not be used after it.
        """

        from .note_authoring import note_kinds_in_document, renumber_note_kinds
        from .shape_position import binary_references, remove_orphaned_images

        paragraph = self.paragraph.element
        for run in paragraph.findall(f"{_HP}run"):
            if any(child is self.element for child in run):
                images = binary_references(self.element) if remove_orphaned else set()
                section = self.paragraph.section
                note_kinds = note_kinds_in_document(section, self.element)
                run.remove(self.element)
                if len(run) == 0 and len(paragraph.findall(f"{_HP}run")) > 1:
                    paragraph.remove(run)
                _clear_paragraph_layout_cache(paragraph)
                section.mark_dirty()
                remove_orphaned_images(section, images)
                renumber_note_kinds(section, note_kinds)  # the notes after the ones its cells held
                return

    def move_to(self, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None) -> None:
        """Move this table into *paragraph* at character *offset* (``None``: the end), with the same
        rules as a picture's or shape's ``move_to``: *paragraph* is a paragraph of the same document or
        its index in ``doc.paragraphs``, the table keeps its ids, a floating table keeps its frames
        where Hancom documents hold such a table, and both paragraphs lose their line layout caches.
        :meth:`copy_after` puts a copy into a new paragraph of its own instead."""

        from .shape_position import place_object

        place_object(self, paragraph, offset, copy=False)

    def copy_to(self, paragraph: "int | HwpxOxmlParagraph", *, offset: int | None = None) -> "HwpxOxmlTable":
        """Put a copy of this table into *paragraph* at *offset* (``None``: the end) and return it, as
        ``copy_after`` copies (fresh ids, fields renumbered, no line layout caches); a copy may go into
        one of the table's own cells."""

        from .shape_position import place_object

        return place_object(self, paragraph, offset, copy=True)  # type: ignore[no-any-return]

    def _restructure(self, op: dict[str, Any]) -> None:
        from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

        from ..table_patch import _CLONE_OPS, TableStructureError, _restructure_table

        element = self.element
        if element.prefix != "hp":
            raise TableStructureError("structure edits need a table whose paragraph namespace is prefixed hp")
        section = self.paragraph.section
        sections = section.document.sections if section.document is not None else [section]
        # A paragraph edited in the tree directly still holds the cache it was read with. The rebuild
        # below makes new elements, which the save can no longer pair with what was read: drop the
        # caches that outlived their content now, while it still can.
        if section._remove_outlived_layout_caches(force=True, rebuilding=element):
            section.mark_dirty()
        used = {
            int(found)
            for part in sections
            for paragraph in part.element.iter(f"{_HP}p")
            if (found := paragraph.get("id") or "").isdigit()
        }
        from .note_authoring import note_kinds_in, renumber_note_kinds

        note_kinds = note_kinds_in((element,))  # before: rows deleted take their notes with them
        xml = etree.tostring(element, encoding="unicode", with_tail=False)
        context = "".join(etree.tostring(part.element, encoding="unicode") for part in sections) \
            if op.get("op") in _CLONE_OPS else ""
        new = etree.fromstring(_restructure_table(xml, op, used_ids=used, context=context))
        before = self._rows_height()
        for child in list(element):
            element.remove(child)
        element.attrib.clear()
        element.attrib.update(new.attrib)
        element.text = new.text
        element.extend(list(new))
        self._grid_cache = None  # the rows and cells were replaced (HwpxOxmlTable keeps its grid here)
        self._grow_height(before)
        _clear_paragraph_layout_cache(self.paragraph.element)  # its line held the table as it was
        section.mark_dirty()
        section._remove_outlived_layout_caches()  # track the rebuilt caches with the content they have now
        # Rows or columns copied with their content repeated their notes' numbers (1, 1), and rows
        # deleted left the numbers after them as they were: number the kinds the table held or holds.
        renumber_note_kinds(section, note_kinds | note_kinds_in((element,)))

    def _rows_height(self) -> int | None:
        """The table's rows' height as the page estimate measures them (:mod:`hwpx.layout.pages`), or None
        when it does not follow the table."""

        from ..layout import pages

        document = self.paragraph.section.document
        if document is None or not document.headers:
            return None
        try:
            return pages._rows_height(pages._Measure(document), self.element)
        except Exception:  # noqa: BLE001  # the height stays as it was
            return None

    def _grow_height(self, before: int | None) -> None:
        """Move the table's saved height (``hp:sz``) by what its rows gained or lost in the edit, as
        Hancom saves the height of the rows it lays out: the rows left as they were keep the height Hancom
        gave them. With rows the estimate does not follow, the height stays as it was.

        A table saved shorter than its rows is one Hancom split across pages: it saves the height of the
        part on the table's first page (tables of the same rows save different heights by where they start),
        and the rows' gain or loss does not say how that part changes. Its height also stays as it was, rather
        than moving by the whole delta, which can take it to nothing."""

        size = self.element.find(f"{_HP}sz")
        if before is None or size is None:
            return
        height = int(size.get("height", 0) or 0)
        if height < before:
            return  # decided before measuring the rows again (a big table's estimate is not free)
        after = self._rows_height()
        if after is None or after == before:
            return
        size.set("height", str(max(0, height + after - before)))


class _ByteTableHeight:
    """The object path's height adjustment for byte edits, with one read-only document context.

    Only the resulting height is returned: the caller keeps its original XML bytes. Current section
    snapshots carry earlier operations and their numbering context, including tables nested in cells.
    """

    def __init__(self, source: bytes) -> None:
        from ..document import HwpxDocument

        self.document: HwpxDocument | None
        try:
            self.document = HwpxDocument.open(source)
        except Exception:  # noqa: BLE001  # byte edits also accept packages the object model cannot open
            self.document = None

    def __call__(self, sections: Mapping[str, bytes], sp: str, ti: int, table: str) -> int | None:
        from ..opc.xml_utils import parse_xml
        from ..table_patch import _iter_table_spans
        from .paragraph import HwpxOxmlParagraph
        from .table import HwpxOxmlTable

        if self.document is None:
            return None
        try:
            for part in self.document.sections:
                part._element = parse_xml(sections[part.part_name])
            section = next(part for part in self.document.sections if part.part_name == sp)
            element: Any = list(section.element.iter(_HP + "tbl"))[ti]
            paragraph = next(element.iterancestors(_HP + "p"))
            native = HwpxOxmlTable(element, HwpxOxmlParagraph(paragraph, section))
            before = native._rows_height()
            if before is None:
                return None
            ts, te = _iter_table_spans(sections[sp])[ti]
            edited = sections[sp][:ts] + table.encode("utf-8") + sections[sp][te:]
            replacement = list(parse_xml(edited).iter(_HP + "tbl"))[ti]
            element.getparent().replace(element, replacement)
            native.element = replacement
            native._grow_height(before)
            return native.height
        except Exception:  # noqa: BLE001  # as in object edits, unsupported row measurement keeps the height
            return None
