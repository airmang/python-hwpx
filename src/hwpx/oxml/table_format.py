# SPDX-License-Identifier: Apache-2.0
"""How a table and its cells look and flow: alignment, borders and shading, header rows, page
breaking, columns, cell zones, emptying a cell and copying a table.

:class:`~hwpx.oxml.table.HwpxOxmlTable`, :class:`~hwpx.oxml.table.HwpxOxmlTableCell` and
:class:`~hwpx.oxml.table.HwpxOxmlTableRow` take these members from the mixins here, kept apart so
that ``table.py`` stays inside the owner-file line budget. Every value is read and written as the
file stores it (OWPML spelling, HWPUNIT lengths); every check runs before anything changes.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence, cast

from ..objects.results import Alignment, BorderFillInfo, CellZone
from ._document_primitives import (
    _HP,
    _clear_paragraph_layout_cache,
    _element_local_name,
    _paragraph_id,
    _refresh_copied_paragraph_subtree_ids,
)
from . import table_sizes as _table_sizes
from .namespaces import HH
from .shape_position import ObjectPlacement, _object_set_position

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph
    from .table import HwpxOxmlTable, HwpxOxmlTableCell

__all__ = [
    "BORDER_SIDES",
    "CELL_TEXT_DIRECTIONS",
    "CELL_VERTICAL_ALIGNMENTS",
    "TABLE_ALIGNMENTS",
    "TABLE_PAGE_SPLITS",
    "HwpxOxmlTableColumn",
    "TableCellFormat",
    "TableFormat",
    "TableRowFormat",
]

#: ``hp:subList/@vertAlign`` of a cell: where its lines sit between its top and bottom.
CELL_VERTICAL_ALIGNMENTS = ("TOP", "CENTER", "BOTTOM")
#: ``hp:subList/@textDirection`` of a cell: its text runs left to right in lines going down
#: (``HORIZONTAL``) or top to bottom (``VERTICAL``, Hancom's 세로쓰기).
CELL_TEXT_DIRECTIONS = ("HORIZONTAL", "VERTICAL")
#: The largest cell spacing (``hp:tbl/@cellSpacing``, HWPUNIT): Hancom keeps it as a 16-bit number.
_MAX_CELL_SPACING = 2**15 - 1
#: Where a table sits across its line: the host paragraph's alignment for a table set as a
#: character, ``hp:pos/@horzAlign`` for a floating one.
TABLE_ALIGNMENTS = ("LEFT", "CENTER", "RIGHT")
#: ``hp:tbl/@pageBreak``: at a page end the table splits (``TABLE``), splits between rows of cells
#: only (``CELL``), or moves whole to the next page (``NONE``).
TABLE_PAGE_SPLITS = ("TABLE", "CELL", "NONE")
#: The four sides of a cell, as ``doc.styles.ensure_border_fill(sides=...)`` names them.
BORDER_SIDES = ("left", "right", "top", "bottom")
_SIDE_ELEMENTS = {"left": "leftBorder", "right": "rightBorder", "top": "topBorder", "bottom": "bottomBorder"}
#: hh:borderFill's children in schema order; a new side goes in its place among them.
_BORDER_FILL_ORDER = ("slash", "backSlash", "leftBorder", "rightBorder", "topBorder", "bottomBorder",
                      "diagonal", "fillBrush")
_TRUE = {"1", "true"}


def _refuse(message: str, code: str, suggestion: str, **context: Any) -> Exception:
    from ..errors import HwpxValueError

    return HwpxValueError(message, code=code, context=context or None, suggestion=suggestion)


def _member(value: object, allowed: tuple[str, ...], *, argument: str, code: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    raise _refuse(
        f"{argument} must be one of {', '.join(allowed)}; got {value!r}", code,
        f"{argument} 는 {list(allowed)} 중 하나여야 합니다(대문자, 정확히 일치).",
        argument=argument, requested=repr(value), allowed=list(allowed),
    )


def _flag(value: object, argument: str, code: str) -> bool:
    if not isinstance(value, bool):
        raise _refuse(f"{argument} must be True or False; got {value!r}", code,
                      f"{argument} 에 True 나 False 를 주세요.", argument=argument, requested=repr(value))
    return value


# ----------------------------------------------------------------------------------------------
# border fills derived from the one a cell uses
# ----------------------------------------------------------------------------------------------


class _BorderFills:
    """Derives new ``hh:borderFill`` definitions from the ones cells use, reusing an identical one.

    The derivation itself is :func:`hwpx.oxml.formatting.derive_definition`, the one path
    ``doc.styles.ensure_border_fill(base_border_fill_id_ref=)`` and the fill setters use too; this
    remembers what each (base, change) gave so a table's cells sharing a border fill derive it once."""

    def __init__(self, table: "HwpxOxmlTable") -> None:
        model = table.paragraph.section.document
        if model is None or not model.headers:
            raise _refuse("a cell's borders and fill need the document's header", "table-border-value",
                          "Edit a table that belongs to an opened or created document.")
        self.table = table
        self.document = model
        self.header = model.headers[0]
        container = self.header._border_fills_element(create=True)
        if container is None:  # pragma: no cover - defensive
            raise _refuse("the header has no border fill list", "table-border-value",
                          "Open the document again; its header is incomplete.")
        self.container = container
        self.memo: dict[tuple[Any, ...], str] = {}

    def base_id(self, cell: "HwpxOxmlTableCell") -> str | None:
        return cell.element.get("borderFillIDRef") or self.table.element.get("borderFillIDRef")

    def derive(self, reference: str | None, key: tuple[Any, ...], change: Callable[[Any], None]) -> str:
        """The id of the border fill that is *reference* (the basic solid one when the header lacks
        it) changed by *change*; *key* names the change for the memo."""

        from .formatting import derive_definition, find_definition

        memo_key = (reference, key)
        if memo_key in self.memo:
            return self.memo[memo_key]
        base = reference if find_definition(self.header, "borderFill", reference) is not None else None
        if base is None:
            base = self.document.ensure_basic_border_fill()
        found = derive_definition(self.header, "borderFill", base, change)
        self.memo[memo_key] = found
        return found


