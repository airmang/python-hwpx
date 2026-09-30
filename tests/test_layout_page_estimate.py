"""``hwpx.experimental.estimate_pages``: the pages and line positions Hancom lays a document out on.

Each ``pages_*.hwpx`` fixture is a document Hancom opened, laid out and saved. Its line caches
(``hp:linesegarray``) hold where Hancom put every line of a paragraph (``vertpos``, from the top
of the column), and ``HANCOM_PAGES`` the number of pages Hancom drew.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.experimental import EstimatedLine, PageEstimate, estimate_pages

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
HANCOM_PAGES = {
    "pages_text_12pt_160": 5,             # 12 pt text, line spacing 160%
    "pages_spacing_20_20": 3,             # spacing before and after paragraphs
    "pages_boundary_widow_on": 2,         # widow/orphan control at the page end
    "pages_line_ends_at_page_foot": 2,    # a line ending right at the body's foot goes on
    "pages_empty_line_ends_at_page_foot": 2,  # an empty one too
    "pages_line_ends_200_above_page_foot": 2,  # one ending 200 above it stays
    "pages_line_ends_1_above_page_foot": 2,    # and one ending 1 above it
    "pages_line_ends_100_above_page_foot": 2,  # and 100 above it: no room is kept below lines
    "pages_keep_keep_with_next": 3,       # keep with next
    "pages_columns_2_break": 4,           # two columns and a column break
    "pages_footnotes_6": 3,               # footnotes at the page foot
    "pages_table_flow_repeat_header": 3,  # a table flowing with the text, header row repeated
    "pages_table_flow_multiline_cells": 4,  # a flowing table split between cell lines
    "pages_table_flow_starts_next_page": 2,  # its first row does not fit: the text goes on under the anchor
    "pages_table_flow_starts_next_page_long": 4,  # the same over two pages: text resumes under the table
    "pages_table_multiline_cells": 3,     # a table set as a character
    "pages_picture_floating_tall": 4,     # top-and-bottom pictures
    "pages_cell_column_settings": 3,      # one-column settings in a table cell's paragraph
    "pages_mixed_sizes_percent": 3,       # 10 pt and 20 pt runs in a paragraph, line spacing 160%
    "pages_mixed_sizes_fixed": 3,         # 12 pt and 30 pt runs, fixed line spacing (lines overlap)
    "pages_mixed_sizes_at_least": 2,      # 8 pt and 16 pt runs, line spacing at least 18 pt
    "pages_picture_before_text_percent": 2,  # a picture set as a character before the text, 160%
    "pages_picture_before_text_fixed": 2,    # a picture taller than the fixed line spacing
    "pages_table_merged_rows_tall": 1,    # a table set as a character, a merged cell taller than its rows
    "pages_table_merged_rows_short": 1,   # the same, the merged cell shorter than its rows
    "pages_table_flow_merged_rows": 2,    # a table flowing with the text, cells merged over rows
    "pages_table_flow_tall_row_carried": 2,  # a row declared taller than its text, cut at the page end
    "pages_table_flow_tall_row_dropped": 2,  # the same, the rest too short to go on
    "pages_table_flow_tall_row_rest_1282": 2,  # a rest of 1282 is dropped
    "pages_table_flow_tall_row_rest_1283": 2,  # a rest of 1283 goes on
    "pages_table_flow_tall_row_cell_margins_0": 2,    # the cells' own margins 0: 1283 goes on
    "pages_table_flow_tall_row_cell_margins_500": 2,  # the cells' own margins 500: 1290 goes on
    "pages_table_flow_tall_row_table_margins_500": 2,  # the table's inner margins 500: 1290 goes on
    "pages_table_flow_tall_row_bottom_aligned": 2,    # cells aligned to the bottom: 1290 goes on
    "pages_table_flow_tall_row_16pt": 2,              # 16 pt text: 1283 goes on
    "pages_table_flow_row_ends_100_above_foot": 2,    # a row of two lines ending 100 above the foot: split
    "pages_table_flow_row_ends_101_above_foot": 2,    # the same ending 101 above it stays
    "pages_table_flow_moved_row_ends_100_above_foot": 2,  # moved row by row: 100 above the foot goes on
    "pages_table_flow_moved_row_ends_101_above_foot": 2,  # and 101 above it stays
    "pages_table_flow_anchor_on_next_page": 2,  # the table's anchor line has no room: both go on
    "pages_table_merged_rows_held": 1,    # a cell merged over rows 0-3 holding one over rows 1-2
    "pages_table_merged_rows_staggered": 1,  # merged over rows 0-1 and 1-2: row 1 has no cell of its own
    "pages_table_merged_rows_ending_first": 1,  # merged over rows 0-2 and 2-3: the one ending first first
    "pages_table_flow_merged_rows_moved_whole": 2,  # moved row by row: rows 1-2 merged go on as one
    "pages_table_flow_merged_three_rows_moved_whole": 2,  # the same with rows 1-3
    "pages_table_flow_merged_rows_split_by_cell": 2,  # split between cell lines: the merged cell's rest goes on
    "pages_table_flow_merged_three_rows_split_by_cell": 2,  # the rest over two rows, what they lack in the last
    "pages_table_flow_merged_rows_declared_row_cut": 2,  # a row under merged rows declared 14000: its rest goes on
    "pages_table_flow_merged_rows_declared_row_dropped": 2,  # the same declared 6000: a rest of 503 is dropped
    "pages_table_flow_merged_cell_declared_cut": 2,  # the merged cell declared 6000: its rest goes on
    "pages_table_flow_merged_cell_declared_rest_1282": 2,  # the merged cell's rest of 1282 is dropped
    "pages_table_flow_merged_cell_declared_rest_1283": 2,  # and one of 1283 goes on
    "pages_table_flow_merged_cell_declared_lines_cut": 2,  # the page end among its 6 lines: cut the same
    "pages_table_anchored_merged_rows_split_by_cell": 2,  # a table anchored in text: merged rows split the same
    "pages_table_nested_after_text": 1,  # a table in a cell of a flowing table, after a line of text
    "pages_table_nested_alone": 1,       # a table alone in a cell of a flowing table
    "pages_table_nested_in_table_as_character": 1,  # a table in a cell of a table set as a character
    "pages_table_nested_row_split": 2,  # a row holding a table splits after its first line of text
    "pages_table_nested_row_moved": 2,  # none of a row holding a table fits: it goes on whole
    "pages_table_nested_row_declared_cut": 2,  # the same row declared 16000: cut above the foot, the rest goes on
    "pages_table_nested_row_declared_cut_near_foot": 2,  # declared 24000, cut 3579 below its top
    "pages_objects_among_text_table": 2,  # a full-width table set as a character among text
    "pages_objects_among_text_equation": 1,  # equations set as characters among text
    "pages_objects_after_text_rectangle": 1,  # rectangles set as characters after text
    "pages_table_anchored_after_text": 1,  # a top-and-bottom table anchored after three lines of text
    "pages_picture_anchored_before_text": 1,  # a top-and-bottom picture anchored before the text
    "pages_table_anchored_offset_before_text": 1,  # 3000 down from the first line: the third line goes below
    "pages_table_anchored_offset_after_text": 1,   # 3000 down from the last line: the next paragraph's second
    "pages_picture_anchored_offset_next_paragraph": 1,  # 1600 down: the next paragraph's first line
    "pages_picture_anchored_small_offset": 1,  # 500 down: the line it stands on goes below it
    "pages_table_offset_flowing_split_by_cell": 2,  # a flowing table 500 down over the page end:
                                                    # the line it stands on goes below its end
    "pages_table_offset_flowing_row_by_row": 2,  # the same moved row by row
    "pages_table_offset_flowing_second_line": 2,  # 2000 down: the second line goes below its end
    "pages_table_offset_flowing_next_paragraph": 2,  # the next paragraph's first line does
    "pages_picture_square_left": 2,       # a picture wrapped square on the left, text beside it into the next paragraph
    "pages_picture_square_right": 2,      # a wide picture wrapped square on the right
    "pages_picture_square_alone": 2,      # a picture wrapped square alone in its paragraph
    "pages_picture_square_wider_than_column": 2,  # no room beside it: the text goes below
    "pages_picture_square_offset": 2,     # a picture wrapped square 3000 below the paragraph's top
    "pages_table_square_alone": 1,        # a table wrapped square alone, as tall as its rows
    "pages_picture_in_front_of_text": 1,  # a picture in front of three lines of text: no line moves
    "pages_rectangle_behind_text_alone": 1,  # a rectangle behind the text alone: an empty line
    "pages_table_as_character_beside_rectangle_in_front": 1,  # beside a rectangle in front, on the paper
    "pages_picture_behind_text_past_page_foot": 2,  # a picture behind the text past the page foot
    "pages_rectangle_on_paper_pushes_its_line": 1,  # top and bottom 15000 below the paper's top: the
                                                     # second line of its paragraph goes below it
    "pages_rectangle_on_paper_at_page_top": 2,  # 4000 below it, anchored mid-page: the page's first
                                                 # lines, in paragraphs before its own, go below it
    "pages_table_on_paper_pushes_a_later_line": 1,  # a table 40000 below it: a line of a later paragraph
    "pages_rectangle_on_paper_across_two_columns": 2,  # across both columns, anchored in the second:
                                                        # the lines of both columns go below it
}


def _hancom_lines(data: bytes) -> list[list[int]]:
    """The ``vertpos`` of each cached line of every body paragraph, sections in order."""

    lines = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)]
        for name in sorted(names, key=lambda name: int(re.findall(r"\d+", name)[0])):
            root = etree.fromstring(archive.read(name))
            lines += [
                [int(seg.get("vertpos")) for seg in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]
                for paragraph in root.findall(f"{HP}p")
            ]
    return lines


def _without_caches(data: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for cache in list(root.iter(f"{HP}linesegarray")):
                    cache.getparent().remove(cache)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


def _assert_like_hancom(estimate: PageEstimate, data: bytes, pages: int) -> None:
    assert estimate.unsupported == ()
    assert estimate.pages == pages
    hancom = _hancom_lines(data)
    estimated = [[line.vertpos for line in lines] for lines in estimate.lines]
    assert len(estimated) == len(hancom)
    assert [mine for mine, theirs in zip(estimated, hancom) if theirs] == [theirs for theirs in hancom if theirs]
    assert max(line.page for lines in estimate.lines for line in lines) == pages - 1


@pytest.mark.parametrize("name", sorted(HANCOM_PAGES))
def test_the_estimate_puts_every_line_where_hancom_did(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, HANCOM_PAGES[name])


@pytest.mark.parametrize("name", sorted(HANCOM_PAGES))
def test_without_line_caches_formfit_breaks_the_lines_the_same(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, HANCOM_PAGES[name])


@pytest.mark.parametrize(
    ("fixture", "pages"),
    [
        ("m2_corpus/public_official_table.hwpx", 5),       # merged rows
        ("m3_gongmun_gold/mpm_recruitment_notice.hwpx", 1),  # a nested table
    ],
)
def test_a_table_set_as_a_character_hancom_laid_out_keeps_its_saved_height(fixture: str, pages: int) -> None:
    # Hancom-made documents: every paragraph in the table keeps its layout cache.
    estimate = estimate_pages(FIXTURES.parent / fixture)

    assert estimate.unsupported == ()
    assert estimate.pages == pages


def test_the_lines_around_a_nested_table_are_where_hancom_put_them() -> None:
    data = (FIXTURES.parent / "m3_gongmun_gold" / "mpm_recruitment_notice.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)


@pytest.mark.parametrize("fixture", ["pages_table_nested_top_and_bottom_alone",
                                     "pages_table_nested_top_and_bottom_before_text", "pages_table_nested_among_text"])
def test_a_cell_holding_a_table_among_text_or_top_and_bottom_is_as_tall_as_hancom_drew_it(fixture: str) -> None:
    # A table in a cell of a flowing table, placed top and bottom alone in its paragraph (the cell
    # reaches down to its foot) or before text (the text goes below it), or set as a character among
    # text: the lines of the cell's caches. Without the caches the estimate does not follow such a cell.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


def test_paragraphs_of_several_character_sizes_hancom_laid_out_follow_their_cached_lines() -> None:
    # A Hancom-made document of three sections whose paragraphs mix character sizes: each line is as
    # tall and as far apart as its layout cache says.
    data = (FIXTURES.parent / "hwpxlib_corpus" / "error__20230728__test.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 39)


def test_another_document_of_mixed_character_sizes_has_hancoms_page_count() -> None:
    estimate = estimate_pages(FIXTURES.parent / "hwpxlib_corpus" / "error__20240626__no_manifest.hwpx")

    assert estimate.unsupported == ()
    assert estimate.pages == 4


def _with_empty_first_runs(data: bytes) -> bytes:
    """Each paragraph starting with an empty run of the default character shape (10 pt), as a paragraph
    python-hwpx made and then added runs to does; Hancom drops such a run when it saves."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for paragraph in root.iter(f"{HP}p"):
                    first = paragraph.find(f"{HP}run")
                    if first is not None and first.get("charPrIDRef") != "0":
                        empty = etree.Element(f"{HP}run", charPrIDRef="0")
                        etree.SubElement(empty, f"{HP}t")
                        first.addprevious(empty)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


