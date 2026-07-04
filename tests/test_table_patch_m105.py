# SPDX-License-Identifier: Apache-2.0
"""M10.5 (014) primitives on the REAL 평가계획 forms.

FR-001 merged-block clone (성취기준 A~E unit) and FR-003 delete_column on a
fully-merged table (반영비율) — the two primitives S-064 could not do. Pinned over
the province's publicly-distributed blank forms (no owner PII)."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import (
    apply_table_ops,
    build_grid,
    _iter_table_spans,
    _direct_cells,
    _parse_table,
    _S_TC,
    _si,
)

FIXT = Path(__file__).parent / "fixtures" / "m105_evalplan"
FORM_2HAK = FIXT / "blank_form_1-2hak.hwpx"


def _section(data: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if re.search(r"section\d+\.xml$", n))
        return name, z.read(name)


def _table(data: bytes, ti: int) -> bytes:
    _, sec = _section(data)
    s, e = _iter_table_spans(sec)[ti]
    return sec[s:e]


def _grid(data: bytes, ti: int):
    return build_grid(_table(data, ti))


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist() if not i.is_dir()}


def _total_width(data: bytes, ti: int) -> int:
    """Max full-width sum across rows = logical table width."""
    _p, rows, _s = _parse_table(_table(data, ti).decode("utf-8"))
    best = 0
    for r in rows:
        cells = _S_TC.findall(r)
        if all((_si(tc, "cellSpan", "rowSpan") or 1) == 1 for tc in cells):
            best = max(best, sum((_si(tc, "cellSz", "width") or 0) for tc in cells))
    return best


@pytest.fixture(scope="module")
def form2() -> bytes:
    return FORM_2HAK.read_bytes()


# ---- FR-001 merged-block clone --------------------------------------------
def test_seongchwi_is_the_merged_block_case(form2):
    # table [8] = 성취기준 (듣기·말하기): header + two 5-row A~E blocks.
    _grid_map, rep = _grid(form2, 8)
    assert (rep.row_count, rep.col_count) == (11, 3) and rep.ok
    cells = _direct_cells(_table(form2, 8))
    assert sum(1 for c in cells if c.row_span == 5) == 2  # two leading 성취기준 cells


def test_insert_block_by_clone_2_to_3(form2):
    res = apply_table_ops(form2, [{"op": "insert_block_by_clone", "table_index": 8, "ref_rows": [1, 5], "count": 1}])
    assert res.ok, res.skipped
    _g, rep = _grid(res.data, 8)
    assert rep.ok and (rep.row_count, rep.col_count) == (16, 3)
    # three leading rowSpan==5 blocks now
    assert sum(1 for c in _direct_cells(_table(res.data, 8)) if c.row_span == 5) == 3


def test_insert_block_by_clone_2_to_8(form2):
    # AC-1: grow to 8 성취기준 (clone the block 6 more times) -> 11 + 6*5 = 41 rows.
    res = apply_table_ops(form2, [{"op": "insert_block_by_clone", "table_index": 8, "ref_rows": [1, 5], "count": 6}])
    assert res.ok, res.skipped
    _g, rep = _grid(res.data, 8)
    assert rep.ok and rep.row_count == 41
    assert sum(1 for c in _direct_cells(_table(res.data, 8)) if c.row_span == 5) == 8


def test_cloned_block_format_equals_reference(form2):
    res = apply_table_ops(form2, [{"op": "insert_block_by_clone", "table_index": 8, "ref_rows": [1, 5], "count": 1}])
    _p, rows, _s = _parse_table(_table(res.data, 8).decode("utf-8"))
    ref_block = rows[1:6]     # original block
    clone_block = rows[6:11]  # inserted clone
    # strip volatile rowAddr + paragraph ids -> the rest (borderFill/paraPr/charPr/
    # cellSz/span pattern/text) must be identical.
    def norm(rs):
        s = "".join(rs)
        s = re.sub(r'rowAddr="\d+"', 'rowAddr="_"', s)
        s = re.sub(r'(<hp:p\b[^>]*\bid=")\d+(")', r'\1_\2', s)
        return s
    assert norm(ref_block) == norm(clone_block)


def test_insert_block_rest_of_section_byte_identical(form2):
    res = apply_table_ops(form2, [{"op": "insert_block_by_clone", "table_index": 8, "ref_rows": [1, 5], "count": 1}])
    b, o = _parts(form2), _parts(res.data)
    SEC = _section(form2)[0]
    assert set(b) == set(o)
    assert all(b[k] == o[k] for k in b if k != SEC)  # only section changed
    # tables other than [8] byte-identical
    _, secb = _section(form2)
    _, seco = _section(res.data)
    sb, so = _iter_table_spans(secb), _iter_table_spans(seco)
    assert len(so) == len(sb)
    for i in range(len(sb)):
        if i == 8:
            continue
        assert secb[sb[i][0]:sb[i][1]] == seco[so[i][0]:so[i][1]]


def test_insert_block_refuses_non_merge_unit(form2):
    # rows [0,2] cut through the first A~E block (leading cell rowSpan=5 straddles) -> refuse.
    res = apply_table_ops(form2, [{"op": "insert_block_by_clone", "table_index": 8, "ref_rows": [0, 2], "count": 1}])
    assert res.byte_identical is True
    assert res.skipped and "merge unit" in res.skipped[0].reason.lower() or "straddle" in res.skipped[0].reason.lower()


# ---- FR-003 delete_column on a fully-merged table --------------------------
def test_banyoung_has_no_uniform_row(form2):
    # table [22] = 반영비율 (9x10, heavy merges): baseline path can't derive widths.
    from hwpx.table_patch import _uniform_col_widths, _grid_col_widths
    tbl = _table(form2, 22).decode("utf-8")
    _p, rows, _s = _parse_table(tbl)
    assert _uniform_col_widths(rows) is None            # the S-064 blocker
    assert _grid_col_widths(tbl) is not None            # FR-003 path derives them


def test_delete_column_drops_jeonggi_and_preserves_width(form2):
    before_w = _total_width(form2, 22)
    _g0, rep0 = _grid(form2, 22)
    assert (rep0.row_count, rep0.col_count) == (9, 10)
    res = apply_table_ops(form2, [{"op": "delete_column", "table_index": 22, "cols": [2, 3, 4, 5]}])
    assert res.ok, res.skipped
    _g1, rep1 = _grid(res.data, 22)
    assert rep1.ok and rep1.col_count == 6          # 10 - 4
    assert rep1.row_count == 8                       # 선택형/논술형 row collapsed
    assert _total_width(res.data, 22) == before_w    # freed width redistributed, total preserved
    # 정기시험 text gone from the table
    assert "정기시험" not in _table(res.data, 22).decode("utf-8")


def test_delete_column_rest_byte_identical(form2):
    res = apply_table_ops(form2, [{"op": "delete_column", "table_index": 22, "cols": [2, 3, 4, 5]}])
    _, secb = _section(form2)
    _, seco = _section(res.data)
    sb, so = _iter_table_spans(secb), _iter_table_spans(seco)
    for i in range(len(sb)):
        if i == 22:
            continue
        assert secb[sb[i][0]:sb[i][1]] == seco[so[i][0]:so[i][1]]
