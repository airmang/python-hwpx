"""``split_cell`` splits a table cell into rows and columns the way Hancom's cell split does.

``tests/fixtures/hancom_saved/table_split_cell_*`` are 3x3 tables made by Hangul (``*_base``) and the same
tables after Hangul split a cell (``c2``/``c3``: into columns, ``r2``/``r3``: into rows). Hangul's rules:

- Into columns the cell's width is shared out evenly, the last part taking what is left over. New grid
  lines go where the parts end, and every other cell keeps its width over the grid columns it now covers.
- Into rows the parts take the rows the cell covers when they divide evenly, else one row each and as many
  new rows after the cell's last as it lacks; the cells beside that row grow over the new rows.
- The content stays in the first part; the others hold one empty paragraph of the cell's format.

Hangul stores split row heights from the content: the first parts as high as their lines, the last what is
left of the cell (0 or less for a cell lower than its content), and it stores the table's laid-out height
anew. python-hwpx shares the cell's stored height out evenly, as Hangul's 'split row heights evenly' does
(``tall_row1_r2_distribute``), and leaves the table's height as it was; Hangul lays the cells out to their
content either way.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.table_patch import TableStructureError, _split_cell, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _saved(name: str) -> bytes:
    return (FIXTURES / f"table_split_cell_{name}.hwpx").read_bytes()


def _table(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "tbl"))


def _shapes(data: bytes, heights: bool = True) -> list[list[tuple]]:
    """Each row's cells as (row, col, rowSpan, colSpan, width, height, border fill, paragraph shape,
    character shape of the first paragraph (0 without a run), text); the height left out on request."""
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
                int(size.get("width")), int(size.get("height")) if heights else None,
                tc.get("borderFillIDRef"), paragraph.get("paraPrIDRef"),
                run.get("charPrIDRef") if run is not None else "0",
                "".join(t.text or "" for t in tc.iter(HP + "t")),
            ))
        rows.append(cells)
    return rows


def _split(data: bytes, row: int, col: int, **parts: int) -> bytes:
    result = apply_table_ops(data, [{"op": "split_cell", "table_index": 0, "row": row, "col": col, **parts}])
    assert result.ok, result.skipped
    return result.data


@pytest.mark.parametrize(
    ("base", "split", "row", "col", "parts"),
    [
        ("base", "c2", 1, 1, {"cols": 2}),
        ("base", "c3", 1, 1, {"cols": 3}),
        ("wide_col1_base", "wide_col1_c2", 1, 1, {"cols": 2}),
        ("merge_r0c12_base", "merge_r0c12_c2", 0, 1, {"cols": 2}),
        ("merge_r0c12_base", "merge_r0c12_c3", 0, 1, {"cols": 3}),
        ("format_base", "format_c2", 1, 1, {"cols": 2}),
        ("tall_row1_base", "tall_row1_r2_distribute", 1, 1, {"rows": 2}),
    ],
)
def test_splits_hancom_stores_alike_are_the_same(base: str, split: str, row: int, col: int, parts: dict) -> None:
    data = _split(_saved(base), row, col, **parts)

    assert _shapes(data) == _shapes(_saved(split))
    assert _table(data).get("colCnt") == _table(_saved(split)).get("colCnt")
    assert _table(data).get("rowCnt") == _table(_saved(split)).get("rowCnt")
    assert _table(data).find(HP + "sz").attrib == _table(_saved(split)).find(HP + "sz").attrib


@pytest.mark.parametrize(
    ("base", "split", "row", "col", "parts"),
    [
        ("base", "r2", 1, 1, {"rows": 2}),
        ("base", "r3", 1, 1, {"rows": 3}),
        ("base", "r2c2", 1, 1, {"rows": 2, "cols": 2}),
        ("vmerge_c1r01_base", "vmerge_c1r01_r2", 0, 1, {"rows": 2}),
        ("vmerge_c1r01_base", "vmerge_c1r01_r3", 0, 1, {"rows": 3}),
        ("format_base", "format_r2", 1, 1, {"rows": 2}),
    ],
)
def test_row_splits_match_hancom_but_for_the_heights(base: str, split: str, row: int, col: int, parts: dict) -> None:
    data = _split(_saved(base), row, col, **parts)

    assert _shapes(data, heights=False) == _shapes(_saved(split), heights=False)
    assert _table(data).get("rowCnt") == _table(_saved(split)).get("rowCnt")
    assert _table(data).get("colCnt") == _table(_saved(split)).get("colCnt")
    assert _table(data).find(HP + "sz").get("width") == _table(_saved(split)).find(HP + "sz").get("width")


@pytest.mark.parametrize(
    ("base", "row", "col", "rows", "expected"),
    [
        ("base", 1, 1, 2, [141, 141]),
        ("base", 1, 1, 3, [94, 94, 94]),
        ("vmerge_c1r01_base", 0, 1, 2, [282, 282]),
        ("tall_row1_base", 1, 1, 2, [1641, 1641]),
    ],
)
def test_row_parts_share_the_stored_height_evenly(base: str, row: int, col: int, rows: int, expected: list) -> None:
    data = _split(_saved(base), row, col, rows=rows)

    parts = [cell for line in _shapes(data) for cell in line if cell[1] == col and cell[0] >= row][:rows]
    assert [cell[5] for cell in parts] == expected
    assert _table(data).find(HP + "sz").get("height") == _table(_saved(base)).find(HP + "sz").get("height")


def test_cell_zones_keep_the_area_they_cover() -> None:
    table = (
        '<hp:tbl rowCnt="2" colCnt="2"><hp:sz width="2000" height="1000"/>'
        "<hp:cellzoneList>"
        '<hp:cellzone startRowAddr="0" startColAddr="1" endRowAddr="1" endColAddr="1" borderFillIDRef="4"/>'
        '<hp:cellzone startRowAddr="1" startColAddr="0" endRowAddr="1" endColAddr="0" borderFillIDRef="5"/>'
        "</hp:cellzoneList>"
        + "".join(
            "<hp:tr>" + "".join(
                f'<hp:tc borderFillIDRef="3"><hp:subList><hp:p id="{10 * row + col + 1}"><hp:run charPrIDRef="0">'
                f"<hp:t>{row}{col}</hp:t></hp:run></hp:p></hp:subList>"
                f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
                f'<hp:cellSz width="1000" height="500"/></hp:tc>'
                for col in range(2)
            ) + "</hp:tr>"
            for row in range(2)
        )
        + "</hp:tbl>"
    )

    split = _split_cell(table, 0, 1, rows=2, cols=2)

    zones = [
        tuple(int(value) for value in found)
        for found in __import__("re").findall(
            r'startRowAddr="(\d+)" startColAddr="(\d+)" endRowAddr="(\d+)" endColAddr="(\d+)"', split
        )
    ]
    assert zones == [(0, 1, 2, 2), (2, 0, 2, 0)]
    assert 'rowCnt="3"' in split and 'colCnt="3"' in split


def test_splits_hancom_does_not_make_are_refused() -> None:
    with pytest.raises(TableStructureError, match="2 or more"):
        _split_cell(_table_xml(), 0, 0)
    with pytest.raises(TableStructureError, match="1..63"):
        _split_cell(_table_xml(), 0, 0, cols=64)
    with pytest.raises(TableStructureError, match="no cell starts"):
        _split_cell(_table_xml(), 0, 5, cols=2)
    result = apply_table_ops(_saved("vmerge_c1r01_base"), [
        {"op": "split_cell", "table_index": 0, "row": 0, "col": 1, "rows": 2},
        {"op": "split_cell", "table_index": 0, "row": 2, "col": 0, "rows": 3},
    ])
    assert result.ok


def _table_xml() -> str:
    with zipfile.ZipFile(FIXTURES / "table_split_cell_base.hwpx") as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    start = section.index("<hp:tbl")
    return section[start:section.index("</hp:tbl>") + len("</hp:tbl>")]


@pytest.mark.parametrize("row,col", [(0, 2), (0, -1), (0, 3), (-1, 0), (3, 0)])
@pytest.mark.parametrize("parts", [{"rows": 2}, {"rows": 2, "cols": 2}])
def test_every_split_requires_an_exact_in_range_anchor(row: int, col: int, parts: dict) -> None:
    source = _saved("merge_r0c12_base")
    result = apply_table_ops(source, [
        {"op": "split_cell", "table_index": 0, "row": row, "col": col, **parts},
    ])

    assert not result.ok
    assert result.data == source
    assert "no cell starts" in str(result.skipped)
