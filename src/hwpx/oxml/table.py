# SPDX-License-Identifier: Apache-2.0
"""Table, row, grid, and cell OXML services."""

from __future__ import annotations

import re as _re
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, NoReturn, Sequence, cast
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _require_text,
    SameElement,
    _DEFAULT_CELL_HEIGHT,
    _DEFAULT_CELL_WIDTH,
    _default_cell_inner_margin_attributes,
    paragraph_attributes,
    _HP,
    _append_child,
    _append_text_with_tabs,
    _clear_paragraph_layout_cache,
    _default_cell_attributes,
    _default_cell_margin_attributes,
    _default_cell_paragraph_attributes,
    _default_sublist_attributes,
    _distribute_size,
    _element_local_name,
    _normalize_color,
    _object_id,
    _paragraph_id,
    FILL_GRADIENT_TYPES,
    FILL_IMAGE_MODES,
)
from ._paragraph_text_edit import clear_text_element, sanitize_keeping_tabs, set_text_with_tabs
from ._paragraph_text_edit import live_paragraph, new_own_text_node, own_text_nodes
from . import table_sizes as _table_sizes
from .table_format import (
    TableCellFormat, TableFormat, TableRowFormat, _BorderFills, _set_fill, refuse_cell_without_sublist,
)
from .table_structure import TableStructureEdits
from .utils import HwpxIndexError
from ..errors import rejects_removed_arguments

from .body import Label, parse_label_element
from .objects import Caption, _read_caption, _remove_caption, _write_caption
from .table_merge import TableGridCache as _TableGridCache, collapse_merged_grid
from .table_merge import bad_spreadsheet_range, cell_out_of_range, cell_remove_refused, check_merge_range

if TYPE_CHECKING:
    from ._document_primitives import IdSource
    from hwpx.form_fit.policy import FitPolicy
    from ..objects.binary_item import BinaryItem
    from hwpx.form_fit.report import FitResult
    from .paragraph import HwpxOxmlParagraph
    from .header import Style
    from .section import HwpxOxmlSection


def _set_cell_borders_preserving(table: Any, cell: Any, color: str, line_type: str) -> None:
    from ..errors import HwpxValueError
    from ._document_primitives import _normalize_border_type
    from .namespaces import HH

    def refuse(message: str) -> NoReturn:
        raise HwpxValueError(
            message, code="cell-border-edit-unsupported",
            suggestion="Select a cell with one existing complete border style and a #RRGGBB color.",
        )

    if not isinstance(color, str) or _re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        refuse("border color must be #RRGGBB")
    document = table.paragraph.section.document
    if document is None or not document.headers:
        refuse("cell border edit requires an attached document header")
    header = document.headers[0]
    try:
        line_type = _normalize_border_type(
            header._BORDER_LINE_TYPE_ALIASES.get(str(line_type).upper(), line_type), header._BORDER_LINE_TYPES
        )
    except (ValueError, TypeError, AttributeError):
        refuse("border line type is unsupported")
    container = header._border_fills_element()
    if container is None:
        refuse("existing border style container is missing")
    reference = cell.element.get("borderFillIDRef") or table.element.get("borderFillIDRef")
    matches = [n for n in container if n.tag == HH + "borderFill" and n.get("id") == reference]
    if len(matches) != 1:
        refuse("existing cell border style is missing or ambiguous")
    _color_existing_borders(deepcopy(matches[0]), color, line_type)  # refuses before anything changes
    from .formatting import derive_definition

    derived = derive_definition(
        header, "borderFill", reference, lambda candidate: _color_existing_borders(candidate, color, line_type)
    )
    cell.element.set("borderFillIDRef", derived)
    table.mark_dirty()
    _match_touching_edges(table, cell)


#: (side of the edited cell, side of the neighbour that shares it)
_SHARED_EDGES = (("rightBorder", "leftBorder"), ("leftBorder", "rightBorder"),
                 ("bottomBorder", "topBorder"), ("topBorder", "bottomBorder"))


def _match_touching_edges(table: Any, cell: Any) -> None:
    """Give each neighbour of *cell* the same line on the edge they share.

    Hancom's cell border command sets both cells of a shared edge. Every cell
    keeps its own four sides and both are drawn, so a neighbour that keeps its
    old line shows through a new one (or keeps a line meant to go). Only the
    neighbour's shared side changes; its other sides and fill stay. Like
    Hancom, a neighbour whose side reaches past this cell's (a merged cell
    beside a single one) is left as it is.
    """
    from .namespaces import HH

    document = table.paragraph.section.document
    if document is None or not document.headers:
        return
    header = document.headers[0]
    container = header._border_fills_element()
    if container is None:
        return
    fills = {n.get("id"): n for n in container if n.tag == HH + "borderFill"}
    own = fills.get(cell.element.get("borderFillIDRef") or table.element.get("borderFillIDRef"))
    if own is None:
        return
    (r0, c0), (rs, cs) = cell.address, cell.span
    r1, c1 = r0 + rs - 1, c0 + cs - 1
    for row in table.rows:
        for other in row.cells:
            (o_r0, o_c0), (o_rs, o_cs) = other.address, other.span
            o_r1, o_c1 = o_r0 + o_rs - 1, o_c0 + o_cs - 1
            # only a neighbour whose shared side lies within this cell's side
            # changes; a longer (merged) neighbour keeps its line, as in Hancom
            rows_within = o_r0 >= r0 and o_r1 <= r1
            cols_within = o_c0 >= c0 and o_c1 <= c1
            touches = (o_c0 == c1 + 1 and rows_within, o_c1 == c0 - 1 and rows_within,
                       o_r0 == r1 + 1 and cols_within, o_r1 == r0 - 1 and cols_within)
            for (own_side, other_side), touching in zip(_SHARED_EDGES, touches):
                if touching:
                    _set_shared_side(table, header, container, fills, other, own.find(HH + own_side), other_side)


def _set_shared_side(table: Any, header: Any, container: Any, fills: dict, other: Any, line: Any, side: str) -> None:
    from .namespaces import HH

    from .formatting import derive_definition

    reference = other.element.get("borderFillIDRef") or table.element.get("borderFillIDRef")
    base = fills.get(reference)
    if base is None or line is None or base.find(HH + side) is None:
        return

    def change(candidate: Any) -> None:
        target = candidate.find(HH + side)
        for key, value in line.attrib.items():
            target.set(key, value)

    other.element.set("borderFillIDRef", derive_definition(header, "borderFill", reference, change))


def _color_existing_borders(candidate: Any, color: str, line_type: str) -> None:
    from ..errors import HwpxValueError
    from .namespaces import HH

    for name in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
        sides = candidate.findall(HH + name)
        if len(sides) != 1:
            raise HwpxValueError(
                "existing cell border style requires exactly four sides",
                code="cell-border-edit-unsupported",
                suggestion="Select a cell with one existing complete border style.",
            )
        sides[0].set("color", color.upper())
        sides[0].set("type", line_type)


def _wrap_paragraph(
    element: ET.Element,
    section: "HwpxOxmlSection",
) -> "HwpxOxmlParagraph":
    from .paragraph import HwpxOxmlParagraph

    return HwpxOxmlParagraph(element, section)


def _is_blank_paragraph(paragraph: ET.Element) -> bool:
    """Whether a paragraph's runs hold nothing but empty ``hp:t``."""
    for run in paragraph.findall(f"{_HP}run"):
        for child in run:
            if _element_local_name(child) != "t" or child.text or len(child):
                return False
    return True


def _holds_object(paragraph: ET.Element) -> bool:
    """Whether a paragraph's runs hold anything besides ``hp:t`` (a table, a picture, a control ...)."""
    return any(_element_local_name(child) != "t" for run in paragraph.findall(f"{_HP}run") for child in run)


