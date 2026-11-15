# SPDX-License-Identifier: Apache-2.0
"""Markdown → HWPX: what the writer used to drop or get wrong (code, outline, pictures, links, notes, quotes …)."""

from __future__ import annotations

import io
import struct
import time
import warnings
import zipfile
import zlib

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxTypeError
from hwpx.tools.markdown_import import MarkdownStyle, append_markdown, from_markdown

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _texts(doc) -> list[str]:
    return [paragraph.text for paragraph in doc.paragraphs]


def _section_xml(doc) -> str:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _shape(doc, paragraph):
    return doc.styles.paragraph_property(paragraph.para_pr_id_ref)


def _heading(doc, paragraph) -> tuple[str, int] | None:
    heading = _shape(doc, paragraph).heading
    return None if heading is None else (heading.type, int(heading.level))


def _style_name(doc, paragraph) -> str:
    return doc.styles.resolve(int(paragraph.style_id_ref)).name


def _tables(doc):
    return [table for paragraph in doc.paragraphs for table in paragraph.tables]


def _quiet(markdown: str, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # these inputs carry everything over: no warning
        return from_markdown(markdown, **kwargs)


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


# -- code ---------------------------------------------------------------------


def test_a_code_block_keeps_every_character_and_line() -> None:
    code = "def f(a, *args, **kw):\n    return a*2 * 3  # __init__ [x](y) <b>"
    doc = _quiet(f"앞\n\n```python\n{code}\n```\n\n뒤", style="plain")

    assert _texts(doc) == ["앞", code, "뒤"]
    run = next(run for run in doc.paragraphs[1].runs if run.text)
    assert doc.styles.font_face(run.char_pr_id_ref) == "돋움체"
    assert _shape(doc, doc.paragraphs[1]).align.horizontal == "LEFT"


def test_inline_code_is_kept_as_written_in_the_code_typeface() -> None:
    doc = _quiet("명령 `a*b*c` 와 `` `**x**` `` 끝", style="plain")

    assert _texts(doc) == ["명령 a*b*c 와 `**x**` 끝"]
    faces = {run.text: doc.styles.font_face(run.char_pr_id_ref) for run in doc.paragraphs[0].runs if run.text}
    assert faces["a*b*c"] == "돋움체" and faces["`**x**`"] == "돋움체"
    assert faces["명령 "] != "돋움체"
    plain = from_markdown("`x`", style=MarkdownStyle(code_font=None, body_font="바탕"))
    assert plain.styles.font_face(next(run for run in plain.paragraphs[0].runs if run.text).char_pr_id_ref) == "바탕"


# -- outline -------------------------------------------------------------------


def test_headings_are_outline_paragraphs_that_hancom_numbers_no_second_time() -> None:
    from hwpx.tools import toc_author

    doc = _quiet("# 제목\n\n## 대항목\n\n### 소항목\n\n#### 세부\n\n##### 다섯\n\n###### 여섯\n\n본문", style="plain")
    paragraphs = doc.paragraphs

    assert [_heading(doc, paragraph) for paragraph in paragraphs[:6]] == [("OUTLINE", level) for level in range(6)]
    assert [_style_name(doc, paragraph) for paragraph in paragraphs[:6]] == [f"개요 {level}" for level in range(1, 7)]
    assert _heading(doc, paragraphs[6]) in (None, ("NONE", 0)) and paragraphs[6].style_id_ref == "0"
    # the outline numbering draws nothing, so the number a heading writes is the only one shown
    section = doc.oxml.sections[0].element
    shape = next(node for node in section.iter(f"{_HP}secPr")).get("outlineShapeIDRef")
    numbering = doc.styles.numbering(shape)
    assert [(child.text or "") for child in numbering.children if child.name == "paraHead"] == [""] * 10
    found = toc_author.outline_heading_paragraphs(doc)
    assert [(level, text) for _paragraph, level, text in found] == [
        (1, "제목"), (2, "대항목"), (3, "소항목"), (4, "세부"), (5, "다섯"), (6, "여섯")
    ]
    assert toc_author.add_native_toc(doc)["entryCount"] == 6


def test_the_report_look_marks_the_heading_text_inside_its_banner_and_box() -> None:
    from hwpx.tools import toc_author

    doc = _quiet("# 계획\n\n## 목적\n\n### 근거\n\n본문")
    banner, box = _tables(doc)
    title = banner.cell(1, 0).paragraphs[0]
    section = box.cell(0, 1).paragraphs[0]

    assert (_heading(doc, title), _style_name(doc, title)) == (("OUTLINE", 0), "개요 1")
    assert (_heading(doc, section), _style_name(doc, section)) == (("OUTLINE", 1), "개요 2")
    assert _heading(doc, box.cell(0, 0).paragraphs[0]) in (None, ("NONE", 0))  # the number cell is no heading
    assert [text for _paragraph, _level, text in toc_author.outline_heading_paragraphs(doc)] == ["1. 근거"]


def test_markdown_added_to_a_document_with_numbered_outlines_keeps_the_style_only() -> None:
    doc = HwpxDocument.new()
    doc.add_heading("기존 제목", 1)
    before = [(child.text or "") for child in doc.styles.numbering("1").children if child.name == "paraHead"]

    doc.text.append_markdown("# 덧붙인 제목\n\n## 덧붙인 항목\n")
    added = [paragraph for paragraph in doc.paragraphs if paragraph.text.startswith("덧붙인")]

    # Hancom would draw "1." before each: the heading keeps its outline style but no outline level
    assert [_style_name(doc, paragraph) for paragraph in added] == ["개요 1", "개요 2"]
    assert [_heading(doc, paragraph) for paragraph in added] == [("NONE", 0), ("NONE", 0)]
    assert [(child.text or "") for child in doc.styles.numbering("1").children if child.name == "paraHead"] == before


# -- pictures ------------------------------------------------------------------


def test_a_picture_under_base_dir_is_placed_with_its_description(tmp_path) -> None:
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "school.png").write_bytes(_png(400, 200))

    doc = _quiet("앞 문단\n\n![학교 전경](img/school.png)\n\n뒤 문단", style="plain", base_dir=tmp_path)
    xml = _section_xml(doc)

    assert xml.count("<hp:pic ") == 1
    assert "!" not in "".join(_texts(doc))
    picture = next(doc.oxml.sections[0].element.iter(f"{_HP}pic"))
    size = picture.find(f"{_HP}sz")
    assert (int(size.get("width")), int(size.get("height"))) == (400 * 75, 200 * 75)
    assert picture.find(f"{_HP}shapeComment").text == "학교 전경"
    caption = picture.find(f"{_HP}caption")
    assert caption is not None and "학교 전경" in "".join(caption.itertext())
    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))
    assert reopened.validate().ok


