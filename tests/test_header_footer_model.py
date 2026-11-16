# SPDX-License-Identifier: Apache-2.0
"""Headers and footers as model objects: list them per page type, read and edit their paragraphs.

``HeaderFooter.add_paragraph``/``add_run``/``add_page_number_field`` return model
objects (paragraph, run, inline object) instead of bare XML elements.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.model import HeaderFooter, InlineObject, Paragraph, Run

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EVEN_ODD = next((FIXTURES / "hwpxlib_corpus").glob("error__20250808__*.hwpx"))


def _section_xml(data: bytes, index: int = 0) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(f"Contents/section{index}.xml").decode("utf-8")


def test_headers_per_page_type_with_their_paragraphs() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.page.set_header(text="홀수 쪽", page_type="ODD")
    doc.page.set_header(text="짝수 쪽", page_type="EVEN")
    doc.page.set_footer(text="꼬리말")
    doc.page.set_visibility(hide_first_header=True)
    reopened = HwpxDocument.open(doc.to_bytes())

    headers = reopened.page.headers()
    assert sorted(header.page_type for header in headers) == ["EVEN", "ODD"]
    assert all(isinstance(header, HeaderFooter) and header.kind == "header" for header in headers)
    odd = reopened.page.header(page_type="ODD")
    assert odd is not None and [p.text for p in odd.paragraphs] == ["홀수 쪽"]
    assert reopened.page.header() is None
    (footer,) = reopened.page.footers()
    assert footer.kind == "footer" and footer.page_type == "BOTH" and footer.text == "꼬리말"
    assert reopened.page.visibility().hide_first_header is True


def test_editing_a_header_through_its_model_objects_reaches_the_copy_hangul_reads() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.page.set_header(text="머리말")
    header = doc.page.header()
    assert header is not None
    header.paragraphs[0].text = "바뀐 머리말"
    added = header.add_paragraph("둘째 줄")
    assert isinstance(added, Paragraph) and added.text == "둘째 줄"
    run = header.add_run(" 덧붙임", paragraph=added)
    assert isinstance(run, Run) and run.text == " 덧붙임"
    number = header.add_page_number_field(paragraph=added)
    assert isinstance(number, InlineObject) and number.element.tag.endswith("pageNum")

    data = doc.to_bytes()
    xml = _section_xml(data)
    # one secPr story and one control copy Hangul reads, both with the new text
    assert xml.count("바뀐 머리말") == 2 and xml.count("둘째 줄") == 2
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    (only,) = reopened.page.headers()
    assert [p.text for p in only.paragraphs] == ["바뀐 머리말", "둘째 줄 덧붙임"]


def test_a_hangul_saved_even_and_odd_header_reads_and_edits_in_place() -> None:
    doc = HwpxDocument.open(EVEN_ODD)
    stories = [*doc.page.headers(section=0), *doc.page.footers(section=0)]
    page_types = sorted(story.page_type for story in stories)
    assert "EVEN" in page_types and "ODD" in page_types
    target = next(story for story in stories if story.page_type == "ODD")
    kind = target.kind
    before = _section_xml(doc.to_bytes()).count(f"<hp:{kind} ")

    target.paragraphs[0].text = "고친 글"
    target.add_paragraph("더한 줄")
    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    # still one story per page type: the edit changed the control Hangul saved, it added no second copy
    assert _section_xml(data).count(f"<hp:{kind} ") == before
    edited = getattr(reopened.page, kind)(page_type="ODD", section=0)
    assert edited is not None
    texts = [p.text for p in edited.paragraphs]
    assert texts[0] == "고친 글" and texts[-1] == "더한 줄"
    assert not re.search(r"고친 글.{0,400}<hp:linesegarray", _section_xml(data), re.S)


def test_a_paragraph_from_elsewhere_is_refused() -> None:
    doc = HwpxDocument.new()
    body = doc.add_paragraph("본문")
    header = doc.page.set_header(text="머리말")
    with pytest.raises(HwpxValueError) as caught:
        header.add_run("x", paragraph=body)
    assert caught.value.code == "story-paragraph-not-here"


def test_set_content_still_writes_page_numbers() -> None:
    doc = HwpxDocument.new()
    footer = doc.page.set_footer(content=[{"children": [{"type": "page_number", "page_number": "page/total"}]}])
    kinds = [number.kind for number in doc.page.auto_numbers()]
    assert kinds == ["PAGE", "TOTAL_PAGE"]
    assert footer.text == "/"
