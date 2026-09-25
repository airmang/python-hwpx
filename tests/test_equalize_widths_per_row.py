"""``equalize_column_widths()`` gives the cells of each row one width, like Hancom's "셀 너비를 같게".

The expected layouts are what Hancom writes for the same tables: each row splits the table
width among its own cells (a merged cell counts once), the width is rounded up to a common
multiple of every row's cell count so that all rows end together, and the column grid is
rebuilt from the new cell edges.
"""

from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.namespaces import HP


def _layout(table) -> tuple[int, list[list[tuple[int, int, int]]]]:
    rows = []
    for tr in table.element.findall(f"{HP}tr"):
        rows.append(
            [
                (
                    int(tc.find(f"{HP}cellAddr").get("colAddr")),
                    int(tc.find(f"{HP}cellSpan").get("colSpan")),
                    int(tc.find(f"{HP}cellSz").get("width")),
                )
                for tc in tr.findall(f"{HP}tc")
            ]
        )
    return table.column_count, rows


def _table_width(table) -> int:
    return int(table.element.find(f"{HP}sz").get("width"))


def test_a_row_with_a_merged_cell_splits_its_width_among_its_own_cells() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3, width=18366)
    table.merge_cells("A1:B1")

    table.equalize_column_widths()

    assert _layout(table) == (
        4,
        [
            [(0, 2, 9183), (2, 2, 9183)],
            [(0, 1, 6122), (1, 2, 6122), (3, 1, 6122)],
            [(0, 1, 6122), (1, 2, 6122), (3, 1, 6122)],
        ],
    )
    assert _table_width(table) == 18366


def test_staggered_cell_edges_line_up_again() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=4, width=18366)
    table.merge_cells("A1:B1")
    table.merge_cells("B2:C2")
    table.set_column_widths([6122, 1415, 4707, 6122])
    assert _layout(table)[1][0] == [(0, 2, 7537), (2, 1, 4707), (3, 1, 6122)]

    table.equalize_column_widths()

    assert _layout(table) == (
        3,
        [
            [(0, 1, 6122), (1, 1, 6122), (2, 1, 6122)],
            [(0, 1, 6122), (1, 1, 6122), (2, 1, 6122)],
        ],
    )


def test_rows_that_do_not_divide_evenly_widen_the_table_to_a_common_multiple() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=4, width=24488)
    table.merge_cells("A1:B1")

    table.equalize_column_widths()

    assert _layout(table) == (
        6,
        [
            [(0, 2, 8164), (2, 2, 8164), (4, 2, 8164)],
            [(0, 1, 6123), (1, 2, 6123), (3, 2, 6123), (5, 1, 6123)],
        ],
    )
    assert _table_width(table) == 24492


def test_a_tall_cell_keeps_one_width_when_its_rows_agree() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3, width=41952)
    table.merge_cells("A1:A2")
    table.merge_cells("A3:B3")

    table.equalize_column_widths()

    assert _layout(table) == (
        4,
        [
            [(0, 1, 13984), (1, 2, 13984), (3, 1, 13984)],
            [(1, 2, 13984), (3, 1, 13984)],
            [(0, 2, 20976), (2, 2, 20976)],
        ],
    )


def test_a_tall_cell_that_would_need_two_widths_is_refused_and_the_table_kept() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3, width=41952)
    table.merge_cells("A1:A2")
    table.merge_cells("B2:C2")
    before = (_layout(table), _table_width(table))

    with pytest.raises(HwpxValueError) as caught:
        table.equalize_column_widths()

    assert isinstance(caught.value, ValueError)
    assert "(0, 0)" in str(caught.value)
    assert (_layout(table), _table_width(table)) == before


def test_the_rebuilt_grid_survives_save_and_reopen() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3, width=18366)
    table.merge_cells("A1:B1")
    table.cell(0, 0).text = "합친 칸"
    table.cell(1, 1).text = "가운데"
    table.equalize_column_widths()
    expected = _layout(table)

    reopened = HwpxDocument.open(document.to_bytes()).tables.all[0]

    assert _layout(reopened) == expected
    assert reopened.cell(0, 0).text == "합친 칸"
    assert reopened.cell(1, 1).text == "가운데"
    assert reopened.cell(1, 2).text == "가운데"
    assert len(list(reopened.iter_grid())) == 3 * 4


def test_resized_cells_drop_their_line_layout_cache() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=4, width=24488)
    table.merge_cells("A1:B1")
    for cell in (table.cell(0, 0), table.cell(1, 0)):
        paragraph = cell.element.find(f"{HP}subList").find(f"{HP}p")
        cache = paragraph.makeelement(f"{HP}linesegarray", {})
        cache.append(cache.makeelement(f"{HP}lineseg", {"horzsize": "1"}))
        paragraph.append(cache)

    table.equalize_column_widths()

    for cell in (table.cell(0, 0), table.cell(1, 0)):
        assert cell.element.find(f".//{HP}linesegarray") is None


def test_an_even_table_is_unchanged() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=3, width=30000)
    before = _layout(table)

    table.equalize_column_widths()

    assert _layout(table) == before
    assert _table_width(table) == 30000
