# SPDX-License-Identifier: Apache-2.0
"""A cell border edit also sets the shared edge of the neighbouring cells.

Each cell keeps its own four sides and both cells of a shared edge are drawn,
so Hancom's cell border command changes the neighbour's side of that edge too.
"""
from __future__ import annotations

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


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


def test_border_fill_without_lines_clears_the_shared_edges() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    no_lines = doc.styles.ensure_border_fill(active_borders=[])
    table.set_cell_border_fill(0, 0, no_lines)
    assert _side(doc, table, 0, 1, "leftBorder")[0] == "NONE"
    assert _side(doc, table, 1, 0, "topBorder")[0] == "NONE"
    reopened = HwpxDocument.open(doc.to_bytes())
    table2 = reopened.paragraphs[1].tables[0] if reopened.paragraphs[1].tables else None
    assert table2 is not None
    assert _side(reopened, table2, 0, 1, "leftBorder")[0] == "NONE"


def test_three_d_lines_are_written_with_hancom_names() -> None:
    doc = HwpxDocument.new()
    fill_id = doc.styles.ensure_border_fill(border_type="THICK_3D")
    fill = doc.oxml.headers[0].element.find(f".//{HH}borderFill[@id='{fill_id}']")
    assert {side.get("type") for side in fill if side.tag.endswith("Border")} <= {"THICK3D", "NONE"}
    assert "THICK3D" in {side.get("type") for side in fill if side.tag.endswith("Border")}
    table = doc.add_table(1, 2)
    table.set_cell_borders(0, 0, color="#000000", line_type="SLIM_3D")
    assert _side(doc, table, 0, 0, "leftBorder")[0] == "3D"
    for name in ("THICK3D", "THICKREV3D", "3D", "REV3D"):
        table.set_cell_borders(0, 1, color="#000000", line_type=name)
        assert _side(doc, table, 0, 1, "rightBorder")[0] == name


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
