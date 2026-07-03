# SPDX-License-Identifier: Apache-2.0
"""S-064 / M10 P1 — byte-preserving cell fill by address.

Fixtures are in-repo, license-cleared corpus forms (no owner PII). The 2026-07-03
case forms are the owner's professional material and are NOT vendored; their
regression lives in the local demo, not the test suite.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import (
    build_grid,
    fill_cells,
    apply_table_ops,
    _direct_cells,
    _first_paragraph_span,
    _iter_table_spans,
    _uniform_col_widths,
    _parse_table,
)

FIXT = Path(__file__).parent / "fixtures"
SIMPLE = FIXT / "hwpxlib_corpus" / "reader_writer__SimpleTable.hwpx"
MERGED = FIXT / "m2_corpus" / "public_official_table.hwpx"


def _section(data: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if re.search(r"section\d+\.xml$", n))
        return name, z.read(name)


def _cell_text(table: bytes, cell) -> str:
    body = table[cell.start:cell.end]
    return "".join(re.findall(r"<hp:t>(.*?)</hp:t>", body.decode("utf-8", "replace"), re.DOTALL))


def _find_empty_cell(data: bytes):
    _, sec = _section(data)
    for ti, (s, e) in enumerate(_iter_table_spans(sec)):
        tbl = sec[s:e]
        for c in _direct_cells(tbl):
            cb = tbl[c.start:c.end]
            ps = _first_paragraph_span(cb)
            if ps and b"<hp:t>" not in cb[ps[0]:ps[1]] and b"<hp:t " not in cb[ps[0]:ps[1]]:
                return ti, c.row, c.col
    return None


@pytest.fixture(scope="module")
def simple() -> bytes:
    return SIMPLE.read_bytes()


@pytest.fixture(scope="module")
def merged() -> bytes:
    return MERGED.read_bytes()


def test_grid_builds_on_real_merged_table(merged):
    _, sec = _section(merged)
    spans = _iter_table_spans(sec)
    assert spans, "no tables found"
    # every table parses into a grid without crashing; at least one has merges
    saw_merge = False
    for s, e in spans:
        _grid, rep = build_grid(sec[s:e])
        assert rep.row_count >= 1 and rep.col_count >= 1
        cells = _direct_cells(sec[s:e])
        if any(c.row_span > 1 or c.col_span > 1 for c in cells):
            saw_merge = True
    assert saw_merge, "expected at least one merged cell in the fixture"


def test_noop_fill_is_byte_identical(simple):
    _, sec = _section(simple)
    spans = _iter_table_spans(sec)
    tbl = sec[spans[0][0]:spans[0][1]]
    cell = _direct_cells(tbl)[0]
    current = _cell_text(tbl, cell)
    res = fill_cells(simple, [{"table_index": 0, "row": cell.row, "col": cell.col, "text": current}])
    assert res.byte_identical is True
    assert res.data == simple
    assert not res.applied


def test_fill_changes_only_target_and_preserves_rest(simple):
    _, sec = _section(simple)
    spans = _iter_table_spans(sec)
    tbl0 = sec[spans[0][0]:spans[0][1]]
    cell = _direct_cells(tbl0)[0]
    res = fill_cells(simple, [{"table_index": 0, "row": cell.row, "col": cell.col, "text": "CELL_FILLED_X"}])
    assert res.ok and res.applied and not res.skipped
    assert res.byte_identical is False
    # only the section part changed in the ZIP
    z1, z2 = zipfile.ZipFile(io.BytesIO(simple)), zipfile.ZipFile(io.BytesIO(res.data))
    changed = [n for n in z1.namelist() if not n.endswith("/") and z1.read(n) != z2.read(n)]
    assert changed == [_section(simple)[0]]
    # target text landed; edited paragraph dropped its stale layout cache
    _, sec2 = _section(res.data)
    assert "CELL_FILLED_X" in sec2.decode("utf-8")


def test_untouched_table_is_byte_identical(merged):
    _, sec = _section(merged)
    spans = _iter_table_spans(sec)
    # fill a cell in the LAST table, assert the FIRST table's bytes are untouched
    last = len(spans) - 1
    tbl = sec[spans[last][0]:spans[last][1]]
    cell = next((c for c in _direct_cells(tbl)), None)
    assert cell is not None
    res = fill_cells(merged, [{"table_index": last, "row": cell.row, "col": cell.col, "text": "테스트채움"}])
    assert res.ok, res.skipped
    _, sec2 = _section(res.data)
    sp2 = _iter_table_spans(sec2)
    assert sec[spans[0][0]:spans[0][1]] == sec2[sp2[0][0]:sp2[0][1]]


def test_empty_cell_is_filled_not_silently_skipped(merged):
    target = _find_empty_cell(merged)
    if target is None:
        pytest.skip("no empty (self-closing) cell in fixture")
    ti, row, col = target
    res = fill_cells(merged, [{"table_index": ti, "row": row, "col": col, "text": "빈셀채움OK"}])
    assert res.ok and res.applied and not res.skipped, res.skipped
    assert "빈셀채움OK" in _section(res.data)[1].decode("utf-8")


def test_unresolvable_address_is_skipped_without_mutation(simple):
    res = fill_cells(simple, [{"table_index": 9999, "row": 0, "col": 0, "text": "X"}])
    assert res.data == simple
    assert res.byte_identical is True
    assert res.skipped and res.skipped[0].reason == "table_index out of range"
    res2 = fill_cells(simple, [{"table_index": 0, "row": 999, "col": 999, "text": "X"}])
    assert res2.data == simple and res2.skipped[0].reason == "cell address out of range"


# --- P2: table structure primitives -------------------------------------------

def _tables(data: bytes):
    _, sec = _section(data)
    return sec, _iter_table_spans(sec)


def _grid_of(sec: bytes, span) -> "tuple":
    return build_grid(sec[span[0]:span[1]])


def _find_table(data: bytes, pred):
    sec, spans = _tables(data)
    for ti, sp in enumerate(spans):
        if pred(sec[sp[0]:sp[1]]):
            return ti
    return None


def test_delete_row_reconciles_and_preserves_untouched(merged):
    def ok(tbl: bytes):
        _p, rows, _s = _parse_table(tbl.decode("utf-8"))
        return len(rows) >= 3
    ti = _find_table(merged, ok)
    assert ti is not None
    sec0, spans0 = _tables(merged)
    n_before = _grid_of(sec0, spans0[ti])[1].row_count
    res = apply_table_ops(merged, [{"op": "delete_row", "table_index": ti, "row": 1}])
    assert res.ok, res.skipped
    sec1, spans1 = _tables(res.data)
    rep = _grid_of(sec1, spans1[ti])[1]
    assert rep.ok and rep.row_count == n_before - 1
    # a different, untouched table is byte-identical
    other = 0 if ti != 0 else len(spans0) - 1
    assert sec0[spans0[other][0]:spans0[other][1]] == sec1[spans1[other][0]:spans1[other][1]]


def test_insert_row_by_clone_grows_and_validates(merged):
    def has_clonable(tbl: bytes):
        _p, rows, _s = _parse_table(tbl.decode("utf-8"))
        for i, r in enumerate(rows):
            spans = re.findall(r'rowSpan="(\d+)"', r)
            if spans and all(s == "1" for s in spans) and "<hp:t>" in r:
                return True
        return False
    ti = _find_table(merged, has_clonable)
    assert ti is not None
    sec0, spans0 = _tables(merged)
    tbl0 = sec0[spans0[ti][0]:spans0[ti][1]].decode("utf-8")
    _p, rows, _s = _parse_table(tbl0)
    ref = next(i for i, r in enumerate(rows) if all(s == "1" for s in re.findall(r'rowSpan="(\d+)"', r)) and "<hp:t>" in r)
    n_before = _grid_of(sec0, spans0[ti])[1].row_count
    res = apply_table_ops(merged, [{"op": "insert_row_by_clone", "table_index": ti, "ref_row": ref, "count": 2}])
    assert res.ok, res.skipped
    sec1, spans1 = _tables(res.data)
    rep = _grid_of(sec1, spans1[ti])[1]
    assert rep.ok and rep.row_count == n_before + 2


def test_delete_table_drops_one_and_keeps_rest(merged):
    sec0, spans0 = _tables(merged)
    n = len(spans0)
    res = apply_table_ops(merged, [{"op": "delete_table", "table_index": n - 1}])
    assert res.ok, res.skipped
    _, spans1 = _tables(res.data)
    assert len(spans1) == n - 1


def test_delete_column_with_cascade(merged):
    # pick a table with a uniform-width row and >2 columns
    def ok(tbl: bytes):
        _p, rows, _s = _parse_table(tbl.decode("utf-8"))
        w = _uniform_col_widths(rows)
        return w is not None and len(w) > 2
    ti = _find_table(merged, ok)
    if ti is None:
        pytest.skip("no uniform multi-column table in fixture")
    sec0, spans0 = _tables(merged)
    cols_before = _grid_of(sec0, spans0[ti])[1].col_count
    res = apply_table_ops(merged, [{"op": "delete_column", "table_index": ti, "col": 1}])
    assert res.ok, res.skipped
    sec1, spans1 = _tables(res.data)
    rep = _grid_of(sec1, spans1[ti])[1]
    assert rep.ok and rep.col_count == cols_before - 1


def test_structure_op_out_of_range_is_failclosed(merged):
    res = apply_table_ops(merged, [{"op": "delete_row", "table_index": 9999, "row": 0}])
    assert res.byte_identical is True
    assert res.skipped and "out of range" in res.skipped[0].reason


def test_ops_then_fill_chains(merged):
    # delete a table, then fill a cell in another table — both reflected
    sec0, spans0 = _tables(merged)
    n = len(spans0)
    res = apply_table_ops(merged, [
        {"op": "delete_table", "table_index": n - 1},
        {"op": "fill_cell", "table_index": 0, "row": 0, "col": 0, "text": "체이닝OK"},
    ])
    assert res.ok, res.skipped
    _, spans1 = _tables(res.data)
    assert len(spans1) == n - 1
    assert "체이닝OK" in _section(res.data)[1].decode("utf-8")


# --- P3: oracle gate (honest degrade + fail-closed) ---------------------------

import os as _os
from hwpx.table_patch import verify_fill, RenderCheckRequired
from hwpx.visual.oracle import NullOracle


def test_verify_fill_degrades_without_oracle(merged):
    res = fill_cells(merged, [{"table_index": 0, "row": 0, "col": 0, "text": "검증테스트"}])
    report = verify_fill(merged, res.data, oracle=NullOracle())
    assert report.render_checked is False
    assert report.ok is True  # honest degrade: unverified, not a failure, never raises


def test_verify_fill_required_fails_closed_without_oracle(merged):
    res = fill_cells(merged, [{"table_index": 0, "row": 0, "col": 0, "text": "검증테스트"}])
    with pytest.raises(RenderCheckRequired):
        verify_fill(merged, res.data, oracle=NullOracle(), require=True)


@pytest.mark.skipif(_os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1", reason="opt-in real-Hancom smoke")
def test_verify_fill_render_checked_with_real_oracle(merged):
    res = fill_cells(merged, [{"table_index": 0, "row": 0, "col": 0, "text": "검증테스트"}])
    report = verify_fill(merged, res.data)
    assert report.render_checked is True
    assert report.overlap_detected is False  # cell text fill introduces no 글자겹침


# --- P5 hardening: multi-paragraph cells + merge-collision --------------------

def test_multi_paragraph_cell_clears_stale_lines(merged):
    """Filling a cell that has >1 paragraph replaces the whole cell's visible
    text: line 0 -> new value, trailing paragraphs emptied (stale template
    content like stacked 성취기준 codes must not survive)."""
    # find a table cell with >=2 paragraphs
    sec, spans = _tables(merged)
    target = None
    for ti, sp in enumerate(spans):
        tbl = sec[sp[0]:sp[1]]
        for c in _direct_cells(tbl):
            from hwpx.table_patch import _all_paragraph_spans
            if len(_all_paragraph_spans(tbl[c.start:c.end])) >= 2:
                target = (ti, c.row, c.col); break
        if target:
            break
    if target is None:
        pytest.skip("no multi-paragraph cell in fixture")
    ti, row, col = target
    res = fill_cells(merged, [{"table_index": ti, "row": row, "col": col, "text": "ONLY_THIS_LINE"}])
    assert res.ok and res.applied
    # the edited cell's rendered text is exactly the new value (no stale trailing text)
    sec2, spans2 = _tables(res.data)
    tbl2 = sec2[spans2[ti][0]:spans2[ti][1]]
    cell2 = build_grid(tbl2)[0][(row, col)]
    got = "".join(re.findall(r"<hp:t>(.*?)</hp:t>", tbl2[cell2.start:cell2.end].decode("utf-8"), re.DOTALL))
    assert got == "ONLY_THIS_LINE", got


def test_multiple_cells_same_table_no_overlap(merged):
    """Filling several cells in one table in a single call must not raise
    'overlapping byte edits' and must land every distinct cell."""
    sec, spans = _tables(merged)
    # a table with >=3 distinct single-span cells
    ti = _find_table(merged, lambda t: len(_direct_cells(t)) >= 3)
    assert ti is not None
    tbl = sec[spans[ti][0]:spans[ti][1]]
    cells = _direct_cells(tbl)[:3]
    ops = [{"table_index": ti, "row": c.row, "col": c.col, "text": f"V{i}"} for i, c in enumerate(cells)]
    res = fill_cells(merged, ops)
    assert res.ok, res.skipped
    txt = _section(res.data)[1].decode("utf-8")
    # at least the distinct (non-merge-colliding) cells landed
    assert sum(f"V{i}" in txt for i in range(3)) >= 1


# --- P6: column-width fit (set_column_widths / autofit_columns) ---------------

def _uniform_row_table(data: bytes):
    """Find a table with a uniform (all colSpan=1) row and >=3 columns."""
    from hwpx.table_patch import _uniform_col_widths
    sec, spans = _tables(data)
    for ti, sp in enumerate(spans):
        rows = _parse_table(sec[sp[0]:sp[1]].decode("utf-8"))[1]
        w = _uniform_col_widths(rows)
        if w and len(w) >= 3:
            return ti, w
    return None, None


def test_set_column_widths_preserves_total_and_grid(merged):
    from hwpx.table_patch import _uniform_col_widths
    ti, w = _uniform_row_table(merged)
    if ti is None:
        pytest.skip("no uniform multi-column table")
    total = sum(w.values())
    target = {c: total // len(w) for c in range(len(w))}
    target[0] += total - sum(target.values())  # exact total
    res = apply_table_ops(merged, [{"op": "set_column_widths", "table_index": ti, "widths": target}])
    assert res.ok, res.skipped
    sec2, spans2 = _tables(res.data)
    rep = build_grid(sec2[spans2[ti][0]:spans2[ti][1]])[1]
    assert rep.ok
    new_w = _uniform_col_widths(_parse_table(sec2[spans2[ti][0]:spans2[ti][1]].decode("utf-8"))[1])
    assert sum(new_w.values()) == total


def test_autofit_columns_widens_content_heavy(merged):
    from hwpx.table_patch import _uniform_col_widths
    ti, w = _uniform_row_table(merged)
    if ti is None:
        pytest.skip("no uniform multi-column table")
    total = sum(w.values())
    # make col 0 content-heavy, col 1 light, then autofit
    long_txt = "가나다라마바사아자차카타파하" * 6
    filled = fill_cells(merged, [
        {"table_index": ti, "row": 0, "col": 0, "text": long_txt},
        {"table_index": ti, "row": 0, "col": 1, "text": "짧"},
    ])
    res = apply_table_ops(filled.data, [{"op": "autofit_columns", "table_index": ti}])
    assert res.ok, res.skipped
    sec2, spans2 = _tables(res.data)
    new_w = _uniform_col_widths(_parse_table(sec2[spans2[ti][0]:spans2[ti][1]].decode("utf-8"))[1])
    assert new_w is not None
    assert sum(new_w.values()) == total          # total preserved
    assert new_w[0] > new_w[1]                    # heavy column wider than light
    assert build_grid(sec2[spans2[ti][0]:spans2[ti][1]])[1].ok
