# SPDX-License-Identifier: Apache-2.0
"""``paragraph=`` takes an index, and refuses another document's paragraph (7.0 fix).

A paragraph object of another document was accepted and that other document was edited
silently. An integer ``paragraph=`` leaked ``AttributeError: 'int' object has no attribute ...``.
"""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError, HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _doc(*texts: str) -> HwpxDocument:
    doc = HwpxDocument.new()
    for text in texts or ("본문", "둘째"):
        doc.add_paragraph(text)
    return doc


CALLS = {
    "notes.add_footnote": lambda d, p: d.notes.add_footnote("각주", p),
    "notes.add_endnote": lambda d, p: d.notes.add_endnote("미주", p),
    "notes.add_memo": lambda d, p: d.notes.add_memo("메모", anchor=p),
    "tracking.insert": lambda d, p: d.tracking.insert(p, "넣은 글"),
    "text.highlight": lambda d, p: d.text.highlight(p, "본문"),
    "shapes.add_rectangle": lambda d, p: d.shapes.add_rectangle(paragraph=p),
    "shapes.add_equation": lambda d, p: d.shapes.add_equation("a+b", paragraph=p),
    "shapes.add_line": lambda d, p: d.shapes.add_line(paragraph=p),
    "refs.add_bookmark": lambda d, p: d.refs.add_bookmark("책갈피", paragraph=p),
    "refs.add_hyperlink": lambda d, p: d.refs.add_hyperlink("https://example.com", "링크", paragraph=p),
    "page.set_columns": lambda d, p: d.page.set_columns(2, paragraph=p),
}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_another_documents_paragraph_is_refused_and_left_alone(name: str) -> None:
    doc, other = _doc(), _doc()
    foreign = other.paragraphs[0]
    before = other.sections[0].to_bytes() if hasattr(other.sections[0], "to_bytes") else None
    with pytest.raises(HwpxValueError) as excinfo:
        CALLS[name](doc, foreign)
    assert excinfo.value.code == "paragraph-not-in-document"
    if before is not None:
        assert other.sections[0].to_bytes() == before


def test_a_removed_paragraph_is_refused_too() -> None:
    doc = _doc("본문", "둘째", "셋째")
    gone = doc.paragraphs[1]
    gone.remove()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.notes.add_footnote("각주", gone)
    assert excinfo.value.code == "paragraph-not-in-document"


INDEXED = {
    "shapes.add_rectangle": lambda d: d.shapes.add_rectangle(paragraph=0),
    "shapes.add_equation": lambda d: d.shapes.add_equation("a+b", paragraph=0),
    "shapes.add_ellipse": lambda d: d.shapes.add_ellipse(paragraph=0),
    "refs.add_bookmark": lambda d: d.refs.add_bookmark("책갈피", paragraph=0),
    "refs.add_hyperlink": lambda d: d.refs.add_hyperlink("https://example.com", "링크", paragraph=0),
    "notes.add_footnote": lambda d: d.notes.add_footnote("각주", 0),
    "notes.add_endnote": lambda d: d.notes.add_endnote("미주", paragraph=0),
    "page.set_columns": lambda d: d.page.set_columns(2, paragraph=1),
}


@pytest.mark.parametrize("name", sorted(INDEXED))
def test_an_index_names_a_paragraph_of_the_document(name: str) -> None:
    doc = _doc()
    count = len(doc.paragraphs)
    INDEXED[name](doc)
    assert len(doc.paragraphs) == count  # put into that paragraph, not a new one


def test_an_index_out_of_range_is_a_typed_error() -> None:
    doc = _doc()
    with pytest.raises(HwpxError) as excinfo:
        doc.shapes.add_rectangle(paragraph=99)
    assert excinfo.value.code == "paragraph-not-found"


def test_paragraphs_in_cells_and_headers_of_the_document_are_accepted() -> None:
    doc = _doc()
    table = doc.add_table(1, 1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    doc.refs.add_bookmark("칸", paragraph=cell_paragraph)
    assert any(True for _ in cell_paragraph.element.iter(f"{HP}bookmark"))