def test_an_empty_run_takes_no_room_and_gives_no_character_shape() -> None:
    # 12 pt and 30 pt runs of 바탕 after an empty 10 pt 함초롬바탕 run: the lines are Hancom's.
    data = (FIXTURES / "pages_mixed_sizes_fixed.hwpx").read_bytes()

    estimate = estimate_pages(_without_caches(_with_empty_first_runs(data)))

    _assert_like_hancom(estimate, data, HANCOM_PAGES["pages_mixed_sizes_fixed"])


def _flowing_table_after(paragraphs: int, rows: int) -> tuple[HwpxDocument, object]:
    document = HwpxDocument.new()
    for index in range(paragraphs):
        document.add_paragraph(f"문단 {index}")
    table = document.add_paragraph("").add_table(rows, 2)
    table.set_treat_as_char(False)
    table.element.set("pageBreak", "CELL")
    for row in range(rows):
        for column in range(2):
            table.set_cell_text(row, column, "칸")
    return document, table


def test_rows_merged_together_taller_than_a_page_are_unsupported() -> None:
    # The cell merged over rows 1-4 is declared 150000 tall: what is left of it after the page end
    # does not fit on the next page either.
    document, table = _flowing_table_after(38, 6)
    table.merge_cells(1, 0, 4, 0)
    for cell in table.element.iter(f"{HP}tc"):
        span = cell.find(f"{HP}cellSpan")
        if span is not None and span.get("rowSpan", "1") != "1":
            cell.find(f"{HP}cellSz").set("height", "150000")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: rows merged together taller than a page",)