def test_a_wide_picture_is_made_as_wide_as_the_text(tmp_path) -> None:
    (tmp_path / "wide.png").write_bytes(_png(3000, 1000))

    doc = _quiet("![넓은 그림](wide.png)", base_dir=tmp_path)
    picture = next(doc.oxml.sections[0].element.iter(f"{_HP}pic"))
    size = picture.find(f"{_HP}sz")
    margins = doc.page.margins()
    text_width = doc.page.size().width - margins.left - margins.right

    assert int(size.get("width")) == text_width
    assert int(size.get("height")) == round(text_width / 3)


@pytest.mark.parametrize(
    "source,reason",
    [
        ("missing.png", "not found: missing.png"),
        ("https://example.com/a.png", "not a file"),
        ("../outside.png", "outside base_dir"),
        ("notes.txt", "not a PNG, JPEG, GIF or BMP"),
    ],
)
def test_a_picture_that_cannot_be_read_leaves_its_description_and_a_warning(tmp_path, source, reason) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "outside.png").write_bytes(_png(10, 10))
    (base / "notes.txt").write_text("글", encoding="utf-8")

    with pytest.warns(UserWarning, match="picture") as caught:
        doc = from_markdown(f"![학교 전경]({source})\n\n아래", style="plain", base_dir=base)

    assert _texts(doc) == ["학교 전경", "아래"]
    assert "<hp:pic " not in _section_xml(doc)
    assert reason in str(caught[0].message)


