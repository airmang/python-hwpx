# SPDX-License-Identifier: Apache-2.0
"""asks10d: a table's rows moved or copied (``table.move_rows``, ``table.copy_rows``)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _table(rows: int = 4, cols: int = 2):
    doc = HwpxDocument.new()
    table = doc.add_paragraph("표").add_table(rows, cols)
    for r in range(rows):
        for c in range(cols):
            table.cell(r, c).text = f"{r}{c}"
    return doc, table


def _texts(table) -> list[list[str]]:
    return [[cell.text for cell in row.cells] for row in table.rows]


def _addresses(table) -> list[list[str]]:
    return [[cell.element.find(f"{HP}cellAddr").get("rowAddr") for cell in row.cells] for row in table.rows]


def test_rows_move_in_front_of_a_row_and_are_numbered_again() -> None:
    doc, table = _table()
    with doc:
        ids = [p.get("id") for p in table.element.iter(f"{HP}p")]
        table.move_rows([2, 3], to=0)
        assert _texts(table) == [["20", "21"], ["30", "31"], ["00", "01"], ["10", "11"]]
        assert _addresses(table) == [["0", "0"], ["1", "1"], ["2", "2"], ["3", "3"]]
        assert sorted(p.get("id") for p in table.element.iter(f"{HP}p")) == sorted(ids)  # the cells themselves
        table.move_rows(0, to=4)
        assert _texts(table)[-1] == ["20", "21"] and table.element.get("rowCnt") == "4"
        table.move_rows(1, to=2)  # right after itself: in place
        assert _texts(table)[1] == ["00", "01"]
        again = HwpxDocument.open(doc.to_bytes())
        assert [[c.text for c in r.cells] for r in again.tables[0].rows] == _texts(table)


def test_rows_copy_with_fresh_ids_and_the_table_grows() -> None:
    doc, table = _table(2, 2)
    with doc:
        height = int(table.element.find(f"{HP}sz").get("height"))
        ids = {p.get("id") for p in table.element.iter(f"{HP}p")}
        table.copy_rows(1, to=0)
        assert _texts(table) == [["10", "11"], ["00", "01"], ["10", "11"]]
        assert table.element.get("rowCnt") == "3" and _addresses(table) == [["0", "0"], ["1", "1"], ["2", "2"]]
        new_ids = [p.get("id") for p in table.element.iter(f"{HP}p")]
        assert len(set(new_ids)) == len(new_ids) and ids < set(new_ids)
        twin = _table(2, 2)[1]
        twin.insert_rows(0, side="above")
        # the stored height follows insert_rows' rule (it grows by what the rows gained, unless the table was
        # saved shorter than its rows)
        assert table.element.find(f"{HP}sz").get("height") == twin.element.find(f"{HP}sz").get("height")
        assert int(table.element.find(f"{HP}sz").get("height")) >= height
        other = doc.add_paragraph("둘째 표").add_table(1, 2)
        other.copy_rows(0, to=1, source=table)
        assert _texts(other)[-1] == ["10", "11"]
        HwpxDocument.open(doc.to_bytes()).close()


def test_a_merged_cell_across_the_edge_is_refused_before_anything_changes() -> None:
    doc, table = _table(4, 2)
    with doc:
        table.merge_cells(1, 0, 2, 0)
        before = _texts(table)
        for call in (lambda: table.move_rows(1, to=4), lambda: table.move_rows([2, 3], to=0),
                     lambda: table.copy_rows(0, to=2), lambda: table.copy_rows([1, 2], to=2)):
            with pytest.raises(HwpxError) as caught:
                call()
            assert caught.value.code == "table-rows-merge-crossed"
        assert _texts(table) == before
        table.move_rows([1, 2], to=0)  # the merged cell's rows whole: fine
        assert table.element.find(f".//{HP}cellSpan[@rowSpan='2']") is not None


def test_bad_rows_columns_and_documents_are_refused() -> None:
    doc, table = _table(3, 2)
    with doc:
        for rows, to in (([0, 2], 1), (5, 0), ([], 0), (0, 9), (True, 0)):
            with pytest.raises(HwpxError) as caught:
                table.move_rows(rows, to=to)
            assert caught.value.code == "table-rows-invalid"
        narrow = doc.add_paragraph("한 칸 표").add_table(1, 1)
        with pytest.raises(HwpxError) as caught:
            narrow.copy_rows(0, to=0, source=table)
        assert caught.value.code == "table-columns-differ"
        with HwpxDocument.new() as other:
            foreign = other.add_paragraph("표").add_table(1, 2)
            with pytest.raises(HwpxError) as caught:
                table.copy_rows(0, to=0, source=foreign)
            assert caught.value.code == "table-rows-other-document"


def test_hancom_merged_table_rows_move_whole() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = HwpxDocument.open(HANCOM / "cell_border_vmerge_base.hwpx")
    with doc:
        table = [place.object for place in doc.text.iter_objects(kinds="table")][0]
        count = len(table.rows)
        table.copy_rows(range(count), to=count)  # every row, merges and all
        assert len(table.rows) == 2 * count
        assert _addresses(table) == [[str(i)] * len(row.cells) for i, row in enumerate(table.rows)]
        HwpxDocument.open(doc.to_bytes()).close()
