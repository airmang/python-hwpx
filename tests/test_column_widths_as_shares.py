"""Columns of unequal width are written as the shares of the text width out of 32768 Hancom keeps (``hp:colSz``).

Hancom lays a column out ``width * text width / 32768`` wide, whatever the shares add up to.
``tests/fixtures/hancom_saved/columns_unequal_widths_in_*.hwpx`` are its saves of two columns written
``[(20000, 1000), (21520, 0)]`` (HWP units adding up to the text width, 42520: the second column then runs off
the paper) and ``[(16000, 768), (16000, 0)]`` (shares adding up to 32768).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.layout import pages as page_layout

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _saved_section(name: str) -> etree._Element:
    with zipfile.ZipFile(FIXTURES / name) as archive:
        return etree.fromstring(archive.read("Contents/section0.xml"))


def _sizes(section: etree._Element) -> list[tuple[str | None, str | None]]:
    return [(size.get("width"), size.get("gap")) for size in section.iter(f"{HP}colSz")]


def _sections(document: HwpxDocument) -> list[bytes]:
    return [etree.tostring(section.element) for section in document.sections]


@pytest.mark.parametrize(
    ("fixture", "widths"),
    [("columns_unequal_widths_in_hwpunit.hwpx", (25952, 27925)), ("columns_unequal_widths_in_shares.hwpx", (20762,) * 2)],
)
def test_hancom_lays_a_column_out_its_share_of_32768_of_the_text_width(fixture: str, widths: tuple[int, ...]) -> None:
    # 20000 and 21520 of 32768 over a text width of 42520 are 25952 and 27925 wide (not 20000 and 21520, their
    # share of what the sizes add up to); 16000 of 32768 is 20762.
    section = _saved_section(fixture)

    assert {int(line.get("horzsize")) for line in section.iter(f"{HP}lineseg")} == set(widths)
    assert page_layout._columns(section, 42520) == (2, min(widths), widths, 0)


@pytest.mark.parametrize("where", ["section", "paragraph"])
def test_column_widths_in_hwp_units_are_written_as_shares(where: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("단 앞 글")

    document.page.set_columns(2, same_size=False, column_widths=[(20000, 1000), (21520, 0)],
                              **({"paragraph": paragraph} if where == "paragraph" else {}))

    written = paragraph.element if where == "paragraph" else document.sections[0].element
    assert _sizes(written) == [("15413", "771"), ("16584", "0")]  # 20000, 1000 and 21520 of 42520


def test_column_widths_in_hwp_units_adding_up_to_the_text_width_come_out_as_wide_as_given() -> None:
    document = HwpxDocument.new()

    document.page.set_columns(2, same_size=False, column_widths=[(20000, 1000), (21520, 0)])

    assert page_layout._columns(document.sections[0].element, 42520)[2] == (20000, 21520)


@pytest.mark.parametrize(
    ("given", "written"),
    [
        ([(10632, 873), (21263, 0)], [(10632, 873), (21263, 0)]),  # shares already
        ([(6552, 873), (12234, 873), (12236, 0)], [(6552, 873), (12234, 873), (12236, 0)]),
        ([(1, 0), (2, 0)], [(10923, 0), (21845, 0)]),  # plain proportions
    ],
)
def test_column_widths_are_written_in_their_proportions_adding_up_to_32768(
    given: list[tuple[int, int]], written: list[tuple[int, int]]
) -> None:
    document = HwpxDocument.new()

    document.page.set_columns(len(given), same_size=False, column_widths=given)

    assert _sizes(document.sections[0].element) == [(str(width), str(gap)) for width, gap in written]


@pytest.mark.parametrize(
    "column_widths",
    [
        [(-1, 0), (20000, 0)],
        [(20000, -1000), (20000, 0)],
        [(0, 0), (0, 0)],
        [(20000.0, 0), (20000, 0)],
        [(True, 0), (1, 0)],
        [(20000,), (20000, 0)],
    ],
)
def test_column_widths_that_are_no_shares_are_refused_before_anything_changes(column_widths: list[tuple]) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("단 앞 글")
    before = (len(document.paragraphs), _sections(document))

    for where in ({}, {"paragraph": paragraph}):  # the section's own columns, new columns at a paragraph
        with pytest.raises(HwpxValueError) as caught:
            document.page.set_columns(2, same_size=False, column_widths=column_widths, **where)
        assert caught.value.code == "page-column-widths-value"

    assert (len(document.paragraphs), _sections(document)) == before
