# SPDX-License-Identifier: Apache-2.0
"""Section body, layout-cache, memo, and composition OXML service."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _require_text,
    keep_ids_clear_of,
    paragraph_attributes,
    _HP,
    _HP_NS,
    _append_child,
    _append_text_with_tabs,
    _child_tag_like,
    _children_by_local,
    _clear_paragraph_layout_cache,
    _clone_paragraph_element,
    _element_local_name,
    _first_child_by_local,
    _paragraph_id,
    _remove_stale_paragraph_layout_cache,
    _serialize_xml,
)
from ..errors import rejects_removed_arguments
from .body import INLINE_OBJECT_NAMES
from .memo import HwpxOxmlFieldMemo, HwpxOxmlMemo, HwpxOxmlMemoGroup, memo_field_id
from .paragraph import HwpxOxmlParagraph
from .section_format import HwpxOxmlSectionProperties
from .namespaces import tag_local_name
from .section_story import HwpxOxmlSectionHeaderFooter, story_marks

if TYPE_CHECKING:
    from ..objects.results import ClearBodyReport
    from ._document_primitives import IdSource
    from ._line_caches import TrackedCaches
    from .document_parts import HwpxOxmlDocument
    from .header import Style
    from .table import HwpxOxmlTable

_CLEAR_BODY_MODES = ("raise", "keep", "strip")
_CLEAR_BODY_KEPT_TAGS = frozenset({f"{_HP}secPr", f"{_HP}ctrl"})
_SECTION_STORY_TAGS = frozenset({f"{_HP}header", f"{_HP}footer"})
# breakSetting flags that belong to the paragraph they were set on, not to the
# paragraphs appended after it, with their ``ensure_paragraph_format`` keys.
_PAGE_FLOW_BREAK_FLAGS = {
    "pageBreakBefore": "page_break_before",
    "keepWithNext": "keep_with_next",
    "keepLines": "keep_lines",
}
# Reference attributes an apply element may carry (compared case-insensitively),
# the same set ``HwpxOxmlSectionProperties`` reads.
_APPLY_REFERENCE_ATTRIBUTES = frozenset(
    {"idref", "headeridref", "headerref", "footeridref", "footerref"}
)
# Descendants of the kept secPr/ctrl children that count as body content:
# tables, inline objects, form objects, and the compose/dutmal text atoms.
_CLEAR_BODY_CONTENT_NAMES = frozenset(
    INLINE_OBJECT_NAMES
    | {"tbl", "compose", "dutmal"}
    | {"btn", "radioBtn", "checkBtn", "comboBox", "listBox", "edit", "scrollBar"}
)


class HwpxOxmlSection:
    """Represents the contents of a section XML part."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
    ):
        self.part_name = part_name
        self._element = element
        self._dirty = False
        self._properties_cache: HwpxOxmlSectionProperties | None = None
        # an empty hp:secPr that properties gave a section without one, put in when written
        self._unattached_properties: ET.Element | None = None
        self._document = document
        # the header/footer copies that agree when opened, for the save to tell which copy an edit changed
        self._story_marks = story_marks(element)
        # the part as it was read, for the save to tell a line cache that outlived its paragraph's content
        self._tracked_caches: TrackedCaches | None = None

    def __copy__(self) -> "HwpxOxmlSection":
        """A shallow copy, as ``copy.copy`` makes one, with its own record of the line caches it watches.

        7.0 kept that record in attributes each judgement bound anew, so a shallow copy went on judging
        with the record of the moment it was made. The record is one object now: the copy gets its own
        copy of it, which a judgement of either section leaves as it is (a judgement binds new tables;
        it changes none it was given)."""

        twin = object.__new__(type(self))
        twin.__dict__.update(self.__dict__)
        if self._tracked_caches is not None:
            twin._tracked_caches = copy.copy(self._tracked_caches)
        return twin

    def __repr__(self) -> str:
        """Return a compact and safe summary of section structure."""

        return (
            f"{self.__class__.__name__}("
            f"part_name={self.part_name!r}, "
            f"paragraphs={len(self.paragraphs)}, "
            f"memos={len(self.memos)}"
            ")"
        )

    def _section_properties_element(self) -> ET.Element | None:
        return self._element.find(f".//{_HP}secPr")

    def _ensure_section_properties_element(self, element: ET.Element | None = None) -> ET.Element:
        """The section's ``hp:secPr``, put in its first run when it has none (*element*: the one to put)."""
        existing = self._section_properties_element()
        if existing is not None:
            return existing

        paragraph = _first_child_by_local(self._element, "p")
        if paragraph is None:
            paragraph_attrs = paragraph_attributes(_paragraph_id(self._ids))
            paragraph = _append_child(
                self._element,
                _child_tag_like(self._element, "p", _HP_NS),
                paragraph_attrs,
            )
        run = _first_child_by_local(paragraph, "run")
        if run is None:
            run = _append_child(
                paragraph,
                _child_tag_like(paragraph, "run", _HP_NS),
                {"charPrIDRef": "0"},
            )
        if element is None:
            element = _append_child(run, _child_tag_like(run, "secPr", _HP_NS))
            self._properties_cache = None
        else:
            run.append(element)
        self._unattached_properties = None
        self.mark_dirty()
        return element

    @property
    def properties(self) -> HwpxOxmlSectionProperties:
        """Return a wrapper exposing section-level options."""

        if self._properties_cache is None:
            element = self._section_properties_element()
            if element is None:
                # Reading changes nothing: a section with no hp:secPr reads as one with an empty
                # hp:secPr (every value None, as not written), and a write puts it in the section.
                element = self._element.makeelement(f"{_HP}secPr", {})
                self._unattached_properties = element
            self._properties_cache = HwpxOxmlSectionProperties(element, self)
        return self._properties_cache

    def _attach_written_properties(self) -> None:
        """Put the ``hp:secPr`` :attr:`properties` read as empty into the section once something is written to it."""

        element = self._unattached_properties
        if element is not None and (len(element) or element.attrib):
            self._ensure_section_properties_element(element)

    def _paragraph_elements(self) -> Iterable[ET.Element]:
        return _children_by_local(self._element, "p")

    @property
    def element(self) -> ET.Element:
        """Return the underlying XML element."""
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def _ids(self) -> "IdSource | None":
        """The id/clock source of this section's document (``None``: no ``seed=``/``now=``, or no document)."""

        return self._document._id_source if self._document is not None else None

    @property
    def paragraphs(self) -> tuple[HwpxOxmlParagraph, ...]:
        """The section's body paragraphs, in order."""
        return tuple(HwpxOxmlParagraph(elm, self) for elm in self._paragraph_elements())

    @property
    def blocks(self) -> "tuple[HwpxOxmlParagraph | HwpxOxmlTable, ...]":
        """The section's paragraphs and the tables placed right in the section, in file order.

        Hancom puts every table in a paragraph, so for its files this is :attr:`paragraphs`. Some
        other programs write a table (``hp:tbl``) as a child of the section itself; such a table
        comes here, where the file has it, as a table object whose ``paragraph`` is ``None``
        (read its text with ``hwpx.tools.exporter.table_grid_text(table)``, its caption with
        ``table.caption``). Other children of the section (``hp:memogroup``: :attr:`memo_group`) are
        not blocks.
        """

        from .._document.text_blocks import section_blocks

        return section_blocks(self)

    def _memo_group_element(self, create: bool = False) -> ET.Element | None:
        element = self._element.find(f"{_HP}memogroup")
        if element is None and create:
            element = _append_child(self._element, f"{_HP}memogroup", {})
            self.mark_dirty()
        return element

    @property
    def memo_group(self) -> HwpxOxmlMemoGroup | None:
        element = self._memo_group_element()
        if element is None:
            return None
        return HwpxOxmlMemoGroup(element, self)

    @property
    def memos(self) -> tuple[HwpxOxmlMemo, ...]:
        """The section's memos: those of its ``hp:memogroup``, then those kept only in a MEMO field
        (Hancom's own form, with the memo's text in the field's ``hp:subList``), in document order.
        A memo in both (python-hwpx anchors its memos with a field carrying the memo's id) counts once."""

        group = self.memo_group
        grouped = group.memos if group is not None else ()
        ids = {memo.id for memo in grouped if memo.id}
        kept_in_fields: list[HwpxOxmlMemo] = [
            HwpxOxmlFieldMemo(field, self)
            for field in self.element.iter(f"{_HP}fieldBegin")
            if field.get("type") == "MEMO" and field.find(f"{_HP}subList") is not None
            and memo_field_id(field) not in ids
        ]
        return (*grouped, *kept_in_fields)

    def add_memo(
        self,
        text: str = "",
        *,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> HwpxOxmlMemo:
        if text is not None:
            _require_text(text)  # not text: refused before anything is written
        element = self._memo_group_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create memo group element")
        group = HwpxOxmlMemoGroup(element, self)
        return group.add_memo(
            text,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    def remove_paragraph(
        self,
        paragraph: HwpxOxmlParagraph | int,
    ) -> None:
        """Remove *paragraph* from this section.

        Accepts either a :class:`HwpxOxmlParagraph` instance or an integer
        index into :attr:`paragraphs`.  Raises ``ValueError`` if the section
        would become empty (HWPX requires at least one ``<hp:p>``).
        """
        if isinstance(paragraph, int):
            paras = self.paragraphs
            if paragraph < 0 or paragraph >= len(paras):
                raise IndexError(f"단락 인덱스 {paragraph}이(가) 범위를 벗어났습니다 (총 {len(paras)}개)")
            paragraph = paras[paragraph]
        paragraph.remove()

    def clear_body(
        self, *, on_control_content: str = "raise", keep_headers: bool = True, keep_column_changes: bool = False
    ) -> ClearBodyReport:
        """Blank this section down to a template: keep its page setup, drop the body.

        What stays: the first paragraph (its attributes untouched), its first
        run with its ``hp:secPr`` (page setup), and the ``hp:ctrl`` children
        (columns, headers, footers, page numbering) of every run of the first
        paragraph -- Hancom often writes those controls in the second run;
        every non-paragraph child of the section (a memo group, for instance).
        What goes: every paragraph after the first, every other child of the
        first paragraph's runs (text, tables, pictures, shapes...), the runs
        after the first that hold no control, and the first paragraph's layout
        cache (``hp:linesegarray``). The images of removed pictures stay in
        the package until ``doc.media.remove_unused_images()`` drops them,
        and the parts of removed charts until ``doc.shapes.remove_unused_charts()``
        does; Hancom drops both when it saves.

        A kept ``hp:ctrl`` can hold content of its own, such as a header with
        a name in it. ``on_control_content`` says what to do when the kept
        children hold non-blank ``hp:t`` text, a table, picture, shape or other
        object, a form object, or ``hp:compose``/``hp:dutmal``:
        ``"raise"`` (default) refuses with
        ``HwpxValueError(code="section-clear-control-content")`` whose
        ``context["tags"]`` names the tags found; ``"keep"`` keeps them and
        reports the tags; ``"strip"`` removes each first-paragraph ``hp:ctrl`` whose
        subtree holds such content, and each ``hp:header``/``hp:footer`` story
        copy inside ``hp:secPr`` that holds content together with the
        ``hp:headerApply``/``hp:footerApply`` pointing at it (``set_header()``
        writes such copies; Hancom reads only the ``hp:ctrl`` story), and
        reports the tags. ``"strip"`` never leaves content behind: when content
        sits anywhere those removals do not reach (elsewhere in ``hp:secPr``,
        say), it refuses with ``section-clear-control-content`` instead.
        Deciding what to strip before a document is shared is the caller's
        policy; this call only reports and carries it out.

        Headers and footers belong to the section, so they stay by default.
        ``keep_headers=False`` removes them, with or without content: the
        ``hp:header``/``hp:footer`` controls of the first paragraph (a
        ``hp:ctrl`` holding nothing else goes whole) and the story copies in
        ``hp:secPr`` with the ``hp:headerApply``/``hp:footerApply`` naming them.
        The page setup, columns and page numbering stay, so what is left is
        the section's own settings and one empty line -- the shape of a new
        Hancom document, which has no header control. ``on_control_content``
        then judges only the controls that stay.

        The first run of the first paragraph must hold an ``hp:secPr``
        directly, or the call raises
        ``HwpxValueError(code="section-clear-no-section-properties")``. Every
        refusal happens before anything changes, so a failed call leaves the
        section as it was. Calling it again on a blank section changes nothing
        and does not mark the section dirty.

        ``keep_column_changes=True`` also keeps each later paragraph of the
        section that changes the columns (an ``hp:ctrl`` holding ``hp:colPr``,
        where Hancom writes a change of columns in the middle of a section): the
        paragraph itself, its id and attributes untouched, with only that control
        in its runs, as the first paragraph keeps its own. A template whose body
        changes from one column to two keeps that change. The default keeps none,
        as before.

        The images of removed pictures and the parts of removed charts stay in
        the package, pointed at by nothing (Hancom drops them when it saves);
        ``doc.media.remove_unused_images()`` and
        ``doc.shapes.remove_unused_charts()`` remove them.
        """

        from ..errors import HwpxValueError
        from ..objects.results import ClearBodyReport

        if on_control_content not in _CLEAR_BODY_MODES:
            raise HwpxValueError(
                f"on_control_content must be one of {', '.join(_CLEAR_BODY_MODES)}: "
                f"{on_control_content!r}",
                code="section-clear-mode-invalid",
                context={"value": on_control_content, "allowed": list(_CLEAR_BODY_MODES)},
            )

        for argument, value in (("keep_headers", keep_headers), ("keep_column_changes", keep_column_changes)):
            if not isinstance(value, bool):
                raise HwpxValueError(
                    f"{argument} must be True or False: {value!r}",
                    code="section-clear-mode-invalid",
                    context={"value": repr(value), "argument": argument},
                )

        paragraphs = self.paragraphs
        runs = paragraphs[0].runs if paragraphs else []
        if not runs or runs[0].element.find(f"{_HP}secPr") is None:
            raise HwpxValueError(
                "the first run of the section's first paragraph holds no hp:secPr",
                code="section-clear-no-section-properties",
                context={"part": self.part_name},
                suggestion="clear_body() keeps the page setup in the first run; "
                "this section has none there to keep.",
            )
        first = paragraphs[0]
        run_elements = [run.element for run in runs]

        header_removals = [] if keep_headers else _plan_header_removal(run_elements)
        found, removals = self._plan_control_content(
            run_elements, on_control_content, excluded=[child for _, child in header_removals]
        )
        removals = header_removals + [pair for pair in removals if not any(
            pair[1] is child for _, child in header_removals)]
        kept, column_removals = _plan_column_changes(
            paragraphs[1:], keep_column_changes, on_control_content, keep_headers, self.part_name, found
        )

        stripped_children = sum(_strip_to_kept_children(run) for run in run_elements)
        for parent, child in removals:
            parent.remove(child)
        # a later run is only kept for the controls it holds
        later_runs = [run for run in run_elements[1:] if len(run) == 0]
        for run in later_runs:
            first.element.remove(run)
        caches = first.element.findall(f"{_HP}linesegarray")
        for cache in caches:
            first.element.remove(cache)
        later_paragraphs = paragraphs[1:]
        _apply_column_changes(kept, column_removals)
        later_paragraphs = tuple(paragraph for paragraph in later_paragraphs
                                 if not any(paragraph.element is element for element in kept))
        for paragraph in later_paragraphs:
            self._element.remove(paragraph.element)
        if later_runs or stripped_children or removals or caches or later_paragraphs or kept:
            self.mark_dirty()
        return ClearBodyReport(
            kept_column_paragraphs=len(kept),
            removed_paragraphs=len(later_paragraphs),
            removed_runs=len(later_runs),
            stripped_run_children=stripped_children,
            control_content=tuple(found),
            stripped_controls=sum(1 for _, child in removals if child.tag == f"{_HP}ctrl")
            + sum(1 for _, child in column_removals if child.tag not in _SECTION_STORY_TAGS),
            stripped_section_stories=sum(
                1 for _, child in removals if child.tag in _SECTION_STORY_TAGS
            ),
        )

    def _plan_control_content(
        self, runs: Sequence[ET.Element], on_control_content: str, *, excluded: Sequence[ET.Element] = (),
        paragraph: int | None = 0,
    ) -> tuple[list[str], list[tuple[ET.Element, ET.Element]]]:
        """Scan the kept children (but *excluded*, which go anyway) and plan the ``"strip"``
        removals, or refuse.

        Refuses (before anything changes) when content is found under
        ``"raise"``, or when content would remain after the ``"strip"`` plan.
        """

        from ..errors import HwpxValueError

        found = _clear_body_kept_content(runs, excluded=excluded)
        if not found or on_control_content == "keep":
            return found, []
        removals = _plan_control_strip(runs) if on_control_content == "strip" else []
        remaining = _clear_body_kept_content(runs, excluded=[*excluded, *(child for _, child in removals)])
        if not remaining:
            return found, removals
        if on_control_content == "raise":
            message = "the kept section controls hold content (a header or footer, perhaps): "
            suggestion = (
                'pass on_control_content="strip" to remove those controls, or "keep" to keep them.'
            )
        else:
            message = "stripping the section controls would still leave content behind: "
            suggestion = 'remove that content first, or pass on_control_content="keep".'
        raise HwpxValueError(
            message + ", ".join(remaining),
            code="section-clear-control-content",
            context={"part": self.part_name, "tags": remaining, "mode": on_control_content,
                     "paragraph": paragraph, "paragraphs": [{"paragraph": paragraph, "tags": remaining}]},
            suggestion=suggestion,
        )

    def _inherited_paragraph_refs(
        self,
        *,
        inherit_outline: bool = True,
    ) -> tuple[str | None, str | None, str | None]:
        """Style refs the next appended paragraph inherits from the last one.

        A list paragraph (bullet/numbered paraPr) must not leak into the next
        paragraph — in Hancom, Enter continues the list but programmatic
        appends of ordinary text are body text. The fidelity audit reproduced
        every following paragraph turning into a list item without this guard.

        With *inherit_outline* false an outline paragraph (a heading) is held
        back the same way: body text added after a heading took the heading's
        shape and style, and Hancom numbered it as the next heading.
        """

        # Only the last paragraph is read: wrapping every paragraph of the section for each append
        # made a long run of appends quadratic.
        last_element = next(
            (child for child in reversed(self._element) if tag_local_name(child.tag) == "p"), None
        )
        if last_element is None:
            return None, None, None
        last = HwpxOxmlParagraph(last_element, self)
        prev_para_ref = last.para_pr_id_ref
        prev_style_ref = last.style_id_ref
        prev_char_ref = last.char_pr_id_ref
        if prev_para_ref is not None and (
            self._para_pr_is_list(prev_para_ref)
            or (not inherit_outline and self._para_pr_heading_type(prev_para_ref) == "OUTLINE")
        ):
            prev_para_ref = None
            prev_style_ref = None
        if prev_para_ref is not None:
            prev_para_ref = self._without_page_flow_breaks(prev_para_ref)
        return prev_para_ref, prev_style_ref, prev_char_ref

    def _header_shapes(self) -> tuple[frozenset[str], dict[str, float]]:
        """What the stale-cache sweep reads from the headers: squeezed paragraph shapes, narrowed character shapes."""

        return self._squeezed_paragraph_shapes(), self._narrowed_char_shapes()

    def _squeezed_paragraph_shapes(self) -> frozenset[str]:
        """The paragraph shapes Hancom presses onto one line: a cache of one line holds all of their text."""

        from ..tools.package_validator import squeezed_paragraph_shapes

        document = self.document
        return frozenset().union(*(
            squeezed_paragraph_shapes(getattr(header, "element", None)) for header in getattr(document, "_headers", [])
        )) if document is not None else frozenset()

    def _narrowed_char_shapes(self) -> dict[str, float]:
        """The character shapes whose glyphs Hancom lays out narrower than their size (상대 크기, 장평), by id."""

        from ..tools.package_validator import narrowed_char_shapes

        document = self.document
        shares: dict[str, float] = {}
        for header in getattr(document, "_headers", []) if document is not None else []:
            shares.update(narrowed_char_shapes(getattr(header, "element", None)))
        return shares

    def _para_pr_element(self, para_pr_id_ref: str | int) -> tuple[Any, ET.Element] | None:
        """The header holding the paraPr *para_pr_id_ref*, and the paraPr."""

        document = self.document
        if document is None:
            return None
        wanted = str(para_pr_id_ref)
        for header in getattr(document, "_headers", []):
            para_properties = getattr(header, "_para_properties_element", None)
            if para_properties is None:
                continue
            container = para_properties()
            if container is None:
                continue
            for para_pr in container:
                if para_pr.get("id") == wanted:
                    return header, para_pr
        return None

    def _para_pr_heading_type(self, para_pr_id_ref: str | int) -> str:
        """The paraPr's ``hh:heading`` type in upper case, ``""`` when it has none."""

        found = self._para_pr_element(para_pr_id_ref)
        if found is None:
            return ""
        for child in found[1]:
            if tag_local_name(child.tag) == "heading":
                return str(child.get("type", "")).upper()
        return ""

    def _para_pr_is_list(self, para_pr_id_ref: str | int) -> bool:
        """True when the paraPr carries a bullet/numbered heading."""

        return self._para_pr_heading_type(para_pr_id_ref) in {"BULLET", "NUMBER"}

    def _without_page_flow_breaks(self, para_pr_id_ref: str) -> str:
        """*para_pr_id_ref*, or the same paragraph shape without its page-flow
        settings when it has any.

        A page break before, keep with next and keep lines belong to the
        paragraph they were set on. Inherited, one ``page_break_before`` would
        start every following paragraph on a page of its own.
        """

        found = self._para_pr_element(para_pr_id_ref)
        if found is None:
            return para_pr_id_ref
        header, para_pr = found
        flags = {
            attr: key
            for child in para_pr
            if tag_local_name(child.tag) == "breakSetting"
            for attr, key in _PAGE_FLOW_BREAK_FLAGS.items()
            if str(child.get(attr, "0")).lower() in {"1", "true"}
        }
        if not flags:
            return para_pr_id_ref
        return header.ensure_paragraph_format(
            base_para_pr_id=para_pr_id_ref,
            break_setting={key: False for key in flags.values()},
        )

    @rejects_removed_arguments
    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        char_pr_id_ref: str | int | None = None,
        include_run: bool = True,
        inherit_style: bool = True,
    ) -> HwpxOxmlParagraph:
        """Append a paragraph to this section and return it.

        When *inherit_style* is ``True`` (the default) and no explicit
        ``paraPrIDRef``, ``styleIDRef`` or ``charPrIDRef`` is given, the
        values are inherited from the **last** paragraph in the section so
        that consecutive paragraphs share the same formatting.

        ``style`` (a name, a numeric id or a ``Style``) also gives the
        paragraph that style's paragraph and character shapes unless they are
        passed, as Hancom does when it applies a style; ``para_pr_id_ref`` and
        ``char_pr_id_ref`` name the shapes directly. With *include_run* false
        the paragraph gets no run (a paragraph made to hold an object). Anything
        else is a property of the returned paragraph (``p.page_break = True``):
        7.0 took away ``run_attributes=``, ``inherit_outline=`` and the keyword
        arguments written as raw XML attributes, and a call that still passes one
        is told so. (7.0 also removed ``style_id_ref=``, which set the style
        reference alone; ``paragraph.style_id_ref = 2`` still does that.)
        """

        return self._add_paragraph(
            text,
            para_pr_id_ref=para_pr_id_ref,
            style=style,
            char_pr_id_ref=char_pr_id_ref,
            include_run=include_run,
            inherit_style=inherit_style,
        )

    def _add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style: "int | str | Style | None" = None,
        char_pr_id_ref: str | int | None = None,
        include_run: bool = True,
        inherit_style: bool = True,
        inherit_outline: bool = True,
        run_attributes: Mapping[str, str] | None = None,
        xml_attributes: Mapping[str, str] | None = None,
    ) -> HwpxOxmlParagraph:
        """:meth:`add_paragraph`, plus what the document layer still needs: *inherit_outline*
        false holds back the paragraph and style references of an outline paragraph (a
        heading) the way a list paragraph's are, *run_attributes* are raw ``hp:run``
        attributes and *xml_attributes* raw ``hp:p`` attributes (the low-level escape
        hatches ``doc.shapes.add_raw``/``add_control`` take)."""

        extra_attrs = dict(xml_attributes or {})
        style_id_ref, para_pr_id_ref, char_pr_id_ref = style_shape_refs(
            self.document,
            style,
            para_pr_id_ref,
            char_pr_id_ref,
            run_attributes,
            extra_attrs,
        )

        # Collect style refs from the last paragraph for inheritance.
        prev_para_ref, prev_style_ref, prev_char_ref = (
            self._inherited_paragraph_refs(inherit_outline=inherit_outline) if inherit_style else (None, None, None)
        )

        attrs = paragraph_attributes(_paragraph_id(self._ids))
        attrs.update(extra_attrs)

        if para_pr_id_ref is not None:
            attrs["paraPrIDRef"] = str(para_pr_id_ref)
        elif prev_para_ref is not None:
            attrs["paraPrIDRef"] = prev_para_ref
        if style_id_ref is not None:
            attrs["styleIDRef"] = str(style_id_ref)
        elif prev_style_ref is not None:
            attrs["styleIDRef"] = prev_style_ref

        paragraph = self._element.makeelement(f"{_HP}p", attrs)

        if include_run:
            run_attrs = dict(run_attributes or {})
            if char_pr_id_ref is not None:
                run_attrs["charPrIDRef"] = str(char_pr_id_ref)
            elif "charPrIDRef" not in run_attrs:
                if prev_char_ref is not None:
                    run_attrs["charPrIDRef"] = prev_char_ref
                else:
                    run_attrs["charPrIDRef"] = "0"

            run = paragraph.makeelement(f"{_HP}run", run_attrs)
            paragraph.append(run)
            _append_text_with_tabs(run, text)

        self._element.append(paragraph)
        self._dirty = True
        return HwpxOxmlParagraph(paragraph, self)

    def insert_paragraphs(
        self,
        index: int,
        paragraphs: Sequence[HwpxOxmlParagraph | ET.Element],
    ) -> tuple[HwpxOxmlParagraph, ...]:
        """Insert copies of *paragraphs* at *index* and return the inserted paragraphs.

        The copies come without section settings (``hp:secPr`` and the columns, header, footer and
        page numbering that go with it), as :meth:`HwpxOxmlParagraph.insert_after` copies: the
        section keeps its own. At index 0 the copies start the section, so its settings move from the
        paragraph that held them to the front of the first copy. Hancom reads a section's settings
        only from its first paragraph: with them in a later one, it saves the section with default
        paper and margins (``section-properties-not-first``).
        """

        from ._paragraph_text_edit import move_section_settings, renumber_copied_fields, section_setting_runs

        existing = self.paragraphs
        if index < 0 or index > len(existing):
            raise IndexError(f"단락 인덱스 {index}이(가) 범위를 벗어났습니다 (총 {len(existing)}개)")

        inserted: list[HwpxOxmlParagraph] = []
        clones = self._element.makeelement(f"{_HP}subList", {})  # holds the copies until they are numbered
        for paragraph in paragraphs:
            source_element = paragraph.element if isinstance(paragraph, HwpxOxmlParagraph) else paragraph
            cloned = _clone_paragraph_element(source_element, ids=self._ids)
            # the section's settings (its headers among them) stay with the paragraph they came from.
            # They go before the fields are numbered: a field in a header that is not taken in is no
            # field of the copies, and neither renews another's id nor is kept clear of
            for run, settings in section_setting_runs(cloned):
                for child in settings:
                    run.remove(child)
                if len(run) == 0:
                    cloned.remove(run)
            clones.append(cloned)
        # as paragraph.copy_to and insert_after(): a copied field gets its own id pair (the copy kept the
        # original's, and neither field could be filled by name or id: ``field-ambiguous``). The copies
        # are numbered together: a field may begin in one paragraph and end in a later one. A field whose
        # id no field of the document has keeps it: paragraphs brought from another document are filled
        # by the ids they came with.
        if next(clones.iter(f"{_HP}fieldBegin"), None) is not None:  # no field in the copies: no search
            document = self.document
            owners: list[Any] = ([*document.sections, *getattr(document, "master_pages", ())]
                                 if document is not None else [self])
            taken = {str(node.get("id")) for owner in owners for node in owner.element.iter(f"{_HP}fieldBegin")}
            renumber_copied_fields(clones, ids=self._ids, taken=taken)
            keep_ids_clear_of(self._ids, (node.get("id") for node in clones.iter(f"{_HP}fieldBegin")))
        for offset, cloned in enumerate(list(clones)):
            self._element.insert(index + offset, cloned)
            inserted.append(HwpxOxmlParagraph(cloned, self))

        if inserted:
            if index == 0 and existing:
                move_section_settings(existing[0].element, inserted[0].element)
            from .shape_position import unique_object_ids

            unique_object_ids(self, [paragraph.element for paragraph in inserted])
            from .note_authoring import renumber_notes_holding

            renumber_notes_holding(self, [paragraph.element for paragraph in inserted])
            self._dirty = True
        return tuple(inserted)

    def copy_paragraph_range(self, start: int, end: int) -> tuple[ET.Element, ...]:
        """Deep copies of the paragraph elements *start* to *end* (both included)."""

        paragraphs = self.paragraphs
        total = len(paragraphs)
        if start < 0 or end < 0 or start >= total or end >= total or start > end:
            raise IndexError(f"문단 범위 {start}..{end}이(가) 유효하지 않습니다 (총 {total}개)")
        return tuple(_clone_paragraph_element(paragraphs[index].element, ids=self._ids) for index in range(start, end + 1))

    def mark_dirty(self) -> None:
        self._dirty = True
        if self._unattached_properties is not None:
            self._attach_written_properties()

    @property
    def dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def clear_layout_cache(self, *, stale_only: bool = False) -> int:
        """Remove the line layout caches (``hp:linesegarray``) of this section and return how many.

        Every paragraph of the section counts: body, table cells, text boxes,
        captions, headers, footers and notes. Hancom lays a paragraph without a
        cache out again when it opens the file, so removing a cache never draws
        text over itself; a cache left on text that changed does. The public
        editing calls already remove the caches of what they change; call this
        after changing the XML yourself.

        ``stale_only=True`` removes only the caches that cannot match their
        paragraph (what every save does anyway): a cached line starting past the
        text, a cache too short for the text, or, in an edited section, a cache
        the part was read with on a paragraph whose content changed since.
        """

        if stale_only:
            return self.remove_stale_layout_caches()
        removed = 0
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            for child in [c for c in paragraph if _element_local_name(c).lower() == "linesegarray"]:
                paragraph.remove(child)
                removed += 1
        if removed:
            self.mark_dirty()
        return removed

    def remove_stale_layout_caches(
        self, *, _header_shapes: tuple[frozenset[str], dict[str, float]] | None = None
    ) -> int:
        """Drop paragraph layout caches that cannot match the paragraph's text.

        A cache is stale when a cached line starts past the plain text, or when
        the text after the last cached line start is far wider than that line
        (the cache lacks lines, so Hancom would draw the tail over itself). The
        save path runs this on every section, so a document whose own caches
        look like that still saves; Hancom lays those paragraphs out again.

        In a section that was edited, a cache the part was read with goes as
        well when its paragraph no longer has the content it came with,
        whatever its lines look like: the edit that changed the paragraph left
        it behind, and Hancom would press the new text into the old line
        count. A cache on unchanged content, and one written since the part
        was read, stays.
        """

        removed = self._remove_outlived_layout_caches()
        # Both come from the document's headers alone, so a save that sweeps
        # every section reads them once and hands them in.
        squeezed, narrowed = _header_shapes or self._header_shapes()
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            if _remove_stale_paragraph_layout_cache(paragraph) or (
                paragraph.get("paraPrIDRef") not in squeezed
                and _remove_short_paragraph_layout_cache(paragraph, narrowed)
            ):
                removed += 1
        if removed:
            self.mark_dirty()
        return removed

    def _remove_outlived_layout_caches(self, *, force: bool = False, rebuilding: Any = None) -> int:
        """Drop the caches an edit left on a paragraph whose content it changed.

        *force* judges them even when the section is not marked edited: an edit about to
        rebuild elements (a table's structure edit) runs it first, because a rebuilt
        paragraph no longer matches the cache it was read with by identity, and then once
        more after, so the rebuilt caches are tracked from there. Both judge every cache of
        the section. Such an edit names its table the first time (*rebuilding*), which
        changes no answer (:meth:`._line_caches.TrackedCaches.judge_all`).
        """

        tracked = self._tracked_caches
        if tracked is None or (not self._dirty and not force):
            return 0
        return tracked.judge_all(self._element, about_to_rebuild=rebuilding)

    def _remember_source(self, source_xml: bytes) -> None:
        """Note the part's bytes and its line caches as read, before anything edits the tree.

        The save uses them to tell a cache that an edit left on a paragraph whose
        content it changed (see :mod:`._line_caches`).
        """

        if not hasattr(self._element, "getparent"):  # lxml trees only
            return
        from ._line_caches import TrackedCaches, cache_elements

        self._tracked_caches = TrackedCaches(cache_elements(self._element), source_xml)

    def remove_layout_caches(self) -> int:
        """Drop all paragraph layout caches from this section.

        Layout cache is editor-derived metadata. Once a section has been
        modified, preserving it is riskier than allowing the editor to
        recalculate it on open.
        """

        removed = 0
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            removed += _clear_paragraph_layout_cache(paragraph)
        if removed:
            self.mark_dirty()
        return removed

    def to_bytes(self) -> bytes:
        self._attach_written_properties()
        return _serialize_xml(self._element)


