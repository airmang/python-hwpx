# SPDX-License-Identifier: Apache-2.0
"""Footnote/endnote (각주/미주) authoring, split out of ``paragraph.py``.

6.14 트레인㊾-3 -- ``paragraph.py``'s owner file sat at exactly 1600 lines
(zero headroom, flagged as a chip in 6.13 트레인㊼ when the date/proofreading
field delegators landed). Same escape valve ``dutmal_compose.py``/
``objects.py``/``field_marks.py`` already established: these methods attach
to ``HwpxOxmlParagraph`` as plain class-attribute assignments in
``paragraph.py`` (``add_footnote = _paragraph_add_footnote``, etc, plus
``footnotes``/``endnotes`` wrapped in ``property()``) rather than living as
inline method bodies there.

No behavior change -- this is a pure move. The functions are copied
verbatim except ``self._NOTE_STYLE_NAMES``/``self._NOTE_STYLE_FALLBACK``
(class attributes on ``HwpxOxmlParagraph``) become plain module-level
constants here, referenced directly instead of through ``self``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _DEFAULT_PARAGRAPH_ATTRS,
    _HP,
    _append_child,
    _default_sublist_attributes,
    _object_id,
    _sanitize_text,
)
from .memo import HwpxOxmlNote

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph

_NOTE_STYLE_NAMES = {"footNote": ("각주", "Footnote"), "endNote": ("미주", "Endnote")}
_NOTE_STYLE_FALLBACK = {"footNote": ("15", "10", "3"), "endNote": ("16", "10", "3")}


def _paragraph_note_style_refs(self: "HwpxOxmlParagraph", tag: str) -> tuple[str, str, str]:
    """(styleIDRef, paraPrIDRef, charPrIDRef) for the note body paragraph.

    Real Hancom puts note bodies on the 각주/미주 paragraph styles. Resolve
    by style name from the header so documents with re-numbered styles stay
    correct; fall back to the fixed template coordinates.
    """

    korean, english = _NOTE_STYLE_NAMES[tag]
    document = self.section.document
    headers = cast(
        "Sequence[object]",
        getattr(document, "_headers", []) if document is not None else [],
    )
    for header in headers:
        styles = getattr(header, "_styles_element", None)
        container = cast(
            "ET.Element | None", styles() if callable(styles) else None
        )
        if container is None:
            continue
        for style in container:
            if style.get("name") == korean or style.get("engName") == english:
                return (
                    style.get("id") or _NOTE_STYLE_FALLBACK[tag][0],
                    style.get("paraPrIDRef") or _NOTE_STYLE_FALLBACK[tag][1],
                    style.get("charPrIDRef") or _NOTE_STYLE_FALLBACK[tag][2],
                )
    return _NOTE_STYLE_FALLBACK[tag]


def _paragraph_note_suffix_char(self: "HwpxOxmlParagraph", tag: str) -> str:
    """The note suffix character from secPr, defaulting to ")"."""

    properties = self.section._section_properties_element()
    if properties is not None:
        pr = properties.find(f"{_HP}{tag}Pr")
        if pr is not None:
            fmt = pr.find(f"{_HP}autoNumFormat")
            if fmt is not None and fmt.get("suffixChar"):
                return fmt.get("suffixChar", ")")
    return ")"


def _paragraph_next_note_number(self: "HwpxOxmlParagraph", tag: str) -> int:
    """Document-continuous note number, counted per note type."""

    document = self.section.document
    sections = document.sections if document is not None else [self.section]
    count = 0
    for section in sections:
        count += sum(1 for _ in section.element.iter(f"{_HP}{tag}"))
    return count + 1


def _paragraph_add_note(
    self: "HwpxOxmlParagraph",
    tag: str,
    text: str,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlNote:
    """Insert a ``<hp:footNote>`` or ``<hp:endNote>`` element.

    Emits the real-Hancom shape (gold-reversed): the note element is
    wrapped in ``<hp:ctrl>`` inside a body run, carries ``number`` and
    ``suffixChar``, and its body paragraph uses the 각주/미주 style with a
    leading ``<hp:autoNum>`` control — without these real Hancom does not
    render the note at all.
    """

    number = _paragraph_next_note_number(self, tag)
    suffix = _paragraph_note_suffix_char(self, tag)
    style_ref, para_pr_ref, note_char_ref = _paragraph_note_style_refs(self, tag)
    if char_pr_id_ref is not None:
        note_char_ref = str(char_pr_id_ref)

    runs = self._run_elements()
    if run_attributes is None and runs:
        run = runs[-1]
    else:
        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
    ctrl = _append_child(run, f"{_HP}ctrl", {})
    note_element = _append_child(
        ctrl,
        f"{_HP}{tag}",
        {
            "number": str(number),
            "suffixChar": str(ord(suffix[0])) if suffix else "41",
            "instid": _object_id(),
        },
    )
    sublist_attrs = _default_sublist_attributes()
    sublist_attrs["vertAlign"] = "TOP"
    sublist = _append_child(note_element, f"{_HP}subList", sublist_attrs)
    p_attrs = dict(_DEFAULT_PARAGRAPH_ATTRS)
    p_attrs.update({"id": "0", "paraPrIDRef": para_pr_ref, "styleIDRef": style_ref})
    paragraph = _append_child(sublist, f"{_HP}p", p_attrs)
    note_run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": note_char_ref})
    num_ctrl = _append_child(note_run, f"{_HP}ctrl", {})
    auto_num = _append_child(
        num_ctrl,
        f"{_HP}autoNum",
        {"num": str(number), "numType": "FOOTNOTE" if tag == "footNote" else "ENDNOTE"},
    )
    _append_child(
        auto_num,
        f"{_HP}autoNumFormat",
        {"type": "DIGIT", "userChar": "", "prefixChar": "", "suffixChar": suffix, "supscript": "0"},
    )
    t = _append_child(note_run, f"{_HP}t", {})
    t.text = _sanitize_text(text)
    self.section.mark_dirty()
    return HwpxOxmlNote(note_element, self)


def _paragraph_add_footnote(
    self: "HwpxOxmlParagraph",
    text: str,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlNote:
    """Insert a footnote at the end of this paragraph."""
    return _paragraph_add_note(self, "footNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)


def _paragraph_add_endnote(
    self: "HwpxOxmlParagraph",
    text: str,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlNote:
    """Insert an endnote at the end of this paragraph."""
    return _paragraph_add_note(self, "endNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)


def _paragraph_footnotes(self: "HwpxOxmlParagraph") -> list[HwpxOxmlNote]:
    """Return all footnotes in this paragraph."""
    return [
        HwpxOxmlNote(el, self)
        for el in self.element.findall(f".//{_HP}footNote")
    ]


def _paragraph_endnotes(self: "HwpxOxmlParagraph") -> list[HwpxOxmlNote]:
    """Return all endnotes in this paragraph."""
    return [
        HwpxOxmlNote(el, self)
        for el in self.element.findall(f".//{_HP}endNote")
    ]
