# SPDX-License-Identifier: Apache-2.0
"""각주·미주 — 문서 전체 목록과 번호, 내용 고치기, 지우기, 문단의 직접 각주."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.note_authoring import note_numbers

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    data = doc.to_bytes()
    again = HwpxDocument.open(data)
    assert not [issue for issue in again.validate().issues if issue.severity == "error"]
    return again


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_document_lists_notes_in_order_with_hancom_numbers() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("첫째")
    second = doc.add_paragraph("둘째")
    doc.notes.add_footnote("하나", paragraph=first)
    doc.notes.add_footnote("셋", paragraph=second)
    doc.notes.add_footnote("둘", paragraph=first)  # 앞 문단에 끼우면 뒤의 번호가 밀린다
    doc.notes.add_endnote("미주", paragraph=second)

    notes = doc.notes.footnotes
    assert [note.text for note in notes] == ["하나", "둘", "셋"]
    assert [note.number for note in notes] == [1, 2, 3]
    assert [note.element.get("number") for note in notes] == ["1", "2", "3"]
    assert [n.number for n in doc.notes.endnotes] == [1]
    assert isinstance(notes, tuple)
    assert notes[2].paragraph.text == "둘째"


def test_note_content_edit_adds_paragraphs_in_the_note_shape() -> None:
    doc = HwpxDocument.new()
    note = doc.notes.add_footnote("첫 줄", paragraph=doc.add_paragraph("본문"))
    added = note.add_paragraph("둘째 줄")
    assert added.text == "둘째 줄"
    assert note.text == "첫 줄\n둘째 줄"
    first, second = note.paragraphs
    assert second.element.get("styleIDRef") == first.element.get("styleIDRef")
    assert second.element.find(f"{HP}run/{HP}ctrl/{HP}autoNum") is None  # 번호는 첫 문단에만
    note.text = "바꾼 글"
    assert note.text == "바꾼 글"
    assert note.element.find(f".//{HP}autoNum") is not None
    again = _reopen(doc)
    assert [n.text for n in again.notes.footnotes] == ["바꾼 글"]


def test_remove_note_takes_mark_and_content_and_renumbers() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    first = doc.notes.add_footnote("하나", paragraph=paragraph)
    doc.notes.add_footnote("둘", paragraph=paragraph)
    first.remove()
    assert [n.text for n in doc.notes.footnotes] == ["둘"]
    remaining = doc.notes.footnotes[0]
    assert remaining.element.get("number") == "1"
    assert remaining.element.find(f".//{HP}autoNum").get("num") == "1"
    assert paragraph.element.find(f"{HP}linesegarray") is None
    again = _reopen(doc)
    assert len(again.notes.footnotes) == 1
    assert again.paragraphs[-1].text == "본문"


def test_paragraph_footnotes_counts_only_its_own_notes() -> None:
    doc = HwpxDocument.new()
    host = doc.add_paragraph("표를 품은 문단")
    table = host.add_table(1, 1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    cell_paragraph.add_footnote("칸 안 각주")
    host.add_footnote("문단 각주")
    assert [n.text for n in host.footnotes] == ["문단 각주"]
    assert [n.text for n in cell_paragraph.footnotes] == ["칸 안 각주"]
    assert len(doc.notes.footnotes) == 2
    # 칸 안의 각주의 문단은 칸의 문단이다
    in_cell = [n for n in doc.notes.footnotes if n.text == "칸 안 각주"][0]
    assert in_cell.paragraph.element is cell_paragraph.element


def _hancom_doc_with_footnotes() -> Path:
    for path in sorted(HANCOM.glob("*.hwpx")):
        doc = HwpxDocument.open(path)
        if len(doc.notes.footnotes) >= 2:
            return path
    pytest.skip("no Hancom-saved document with two footnotes")


def test_remove_a_footnote_from_a_hancom_saved_document() -> None:
    path = _hancom_doc_with_footnotes()
    original = path.read_bytes()
    doc = HwpxDocument.open(original)
    before = doc.notes.footnotes
    texts = [n.text for n in before]
    host = before[0].paragraph
    before[0].remove()
    after = doc.notes.footnotes
    assert [n.text for n in after] == texts[1:]
    assert [n.number for n in after] == list(range(1, len(after) + 1))
    assert host.element.find(f"{HP}linesegarray") is None
    data = doc.to_bytes()
    again = HwpxDocument.open(data)
    assert not [i for i in again.validate().issues if i.severity == "error"]
    assert [n.text for n in again.notes.footnotes] == texts[1:]
    old, new = _parts(original), _parts(data)
    changed = {name for name in old if old[name] != new.get(name)}
    assert changed and all(name.startswith("Contents/section") for name in changed)


def test_note_numbers_match_the_numbers_hancom_wrote() -> None:
    checked = 0
    for path in sorted(HANCOM.glob("*.hwpx")):
        doc = HwpxDocument.open(path)
        sections = [section.element for section in doc.oxml.sections]
        numbers = note_numbers(sections)
        for element, number in numbers.items():
            if element.get("number") is not None:
                assert element.get("number") == str(number), path.name
                checked += 1
    assert checked > 50