def _set_sides(candidate: Any, sides: Iterable[str], line: dict[str, str]) -> None:
    for side in sides:
        name = _SIDE_ELEMENTS[side]
        target = candidate.find(HH + name)
        if target is None:
            target = candidate.makeelement(HH + name, {})
            rank = _BORDER_FILL_ORDER.index(name)
            index = sum(1 for child in candidate if _element_local_name(child) in _BORDER_FILL_ORDER[:rank])
            candidate.insert(index, target)
        for attribute in ("type", "width", "color"):
            target.set(attribute, line[attribute])


def _set_fill(candidate: Any, color: str | None) -> None:
    from .formatting import set_border_fill_color

    set_border_fill_color(candidate, color)


def _check_border_fill_id(table: Any, value: object) -> None:
    """Refuse *value* unless it is the id of an ``hh:borderFill`` the document's header defines."""

    model = table.paragraph.section.document
    header = model.headers[0] if model is not None and model.headers else None
    fills = header._border_fills_element() if header is not None else None
    known = fills is not None and not isinstance(value, bool) and isinstance(value, (str, int)) and any(
        node.get("id") == str(value) for node in fills)
    if not known:
        raise _refuse(f"border fill {value!r} is not defined in the document's header",
                      "table-border-fill-not-found",
                      "Pass the id of an existing border fill, e.g. one doc.styles.ensure_border_fill(...) returns.",
                      value=repr(value))


def _border_line(line_type: object, width_mm: object, color: object) -> dict[str, str]:
    from .utils import line_width_text

    if not isinstance(color, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        raise _refuse(f"border color must be #RRGGBB; got {color!r}", "table-border-value",
                      "Pass a colour such as '#000000'.", color=repr(color))
    from .header_part import HwpxOxmlHeader

    allowed = tuple(sorted(HwpxOxmlHeader._BORDER_LINE_TYPES | {"NONE"}))
    if not isinstance(line_type, str) or line_type not in allowed:
        raise _refuse(f"line_type must be one of {', '.join(allowed)}; got {line_type!r}", "table-border-value",
                      "Pass an OWPML line type such as 'SOLID', 'DASH', 'DOUBLE_SLIM' or 'NONE' (no line).",
                      line_type=repr(line_type))
    if isinstance(width_mm, bool) or not isinstance(width_mm, (int, float)):
        raise _refuse(f"border_width_mm must be a number of millimetres; got {width_mm!r}", "table-border-value",
                      "Pass a line width in mm such as 0.12 or 0.4.", border_width_mm=repr(width_mm))
    return {"type": line_type, "width": line_width_text(width_mm, argument="border_width_mm"), "color": color.upper()}


# ----------------------------------------------------------------------------------------------
# cell
# ----------------------------------------------------------------------------------------------


def refuse_cell_without_sublist(cell: Any) -> None:
    """Refuse to write into the cell element *cell* when it holds its paragraphs as its own children, with no
    ``hp:subList``: no writer of Hancom's makes such a cell, and Hancom 2024 does not open the documents
    that have them (``tests/fixtures/reader_robustness/irb_form_*``), so there is no form to write by."""

    if cell.find(f"{_HP}p") is not None:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "the cell holds its paragraphs without an hp:subList, a form Hancom does not write or open; "
            "it is read, not written",
            code="table-cell-no-sublist",
            suggestion="Read the cell (cell.paragraphs, cell.text); write into a document Hancom wrote.",
        )


