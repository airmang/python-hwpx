# SPDX-License-Identifier: Apache-2.0
"""M9-full P1 (specs/010 FR-005): plan-v2 native auto-TOC option.

``{"type": "toc", "native": true}`` must lower to the M7 Hancom-native
TABLEOFCONTENTS field (dirty=1 -> Hancom regenerates entries+pages on open,
measured in S-062) instead of the static ``text\\tpage`` BuilderToc, and must
enforce the measured ContentsStyles trap: body text may not sit on style 0
(바탕글) when a native TOC is present or Hancom collects it as TOC entries.
Plans without ``native`` keep today's static output byte-for-byte semantics.
"""
from __future__ import annotations

import pytest

from hwpx import create_document_from_plan, validate_document_plan
from hwpx.document import HwpxDocument
from hwpx.tools import toc_fidelity as tf
from hwpx.tools.package_validator import validate_editor_open_safety

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
PLAN_V2 = "hwpx.document_plan.v2"

_DEFAULT_BLOCKS = [
    {"type": "heading", "level": 1, "text": "추진 배경"},
    {"type": "paragraph", "text": "추진 배경에 대한 본문입니다."},
    {"type": "heading", "level": 1, "text": "추진 계획"},
    {"type": "paragraph", "text": "추진 계획에 대한 본문입니다."},
]


def _plan(toc_block, blocks=None):
    all_blocks = ([toc_block] if toc_block else []) + (
        list(blocks) if blocks is not None else list(_DEFAULT_BLOCKS)
    )
    return {"schemaVersion": PLAN_V2, "sections": [{"blocks": all_blocks}]}


def _toc_field_begins(document: HwpxDocument) -> list:
    found = []
    for section in document.oxml.sections:
        for begin in section.element.iter(f"{HP}fieldBegin"):
            if begin.get("type") == "TABLEOFCONTENTS":
                found.append(begin)
    return found


def _section_paragraph_elements(document: HwpxDocument) -> list:
    return list(document.oxml.sections[0].element.findall(f"{HP}p"))


def _own_text(p_el) -> str:
    """Paragraph text from direct runs; hp:tab (sibling or nested) -> '\\t'."""
    parts = []
    for run in p_el.findall(f"{HP}run"):
        for node in run:
            if node.tag == f"{HP}tab":
                parts.append("\t")
                parts.append(node.tail or "")
            elif node.tag == f"{HP}t":
                parts.append(node.text or "")
                for child in node:
                    if child.tag == f"{HP}tab":
                        parts.append("\t")
                    parts.append(child.tail or "")
    return "".join(parts)


# ── (a) native:true -> TABLEOFCONTENTS field with dirty=1 ────────────
def test_native_toc_plan_emits_tableofcontents_field_with_dirty():
    plan = _plan({"type": "toc", "native": True})
    document = create_document_from_plan(plan)
    begins = _toc_field_begins(document)
    assert len(begins) == 1
    assert begins[0].get("dirty") == "1"  # measured open-time regeneration trigger

    reopened = HwpxDocument.open(document.to_bytes())
    model = tf.parse_toc_model(reopened)
    assert model.toc_field_id is not None
    assert len(model.entries) == 2  # both outline headings collected
    assert "추진 배경" in model.entries[0].title
    assert "추진 계획" in model.entries[1].title
    report = tf.structural_report(reopened)
    assert report["hasNativeToc"] is True
    assert report["targetsResolve"] is True

    # no static plaintext TOC lines alongside the native field
    static_lines = {"추진 배경\t1", "추진 계획\t2", "목차"}
    texts = {_own_text(p) for p in _section_paragraph_elements(document)}
    assert not (texts & static_lines)


def test_native_toc_plan_output_is_editor_open_safe():
    document = create_document_from_plan(_plan({"type": "toc", "native": True}))
    report = validate_editor_open_safety(document.to_bytes())
    ok = getattr(report, "ok", None)
    if ok is None and isinstance(report, dict):
        ok = report.get("ok")
    assert ok is True, report


def test_native_toc_options_flow_through():
    plan = _plan({"type": "toc", "native": True, "dirty": False, "hyperlink": False})
    document = create_document_from_plan(plan)
    begins = _toc_field_begins(document)
    assert len(begins) == 1
    assert begins[0].get("dirty") == "0"
    model = tf.parse_toc_model(HwpxDocument.open(document.to_bytes()))
    assert model.toc_command and "ContentsHyperlink:bool:0" in model.toc_command


