"""Every way of copying (or moving) a footnote or endnote along with what holds it writes the notes' numbers again
in document order, as ``note.copy_to`` and ``copy_range`` do. Before, a copied paragraph, table, row or document
kept the numbers it had, and the saved numbers repeated (1, 2, 1) or ran out of order (2, 1)."""
from __future__ import annotations

from typing import Any, Callable

import pytest

from hwpx import HwpxDocument
from hwpx.tools import document_merge

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _numbers(document: HwpxDocument, tag: str) -> list[str]:
    saved = HwpxDocument.open(document.to_bytes())
    return [note.get("number") for section in saved.oxml.sections for note in section.element.iter(_HP + tag)]


def _two_paragraphs(kind: str) -> tuple[HwpxDocument, Any, Any]:
    document = HwpxDocument.new()
    first = document.add_paragraph("ab")
    second = document.add_paragraph("cd")
    for paragraph in (first, second):
        getattr(paragraph, "add_" + kind)("x", offset=1)
    return document, first, second


def _table_and_paragraph(kind: str) -> tuple[HwpxDocument, Any, Any]:
    document = HwpxDocument.new()
    document.add_paragraph("ab")
    table = document.add_table(2, 1)
    getattr(table.cell(0, 0).paragraphs[0], "add_" + kind)("x")
    after = document.add_paragraph("cd")
    getattr(after, "add_" + kind)("y", offset=1)
    return document, table, after


def _paragraphs(call: Callable[[HwpxDocument, Any, Any], object]) -> Callable[[str], HwpxDocument]:
    def run(kind: str) -> HwpxDocument:
        document, first, second = _two_paragraphs(kind)
        call(document, first, second)
        return document
    return run


def _table(call: Callable[[HwpxDocument, Any, Any], object]) -> Callable[[str], HwpxDocument]:
    def run(kind: str) -> HwpxDocument:
        document, table, after = _table_and_paragraph(kind)
        call(document, table, after)
        return document
    return run


def _other_document(kind: str) -> HwpxDocument:
    _source, first, _second = _two_paragraphs(kind)
    target, _a, _b = _two_paragraphs(kind)
    first.copy_to(target.paragraphs[-1])
    return target


def _merged(kind: str, *, append: bool) -> HwpxDocument:
    target, _a, _b = _two_paragraphs(kind)
    source, _c, _d = _two_paragraphs(kind)
    if append:
        document_merge.append_document(target, source)
    else:
        document_merge.insert_document(target, source, after_paragraph_index=0)
    return target


def _rows_moved(kind: str) -> HwpxDocument:
    document, table, _after = _table_and_paragraph(kind)
    getattr(table.cell(1, 0).paragraphs[0], "add_" + kind)("z")
    table.move_rows(0, to=2)
    return document


_CASES: dict[str, Callable[[str], HwpxDocument]] = {
    "paragraph.copy_to": _paragraphs(lambda d, a, b: a.copy_to(b)),
    "paragraph.copy_to(before=True)": _paragraphs(lambda d, a, b: b.copy_to(a, before=True)),
    "paragraph.insert_after()": _paragraphs(lambda d, a, b: a.insert_after()),
    "paragraph.insert_before()": _paragraphs(lambda d, a, b: b.insert_before()),
    "paragraph.move_after": _paragraphs(lambda d, a, b: a.move_after(b)),
    "section.insert_paragraphs": _paragraphs(lambda d, a, b: d.sections[0].insert_paragraphs(1, [b])),
    "insert_document": lambda kind: _merged(kind, append=False),
    "append_document": lambda kind: _merged(kind, append=True),
    "paragraph.copy_to another document": _other_document,
    "table.copy_to": _table(lambda d, t, after: t.copy_to(after, offset=0)),
    "table.copy_after": _table(lambda d, t, after: t.copy_after()),
    "table.move_to": _table(lambda d, t, after: t.move_to(after, offset=2)),
    "table.copy_rows": _table(lambda d, t, after: t.copy_rows(0, to=2)),
    "table.move_rows": _rows_moved,
}


@pytest.mark.parametrize("kind", ["footnote", "endnote"])
@pytest.mark.parametrize("case", sorted(_CASES))
def test_copied_or_moved_notes_are_numbered_in_document_order(case: str, kind: str) -> None:
    tag = "footNote" if kind == "footnote" else "endNote"
    numbers = _numbers(_CASES[case](kind), tag)
    assert numbers == [str(n) for n in range(1, len(numbers) + 1)]
    assert len(numbers) >= 2
