"""Paragraph objects of table cells, headers and footers can be removed and rewritten in place."""

from __future__ import annotations

import io

import pytest

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.oxml.paragraph import HwpxOxmlParagraph


def test_a_cell_paragraph_is_removed_from_its_cell() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.set_text("첫째\n둘째", split_paragraphs=True)

    cell.paragraphs[1].remove()

    assert [p.text for p in cell.paragraphs] == ["첫째"]
    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))
    assert reopened.tables.all[0].cell(0, 0).text == "첫째"


def test_the_last_paragraph_of_a_cell_stays() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.text = "하나"

    with pytest.raises(ValueError, match="최소 하나"):
        cell.paragraphs[0].remove()
    assert cell.text == "하나"


def test_a_header_paragraph_is_removed_from_its_header() -> None:
    doc = HwpxDocument.new()
    header = doc.page.set_header(text="머리말")
    header.add_paragraph()
    story = header.element.find(f"{HP}subList")
    last = HwpxOxmlParagraph(story.findall(f"{HP}p")[-1], doc.sections[0])

    last.remove()

    assert len(story.findall(f"{HP}p")) == 1


def test_a_body_paragraph_still_goes_and_a_second_remove_is_quiet() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("지울 문단")
    before = len(doc.paragraphs)

    paragraph.remove()
    paragraph.remove()

    assert len(doc.paragraphs) == before - 1


def test_a_cell_paragraph_takes_its_model_back_in_place() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.text = "셀 글"
    paragraph = cell.paragraphs[0]
    model = paragraph.to_model()

    paragraph.apply_model(model)

    assert [p.text for p in cell.paragraphs] == ["셀 글"]
