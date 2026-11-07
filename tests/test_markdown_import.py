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


# -- clean new-document mode ----------------------------------------------


def test_default_document_still_inherits() -> None:
    doc = HwpxDocument.new()
    heading = doc.add_heading("제목", 1)
    paragraph = doc.add_paragraph("본문")
    assert paragraph.para_pr_id_ref == heading.para_pr_id_ref


def test_clean_document_does_not_inherit_unless_asked() -> None:
    doc = HwpxDocument.new(inherit_style=False)
    heading = doc.add_heading("제목", 1)
    paragraph = doc.add_paragraph("본문")
    assert paragraph.para_pr_id_ref != heading.para_pr_id_ref
    assert paragraph.style_id_ref == "0"
    explicit = doc.add_paragraph("물려받음", inherit_style=True)
    assert explicit.para_pr_id_ref == paragraph.para_pr_id_ref  # inherits from the previous paragraph