@pytest.mark.parametrize(("height", "rest"), [(20000, 13221), (8029, 0), (8061, 0), (8062, 1283), (8079, 1300)])
def test_a_flowing_row_taller_than_its_text_is_cut_just_above_the_page_foot(height: int, rest: int) -> None:
    # The row starts 6880 above the foot: Hancom cuts it 101 above the foot and carries the rest to the
    # next page, unless the rest is 1282 or less (then the next row starts that page). The fixtures
    # pages_table_flow_tall_row_rest_1282 and _1283 are rows placed the same way, saved by Hancom.
    document, table = _flowing_table_after(35, 3)
    for cell in table.element.iter(f"{HP}tc"):
        if cell.find(f"{HP}cellAddr").get("rowAddr") == "1":
            cell.find(f"{HP}cellSz").set("height", str(height))
    document.add_paragraph("표 뒤")

    estimate = estimate_pages(document)

    assert estimate.unsupported == ()
    assert estimate.lines[-1] == (EstimatedLine(page=1, column=0, vertpos=rest + 1282),)


def test_a_flowing_table_whose_anchor_line_has_no_room_starts_on_the_next_page() -> None:
    document, _ = _flowing_table_after(40, 3)  # the anchor line would start 65600, 1000 tall
    document.add_paragraph("표 뒤")

    estimate = estimate_pages(document)

    assert estimate.lines[-2] == (EstimatedLine(page=1, column=0, vertpos=0),)
    assert estimate.lines[-1] == (EstimatedLine(page=1, column=0, vertpos=3 * 1282),)


