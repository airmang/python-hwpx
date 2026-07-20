# SPDX-License-Identifier: Apache-2.0
"""Table, row, grid, and cell OXML services."""

from __future__ import annotations

import re as _re
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Sequence, cast
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_CELL_HEIGHT,
    _DEFAULT_CELL_WIDTH,
    _DEFAULT_PARAGRAPH_ATTRS,
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
    _object_id,
    _paragraph_id,
    _sanitize_text,
)

if TYPE_CHECKING:
    from hwpx.form_fit.policy import FitPolicy
    from hwpx.form_fit.report import FitResult
    from .paragraph import HwpxOxmlParagraph
    from .section import HwpxOxmlSection


def _wrap_paragraph(
    element: ET.Element,
    section: "HwpxOxmlSection",
) -> "HwpxOxmlParagraph":
    from .paragraph import HwpxOxmlParagraph

    return HwpxOxmlParagraph(element, section)

class HwpxOxmlTableCell:
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
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = _append_child(
                self.element, f"{_HP}subList", _default_sublist_attributes()
            )
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph = _append_child(
                sublist, f"{_HP}p", _default_cell_paragraph_attributes()
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
        span = self._span_element()
        row_span = int(span.get("rowSpan", "1"))
        col_span = int(span.get("colSpan", "1"))
        return (row_span, col_span)

    def set_span(self, row_span: int, col_span: int) -> None:
        span = self._span_element()
        span.set("rowSpan", str(max(row_span, 1)))
        span.set("colSpan", str(max(col_span, 1)))
        self.table.mark_dirty()

    @property
    def width(self) -> int:
        size = self._size_element()
        return int(size.get("width", "0"))

    @property
    def height(self) -> int:
        size = self._size_element()
        return int(size.get("height", "0"))

    def set_size(self, width: int | None = None, height: int | None = None) -> None:
        size = self._size_element()
        if width is not None:
            size.set("width", str(max(width, 0)))
        if height is not None:
            size.set("height", str(max(height, 0)))
        self.table.mark_dirty()

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
        attrs = dict(_default_cell_paragraph_attributes())
        if source is not None:
            for key in ("paraPrIDRef", "styleIDRef", "pageBreak", "columnBreak", "merged"):
                value = source.get(key)
                if value is not None:
                    attrs[key] = value
        attrs["id"] = _paragraph_id()
        return attrs

    def _run_char_pr_for_line(self, paragraphs: Sequence["HwpxOxmlParagraph"], index: int) -> str:
        if index < len(paragraphs):
            for run in paragraphs[index].runs:
                if run.char_pr_id_ref is not None:
                    return str(run.char_pr_id_ref)
        return self._first_run_char_pr_id_ref()

    def _set_split_paragraph_text(self, value: str) -> None:
        sublist = self._ensure_sublist()
        existing = self.paragraphs
        lines = (value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines:
            lines = [""]

        for paragraph in list(sublist.findall(f"{_HP}p")):
            sublist.remove(paragraph)

        for index, line in enumerate(lines):
            source = existing[index] if index < len(existing) else existing[0] if existing else None
            paragraph = _append_child(sublist, f"{_HP}p", self._paragraph_format_attrs(source))
            run = _append_child(
                paragraph,
                f"{_HP}run",
                {"charPrIDRef": self._run_char_pr_for_line(existing, index)},
            )
            _append_text_with_tabs(run, line)

    def set_text(
        self,
        value: str,
        *,
        preserve_format: bool = True,
        split_paragraphs: bool = False,
    ) -> None:
        previous_text = self.text
        sanitized_value = _sanitize_text(value)
        if sanitized_value and sanitized_value != previous_text:
            sublist = self._ensure_sublist()
            if (sublist.get("lineWrap") or "").upper() == "SQUEEZE":
                # SQUEEZE can compress a longer filled value until Hancom
                # renders adjacent glyphs on top of each other.  New content
                # should wrap/reflow; untouched template cells keep their mode.
                sublist.set("lineWrap", "BREAK")
        if split_paragraphs:
            self._set_split_paragraph_text(sanitized_value)
            self._clear_own_layout_caches()
            self.element.set("dirty", "1")
            self.table.mark_dirty()
            return

        text_element = self._ensure_text_element()
        text_element.text = sanitized_value
        for node in self.element.findall(f".//{_HP}t"):
            if node is text_element:
                continue
            if node.text:
                node.text = ""
        if not preserve_format:
            current: Any | None = text_element
            while current is not None and _element_local_name(current) != "run":
                current = current.getparent() if hasattr(current, "getparent") else None
            if current is not None:
                current.set("charPrIDRef", "0")
        self._clear_own_layout_caches()
        self.element.set("dirty", "1")
        self.table.mark_dirty()

    def _clear_own_layout_caches(self) -> None:
        # Edit-scoped invalidation: only this cell's paragraphs lose their
        # layout caches, so Hancom re-lays-out just the filled cell instead of
        # the whole section (specs/031 P0 — the whole-section nuke shifted
        # pages and stacked glyphs on multi-page forms).
        for node in self.element.iter():
            if _element_local_name(node) == "p":
                _clear_paragraph_layout_cache(node)

    def remove(self) -> None:
        self._row_element.remove(self.element)
        self.table.mark_dirty()

    # ------------------------------------------------------------------
    # Nested content helpers
    # ------------------------------------------------------------------

    def _ensure_sublist(self) -> ET.Element:
        """Return (or lazily create) the ``<hp:subList>`` container."""
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = _append_child(self.element, f"{_HP}subList", _default_sublist_attributes())
        return sublist

    @property
    def paragraphs(self) -> list["HwpxOxmlParagraph"]:
        """Return paragraphs inside this cell's ``<hp:subList>``."""
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            return []
        section = self.table.paragraph.section
        return [_wrap_paragraph(p, section) for p in sublist.findall(f"{_HP}p")]

    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph to this cell and return it."""
        sublist = self._ensure_sublist()

        attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
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
    def tables(self) -> list["HwpxOxmlTable"]:
        """Return nested tables inside this cell."""
        result: list["HwpxOxmlTable"] = []
        for para in self.paragraphs:
            result.extend(para.tables)
        return result

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
        # Resolve border fill ID
        if border_fill_id_ref is None:
            document = self.table.paragraph.section.document
            if document is not None:
                border_fill_id_ref = document.ensure_basic_border_fill()
            else:
                border_fill_id_ref = "0"

        # Create a host paragraph for the nested table
        para = self.add_paragraph("")
        return para.add_table(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=border_fill_id_ref,
        )


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


class HwpxOxmlTableRow:
    """Represents a table row."""

    def __init__(self, element: ET.Element, table: "HwpxOxmlTable"):
        self.element = element
        self.table = table

    @property
    def cells(self) -> list[HwpxOxmlTableCell]:
        return [
            HwpxOxmlTableCell(cell_element, self.table, self.element)
            for cell_element in self.element.findall(f"{_HP}tc")
        ]


class HwpxOxmlTable:
    """Representation of an ``<hp:tbl>`` inline object."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    def __repr__(self) -> str:
        """Return a compact and safe summary of table geometry."""

        return (
            f"{self.__class__.__name__}("
            f"rows={self.row_count}, "
            f"cols={self.column_count}, "
            f"physical_rows={len(self.rows)}"
            ")"
        )

    @classmethod
    def create(
        cls,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
    ) -> ET.Element:
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive integers")

        table_width = width if width is not None else cols * _DEFAULT_CELL_WIDTH
        table_height = height if height is not None else rows * _DEFAULT_CELL_HEIGHT
        if border_fill_id_ref is None:
            raise ValueError("border_fill_id_ref must be provided")
        border_fill = str(border_fill_id_ref)

        table_attrs = {
            "id": _object_id(),
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
        ET.SubElement(table, f"{_HP}inMargin", _default_cell_margin_attributes())

        column_widths = _distribute_size(max(table_width, 0), cols)
        row_heights = _distribute_size(max(table_height, 0), rows)

        for row_index in range(rows):
            row = ET.SubElement(table, f"{_HP}tr")
            for col_index in range(cols):
                cell = ET.SubElement(row, f"{_HP}tc", _default_cell_attributes(border_fill))
                sublist = ET.SubElement(cell, f"{_HP}subList", _default_sublist_attributes())
                paragraph = ET.SubElement(sublist, f"{_HP}p", _default_cell_paragraph_attributes())
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
                ET.SubElement(cell, f"{_HP}cellMargin", _default_cell_margin_attributes())
        return table

    def mark_dirty(self) -> None:
        self.paragraph.section.mark_dirty()

    @property
    def row_count(self) -> int:
        value = self.element.get("rowCnt")
        if value is not None and value.isdigit():
            return int(value)
        return len(self.element.findall(f"{_HP}tr"))

    @property
    def column_count(self) -> int:
        value = self.element.get("colCnt")
        if value is not None and value.isdigit():
            return int(value)
        first_row = self.element.find(f"{_HP}tr")
        if first_row is None:
            return 0
        return len(first_row.findall(f"{_HP}tc"))

    @property
    def rows(self) -> list[HwpxOxmlTableRow]:
        return [HwpxOxmlTableRow(row, self) for row in self.element.findall(f"{_HP}tr")]

    def _build_cell_grid(self) -> dict[tuple[int, int], HwpxTableGridPosition]:
        mapping: dict[tuple[int, int], HwpxTableGridPosition] = {}

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
        if row_index < 0 or col_index < 0:
            raise IndexError("row_index and col_index must be non-negative")

        row_count = self.row_count
        col_count = self.column_count
        if row_index >= row_count or col_index >= col_count:
            raise IndexError(
                "cell coordinates (%d, %d) exceed table bounds %dx%d"
                % (row_index, col_index, row_count, col_count)
            )

        entry = self._build_cell_grid().get((row_index, col_index))
        if entry is None:
            raise IndexError(
                "cell coordinates (%d, %d) are covered by a merged cell"
                " without an accessible anchor; inspect iter_grid() for details"
                % (row_index, col_index)
            )
        return entry

    def iter_grid(self) -> Iterator[HwpxTableGridPosition]:
        """Yield grid-aware mappings for every logical table position."""

        mapping = self._build_cell_grid()
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

    def get_cell_map(self) -> list[list[HwpxTableGridPosition]]:
        """Return a 2D list mapping logical positions to physical cells."""

        row_count = self.row_count
        col_count = self.column_count
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

        return [
            [
                cast(HwpxTableGridPosition, grid[row_index][col_index])
                for col_index in range(col_count)
            ]
            for row_index in range(row_count)
        ]

    def cell(self, row_index: int, col_index: int) -> HwpxOxmlTableCell:
        entry = self._grid_entry(row_index, col_index)
        return entry.cell

    def set_cell_shading(self, row_index: int, col_index: int, color: str) -> None:
        cell = self.cell(row_index, col_index)
        document = self.paragraph.section.document
        if document is None:
            raise ValueError("table is not attached to a document")
        border_fill_id = document.ensure_shading_border_fill(
            color,
            base_border_fill_id=cell.element.get("borderFillIDRef") or self.element.get("borderFillIDRef"),
        )
        cell.element.set("borderFillIDRef", border_fill_id)
        self.mark_dirty()

    def set_column_widths(self, weights: Sequence[int | float]) -> None:
        if len(weights) != self.column_count:
            raise ValueError("column width weights must match table column count")
        numeric_weights = [max(float(weight), 0.0) for weight in weights]
        if not any(numeric_weights):
            raise ValueError("at least one column width weight must be positive")

        sz = self.element.find(f"{_HP}sz")
        if sz is not None and sz.get("width", "").isdigit():
            total_width = int(sz.get("width", "0"))
        else:
            total_width = sum(self.cell(0, col).width for col in range(self.column_count))
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
        for entry in self.iter_grid():
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

    def set_cell_text(
        self,
        row_index: int,
        col_index: int,
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
        :class:`~hwpx.form_fit.report.FitResult` carries the verdict (and an
        ``overflow=fail`` miss makes ``ok`` ``False``). ``split_paragraphs`` is
        ignored in fit mode — line breaks are decided by measurement.
        """

        if logical:
            entry = self._grid_entry(row_index, col_index)
            if split_merged and not entry.is_anchor:
                cell = self.split_merged_cell(row_index, col_index)
            else:
                cell = entry.cell
        else:
            cell = self.cell(row_index, col_index)

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
                field_id=f"r{row_index}c{col_index}",
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
        paragraph_attrs = _default_cell_paragraph_attributes()
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
            {"rowAddr": str(logical_row), "colAddr": str(logical_col)},
        )
        _append_child(
            new_cell_element,
            f"{_HP}cellSpan",
            {"rowSpan": "1", "colSpan": "1"},
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
            logical_row, logical_col, col_width, row_height,
        )
        self._insert_split_cell_at_position(row_element, new_cell_element, logical_col)

    def split_merged_cell(
        self, row_index: int, col_index: int
    ) -> HwpxOxmlTableCell:
        entry = self._grid_entry(row_index, col_index)
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

        self.mark_dirty()
        return self.cell(row_index, col_index)

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
            raise ValueError(f"invalid spreadsheet range: {value!r}")
        start_col_label, start_row_label, end_col_label, end_row_label = match.groups()
        start_row = int(start_row_label) - 1
        end_row = int(end_row_label) - 1
        start_col = cls._spreadsheet_column_index(start_col_label)
        end_col = cls._spreadsheet_column_index(end_col_label)
        return start_row, start_col, end_row, end_col

    def _resolve_merge_target(
        self, start_row: int, start_col: int, end_row: int, end_col: int
    ) -> HwpxOxmlTableCell:
        if start_row > end_row or start_col > end_col:
            raise ValueError("merge coordinates must describe a valid rectangle")
        if start_row < 0 or start_col < 0:
            raise IndexError("merge coordinates must be non-negative")
        if end_row >= self.row_count or end_col >= self.column_count:
            raise IndexError("merge coordinates exceed table bounds")

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
    ) -> tuple[set[ET.Element], int, int]:
        removal_elements: set[ET.Element] = set()
        width_elements: set[ET.Element] = set()
        height_elements: set[ET.Element] = set()
        total_width = 0
        total_height = 0

        for row_index in range(start_row, end_row + 1):
            for col_index in range(start_col, end_col + 1):
                cell = self.cell(row_index, col_index)
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
        return removal_elements, total_width, total_height

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

    def merge_cells(
        self,
        start_row: int | str,
        start_col: int | None = None,
        end_row: int | None = None,
        end_col: int | None = None,
    ) -> HwpxOxmlTableCell:
        if isinstance(start_row, str):
            start_row, start_col, end_row, end_col = self._parse_spreadsheet_range(start_row)
        if start_col is None or end_row is None or end_col is None:
            raise TypeError("merge_cells requires either a spreadsheet range or four coordinates")

        target = self._resolve_merge_target(start_row, start_col, end_row, end_col)
        new_row_span = end_row - start_row + 1
        new_col_span = end_col - start_col + 1

        element_to_row = self._build_element_to_row_map()
        removal_elements, total_width, total_height = self._scan_merge_region(
            start_row, start_col, end_row, end_col, target
        )

        if not removal_elements and target.span == (new_row_span, new_col_span):
            return target

        self._remove_merged_cell_elements(removal_elements, element_to_row)

        target.set_span(new_row_span, new_col_span)
        target.set_size(total_width or target.width, total_height or target.height)
        self.mark_dirty()
        return target

__all__ = ["HwpxOxmlTable", "HwpxOxmlTableCell", "HwpxOxmlTableRow", "HwpxTableGridPosition"]
