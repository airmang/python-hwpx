"""Caption gaps, column gaps and new numbers Hancom does not keep are refused before anything changes.

Hancom keeps a caption's gap and the gap between columns of the same width as signed 16-bit numbers and a new
number (``hp:newNum/@num``) as an unsigned one, reading anything else wrapped (and a column gap written as negative
text as 0). ``tests/fixtures/hancom_saved/caption_gap_*.hwpx``, ``columns_gap_*.hwpx`` and ``new_page_number_*.hwpx``
are its saves of a table caption written 32767, -1 and 32768 from the table, of two columns written 32767, 32768
and -1 apart and of a page number restarted at 0, 65535, 65536 and -1.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


_SAVED_VALUES = {"caption": "gap", "colPr": "sameGap", "newNum": "num"}


def _saved(name: str, tag: str) -> str | None:
    """The first ``hp:<tag>``'s saved value in the Hancom-saved fixture *name*: a caption's gap, the columns' gap
    or a newNum's num."""

    with zipfile.ZipFile(FIXTURES / name) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    return next(root.iter(f"{HP}{tag}")).get(_SAVED_VALUES[tag])


def _sections(document: HwpxDocument) -> list[bytes]:
    return [etree.tostring(section.element) for section in document.sections]


def test_hancom_keeps_a_caption_gap_as_a_signed_16_bit_number() -> None:
    assert _saved("caption_gap_largest_kept.hwpx", "caption") == "32767"
    assert _saved("caption_gap_negative_kept.hwpx", "caption") == "-1"
    assert _saved("caption_gap_wrapped.hwpx", "caption") == "-32768"  # written 32768


@pytest.mark.parametrize("gap", [32768, -32769, 65536, 850.0, True])
def test_a_caption_gap_hancom_does_not_keep_is_refused_before_anything_changes(gap: object) -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    shape = document.shapes.add_rectangle(width=14400, height=7200)
    shape.set_caption("그림 1", side="BOTTOM", gap=850)
    before = etree.tostring(table.element), etree.tostring(shape.element)

    for host in (table, shape):
        with pytest.raises(HwpxValueError) as caught:
            host.set_caption("새 캡션", side="BOTTOM", gap=gap)  # type: ignore[arg-type]
        assert caught.value.code == "shape-caption-gap-value"

    assert (etree.tostring(table.element), etree.tostring(shape.element)) == before


@pytest.mark.parametrize("gap", [-32768, -1, 0, 32767])
def test_the_caption_gaps_hancom_keeps_are_written_as_given(gap: int) -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)

    table.set_caption("표 1", side="BOTTOM", gap=gap)

    assert table.element.find(f"{HP}caption").get("gap") == str(gap)


def test_hancom_reads_the_gap_between_columns_as_a_signed_16_bit_number() -> None:
    assert _saved("columns_gap_largest_kept.hwpx", "colPr") == "32767"
    # written 32768: read as -32768 (the second column then starts inside the first), saved unsigned 32-bit
    assert _saved("columns_gap_wrapped.hwpx", "colPr") == str(2**32 - 2**15)
    assert _saved("columns_gap_negative_read_as_0.hwpx", "colPr") == "0"  # written "-1"


@pytest.mark.parametrize("gap", [-1, 32768, 65536, 1200.0, True])
def test_a_column_gap_hancom_does_not_keep_is_refused_before_anything_changes(gap: object) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("단 앞 글")
    before = (len(document.paragraphs), _sections(document))

    for where in ({}, {"paragraph": paragraph}):  # the section's own columns, new columns at a paragraph
        with pytest.raises(HwpxValueError) as caught:
            document.page.set_columns(col_count=2, same_gap=gap, **where)  # type: ignore[arg-type]
        assert caught.value.code == "page-column-gap-value"

    assert (len(document.paragraphs), _sections(document)) == before


@pytest.mark.parametrize("gap_mm", [-1.0, 200.0])
def test_page_setup_checks_the_column_gap_before_the_page_changes(gap_mm: float) -> None:
    document = HwpxDocument.new()
    before = _sections(document)

    with pytest.raises(HwpxValueError) as caught:
        document.page.setup(paper_size="A4", orientation="LANDSCAPE", columns=2, column_gap_mm=gap_mm)

    assert caught.value.code == "page-column-gap-value"
    assert _sections(document) == before


@pytest.mark.parametrize("gap", [0, 32767])
def test_the_column_gaps_hancom_keeps_are_written_as_given(gap: int) -> None:
    document = HwpxDocument.new()

    document.page.set_columns(col_count=2, same_gap=gap)

    assert next(document.sections[0].element.iter(f"{HP}colPr")).get("sameGap") == str(gap)


def test_hancom_keeps_a_new_number_as_an_unsigned_16_bit_number() -> None:
    assert _saved("new_page_number_smallest_kept.hwpx", "newNum") == "0"
    assert _saved("new_page_number_largest_kept.hwpx", "newNum") == "65535"
    assert _saved("new_page_number_wrapped.hwpx", "newNum") == "0"  # written 65536
    assert _saved("new_page_number_negative_wrapped.hwpx", "newNum") == "65535"  # written -1


@pytest.mark.parametrize("number", [-1, 65536, 2**31])
@pytest.mark.parametrize("kind", ["PAGE", "TABLE"])
def test_a_new_number_hancom_does_not_keep_is_refused_before_anything_is_added(number: int, kind: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("2쪽 첫 글")
    before = etree.tostring(paragraph.element)

    with pytest.raises(HwpxValueError) as caught:
        document.page.restart_page_number(paragraph, number=number, kind=kind)

    assert caught.value.code == "page-new-num-value"
    assert etree.tostring(paragraph.element) == before


@pytest.mark.parametrize("number", [0, 65535])
def test_the_new_numbers_hancom_keeps_are_written_as_given(number: int) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("2쪽 첫 글")

    document.page.restart_page_number(paragraph, number=number)

    assert next(paragraph.element.iter(f"{HP}newNum")).get("num") == str(number)
