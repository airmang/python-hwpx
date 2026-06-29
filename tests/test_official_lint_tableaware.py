# SPDX-License-Identifier: Apache-2.0
"""M3 P2 — official lint must read table-cell text (real 시행문 두문/결문 live in tables)."""
from __future__ import annotations

from pathlib import Path

from hwpx.tools.official_lint import _paragraphs_from_source

GOLD = Path("tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx")


def test_table_cells_surface_in_extraction():
    paras = _paragraphs_from_source(GOLD)
    joined = " ".join(paras)
    # 두문/결문 of a real 시행문 live in tables; table-aware reading must surface them.
    # NB: a real 시행문 does NOT print the label "발신명의" — the 발신명의 is the
    # issuer name itself (e.g. 서울특별시장), positioned in the 결문 after 시행.
    assert "수신" in joined, "수신 (두문) not surfaced — table cells not read"
    assert "경유" in joined, "경유 (두문) not surfaced — table cells not read"
    assert "시행" in joined, "시행 (결문) not surfaced — table cells not read"
    assert "공개" in joined, "공개구분 (결문) not surfaced — table cells not read"