def test_native_toc_inserted_at_block_position():
    plan = _plan(
        None,
        blocks=[
            {"type": "heading", "level": 1, "text": "머리 제목"},
            {"type": "toc", "native": True},
            {"type": "heading", "level": 1, "text": "꼬리 제목"},
        ],
    )
    document = create_document_from_plan(plan)
    paragraphs = _section_paragraph_elements(document)
    toc_open_index = next(
        index
        for index, p_el in enumerate(paragraphs)
        if any(
            begin.get("type") == "TABLEOFCONTENTS"
            for begin in p_el.iter(f"{HP}fieldBegin")
        )
    )
    head_index = next(i for i, p in enumerate(paragraphs) if _own_text(p) == "머리 제목")
    tail_index = next(i for i, p in enumerate(paragraphs) if _own_text(p) == "꼬리 제목")
    assert head_index < toc_open_index < tail_index
    # both headings are still collected as entries regardless of position
    model = tf.parse_toc_model(HwpxDocument.open(document.to_bytes()))
    assert len(model.entries) == 2


# ── (b) static default unchanged ─────────────────────────────────────
def test_static_toc_default_unchanged():
    entries = [{"level": 1, "text": "추진 배경", "page": "1"}]
    for toc_block in (
        {"type": "toc", "entries": entries},
        {"type": "toc", "entries": entries, "native": False},
    ):
        document = create_document_from_plan(_plan(toc_block))
        assert _toc_field_begins(document) == []
        texts = [_own_text(p) for p in _section_paragraph_elements(document)]
        assert "목차" in texts
        assert "추진 배경\t1" in texts
        # static body text keeps today's style-0 assignment (no churn)
        body = [p for p in _section_paragraph_elements(document) if "본문입니다" in _own_text(p)]
        assert body
        assert all(p.get("styleIDRef") == "0" for p in body)


# ── (c) ContentsStyles trap: body must leave style 0 under a native TOC ──
def test_native_toc_routes_body_off_collected_style0():
    document = create_document_from_plan(_plan({"type": "toc", "native": True}))
    paragraphs = _section_paragraph_elements(document)

    body = [p for p in paragraphs if "본문입니다" in _own_text(p)]
    assert body
    # measured M7 trap: ContentsStyles:wstring:0: collects style-0 paragraphs,
    # so composed body text must sit on 본문 (style 1 in the skeleton).
    assert all(p.get("styleIDRef") == "1" for p in body)
    # paraPrIDRef untouched -> visual formatting identical to the static path
    assert all(p.get("paraPrIDRef") == "0" for p in body)

    # headings keep their outline styles (they are the TOC's entry source)
    headings = [p for p in paragraphs if _own_text(p) in {"추진 배경", "추진 계획"}]
    assert headings
    assert all(p.get("styleIDRef") == "2" for p in headings)  # 개요 1

    # the TOC region's own paragraphs stay on style 0 per the gold contract
    toc_region = [
        p
        for p in paragraphs
        if any(True for _ in p.iter(f"{HP}fieldBegin"))
        or any(True for _ in p.iter(f"{HP}fieldEnd"))
    ]
    assert toc_region
    assert all(p.get("styleIDRef") == "0" for p in toc_region)


# ── (d) plan validation accepts (and type-checks) the native key ─────
def test_validation_accepts_native_key():
    assert validate_document_plan(_plan({"type": "toc", "native": True})).ok is True
    assert validate_document_plan(_plan({"type": "toc", "native": False})).ok is True


def test_validation_rejects_non_boolean_native():
    report = validate_document_plan(_plan({"type": "toc", "native": "yes"}))
    assert report.ok is False
    assert any(issue.code == "invalid_native_flag" for issue in report.issues)


# ── honest failure modes ─────────────────────────────────────────────
def test_native_toc_without_headings_raises():
    plan = _plan(
        {"type": "toc", "native": True},
        blocks=[{"type": "paragraph", "text": "제목 없는 본문뿐입니다."}],
    )
    with pytest.raises(ValueError, match="no outline headings"):
        create_document_from_plan(plan)


def test_multiple_native_tocs_raise():
    plan = _plan(
        None,
        blocks=[
            {"type": "toc", "native": True},
            {"type": "heading", "level": 1, "text": "추진 배경"},
            {"type": "toc", "native": True},
        ],
    )
    with pytest.raises(ValueError, match="native TOC"):
        create_document_from_plan(plan)


# ── builder-node surface (what the plan lowers to) ───────────────────
def test_builder_native_toc_node_direct():
    from hwpx.builder.core import Document, Heading, NativeToc, Paragraph, Section

    builder = Document(
        sections=[
            Section(
                children=[
                    NativeToc(),
                    Heading(level=1, text="첫 번째 제목"),
                    Paragraph(text="본문 문단입니다."),
                ]
            )
        ]
    )
    assert builder.feature_flags()["toc"] is True
    document = builder.lower()
    assert len(_toc_field_begins(document)) == 1
    model = tf.parse_toc_model(HwpxDocument.open(document.to_bytes()))
    assert len(model.entries) == 1
    assert "첫 번째 제목" in model.entries[0].title
