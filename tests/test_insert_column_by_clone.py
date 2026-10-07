"""``insert_column_by_clone`` inserts grid columns the way Hancom's column insertion does.

``tests/fixtures/hancom_saved/table_insert_column_*`` are 3x3 tables made by Hangul (``*_base``) and the
same tables after Hangul inserted columns right (``side0_count1``: left) of a cell of column 1 (the other
files). Hangul's rules:

- A new column is as wide as the column it is inserted right of, and the table grows by it, past the
  text width if need be.
- Each new cell takes the border fill, paragraph shape and character shape of the cell of the same row
  in that column, and holds one empty paragraph.
- A cell merged across the new columns grows its colSpan over them (Hangul leaves its stored width as it
  was and draws it by the grid), right of a cell merged from the left that ends at the column each new
  column gets a cell of its own, and a cell merged down the column is cloned with its rows.

``blank=True`` gives Hangul's empty cells; by default the new cells keep the text of the cells they
clone, as ``insert_row_by_clone`` does.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.table_patch import TableStructureError, _insert_column_by_clone, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _table(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    return next(root.iter(HP + "tbl"))


def _cells(data: bytes) -> list[list[tuple]]:
    """Each row's cells as (row, col, rowSpan, colSpan, width, height, border fill, paragraph shape,
    character shape of the first paragraph (0 without a run), text)."""
    rows = []
    for tr in _table(data).findall(HP + "tr"):
        cells = []
        for tc in tr.findall(HP + "tc"):
            addr, span, size = tc.find(HP + "cellAddr"), tc.find(HP + "cellSpan"), tc.find(HP + "cellSz")
            paragraph = tc.find(HP + "subList").find(HP + "p")
            run = paragraph.find(HP + "run")
            cells.append((
                int(addr.get("rowAddr")), int(addr.get("colAddr")),
                int(span.get("rowSpan")), int(span.get("colSpan")),
                int(size.get("width")), int(size.get("height")),
                tc.get("borderFillIDRef"), paragraph.get("paraPrIDRef"),
                run.get("charPrIDRef") if run is not None else "0",
                "".join(t.text or "" for t in tc.iter(HP + "t")),
            ))
        rows.append(cells)
    return rows


def _insert(data: bytes, ref_col: int, count: int = 1, **options) -> bytes:
    op = {"op": "insert_column_by_clone", "table_index": 0, "ref_col": ref_col, "count": count, **options}
    result = apply_table_ops(data, [op])
    assert result.ok, result.skipped
    return result.data


def _saved(name: str) -> bytes:
    return (FIXTURES / f"table_insert_column_{name}.hwpx").read_bytes()


@pytest.mark.parametrize(
    ("base", "inserted", "count", "side"),
    [
        ("base", "side1_count1", 1, "right"),
        ("base", "side1_count3", 3, "right"),
        ("base", "side0_count1", 1, "left"),
        ("wide_col1_all_base", "wide_col1_all_side1", 1, "right"),
        ("merge_r0c01_base", "merge_r0c01_side1", 1, "right"),
        ("merge_r0c12_base", "merge_r0c12_side1", 1, "right"),
        ("vmerge_c1r01_base", "vmerge_c1r01_side1", 1, "right"),
        ("formats_base", "formats_side1", 1, "right"),
        ("formats2_base", "formats2_side1", 1, "right"),
        ("full_width0_base", "full_width0_side1", 1, "right"),
    ],
)
def test_blank_columns_are_the_ones_hancom_inserts(base: str, inserted: str, count: int, side: str) -> None:
    data = _insert(_saved(base), 1, count, side=side, blank=True)

    mine, hancom = _cells(data), _cells(_saved(inserted))
    assert _table(data).get("colCnt") == _table(_saved(inserted)).get("colCnt")
    assert _table(data).find(HP + "sz").attrib == _table(_saved(inserted)).find(HP + "sz").attrib
    without_spanned_widths = [
        [cell[:4] + (None if cell[3] > 1 else cell[4],) + cell[5:] for cell in row] for row in mine
    ]
    assert without_spanned_widths == [
        [cell[:4] + (None if cell[3] > 1 else cell[4],) + cell[5:] for cell in row] for row in hancom
    ]


def test_a_cell_merged_across_the_new_column_is_written_as_wide_as_its_columns() -> None:
    data = _insert(_saved("merge_r0c12_base"), 1, blank=True)

    merged = _cells(data)[0][1]
    assert merged[3] == 3
    assert merged[4] == 3 * 13984  # Hangul keeps the old 27968 and draws the cell by the grid
    assert _cells(_saved("merge_r0c12_side1"))[0][1][4] == 2 * 13984


def test_by_default_the_new_cells_keep_the_text_they_clone() -> None:
    data = _insert(_saved("formats_base"), 1)

    for row, cells in enumerate(_cells(data)):
        assert [cell[9] for cell in cells] == [f"r{row}c0", f"r{row}c1", f"r{row}c1", f"r{row}c2"]
    assert [cell[6:9] for cell in _cells(data)[1][1:3]] == [("4", "1", "1"), ("4", "1", "1")]


def test_left_of_a_column_merged_cells_follow_the_same_rules() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=4)
    for row in range(2):
        for col in range(4):
            table.cell(row, col).text = f"r{row}c{col}"
    table.merge_cells("A1:B1")
    table.merge_cells("C1:D1")

    data = _insert(document.to_bytes(), 1, side="left")
    rows = _cells(data)
    assert [cell[1:4] + (cell[9],) for cell in rows[0]] == [(0, 1, 3, "r0c0r0c1"), (3, 1, 2, "r0c2r0c3")]
    assert [cell[1] for cell in rows[1]] == [0, 1, 2, 3, 4]
    assert rows[1][1][9] == rows[1][2][9] == "r1c1"

    data = _insert(document.to_bytes(), 2, side="left")
    rows = _cells(data)
    assert [cell[1:4] + (cell[9],) for cell in rows[0]] == [
        (0, 1, 2, "r0c0r0c1"), (2, 1, 1, ""), (3, 1, 2, "r0c2r0c3"),
    ]
    assert rows[0][1][4] == rows[1][2][4]


def test_new_paragraphs_take_ids_unused_in_the_document() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "a"

    data = _insert(document.to_bytes(), 0, count=2)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    ids = re.findall(r'<hp:p\b[^>]*\bid="(\d+)"', section)
    assert len(ids) == len(set(ids))


def _bare_table(zones: str = "") -> str:
    rows = "".join(
        "<hp:tr>" + "".join(
            f'<hp:tc borderFillIDRef="3"><hp:subList><hp:p id="{10 * row + col + 1}"><hp:run charPrIDRef="0">'
            f"<hp:t>{row}{col}</hp:t></hp:run></hp:p></hp:subList>"
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="1000" height="500"/></hp:tc>'
            for col in range(3)
        ) + "</hp:tr>"
        for row in range(2)
    )
    return f'<hp:tbl rowCnt="2" colCnt="3"><hp:sz width="3000" height="1000"/>{zones}{rows}</hp:tbl>'


def test_cell_zones_move_with_their_columns() -> None:
    zones = (
        "<hp:cellzoneList>"
        '<hp:cellzone startRowAddr="0" startColAddr="0" endRowAddr="1" endColAddr="0" borderFillIDRef="4"/>'
        '<hp:cellzone startRowAddr="0" startColAddr="0" endRowAddr="0" endColAddr="2" borderFillIDRef="5"/>'
        '<hp:cellzone startRowAddr="1" startColAddr="2" endRowAddr="1" endColAddr="2" borderFillIDRef="6"/>'
        "</hp:cellzoneList>"
    )

    table = _insert_column_by_clone(_bare_table(zones), 1)

    found = re.findall(r'startColAddr="(\d+)" endRowAddr="\d+" endColAddr="(\d+)"', table)
    assert found == [("0", "0"), ("0", "3"), ("3", "3")]
    assert 'colCnt="4"' in table and '<hp:sz width="4000"' in table

    table = _insert_column_by_clone(_bare_table(zones), 0, side="left")
    found = re.findall(r'startColAddr="(\d+)" endRowAddr="\d+" endColAddr="(\d+)"', table)
    assert found == [("1", "1"), ("1", "3"), ("3", "3")]


def test_out_of_range_columns_and_nested_tables_are_refused() -> None:
    with pytest.raises(TableStructureError, match="out of range"):
        _insert_column_by_clone(_bare_table(), 3)
    with pytest.raises(TableStructureError, match="side"):
        _insert_column_by_clone(_bare_table(), 0, side="above")
    nested = _bare_table().replace("<hp:t>00</hp:t>", '<hp:t>00</hp:t></hp:run><hp:run><hp:tbl rowCnt="1"/>')
    with pytest.raises(TableStructureError, match="nested"):
        _insert_column_by_clone(nested, 0)
    result = apply_table_ops(_saved("base"), [{"op": "insert_column_by_clone", "table_index": 0, "ref_col": 3}])
    assert not result.ok and "out of range" in result.skipped[0].reason
