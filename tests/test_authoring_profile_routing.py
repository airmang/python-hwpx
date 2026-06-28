# SPDX-License-Identifier: Apache-2.0
"""M3 P1 — document_type -> design profile routing + 결문 IR bridge."""
from __future__ import annotations

from hwpx.authoring import (
    _resolve_design_profile,
    _bridge_to_design_plan,
    create_document_from_plan,
)
from hwpx.design.plan import DocumentPlan as DesignPlan
from hwpx.document import HwpxDocument


def _plan(**over):
    base = {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "교육협력 사업 추진 협조 요청",
        "metadata": {"document_type": "공문"},
        "blocks": [
            {"type": "heading", "level": 1, "text": "1. 관련"},
            {"type": "paragraph", "text": "가. 협조하여 주시기 바랍니다.  끝."},
        ],
    }
    base.update(over)
    return base


# --- Task 1: resolver ---
def test_resolve_known_korean_types():
    assert _resolve_design_profile(_plan()) == "official_notice"
    assert _resolve_design_profile(_plan(metadata={"document_type": "보고서"})) == "report"
    assert _resolve_design_profile(_plan(metadata={"document_type": "가정통신문"})) == "home_notice"


def test_resolve_profile_id_direct():
    assert _resolve_design_profile(_plan(metadata={"document_type": "official_notice"})) == "official_notice"


def test_resolve_unknown_returns_none():
    assert _resolve_design_profile(_plan(metadata={"document_type": "메모"})) is None
    assert _resolve_design_profile(_plan(metadata={})) is None


# --- Task 2: bridge ---
def test_bridge_maps_title_and_roles():
    dp = _bridge_to_design_plan(_plan(), "official_notice")
    assert isinstance(dp, DesignPlan)
    assert dp.profile == "official_notice"
    assert dp.title == "교육협력 사업 추진 협조 요청"
    roles = [(b.type, b.role) for b in dp.blocks]
    assert ("paragraph", "heading") in roles
    assert ("paragraph", "body") in roles


def test_bridge_level2_is_subheading():
    dp = _bridge_to_design_plan(_plan(blocks=[{"type": "heading", "level": 2, "text": "x"}]), "report")
    assert ("paragraph", "subheading") in [(b.type, b.role) for b in dp.blocks]


def test_bridge_bullets_become_body():
    dp = _bridge_to_design_plan(
        _plan(blocks=[{"type": "bullets", "items": ["가. 첫째", "나. 둘째"]}]), "official_notice"
    )
    bodies = [b.text for b in dp.blocks if b.role == "body"]
    assert "가. 첫째" in bodies and "나. 둘째" in bodies


# --- Task 3: 결문 메타 ---
def test_bridge_appends_gyeolmun():
    plan = _plan(gyeolmun={
        "issuer": "○○교육지원청교육장",
        "productionNumber": "교육협력과-123",
        "enforcementDate": "2026. 6. 27.",
        "disclosure": "공개",
    })
    dp = _bridge_to_design_plan(plan, "official_notice")
    texts = " ".join(b.text for b in dp.blocks)
    assert "○○교육지원청교육장" in texts
    assert "교육협력과-123" in texts
    assert "2026. 6. 27." in texts
    assert "공개" in texts


# --- Task 4: route (contract preserved) ---
def test_gongmun_routes_to_profile_and_opens():
    doc = create_document_from_plan(_plan())
    assert isinstance(doc, HwpxDocument)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "협조" in text
    doc.close()


def test_unknown_type_uses_from_scratch_path():
    doc = create_document_from_plan(_plan(metadata={"document_type": "메모"}))
    assert isinstance(doc, HwpxDocument)
    doc.close()
