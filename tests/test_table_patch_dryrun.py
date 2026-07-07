"""apply_table_ops dry_run — Stage 2 상의 루프의 승인 근거(기계 증거).

dry-run은 해석·검증·fail-closed를 전부 실제로 수행하되 파일을 쓰지 않고,
구조 op별 transcript(해석 방법·전후 dims)와 fill의 old→new 텍스트를 돌려준다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hwpx.table_patch import apply_table_ops

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_dry_run_reports_transcript_without_writing(work, tmp_path):
    out = tmp_path / "out.hwpx"
    before = work.read_bytes()
    res = apply_table_ops(
        work,
        [
            {"op": "delete_table", "table_index": 5},
            {"op": "fill_cell", "table_index": 2, "row": 5, "col": 3, "text": "미리보기"},
        ],
        output_path=out,
        dry_run=True,
    )
    assert not out.exists(), "dry-run이 파일을 썼다"
    assert work.read_bytes() == before
    # 구조 op transcript: 해석 결과 + 전후 dims
    entry = res.transcript[0]
    assert entry["op"] == "delete_table" and entry["status"] == "would_apply"
    assert entry["dims"].endswith("→deleted") and "x" in entry["dims"]
    # fill은 old→new 텍스트가 승인 근거
    fill = next(a for a in res.applied if a.replacement_text == "미리보기")
    assert fill.table_index == 2 and fill.row == 5 and fill.col == 3
    assert res.to_dict()["transcript"][0]["op"] == "delete_table"


def test_dry_run_still_fail_closed_on_bad_target(work):
    res = apply_table_ops(
        work,
        [{"op": "delete_table", "table_anchor": "존재하지않는헤딩"}],
        dry_run=True,
    )
    assert res.skipped and "matched no table" in res.skipped[0].reason
    assert res.transcript[0]["status"].startswith("refused")


def test_wet_run_transcript_says_applied(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(work, [{"op": "delete_table", "table_index": 5}], output_path=out)
    assert out.exists()
    assert res.transcript[0]["status"] == "applied"
