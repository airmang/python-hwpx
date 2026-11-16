"""Page size and margins read as the file has them: a value left out is the schema's default where
the schema has one, and ``None`` where it has none or the value is not a number -- never a 0 nobody
wrote. Hancom writes every one of these attributes (1,637 ``hp:secPr`` of the public corpora, none
left out), so Hancom-saved documents read as before."""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


def _page_pr(doc: HwpxDocument):
    return doc.sections[0].element.find(f".//{HP}secPr/{HP}pagePr")


def test_hancom_saved_page_reads_every_value_it_holds() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")
    page_pr = _page_pr(doc)
    margin = page_pr.find(f"{HP}margin")
    size = doc.page.size(section=0)
    margins = doc.page.margins(section=0)
    assert (size.width, size.height) == (int(page_pr.get("width")), int(page_pr.get("height")))
    assert {side: getattr(margins, side) for side in ("left", "right", "top", "bottom", "header", "footer", "gutter")} \
        == {side: int(margin.get(side)) for side in ("left", "right", "top", "bottom", "header", "footer", "gutter")}


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_a_required_margin_left_out_reads_none(side: str) -> None:
    doc = HwpxDocument.new()
    del _page_pr(doc).find(f"{HP}margin").attrib[side]
    assert getattr(doc.page.margins(section=0), side) is None


@pytest.mark.parametrize(("side", "default"), [("header", 4252), ("footer", 4252), ("gutter", 0)])
def test_an_optional_margin_left_out_reads_the_schema_default(side: str, default: int) -> None:
    doc = HwpxDocument.new()
    margin = _page_pr(doc).find(f"{HP}margin")
    margin.set(side, "1234")
    del margin.attrib[side]
    assert getattr(doc.page.margins(section=0), side) == default


@pytest.mark.parametrize(("name", "default"), [("width", 59528), ("height", 84188)])
def test_a_page_size_left_out_reads_the_schema_default(name: str, default: int) -> None:
    doc = HwpxDocument.new()
    del _page_pr(doc).attrib[name]
    assert getattr(doc.page.size(section=0), name) == default


def test_a_value_that_is_not_a_number_reads_none() -> None:
    doc = HwpxDocument.new()
    page_pr = _page_pr(doc)
    page_pr.set("width", "wide")
    page_pr.find(f"{HP}margin").set("left", "1cm")
    size = doc.page.size(section=0)
    assert size.width is None and size.drawn_width is None and size.drawn_height is None
    assert doc.page.margins(section=0).left is None


def test_no_page_setting_reads_none_and_new_tables_take_no_guessed_width() -> None:
    doc = HwpxDocument.new()
    sec_pr = doc.sections[0].element.find(f".//{HP}secPr")
    sec_pr.remove(sec_pr.find(f"{HP}pagePr"))
    size, margins = doc.page.size(section=0), doc.page.margins(section=0)
    assert (size.width, size.height, margins.left, margins.header) == (None, None, None, None)
    paragraph = doc.add_paragraph("")
    assert paragraph.available_width is None
    table = paragraph.add_table(1, 2)  # falls back to the fixed default width, as it did with 0
    assert table.width > 0


def test_a_zero_written_in_the_file_still_reads_zero() -> None:
    doc = HwpxDocument.new()
    _page_pr(doc).find(f"{HP}margin").set("gutter", "0")
    _page_pr(doc).find(f"{HP}margin").set("left", "0")
    margins = doc.page.margins(section=0)
    assert (margins.left, margins.gutter) == (0, 0)