class TableCellFormat:
    """A cell's vertical alignment, header mark, border fill read and emptying."""

    element: Any
    table: "HwpxOxmlTable"

    @property
    def has_sub_list(self) -> bool:
        """Whether the cell holds its paragraphs in an ``hp:subList``, as Hancom writes every cell. ``False``
        for a cell some other writer gave its paragraphs as its own children: :attr:`paragraphs` reads them,
        and a write into the cell is refused (``table-cell-no-sublist``)."""

        return self.element.find(f"{_HP}subList") is not None or self.element.find(f"{_HP}p") is None

    @property
    def address_written(self) -> bool:
        """Whether the cell's ``hp:cellAddr`` is written with both of its numbers (Hancom writes it in every
        cell). ``False`` when it is not: :attr:`address` then reads ``(0, 0)``, which is not the cell's
        place; ``table.cell_map`` gives the place from the grid."""

        addr = self.element.find(f"{_HP}cellAddr")
        if addr is None:
            return False
        return all(str(addr.get(name, "")).strip().isdigit() for name in ("rowAddr", "colAddr"))

    if TYPE_CHECKING:
        def _ensure_sublist(self) -> Any: ...
        def _clear_own_layout_caches(self) -> None: ...

    @property
    def vertical_alignment(self) -> str:
        """Where the cell's lines sit between its top and bottom: ``"TOP"``, ``"CENTER"`` or ``"BOTTOM"``
        (``hp:subList/@vertAlign``; ``"TOP"``, the schema default, when the cell does not say).

        Setting it takes one of the three (exact, uppercase); anything else is refused
        (``table-cell-vertical-alignment-value``). The cell's paragraphs and the paragraph holding
        the table lose their line layout cache when it changes.
        """

        sublist = self.element.find(f"{_HP}subList")
        return (sublist.get("vertAlign") if sublist is not None else None) or "TOP"

    @vertical_alignment.setter
    def vertical_alignment(self, value: str) -> None:
        wanted = _member(value, CELL_VERTICAL_ALIGNMENTS, argument="vertical_alignment",
                         code="table-cell-vertical-alignment-value")
        sublist = self._ensure_sublist()
        if sublist.get("vertAlign") != wanted:
            sublist.set("vertAlign", wanted)
            self._clear_own_layout_caches()
            self.table.mark_dirty()

    @property
    def is_header(self) -> bool:
        """Whether the cell is a title cell (``hp:tc/@header``, Hancom's 셀 속성 → 제목 셀).

        A table repeats its rows of title cells at the top of each page it runs onto when
        :attr:`HwpxOxmlTable.repeat_header` is on. Setting it takes ``True`` or ``False``
        (``table-header-rows-value``); :meth:`HwpxOxmlTable.set_header_rows` sets whole rows.
        """

        return (self.element.get("header") or "").strip().lower() in _TRUE

    @is_header.setter
    def is_header(self, value: bool) -> None:
        wanted = "1" if _flag(value, "is_header", "table-header-rows-value") else "0"
        if self.element.get("header") != wanted:
            self.element.set("header", wanted)
            self.table.mark_dirty()

    @property
    def border_fill_id_ref(self) -> str | None:
        """The id of the ``hh:borderFill`` the cell names (``hp:tc/@borderFillIDRef``), as written:
        its four lines, diagonals and fill.

        Setting it takes the id of a border fill the document defines (a ``str`` or ``int``, e.g. one
        ``doc.styles.ensure_border_fill(...)`` returns); an unknown id is refused with
        ``table-border-fill-not-found``, before anything changes. Only this cell's reference changes
        (:meth:`HwpxOxmlTable.set_cell_borders` also gives the neighbours the edge they share, as
        Hancom's border dialog does). The cell's size and margins stay, so no line layout cache is
        dropped, as for the table's own :attr:`HwpxOxmlTable.border_fill_id_ref`.
        """

        return self.element.get("borderFillIDRef")

    @border_fill_id_ref.setter
    def border_fill_id_ref(self, value: "str | int") -> None:
        _check_border_fill_id(self.table, value)
        if self.element.get("borderFillIDRef") != str(value):
            self.element.set("borderFillIDRef", str(value))
            self.table.mark_dirty()

    @property
    def border_fill(self) -> BorderFillInfo | None:
        """The cell's four lines, diagonal and solid fill as a value (``doc.styles.border_fill``'s
        type): the ``hh:borderFill`` the cell names, else the table's. ``None`` when the id names none."""

        from .header_fonts import border_fill_info

        model = self.table.paragraph.section.document
        header = model.headers[0] if model is not None and model.headers else None
        reference = self.element.get("borderFillIDRef") or self.table.element.get("borderFillIDRef")
        return border_fill_info(header, reference)

    @property
    def text_direction(self) -> str:
        """How the cell's text runs (``hp:subList/@textDirection``): ``"HORIZONTAL"``, left to right in
        lines going down, or ``"VERTICAL"``, top to bottom (Hancom's 셀 속성 → 세로쓰기).
        ``"HORIZONTAL"``, the schema default, when the cell does not say.

        Setting it takes one of the two (exact, uppercase; else ``table-cell-text-direction-value``).
        The cell keeps its size; its paragraphs and the paragraphs holding the table lose their line
        layout cache, as the lines are laid out anew.
        """

        sublist = self.element.find(f"{_HP}subList")
        return (sublist.get("textDirection") if sublist is not None else None) or "HORIZONTAL"

    @text_direction.setter
    def text_direction(self, value: str) -> None:
        wanted = _member(value, CELL_TEXT_DIRECTIONS, argument="text_direction",
                         code="table-cell-text-direction-value")
        sublist = self._ensure_sublist()
        if sublist.get("textDirection") != wanted:
            sublist.set("textDirection", wanted)
            self._clear_own_layout_caches()
            self.table.mark_dirty()

    @property
    def protected(self) -> bool:
        """Whether the cell is protected (``hp:tc/@protect``, Hancom's 셀 보호): its content cannot be
        changed in Hancom. Setting it takes ``True`` or ``False`` (``table-cell-flag-value``)."""

        return (self.element.get("protect") or "").strip().lower() in _TRUE

    @protected.setter
    def protected(self, value: bool) -> None:
        self._set_flag("protect", _flag(value, "protected", "table-cell-flag-value"))

    @property
    def editable(self) -> bool:
        """Whether the cell can be typed into while the document is in form mode (``hp:tc/@editable``,
        Hancom's 양식 모드에서 편집 가능). Setting it takes ``True`` or ``False``
        (``table-cell-flag-value``)."""

        return (self.element.get("editable") or "").strip().lower() in _TRUE

    @editable.setter
    def editable(self, value: bool) -> None:
        self._set_flag("editable", _flag(value, "editable", "table-cell-flag-value"))

    def _set_flag(self, attribute: str, value: bool) -> None:
        wanted = "1" if value else "0"
        if self.element.get(attribute) != wanted:
            self.element.set(attribute, wanted)
            self.table.mark_dirty()

    def clear(self) -> None:
        """Empty the cell: its paragraphs, tables and objects go, one empty paragraph stays.

        The empty paragraph keeps the first paragraph's paragraph shape and style and its first
        run's character shape, as Hancom's 지우기 leaves a cell; text typed in later looks as before.
        The paragraph holding the table loses its line layout cache.
        """

        sublist = self._ensure_sublist()
        paragraphs = sublist.findall(f"{_HP}p")
        first = paragraphs[0] if paragraphs else None
        attributes = {"id": _paragraph_id(self.table.paragraph.section._ids), "paraPrIDRef": "0", "styleIDRef": "0", "pageBreak": "0",
                      "columnBreak": "0", "merged": "0"}
        char_pr = "0"
        if first is not None:
            for name in ("paraPrIDRef", "styleIDRef"):
                if first.get(name) is not None:
                    attributes[name] = first.get(name) or "0"
            run = first.find(f"{_HP}run")
            if run is not None:
                char_pr = run.get("charPrIDRef") or "0"
            if len(paragraphs) == 1 and first.findall(f"{_HP}run") and all(
                _element_local_name(node) == "t" and not node.text and not len(node)
                for run in first.findall(f"{_HP}run") for node in run
            ) and len(first.findall(f"{_HP}run")) == 1:
                return  # already one empty paragraph
        for paragraph in paragraphs:
            sublist.remove(paragraph)
        paragraph = sublist.makeelement(f"{_HP}p", attributes)
        sublist.append(paragraph)
        run = paragraph.makeelement(f"{_HP}run", {"charPrIDRef": char_pr})
        paragraph.append(run)
        run.append(run.makeelement(f"{_HP}t", {}))
        _clear_paragraph_layout_cache(paragraph)
        self.table.mark_dirty()


# ----------------------------------------------------------------------------------------------
# row and column
# ----------------------------------------------------------------------------------------------


