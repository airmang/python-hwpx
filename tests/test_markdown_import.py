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
    doc = from_markdown(SAMPLE, style="plain")
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
    doc = from_markdown("# 제목\n\n본문\n\n1. 하나\n2. 둘\n\n뒤 문단\n", style="plain")
    texts = [p.text for p in doc.paragraphs]
    for name in ("본문", "뒤 문단"):
        paragraph = doc.paragraphs[texts.index(name)]
        assert _has_heading(doc, paragraph) in (None, "NONE")
        assert paragraph.style_id_ref == "0"


def test_save_reopen_and_editor_open_safety(tmp_path) -> None:
    doc = from_markdown(SAMPLE, style="plain")
    path = tmp_path / "md.hwpx"
    doc.save_to_path(path)
    reopened = HwpxDocument.open(path)
    assert [p.text for p in reopened.paragraphs] == [p.text for p in doc.paragraphs]
    assert "| 1학기 | 10 | 12 |" in reopened.text.markdown()
    assert validate_editor_open_safety(path).to_dict()["ok"] is True


def test_unknown_markdown_never_raises() -> None:
    doc = from_markdown("> 인용\n\n---\n\n<div>html</div>\n\n```\ncode  kept\n```\n\n- - -\n\n####### 7\n", style="plain")
    texts = [p.text for p in doc.paragraphs]
    assert "인용" in texts
    assert "<div>html</div>" in texts
    assert "code  kept" in texts
    assert "####### 7" in texts


def test_empty_and_table_first_markdown() -> None:
    assert [p.text for p in from_markdown("", style="plain").paragraphs] == [""]
    doc = from_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n\n뒤\n", style="plain")
    assert doc.paragraphs[0].text == ""  # the section paragraph is not a table anchor
    assert doc.paragraphs[-1].text == "뒤"


def test_hard_line_break_and_br_in_cells() -> None:
    doc = from_markdown("첫 줄  \n둘째 줄\n\n| a<br>b |\n", style="plain")
    assert doc.paragraphs[0].text == "첫 줄\n둘째 줄"
    (table,) = [t for p in doc.paragraphs for t in p.tables]
    assert "a" in table.cell(0, 0).text and "b" in table.cell(0, 0).text


def test_numbered_list_start_is_kept() -> None:
    doc = from_markdown("3. 셋\n4. 넷\n", style="plain")
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
    doc = from_markdown(LABELLED, style="plain")
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
        "| 이름 | 대상 | 인원 | 비고 |\n|:---|:---:|---:|---|\n| 코딩 기초 | 1학년 | 24 | 심화반 예정 |\n",
        style="plain",
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
    doc = from_markdown(LABELLED, style="plain")
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
    doc = from_markdown("| 하나뿐 |\n|---|\n| 값 |\n\n" + LABELLED, style="plain")
    path = tmp_path / "tables.hwpx"

    doc.save_to_path(path)

    assert validate_editor_open_safety(path).to_dict()["ok"] is True
    reopened = HwpxDocument.open(path)
    assert "| 기간 | 2026. 3. 2.(월) ~ 2026. 7. 17.(금) |" in reopened.text.markdown()


# -- nested lists and the report look -----------------------------------------

REPORT = (
    "# 운영 계획\n\n## 목적\n\n본문이다.\n\n## 운영 방침\n\n### 편성\n\n- 하나\n  - 둘\n    - 셋\n\n"
    "### 선정\n\n#### 기준\n\n## 현황\n\n| 구분 | 내용 |\n|---|---|\n| 기간 | 한 학기 |\n"
)


def _shape(doc, paragraph):
    return doc.styles.paragraph_property(paragraph.para_pr_id_ref)


def test_nested_list_items_move_right_by_depth() -> None:
    doc = from_markdown("- 하나\n  - 둘\n    - 셋\n- 넷\n\n1. 가\n   1. 나\n", style="plain")
    lefts = [int(_shape(doc, paragraph).margin.left) for paragraph in doc.paragraphs]

    assert lefts[0] == lefts[3] == lefts[4] == 0
    assert 0 < lefts[1] < lefts[2] and lefts[2] == 2 * lefts[1]
    assert lefts[5] == lefts[1]
    # the items are still list items of their depth
    assert [_shape(doc, paragraph).heading.level for paragraph in doc.paragraphs[:3]] == [0, 1, 2]

    flat = from_markdown("- 하나\n  - 둘\n", style=MarkdownStyle(list_indent_mm=0))
    assert [int(_shape(flat, paragraph).margin.left) for paragraph in flat.paragraphs] == [0, 0]
    wide = from_markdown("- 하나\n  - 둘\n", style=MarkdownStyle(list_indent_mm=10))
    assert int(_shape(wide, wide.paragraphs[1]).margin.left) > lefts[1]


