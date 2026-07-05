# SPDX-License-Identifier: Apache-2.0
"""Form-fill quality scorer (evalplan GOAL loop fitness function).

Fixtures are in-repo public forms (province blank form + corpus tables) — the
owner's gold/filled material is NOT vendored (PII). The gold integration test is
gated on a local path and skips in CI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hwpx.formfill_quality import (
    MEASURED,
    NEEDS_REVIEW,
    UNVERIFIED,
    detect_overflow_crossings,
    score_compliance,
    score_content,
    score_form_fill,
    score_format_fidelity,
    score_structure,
    _classify,
    _skeleton,
    _tables,
)
from hwpx.table_patch import fill_cells

FIXT = Path(__file__).parent / "fixtures"
BLANK = FIXT / "m105_evalplan" / "blank_form_3hak.hwpx"
CORPUS_TABLE = FIXT / "m2_corpus" / "public_official_table.hwpx"


# --------------------------------------------------------------------------- #
# A. overflow detector (synthetic PDF — no oracle needed)
# --------------------------------------------------------------------------- #

def _has_fitz() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_fitz(), reason="PyMuPDF unavailable")
def test_overflow_crossing_detects_text_over_border(tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    # vertical cell border at x=100, spanning the text's vertical band
    page.draw_line(fitz.Point(100, 40), fitz.Point(100, 160))
    # word that straddles the border (overflow) and one safely inside a cell
    page.insert_text(fitz.Point(92, 100), "OVER", fontsize=14)   # starts left, extends right past 100
    page.insert_text(fitz.Point(130, 130), "SAFE", fontsize=10)  # entirely right of the border
    pdf = tmp_path / "synthetic.pdf"
    doc.save(str(pdf))
    doc.close()

    incidents = detect_overflow_crossings(pdf)
    texts = {i["text"] for i in incidents}
    assert "OVER" in texts
    assert "SAFE" not in texts


@pytest.mark.skipif(not _has_fitz(), reason="PyMuPDF unavailable")
def test_overflow_clean_page_zero_crossings(tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.draw_line(fitz.Point(100, 40), fitz.Point(100, 160))
    page.insert_text(fitz.Point(20, 100), "LEFT", fontsize=10)   # left cell
    page.insert_text(fitz.Point(130, 100), "RIGHT", fontsize=10)  # right cell
    pdf = tmp_path / "clean.pdf"
    doc.save(str(pdf))
    doc.close()
    assert detect_overflow_crossings(pdf) == []


# --------------------------------------------------------------------------- #
# B. byte fidelity
# --------------------------------------------------------------------------- #

def test_format_fidelity_blank_self_is_full():
    """A doc identical to blank carries every table verbatim -> full B."""
    a = score_format_fidelity(BLANK, BLANK)
    assert a.key == "B" and a.status == MEASURED
    assert a.detail["carry_rate"] == 1.0
    assert a.score == a.weight


def test_format_fidelity_byte_preserving_edit_stays_high():
    """A single spliced cell keeps every other table verbatim and reuses the
    blank's formatting vocabulary -> B stays high (byte-preservation)."""
    data = BLANK.read_bytes()
    # fill one real cell of the 교수학습 운영 table (#02) by address
    res = fill_cells(data, [{"table_index": 2, "row": 1, "col": 2, "text": "단원 채움"}])
    edited = res.data
    a = score_format_fidelity(edited, BLANK)
    assert a.score > 0.8 * a.weight, a.findings
    assert a.detail["carried"] >= len(_tables(BLANK)) - 2


def test_format_fidelity_regeneration_scores_low():
    """A document sharing no table bytes with blank reads as regenerated."""
    a = score_format_fidelity(CORPUS_TABLE, BLANK)
    assert a.detail["carried"] == 0
    assert a.score < 0.5 * a.weight
    assert any("REGENERATION" in f or "regenerated" in f for f in a.findings)


# --------------------------------------------------------------------------- #
# C. structure conformance
# --------------------------------------------------------------------------- #

def test_structure_self_is_full():
    a = score_structure(BLANK, BLANK)
    assert a.key == "C" and a.score == a.weight


