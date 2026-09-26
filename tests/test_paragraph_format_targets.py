"""doc.styles.apply_paragraph_format(paragraphs=...) formats cell, header and footer paragraphs."""

from __future__ import annotations

import io

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxTypeError, HwpxValueError
from hwpx.oxml.namespaces import HH, HP

FORMAT = {"spacing_before_pt": 4, "spacing_after_pt": 4, "line_spacing_percent": 130, "alignment": "CENTER"}


def _para_pr(doc: HwpxDocument, paragraph) -> dict[str, object]:
    element = doc._root.headers[0].element.find(f".//{HH}paraPr[@id='{paragraph.para_pr_id_ref}']")
    assert element is not None
    local = {node.tag.rsplit("}", 1)[-1]: node for node in element.iter()}
    return {
        "align": local["align"].get("horizontal"),
        "line_spacing": {node.get("value") for node in element.iter() if node.tag == f"{HH}lineSpacing"},
        "prev": {node.get("value") for node in element.iter() if node.tag.endswith("}prev")},
        "next": {node.get("value") for node in element.iter() if node.tag.endswith("}next")},
    }


def _formatted(doc: HwpxDocument, paragraph) -> bool:
    shape = _para_pr(doc, paragraph)
    return shape["align"] == "CENTER" and shape["line_spacing"] == {"130"} and shape["prev"] == {"400"} \
        and shape["next"] == {"400"}


def _doc_with_stories() -> tuple[HwpxDocument, object, object, object]:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    table = doc.add_table(2, 2)
    table.cell(0, 0).text = "첫 칸"
    table.cell(0, 1).text = "둘째 칸"
    header = doc.page.set_header(text="머리말")
    footer = doc.page.set_footer(text="꼬리말")
    return doc, table, header, footer


def test_cell_header_and_footer_paragraphs_take_the_format() -> None:
    doc, table, header, footer = _doc_with_stories()
    targets = [table.cell(0, 0).paragraphs[0], *header.paragraphs, *footer.paragraphs]

    result = doc.styles.apply_paragraph_format(paragraphs=targets, **FORMAT)

    assert result.formatted == 3
    assert all(_formatted(doc, paragraph) for paragraph in targets)


def test_other_paragraphs_sharing_the_shape_keep_it() -> None:
    doc, table, header, _ = _doc_with_stories()
    other_cell = table.cell(0, 1).paragraphs[0]
    body = doc.paragraphs[-1]
    before = (other_cell.para_pr_id_ref, body.para_pr_id_ref, _para_pr(doc, other_cell))

    doc.styles.apply_paragraph_format(paragraphs=[table.cell(0, 0).paragraphs[0]], alignment="CENTER")

    assert (other_cell.para_pr_id_ref, body.para_pr_id_ref, _para_pr(doc, other_cell)) == before
    assert _para_pr(doc, table.cell(0, 0).paragraphs[0])["align"] == "CENTER"


def test_a_paragraph_of_a_nested_table_can_be_a_target() -> None:
    doc = HwpxDocument.new()
    inner = doc.add_table(1, 1).cell(0, 0).paragraphs[0].add_table(1, 1)
    inner.cell(0, 0).text = "안쪽"

    doc.styles.apply_paragraph_format(paragraphs=inner.cell(0, 0).paragraphs, **FORMAT)

    assert _formatted(doc, inner.cell(0, 0).paragraphs[0])


def test_the_result_lists_body_indexes_only() -> None:
    doc, table, header, _ = _doc_with_stories()
    body_index = len(doc.paragraphs) - 1

    result = doc.styles.apply_paragraph_format(
        paragraphs=[doc.paragraphs[body_index], table.cell(0, 0).paragraphs[0], *header.paragraphs],
        alignment="RIGHT",
    )

    assert result.formatted == 3
    assert result.paragraphs == (body_index,)


def test_a_paragraph_of_another_document_is_refused_before_any_change() -> None:
    doc, table, _, _ = _doc_with_stories()
    other = HwpxDocument.new()
    other.add_paragraph("다른 문서")
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    header_xml = doc._root.headers[0].element
    tab_count = len(header_xml.findall(f".//{HH}tabPr"))
    before = cell_paragraph.para_pr_id_ref

    with pytest.raises(HwpxValueError) as refused:
        doc.styles.apply_paragraph_format(
            paragraphs=[cell_paragraph, other.paragraphs[-1]], alignment="CENTER", tab_stops=[{"pos_mm": 20}]
        )

    assert refused.value.code == "paragraph-not-in-document"
    assert refused.value.context["position"] == 1
    assert cell_paragraph.para_pr_id_ref == before
    assert len(header_xml.findall(f".//{HH}tabPr")) == tab_count


