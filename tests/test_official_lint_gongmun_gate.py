# SPDX-License-Identifier: Apache-2.0
"""M3 P2 — 공문 structure hard-gate anchored by the real 시행문."""
from __future__ import annotations

import tempfile
from pathlib import Path

from hwpx.authoring import create_document_from_plan
from hwpx.document import HwpxDocument
from hwpx.tools.official_lint import inspect_official_document_style as lint

GOLD = "tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx"


def _structure_rules(report):
    return {v["rule"] for v in report["violations"] if v["severity"] == "error"}


def test_gold_sihaengmun_passes_structure_gate():
    r = lint(GOLD, document_type="공문")
    assert r["structure_pass"] is True, f"gold should pass; errors={_structure_rules(r)}"


def test_incomplete_gongmun_fails_with_missing_spine():
    r = lint({"paragraphs": ["○○ 협조 안내", "1. 알려드립니다."]}, document_type="공문")
    assert r["structure_pass"] is False
    errs = _structure_rules(r)
    assert "missing-susin" in errs
    assert "missing-sihaeng" in errs
    assert "missing-disclosure" in errs
    assert "missing-balsinmyeongui" in errs
    assert "missing-end-marker" in errs


def test_no_document_type_is_backward_compatible():
    # Without document_type: no structure rules; legacy `pass` semantics intact.
    src = {"paragraphs": ["제목", "1. 본문입니다.  끝."]}
    r = lint(src)
    assert "structure_pass" in r
    assert not any(v["rule"].startswith("missing-") for v in r["violations"])


def test_composed_gongmun_passes_structure_gate():
    plan = {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "교육협력 사업 추진 협조 요청",
        "metadata": {"document_type": "공문"},
        "blocks": [
            {"type": "paragraph", "text": "수신  각급학교장"},
            {"type": "heading", "level": 1, "text": "1. 관련"},
            {"type": "paragraph", "text": "가. 적극 협조하여 주시기 바랍니다.  끝."},
        ],
        "gyeolmun": {"issuer": "○○교육지원청교육장", "enforcementDate": "2026. 6. 27.", "disclosure": "공개"},
    }
    doc = create_document_from_plan(plan)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "g.hwpx"
        doc.save_to_path(str(f))
        doc.close()
        r = lint(str(f), document_type="공문")
    assert r["structure_pass"] is True, f"composed 공문 should pass; errors={_structure_rules(r)}"
