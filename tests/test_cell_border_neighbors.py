# SPDX-License-Identifier: Apache-2.0
"""A cell border edit also sets the shared edge of the neighbouring cells.

Each cell keeps its own four sides and both cells of a shared edge are drawn,
so Hancom's cell border command changes the neighbour's side of that edge too.
``set_cell_borders`` does the same; ``set_cell_border_fill`` only points one
cell at a definition and leaves its neighbours alone.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def _side(doc: HwpxDocument, table, row: int, col: int, side: str) -> tuple[str | None, str | None]:
    ref = table.cell(row, col).element.get("borderFillIDRef")
    fill = doc.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{ref}']")
    element = fill.find(f"{HH}{side}")
    return element.get("type"), element.get("color")


def test_corner_cell_border_reaches_the_right_and_lower_neighbours() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    before = _side(doc, table, 1, 1, "leftBorder")
    table.set_cell_borders(0, 0, color="#FF0000", line_type="DASH")
    assert _side(doc, table, 0, 0, "rightBorder") == ("DASH", "#FF0000")
    assert _side(doc, table, 0, 1, "leftBorder") == ("DASH", "#FF0000")
    assert _side(doc, table, 1, 0, "topBorder") == ("DASH", "#FF0000")
    # the neighbours' other sides and the far cell stay as they were
    assert _side(doc, table, 0, 1, "rightBorder") != ("DASH", "#FF0000")
    assert _side(doc, table, 1, 1, "leftBorder") == before


def test_middle_cell_border_reaches_all_four_neighbours() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    table.set_cell_borders(1, 1, color="#0000FF", line_type="DOT")
    assert _side(doc, table, 0, 1, "bottomBorder") == ("DOT", "#0000FF")
    assert _side(doc, table, 2, 1, "topBorder") == ("DOT", "#0000FF")
    assert _side(doc, table, 1, 0, "rightBorder") == ("DOT", "#0000FF")
    assert _side(doc, table, 1, 2, "leftBorder") == ("DOT", "#0000FF")
    assert _side(doc, table, 0, 0, "bottomBorder") != ("DOT", "#0000FF")


def test_the_shared_edges_survive_save_and_reopen() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    table.set_cell_borders(0, 0, color="#FF0000", line_type="DASH")
    reopened = HwpxDocument.open(doc.to_bytes())
    table2 = reopened.paragraphs[1].tables[0] if reopened.paragraphs[1].tables else None
    assert table2 is not None
    assert _side(reopened, table2, 0, 1, "leftBorder") == ("DASH", "#FF0000")
    assert _side(reopened, table2, 1, 0, "topBorder") == ("DASH", "#FF0000")


def test_pointing_one_cell_at_a_border_fill_leaves_the_neighbours_alone() -> None:
    # A cell pointed at its own definition, one cell at a time, is how per-cell
    # lines (connectors, open boxes) are drawn: the neighbours must keep theirs.
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    before = {
        (row, col, side): _side(doc, table, row, col, side)
        for row, col in ((0, 1), (1, 0), (1, 1))
        for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder")
    }
    no_lines = doc.styles.ensure_border_fill(active_borders=[])
    table.set_cell_border_fill(0, 0, no_lines)
    assert _side(doc, table, 0, 0, "rightBorder")[0] == "NONE"
    assert {key: _side(doc, table, *key) for key in before} == before


def test_a_longer_merged_neighbour_keeps_its_line() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    table.merge_cells(0, 0, 1, 0)  # (0,0) spans two rows
    before = _side(doc, table, 0, 0, "rightBorder")
    table.set_cell_borders(0, 1, color="#FF0000", line_type="DASH")
    assert _side(doc, table, 0, 0, "rightBorder") == before
    assert _side(doc, table, 0, 2, "leftBorder") == ("DASH", "#FF0000")
    assert _side(doc, table, 1, 1, "topBorder") == ("DASH", "#FF0000")


def test_a_merged_cell_reaches_every_neighbour_along_its_side() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    table.merge_cells(0, 0, 1, 0)
    table.set_cell_borders(0, 0, color="#FF0000", line_type="DASH")
    assert _side(doc, table, 0, 1, "leftBorder") == ("DASH", "#FF0000")
    assert _side(doc, table, 1, 1, "leftBorder") == ("DASH", "#FF0000")
    assert _side(doc, table, 2, 0, "topBorder") == ("DASH", "#FF0000")


def _sides_by_cell(doc: HwpxDocument) -> dict[tuple[int, int], dict[str, tuple[str | None, ...]]]:
    """(row, col) -> side -> (type, width, color) of the first table, read through each cell's border fill."""
    table = next(table for paragraph in doc.paragraphs for table in paragraph.tables)
    header = doc.oxml.headers[0].element
    cells = {}
    for tc in table.element.iter(f"{HP}tc"):
        address = tc.find(f"{HP}cellAddr")
        fill = header.find(f".//{HH}borderFill[@id='{tc.get('borderFillIDRef')}']")
        sides = {side: fill.find(f"{HH}{side}") for side in SIDES}
        cells[(int(address.get("rowAddr")), int(address.get("colAddr")))] = {
            side: (element.get("type"), element.get("width"), element.get("color")) for side, element in sides.items()
        }
    return cells


@pytest.mark.parametrize(
    ("base", "edited", "row", "col"),
    [
        ("cell_border_2x3_base", "cell_border_2x3_corner_dash", 0, 0),
        ("cell_border_3x3_base", "cell_border_3x3_middle_dash", 1, 1),
        # (0,0)-(1,0) merged: the longer merged neighbour on the left keeps its line
        ("cell_border_vmerge_base", "cell_border_vmerge_neighbor_dash", 0, 1),
        # the merged cell itself: both cells along its right side take the line
        ("cell_border_vmerge_base", "cell_border_vmerge_self_dash", 0, 0),
    ],
)
def test_the_borders_are_the_ones_hancom_saves(base: str, edited: str, row: int, col: int) -> None:
    """Hancom gave one cell of each saved table a red dashed cell border; the same call here matches it."""
    doc = HwpxDocument.open((FIXTURES / f"{base}.hwpx").read_bytes())
    table = next(table for paragraph in doc.paragraphs for table in paragraph.tables)

    table.set_cell_borders(row, col, color="#FF0000", line_type="DASH")

    assert _sides_by_cell(doc) == _sides_by_cell(HwpxDocument.open((FIXTURES / f"{edited}.hwpx").read_bytes()))
