"""set_cell_line_spacing — 셀 내부 문단 줄간격 (Stage 3 간격 프리미티브 P2b)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import apply_table_ops

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_spacing_remaps_parapr_and_strips_lineseg(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[2, 4]], "line_spacing": 130}],
        output_path=out,
    )
    assert res.ok, [s.reason for s in res.skipped]
    entry = next(t for t in res.transcript if t["op"] == "set_cell_line_spacing")
    assert entry["status"] == "applied" and entry["cellsTouched"] == 1

    z = zipfile.ZipFile(out)
    header = z.read("Contents/header.xml").decode("utf-8")
    sec = z.read("Contents/section0.xml").decode("utf-8")
    zb = zipfile.ZipFile(work)
    header0 = zb.read("Contents/header.xml").decode("utf-8")
    # 새 paraPr가 추가되고 lineSpacing=130
    n0 = len(re.findall(r"<hh:paraPr\b", header0))
    n1 = len(re.findall(r"<hh:paraPr\b", header))
    assert n1 > n0
    new_ids = set(re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header)) - set(
        re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header0))
    assert new_ids
    nid = new_ids.pop()
    blk = re.search(r'<hh:paraPr\b[^>]*\bid="' + nid + r'".*?</hh:paraPr>', header, re.S).group(0)
    assert re.search(r'<hh:lineSpacing\b[^>]*\bvalue="130"', blk)
    # 클론의 switch/case 분기까지 전부 130
    assert not re.search(r'<hh:lineSpacing\b[^>]*\bvalue="(?!130)\d+"', blk)
    # 대상 셀 문단이 새 paraPr를 참조 + lineseg 제거
    assert f'paraPrIDRef="{nid}"' in sec
    i = sec.find(f'paraPrIDRef="{nid}"')
    pstart = sec.rfind("<hp:p", 0, i)
    pend = sec.find("</hp:p>", i)
    assert "linesegarray" not in sec[pstart:pend]


def test_untouched_cells_unaffected_and_original_parapr_kept(work, tmp_path):
    out = tmp_path / "out.hwpx"
    apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "rows": [3], "line_spacing": 115}],
        output_path=out,
    )
    header = zipfile.ZipFile(out).read("Contents/header.xml").decode("utf-8")
    # 원본 paraPr들은 그대로 존재(다른 문단 불변)
    header0 = zipfile.ZipFile(work).read("Contents/header.xml").decode("utf-8")
    for pid in re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header0)[:5]:
        assert re.search(r'<hh:paraPr\b[^>]*\bid="' + pid + r'"', header)


def test_no_matching_cells_refused(work):
    res = apply_table_ops(
        work, [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[999, 999]], "line_spacing": 130}],
    )
    assert res.skipped and "no matching cells" in res.skipped[-1].reason


def test_dry_run_reports_would_apply(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[2, 4]], "line_spacing": 130}],
        output_path=out, dry_run=True,
    )
    entry = next(t for t in res.transcript if t["op"] == "set_cell_line_spacing")
    assert entry["status"] == "would_apply"
    assert not out.exists()
