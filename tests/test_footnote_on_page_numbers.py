# SPDX-License-Identifier: Apache-2.0
"""Footnotes numbered again on every page (``ON_PAGE``): the engine does not number them.

Their numbers depend on where the pages break, which python-hwpx does not lay out. No public
document numbers notes ``ON_PAGE`` (1,339 HWPX and 319 converted HWP sections, all
``CONTINUOUS``), so what Hancom writes into ``number`` there is not known; the rule is to leave the
written numbers as they are and give a new note its count in the document. ``note.number`` reads the
number the file holds. Other numberings keep being renumbered (``test_*notes*`` elsewhere).
"""

from __future__ import annotations

import io
import zipfile

from lxml import etree

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _numbers(data: bytes) -> list[tuple[str | None, str | None]]:
    """(``number``, the body's ``hp:autoNum@num``) of every footnote, in document order."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    return [
        (note.get("number"), next((auto.get("num") for auto in note.iter(f"{HP}autoNum")), None))
        for note in section.iter(f"{HP}footNote")
    ]


def _on_page(*texts: str) -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.page.set_footnote_shape(numbering="ON_PAGE")
    doc.add_paragraph("각주 없는 첫 문단")
    for text in texts:
        paragraph = doc.add_paragraph(f"{text} 본문")
        doc.notes.add_footnote(text, paragraph=paragraph)
    return doc


def test_numbers_written_in_an_on_page_section_are_left_alone() -> None:
    doc = _on_page("하나", "둘", "셋")
    assert _numbers(doc.to_bytes()) == [("1", "1"), ("2", "2"), ("3", "3")]

    # a note added before the others takes its count in the document, the others keep theirs
    first = next(p for p in doc.paragraphs if p.text == "각주 없는 첫 문단")
    doc.notes.add_footnote("앞", paragraph=first)
    numbers = _numbers(doc.to_bytes())
    assert numbers == [("4", "4"), ("1", "1"), ("2", "2"), ("3", "3")]
    assert [note.number for note in doc.notes.footnotes] == [4, 1, 2, 3]

    # removing one renumbers nothing
    doc.notes.footnotes[1].remove()
    assert _numbers(doc.to_bytes()) == [("4", "4"), ("2", "2"), ("3", "3")]


def test_note_number_reads_what_the_file_holds_there() -> None:
    doc = _on_page("하나", "둘")
    first = doc.sections[0].element.find(f".//{HP}footNote")
    first.set("number", "7")  # as if laid out on a page of its own
    reopened = HwpxDocument.open(doc.to_bytes())
    assert [note.number for note in reopened.notes.footnotes] == [7, 2]


def test_a_continuous_section_still_renumbers() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("각주 없는 첫 문단")
    for text in ("하나", "둘", "셋"):
        doc.notes.add_footnote(text, paragraph=doc.add_paragraph(f"{text} 본문"))
    doc.notes.add_footnote("앞", paragraph=first)
    assert _numbers(doc.to_bytes()) == [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")]
    assert [note.number for note in doc.notes.footnotes] == [1, 2, 3, 4]


def test_an_on_page_document_saves_reopens_and_validates() -> None:
    data = _on_page("하나", "둘", "셋").to_bytes()
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    assert reopened.page.footnote_shape().numbering == "ON_PAGE"
