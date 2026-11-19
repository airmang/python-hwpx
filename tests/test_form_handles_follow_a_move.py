"""Objects taken before a move to another section save what is changed through them (exec7/rv3).

#800 made paragraphs, runs, tables, objects and notes follow a move. Bookmarks, check boxes, radio
buttons, combo boxes, edit boxes and named text boxes still marked the section they were taken from:
after the paragraph (or the table, text box or note around them) went to another section and the
document was written once, a change through the old object returned and was not saved.

Each case: take the object, move what holds it to section 2, write the document (so nothing is
pending), change through the object taken before the move, and read the saved document again.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from hwpx import HwpxDocument


def _two_sections() -> tuple[HwpxDocument, Any, Any]:
    document = HwpxDocument.new()
    document.add_paragraph("stay")
    moving = document.add_paragraph("move")
    destination = document.add_section().paragraphs[0]
    return document, moving, destination


def _saved(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


def _in_paragraph(document: HwpxDocument, moving: Any) -> tuple[Any, Callable[[Any], None]]:
    return moving, lambda destination: moving.move_after(destination)


def _in_cell(document: HwpxDocument, moving: Any) -> tuple[Any, Callable[[Any], None]]:
    table = moving.add_table(1, 1)
    return table.cell(0, 0).paragraphs[0], lambda destination: table.move_to(destination)


def _in_text_box(document: HwpxDocument, moving: Any) -> tuple[Any, Callable[[Any], None]]:
    box = moving.add_rectangle(4000, 2000)
    box.set_draw_text("상자 글")
    return box.draw_text.paragraphs[0], lambda destination: box.move_to(destination)


def _in_footnote(document: HwpxDocument, moving: Any) -> tuple[Any, Callable[[Any], None]]:
    note = moving.add_footnote("각주 글")
    return note.paragraphs[0], lambda destination: note.move_to(destination)


@pytest.mark.parametrize("place", [_in_paragraph, _in_cell, _in_text_box, _in_footnote],
                         ids=["paragraph", "table-cell", "text-box", "footnote"])
@pytest.mark.parametrize("reopened", [False, True], ids=["new", "opened"])
def test_a_bookmark_taken_before_the_move_renames_and_removes(place: Any, reopened: bool) -> None:
    document, moving, destination = _two_sections()
    holder, _move = place(document, moving)
    holder.add_bookmark("old")
    if reopened:  # the same on a document as a caller opens it
        document = HwpxDocument.open(document.to_bytes())
        moving = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("move"))
        destination = document.sections[1].paragraphs[0]
        if place is _in_paragraph:
            move: Callable[[Any], None] = moving.move_after
        elif place is _in_cell:
            move = moving.tables[0].move_to
        elif place is _in_text_box:
            move = moving.shapes[0].move_to
        else:
            move = moving.footnotes[0].move_to
    else:
        move = _move
    mark = document.refs.bookmarks[0]

    move(destination)
    document.to_bytes()
    renamed = mark.rename("new")

    assert renamed.name == "new"
    assert [bookmark.name for bookmark in _saved(document).refs.bookmarks] == ["new"]

    document.to_bytes()
    renamed.remove()
    assert _saved(document).refs.bookmarks == ()


def test_form_controls_taken_before_the_move_save_their_values() -> None:
    document, moving, destination = _two_sections()
    check = document.fields.add_check_box("확인", paragraph=moving)
    radio = document.fields.add_radio_button("선택", paragraph=moving)
    combo = document.fields.add_combo_box("old", paragraph=moving)
    edit = document.fields.add_edit_box("old", paragraph=moving)
    moving.add_rectangle(1000, 1000).set_draw_text("old", name="Box")
    box = document.fields.text_boxes[0]

    moving.move_after(destination)
    document.to_bytes()
    check.checked = radio.checked = True
    combo.text = edit.text = box.text = "new"

    assert check.section is document.sections[1] and combo.section is document.sections[1]
    fields = _saved(document).fields
    assert (fields.check_boxes[0].checked, fields.radio_buttons[0].checked) == (True, True)
    assert (fields.combo_boxes[0].text, fields.edit_boxes[0].text, fields.text_boxes[0].text) == ("new", "new", "new")


def test_a_radio_button_taken_before_the_move_still_unchecks_its_group() -> None:
    document, moving, destination = _two_sections()
    stays = document.fields.add_radio_button("남는 것", group="g", checked=True, paragraph=document.paragraphs[0])
    moved = document.fields.add_radio_button("옮긴 것", group="g", paragraph=moving)

    moving.move_after(destination)
    document.to_bytes()
    moved.checked = True

    saved = {button.caption: button.checked for button in _saved(document).fields.radio_buttons}
    assert saved == {"남는 것": False, "옮긴 것": True}
    assert stays.checked is False
