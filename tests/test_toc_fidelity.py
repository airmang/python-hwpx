# SPDX-License-Identifier: Apache-2.0
"""M7 / S-062 P1: native TOC / cross-reference fidelity harness.

Ground truth = owner-authored Hancom gold pair (tests/fixtures/m7_toc_gold/):
A = fresh TOC (entries 1,2,2,3; CROSSREF cached 2), B = after body growth with
NO 차례 새로 고침 (CROSSREF auto-recomputed to 3; TOC entries stale).
No live Hancom render in this suite — the oracle leg is exercised with
synthetic word boxes (S-060 discipline: live render is HWPX_MAC_ORACLE_SMOKE).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools import toc_fidelity as tf

GOLD = Path(__file__).resolve().parent / "fixtures" / "m7_toc_gold"
A = GOLD / "hancom-native-toc-A.hwpx"
B = GOLD / "hancom-native-toc-B.hwpx"

TARGET_HEADING_2 = "56578352"  # "개요 두 번째" — the CROSSREF target


# ── parsing the captured contract ────────────────────────────────────
def test_parse_native_toc_field_and_command():
    model = tf.parse_toc_model(A)
    assert model.toc_field_id is not None
    assert model.toc_command and model.toc_command.startswith("TableOfContents:set:")
    assert "ContentsLeader" in model.toc_command


def test_parse_entries_titles_and_pages_incl_nested_tab():
    model = tf.parse_toc_model(A)
    assert len(model.entries) == 4
    pages = [e.cached_page for e in model.entries]
    assert pages == [1, 2, 2, 3]
    assert all("개요" in e.title for e in model.entries)
    assert all(e.target_id and e.target_id.isdigit() for e in model.entries)


def test_parse_crossref_cached_result_run():
    a = tf.parse_toc_model(A)
    b = tf.parse_toc_model(B)
    assert [c.cached_page for c in a.crossrefs] == [2]
    assert [c.cached_page for c in b.crossrefs] == [3]  # auto-recomputed by Hancom
    assert a.crossrefs[0].target_id == TARGET_HEADING_2
    assert a.crossrefs[0].ref_content_type == "OBJECT_TYPE_PAGE"


def test_anchor_targets_resolve_to_paragraph_ids():
    report = tf.structural_report(A)
    assert report["hasNativeToc"] is True
    assert report["targetsResolve"] is True
    assert report["unresolvedTargets"] == []


# ── stale detection without any oracle ───────────────────────────────
def test_fresh_doc_is_internally_consistent():
    report = tf.structural_report(A)
    assert report["internally_consistent"] is True


def test_stale_toc_detected_structurally_via_crossref_conflict():
    """B: CROSSREF says 개요2 is on page 3, TOC entry still says 2 — conflict."""
    report = tf.structural_report(B)
    assert report["internally_consistent"] is False
    conflict = report["internal_conflicts"][0]
    assert conflict["targetId"] == TARGET_HEADING_2
    assert conflict["tocCachedPage"] == 2
    assert conflict["crossrefCachedPage"] == 3


def test_toc_verify_degrades_honestly_without_oracle():
    fresh = tf.toc_verify(A)
    assert fresh["render_checked"] is False
    assert fresh["verdict"] == "unverified"
    stale = tf.toc_verify(B)
    assert stale["verdict"] == "stale_detected_structurally"


# ── repagination trigger ─────────────────────────────────────────────
def test_grow_paragraph_lengthens_target():
    doc = HwpxDocument.open(A)

    def target_len(d):
        return next(
            len(p.text or "")
            for s in d.sections
            for p in s.paragraphs
            if "본문입니다" in (p.text or "")
        )

    before = target_len(doc)
    assert tf.grow_paragraph(doc, contains="본문입니다", added_chars=1500)
    assert target_len(doc) >= before + 1400
    # survives a save/reopen round-trip
    reopened = HwpxDocument.open(doc.to_bytes())
    assert target_len(reopened) >= before + 1400


# ── oracle leg with synthetic render (deterministic, no Hancom) ──────
def _fake_boxes(pages: dict[int, list[str]]):
    """Build word boxes where each string in a page's list is its own LINE."""
    from hwpx.form_fit.wordbox import WordBox

    boxes = []
    for page, lines in pages.items():
        for line_no, line in enumerate(lines):
            for word_no, word in enumerate(line.split()):
                boxes.append(
                    WordBox(
                        x0=word_no, y0=line_no, x1=word_no + 1, y1=line_no + 1,
                        text=word, page=page, block=0, line=line_no, word_no=word_no,
                    )
                )
    return boxes


