# SPDX-License-Identifier: Apache-2.0
"""A border/fill whose sides differ, and the heights of a table's rows.

A ruled table (open at the sides, a heavy line above and below, a double line under the header
row) needs a different line on each side of a cell, and a banner needs rows of a given height.
"""
from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument


def _lines(document: HwpxDocument, fill_id: str) -> dict[str, tuple[str, float, str]]:
    info = document.styles.border_fill_info(fill_id)
    assert info is not None
    return {
        side: (line.type, line.width_mm, line.color)
        for side, line in (("left", info.left), ("right", info.right), ("top", info.top), ("bottom", info.bottom))
    }


def test_each_side_takes_its_own_line() -> None:
    document = HwpxDocument.new()

    fill_id = document.styles.ensure_border_fill(
        border_color="#000000",
        border_width="0.15 mm",
        fill_color="#DFE6F7",
        sides={
            "left": None,
            "top": {"width": "0.4 mm"},
            "bottom": {"type": "double_slim", "width": 0.5, "color": "#112233"},
        },
    )

    assert _lines(document, fill_id) == {
        "left": ("NONE", 0.15, "#000000"),
        "right": ("SOLID", 0.15, "#000000"),  # not named: the uniform border
        "top": ("SOLID", 0.4, "#000000"),  # what a side leaves out is the uniform border's
        "bottom": ("DOUBLE_SLIM", 0.5, "#112233"),
    }
    info = document.styles.border_fill_info(fill_id)
    assert info is not None and info.fill == "#DFE6F7"


def test_a_side_not_named_follows_active_borders() -> None:
    document = HwpxDocument.new()

    fill_id = document.styles.ensure_border_fill(active_borders=("top",), sides={"bottom": {"width": "0.4 mm"}})

    lines = _lines(document, fill_id)
    assert [lines[side][0] for side in ("left", "right", "top", "bottom")] == ["NONE", "NONE", "SOLID", "SOLID"]
    assert (lines["top"][1], lines["bottom"][1]) == (0.12, 0.4)


def test_the_same_sides_give_the_same_border_fill() -> None:
    document = HwpxDocument.new()
    sides = {"left": None, "right": None, "top": {"width": "0.4 mm"}}

    first = document.styles.ensure_border_fill(border_color="#000000", sides=sides)
    again = document.styles.ensure_border_fill(border_color="#000000", sides={"top": {"width": "0.40mm"}, "left": None, "right": None})
    uniform = document.styles.ensure_border_fill(border_color="#000000")
    other = document.styles.ensure_border_fill(border_color="#000000", sides={**sides, "top": {"width": "0.5 mm"}})

    assert first == again
    assert len({first, uniform, other}) == 3


@pytest.mark.parametrize(
    "sides",
    [
        {"middle": None},
        {"top": {"weight": "0.4 mm"}},
        {"top": {"type": "XYZ"}},
    ],
)
def test_a_side_that_cannot_be_drawn_is_refused_before_anything_is_added(sides) -> None:
    document = HwpxDocument.new()
    before = set(document.styles.border_fills)

    with pytest.raises(ValueError):
        document.styles.ensure_border_fill(sides=sides)

    assert set(document.styles.border_fills) == before


def test_a_border_fill_with_its_own_sides_saves_and_reopens(tmp_path) -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    fill_id = document.styles.ensure_border_fill(
        border_color="#000000", sides={"left": None, "bottom": {"type": "DOUBLE_SLIM", "width": "0.5 mm"}}
    )
    table.set_cell_border_fill(0, 0, fill_id)
    path = tmp_path / "sides.hwpx"

    document.save_to_path(path)

    reopened = HwpxDocument.open(path)
    cell = next(table for paragraph in reopened.paragraphs for table in paragraph.tables).cell(0, 0)
    lines = _lines(reopened, cell.element.get("borderFillIDRef"))
    assert lines["left"][0] == "NONE" and lines["bottom"][:2] == ("DOUBLE_SLIM", 0.5)


def test_rows_take_the_heights_given_and_the_table_their_sum() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 2)

    table.set_row_heights([430, 3570, 430])

    assert [[table.cell(row, col).height for col in range(2)] for row in range(3)] == [[430] * 2, [3570] * 2, [430] * 2]
    assert table.height == 4430


def test_a_cell_over_two_rows_takes_both_heights() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    table.merge_cells(0, 0, 1, 0)

    table.set_row_heights([1000, 2000, 3000])

    assert table.cell(0, 0).height == 3000
    assert [table.cell(row, 1).height for row in range(3)] == [1000, 2000, 3000]
    assert table.height == 6000


@pytest.mark.parametrize("heights", [[1000, 1000], [1000, 0, 1000], [1000, 1000.5, 1000], [True, 1000, 1000]])
def test_heights_that_do_not_fit_the_rows_are_refused_and_change_nothing(heights) -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    before = [table.cell(row, 0).height for row in range(3)], table.height

    with pytest.raises(ValueError) as caught:
        table.set_row_heights(heights)

    assert caught.value.code == "table-row-heights-value"  # type: ignore[attr-defined]
    assert ([table.cell(row, 0).height for row in range(3)], table.height) == before