#: A numbered look without boxes: a centred title over a rule, headings numbered 1. 가. 1).
NUMBERED = MarkdownStyle(
    heading_sizes=(20.0, 15.0, 13.0, 12.0),
    body_size=12.0,
    table_size=11.0,
    title_align="center",
    title_rule=True,
    heading_numbers=(None, "1.", "가.", "1)"),
)


def _tables(doc):
    return [table for paragraph in doc.paragraphs for table in paragraph.tables]


def _border(doc, cell):
    return doc.styles.border_fill_info(cell.element.get("borderFillIDRef"))


def _line(side) -> tuple[str, float]:
    return side.type, side.width_mm


def _run(paragraph, text):
    return next(run for run in paragraph.runs if run.text == text)


def _ink(doc, run) -> str:
    return doc.styles.char_property(run.char_pr_id_ref).attributes["textColor"]


def test_a_style_numbers_headings_and_centres_the_title_over_a_rule() -> None:
    doc = from_markdown(REPORT, style=NUMBERED)
    texts = [paragraph.text for paragraph in doc.paragraphs]

    assert texts[0] == "운영 계획"  # the title carries no number
    assert [text for text in texts if text[:1].isdigit() or text[:2] in ("가.", "나.")] == [
        "1. 목적",
        "2. 운영 방침",
        "가. 편성",
        "나. 선정",
        "1) 기준",
        "3. 현황",
    ]
    title = _shape(doc, doc.paragraphs[0])
    assert title.align.horizontal == "CENTER"
    assert title.border.border_fill_id_ref != _shape(doc, doc.paragraphs[2]).border.border_fill_id_ref  # the rule
    assert _shape(doc, doc.paragraphs[1]).align.horizontal != "CENTER"
    assert _char(doc, doc.paragraphs[0], "운영 계획").height == 2000
    assert _char(doc, doc.paragraphs[2], "본문이다.").height == 1200
    assert _char(doc, _table(doc).cell(1, 1).paragraphs[0], "한 학기").height == 1100


def test_the_report_look_draws_the_title_in_a_banner_with_colour_strips() -> None:
    doc = from_markdown(REPORT, style="report")

    banner = doc.paragraphs[0].tables[0]  # in the blank document's first line: nothing stands above the title
    assert (banner.row_count, banner.column_count) == (3, 2)
    title_cell = banner.cell(1, 0)
    assert title_cell.text == "운영 계획" and title_cell.span == (1, 2)
    strips = [banner.cell(row, col) for row, col in ((0, 0), (0, 1), (2, 0), (2, 1))]
    assert [_border(doc, strip).fill for strip in strips] == ["#0099FF", "#FFCC00", "#339900", "#FF3300"]
    assert _border(doc, title_cell).fill == "#EFEFEF"
    for cell in (*strips, title_cell):
        box = _border(doc, cell)
        assert {box.left.type, box.right.type, box.top.type, box.bottom.type} == {"NONE"}
    # a strip is a row lower than a line of text: its empty line is set in a very small size
    assert strips[0].height < 500 < title_cell.height
    assert all(_look(doc, run).height == 100 for run in strips[0].paragraphs[0].runs)

    title = _run(title_cell.paragraphs[0], "운영 계획")
    assert (_look(doc, title).height, _look(doc, title).bold) == (2100, True)
    assert doc.styles.font_face(title.char_pr_id_ref) == "HY헤드라인M"
    assert _align(doc, title_cell) == "CENTER"


