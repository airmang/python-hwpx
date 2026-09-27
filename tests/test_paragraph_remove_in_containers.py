"""Paragraph objects of table cells, headers and footers can be removed and rewritten in place."""

from __future__ import annotations

import io
import warnings

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
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


@pytest.mark.parametrize(
    "holder",
    ["section", "cell", "header"],
)
def test_the_last_paragraph_refusal_is_typed_and_names_its_container(holder: str) -> None:
    doc = HwpxDocument.new()
    if holder == "section":
        paragraph = doc.paragraphs[0]
    elif holder == "cell":
        paragraph = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    else:
        header = doc.page.set_header(text="머리말")
        story = header.element.find(f"{HP}subList")
        paragraph = HwpxOxmlParagraph(story.findall(f"{HP}p")[0], doc.sections[0])

    with pytest.raises(HwpxValueError, match="최소 하나") as caught:
        paragraph.remove()

    assert isinstance(caught.value, ValueError)
    assert caught.value.code == "paragraph-remove-last"
    assert caught.value.context["container"] == holder
    assert caught.value.suggestion


def _cell_holding_a_nested_table_after_an_empty_paragraph() -> bytes:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.add_table(1, 1).cell(0, 0).text = "안쪽"
    assert [(p.text, len(p.tables)) for p in cell.paragraphs] == [("", 0), ("", 1)]
    return doc.to_bytes()


def test_removing_a_cell_paragraph_writes_the_same_bytes_as_editing_the_tree() -> None:
    source = _cell_holding_a_nested_table_after_an_empty_paragraph()
    by_tree = HwpxDocument.open(io.BytesIO(source))
    by_api = HwpxDocument.open(io.BytesIO(source))

    tree_cell = by_tree.tables.all[0].cell(0, 0)
    tree_cell.element.find(f"{HP}subList").remove(tree_cell.paragraphs[0].element)
    by_tree.sections[0].mark_dirty()
    api_cell = by_api.tables.all[0].cell(0, 0)
    api_cell.paragraphs[0].remove()

    assert by_tree.to_bytes() == by_api.to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(by_api.to_bytes())).tables.all[0].cell(0, 0)
    assert len(reopened.paragraphs) == 1
    assert reopened.tables[0].cell(0, 0).text == "안쪽"


def test_apply_model_on_a_cell_paragraph_does_not_truth_test_an_element() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    cell.text = "셀 글"
    paragraph = cell.paragraphs[0]
    model = paragraph.to_model()

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        paragraph.apply_model(model)

    assert [p.text for p in cell.paragraphs] == ["셀 글"]
