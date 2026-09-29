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


def test_a_merged_table_hancom_has_not_laid_out_is_unsupported() -> None:
    data = (FIXTURES.parent / "m2_corpus" / "public_official_table.hwpx").read_bytes()

    estimate = estimate_pages(_without_caches(data))

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a table with merged rows",)


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


def test_a_page_break_among_merged_rows_of_a_flowing_table_is_unsupported() -> None:
    document, table = _flowing_table_after(38, 6)
    table.merge_cells(1, 0, 4, 0)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a page break among rows merged in a flowing table",)


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


def test_a_document_with_endnotes_is_unsupported() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    document.notes.add_endnote("미주", paragraph)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.lines == ()
    assert estimate.unsupported == ("section 0: endnotes",)
