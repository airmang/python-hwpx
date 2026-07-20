# SPDX-License-Identifier: Apache-2.0
"""Paragraph content and inline-composition OXML service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _HP_NS,
    _append_child,
    _append_text_with_tabs,
    _child_tag_like,
    _children_by_local,
    _clear_paragraph_layout_cache,
    _default_sublist_attributes,
    _is_tab_control_element,
    _object_id,
    _paragraph_id,
    _sanitize_text,
)
from .memo import HwpxOxmlNote
from .namespaces import tag_local_name
from .objects import (
    HwpxOxmlInlineObject,
    HwpxOxmlShape,
    _create_ellipse_element,
    _create_line_element,
    _create_picture_element,
    _create_rectangle_element,
)
from .run import HwpxOxmlRun
from .table import HwpxOxmlTable

if TYPE_CHECKING:
    from .section import HwpxOxmlSection


@dataclass
class HwpxOxmlParagraph:
    """Lightweight wrapper around an ``<hp:p>`` element."""

    element: ET.Element
    section: HwpxOxmlSection

    def __repr__(self) -> str:
        """Return a compact and safe summary of paragraph contents."""

        runs = self._run_elements()
        return (
            f"{self.__class__.__name__}("
            f"runs={len(runs)}, "
            f"tables={len(self.tables)}, "
            f"text_length={len(self.text)}"
            ")"
        )

    def to_model(self) -> "body.Paragraph":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_paragraph_element(node)

    @property
    def model(self) -> "body.Paragraph":
        return self.to_model()

    def apply_model(self, model: "body.Paragraph") -> None:
        new_node = body.serialize_paragraph(model)
        xml_bytes = LET.tostring(new_node)
        parent = self.section.element
        if isinstance(parent, LET._Element):
            replacement = LET.fromstring(xml_bytes)
        else:
            replacement = ET.fromstring(xml_bytes)
        paragraph_children = list(parent)
        index = paragraph_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        self.section.mark_dirty()

    def _run_elements(self) -> list[ET.Element]:
        return _children_by_local(self.element, "run")

    def _ensure_run(self) -> ET.Element:
        runs = self._run_elements()
        if runs:
            return runs[0]

        run_attrs: dict[str, str] = {}
        default_char = self.char_pr_id_ref or "0"
        if default_char is not None:
            run_attrs["charPrIDRef"] = default_char
        run = self.element.makeelement(_child_tag_like(self.element, "run", _HP_NS), run_attrs)
        self.element.append(run)
        return run

    @property
    def runs(self) -> list[HwpxOxmlRun]:
        """Return the runs contained in this paragraph."""
        return [HwpxOxmlRun(run, self) for run in self._run_elements()]

    def _last_text_run_for_tracked_insert(
        self,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlRun:
        desired_char = None if char_pr_id_ref is None else str(char_pr_id_ref)
        runs = self.runs

        if desired_char is not None:
            for run in reversed(runs):
                if run.char_pr_id_ref != desired_char:
                    continue
                if run.to_model().text_spans:
                    return run
            return self.add_run("", char_pr_id_ref=desired_char)

        for run in reversed(runs):
            if run.to_model().text_spans:
                return run
        return self.add_run("", char_pr_id_ref=self.char_pr_id_ref or "0")

    def add_tracked_insert(
        self,
        text: str,
        *,
        change_id: int,
        mark_id: int,
        char_pr_id_ref: str | int | None = None,
    ) -> None:
        sanitized = _sanitize_text(text)
        if not sanitized:
            raise ValueError("tracked insert text must be non-empty")

        run = self._last_text_run_for_tracked_insert(char_pr_id_ref=char_pr_id_ref)
        model = run.to_model()
        body.append_tracked_insert_to_run(
            model,
            sanitized,
            tc_id=change_id,
            mark_id=mark_id,
        )
        run.apply_model(model)

    def add_tracked_delete(
        self,
        *,
        change_id: int,
        first_mark_id: int,
        match: str | None = None,
    ) -> int:
        if match == "":
            raise ValueError("match must be a non-empty string")

        next_mark_id = first_mark_id
        if match is not None:
            for run in self.runs:
                model = run.to_model()
                if match not in "".join(span.text for span in model.text_spans):
                    continue
                for span in model.text_spans:
                    if body.wrap_tracked_delete_in_span(
                        span,
                        tc_id=change_id,
                        mark_id=next_mark_id,
                        match=match,
                    ):
                        run.apply_model(model)
                        return next_mark_id + 1
                raise ValueError("match crosses inline markup and cannot be wrapped safely")
            raise ValueError("match text was not found in the paragraph")

        modified = False
        for run in self.runs:
            model = run.to_model()
            changed = False
            for span in model.text_spans:
                if not span.text:
                    continue
                body.wrap_tracked_delete_in_span(
                    span,
                    tc_id=change_id,
                    mark_id=next_mark_id,
                )
                next_mark_id += 1
                changed = True
            if changed:
                run.apply_model(model)
                modified = True

        if not modified:
            raise ValueError("paragraph contains no text to delete")
        return next_mark_id

    @property
    def text(self) -> str:
        """Return the concatenated textual content of this paragraph."""
        texts: list[str] = []
        for run in self._run_elements():
            for child in run:
                if tag_local_name(child.tag) == "t":
                    if child.text:
                        texts.append(child.text)
                elif tag_local_name(child.tag) == "tab" or _is_tab_control_element(child):
                    texts.append("\t")
        return "".join(texts)

    @text.setter
    def text(self, value: str) -> None:
        """Replace the textual contents of this paragraph.

        Style references (``paraPrIDRef``, ``styleIDRef`` on the paragraph and
        ``charPrIDRef`` on the surviving run) are preserved.  Empty runs that
        contained only text nodes are removed to keep the XML clean.
        """
        runs = self._run_elements()

        # Identify first run — its charPrIDRef will be kept.
        first_run = self._ensure_run()

        # Remove existing text/tab nodes from all runs.
        for run in runs:
            for child in list(run):
                if tag_local_name(child.tag) in {"t", "tab"} or _is_tab_control_element(child):
                    run.remove(child)

        # Remove non-first runs that are now empty (only had text).
        # Runs with non-text children (tables, shapes, controls) are kept.
        for run in runs:
            if run is first_run:
                continue
            if len(list(run)) == 0:
                self.element.remove(run)

        # Write the new text into the first run, preserving tabs as <hp:tab/>.
        _append_text_with_tabs(first_run, value)
        _clear_paragraph_layout_cache(self.element)
        self.section.mark_dirty()

    def clear_text(self) -> None:
        """Remove all text content while preserving styles and non-text elements.

        Style references on the paragraph and surviving runs are kept intact.
        Empty runs are cleaned up.
        """
        runs = self._run_elements()
        for run in runs:
            for child in list(run):
                if child.tag == f"{_HP}t":
                    run.remove(child)
        # Remove runs that are now completely empty.
        for run in list(runs):
            if len(list(run)) == 0:
                self.element.remove(run)
        _clear_paragraph_layout_cache(self.element)
        self.section.mark_dirty()

    def remove(self) -> None:
        """Remove this paragraph from its parent section.

        After removal, the paragraph wrapper should no longer be used.
        Raises ``ValueError`` if the section would become empty (HWPX
        requires at least one ``<hp:p>`` per section).
        """
        parent = self.section.element
        siblings = parent.findall(f"{_HP}p")
        if len(siblings) <= 1:
            raise ValueError(
                "섹션에는 최소 하나의 단락이 필요합니다. "
                "마지막 단락은 삭제할 수 없습니다."
            )
        try:
            parent.remove(self.element)
        except ValueError:  # pragma: no cover – defensive
            return
        self.section.mark_dirty()

    def _create_run_for_object(
        self,
        run_attributes: dict[str, str] | None = None,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> ET.Element:
        attrs = dict(run_attributes or {})
        if char_pr_id_ref is not None:
            attrs.setdefault("charPrIDRef", str(char_pr_id_ref))
        elif "charPrIDRef" not in attrs:
            default_char = self.char_pr_id_ref or "0"
            if default_char is not None:
                attrs["charPrIDRef"] = str(default_char)
        run = self.element.makeelement(f"{_HP}run", attrs)
        self.element.append(run)
        return run

    def add_run(
        self,
        text: str = "",
        *,
        char_pr_id_ref: str | int | None = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
        attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlRun:
        """Append a new run to the paragraph and return its wrapper."""

        run_attrs = dict(attributes or {})

        if "charPrIDRef" not in run_attrs:
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            else:
                document = self.section.document
                if document is not None:
                    style_id = document.ensure_run_style(
                        bold=bool(bold),
                        italic=bool(italic),
                        underline=bool(underline),
                        color=color,
                        font=font,
                        size=size,
                        highlight=highlight,
                        strike=strike,
                    )
                    run_attrs["charPrIDRef"] = style_id
                else:
                    default_char = self.char_pr_id_ref or "0"
                    if default_char is not None:
                        run_attrs["charPrIDRef"] = str(default_char)

        run_element = _append_child(self.element, f"{_HP}run", run_attrs)
        text_element = _append_child(run_element, f"{_HP}t", {})
        text_element.text = text
        self.section.mark_dirty()
        return HwpxOxmlRun(run_element, self)

    @property
    def tables(self) -> list["HwpxOxmlTable"]:
        """Return the tables embedded within this paragraph."""

        tables: list[HwpxOxmlTable] = []
        for run in self._run_elements():
            for child in run:
                if child.tag == f"{_HP}tbl":
                    tables.append(HwpxOxmlTable(child, self))
        return tables

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlTable:
        if border_fill_id_ref is None:
            document = self.section.document
            if document is not None:
                resolved_border_fill: str | int = document.ensure_basic_border_fill()
            else:
                resolved_border_fill = "0"
        else:
            resolved_border_fill = border_fill_id_ref

        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        table_element = HwpxOxmlTable.create(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=resolved_border_fill,
        )
        if type(table_element) is not type(run):
            table_element = LET.fromstring(ET.tostring(table_element, encoding="utf-8"))

        run.append(table_element)
        self.section.mark_dirty()
        return HwpxOxmlTable(table_element, self)

    def add_shape(
        self,
        shape_type: str,
        attributes: dict[str, str] | None = None,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a generic shape element.

        For spec-compliant LINE / RECT / ELLIPSE shapes, prefer the
        dedicated ``add_line``, ``add_rectangle``, and ``add_ellipse``
        methods which build the full OWPML child structure.
        """
        if not shape_type:
            raise ValueError("shape_type must be a non-empty string")
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = _append_child(run, f"{_HP}{shape_type}", dict(attributes or {}))
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    def add_picture(
        self,
        binary_item_id_ref: str,
        *,
        width: int = 14400,
        height: int = 14400,
        align: str | None = None,
        treat_as_char: bool = True,
        pos_overrides: dict[str, str | int] | None = None,
        text_wrap: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a corpus-shaped ``<hp:pic>`` referencing embedded BinData.

        With ``treat_as_char=False`` and ``pos_overrides`` the picture is placed as a
        **floating** object: ``pos_overrides`` sets ``horz/vertRelTo`` (e.g. ``PAPER``),
        ``horz/vertAlign`` and ``horz/vertOffset`` (HWPUNIT, non-negative) on the
        ``<hp:pos>`` so the image lands at a fixed page position (used by 직인 placement).
        ``text_wrap`` overrides the pic's ``textWrap`` (e.g. ``IN_FRONT_OF_TEXT`` so a
        seal stamped over a line does not reflow the text it overlaps).
        """

        if pos_overrides and treat_as_char:
            raise ValueError(
                "pos_overrides is for floating placement; pass treat_as_char=False "
                "(a PAPER-relative <hp:pos> on an inline pic is contradictory)"
            )

        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = _create_picture_element(
            str(binary_item_id_ref),
            int(width),
            int(height),
            align=align,
            treat_as_char=treat_as_char,
            pos_overrides=pos_overrides,
            text_wrap=text_wrap,
        )
        if type(element) is not type(run):
            element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
        run.append(element)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    # ------------------------------------------------------------------
    # Spec-compliant drawing shape helpers
    # ------------------------------------------------------------------

    def _insert_shape_element(
        self,
        element: ET.Element,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlShape:
        """Attach a pre-built shape element into a new run and return a wrapper."""
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        # Ensure element type matches the run type (lxml vs stdlib ET)
        if type(element) is not type(run):
            element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
        run.append(element)
        self.section.mark_dirty()
        return HwpxOxmlShape(element, self)

    def add_line(
        self,
        start_x: int = 0,
        start_y: int = 0,
        end_x: int = 14400,
        end_y: int = 0,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        treat_as_char: bool = True,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a spec-compliant ``<hp:line>`` drawing shape.

        Coordinates are in HWPUNIT (7200 per inch).
        """
        el = _create_line_element(
            start_x, start_y, end_x, end_y,
            line_color=line_color,
            line_width=line_width,
            treat_as_char=treat_as_char,
        )
        return self._insert_shape_element(
            el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
        )

    def add_rectangle(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        ratio: int = 0,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a spec-compliant ``<hp:rect>`` drawing shape.

        Dimensions are in HWPUNIT.  *ratio* controls corner roundness
        (0 = sharp, 50 = semicircle).
        """
        el = _create_rectangle_element(
            width, height,
            ratio=ratio,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
        )
        return self._insert_shape_element(
            el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
        )

    def add_ellipse(
        self,
        width: int = 14400,
        height: int = 7200,
        *,
        line_color: str = "#000000",
        line_width: str = "283",
        fill_color: str | None = None,
        treat_as_char: bool = True,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlShape:
        """Insert a spec-compliant ``<hp:ellipse>`` drawing shape.

        Dimensions are in HWPUNIT.
        """
        el = _create_ellipse_element(
            width, height,
            line_color=line_color,
            line_width=line_width,
            fill_color=fill_color,
            treat_as_char=treat_as_char,
        )
        return self._insert_shape_element(
            el, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
        )

    @property
    def shapes(self) -> list[HwpxOxmlShape]:
        """Return all drawing shapes embedded in this paragraph."""
        shape_tags = {f"{_HP}line", f"{_HP}rect", f"{_HP}ellipse",
                      f"{_HP}arc", f"{_HP}polygon", f"{_HP}curve",
                      f"{_HP}connectLine"}
        result: list[HwpxOxmlShape] = []
        for run in self._run_elements():
            for child in run:
                if child.tag in shape_tags:
                    result.append(HwpxOxmlShape(child, self))
        return result

    def add_control(
        self,
        attributes: dict[str, str] | None = None,
        *,
        control_type: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        attrs = dict(attributes or {})
        if control_type is not None:
            attrs.setdefault("type", control_type)
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = ET.SubElement(run, f"{_HP}ctrl", attrs)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(element, self)

    # ------------------------------------------------------------------
    # Column definition helpers
    # ------------------------------------------------------------------

    def add_column_definition(
        self,
        col_count: int = 2,
        *,
        col_type: str = "NEWSPAPER",
        layout: str = "LEFT",
        same_size: bool = True,
        same_gap: int = 1200,
        column_widths: Sequence[tuple[int, int]] | None = None,
        separator_type: str | None = None,
        separator_width: str | None = None,
        separator_color: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a column definition control ``<hp:ctrl><hp:colPr>…</hp:colPr></hp:ctrl>``.

        Args:
            col_count: Number of columns (1–255).
            col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
            layout: ``LEFT``, ``RIGHT``, or ``MIRROR``.
            same_size: If ``True`` all columns have equal width.
            same_gap: Gap between columns when *same_size* is ``True`` (HWPUNIT).
            column_widths: When *same_size* is ``False``, a sequence of
                ``(width, gap)`` tuples – one per column.
            separator_type: Line type for the column separator (e.g. ``SOLID``).
            separator_width: Line width (e.g. ``0.12 mm``).
            separator_color: Line colour (e.g. ``#000000``).
        """
        if not 1 <= col_count <= 255:
            raise ValueError("col_count must be between 1 and 255")

        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref,
        )
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        col_pr_attrs: dict[str, str] = {
            "id": _object_id(),
            "type": col_type,
            "layout": layout,
            "colCount": str(col_count),
            "sameSz": str(same_size).lower(),
            "sameGap": str(same_gap) if same_size else "0",
        }
        col_pr = _append_child(ctrl, f"{_HP}colPr", col_pr_attrs)

        # Optional column separator line
        if separator_type or separator_width or separator_color:
            line_attrs: dict[str, str] = {}
            if separator_type:
                line_attrs["type"] = separator_type
            if separator_width:
                line_attrs["width"] = separator_width
            if separator_color:
                line_attrs["color"] = separator_color
            _append_child(col_pr, f"{_HP}colLine", line_attrs)

        # Individual column sizes when same_size=False
        if not same_size and column_widths:
            for w, g in column_widths:
                _append_child(col_pr, f"{_HP}colSz", {
                    "width": str(w), "gap": str(g),
                })

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    # ------------------------------------------------------------------
    # Bookmark / Hyperlink helpers
    # ------------------------------------------------------------------

    def add_bookmark(
        self,
        name: str,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a bookmark marker ``<hp:ctrl><hp:bookmark name="..."/></hp:ctrl>``.

        The bookmark name can be referenced by hyperlinks or cross-references.
        """
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref,
        )
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        _append_child(ctrl, f"{_HP}bookmark", {"name": name})
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    def add_hyperlink(
        self,
        url: str,
        display_text: str,
        *,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a hyperlink spanning three runs: fieldBegin, text, fieldEnd.

        Args:
            url: The target URL or bookmark reference.
            display_text: The visible text for the hyperlink.

        Returns:
            The ``<hp:ctrl>`` element wrapping the ``<hp:fieldBegin>``.
        """
        field_id = _object_id()

        # Run 1: fieldBegin
        run1 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl1 = _append_child(run1, f"{_HP}ctrl", {})
        fb_attrs: dict[str, str] = {
            "id": field_id,
            "type": "HYPERLINK",
            "name": url,
            "editable": "false",
            "dirty": "false",
        }
        _append_child(ctrl1, f"{_HP}fieldBegin", fb_attrs)

        # Run 2: visible text content
        run2 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        t = _append_child(run2, f"{_HP}t", {})
        t.text = _sanitize_text(display_text)

        # Run 3: fieldEnd
        run3 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl3 = _append_child(run3, f"{_HP}ctrl", {})
        _append_child(ctrl3, f"{_HP}fieldEnd", {"beginIDRef": field_id})

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl1, self)

    @property
    def bookmarks(self) -> list[str]:
        """Return the names of all bookmarks in this paragraph."""
        names: list[str] = []
        for run in self._run_elements():
            for ctrl in run.findall(f"{_HP}ctrl"):
                for bm in ctrl.findall(f"{_HP}bookmark"):
                    name = bm.get("name", "")
                    if name:
                        names.append(name)
        return names

    @property
    def hyperlinks(self) -> list[dict[str, str]]:
        """Return metadata for all hyperlinks in this paragraph.

        Each dict has ``id``, ``url`` (from the ``name`` attribute),
        and ``type`` keys.
        """
        result: list[dict[str, str]] = []
        for run in self._run_elements():
            for ctrl in run.findall(f"{_HP}ctrl"):
                for fb in ctrl.findall(f"{_HP}fieldBegin"):
                    if fb.get("type") == "HYPERLINK":
                        result.append({
                            "id": fb.get("id", ""),
                            "url": fb.get("name", ""),
                            "type": fb.get("type", ""),
                        })
        return result

    # ------------------------------------------------------------------
    # Footnote / Endnote helpers
    # ------------------------------------------------------------------

    def _add_note(
        self,
        tag: str,
        text: str,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Insert a ``<hp:footNote>`` or ``<hp:endNote>`` element."""

        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        note_element = _append_child(run, f"{_HP}{tag}", {"instId": _object_id()})
        sublist = _append_child(note_element, f"{_HP}subList", _default_sublist_attributes())
        p_attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
        paragraph = _append_child(sublist, f"{_HP}p", p_attrs)
        # 본문 run의 charPrIDRef도 인자를 따라가도록 적용 (host run과 동일 스타일).
        # None이면 "0"(default).
        body_cpr = "0" if char_pr_id_ref is None else str(char_pr_id_ref)
        note_run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": body_cpr})
        t = _append_child(note_run, f"{_HP}t", {})
        t.text = _sanitize_text(text)
        self.section.mark_dirty()
        return HwpxOxmlNote(note_element, self)

    def add_footnote(
        self,
        text: str,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Insert a footnote at the end of this paragraph."""
        return self._add_note("footNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)

    def add_endnote(
        self,
        text: str,
        *,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlNote:
        """Insert an endnote at the end of this paragraph."""
        return self._add_note("endNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)

    @property
    def footnotes(self) -> list[HwpxOxmlNote]:
        """Return all footnotes in this paragraph."""
        return [
            HwpxOxmlNote(el, self)
            for el in self.element.findall(f".//{_HP}footNote")
        ]

    @property
    def endnotes(self) -> list[HwpxOxmlNote]:
        """Return all endnotes in this paragraph."""
        return [
            HwpxOxmlNote(el, self)
            for el in self.element.findall(f".//{_HP}endNote")
        ]

    @property
    def para_pr_id_ref(self) -> str | None:
        """Return the paragraph property reference applied to this paragraph."""
        return self.element.get("paraPrIDRef")

    @para_pr_id_ref.setter
    def para_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "paraPrIDRef" in self.element.attrib:
                del self.element.attrib["paraPrIDRef"]
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("paraPrIDRef") != new_value:
            self.element.set("paraPrIDRef", new_value)
            self.section.mark_dirty()

    @property
    def style_id_ref(self) -> str | None:
        """Return the style reference applied to this paragraph."""
        return self.element.get("styleIDRef")

    @style_id_ref.setter
    def style_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "styleIDRef" in self.element.attrib:
                del self.element.attrib["styleIDRef"]
                self.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("styleIDRef") != new_value:
            self.element.set("styleIDRef", new_value)
            self.section.mark_dirty()

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the shared character property reference across runs.

        If runs use multiple different references the value ``None`` is
        returned, indicating the paragraph does not have a uniform character
        style applied.
        """

        values: set[str] = set()
        for run in self._run_elements():
            value = run.get("charPrIDRef")
            if value is not None:
                values.add(value)

        if not values:
            return None
        if len(values) == 1:
            return next(iter(values))
        return None

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        new_value = None if value is None else str(value)
        runs = self._run_elements()
        if not runs:
            runs = [self._ensure_run()]

        changed = False
        for run in runs:
            if new_value is None:
                if "charPrIDRef" in run.attrib:
                    del run.attrib["charPrIDRef"]
                    changed = True
            else:
                if run.get("charPrIDRef") != new_value:
                    run.set("charPrIDRef", new_value)
                    changed = True

        if changed:
            # A style swap changes glyph metrics, so the cached line layout of
            # this paragraph no longer holds.
            _clear_paragraph_layout_cache(self.element)
            self.section.mark_dirty()

__all__ = ["HwpxOxmlParagraph"]
