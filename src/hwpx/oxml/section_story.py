# SPDX-License-Identifier: Apache-2.0
"""Owned section header/footer story behavior."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _clear_paragraph_layout_cache,
    _default_sublist_attributes,
    _paragraph_id,
    _sanitize_text,
)

if TYPE_CHECKING:
    from .section_format import HwpxOxmlSectionProperties


def _direct_children(element: ET.Element, tag: str) -> list[ET.Element]:
    """Return direct element children with the exact qualified *tag*."""

    return [child for child in list(element) if child.tag == tag]


def _simple_story_text_target(
    element: ET.Element,
) -> tuple[ET.Element, ET.Element, ET.Element, ET.Element]:
    """Validate and return the one losslessly editable story text leaf.

    The first story leap deliberately accepts only the measured simple shape:
    one ``subList`` containing one paragraph, one run, and one text leaf.  A
    cached ``lineSegArray`` is layout metadata and may be discarded after a
    text edit; every other child is semantic content and therefore fails
    closed before mutation.
    """

    children = list(element)
    sublists = _direct_children(element, f"{_HP}subList")
    if len(sublists) != 1 or children != sublists:
        raise ValueError("header story must contain exactly one direct subList")
    sublist = sublists[0]

    paragraphs = _direct_children(sublist, f"{_HP}p")
    if len(paragraphs) != 1 or list(sublist) != paragraphs:
        raise ValueError("header story must contain exactly one direct paragraph")
    paragraph = paragraphs[0]

    paragraph_children = list(paragraph)
    runs = _direct_children(paragraph, f"{_HP}run")
    if len(runs) != 1 or any(
        child.tag not in {f"{_HP}run", f"{_HP}lineSegArray"}
        for child in paragraph_children
    ):
        raise ValueError("header story has rich or control-bearing paragraph content")
    run = runs[0]

    texts = _direct_children(run, f"{_HP}t")
    if len(texts) != 1 or list(run) != texts or list(texts[0]):
        raise ValueError("header story has rich or control-bearing run content")
    return sublist, paragraph, run, texts[0]


def _iter_body_runs_without_section_properties(
    element: ET.Element,
) -> Iterator[ET.Element]:
    """Yield body runs while pruning the logical ``secPr`` story tree."""

    for child in list(element):
        if child.tag == f"{_HP}secPr":
            continue
        if child.tag == f"{_HP}run":
            yield child
        yield from _iter_body_runs_without_section_properties(child)


def _validate_simple_story_value(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("header story text must be a string")
    if any(character in value for character in ("\t", "\r", "\n")):
        raise ValueError("header story text cannot contain tabs or line breaks")
    if _sanitize_text(value) != value:
        raise ValueError("header story text contains illegal XML characters")


def _story_kind(element: ET.Element) -> str:
    if element.tag == f"{_HP}header":
        return "header"
    if element.tag == f"{_HP}footer":
        return "footer"
    raise ValueError("unsupported section story kind")


def _validate_logical_story_identity(
    element: ET.Element,
    properties: Any,
    kind: str,
) -> tuple[str, str]:
    native_id = element.get("id")
    page_type = element.get("applyPageType")
    if not native_id or page_type not in {"BOTH", "EVEN", "ODD"}:
        raise ValueError("header story has no stable id/page-type binding")
    conflicts = [
        story
        for story in properties.element.findall(f"{_HP}{kind}")
        if story.get("id") == native_id
        or story.get("applyPageType", "BOTH") == page_type
    ]
    if len(conflicts) != 1 or conflicts[0] is not element:
        raise ValueError("header story id/page-type binding is ambiguous")
    return native_id, page_type


def _validate_story_apply(
    properties: Any,
    apply_element: ET.Element | None,
    kind: str,
    native_id: str,
    page_type: str,
) -> None:
    applies = [
        apply
        for apply in properties._apply_elements(kind)
        if properties._apply_reference(apply, kind) == native_id
    ]
    expected = applies[0] if len(applies) == 1 else None
    if expected is not apply_element:
        raise ValueError("header story apply linkage is missing or ambiguous")
    if expected is None or expected.get("applyPageType", "BOTH") != page_type:
        raise ValueError("header story apply linkage is missing or ambiguous")


def _iter_control_stories(
    section_element: ET.Element,
    kind: str,
) -> Iterator[tuple[ET.Element, ET.Element]]:
    for run in _iter_body_runs_without_section_properties(section_element):
        for control in _direct_children(run, f"{_HP}ctrl"):
            for story in _direct_children(control, f"{_HP}{kind}"):
                yield control, story


def _find_target_mirror(
    section_element: ET.Element,
    kind: str,
    native_id: str,
    page_type: str,
) -> ET.Element | None:
    targets: list[ET.Element] = []
    for control, story in _iter_control_stories(section_element, kind):
        same_id = story.get("id") == native_id
        same_page_type = story.get("applyPageType", "BOTH") == page_type
        if same_id != same_page_type:
            raise ValueError("header story mirror linkage is inconsistent")
        if same_id and same_page_type:
            if list(control) != [story]:
                raise ValueError("header story mirror control is not isolated")
            targets.append(story)
    if len(targets) > 1:
        raise ValueError("header story mirror binding is ambiguous")
    return targets[0] if targets else None


def _story_structure_signature(
    element: ET.Element,
    parts: tuple[ET.Element, ET.Element, ET.Element, ET.Element],
) -> tuple[dict[str, str], ...]:
    sublist, paragraph, run, text = parts
    return tuple(
        dict(node.attrib) for node in (element, sublist, paragraph, run, text)
    )


def _validated_mirror_parts(
    mirror: ET.Element,
    logical: ET.Element,
    logical_parts: tuple[ET.Element, ET.Element, ET.Element, ET.Element],
) -> tuple[ET.Element, ET.Element, ET.Element, ET.Element]:
    mirror_parts = _simple_story_text_target(mirror)
    logical_text = logical_parts[3]
    mirror_text = mirror_parts[3]
    if _story_structure_signature(mirror, mirror_parts) != _story_structure_signature(
        logical, logical_parts
    ):
        raise ValueError("header story logical/mirror structures are inconsistent")
    if mirror_text.text != logical_text.text:
        raise ValueError("header story logical/mirror structures are inconsistent")
    return mirror_parts


class HwpxOxmlSectionHeaderFooter:
    """Wraps a ``<hp:header>`` or ``<hp:footer>`` element."""

    def __init__(
        self,
        element: ET.Element,
        properties: "HwpxOxmlSectionProperties",
        apply_element: ET.Element | None = None,
    ):
        self.element = element
        self._properties = properties
        self._apply_element = apply_element

    @property
    def apply_element(self) -> ET.Element | None:
        """Return the corresponding ``<hp:headerApply>``/``<hp:footerApply>`` element."""

        return self._apply_element

    @property
    def id(self) -> str | None:
        """Return the identifier assigned to the header/footer element."""

        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            changed = False
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                changed = True
            if self._update_apply_reference(None):
                changed = True
            if changed:
                self._properties.section.mark_dirty()
            return

        new_value = str(value)
        changed = False
        if self.element.get("id") != new_value:
            self.element.set("id", new_value)
            changed = True
        if self._update_apply_reference(new_value):
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    @property
    def apply_page_type(self) -> str:
        """Return the page type the header/footer applies to."""

        value = self.element.get("applyPageType")
        if value is not None:
            return value
        if self._apply_element is not None:
            return self._apply_element.get("applyPageType", "BOTH")
        return "BOTH"

    @apply_page_type.setter
    def apply_page_type(self, value: str) -> None:
        changed = False
        if self.element.get("applyPageType") != value:
            self.element.set("applyPageType", value)
            changed = True
        if self._apply_element is not None and self._apply_element.get("applyPageType") != value:
            self._apply_element.set("applyPageType", value)
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    def _apply_id_attributes(self) -> tuple[str, ...]:
        if self.element.tag.endswith("header"):
            return ("idRef", "headerIDRef", "headerIdRef", "headerRef")
        return ("idRef", "footerIDRef", "footerIdRef", "footerRef")

    def _update_apply_reference(self, value: str | None) -> bool:
        apply = self._apply_element
        if apply is None:
            return False

        candidate_keys = {name.lower() for name in self._apply_id_attributes()}
        attr_candidates: list[str] = []
        for name in list(apply.attrib.keys()):
            if name.lower() in candidate_keys:
                attr_candidates.append(name)

        changed = False
        if value is None:
            for attr in attr_candidates:
                if attr in apply.attrib:
                    del apply.attrib[attr]
                    changed = True
            return changed

        target_attr = None
        for attr in attr_candidates:
            lower = attr.lower()
            if lower == "idref" or (
                self.element.tag.endswith("header") and "header" in lower
            ) or (
                self.element.tag.endswith("footer") and "footer" in lower
            ):
                target_attr = attr
                break
        if target_attr is None:
            target_attr = self._apply_id_attributes()[0]

        if apply.get(target_attr) != value:
            apply.set(target_attr, value)
            changed = True

        for attr in list(apply.attrib.keys()):
            if attr == target_attr:
                continue
            if attr.lower() in candidate_keys:
                del apply.attrib[attr]
                changed = True

        return changed

    def _initial_sublist_attributes(self) -> dict[str, str]:
        attrs = dict(_default_sublist_attributes())
        attrs["vertAlign"] = "TOP" if self.element.tag.endswith("header") else "BOTTOM"
        size = self._properties.page_size
        margins = self._properties.page_margins
        text_width = max(size.width - margins.left - margins.right, 0)
        text_height = margins.header if self.element.tag.endswith("header") else margins.footer
        if text_width:
            attrs["textWidth"] = str(text_width)
        if text_height:
            attrs["textHeight"] = str(text_height)
        return attrs

    def _ensure_text_element(self) -> ET.Element:
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = _append_child(
                self.element,
                f"{_HP}subList",
                self._initial_sublist_attributes(),
            )
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
            paragraph_attrs["id"] = _paragraph_id()
            paragraph = _append_child(sublist, f"{_HP}p", paragraph_attrs)
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        text = run.find(f"{_HP}t")
        if text is None:
            text = _append_child(run, f"{_HP}t")
        return text

    @property
    def text(self) -> str:
        """Return the concatenated text content of the header/footer."""

        parts: list[str] = []
        for node in self.element.findall(f".//{_HP}t"):
            if node.text:
                parts.append(node.text)
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        # Replace existing content with a simple paragraph.
        for child in list(self.element):
            if child.tag == f"{_HP}subList":
                self.element.remove(child)
        text_node = self._ensure_text_element()
        text_node.text = _sanitize_text(value)
        # Clear cached lineseg so Hangul recalculates layout.
        for p_elem in self.element.findall(f".//{_HP}p"):
            _clear_paragraph_layout_cache(p_elem)
        self._properties.section.mark_dirty()

    def set_simple_text_preserving(self, value: str) -> None:
        """Edit one existing simple story without rebuilding its structure.

        This is the bounded transaction primitive used by the agent layer.  It
        preserves native ids, formatting attributes, apply linkage, and every
        unrelated mirrored header/footer control.  Ambiguous, stale, or rich
        structures are rejected before the first mutation.
        """

        _validate_simple_story_value(value)
        kind = _story_kind(self.element)
        native_id, page_type = _validate_logical_story_identity(
            self.element, self._properties, kind
        )
        _validate_story_apply(
            self._properties, self._apply_element, kind, native_id, page_type
        )
        logical_parts = _simple_story_text_target(self.element)
        logical_paragraph = logical_parts[1]
        logical_text = logical_parts[3]
        mirror = _find_target_mirror(
            self._properties.section.element, kind, native_id, page_type
        )
        mirror_parts = (
            None
            if mirror is None
            else _validated_mirror_parts(mirror, self.element, logical_parts)
        )
        changed = logical_text.text != value
        logical_text.text = value
        changed = bool(_clear_paragraph_layout_cache(logical_paragraph)) or changed
        if mirror_parts is not None:
            mirror_paragraph = mirror_parts[1]
            mirror_text = mirror_parts[3]
            mirror_text.text = value
            changed = bool(_clear_paragraph_layout_cache(mirror_paragraph)) or changed
        else:
            run = self._properties._header_footer_control_run()
            control = _append_child(run, f"{_HP}ctrl", {})
            control.append(deepcopy(self.element))
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    def _ensure_sublist(self) -> ET.Element:
        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            sublist = _append_child(
                self.element,
                f"{_HP}subList",
                self._initial_sublist_attributes(),
            )
        return sublist

    def clear_content(self) -> None:
        """Remove existing rich/plain content while keeping header/footer linkage."""

        removed = False
        for child in list(self.element):
            if child.tag == f"{_HP}subList":
                self.element.remove(child)
                removed = True
        if removed:
            self._properties.section.mark_dirty()

    def add_paragraph(self, *, align: str | None = None) -> ET.Element:
        """Append an empty paragraph to the header/footer subList."""

        sublist = self._ensure_sublist()
        paragraph_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
        paragraph_attrs["id"] = _paragraph_id()
        if align:
            document = self._properties.section.document
            if document is not None and document.headers:
                paragraph_attrs["paraPrIDRef"] = document.headers[0].ensure_paragraph_alignment(
                    str(align)
                )
        paragraph = _append_child(sublist, f"{_HP}p", paragraph_attrs)
        self._properties.section.mark_dirty()
        return paragraph

    def _ensure_content_paragraph(self) -> ET.Element:
        sublist = self._ensure_sublist()
        paragraph = sublist.find(f"{_HP}p")
        if paragraph is None:
            paragraph = self.add_paragraph()
        return paragraph

    def add_run(
        self,
        text: str,
        *,
        paragraph: ET.Element | None = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
    ) -> ET.Element:
        """Append a text run to a header/footer paragraph."""

        target = paragraph if paragraph is not None else self._ensure_content_paragraph()
        char_pr_id_ref = "0"
        if any((bold, italic, underline, color, font, size, highlight, strike)):
            document = self._properties.section.document
            if document is not None:
                char_pr_id_ref = document.ensure_run_style(
                    bold=bold,
                    italic=italic,
                    underline=underline,
                    color=color,
                    font=font,
                    size=size,
                    highlight=highlight,
                    strike=strike,
                )
        run = _append_child(target, f"{_HP}run", {"charPrIDRef": str(char_pr_id_ref)})
        text_node = _append_child(run, f"{_HP}t")
        text_node.text = _sanitize_text(text)
        _clear_paragraph_layout_cache(target)
        self._properties.section.mark_dirty()
        return run

    def add_page_number_field(
        self,
        *,
        paragraph: ET.Element | None = None,
        format: str = "page",
        position: str = "BOTTOM_CENTER",
        format_type: str | None = None,
    ) -> ET.Element:
        """Append the corpus-observed automatic page-number control."""

        target = paragraph if paragraph is not None else self._ensure_content_paragraph()
        normalized_format = str(format_type or format or "DIGIT").strip().upper()
        format_aliases = {
            "PAGE": "DIGIT",
            "PAGE/TOTAL": "DIGIT",
            "NUMBER": "DIGIT",
            "DIGIT": "DIGIT",
            "ROMAN": "ROMAN_CAPITAL",
            "ROMAN_UPPER": "ROMAN_CAPITAL",
            "ROMAN_LOWER": "ROMAN_SMALL",
            "ALPHA": "LATIN_CAPITAL",
            "ALPHA_UPPER": "LATIN_CAPITAL",
            "ALPHA_LOWER": "LATIN_SMALL",
        }
        page_format_type = format_aliases.get(normalized_format, normalized_format)
        auto_run = _append_child(target, f"{_HP}run", {"charPrIDRef": "0"})
        auto_ctrl = _append_child(auto_run, f"{_HP}ctrl", {})
        _append_child(auto_ctrl, f"{_HP}autoNum", {"num": "1", "numType": "PAGE"})
        run = _append_child(target, f"{_HP}run", {"charPrIDRef": "0"})
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        page_number = _append_child(
            ctrl,
            f"{_HP}pageNum",
            {"pos": position, "formatType": page_format_type, "sideChar": "-"},
        )
        _clear_paragraph_layout_cache(target)
        self._properties.section.mark_dirty()
        return page_number

    def set_content(self, content: Sequence[Mapping[str, Any]]) -> None:
        """Replace header/footer content with paragraph/run/page-number specs."""

        self.clear_content()
        for paragraph_spec in content:
            paragraph = self.add_paragraph(align=paragraph_spec.get("align"))
            children = paragraph_spec.get("children")
            if children is None:
                children = paragraph_spec.get("runs")
            children = children or ()
            if not children and paragraph_spec.get("text"):
                children = ({"type": "run", "text": paragraph_spec.get("text", "")},)
            for child in children:
                page_number_format = child.get("page_number")
                kind = "page_number" if page_number_format is not None else str(child.get("type", "run"))
                if kind == "run":
                    self.add_run(
                        str(child.get("text", "")),
                        paragraph=paragraph,
                        bold=bool(child.get("bold", False)),
                        italic=bool(child.get("italic", False)),
                        underline=bool(child.get("underline", False)),
                        color=child.get("color"),
                        font=child.get("font"),
                        size=child.get("size"),
                        highlight=child.get("highlight"),
                        strike=child.get("strike"),
                    )
                    continue
                if kind == "page_number":
                    page_format = str(page_number_format or child.get("format", "page"))
                    self.add_page_number_field(
                        paragraph=paragraph,
                        format=page_format,
                        position=str(child.get("position", "BOTTOM_CENTER")),
                        format_type=child.get("formatType") or child.get("format_type"),
                    )
                    if page_format == "page/total":
                        self.add_run("/", paragraph=paragraph)
                        self.add_page_number_field(
                            paragraph=paragraph,
                            format=page_format,
                            position=str(child.get("position", "BOTTOM_CENTER")),
                            format_type=child.get("formatType") or child.get("format_type"),
                        )
                    continue
                raise ValueError(f"unsupported header/footer content type: {kind}")

__all__ = ["HwpxOxmlSectionHeaderFooter"]
