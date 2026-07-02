# SPDX-License-Identifier: Apache-2.0
"""M7 / S-062 P2: native TOC / CROSSREF emission per the P0 contract.

Emission is verified with the P1 harness (hwpx.tools.toc_fidelity) — the
authoring surface and the fidelity harness agree by construction, mirroring
the M6 read_fidelity pattern."""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import validate_editor_open_safety
from hwpx.document import HwpxDocument
from hwpx.tools import toc_author as ta
from hwpx.tools import toc_fidelity as tf
from hwpx.tools.roundtrip_diff import roundtrip_report

GOLD_A = Path(__file__).resolve().parent / "fixtures" / "m7_toc_gold" / "hancom-native-toc-A.hwpx"


def _doc_with_headings(count: int = 3) -> tuple[HwpxDocument, list]:
    doc = HwpxDocument.new()
    headings = []
    for i in range(1, count + 1):
        h = doc.add_paragraph(f"개요 {i}번 제목")
        headings.append(h)
        doc.add_paragraph(f"{i}번 제목의 본문입니다. " * 20)
    return doc, headings


# ── anchors ──────────────────────────────────────────────────────────
def test_outline_heading_detection_on_gold():
    doc = HwpxDocument.open(GOLD_A)
    detected = ta.outline_heading_paragraphs(doc)
    assert len(detected) == 4
    assert [lvl for _p, lvl, _t in detected] == [1, 1, 1, 1]
    assert all("개요" in text for _p, _lvl, text in detected)


def test_ensure_anchor_id_rewrites_shared_constant():
    doc, headings = _doc_with_headings(2)
    for h in headings:
        h.element.set("id", "2147483648")  # the shared generated-paragraph constant
    ids = {ta.ensure_paragraph_anchor_id(doc, h) for h in headings}
    assert len(ids) == 2
    assert "2147483648" not in ids


# ── native TOC emission, verified by the P1 harness ──────────────────
def test_emit_native_toc_roundtrips_through_harness():
    doc, headings = _doc_with_headings(3)
    summary = ta.add_native_toc(doc, headings=headings)
    assert summary["entryCount"] == 3

    reopened = HwpxDocument.open(doc.to_bytes())
    model = tf.parse_toc_model(reopened)
    assert model.toc_field_id is not None
    assert model.toc_command and "ContentsLevel:int:2" in model.toc_command
    assert len(model.entries) == 3
    assert [e.cached_page for e in model.entries] == [1, 1, 1]  # honest estimates
    report = tf.structural_report(reopened)
    assert report["hasNativeToc"] is True
    assert report["targetsResolve"] is True
    assert report["internally_consistent"] is True


def test_emit_crossref_roundtrips_through_harness():
    doc, headings = _doc_with_headings(3)
    ref_holder = doc.add_paragraph("자세한 내용은 참조: ")
    result = ta.add_page_crossref(doc, ref_holder, headings[1], cached_page=2)

    reopened = HwpxDocument.open(doc.to_bytes())
    model = tf.parse_toc_model(reopened)
    assert [c.cached_page for c in model.crossrefs] == [2]
    assert model.crossrefs[0].target_id == result["targetId"]
    assert model.crossrefs[0].ref_content_type == "OBJECT_TYPE_PAGE"
    assert tf.structural_report(reopened)["targetsResolve"] is True


def test_emitted_command_dsl_matches_gold_contract():
    doc, headings = _doc_with_headings(2)
    ta.add_native_toc(doc, headings=headings, level=2, leader=3, hyperlink=True)
    model = tf.parse_toc_model(HwpxDocument.open(doc.to_bytes()))
    gold = tf.parse_toc_model(GOLD_A)
    assert model.toc_command == gold.toc_command  # verbatim contract replication


