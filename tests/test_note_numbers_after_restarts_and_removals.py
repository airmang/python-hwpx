"""Stored note numbers follow every edit that changes the order of notes (exec7/rv3).

#800 wrote the numbers again on the fourteen paths that copy or move something holding a note. The
number a note is saved with (``number`` and its ``hp:autoNum``) still differed from the one the
document counts (``note.number``) after:

- moving or copying a paragraph that holds a restart (``hp:newNum``) and no note,
- ``insert_rows``/``insert_columns`` with ``copy_content=True`` (two notes numbered 1),
- removing a paragraph, a run, a table or a text box holding notes or a restart, and deleting rows
  or columns (the notes after them kept their old numbers).

Each case reads the saved document again and compares both numbers of every note.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from hwpx import HwpxDocument

KINDS = ("footnote", "endnote")


def _numbers(document: HwpxDocument, kind: str) -> list[tuple[int, int]]:
    """``(counted, stored)`` of every note of *kind* in the saved document."""

    notes = getattr(HwpxDocument.open(document.to_bytes()).notes, kind + "s")
    return [(note.number, int(note.element.get("number"))) for note in notes]


def _add(paragraph: Any, kind: str, text: str) -> Any:
    return getattr(paragraph, "add_" + kind)(text)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(("operation", "expected"), [("move_after", [1, 7]), ("copy_to", [7, 7])])
def test_a_restart_paragraph_moved_or_copied(kind: str, operation: str, expected: list[int]) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("keep")
    restart = document.add_paragraph("restart")
    restart.add_number_restart(kind=kind.upper(), number=7)
    first = document.add_paragraph("a")
    _add(first, kind, "x")
    _add(document.add_paragraph("b"), kind, "y")

    getattr(restart, operation)(first)

    assert _numbers(document, kind) == [(number, number) for number in expected]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("operation", ["insert_rows", "insert_columns"])
def test_rows_and_columns_copied_with_their_content(kind: str, operation: str) -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    _add(table.cell(0, 0).paragraphs[0], kind, "x")
    _add(document.add_paragraph("after"), kind, "tail")

    getattr(table, operation)(0, copy_content=True)

    assert _numbers(document, kind) == [(1, 1), (2, 2), (3, 3)]


def _delete_rows(document: HwpxDocument, kind: str) -> None:
    table = document.add_table(3, 1)
    for row in range(3):
        _add(table.cell(row, 0).paragraphs[0], kind, f"n{row}")
    _add(document.add_paragraph("after"), kind, "tail")
    table.delete_rows(0)


def _delete_columns(document: HwpxDocument, kind: str) -> None:
    table = document.add_table(1, 3)
    for column in range(3):
        _add(table.cell(0, column).paragraphs[0], kind, f"n{column}")
    _add(document.add_paragraph("after"), kind, "tail")
    table.delete_columns(0)


def _remove_restart_paragraph(document: HwpxDocument, kind: str) -> None:
    document.add_paragraph("keep")  # the first paragraph holds the section's settings; not that one
    restart = document.add_paragraph("restart")
    restart.add_number_restart(kind=kind.upper(), number=7)
    for text in ("a", "b", "c"):
        _add(document.add_paragraph(text), kind, text)
    restart.remove()


def _remove_paragraph(document: HwpxDocument, kind: str) -> None:
    first = document.add_paragraph("a")
    _add(first, kind, "x")
    for text in ("b", "c", "d"):
        _add(document.add_paragraph(text), kind, text)
    first.remove()


def _remove_run(document: HwpxDocument, kind: str) -> None:
    first = document.add_paragraph("a")
    note = _add(first, kind, "x")
    for text in ("b", "c", "d"):
        _add(document.add_paragraph(text), kind, text)
    next(run for run in first.runs if any(node is note.element for node in run.element.iter())).remove()


def _remove_table(document: HwpxDocument, kind: str) -> None:
    table = document.add_table(1, 1)
    _add(table.cell(0, 0).paragraphs[0], kind, "x")
    for text in ("b", "c", "d"):
        _add(document.add_paragraph(text), kind, text)
    table.remove()


def _remove_text_box(document: HwpxDocument, kind: str) -> None:
    box = document.add_paragraph("box").add_rectangle(4000, 2000)
    box.set_draw_text("상자 글")
    _add(box.draw_text.paragraphs[0], kind, "x")
    for text in ("b", "c", "d"):
        _add(document.add_paragraph(text), kind, text)
    box.remove()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "edit",
    [_delete_rows, _delete_columns, _remove_restart_paragraph, _remove_paragraph, _remove_run, _remove_table,
     _remove_text_box],
    ids=lambda edit: edit.__name__.lstrip("_"),
)
def test_the_notes_left_are_numbered_from_one(kind: str, edit: Callable[[HwpxDocument, str], None]) -> None:
    document = HwpxDocument.new()
    edit(document, kind)

    assert _numbers(document, kind) == [(1, 1), (2, 2), (3, 3)]


def _detached_paragraph(old: Any) -> Any:
    return old


def _detached_run(old: Any) -> Any:
    return next(run for run in old.runs if run.element.find(".//{*}footNote") is not None)


def _detached_table(old: Any) -> Any:
    return old.tables[0]


def _detached_shape(old: Any) -> Any:
    return old.shapes[0]


@pytest.mark.parametrize("take", [_detached_paragraph, _detached_run, _detached_table, _detached_shape],
                         ids=lambda take: take.__name__.replace("_detached_", ""))
def test_removing_something_of_a_removed_section_leaves_the_documents_notes(take: Callable[[Any], Any]) -> None:
    """A paragraph of a removed section still hangs in that section's tree, so ``remove()`` on it (or on a
    run, table or text box in it) succeeds there. Its notes are not the document's: the notes of the
    sections left keep the numbers they are saved with, and the document its bytes."""

    document = HwpxDocument.new()
    document.add_paragraph("keep")
    old = document.add_paragraph("old")
    if take in (_detached_paragraph, _detached_run):
        old.add_footnote("old")
    elif take is _detached_table:
        old.add_table(1, 1).cell(0, 0).paragraphs[0].add_footnote("old")
    else:
        box = old.add_rectangle(4000, 2000)
        box.set_draw_text("상자 글")
        box.draw_text.paragraphs[0].add_footnote("old")
    document.add_section().add_paragraph("live").add_footnote("live")
    document = HwpxDocument.open(document.to_bytes())
    target = take(next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("old")))
    document.remove_section(0)
    before = document.to_bytes()

    target.remove()

    assert document.to_bytes() == before


def test_a_note_mark_without_a_number_reads_as_one_and_is_numbered() -> None:
    """``hp:autoNum`` without ``num`` reads as 1 (the schema's default). The note copied behind it is 2:
    its mark was left without the attribute, so it showed 1 under a note stored as 2."""

    document = HwpxDocument.new()
    note = document.add_table(1, 1).cell(0, 0).paragraphs[0].add_footnote("x")
    del note.element.find(".//{*}autoNum").attrib["num"]
    document = HwpxDocument.open(document.to_bytes())

    document.tables[0].insert_rows(0, copy_content=True)

    notes = HwpxDocument.open(document.to_bytes()).notes.footnotes
    marks = [note.element.find(".//{*}autoNum") for note in notes]
    assert [(note.number, note.element.get("number")) for note in notes] == [(1, "1"), (2, "2")]
    assert [mark.get("num", "1") for mark in marks] == ["1", "2"]
    assert "num" not in marks[0].attrib  # the first is 1 as it was: nothing written
