# SPDX-License-Identifier: Apache-2.0
"""resolve_slot_metrics reads what it measures more than once only once (issue 695).

A row stored shorter than one line grows with its text, so measuring one of its
cells measures every cell of the row; each of those measures used to read the
whole table's column grid again, so measuring a whole table grew with the square
of its rows. One call now reads the grid once and each cell's settings once, and
gives what it gave before.
"""
from __future__ import annotations

import importlib
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.oxml.table_sizes import grid_widths_of

# ``hwpx.form_fit.measure`` the attribute is the measure() function; the module is read by its name.
slot_measure = importlib.import_module("hwpx.form_fit.measure")

_HP_URI = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _growing_table(rows: int, columns: int = 6):
    document = HwpxDocument.new()
    table = document.add_table(rows, columns)
    for row in range(rows):
        for column in range(columns):
            # Every third cell wraps, so the rows are not all one line tall.
            value = f"칸 {row}-{column} 합성 값" + (" 길게 이어지는 합성 문장" * 6 if (row + column) % 3 == 0 else "")
            table.cell(row, column).text = value
    return document, table


def _counting(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    calls: list[int] = []
    original = getattr(slot_measure, name)

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(slot_measure, name, counted)
    return calls


def test_a_growing_row_is_measured_reading_the_table_grid_once(monkeypatch: pytest.MonkeyPatch) -> None:
    document, table = _growing_table(40)
    cell = table.cell(20, 3)
    top, bottom = cell.margins.top, cell.margins.bottom
    assert float(cell.height) - top - bottom < 1000, "the row must grow with its text for this test"

    grids = _counting(monkeypatch, "grid_widths_of")
    styles = _counting(monkeypatch, "_cell_text_style")
    slot = slot_measure.resolve_slot_metrics(cell, document, safety=1.0)

    assert slot.available_height is not None and slot.available_height > 0
    # Once for the table, not once for each of the row's six cells and again for the cell asked for.
    assert len(grids) == 1
    # Each cell of the row once: the cell asked for is not read a second time for its row's height.
    assert len(styles) == 6


@pytest.mark.parametrize(
    ("max_lines", "font_pt", "safety"),
    [(1, None, 1.0), (1, None, slot_measure.DEFAULT_SAFETY), (3, 8.0, 0.9), (2, 11.0, 1.0)],
)
def test_a_growing_row_measures_as_its_cells_measured_alone(max_lines, font_pt, safety) -> None:
    document, table = _growing_table(8, 4)

    for row in range(8):
        for column in range(4):
            cell = table.cell(row, column)
            margins = cell.margins
            # Every read made afresh, nothing shared between the measures.
            alone = replace(
                slot_measure._cell_slot(cell, document, max_lines=max_lines, font_pt=font_pt, safety=safety),
                available_height=slot_measure._auto_grow_row_height(cell, document) - margins.top - margins.bottom,
            )
            assert slot_measure.resolve_slot_metrics(
                cell, document, max_lines=max_lines, font_pt=font_pt, safety=safety
            ) == alone


def test_an_edit_between_two_calls_is_read_by_the_second() -> None:
    document, table = _growing_table(3, 3)
    cell = table.cell(1, 1)
    first = slot_measure.resolve_slot_metrics(cell, document, safety=1.0)

    table.cell(1, 2).text = "다른 칸을 여러 줄로 늘리는 합성 문장" * 8
    second = slot_measure.resolve_slot_metrics(cell, document, safety=1.0)

    assert second.available_height is not None and first.available_height is not None
    assert second.available_height > first.available_height


_GRID_TABLE = f"""<hp:tbl xmlns:hp="{_HP_URI}" cellSpacing="10">
  <hp:tr>
    <hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>
      <hp:cellSz width="1000" height="500"/></hp:tc>
    <hp:tc><!-- a comment among the children --><hp:cellAddr colAddr="1" rowAddr="0"/>
      <hp:cellSpan colSpan="2" rowSpan="1"/><hp:cellSz width="3000" height="500"/>
      <hp:cellSz width="9999" height="500"/></hp:tc>
  </hp:tr>
  <!-- a comment among the rows -->
  <hp:tr>
    <hp:tc><hp:cellAddr colAddr="0" rowAddr="1"/><hp:cellSz width="1200" height="500"/></hp:tc>
    <hp:tc><hp:cellAddr colAddr="1" rowAddr="1"/><hp:cellSz width="1000" height="500"/></hp:tc>
    <hp:tc><hp:cellAddr colAddr="2" rowAddr="1"/><hp:cellSz width="1000" height="500"/></hp:tc>
  </hp:tr>
</hp:tbl>"""


@pytest.mark.parametrize("parse", [ET.fromstring, etree.fromstring], ids=["stdlib", "lxml"])
def test_the_grid_widths_read_each_cell_once_as_before(parse) -> None:
    table = parse(_GRID_TABLE)
    cells = [tc for tr in table.findall(f"{{{_HP_URI}}}tr") for tc in tr.findall(f"{{{_HP_URI}}}tc")]

    widths = grid_widths_of(table)

    # The first column is as wide as its widest cell (1200), the merged cell keeps its own width and the
    # last cell of the second row reaches to the merged cell's end; the first hp:cellSz of a cell counts.
    assert [widths[tc] for tc in cells] == [1200, 3000, 1200, 1000, 1990]


@pytest.mark.parametrize("parse", [ET.fromstring, etree.fromstring], ids=["stdlib", "lxml"])
def test_the_grid_widths_of_a_cell_without_an_address_or_size(parse) -> None:
    no_address = parse(_GRID_TABLE.replace('<hp:cellAddr colAddr="2" rowAddr="1"/>', ""))
    assert grid_widths_of(no_address) == {}

    no_size = parse(_GRID_TABLE.replace('<hp:cellSz width="1200" height="500"/>', ""))
    with pytest.raises(AttributeError):
        grid_widths_of(no_size)
