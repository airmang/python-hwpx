"""``insert_row_by_clone`` next to merged cells inserts rows the way Hancom does.

A 3x3 table with (0,0)-(1,0) merged vertically. Hancom's row insertion below row 0 grows the
merged cell to three rows and gives the new row cells only in the other columns; below row 1,
where the merged cell ends, the new row gets a cell in every column, the one under the merged
cell empty and one row high.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.table_patch import TableStructureError, _insert_row_by_clone, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _merged_table_document() -> bytes:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"
    table.merge_cells("A1:A2")
    return document.to_bytes()


def _cells(data: bytes) -> list[list[tuple[int, int, int, int, str]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    table = next(root.iter(HP + "tbl"))
    rows = []
    for tr in table.findall(HP + "tr"):
        rows.append([
            (
                int(tc.find(HP + "cellAddr").get("rowAddr")),
                int(tc.find(HP + "cellAddr").get("colAddr")),
                int(tc.find(HP + "cellSpan").get("rowSpan")),
                int(tc.find(HP + "cellSpan").get("colSpan")),
                "".join(t.text or "" for t in tc.iter(HP + "t")),
            )
            for tc in tr.findall(HP + "tc")
        ])
    return rows


def _insert(data: bytes, ref_row: int, count: int = 1) -> bytes:
    result = apply_table_ops(data, [{"op": "insert_row_by_clone", "table_index": 0, "ref_row": ref_row, "count": count}])
    assert result.ok, result.skipped
    return result.data


def test_inside_a_merged_cell_the_cell_grows_and_the_other_columns_are_cloned() -> None:
    data = _insert(_merged_table_document(), 0)

    rows = _cells(data)
    assert rows[0][0][:4] == (0, 0, 3, 1)
    assert [cell[1:] for cell in rows[1]] == [(1, 1, 1, "r0c1"), (2, 1, 1, "r0c2")]
    assert [cell[0] for cell in rows[1]] == [1, 1]
    assert [cell[:2] for cell in rows[2]] == [(2, 1), (2, 2)]
    assert [cell[:2] for cell in rows[3]] == [(3, 0), (3, 1), (3, 2)]


def test_below_a_merged_cell_the_new_row_gets_an_empty_cell_under_it() -> None:
    source = _merged_table_document()

    data = _insert(source, 1)

    rows = _cells(data)
    assert rows[0][0][:4] == (0, 0, 2, 1)
    assert rows[2] == [(2, 0, 1, 1, ""), (2, 1, 1, 1, "r1c1"), (2, 2, 1, 1, "r1c2")]
    assert [cell[:2] for cell in rows[3]] == [(3, 0), (3, 1), (3, 2)]


def test_the_empty_cell_keeps_the_merged_cell_format_and_takes_the_row_height() -> None:
    source = _merged_table_document()
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        table = next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))
    merged = table.find(HP + "tr").find(HP + "tc")
    neighbour = table.findall(HP + "tr")[1].find(HP + "tc")

    data = _insert(source, 1)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        new_table = next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))
    blank = new_table.findall(HP + "tr")[2].find(HP + "tc")
    assert blank.get("borderFillIDRef") == merged.get("borderFillIDRef")
    assert blank.find(HP + "cellSz").get("width") == merged.find(HP + "cellSz").get("width")
    assert blank.find(HP + "cellSz").get("height") == neighbour.find(HP + "cellSz").get("height")
    assert len(blank.find(HP + "subList").findall(HP + "p")) == 1
    assert blank.find(f".//{HP}linesegarray") is None


def test_the_empty_cell_holds_one_empty_paragraph_even_under_a_multi_paragraph_cell() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=2)
    table.merge_cells("A1:A2")
    table.cell(0, 0).set_text("첫째\n둘째", split_paragraphs=True)

    data = _insert(document.to_bytes(), 1)

    rows = _cells(data)
    assert rows[2][0] == (2, 0, 1, 1, "")
    assert rows[0][0][4] == "첫째둘째"


def test_several_new_rows_all_follow_the_same_rule() -> None:
    data = _insert(_merged_table_document(), 0, count=2)

    rows = _cells(data)
    assert rows[0][0][:3] == (0, 0, 4)
    assert [[cell[:2] for cell in row] for row in rows[1:3]] == [[(1, 1), (1, 2)], [(2, 1), (2, 2)]]
    assert len(rows) == 5


def test_a_row_covered_entirely_by_cells_running_on_is_refused() -> None:
    table = (
        '<hp:tbl rowCnt="2" colCnt="1"><hp:tr><hp:tc><hp:subList><hp:p id="1"><hp:run charPrIDRef="0">'
        '<hp:t>a</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="2"/><hp:cellSz width="100" height="200"/></hp:tc></hp:tr>'
        "<hp:tr></hp:tr></hp:tbl>"
    )

    with pytest.raises(TableStructureError, match="runs on below"):
        _insert_row_by_clone(table, 0)
