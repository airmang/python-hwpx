# SPDX-License-Identifier: Apache-2.0
"""write_line_caches gives plain text paragraphs the line layout cache Hancom writes."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.layout.line_cache import write_line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
# Hancom Office laid these documents out from python-hwpx's paragraphs without a cache and saved them.
HANCOM_LAID_OUT = ["line_cache_tabs.hwpx", "line_cache_line_breaks.hwpx", "line_cache_hanging_indents.hwpx",
                   "line_cache_indents.hwpx", "line_cache_labels.hwpx",
                   "line_cache_mixed_sizes.hwpx", "line_cache_taller_past_a_break.hwpx", "line_cache_table_cells.hwpx",
                   "line_cache_mixed_faces_tabs.hwpx"]


def _body(document: HwpxDocument) -> list:
    return [p for section in document.oxml.sections for p in section.element.findall(f"{HP}p")]


def _segments(paragraph) -> list[dict[str, str]]:
    return [dict(segment.attrib) for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]


@pytest.mark.parametrize("name", HANCOM_LAID_OUT)
def test_the_caches_written_are_the_ones_hancom_wrote(name: str) -> None:
    hancom = HwpxDocument.open(FIXTURES / name)
    document = HwpxDocument.open(FIXTURES / name)
    for paragraph in _body(document):
        for cache in paragraph.findall(f"{HP}linesegarray"):
            paragraph.remove(cache)
        for tab in paragraph.iter(f"{HP}tab"):
            tab.attrib.clear()  # as python-hwpx writes a tab

    report = write_line_caches(document)

    assert report.written and not report.unsupported
    written = [(mine, theirs) for mine, theirs in zip(_body(document), _body(hancom)) if _segments(mine)]
    assert len(written) == report.written
    for mine, theirs in written:
        assert _segments(mine) == _segments(theirs)
        assert [dict(tab.attrib) for tab in mine.iter(f"{HP}tab")] == [dict(tab.attrib) for tab in theirs.iter(f"{HP}tab")]


def test_a_new_paragraph_gets_hancoms_line_metrics() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("가나다 " * 40)

    report = write_line_caches(document)

    assert report.written == 1 and report.kept == 1  # the template's first paragraph keeps its own
    segments = _segments(_body(document)[-1])
    assert len(segments) > 1
    assert {(s["vertsize"], s["textheight"], s["baseline"], s["spacing"]) for s in segments} == {
        ("1000", "1000", "850", "600")
    }
    assert [int(s["vertpos"]) for s in segments] == [1600 * (n + 1) for n in range(len(segments))]
    buffer = io.BytesIO()
    document.save_to_stream(buffer)
    reopened = HwpxDocument.open(buffer.getvalue())
    assert _segments(_body(reopened)[-1]) == segments  # the save keeps them


def test_a_paragraph_holding_a_table_gets_one_line_as_tall_as_it() -> None:
    document = HwpxDocument.new()
    document.add_table(2, 2)

    report = write_line_caches(document)

    # The paragraph holding the table gets one line as tall as the table, its four cells' empty paragraphs theirs.
    assert report.written == 5 and report.skipped == 0
    [line] = _segments(_body(document)[-1])
    table = _body(document)[-1].find(f"{HP}run/{HP}tbl")
    assert int(line["vertsize"]) == int(table.find(f"{HP}sz").get("height")) > 282 * 2


@pytest.mark.parametrize(("side", "gap", "extra"), [("TOP", 850, 1000 + 850), ("BOTTOM", 566, 1000 + 566),
                                                    ("LEFT", 850, 0), ("RIGHT", 850, 0)])
def test_a_table_with_a_caption_holds_it_in_its_line(side: str, gap: int, extra: int) -> None:
    # A caption above or below the table takes its line (1000 for one line of 10 pt) and its gap in the table's
    # line, as Hancom saves it; one beside the table takes none.
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_caption("표 1", side=side, gap=gap)

    write_line_caches(document)

    [line] = _segments(_body(document)[-1])
    rows = int(_body(document)[-1].find(f"{HP}run/{HP}tbl/{HP}sz").get("height"))
    assert int(line["vertsize"]) == rows + extra


@pytest.mark.parametrize(("vertical", "baseline"), [("BASELINE", "850"), ("TOP", "0"), ("CENTER", "500"),
                                                   ("BOTTOM", "1000")])
def test_a_paragraph_gets_the_baseline_of_where_it_sets_its_characters(vertical: str, baseline: str) -> None:
    # Hancom writes the baseline at 85 % of the text height for characters on their baseline, 0 at the top of
    # their line, half of it at the centre and all of it at the bottom.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("가나다")
    document.styles.apply_paragraph_format(paragraphs=[paragraph], alignment="LEFT")
    shape_id = _body(document)[-1].get("paraPrIDRef")
    shape = next(el for el in document.oxml.headers[0].element.iter(f"{HH}paraPr") if el.get("id") == shape_id)
    shape.find(f"{HH}align").set("vertical", vertical)

    report = write_line_caches(document)

    assert report.written == 1
    assert _segments(_body(document)[-1])[0]["baseline"] == baseline


def test_a_larger_paragraph_end_makes_the_last_lines_text_as_tall() -> None:
    # An empty run ending the paragraph, larger than its text, makes its last line and that line's text as tall.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_run("가나다", char_pr_id_ref=document.styles.ensure_run(size=10))
    paragraph.add_run("", char_pr_id_ref=document.styles.ensure_run(size=16))

    report = write_line_caches(document)

    assert report.written == 1
    [line] = _segments(_body(document)[-1])
    assert (line["vertsize"], line["textheight"], line["baseline"]) == ("1600", "1600", "1360")


@pytest.mark.parametrize("style", [{"font": "HY신명조"}, {"font": "KoPub바탕체 Light"}, {"letter_spacing": -40},
                                   {"ratio": 210}, {"font": "한양신명조", "bold": True},
                                   {"font": "한양견고딕", "bold": True}])
def test_a_paragraph_in_a_face_or_look_not_seen_on_the_desktop_is_left_for_hancom(style: dict) -> None:
    # A face Hancom may draw in another one, or 장평 and 자간 past those seen on the desktop, are left for Hancom.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_run("가나다 " * 30, char_pr_id_ref=document.styles.ensure_run(**style))

    report = write_line_caches(document)

    assert report.written == 0 and report.skipped == 1


@pytest.mark.parametrize("style", [{"letter_spacing": -5}, {"ratio": 90}, {"ratio": 110, "letter_spacing": 5},
                                   {"font": "한양신명조"}, {"font": "맑은 고딕", "bold": True},
                                   {"font": "휴먼명조", "bold": True}])
def test_a_paragraph_at_a_look_seen_on_the_desktop_gets_a_cache(style: dict) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_run("가나다 " * 5, char_pr_id_ref=document.styles.ensure_run(**style))

    report = write_line_caches(document)

    assert report.written == 1


def test_a_page_control_among_the_text_is_left_for_hancom() -> None:
    # A page control among the text (not before it) was seen to break the line elsewhere than FormFit.
    document = HwpxDocument.new()
    document.add_paragraph("가나다 " * 40)
    run = _body(document)[-1].find(f"{HP}run")
    ctrl = run.makeelement(f"{HP}ctrl", {})
    ctrl.append(ctrl.makeelement(f"{HP}pageHiding", {"hideHeader": "0", "hideFooter": "0", "hideMasterPage": "0",
                                                     "hideBorder": "0", "hideFill": "0", "hidePageNum": "1"}))
    text = run.find(f"{HP}t")
    tail = run.makeelement(f"{HP}t", {})
    tail.text, text.text = text.text[1:], text.text[:1]
    text.addnext(ctrl)
    ctrl.addnext(tail)

    report = write_line_caches(document)

    assert report.written == 0 and report.skipped == 1


@pytest.mark.parametrize(("condense", "spacing", "written"), [("0", 0, 1), ("10", 0, 0), ("0", -10, 0)])
def test_a_no_break_space_among_spaces_that_shrink_is_left_for_hancom(condense: str, spacing: int, written: int) -> None:
    # A no-break space in a paragraph with 최소 공백 was seen to break a line elsewhere than FormFit, and one with
    # 자간 takes none of it: such paragraphs are left for Hancom.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_run("가나 다라 마바", char_pr_id_ref=document.styles.ensure_run(letter_spacing=spacing))
    shape_id = _body(document)[-1].get("paraPrIDRef")
    next(el for el in document.oxml.headers[0].element.iter(f"{HH}paraPr") if el.get("id") == shape_id).set(
        "condense", condense)

    report = write_line_caches(document)

    assert report.written == written


def test_a_glyph_not_seen_on_the_desktop_is_left_for_hancom() -> None:
    # "｢" (U+FF62) has a table advance read from the font, not one seen on the desktop.
    document = HwpxDocument.new()
    document.add_paragraph("｢가나다｣")

    report = write_line_caches(document)

    assert report.written == 0 and report.skipped == 1


def _cell_paragraphs(document: HwpxDocument) -> list:
    return [p for section in document.oxml.sections for cell in section.element.iter(f"{HP}tc")
            for p in cell.findall(f"{HP}subList/{HP}p")]


def test_the_caches_written_in_table_cells_are_the_ones_hancom_wrote() -> None:
    # Hancom laid out a form of several tables from python-hwpx's cells without a cache: each cell's lines go
    # down from the top of its text area, as wide as the area in whole layout units.
    hancom = HwpxDocument.open(FIXTURES / "line_cache_table_cells.hwpx")
    document = HwpxDocument.open(FIXTURES / "line_cache_table_cells.hwpx")
    for paragraph in document.oxml.sections[0].element.iter(f"{HP}p"):
        for cache in paragraph.findall(f"{HP}linesegarray"):
            paragraph.remove(cache)

    write_line_caches(document)

    written = [(mine, theirs) for mine, theirs in zip(_cell_paragraphs(document), _cell_paragraphs(hancom))
               if _segments(mine)]
    assert len(written) > 10
    for mine, theirs in written:
        assert _segments(mine) == _segments(theirs)


def test_a_tab_gets_the_width_hancom_lays_it_out_at() -> None:
    # With a cache Hancom draws a tab as wide as hp:tab says: "항목" (1944 in 함초롬바탕) then a tab to the default stop at 4000.
    document = HwpxDocument.new()
    document.add_paragraph("항목	내용")

    report = write_line_caches(document)

    assert report.written == 1
    [tab] = _body(document)[-1].iter(f"{HP}tab")
    assert dict(tab.attrib) == {"width": "2056", "leader": "0", "type": "1"}


@pytest.mark.parametrize(("head", "written"), [("가" * 16, 1), ("가" * 16 + "!", 0)])
def test_a_tab_close_to_a_tab_stop_is_left_for_hancom(head: str, written: int) -> None:
    # Sixteen 가 take 15,552 (972 each), 448 short of the stop at 16,000: their tab reaches it surely. With a "!" (half
    # an em) they take 16,052, 52 past it, closer than a layout unit for each of the 17 characters: text that much
    # off from Hancom's would take the tab to another stop.
    document = HwpxDocument.new()
    document.add_paragraph(f"{head}\t내용")

    report = write_line_caches(document)

    assert report.written == written and report.skipped == 1 - written


def test_a_tab_right_after_a_tab_starts_at_its_stop_surely() -> None:
    # The first tab ends at the stop at 4000, exactly where the second one starts: no character before the second
    # tab could be off, so it reaches the stop at 8000 surely.
    document = HwpxDocument.new()
    document.add_paragraph("항목\t\t내용")

    report = write_line_caches(document)

    assert report.written == 1
    assert [tab.get("width") for tab in _body(document)[-1].iter(f"{HP}tab")] == ["2056", "4000"]


def test_a_line_break_typed_into_the_text_is_left_for_hancom() -> None:
    # Hancom writes a line break as hp:lineBreak; a newline in hp:t's own text is left for it to lay out.
    document = HwpxDocument.new()
    document.add_paragraph("첫 줄\n둘째 줄")

    report = write_line_caches(document)

    assert report.written == 0 and report.skipped == 1


@pytest.mark.parametrize("text", ["이모지 😀 하나", "a" * 200])
def test_a_paragraph_laid_out_less_surely_is_left_for_hancom(text: str) -> None:
    # Hancom takes the line breaks from a cache as written, so a paragraph with a glyph no table gives an advance
    # for, or with a word too long for a line, is left for Hancom to break.
    document = HwpxDocument.new()
    document.add_paragraph(text)

    report = write_line_caches(document)

    assert report.written == 0 and report.skipped == 1


@pytest.mark.parametrize(("right_mm", "written"), [(6.0, 1), (7.0, 0)])
def test_a_line_ending_close_to_its_room_is_left_for_hancom(right_mm: float, written: int) -> None:
    # Twelve words of 3,416 HWPUNIT (the last without its space) take 40,492 of the line. 7 mm to the right leaves
    # it 44 more, and a width a little off from Hancom's could break the line elsewhere; 6 mm leaves 327.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("가나다 " * 20)
    document.styles.apply_paragraph_format(paragraphs=[paragraph], indent_right_mm=right_mm)

    report = write_line_caches(document)

    assert report.written == written and report.skipped == 1 - written


def test_a_paragraph_of_several_character_sizes_gets_a_cache() -> None:
    # Hancom makes each line as tall as its largest character and draws its text that high.
    document = HwpxDocument.open(FIXTURES / "line_cache_mixed_sizes.hwpx")
    hancom = HwpxDocument.open(FIXTURES / "line_cache_mixed_sizes.hwpx")
    for paragraph in _body(document):
        for cache in paragraph.findall(f"{HP}linesegarray"):
            paragraph.remove(cache)

    write_line_caches(document)

    mixed = [
        (mine, theirs)
        for mine, theirs in zip(_body(document), _body(hancom))
        if _segments(mine) and len({run.get("charPrIDRef") for run in mine.findall(f"{HP}run")}) > 1
    ]
    assert mixed
    for mine, theirs in mixed:
        assert _segments(mine) == _segments(theirs)


def test_a_table_whose_cells_are_not_laid_out_surely_keeps_its_line_for_hancom() -> None:
    # The table's line is as tall as its rows, and a row as tall as its cells' lines: a cell laid out less surely
    # leaves the table's line for Hancom too.
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "이모지 😀"

    write_line_caches(document)

    assert not _segments(_body(document)[-1])


def test_a_paragraph_holding_page_controls_gets_a_cache() -> None:
    # A header, a footer and a page number take no room on a line; each control counts eight characters in a
    # line's text position, as a section's own definitions do.
    document = HwpxDocument.new()
    document.set_header_text("머리말")
    document.set_footer_text("꼬리말")
    document.add_paragraph("가나다 " * 40)

    first = _body(document)[0]
    for cache in first.findall(f"{HP}linesegarray"):  # the template's own
        first.remove(cache)

    report = write_line_caches(document)

    controls = [child for run in first.findall(f"{HP}run") for child in run
                if child.tag.endswith("}ctrl") and any(not grand.tag.endswith("}colPr") for grand in child)]
    assert controls and _segments(first)
    assert report.written == 2


def test_a_paragraph_of_several_faces_gets_a_cache() -> None:
    # Runs of other faces, 장평 or 자간 break their lines with their own advances, as Hancom lays them out.
    document = HwpxDocument.open(FIXTURES / "line_cache_mixed_faces.hwpx")
    hancom = HwpxDocument.open(FIXTURES / "line_cache_mixed_faces.hwpx")
    for paragraph in _body(document):
        for cache in paragraph.findall(f"{HP}linesegarray"):
            paragraph.remove(cache)

    write_line_caches(document)

    faces = [
        (mine, theirs)
        for mine, theirs in zip(_body(document), _body(hancom))
        if _segments(mine) and len({run.get("charPrIDRef") for run in mine.findall(f"{HP}run")}) > 1
    ]
    assert len(faces) >= 3
    for mine, theirs in faces:
        assert _segments(mine) == _segments(theirs)


def test_a_tab_among_runs_of_several_faces_gets_its_width() -> None:
    # The text before a tab takes each character's own run's advance, and the tab reaches the next default stop.
    document = HwpxDocument.open(FIXTURES / "line_cache_mixed_faces_tabs.hwpx")
    hancom = HwpxDocument.open(FIXTURES / "line_cache_mixed_faces_tabs.hwpx")
    for paragraph in _body(document):
        for cache in paragraph.findall(f"{HP}linesegarray"):
            paragraph.remove(cache)
        for tab in paragraph.iter(f"{HP}tab"):
            tab.attrib.clear()

    write_line_caches(document)

    tabbed = [
        (mine, theirs)
        for mine, theirs in zip(_body(document), _body(hancom))
        if _segments(mine) and mine.find(f".//{HP}tab") is not None
        and len({run.get("charPrIDRef") for run in mine.findall(f"{HP}run")}) > 1
    ]
    assert len(tabbed) >= 2
    for mine, theirs in tabbed:
        assert [dict(tab.attrib) for tab in mine.iter(f"{HP}tab")] == [dict(tab.attrib) for tab in theirs.iter(f"{HP}tab")]