def _column_controls(paragraph: ET.Element) -> list[ET.Element]:
    """The ``hp:ctrl`` children of *paragraph*'s runs that hold a column definition (``hp:colPr``)."""

    return [child for run in paragraph if run.tag == f"{_HP}run" for child in run
            if child.tag == f"{_HP}ctrl" and child.find(f"{_HP}colPr") is not None]


def _plan_column_changes(
    later: Sequence[Any], wanted: bool, mode: str, keep_headers: bool, part_name: str, found_before: list[str]
) -> tuple[list[ET.Element], list[tuple[ET.Element, ET.Element]]]:
    """:func:`_find_column_changes` for ``clear_body``: the later paragraph objects *later* when *wanted*, the
    content found added to *found_before*."""

    kept, found, removals = _find_column_changes(
        [paragraph.element for paragraph in later] if wanted else [], mode, keep_headers, part_name
    )
    found_before += [tag for tag in found if tag not in found_before]
    return kept, removals


def _apply_column_changes(kept: list[ET.Element], removals: list[tuple[ET.Element, ET.Element]]) -> None:
    for parent, child in removals:
        parent.remove(child)
    for element in kept:
        _strip_to_column_controls(element)


def _find_column_changes(
    paragraphs: Sequence[ET.Element], mode: str, keep_headers: bool, part_name: str
) -> tuple[list[ET.Element], list[str], list[tuple[ET.Element, ET.Element]]]:
    """``clear_body(keep_column_changes=True)``'s plan, made before anything changes: the later paragraphs that
    change the columns (kept), the content tags found beside the column definition in their controls, and the
    ``(control, child)`` pairs to remove -- a header or footer when not *keep_headers*, and under ``"strip"`` each
    child holding content. ``"raise"`` refuses such content (``section-clear-control-content``) as it does in the
    first paragraph; nothing in those controls goes silently."""

    from ..errors import HwpxValueError

    kept: list[ET.Element] = []
    found: list[str] = []
    removals: list[tuple[ET.Element, ET.Element]] = []
    held: list[dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs, start=1):  # the section's paragraphs after its first
        controls = _column_controls(paragraph)
        if not controls:
            continue
        kept.append(paragraph)
        for control in controls:
            for child in control:
                if child.tag == f"{_HP}colPr":
                    continue
                if not keep_headers and child.tag in _SECTION_STORY_TAGS:
                    removals.append((control, child))
                    continue
                tags: list[str] = []
                _collect_content_tags(child, tags, ())
                found += [tag for tag in tags if tag not in found]
                if tags:
                    held.append({"paragraph": index, "tags": tags})
                if tags and mode == "strip":
                    removals.append((control, child))
    if found and mode == "raise":
        raise HwpxValueError(
            "a column change kept in the section holds content beside its column definition: " + ", ".join(found),
            code="section-clear-control-content",
            context={"part": part_name, "tags": found, "mode": mode, "paragraph": held[0]["paragraph"],
                     "paragraphs": held},
            suggestion='pass on_control_content="strip" to remove it, or "keep" to keep it.',
        )
    return kept, found, removals


