# SPDX-License-Identifier: Apache-2.0
"""Owned section header/footer story behavior."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, cast
import xml.etree.ElementTree as ET

from ._document_primitives import (
    SameElement,
    paragraph_attributes,
    _HP,
    _append_child,
    _clear_paragraph_layout_cache,
    _default_sublist_attributes,
    _paragraph_id,
    _require_text,
    _sanitize_text,
    _text_element_content,
)
from ._paragraph_text_edit import set_text_with_tabs
from .numbering_kinds import number_format

if TYPE_CHECKING:
    from .header import Style
    from .objects import HwpxOxmlInlineObject
    from .paragraph import HwpxOxmlParagraph
    from .run import HwpxOxmlRun
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
        child.tag not in {f"{_HP}run", f"{_HP}lineSegArray", f"{_HP}linesegarray"}
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


def _place_both_first(section_element: ET.Element, story: ET.Element) -> None:
    """Move the control holding a ``BOTH`` *story* ahead of its run's ODD/EVEN controls.

    Hancom draws the last applicable control on each page, so a ``BOTH`` control
    after an ``ODD`` or ``EVEN`` one would hide it.
    """

    kind = _story_kind(story)
    for run in _iter_body_runs_without_section_properties(section_element):
        controls = _direct_children(run, f"{_HP}ctrl")
        owner = next((control for control in controls if any(child is story for child in control)), None)
        if owner is None:
            continue
        specific = [
            control for control in controls
            if (other := control.find(f"{_HP}{kind}")) is not None
            and other.get("applyPageType", "BOTH") != "BOTH"
        ]
        children = list(run)
        if specific and children.index(specific[0]) < children.index(owner):
            run.remove(owner)
            run.insert(list(run).index(specific[0]), owner)
        return


_STORY_TAGS = (f"{_HP}header", f"{_HP}footer")
_PairKey = tuple[str, "str | None", str]


def _pair_key(story: ET.Element) -> _PairKey:
    return (_story_kind(story), story.get("id"), story.get("applyPageType", "BOTH"))


def _tree_key(element: ET.Element) -> tuple:
    """The content of *element* -- tag, attributes, text, children and their tails -- without its own tail."""

    children = tuple((_tree_key(child), child.tail or "") for child in element)
    return (element.tag, tuple(sorted(element.attrib.items())), element.text or "", children)


def story_control_index(run: ET.Element, before: ET.Element | None = None) -> int:
    """Where a header or footer ``hp:ctrl`` goes in the section's first *run*: at its end, but ahead
    of *before* and of a control that starts a field. Hancom drops a header or footer control that
    sits inside a field's span when it saves the document."""

    for index, child in enumerate(run):
        if child is before or (child.tag == f"{_HP}ctrl" and child.find(f"{_HP}fieldBegin") is not None):
            return index
    return len(run)


def _control_story_index(section_element: ET.Element) -> dict[_PairKey, list[ET.Element]]:
    """Every header/footer a body control holds, by (kind, id, page type), in one pass over the section."""

    index: dict[_PairKey, list[ET.Element]] = {}
    for run in _iter_body_runs_without_section_properties(section_element):
        for control in _direct_children(run, f"{_HP}ctrl"):
            for story in control:
                if story.tag in _STORY_TAGS:
                    index.setdefault(_pair_key(story), []).append(story)
    return index


def _story_pairs(section_element: ET.Element) -> list[tuple[ET.Element, ET.Element]]:
    """(``hp:secPr`` story, its one ``hp:ctrl`` copy) for each story python-hwpx 6.x kept twice."""

    stories = [story for sec_pr in section_element.findall(f"{_HP}p/{_HP}run/{_HP}secPr")
               for story in sec_pr if story.tag in _STORY_TAGS]
    if not stories:
        return []
    index = _control_story_index(section_element)
    return [(story, copies[0]) for story in stories if len(copies := index.get(_pair_key(story), [])) == 1]


def story_marks(section_element: ET.Element) -> dict[_PairKey, tuple]:
    """The content of each story whose two copies agree, for a later save to tell which copy changed."""

    return {_pair_key(story): content for story, mirror in _story_pairs(section_element)
            if (content := _tree_key(story)) == _tree_key(mirror)}


