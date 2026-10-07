"""``insert_row_by_clone`` inserts above a row (``side: "above"``) and with empty cells (``blank``).

``tests/fixtures/hancom_saved/table_insert_row_*`` are 3x3 tables made by Hangul (``*_base``) and the same
tables after Hangul inserted rows below or above a cell of the row named in the file. Hangul's rules:

- A new row is as high as the row it is inserted next to (its stored height).
- Each new cell takes the border fill, paragraph shape and character shape of the cell of the same column
  in that row, a cell merged across columns there included, and holds one empty paragraph.
- A cell merged across the new rows grows its rowSpan over them (its stored height kept), and next to a
  merged cell that ends (above the row: starts) at the row each new row gets a cell of its own.

Hangul also stores the table's laid-out height (``hp:sz``) anew; python-hwpx leaves it as it was, and
Hangul lays the table out again when it opens it. Cell zones move with their rows.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.table_patch import TableStructureError, _insert_row_by_clone, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _document(merge: str | None = None) -> bytes:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"
    if merge:
        table.merge_cells(merge)
    return document.to_bytes()


def _cells(data: bytes) -> list[list[tuple[int, int, int, int, str]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        table = next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))
    return [
        [
            (
                int(tc.find(HP + "cellAddr").get("rowAddr")),
                int(tc.find(HP + "cellAddr").get("colAddr")),
                int(tc.find(HP + "cellSpan").get("rowSpan")),
                int(tc.find(HP + "cellSpan").get("colSpan")),
                "".join(t.text or "" for t in tc.iter(HP + "t")),
            )
            for tc in tr.findall(HP + "tc")
        ]
        for tr in table.findall(HP + "tr")
    ]


def _insert(data: bytes, ref_row: int, count: int = 1, **options) -> bytes:
    op = {"op": "insert_row_by_clone", "table_index": 0, "ref_row": ref_row, "count": count, **options}
    result = apply_table_ops(data, [op])
    assert result.ok, result.skipped
    return result.data


def _table(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))


def _shapes(data: bytes) -> list[list[tuple]]:
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


def _saved(name: str) -> bytes:
    return (FIXTURES / f"table_insert_row_{name}.hwpx").read_bytes()


@pytest.mark.parametrize(
    ("base", "inserted", "ref_row", "count", "side"),
    [
        ("base", "below_count1", 1, 1, "below"),
        ("base", "above_count1", 1, 1, "above"),
        ("base", "below_count3", 1, 3, "below"),
        ("tall_row1_base", "tall_row1_below", 1, 1, "below"),
        ("tall_row1_base", "tall_row1_above", 1, 1, "above"),
        ("tall_row1_base", "tall_row1_from21_above", 2, 1, "above"),
        ("vmerge_c1r01_base", "vmerge_c1r01_from00_below", 0, 1, "below"),
        ("vmerge_c1r01_base", "vmerge_c1r01_from10_below", 1, 1, "below"),
        ("vmerge_c1r01_base", "vmerge_c1r01_from10_above", 1, 1, "above"),
        ("vmerge_c1r01_base", "vmerge_c1r01_from20_above", 2, 1, "above"),
        ("vmerge_c1r01_base", "vmerge_c1r01_from00_above", 0, 1, "above"),
        ("hmerge_r1c01_base", "hmerge_r1c01_from12_below", 1, 1, "below"),
        ("hmerge_r1c01_base", "hmerge_r1c01_from12_above", 1, 1, "above"),
        ("formats_row1_base", "formats_row1_below", 1, 1, "below"),
        ("formats_row1_base", "formats_row1_above", 1, 1, "above"),
    ],
)
def test_blank_rows_are_the_ones_hancom_inserts(base: str, inserted: str, ref_row: int, count: int, side: str) -> None:
    data = _insert(_saved(base), ref_row, count, side=side, blank=True)

    assert _shapes(data) == _shapes(_saved(inserted))
    assert _table(data).get("rowCnt") == _table(_saved(inserted)).get("rowCnt")
    assert _table(data).find(HP + "sz").get("width") == _table(_saved(inserted)).find(HP + "sz").get("width")
    assert _table(data).find(HP + "sz").get("height") == _table(_saved(base)).find(HP + "sz").get("height")


def test_above_a_row_its_clone_comes_first() -> None:
    rows = _cells(_insert(_document(), 1, side="above"))

    assert [[cell[4] for cell in row] for row in rows] == [
        ["r0c0", "r0c1", "r0c2"], ["r1c0", "r1c1", "r1c2"], ["r1c0", "r1c1", "r1c2"], ["r2c0", "r2c1", "r2c2"],
    ]
    assert [[cell[0] for cell in row] for row in rows] == [[0] * 3, [1] * 3, [2] * 3, [3] * 3]


def test_blank_rows_hold_empty_cells() -> None:
    rows = _cells(_insert(_document(), 0, count=2, blank=True))

    assert [[cell[4] for cell in row] for row in rows[1:3]] == [["", "", ""], ["", "", ""]]
    assert rows[3][0][:2] == (3, 0)


def test_above_a_row_a_cell_merged_into_it_from_above_grows() -> None:
    rows = _cells(_insert(_document("B1:B2"), 1, side="above"))

    assert rows[0][1][:4] == (0, 1, 3, 1)
    assert [cell[1] for cell in rows[1]] == [0, 2]
    assert [cell[1] for cell in rows[2]] == [0, 2]


def test_above_a_row_a_merged_cell_starting_there_gets_an_empty_cell_above_it() -> None:
    rows = _cells(_insert(_document("B2:B3"), 1, side="above"))

    assert [cell[1:5] for cell in rows[1]] == [(0, 1, 1, "r1c0"), (1, 1, 1, ""), (2, 1, 1, "r1c2")]
    assert rows[2][1][:4] == (2, 1, 2, 1)


def _bare_table(zones: str) -> str:
    rows = "".join(
        "<hp:tr>" + "".join(
            f'<hp:tc borderFillIDRef="3"><hp:subList><hp:p id="{10 * row + col + 1}"><hp:run charPrIDRef="0">'
            f"<hp:t>{row}{col}</hp:t></hp:run></hp:p></hp:subList>"
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="1000" height="500"/></hp:tc>'
            for col in range(2)
        ) + "</hp:tr>"
        for row in range(3)
    )
    return f'<hp:tbl rowCnt="3" colCnt="2"><hp:sz width="2000" height="1500"/>{zones}{rows}</hp:tbl>'


def test_cell_zones_move_with_their_rows() -> None:
    zones = (
        "<hp:cellzoneList>"
        '<hp:cellzone startRowAddr="0" startColAddr="0" endRowAddr="0" endColAddr="1" borderFillIDRef="4"/>'
        '<hp:cellzone startRowAddr="0" startColAddr="0" endRowAddr="2" endColAddr="0" borderFillIDRef="5"/>'
        '<hp:cellzone startRowAddr="2" startColAddr="1" endRowAddr="2" endColAddr="1" borderFillIDRef="6"/>'
        "</hp:cellzoneList>"
    )

    below = _insert_row_by_clone(_bare_table(zones), 0)
    above = _insert_row_by_clone(_bare_table(zones), 0, side="above")

    pattern = r'startRowAddr="(\d+)" startColAddr="\d+" endRowAddr="(\d+)"'
    assert re.findall(pattern, below) == [("0", "0"), ("0", "3"), ("3", "3")]
    assert re.findall(pattern, above) == [("1", "1"), ("1", "3"), ("3", "3")]


def test_a_side_other_than_above_or_below_is_refused() -> None:
    with pytest.raises(TableStructureError, match="side"):
        _insert_row_by_clone(_bare_table(""), 0, side="left")