def clear_paragraph_content(paragraph: Any, *, keep_headers: bool, on_control_content: str) -> Any:
    """``paragraph.clear_content``: empty *paragraph* of its body content, keeping its section settings.

    What stays: ``hp:secPr`` and the controls holding only page-level settings beside it -- the column
    definition always (Hancom opens a section without it with default paper and margins), headers and footers
    as *keep_headers* says, page numbering, hiding and new numbers -- by the rule ``clear_body`` keeps the first
    paragraph's. Content inside what stays (a header's text, say) follows *on_control_content* as there:
    ``"raise"`` refuses (``section-clear-control-content``), ``"keep"`` keeps it, ``"strip"`` removes it and
    reports it. Everything else goes: text, tables, pictures, notes, bookmarks, fields. A paragraph left with
    no ``hp:t`` gets one run holding ``<hp:t/>`` after its settings, Hancom's empty line."""

    from ..errors import HwpxValueError
    from ..objects.results import ClearBodyReport
    from ._paragraph_text_edit import is_section_setting, section_setting_runs, split_column_controls

    if on_control_content not in _CLEAR_BODY_MODES:
        raise HwpxValueError(
            f"on_control_content must be one of {', '.join(_CLEAR_BODY_MODES)}: {on_control_content!r}",
            code="section-clear-mode-invalid",
            context={"value": on_control_content, "allowed": list(_CLEAR_BODY_MODES)},
        )
    if not isinstance(keep_headers, bool):
        raise HwpxValueError(f"keep_headers must be True or False: {keep_headers!r}", code="section-clear-mode-invalid",
                             context={"value": repr(keep_headers), "argument": "keep_headers"})
    element = paragraph.element
    runs = [child for child in element if child.tag == f"{_HP}run"]
    if section_setting_runs(element):
        # A column layout sharing its ctrl with a field begin or another control stays, as a setting.
        split_column_controls(element)
    kept = [child for run in runs for child in run if is_section_setting(child)]
    dropped = [child for run in runs for child in run if not any(child is node for node in kept)]
    header_removals = [] if keep_headers else _plan_header_removal(runs)
    excluded = [child for _, child in header_removals] + [child for child in dropped if child.tag == f"{_HP}ctrl"]
    siblings = [child for child in element.getparent()] if element.getparent() is not None else []
    place = next((index for index, node in enumerate(n for n in siblings if n.tag == element.tag)
                  if node is element), None)
    found, removals = paragraph.section._plan_control_content(runs, on_control_content, excluded=excluded,
                                                             paragraph=place)
    removals = header_removals + [pair for pair in removals if any(pair[1] is node for node in kept)
                                  and not any(pair[1] is child for _, child in header_removals)]
    first_attributes = dict(runs[0].attrib) if runs else {"charPrIDRef": "0"}
    text_attributes = next((dict(run.attrib) for run in runs for child in run if child.tag == f"{_HP}t"),
                           first_attributes)
    # The notes (and the number restarts) that go with the content: the notes left are numbered again, as
    # after paragraph.remove(). They kept the numbers they had, so the file said 2 for the note read as 1.
    from .note_authoring import note_kinds_in_all, renumber_note_kinds

    note_kinds = note_kinds_in_all(paragraph.section, [*dropped, *(child for _, child in removals)])
    for child in dropped:
        child.getparent().remove(child)
    for parent, child in removals:
        parent.remove(child)
    renumber_note_kinds(paragraph.section, note_kinds)
    emptied = [run for run in runs if len(run) == 0]
    for run in emptied:
        element.remove(run)
    if element.find(f"{_HP}run/{_HP}t") is None:
        run = element.makeelement(f"{_HP}run", text_attributes)
        run.append(run.makeelement(f"{_HP}t", {}))
        others = [child for child in element if child.tag == f"{_HP}run"]
        element.insert(list(element).index(others[-1]) + 1 if others else 0, run)
    for cache in element.findall(f"{_HP}linesegarray"):
        element.remove(cache)
    if dropped or removals or emptied:
        paragraph.section.mark_dirty()
    return ClearBodyReport(
        removed_paragraphs=0,
        removed_runs=len(emptied),
        stripped_run_children=len(dropped),
        control_content=tuple(found),
        stripped_controls=sum(1 for _, child in removals if child.tag == f"{_HP}ctrl"),
        stripped_section_stories=sum(1 for _, child in removals if child.tag in _SECTION_STORY_TAGS),
    )