def control_twins(section_element: ET.Element) -> set[ET.Element]:
    """The ``hp:ctrl`` copies of the stories python-hwpx 6.x kept twice.

    A reader that walks the whole section skips them, so that each header or
    footer counts once (its form fields, for one).
    """

    return {mirror for _, mirror in _story_pairs(section_element)}


def _copy_into(target: ET.Element, source: ET.Element) -> None:
    """Give *target* the content of *source*, keeping *target* itself (and its tail) in place."""

    target.attrib.clear()
    target.attrib.update(source.attrib)
    target.text = source.text
    for child in list(target):
        target.remove(child)
    for child in source:
        target.append(deepcopy(child))


def sync_story_mirrors(section: Any) -> int:
    """Bring the two copies of each header/footer back in step before a save.

    The stories python-hwpx up to 6.x wrote live twice: under ``hp:secPr``,
    where its story objects read and edit them, and in a body ``hp:ctrl``, the
    only copy Hancom reads (python-hwpx 7.0 writes the control copy alone, and
    drops a 6.x ``hp:secPr`` copy when that story is set again). When the
    copies differ, the one that changed since they last
    agreed (when the document was opened, when the story was set, or at the
    last save) is copied over the other; when that is not known, or both
    changed, the ``hp:secPr`` story wins. Both elements stay in place, so story
    objects keep working after a save. A pair is synced only when exactly one
    control story has the same id and page type; stories that exist only as a
    control, as in documents Hancom saved, are left alone.
    """

    marks = getattr(section, "_story_marks", None) or {}
    fresh: dict[_PairKey, tuple] = {}
    changed = 0
    for story, mirror in _story_pairs(section.element):
        key = _pair_key(story)
        logical = _tree_key(story)
        if logical != _tree_key(mirror):
            if marks.get(key) == logical:  # only the control copy changed
                _copy_into(story, mirror)
            else:
                _copy_into(mirror, story)
            changed += 1
        fresh[key] = _tree_key(story)
    section._story_marks = fresh
    return changed


def _section_story_elements(properties: Any, kind: str) -> list[ET.Element]:
    """Expose native control-only stories as well as legacy logical stories."""
    logical = properties.element.findall(f"{_HP}{kind}")
    identities = {(s.get("id"), s.get("applyPageType", "BOTH")) for s in logical}
    return logical + [
        story for _, story in _iter_control_stories(properties.section.element, kind)
        if (story.get("id"), story.get("applyPageType", "BOTH")) not in identities
    ]


def _set_control_story_text(element: ET.Element, properties: Any, value: str) -> None:
    """Edit a unique native control in place, without synthesizing a secPr copy."""
    from ..errors import HwpxValueError

    kind = _story_kind(element)
    native_id, page_type = element.get("id"), element.get("applyPageType")
    conflicts = [
        s for s in _section_story_elements(properties, kind)
        if s.get("id") == native_id or s.get("applyPageType", "BOTH") == page_type
    ]
    if (not native_id or page_type not in {"BOTH", "EVEN", "ODD"}
            or len(conflicts) != 1 or conflicts[0] is not element):
        raise HwpxValueError(
            "native story identity is missing or ambiguous", code="story-ambiguous",
            suggestion="Inspect story IDs and page types before selecting one control.",
        )
    mirror = _find_target_mirror(properties.section.element, kind, native_id, page_type)
    if mirror is not element or properties._apply_elements(kind):
        raise HwpxValueError(
            "native story linkage is inconsistent", code="story-linkage",
            suggestion="Inspect the existing control and section apply metadata.",
        )
    paragraph, text = _native_story_text_target(element)
    changed = text.text != value
    text.text = value
    changed = bool(_clear_paragraph_layout_cache(paragraph)) or changed
    if changed:
        properties.section.mark_dirty()


def _native_story_text_target(element: ET.Element) -> tuple[ET.Element, ET.Element]:
    """Find one visible simple text leaf while retaining empty native paragraphs."""
    from ..errors import HwpxValueError

    invalid = HwpxValueError(
        "native story must have one visible text leaf without rich controls",
        code="story-rich-content",
        suggestion="Select individual runs for rich content instead of replacing the story.",
    )
    sublists = _direct_children(element, f"{_HP}subList")
    if len(sublists) != 1 or list(element) != sublists:
        raise invalid
    targets: list[tuple[ET.Element, ET.Element]] = []
    for paragraph in sublists[0]:
        if paragraph.tag != f"{_HP}p":
            raise invalid
        targets.extend((paragraph, text) for text in _native_paragraph_texts(paragraph, invalid))
    if len(targets) != 1:
        raise invalid
    return targets[0]


