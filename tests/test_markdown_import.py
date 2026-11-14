# SPDX-License-Identifier: Apache-2.0
"""Markdown → HWPX (``hwpx.tools.markdown_import``) and the clean new-document mode."""

from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools.markdown_import import MarkdownStyle, from_markdown, parse_inline
from hwpx.tools.package_validator import validate_editor_open_safety


class _Look:
    def __init__(self, run_style) -> None:
        self.bold = "bold" in run_style.child_attributes
        self.italic = "italic" in run_style.child_attributes
        self.height = int(run_style.attributes["height"])


def _look(doc, run) -> _Look:
    return _Look(doc.styles.char_property(run.char_pr_id_ref))


def _char(doc, paragraph, text) -> _Look:
    for run in paragraph.runs:
        if run.text == text:
            return _look(doc, run)
    raise AssertionError(f"no run {text!r}")


def _has_heading(doc, paragraph) -> str | None:
    para_pr = doc.styles.paragraph_property(paragraph.para_pr_id_ref)
    heading = getattr(para_pr, "heading", None)
    return getattr(heading, "type", None) if heading is not None else None


# -- inline ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("plain", [("plain", False, False)]),
        ("a **b** c", [("a ", False, False), ("b", True, False), (" c", False, False)]),
        ("__b__", [("b", True, False)]),
        ("*i* x", [("i", False, True), (" x", False, False)]),
        ("***bi***", [("bi", True, True)]),
        ("2 * 3 = 6", [("2 * 3 = 6", False, False)]),
        ("**unclosed", [("**unclosed", False, False)]),
        (r"\*literal\*", [("*literal*", False, False)]),
        ("see [docs](https://example.com) now", [("see docs now", False, False)]),
        ("`a*b*c`", [("a*b*c", False, False)]),
    ],
)
def test_parse_inline(text, expected) -> None:
    assert parse_inline(text) == expected


# -- blocks ---------------------------------------------------------------

SAMPLE = """# 운영 보고

이 보고서는 **핵심 성과**와 *과제*를 정리한다.
둘째 줄은 이어진다.

## 추진 배경

다음과 같다:
- 첫째 항목
- 둘째 항목
  - 하위 항목
1. 번호 하나
2. 번호 둘

| 구분 | 목표 | 실적 |
|---|:---:|---:|
| 1학기 | 10 | **12** |
| 2학기 | 20 |

### 맺음

끝 문단.
"""


def test_from_markdown_writes_each_construct() -> None:
    doc = from_markdown(SAMPLE)
    texts = [p.text for p in doc.paragraphs]
    assert texts[0] == "운영 보고"  # the blank document's first line is reused
    assert "이 보고서는 핵심 성과와 과제를 정리한다. 둘째 줄은 이어진다." in texts
    assert texts.index("다음과 같다:") + 1 == texts.index("첫째 항목")  # a list interrupts a paragraph

    title = doc.paragraphs[0]
    assert _char(doc, title, "운영 보고").bold
    sub = doc.paragraphs[texts.index("추진 배경")]
    assert _char(doc, sub, "추진 배경").bold

    body = doc.paragraphs[texts.index("이 보고서는 핵심 성과와 과제를 정리한다. 둘째 줄은 이어진다.")]
    assert _char(doc, body, "핵심 성과").bold
    assert _char(doc, body, "과제").italic
    assert not _char(doc, body, "이 보고서는 ").bold

    for name in ("첫째 항목", "둘째 항목", "하위 항목"):
        assert _has_heading(doc, doc.paragraphs[texts.index(name)]) == "BULLET"
    for name in ("번호 하나", "번호 둘"):
        assert _has_heading(doc, doc.paragraphs[texts.index(name)]) == "NUMBER"
    first = doc.paragraphs[texts.index("첫째 항목")]
    nested = doc.paragraphs[texts.index("하위 항목")]
    assert first.para_pr_id_ref != nested.para_pr_id_ref  # level 2 is its own shape

    (table,) = [t for p in doc.paragraphs for t in p.tables]
    assert (table.row_count, table.column_count) == (3, 3)
    assert table.cell(0, 0).text == "구분"
    assert table.cell(2, 2).text == ""  # a short row is padded
    header_run = next(r for r in table.cell(0, 1).paragraphs[0].runs if r.text)
    assert _look(doc, header_run).bold
    assert table.cell(0, 0).element.get("borderFillIDRef") != table.cell(1, 0).element.get("borderFillIDRef")
    bold_cell = next(r for r in table.cell(1, 2).paragraphs[0].runs if r.text)
    assert _look(doc, bold_cell).bold


def test_no_outline_or_list_numbering_leaks_into_following_paragraphs() -> None:
    doc = from_markdown("# 제목\n\n본문\n\n1. 하나\n2. 둘\n\n뒤 문단\n")
    texts = [p.text for p in doc.paragraphs]
    for name in ("본문", "뒤 문단"):
        paragraph = doc.paragraphs[texts.index(name)]
        assert _has_heading(doc, paragraph) in (None, "NONE")
        assert paragraph.style_id_ref == "0"


