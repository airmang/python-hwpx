# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B2 게이트 — `doc.tables`.

표를 **만드는** 것은 루트에 남았다(`doc.add_table`). 만든 다음에 하는 일들이
이 네임스페이스다.
"""

from __future__ import annotations

import inspect
import warnings

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


def test_the_moved_root_name_still_answers_with_a_warning(document: HwpxDocument) -> None:
    table = document.add_table(2, 2)
    with pytest.warns(DeprecationWarning) as record:
        cell = document.merge_table_cells(table, "A1:B1")
    assert "doc.tables.merge_cells" in str(record[0].message)
    assert isinstance(cell, model.TableCell)


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


def test_find_cell_by_label_locates_the_neighbour(document: HwpxDocument) -> None:
    table = document.add_table(1, 2)
    table.set_cell_text(0, 0, "이름")
    found = document.tables.find_cell_by_label("이름")
    assert found["count"] == 1
    match = found["matches"][0]
    assert match["label_cell"]["col"] == 0
    assert match["target_cell"]["col"] == 1


def test_fill_by_path_writes_through_the_label_path(document: HwpxDocument) -> None:
    table = document.add_table(1, 2)
    table.set_cell_text(0, 0, "이름")
    # 경로 문법: ``라벨>방향`` — 방향이 없으면 채우지 않고 이유를 보고한다.
    result = document.tables.fill_by_path({"이름>right": "홍길동"})
    assert result["applied_count"] == 1, result
    assert table.cell(0, 1).text == "홍길동"

    missing_direction = document.tables.fill_by_path({"이름": "값"})
    assert missing_direction["applied_count"] == 0
    assert "direction" in missing_direction["failed"][0]["reason"]


def test_an_empty_mapping_is_a_no_op(document: HwpxDocument) -> None:
    result = document.tables.fill_by_path({})
    assert result["applied_count"] == 0 and result["failed_count"] == 0


def test_the_moved_lookup_names_still_answer(document: HwpxDocument) -> None:
    document.add_table(1, 1)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert document.get_table_map() == document.tables.map()
        assert document.find_cell_by_label("x") == document.tables.find_cell_by_label("x")
    assert len([w for w in caught if issubclass(w.category, DeprecationWarning)]) == 2
