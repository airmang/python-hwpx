# SPDX-License-Identifier: Apache-2.0
"""표 나누기(split_table)·붙이기(merge_table) -- cycle 6.12 트레인㊸ 갭⑤.

OWPML 스키마에 표 나누기/붙이기 전용 어휘는 없다(`hp:tbl`은 `pageBreak`/
`repeatHeader`/`rowCnt`/`colCnt`/`cellSpacing`/`borderFillIDRef`뿐,
`TableType`, ``ParaList XML schema.xml:2008``) -- 순수 구조 편집이라
기존 ``_delete_rows``/``_insert_block_by_clone``과 같은 fail-closed
원칙(병합 셀이 경계를 걸치면 거부)을 그대로 따른다. 표 뒤집기("표
뒤집기")는 이번 트레인에서 의도적으로 보류했다 -- 병합 셀·중첩표에서
행/열 순서 반전의 정의가 흐려지고 실코퍼스에 근거로 삼을 예시가 없다
(``apply_table_ops``의 독스트링과 ``docs/support-matrix.md`` 참조).
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import (
    TableStructureError,
    _blank_region,
    _iter_table_spans,
    _merge_table_rows,
    _split_table_rows,
    apply_table_ops,
    build_grid,
)

FIXT = Path(__file__).parent / "fixtures"
MERGED = FIXT / "m2_corpus" / "public_official_table.hwpx"


def _section(data: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if re.search(r"section\d+\.xml$", n))
        return name, z.read(name)


def _tables(data: bytes):
    _, sec = _section(data)
    return sec, _iter_table_spans(sec)


def _grid_of(sec: bytes, span):
    return build_grid(sec[span[0]:span[1]])


def _tbl_id(table_xml: bytes | str) -> str | None:
    text = table_xml.decode("utf-8") if isinstance(table_xml, bytes) else table_xml
    m = re.search(r'<hp:tbl\b[^>]*\bid="(\d+)"', text)
    return m.group(1) if m else None


@pytest.fixture(scope="module")
def merged() -> bytes:
    return MERGED.read_bytes()


def _simple_table(row_cnt: int, col_cnt: int = 1) -> str:
    """A synthetic table with no merged cells: one column, *row_cnt* rows."""
    rows = "".join(
        f'<hp:tr><hp:tc><hp:cellAddr colAddr="0" rowAddr="{r}"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="1000" height="1000"/></hp:tc></hp:tr>'
        for r in range(row_cnt)
    )
    return f'<hp:tbl id="1" rowCnt="{row_cnt}" colCnt="{col_cnt}">{rows}</hp:tbl>'


# --------------------------------------------------------------------------
# _split_table_rows / _merge_table_rows -- pure-function unit tests


def test_split_table_rows_produces_two_grid_valid_tables() -> None:
    table = _simple_table(4)
    top, bottom = _split_table_rows(table, 1)

    top_grid, top_rep = build_grid(top.encode())
    bottom_grid, bottom_rep = build_grid(bottom.encode())
    assert top_rep.ok and top_rep.row_count == 1
    assert bottom_rep.ok and bottom_rep.row_count == 3
    # bottom half's rowAddr is renumbered from 0, not left at 1..3
    assert set(r for r, _c in bottom_grid) == {0, 1, 2}


def test_split_table_rows_rejects_out_of_range_split_row() -> None:
    table = _simple_table(3)
    with pytest.raises(TableStructureError):
        _split_table_rows(table, 0)
    with pytest.raises(TableStructureError):
        _split_table_rows(table, 3)


def test_split_table_rows_refuses_when_a_merged_cell_crosses_the_boundary() -> None:
    table = (
        '<hp:tbl id="1" rowCnt="3" colCnt="1">'
        '<hp:tr><hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/>'
        '<hp:cellSpan colSpan="1" rowSpan="2"/>'
        '<hp:cellSz width="1000" height="2000"/></hp:tc></hp:tr>'
        '<hp:tr></hp:tr>'
        '<hp:tr><hp:tc><hp:cellAddr colAddr="0" rowAddr="2"/>'
        '<hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="1000" height="1000"/></hp:tc></hp:tr>'
        '</hp:tbl>'
    )
    with pytest.raises(TableStructureError, match="crosses split_row"):
        _split_table_rows(table, 1)
    # splitting exactly where the span ends is fine.
    top, bottom = _split_table_rows(table, 2)
    assert build_grid(top.encode())[1].ok
    assert build_grid(bottom.encode())[1].ok


def test_merge_table_rows_recombines_a_split_pair() -> None:
    original = _simple_table(4)
    top, bottom = _split_table_rows(original, 1)

    merged = _merge_table_rows(top, bottom)

    grid, rep = build_grid(merged.encode())
    assert rep.ok and rep.row_count == 4 and rep.col_count == 1
    assert set(r for r, _c in grid) == {0, 1, 2, 3}


def test_merge_table_rows_rejects_column_count_mismatch() -> None:
    top = _simple_table(2, col_cnt=1)
    bottom = _simple_table(2, col_cnt=2)
    with pytest.raises(TableStructureError, match="colCnt mismatch"):
        _merge_table_rows(top, bottom)


def test_blank_region_detects_real_text_but_not_empty_paragraphs() -> None:
    assert _blank_region(b"<hp:p><hp:run><hp:t></hp:t></hp:run></hp:p>", 0, 44)
    text = b"<hp:p><hp:run><hp:t>\xea\xb0\x80</hp:t></hp:run></hp:p>"
    assert not _blank_region(text, 0, len(text))


# --------------------------------------------------------------------------
# apply_table_ops integration -- real fixture (public_official_table.hwpx)


def test_apply_table_ops_split_table_grows_table_count_and_preserves_others(merged) -> None:
    sec0, spans0 = _tables(merged)
    n = len(spans0)
    # table 2: rowCnt=2, colCnt=1, no rowSpan>1 -- a clean split target.
    ti = 2
    assert _grid_of(sec0, spans0[ti])[1].row_count == 2

    res = apply_table_ops(merged, [{"op": "split_table", "table_index": ti, "split_row": 1}])
    assert res.ok, res.skipped

    sec1, spans1 = _tables(res.data)
    assert len(spans1) == n + 1

    top_rep = _grid_of(sec1, spans1[ti])[1]
    bottom_rep = _grid_of(sec1, spans1[ti + 1])[1]
    assert top_rep.ok and top_rep.row_count == 1
    assert bottom_rep.ok and bottom_rep.row_count == 1

    # the new (bottom) table got a different id than the original.
    top_id = _tbl_id(sec1[spans1[ti][0]:spans1[ti][1]])
    bottom_id = _tbl_id(sec1[spans1[ti + 1][0]:spans1[ti + 1][1]])
    assert top_id == _tbl_id(sec0[spans0[ti][0]:spans0[ti][1]])
    assert bottom_id is not None and bottom_id != top_id

    # every OTHER table is untouched (byte-identical) -- indices after ti
    # shift by one (a new table was inserted), so compare by id instead.
    other_ids_before = {
        _tbl_id(sec0[s:e]) for i, (s, e) in enumerate(spans0) if i != ti
    }
    other_ids_after = {
        _tbl_id(sec1[s:e]) for i, (s, e) in enumerate(spans1) if i not in (ti, ti + 1)
    }
    assert other_ids_before == other_ids_after


def test_apply_table_ops_split_table_refuses_when_a_span_crosses_the_row(merged) -> None:
    # table 10: rowCnt=11, row 0 has a cell with rowAddr=0 rowSpan=2 -- a
    # split at row 1 would cross it.
    res = apply_table_ops(merged, [{"op": "split_table", "table_index": 10, "split_row": 1}])
    assert not res.ok
    assert res.skipped
    assert "crosses split_row" in res.skipped[0].reason


def test_apply_table_ops_split_table_succeeds_right_after_a_span_ends(merged) -> None:
    # same table, but split_row=2 sits exactly where the row-0 span ends.
    sec0, spans0 = _tables(merged)
    res = apply_table_ops(merged, [{"op": "split_table", "table_index": 10, "split_row": 2}])
    assert res.ok, res.skipped
    sec1, spans1 = _tables(res.data)
    top_rep = _grid_of(sec1, spans1[10])[1]
    bottom_rep = _grid_of(sec1, spans1[11])[1]
    assert top_rep.ok and top_rep.row_count == 2
    assert bottom_rep.ok and bottom_rep.row_count == 9


def test_apply_table_ops_split_table_refuses_nested_tables(merged) -> None:
    # table 8 declares rowCnt=1 but the raw row scan finds 12 <hp:tr> --
    # a nested table inside one of its cells (_guard_flat's territory).
    res = apply_table_ops(merged, [{"op": "split_table", "table_index": 8, "split_row": 1}])
    assert not res.ok
    assert res.skipped
    assert "nested" in res.skipped[0].reason


def test_apply_table_ops_split_table_requires_split_row(merged) -> None:
    res = apply_table_ops(merged, [{"op": "split_table", "table_index": 2}])
    assert not res.ok
    assert res.skipped and "split_row" in res.skipped[0].reason


def test_apply_table_ops_merge_table_reverses_a_split(merged) -> None:
    split = apply_table_ops(merged, [{"op": "split_table", "table_index": 2, "split_row": 1}])
    assert split.ok, split.skipped

    remerged = apply_table_ops(split.data, [{"op": "merge_table", "table_index": 2}])
    assert remerged.ok, remerged.skipped

    sec0, spans0 = _tables(merged)
    sec1, spans1 = _tables(remerged.data)
    assert len(spans1) == len(spans0)
    rep = _grid_of(sec1, spans1[2])[1]
    assert rep.ok and rep.row_count == 2 and rep.col_count == 1


def test_apply_table_ops_merge_table_refuses_column_count_mismatch(merged) -> None:
    # table 2 (colCnt=1) immediately followed (no gap) by table 3 (colCnt=3).
    res = apply_table_ops(merged, [{"op": "merge_table", "table_index": 2}])
    assert not res.ok
    assert res.skipped
    assert "colCnt mismatch" in res.skipped[0].reason


def test_apply_table_ops_merge_table_refuses_without_a_next_table(merged) -> None:
    _sec0, spans0 = _tables(merged)
    last = len(spans0) - 1
    res = apply_table_ops(merged, [{"op": "merge_table", "table_index": last}])
    assert not res.ok
    assert res.skipped
    assert "no next table" in res.skipped[0].reason


def test_apply_table_ops_split_table_dry_run_reports_would_apply(merged, tmp_path) -> None:
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        merged,
        [{"op": "split_table", "table_index": 2, "split_row": 1}],
        output_path=out,
        dry_run=True,
    )
    assert not out.exists(), "dry-run이 파일을 썼다"
    entry = res.transcript[0]
    assert entry["op"] == "split_table" and entry["status"] == "would_apply"
    assert "1x1" in entry["dims"]
