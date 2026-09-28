# SPDX-License-Identifier: Apache-2.0
"""Section body, layout-cache, memo, and composition OXML service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
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
from .body import INLINE_OBJECT_NAMES
from .memo import HwpxOxmlMemo, HwpxOxmlMemoGroup
from .paragraph import HwpxOxmlParagraph
from .section_format import HwpxOxmlSectionProperties
from .namespaces import tag_local_name
from .section_story import HwpxOxmlSectionHeaderFooter, story_marks

if TYPE_CHECKING:
    from ..objects.results import ClearBodyReport
    from .document_parts import HwpxOxmlDocument

_CLEAR_BODY_MODES = ("raise", "keep", "strip")
_CLEAR_BODY_KEPT_TAGS = frozenset({f"{_HP}secPr", f"{_HP}ctrl"})
_SECTION_STORY_TAGS = frozenset({f"{_HP}header", f"{_HP}footer"})
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
        self._document = document
        # the header/footer copies that agree when opened, for the save to tell which copy an edit changed
        self._story_marks = story_marks(element)

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

    def _ensure_section_properties_element(self) -> ET.Element:
        element = self._section_properties_element()
        if element is not None:
            return element

        paragraph = _first_child_by_local(self._element, "p")
        if paragraph is None:
            paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
            paragraph_attrs["id"] = _paragraph_id()
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
        element = _append_child(run, _child_tag_like(run, "secPr", _HP_NS))
        self._properties_cache = None
        self.mark_dirty()
        return element

    @property
    def properties(self) -> HwpxOxmlSectionProperties:
        """Return a wrapper exposing section-level options."""

        if self._properties_cache is None:
            element = self._section_properties_element()
            if element is None:
                element = self._ensure_section_properties_element()
            self._properties_cache = HwpxOxmlSectionProperties(element, self)
        return self._properties_cache

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
    def paragraphs(self) -> list[HwpxOxmlParagraph]:
        """Return the paragraphs defined in this section."""
        return [HwpxOxmlParagraph(elm, self) for elm in self._paragraph_elements()]

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
    def memos(self) -> list[HwpxOxmlMemo]:
        group = self.memo_group
        if group is None:
            return []
        return group.memos

    def add_memo(
        self,
        text: str = "",
        *,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: Optional[dict[str, str]] = None,
    ) -> HwpxOxmlMemo:
        element = self._memo_group_element(create=True)
        if element is None:  # pragma: no cover - defensive branch
            raise RuntimeError("failed to create memo group element")
        group = HwpxOxmlMemoGroup(element, self)
        return group.add_memo(
            text,
            memo_shape_id_ref=memo_shape_id_ref,
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

    def clear_body(self, *, on_control_content: str = "raise") -> ClearBodyReport:
        """Blank this section down to a template: keep its page setup, drop the body.

        What stays: the first paragraph (its attributes untouched), its first
        run with its ``hp:secPr`` (page setup), and the ``hp:ctrl`` children
        (columns, headers, footers, page numbering) of every run of the first
        paragraph -- Hancom often writes those controls in the second run;
        every non-paragraph child of the section (a memo group, for instance).
        What goes: every paragraph after the first, every other child of the
        first paragraph's runs (text, tables, pictures, shapes...), the runs
        after the first that hold no control, and the first paragraph's layout
        cache (``hp:linesegarray``).

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

        The first run of the first paragraph must hold an ``hp:secPr``
        directly, or the call raises
        ``HwpxValueError(code="section-clear-no-section-properties")``. Every
        refusal happens before anything changes, so a failed call leaves the
        section as it was. Calling it again on a blank section changes nothing
        and does not mark the section dirty.

        The images of removed pictures stay in the package, pointed at by
        nothing (Hancom drops them when it saves);
        ``doc.media.remove_unused_images()`` removes them.
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

        found, removals = self._plan_control_content(run_elements, on_control_content)

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
        for paragraph in later_paragraphs:
            self._element.remove(paragraph.element)
        if later_runs or stripped_children or removals or caches or later_paragraphs:
            self.mark_dirty()
        return ClearBodyReport(
            removed_paragraphs=len(later_paragraphs),
            removed_runs=len(later_runs),
            stripped_run_children=stripped_children,
            control_content=tuple(found),
            stripped_controls=sum(1 for _, child in removals if child.tag == f"{_HP}ctrl"),
            stripped_section_stories=sum(
                1 for _, child in removals if child.tag in _SECTION_STORY_TAGS
            ),
        )

    def _plan_control_content(
        self, runs: Sequence[ET.Element], on_control_content: str
    ) -> tuple[list[str], list[tuple[ET.Element, ET.Element]]]:
        """Scan the kept children and plan the ``"strip"`` removals, or refuse.

        Refuses (before anything changes) when content is found under
        ``"raise"``, or when content would remain after the ``"strip"`` plan.
        """

        from ..errors import HwpxValueError

        found = _clear_body_kept_content(runs, excluded=())
        if not found or on_control_content == "keep":
            return found, []
        removals = _plan_control_strip(runs) if on_control_content == "strip" else []
        remaining = _clear_body_kept_content(runs, excluded=[child for _, child in removals])
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
            context={"part": self.part_name, "tags": remaining, "mode": on_control_content},
            suggestion=suggestion,
        )

    def _inherited_paragraph_refs(
        self,
    ) -> tuple[str | None, str | None, str | None]:
        """Style refs the next appended paragraph inherits from the last one.

        A list paragraph (bullet/numbered paraPr) must not leak into the next
        paragraph — in Hancom, Enter continues the list but programmatic
        appends of ordinary text are body text. The fidelity audit reproduced
        every following paragraph turning into a list item without this guard.
        """

        existing = self.paragraphs
        if not existing:
            return None, None, None
        last = existing[-1]
        prev_para_ref = last.para_pr_id_ref
        prev_style_ref = last.style_id_ref
        prev_char_ref = last.char_pr_id_ref
        if prev_para_ref is not None and self._para_pr_is_list(prev_para_ref):
            prev_para_ref = None
            prev_style_ref = None
        return prev_para_ref, prev_style_ref, prev_char_ref

    def _para_pr_is_list(self, para_pr_id_ref: str | int) -> bool:
        """True when the paraPr carries a bullet/numbered heading."""

        document = self.document
        if document is None:
            return False
        wanted = str(para_pr_id_ref)
        for header in getattr(document, "_headers", []):
            para_properties = getattr(header, "_para_properties_element", None)
            if para_properties is None:
                continue
            container = para_properties()
            if container is None:
                continue
            for para_pr in container:
                if para_pr.get("id") != wanted:
                    continue
                for child in para_pr:
                    if tag_local_name(child.tag) == "heading":
                        return str(child.get("type", "")).upper() in {
                            "BULLET",
                            "NUMBER",
                        }
                return False
        return False

    def add_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        inherit_style: bool = True,
        **extra_attrs: str,
    ) -> HwpxOxmlParagraph:
        """Create a new paragraph element appended to this section.

        When *inherit_style* is ``True`` (the default) and no explicit
        ``paraPrIDRef``, ``styleIDRef`` or ``charPrIDRef`` is given, the
        values are inherited from the **last** paragraph in the section so
        that consecutive paragraphs share the same formatting.

        The optional ``para_pr_id_ref`` and ``style_id_ref`` parameters
        control the paragraph-level references, while ``char_pr_id_ref`` and
        ``run_attributes`` customise the initial ``<hp:run>`` element when
        ``include_run`` is :data:`True`.
        """

        # Collect style refs from the last paragraph for inheritance.
        prev_para_ref, prev_style_ref, prev_char_ref = (
            self._inherited_paragraph_refs() if inherit_style else (None, None, None)
        )

        attrs = {"id": _paragraph_id(), **_DEFAULT_PARAGRAPH_ATTRS}
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
    ) -> list[HwpxOxmlParagraph]:
        """Insert paragraph copies at *index* and return wrappers for them."""

        existing = self.paragraphs
        if index < 0 or index > len(existing):
            raise IndexError(f"단락 인덱스 {index}이(가) 범위를 벗어났습니다 (총 {len(existing)}개)")

        inserted: list[HwpxOxmlParagraph] = []
        for offset, paragraph in enumerate(paragraphs):
            source_element = paragraph.element if isinstance(paragraph, HwpxOxmlParagraph) else paragraph
            cloned = _clone_paragraph_element(source_element)
            self._element.insert(index + offset, cloned)
            inserted.append(HwpxOxmlParagraph(cloned, self))

        if inserted:
            self._dirty = True
        return inserted

    def copy_paragraph_range(self, start: int, end: int) -> list[ET.Element]:
        """Return deep-copied paragraph elements for the inclusive range."""

        paragraphs = self.paragraphs
        total = len(paragraphs)
        if start < 0 or end < 0 or start >= total or end >= total or start > end:
            raise IndexError(f"문단 범위 {start}..{end}이(가) 유효하지 않습니다 (총 {total}개)")
        return [_clone_paragraph_element(paragraphs[index].element) for index in range(start, end + 1)]

    def mark_dirty(self) -> None:
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def remove_stale_layout_caches(self) -> int:
        """Drop paragraph layout caches that cannot match the paragraph's text.

        A cache is stale when a cached line starts past the plain text, or when
        the text after the last cached line start is far wider than that line
        (the cache lacks lines, so Hancom would draw the tail over itself). The
        save path runs this on every section, so a document whose own caches
        look like that still saves; Hancom lays those paragraphs out again.
        """

        removed = 0
        for paragraph in self._element.iter():
            if _element_local_name(paragraph) != "p":
                continue
            if _remove_stale_paragraph_layout_cache(paragraph) or _remove_short_paragraph_layout_cache(
                paragraph
            ):
                removed += 1
        if removed:
            self.mark_dirty()
        return removed

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
        return _serialize_xml(self._element)


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