def test_a_removed_paragraph_is_refused() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("남음")
    gone = doc.add_paragraph("지움")
    gone.remove()

    with pytest.raises(HwpxValueError) as refused:
        doc.styles.apply_paragraph_format(paragraphs=[gone], alignment="CENTER")

    assert refused.value.code == "paragraph-not-in-document"


@pytest.mark.parametrize(
    ("kwargs", "code", "error"),
    [
        ({"paragraphs": [], "alignment": "CENTER"}, "paragraph-indexes-empty", HwpxValueError),
        ({"paragraphs": ["본문"], "alignment": "CENTER"}, "paragraph-invalid-type", HwpxTypeError),
        ({"paragraphs": "PARAGRAPHS", "paragraph_index": 0, "alignment": "CENTER"},
         "paragraph-argument-conflict", HwpxValueError),
        ({"paragraphs": "PARAGRAPHS", "paragraph_indexes": [0], "alignment": "CENTER"},
         "paragraph-argument-conflict", HwpxValueError),
    ],
)
def test_bad_target_arguments_are_refused(kwargs, code, error) -> None:
    doc, table, _, _ = _doc_with_stories()
    if kwargs["paragraphs"] == "PARAGRAPHS":
        kwargs = {**kwargs, "paragraphs": [table.cell(0, 0).paragraphs[0]]}

    with pytest.raises(error) as refused:
        doc.styles.apply_paragraph_format(**kwargs)

    assert refused.value.code == code


def test_applying_twice_reuses_the_same_shape() -> None:
    doc, table, _, _ = _doc_with_stories()
    paragraph = table.cell(0, 0).paragraphs[0]

    doc.styles.apply_paragraph_format(paragraphs=[paragraph], **FORMAT)
    first = paragraph.para_pr_id_ref
    doc.styles.apply_paragraph_format(paragraphs=[paragraph], **FORMAT)

    assert paragraph.para_pr_id_ref == first


def test_the_format_survives_saving_and_keeps_runs_and_fields() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.add_run("굵게", bold=True)
    doc.fields.add("이름", prompt="이름", paragraph=paragraph)
    runs_before = [run.text for run in paragraph.runs]
    field_count = len(paragraph.element.findall(f".//{HP}fieldBegin"))

    doc.styles.apply_paragraph_format(paragraphs=[paragraph], **FORMAT)
    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))
    again = reopened.tables.all[0].cell(0, 0).paragraphs[0]

    assert _formatted(reopened, again)
    assert [run.text for run in again.runs] == runs_before
    assert len(again.element.findall(f".//{HP}fieldBegin")) == field_count


def test_the_formatted_paragraphs_lose_their_line_caches() -> None:
    doc, table, _, _ = _doc_with_stories()
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.element.append(paragraph.element.makeelement(f"{HP}linesegarray", {}))

    doc.styles.apply_paragraph_format(paragraphs=[paragraph], line_spacing_percent=130)

    assert paragraph.element.find(f"{HP}linesegarray") is None


def test_a_small_guide_formats_every_story_and_stays_valid() -> None:
    from hwpx.tools.validator import validate_document

    doc = HwpxDocument.new()
    doc.add_heading("안내서", level=1)
    body = doc.add_paragraph("")
    body.add_run("본문은 10.5pt로 쓴다.", size=10.5)
    table = doc.add_table(2, 2)
    for col, label in enumerate(("항목", "내용")):
        table.cell(0, col).text = label
        table.set_cell_shading(0, col, "#D9E2F3")
    table.cell(1, 0).text = "일정"
    table.cell(1, 1).text = "9월"
    header = doc.page.set_header(text="안내서 머리말")
    footer = doc.page.set_page_number(format="page/total")
    cells = [paragraph for row in range(2) for col in range(2) for paragraph in table.cell(row, col).paragraphs]
    stories = [*header.paragraphs, *footer.paragraphs]

    doc.styles.apply_paragraph_format(paragraphs=[body], spacing_before_pt=4, spacing_after_pt=7)
    doc.styles.apply_paragraph_format(paragraphs=cells, spacing_before_pt=4, spacing_after_pt=4, line_spacing_percent=130)
    doc.styles.apply_paragraph_format(paragraphs=stories, alignment="CENTER")
    data = doc.to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(data))
    again = reopened.tables.all[0]
    [body_again] = [p for p in reopened.paragraphs if p.text == "본문은 10.5pt로 쓴다."]

    assert (_para_pr(reopened, body_again)["prev"], _para_pr(reopened, body_again)["next"]) == ({"400"}, {"700"})
    assert all(_para_pr(reopened, p)["line_spacing"] == {"130"} for row in range(2) for col in range(2)
               for p in again.cell(row, col).paragraphs)
    assert all(_para_pr(reopened, p)["align"] == "CENTER"
               for story in (reopened.sections[0].properties.headers + reopened.sections[0].properties.footers)
               for p in story.paragraphs)
    assert not validate_document(data).errors