def _native_paragraph_texts(paragraph: ET.Element, invalid: ValueError) -> Iterator[ET.Element]:
    for run in paragraph:
        if run.tag in {f"{_HP}lineSegArray", f"{_HP}linesegarray"}:
            continue
        if run.tag != f"{_HP}run":
            raise invalid
        for text in run:
            if text.tag != f"{_HP}t" or list(text):
                raise invalid
            if text.text:
                yield text


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


class HwpxOxmlSectionHeaderFooter(SameElement):
    """Wraps a ``<hp:header>`` or ``<hp:footer>`` element."""

    def __init__(
        self,
        element: ET.Element,
        properties: "HwpxOxmlSectionProperties",
        apply_element: ET.Element | None = None,
    ):
        self.element = element
        self._held_properties = properties
        self._apply_element = apply_element

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "apply_page_type":  # the 6.x name: a write is refused like a read, not kept aside (7.0)
            from .._removed_names import removed_name_error

            error = removed_name_error("HeaderFooter", name)
            if error is not None:
                raise error
        object.__setattr__(self, name, value)

    @property
    def _properties(self) -> "HwpxOxmlSectionProperties":
        """The properties of the section holding the header or footer now. Its control sits in a body
        paragraph, and once that paragraph moved to another section the story is that section's: an
        edit through an object taken before the move marked the section it was taken from, so the
        change was reported and not saved."""

        from ._paragraph_text_edit import live_holder

        held = self._held_properties
        section = live_holder(self.element, held.section)
        if section is not held.section and hasattr(section, "properties"):
            self._held_properties = held = section.properties
        return held

    @property
    def apply_element(self) -> ET.Element | None:
        """Return the corresponding ``<hp:headerApply>``/``<hp:footerApply>`` element."""

        return self._apply_element

    def _control_copy(self) -> ET.Element | None:
        """The one ``hp:ctrl`` copy of this ``hp:secPr`` story (same id and page type), if any."""

        if all(child is not self.element for child in self._properties.element):
            return None
        copies = _control_story_index(self._properties.section.element).get(_pair_key(self.element), [])
        return copies[0] if len(copies) == 1 else None

    @property
    def id(self) -> str | None:
        """Return the identifier assigned to the header/footer element."""

        return self.element.get("id")

    @id.setter
    def id(self, value: str | None) -> None:
        copy = self._control_copy()
        if value is None:
            changed = False
            if "id" in self.element.attrib:
                del self.element.attrib["id"]
                changed = True
            if copy is not None and "id" in copy.attrib:
                del copy.attrib["id"]
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
        if copy is not None:
            copy.set("id", new_value)
        if self._update_apply_reference(new_value):
            changed = True
        if changed:
            self._properties.section.mark_dirty()

    @property
    def page_type(self) -> str:
        """The pages this header/footer is drawn on (``applyPageType``): ``BOTH``, ``EVEN``, ``ODD``,
        ``FIRST`` or ``LAST``, the name ``doc.page.set_header(page_type=...)`` uses.

        Setting it moves the header/footer to other pages: the story, its apply element and its
        control copy all take the value.
        """

        value = self.element.get("applyPageType")
        if value is not None:
            return value
        if self._apply_element is not None:
            return self._apply_element.get("applyPageType", "BOTH")
        return "BOTH"

    @page_type.setter
    def page_type(self, value: str) -> None:
        copy = self._control_copy()
        changed = False
        if self.element.get("applyPageType") != value:
            self.element.set("applyPageType", value)
            changed = True
        if self._apply_element is not None and self._apply_element.get("applyPageType") != value:
            self._apply_element.set("applyPageType", value)
            changed = True
        if copy is not None and copy.get("applyPageType") != value:
            copy.set("applyPageType", value)
            changed = True
        if changed and value == "BOTH":
            # the control Hancom reads: the copy, or the story itself when it exists only as a control
            _place_both_first(self._properties.section.element, copy if copy is not None else self.element)
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
        known = size.drawn_width is not None and margins.left is not None and margins.right is not None
        text_width = max(size.drawn_width - margins.left - margins.right, 0) if known else 0  # type: ignore[operator]
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
            paragraph_attrs = paragraph_attributes(_paragraph_id(self._properties.section._ids))
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

        return "".join(_text_element_content(node) for node in self.element.findall(f".//{_HP}t"))

    @text.setter
    def text(self, value: str) -> None:
        # Not text: refused before the old content goes (it went first, and the refusal left the
        # header or footer empty).
        _require_text(value)
        # Replace existing content with a simple paragraph (the notes in it leave the count).
        self._remove_sublists()
        # A tab becomes an hp:tab inside hp:t, as Hancom writes it.
        set_text_with_tabs(self._ensure_text_element(), value)
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
        if not any(self.element is s for s in self._properties.element.findall(f"{_HP}{kind}")):
            _set_control_story_text(self.element, self._properties, value)
            return
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
            control = run.makeelement(f"{_HP}ctrl", {})
            run.insert(story_control_index(run), control)
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

    def _remove_sublists(self) -> bool:
        from .note_authoring import note_kinds_in_all, renumber_note_kinds

        section = self._properties.section
        gone = [child for child in self.element if child.tag == f"{_HP}subList"]
        note_kinds = note_kinds_in_all(section, gone)  # notes in the text that goes: the rest count again
        for child in gone:
            self.element.remove(child)
        renumber_note_kinds(section, note_kinds)
        return bool(gone)

    def clear_content(self) -> None:
        """Remove existing rich/plain content while keeping header/footer linkage.

        One empty paragraph stays: Hancom cannot open a document with a header or
        footer that has no ``hp:subList``.
        """

        self._remove_sublists()
        set_text_with_tabs(self._ensure_text_element(), "")
        self._properties.section.mark_dirty()

    @property
    def paragraphs(self) -> tuple["HwpxOxmlParagraph", ...]:
        """The paragraphs of this header/footer, like ``cell.paragraphs``."""

        from .paragraph import HwpxOxmlParagraph

        sublist = self.element.find(f"{_HP}subList")
        if sublist is None:
            return ()
        section = self._properties.section
        return tuple(HwpxOxmlParagraph(element, section) for element in sublist.findall(f"{_HP}p"))

    @property
    def kind(self) -> str:
        """``"header"`` or ``"footer"``."""

        return _story_kind(self.element)

    def add_paragraph(
        self,
        text: str = "",
        *,
        style: "int | str | Style | None" = None,
        para_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph (with *text*, if given) and return it as a paragraph object.

        ``style`` (a name, a numeric id or a ``Style``) gives the paragraph that style and its
        paragraph and character shapes unless they are passed; ``para_pr_id_ref`` and
        ``char_pr_id_ref`` name the shapes directly, as every ``add_paragraph`` takes them. The
        rest is a property of the returned paragraph (``p.alignment = "CENTER"``; 7.0 took away
        ``align=``). Up to 6.x this returned the bare ``hp:p`` element and took no text.
        """

        _require_text(text)  # not text: refused before anything is written
        from .paragraph import HwpxOxmlParagraph
        from .section import style_shape_refs

        section = self._properties.section
        style_id_ref, para_pr_id_ref, char_pr_id_ref = style_shape_refs(
            section.document, style, para_pr_id_ref, char_pr_id_ref
        )
        element = self._append_paragraph_element()
        if para_pr_id_ref is not None:
            element.set("paraPrIDRef", str(para_pr_id_ref))
        if style_id_ref is not None:
            element.set("styleIDRef", str(style_id_ref))
        if text or char_pr_id_ref is not None:
            run = _append_child(element, f"{_HP}run", {"charPrIDRef": str(char_pr_id_ref or "0")})
            set_text_with_tabs(_append_child(run, f"{_HP}t"), text)
            _clear_paragraph_layout_cache(element)
        return HwpxOxmlParagraph(element, section)

    def _append_paragraph_element(self, *, align: str | None = None) -> ET.Element:
        """Append an empty paragraph to the header/footer subList."""

        sublist = self._ensure_sublist()
        paragraph_attrs = paragraph_attributes(_paragraph_id(self._properties.section._ids))
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
            paragraph = self._append_paragraph_element()
        return paragraph

    def add_run(
        self,
        text: str,
        *,
        paragraph: "HwpxOxmlParagraph | ET.Element | None" = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        color: str | None = None,
        font: str | None = None,
        size: int | float | None = None,
        highlight: str | None = None,
        strike: bool | None = None,
    ) -> "HwpxOxmlRun":
        """Append a text run to a header/footer paragraph and return it as a run object.

        *paragraph* is one of :attr:`paragraphs` (or its element); by default the first.
        Up to 6.x this returned the bare ``hp:run`` element.
        """

        _require_text(text)  # not text: refused before anything is written
        from .paragraph import HwpxOxmlParagraph
        from .run import HwpxOxmlRun

        target = self._paragraph_element(paragraph)
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
        set_text_with_tabs(_append_child(run, f"{_HP}t"), text)
        _clear_paragraph_layout_cache(target)
        self._properties.section.mark_dirty()
        return HwpxOxmlRun(run, HwpxOxmlParagraph(target, self._properties.section))

    def _paragraph_element(self, paragraph: "HwpxOxmlParagraph | ET.Element | None") -> ET.Element:
        if paragraph is None:
            return self._ensure_content_paragraph()
        held = getattr(paragraph, "element", None)
        element = cast(ET.Element, paragraph if held is None else held)
        if not any(node is element for node in self.element.iter(f"{_HP}p")):
            from ..errors import HwpxValueError

            raise HwpxValueError(
                "the paragraph is not in this header/footer",
                code="story-paragraph-not-here",
                suggestion="Pass one of this header/footer's own paragraphs (story.paragraphs).",
            )
        return element

    def add_page_number_field(
        self,
        *,
        paragraph: "HwpxOxmlParagraph | ET.Element | None" = None,
        format: str = "page",
        position: str = "BOTTOM_CENTER",
        format_type: str | None = None,
    ) -> "HwpxOxmlInlineObject":
        """Append the corpus-observed automatic page-number control.

        Returns the page-number control (``hp:pageNum``) as an inline object; up to 6.x
        the bare element.
        """

        from .objects import HwpxOxmlInlineObject
        from .paragraph import HwpxOxmlParagraph

        target = self._paragraph_element(paragraph)
        normalized_format = str(format_type or format or "DIGIT").strip().upper()
        # ``format`` also names the display ("page", "page/total"); those count in digits.
        page_format_type = number_format("DIGIT" if normalized_format in {"PAGE", "PAGE/TOTAL"} else normalized_format)
        auto_run = _append_child(target, f"{_HP}run", {"charPrIDRef": "0"})
        auto_ctrl = _append_child(auto_run, f"{_HP}ctrl", {})
        _append_auto_number(auto_ctrl, "PAGE", page_format_type)
        run = _append_child(target, f"{_HP}run", {"charPrIDRef": "0"})
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        page_number = _append_child(
            ctrl,
            f"{_HP}pageNum",
            {"pos": position, "formatType": page_format_type, "sideChar": "-"},
        )
        _clear_paragraph_layout_cache(target)
        self._properties.section.mark_dirty()
        return HwpxOxmlInlineObject(page_number, HwpxOxmlParagraph(target, self._properties.section))

    def _add_total_page_counter(self, paragraph: ET.Element, format_type: str = "DIGIT") -> None:
        """Append the total-page counter of a "page/total" field.

        Hancom's own page/total headers and footers put
        ``hp:autoNum numType="TOTAL_PAGE"`` after the "/"; a second PAGE
        counter drew "1/1, 2/2, 3/3" on a three-page document. The position
        control (``hp:pageNum``) belongs to the page counter only, so none is
        added here. The total takes the page counter's number format.
        """

        run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        ctrl = _append_child(run, f"{_HP}ctrl", {})
        _append_auto_number(ctrl, "TOTAL_PAGE", format_type)
        _clear_paragraph_layout_cache(paragraph)
        self._properties.section.mark_dirty()

    def set_content(self, content: Sequence[Mapping[str, Any]]) -> None:
        """Replace header/footer content with paragraph/run/page-number specs.

        A value that is refused (a colour, a page number format, ...) leaves the
        header/footer as it was.
        """

        self._check_content(content)
        # What is there now, as it is: the same nodes go back if writing still fails, so a paragraph or
        # run object taken before keeps writing into the document. Copies went back before, and an edit
        # through such an object was then reported and not saved.
        attributes, text, children = dict(self.element.attrib), self.element.text, list(self.element)
        try:
            self._fill_content(content)
        except Exception:
            self.element.attrib.clear()
            self.element.attrib.update(attributes)
            self.element.text = text
            for child in list(self.element):
                self.element.remove(child)
            self.element.extend(children)
            # the notes that went with the old content were counted out; they are back
            from .note_authoring import note_kinds_in, renumber_note_kinds

            renumber_note_kinds(self._properties.section, note_kinds_in(children))
            raise

    @staticmethod
    def _check_content(content: Sequence[Mapping[str, Any]]) -> None:
        """Everything :meth:`_fill_content` refuses, checked for the whole of *content* before the first
        paragraph is written: the kind of each child, a run's colours, size and font, a page number's
        format, a paragraph's alignment. A later child refused used to leave what the earlier ones had
        declared (a character shape for a sized run) in the header of the document."""

        from .color import normalize_color
        from .header_fonts import check_run_fonts, check_run_size
        from .header_part import HwpxOxmlHeader

        for paragraph_spec in content:
            align = paragraph_spec.get("align")
            if align:
                HwpxOxmlHeader._normalize_paragraph_alignment(str(align))
            children = paragraph_spec.get("children")
            if children is None:
                children = paragraph_spec.get("runs")
            for child in children or ():
                page_number_format = child.get("page_number")
                kind = "page_number" if page_number_format is not None else str(child.get("type", "run"))
                if kind == "run":
                    for key in ("color", "highlight"):
                        if child.get(key) is not None:
                            normalize_color(child.get(key))
                    check_run_size(child.get("size"))
                    check_run_fonts(child.get("font"), None)
                elif kind == "page_number":
                    page_format = str(page_number_format or child.get("format", "page"))
                    chosen = str(child.get("formatType") or child.get("format_type") or page_format or "DIGIT")
                    chosen = chosen.strip().upper()
                    number_format("DIGIT" if chosen in {"PAGE", "PAGE/TOTAL"} else chosen)
                else:
                    raise _unsupported_content(kind)

    def _fill_content(self, content: Sequence[Mapping[str, Any]]) -> None:
        if not content:
            self.clear_content()
            return
        self._remove_sublists()
        self._properties.section.mark_dirty()
        for paragraph_spec in content:
            paragraph = self._append_paragraph_element(align=paragraph_spec.get("align"))
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
                    page_number = self.add_page_number_field(
                        paragraph=paragraph,
                        format=page_format,
                        position=str(child.get("position", "BOTTOM_CENTER")),
                        format_type=child.get("formatType") or child.get("format_type"),
                    )
                    if page_format == "page/total":
                        self.add_run("/", paragraph=paragraph)
                        self._add_total_page_counter(paragraph, page_number.element.get("formatType") or "DIGIT")
                    continue
                raise _unsupported_content(kind)

def _unsupported_content(kind: str) -> Exception:
    from ..errors import HwpxValueError

    return HwpxValueError(
        f"unsupported header/footer content type: {kind}",
        code="story-content-type-unsupported",
        context={"requested": kind},
        suggestion='Use {"text": ...} for a run or {"page_number": "page"} for a page number.',
    )


def _append_auto_number(ctrl: ET.Element, num_type: str, format_type: str) -> ET.Element:
    """Append ``hp:autoNum`` with its number format, as Hancom writes it.

    Hancom draws the number from the ``hp:autoNum`` itself and reads its shape
    from the ``hp:autoNumFormat`` child; without one it draws plain digits,
    whatever the neighbouring ``hp:pageNum@formatType`` says.
    """
    auto = _append_child(ctrl, f"{_HP}autoNum", {"num": "1", "numType": num_type})
    _append_child(
        auto,
        f"{_HP}autoNumFormat",
        {"type": format_type, "userChar": "", "prefixChar": "", "suffixChar": "", "supscript": "0"},
    )
    return auto


__all__ = ["HwpxOxmlSectionHeaderFooter"]
