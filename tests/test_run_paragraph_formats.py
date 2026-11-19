# SPDX-License-Identifier: Apache-2.0
"""Character and paragraph formats read and written on one run or one paragraph,
character-range formatting, and the style verbs built on the same derivation."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.model import Paragraph
from hwpx.errors import HwpxLookupError, HwpxTypeError, HwpxValueError
from hwpx.objects import Alignment, LineSpacing, LineSpacingType

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    document.save(buffer)
    reopened = HwpxDocument.open(buffer.getvalue())
    assert reopened.validate().ok
    return reopened


def _definitions(document: HwpxDocument, kind: str) -> dict[str, bytes]:
    header = document.oxml.headers[0].element
    return {
        element.get("id"): etree.tostring(element)
        for element in header.iter(f"{HH}{kind}")
    }


def _item_counts_match(document: HwpxDocument) -> None:
    header = document.oxml.headers[0].element
    for container, kind in (("charProperties", "charPr"), ("paraProperties", "paraPr"),
                            ("tabProperties", "tabPr"), ("borderFills", "borderFill"), ("styles", "style")):
        element = header.find(f".//{HH}{container}")
        if element is not None:
            assert element.get("itemCnt") == str(len(element.findall(f"{HH}{kind}")))


def _has_cache(paragraph) -> bool:
    return any(etree.QName(child).localname.lower() == "linesegarray" for child in paragraph.element)


# --------------------------------------------------------------------------
# Runs


def test_run_size_on_a_hancom_saved_document_changes_that_run_alone() -> None:
    document = HwpxDocument.open(HANCOM / "formfit_bold_advances.hwpx")
    first, second = document.paragraphs[1], document.paragraphs[3]
    assert first.runs[0].char_pr_id_ref == second.runs[0].char_pr_id_ref == "7"
    assert _has_cache(first) and _has_cache(second)
    before = _definitions(document, "charPr")

    run = first.runs[0]
    assert run.size == 9.0
    run.size = 13.7

    assert run.size == 13.7
    assert second.runs[0].char_pr_id_ref == "7" and second.runs[0].size == 9.0
    assert not _has_cache(first) and _has_cache(second)
    after = _definitions(document, "charPr")
    assert {key: value for key, value in after.items() if key in before} == before
    assert len(after) == len(before) + 1
    _item_counts_match(document)

    run.size = 13.7  # the same value again: nothing new
    second.runs[0].size = 13.7  # another run asking for the same content reuses it
    assert len(_definitions(document, "charPr")) == len(before) + 1
    assert second.runs[0].char_pr_id_ref == run.char_pr_id_ref

    reopened = _reopen(document)
    assert reopened.paragraphs[1].runs[0].size == 13.7
    assert reopened.paragraphs[5].runs[0].size == 9.0


def test_run_format_properties_round_trip() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("서식")
    other = document.add_paragraph("그대로")
    run = paragraph.runs[-1]
    assert (run.size, run.font, run.color, run.highlight) == (10.0, "함초롬바탕", "#000000", None)
    assert (run.bold, run.italic, run.strike, run.superscript, run.subscript) == (False, False, False, False, False)
    assert (run.letter_spacing, run.ratio) == (0, 100)

    run.font = "맑은 고딕"
    run.color = "#ff0000"
    run.highlight = "#FFFF00"
    run.strike = True
    run.superscript = True
    run.letter_spacing = -5
    run.ratio = 90
    run.set_format(italic=True, size=11.5)
    assert run.font == "맑은 고딕"
    assert document.styles.font_face(run.char_pr_id_ref, "LATIN") == "맑은 고딕"
    assert (run.color, run.highlight, run.strike, run.superscript) == ("#FF0000", "#FFFF00", True, True)
    assert (run.letter_spacing, run.ratio, run.italic, run.size) == (-5, 90, True, 11.5)
    run.subscript = True
    assert (run.superscript, run.subscript) == (False, True)
    run.highlight = None
    assert run.highlight is None

    run.set_font("Arial", lang="LATIN")
    assert run.font == "맑은 고딕"
    assert document.styles.font_face(run.char_pr_id_ref, "LATIN") == "Arial"

    reopened = _reopen(document)
    again = reopened.paragraphs[0].runs[-1]
    assert (again.size, again.font, again.color, again.subscript, again.ratio) == (11.5, "맑은 고딕", "#FF0000", True, 90)
    assert reopened.paragraphs[1].runs[-1].size == 10.0 and other.runs[-1].color == "#000000"
    style = reopened.styles.char_property(again.char_pr_id_ref)
    assert style is not None and (style.size, style.color, style.font) == (11.5, "#FF0000", "맑은 고딕")
    _item_counts_match(reopened)


def test_run_format_refuses_bad_values_before_changing_anything() -> None:
    document = HwpxDocument.new()
    run = document.add_paragraph("x").runs[-1]
    before = _definitions(document, "charPr")
    with pytest.raises(HwpxTypeError) as unknown:
        run.set_format(weight=700)
    assert unknown.value.code == "style-run-format-invalid"
    with pytest.raises(HwpxValueError) as spacing:
        run.set_format(letter_spacing=101, size=12)
    assert spacing.value.code == "style-run-format-invalid"
    with pytest.raises(HwpxValueError) as color:
        run.color = "빨강"
    assert color.value.code == "style-color-invalid"
    with pytest.raises(HwpxValueError) as both:
        run.set_format(superscript=True, subscript=True)
    assert both.value.code == "style-run-format-invalid"
    with pytest.raises(HwpxValueError) as empty:
        run.set_format()
    assert empty.value.code == "style-run-format-empty"
    assert _definitions(document, "charPr") == before and run.size == 10.0


def test_run_text_writes_tabs_and_line_breaks_as_elements_and_reads_them_back() -> None:
    document = HwpxDocument.new()
    run = document.add_paragraph("x").runs[-1]
    run.text = "a\tb\nc"
    assert run.text == "a\tb\nc"
    text = run.element.find(f"{HP}t")
    assert [etree.QName(child).localname for child in text] == ["tab", "lineBreak"]


# --------------------------------------------------------------------------
# Paragraphs


def test_paragraph_formats_read_from_a_hancom_saved_shape() -> None:
    document = HwpxDocument.open(HANCOM / "formfit_font_line_heights.hwpx")
    section = document.sections[0]
    every = [Paragraph(element, section) for element in section.element.iter(f"{HP}p")]  # cells too
    spacings = {paragraph.line_spacing for paragraph in every}
    assert LineSpacing(LineSpacingType.FIXED, 2000) in spacings  # case 2000, default 4000
    assert LineSpacing("AT_LEAST", 1200) in spacings
    assert LineSpacing("BETWEEN_LINES", 300) in spacings
    first = document.paragraphs[0]
    assert isinstance(first.alignment, Alignment)
    assert first.outline_level == 0 and first.style is not None


def test_paragraph_format_setters_change_that_paragraph_alone() -> None:
    document = HwpxDocument.open(HANCOM / "formfit_bold_advances.hwpx")
    target, neighbour = document.paragraphs[1], document.paragraphs[2]
    assert target.para_pr_id_ref == neighbour.para_pr_id_ref
    before = _definitions(document, "paraPr")

    target.alignment = "center"
    target.indent_left_mm = 10
    target.indent_right_mm = 5.5
    target.first_line_indent_mm = -3
    target.spacing_before_pt = 6
    target.spacing_after_pt = 4
    target.line_spacing = 200
    target.keep_with_next = True
    target.keep_lines = True
    target.widow_orphan = True
    target.page_break_before = True

    assert target.alignment is Alignment.CENTER and target.alignment == "CENTER"
    assert (target.indent_left_mm, target.indent_right_mm, target.first_line_indent_mm) == (10.0, 5.5, -3.0)
    assert (target.spacing_before_pt, target.spacing_after_pt) == (6.0, 4.0)
    assert target.line_spacing == LineSpacing("PERCENT", 200)
    assert (target.keep_with_next, target.keep_lines, target.widow_orphan, target.page_break_before) == (
        True, True, True, True)
    assert neighbour.alignment is Alignment.JUSTIFY and neighbour.indent_left_mm == 0.0
    assert neighbour.line_spacing == LineSpacing("PERCENT", 160) and neighbour.keep_with_next is False
    assert not _has_cache(target) and _has_cache(neighbour)
    after = _definitions(document, "paraPr")
    assert {key: value for key, value in after.items() if key in before} == before
    _item_counts_match(document)

    # Hancom keeps a margin and a length line spacing twice over in hp:default.
    shape = document.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{target.para_pr_id_ref}']")
    assert shape.find(f".//{HP}case/{HH}margin/*[@value='2835']") is not None
    assert shape.find(f".//{HP}default/{HH}margin/*[@value='5670']") is not None
    target.line_spacing = LineSpacing("FIXED", 1800)
    shape = document.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{target.para_pr_id_ref}']")
    assert shape.find(f".//{HP}case/{HH}lineSpacing").get("value") == "1800"
    assert shape.find(f".//{HP}default/{HH}lineSpacing").get("value") == "3600"

    count = len(_definitions(document, "paraPr"))
    target.alignment = Alignment.CENTER  # unchanged: nothing new
    neighbour.line_spacing = 160
    assert len(_definitions(document, "paraPr")) == count

    reopened = _reopen(document)
    again = reopened.paragraphs[1]
    assert again.line_spacing == LineSpacing("FIXED", 1800) and again.indent_left_mm == 10.0
    assert reopened.paragraphs[2].alignment is Alignment.JUSTIFY


def _paragraph_values(paragraph) -> tuple:
    return (paragraph.alignment, paragraph.indent_left_mm, paragraph.indent_right_mm, paragraph.first_line_indent_mm,
            paragraph.spacing_before_pt, paragraph.spacing_after_pt, paragraph.line_spacing,
            paragraph.page_break_before, paragraph.keep_with_next, paragraph.outline_level)


@pytest.mark.parametrize("name, value, index", [
    ("indent_left_mm", 20.0, 1), ("alignment", Alignment.RIGHT, 0), ("line_spacing", LineSpacing("PERCENT", 250), 6),
])
def test_one_paragraph_setter_changes_one_value_of_one_paragraph(name, value, index) -> None:
    document = HwpxDocument.open(HANCOM / "formfit_bold_advances.hwpx")
    target, other = document.paragraphs[1], document.paragraphs[2]
    target_before, other_before = _paragraph_values(target), _paragraph_values(other)
    setattr(target, name, value)
    after = _paragraph_values(target)
    assert after[index] == value
    assert after[:index] + after[index + 1:] == target_before[:index] + target_before[index + 1:]
    assert _paragraph_values(other) == other_before


def test_paragraph_breaks_outline_level_and_style() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    assert paragraph.page_break is False and paragraph.outline_level == 0
    paragraph.page_break = True
    assert paragraph.element.get("pageBreak") == "1" and paragraph.page_break
    paragraph.outline_level = 3
    assert paragraph.outline_level == 3
    paragraph.outline_level = 0
    assert paragraph.outline_level == 0

    heading = document.add_paragraph("제목", style="개요 2")
    styled = document.add_paragraph("제목")
    styled.style = "Outline 2"
    assert styled.style is not None and styled.style.name == "개요 2"
    assert (styled.style_id_ref, styled.para_pr_id_ref, styled.char_pr_id_ref) == (
        heading.style_id_ref, heading.para_pr_id_ref, heading.char_pr_id_ref)
    assert styled.outline_level == 2
    with pytest.raises(HwpxLookupError) as missing:
        styled.style = "개요2"
    assert missing.value.code == "style-not-found"
    with pytest.raises(HwpxValueError) as bad:
        styled.alignment = "middle-ish"
    assert bad.value.code == "paragraph-alignment-invalid"
    with pytest.raises(HwpxValueError) as level:
        styled.outline_level = 11
    assert level.value.code == "paragraph-outline-level-out-of-range"
    _reopen(document)


# --------------------------------------------------------------------------
# Splitting runs and formatting a range


def _range_document():
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("가나\t다라\n마바 사")
    return document, paragraph


def test_format_range_keeps_tabs_line_breaks_and_text() -> None:
    document, paragraph = _range_document()
    text = paragraph.text
    runs = paragraph.format_range(1, 7, bold=True, size=12)

    assert paragraph.text == text
    assert "".join(run.text for run in runs) == text[1:7] == "나\t다라\n마"
    assert all(run.bold and run.size == 12.0 for run in runs)
    pieces = [(run.text, run.bold) for run in paragraph.runs if run.text]
    assert pieces == [("가", False), ("나\t다라\n마", True), ("바 사", False)]
    elements = [etree.QName(child).localname for run in runs for t in run.element.findall(f"{HP}t") for child in t]
    assert elements == ["tab", "lineBreak"]
    # The section settings stay in the paragraph's first run, once.
    assert len(paragraph.element.findall(f".//{HP}secPr")) == 1
    assert paragraph.runs[0].element.find(f"{HP}secPr") is not None

    paragraph.format_range(0, 2, italic=True)  # across the boundary made before
    assert [(run.text, run.bold, run.italic) for run in paragraph.runs if run.text][:2] == [
        ("가", False, True), ("나", True, True)]
    reopened = _reopen(document)
    assert reopened.paragraphs[0].text == text


def test_split_run_returns_the_run_starting_at_the_offset() -> None:
    _, paragraph = _range_document()
    run = paragraph.split_run(3)
    assert run.text == "\t다라\n마바 사"[1:] or run.text.startswith("다")
    assert paragraph.text == "가나\t다라\n마바 사"
    same = paragraph.split_run(3)  # already a boundary
    assert same.element is run.element
    with pytest.raises(HwpxValueError) as outside:
        paragraph.split_run(0)
    assert outside.value.code == "paragraph-range-invalid"
    with pytest.raises(HwpxValueError):
        paragraph.split_run(len(paragraph.text))


def test_format_range_counts_controls_as_no_character() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞")
    paragraph.add_bookmark("표시")
    paragraph.add_run("뒤쪽")
    assert paragraph.text == "앞뒤쪽"
    runs = paragraph.format_range(1, 2, color="#0000FF")
    assert [run.text for run in runs] == ["뒤"]
    assert [mark.name for mark in paragraph.bookmarks] == ["표시"]
    assert paragraph.text == "앞뒤쪽"
    with pytest.raises(HwpxValueError) as past:
        paragraph.format_range(0, 9, bold=True)
    assert past.value.code == "paragraph-range-invalid"
    assert paragraph.format_range(2, 2, bold=True) == ()
    _reopen(document)


def test_format_range_on_a_hancom_saved_paragraph() -> None:
    document = HwpxDocument.open(HANCOM / "formfit_bold_advances.hwpx")
    paragraph = document.paragraphs[1]
    text = paragraph.text
    runs = paragraph.format_range(1, 4, underline=True)
    assert paragraph.text == text and "".join(run.text for run in runs) == text[1:4]
    assert all(run.underline for run in runs)
    assert document.paragraphs[3].runs[0].underline is False
    reopened = _reopen(document)
    assert reopened.paragraphs[1].text == text


def test_a_format_edit_changes_only_the_header_and_that_section() -> None:
    source = (HANCOM / "formfit_bold_advances.hwpx").read_bytes()
    document = HwpxDocument.open(source)
    document.paragraphs[1].runs[0].size = 12
    document.paragraphs[1].alignment = "RIGHT"
    buffer = io.BytesIO()
    document.save(buffer)
    before, after = zipfile.ZipFile(io.BytesIO(source)), zipfile.ZipFile(buffer)
    changed = {name for name in before.namelist() if before.read(name) != after.read(name)}
    assert changed == {"Contents/header.xml", "Contents/section0.xml"}
