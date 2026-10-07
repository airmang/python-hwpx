"""New tables and ``set_column_widths`` write a column narrower than Hancom draws it at its floor.

Hancom draws a table column at least its cells' left and right margins and 283 wide, keeps the narrower width
written in the cells, and saves the table as wide as it draws the columns.
``tests/fixtures/hancom_saved/table_column_floor_*.hwpx`` are its saves of two-column tables whose first column
is written just below or above the floor (cell margins 510 + 510, 0 + 0 and 1000 + 1000) and the second 20000
wide; ``table_width_zero.hwpx`` of a 2x2 table written 0 wide, ``table_column_weights_zero_one.hwpx`` of a table
42520 wide given column weights 0 and 1.
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


def _saved_table(name: str) -> etree._Element:
    with zipfile.ZipFile(FIXTURES / name) as archive:
        return next(etree.fromstring(archive.read("Contents/section0.xml")).iter(f"{HP}tbl"))


def _table_width(table: etree._Element) -> int:
    return int(table.find(f"{HP}sz").get("width"))


def _sections(document: HwpxDocument) -> list[bytes]:
    return [etree.tostring(section.element) for section in document.sections]


@pytest.mark.parametrize(
    ("fixture", "written", "drawn"),
    [
        ("table_column_floor_1302.hwpx", 1302, 1303),  # the table's margins, 510 + 510
        ("table_column_floor_1304.hwpx", 1304, 1304),
        ("table_column_floor_m0_282.hwpx", 282, 283),  # the cells' own margins, 0 + 0
        ("table_column_floor_m1000_2282.hwpx", 2282, 2283),  # 1000 + 1000
    ],
)
def test_hancom_draws_a_column_at_least_its_cell_margins_and_283_wide(fixture: str, written: int, drawn: int) -> None:
    table = _saved_table(fixture)

    assert [int(size.get("width")) for size in table.iter(f"{HP}cellSz")] == [written, 20000]  # kept
    assert _table_width(table) == drawn + 20000


def test_hancom_saves_a_table_as_wide_as_it_draws_its_columns() -> None:
    assert _table_width(_saved_table("table_width_zero.hwpx")) == 2 * 1303  # written 0 wide
    assert _table_width(_saved_table("table_column_weights_zero_one.hwpx")) == 1303 + 42520  # weights 0 and 1


@pytest.mark.parametrize(("width", "written"), [(1, 2606), (2605, 2606), (2606, 2606), (2609, 2609)])
def test_a_new_table_is_written_as_wide_as_hancom_draws_its_columns(width: int, written: int) -> None:
    document = HwpxDocument.new()

    table = document.add_table(2, 2, width=width)

    assert _table_width(table.element) == written
    assert sum(table.cell(0, column).width for column in range(2)) == written
    assert min(table.cell(row, column).width for row in range(2) for column in range(2)) >= 1303


def test_a_nested_table_in_a_narrow_cell_is_written_as_wide_as_hancom_draws_its_columns() -> None:
    document = HwpxDocument.new()
    outer = document.add_table(1, 2, width=2606)  # 1303-wide cells: 283 inside their margins

    nested = outer.cell(0, 0).add_table(1, 2)

    assert _table_width(nested.element) == 2606


@pytest.mark.parametrize("width", [0, -1, 2**31, 2606.0, True])
def test_a_table_width_that_is_no_positive_int_is_refused_before_anything_is_added(width: object) -> None:
    document = HwpxDocument.new()
    outer = document.add_table(1, 1)
    paragraph = document.add_paragraph("표 앞 글")
    before = (len(document.paragraphs), _sections(document))

    for add in (
        lambda: document.add_table(2, 2, width=width),
        lambda: outer.cell(0, 0).add_table(2, 2, width=width),
        lambda: paragraph.add_table(2, 2, width=width),
    ):
        with pytest.raises(HwpxValueError) as caught:
            add()  # type: ignore[no-untyped-call]
        assert caught.value.code == "table-width-value"

    assert (len(document.paragraphs), _sections(document)) == before


def test_set_column_widths_writes_a_column_below_its_floor_at_the_floor_and_the_table_wider() -> None:
    # As Hancom saved the same table and weights: 1303 and 42520 wide, 43823 in all.
    document = HwpxDocument.new()
    table = document.add_table(2, 2)

    table.set_column_widths([0, 1])

    assert [[table.cell(row, column).width for column in range(2)] for row in range(2)] == [[1303, 42520]] * 2
    assert _table_width(table.element) == _table_width(_saved_table("table_column_weights_zero_one.hwpx"))


def test_a_column_takes_the_floor_of_its_own_cell_margins() -> None:
    # As Hancom saved the table: cell margins 0 + 0, the column 282 written and 283 drawn, 20283 in all.
    document = HwpxDocument.new()
    table = document.add_table(1, 2, width=20282)
    table.cell(0, 0).set_margins(left=0, right=0)

    table.set_column_widths([282, 20000])

    assert [table.cell(0, column).width for column in range(2)] == [283, 20000]
    assert _table_width(table.element) == _table_width(_saved_table("table_column_floor_m0_282.hwpx"))
