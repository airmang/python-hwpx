"""What the final review of 7.0.0 found beside the refused calls (exec7/rv4).

* The number written for a note (``number`` and the ``hp:autoNum`` its text starts with) is the number
  the engine reads, also after a paragraph's content is cleared, a text box's text is taken out or
  the numbering is started again in front of it. The file said 2 for the only note left.
* A field in a copied note, or in a paragraph copied with ``section.insert_paragraphs``, gets its own
  id pair, as one in a copied paragraph, table or range does. Two fields of one id cannot be filled.
* A 덧말 or a 글자 겹치기 taken before its range moved to another section saves what is changed
  through it, as the other objects do since #800 and #803.
* Adding a tracked change does not turn on bit 0 of ``hh:trackchageConfig@flags``. It was set "for
  display" and is not what shows the marks; with it Hancom crashed opening a document that also had a
  table of contents to make again (Hangul 12.30.0 for macOS, 2026-11-20). A document whose flags hide
  the marks is set to the value Hancom writes (56); one that shows them is left as it is.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from typing import Any

import pytest

from hwpx import HwpxDocument


def _saved(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


# -- note numbers ---------------------------------------------------------------------------------


def _written_and_read(document: HwpxDocument) -> list[tuple[str, int, str | None, str | None]]:
    """Each note of the saved document: its kind, the number read, and the two numbers written."""

    out = []
    reopened = _saved(document)
    for kind in ("footnotes", "endnotes"):
        for note in getattr(reopened.notes, kind):
            auto = note.element.find(".//{*}autoNum")
            out.append((kind, note.number, note.element.get("number"), auto.get("num") if auto is not None else None))
    return out


def _numbers_agree(document: HwpxDocument) -> None:
    notes = _written_and_read(document)
    assert notes, "the case kept no note to look at"
    wrong = [note for note in notes if (note[2], note[3]) != (str(note[1]), str(note[1]))]
    assert not wrong, f"written numbers differ from the numbers read: {wrong}"


def _with_notes() -> tuple[HwpxDocument, Any, Any, Any, Any]:
    document = HwpxDocument.new()
    first = document.add_paragraph("first paragraph")
    first.add_footnote("one")
    first.add_endnote("e-one")
    table = document.add_table(1, 1)
    table.cell(0, 0).paragraphs[0].add_footnote("in cell")
    box = document.shapes.add_rectangle(paragraph=document.add_paragraph("box"))
    box.set_draw_text("boxed")
    box.draw_text.paragraphs[0].add_footnote("in box")
    last = document.add_paragraph("last")
    last.add_footnote("keep")
    last.add_endnote("e-keep")
    return document, first, table, box, last


_NOTE_EDITS: dict[str, Callable[[HwpxDocument, Any, Any, Any, Any], Any]] = {
    "clear_content": lambda d, first, table, box, last: first.clear_content(),
    "clear_text": lambda d, first, table, box, last: first.clear_text(),
    "text": lambda d, first, table, box, last: setattr(first, "text", "new"),
    "delete_range": lambda d, first, table, box, last: first.delete_range(0, len(first.text), objects="remove"),
    "paragraph.remove": lambda d, first, table, box, last: first.remove(),
    "table.remove": lambda d, first, table, box, last: table.remove(),
    "shape.remove": lambda d, first, table, box, last: box.remove(),
    "remove_draw_text": lambda d, first, table, box, last: box.remove_draw_text(),
    "cell.text": lambda d, first, table, box, last: setattr(table.cell(0, 0), "text", "x"),
    "note.remove": lambda d, first, table, box, last: first.footnotes[0].remove(),
    "add_number_restart(footnote)": lambda d, first, table, box, last: first.add_number_restart(kind="FOOTNOTE", number=7),
    "add_number_restart(endnote)": lambda d, first, table, box, last: d.page.add_number_restart(first, number=7, kind="ENDNOTE"),
    "add_number_restart(page)": lambda d, first, table, box, last: first.add_number_restart(kind="PAGE", number=3),
    "copy_to": lambda d, first, table, box, last: first.copy_to(last),
    "move_after": lambda d, first, table, box, last: first.move_after(last),
    "table.copy_to": lambda d, first, table, box, last: table.copy_to(last),
    "to another section": lambda d, first, table, box, last: first.move_after(d.add_section().paragraphs[0]),
}


@pytest.mark.parametrize("edit", sorted(_NOTE_EDITS))
def test_the_number_written_for_a_note_is_the_number_read(edit: str) -> None:
    document, *handles = _with_notes()
    _numbers_agree(document)

    _NOTE_EDITS[edit](document, *handles)

    _numbers_agree(document)


def test_a_restart_gives_the_notes_after_it_its_number() -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("first")
    document.add_paragraph("last").add_footnote("keep")

    first.add_number_restart(kind="FOOTNOTE", number=7)

    assert _written_and_read(document) == [("footnotes", 7, "7", "7")]


def test_clearing_a_paragraph_numbers_the_note_left_as_the_first() -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("first")
    first.add_footnote("discard")
    document.add_paragraph("last").add_footnote("keep")

    first.clear_content()

    assert _written_and_read(document) == [("footnotes", 1, "1", "1")]


# -- copied fields --------------------------------------------------------------------------------


def _field_ids(document: HwpxDocument) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    begins = re.findall(r'<hp:fieldBegin id="(\d+)"', xml)
    ends = re.findall(r'<hp:fieldEnd beginIDRef="(\d+)"', xml)
    assert sorted(begins) == sorted(ends), "each begin has its end"
    return begins


def test_a_copied_note_gives_its_fields_ids_of_their_own() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("body")
    note = paragraph.add_footnote("note")
    note.paragraphs[0].add_form_field("x")
    note.paragraphs[0].add_hyperlink("https://a.example", "link")

    note.copy_to(paragraph)

    ids = _field_ids(document)
    assert len(ids) == 4 and len(set(ids)) == 4
    first, second = [field for field in _saved(document).fields.all if field.name == "x"]
    reopened = _saved(document)
    target = [field for field in reopened.fields.all if field.name == "x"][1]
    target.value = "second"
    values = [field.value for field in _saved(reopened).fields.all if field.name == "x"]
    assert values.count("second") == 1 and first.field_id != second.field_id


def test_paragraphs_inserted_as_copies_give_their_fields_ids_of_their_own() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("body")
    paragraph.add_form_field("x")

    document.sections[0].insert_paragraphs(1, [paragraph])

    ids = _field_ids(document)
    assert len(ids) == 2 and len(set(ids)) == 2
    reopened = _saved(document)
    reopened.fields.all[1].value = "second"  # was field-ambiguous: two fields of one id
    assert [field.value for field in _saved(reopened).fields.all].count("second") == 1


# -- marks that moved with their range ------------------------------------------------------------

_MARKS: dict[str, Callable[[HwpxDocument, Any], tuple[Callable[[], Any], Callable[[HwpxDocument], bool]]]] = {}


def _mark(name: str) -> Callable[[Any], Any]:
    def register(make: Any) -> Any:
        _MARKS[name] = make
        return make

    return register


@_mark("ruby.ruby_text")
def _ruby_text(document: HwpxDocument, paragraph: Any) -> Any:
    ruby = document.shapes.add_ruby("base", "old", paragraph=paragraph)
    return lambda: setattr(ruby, "ruby_text", "new"), lambda saved: saved.shapes.rubies[0].ruby_text == "new"


@_mark("ruby.text")
def _ruby_main(document: HwpxDocument, paragraph: Any) -> Any:
    ruby = document.shapes.add_ruby("base", "old", paragraph=paragraph)
    return lambda: setattr(ruby, "text", "BASE"), lambda saved: saved.shapes.rubies[0].text == "BASE"


@_mark("ruby.remove")
def _ruby_remove(document: HwpxDocument, paragraph: Any) -> Any:
    ruby = document.shapes.add_ruby("base", "old", paragraph=paragraph)
    return ruby.remove, lambda saved: len(saved.shapes.rubies) == 0


@_mark("composed.text")
def _composed_text(document: HwpxDocument, paragraph: Any) -> Any:
    composed = document.shapes.add_composed_character("12", paragraph=paragraph)
    return lambda: setattr(composed, "text", "34"), lambda saved: saved.shapes.composed_characters[0].text == "34"


@_mark("composed.remove")
def _composed_remove(document: HwpxDocument, paragraph: Any) -> Any:
    composed = document.shapes.add_composed_character("12", paragraph=paragraph)
    return composed.remove, lambda saved: len(saved.shapes.composed_characters) == 0


@pytest.mark.parametrize("mark", sorted(_MARKS))
@pytest.mark.parametrize("move", ["move_range", "move_after"])
def test_a_mark_taken_before_its_text_moved_saves_what_is_changed_through_it(mark: str, move: str) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("stays, so the section keeps a paragraph")
    paragraph = document.add_paragraph("a")
    edit, saved_has_it = _MARKS[mark](document, paragraph)
    paragraph.add_run("z")
    destination = document.add_section().paragraphs[0]
    if move == "move_range":
        paragraph.move_range(0, len(paragraph.text), to=destination)
    else:
        paragraph.move_after(destination)
    document.to_bytes()  # nothing is pending when the edit comes

    edit()

    assert saved_has_it(_saved(document))


def test_a_mark_follows_to_the_paragraph_its_range_went_to() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("a")
    ruby = document.shapes.add_ruby("base", "old", paragraph=paragraph)
    paragraph.add_run("z")
    destination = document.add_section().paragraphs[0]

    paragraph.move_range(0, len(paragraph.text), to=destination)

    assert ruby.paragraph.element is destination.element
    assert ruby.paragraph.section is document.sections[1]


# -- tracked changes and the table of contents ----------------------------------------------------


def _track_flags(document: HwpxDocument) -> str | None:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
    found = re.search(r'<hh:trackchageConfig flags="(\d+)"', header)
    return found.group(1) if found else None


@pytest.mark.parametrize("kind", ["insert", "delete", "replace"])
@pytest.mark.parametrize("order", ["change first", "contents first"])
def test_a_tracked_change_leaves_the_tracking_flags_as_they_were(kind: str, order: str) -> None:
    document = HwpxDocument.new()
    before = _track_flags(document)
    document.add_heading("1. 개요", level=1)
    paragraph = document.add_paragraph("이 문장은 고쳐질 예정입니다.")

    def change() -> None:
        if kind == "insert":
            document.tracking.insert(paragraph, " 덧붙임", author="검토자")
        elif kind == "delete":
            document.tracking.delete(paragraph, match="고쳐질", author="검토자")
        else:
            document.tracking.replace(paragraph, "고쳐질", "수정될", author="검토자")

    steps = [change, lambda: document.refs.add_table_of_contents(index=0)]
    for step in steps if order == "change first" else reversed(steps):
        step()

    assert before == "56"  # what Hancom writes, also for a document with changes (reader_writer__ChangeTrack)
    assert _track_flags(document) == before
    assert len(_saved(document).tracking.changes) >= 1


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("4", "56"), ("0", "56"), ("60", "56"), ("2", "56"), ("32", "56"),  # hidden: shown as Hancom writes it
        ("1", "57"), ("5", "57"),  # bit 0, whatever it means, stays as the document has it
        ("56", "56"), ("57", "57"), ("40", "40"),  # shown already: left alone
    ],
)
def test_a_tracked_change_is_shown_and_bit_0_is_not_turned_on(before: str, after: str) -> None:
    from hwpx.tools.redline import _track_change_display_enabled

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    header.element.find("{*}trackchageConfig").set("flags", before)
    header.mark_dirty()
    document = _saved(document)

    document.tracking.insert(document.add_paragraph("text"), " more", author="a")

    assert _track_flags(document) == after
    assert _track_change_display_enabled(_saved(document))


def test_a_document_without_the_tracking_element_gets_none() -> None:
    from hwpx.tools.redline import _track_change_display_enabled

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    header.element.remove(header.element.find("{*}trackchageConfig"))
    header.mark_dirty()
    document = _saved(document)

    document.tracking.insert(document.add_paragraph("text"), " more", author="a")

    assert _track_flags(document) is None  # Hancom draws the marks without it
    assert _track_change_display_enabled(_saved(document))


@pytest.mark.parametrize("flags", [0, 1, 4, 5, 8, 16, 24, 2, 32, 48, 60])
def test_flags_that_hide_the_marks_are_reported_as_hidden(flags: int) -> None:
    from hwpx.oxml.header_part import _track_change_marks_shown

    assert not _track_change_marks_shown(flags)


@pytest.mark.parametrize("flags", [None, 40, 56, 57])
def test_flags_that_show_the_marks_are_reported_as_shown(flags: int | None) -> None:
    from hwpx.oxml.header_part import _track_change_marks_shown

    assert _track_change_marks_shown(flags)

