# SPDX-License-Identifier: Apache-2.0
"""write_line_caches gives plain text paragraphs the line layout cache Hancom writes."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.layout.line_cache import write_line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
# Hancom Office laid these documents out from python-hwpx's paragraphs without a cache and saved them.
HANCOM_LAID_OUT = ["line_cache_tabs.hwpx", "line_cache_line_breaks.hwpx", "line_cache_hanging_indents.hwpx",
                   "line_cache_indents.hwpx", "line_cache_labels.hwpx",
                   "line_cache_mixed_sizes.hwpx", "line_cache_taller_past_a_break.hwpx"]


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


def test_a_paragraph_with_an_object_is_left_for_hancom() -> None:
    document = HwpxDocument.new()
    document.add_table(2, 2)

    report = write_line_caches(document)

    # The paragraph holding the table is left for Hancom; its four cells' empty paragraphs get caches.
    assert report.written == 4 and report.skipped == 1
    assert not _segments(_body(document)[-1])


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