class TableRowFormat:
    """A row's place and stored height."""

    element: Any
    table: "HwpxOxmlTable"

    @property
    def index(self) -> int:
        """The row's place in the table, from 0 (its ``hp:tr`` among the table's)."""

        return next(i for i, row in enumerate(self.table.element.findall(f"{_HP}tr")) if row is self.element)

    @property
    def height(self) -> int:
        """The row's stored height in HWPUNIT (:attr:`HwpxOxmlTable.row_heights`); Hancom draws it
        taller when its text needs more room. Setting it is :meth:`HwpxOxmlTable.set_row_height`."""

        return self.table.row_heights[self.index]

    @height.setter
    def height(self, value: int) -> None:
        self.table.set_row_height(self.index, value)


class HwpxOxmlTableColumn:
    """A column of a table's grid. Hancom stores no column element: a column is the cells starting
    at it and its width is read from their ``hp:cellSz``."""

    def __init__(self, table: "HwpxOxmlTable", index: int) -> None:
        self.table = table
        self._index = index

    @property
    def index(self) -> int:
        """The column's place in the table's grid, from 0."""

        return self._index

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(index={self.index}, width={self.width})"

    @property
    def cells(self) -> tuple["HwpxOxmlTableCell", ...]:
        """The cells starting in this column (``colAddr`` equal to it), top to bottom.

        Like :attr:`HwpxOxmlTableRow.cells` for a row: a merged cell belongs to the column it starts
        in, so the columns of a table together hold each of its cells once.
        """

        found = [
            entry.cell for entry in self.table.iter_grid()
            if entry.is_anchor and entry.column == self.index
        ]
        return tuple(found)

    @property
    def width(self) -> int:
        """The column's width on the table's grid, in HWPUNIT (:attr:`HwpxOxmlTable.column_widths`).
        Setting it is :meth:`HwpxOxmlTable.set_column_width`."""

        return self.table.column_widths[self.index]

    @width.setter
    def width(self, value: int) -> None:
        self.table.set_column_width(self.index, value)


# ----------------------------------------------------------------------------------------------
# table
# ----------------------------------------------------------------------------------------------