def test_save_reopen_and_editor_open_safety(tmp_path) -> None:
    doc = from_markdown(SAMPLE)
    path = tmp_path / "md.hwpx"
    doc.save_to_path(path)
    reopened = HwpxDocument.open(path)
    assert [p.text for p in reopened.paragraphs] == [p.text for p in doc.paragraphs]
    assert "| 1학기 | 10 | 12 |" in reopened.text.markdown()
    assert validate_editor_open_safety(path).to_dict()["ok"] is True


def test_unknown_markdown_never_raises() -> None:
    doc = from_markdown("> 인용\n\n---\n\n<div>html</div>\n\n```\ncode  kept\n```\n\n- - -\n\n####### 7\n")
    texts = [p.text for p in doc.paragraphs]
    assert "인용" in texts
    assert "<div>html</div>" in texts
    assert "code  kept" in texts
    assert "####### 7" in texts


def test_empty_and_table_first_markdown() -> None:
    assert [p.text for p in from_markdown("").paragraphs] == [""]
    doc = from_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n\n뒤\n")
    assert doc.paragraphs[0].text == ""  # the section paragraph is not a table anchor
    assert doc.paragraphs[-1].text == "뒤"


def test_hard_line_break_and_br_in_cells() -> None:
    doc = from_markdown("첫 줄  \n둘째 줄\n\n| a<br>b |\n")
    assert doc.paragraphs[0].text == "첫 줄\n둘째 줄"
    (table,) = [t for p in doc.paragraphs for t in p.tables]
    assert "a" in table.cell(0, 0).text and "b" in table.cell(0, 0).text


def test_numbered_list_start_is_kept() -> None:
    doc = from_markdown("3. 셋\n4. 넷\n")
    numbering_id = doc.styles.paragraph_property(doc.paragraphs[0].para_pr_id_ref).heading.id_ref
    numbering = doc.styles.numbering(numbering_id)
    assert numbering is not None
    assert "3" in {child.attributes.get("start") for child in numbering.children if child.name == "paraHead"}


def test_style_overrides_sizes() -> None:
    doc = from_markdown("# 큰 제목\n\n본문", style=MarkdownStyle(heading_sizes=(20, 14, 12, 10), body_size=11))
    assert _char(doc, doc.paragraphs[0], "큰 제목").height == 2000
    assert _char(doc, doc.paragraphs[1], "본문").height == 1100
    with pytest.raises(ValueError):
        MarkdownStyle(heading_sizes=(16, 12))  # type: ignore[arg-type]


def test_append_markdown_adds_to_an_existing_document() -> None:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "기존"
    doc.add_heading("개요 제목", 1)
    doc.text.append_markdown("새 문단\n\n- 항목")
    texts = [p.text for p in doc.paragraphs]
    assert texts[:2] == ["기존", "개요 제목"]
    added = doc.paragraphs[texts.index("새 문단")]
    assert _has_heading(doc, added) in (None, "NONE")  # not the heading's outline


# -- table look -------------------------------------------------------------


def _table(doc):
    (table,) = [t for p in doc.paragraphs for t in p.tables]
    return table


def _align(doc, cell) -> str:
    return doc.styles.paragraph_property(cell.paragraphs[0].para_pr_id_ref).align.horizontal


LABELLED = (
    "| 구분 | 내용 |\n|---|---|\n"
    "| 기간 | 2026. 3. 2.(월) ~ 2026. 7. 17.(금) |\n"
    "| 대상 | 1~3학년 전체 (약 620명) |\n"
)


def test_header_cells_are_centred_and_body_cells_are_left_alone() -> None:
    doc = from_markdown(LABELLED)
    table = _table(doc)
    body = _align(doc, table.cell(1, 1))

    assert [_align(doc, table.cell(0, col)) for col in range(2)] == ["CENTER", "CENTER"]
    assert body != "CENTER"
    assert _align(doc, table.cell(1, 0)) == body


def test_header_alignment_can_be_left_as_the_body_is() -> None:
    doc = from_markdown(LABELLED, style=MarkdownStyle(table_header_align=None))
    table = _table(doc)

    assert _align(doc, table.cell(0, 0)) == _align(doc, table.cell(1, 0))
    with pytest.raises(ValueError, match="table_header_align"):
        MarkdownStyle(table_header_align="middle")


def test_the_separator_row_aligns_whole_columns() -> None:
    doc = from_markdown(
        "| 이름 | 대상 | 인원 | 비고 |\n|:---|:---:|---:|---|\n| 코딩 기초 | 1학년 | 24 | 심화반 예정 |\n"
    )
    table = _table(doc)
    plain = _align(doc, table.cell(1, 3))

    assert [_align(doc, table.cell(1, col)) for col in range(4)] == [plain, "CENTER", "RIGHT", plain]
    # a header cell follows its column's alignment, and is centred where the column has none
    assert _align(doc, table.cell(0, 0)) == plain
    assert _align(doc, table.cell(0, 1)) == "CENTER"
    assert _align(doc, table.cell(0, 2)) == "RIGHT"
    assert _align(doc, table.cell(0, 3)) == "CENTER"
    assert table.cell(1, 2).text == "24"


