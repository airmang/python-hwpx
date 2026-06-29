# SPDX-License-Identifier: Apache-2.0
"""M3 P3 — honest render_checked / visual_complete wired into authoring quality."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from hwpx.authoring import create_document_from_plan, inspect_document_authoring_quality

PLAN = {
    "schemaVersion": "hwpx.document_plan.v1",
    "title": "교육협력 사업 추진 협조 요청",
    "metadata": {"document_type": "공문"},
    "blocks": [
        {"type": "paragraph", "text": "수신  각급학교장"},
        {"type": "heading", "level": 1, "text": "1. 관련"},
        {"type": "paragraph", "text": "가. 협조하여 주시기 바랍니다.  끝."},
    ],
    "gyeolmun": {"issuer": "○○교육지원청교육장", "enforcementDate": "2026. 6. 27.", "disclosure": "공개"},
}


def _doc_path(tmp: str) -> str:
    doc = create_document_from_plan(PLAN)
    f = Path(tmp) / "g.hwpx"
    doc.save_to_path(str(f))
    doc.close()
    return str(f)


def test_no_render_is_unverified_not_silent_true():
    # verify_render defaults False -> no oracle invoked -> honest unverified.
    with tempfile.TemporaryDirectory() as tmp:
        rep = inspect_document_authoring_quality(_doc_path(tmp), plan=PLAN)
    assert rep["render_checked"] is False
    assert rep["visual_complete"] == "unverified"
    assert rep["visual_review_required"] is True


@pytest.mark.skipif(
    os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom for the render_checked smoke",
)
def test_verify_render_real_oracle_sets_render_checked():
    from hwpx.visual import oracle as o

    if not o.MacHancomOracle().available():
        pytest.skip("Hancom not available")
    with tempfile.TemporaryDirectory() as tmp:
        rep = inspect_document_authoring_quality(_doc_path(tmp), plan=PLAN, verify_render=True)
    assert rep["render_checked"] is True
    assert rep["visual_complete"] is True
    assert rep["visual_review_required"] is False