def _is_blank_cell(element: ET.Element) -> bool:
    """Whether a cell holds one empty paragraph and nothing else, like a new cell."""
    sublist = element.find(f"{_HP}subList")
    paragraphs = [] if sublist is None else sublist.findall(f"{_HP}p")
    return len(paragraphs) <= 1 and all(_is_blank_paragraph(paragraph) for paragraph in paragraphs)



class HwpxOxmlTableCell(SameElement, TableCellFormat):
    """Represents an individual table cell."""

    def __init__(
        self,
        element: ET.Element,
        table: "HwpxOxmlTable",
        row_element: ET.Element,
    ):
        self.element = element
        self.table = table
        self._row_element = row_element

    def _addr_element(self) -> ET.Element | None:
        return self.element.find(f"{_HP}cellAddr")

    def _span_element(self) -> ET.Element:
        span = self.element.find(f"{_HP}cellSpan")
        if span is None:
            span = ET.SubElement(self.element, f"{_HP}cellSpan", {"colSpan": "1", "rowSpan": "1"})
        return span

    def _size_element(self) -> ET.Element:
        size = self.element.find(f"{_HP}cellSz")
        if size is None:
            size = ET.SubElement(self.element, f"{_HP}cellSz", {"width": "0", "height": "0"})
        return size

    def _ensure_text_element(self) -> ET.Element:
        sublist = self._ensure_sublist()
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph = _append_child(
                sublist, f"{_HP}p", _default_cell_paragraph_attributes(self.table.paragraph.section._ids)
            )
        _clear_paragraph_layout_cache(paragraph)
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        text = run.find(f"{_HP}t")
        if text is None:
            text = _append_child(run, f"{_HP}t")
        return text

    @property
    def address(self) -> tuple[int, int]:
        addr = self._addr_element()
        if addr is None:
            return (0, 0)
        row = int(addr.get("rowAddr", "0"))
        col = int(addr.get("colAddr", "0"))
        return (row, col)

    @property
    def span(self) -> tuple[int, int]:
        # Reading never writes: a cell without ``hp:cellSpan`` spans one row and one column.
        span = self.element.find(f"{_HP}cellSpan")
        if span is None:
            return (1, 1)
        row_span = int(span.get("rowSpan", "1"))
        col_span = int(span.get("colSpan", "1"))
        return (row_span, col_span)

    @property
    def field_name(self) -> str:
        """이 칸의 셀 필드 이름(``hp:tc@name``, 한/글 "셀 속성 → 필드 이름"). 없으면 빈 문자열."""

        return self.element.get("name") or ""

    @field_name.setter
    def field_name(self, value: str | None) -> None:
        self.element.set("name", (value or "").strip())
        self.table.mark_dirty()

    def set_span(self, row_span: int, col_span: int) -> None:
        span = self._span_element()
        span.set("rowSpan", str(max(row_span, 1)))
        span.set("colSpan", str(max(col_span, 1)))
        self.table._invalidate_grid()
        self.table.mark_dirty()

    @property
    def width(self) -> int:
        # Reading never writes: a cell without ``hp:cellSz`` reads as 0, as an empty one does.
        size = self.element.find(f"{_HP}cellSz")
        return int(size.get("width", "0")) if size is not None else 0

    @property
    def height(self) -> int:
        size = self.element.find(f"{_HP}cellSz")
        return int(size.get("height", "0")) if size is not None else 0

    def set_size(self, width: int | None = None, height: int | None = None) -> None:
        for argument, value in (("width", width), ("height", height)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                from ..errors import argument_type_error

                raise argument_type_error(argument, value, "an int (HWPUNIT) or None")
        size = self._size_element()
        if width is not None:
            size.set("width", str(max(width, 0)))
        if height is not None:
            size.set("height", str(max(height, 0)))
        self.table._invalidate_grid()
        self.table.mark_dirty()

    margins = property(_table_sizes.cell_margins)
    set_margins = _table_sizes.set_cell_margins

    @property
    def text(self) -> str:
        paragraphs = self.paragraphs
        if paragraphs:
            return "\n".join(paragraph.text or "" for paragraph in paragraphs)
        parts: list[str] = []
        for t_elem in self.element.findall(f".//{_HP}t"):
            if t_elem.text:
                parts.append(t_elem.text)
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        self.set_text(value)

    def _first_run_char_pr_id_ref(self) -> str:
        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                if run.char_pr_id_ref is not None:
                    return str(run.char_pr_id_ref)
        return "0"

    def _paragraph_format_attrs(self, paragraph: "HwpxOxmlParagraph" | None = None) -> dict[str, str]:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        source = paragraph.element if paragraph is not None else None
        ids = self.table.paragraph.section._ids
        attrs = dict(_default_cell_paragraph_attributes(ids))
        if source is not None:
            for key in ("paraPrIDRef", "styleIDRef", "pageBreak", "columnBreak", "merged"):
                value = source.get(key)
                if value is not None:
                    attrs[key] = value
        attrs["id"] = _paragraph_id(ids)
        return attrs

    def _run_char_pr_for_line(self, paragraphs: Sequence["HwpxOxmlParagraph"], index: int) -> str:
        if index < len(paragraphs):
            for run in paragraphs[index].runs:
                if run.char_pr_id_ref is not None:
                    return str(run.char_pr_id_ref)
        return self._first_run_char_pr_id_ref()

    def _set_split_paragraph_text(self, value: str) -> None:
        sublist = self._ensure_sublist()
        lines = (value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines:
            lines = [""]

        # A paragraph holding a table or an object keeps its place and what it
        # holds; only its own text goes. The lines replace the cell's other
        # paragraphs, where the first of them was, or go in front of the first
        # holder when the cell has none.
        existing = self.paragraphs
        holders = [paragraph for paragraph in existing if _holds_object(paragraph.element)]
        own = [paragraph for paragraph in existing if not _holds_object(paragraph.element)]
        anchor = own[0].element if own else holders[0].element if holders else None
        position = 0
        for child in sublist:
            if child is anchor:
                break
            if not any(child is paragraph.element for paragraph in own):
                position += 1
        for paragraph in own:
            sublist.remove(paragraph.element)
        for paragraph in holders:
            for node in paragraph.element.findall(f"{_HP}run/{_HP}t"):
                clear_text_element(node)

        for index, line in enumerate(lines):
            source = own[index] if index < len(own) else own[0] if own else holders[0] if holders else None
            line_paragraph = _append_child(sublist, f"{_HP}p", self._paragraph_format_attrs(source))
            sublist.remove(line_paragraph)
            sublist.insert(position + index, line_paragraph)
            run = _append_child(
                line_paragraph,
                f"{_HP}run",
                {"charPrIDRef": self._run_char_pr_for_line(own, index)},
            )
            _append_text_with_tabs(run, line)

    def _wrap_new_content(self, value: str, previous_text: str) -> None:
        """Let a value that would squeeze too far wrap in a SQUEEZE cell.

        Hancom keeps a SQUEEZE cell's text on one line and narrows only the
        spacing between its characters: a line up to 1.1 times the cell's line
        width still reads, a longer one makes the characters touch and overlap.
        Such a value switches the cell to BREAK; a shorter one keeps SQUEEZE,
        as Hancom's own fill does.  Untouched template cells keep their mode.
        """
        if value and value != previous_text:
            sublist = self._ensure_sublist()
            if (sublist.get("lineWrap") or "").upper() == "SQUEEZE" and not _table_sizes.squeezes_readably(self, value):
                sublist.set("lineWrap", "BREAK")

    def set_text(
        self,
        value: str,
        *,
        preserve_format: bool = True,
        split_paragraphs: bool = False,
    ) -> None:
        previous_text = self.text
        sanitized_value = sanitize_keeping_tabs(value)
        if sanitized_value == previous_text and preserve_format:
            return  # the same text changes nothing: paragraphs, runs and line caches stay
        self._wrap_new_content(sanitized_value, previous_text)
        if split_paragraphs:
            self._set_split_paragraph_text(sanitized_value)
            self._clear_own_layout_caches()
            self.element.set("dirty", "1")
            self.table.mark_dirty()
            return

        # Only the cell's own paragraphs take the text: a table or object inside
        # the cell keeps its text.
        own = own_text_nodes(self._ensure_sublist())
        text_element = own[0] if own else new_own_text_node(self._ensure_sublist(), self._first_run_char_pr_id_ref())
        set_text_with_tabs(text_element, sanitized_value)
        for node in own[1:]:
            clear_text_element(node)
        self._drop_blank_paragraphs(text_element)
        if not preserve_format:
            current: Any | None = text_element
            while current is not None and _element_local_name(current) != "run":
                current = current.getparent() if hasattr(current, "getparent") else None
            if current is not None:
                current.set("charPrIDRef", "0")
        self._clear_own_layout_caches()
        self.element.set("dirty", "1")
        self.table.mark_dirty()

    def _drop_blank_paragraphs(self, text_element: ET.Element) -> None:
        # As Hancom fills a cell, the value becomes the cell's one paragraph: every
        # other paragraph of the cell holding no text and nothing else goes, the
        # blank lines it had included, so the cell reads back the text it was given.
        # A paragraph holding a table or an object stays.
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            return
        for paragraph in sublist.findall(f"{_HP}p"):
            own = [node for run in paragraph.findall(f"{_HP}run") for node in run.findall(f"{_HP}t")]
            if not any(node is text_element for node in own) and _is_blank_paragraph(paragraph):
                sublist.remove(paragraph)

    def _clear_own_layout_caches(self) -> None:
        # Edit-scoped invalidation: only this cell's paragraphs lose their
        # layout caches, so Hancom re-lays-out just the filled cell instead of
        # the whole section (specs/031 P0 — the whole-section nuke shifted
        # pages and stacked glyphs on multi-page forms).
        for node in self.element.iter():
            if _element_local_name(node) == "p":
                _clear_paragraph_layout_cache(node)

    def remove(self) -> None:
        """Refused: taking one cell out of the grid leaves a hole Hancom cannot lay out.

        Raises :class:`~hwpx.errors.HwpxValueError` (``code="table-cell-remove-unsupported"``).
        Delete the whole row or column (``table.delete_rows``, ``table.delete_columns``), merge
        the cell into its neighbour (``table.merge_cells``), or empty it (``cell.text = ""``).
        """

        raise cell_remove_refused()

    # ------------------------------------------------------------------
    # Nested content helpers
    # ------------------------------------------------------------------

    def _ensure_sublist(self) -> ET.Element:
        """Return (or lazily create) the ``<hp:subList>`` container."""
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            refuse_cell_without_sublist(self.element)  # its paragraphs are the cell's own children
            sublist = _append_child(self.element, f"{_HP}subList", _default_sublist_attributes())
        return sublist

    @property
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        """The paragraphs inside this cell's ``<hp:subList>``, in order -- or, in a cell some writer gave its
        paragraphs as its own children (no ``hp:subList``, :attr:`has_sub_list` ``False``), those."""
        sublist = self.element.find(f"{_HP}subList")
        holder = sublist if sublist is not None else self.element
        # a table some writer left outside any paragraph has no section: its paragraphs are read only
        section = cast("HwpxOxmlSection", getattr(self.table.paragraph, "section", None))
        return tuple(_wrap_paragraph(p, section) for p in holder.findall(f"{_HP}p"))

    @rejects_removed_arguments
    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph to this cell and return it.

        ``style`` (a name, a numeric id or a ``Style``) also gives the paragraph that
        style's paragraph and character shapes unless they are passed. To set the style
        reference alone (7.0 removed ``style_id_ref=``), set ``paragraph.style_id_ref``.
        """
        _require_text(text)  # not text: refused before anything is written
        style_id_ref: str | int | None = None
        if style is not None:
            from .section import style_shape_refs

            style_id_ref, para_pr_id_ref, char_pr_id_ref = style_shape_refs(
                self.table.paragraph.section.document, style, para_pr_id_ref, char_pr_id_ref
            )
        sublist = self._ensure_sublist()

        attrs = paragraph_attributes(_paragraph_id(self.table.paragraph.section._ids))
        if para_pr_id_ref is not None:
            attrs["paraPrIDRef"] = str(para_pr_id_ref)
        if style_id_ref is not None:
            attrs["styleIDRef"] = str(style_id_ref)

        paragraph = _append_child(sublist, f"{_HP}p", attrs)

        run_attrs: dict[str, str] = {}
        if char_pr_id_ref is not None:
            run_attrs["charPrIDRef"] = str(char_pr_id_ref)
        else:
            run_attrs["charPrIDRef"] = "0"

        run = _append_child(paragraph, f"{_HP}run", run_attrs)
        _append_text_with_tabs(run, text)

        self.table.mark_dirty()
        section = self.table.paragraph.section
        return _wrap_paragraph(paragraph, section)

    @property
    def tables(self) -> tuple["HwpxOxmlTable", ...]:
        """The tables nested inside this cell, in order."""
        result: list["HwpxOxmlTable"] = []
        for para in self.paragraphs:
            result.extend(para.tables)
        return tuple(result)

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
    ) -> "HwpxOxmlTable":
        """Insert a nested table inside this cell.

        The table is created inside a new paragraph within the cell's
        ``<hp:subList>``.
        """
        _table_sizes.validate_table_size(rows, cols)  # before a border fill is declared or a paragraph added
        height = _table_sizes.check_new_table_height(height)
        _table_sizes.new_table_width(width, cols)  # checked before a paragraph is added
        # Resolve border fill ID
        if border_fill_id_ref is None:
            document = self.table.paragraph.section.document
            if document is not None:
                border_fill_id_ref = document.ensure_basic_border_fill()
            else:
                border_fill_id_ref = "0"

        # Create a host paragraph for the nested table
        para = self.add_paragraph("")
        try:
            return para.add_table(
                rows,
                cols,
                width=width,
                height=height,
                border_fill_id_ref=border_fill_id_ref,
            )
        except BaseException:
            # refused after all (a height, a border fill id): the paragraph made for the table goes again
            from ._paragraph_text_edit import paragraph_container

            holder = paragraph_container(para.element, para.section.element)
            if holder is not None:
                holder.remove(para.element)
            raise


@dataclass(frozen=True)
class HwpxTableGridPosition:
    """Mapping between a logical table position and a physical cell."""

    row: int
    column: int
    cell: HwpxOxmlTableCell
    anchor: tuple[int, int]
    span: tuple[int, int]

    @property
    def is_anchor(self) -> bool:
        return (self.row, self.column) == self.anchor

    @property
    def row_span(self) -> int:
        return self.span[0]

    @property
    def col_span(self) -> int:
        return self.span[1]



class HwpxOxmlTableRow(SameElement, TableRowFormat):
    """Represents a table row."""

    def __init__(self, element: ET.Element, table: "HwpxOxmlTable"):
        self.element = element
        self.table = table

    @property
    def cells(self) -> tuple[HwpxOxmlTableCell, ...]:
        """The row's cells (its ``hp:tc``), left to right."""
        return tuple(
            HwpxOxmlTableCell(cell_element, self.table, self.element)
            for cell_element in self.element.findall(f"{_HP}tc")
        )


class HwpxOxmlTable(SameElement, TableStructureEdits, TableFormat):
    """Representation of an ``<hp:tbl>`` inline object."""

    #: The section of a table placed right in it (``section.blocks``), which has no paragraph.
    _section: "HwpxOxmlSection | None" = None

    if TYPE_CHECKING:
        paragraph: "HwpxOxmlParagraph"
    else:
        paragraph = live_paragraph  # the paragraph holding it now, also after a move

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph
        self._grid_cache: _TableGridCache | None = None

    def __repr__(self) -> str:
        """Return a compact and safe summary of table geometry."""

        return (
            f"{self.__class__.__name__}("
            f"rows={self.row_count}, "
            f"cols={self.column_count}, "
            f"physical_rows={len(self.rows)}"
            ")"
        )

    @property
    def height(self) -> int:
        """Declared table height in HWP units."""
        size = self.element.find(f"{_HP}sz")
        return int(size.get("height", "0")) if size is not None else 0

    @property
    def treat_as_char(self) -> bool:
        """Whether Hancom lays out this table as one inline character."""
        position = self.element.find(f"{_HP}pos")
        return position is not None and position.get("treatAsChar", "1") == "1"

    out_margins = property(_table_sizes.table_out_margins)
    set_out_margins = _table_sizes.set_table_out_margins

    def set_treat_as_char(self, value: bool) -> None:
        """Choose inline layout or flowing table layout across pages."""
        position = self.element.find(f"{_HP}pos")
        if position is None:
            from ..errors import HwpxValueError

            raise HwpxValueError("table has no hp:pos", code="table-position-missing")
        desired = "1" if value else "0"
        if position.get("treatAsChar") != desired:
            position.set("treatAsChar", desired)
            _clear_paragraph_layout_cache(self.paragraph.element)  # the table leaves (or joins) its line
            self.mark_dirty()

    # --- caption (hp:caption) -----------------------------------------

    @property
    def caption(self) -> "Caption | None":
        """This table's ``hp:caption``, or ``None`` if it doesn't have one."""

        # A table placed right in a section (``section.blocks``) has no paragraph; it knows its section.
        section = self.paragraph.section if self.paragraph is not None else self._section
        return _read_caption(self.element, section)  # type: ignore[arg-type]

    def set_caption(
        self,
        text: str,
        *,
        side: str = "TOP",
        full_size: bool = False,
        width: int | None = None,
        gap: int = 850,
        char_pr_id_ref: str | int | None = None,
    ) -> "Caption":
        """Create (or replace the text of) this table's ``hp:caption`` (*full_size*: ``fullSz``).

        실코퍼스 15건 전수 관행(93%가 표 캡션): ``side="TOP"``·``fullSz=False``
        가 사실상 유일한 조합, ``gap`` 은 850(다수) 또는 566. See
        ``hwpx.oxml.objects`` 모듈 상단 주석의 실측 근거.
        """

        _require_text(text)  # not text: refused before anything is written
        return _write_caption(
            self.element, text, section=self.paragraph.section,
            side=side, full_sz=full_size, width=width, gap=gap,
            char_pr_id_ref=char_pr_id_ref,
        )

    def remove_caption(self) -> bool:
        """Remove this table's ``hp:caption`` if present. Returns whether one was removed."""

        return _remove_caption(self.element, self.paragraph.section)

    # --- label (hp:label) -----------------------------------------

    @property
    def label(self) -> "Label | None":
        """This table's ``hp:label`` (Avery-style label-sheet/nameplate
        print layout), or ``None`` if it doesn't have one. Table-exclusive
        (DEV-023, ``docs/owpml-deviations.md`` — inferred from
        75 real private documents, structure matches the vendored schema
        exactly, no deviation to register beyond the element's existence)."""

        element = self.element.find(f"{_HP}label")
        if element is None:
            return None
        return parse_label_element(element)

    def set_label(
        self,
        *,
        topmargin: int | None = None,
        leftmargin: int | None = None,
        boxwidth: int | None = None,
        boxlength: int | None = None,
        boxmarginhor: int | None = None,
        boxmarginver: int | None = None,
        labelcols: int | None = None,
        labelrows: int | None = None,
        landscape: str | None = None,
        pagewidth: int | None = None,
        pageheight: int | None = None,
    ) -> "Label":
        """Create (or replace) this table's ``hp:label``.

        Always placed as the table's *last* child -- every real occurrence
        (436/436, DEV-023) sits after all ``hp:tr`` rows, matching
        ``ParaList XML schema.xml``'s own sequence order. Values are not
        restricted to the two combinations the format inference sample
        observed (a 2x9 small-label sheet and a 1x2 large-square nameplate
        layout) -- there is no real-corpus evidence for what other
        combinations Hancom accepts or rejects, so this does not guess at
        a validation rule beyond the schema's own (``labelcols``/
        ``labelrows``/etc. are ``xs:nonNegativeInteger``, ``landscape`` is
        ``WIDELY``/``NARROWLY``).
        """

        existing = self.element.find(f"{_HP}label")
        if existing is not None:
            self.element.remove(existing)

        attrs: dict[str, str] = {}
        for name, value in (
            ("topmargin", topmargin),
            ("leftmargin", leftmargin),
            ("boxwidth", boxwidth),
            ("boxlength", boxlength),
            ("boxmarginhor", boxmarginhor),
            ("boxmarginver", boxmarginver),
            ("labelcols", labelcols),
            ("labelrows", labelrows),
        ):
            if value is not None:
                attrs[name] = str(int(value))
        if landscape is not None:
            attrs["landscape"] = landscape
        for name, value in (("pagewidth", pagewidth), ("pageheight", pageheight)):
            if value is not None:
                attrs[name] = str(int(value))

        element = self.element.makeelement(f"{_HP}label", attrs)
        self.element.append(element)
        self.paragraph.section.mark_dirty()
        return parse_label_element(element)

    def remove_label(self) -> bool:
        """Remove this table's ``hp:label`` if present. Returns whether one was removed."""

        element = self.element.find(f"{_HP}label")
        if element is None:
            return False
        self.element.remove(element)
        self.paragraph.section.mark_dirty()
        return True

    @classmethod
    def create(
        cls,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        ids: "IdSource | None",
    ) -> ET.Element:
        """A new ``hp:tbl`` element; *ids* is the id source of the document it is made for."""
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive integers")

        table_width = _table_sizes.new_table_width(width if width is not None else cols * _DEFAULT_CELL_WIDTH, cols)
        table_height = height if height is not None else rows * _DEFAULT_CELL_HEIGHT
        if border_fill_id_ref is None:
            raise ValueError("border_fill_id_ref must be provided")
        border_fill = str(border_fill_id_ref)

        table_attrs = {
            "id": _object_id(ids),
            "zOrder": "0",
            "numberingType": "TABLE",
            "textWrap": "TOP_AND_BOTTOM",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "pageBreak": "CELL",
            "repeatHeader": "0",
            "rowCnt": str(rows),
            "colCnt": str(cols),
            "cellSpacing": "0",
            "borderFillIDRef": border_fill,
            "noAdjust": "0",
        }

        table = ET.Element(f"{_HP}tbl", table_attrs)
        ET.SubElement(
            table,
            f"{_HP}sz",
            {
                "width": str(max(table_width, 0)),
                "widthRelTo": "ABSOLUTE",
                "height": str(max(table_height, 0)),
                "heightRelTo": "ABSOLUTE",
                "protect": "0",
            },
        )
        ET.SubElement(
            table,
            f"{_HP}pos",
            {
                "treatAsChar": "1",
                "affectLSpacing": "0",
                "flowWithText": "1",
                "allowOverlap": "0",
                "holdAnchorAndSO": "0",
                "vertRelTo": "PARA",
                "horzRelTo": "COLUMN",
                "vertAlign": "TOP",
                "horzAlign": "LEFT",
                "vertOffset": "0",
                "horzOffset": "0",
            },
        )
        ET.SubElement(table, f"{_HP}outMargin", _default_cell_margin_attributes())
        ET.SubElement(table, f"{_HP}inMargin", _default_cell_inner_margin_attributes())

        column_widths = _distribute_size(max(table_width, 0), cols)
        row_heights = _distribute_size(max(table_height, 0), rows)

        for row_index in range(rows):
            row = ET.SubElement(table, f"{_HP}tr")
            for col_index in range(cols):
                cell = ET.SubElement(row, f"{_HP}tc", _default_cell_attributes(border_fill))
                sublist = ET.SubElement(cell, f"{_HP}subList", _default_sublist_attributes())
                paragraph = ET.SubElement(sublist, f"{_HP}p", _default_cell_paragraph_attributes(ids))
                run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
                ET.SubElement(run, f"{_HP}t")
                ET.SubElement(
                    cell,
                    f"{_HP}cellAddr",
                    {"colAddr": str(col_index), "rowAddr": str(row_index)},
                )
                ET.SubElement(cell, f"{_HP}cellSpan", {"colSpan": "1", "rowSpan": "1"})
                ET.SubElement(
                    cell,
                    f"{_HP}cellSz",
                    {
                        "width": str(column_widths[col_index] if column_widths else 0),
                        "height": str(row_heights[row_index] if row_heights else 0),
                    },
                )
                ET.SubElement(cell, f"{_HP}cellMargin", _default_cell_inner_margin_attributes())
        return table

    def mark_dirty(self) -> None:
        self.paragraph.section.mark_dirty()

    @property
    def row_count(self) -> int:
        value = self.element.get("rowCnt")
        if value is not None and value.isdigit():
            return _table_sizes.declared_count(value)
        return len(self.element.findall(f"{_HP}tr"))

    @property
    def column_count(self) -> int:
        value = self.element.get("colCnt")
        if value is not None and value.isdigit():
            return _table_sizes.declared_count(value)
        first_row = self.element.find(f"{_HP}tr")
        if first_row is None:
            return 0
        return len(first_row.findall(f"{_HP}tc"))

    @property
    def rows(self) -> tuple[HwpxOxmlTableRow, ...]:
        """The table's rows (its ``hp:tr``), top to bottom."""
        return tuple(HwpxOxmlTableRow(row, self) for row in self.element.findall(f"{_HP}tr"))

    def _invalidate_grid(self) -> None:
        """Forget the built grid.  Every edit that moves, adds, removes, merges or resizes cells calls this."""

        self._grid_cache = None

    def _cell_grid(self) -> dict[tuple[int, int], HwpxTableGridPosition]:
        """The grid of the table as it is now: the kept one when no row, cell, address, span or size
        changed since it was built (checked against the XML, so an edit made outside this object is
        seen too), else a new one.  Callers must not change the returned mapping."""

        cache = getattr(self, "_grid_cache", None)
        if cache is not None and cache.still_valid(self.element):
            return cache.mapping
        self._grid_cache = None
        mapping = self._build_cell_grid()
        self._grid_cache = _TableGridCache(mapping, self.element)
        return mapping

    def _build_cell_grid(self) -> dict[tuple[int, int], HwpxTableGridPosition]:
        mapping: dict[tuple[int, int], HwpxTableGridPosition] = {}
        positions = _table_sizes.GridPositions()  # what the spans in the file may cover in all

        def _is_deactivated_cell(
            cell: HwpxOxmlTableCell, span: tuple[int, int]
        ) -> bool:
            span_row, span_col = span
            if span_row != 1 or span_col != 1:
                return False
            if cell.width != 0 or cell.height != 0:
                return False
            for text_element in cell.element.findall(f".//{_HP}t"):
                if text_element.text:
                    return False
            return True

        for row in self.element.findall(f"{_HP}tr"):
            for cell_element in row.findall(f"{_HP}tc"):
                wrapper = HwpxOxmlTableCell(cell_element, self, row)
                start_row, start_col = wrapper.address
                span_row, span_col = wrapper.span
                wrapper_span = (span_row, span_col)
                positions.take(span_row, span_col)
                wrapper_is_deactivated = _is_deactivated_cell(wrapper, wrapper_span)
                for logical_row in range(start_row, start_row + span_row):
                    for logical_col in range(start_col, start_col + span_col):
                        key = (logical_row, logical_col)
                        existing = mapping.get(key)
                        entry = HwpxTableGridPosition(
                            row=logical_row,
                            column=logical_col,
                            cell=wrapper,
                            anchor=(start_row, start_col),
                            span=(span_row, span_col),
                        )
                        if (
                            existing is not None
                            and existing.cell.element is not wrapper.element
                        ):
                            existing_span = existing.span
                            existing_spans_multiple = (
                                existing_span[0] != 1 or existing_span[1] != 1
                            )
                            wrapper_spans_multiple = (
                                wrapper_span[0] != 1 or wrapper_span[1] != 1
                            )
                            existing_is_deactivated = _is_deactivated_cell(
                                existing.cell, existing_span
                            )

                            if (
                                wrapper_is_deactivated
                                and existing_spans_multiple
                            ):
                                continue
                            if (
                                existing_is_deactivated
                                and wrapper_spans_multiple
                            ):
                                mapping[key] = entry
                                continue
                            raise ValueError(
                                "table grid contains overlapping cell spans"
                            )
                        mapping[key] = entry
        return mapping

    def _grid_entry(self, row_index: int, col_index: int) -> HwpxTableGridPosition:
        for argument, value in (("row", row_index), ("col", col_index)):
            if isinstance(value, bool) or not isinstance(value, int):
                from ..errors import argument_type_error

                raise argument_type_error(argument, value, "int", suggestion="칸은 table.cell(0, 1) 처럼 행·열 번호로 고르세요.")
        row_count = self.row_count
        col_count = self.column_count
        if row_index < 0 or col_index < 0 or row_index >= row_count or col_index >= col_count:
            raise cell_out_of_range(row_index, col_index, row_count, col_count)

        entry = None
        cache = getattr(self, "_grid_cache", None)
        if cache is not None and cache.fast and cache.same_shape(self.element):
            # The kept grid answers when the table has the same rows and cells and the cell found still
            # has the address, span and size it was built with; anything else goes through the full check.
            entry = cache.mapping.get((row_index, col_index))
            if entry is not None and not cache.cell_unchanged(entry.cell.element):
                entry = None
        if entry is None:
            entry = self._cell_grid().get((row_index, col_index))
        if entry is None:
            raise HwpxIndexError(
                "cell coordinates (%d, %d) are covered by a merged cell"
                " without an accessible anchor; inspect iter_grid() for details"
                % (row_index, col_index),
                code="table-cell-not-found",
                context={"row": row_index, "col": col_index},
                suggestion="table.iter_grid() 로 병합된 칸의 위치를 확인하세요.",
            )
        return entry

    def iter_grid(self) -> Iterator[HwpxTableGridPosition]:
        """Yield grid-aware mappings for every logical table position."""

        mapping = self._cell_grid()
        row_count = self.row_count
        col_count = self.column_count
        for row_index in range(row_count):
            for col_index in range(col_count):
                entry = mapping.get((row_index, col_index))
                if entry is None:
                    raise IndexError(
                        "cell coordinates (%d, %d) do not resolve to a physical cell"
                        % (row_index, col_index)
                    )
                yield entry

    @property
    def cell_map(self) -> tuple[tuple[HwpxTableGridPosition, ...], ...]:
        """The table's grid: ``cell_map[row][col]`` is the grid position at that row and column,
        naming the cell that covers it (a merged cell covers several)."""

        row_count = self.row_count
        col_count = self.column_count
        _table_sizes.check_grid(row_count, col_count)  # rowCnt/colCnt are what the file says
        grid: list[list[HwpxTableGridPosition | None]] = [
            [None for _ in range(col_count)] for _ in range(row_count)
        ]
        for entry in self.iter_grid():
            grid[entry.row][entry.column] = entry

        for row_index in range(row_count):
            for col_index in range(col_count):
                if grid[row_index][col_index] is None:
                    raise IndexError(
                        "cell coordinates (%d, %d) do not resolve to a physical cell"
                        % (row_index, col_index)
                    )

        return tuple(
            tuple(
                cast(HwpxTableGridPosition, grid[row_index][col_index])
                for col_index in range(col_count)
            )
            for row_index in range(row_count)
        )

    def cell(self, row: int, col: int) -> HwpxOxmlTableCell:
        """The cell covering grid position (*row*, *col*), from 0 (a merged cell's anchor)."""
        entry = self._grid_entry(row, col)
        return entry.cell

    def set_cell_border_fill(
        self, row: int, col: int, border_fill_id_ref: str | int
    ) -> None:
        """Point one cell at a header ``borderFill`` definition.

        Pairs with :meth:`set_cell_shading`; obtain ids from
        ``document.ensure_border_fill`` (line style/width/color/fill). Only
        this cell changes; :meth:`set_cell_borders` also sets the edges the
        neighbouring cells share with it.
        """
        cell = self.cell(row, col)
        cell.element.set("borderFillIDRef", str(border_fill_id_ref))
        self.mark_dirty()

    def set_cell_borders(
        self, row: int, col: int, *, color: str, line_type: str = "SOLID"
    ) -> None:
        """Change four existing border colors/types, preserving fill and widths.

        Copies and deduplicates the complete existing style; other cells that
        share it remain unchanged, except that the neighbouring cells take the
        same line on the edge they share with this cell, as in Hancom. Missing
        or ambiguous style definitions refuse.
        """
        cell = self.cell(row, col)
        _set_cell_borders_preserving(self, cell, color, line_type)

    def set_cell_shading(self, row: int, col: int, color: str) -> None:
        """Fill one cell with *color*; its lines stay (a fill derived from its own, as ``set_shading``)."""
        cell = self.cell(row, col)
        if self.paragraph.section.document is None:
            raise ValueError("table is not attached to a document")
        fills = _BorderFills(self)
        value = _normalize_color(color)
        cell.element.set("borderFillIDRef", fills.derive(fills.base_id(cell), ("fill", value),
                                                         lambda candidate: _set_fill(candidate, value)))
        self.mark_dirty()

    def set_cell_fill_image(
        self,
        row: int,
        col: int,
        image: "str | BinaryItem",
        *,
        mode: str = "TOTAL",
    ) -> None:
        """Fill one cell's background with a ``doc.media.add_image(...)`` item.

        *image* is a :class:`~hwpx.objects.binary_item.BinaryItem` (or its
        ``item_id`` string) already registered via ``doc.media``. *mode*
        selects the ``hc:imgBrush`` fit mode (Core XML schema.xml:813-889);
        real corpus (hwpxlib_corpus, 5 files) observes only ``"TOTAL"``
        (scale-to-fit), the default here.
        """

        cell = self.cell(row, col)
        document = self.paragraph.section.document
        if document is None:
            raise ValueError("table is not attached to a document")
        item_id = str(image)
        if not item_id:
            raise ValueError("image must be a non-empty doc.media binary item id")
        normalized_mode = str(mode).upper()
        if normalized_mode not in FILL_IMAGE_MODES:
            raise ValueError(
                f"unsupported mode {mode!r}; expected one of "
                + ", ".join(sorted(FILL_IMAGE_MODES))
            )
        border_fill_id = document.ensure_shading_border_fill(
            fill_image={
                "binaryItemIDRef": item_id,
                "mode": normalized_mode,
                "bright": "0",
                "contrast": "0",
                "effect": "REAL_PIC",
                "alpha": "0",
            },
            base_border_fill_id=cell.element.get("borderFillIDRef") or self.element.get("borderFillIDRef"),
        )
        cell.element.set("borderFillIDRef", border_fill_id)
        self.mark_dirty()

    def set_cell_fill_gradient(
        self,
        row: int,
        col: int,
        colors: Sequence[str],
        *,
        gradient_type: str = "LINEAR",
        angle: int = 90,
    ) -> None:
        """Fill one cell's background with an ``hc:gradation`` (Core XML
        schema.xml:710-803). *colors* needs at least two ``#RRGGBB`` values;
        real corpus (hwpxlib_corpus, 2 files) observes only
        ``gradient_type="LINEAR"``, the default here.
        """

        cell = self.cell(row, col)
        document = self.paragraph.section.document
        if document is None:
            raise ValueError("table is not attached to a document")
        color_list = [str(color) for color in colors]
        if len(color_list) < 2:
            raise ValueError("colors needs at least two entries")
        normalized_type = str(gradient_type).upper()
        if normalized_type not in FILL_GRADIENT_TYPES:
            raise ValueError(
                f"unsupported gradient_type {gradient_type!r}; expected one of "
                + ", ".join(sorted(FILL_GRADIENT_TYPES))
            )
        border_fill_id = document.ensure_shading_border_fill(
            fill_gradient={
                "type": normalized_type,
                "angle": str(int(angle)),
                "centerX": "0",
                "centerY": "0",
                "step": "255",
                "colorNum": str(len(color_list)),
                "stepCenter": "50",
                "alpha": "0",
                "colors": color_list,
            },
            base_border_fill_id=cell.element.get("borderFillIDRef") or self.element.get("borderFillIDRef"),
        )
        cell.element.set("borderFillIDRef", border_fill_id)
        self.mark_dirty()

    def set_column_widths(self, weights: Sequence[int | float]) -> None:
        _table_sizes.set_column_widths(self, weights)

    def equalize_column_widths(self) -> None:
        """행마다 칸 너비를 같게 한다(한/글 "셀 너비를 같게"와 같은 결과).

        행마다 그 행을 지나는 칸(합친 칸은 한 칸)에 같은 너비를 준다. 모든 행이 같은
        자리에서 끝나도록 표 너비를 행마다의 칸 수로 모두 나누어떨어지는 가장 가까운 값까지
        올린다(예: 3칸 행과 4칸 행이 있으면 12의 배수). 한/글과 같아서, 칸 수가 다른 행이
        많으면 표가 크게 넓어질 수 있다(5칸부터 11칸까지의 행이면 27720의 배수). 행마다 칸
        경계가 달라지면 열 격자(``colCnt``·``hp:cellAddr``·``hp:cellSpan``)를 그 경계로 다시
        짜고, ``hp:cellzone``의 열 주소도 새 격자로 옮긴다. 칸 영역이 같은 칸을 덮는 사각형이
        될 수 없으면 표를 그대로 두고 :class:`~hwpx.errors.HwpxValueError`를 낸다.

        여러 행에 걸친 칸이 행마다 다른 자리를 받아야 하면(예: 세로로 합친 칸 옆 행들의
        칸 수가 다름) 한/글처럼 표를 그대로 두고 :class:`~hwpx.errors.HwpxValueError`를
        낸다. 격자 열마다 같은 너비를 주려면 ``set_column_widths([1] * column_count)``를
        쓴다. 이 메서드가 전에 나누던 방식(표 너비 유지, 앞 n-1열 ``round(W / n)``, 마지막
        열 나머지)이 바로 그 호출이다.
        """

        _table_sizes.equalize_column_widths(self)

    def equalize_row_heights(self) -> None:
        """모든 행 높이를 같게 만든다(6.13 트레인㊻, 갭"셀 높이를 같게").

        ``set_column_widths``의 행 대응 — 병합 셀은 자신이 덮는 행들의
        새 높이 합을 받는다(같은 ``iter_grid``/rowSpan 로직, 축만 다름).
        전체 높이는 표 자신의 ``hp:sz`` height를 우선하고, 없으면(방어적)
        0열 셀들의 높이 합으로 대체한다 — ``set_column_widths``의
        ``total_width`` 유도와 동형.
        """
        _table_sizes.equalize_row_heights(self)

    def set_row_heights(self, heights: Sequence[int]) -> None:
        """행마다 높이(HWPUNIT)를 주고 표 높이를 그 합으로 맞춘다.

        한/글은 행을 이 높이보다 낮게 그리지 않고, 글이 더 길면 그만큼 늘린다. 여러 행에
        걸친 칸은 걸친 행 높이의 합을 받는다. 행 수와 개수가 다르거나 양의 정수가 아니면
        ``table-row-heights-value``로 거부한다.
        """
        _table_sizes.set_row_heights(self, heights)

    def set_cell_text(
        self,
        row: int,
        col: int,
        text: str,
        *,
        logical: bool = False,
        split_merged: bool = False,
        preserve_format: bool = True,
        split_paragraphs: bool = False,
        fit: "FitPolicy | None" = None,
        ledger: Any | None = None,
    ) -> "FitResult | None":
        """Set cell text. When *fit* is given, run the FormFit engine (plan §2 C).

        Without *fit* this is the historical raw set (returns ``None``). With a
        :class:`~hwpx.form_fit.policy.FitPolicy` the value is measured against the
        cell box and wrapped/shrunk/failed accordingly; the returned
        :class:`~hwpx.form_fit.report.FitResult` carries the verdict. An
        ``overflow=fail`` miss makes ``ok`` ``False`` and leaves the cell as it
        was. ``split_paragraphs`` is ignored in fit mode — line breaks are
        decided by measurement.
        """

        if logical:
            entry = self._grid_entry(row, col)
            if split_merged and not entry.is_anchor:
                cell = self.split_merged_cell(row, col)
            else:
                cell = entry.cell
        else:
            cell = self.cell(row, col)

        if fit is not None:
            from hwpx.form_fit.apply import fit_cell_text

            section = self.paragraph.section
            return fit_cell_text(
                cell,
                text,
                fit,
                document=getattr(section, "document", None),
                ledger=ledger,
                part_name=getattr(section, "part_name", None),
                field_id=f"r{row}c{col}",
                preserve_format=preserve_format,
            )

        cell.set_text(
            text,
            preserve_format=preserve_format,
            split_paragraphs=split_paragraphs,
        )
        return None

    @staticmethod
    def _split_cell_size_segments(size: int, span: int) -> list[int]:
        segments = _distribute_size(size, span)
        if not segments:
            segments = [size] + [0] * (span - 1)
        return segments

    @staticmethod
    def _split_merged_cell_update_anchor(
        cell: HwpxOxmlTableCell, start_row: int, start_col: int, col_width: int, row_height: int
    ) -> None:
        addr = cell._addr_element()
        if addr is None:
            addr = _append_child(cell.element, f"{_HP}cellAddr")
        addr.set("rowAddr", str(start_row))
        addr.set("colAddr", str(start_col))
        span_element = cell._span_element()
        span_element.set("rowSpan", "1")
        span_element.set("colSpan", "1")
        size_element = cell._size_element()
        size_element.set("width", str(col_width))
        size_element.set("height", str(row_height))

    def _find_split_cell_overlap(
        self,
        row_element: Any,
        cell: HwpxOxmlTableCell,
        start_row: int,
        start_col: int,
        logical_row: int,
        logical_col: int,
    ) -> HwpxOxmlTableCell | None:
        for existing in row_element.findall(f"{_HP}tc"):
            wrapper = HwpxOxmlTableCell(existing, self, row_element)
            existing_row, existing_col = wrapper.address
            span_r, span_c = wrapper.span
            if existing_row == logical_row and existing_col == logical_col:
                return wrapper
            if (
                existing_row <= logical_row < existing_row + span_r
                and existing_col <= logical_col < existing_col + span_c
            ):
                if wrapper.element is cell.element:
                    continue
                raise ValueError(
                    "Cannot split merged cell covering (%d, %d) because"
                    " position (%d, %d) overlaps another merged cell"
                    % (start_row, start_col, logical_row, logical_col)
                )
        return None

    @staticmethod
    def _copy_attrs_excluding_id(source_attrs: Any, target: dict[str, str]) -> None:
        for key, value in source_attrs.items():
            if key == "id":
                continue
            target.setdefault(key, value)

    @staticmethod
    def _build_split_cell_element(
        row_element: Any,
        template_attrs: dict[str, str],
        preserved_children: list[Any],
        template_sublist: Any,
        template_margin: Any,
        logical_row: int,
        logical_col: int,
        col_width: int,
        row_height: int,
        ids: "IdSource | None",
    ) -> Any:
        # Use makeelement() so the new cell matches the XML engine
        # of the existing tree (stdlib ET or lxml).  ET.Element()
        # always produces stdlib elements which cannot be appended to
        # an lxml tree (and vice-versa), causing TypeError at runtime
        # when splitting cells in documents parsed via lxml.
        new_cell_element = row_element.makeelement(f"{_HP}tc", dict(template_attrs))
        for child in preserved_children:
            new_cell_element.append(deepcopy(child))

        sublist_attrs = _default_sublist_attributes()
        template_para = None
        if template_sublist is not None:
            HwpxOxmlTable._copy_attrs_excluding_id(template_sublist.attrib, sublist_attrs)
            template_para = template_sublist.find(f"{_HP}p")

        sublist = _append_child(new_cell_element, f"{_HP}subList", sublist_attrs)
        paragraph_attrs = _default_cell_paragraph_attributes(ids)
        run_attrs = {"charPrIDRef": "0"}
        if template_para is not None:
            HwpxOxmlTable._copy_attrs_excluding_id(template_para.attrib, paragraph_attrs)
            template_run = template_para.find(f"{_HP}run")
            if template_run is not None:
                run_attrs = dict(template_run.attrib)
                if "charPrIDRef" not in run_attrs:
                    run_attrs["charPrIDRef"] = "0"
        paragraph = _append_child(sublist, f"{_HP}p", paragraph_attrs)
        run = _append_child(paragraph, f"{_HP}run", run_attrs)
        _append_child(run, f"{_HP}t")

        _append_child(
            new_cell_element,
            f"{_HP}cellAddr",
            {"colAddr": str(logical_col), "rowAddr": str(logical_row)},  # Hancom's order
        )
        _append_child(
            new_cell_element,
            f"{_HP}cellSpan",
            {"colSpan": "1", "rowSpan": "1"},
        )
        _append_child(
            new_cell_element,
            f"{_HP}cellSz",
            {"width": str(col_width), "height": str(row_height)},
        )
        if template_margin is not None:
            new_cell_element.append(deepcopy(template_margin))
        else:
            _append_child(
                new_cell_element,
                f"{_HP}cellMargin",
                _default_cell_margin_attributes(),
            )
        return new_cell_element

    def _insert_split_cell_at_position(
        self, row_element: Any, new_cell_element: Any, logical_col: int
    ) -> None:
        existing_cells = list(row_element.findall(f"{_HP}tc"))
        insert_index = len(existing_cells)
        for idx, existing in enumerate(existing_cells):
            wrapper = HwpxOxmlTableCell(existing, self, row_element)
            if wrapper.address[1] > logical_col:
                insert_index = idx
                break
        row_element.insert(insert_index, new_cell_element)

    def _fill_split_cell_position(
        self,
        cell: HwpxOxmlTableCell,
        row_element: Any,
        start_row: int,
        start_col: int,
        template_attrs: dict[str, str],
        preserved_children: list[Any],
        template_sublist: Any,
        template_margin: Any,
        row_offset: int,
        col_offset: int,
        logical_row: int,
        logical_col: int,
        row_height: int,
        col_width: int,
    ) -> None:
        if row_offset == 0 and col_offset == 0:
            self._split_merged_cell_update_anchor(cell, start_row, start_col, col_width, row_height)
            return

        existing_target = self._find_split_cell_overlap(
            row_element, cell, start_row, start_col, logical_row, logical_col
        )
        if existing_target is not None:
            existing_target.set_span(1, 1)
            existing_target.set_size(col_width, row_height)
            return

        new_cell_element = self._build_split_cell_element(
            row_element, template_attrs, preserved_children, template_sublist, template_margin,
            logical_row, logical_col, col_width, row_height, self.paragraph.section._ids,
        )
        self._insert_split_cell_at_position(row_element, new_cell_element, logical_col)

    def split_merged_cell(
        self, row: int, col: int
    ) -> HwpxOxmlTableCell:
        """Split the merged cell covering (*row*, *col*) back into single cells; return the one at
        (*row*, *col*). A cell that is not merged is returned as it is."""
        entry = self._grid_entry(row, col)
        cell = entry.cell
        start_row, start_col = entry.anchor
        span_row, span_col = entry.span

        if span_row == 1 and span_col == 1:
            return cell

        row_elements = self.element.findall(f"{_HP}tr")
        if len(row_elements) < start_row + span_row:
            raise IndexError(
                "table rows missing while splitting merged cell covering"
                f" ({start_row}, {start_col})"
            )

        width_segments = self._split_cell_size_segments(cell.width, span_col)
        height_segments = self._split_cell_size_segments(cell.height, span_row)

        template_attrs = {key: value for key, value in cell.element.attrib.items()}
        preserved_children = [
            deepcopy(child)
            for child in cell.element
            if _element_local_name(child)
            not in {"subList", "cellAddr", "cellSpan", "cellSz", "cellMargin"}
        ]
        template_sublist = cell.element.find(f"{_HP}subList")
        template_margin = cell.element.find(f"{_HP}cellMargin")

        for row_offset in range(span_row):
            logical_row = start_row + row_offset
            row_element = row_elements[logical_row]
            row_height = height_segments[row_offset] if row_offset < len(height_segments) else cell.height
            for col_offset in range(span_col):
                logical_col = start_col + col_offset
                col_width = width_segments[col_offset] if col_offset < len(width_segments) else cell.width
                self._fill_split_cell_position(
                    cell, row_element, start_row, start_col,
                    template_attrs, preserved_children, template_sublist, template_margin,
                    row_offset, col_offset, logical_row, logical_col, row_height, col_width,
                )

        self._invalidate_grid()
        self.mark_dirty()
        return self.cell(row, col)

    @staticmethod
    def _spreadsheet_column_index(value: str) -> int:
        column = value.strip().upper()
        if not column or not column.isalpha():
            raise ValueError(f"invalid spreadsheet column: {value!r}")
        index = 0
        for char in column:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index - 1

    @classmethod
    def _parse_spreadsheet_range(cls, value: str) -> tuple[int, int, int, int]:
        match = _re.fullmatch(r"\s*([A-Za-z]+)([0-9]+)\s*:\s*([A-Za-z]+)([0-9]+)\s*", value)
        if match is None:
            raise bad_spreadsheet_range(value)
        start_col_label, start_row_label, end_col_label, end_row_label = match.groups()
        start_row = int(start_row_label) - 1
        end_row = int(end_row_label) - 1
        start_col = cls._spreadsheet_column_index(start_col_label)
        end_col = cls._spreadsheet_column_index(end_col_label)
        return start_row, start_col, end_row, end_col

    def _resolve_merge_target(
        self, start_row: int, start_col: int, end_row: int, end_col: int
    ) -> HwpxOxmlTableCell:
        check_merge_range(start_row, start_col, end_row, end_col, self.row_count, self.column_count)

        target = self.cell(start_row, start_col)
        addr_row, addr_col = target.address
        if addr_row != start_row or addr_col != start_col:
            raise ValueError("top-left cell must align with merge starting position")
        return target

    def _build_element_to_row_map(self) -> dict[ET.Element, ET.Element]:
        element_to_row: dict[ET.Element, ET.Element] = {}
        for row in self.element.findall(f"{_HP}tr"):
            for cell_element in row.findall(f"{_HP}tc"):
                element_to_row[cell_element] = row
        return element_to_row

    def _scan_merge_region(
        self, start_row: int, start_col: int, end_row: int, end_col: int, target: HwpxOxmlTableCell
    ) -> tuple[set[ET.Element], int, int, list[ET.Element]]:
        """The covered cells, the merged size, and the region's cells in reading order."""
        removal_elements: set[ET.Element] = set()
        width_elements: set[ET.Element] = set()
        height_elements: set[ET.Element] = set()
        total_width = 0
        total_height = 0
        in_order: list[ET.Element] = []
        seen: set[ET.Element] = set()
        grid = self._cell_grid()

        for row_index in range(start_row, end_row + 1):
            for col_index in range(start_col, end_col + 1):
                entry = grid.get((row_index, col_index))
                cell = entry.cell if entry is not None else self.cell(row_index, col_index)
                if cell.element not in seen:
                    seen.add(cell.element)
                    in_order.append(cell.element)
                cell_row, cell_col = cell.address
                span_row, span_col = cell.span
                if (
                    cell_row < start_row
                    or cell_col < start_col
                    or cell_row + span_row - 1 > end_row
                    or cell_col + span_col - 1 > end_col
                ):
                    raise ValueError("Cells to merge must be entirely inside the merge region")
                if row_index == start_row and cell.element not in width_elements:
                    width_elements.add(cell.element)
                    total_width += cell.width
                if col_index == start_col and cell.element not in height_elements:
                    height_elements.add(cell.element)
                    total_height += cell.height
                if cell.element is not target.element:
                    removal_elements.add(cell.element)
        return removal_elements, total_width, total_height, in_order

    @staticmethod
    def _remove_merged_cell_elements(
        removal_elements: set[ET.Element], element_to_row: dict[ET.Element, ET.Element]
    ) -> None:
        for element in removal_elements:
            row_element = element_to_row.get(element)
            if row_element is None:
                continue
            # Native Hancom HWPX omits physical ``hp:tc`` elements covered by
            # a merged anchor.  Keeping zero-sized cells at the covered
            # addresses looks logically equivalent to our grid mapper, but
            # Hancom Office can classify that table structure as damaged.
            # ``split_merged_cell`` already recreates omitted cells, so remove
            # them here instead of retaining deactivated placeholders.
            row_element.remove(element)

    def _move_covered_contents(self, target: HwpxOxmlTableCell, region: list[ET.Element]) -> None:
        # The merged cell takes the paragraphs of every cell that holds
        # something, in reading order.  A blank cell adds nothing, and a blank
        # merged cell gives up its own empty line to the moved paragraphs.
        filled = [element for element in region if not _is_blank_cell(element)]
        if not filled or (len(filled) == 1 and filled[0] is target.element):
            return
        sublist = target._ensure_sublist()
        if filled[0] is not target.element:
            for paragraph in sublist.findall(f"{_HP}p"):
                sublist.remove(paragraph)
        for element in filled:
            source = element.find(f"{_HP}subList")
            if element is target.element or source is None:
                continue
            for paragraph in source.findall(f"{_HP}p"):
                source.remove(paragraph)
                sublist.append(paragraph)

    def merge_cells(
        self,
        start_row: int | str,
        start_col: int | None = None,
        end_row: int | None = None,
        end_col: int | None = None,
    ) -> HwpxOxmlTableCell:
        """Merge a rectangle of cells into its top-left cell and return that cell.

        The merged cell keeps the paragraphs of the covered cells that hold
        text or objects, in reading order after its own; blank cells add nothing.
        Rows the merge leaves without cells and columns no cell starts at are
        removed, as Hancom does: a merge over whole rows makes one row of their
        height, and merging a whole table leaves a one-cell table.
        """
        if isinstance(start_row, str):
            start_row, start_col, end_row, end_col = self._parse_spreadsheet_range(start_row)
        if start_col is None or end_row is None or end_col is None:
            raise TypeError("merge_cells requires either a spreadsheet range or four coordinates")

        target = self._resolve_merge_target(start_row, start_col, end_row, end_col)
        new_row_span = end_row - start_row + 1
        new_col_span = end_col - start_col + 1

        element_to_row = self._build_element_to_row_map()
        removal_elements, total_width, total_height, region = self._scan_merge_region(
            start_row, start_col, end_row, end_col, target
        )

        if not removal_elements and target.span == (new_row_span, new_col_span):
            return target

        self._move_covered_contents(target, region)
        self._remove_merged_cell_elements(removal_elements, element_to_row)

        target.set_span(new_row_span, new_col_span)
        target.set_size(total_width or target.width, total_height or target.height)
        # the cell is wider or taller now and may hold moved paragraphs, so its
        # line caches no longer describe it
        target._clear_own_layout_caches()
        collapse_merged_grid(self.element)
        self._invalidate_grid()
        self.mark_dirty()
        return target

__all__ = ["HwpxOxmlTable", "HwpxOxmlTableCell", "HwpxOxmlTableRow", "HwpxTableGridPosition"]