def test_structure_counts_use_content_expected_not_gold():
    """Counts are matched to the content-derived `expected`, not gold's counts —
    a cross-semester fill has different block counts than the 1학기 gold."""
    # produced == blank (so its own counts), gold == blank too. Force an
    # `expected` that disagrees with the actual counts -> those checks fail,
    # proving `expected` (not gold) drives the count checks.
    real = _skeleton(BLANK)["kinds"]
    bogus = {"achievement": real.get("achievement", 0) + 5,
             "level": real.get("level", 0) + 5,
             "rubric": real.get("rubric", 0) + 5,
             "achieve_rate": real.get("achieve_rate", 0)}
    a = score_structure(BLANK, BLANK, expected=bogus)
    assert any("content-expected" in f for f in a.findings)
    # with matching expected, count checks pass
    ok = score_structure(BLANK, BLANK, expected=real)
    assert ok.score >= a.score


def test_structure_blank_vs_itself_kinds_present():
    """The blank form still carries the red/optional tables + 정기시험 column."""
    sk = _skeleton(BLANK)
    assert sk["ratio_has_regular_exam"] is True          # 정기시험 column present
    kinds = sk["kinds"]
    assert kinds.get("seokcha", 0) >= 1                  # 석차등급 red table present
    assert kinds.get("submit", 0) >= 1                   # 제출 red table present


# --------------------------------------------------------------------------- #
# D / E
# --------------------------------------------------------------------------- #

def test_content_axis_runs_and_reports():
    a = score_content(BLANK)
    assert a.key == "D" and a.status == MEASURED
    assert 0 <= a.score <= a.weight


def test_content_foreign_sample_penalty(tmp_path):
    """A produced file that still holds the blank's sample standard codes (not in
    the review MD) is penalised -- content must REPLACE samples, not add beside."""
    md = tmp_path / "c.md"
    md.write_text("[12신규01-01] 신규 표준 하나", encoding="utf-8")
    # blank scored against a review whose codes it does not contain, with blank as
    # the sample reference -> every blank code is 'foreign' and still present.
    a = score_content(BLANK, content=str(md), blank=BLANK)
    assert a.detail["leftover_sample_frac"] > 0.5
    assert a.detail["content_match"] == 0.0


def test_compliance_flags_regular_exam_on_blank():
    """Blank still has the 정기시험 column -> the gold-calibrated lint flags it."""
    a = score_compliance(BLANK)
    assert a.key == "E" and a.status == NEEDS_REVIEW
    assert any("정기시험" in f for f in a.findings)


# --------------------------------------------------------------------------- #
# top-level
# --------------------------------------------------------------------------- #

def test_score_form_fill_structural_only_no_oracle():
    """run_render=False -> A is unverified (never a silent pass), other axes score."""
    sc = score_form_fill(BLANK, BLANK, BLANK, run_render=False)
    a = sc.axis("A")
    assert a.status == UNVERIFIED and a.score == 0.0
    assert sc.axis("B").score == sc.axis("B").weight        # blank carries itself
    assert not sc.render_checked
    # lowest_axis excludes the unverified A (you fix the oracle, not the content),
    # so diagnosis points at a measured axis:
    assert sc.lowest_axis().status != UNVERIFIED
    assert sc.to_dict()["lowest_axis"] != "A"


# --------------------------------------------------------------------------- #
# gold integration (local only — owner PII, skipped in CI)
# --------------------------------------------------------------------------- #

_GOLD = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/01_참고_기제출본/2026_1학기_3학년_인공지능기초.hwpx"))
_LOCAL_BLANK = Path(os.path.expanduser(
    "~/School/Prep/2학기_평가계획/00_원본_양식_유의사항/양식_3학년_2학기.hwpx"))


@pytest.mark.skipif(not (_GOLD.exists() and _LOCAL_BLANK.exists()),
                    reason="owner-local gold/blank not present (PII, not vendored)")
def test_gold_self_structural_ceiling():
    """Gold matches its own skeleton (C=20) and content (D=15); B is low by design
    (gold was re-serialised by Hancom, so it is not byte-identical to blank)."""
    sc = score_form_fill(_GOLD, _GOLD, _LOCAL_BLANK, run_render=False)
    assert sc.axis("C").score == sc.axis("C").weight
    assert sc.axis("D").score == sc.axis("D").weight
    assert sc.axis("B").score < 0.6 * sc.axis("B").weight   # by-design low
    assert sc.lowest_axis().key == "B"
