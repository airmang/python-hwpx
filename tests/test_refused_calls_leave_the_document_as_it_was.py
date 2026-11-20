"""A call that is refused leaves the document as it was (exec7/rv4).

The final review of 7.0.0 found calls that raised and had already changed the document: a note moved
into its own cell was gone, a picture refused for its style left its image in the file, a text that is
not a ``str`` emptied the note it was assigned to, a header's content refused at its second run left
the first run's character shape (and cut off the paragraph objects taken before), a master page
refused by the second section stayed on the first, a column count refused by ``page.setup`` came
after the paper size was written, and every ``doc.<namespace>.add_*`` made its paragraph before it
checked what was to go into it.

Each case compares the trees of every section, header and master page, and the images of the
package, before and after the refused call. ``to_bytes()`` is not the measure: a call that raises
before it marks its section changed leaves the bytes alone while the tree it would save next is
already different.
"""

from __future__ import annotations

from base64 import b64decode
from collections.abc import Callable
from typing import Any

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGPYDQAAvQC8nHnAdAAAAABJRU5ErkJggg=="
)


def _state(document: HwpxDocument) -> tuple[list[bytes], list[str]]:
    parts = [*document.oxml.sections, *document.oxml.headers, *document.oxml.master_pages]
    return [etree.tostring(part.element) for part in parts], sorted(str(item) for item in document.media.images)


