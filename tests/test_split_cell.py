"""split_cell_vertical — rowSpan 병합 셀 분할 (Stage 3, 루브릭 그룹 정렬용)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import _iter_table_spans, _sections, apply_table_ops

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


def _rubric_table_index(path):
    data = Path(path).read_bytes()
    sec = _sections(data)["Contents/section0.xml"]
    spans = _iter_table_spans(sec)
    for i, (a, b) in enumerate(spans):
        if "전근대사".encode("utf-8") in sec[a:b]:
            return i
    raise AssertionError("rubric sample table not found")


def _col_cells(path, ti, col):
    """(rowAddr, rowSpan) list for a column's anchor cells."""
    data = Path(path).read_bytes()
    sec = _sections(data)["Contents/section0.xml"]
    a, b = _iter_table_spans(sec)[ti]
    tbl = sec[a:b].decode("utf-8")
    out = []
    for tc in re.finditer(r"<hp:tc\b.*?</hp:tc>", tbl, re.S):
        blk = tc.group(0)
        ad = re.search(r"<hp:cellAddr\b[^>]*/>", blk).group(0)
        c = int(re.search(r'colAddr="(\d+)"', ad).group(1))
        r = int(re.search(r'rowAddr="(\d+)"', ad).group(1))
        if c == col:
            rs = int(re.search(r'rowSpan="(\d+)"', re.search(r"<hp:cellSpan\b[^>]*/>", blk).group(0)).group(1))
            out.append((r, rs))
    return sorted(out)


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_split_7span_into_three_groups(work, tmp_path):
    ti = _rubric_table_index(work)
    # col1(평가항목) has a single rowSpan=7 cell at r6
    before = _col_cells(work, ti, 1)
    assert (6, 7) in before
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "split_cell_vertical", "table_index": ti, "row": 6, "col": 1, "sizes": [3, 2, 2]}],
        output_path=out,
    )
    assert res.ok, res.skipped
    after = _col_cells(out, ti, 1)
    # now three anchor cells at r6(rs3), r9(rs2), r11(rs2)
    assert (6, 3) in after and (9, 2) in after and (11, 2) in after
    # tail cells (기본점수/결석 at r13,r14) unchanged
    assert (13, 1) in after and (14, 1) in after


def test_sizes_sum_mismatch_refused(work):
    ti = _rubric_table_index(work)
    res = apply_table_ops(
        work, [{"op": "split_cell_vertical", "table_index": ti, "row": 6, "col": 1, "sizes": [3, 3]}]
    )
    assert res.skipped and "sum" in res.skipped[0].reason


def test_split_then_render_opens_clean(work, tmp_path):
    ti = _rubric_table_index(work)
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "split_cell_vertical", "table_index": ti, "row": 6, "col": 1, "sizes": [3, 2, 2]},
         {"op": "split_cell_vertical", "table_index": ti, "row": 6, "col": 2, "sizes": [3, 2, 2]}],
        output_path=out,
    )
    assert res.ok, res.skipped
    assert res.open_safety.get("ok")


def test_dry_run_no_write(work, tmp_path):
    ti = _rubric_table_index(work)
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "split_cell_vertical", "table_index": ti, "row": 6, "col": 1, "sizes": [3, 2, 2]}],
        output_path=out, dry_run=True,
    )
    assert res.transcript[0]["status"] == "would_apply" and not out.exists()