def test_toc_plus_crossref_shared_target_consistency_check_works():
    """Emit both against the same heading with DIFFERENT cached pages — the
    harness's oracle-free conflict detector must flag it (and agreeing caches
    must pass), proving our emission feeds the stale detector correctly."""
    doc, headings = _doc_with_headings(3)
    ta.add_native_toc(doc, headings=headings)  # entries cached at 1
    holder = doc.add_paragraph("참조 ")
    ta.add_page_crossref(doc, holder, headings[0], cached_page=9)  # conflict
    report = tf.structural_report(HwpxDocument.open(doc.to_bytes()))
    assert report["internally_consistent"] is False

    doc2, headings2 = _doc_with_headings(3)
    ta.add_native_toc(doc2, headings=headings2)
    holder2 = doc2.add_paragraph("참조 ")
    ta.add_page_crossref(doc2, holder2, headings2[0], cached_page=1)  # agrees
    report2 = tf.structural_report(HwpxDocument.open(doc2.to_bytes()))
    assert report2["internally_consistent"] is True


# ── safety + structural round-trip guards ────────────────────────────
def test_emitted_document_is_editor_open_safe():
    doc, headings = _doc_with_headings(3)
    ta.add_native_toc(doc, headings=headings)
    holder = doc.add_paragraph("참조 ")
    ta.add_page_crossref(doc, holder, headings[2], cached_page=1)
    report = validate_editor_open_safety(doc.to_bytes())
    ok = getattr(report, "ok", None)
    if ok is None and isinstance(report, dict):
        ok = report.get("ok")
    assert ok is True, report


def test_emitted_fields_survive_structural_roundtrip():
    doc, headings = _doc_with_headings(3)
    ta.add_native_toc(doc, headings=headings)
    holder = doc.add_paragraph("참조 ")
    ta.add_page_crossref(doc, holder, headings[0], cached_page=1)
    report = roundtrip_report(doc.to_bytes())
    assert report["reopened"] is True
    assert report["lost_elements"] == {}, report["lost_elements"]
    # field skeleton intact after round-trip
    assert report["after_counts"].get("fieldBegin", 0) >= 5  # 1 TOC + 3 entries + 1 xref
    assert report["after_counts"].get("fieldEnd", 0) >= 5
    assert report["after_counts"].get("tab", 0) >= 3


def test_native_toc_dirty_default_and_mark_toc_dirty():
    """dirty=1 is the measured re-number trigger (Hancom regenerates the region
    on open); authored TOCs default to it, and mark_toc_dirty re-arms it."""
    from lxml import etree as LET

    _HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

    def toc_dirty(doc):
        for sec in doc.oxml.sections:
            for fb in sec.element.iter(f"{_HP}fieldBegin"):
                if fb.get("type") == "TABLEOFCONTENTS":
                    return fb.get("dirty")
        return None

    doc, headings = _doc_with_headings(2)
    ta.add_native_toc(doc, headings=headings)
    assert toc_dirty(doc) == "1"  # default: first Hancom open recomputes

    doc2, headings2 = _doc_with_headings(2)
    ta.add_native_toc(doc2, headings=headings2, dirty=False)
    assert toc_dirty(doc2) == "0"
    assert ta.mark_toc_dirty(doc2) == 1
    assert toc_dirty(doc2) == "1"


def test_parse_plain_regenerated_entries_inside_region():
    """Hancom's ContentsHyperlink:0 regeneration emits PLAIN entries (no
    HYPERLINK field) — the harness must still see them inside the TOC region."""
    doc, headings = _doc_with_headings(2)
    ta.add_native_toc(doc, headings=headings, hyperlink=False)
    # strip the HYPERLINK wrappers to simulate Hancom's plain regeneration
    from lxml import etree as LET

    _HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    for sec in doc.oxml.sections:
        for fb in list(sec.element.iter(f"{_HP}fieldBegin")):
            if fb.get("type") == "HYPERLINK":
                ctrl = fb.getparent()
                run = ctrl.getparent()
                run.remove(ctrl)
    model = tf.parse_toc_model(HwpxDocument.open(doc.to_bytes()))
    assert len(model.entries) == 2
    assert all(e.target_id is None for e in model.entries)  # identity by title
    assert all(e.cached_page == 1 for e in model.entries)
