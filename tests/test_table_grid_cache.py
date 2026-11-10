"""The table keeps its cell grid between coordinate reads and rebuilds it when the table changes."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.table import HwpxOxmlTable

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _table(rows: int = 4, cols: int = 4) -> HwpxOxmlTable:
    document = HwpxDocument.new()
    table = document.add_table(rows, cols)
    for position in table.iter_grid():
        position.cell.text = f"r{position.row}c{position.column}"
    return table


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = HwpxOxmlTable._compute_cell_grid

    def counting(self: HwpxOxmlTable):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(HwpxOxmlTable, "_compute_cell_grid", counting)
    return calls


def test_coordinate_reads_build_the_grid_once(builds: list[int]) -> None:
    table = _table()  # builds the grid to fill the cells

    texts = [table.cell(row, col).text for row in range(4) for col in range(4)]
    for row in range(4):
        for col in range(4):
            table.set_cell_text(row, col, f"new {row},{col}")
    list(table.iter_grid())
    table.get_cell_map()

    assert texts[5] == "r1c1"
    assert table.cell(3, 3).text == "new 3,3"
    assert len(builds) == 1


def test_merge_and_split_rebuild_the_grid() -> None:
    table = _table()
    assert table.cell(1, 1).address == (1, 1)

    merged = table.merge_cells(0, 0, 1, 1)
    assert table.cell(1, 1).element is merged.element
    assert table.cell(1, 1).span == (2, 2)

    table.split_merged_cell(1, 1)
    assert table.cell(1, 1).address == (1, 1)
    assert table.cell(0, 0).span == (1, 1)


def test_row_and_column_edits_rebuild_the_grid() -> None:
    table = _table()
    assert table.cell(3, 3).text == "r3c3"

    table.insert_rows(0, 1)
    assert table.row_count == 5
    assert table.cell(4, 3).text == "r3c3"

    table.delete_columns(0)
    assert table.cell(4, 2).text == "r3c3"
    with pytest.raises(IndexError):
        table.cell(4, 3)


def test_edit_through_another_wrapper_of_the_same_table_is_seen() -> None:
    table = _table()
    assert table.cell(0, 1).address == (0, 1)

    other = HwpxOxmlTable(table.element, table.paragraph)
    merged = other.merge_cells(0, 0, 0, 1)

    assert table.cell(0, 1).element is merged.element
    assert [position.anchor for position in table.iter_grid()][:2] == [(0, 0), (0, 0)]


def test_raw_xml_edits_are_seen() -> None:
    table = _table()
    first_row = table.element.findall(f"{_HP}tr")[0]
    first, second = first_row.findall(f"{_HP}tc")[:2]
    assert table.cell(0, 1).element is second

    # the first cell grows over the second, which is taken out, as a merge saved by Hancom looks
    first.find(f"{_HP}cellSpan").set("colSpan", "2")
    first_row.remove(second)
    assert table.cell(0, 1).element is first
    assert table.cell(0, 0).span == (1, 2)

    # and back
    first.find(f"{_HP}cellSpan").set("colSpan", "1")
    first_row.insert(1, second)
    assert table.cell(0, 1).element is second

    # a cell that moves to another address
    second.find(f"{_HP}cellAddr").set("colAddr", "0")
    with pytest.raises(ValueError, match="overlapping"):
        table.cell(0, 1)
    second.find(f"{_HP}cellAddr").set("colAddr", "1")
    assert table.cell(0, 1).element is second


def test_text_in_a_zero_sized_covered_cell_is_seen() -> None:
    table = _table()
    first_row = table.element.findall(f"{_HP}tr")[0]
    first, second = first_row.findall(f"{_HP}tc")[:2]
    table.cell(0, 1).text = ""
    first.find(f"{_HP}cellSpan").set("colSpan", "2")
    second.find(f"{_HP}cellSz").set("width", "0")
    second.find(f"{_HP}cellSz").set("height", "0")

    # an empty zero-sized cell under a merged one is a placeholder: the merged cell answers
    assert table.cell(0, 1).element is first

    # with text it is a real cell again, and the two overlap
    second.find(f".//{_HP}t").text = "x"
    with pytest.raises(ValueError, match="overlapping"):
        table.cell(0, 1)
