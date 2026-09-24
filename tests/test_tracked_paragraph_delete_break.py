# SPDX-License-Identifier: Apache-2.0
"""A tracked delete of a whole paragraph also deletes its break when another paragraph follows."""

from __future__ import annotations

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _ends(paragraph) -> list[str | None]:
    return [end.get("paraend") for end in paragraph.element.iter(f"{HP}deleteEnd")]


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "first"
    doc.add_paragraph("second paragraph to delete")
    doc.add_paragraph("third")
    return doc


def test_whole_paragraph_delete_marks_the_break_deleted() -> None:
    doc = _document()
    doc.tracking.delete(1)
    assert _ends(doc.paragraphs[1]) == ["1"]
    reopened = HwpxDocument.open(doc.to_bytes())
    assert _ends(reopened.paragraphs[1]) == ["1"]


def test_last_paragraph_keeps_its_break() -> None:
    doc = _document()
    doc.tracking.delete(2)
    assert _ends(doc.paragraphs[2]) == ["0"]


def test_partial_delete_keeps_the_break() -> None:
    doc = _document()
    doc.tracking.delete(1, match="to delete")
    assert _ends(doc.paragraphs[1]) == ["0"]


def test_paragraph_with_a_control_keeps_its_break() -> None:
    doc = _document()
    doc.refs.add_bookmark("mark", paragraph=doc.paragraphs[1])
    doc.tracking.delete(1)
    assert set(_ends(doc.paragraphs[1])) == {"0"}