def test_the_report_look_draws_a_section_as_a_numbered_box() -> None:
    doc = from_markdown(REPORT, style="report")

    boxes = _tables(doc)[1:4]
    assert [(box.cell(0, 0).text, box.cell(0, 1).text) for box in boxes] == [
        ("Ⅰ", "목적"),
        ("Ⅱ", "운영 방침"),
        ("Ⅲ", "현황"),
    ]
    number_cell, heading_cell = boxes[0].cell(0, 0), boxes[0].cell(0, 1)
    filled = _border(doc, number_cell)
    assert filled.fill == "#000066"
    assert {(_line(side), side.color) for side in (filled.left, filled.right, filled.top, filled.bottom)} == {
        (("SOLID", 0.4), "#88A1EB")
    }
    open_box = _border(doc, heading_cell)
    assert (_line(open_box.left), _line(open_box.bottom)) == (("SOLID", 0.4), ("SOLID", 0.4))
    assert (open_box.top.type, open_box.right.type, open_box.fill) == ("NONE", "NONE", None)

    number = _run(number_cell.paragraphs[0], "Ⅰ")
    heading = _run(heading_cell.paragraphs[0], "목적")
    assert (_look(doc, number).height, _ink(doc, number)) == (1800, "#FFFFFF")
    assert (_look(doc, heading).height, _look(doc, heading).bold, _ink(doc, heading)) == (1600, True, "#1B1760")
    assert doc.styles.font_face(heading.char_pr_id_ref) == "HY헤드라인M"
    # the box is as wide as its heading needs, and the longer heading has the wider box
    text_width = _tables(doc)[0].cell(1, 0).width
    assert number_cell.width + heading_cell.width < text_width / 2
    assert boxes[1].cell(0, 1).width > heading_cell.width


def test_a_boxed_section_shows_the_number_the_heading_carries() -> None:
    doc = from_markdown(
        "## Ⅱ. 현황\n\n## 3) 계획\n\n## (4) 일정\n\n## 제5장 맺음\n\n## 그 밖\n\n"
        "## 쪽 너비보다 긴 제목은 표가 본문 너비를 넘지 않게 하고 칸 안에서 줄을 바꾼다 그래서 일부러 길게 쓴다\n",
        style="report",
    )

    boxes = _tables(doc)
    assert [[cell.text for row in box.rows for cell in row.cells] for box in boxes[:5]] == [
        ["Ⅱ", "현황"],
        ["3", "계획"],
        ["(4)", "일정"],
        ["제5장 맺음"],  # a chapter name stays in the heading, which is drawn without a number cell
        ["Ⅰ", "그 밖"],  # no number of its own: the first the look counts
    ]
    lone = _border(doc, boxes[3].cell(0, 0))
    assert (_line(lone.left), _line(lone.bottom), lone.top.type) == (("SOLID", 0.4), ("SOLID", 0.4), "NONE")
    margins = doc.page.margins()
    text_width = doc.page.size().width - margins.left - margins.right
    assert sum(cell.width for cell in boxes[5].rows[0].cells) == text_width  # never wider than the text


def test_the_report_look_sets_headings_body_and_bullets() -> None:
    doc = from_markdown(REPORT, style="report")
    texts = [paragraph.text for paragraph in doc.paragraphs]

    assert [text for text in texts if text[:2] in ("1.", "2.", "가.")] == ["1. 편성", "2. 선정", "가. 기준"]
    item = doc.paragraphs[texts.index("1. 편성")]
    assert (_char(doc, item, "편성").height, _char(doc, item, "편성").bold) == (1400, False)
    assert doc.styles.font_face(_run(item, "편성").char_pr_id_ref) == "HY헤드라인M"
    small = doc.paragraphs[texts.index("가. 기준")]
    assert (_char(doc, small, "기준").height, _char(doc, small, "기준").bold) == (1200, False)
    assert doc.styles.font_face(_run(small, "기준").char_pr_id_ref) == "휴먼명조"
    assert int(_shape(doc, small).margin.left) > 0 == int(_shape(doc, item).margin.left)

    body = doc.paragraphs[texts.index("본문이다.")]
    assert _char(doc, body, "본문이다.").height == 1200
    assert doc.styles.font_face(_run(body, "본문이다.").char_pr_id_ref) == "휴먼명조"

    bullets = [doc.paragraphs[texts.index(name)] for name in ("하나", "둘", "셋")]
    assert [doc.styles.bullet(_shape(doc, bullet).heading.id_ref).char for bullet in bullets] == ["□", "-", "·"]
    lefts = [int(_shape(doc, bullet).margin.left) for bullet in bullets]
    assert 0 < lefts[0] < lefts[1] < lefts[2]  # the first depth stands in from the heading too