def _strip_to_column_controls(paragraph: ET.Element) -> None:
    """Leave in *paragraph* only its controls holding a column definition, whole; runs left empty and the
    line layout cache go."""

    controls = _column_controls(paragraph)
    for run in [child for child in paragraph if child.tag == f"{_HP}run"]:
        for child in list(run):
            if not any(child is control for control in controls):
                run.remove(child)
        if len(run) == 0:
            paragraph.remove(run)
    for cache in paragraph.findall(f"{_HP}linesegarray"):
        paragraph.remove(cache)


def _strip_to_kept_children(run: ET.Element) -> int:
    """Remove every child of *run* but ``hp:secPr``/``hp:ctrl``; return the count."""

    removed = [child for child in run if child.tag not in _CLEAR_BODY_KEPT_TAGS]
    for child in removed:
        run.remove(child)
    return len(removed)


def _clear_body_kept_content(
    runs: Sequence[ET.Element], *, excluded: Sequence[ET.Element]
) -> list[str]:
    """Content tags inside the kept secPr/ctrl children, skipping *excluded* subtrees."""

    found: list[str] = []
    for run in runs:
        for child in run:
            if child.tag in _CLEAR_BODY_KEPT_TAGS:
                _collect_content_tags(child, found, excluded)
    return found


def _collect_content_tags(
    element: ET.Element, found: list[str], excluded: Sequence[ET.Element]
) -> None:
    """Append ``hp:<name>`` tags of body content under *element*, first-seen order.

    A ``hp:t`` counts when its text is not blank -- its own text or the text
    after a child element in it, as in ``<hp:t><hp:tab/>name</hp:t>``; any element named in
    ``_CLEAR_BODY_CONTENT_NAMES`` counts as it is.
    """

    stack = [element]
    while stack:
        node = stack.pop()
        if any(node is skip for skip in excluded):
            continue
        name = _element_local_name(node)
        if name == "t":
            holds = bool((node.text or "").strip()) or any((child.tail or "").strip() for child in node)
        else:
            holds = name in _CLEAR_BODY_CONTENT_NAMES
        if holds and f"hp:{name}" not in found:
            found.append(f"hp:{name}")
        stack.extend(reversed(list(node)))