def _synthetic_pages(model, actual_pages: dict[str, int]) -> dict[int, list[str]]:
    """TOC page 0 carries entry-like lines (title + leader + page digits) and
    body-echo lines — both must NOT match; headings render as their own line
    with an outline-number prefix on their actual page."""
    titles = {e.target_id: model.paragraph_texts[e.target_id] for e in model.entries}
    pages: dict[int, list[str]] = {0: ["< 제목 차례 >"]}
    for i, entry in enumerate(model.entries, start=1):
        pages[0].append(f"{i}. {titles[entry.target_id]} ..... {entry.cached_page}")
    for i, (tid, page) in enumerate(sorted(actual_pages.items(), key=lambda kv: kv[1]), start=1):
        pages.setdefault(page - 1, []).append(f"{i}. {titles[tid]}")
        pages[page - 1].append(f"{titles[tid]}의 본문입니다 본문이 이어집니다")  # body echo
    return pages


def test_oracle_leg_verified_when_cached_matches_render(monkeypatch):
    model = tf.parse_toc_model(A)
    actual = {e.target_id: e.cached_page for e in model.entries}
    monkeypatch.setattr(
        "hwpx.form_fit.wordbox.extract_word_boxes",
        lambda pdf, **kw: _fake_boxes(_synthetic_pages(model, actual)),
    )
    report = tf.toc_verify(A, pdf_path="synthetic.pdf")
    assert report["render_checked"] is True
    assert report["toc_correctness_ratio"] == 1.0
    assert report["crossref_correctness_ratio"] == 1.0
    assert report["verdict"] == "verified"


def test_oracle_leg_detects_stale_after_page_shift(monkeypatch):
    """B's real layout: 개요2 now renders on page 3 while the TOC still says 2."""
    model = tf.parse_toc_model(B)
    actual = {"56578383": 1, "56578352": 3, "56578353": 3, "56578361": 4}
    monkeypatch.setattr(
        "hwpx.form_fit.wordbox.extract_word_boxes",
        lambda pdf, **kw: _fake_boxes(_synthetic_pages(model, actual)),
    )
    report = tf.toc_verify(B, pdf_path="synthetic.pdf")
    assert report["render_checked"] is True
    assert report["verdict"] == "stale"
    assert report["toc_correctness_ratio"] < 1.0
    stale_targets = {row["targetId"] for row in report["stale_entries"]}
    assert TARGET_HEADING_2 in stale_targets
    # the auto-recomputed CROSSREF stays correct even while the TOC is stale
    assert report["crossref_correctness_ratio"] == 1.0


def test_heading_line_matching_rejects_toc_entries_and_body_echo(monkeypatch):
    """The two real-render false-match modes must stay dead: a TOC entry line
    (trailing leader+digits) and a body echo (line continues past the title)
    never count as the heading's page."""
    pages = {
        0: ["< 제목 차례 >", "1. 개요 첫 번째 ..... 1", "개요 첫 번째의 본문입니다"],
        3: ["1. 개요 첫 번째"],
    }
    monkeypatch.setattr(
        "hwpx.form_fit.wordbox.extract_word_boxes", lambda pdf, **kw: _fake_boxes(pages)
    )
    result = tf.heading_rendered_pages("synthetic.pdf", {"x": "개요 첫 번째"})
    assert result == {"x": 4}  # only the real heading line on fitz page 3 -> page 4


# ── live Hancom render smoke (opt-in only — never in the default suite) ─
@pytest.mark.skipif(
    __import__("os").environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the TOC render smoke",
)
def test_live_oracle_detects_fresh_vs_stale_toc():
    from hwpx.visual.oracle import resolve_oracle

    oracle = resolve_oracle()
    assert oracle.available(), "no Hancom render backend reachable"
    fresh = tf.toc_verify(A, oracle=oracle)
    assert fresh["render_checked"] is True
    assert fresh["verdict"] == "verified", fresh
    stale = tf.toc_verify(B, oracle=oracle)
    assert stale["render_checked"] is True
    assert stale["verdict"] == "stale", stale
