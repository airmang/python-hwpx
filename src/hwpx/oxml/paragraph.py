# SPDX-License-Identifier: Apache-2.0
"""Paragraph content and inline-composition OXML service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence, cast
import warnings
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import (
    _HP,
    _HP_NS,
    _append_child,
    _append_text_with_run_choice_atoms,
    _append_text_with_tabs,
    _child_tag_like,
    _children_by_local,
    _clear_paragraph_layout_cache,
    _is_tab_control_element,
    _normalize_enum_attr,
    _object_id,
    _sanitize_text,
    NEW_NUM_KINDS,
)
from .namespaces import XML_NS, tag_local_name
from .dutmal_compose import _paragraph_add_composed_character, _paragraph_add_dutmal
from .field_marks import (
    _paragraph_add_date_field,
    _paragraph_add_path_field,
    _paragraph_add_proofreading_mark,
)
from .note_authoring import (
    _paragraph_add_endnote,
    _paragraph_add_footnote,
    _paragraph_endnotes,
    _paragraph_footnotes,
)
from .objects import (
    HwpxOxmlInlineObject,
    _create_picture_element,
    _missing_shape_children,
    _paragraph_add_arc,
    _paragraph_add_container,
    _paragraph_add_ellipse,
    _paragraph_add_line,
    _paragraph_add_polygon,
    _paragraph_add_rectangle,
    _paragraph_insert_shape_element,
    _paragraph_shapes,
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

    def _add_tracked_replace(
        self,
        old: str,
        new: str,
        *,
        delete_change_id: int,
        insert_change_id: int,
        first_mark_id: int,
    ) -> None:
        """Apply one replacement atomically to a single run model."""

        if old == "":
            raise ValueError("match must be a non-empty string")
        sanitized = _sanitize_text(new)
        if not sanitized:
            raise ValueError("tracked insert text must be non-empty")

        for run in self.runs:
            model = run.to_model()
            for span in model.text_spans:
                if old not in span.text:
                    continue
                if not body.wrap_tracked_delete_in_span(
                    span,
                    tc_id=delete_change_id,
                    mark_id=first_mark_id,
                    match=old,
                ):
                    raise ValueError(
                        "match crosses inline markup and cannot be wrapped safely"
                    )
                if not body.insert_tracked_text_after_delete(
                    span,
                    sanitized,
                    delete_tc_id=delete_change_id,
                    insert_tc_id=insert_change_id,
                    mark_id=first_mark_id + 1,
                ):
                    raise RuntimeError(
                        "tracked replacement lost its delete boundary"
                    )
                run.apply_model(model)
                return

        raise ValueError("match text was not found in the paragraph")

    def add_highlight(
        self,
        *,
        color: str,
        match: str,
    ) -> None:
        """Wrap the first occurrence of *match* in ``hp:markpenBegin``/``markpenEnd``.

        Mirrors :meth:`add_tracked_delete`'s substring branch: the first run
        whose spans concatenate to contain *match* is targeted, then the
        specific span holding it (contiguously) is wrapped.
        """

        if not match:
            raise ValueError("match must be a non-empty string")

        for run in self.runs:
            model = run.to_model()
            if match not in "".join(span.text for span in model.text_spans):
                continue
            for span in model.text_spans:
                if body.wrap_highlight_in_span(span, color=color, match=match):
                    run.apply_model(model)
                    return
            raise ValueError("match crosses inline markup and cannot be wrapped safely")

        raise ValueError("match text was not found in the paragraph")

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
        expand_special_characters: bool = False,
    ) -> HwpxOxmlRun:
        """Append a new run to the paragraph and return its wrapper.

        *expand_special_characters* (default ``False`` — opt-in, no change
        to any existing caller's output) converts three characters embedded
        in *text* to their real-corpus OWPML element form instead of
        leaving them as literal bytes inside ``hp:t``: ``"\\n"`` ->
        ``hp:lineBreak``, ``"\\u00a0"`` (no-break space) -> ``hp:nbSpace``,
        ``"\\u3000"`` (CJK full-width space) -> ``hp:fwSpace``. Real corpus
        (``error__20230818__test.hwpx``, ``error__20251107__test.hwpx``,
        ``error__20250808__...hwpx``) confirms Hancom always emits these as
        elements nested inside a single ``hp:t`` — never as literal
        characters, and never (for these three specifically) as a sibling
        of ``hp:t`` the way ``hp:tab`` is. Off by default because the plain
        ``text=`` path here never processed these characters before, and
        other call sites in this codebase (table cell multiline splitting,
        for one) already give ``"\\n"`` a different meaning of their own.
        """

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
        if expand_special_characters:
            _append_text_with_run_choice_atoms(run_element, text)
        else:
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

    def _context_table_width(self) -> int | None:
        """Hancom-like default table width for this paragraph's context.

        Inside a table cell the parent cell's usable width bounds the new
        (nested) table — the fidelity audit reproduced silent content loss
        when the fixed per-cell default exceeded it. At body level Hancom
        fits a new table to the text width (page width minus margins).
        Returns ``None`` when neither context is measurable.
        """

        # stdlib ET has no getparent; lxml-backed elements do. Guarded getattr
        # keeps both backends working (19 suite failures without the guard).
        get_parent = getattr(self.element, "getparent", None)
        ancestor = cast(
            "ET.Element | None", get_parent() if callable(get_parent) else None
        )
        while ancestor is not None:
            if tag_local_name(ancestor.tag) == "tc":
                cell_sz = ancestor.find(f"{_HP}cellSz")
                margin = ancestor.find(f"{_HP}cellMargin")
                if cell_sz is not None:
                    try:
                        width = int(cell_sz.get("width", "0"))
                    except ValueError:
                        return None
                    pad = 0
                    if margin is not None:
                        try:
                            pad = int(margin.get("left", "0")) + int(
                                margin.get("right", "0")
                            )
                        except ValueError:
                            pad = 0
                    usable = width - pad
                    return usable if usable > 0 else None
                return None
            next_parent = getattr(ancestor, "getparent", None)
            ancestor = cast(
                "ET.Element | None",
                next_parent() if callable(next_parent) else None,
            )

        try:
            properties = self.section.properties
            page = properties.page_size
            margins = properties.page_margins
        except Exception:
            return None
        if page.width <= 0:
            return None
        usable = page.width - margins.left - margins.right - margins.gutter
        return usable if usable > 0 else None

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
        if width is None:
            width = self._context_table_width()
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

        This is a low-level escape hatch: it writes the element and the
        attributes it is handed and nothing else, so the result is **not a
        document Hancom can open** until the caller supplies the required
        OWPML children (``offset``, ``orgSz``, ``curSz``, ``sz``, ``pos`` and
        the type-specific geometry).  A :class:`UserWarning` is raised while
        they are missing.

        For LINE / RECT / ELLIPSE shapes, prefer the dedicated ``add_line``,
        ``add_rectangle``, and ``add_ellipse`` methods, which build the full
        child structure.
        """
        if not shape_type:
            raise ValueError("shape_type must be a non-empty string")
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        element = _append_child(run, f"{_HP}{shape_type}", dict(attributes or {}))
        missing = _missing_shape_children(element)
        if missing:
            warnings.warn(
                f"add_shape({shape_type!r}) produced a shape without "
                f"{', '.join(missing)}; Hancom refuses to open a document "
                "containing it. Use add_line/add_rectangle/add_ellipse, or "
                "append the missing OWPML children yourself.",
                UserWarning,
                stacklevel=2,
            )
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
    #
    # Implementations live in ``oxml/objects.py`` (this owner module sits at
    # the modularization line cap) and are attached here as plain class
    # attributes — a function assigned this way is a method like any other,
    # so ``paragraph.add_rectangle(...)`` etc. keep working unchanged.

    _insert_shape_element = _paragraph_insert_shape_element
    add_line = _paragraph_add_line
    add_rectangle = _paragraph_add_rectangle
    add_ellipse = _paragraph_add_ellipse
    add_polygon = _paragraph_add_polygon
    add_arc = _paragraph_add_arc
    add_container = _paragraph_add_container
    shapes = property(_paragraph_shapes)

    # Implementations live in ``oxml/dutmal_compose.py`` -- ``objects.py``
    # (the shape-helpers' own overflow destination above) itself has no
    # headroom left either (1526/1600 measured before this module existed),
    # so this is a second overflow module, same reasoning.
    add_composed_character = _paragraph_add_composed_character
    add_dutmal = _paragraph_add_dutmal

    def add_control(
        self,
        attributes: dict[str, str] | None = None,
        *,
        control_type: str | None = None,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a generic ``<hp:ctrl>`` control element.

        This is a low-level escape hatch: an ``<hp:ctrl>`` carries no meaning
        of its own — the control it represents is its child element (
        ``colPr``, ``bookmark``, ``fieldBegin``, …).  Until the caller appends
        one, the element is empty and **Hancom refuses to open the document**,
        so a :class:`UserWarning` is raised.

        For the controls this package builds, prefer the dedicated
        ``add_column_definition``, ``add_bookmark``, and ``add_hyperlink``
        methods, which write the full child structure.
        """
        attrs = dict(attributes or {})
        if control_type is not None:
            attrs.setdefault("type", control_type)
        run = self._create_run_for_object(
            run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
        # ``ET.SubElement``는 stdlib Element만 받는다. 이 트리는 lxml이라
        # 그대로 부르면 TypeError로 항상 실패했다 — add_control은 문서에
        # 예제까지 있으면서 한 번도 동작한 적이 없다. 이 패키지의 다른
        # 생성 지점처럼 부모에게 만들게 해서 구현체를 맞춘다.
        element = run.makeelement(f"{_HP}ctrl", attrs)
        run.append(element)
        if len(element) == 0:
            warnings.warn(
                "add_control() produced an <hp:ctrl> with no control child; "
                "Hancom refuses to open a document containing it. Use "
                "add_column_definition/add_bookmark/add_hyperlink, or append "
                "the control element yourself.",
                UserWarning,
                stacklevel=2,
            )
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

        # 실한컴 gold 관례: 링크 서식(charPr)은 표시 텍스트 런에만 싣고
        # fieldBegin/fieldEnd 런은 주변 서식을 유지한다 — 뒤에 추가되는
        # 문단이 링크 서식을 상속(파랑 전염)하지 않게 하는 조건이기도 하다.
        run1 = self._create_run_for_object()
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
        run3 = self._create_run_for_object()
        ctrl3 = _append_child(run3, f"{_HP}ctrl", {})
        _append_child(ctrl3, f"{_HP}fieldEnd", {"beginIDRef": field_id})

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl1, self)

    add_date_field = _paragraph_add_date_field
    add_proofreading_mark = _paragraph_add_proofreading_mark
    add_path_field = _paragraph_add_path_field

    def add_title_mark(self, *, in_toc: bool) -> HwpxOxmlInlineObject:
        """이 문단의 첫 run 첫 ``hp:t`` 맨 앞에 ``<hp:titleMark
        ignore="0|1"/>``를 끼워 넣는다 -- "차례 숨기기"/"제목 차례 표시"의
        실측 계약(DEV-044, 6.15 박스 COM `SetPos`+`MarkTitle`/`HideTitle`
        3변형이 캐럿 문단 타겟팅을 확정: 마크는 항상 캐럿이 있는 문단에
        들어간다, 이전 Mac 프로브의 p0 착지는 캐럿 이동 불가에 따른
        퇴화 현상이었다).

        *in_toc*: ``True``(제목 차례 표시)면 ``ignore="1"``,
        ``False``(차례 숨기기)면 ``ignore="0"`` -- 이름의 직관과 반대인
        폴라리티가 실측 그대로다(Mac GUI A/B·Windows COM 독립 재확인
        일치). 호출자가 대상 문단을 직접 지정하는 이 API 형태가 실
        편집기의 "캐럿이 있는 문단" 타겟팅과 정확히 대응한다.
        """
        target_run: ET.Element | None = None
        text_element: ET.Element | None = None
        for run in self._run_elements():
            candidates = _children_by_local(run, "t")
            if candidates:
                target_run, text_element = run, candidates[0]
                break
        if text_element is None or target_run is None:
            from ..errors import HwpxStateError

            raise HwpxStateError(
                "문단에 hp:t를 가진 run이 없어 titleMark를 넣을 자리가 없습니다.",
                code="paragraph-title-mark-no-text-run",
            )
        mark = text_element.makeelement(
            _child_tag_like(text_element, "titleMark", _HP_NS),
            {"ignore": "1" if in_toc else "0"},
        )
        mark.tail = text_element.text
        text_element.text = None
        text_element.insert(0, mark)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(mark, self)

    def add_new_num(
        self,
        *,
        number: int = 1,
        kind: str = "PAGE",
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert ``<hp:ctrl><hp:newNum num="..." numType="..."/></hp:ctrl>``.

        Restarts the running count *kind* (``PAGE`` by default) at *number*
        from this paragraph onward — real corpus (hwpxlib_corpus, 7+ files)
        always self-closes ``hp:newNum`` with only ``num``/``numType``, even
        though the schema (``ParaList XML schema.xml:2741-2759``) declares a
        required ``autoNumFormat`` child; matching real Hancom output takes
        priority over the schema here.
        """

        normalized_kind = _normalize_enum_attr(kind or "PAGE", NEW_NUM_KINDS, label="kind")
        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        _append_child(
            ctrl, f"{_HP}newNum", {"num": str(int(number)), "numType": normalized_kind},
        )
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    def add_page_hiding(
        self,
        *,
        header: bool = False,
        footer: bool = False,
        master_page: bool = False,
        border: bool = False,
        fill: bool = False,
        page_num: bool = False,
        run_attributes: dict[str, str] | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert ``<hp:ctrl><hp:pageHiding .../></hp:ctrl>``.

        Hides the named page elements from this paragraph's page onward
        (``ParaList XML schema.xml:148-163`` — six independent booleans, all
        default ``false``/unhidden). Matches real corpus (hwpxlib_corpus, 4
        files) sibling placement: its own dedicated ``hp:ctrl``, typically
        alongside a ``newNum``/``pageNum`` control in the section-opening
        paragraph's first run.
        """

        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        _append_child(
            ctrl,
            f"{_HP}pageHiding",
            {
                "hideHeader": "1" if header else "0",
                "hideFooter": "1" if footer else "0",
                "hideMasterPage": "1" if master_page else "0",
                "hideBorder": "1" if border else "0",
                "hideFill": "1" if fill else "0",
                "hidePageNum": "1" if page_num else "0",
            },
        )
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl, self)

    def add_chart(
        self,
        chart_id_ref: str,
        *,
        size: tuple[int, int] | None = None,
        treat_as_char: bool = False,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a native ``<hp:chart>`` anchor referencing a chartML part.

        Emits the real-Hancom chart anchor (contract reverse-engineered in
        specs/055-chart-authoring/evidence/p0/chart-contract.md): the chart
        content lives in an ECMA-376 chartML part addressed directly by
        ``chartIDRef`` (real Hancom registers the part in no manifest), and
        Hancom lays the chart out from the chartML alone — no OLE fallback or
        pre-rendered image is required.

        Args:
            chart_id_ref: Package path of the chartML part
                (e.g. ``Chart/chart1.xml``).
            size: Optional ``(width, height)`` HWPUNIT pair for ``<hp:sz>``;
                defaults to the gold document's 32250x18750.
            treat_as_char: ``True`` places the chart inline in the text flow;
                the default mirrors the gold float placement.
        """
        reference = chart_id_ref.strip()
        if not reference:
            raise ValueError("chart_id_ref must be a non-empty package path")
        width, height = size if size is not None else (32250, 18750)
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref
        )
        chart = _append_child(run, f"{_HP}chart", {
            "id": _object_id(),
            "zOrder": "0",
            "numberingType": "PICTURE",
            "textWrap": "TOP_AND_BOTTOM" if treat_as_char else "SQUARE",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "chartIDRef": reference,
        })
        _append_child(chart, f"{_HP}sz", {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(chart, f"{_HP}pos", {
            "treatAsChar": "1" if treat_as_char else "0",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "0",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "PARA" if treat_as_char else "COLUMN",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(chart, f"{_HP}outMargin", {
            "left": "0",
            "right": "0",
            "top": "0",
            "bottom": "0",
        })
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(chart, self)

    def add_drop_cap(
        self,
        character: str,
        *,
        width: int,
        height: int,
        style: str = "TripleLine",
        char_pr_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a real-Hancom-shaped drop cap (문단 첫 글자 장식).

        Element construction lives in :mod:`.drop_cap` (real-corpus reverse
        engineering, ``TripleLine``-only v1 scope -- see that module's own
        docstring). This method only wires the built element into this
        paragraph's run, matching :meth:`add_chart`'s own thin-wiring shape.
        """

        from .drop_cap import create_drop_cap_element

        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
        drop_cap = create_drop_cap_element(
            width, height, character,
            style=style, char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
        )
        # Ensure element type matches the run type (lxml vs stdlib ET) --
        # same bridge _paragraph_insert_shape_element uses.
        if type(drop_cap) is not type(run):
            drop_cap = LET.fromstring(ET.tostring(drop_cap, encoding="utf-8"))
        run.append(drop_cap)
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(drop_cap, self)

    def add_equation(
        self,
        script: str,
        *,
        base_unit: int = 1100,
        size: tuple[int, int] | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert an inline ``<hp:equation>`` carrying an EqEdit *script*.

        Emits the real-Hancom equation shape (contract reverse-engineered in
        specs/054-equation-authoring/evidence/p0/equation-contract.md): the
        EqEdit source lives in the ``<hp:script>`` child, no lineseg cache is
        written (Hancom re-lays-out on open), and the shape is inline
        (``treatAsChar="1"``) so it renders in the page flow.

        Args:
            script: EqEdit script stored verbatim (e.g. ``{a} over {b}``).
            base_unit: Equation base font size in 1/100 pt (gold: 1100/1200).
            size: Optional explicit ``(width, height)`` HWPUNIT pair for
                ``<hp:sz>``; when omitted a proportional placeholder is
                written — Hancom re-measures on open (P0 evidence).
        """
        text = script.strip()
        if not text:
            raise ValueError("equation script must be a non-empty string")
        if base_unit <= 0:
            raise ValueError("base_unit must be positive")
        if size is None:
            visible = len(text.replace("{", "").replace("}", "").replace(" ", ""))
            width = int(base_unit * 0.45 * max(6, visible))
            height = int(base_unit * 2.5)
        else:
            width, height = size
        run = self._create_run_for_object(
            run_attributes, char_pr_id_ref=char_pr_id_ref
        )
        equation = _append_child(run, f"{_HP}equation", {
            "id": _object_id(),
            "zOrder": "0",
            "numberingType": "EQUATION",
            "textWrap": "TOP_AND_BOTTOM",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "version": "Equation Version 60",
            "baseLine": str(max(1, round(base_unit * 69 / 1200))),
            "textColor": "#000000",
            "baseUnit": str(base_unit),
            "lineMode": "CHAR",
            "font": "HYhwpEQ",
        })
        _append_child(equation, f"{_HP}sz", {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(equation, f"{_HP}pos", {
            "treatAsChar": "1",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "0",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "PARA",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(equation, f"{_HP}outMargin", {
            "left": "56",
            "right": "56",
            "top": "0",
            "bottom": "0",
        })
        comment = _append_child(equation, f"{_HP}shapeComment", {})
        comment.text = "수식입니다."
        script_element = _append_child(equation, f"{_HP}script", {})
        script_element.text = text
        self.section.mark_dirty()
        return HwpxOxmlInlineObject(equation, self)

    def add_form_field(
        self,
        name: str,
        *,
        prompt: str = "",
        memo: str = "",
        editable: bool = True,
        prompt_char_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a click-here (누름틀) form field at the end of this paragraph.

        Emits the real-Hancom CLICKHERE shape (reverse-engineered from Hancom
        Office 12.0.0.3288 gold documents):
        a ``fieldBegin`` ctrl run carrying the ``Prop``/``Command``/``Direction``/
        ``HelpState`` parameters, an optional prompt run showing *prompt* (the
        안내문, screen-only — Hancom does not print it), and a ``fieldEnd`` ctrl
        run. ``Command`` lengths count UTF-16 characters, so values may contain
        spaces. ``id``/``fieldid`` values are semantically free — Hancom reissues
        its own on save.

        Args:
            name: Field name used by ``list_form_fields``/``fill_form_field``.
            prompt: 안내문 text shown while the field is empty (``Direction``).
            memo: Help text (``HelpState``).
            prompt_char_pr_id_ref: charPr for the prompt run (callers normally
                pass a red-italic style; Hancom uses one).

        Returns:
            The ``<hp:ctrl>`` element wrapping the ``<hp:fieldBegin>``.
        """
        field_id = _object_id()
        field_instance_id = _object_id()
        direction = _sanitize_text(prompt)
        help_state = _sanitize_text(memo)

        # Run 1: fieldBegin with the CLICKHERE parameter block
        run1 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl1 = _append_child(run1, f"{_HP}ctrl", {})
        field_begin = _append_child(ctrl1, f"{_HP}fieldBegin", {
            "id": field_id,
            "type": "CLICK_HERE",
            "name": _sanitize_text(name),
            "editable": "1" if editable else "0",
            "dirty": "0",
            "zorder": "-1",
            "fieldid": field_instance_id,
            "metaTag": "",
        })
        payload = (
            f"Direction:wstring:{len(direction)}:{direction} "
            f"HelpState:wstring:{len(help_state)}:{help_state} "
        )
        param_count = 2 + (1 if direction else 0) + (1 if help_state else 0)
        parameters = _append_child(
            field_begin, f"{_HP}parameters", {"cnt": str(param_count), "name": ""}
        )
        prop = _append_child(parameters, f"{_HP}integerParam", {"name": "Prop"})
        prop.text = "9"
        command = _append_child(parameters, f"{_HP}stringParam", {
            "name": "Command",
            f"{{{XML_NS}}}space": "preserve",
        })
        command.text = f"Clickhere:set:{len(payload)}:{payload} "
        if direction:
            direction_param = _append_child(
                parameters, f"{_HP}stringParam", {"name": "Direction"}
            )
            direction_param.text = direction
        if help_state:
            help_param = _append_child(
                parameters, f"{_HP}stringParam", {"name": "HelpState"}
            )
            help_param.text = help_state

        # Run 2: the prompt placeholder (only while a prompt exists)
        if direction:
            run2 = self._create_run_for_object(
                char_pr_id_ref=(
                    prompt_char_pr_id_ref
                    if prompt_char_pr_id_ref is not None
                    else char_pr_id_ref
                ),
            )
            prompt_text = _append_child(run2, f"{_HP}t", {})
            prompt_text.text = direction

        # Run 3: fieldEnd + trailing empty text node (gold shape)
        run3 = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        ctrl3 = _append_child(run3, f"{_HP}ctrl", {})
        _append_child(ctrl3, f"{_HP}fieldEnd", {
            "beginIDRef": field_id,
            "fieldid": field_instance_id,
        })
        _append_child(run3, f"{_HP}t", {})

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(ctrl1, self)

    def add_check_box(
        self,
        caption: str,
        *,
        checked: bool = False,
        name: str | None = None,
        width: int = 9921,
        height: int = 1984,
        char_pr_id_ref: str | int | None = None,
    ) -> HwpxOxmlInlineObject:
        """Insert a check-box form object (체크박스) at the end of this paragraph.

        Emits the real-Hancom ``<hp:checkBtn>`` shape. Unlike the click-here
        field this is **not** wrapped in ``<hp:ctrl>`` — it is a direct child of
        the run, beside the ``<hp:t>`` node.

        Hancom refuses to open a document whose ``checkBtn`` lacks
        ``<hp:formCharPr>`` (measured: the same file with the element present
        opens, without it Hancom reports a read error and produces nothing), so
        the child block is always emitted. ``caption`` is drawn next to the box
        and appears in the rendered text layer; ``checked`` selects the
        ``CHECKED``/``UNCHECKED`` value that draws ☑ or □.

        Args:
            caption: Label drawn beside the box.
            checked: Initial state.
            name: Object name. Defaults to a generated ``CheckBox<N>``.
            width: Box + caption width in HWPUNIT.
            height: Box height in HWPUNIT.
        """

        run = self._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
        check = _append_child(run, f"{_HP}checkBtn", {
            "caption": _sanitize_text(caption),
            "value": "CHECKED" if checked else "UNCHECKED",
            "radioGroupName": "",
            "triState": "0",
            "backStyle": "OPAQUE",
            "name": _sanitize_text(name) if name else f"CheckBox{_object_id()}",
            "foreColor": "#000000",
            "backColor": "#FFFFFF",
            "groupName": "",
            "tabStop": "1",
            "editable": "1",
            "tabOrder": "0",
            "enabled": "1",
            "borderTypeIDRef": "0",
            "drawFrame": "1",
            "printable": "1",
            "command": "",
        })
        _append_child(check, f"{_HP}formCharPr", {
            "charPrIDRef": str(char_pr_id_ref if char_pr_id_ref is not None else 0),
            "followContext": "0",
            "autoSz": "0",
            "wordWrap": "0",
        })
        _append_child(check, f"{_HP}sz", {
            "width": str(int(width)),
            "widthRelTo": "ABSOLUTE",
            "height": str(int(height)),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        })
        _append_child(check, f"{_HP}pos", {
            "treatAsChar": "1",
            "affectLSpacing": "0",
            "flowWithText": "1",
            "allowOverlap": "1",
            "holdAnchorAndSO": "0",
            "vertRelTo": "PARA",
            "horzRelTo": "COLUMN",
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": "0",
            "horzOffset": "0",
        })
        _append_child(check, f"{_HP}outMargin", {
            "left": "0", "right": "0", "top": "0", "bottom": "0",
        })
        _append_child(run, f"{_HP}t", {})

        self.section.mark_dirty()
        return HwpxOxmlInlineObject(check, self)

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

    # Footnote/endnote authoring lives in note_authoring.py (owner-file
    # headroom, see class-attribute assignments near the top of this class).
    add_footnote = _paragraph_add_footnote
    add_endnote = _paragraph_add_endnote
    footnotes = property(_paragraph_footnotes)
    endnotes = property(_paragraph_endnotes)

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
    def column_break(self) -> bool:
        """Whether this paragraph forces a column break before it starts.

        This is ``hp:p``'s own ``columnBreak`` attribute -- a per-paragraph
        instance flag (default ``"0"``, always present on every parsed
        paragraph already), distinct from ``hh:breakSetting``'s
        ``pageBreakBefore`` (a shared paraPr *style* property that
        ``set_paragraph_format``'s ``page_break_before`` controls). The
        sibling ``pageBreak`` attribute uses the same "0"/"1" lexical form
        (real-corpus confirmed: 73/14266 paragraphs carry ``pageBreak="1"``,
        never ``"true"``/``"false"`` — 6.12 트레인㊸ 갭④).
        """
        return self.element.get("columnBreak") == "1"

    @column_break.setter
    def column_break(self, value: bool) -> None:
        new_value = "1" if value else "0"
        if self.element.get("columnBreak") != new_value:
            self.element.set("columnBreak", new_value)
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