def _holds_content(element: ET.Element) -> bool:
    found: list[str] = []
    _collect_content_tags(element, found, ())
    return bool(found)


def _plan_control_strip(runs: Sequence[ET.Element]) -> list[tuple[ET.Element, ET.Element]]:
    """``(parent, child)`` pairs ``"strip"`` removes from the first paragraph's runs.

    The runs' ``hp:ctrl`` children that hold content, and, inside the
    ``hp:secPr``, the ``hp:header``/``hp:footer`` story copies that hold
    content together with the ``hp:headerApply``/``hp:footerApply`` that
    point at them by id. Those copies are not OWPML ``hp:secPr`` children;
    ``set_header()``/``set_footer()`` write them, and Hancom reads only the
    ``hp:ctrl`` story.
    """

    removals: list[tuple[ET.Element, ET.Element]] = []
    for run in runs:
        for child in run:
            if child.tag == f"{_HP}ctrl" and _holds_content(child):
                removals.append((run, child))
            elif child.tag == f"{_HP}secPr":
                removals.extend(_plan_section_story_strip(child))
    return removals


def _plan_header_removal(runs: Sequence[ET.Element]) -> list[tuple[ET.Element, ET.Element]]:
    """``(parent, child)`` pairs ``keep_headers=False`` removes: every header and footer of the first
    paragraph's runs (a ``hp:ctrl`` holding only them goes whole) and the story copies in
    ``hp:secPr`` with the applies naming them, content or not."""

    removals: list[tuple[ET.Element, ET.Element]] = []
    for run in runs:
        for child in run:
            if child.tag == f"{_HP}ctrl":
                stories = [node for node in child if node.tag in _SECTION_STORY_TAGS]
                if stories and len(stories) == len(child):
                    removals.append((run, child))
                else:
                    removals.extend((child, story) for story in stories)
            elif child.tag == f"{_HP}secPr":
                removals.extend(_plan_section_story_strip(child, content_only=False))
    return removals