def test_a_table_whose_row_addresses_skip_is_estimated_without_the_missing_rows() -> None:
    # Documents edited by other tools can number their rows with gaps (row 2 saved as row 5).
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    for cell in table.element.iter(f"{HP}tc"):
        address = cell.find(f"{HP}cellAddr")
        if address.get("rowAddr") == "2":
            address.set("rowAddr", "5")

    estimate = estimate_pages(document)

    assert estimate.unsupported == ()
    assert estimate.pages == 1


def test_a_page_break_in_a_row_holding_a_table_beside_a_taller_cell_is_unsupported() -> None:
    # Row 1's cell (1, 0) holds more lines than the cell beside it holding a table; the page end falls
    # among them.
    document, table = _flowing_table_after(38, 3)
    table.cell(1, 1).add_table(2, 2, width=18000)
    table.set_cell_text(1, 0, "칸 글 " * 150)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a page break in a flowing table row holding a table",)


def test_a_top_and_bottom_table_not_split_offset_past_the_page_foot_is_unsupported() -> None:
    document, table = _flowing_table_after(38, 3)
    table.element.set("pageBreak", "NONE")
    table.element.find(f"{HP}pos").set("vertOffset", "3000")
    document.paragraphs[-1].add_run("앵커 문단 글")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == (
        "section 0: a square-wrapped or offset top-and-bottom object past the page foot",)


