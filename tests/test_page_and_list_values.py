"""Page, section and list values Hancom does not keep are refused before anything changes.

Hancom keeps a line number's start and step, a section's start numbers and a list's start as 16 bits unsigned, a
page border's offsets as 16 bits signed, and reads a gutter type or a page border's fill area it does not know as
its default. ``tests/fixtures/hancom_saved/`` holds its saves of each value written past those bounds:
``line_numbers_start_65536``, ``list_start_65536``, ``list_start_huge`` (2**31), ``section_start_page_65536``,
``section_start_page_huge`` (2**31), ``section_start_table_65536``, ``page_border_offset_huge`` (2**31),
``page_border_fill_area_unknown`` (EVERYWHERE) and ``page_gutter_type_unknown`` (MIDDLE); and of the values it
keeps at the bounds: ``page_border_offset_32767`` and ``page_border_offset_65535`` (read as -1),
``line_numbers_count_by_65536``, and 0 (``line_numbers_start_0``, ``section_start_page_0``, ``list_start_0``). The
negative values python-hwpx used to write as 0 are refused too.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _saved(name: str, part: str = "Contents/section0.xml") -> etree._Element:
    with zipfile.ZipFile(FIXTURES / f"{name}.hwpx") as archive:
        return etree.fromstring(archive.read(part))


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    for index in range(3):
        document.add_paragraph(f"항목 {index + 1}")
    return document


def _parts(document: HwpxDocument) -> list[bytes]:
    return [etree.tostring(part.element) for part in (*document.oxml.headers, *document.sections)]


def test_hancom_keeps_numbers_as_16_bits_and_reads_unknown_page_values_as_its_defaults() -> None:
    assert next(_saved("line_numbers_start_65536").iter(f"{HP}lineNumberShape")).get("startNumber") == "0"
    starts = {numbering.get("start") for numbering in _saved("list_start_65536", "Contents/header.xml").iter(f"{HH}numbering")}
    assert starts == {"0"}  # 65536, and the new document's own list starting at 0
    starts = [numbering.get("start") for numbering in _saved("list_start_huge", "Contents/header.xml").iter(f"{HH}numbering")]
    assert starts[-1] == "65535"  # 2**31
    for name, attribute in (("section_start_page_65536", "page"), ("section_start_page_huge", "page"),
                            ("section_start_table_65536", "tbl")):
        assert next(_saved(name).iter(f"{HP}startNum")).get(attribute) == "0"
    assert next(_saved("page_border_offset_huge").iter(f"{HP}pageBorderFill")).find(f"{HP}offset").get("top") == "0"
    assert next(_saved("page_border_fill_area_unknown").iter(f"{HP}pageBorderFill")).get("fillArea") == "PAPER"
    assert next(_saved("page_gutter_type_unknown").iter(f"{HP}pagePr")).get("gutterType") == "LEFT_ONLY"


def test_hancom_keeps_0_and_the_last_value_of_each_bound() -> None:
    def offset(name: str) -> str | None:
        return next(_saved(name).iter(f"{HP}pageBorderFill")).find(f"{HP}offset").get("top")

    assert offset("page_border_offset_32767") == "32767"
    assert offset("page_border_offset_65535") == str(2**32 - 1)  # read as -1, saved in its unsigned form
    assert next(_saved("line_numbers_count_by_65536").iter(f"{HP}lineNumberShape")).get("countBy") == "0"
    assert next(_saved("line_numbers_start_0").iter(f"{HP}lineNumberShape")).get("startNumber") == "0"
    assert next(_saved("section_start_page_0").iter(f"{HP}startNum")).get("page") == "0"  # the page numbers go on
    assert {numbering.get("start") for numbering in _saved("list_start_0", "Contents/header.xml").iter(f"{HH}numbering")} \
        == {"0"}  # drawn as 1


_REFUSED: dict[str, tuple[Callable[[HwpxDocument], object], str]] = {
    "line number start past 16 bits": (lambda d: d.page.set_line_numbers(start_number=65536), "page-number-value"),
    "line number step past 16 bits": (lambda d: d.page.set_line_numbers(count_by=65536), "page-number-value"),
    "negative line number start": (lambda d: d.page.set_line_numbers(start_number=-1), "page-number-value"),
    "negative line number distance": (lambda d: d.page.set_line_numbers(distance=-1), "page-number-value"),
    "section page start past 16 bits": (
        lambda d: d.oxml.sections[0].properties.set_start_numbering(page=65536), "page-number-value"),
    "section table start past 16 bits": (
        lambda d: d.oxml.sections[0].properties.set_start_numbering(table=65536), "page-number-value"),
    "negative section start": (
        lambda d: d.oxml.sections[0].properties.set_start_numbering(equation=-1), "page-number-value"),
    "list start past 16 bits": (
        lambda d: d.styles.apply_list_format(paragraph_indexes=[1, 2], kind="number", start=65536),
        "style-list-start-value"),
    "negative list start": (
        lambda d: d.styles.apply_list_format(paragraph_indexes=[1, 2], kind="number", start=-1),
        "style-list-start-value"),
    "page border type": (
        lambda d: d.oxml.sections[0].properties.set_page_border_fill(page_type="SOMETIMES"),
        "page-border-fill-invalid"),
    "page border fill area": (
        lambda d: d.oxml.sections[0].properties.set_page_border_fill(fill_area="EVERYWHERE"),
        "page-border-fill-invalid"),
    "page border offset past 16 bits signed": (
        lambda d: d.oxml.sections[0].properties.set_page_border_fill(offset_top=32768), "page-border-fill-invalid"),
    "negative page border offset": (
        lambda d: d.oxml.sections[0].properties.set_page_border_fill(offset_left=-1), "page-border-fill-invalid"),
    "gutter type": (lambda d: d.page.set_size(gutter_type="MIDDLE"), "page-gutter-type-invalid"),
    "negative page width": (lambda d: d.page.set_size(width=-1), "page-size-value"),
    "page height past 31 bits": (lambda d: d.page.set_size(height=2**31), "page-size-value"),
    "negative margin": (lambda d: d.page.set_margins(left=-1000), "page-size-value"),
    "negative header margin": (lambda d: d.page.set_margins(header=-1), "page-size-value"),
    "negative margin in page setup": (lambda d: d.page.setup(paper_size="A4", margin_left_mm=-1), "page-size-value"),
    "negative character size": (lambda d: d.styles.ensure_run(size=-1), "style-run-size-value"),
}


@pytest.mark.parametrize("case", sorted(_REFUSED))
def test_a_value_hancom_does_not_keep_is_refused_before_anything_changes(case: str) -> None:
    call, code = _REFUSED[case]
    document = _document()
    before = _parts(document)

    with pytest.raises(HwpxValueError) as caught:
        call(document)

    assert caught.value.code == code
    assert _parts(document) == before


def test_the_bounds_hancom_keeps_are_written_as_given() -> None:
    document = _document()
    properties = document.oxml.sections[0].properties

    document.page.set_line_numbers(start_number=65535, count_by=0, distance=2**31 - 1)
    properties.set_start_numbering(page=0, table=65535)
    properties.set_page_border_fill(offset_top=32767, offset_left=0)
    document.styles.apply_list_format(paragraph_indexes=[1, 2], kind="number", start=0)

    section = document.sections[0].element
    line_numbers = next(section.iter(f"{HP}lineNumberShape"))
    assert (line_numbers.get("startNumber"), line_numbers.get("countBy"), line_numbers.get("distance")) == \
        ("65535", "0", str(2**31 - 1))
    start = next(section.iter(f"{HP}startNum"))
    assert (start.get("page"), start.get("tbl")) == ("0", "65535")
    offset = next(section.iter(f"{HP}pageBorderFill")).find(f"{HP}offset")
    assert (offset.get("top"), offset.get("left")) == ("32767", "0")
    assert "0" in {numbering.get("start") for numbering in document.oxml.headers[0].element.iter(f"{HH}numbering")}


@pytest.mark.parametrize(("tag", "call"), [
    ("startNum", lambda p: p.set_start_numbering(page=2)),
    ("lineNumberShape", lambda p: p.set_line_number_shape(count_by=5)),
    ("pageBorderFill", lambda p: p.set_page_border_fill(page_type="BOTH", offset_top=500)),
    ("grid", lambda p: p.set_grid(line_grid=0)),
    ("visibility", lambda p: p.set_visibility(hide_first_header=True)),
])
def test_a_setting_missing_from_a_section_is_added(tag: str, call: Callable[[object], object]) -> None:
    # The section settings are lxml elements: a setting they lack is added with them, not with the standard library
    # (which failed with TypeError).
    document = HwpxDocument.new()
    properties = document.oxml.sections[0].properties
    for element in list(properties.element.findall(f"{HP}{tag}")):
        properties.element.remove(element)

    call(properties)

    assert properties.element.find(f"{HP}{tag}") is not None