def test_a_paragraph_stands_as_far_right_as_the_heading_above_it() -> None:
    doc = from_markdown("### 항목\n\n항목 아래\n\n#### 작은 항목\n\n작은 항목 아래\n\n### 다음\n\n다시 왼쪽\n", style="report")
    left = {paragraph.text: int(_shape(doc, paragraph).margin.left) for paragraph in doc.paragraphs}

    assert left["항목 아래"] == left["다시 왼쪽"] == 0
    assert left["작은 항목 아래"] == left["가. 작은 항목"] > 0


def test_the_report_look_rules_a_table() -> None:
    doc = from_markdown(REPORT + "| 기관 | 세움 |\n", style="report")
    table = _tables(doc)[-1]
    heavy, thin, double = ("SOLID", 0.4), ("SOLID", 0.15), ("DOUBLE_SLIM", 0.5)

    def lines(row: int, col: int):
        box = _border(doc, table.cell(row, col))
        return _line(box.left) if box.left.type != "NONE" else None, _line(box.right) if box.right.type != "NONE" else None, _line(box.top), _line(box.bottom)

    assert lines(0, 0) == (None, thin, heavy, double)  # open at the sides, a double line under the header
    assert lines(0, 1) == (thin, None, heavy, double)
    assert lines(1, 0) == (None, thin, double, thin)
    assert lines(2, 1) == (thin, None, thin, heavy)
    assert _border(doc, table.cell(0, 0)).fill == "#DFE6F7" and _border(doc, table.cell(1, 0)).fill is None

    cell_text = _run(table.cell(1, 1).paragraphs[0], "한 학기")
    assert _look(doc, cell_text).height == 1200
    assert doc.styles.font_face(cell_text.char_pr_id_ref) == "한컴산뜻돋움"
    row_height = round(9.2 * 7200 / 25.4)
    assert {cell.height for row in table.rows for cell in row.cells} == {row_height}
    assert table.height == 3 * row_height

    headless = from_markdown("| 가 | 나 |\n| 다 | 라 |\n", style="report")  # no header row: no double line, no fill
    first = _border(headless, _tables(headless)[0].cell(0, 0))
    assert (_line(first.top), _line(first.bottom), first.fill) == (heavy, thin, None)
    only = from_markdown("| 구분 | 내용 |\n|---|---|\n", style="report")  # a header row alone closes the table
    assert _line(_border(only, _tables(only)[0].cell(0, 0)).bottom) == heavy


def test_the_report_look_sets_the_page_of_a_new_document_only() -> None:
    doc = from_markdown(REPORT, style="report")
    margins = doc.page.margins()
    mm = 7200 / 25.4

    assert [margins.left, margins.right, margins.top, margins.bottom] == [round(20 * mm)] * 3 + [round(15 * mm)]
    assert [margins.header, margins.footer] == [round(10 * mm)] * 2
    # the banner is as wide as the text between those margins
    assert doc.paragraphs[0].tables[0].cell(1, 0).width == doc.page.size().width - margins.left - margins.right

    existing = HwpxDocument.new()
    before = existing.page.margins()
    existing.text.append_markdown(REPORT, style="report")
    assert existing.page.margins() == before  # the caller's page is the caller's


def test_the_report_look_by_name_is_the_report_style() -> None:
    by_name = from_markdown(REPORT, style="report")
    korean = from_markdown(REPORT, style="보고서")
    by_style = from_markdown(REPORT, style=MarkdownStyle.report())

    assert [p.text for p in by_name.paragraphs] == [p.text for p in by_style.paragraphs] == [p.text for p in korean.paragraphs]
    with pytest.raises(ValueError, match="unknown Markdown style") as caught:
        from_markdown("# 제목", style="letter")
    assert caught.value.code == "text-markdown-style-invalid"  # type: ignore[attr-defined]


def test_the_report_look_puts_a_page_number_in_a_new_document_only(tmp_path) -> None:
    def has_footer(document) -> bool:
        path = tmp_path / "out.hwpx"
        document.save_to_path(path)
        import zipfile

        with zipfile.ZipFile(path) as archive:
            return b"<hp:footer" in archive.read("Contents/section0.xml")

    assert has_footer(from_markdown(REPORT, style="report")) is True
    assert has_footer(from_markdown(REPORT, style="plain")) is False
    existing = HwpxDocument.new()
    existing.text.append_markdown(REPORT, style="report")
    assert has_footer(existing) is False  # the caller's footer is the caller's


