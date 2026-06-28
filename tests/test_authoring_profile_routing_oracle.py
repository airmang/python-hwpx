# SPDX-License-Identifier: Apache-2.0
"""M3 P1 — oracle smoke: routed 공문·보고서·가정통신문 open clean in real Hancom.

Gated by HWPX_MAC_ORACLE_SMOKE=1 (macOS + Hancom). Proves the PUBLIC authoring
path (create_document_from_plan) routes document_type -> design profile and the
result opens clean (PDF render + fitz text) — FR-001/002/003/007 end-to-end.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from hwpx.authoring import create_document_from_plan
from hwpx.visual import oracle as o

pytestmark = pytest.mark.skipif(
    os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the authoring render smoke",
)

GONGMUN = {
    "schemaVersion": "hwpx.document_plan.v1",
    "title": "2026학년도 교육협력 사업 추진 협조 요청",
    "metadata": {"document_type": "공문"},
    "blocks": [
        {"type": "paragraph", "text": "수신  각급학교장"},
        {"type": "heading", "level": 1, "text": "1. 관련"},
        {"type": "paragraph", "text": "가. 교육협력 사업 추진 계획(2026. 6. 1.)"},
        {"type": "heading", "level": 1, "text": "2. 협조 요청 사항"},
        {"type": "paragraph", "text": "가. 원활한 사업 추진을 위하여 적극 협조하여 주시기 바랍니다.  끝."},
    ],
    "gyeolmun": {"issuer": "○○교육지원청교육장", "productionNumber": "교육협력과-1234",
                 "enforcementDate": "2026. 6. 27.", "disclosure": "공개"},
}
BOGOSEO = {
    "schemaVersion": "hwpx.document_plan.v1",
    "title": "부서별 추진실적 보고서",
    "metadata": {"document_type": "보고서"},
    "blocks": [
        {"type": "heading", "level": 1, "text": "1. 추진 개요"},
        {"type": "paragraph", "text": "가. 분기별 추진 실적을 다음과 같이 보고합니다."},
        {"type": "heading", "level": 2, "text": "가. 세부 실적"},
        {"type": "table", "columns": ["부서", "실적"], "rows": [["기획", "100%"], ["운영", "95%"]]},
        {"type": "heading", "level": 1, "text": "2. 향후 계획"},
        {"type": "paragraph", "text": "가. 차기 분기 목표를 상향 조정한다."},
    ],
}
GAJEONG = {
    "schemaVersion": "hwpx.document_plan.v1",
    "title": "여름방학 생활 안내 가정통신문",
    "metadata": {"document_type": "가정통신문"},
    "blocks": [
        {"type": "paragraph", "text": "학부모님, 안녕하십니까?"},
        {"type": "heading", "level": 1, "text": "1. 여름방학 기간"},
        {"type": "paragraph", "text": "가. 2026. 7. 21.(화) ~ 2026. 8. 17.(월)"},
        {"type": "paragraph", "text": "2026. 7. 18."},
        {"type": "paragraph", "text": "○○중학교장"},
    ],
}


@pytest.mark.parametrize("name,plan", [("gongmun", GONGMUN), ("bogoseo", BOGOSEO), ("gajeong", GAJEONG)])
def test_routed_document_opens_clean(name, plan):
    fitz = pytest.importorskip("fitz")
    mac = o.MacHancomOracle()
    if not mac.available():
        pytest.skip("Hancom not available")
    doc = create_document_from_plan(plan)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            hwpx = Path(tmp) / f"{name}.hwpx"
            doc.save_to_path(str(hwpx))
            pdf = Path(tmp) / f"{name}.pdf"
            rendered = mac.render_pdf(str(hwpx), str(pdf))
            assert rendered and Path(rendered).exists(), f"{name}: Hancom did not render"
            d = fitz.open(rendered)
            text = "".join(p.get_text() for p in d)
            d.close()
            assert len(text) > 0, f"{name}: rendered PDF has no extractable text"
    finally:
        doc.close()
