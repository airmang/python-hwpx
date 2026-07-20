"""Characterization tests for hwpx.tools.fuzz.catalog.derive_expected.

derive_expected had zero direct test coverage (only indirect, through the
fuzz runner pipeline) ahead of a complexity refactor (S-088 P3). These tests
pin its behavior for every operation branch so the decomposition into
per-operation handlers can be verified as behavior-preserving.
"""

from __future__ import annotations

from hwpx.tools.fuzz.catalog import derive_expected


def test_empty_operations():
    result = derive_expected([])
    assert result == {
        "texts": [],
        "bodyTexts": [],
        "tableTexts": [],
        "table_count": 0,
        "catalog_operations": [],
    }


def test_build_document_paragraphs_and_table():
    ops = [
        {
            "op": "build_document",
            "paragraphs": ["첫 문단", "", "둘째 문단"],
            "table": {"header": ["A", "B"], "rows": [["1", "2"]]},
        }
    ]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["첫 문단", "둘째 문단"]
    assert result["tableTexts"] == ["A", "B", "1", "2"]
    assert result["table_count"] == 1
    assert result["catalog_operations"] == ["build_document"]


def test_build_document_without_table_is_skipped():
    ops = [{"op": "build_document", "paragraphs": ["텍스트"]}]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["텍스트"]
    assert result["tableTexts"] == []
    assert result["table_count"] == 0


def test_add_paragraph_and_add_styled_run():
    ops = [
        {"op": "add_paragraph", "text": "문단 텍스트"},
        {"op": "add_styled_run", "text": "스타일 텍스트"},
        {"op": "add_paragraph", "text": ""},
    ]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["문단 텍스트", "스타일 텍스트"]


def test_add_table_and_set_table_cell_text():
    ops = [
        {"op": "add_table", "cells": [["a", "b"], ["c", "d"]]},
        {"op": "set_table_cell_text", "table_index": 0, "row": 0, "col": 1, "text": "changed"},
    ]
    result = derive_expected(ops)
    assert result["tableTexts"] == ["a", "changed", "c", "d"]
    assert result["table_count"] == 1


def test_set_table_cell_text_out_of_bounds_is_ignored():
    ops = [
        {"op": "add_table", "cells": [["a"]]},
        {"op": "set_table_cell_text", "table_index": 5, "row": 0, "col": 0, "text": "x"},
        {"op": "set_table_cell_text", "table_index": 0, "row": 9, "col": 0, "text": "y"},
        {"op": "set_table_cell_text", "table_index": 0, "row": 0, "col": 9, "text": "z"},
    ]
    result = derive_expected(ops)
    assert result["tableTexts"] == ["a"]


def test_merge_table_cells_blanks_b1_and_redirects_writes_to_a1():
    ops = [
        {"op": "add_table", "cells": [["a", "b"], ["c", "d"]]},
        {"op": "merge_table_cells", "table_index": 0, "range": "A1:B1"},
    ]
    result = derive_expected(ops)
    # B1 is blanked by the merge.
    assert result["tableTexts"] == ["a", "c", "d"]

    # A subsequent write targeting the merged-away cell (0,1) redirects to (0,0).
    ops_with_write = ops + [
        {"op": "set_table_cell_text", "table_index": 0, "row": 0, "col": 1, "text": "redirected"}
    ]
    redirected = derive_expected(ops_with_write)
    assert redirected["tableTexts"] == ["redirected", "c", "d"]


def test_merge_table_cells_wrong_range_or_index_is_noop():
    ops = [
        {"op": "add_table", "cells": [["a", "b"]]},
        {"op": "merge_table_cells", "table_index": 0, "range": "A1:C1"},
        {"op": "merge_table_cells", "table_index": 9, "range": "A1:B1"},
    ]
    result = derive_expected(ops)
    assert result["tableTexts"] == ["a", "b"]


def test_replace_text_no_limit():
    ops = [
        {"op": "add_paragraph", "text": "가가가"},
        {"op": "replace_text", "search": "가", "replacement": "나"},
    ]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["나나나"]


def test_replace_text_with_limit():
    ops = [
        {"op": "add_paragraph", "text": "가가가"},
        {"op": "replace_text", "search": "가", "replacement": "나", "limit": 2},
    ]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["나나가"]


def test_replace_text_empty_search_is_noop():
    ops = [
        {"op": "add_paragraph", "text": "그대로"},
        {"op": "replace_text", "search": "", "replacement": "x"},
    ]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["그대로"]


def test_add_memo_appends_anchor_text():
    ops = [{"op": "add_memo", "anchor_text": "메모 앵커"}]
    result = derive_expected(ops)
    assert result["bodyTexts"] == ["메모 앵커"]


def test_unknown_op_is_ignored():
    ops = [{"op": "unknown_future_op", "text": "should not appear"}]
    result = derive_expected(ops)
    assert result["bodyTexts"] == []
    assert result["catalog_operations"] == ["unknown_future_op"]


def test_texts_combines_body_then_table_in_order():
    ops = [
        {"op": "add_paragraph", "text": "body"},
        {"op": "add_table", "cells": [["cell"]]},
    ]
    result = derive_expected(ops)
    assert result["texts"] == ["body", "cell"]


def test_catalog_operations_are_sorted_and_deduplicated():
    ops = [
        {"op": "add_memo", "anchor_text": "a"},
        {"op": "add_paragraph", "text": "b"},
        {"op": "add_memo", "anchor_text": "c"},
    ]
    result = derive_expected(ops)
    assert result["catalog_operations"] == ["add_memo", "add_paragraph"]
