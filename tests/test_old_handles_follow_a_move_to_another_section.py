"""An object taken before its table, text box, note or paragraph moved to another section still edits what is
saved: the edit marks the section holding it now. Before, the paragraph object kept the section it was taken
from, the edit reported success and the saved file had none of it."""
from __future__ import annotations

from typing import Any, Callable

import pytest

from hwpx import HwpxDocument


def _document() -> tuple[HwpxDocument, dict[str, Any], Any]:
    document = HwpxDocument.new()
    document.add_paragraph("1234")
    host = document.add_paragraph("xy")
    table = host.add_table(2, 1)
    caption = table.set_caption("cap")
    box = host.add_rectangle(1000, 1000)
    draw_text = box.set_draw_text("bb")
    note = host.add_footnote("nn")
    section = document.add_section()
    target = section.paragraphs[0]
    target.text = "w"
    handles = {
        "table": table, "cell": table.cell(0, 0).paragraphs[0], "caption": caption,
        "caption paragraph": caption.paragraphs[0], "box": box, "draw text": draw_text,
        "draw text paragraph": draw_text.paragraphs[0], "note": note, "note paragraph": note.body_paragraph,
        "run": table.cell(0, 0).paragraphs[0].add_run("r"), "host": host,
    }
    return document, handles, target


_MOVES: dict[str, Callable[[dict[str, Any], Any], None]] = {
    "table.move_to": lambda h, q: h["table"].move_to(q, offset=1),
    "shape.move_to": lambda h, q: h["box"].move_to(q, offset=1),
    "note.move_to": lambda h, q: h["note"].move_to(q, offset=1),
    "paragraph.move_after": lambda h, q: h["host"].move_after(q),
    "move_range with the objects": lambda h, q: (
        h["table"].move_to(h["host"], offset=1), h["box"].move_to(h["host"], offset=1),
        h["host"].move_range(0, len(h["host"].text), to=q, offset=1),
    ),
}

_EDITS: dict[str, tuple[Callable[[dict[str, Any]], object], bytes]] = {
    "cell text": (lambda h: setattr(h["cell"], "text", "ZZ"), b"ZZ"),
    "cell insert_text": (lambda h: h["cell"].insert_text(0, "ZZ"), b"ZZ"),
    "table cell text": (lambda h: setattr(h["table"].cell(1, 0), "text", "ZZ"), b"ZZ"),
    "table insert_rows": (lambda h: h["table"].insert_rows(0), b"<hp:tr"),
    "table set_treat_as_char": (lambda h: h["table"].set_treat_as_char(False), b'treatAsChar="0"'),
    "caption add_paragraph": (lambda h: h["caption"].add_paragraph("ZZ"), b"ZZ"),
    "caption paragraph text": (lambda h: setattr(h["caption paragraph"], "text", "ZZ"), b"ZZ"),
    "text box add_paragraph": (lambda h: h["draw text"].add_paragraph("ZZ"), b"ZZ"),
    "text box paragraph text": (lambda h: setattr(h["draw text paragraph"], "text", "ZZ"), b"ZZ"),
    "note text": (lambda h: setattr(h["note"], "text", "ZZ"), b"ZZ"),
    "note paragraph text": (lambda h: setattr(h["note paragraph"], "text", "ZZ"), b"ZZ"),
    "run text": (lambda h: setattr(h["run"], "text", "ZZ"), b"ZZ"),
    "shape set_position": (lambda h: h["box"].set_position(text_wrap="TOP_AND_BOTTOM"), b"TOP_AND_BOTTOM"),
}


def _sections(document: HwpxDocument) -> bytes:
    from lxml import etree

    reopened = HwpxDocument.open(document.to_bytes())
    return b"".join(etree.tostring(section.element) for section in reopened.oxml.sections)


@pytest.mark.parametrize("edit", sorted(_EDITS))
@pytest.mark.parametrize("move", sorted(_MOVES))
def test_an_edit_through_an_object_taken_before_the_move_is_saved(move: str, edit: str) -> None:
    document, handles, target = _document()
    _MOVES[move](handles, target)
    before = _sections(document)
    change, mark = _EDITS[edit]
    change(handles)
    assert _sections(document).count(mark) > before.count(mark)


def test_the_case_from_the_report() -> None:
    document = HwpxDocument.new()
    source = document.add_paragraph("1234")
    table = document.add_paragraph("xy").add_table(1, 1)
    cell = table.cell(0, 0).paragraphs[0]
    section = document.add_section()
    section.paragraphs[0].text = "w"
    table.move_to(section.paragraphs[0], offset=1)
    document.to_bytes()

    source.move_range(1, 3, to=cell)

    assert cell.section is section
    saved = HwpxDocument.open(document.to_bytes())
    assert saved.paragraphs[0].text == "14"
    assert saved.sections[-1].paragraphs[0].tables[0].cell(0, 0).paragraphs[0].text == "23"


@pytest.mark.parametrize("move", ["move_after", "move_range"])
def test_a_memo_taken_before_its_paragraph_moved_is_saved(move: str) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("keep")
    paragraph = document.add_paragraph("abcd")
    memo = document.notes.add_memo("44", paragraph=paragraph, match="b")
    section = document.add_section()
    section.paragraphs[0].text = "w"
    if move == "move_after":
        paragraph.move_after(section.paragraphs[0])
    else:
        paragraph.move_range(0, 4, to=section.paragraphs[0])
    document.to_bytes()

    memo.set_text("ZZ")

    assert [m.text for m in HwpxDocument.open(document.to_bytes()).notes.memos] == ["ZZ"]


def test_a_paragraph_in_a_removed_section_keeps_its_section() -> None:
    document = HwpxDocument.new()
    section = document.add_section()
    paragraph = section.paragraphs[0]
    document.remove_section(section)
    assert paragraph.section is section  # still refused as taken out