def test_the_page_number_takes_a_character_on_each_side() -> None:
    def footer_text(document) -> list[str]:
        footer = document.oxml.sections[0].element.find(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}footer")
        return [node.text or "" for node in footer.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}t")]

    assert footer_text(from_markdown("본문", style="report")) == ["- ", " -"]  # drawn "- 1 -"
    assert footer_text(from_markdown("본문", style=MarkdownStyle(page_number=True))) == []


def test_a_heading_with_its_own_number_is_not_numbered_again() -> None:
    doc = from_markdown(
        "# 계획\n\n## 1. 목적\n\n## 2. 방침\n\n### 가. 편성\n\n### 2026학년도 일정\n\n## Ⅲ. 현황\n\n## 제4장 맺음\n",
        style=NUMBERED,
    )

    assert [paragraph.text for paragraph in doc.paragraphs] == [
        "계획",
        "1. 목적",
        "2. 방침",
        "가. 편성",
        "가. 2026학년도 일정",  # no number of its own, so it takes the level's first
        "Ⅲ. 현황",
        "제4장 맺음",
    ]


def test_lower_numbers_start_again_under_a_heading_that_carries_its_own_number() -> None:
    doc = from_markdown(
        "## Ⅰ. 개요\n\n### 근거\n\n### 목적\n\n## Ⅱ. 편성\n\n### 일정\n\n#### 첫날\n\n### 3. 장소\n\n#### 강의실\n",
        style="report",
    )

    assert [paragraph.text for paragraph in doc.paragraphs if paragraph.text] == [
        "1. 근거",
        "2. 목적",
        "1. 일정",  # not 3.: the section before it wrote its own number, and the count still starts again
        "가. 첫날",
        "3. 장소",
        "가. 강의실",
    ]


def test_heading_numbers_take_the_forms_asked_for() -> None:
    from hwpx.tools.markdown_import import _NUMBER_FORMS, _ganada

    assert [_ganada(number) for number in (1, 2, 14, 15, 16, 28, 29)] == ["가", "나", "하", "거", "너", "허", "고"]
    assert _ganada(85) == "85"
    assert {form: make(3) for form, make in _NUMBER_FORMS.items()} == {
        "1.": "3.",
        "가.": "다.",
        "1)": "3)",
        "가)": "다)",
        "(1)": "(3)",
        "(가)": "(다)",
        "①": "③",
        "Ⅰ.": "Ⅲ.",
    }
    doc = from_markdown(
        "## 하나\n\n### 둘\n\n## 셋\n\n### 넷\n",
        style=MarkdownStyle(heading_numbers=(None, "Ⅰ.", "①", None)),
    )
    assert [paragraph.text for paragraph in doc.paragraphs] == ["Ⅰ. 하나", "① 둘", "Ⅱ. 셋", "① 넷"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title_align": "middle"},
        {"heading_numbers": (None, "1.")},
        {"heading_numbers": (None, "A.", None, None)},
        {"bullet_chars": ("○", "--")},
        {"table_size": 0},
        {"list_indent_mm": -1},
        {"title_space_after_pt": -1},
        {"title_look": "box"},
        {"section_look": "banner"},
        {"table_look": "lines"},
        {"heading_bold": (True, False)},
        {"heading_bold": "yes"},
        {"heading_fonts": ("HY헤드라인M",)},
        {"heading_fonts": ("", None, None, None)},
        {"heading_indents_mm": (0, 0, 0, -1)},
        {"banner_colors": ("#0099FF", "#FFCC00")},
        {"banner_fill": ""},
        {"section_colors": ("#000066", "#88A1EB", None)},
        {"page_margins_mm": (20, 20)},
        {"page_margins_mm": (20, 20, 20, -15)},
        {"page_number_side": "--"},
        {"table_row_height_mm": 0},
        {"list_first_indent_mm": -1},
        {"body_font": ""},
        {"table_font": 3},
    ],
)
def test_a_style_value_that_cannot_be_drawn_is_refused(kwargs) -> None:
    with pytest.raises(ValueError) as caught:
        MarkdownStyle(**kwargs)
    assert caught.value.code == "text-markdown-style-invalid"  # type: ignore[attr-defined]


