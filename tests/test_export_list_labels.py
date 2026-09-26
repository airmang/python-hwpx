"""``list_labels=True`` writes the labels Hancom draws before numbered, outline and bullet paragraphs.

Counting follows Hancom: one counter per numbering and level, deeper levels restart after a
higher one, and levels skipped on the way down count at their start value.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import _ListLabels, export_html, export_markdown, export_text

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _numbered(count: int) -> HwpxDocument:
    document = HwpxDocument.new()
    for index in range(1, count + 1):
        document.add_paragraph(f"항목{index}")
    document.styles.apply_list_format(paragraph_indexes=list(range(1, count + 1)), kind="number")
    return document


def _header(heads: dict[int, tuple[str, str]]) -> ET.Element:
    header = ET.Element(f"{HH}head")
    numbering = ET.SubElement(header, f"{HH}numbering", {"id": "1"})
    for level, (text, number_format) in heads.items():
        ET.SubElement(numbering, f"{HH}paraHead", {"level": str(level), "numFormat": number_format, "start": "1"}).text = text
    for level in heads:
        para_pr = ET.SubElement(header, f"{HH}paraPr", {"id": str(level)})
        ET.SubElement(para_pr, f"{HH}heading", {"type": "NUMBER", "idRef": "1", "level": str(level - 1)})
    return header


def _labels(heads: dict[int, tuple[str, str]], levels: list[int]) -> list[str]:
    labels = _ListLabels(_header(heads))
    return [labels.label(ET.Element(f"{HP}p", {"paraPrIDRef": str(level)})) for level in levels]


def test_labels_are_off_by_default() -> None:
    assert export_text(_numbered(2)).split("\n") == ["항목1", "항목2"]


def test_numbered_paragraphs_count_up() -> None:
    assert export_text(_numbered(3), list_labels=True).split("\n") == ["1. 항목1", "2. 항목2", "3. 항목3"]


def test_a_deeper_level_restarts_under_each_higher_one() -> None:
    heads = {1: ("^1.", "DIGIT"), 2: ("^2)", "HANGUL_SYLLABLE"), 3: ("(^3)", "CIRCLED_DIGIT")}

    assert _labels(heads, [1, 2, 2, 3, 1, 2]) == ["1.", "가)", "나)", "(①)", "2.", "가)"]


def test_a_skipped_level_counts_at_its_start_value() -> None:
    heads = {1: ("^1.", "DIGIT"), 2: ("^1.^2.", "DIGIT"), 3: ("^1.^2.^3", "ROMAN_SMALL")}

    assert _labels(heads, [3, 3, 2]) == ["1.1.i", "1.1.ii", "1.2."]


def test_caret_n_writes_the_numbers_of_every_level_down_to_its_own() -> None:
    heads = {1: ("^N", "DIGIT"), 2: ("^N", "HANGUL_SYLLABLE"), 3: ("(^N)", "DIGIT")}

    assert _labels(heads, [1, 2, 2, 3, 1, 2]) == ["1.", "1.1.", "1.2.", "(1.2.1.)", "2.", "2.1."]


def test_a_numbering_that_is_not_defined_numbers_every_level() -> None:
    header = ET.Element(f"{HH}head")
    for level in (1, 2):
        para_pr = ET.SubElement(header, f"{HH}paraPr", {"id": str(level)})
        ET.SubElement(para_pr, f"{HH}heading", {"type": "NUMBER", "idRef": "9", "level": str(level - 1)})
    labels = _ListLabels(header)

    assert [labels.label(ET.Element(f"{HP}p", {"paraPrIDRef": str(level)})) for level in (1, 2, 2, 1)] == [
        "1.",
        "1.1.",
        "1.2.",
        "2.",
    ]


def test_a_bullet_that_is_not_defined_is_a_black_circle() -> None:
    header = ET.Element(f"{HH}head")
    para_pr = ET.SubElement(header, f"{HH}paraPr", {"id": "1"})
    ET.SubElement(para_pr, f"{HH}heading", {"type": "BULLET", "idRef": "0", "level": "0"})

    assert _ListLabels(header).label(ET.Element(f"{HP}p", {"paraPrIDRef": "1"})) == "●"


def test_a_numbering_text_of_one_symbol_character_is_written_as_the_symbol() -> None:
    heads = {1: ("\uf09f", "DIGIT"), 2: ("^2\uf06c", "DIGIT")}

    assert _labels(heads, [1, 2]) == ["●", "1\uf06c"]


def test_number_formats() -> None:
    formats = ["LATIN_CAPITAL", "ROMAN_CAPITAL", "HANGUL_JAMO", "CIRCLED_HANGUL_SYLLABLE"]
    labels = [_labels({1: ("^1", number_format)}, [1, 1, 1, 1])[-1] for number_format in formats]

    assert labels == ["D", "IV", "ㄹ", "㉱"]


def test_bullets_take_their_character() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("기본")
    document.add_paragraph("동그라미")
    document.styles.apply_list_format(paragraph_index=1, kind="bullet")
    document.styles.apply_list_format(paragraph_index=2, kind="bullet", bullet_char="●")

    assert export_text(document, list_labels=True).split("\n") == ["- 기본", "● 동그라미"]


def test_symbol_font_bullets_are_written_as_unicode_symbols() -> None:
    document = HwpxDocument.new()
    for text in ("동그라미", "네모", "그대로"):
        document.add_paragraph(text)
    document.styles.apply_list_format(paragraph_index=1, kind="bullet", bullet_char="\uf09f")
    document.styles.apply_list_format(paragraph_index=2, kind="bullet", bullet_char="\uf0a7")
    document.styles.apply_list_format(paragraph_index=3, kind="bullet", bullet_char="\uf0a2")

    assert export_text(document, list_labels=True).split("\n") == ["● 동그라미", "■ 네모", "\uf0a2 그대로"]


def test_symbol_characters_in_the_text_are_kept() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("앞 \uf09f 뒤")

    assert export_text(document, list_labels=True) == "앞 \uf09f 뒤"


def test_outline_headings_use_the_section_outline_numbering() -> None:
    document = HwpxDocument.new()
    document.add_heading("큰 제목", level=1)
    document.add_heading("작은 제목", level=2)
    document.add_heading("다음 큰 제목", level=1)

    assert export_text(document, list_labels=True).split("\n") == ["1. 큰 제목", "가. 작은 제목", "2. 다음 큰 제목"]


def test_markdown_html_and_the_document_namespace_carry_the_labels() -> None:
    document = _numbered(2)

    assert "1. 항목1" in export_markdown(document, list_labels=True)
    assert "<p>2. 항목2</p>" in export_html(document, list_labels=True, full_document=False)
    assert document.text.plain(list_labels=True).startswith("1. 항목1")


def test_numbered_paragraphs_in_cells_keep_counting_in_reading_order() -> None:
    document = _numbered(1)
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "칸 항목"
    list_style = document.paragraphs[1].element.get("paraPrIDRef")
    cell.paragraphs[0].element.set("paraPrIDRef", list_style)
    document.add_paragraph("뒤 항목")
    document.paragraphs[-1].element.set("paraPrIDRef", list_style)

    assert export_text(document, list_labels=True).split("\n") == ["1. 항목1", "2. 칸 항목", "3. 뒤 항목"]


def test_a_saved_document_gives_the_same_labels() -> None:
    document = _numbered(3)

    assert export_text(document.to_bytes(), list_labels=True) == export_text(document, list_labels=True)
