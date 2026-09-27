# SPDX-License-Identifier: Apache-2.0
"""Run content and character-format wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence
import xml.etree.ElementTree as ET

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from . import body
from ._document_primitives import (
    _HH,
    _HP,
    _clear_paragraph_layout_cache,
    _element_local_name,
    _text_element_content,
)
from ._paragraph_text_edit import clear_text_element, set_text_with_tabs

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph


@dataclass(slots=True)
class RunStyle:
    """Represents the resolved character style applied to a run."""

    id: str
    attributes: dict[str, str]
    child_attributes: dict[str, dict[str, str]]

    def text_color(self) -> str | None:
        return self.attributes.get("textColor")

    def underline_type(self) -> str | None:
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("type")

    def underline_color(self) -> str | None:
        underline = self.child_attributes.get("underline")
        if underline is None:
            return None
        return underline.get("color")

    def outline_type(self) -> str | None:
        outline = self.child_attributes.get("outline")
        if outline is None:
            return None
        return outline.get("type")

    def is_superscript(self) -> bool:
        return "supscript" in self.child_attributes

    def is_subscript(self) -> bool:
        return "subscript" in self.child_attributes

    def is_emboss(self) -> bool:
        return "emboss" in self.child_attributes

    def is_engrave(self) -> bool:
        return "engrave" in self.child_attributes

    def matches(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
    ) -> bool:
        if text_color is not None and self.text_color() != text_color:
            return False
        if underline_type is not None and self.underline_type() != underline_type:
            return False
        if underline_color is not None and self.underline_color() != underline_color:
            return False
        return True


def _char_properties_from_header(element: ET.Element) -> dict[str, RunStyle]:
    mapping: dict[str, RunStyle] = {}
    ref_list = element.find(f"{_HH}refList")
    if ref_list is None:
        return mapping
    char_props_element = ref_list.find(f"{_HH}charProperties")
    if char_props_element is None:
        return mapping

    for child in char_props_element.findall(f"{_HH}charPr"):
        char_id = child.get("id")
        if not char_id:
            continue
        attributes = {key: value for key, value in child.attrib.items() if key != "id"}
        child_attributes: dict[str, dict[str, str]] = {}
        for grandchild in child:
            if len(list(grandchild)) == 0 and (grandchild.text is None or not grandchild.text.strip()):
                child_attributes[_element_local_name(grandchild)] = {
                    key: value for key, value in grandchild.attrib.items()
                }
        style = RunStyle(id=char_id, attributes=attributes, child_attributes=child_attributes)
        if char_id not in mapping:
            mapping[char_id] = style
        try:
            normalized = str(int(char_id))
        except (TypeError, ValueError):
            normalized = None
        if normalized and normalized not in mapping:
            mapping[normalized] = style
    return mapping
class _ReplaceSegment:
    __slots__ = ("element", "attr", "text")

    def __init__(self, element: ET.Element, attr: str, text: str) -> None:
        self.element = element
        self.attr = attr
        self.text = text

    def set(self, value: str) -> None:
        self.text = value
        if value:
            setattr(self.element, self.attr, value)
        else:
            setattr(self.element, self.attr, "")


def _replace_segment_boundaries(segments: Sequence[_ReplaceSegment]) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    offset = 0
    for segment in segments:
        start = offset
        offset += len(segment.text)
        bounds.append((start, offset))
    return bounds


def _distribute_replacement(total: int, weights: Sequence[int]) -> list[int]:
    if not weights:
        return []
    if total <= 0:
        return [0 for _ in weights]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        # Evenly spread characters when no weight information is
        # available (e.g. replacement inside empty segments).
        base = total // len(weights)
        remainder = total - base * len(weights)
        allocation = [base] * len(weights)
        for index in range(remainder):
            allocation[index] += 1
        return allocation

    allocation = []
    remainder = total
    residuals: list[tuple[int, int]] = []
    for index, weight in enumerate(weights):
        share = total * weight // weight_sum
        allocation.append(share)
        remainder -= share
        residuals.append((total * weight % weight_sum, index))

    # Distribute leftover characters based on the size of the modulus so
    # that larger weights receive the extra characters first.
    residuals.sort(key=lambda item: (-item[0], item[1]))
    idx = 0
    while remainder > 0 and residuals:
        _, target = residuals[idx]
        allocation[target] += 1
        remainder -= 1
        idx = (idx + 1) % len(residuals)

    if remainder > 0:
        allocation[-1] += remainder
    return allocation


def _apply_run_replacement(
    segments: list[_ReplaceSegment],
    start: int,
    end: int,
    replacement_text: str,
) -> None:
    bounds = _replace_segment_boundaries(segments)
    affected: list[tuple[int, int, int]] = []
    for index, (seg_start, seg_end) in enumerate(bounds):
        if start >= seg_end or end <= seg_start:
            continue
        local_start = max(0, start - seg_start)
        local_end = min(len(segments[index].text), end - seg_start)
        affected.append((index, local_start, local_end))

    if not affected:
        return

    weights = [local_end - local_start for _, local_start, local_end in affected]
    allocation = _distribute_replacement(len(replacement_text), weights)

    replacement_offset = 0
    first_index = affected[0][0]
    last_index = affected[-1][0]

    for (segment_index, local_start, local_end), share in zip(affected, allocation):
        segment = segments[segment_index]
        prefix = segment.text[:local_start] if segment_index == first_index else ""
        suffix = segment.text[local_end:] if segment_index == last_index else ""
        portion = replacement_text[replacement_offset : replacement_offset + share]
        replacement_offset += share
        segment.set(prefix + portion + suffix)


def _replace_all_occurrences(
    segments: list[_ReplaceSegment], search: str, replacement: str, count: int | None
) -> int:
    total_replacements = 0
    remaining = count
    search_start = 0
    combined = "".join(segment.text for segment in segments)

    while True:
        if remaining is not None and remaining <= 0:
            break
        position = combined.find(search, search_start)
        if position == -1:
            break
        end_position = position + len(search)
        _apply_run_replacement(segments, position, end_position, replacement)
        total_replacements += 1
        if remaining is not None:
            remaining -= 1
        combined = "".join(segment.text for segment in segments)
        if replacement:
            search_start = position + len(replacement)
        else:
            search_start = position
        if search_start > len(combined):
            search_start = len(combined)

    return total_replacements


#: Character elements inside ``hp:t``: a tab, a line break, a soft hyphen, a non-breaking or
#: fixed-width space. Hancom's search reads each as a character, so text is not joined across one.
_TEXT_CHARACTER_ELEMENTS = frozenset({"tab", "lineBreak", "hyphen", "nbSpace", "fwSpace"})


def _text_stretches(runs: Sequence[ET.Element]) -> list[list[_ReplaceSegment]]:
    """Split the text of consecutive runs into the stretches one match may cover."""

    stretches: list[list[_ReplaceSegment]] = [[]]

    def cut() -> None:
        if stretches[-1]:
            stretches.append([])

    def visit(element: ET.Element) -> None:
        stretches[-1].append(_ReplaceSegment(element, "text", element.text or ""))
        for child in list(element):
            if not isinstance(child.tag, str):
                pass  # a comment or processing instruction: not text, the text around it still joins
            elif _element_local_name(child) in _TEXT_CHARACTER_ELEMENTS:
                cut()
            else:
                visit(child)
            stretches[-1].append(_ReplaceSegment(child, "tail", child.tail or ""))

    for run in runs:
        for child in run:
            if _element_local_name(child) == "t":
                visit(child)
            else:
                cut()
    return [stretch for stretch in stretches if stretch]


def _overlay_replacement(segments: Sequence[_ReplaceSegment], start: int, end: int, replacement: str) -> None:
    """Replace ``[start, end)`` of the joined *segments* character by character, as Hancom does.

    The i-th replacement character takes the place of the i-th matched character, so it keeps
    that character's run. Replacement characters beyond the match follow its last character;
    matched characters beyond the replacement are removed.
    """

    affected: list[tuple[_ReplaceSegment, int, int]] = []
    offset = 0
    for segment in segments:
        segment_start, offset = offset, offset + len(segment.text)
        if offset <= start or segment_start >= end:
            continue
        affected.append((segment, max(start - segment_start, 0), min(end - segment_start, len(segment.text))))
    used = 0
    for index, (segment, local_start, local_end) in enumerate(affected):
        last = index == len(affected) - 1
        portion = replacement[used:] if last else replacement[used : used + local_end - local_start]
        used += len(portion)
        segment.set(segment.text[:local_start] + portion + segment.text[local_end:])


def replace_across_runs(
    paragraph: "HwpxOxmlParagraph",
    runs: Sequence[ET.Element],
    search: str,
    replacement: str,
    *,
    count: int | None = None,
) -> int:
    """Replace non-empty *search* in consecutive *runs* of *paragraph* as Hancom's find and replace does.

    A match may start in one run and end in a later one. Each replacement character takes the
    place, and so the run, of the matched character at the same position; extra replacement
    characters follow the last matched one, and matched characters left over are removed (a
    run may be left empty). Text is joined across run boundaries and markup such as
    highlights, but not across a tab, a line break or another character element, nor across a
    control or an object. Returns the number of replacements.
    """

    total = 0
    for segments in _text_stretches(runs):
        combined = "".join(segment.text for segment in segments)
        position = combined.find(search)
        while position != -1 and (count is None or total < count):
            _overlay_replacement(segments, position, position + len(search), replacement)
            total += 1
            combined = "".join(segment.text for segment in segments)
            position = combined.find(search, position + len(replacement))
    if total:
        _clear_paragraph_layout_cache(paragraph.element)
        paragraph.section.mark_dirty()
    return total


class HwpxOxmlRun:
    """Lightweight wrapper around an ``<hp:run>`` element."""

    def __init__(self, element: ET.Element, paragraph: "HwpxOxmlParagraph"):
        self.element = element
        self.paragraph = paragraph

    def to_model(self) -> "body.Run":
        xml_bytes = ET.tostring(self.element, encoding="utf-8")
        node = LET.fromstring(xml_bytes)
        return body.parse_run_element(node)

    @property
    def model(self) -> "body.Run":
        return self.to_model()

    def apply_model(self, model: "body.Run") -> None:
        new_node = body.serialize_run(model)
        xml_bytes = LET.tostring(new_node)
        parent = self.paragraph.element
        if isinstance(parent, LET._Element):
            replacement = LET.fromstring(xml_bytes)
        else:
            replacement = ET.fromstring(xml_bytes)
        run_children = list(parent)
        index = run_children.index(self.element)
        parent.remove(self.element)
        parent.insert(index, replacement)
        self.element = replacement
        # Replacing the run rewrites its text/markup, so the cached line layout
        # of the containing paragraph no longer holds. Tracked-change marks also
        # make the paragraph unjudgeable for the save-time stale sweep, so this
        # is the only point that can invalidate it.
        _clear_paragraph_layout_cache(parent)
        self.paragraph.section.mark_dirty()

    def _current_format_flags(self) -> tuple[bool, bool, bool] | None:
        style = self.style
        if style is None:
            return None
        bold = "bold" in style.child_attributes
        italic = "italic" in style.child_attributes
        underline_attrs = style.child_attributes.get("underline")
        underline = False
        if underline_attrs is not None:
            underline = underline_attrs.get("type", "").upper() != "NONE"
        return bold, italic, underline

    def _apply_format_change(
        self,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
    ) -> None:
        document = self.paragraph.section.document
        if document is None:
            raise RuntimeError("run is not attached to a document")

        current = self._current_format_flags()
        if current is None:
            current = (False, False, False)

        target = [
            current[0] if bold is None else bool(bold),
            current[1] if italic is None else bool(italic),
            current[2] if underline is None else bool(underline),
        ]

        if tuple(target) == current:
            return

        style_id = document.ensure_run_style(
            bold=target[0],
            italic=target[1],
            underline=target[2],
            base_char_pr_id=self.char_pr_id_ref,
        )
        self.char_pr_id_ref = style_id

    @property
    def char_pr_id_ref(self) -> str | None:
        """Return the character property reference applied to the run."""
        return self.element.get("charPrIDRef")

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int | None) -> None:
        if value is None:
            if "charPrIDRef" in self.element.attrib:
                del self.element.attrib["charPrIDRef"]
                _clear_paragraph_layout_cache(self.paragraph.element)
                self.paragraph.section.mark_dirty()
            return

        new_value = str(value)
        if self.element.get("charPrIDRef") != new_value:
            self.element.set("charPrIDRef", new_value)
            # A style swap changes glyph metrics, so the cached line layout of
            # the containing paragraph no longer holds.
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()

    def _plain_text_nodes(self) -> list[ET.Element]:
        return [
            node
            for node in self.element.findall(f"{_HP}t")
            if len(list(node)) == 0
        ]

    def _ensure_plain_text_node(self) -> ET.Element:
        nodes = self._plain_text_nodes()
        if nodes:
            return nodes[0]
        t = self.element.makeelement(f"{_HP}t", {})
        self.element.append(t)
        return t

    @property
    def text(self) -> str:
        parts: list[str] = []
        for node in self.element.findall(f"{_HP}t"):
            parts.append(_text_element_content(node))
        return "".join(parts)

    @text.setter
    def text(self, value: str) -> None:
        # The value replaces the run's whole text in place: the first hp:t
        # (which may sit between field controls) takes it, tabs as hp:tab
        # elements, and every hp:t loses its old text together with the line
        # breaks, tabs and spaces inside it and the text after them.
        changed = self.text != value
        nodes = self.element.findall(f"{_HP}t")
        primary = nodes[0] if nodes else self._ensure_plain_text_node()
        set_text_with_tabs(primary, value)
        for node in nodes[1:]:
            clear_text_element(node)
        if changed:
            _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()

    @property
    def style(self) -> RunStyle | None:
        document = self.paragraph.section.document
        if document is None:
            return None
        char_pr_id = self.char_pr_id_ref
        if char_pr_id is None:
            return None
        return document.char_property(char_pr_id)

    def replace_text(
        self,
        search: str,
        replacement: str,
        *,
        count: int | None = None,
        _clear_layout: bool = True,
    ) -> int:
        """Replace ``search`` with ``replacement`` within ``<hp:t>`` nodes.

        The replacement traverses nested markup tags (e.g. highlights) and
        preserves the existing element structure so formatting metadata remains
        intact. Text on the two sides of a tab, a line break or another
        character element, or of a control, is not joined -- Hancom reads each
        as a character of its own. Returns the number of replacements.
        """

        if not search:
            raise ValueError("search text must be a non-empty string")

        if count is not None and count <= 0:
            return 0

        total_replacements = 0
        for segments in _text_stretches([self.element]):
            remaining = None if count is None else count - total_replacements
            if remaining is not None and remaining <= 0:
                break
            total_replacements += _replace_all_occurrences(segments, search, replacement, remaining)

        if total_replacements:
            if _clear_layout:
                _clear_paragraph_layout_cache(self.paragraph.element)
            self.paragraph.section.mark_dirty()
        return total_replacements

    def remove(self) -> None:
        parent = self.paragraph.element
        try:
            parent.remove(self.element)
        except ValueError:  # pragma: no cover - defensive branch
            return
        self.paragraph.section.mark_dirty()

    @property
    def bold(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[0]

    @bold.setter
    def bold(self, value: bool | None) -> None:
        self._apply_format_change(bold=value)

    @property
    def italic(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[1]

    @italic.setter
    def italic(self, value: bool | None) -> None:
        self._apply_format_change(italic=value)

    @property
    def underline(self) -> bool | None:
        flags = self._current_format_flags()
        if flags is None:
            return None
        return flags[2]

    @underline.setter
    def underline(self, value: bool | None) -> None:
        self._apply_format_change(underline=value)

__all__ = ["HwpxOxmlRun", "RunStyle", "replace_across_runs"]
