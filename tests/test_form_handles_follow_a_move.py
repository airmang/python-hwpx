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


def test_a_bookmark_in_a_master_page_renames_with_the_links_to_it() -> None:
    """The rename marked the body sections only: the body link was saved pointing at the new name and the
    bookmark, in the master page, kept the old one."""

    document = HwpxDocument.new()
    document.parts.add_master_page(text="M", section=0).paragraphs[0].add_bookmark("old")
    document.paragraphs[0].add_hyperlink("#old", "jump")
    document = HwpxDocument.open(document.to_bytes())

    document.parts.master_pages[0].paragraphs[0].bookmarks[0].rename("new")

    saved = _saved(document)
    assert saved.parts.master_pages[0].paragraphs[0].bookmarks[0].name == "new"
    assert saved.refs.hyperlinks[0].url == "#new"


def test_two_objects_of_one_bookmark_rename_from_the_name_it_has() -> None:
    document, moving, destination = _two_sections()
    moving.add_bookmark("old")
    moving.add_hyperlink("#old", "jump")
    first, second = moving.bookmarks[0], moving.bookmarks[0]
    moving.move_after(destination)
    document.to_bytes()

    first.rename("middle")
    document.to_bytes()
    second.rename("new")  # taken when the name was "old"

    saved = _saved(document)
    assert (saved.refs.bookmarks[0].name, saved.refs.hyperlinks[0].url) == ("new", "#new")


def test_a_field_bookmark_whose_start_moved_away_from_its_end_is_removed_whole() -> None:
    from lxml.etree import SubElement

    from hwpx.oxml.namespaces import HP

    document = HwpxDocument.new()
    for tag, attributes in (("fieldBegin", {"type": "BOOKMARK", "name": "span", "id": "42"}),
                            ("fieldEnd", {"beginIDRef": "42"})):
        run = document.add_paragraph(tag).runs[0].element
        SubElement(SubElement(run, HP + "ctrl"), HP + tag, attributes)
    document.add_section()
    document = HwpxDocument.open(document.to_bytes())
    mark = document.refs.bookmarks[0]
    document.sections[0].paragraphs[-2].move_after(document.sections[1].paragraphs[0])
    document.to_bytes()

    mark.remove()

    saved = _saved(document)
    for tag in ("fieldBegin", "fieldEnd"):
        assert [len(list(section.element.iter(HP + tag))) for section in saved.sections] == [0, 0]


def test_a_bookmark_of_a_plain_elementtree_section_still_renames() -> None:
    """A model section over ``xml.etree`` elements has no way up the tree; the rename works as before."""

    import xml.etree.ElementTree as ET

    from hwpx.model import Section
    from hwpx.oxml.namespaces import HP, HS

    root = ET.Element(HS + "sec")
    run = ET.SubElement(ET.SubElement(root, HP + "p"), HP + "run")
    mark = ET.SubElement(ET.SubElement(run, HP + "ctrl"), HP + "bookmark", name="old")
    section = Section("section0.xml", root)

    section.paragraphs[0].bookmarks[0].rename("new")

    assert (mark.get("name"), section.dirty) == ("new", True)


def test_a_hyperlink_taken_before_its_range_moved_saves_its_new_target() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("a")
    link = paragraph.add_hyperlink("https://old.example", "label")
    paragraph.add_run("z")
    destination = document.add_section().paragraphs[0]

    paragraph.move_range(0, len(paragraph.text), to=destination)
    document.to_bytes()
    link.url = "https://new.example"

    assert link.paragraph.section is document.sections[1]
    assert _saved(document).refs.hyperlinks[0].url == "https://new.example"


def test_a_field_bookmark_written_with_spaces_around_its_name_renames_with_its_links() -> None:
    """``name=" old "`` reads as ``old`` and links point at ``#old``."""

    from lxml.etree import SubElement

    from hwpx.oxml.namespaces import HP

    document = HwpxDocument.new()
    begin, end = (document.add_paragraph(text) for text in ("begin", "end"))
    for paragraph, tag, attributes in ((begin, "fieldBegin", {"id": "13", "type": "BOOKMARK", "name": " old "}),
                                       (end, "fieldEnd", {"beginIDRef": "13"})):
        SubElement(SubElement(paragraph.runs[0].element, HP + "ctrl"), HP + tag, attributes)
    begin.add_hyperlink("#old", "go")

    begin.bookmarks[0].rename("new")

    saved = _saved(document)
    assert (saved.refs.bookmarks[0].name, saved.refs.hyperlinks[0].url) == ("new", "#new")


def test_a_point_bookmark_is_renamed_by_its_name_as_written() -> None:
    """A point bookmark's name is read as written, spaces included: ``" old "`` and ``"old"`` are two
    bookmarks, and renaming the first moves the links to it and not the links to the other."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("p")
    paragraph.add_bookmark(" old ")
    paragraph.add_bookmark("old")
    paragraph.add_hyperlink("# old ", "first")
    paragraph.add_hyperlink("#old", "second")
    spaced = next(bookmark for bookmark in paragraph.bookmarks if bookmark.name == " old ")

    spaced.rename("new")

    assert [link.url for link in _saved(document).refs.hyperlinks] == ["#new", "#old"]