class TableFormat:
    """A table's alignment, page flow, header rows, ranges of cells, borders, shading, zones and copies."""

    element: Any
    paragraph: "HwpxOxmlParagraph"

    if TYPE_CHECKING:
        row_count: int
        column_count: int

        def mark_dirty(self) -> None: ...
        def iter_grid(self) -> Any: ...
        def cell(self, row: int, col: int) -> "HwpxOxmlTableCell": ...
        @classmethod
        def _parse_spreadsheet_range(cls, value: str) -> tuple[int, int, int, int]: ...

    # -- sizes and margins (bodies in table_sizes.py) and placement (shape_position.py) ---------

    width = property(_table_sizes.table_width)
    set_width = _table_sizes.set_table_width
    column_widths = property(_table_sizes.column_widths)
    row_heights = property(_table_sizes.row_heights)
    set_column_width = _table_sizes.set_column_width
    set_row_height = _table_sizes.set_row_height
    in_margins = property(_table_sizes.table_in_margins)
    set_in_margins = _table_sizes.set_table_in_margins
    # The same placement call every object takes: treat_as_char, text_wrap, offsets, frames.
    set_position = _object_set_position
    # The same placement reads every object has (bodies in shape_position.ObjectPlacement): where it
    # sits (frames, offsets of a floating table, text wrap and flow), its drawing order, its lock and
    # the caption numbering it counts in.
    position = ObjectPlacement.position
    z_order = ObjectPlacement.z_order
    locked = ObjectPlacement.locked
    numbering_type = ObjectPlacement.numbering_type
    # The section whose part holds the table (a nested table's too); None on a master page.
    section = ObjectPlacement.section

    @property
    def cell_spacing(self) -> int:
        """The room between the table's cells and around them (``hp:tbl/@cellSpacing``, HWPUNIT);
        0 when they touch.

        Setting it takes an int in ``0 <= value <= 32767`` (``table-cell-spacing-value``). The cells
        keep their sizes and the table grows or shrinks around them, as Hancom stores a spaced table:
        its ``hp:sz`` width is the columns plus one spacing more than there are columns, its height
        the rows on its first page plus one spacing more than those rows (Hancom-saved tables with
        spacings 200 and 850 hold exactly these). The paragraph holding the table loses its line
        layout cache. With spacing, the table's own border and fill (:attr:`border_fill_id_ref`)
        show in the gaps.
        """

        try:
            return int(self.element.get("cellSpacing") or 0)
        except ValueError:
            return 0

    @cell_spacing.setter
    def cell_spacing(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_CELL_SPACING:
            raise _refuse(f"cell_spacing must be an int in 0..{_MAX_CELL_SPACING} (HWPUNIT); got {value!r}",
                          "table-cell-spacing-value", "Pass the room between cells in HWPUNIT, e.g. 283 for 1 mm.",
                          value=repr(value))
        before = self.cell_spacing
        if value == before and self.element.get("cellSpacing") is not None:
            return
        size = self.element.find(f"{_HP}sz")
        if size is not None:
            size.set("width", str(sum(_table_sizes.column_widths(self)) + (self.column_count + 1) * value))
            heights = _table_sizes.row_heights(self)
            try:
                stored = int(size.get("height") or 0)
            except ValueError:
                stored = -1
            # Hancom stores the height of the rows on the table's first page with their spacings: the same
            # rows take the new spacing (a table on one page: all of them).
            for count in range(len(heights), 0, -1):
                if stored == sum(heights[:count]) + (count + 1) * before:
                    size.set("height", str(sum(heights[:count]) + (count + 1) * value))
                    break
        self.element.set("cellSpacing", str(value))
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.mark_dirty()

    @property
    def border_fill_id_ref(self) -> str | None:
        """The id of the table's own ``hh:borderFill`` (``hp:tbl/@borderFillIDRef``): the border and
        fill of the table itself. Hancom draws its fill behind the cells (a cell without a fill of its
        own shows it) and its lines around the table where cell spacing leaves room (with no spacing the
        cells' own lines cover them). As written; ``None`` when the table names none.

        Setting it takes the id of a border fill the document defines (a ``str`` or ``int``, e.g. one
        ``doc.styles.ensure_border_fill(...)`` returns); an unknown id is refused with
        ``table-border-fill-not-found``. The cells keep their own.
        """

        return self.element.get("borderFillIDRef")

    @border_fill_id_ref.setter
    def border_fill_id_ref(self, value: "str | int") -> None:
        _check_border_fill_id(self, value)
        if self.element.get("borderFillIDRef") != str(value):
            self.element.set("borderFillIDRef", str(value))
            self.mark_dirty()

    @property
    def border_fill(self) -> BorderFillInfo | None:
        """The table's own four lines, diagonal and solid fill (:attr:`border_fill_id_ref`) as a value,
        ``TableCell.border_fill``'s type; ``None`` when the id names none."""

        from .header_fonts import border_fill_info

        model = self.paragraph.section.document
        header = model.headers[0] if model is not None and model.headers else None
        return border_fill_info(header, self.element.get("borderFillIDRef"))

    def _floating(self) -> bool:
        position = self.element.find(f"{_HP}pos")
        return position is not None and (position.get("treatAsChar") or "").strip().lower() not in _TRUE

    @property
    def alignment(self) -> Alignment:
        """Where the table sits across its line: :class:`hwpx.objects.Alignment` ``LEFT``,
        ``CENTER`` or ``RIGHT`` (also a ``str``: ``table.alignment == "CENTER"`` holds).

        A table set as a character (:attr:`treat_as_char`) sits where its paragraph's alignment puts
        it: ``CENTER`` and ``RIGHT`` as they are, anything else (justified, distributed) on the
        left. A floating table reads its ``hp:pos/@horzAlign``, measured in its ``horzRelTo`` frame;
        the two values a floating table can have besides those three, ``"INSIDE"`` and
        ``"OUTSIDE"`` (book-binding sides), read as those plain strings.

        Setting it takes ``LEFT``, ``CENTER`` or ``RIGHT`` (an ``Alignment`` or the exact uppercase
        string; else ``table-alignment-value``). A table set as a character goes where its
        paragraph's alignment puts it, as Hancom aligns one, so the paragraph holding it takes that
        alignment (a paragraph shape derived from its own: line spacing, indents and the rest
        stay). Other text in that paragraph moves with it. A floating table takes it as
        ``hp:pos/@horzAlign`` in its own frame; its offset stays. The paragraph holding the table
        loses its line layout cache.
        """

        position = self.element.find(f"{_HP}pos")
        if self._floating():
            written = (position.get("horzAlign") if position is not None else None) or "LEFT"
            return Alignment(written) if written in TABLE_ALIGNMENTS else cast(Alignment, written)
        model = self.paragraph.section.document
        shape = model.paragraph_property(self.paragraph.element.get("paraPrIDRef")) if model else None
        horizontal = shape.alignment.horizontal if shape is not None and shape.alignment is not None else None
        return Alignment(horizontal) if horizontal in ("CENTER", "RIGHT") else Alignment.LEFT

    @alignment.setter
    def alignment(self, alignment: "Alignment | str") -> None:
        value = _member(str(alignment) if isinstance(alignment, Alignment) else alignment, TABLE_ALIGNMENTS,
                        argument="alignment", code="table-alignment-value")
        if value == self.alignment:
            return
        if self._floating():
            self.element.find(f"{_HP}pos").set("horzAlign", value)
        else:
            model = self.paragraph.section.document
            if model is None or not model.headers:
                raise _refuse("aligning a table set as a character needs the document's header",
                              "table-alignment-value", "Align a table that belongs to an opened or created document.")
            shape_id = model.headers[0].ensure_paragraph_format(
                base_para_pr_id=self.paragraph.element.get("paraPrIDRef"), alignment=value,
            )
            self.paragraph.element.set("paraPrIDRef", str(shape_id))
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.mark_dirty()

    @property
    def text_wrap(self) -> str | None:
        """How the body text goes around the table (``hp:tbl/@textWrap``, e.g. ``"TOP_AND_BOTTOM"``), as
        written; set it with :meth:`set_position`."""

        return self.element.get("textWrap")

    # -- page flow and header rows -------------------------------------------------------------

    @property
    def page_split(self) -> str:
        """How the table splits where a page ends (``hp:tbl/@pageBreak``, Hancom's 표 속성 → 쪽 경계에서
        나눔): ``"TABLE"`` splits it, ``"CELL"`` splits it between rows of cells, ``"NONE"`` moves it
        whole to the next page. (Not ``Paragraph.page_break``, the page break before a paragraph.)

        Setting it takes one of the three (exact, uppercase; else ``table-page-split-value``). The
        paragraph holding the table loses its line layout cache.
        """

        return self.element.get("pageBreak") or "CELL"

    @page_split.setter
    def page_split(self, value: str) -> None:
        wanted = _member(value, TABLE_PAGE_SPLITS, argument="page_split", code="table-page-split-value")
        if self.element.get("pageBreak") != wanted:
            self.element.set("pageBreak", wanted)
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.mark_dirty()

    @property
    def repeat_header(self) -> bool:
        """Whether the title rows repeat at the top of each page the table runs onto (``hp:tbl/@repeatHeader``,
        Hancom's 표 속성 → 제목 줄 자동 반복).

        Setting it takes ``True`` or ``False`` (``table-header-rows-value``) and writes only this flag:
        the title cells (:attr:`HwpxOxmlTableCell.is_header`) stay as they are. The two are separate in
        Hancom's files too: the tables Hancom made and saved in ``tests/fixtures/hancom_saved``
        (``cell_border_2x3_base.hwpx`` and the others) say ``repeatHeader="1"`` with no title cell.
        :meth:`set_header_rows` sets the title rows and the flag together. The paragraph
        holding the table loses its line layout cache, as for :attr:`page_split`: the table's pages
        are laid out anew.
        """

        return (self.element.get("repeatHeader") or "").strip().lower() in _TRUE

    @repeat_header.setter
    def repeat_header(self, value: bool) -> None:
        wanted = "1" if _flag(value, "repeat_header", "table-header-rows-value") else "0"
        if self.element.get("repeatHeader") != wanted:
            self.element.set("repeatHeader", wanted)
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.mark_dirty()

    @property
    def no_adjust(self) -> bool:
        """``hp:tbl/@noAdjust`` as written (Hancom's 표 속성 "자동으로 크기 조절" turned off).
        Setting it takes ``True`` or ``False`` (``table-no-adjust-value``)."""

        return (self.element.get("noAdjust") or "").strip().lower() in _TRUE

    @no_adjust.setter
    def no_adjust(self, value: bool) -> None:
        wanted = "1" if _flag(value, "no_adjust", "table-no-adjust-value") else "0"
        if self.element.get("noAdjust") != wanted:
            self.element.set("noAdjust", wanted)
            self.mark_dirty()

    @property
    def header_rows(self) -> int:
        """How many rows from the top hold only title cells (:attr:`HwpxOxmlTableCell.is_header`)."""

        flags: dict[int, bool] = {}
        for entry in self.iter_grid():
            flags[entry.row] = flags.get(entry.row, True) and entry.cell.is_header
        count = 0
        while flags.get(count):
            count += 1
        return count

    def set_header_rows(self, count: int, *, repeat: bool = True) -> None:
        """Make the first *count* rows the table's title rows, and repeat them on each page (*repeat*).

        Their cells become title cells and every other cell stops being one; *repeat* writes
        ``repeatHeader`` (off when *count* is 0). A cell merged across the line under the title
        rows is refused, as is a *count* outside ``0..row_count`` (``table-header-rows-value``).
        """

        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= self.row_count:
            raise _refuse(f"count must be an int in 0..{self.row_count}; got {count!r}", "table-header-rows-value",
                          "Pass how many rows from the top are title rows.", count=repr(count))
        _flag(repeat, "repeat", "table-header-rows-value")
        cells: dict[int, Any] = {}
        for entry in self.iter_grid():
            cells[id(entry.cell.element)] = entry
        for entry in cells.values():
            top, span = entry.anchor[0], entry.span[0]
            if top < count < top + span:
                raise _refuse(f"cell {entry.anchor} is merged across the line under row {count - 1}",
                              "table-header-rows-value",
                              "Split that cell first, or choose a count at the bottom of a merged cell.",
                              row=entry.anchor[0], col=entry.anchor[1])
        for entry in cells.values():
            entry.cell.is_header = entry.anchor[0] < count
        wanted = "1" if repeat and count > 0 else "0"
        if self.element.get("repeatHeader") != wanted:
            self.element.set("repeatHeader", wanted)
        _clear_paragraph_layout_cache(self.paragraph.element)
        self.mark_dirty()

    # -- columns and ranges --------------------------------------------------------------------

    @property
    def columns(self) -> tuple[HwpxOxmlTableColumn, ...]:
        """The table's grid columns, left to right (``len(table.columns) == table.column_count``)."""

        return tuple(HwpxOxmlTableColumn(self, index) for index in range(self.column_count))  # type: ignore[arg-type]

    def _range(self, cell_range: str | None) -> tuple[int, int, int, int]:
        """(top, left, bottom, right) of *cell_range*, grown to cover each merged cell it touches."""

        from .table_merge import check_merge_range

        if cell_range is None:
            return 0, 0, self.row_count - 1, self.column_count - 1
        if not isinstance(cell_range, str):
            raise _refuse(f"cell_range must be a str such as 'A1:B2' or 'B2'; got {cell_range!r}",
                          "table-merge-range-invalid", "Pass a spreadsheet range such as 'A1:C1', or None for every cell.")
        text = cell_range if ":" in cell_range else f"{cell_range}:{cell_range}"
        top, left, bottom, right = self._parse_spreadsheet_range(text)
        check_merge_range(top, left, bottom, right, self.row_count, self.column_count)
        while True:
            grown = (top, left, bottom, right)
            for entry in self.iter_grid():
                if top <= entry.row <= bottom and left <= entry.column <= right:
                    (r0, c0), (rs, cs) = entry.anchor, entry.span
                    top, left = min(top, r0), min(left, c0)
                    bottom, right = max(bottom, r0 + rs - 1), max(right, c0 + cs - 1)
            if grown == (top, left, bottom, right):
                return grown

    def cells_in(self, cell_range: str | None = None) -> tuple["HwpxOxmlTableCell", ...]:
        """The cells in *cell_range* (``"A1:C2"``, ``"B2"``; ``None``: the whole table), each once, in
        reading order. A merged cell counts when any part of it is in the range."""

        top, left, bottom, right = self._range(cell_range)
        seen: dict[int, "HwpxOxmlTableCell"] = {}
        for entry in self.iter_grid():
            if top <= entry.row <= bottom and left <= entry.column <= right:
                seen.setdefault(id(entry.cell.element), entry.cell)
        return tuple(sorted(seen.values(), key=lambda cell: cell.address))

    def set_borders(
        self,
        cell_range: str | None = None,
        *,
        sides: Sequence[str] | None = None,
        line_type: str = "SOLID",
        border_width_mm: float = 0.12,
        color: str = "#000000",
        inner: bool = True,
    ) -> None:
        """Draw one kind of line on the cells of *cell_range* (``None``: the whole table).

        *sides* picks the cell sides (``"left"``, ``"right"``, ``"top"``, ``"bottom"``; all four when
        ``None``). With *inner* ``False`` only the sides on the range's outline change, so
        ``table.set_borders(border_width_mm=0.4, inner=False)`` draws a thick frame around the table.
        *line_type* is an OWPML line type (``"SOLID"``, ``"DASH"``, ``"DOUBLE_SLIM"``...; ``"NONE"``
        draws no line), *border_width_mm* a width in mm (written as the nearest of Hancom's widths) and
        *color* ``#RRGGBB``. A cell outside the range that shares an outline side takes the same
        line on it, as Hancom's cell border command does (a merged neighbour reaching past the range
        keeps its own). Each cell keeps its other sides, diagonals and fill: the line goes into a
        border fill derived from the cell's own, reused when an identical one exists. Bad values
        are refused before anything changes (``table-border-value``).
        """

        chosen = BORDER_SIDES if sides is None else tuple(sides)
        if isinstance(sides, str) or not chosen or any(side not in BORDER_SIDES for side in chosen):
            raise _refuse(f"sides must name some of {', '.join(BORDER_SIDES)}; got {sides!r}", "table-border-value",
                          "Pass e.g. sides=('top', 'bottom'), or leave it out for all four.", sides=repr(sides))
        _flag(inner, "inner", "table-border-value")
        line = _border_line(line_type, border_width_mm, color)
        top, left, bottom, right = self._range(cell_range)
        fills = _BorderFills(self)  # type: ignore[arg-type]
        changes: dict[int, tuple["HwpxOxmlTableCell", set[str]]] = {}
        for entry in self.iter_grid():
            cell = entry.cell
            (r0, c0), (rs, cs) = entry.anchor, entry.span
            r1, c1 = r0 + rs - 1, c0 + cs - 1
            inside = top <= r0 and r1 <= bottom and left <= c0 and c1 <= right
            on_edge = {"left": c0 == left, "right": c1 == right, "top": r0 == top, "bottom": r1 == bottom}
            if inside:
                wanted = {side for side in chosen if inner or on_edge[side]}
            else:  # a neighbour sharing an outline side, lying within that side
                rows_within, cols_within = top <= r0 and r1 <= bottom, left <= c0 and c1 <= right
                touching = {"left": c0 == right + 1 and rows_within, "right": c1 == left - 1 and rows_within,
                            "top": r0 == bottom + 1 and cols_within, "bottom": r1 == top - 1 and cols_within}
                mirror = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
                wanted = {side for side, hit in touching.items() if hit and mirror[side] in chosen}
            if wanted:
                changes.setdefault(id(cell.element), (cell, set()))[1].update(wanted)
        for cell, wanted in changes.values():
            ordered = tuple(side for side in BORDER_SIDES if side in wanted)
            new_id = fills.derive(fills.base_id(cell), ("sides", ordered, tuple(sorted(line.items()))),
                                  lambda candidate, ordered=ordered: _set_sides(candidate, ordered, line))
            cell.element.set("borderFillIDRef", new_id)
        if changes:
            self.mark_dirty()

    def set_shading(self, cell_range: str | None = None, *, color: str | None) -> None:
        """Fill the cells of *cell_range* (``None``: the whole table) with *color* (``#RRGGBB``), or take
        their fill away (``None``). Each cell keeps its lines: the fill goes into a border fill
        derived from the cell's own (``table-shading-value`` for a bad colour)."""

        if color is not None and (not isinstance(color, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None):
            raise _refuse(f"color must be #RRGGBB or None; got {color!r}", "table-shading-value",
                          "Pass a colour such as '#D9D9D9', or None to take the fill away.", color=repr(color))
        value = color.upper() if color is not None else None
        fills = _BorderFills(self)  # type: ignore[arg-type]
        cells = self.cells_in(cell_range)
        for cell in cells:
            new_id = fills.derive(fills.base_id(cell), ("fill", value),
                                  lambda candidate: _set_fill(candidate, value))
            cell.element.set("borderFillIDRef", new_id)
        if cells:
            self.mark_dirty()

    @property
    def cell_zones(self) -> tuple[CellZone, ...]:
        """The table's cell zones (``hp:cellzoneList/hp:cellzone``): rectangles of cells drawn with a
        border fill of their own over the cells' own, in document order."""

        zones = []
        for zone in self.element.findall(f"{_HP}cellzoneList/{_HP}cellzone"):
            values = [int(zone.get(name) or 0) for name in ("startRowAddr", "startColAddr", "endRowAddr", "endColAddr")]
            zones.append(CellZone(*values, border_fill_id_ref=zone.get("borderFillIDRef")))
        return tuple(zones)

    def _zone_border_fill(self, border_fill_id_ref: object) -> str:
        if isinstance(border_fill_id_ref, bool) or not isinstance(border_fill_id_ref, (str, int)):
            raise _refuse(f"border_fill_id_ref must be a border fill id; got {border_fill_id_ref!r}",
                          "table-cell-zone-border-fill-unknown",
                          "Pass an id from doc.styles.ensure_border_fill(...).", requested=repr(border_fill_id_ref))
        reference = str(border_fill_id_ref).strip()
        model = self.paragraph.section.document
        if model is None or reference not in model.border_fills:
            raise _refuse(f"the document has no border fill {reference!r}", "table-cell-zone-border-fill-unknown",
                          "Make one with doc.styles.ensure_border_fill(...) and pass its id.", requested=reference)
        return reference

    def _zone_elements(self) -> list[Any]:
        return self.element.findall(f"{_HP}cellzoneList/{_HP}cellzone")

    def _zone_bounds(self, cell_range: object) -> tuple[int, int, int, int]:
        """(top, left, bottom, right) of *cell_range* on the table's grid, as written: a zone is a
        rectangle of grid cells, and Hancom saves zones that cut through a merged cell."""

        from .table_merge import check_merge_range

        if not isinstance(cell_range, str) or not cell_range:
            raise _refuse(f"cell_range must be a str such as 'A1:B2' or 'B2'; got {cell_range!r}",
                          "table-merge-range-invalid", "Pass a spreadsheet range such as 'A2:C4'.")
        text = cell_range if ":" in cell_range else f"{cell_range}:{cell_range}"
        top, left, bottom, right = self._parse_spreadsheet_range(text)
        check_merge_range(top, left, bottom, right, self.row_count, self.column_count)
        return top, left, bottom, right

    def _zone_at(self, index: object) -> Any:
        zones = self._zone_elements()
        if isinstance(index, bool) or not isinstance(index, int) or not -len(zones) <= index < len(zones):
            raise _refuse(f"the table has no cell zone {index!r} ({len(zones)} zones)", "table-cell-zone-not-found",
                          "Pass an index into table.cell_zones.", requested=repr(index), count=len(zones))
        return zones[index]

    def add_cell_zone(self, cell_range: str, *, border_fill_id_ref: str | int) -> CellZone:
        """Draw the border fill *border_fill_id_ref* over the cells of *cell_range* (``"A2:B3"``) as one
        area, a cell zone (``hp:cellzone``), and return it as :attr:`cell_zones` reads it.

        This is what Hancom saves when a border, a diagonal or a fill is given to several cells at once
        "as one cell": the zone's lines run around the range and its fill covers it whole. The range is
        taken on the table's grid as written (Hancom's own zones may cut through a merged cell); the
        cells keep their own border fills. *border_fill_id_ref* names a border fill of the document
        (``doc.styles.ensure_border_fill(...)``); an unknown one is refused
        (``table-cell-zone-border-fill-unknown``), as is a range outside the table. The zone goes after
        the table's others (``hp:cellzoneList`` before the rows, made when the table has none).
        """

        top, left, bottom, right = self._zone_bounds(cell_range)
        reference = self._zone_border_fill(border_fill_id_ref)
        holder = self.element.find(f"{_HP}cellzoneList")
        if holder is None:
            holder = self.element.makeelement(f"{_HP}cellzoneList", {})
            rows = [i for i, child in enumerate(self.element) if _element_local_name(child) == "tr"]
            self.element.insert(rows[0] if rows else len(self.element), holder)
        holder.append(holder.makeelement(f"{_HP}cellzone", {
            "startRowAddr": str(top), "startColAddr": str(left), "endRowAddr": str(bottom), "endColAddr": str(right),
            "borderFillIDRef": reference,
        }))
        self.mark_dirty()
        return self.cell_zones[-1]

    def set_cell_zone(
        self, index: int, *, cell_range: str | None = None, border_fill_id_ref: str | int | None = None
    ) -> CellZone:
        """Move cell zone *index* (of :attr:`cell_zones`) to *cell_range* and/or give it the border fill
        *border_fill_id_ref*, checked as :meth:`add_cell_zone` checks them, and return it as it is now.
        A zone that is not there is ``table-cell-zone-not-found``."""

        zone = self._zone_at(index)
        bounds = self._zone_bounds(cell_range) if cell_range is not None else None
        reference = self._zone_border_fill(border_fill_id_ref) if border_fill_id_ref is not None else None
        before = dict(zone.attrib)
        if bounds is not None:
            for name, value in zip(("startRowAddr", "startColAddr", "endRowAddr", "endColAddr"), bounds):
                zone.set(name, str(value))
        if reference is not None:
            zone.set("borderFillIDRef", reference)
        if dict(zone.attrib) != before:
            self.mark_dirty()
        return self.cell_zones[self._zone_elements().index(zone)]

    def remove_cell_zone(self, index: int) -> None:
        """Take cell zone *index* (of :attr:`cell_zones`) away; its cells show their own borders and fills
        again. The list goes with its last zone, as Hancom writes a table without zones."""

        zone = self._zone_at(index)
        holder = zone.getparent()
        holder.remove(zone)
        if not len(holder):
            self.element.remove(holder)
        self.mark_dirty()

    # -- copy --------------------------------------------------------------------------------

    def copy_after(self, paragraph: "int | HwpxOxmlParagraph | None" = None) -> "HwpxOxmlTable":
        """Put a copy of the table in a new paragraph right after *paragraph* and return the copy.

        *paragraph* is a paragraph of the same document (also one in a cell), or its index in the
        document's paragraphs; ``None`` is the paragraph holding this table. The copy has fresh
        ids (its tables, objects and paragraphs; a field's begin and end get a new pair, so a
        copied form field fills apart from the original; a memo anchored in a cell becomes a memo
        of its own) and no line layout caches. The new paragraph takes the paragraph shape and
        style of the one holding this table. ``copy_to`` puts a copy into an existing paragraph.
        """

        from .paragraph import HwpxOxmlParagraph
        from .table import HwpxOxmlTable
        from ._paragraph_text_edit import paragraph_container, renumber_copied_fields

        section = self.paragraph.section
        model = section.document
        if paragraph is None:
            target = self.paragraph
        elif isinstance(paragraph, HwpxOxmlParagraph):
            target = paragraph
        elif isinstance(paragraph, int) and not isinstance(paragraph, bool) and model is not None:
            paragraphs = model.paragraphs
            if not -len(paragraphs) <= paragraph < len(paragraphs):
                from .utils import HwpxIndexError

                raise HwpxIndexError(f"paragraph {paragraph} is out of range ({len(paragraphs)} paragraphs)",
                                     code="paragraph-not-in-document", context={"requested": paragraph},
                                     suggestion=f"Pass an index in 0..{len(paragraphs) - 1}, or the paragraph itself.")
            target = paragraphs[paragraph]
        else:
            raise _refuse(f"paragraph must be a paragraph or its index; got {paragraph!r}",
                          "paragraph-not-in-document", "Pass a paragraph of this document, or its index.")
        parent = paragraph_container(target.element, target.section.element)
        if parent is None or target.section.document is not model:
            raise _refuse("the paragraph does not belong to this table's document", "paragraph-not-in-document",
                          "Pass a paragraph of the document that holds the table.")
        host = self.paragraph.element
        new = host.makeelement(host.tag, {"id": _paragraph_id(target.section._ids), "paraPrIDRef": host.get("paraPrIDRef") or "0",
                                          "styleIDRef": host.get("styleIDRef") or "0", "pageBreak": "0",
                                          "columnBreak": "0", "merged": "0"})
        source_run = next((run for run in host.findall(f"{_HP}run") if any(c is self.element for c in run)), None)
        run = new.makeelement(f"{_HP}run", {"charPrIDRef": (source_run.get("charPrIDRef") if source_run is not None
                                                             else None) or "0"})
        new.append(run)
        copy = deepcopy(self.element)
        copy.tail = None
        _refresh_copied_paragraph_subtree_ids(copy, ids=target.section._ids)
        renumber_copied_fields(copy, ids=target.section._ids)
        for node in copy.iter(f"{_HP}p"):
            _clear_paragraph_layout_cache(node)
        from .memo import renew_copied_memos  # a copied memo anchor gets a memo of its own

        renew_copied_memos(copy, list(model.sections) if model is not None else [section], target.section)
        run.append(copy)
        parent.insert(list(parent).index(target.element) + 1, new)
        from .shape_position import stack_new_object

        stack_new_object(copy, target.section)  # over the others, as Hancom pastes a copy
        _clear_paragraph_layout_cache(new)
        from .note_authoring import renumber_notes_holding

        renumber_notes_holding(target.section, (copy,))
        target.section.mark_dirty()
        return HwpxOxmlTable(copy, HwpxOxmlParagraph(new, target.section))