def test_bullets_by_depth_and_one_bullet_for_all() -> None:
    def bullets(document) -> list[str]:
        chars = []
        for paragraph in document.paragraphs:
            heading = _shape(document, paragraph).heading
            chars.append(document.styles.bullet(heading.id_ref).char)
        return chars

    md = "- 하나\n  - 둘\n    - 셋\n      - 넷\n"
    assert bullets(from_markdown(md, style=MarkdownStyle(bullet_chars=("○", "-", "·")))) == ["○", "-", "·", "·"]
    assert bullets(from_markdown(md, style=MarkdownStyle(bullet_char="●"))) == ["●"] * 4


def test_the_report_look_saves_and_reopens(tmp_path) -> None:
    path = tmp_path / "report.hwpx"

    from_markdown(REPORT, style="report").save_to_path(path)

    assert validate_editor_open_safety(path).to_dict()["ok"] is True
    reopened = HwpxDocument.open(path)
    assert [box.cell(0, 1).text for box in _tables(reopened)[1:4]] == ["목적", "운영 방침", "현황"]
    assert "1. 편성" in reopened.text.markdown()


def test_heading_bold_and_typefaces_can_be_given_by_level() -> None:
    style = MarkdownStyle(
        heading_bold=(True, False, True, False),
        heading_fonts=("돋움", None, None, "굴림"),
        body_font="바탕",
        table_font="돋움",
    )
    doc = from_markdown("# 하나\n\n## 둘\n\n### 셋\n\n#### 넷\n\n본문\n\n| 칸 |\n|---|\n", style=style)
    by_text = {paragraph.text: paragraph for paragraph in doc.paragraphs}

    assert [_char(doc, by_text[name], name).bold for name in ("하나", "둘", "셋", "넷")] == [True, False, True, False]
    faces = {name: doc.styles.font_face(_run(by_text[name], name).char_pr_id_ref) for name in ("하나", "둘", "넷", "본문")}
    assert faces == {"하나": "돋움", "둘": "바탕", "넷": "굴림", "본문": "바탕"}  # a heading without its own takes the body's
    cell = _table(doc).cell(0, 0).paragraphs[0]
    assert doc.styles.font_face(_run(cell, "칸").char_pr_id_ref) == "돋움"


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


# -- the default look and the byline ---------------------------------------------


def test_a_new_document_takes_the_report_look_and_an_appended_one_the_plain_look() -> None:
    made = from_markdown(REPORT)
    assert made.paragraphs[0].tables[0].cell(1, 0).text == "운영 계획"  # the banner: the report look
    assert [p.text for p in made.paragraphs] == [p.text for p in from_markdown(REPORT, style="report").paragraphs]

    plain = from_markdown(REPORT, style="plain")
    assert plain.paragraphs[0].text == "운영 계획" and not plain.paragraphs[0].tables
    assert [p.text for p in plain.paragraphs] == [p.text for p in from_markdown(REPORT, style=MarkdownStyle()).paragraphs]

    existing = HwpxDocument.new()
    existing.text.append_markdown("# 덧붙인 제목\n\n본문\n")
    assert "덧붙인 제목" in [p.text for p in existing.paragraphs]  # a paragraph, not a banner
    assert not _tables(existing)


def test_the_byline_stands_right_aligned_under_the_title() -> None:
    doc = from_markdown("# 운영 계획\n\n## 목적\n\n본문\n\n# 붙임\n", byline="교무기획부")
    texts = [paragraph.text for paragraph in doc.paragraphs]

    assert texts.count("교무기획부") == 1 and texts[1] == "교무기획부"  # under the first title only
    line = doc.paragraphs[1]
    run = _run(line, "교무기획부")
    assert _shape(doc, line).align.horizontal == "RIGHT"
    assert (_look(doc, run).height, _look(doc, run).bold) == (1300, True)
    assert doc.styles.font_face(run.char_pr_id_ref) == "한컴산뜻돋움"
    # the space kept under the title is kept under the byline instead
    assert int(_shape(doc, doc.paragraphs[0]).margin.next) == 0 < int(_shape(doc, line).margin.next)