def _saved(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


def _rich() -> HwpxDocument:
    """A document with one of each thing the cases write into, opened from its bytes so nothing is
    pending."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("body text")
    paragraph.add_footnote("foot")
    paragraph.add_endnote("end")
    document.notes.add_memo("memo", paragraph=document.add_paragraph("memo host"))
    table = document.add_table(1, 1)
    table.set_cell_text(0, 0, "cell")
    document.page.set_header(text="head")
    document.page.set_footer(text="foot")
    box = document.shapes.add_rectangle(paragraph=document.add_paragraph("box host"))
    box.set_draw_text("boxed")
    document.add_picture(PNG, "png")
    return _saved(document)


def _refused(document: HwpxDocument, call: Callable[[], Any]) -> BaseException:
    before = _state(document)
    with pytest.raises(Exception) as caught:  # noqa: PT011 - the kind is each case's own
        call()
    assert _state(document) == before, f"refused with {caught.value!r}, and the document changed"
    return caught.value


# -- a note into its own text ---------------------------------------------------------------------


def test_a_note_moved_into_its_own_cell_is_refused_and_stays() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_footnote("keep this note")
    cell = note.paragraphs[0].add_table(1, 1).cell(0, 0)

    error = _refused(document, lambda: note.move_to(cell.paragraphs[0]))

    assert isinstance(error, HwpxError) and error.code == "note-move-into-itself"
    kept = _saved(document).notes.footnotes
    assert len(kept) == 1 and "keep this note" in kept[0].text
    assert len(kept[0].paragraphs[0].tables) == 1  # the table in the note stayed with it


def test_a_note_still_copies_into_its_own_cell() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_footnote("note")
    cell = note.paragraphs[0].add_table(1, 1).cell(0, 0)

    note.copy_to(cell.paragraphs[0])

    assert len(_saved(document).notes.footnotes) == 2


# -- a picture ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("style", "no such style"), ("section", 9), ("alignment", "MIDDLE"), ("brightness", 999),
        ("contrast", 999), ("effect", "X"), ("alpha", 999), ("line_color", "nope"), ("line_width_mm", -1),
        ("crop", (1, 2)), ("width", -5), ("height", -5), ("width_mm", -1), ("soft_edge", -3),
        ("shadow", "x"), ("glow", "x"), ("reflection", "x"),
    ],
)
def test_a_refused_picture_leaves_neither_its_image_nor_a_paragraph(argument: str, value: Any) -> None:
    document = _rich()
    _refused(document, lambda: document.add_picture(PNG, "png", **{argument: value}))


def test_a_picture_that_is_added_has_one_image_and_one_paragraph() -> None:
    document = HwpxDocument.new()
    count = len(document.paragraphs)

    document.add_picture(PNG, "png", alignment="CENTER")

    reopened = _saved(document)
    assert len(reopened.media.pictures) == 1 and len(reopened.media.images) == 1
    assert len(reopened.paragraphs) == count + 1


# -- text that is not text ------------------------------------------------------------------------

_TEXT_WRITERS: dict[str, Callable[[HwpxDocument, Any], Any]] = {
    "paragraph.text": lambda d, v: setattr(d.paragraphs[0], "text", v),
    "paragraph.add_run": lambda d, v: d.paragraphs[0].add_run(v),
    "paragraph.insert_text": lambda d, v: d.paragraphs[0].insert_text(0, v),
    "footnote.text": lambda d, v: setattr(d.notes.footnotes[0], "text", v),
    "endnote.text": lambda d, v: setattr(d.notes.endnotes[0], "text", v),
    "footnote.add_paragraph": lambda d, v: d.notes.footnotes[0].add_paragraph(v),
    "footnote.add_run": lambda d, v: d.notes.footnotes[0].add_run(v),
    "memo.text": lambda d, v: setattr(d.notes.memos[0], "text", v),
    "memo.set_text": lambda d, v: d.notes.memos[0].set_text(v),
    "header.text": lambda d, v: setattr(d.page.header(), "text", v),
    "header.add_paragraph": lambda d, v: d.page.header().add_paragraph(v),
    "header.add_run": lambda d, v: d.page.header().add_run(v),
    "page.set_header": lambda d, v: d.page.set_header(text=v),
    "page.set_footer": lambda d, v: d.page.set_footer(text=v),
    "cell.text": lambda d, v: setattr(d.tables.all[0].cell(0, 0), "text", v),
    "cell.add_paragraph": lambda d, v: d.tables.all[0].cell(0, 0).add_paragraph(v),
    "table.set_cell_text": lambda d, v: d.tables.all[0].set_cell_text(0, 0, v),
    "table.set_caption": lambda d, v: d.tables.all[0].set_caption(v),
    "picture.set_caption": lambda d, v: d.media.pictures[0].set_caption(v),
    "paragraph.add_footnote": lambda d, v: d.paragraphs[0].add_footnote(v),
    "paragraph.add_endnote": lambda d, v: d.paragraphs[0].add_endnote(v),
    "paragraph.add_form_field": lambda d, v: d.paragraphs[0].add_form_field("name", prompt=v),
    "paragraph.add_check_box": lambda d, v: d.paragraphs[0].add_check_box(v),
    "paragraph.add_check_box(name)": lambda d, v: d.paragraphs[0].add_check_box("caption", name=v),
    "notes.add_footnote": lambda d, v: d.notes.add_footnote(v),
    "notes.add_endnote": lambda d, v: d.notes.add_endnote(v),
    "notes.add_memo": lambda d, v: d.notes.add_memo(v, paragraph=d.paragraphs[0]),
    "refs.add_hyperlink": lambda d, v: d.refs.add_hyperlink("https://a.example", v),
    "add_paragraph": lambda d, v: d.add_paragraph(v),
    "add_heading": lambda d, v: d.add_heading(v),
}


@pytest.mark.parametrize("writer", sorted(_TEXT_WRITERS))
@pytest.mark.parametrize("value", [123, b"bytes", ("a", "b")], ids=["int", "bytes", "tuple"])
def test_text_that_is_not_a_str_is_refused_before_anything_is_written(writer: str, value: Any) -> None:
    document = _rich()
    _refused(document, lambda: _TEXT_WRITERS[writer](document, value))


def test_a_note_keeps_its_text_when_none_is_assigned() -> None:
    document = HwpxDocument.new()
    note = document.add_paragraph("body").add_footnote("keep me")

    with pytest.raises(HwpxError) as caught:
        note.text = None  # type: ignore[assignment]

    assert caught.value.code == "paragraph-text-invalid-type"
    assert _saved(document).notes.footnotes[0].text == note.text
    assert "keep me" in note.text


def test_a_memo_still_takes_none_as_no_text() -> None:
    document = HwpxDocument.new()
    memo = document.notes.add_memo("memo", paragraph=document.add_paragraph("host"))

    memo.text = None  # type: ignore[assignment]

    assert _saved(document).notes.memos[0].text == ""


# -- a header's or footer's content ---------------------------------------------------------------

_BAD_CONTENT: dict[str, list[dict[str, Any]]] = {
    "kind after a sized run": [{"children": [{"text": "draft", "size": 37}, {"type": "bad"}]}],
    "size after a bold run": [{"children": [{"text": "draft", "bold": True}, {"text": "x", "size": -1}]}],
    "font after a sized run": [{"children": [{"text": "draft", "size": 37}, {"text": "x", "font": 5}]}],
    "colour after a sized run": [{"children": [{"text": "draft", "size": 37}, {"text": "x", "color": "nope"}]}],
    "format after a sized run": [{"children": [{"text": "draft", "size": 37}, {"page_number": "ROMAN-ISH"}]}],
    "alignment of a later paragraph": [{"children": [{"text": "draft", "size": 37}]}, {"align": "SIDEWAYS", "text": "x"}],
}


@pytest.mark.parametrize("case", sorted(_BAD_CONTENT))
def test_refused_header_content_leaves_the_header_and_the_styles(case: str) -> None:
    document = _rich()
    _refused(document, lambda: document.page.set_header(content=_BAD_CONTENT[case]))
    _refused(document, lambda: document.page.header().set_content(_BAD_CONTENT[case]))


def test_a_paragraph_taken_before_refused_header_content_still_writes() -> None:
    document = HwpxDocument.new()
    document.page.set_header(text="original")
    document = _saved(document)
    paragraph = document.page.header().paragraphs[0]
    shapes = len(document.styles.char_properties)

    with pytest.raises(ValueError, match="unsupported header/footer content type") as caught:
        document.page.set_header(content=_BAD_CONTENT["kind after a sized run"])
    paragraph.text = "revised"

    assert isinstance(caught.value, HwpxError) and caught.value.code == "story-content-type-unsupported"
    reopened = _saved(document)
    assert reopened.page.header().text == "revised"
    assert len(reopened.styles.char_properties) == shapes


def test_header_content_that_is_fine_is_written_as_before() -> None:
    document = HwpxDocument.new()

    document.page.set_header(content=[
        {"align": "CENTER", "children": [{"text": "제목 ", "bold": True, "size": 12}, {"page_number": "page/total"}]},
    ])

    assert "제목" in _saved(document).page.header().text


# -- one master page for every section -------------------------------------------------------------


def test_a_master_page_refused_by_a_later_section_is_put_on_none() -> None:
    document = HwpxDocument.new()
    document.add_section()
    document.add_section()
    document.parts.add_master_page(text="A", page_type="BOTH", section=1)
    other = document.parts.add_master_page(text="B", page_type="BOTH", section=2)
    document = _saved(document)
    other = document.parts.master_pages[1]

    error = _refused(document, lambda: document.page.set_master_page(other, section="all"))

    assert isinstance(error, HwpxError) and error.code == "master-page-pages-taken"
    assert _saved(document).page.master_page_refs(section=0) == ()


def test_a_master_page_goes_on_every_section_that_can_take_it() -> None:
    document = HwpxDocument.new()
    document.add_section()
    page = document.parts.add_master_page(text="A", page_type="BOTH", section=0)

    document.page.set_master_page(page, section="all")

    reopened = _saved(document)
    assert reopened.page.master_page_refs(section=0) == reopened.page.master_page_refs(section=1) != ()


# -- page setup ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {"paper_size": "A5", "columns": 0},
        {"orientation": "landscape", "columns": -2},
        {"margin_left_mm": 10, "columns": 0},
        {"paper_size": "A5", "margin_left_mm": 10**9},
        {"paper_size": "no such paper", "margin_left_mm": 10},
    ],
)
def test_a_refused_page_setup_changes_neither_paper_nor_margins(arguments: dict[str, Any]) -> None:
    document = _rich()
    width = document.page.size().width
    _refused(document, lambda: document.page.setup(**arguments))
    assert _saved(document).page.size().width == width


# -- an object for a new paragraph ----------------------------------------------------------------

_ADDS: dict[str, Callable[[HwpxDocument], Any]] = {
    "line colour": lambda d: d.shapes.add_line(line_color="nope"),
    "rectangle colour": lambda d: d.shapes.add_rectangle(line_color="nope"),
    "ellipse line width": lambda d: d.shapes.add_ellipse(line_width_mm=-1),
    "arc type": lambda d: d.shapes.add_arc(arc_type="no such"),
    "arc corner": lambda d: d.shapes.add_arc(corner="no such"),
    "curve points": lambda d: d.shapes.add_curve([(0, 0)]),
    "drop cap character": lambda d: d.shapes.add_drop_cap("", 1000, 1000),
    "ruby text": lambda d: d.shapes.add_ruby("base", 123),  # type: ignore[arg-type]
    "composed character": lambda d: d.shapes.add_composed_character(123),  # type: ignore[arg-type]
    "equation script": lambda d: d.shapes.add_equation(123),  # type: ignore[arg-type]
    "footnote offset": lambda d: d.notes.add_footnote("note", offset=5),
    "endnote offset": lambda d: d.notes.add_endnote("note", offset="end"),  # type: ignore[arg-type]
    "bookmark name": lambda d: d.refs.add_bookmark(123),  # type: ignore[arg-type]
    "bookmark offset": lambda d: d.refs.add_bookmark("name", offset=5),
    "hyperlink url": lambda d: d.refs.add_hyperlink("", "text"),
    "hyperlink url type": lambda d: d.refs.add_hyperlink(123, "text"),  # type: ignore[arg-type]
    "form field name": lambda d: d.fields.add(123),  # type: ignore[arg-type]
    "check box caption": lambda d: d.fields.add_check_box(123),  # type: ignore[arg-type]
    "radio button caption": lambda d: d.fields.add_radio_button(123),  # type: ignore[arg-type]
    "edit box text": lambda d: d.fields.add_edit_box(text=123),  # type: ignore[arg-type]
}


@pytest.mark.parametrize("case", sorted(_ADDS))
def test_a_refused_add_leaves_no_empty_paragraph(case: str) -> None:
    document = _rich()
    count = len(document.paragraphs)
    _refused(document, lambda: _ADDS[case](document))
    assert len(_saved(document).paragraphs) == count


def test_an_add_that_goes_through_still_makes_its_paragraph() -> None:
    document = HwpxDocument.new()
    count = len(document.paragraphs)

    document.shapes.add_line()
    document.notes.add_footnote("note")

    assert len(_saved(document).paragraphs) == count + 2


# -- a table in a cell, a check box ---------------------------------------------------------------


@pytest.mark.parametrize(("rows", "cols"), [("two", 2), (0, 2), (2, -1), (2.5, 2)])
def test_a_refused_table_in_a_cell_leaves_the_cell_and_the_border_fills(rows: Any, cols: Any) -> None:
    document = _rich()
    cell = document.tables.all[0].cell(0, 0)
    _refused(document, lambda: cell.add_table(rows, cols))


@pytest.mark.parametrize("arguments", [{"width": "wide"}, {"height": [1]}, {"name": 5}])
def test_a_check_box_that_cannot_be_written_leaves_no_run(arguments: dict[str, Any]) -> None:
    document = _rich()
    paragraph = document.paragraphs[0]
    _refused(document, lambda: paragraph.add_check_box("caption", **arguments))
