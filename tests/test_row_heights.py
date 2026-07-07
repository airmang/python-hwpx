"""set_row_heights — 행높이 명시 설정/재배분 (Stage 3 간격 프리미티브)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import apply_table_ops

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


def _table_cells(path, table_index):
    xml = zipfile.ZipFile(path).read("Contents/section0.xml").decode("utf-8")
    spans = [m.span() for m in re.finditer(r"<hp:tbl\b", xml)]
    start = spans[table_index][0]
    depth = 0
    for m in re.finditer(r"<hp:tbl\b|</hp:tbl>", xml[start:]):
        depth += 1 if not m.group().startswith("</") else -1
        if depth == 0:
            table = xml[start: start + m.end()]
            break
    out = []
    for m in re.finditer(r"<hp:tc\b.*?</hp:tc>", table, re.S):
        blk = m.group(0)
        ra = int(re.search(r'rowAddr="(\d+)"', blk).group(1))
        rs_m = re.search(r'rowSpan="(\d+)"', blk)
        h = int(re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', blk).group(1))
        out.append((ra, int(rs_m.group(1)) if rs_m else 1, h))
    return out


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_single_row_resize_updates_cells_and_merged_sums(work, tmp_path):
    before = _table_cells(work, 2)
    target_row = 2
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work, [{"op": "set_row_heights", "table_index": 2, "heights": {target_row: 5000}}],
        output_path=out,
    )
    assert res.ok, res.skipped
    after = _table_cells(out, 2)
    cur = {ra: h for ra, rs, h in before if rs == 1}
    for (ra, rs, h0), (_, _, h1) in zip(before, after):
        covered = range(ra, ra + rs)
        if target_row not in covered:
            assert h1 == h0  # 무관 셀 불변
        else:
            expected = sum(5000 if r == target_row else cur[r] for r in covered)
            assert h1 == expected


def test_out_of_range_row_refused(work):
    res = apply_table_ops(work, [{"op": "set_row_heights", "table_index": 2, "heights": {999: 5000}}])
    assert res.skipped and "out of range" in res.skipped[0].reason


def test_transcript_and_dry_run(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work, [{"op": "set_row_heights", "table_index": 2, "heights": {2: 5000}}],
        output_path=out, dry_run=True,
    )
    assert res.transcript[0]["status"] == "would_apply"
    assert not out.exists()