def _plan_section_story_strip(section_properties: ET.Element) -> list[tuple[ET.Element, ET.Element]]:
    removals: list[tuple[ET.Element, ET.Element]] = []
    for story in section_properties:
        if story.tag not in _SECTION_STORY_TAGS or not _holds_content(story):
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


def _remove_short_paragraph_layout_cache(paragraph: ET.Element) -> bool:
    """Clear a plain paragraph's cache whose lines cannot hold its text.

    Uses the editor-open-safety rule itself
    (``package_validator._check_line_seg_tail_coverage``), so the save-time
    sweep removes exactly the caches that check would refuse.
    """

    from ..tools.package_validator import (
        PackageValidationIssue,
        _check_line_seg_tail_coverage,
        _simple_paragraph_text,
    )

    text = _simple_paragraph_text(paragraph)
    if text is None:
        return False
    for child in paragraph:
        if _element_local_name(child).lower() != "linesegarray":
            continue
        line_segs = [seg for seg in child if _element_local_name(seg).lower() == "lineseg"]
        findings: list[PackageValidationIssue] = []
        _check_line_seg_tail_coverage(findings, "", 0, text, line_segs)
        if findings:
            _clear_paragraph_layout_cache(paragraph)
            return True
    return False


__all__ = ["HwpxOxmlSection", "HwpxOxmlSectionHeaderFooter", "HwpxOxmlSectionProperties"]