def _plan_section_story_strip(
    section_properties: ET.Element, *, content_only: bool = True
) -> list[tuple[ET.Element, ET.Element]]:
    removals: list[tuple[ET.Element, ET.Element]] = []
    for story in section_properties:
        if story.tag not in _SECTION_STORY_TAGS or (content_only and not _holds_content(story)):
            continue
        removals.append((section_properties, story))
        story_id = story.get("id")
        apply_tag = f"{story.tag}Apply"
        for apply in section_properties:
            if apply.tag == apply_tag and story_id and _apply_reference(apply) == story_id:
                removals.append((section_properties, apply))
    return removals


def _apply_reference(apply: ET.Element) -> str | None:
    """The story id an ``hp:headerApply``/``hp:footerApply`` points at."""

    for attr, value in apply.attrib.items():
        if attr.lower() in _APPLY_REFERENCE_ATTRIBUTES and value:
            return value
    return None


def _remove_short_paragraph_layout_cache(paragraph: ET.Element, narrowed: Mapping[str, float] | None = None) -> bool:
    """Clear a plain paragraph's cache whose lines cannot hold its text.

    Uses the editor-open-safety rule itself
    (``package_validator._check_line_seg_tail_coverage``), so the save-time
    sweep removes exactly the caches that check would refuse.
    """

    from ..tools.package_validator import (
        PackageValidationIssue,
        _check_line_seg_tail_coverage,
        _simple_paragraph_text,
        paragraph_narrowest,
    )

    text = _simple_paragraph_text(paragraph)
    if text is None:
        return False
    for child in paragraph:
        if _element_local_name(child).lower() != "linesegarray":
            continue
        line_segs = [seg for seg in child if _element_local_name(seg).lower() == "lineseg"]
        findings: list[PackageValidationIssue] = []
        _check_line_seg_tail_coverage(findings, "", 0, text, line_segs, paragraph_narrowest(paragraph, narrowed or {}))
        if findings:
            _clear_paragraph_layout_cache(paragraph)
            return True
    return False


