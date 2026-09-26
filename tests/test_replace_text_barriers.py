"""``doc.text.replace`` does not join text on the two sides of a tab or a line break.

Hancom reads a tab or a line break as a character of its own, so "사<tab/>과" is not "사과";
highlight marks inside the text still do not split a word.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def test_a_tab_between_the_letters_is_not_a_match() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("탭사\t과 그리고 사과")

    count = document.text.replace("사과", "배")

    assert count == 1
    assert paragraph.text == "탭사\t과 그리고 배"


def test_a_line_break_between_the_letters_is_not_a_match() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    text = paragraph.runs[0].element.find(f"{HP}t")
    text.text = "사"
    line_break = text.makeelement(f"{HP}lineBreak", {})
    line_break.tail = "과"
    text.append(line_break)

    assert document.text.replace("사과", "배") == 0
    assert text.text == "사" and line_break.tail == "과"


def test_a_highlighted_word_is_still_one_word() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞 사과 뒤")
    document.text.highlight(paragraph, "사과")

    count = document.text.replace("사과", "배")

    assert count == 1
    assert "배" in paragraph.text and "사과" not in paragraph.text


def test_limit_still_counts_across_the_stretches_of_a_run() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("사과\t사과\t사과")

    count = document.text.replace("사과", "배", limit=2)

    assert count == 2
    assert paragraph.text == "배\t배\t사과"
