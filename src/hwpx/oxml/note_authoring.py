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

from typing import TYPE_CHECKING, Any, Sequence, cast
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _require_text,
    paragraph_attributes,
    _HP,
    _append_child,
    _clear_paragraph_layout_cache,
    _default_sublist_attributes,
    _object_id,
)
from ._paragraph_text_edit import set_text_with_tabs
from .memo import HwpxOxmlNote

if TYPE_CHECKING:
    from ..objects.results import NumberRestart
    from .paragraph import HwpxOxmlParagraph
    from .section import HwpxOxmlSection

_NOTE_STYLE_NAMES = {"footNote": ("각주", "Footnote"), "endNote": ("미주", "Endnote")}
_NOTE_STYLE_FALLBACK = {"footNote": ("15", "10", "3"), "endNote": ("16", "10", "3")}


def _paragraph_note_style_refs(self: "HwpxOxmlParagraph", tag: str) -> tuple[str, str, str]:
    """(styleIDRef, paraPrIDRef, charPrIDRef) for the note body paragraph.

    Real Hancom puts note bodies on the 각주/미주 paragraph styles. Resolve
    by style name from the header so documents with re-numbered styles stay
    correct.

    A document without that style (one made from a single-style template, some exam forms) gets the
    note body on its first style and that style's shapes, or on the host paragraph's when the header
    has no style at all: the fixed template ids (style 15, shapes 10 and 3) name nothing there, or name
    another style (an outline level). They are used only when there is no header to look in.
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
    looked = False
    for header in headers:
        styles = getattr(header, "_styles_element", None)
        container = cast("ET.Element | None", styles() if callable(styles) else None)
        if container is None:
            continue
        looked = True
        first = next((style for style in container if style.get("id") is not None), None)
        if first is not None and first.get("paraPrIDRef") is not None and first.get("charPrIDRef") is not None:
            return (first.get("id") or "0", first.get("paraPrIDRef") or "0", first.get("charPrIDRef") or "0")
    if looked or headers:
        host = self.element
        run = host.find(f"{_HP}run")
        return (
            host.get("styleIDRef") or "0",
            host.get("paraPrIDRef") or "0",
            (run.get("charPrIDRef") if run is not None else None) or "0",
        )
    return _NOTE_STYLE_FALLBACK[tag]


def _paragraph_note_number_format(self: "HwpxOxmlParagraph", tag: str) -> dict[str, str]:
    """The number shape of a new note: its section's ``{tag}Pr/autoNumFormat``, as Hancom copies it.

    Hancom writes a note's own ``hp:autoNum`` format as its section's note number shape (140 of the
    140 notes of the Hancom-saved fixtures, and a footnote Hancom 2024 inserted under a section
    numbering them ``[i`` in superscript: ``type="ROMAN_SMALL" prefixChar="[" suffixChar=""
    supscript="1"``). A section without one numbers them ``1)``: digits, ``)`` after, not raised.
    """

    shape = {"type": "DIGIT", "userChar": "", "prefixChar": "", "suffixChar": ")", "supscript": "0"}
    properties = self.section._section_properties_element()
    pr = properties.find(f"{_HP}{tag}Pr") if properties is not None else None
    fmt = pr.find(f"{_HP}autoNumFormat") if pr is not None else None
    if fmt is not None:
        for name in ("type", "userChar", "prefixChar", "suffixChar"):
            value = fmt.get(name)
            if value is not None:
                shape[name] = value
        # written as Hancom writes it in a note, 1 or 0 (a section may say true/false)
        shape["supscript"] = "1" if (fmt.get("supscript") or "").strip().lower() in ("1", "true") else "0"
    return shape


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
    offset: int | None = None,
) -> HwpxOxmlNote:
    """Insert a ``<hp:footNote>`` or ``<hp:endNote>`` element.

    *offset* (``None``: the end) puts it at that character of ``paragraph.text``: after the controls already
    there, before the character -- in the middle of a run's text between two ``hp:t`` of that run, as Hancom
    writes one (``mid_text_footnote``, ``mid_text_endnote``).

    Emits the real-Hancom shape (gold-reversed): the note element is
    wrapped in ``<hp:ctrl>`` inside a body run, carries ``number`` and
    ``suffixChar``, and its body paragraph uses the 각주/미주 style with a
    leading ``<hp:autoNum>`` control — without these real Hancom does not
    render the note at all.
    """

    _require_text(text)  # not text: refused before anything is written
    from ._paragraph_text_edit import require_in_document

    require_in_document(self, caller="add_note")
    if not hasattr(self.section, "_section_properties_element"):
        # A master page: no Hancom-saved document shows a footnote or an endnote on one, and the note's
        # number format is its section's. It raised AttributeError here.
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "a footnote or an endnote goes into the body, a cell, a text box or a caption; not a master page",
            code="paragraph-move-place-unsupported",
            context={"box": "master_page"},
            suggestion="Add the note to a paragraph of the body.",
        )
    if offset is not None:
        from .text_ranges import _check_offset

        offset = _check_offset("offset", offset, 0, len(self.text))
    number = _paragraph_next_note_number(self, tag)
    number_shape = _paragraph_note_number_format(self, tag)
    style_ref, para_pr_ref, note_char_ref = _paragraph_note_style_refs(self, tag)
    if char_pr_id_ref is not None:
        note_char_ref = str(char_pr_id_ref)

    runs = self._run_elements()
    if run_attributes is None and runs:
        run = runs[-1]
    else:
        run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
    ctrl = _append_child(run, f"{_HP}ctrl", {})
    # the characters around the number as character codes, each only when the section has one
    # (Hancom writes ``number="1" suffixChar="41"`` for ``1)``, ``prefixChar="91"`` for ``[``, none for ``1``)
    note_attributes = {"number": str(number)}
    for name in ("prefixChar", "suffixChar"):
        if number_shape[name]:
            note_attributes[name] = str(ord(number_shape[name][0]))
    note_attributes["instId"] = _object_id(self.section._ids)
    note_element = _append_child(ctrl, f"{_HP}{tag}", note_attributes)
    sublist_attrs = _default_sublist_attributes()
    sublist_attrs["vertAlign"] = "TOP"
    sublist = _append_child(note_element, f"{_HP}subList", sublist_attrs)
    p_attrs = paragraph_attributes("0", paraPrIDRef=para_pr_ref, styleIDRef=style_ref)
    paragraph = _append_child(sublist, f"{_HP}p", p_attrs)
    note_run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": note_char_ref})
    num_ctrl = _append_child(note_run, f"{_HP}ctrl", {})
    auto_num = _append_child(
        num_ctrl,
        f"{_HP}autoNum",
        {"num": str(number), "numType": "FOOTNOTE" if tag == "footNote" else "ENDNOTE"},
    )
    _append_child(auto_num, f"{_HP}autoNumFormat", number_shape)
    set_text_with_tabs(_append_child(note_run, f"{_HP}t", {}), text)
    if offset is not None:
        from .text_ranges import drop_if_empty, put_at

        put_at(self.element, offset, ctrl)
        drop_if_empty(self.element, run)
    _clear_paragraph_layout_cache(self.element)  # the note's control takes room in the text: laid out again
    self.section.mark_dirty()
    # A note added before others takes their place in the count: those after it move up one.
    renumber_notes(self.section, tag)
    return HwpxOxmlNote(note_element, self)


def _paragraph_add_footnote(
    self: "HwpxOxmlParagraph",
    text: str,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
    offset: int | None = None,
) -> HwpxOxmlNote:
    """Insert a footnote at the end of this paragraph (*offset*: at that character)."""
    return _paragraph_add_note(self, "footNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
                               offset=offset)


def _paragraph_add_endnote(
    self: "HwpxOxmlParagraph",
    text: str,
    *,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
    offset: int | None = None,
) -> HwpxOxmlNote:
    """Insert an endnote at the end of this paragraph (*offset*: at that character)."""
    return _paragraph_add_note(self, "endNote", text, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref,
                               offset=offset)


def _paragraph_add_number_restart(
    self: "HwpxOxmlParagraph",
    *,
    number: int = 1,
    kind: str = "PAGE",
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "NumberRestart":
    """Insert ``<hp:ctrl><hp:newNum num="..." numType="..."/></hp:ctrl>`` and return it as the
    :class:`~hwpx.objects.NumberRestart` ``doc.page.number_restarts`` reads.

    Restarts the running count *kind* (``PAGE`` by default) at *number*
    from this paragraph onward — real corpus (hwpxlib_corpus, 7+ files)
    always self-closes ``hp:newNum`` with only ``num``/``numType``, even
    though the schema (``ParaList XML schema.xml:2741-2759``) declares a
    required ``autoNumFormat`` child; matching real Hancom output takes
    priority over the schema here.
    """

    from ..objects.results import NumberRestart
    from ._document_primitives import NEW_NUM_KINDS, _normalize_enum_attr
    from .section_format import validate_new_number

    normalized_kind = _normalize_enum_attr(kind or "PAGE", NEW_NUM_KINDS, label="kind")
    number = validate_new_number(number)  # before its run is added
    run = self._create_run_for_object(run_attributes, char_pr_id_ref=char_pr_id_ref)
    ctrl = _append_child(run, f"{_HP}ctrl", {})
    _append_child(
        ctrl, f"{_HP}newNum", {"num": str(number), "numType": normalized_kind},
    )
    self.section.mark_dirty()
    # A restart of footnote or endnote numbers: the notes after it are written with their new numbers
    # (they kept the old ones, so the file said 1 for the note read as 7).
    renumber_note_kinds(self.section, note_kinds_in_document(self.section, ctrl))
    return NumberRestart(kind=normalized_kind, number=number, paragraph=self)


# The name it had as a method of the paragraph class, before it moved here beside the numbering.
_paragraph_add_number_restart.__name__ = "add_number_restart"
_paragraph_add_number_restart.__qualname__ = "HwpxOxmlParagraph.add_number_restart"


def _direct_notes(paragraph: ET.Element, tag: str) -> list[ET.Element]:
    """The notes of kind *tag* this paragraph holds itself, in order: Hancom's
    ``hp:run/hp:ctrl/hp:footNote`` and the ``hp:run/hp:footNote`` older python-hwpx
    wrote. A note in a table cell or text box of the paragraph belongs to that
    cell's or box's own paragraph."""

    found: list[ET.Element] = []
    for run in paragraph:
        if run.tag != f"{_HP}run":
            continue
        for child in run:
            if child.tag == f"{_HP}{tag}":
                found.append(child)
            elif child.tag == f"{_HP}ctrl":
                found.extend(note for note in child if note.tag == f"{_HP}{tag}")
    return found


def _paragraph_footnotes(self: "HwpxOxmlParagraph") -> tuple[HwpxOxmlNote, ...]:
    """The footnotes this paragraph holds (not those in its tables or boxes), in order."""
    return tuple(HwpxOxmlNote(el, self) for el in _direct_notes(self.element, "footNote"))


def _paragraph_endnotes(self: "HwpxOxmlParagraph") -> tuple[HwpxOxmlNote, ...]:
    """The endnotes this paragraph holds (not those in its tables or boxes), in order."""
    return tuple(HwpxOxmlNote(el, self) for el in _direct_notes(self.element, "endNote"))


_NOTE_NUM_TYPES = {"footNote": "FOOTNOTE", "endNote": "ENDNOTE"}


def note_numbers(sections: Sequence[ET.Element]) -> dict[ET.Element, int]:
    """Hancom's number of every foot and end note of the section elements *sections*.

    Each kind counts on its own, from 1, in document order. A section whose note
    numbering is ``ON_SECTION`` starts again at its ``newNum``; any other runs on
    from the section before. An ``hp:newNum`` control of the kind sets the next
    number. The numbers Hancom writes in ``number`` are these (1241 of 1241 notes
    in the public corpus, all numbered ``CONTINUOUS``).

    A section that numbers the kind ``ON_PAGE`` starts again on every page, so its
    numbers depend on a page layout this engine does not make: such a note's number
    is the ``number`` the file holds (the count when it holds none), and the count
    runs on past it. Hancom numbers such notes again when it opens the document and
    writes the per-page numbers into ``number`` and ``hp:autoNum`` when it saves
    (Hangul 2024: notes stored as 1..6, or all as 7, were drawn and saved as
    1, 2, 1, 2, 1, 2 on three pages), so the number held is the one of the last
    Hancom save.
    """

    return {note: number for notes in _notes_counted(sections) for note, number in notes}


def _notes_counted(sections: Sequence[ET.Element]) -> list[list[tuple[ET.Element, int]]]:
    """For each of *sections*, its notes in document order with their numbers (:func:`note_numbers`)."""

    counters = {"FOOTNOTE": 1, "ENDNOTE": 1}
    counted: list[list[tuple[ET.Element, int]]] = []
    for section in sections:
        numbers: list[tuple[ET.Element, int]] = []
        counted.append(numbers)
        per_page = set(_kinds_numbered_per_page(section))
        sec_pr = next(section.iter(f"{_HP}secPr"), None)
        for tag, kind in _NOTE_NUM_TYPES.items():
            properties = sec_pr.find(f"{_HP}{tag}Pr") if sec_pr is not None else None
            numbering = properties.find(f"{_HP}numbering") if properties is not None else None
            if numbering is not None and numbering.get("type") == "ON_SECTION":
                counters[kind] = _int_or(numbering.get("newNum"), 1)
        wanted = (f"{_HP}newNum", f"{_HP}footNote", f"{_HP}endNote")
        search: Any = section.iter
        found = search(*wanted) if hasattr(section, "getparent") else (  # lxml finds them by tag
            node for node in section.iter() if node.tag in wanted)
        for element in found:
            if element.tag == f"{_HP}newNum":
                if element.get("numType") in counters:
                    counters[element.get("numType") or ""] = _int_or(element.get("num"), 1)
                continue
            tag = _element_local(element)
            kind = _NOTE_NUM_TYPES[tag]
            numbers.append((element, _int_or(element.get("number"), counters[kind]) if tag in per_page
                            else counters[kind]))
            counters[kind] += 1
    return counted


def _kinds_numbered_per_page(section: ET.Element) -> list[str]:
    """The note kinds (``footNote``/``endNote``) *section* numbers ``ON_PAGE``."""

    sec_pr = next(section.iter(f"{_HP}secPr"), None)
    kinds = []
    for tag in _NOTE_NUM_TYPES:
        properties = sec_pr.find(f"{_HP}{tag}Pr") if sec_pr is not None else None
        numbering = properties.find(f"{_HP}numbering") if properties is not None else None
        if numbering is not None and numbering.get("type") == "ON_PAGE":
            kinds.append(tag)
    return kinds


def _int_or(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _element_local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def _sections_of(section: "HwpxOxmlSection") -> list["HwpxOxmlSection"]:
    document = section.document
    return list(document.sections) if document is not None else [section]


def _note_numbering_type(section: "HwpxOxmlSection", tag: str) -> str | None:
    """How the section numbers notes of kind *tag*: ``CONTINUOUS``, ``ON_SECTION``, ``ON_PAGE`` or
    ``None`` when it does not say. Read from the section's properties, which it keeps at hand: looking
    for ``hp:secPr`` in the tree each time walked a long first paragraph."""

    sec_pr = section.properties.element
    top: Any = sec_pr
    while hasattr(top, "getparent") and (parent := top.getparent()) is not None:
        top = parent
    if not hasattr(top, "getparent") or top is not section.element:
        # the properties kept at hand are of a paragraph that was replaced (paragraph.apply_model): the
        # ones in the tree now
        found = section._section_properties_element()
        if found is None:
            return None
        sec_pr = found
    properties = sec_pr.find(f"{_HP}{tag}Pr") if sec_pr is not None else None
    numbering = properties.find(f"{_HP}numbering") if properties is not None else None
    return numbering.get("type") if numbering is not None else None


def renumber_notes(section: "HwpxOxmlSection", tag: str) -> None:
    """Write Hancom's numbers (:func:`note_numbers`) into the notes of kind *tag* of the
    document *section* belongs to: the note's ``number`` and the ``hp:autoNum`` its body
    starts with, where they differ. A note whose number changes its count of digits
    drops its paragraph's line cache, as its mark changes width.

    A section that numbers the kind ``ON_PAGE`` is left alone: those numbers start again on each
    page, which this engine does not lay out. So are the sections after it whose count runs on from
    it, up to the next section that starts the count again (``ON_SECTION``). The numbers already
    written there stay as they are; a note added there carries its count in the document. Hancom
    numbers them again per page when it opens the document and writes those numbers when it saves
    (Hangul 2024), so what is written there does not change what Hancom draws. Every other section
    is numbered as in any document."""

    sections = _sections_of(section)
    known = True  # the count is known up to here: from the start, or from a section that starts it again
    written: list["HwpxOxmlSection"] = []
    for owner in sections:
        numbering = _note_numbering_type(owner, tag)
        if numbering == "ON_PAGE":
            known = False
        elif numbering == "ON_SECTION":
            known = True
        if known:  # per page, or running on from a section numbered per page: what is written stays
            written.append(owner)
    if not written:
        return  # every section numbered per page: nothing to count for
    # one walk through each section finds the notes and counts them
    counted = _notes_counted([owner.element for owner in sections])
    for owner, notes in zip(sections, counted):
        if not any(owner is one for one in written):
            continue
        changed = False
        for note, counted_number in notes:
            if note.tag != f"{_HP}{tag}":
                continue
            number = str(counted_number)
            old = note.get("number")
            if old is not None and old != number:
                note.set("number", number)
                changed = True
                if len(old) != len(number):
                    host = _host_paragraph(owner.element, note)
                    if host is not None:
                        _clear_paragraph_layout_cache(host)
            for auto_num in note.iter(f"{_HP}autoNum"):
                if auto_num.get("numType") != _NOTE_NUM_TYPES[tag]:
                    continue  # another kind of number in the note's text (a page number): not its mark
                # an hp:autoNum without ``num`` reads as 1 (the schema's default)
                if auto_num.get("num", "1") != number:
                    auto_num.set("num", number)
                    changed = True
                break
        if changed:
            owner.mark_dirty()


def renumber_notes_holding(section: "HwpxOxmlSection", elements: "Sequence[ET.Element]") -> None:
    """After *elements* (paragraphs, tables, objects or rows copied or moved) went into the document of
    *section*: write the numbers of the kinds of note they hold again, in document order, as a note copied
    with ``note.copy_to`` or a range with ``copy_range`` gets them (:func:`renumber_notes`). A copy kept the
    numbers of what it copied, so the saved numbers repeated (1, 2, 1)."""

    renumber_note_kinds(section, note_kinds_in(elements))


def note_kinds_in(elements: "Sequence[ET.Element]") -> set[str]:
    """The kinds of note (``footNote``, ``endNote``) whose numbers depend on *elements*: the notes they
    hold, and the kinds a ``hp:newNum`` in them starts counting again. A paragraph holding only such a
    restart holds no note, yet moving or copying it changes the number of every note after it."""

    kinds: set[str] = set()
    restarted = {num_type: tag for tag, num_type in _NOTE_NUM_TYPES.items()}
    wanted = (f"{_HP}footNote", f"{_HP}endNote", f"{_HP}newNum")
    for element in elements:
        # by tag, so that a long text without notes is not walked node by node
        search: Any = element.iter
        found = search(*wanted) if hasattr(element, "getparent") else (  # lxml takes several tags
            node for node in element.iter() if node.tag in wanted)
        for node in found:
            name = _element_local(node)
            if name in _NOTE_NUM_TYPES:
                kinds.add(name)
            elif node.get("numType") in restarted:
                kinds.add(restarted[str(node.get("numType"))])
    return kinds


def note_kinds_in_document(section: "HwpxOxmlSection", element: ET.Element) -> set[str]:
    """:func:`note_kinds_in` *element* while it is in the document of *section*; nothing for an element
    already taken out (in a removed section, or in a table, note or text box taken out): its notes are not
    among the document's, so taking it apart further must not number the document's notes again."""

    from ._paragraph_text_edit import in_document

    kinds = note_kinds_in((element,))  # first: most removals hold no note, and need no look at the document
    return kinds if kinds and in_document(element, section) else set()


def note_kinds_in_all(section: "HwpxOxmlSection", elements: "Sequence[ET.Element]") -> set[str]:
    """:func:`note_kinds_in_document` of each of *elements*, together: what is about to be taken out."""

    kinds: set[str] = set()
    for element in elements:
        kinds |= note_kinds_in_document(section, element)
    return kinds


def renumber_note_kinds(section: "HwpxOxmlSection", kinds: "set[str]") -> None:
    for tag in sorted(kinds):
        renumber_notes(section, tag)


def _host_paragraph(root: ET.Element, element: ET.Element) -> ET.Element | None:
    """The innermost ``hp:p`` holding *element* (lxml: up the parents; else down from *root*)."""

    getparent = getattr(element, "getparent", None)
    if getparent is not None:
        node = getparent()
        while node is not None and node.tag != f"{_HP}p":
            node = node.getparent()
        return node

    def walk(node: ET.Element, nearest: ET.Element | None) -> ET.Element | None:
        if node.tag == f"{_HP}p":
            nearest = node
        for child in node:
            if child is element:
                return nearest
            found = walk(child, nearest)
            if found is not None:
                return found
        return None

    return walk(root, None)


def iter_document_notes(section: "HwpxOxmlSection", tag: str) -> list[HwpxOxmlNote]:
    """Every note of kind *tag* in the document *section* belongs to, in document order,
    those in table cells, text boxes and other notes included, each with the paragraph
    holding it."""

    from .paragraph import HwpxOxmlParagraph

    notes: list[HwpxOxmlNote] = []
    for owner in _sections_of(section):
        for element in owner.element.iter(f"{_HP}{tag}"):
            host = _host_paragraph(owner.element, element)
            if host is not None:
                notes.append(HwpxOxmlNote(element, HwpxOxmlParagraph(host, owner)))
    return notes


def remove_note(note: HwpxOxmlNote) -> None:
    """Take *note* out of the text: its control, the ``hp:ctrl`` it leaves empty and a run
    left empty by that. The other notes of its kind are numbered again and the paragraph
    holding it is laid out again."""

    element = note.element
    section = note.paragraph.section
    host = _host_paragraph(section.element, element)
    if host is None:
        host = note.paragraph.element
    parent = _parent(host, element)
    if parent is None:
        return
    parent.remove(element)
    run: ET.Element | None = parent
    if parent.tag == f"{_HP}ctrl" and not list(parent):
        run = _parent(host, parent)
        if run is not None:
            run.remove(parent)
    if run is not None and run.tag == f"{_HP}run" and not list(run) and len(host.findall(f"{_HP}run")) > 1:
        host.remove(run)
    _clear_paragraph_layout_cache(host)
    section.mark_dirty()
    # its kind, and the kinds of the notes in its text (a footnote in a removed endnote went with it)
    renumber_note_kinds(section, note_kinds_in((element,)))


def _parent(root: ET.Element, element: ET.Element) -> ET.Element | None:
    getparent = getattr(element, "getparent", None)
    if getparent is not None:
        return getparent()
    for node in root.iter():
        for child in node:
            if child is element:
                return node
    return None