@pytest.mark.parametrize(("fixture", "content"), [("pages_composed_characters", "compose"),
                                                  ("pages_ruby_text", "dutmal")])
def test_composed_characters_and_ruby_text_follow_the_lines_hancom_drew(fixture: str, content: str) -> None:
    # Circled numbers among three lines of text, and ruby text above a word: the lines of their
    # paragraphs' caches. Without the caches the estimate does not break such lines itself.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    assert estimate_pages(_without_caches(data)).unsupported == (
        f"section 0: {content} in a paragraph without a layout cache",)


def test_lines_of_two_columns_are_in_columns() -> None:
    estimate = estimate_pages(FIXTURES / "pages_columns_2_break.hwpx")

    assert {line.column for lines in estimate.lines for line in lines} == {0, 1}


def test_a_document_a_path_and_bytes_give_the_same_estimate() -> None:
    path = FIXTURES / "pages_footnotes_6.hwpx"

    assert estimate_pages(HwpxDocument.open(path)) == estimate_pages(path) == estimate_pages(path.read_bytes())


def test_a_new_document_is_one_page() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")

    estimate = estimate_pages(document)

    assert estimate.pages == 1
    assert estimate.lines[-1] == (EstimatedLine(page=0, column=0, vertpos=1600),)


def test_an_object_placed_on_the_paper_on_a_page_with_a_flowing_table_is_unsupported() -> None:
    document, _ = _flowing_table_after(3, 3)
    paragraph = document.add_paragraph("종이 기준 개체 곁 글")
    rectangle = document.shapes.add_rectangle(20000, 8000, treat_as_char=True, paragraph=paragraph).element
    rectangle.set("textWrap", "TOP_AND_BOTTOM")
    for key, value in (("treatAsChar", "0"), ("vertRelTo", "PAPER"), ("horzRelTo", "PAPER"),
                       ("vertAlign", "TOP"), ("vertOffset", "15000")):
        rectangle.find(f"{HP}pos").set(key, value)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a table on a page with an object placed on the paper",)


def test_a_document_with_endnotes_is_unsupported() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    document.notes.add_endnote("미주", paragraph)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.lines == ()
    assert estimate.unsupported == ("section 0: endnotes",)
