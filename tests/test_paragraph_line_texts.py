"""``paragraph.line_texts``: the text of each line Hancom laid out when it last saved.

The lines are cut where ``hp:lineseg@textpos`` says, counting as Hancom counts (a tab or a control 8,
an object 8, a line break 1, a character outside the basic plane 2, a highlight's marks 0). Checked on
the 250 Hancom 2024 conversions of public samples: 192,299 paragraphs with saved lines, every forced
line break ends a line and the lines put together are ``paragraph.text``; 179 paragraphs holding a
tracked change or a table-of-contents mark read ``None``.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


def _paragraph(name: str, where: str, predicate):
    doc = HwpxDocument.open(SAVED / name)
    for place in doc.text.iter_paragraphs(where=where):
        if predicate(place.paragraph):
            return place.paragraph
    raise AssertionError(f"no such paragraph in {name}")


def test_a_line_break_after_a_field_ends_the_first_line() -> None:
    # "주소: " + field begin (8) + "서울" + line break; the second line starts right after the break
    paragraph = _paragraph("form_field_line_break.hwpx", "body", lambda p: "\n" in p.text)
    assert paragraph.line_texts == ("주소: 서울\n", "종로구")
    assert [s.text_position for s in paragraph.line_segments] == [0, len("주소: ") + 8 + len("서울") + 1]


def test_cell_paragraphs_read_their_lines() -> None:
    paragraph = _paragraph("auto_grow_cell_filled.hwpx", "cell", lambda p: len(p.line_segments) > 1)
    lines = paragraph.line_texts
    assert len(lines) == len(paragraph.line_segments) > 1
    assert "".join(lines) == paragraph.text


def test_tabs_take_eight_places() -> None:
    paragraph = _paragraph("line_cache_mixed_faces_tabs.hwpx", "body",
                           lambda p: "\t" in p.text and len(p.line_segments) > 1)
    lines = paragraph.line_texts
    assert "".join(lines) == paragraph.text
    tabs_on_first = lines[0].count("\t")
    assert paragraph.line_segments[1].text_position == len(lines[0]) + 7 * tabs_on_first


def test_an_equation_takes_eight_places_and_no_text() -> None:
    paragraph = _paragraph("pages_objects_among_text_equation.hwpx", "body",
                           lambda p: bool(p.equations) and len(p.line_segments) > 1)
    lines = paragraph.line_texts
    assert "".join(lines) == paragraph.text
    assert len(lines) == len(paragraph.line_segments)


def test_a_line_holding_only_a_picture_reads_empty() -> None:
    paragraph = _paragraph("formfit_inline_objects.hwpx", "cell",
                           lambda p: bool(p.pictures) and len(p.line_segments) > 1)
    assert paragraph.line_texts[0] == ""


def test_no_saved_lines_reads_an_empty_tuple() -> None:
    doc = HwpxDocument.new()
    assert doc.add_paragraph("새 문단").line_texts == ()


def test_a_tracked_change_mark_is_not_counted_at_a_guess() -> None:
    doc = HwpxDocument.open(SAVED / "form_field_line_break.hwpx")
    paragraph = next(p.paragraph for p in doc.text.iter_paragraphs() if "\n" in p.paragraph.text)
    text = paragraph.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}run/"
                                  "{http://www.hancom.co.kr/hwpml/2011/paragraph}t")
    text.insert(0, text.makeelement("{http://www.hancom.co.kr/hwpml/2011/paragraph}insertBegin", {"Id": "1"}))
    assert paragraph.line_segments  # the cache is still there: only the count is unknown
    assert paragraph.line_texts is None