def test_the_byline_is_the_first_line_when_there_is_no_title() -> None:
    doc = from_markdown("## 목적\n\n본문\n", style="plain", byline="교무기획부\n2026. 11. 13.")

    first = doc.paragraphs[0]
    assert first.text.replace("\n", " ").split() == ["교무기획부", "2026.", "11.", "13."]
    assert _shape(doc, first).align.horizontal == "RIGHT"
    assert not _look(doc, next(run for run in first.runs if run.text)).bold  # the plain look does not embolden it
    assert doc.paragraphs[1].text == "목적"

    none = from_markdown("# 제목\n", byline="  ")
    assert [paragraph.text for paragraph in none.paragraphs] == [""]  # only the banner's paragraph


def test_append_markdown_takes_a_byline_too() -> None:
    doc = HwpxDocument.new()
    doc.text.append_markdown("# 제목\n\n본문\n", byline="연구부")
    texts = [paragraph.text for paragraph in doc.paragraphs]

    assert texts[texts.index("제목") + 1] == "연구부"
    assert _shape(doc, doc.paragraphs[texts.index("연구부")]).align.horizontal == "RIGHT"


# -- what the report look does by what the text holds ---------------------------------


def _spacing(doc, paragraph) -> int:
    run = next(run for run in paragraph.runs if run.text)
    return int((doc.styles.char_property(run.char_pr_id_ref).child_attributes.get("spacing") or {}).get("hangul", "0"))


def test_a_two_column_table_spreads_its_labels_and_a_wider_one_centres_what_fits() -> None:
    doc = from_markdown(
        "| 구분 | 내용 |\n|---|---|\n| 행사명 | 가을 책 잔치 |\n| 장소 | 도서관 2층 열람실 |\n\n"
        "| 구분 | 맡은 이 | 하는 일 | 인원 |\n|---|---|---|---|\n"
        "| 준비 | 책 고르기 모둠 | 학년마다 읽을 책을 열 권씩 골라 목록을 만들고 도서관 누리집에 올려 누구나 미리 볼 수 있게 한다 | 2 |\n\n"
        "| 번호 | 이름 | 점수 |\n|---|:---|---:|\n| 1 | 가람 | 90 |\n"
    )
    labels, wide, given = _tables(doc)

    assert [_align(doc, labels.cell(row, 0)) for row in (1, 2)] == ["DISTRIBUTE", "DISTRIBUTE"]
    assert _align(doc, labels.cell(1, 1)) not in ("CENTER", "DISTRIBUTE")  # what a label names reads from the left
    assert _align(doc, labels.cell(0, 0)) == "CENTER"  # the header row is centred as before
    # a column whose cells fit on one line is centred, the one that wraps is not
    assert [_align(doc, wide.cell(1, col)) == "CENTER" for col in range(4)] == [True, True, False, True]
    # a column the Markdown aligns itself is left to it
    assert [_align(doc, given.cell(1, col)) for col in range(3)] == ["CENTER", _align(doc, labels.cell(1, 1)), "RIGHT"]

    # the plain look leaves body cells as they are
    plain = _tables(from_markdown("| 구분 | 내용 |\n|---|---|\n| 행사명 | 책 잔치 |\n", style="plain"))[0]
    assert plain.cell(1, 0).paragraphs[0].para_pr_id_ref == plain.cell(1, 1).paragraphs[0].para_pr_id_ref


def test_one_letter_labels_are_centred_not_spread() -> None:
    doc = from_markdown("| 가 | 첫째 항목 |\n| 나 | 둘째 항목 |\n")
    table = _tables(doc)[0]

    assert [_align(doc, table.cell(row, 0)) for row in (0, 1)] == ["CENTER", "CENTER"]


def test_a_list_under_a_small_heading_takes_its_own_bullets() -> None:
    doc = from_markdown("### 항목\n\n- 하나\n  - 둘\n\n#### 작은 항목\n\n- 셋\n  - 넷\n\n### 다음\n\n- 다섯\n")
    by_text = {paragraph.text: paragraph for paragraph in doc.paragraphs}

    def bullet(text: str) -> str:
        return doc.styles.bullet(_shape(doc, by_text[text]).heading.id_ref).char

    assert [bullet(text) for text in ("하나", "둘", "셋", "넷", "다섯")] == ["□", "-", "◦", "-", "□"]
    plain = from_markdown("#### 작은 항목\n\n- 셋\n", style=MarkdownStyle(bullet_chars=("○",)))
    assert plain.styles.bullet(_shape(plain, plain.paragraphs[1]).heading.id_ref).char == "○"