def style_shape_refs(
    document: "HwpxOxmlDocument | None",
    style: "int | str | Style | None",
    para_pr_id_ref: str | int | None,
    char_pr_id_ref: str | int | None,
    run_attributes: Mapping[str, str] | None = None,
    paragraph_attributes: Mapping[str, str] | None = None,
) -> tuple[str | int | None, str | int | None, str | int | None]:
    """``(styleIDRef, paraPrIDRef, charPrIDRef)`` for a paragraph made with *style*: the
    style's id, and its paragraph and character shapes where none were given (a
    ``charPrIDRef`` in *run_attributes*, a ``paraPrIDRef`` in *paragraph_attributes*
    counts as given). No *style*: no reference."""

    if style is None:
        return None, para_pr_id_ref, char_pr_id_ref
    if document is not None:
        from .formatting import resolve_style

        resolved = resolve_style(document, style)
    elif isinstance(style, (int, str)):
        from ..errors import HwpxLookupError

        raise HwpxLookupError(
            f"스타일 {style!r} 을(를) 찾을 수 없습니다: 구역이 문서에 붙어 있지 않아 스타일 목록이 없습니다.",
            code="style-not-found",
            context={"requested": style, "available": [], "availableCount": 0},
            suggestion="문서의 구역에서 부르거나 Style 객체를 주세요.",
        )
    else:
        resolved = style
    style_id = resolved.id if resolved.id is not None else resolved.raw_id
    if para_pr_id_ref is None and "paraPrIDRef" not in (paragraph_attributes or {}):
        para_pr_id_ref = resolved.para_pr_id_ref
    if char_pr_id_ref is None and "charPrIDRef" not in (run_attributes or {}):
        char_pr_id_ref = resolved.char_pr_id_ref
    return style_id, para_pr_id_ref, char_pr_id_ref


__all__ = ["HwpxOxmlSection", "HwpxOxmlSectionHeaderFooter", "HwpxOxmlSectionProperties"]