def test_no_picture_file_is_read_without_base_dir(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.png").write_bytes(_png(10, 10))
    monkeypatch.chdir(tmp_path)

    with pytest.warns(UserWarning, match="no base_dir"):
        doc = from_markdown("![그림](a.png)", style="plain")

    assert "<hp:pic " not in _section_xml(doc) and _texts(doc) == ["그림"]


# -- links, notes, quotes, rules --------------------------------------------------


def test_links_are_hyperlinks() -> None:
    doc = _quiet(
        "[교육청](https://www.example.go.kr) 과 <https://a.b/c>, [참고][r] 그리고 <x@y.kr>\n\n[r]: https://ref.kr/p",
        style="plain",
    )
    xml = _section_xml(doc)

    assert _texts(doc) == ["교육청 과 https://a.b/c, 참고 그리고 x@y.kr"]
    assert xml.count('type="HYPERLINK"') == 4
    for url in ("https://www.example.go.kr", "https://a.b/c", "https://ref.kr/p", "mailto:x@y.kr"):
        assert url in xml
    link = next(run for run in doc.paragraphs[0].runs if run.text == "교육청")
    assert doc.styles.char_property(link.char_pr_id_ref).attributes["textColor"] == "#0000FF"


def test_a_footnote_reference_becomes_a_footnote() -> None:
    doc = _quiet("본문이 있다.[^1] 그리고 또.[^note]\n\n[^1]: 첫 각주 **내용**.\n[^note]: 둘째\n    이어지는 줄", style="plain")
    xml = _section_xml(doc)

    assert _texts(doc)[0].startswith("본문이 있다.")
    assert "[^" not in "".join(_texts(doc))
    assert xml.count("<hp:footNote ") + xml.count("<hp:footNote>") == 2
    assert "첫 각주 내용." in xml and "둘째 이어지는 줄" in xml


def test_a_quote_stands_in_from_the_text_around_it() -> None:
    doc = _quiet("앞\n\n> 인용한 말이다.\n> 둘째 줄.\n>\n> - 인용 안 목록\n\n뒤", style="plain")
    by_text = {paragraph.text: paragraph for paragraph in doc.paragraphs}

    quoted = by_text["인용한 말이다. 둘째 줄."]
    assert int(_shape(doc, quoted).margin.left) > 0 == int(_shape(doc, by_text["앞"]).margin.left)
    assert int(_shape(doc, by_text["인용 안 목록"]).margin.left) > int(_shape(doc, quoted).margin.left) - 1
    assert int(_shape(doc, by_text["뒤"]).margin.left) == 0


def test_a_rule_is_dropped_without_a_warning() -> None:
    doc = _quiet("위\n\n---\n\n아래\n\n***\n", style="plain")

    assert _texts(doc) == ["위", "아래"]


# -- what is not carried over -------------------------------------------------------


def test_what_is_not_carried_over_is_named_in_one_warning() -> None:
    with pytest.warns(UserWarning) as caught:
        doc = from_markdown("<b>굵게</b> 본문[^9]\n\n[^unused]: 아무도 안 부름\n\n![그림](a.png)", style="plain")

    assert len(caught) == 1
    message = str(caught[0].message)
    assert message.startswith("from_markdown: Markdown not carried over:")
    for part in ("2 HTML tag(s)", "1 footnote reference(s) without a definition", "[^9]", "1 footnote definition(s)", "1 picture(s)"):
        assert part in message
    assert _texts(doc)[0] == "<b>굵게</b> 본문[^9]"

    other = HwpxDocument.new()
    with pytest.warns(UserWarning, match="^append_markdown: "):
        append_markdown(other, "<i>x</i>")


# -- tables ----------------------------------------------------------------------


def test_a_table_without_its_outer_pipes_is_a_table() -> None:
    doc = _quiet("앞 문단\n구분 | 내용\n---|:---:\n기간 | 3월\n대상 | 전교생\n\n뒤", style="plain")
    (table,) = _tables(doc)

    assert (table.row_count, table.column_count) == (3, 2)
    assert [[cell.text for cell in row.cells] for row in table.rows] == [["구분", "내용"], ["기간", "3월"], ["대상", "전교생"]]
    assert "앞 문단" in _texts(doc) and "뒤" in _texts(doc)
    assert _texts(from_markdown("a | b 는 표가 아니다", style="plain")) == ["a | b 는 표가 아니다"]


def test_the_header_row_repeats_on_each_page() -> None:
    doc = _quiet("| 구분 | 내용 |\n|---|---|\n" + "".join(f"| {i} | 줄 |\n" for i in range(5)))
    (table,) = _tables(doc)

    assert table.element.get("repeatHeader") == "1"
    assert [table.cell(0, col).element.get("header") for col in range(2)] == ["1", "1"]
    assert table.cell(1, 0).element.get("header") != "1"
    headless = _tables(_quiet("| a | b |\n| c | d |\n"))[0]
    assert headless.element.get("repeatHeader") == "0"


# -- numbers ----------------------------------------------------------------------


def test_numbers_a_heading_writes_itself_are_not_numbered_again() -> None:
    doc = _quiet("## 3.1 소수점 번호\n\n### A. 영문 번호\n\n### b) 소문자\n\n### 3.2.1. 세 겹\n\n### 1.5배 늘었다\n")
    (box,) = _tables(doc)

    assert (box.cell(0, 0).text, box.cell(0, 1).text) == ("3.1", "소수점 번호")
    assert [text for text in _texts(doc) if text] == ["A. 영문 번호", "b) 소문자", "3.2.1. 세 겹", "1. 1.5배 늘었다"]


def test_markdown_added_in_parts_numbers_on() -> None:
    doc = _quiet("# 계획\n\n## 목적\n\n### 근거\n\n### 범위\n")
    append_markdown(doc, "### 대상\n\n## 방침\n\n### 편성\n", style="report")
    append_markdown(doc, "## 일정\n", style="report")

    boxes = _tables(doc)[1:]
    assert [(box.cell(0, 0).text, box.cell(0, 1).text) for box in boxes] == [("Ⅰ", "목적"), ("Ⅱ", "방침"), ("Ⅲ", "일정")]
    assert [text for text in _texts(doc) if text] == ["1. 근거", "2. 범위", "3. 대상", "1. 편성"]


def test_fifth_and_sixth_level_headings_are_levels_of_their_own() -> None:
    doc = _quiet("#### 넷\n\n##### 다섯\n\n##### 다섯 둘\n\n###### 여섯\n\n#### 넷 둘\n\n##### 다섯 셋\n")

    assert [text for text in _texts(doc) if text] == ["가. 넷", "1) 다섯", "2) 다섯 둘", "가) 여섯", "나. 넷 둘", "1) 다섯 셋"]
    plain = _quiet("#### 넷\n\n##### 다섯\n\n###### 여섯\n", style="plain")
    assert _texts(plain) == ["넷", "다섯", "여섯"]


def test_a_nested_numbered_list_numbers_its_depths_as_hancom_does() -> None:
    doc = _quiet("1. 첫째\n   1. 안의 하나\n      1. 더 안\n2. 둘째\n", style="plain")
    heading = _shape(doc, doc.paragraphs[0]).heading
    numbering = doc.styles.numbering(heading.id_ref)
    heads = {int(child.attributes["level"]): child for child in numbering.children if child.name == "paraHead"}

    assert [(heads[level].text, heads[level].attributes["numFormat"]) for level in (1, 2, 3)] == [
        ("^1.", "DIGIT"),
        ("^2.", "HANGUL_SYLLABLE"),
        ("^3)", "DIGIT"),
    ]
    assert {_shape(doc, paragraph).heading.id_ref for paragraph in doc.paragraphs} == {heading.id_ref}
    assert [int(_shape(doc, paragraph).heading.level) for paragraph in doc.paragraphs] == [0, 1, 2, 0]
    again = _quiet("1. 하나\n\n중간\n\n1. 다시\n", style="plain")
    first, second = (_shape(again, again.paragraphs[i]).heading.id_ref for i in (0, 2))
    assert first != second  # a second list starts again


def test_a_long_list_is_written_without_looking_each_item_up(monkeypatch) -> None:
    reads = []
    paragraphs = HwpxDocument.paragraphs

    def counted(self):
        reads.append(1)
        return paragraphs.fget(self)

    monkeypatch.setattr(HwpxDocument, "paragraphs", property(counted))
    markdown = "\n".join(f"- 항목 {number} 내용을 적는다" for number in range(1600))
    started = time.perf_counter()
    doc = _quiet(markdown)
    elapsed = time.perf_counter() - started

    assert len(doc.paragraphs) == 1600
    assert len(reads) < 10  # each item looked itself up in every paragraph of the body: 2.9 s
    assert elapsed < 10


# -- small syntax and arguments -------------------------------------------------------


def test_setext_headings_tasks_strike_and_underscore_italics() -> None:
    doc = _quiet("큰 제목\n====\n\n작은 제목\n---\n\n- [ ] 할 일\n- [x] 끝난 일\n\n~~지운 글~~ _기울임_ 과 snake_case_name", style="plain")

    assert _texts(doc) == ["큰 제목", "작은 제목", "☐ 할 일", "☑ 끝난 일", "지운 글 기울임 과 snake_case_name"]
    assert [_heading(doc, paragraph) for paragraph in doc.paragraphs[:2]] == [("OUTLINE", 0), ("OUTLINE", 1)]
    runs = {run.text: doc.styles.char_property(run.char_pr_id_ref) for run in doc.paragraphs[4].runs if run.text}
    assert runs["지운 글"].child_attributes.get("strikeout", {}).get("shape", "NONE") != "NONE"
    assert "italic" in runs["기울임"].child_attributes
    assert "italic" not in runs[" 과 snake_case_name"].child_attributes


@pytest.mark.parametrize("value", [None, b"# x", 3])
def test_markdown_that_is_not_text_is_refused(value) -> None:
    with pytest.raises(HwpxTypeError) as caught:
        from_markdown(value)  # type: ignore[arg-type]
    assert isinstance(caught.value, TypeError)
    with pytest.raises(HwpxTypeError):
        append_markdown(HwpxDocument.new(), value)  # type: ignore[arg-type]


def test_everything_together_saves_reopens_and_validates(tmp_path) -> None:
    (tmp_path / "a.png").write_bytes(_png(40, 30))
    markdown = (
        "# 제목\n\n## 개요\n\n본문[^1] [링크](https://x.kr) `코드`\n\n![그림](a.png)\n\n> 인용\n\n"
        "```\n*a* **b**\n```\n\n1. 하나\n   1. 가\n\n구분 | 내용\n---|---\n가 | 나\n\n[^1]: 각주\n"
    )
    for style in ("report", "plain"):
        doc = _quiet(markdown, style=style, base_dir=tmp_path)
        path = tmp_path / f"{style}.hwpx"
        doc.save_to_path(path)
        reopened = HwpxDocument.open(path)
        assert reopened.validate().ok
        assert "*a* **b**" in [paragraph.text for paragraph in reopened.paragraphs]