def test_a_note_is_set_in_the_note_size() -> None:
    doc = from_markdown("본문이다.\n\n※ 일정은 바뀔 수 있음\n\n- ※ 목록 안의 표시는 그대로 둔다\n")
    by_text = {paragraph.text: paragraph for paragraph in doc.paragraphs}
    note = _run(by_text["※ 일정은 바뀔 수 있음"], "※ 일정은 바뀔 수 있음")

    assert _look(doc, note).height == 1000
    assert doc.styles.font_face(note.char_pr_id_ref) == "한컴산뜻돋움"
    assert _char(doc, by_text["본문이다."], "본문이다.").height == 1200
    item = by_text["※ 목록 안의 표시는 그대로 둔다"]
    assert _look(doc, next(run for run in item.runs if run.text)).height == 1200
    plain = from_markdown("※ 일정은 바뀔 수 있음\n", style="plain")
    assert _look(plain, next(run for run in plain.paragraphs[0].runs if run.text)).height == 1000  # the base size


#: In the report look, at the first list depth: a little past one line, and well past it.
LITTLE_OVER = "도서관 2층 열람실에서 10월 셋째 주 금요일 오후 3시부터 책 읽어 주기 모임을 연다"
TWO_LINES = "학년마다 읽을 책을 열 권씩 골라 목록을 만들고 도서관 누리집에 올려 누구나 미리 볼 수 있게 하며 빌려 간 책은 두 주 안에 돌려받는다"


def test_a_list_item_a_little_too_long_is_kept_on_one_line_by_its_letter_spacing() -> None:
    doc = from_markdown(f"- 짧은 항목\n- {LITTLE_OVER}\n- {TWO_LINES}\n  - {LITTLE_OVER}\n\n{LITTLE_OVER}\n")
    short, over, long, nested, body = doc.paragraphs

    assert _spacing(doc, short) == 0  # fits as it is
    assert -8 <= _spacing(doc, over) < 0
    assert _spacing(doc, long) == 0  # would need more than the look allows: it wraps as it is
    assert _spacing(doc, body) == 0  # a paragraph of prose is not a line to keep whole
    assert -8 <= _spacing(doc, nested) <= 0
    # every run of the item is narrowed alike, the bold ones too
    mixed = from_markdown(f"- {LITTLE_OVER[:20]}**{LITTLE_OVER[20:30]}**{LITTLE_OVER[30:]}\n")
    runs = [run for run in mixed.paragraphs[0].runs if run.text]
    spacings = {(mixed.styles.char_property(run.char_pr_id_ref).child_attributes.get("spacing") or {}).get("hangul") for run in runs}
    assert len(runs) == 3 and len(spacings) == 1 and int(spacings.pop()) < 0
    assert _look(mixed, runs[1]).bold and not _look(mixed, runs[0]).bold


def test_the_letter_spacing_is_never_narrowed_past_what_the_style_allows() -> None:
    from dataclasses import replace

    never = from_markdown(f"- {LITTLE_OVER}\n", style=replace(MarkdownStyle.report(), list_fit_spacing=0))
    assert _spacing(never, never.paragraphs[0]) == 0
    plain = from_markdown(f"- {LITTLE_OVER}\n", style="plain")
    assert _spacing(plain, plain.paragraphs[0]) == 0
    slight = from_markdown(f"- {LITTLE_OVER}\n", style=replace(MarkdownStyle.report(), list_fit_spacing=1))
    assert _spacing(slight, slight.paragraphs[0]) in (0, -1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"table_align": "center"},
        {"list_fit_spacing": 11},
        {"list_fit_spacing": -1},
        {"list_fit_spacing": 2.5},
        {"list_fit_spacing": True},
        {"sub_bullet_chars": ("◦◦",)},
        {"note_size": 0},
        {"note_font": ""},
        {"byline_size": 0},
        {"byline_font": ""},
    ],
)
def test_a_value_of_the_newer_fields_that_cannot_be_drawn_is_refused(kwargs) -> None:
    with pytest.raises(ValueError) as caught:
        MarkdownStyle(**kwargs)
    assert caught.value.code == "text-markdown-style-invalid"  # type: ignore[attr-defined]
