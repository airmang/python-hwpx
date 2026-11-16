# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B2 게이트 — `doc.tables`.

표를 **만드는** 것은 루트에 남았다(`doc.add_table`). 만든 다음에 하는 일들이
이 네임스페이스다.
"""

from __future__ import annotations

import inspect

import pytest

from hwpx import model
from hwpx.document import HwpxDocument


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


# --------------------------------------------------------------------------
# 게이트 ③ merge_cells 반환 주석에서 Any 가 사라졌다


def test_merge_cells_is_annotated_as_a_table_cell() -> None:
    """5.x 는 런타임에 셀을 돌려주면서 타입만 ``Any`` 라고 말했다."""

    from hwpx._document.ns.tables import TablesNamespace

    annotation = str(inspect.signature(TablesNamespace.merge_cells).return_annotation)
    assert "TableCell" in annotation
    assert "Any" not in annotation


def test_merge_cells_returns_the_surviving_cell(document: HwpxDocument) -> None:
    table = document.add_table(2, 2)
    cell = document.tables.merge_cells(table, "A1:B1")
    assert isinstance(cell, model.TableCell)
    assert cell.span == (1, 2)


def test_the_removed_root_name_points_at_doc_tables(document: HwpxDocument) -> None:
    from hwpx.errors import HwpxAttributeError

    table = document.add_table(2, 2)
    with pytest.raises(HwpxAttributeError) as excinfo:
        document.merge_table_cells(table, "A1:B1")  # type: ignore[attr-defined]
    assert "doc.tables.merge_cells" in str(excinfo.value)
    assert isinstance(document.tables.merge_cells(table, "A1:B1"), model.TableCell)


# --------------------------------------------------------------------------
# 탐색·매핑·채움


def test_map_reports_every_table_in_document_order(document: HwpxDocument) -> None:
    document.add_table(2, 2)
    document.add_table(3, 1)
    mapped = document.tables.map()["tables"]
    assert [(entry["rows"], entry["cols"]) for entry in mapped] == [(2, 2), (3, 1)]
    assert [entry["table_index"] for entry in mapped] == [0, 1]


def test_all_and_len_agree_with_the_map(document: HwpxDocument) -> None:
    document.add_table(2, 2)
    document.add_table(3, 1)
    assert len(document.tables) == 2
    assert len(document.tables.all) == 2
    assert all(isinstance(table, model.Table) for table in document.tables)


def test_tables_index_and_slice_in_document_order(document: HwpxDocument) -> None:
    document.add_table(2, 2)
    document.add_table(3, 1)
    document.add_table(1, 4)
    shapes = [(t.row_count, t.column_count) for t in document.tables]
    assert shapes == [(2, 2), (3, 1), (1, 4)]
    assert (document.tables[0].row_count, document.tables[0].column_count) == (2, 2)
    assert (document.tables[-1].row_count, document.tables[-1].column_count) == (1, 4)
    assert [(t.row_count, t.column_count) for t in document.tables[1:]] == [(3, 1), (1, 4)]
    assert all(isinstance(table, model.Table) for table in document.tables[:2])
    with pytest.raises(IndexError):
        document.tables[3]


def test_an_indexed_table_edits_the_document(document: HwpxDocument) -> None:
    document.add_table(2, 2)
    document.tables[0].set_cell_text(0, 0, "첫 칸")
    reopened = HwpxDocument.open(document.to_bytes())
    assert reopened.tables[0].cell(0, 0).text == "첫 칸"


def test_the_removed_lookup_names_point_at_their_new_place(document: HwpxDocument) -> None:
    from hwpx.errors import HwpxAttributeError

    document.add_table(1, 1)
    for name, target, moving in [
        ("get_table_map", "doc.tables.map", False),
        ("find_cell_by_label", "from hwpx_automation.forms import find_cell_by_label", True),
    ]:
        with pytest.raises(HwpxAttributeError) as excinfo:
            getattr(document, name)
        assert target in str(excinfo.value)
        assert excinfo.value.context["movingToAutomation"] is moving
