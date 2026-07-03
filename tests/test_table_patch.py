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
    _direct_cells,
    _first_paragraph_span,
    _iter_table_spans,
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
