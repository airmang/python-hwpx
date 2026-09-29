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
    "pages_table_multiline_cells": 3,     # a table set as a character
    "pages_picture_floating_tall": 4,     # top-and-bottom pictures
    "pages_cell_column_settings": 3,      # one-column settings in a table cell's paragraph
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


def test_mixed_character_sizes_without_layout_caches_are_unsupported() -> None:
    data = (FIXTURES.parent / "hwpxlib_corpus" / "error__20230728__test.hwpx").read_bytes()

    estimate = estimate_pages(_without_caches(data))

    assert estimate.pages is None
    assert "section 2: mixed character sizes in a paragraph" in estimate.unsupported


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