def test_a_label_column_is_narrow_and_the_text_column_takes_the_rest() -> None:
    doc = from_markdown(LABELLED)
    table = _table(doc)
    equal = _table(from_markdown(LABELLED, style=MarkdownStyle(table_fit_columns=False)))
    label, text = table.cell(0, 0).width, table.cell(0, 1).width

    assert label * 2 < text
    assert label + text == equal.cell(0, 0).width + equal.cell(0, 1).width  # the table is as wide as before
    assert abs(equal.cell(0, 0).width - equal.cell(0, 1).width) <= 1
    assert [table.cell(row, 0).width for row in range(3)] == [label] * 3


def test_short_columns_keep_their_line_when_the_text_does_not_fit() -> None:
    from hwpx.form_fit.measure import estimate_text_width
    from hwpx.tools.markdown_import import _column_weights

    long_text = "학부모 공개 수업 1회 포함, 도서관과 함께 운영하며 지역 강사가 참여한다. " * 3
    rows = [["프로그램", "인원", "비고"], ["독서 토론", "31", long_text]]
    total = 42520

    weights = _column_weights(rows, 3, 10.0, total)

    assert abs(sum(weights) - total) < 1  # the columns fill the table exactly
    assert weights[0] > estimate_text_width("독서 토론", 10.0)  # no wrap in the label column
    assert weights[1] > estimate_text_width("인원", 10.0)
    assert weights[2] == max(weights) and weights[2] < estimate_text_width(long_text, 10.0)


def test_columns_that_fit_are_shared_out_by_their_need() -> None:
    from hwpx.tools.markdown_import import _column_weights

    weights = _column_weights([["가", "가나다라마바사아자차카타파하"]], 2, 10.0, 42520)

    assert sum(weights) < 42520  # set_column_widths stretches them in proportion
    assert weights[0] < weights[1]


def test_too_many_columns_share_the_table_alike() -> None:
    from hwpx.tools.markdown_import import _column_weights

    weights = _column_weights([["긴 낱말이 들어간 칸"] * 30], 30, 10.0, 42520)

    assert weights == [1.0] * 30


def test_a_one_column_table_and_a_fitted_table_save_and_reopen(tmp_path) -> None:
    doc = from_markdown("| 하나뿐 |\n|---|\n| 값 |\n\n" + LABELLED)
    path = tmp_path / "tables.hwpx"

    doc.save_to_path(path)

    assert validate_editor_open_safety(path).to_dict()["ok"] is True
    reopened = HwpxDocument.open(path)
    assert "| 기간 | 2026. 3. 2.(월) ~ 2026. 7. 17.(금) |" in reopened.text.markdown()


# -- clean new-document mode ----------------------------------------------


def test_default_document_inherits_from_body_text_but_not_from_a_heading() -> None:
    doc = HwpxDocument.new()
    heading = doc.add_heading("제목", 1)
    body = doc.add_paragraph("본문")
    # 제목 뒤의 본문은 제목의 문단 모양·스타일(개요)을 받지 않는다. 받으면 한/글이 본문에 개요 번호를 붙인다.
    assert (body.para_pr_id_ref, body.style_id_ref) == ("0", "0")
    assert body.para_pr_id_ref != heading.para_pr_id_ref
    # 본문 뒤의 본문은 전처럼 앞 문단을 따른다.
    styled = doc.add_paragraph("모양을 준 본문", para_pr_id_ref="9", style_id_ref="1")
    following = doc.add_paragraph("이어지는 본문")
    assert (following.para_pr_id_ref, following.style_id_ref) == (styled.para_pr_id_ref, "1")


def test_a_call_that_asks_to_inherit_takes_the_heading_shape() -> None:
    doc = HwpxDocument.new()
    heading = doc.add_heading("제목", 1)
    paragraph = doc.add_paragraph("제목 모양의 문단", inherit_style=True)
    assert (paragraph.para_pr_id_ref, paragraph.style_id_ref) == (heading.para_pr_id_ref, heading.style_id_ref)


def test_clean_document_does_not_inherit_unless_asked() -> None:
    doc = HwpxDocument.new(inherit_style=False)
    heading = doc.add_heading("제목", 1)
    paragraph = doc.add_paragraph("본문")
    assert paragraph.para_pr_id_ref != heading.para_pr_id_ref
    assert paragraph.style_id_ref == "0"
    explicit = doc.add_paragraph("물려받음", inherit_style=True)
    assert explicit.para_pr_id_ref == paragraph.para_pr_id_ref  # inherits from the previous paragraph
