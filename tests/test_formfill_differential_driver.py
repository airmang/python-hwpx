# SPDX-License-Identifier: Apache-2.0
"""Form-fill differential corpus driver tests (M9-full P3, specs/010 FR-004).

Covers the :class:`PrerenderedOracle` shim (mapping, copy semantics, the
``None``-on-unmapped degrade contract), parity of the driver's composed verdict
with the shipped ``verify_form_fill_differential`` decision, the per-pair
honesty buckets (``no_render`` / ``no_blank_render`` / ``render_failure`` /
``clip_undetectable``), the once-per-unique-blank geometry cache, and the pure
aggregation math (verified-only denominators + rule-of-three lower bounds +
fail-closed exit 3). PDF fixtures reuse the synthetic builders from
``tests/test_form_fit_wordbox.py`` (no Hancom needed anywhere here).
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from hwpx.form_fit import wordbox as wb
from tests.test_form_fit_wordbox import _layout_pdf, _overlap_pdf

# Load scripts/corpus_formfill_differential.py as a module (scripts/ is not a
# package) — same pattern as tests/test_openrate.py.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_formfill_differential", _SCRIPTS / "corpus_formfill_differential.py"
)
assert _spec is not None and _spec.loader is not None
cfd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfd)

needs_fitz = pytest.mark.skipif(
    not wb.fitz_available(), reason="PyMuPDF (fitz) not installed"
)


def _prose_pdf(path, *, lines=3):
    """A table-free PDF: find_tables detects nothing -> clip-undetectable tier."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    for i in range(lines):
        page.insert_text((40, 50 + 20 * i), f"prose line {i}", fontsize=11)
    doc.save(str(path))
    doc.close()


def _record(blank, filled, rid="pair-1", *, produced=True):
    return {
        "id": rid,
        "bucket": "form-fit",
        "produced": produced,
        "input_path": str(blank),
        "output_path": str(filled),
    }


def _manifest(tmp_path, records):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schemaVersion": 1, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# --- PrerenderedOracle shim: mapping + degrade contract ----------------------

@needs_fitz
def test_shim_serves_mapped_pdf_and_copies(tmp_path):
    pdf = tmp_path / "b.pdf"
    _layout_pdf(pdf, pages=1, rows=2, cols=2)
    oracle = cfd.PrerenderedOracle({"b.hwpx": str(pdf)})
    assert oracle.available() is True
    # mapping is by source BASENAME, path-independent; no out -> the frozen PDF itself
    assert oracle.render_pdf("/some/dir/b.hwpx") == str(pdf)
    # with an out path the caller owns the copy (verify_* pre-deletes/removes it)
    out = tmp_path / "staged" / "out.pdf"
    out.parent.mkdir()
    got = oracle.render_pdf("/other/dir/b.hwpx", str(out))
    assert got == str(out)
    assert out.read_bytes() == pdf.read_bytes()


def test_shim_unmapped_or_missing_pdf_returns_none(tmp_path):
    oracle = cfd.PrerenderedOracle({})
    assert oracle.available() is True  # the shim IS reachable; the SOURCE is unmapped
    assert oracle.render_pdf("nope.hwpx") is None
    # mapped but the PDF vanished/empty on disk -> same degrade, never a crash
    gone = cfd.PrerenderedOracle({"gone.hwpx": str(tmp_path / "missing.pdf")})
    assert gone.render_pdf("gone.hwpx") is None
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert cfd.PrerenderedOracle({"e.hwpx": str(empty)}).render_pdf("e.hwpx") is None
    assert oracle.render_many([("x.hwpx", str(tmp_path / "o.pdf"))]) == {"x.hwpx": None}


def test_shim_degrades_verify_differential_to_unverified():
    # The real oracle contract: render_pdf -> None makes verify_* degrade to an
    # honest unverified verdict (never a silent pass, never a raise).
    v = wb.verify_form_fill_differential(
        "unmapped_blank.hwpx", "unmapped_filled.hwpx", oracle=cfd.PrerenderedOracle({})
    )
    assert v.render_checked is False and v.ok is False
    assert "unverified" in v.note


# --- parity: composed verdict == shipped verify_form_fill_differential -------

@needs_fitz
def test_composed_verdict_matches_shipped_function(tmp_path):
    # The driver composes the decision from pure functions (blank cached); the
    # shipped hot path must yield the IDENTICAL verdict through the shim.
    blank_pdf = tmp_path / "blank.pdf"
    filled_pdf = tmp_path / "filled.pdf"
    _overlap_pdf(blank_pdf, extra=False)
    _overlap_pdf(filled_pdf, extra=True)  # the fill introduced one new over-print
    oracle = cfd.PrerenderedOracle(
        {"b.hwpx": str(blank_pdf), "f.hwpx": str(filled_pdf)}
    )
    shipped = wb.verify_form_fill_differential("b.hwpx", "f.hwpx", oracle=oracle)
    composed = cfd.differential_verdict(
        cfd._extract_geometry(str(blank_pdf)), cfd._extract_geometry(str(filled_pdf))
    )
    assert composed.to_dict() == shipped.to_dict()
    assert composed.overlap_detected is True and composed.ok is False


# --- driver end-to-end: pass pair -------------------------------------------

@needs_fitz
def test_driver_pass_pair_and_report_math(tmp_path):
    blank_dir = tmp_path / "blanks"
    filled_dir = tmp_path / "filled"
    blank_dir.mkdir()
    filled_dir.mkdir()
    # blank rendered by the box leg with its NNN_ batch prefix; filled by stem
    _layout_pdf(blank_dir / "000_form_a.pdf", pages=1, rows=3, cols=2)
    _layout_pdf(filled_dir / "formfit-form_a-medium.pdf", pages=1, rows=3, cols=2)
    manifest = _manifest(
        tmp_path,
        [
            _record(
                "/corpus/downloads/form_a.hwpx",
                "/corpus/form-fit/formfit-form_a-medium.hwpx",
            )
        ],
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        [
            "--manifest", str(manifest),
            "--blank-pdf-dir", str(blank_dir),
            "--filled-pdf-dir", str(filled_dir),
            "--out", str(out),
        ]
    )
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    (pair,) = report["pairs"]
    assert pair["status"] == "verified" and pair["ok"] is True
    assert pair["newOverflow"] == 0
    assert pair["layoutStable"] is True
    assert pair["newOverlap"] == 0
    assert pair["overflowChecked"] is True and pair["overflowTier"] == "checked"
    totals = report["totals"]
    assert totals["verified"] == 1 and totals["unverified"] == 0
    assert totals["fullyVerified"] == 1 and totals["passed"] == 1
    assert totals["passRate"] == 1.0
    # n=1 all-pass: rule of three floors at 0.0 — the bound is published, not 100%
    assert totals["passRateLowerBound"] == pytest.approx(0.0)
    assert report["failures"] == []
    assert report["generatedAt"] is None  # root stamps; never datetime.now


# --- driver honesty buckets: unverified reasons + fail-closed exit -----------

def test_driver_missing_filled_pdf_is_unverified_no_render(tmp_path):
    blank_dir = tmp_path / "blanks"
    blank_dir.mkdir()
    # binding is by stem only — the blank is never parsed when the filled leg is absent
    (blank_dir / "000_form_a.pdf").write_bytes(b"%PDF-placeholder")
    manifest = _manifest(
        tmp_path, [_record("/d/form_a.hwpx", "/o/formfit-form_a-medium.hwpx")]
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        ["--manifest", str(manifest), "--blank-pdf-dir", str(blank_dir), "--out", str(out)]
    )
    assert rc == 3  # fail-closed: 0 pairs verified
    report = json.loads(out.read_text(encoding="utf-8"))  # still written for inspection
    (pair,) = report["pairs"]
    assert pair["status"] == "unverified" and pair["reasonKind"] == "no_render"
    totals = report["totals"]
    assert totals["verified"] == 0 and totals["unverified"] == 1
    assert totals["unverifiedReasons"] == {"no_render": 1}
    assert totals["passRate"] is None  # unverified never folds into pass or fail


def test_driver_missing_blank_pdf_is_unverified_no_blank_render(tmp_path):
    blank_dir = tmp_path / "blanks"
    filled_dir = tmp_path / "filled"
    blank_dir.mkdir()
    filled_dir.mkdir()
    (filled_dir / "formfit-form_a-medium.pdf").write_bytes(b"%PDF-placeholder")
    manifest = _manifest(
        tmp_path, [_record("/d/form_a.hwpx", "/o/formfit-form_a-medium.hwpx")]
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        [
            "--manifest", str(manifest),
            "--blank-pdf-dir", str(blank_dir),
            "--filled-pdf-dir", str(filled_dir),
            "--out", str(out),
        ]
    )
    assert rc == 3
    report = json.loads(out.read_text(encoding="utf-8"))
    (pair,) = report["pairs"]
    assert pair["status"] == "unverified" and pair["reasonKind"] == "no_blank_render"


@needs_fitz
def test_driver_unreadable_filled_pdf_is_render_failure(tmp_path):
    blank_dir = tmp_path / "blanks"
    filled_dir = tmp_path / "filled"
    blank_dir.mkdir()
    filled_dir.mkdir()
    _layout_pdf(blank_dir / "000_form_a.pdf", pages=1, rows=2, cols=2)
    # exists + non-empty but not parseable -> honest render_failure, never a crash
    (filled_dir / "formfit-form_a-medium.pdf").write_bytes(b"not a pdf at all")
    manifest = _manifest(
        tmp_path, [_record("/d/form_a.hwpx", "/o/formfit-form_a-medium.hwpx")]
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        [
            "--manifest", str(manifest),
            "--blank-pdf-dir", str(blank_dir),
            "--filled-pdf-dir", str(filled_dir),
            "--out", str(out),
        ]
    )
    assert rc == 3
    report = json.loads(out.read_text(encoding="utf-8"))
    (pair,) = report["pairs"]
    assert pair["status"] == "unverified" and pair["reasonKind"] == "render_failure"


# --- clip-undetectable tier (live extract_cell_clips == 0) -------------------

@needs_fitz
def test_driver_clip_undetectable_tier_still_judges_layout_and_overlap(tmp_path):
    # The 3-prose-docs case from the P0 spike: no find_tables cells -> overflow
    # honestly not evaluated, layout + overlap still decided.
    blank_dir = tmp_path / "blanks"
    filled_dir = tmp_path / "filled"
    blank_dir.mkdir()
    filled_dir.mkdir()
    _prose_pdf(blank_dir / "015_prose_doc.pdf")
    _prose_pdf(filled_dir / "formfit-prose_doc-short.pdf")
    manifest = _manifest(
        tmp_path, [_record("/d/prose_doc.hwpx", "/o/formfit-prose_doc-short.hwpx")]
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        [
            "--manifest", str(manifest),
            "--blank-pdf-dir", str(blank_dir),
            "--filled-pdf-dir", str(filled_dir),
            "--out", str(out),
        ]
    )
    assert rc == 0  # the pair IS verified (layout/overlap decided)
    report = json.loads(out.read_text(encoding="utf-8"))
    (pair,) = report["pairs"]
    assert pair["status"] == "verified"
    assert pair["overflowTier"] == "clip_undetectable"
    assert pair["overflowChecked"] is False and pair["blankClipDetectable"] is False
    assert pair["layoutStable"] is True and pair["newOverlap"] == 0
    totals = report["totals"]
    assert totals["clipUndetectable"] == 1
    assert totals["clipUndetectableLayoutOverlapPass"] == 1
    # excluded from the overflow + all-pass cells -> no inflated pass rate
    assert totals["fullyVerified"] == 0 and totals["passRate"] is None
    cells = {c["name"]: c for c in report["cells"]}
    assert cells["new_overflow_zero"]["n"] == 0
    assert cells["all_pass"]["n"] == 0
    assert cells["layout_stable"]["n"] == 1 and cells["layout_stable"]["passed"] == 1
    assert cells["new_overlap_zero"]["n"] == 1 and cells["new_overlap_zero"]["passed"] == 1


# --- failing pair: a new overlap the fill introduced -------------------------

@needs_fitz
def test_driver_flags_new_overlap_failure(tmp_path):
    blank_dir = tmp_path / "blanks"
    filled_dir = tmp_path / "filled"
    blank_dir.mkdir()
    filled_dir.mkdir()
    _overlap_pdf(blank_dir / "003_slot_form.pdf", extra=False)
    _overlap_pdf(filled_dir / "formfit-slot_form-long.pdf", extra=True)
    manifest = _manifest(
        tmp_path, [_record("/d/slot_form.hwpx", "/o/formfit-slot_form-long.hwpx", "ov-1")]
    )
    out = tmp_path / "report.json"
    rc = cfd.main(
        [
            "--manifest", str(manifest),
            "--blank-pdf-dir", str(blank_dir),
            "--filled-pdf-dir", str(filled_dir),
            "--out", str(out),
        ]
    )
    assert rc == 0  # verified (a FAIL is a verified verdict, not a fail-closed exit)
    report = json.loads(out.read_text(encoding="utf-8"))
    (pair,) = report["pairs"]
    assert pair["status"] == "verified"
    assert pair["newOverlap"] >= 1 and pair["ok"] is False
    assert "new glyph overlap" in pair["note"]
    assert [f["id"] for f in report["failures"]] == ["ov-1"]


# --- blank geometry cache: extracted once per unique blank -------------------

@needs_fitz
def test_blank_geometry_extracted_once_per_unique_blank(tmp_path, monkeypatch):
    blank_pdf = tmp_path / "blank.pdf"
    _layout_pdf(blank_pdf, pages=1, rows=2, cols=2)
    fills = {}
    for name in ("fill1", "fill2", "fill3"):
        p = tmp_path / f"{name}.pdf"
        _layout_pdf(p, pages=1, rows=2, cols=2)
        fills[name] = str(p)
    records = [
        _record("/d/form_a.hwpx", f"/o/{name}.hwpx", rid=name) for name in fills
    ]
    calls: list[str] = []
    real = cfd._extract_geometry

    def counting(pdf_path):
        calls.append(pdf_path)
        return real(pdf_path)

    monkeypatch.setattr(cfd, "_extract_geometry", counting)
    results = cfd.evaluate_pairs(
        records, blank_pdf_map={"form_a": str(blank_pdf)}, filled_pdf_map=fills
    )
    assert [r["status"] for r in results] == ["verified"] * 3
    assert calls.count(str(blank_pdf)) == 1  # the blank was extracted exactly ONCE
    assert len(calls) == 1 + len(fills)  # 1 blank + one per filled


# --- PDF binding: NNN_ prefix stripping + ambiguity ---------------------------

def test_build_pdf_map_strips_batch_prefix(tmp_path):
    (tmp_path / "007_form_a.pdf").write_bytes(b"x")
    (tmp_path / "form_b.pdf").write_bytes(b"x")
    (tmp_path / "not_a_pdf.txt").write_bytes(b"x")
    mapping, warnings = cfd.build_pdf_map(str(tmp_path))
    assert mapping["form_a"].endswith("007_form_a.pdf")
    assert mapping["007_form_a"].endswith("007_form_a.pdf")  # raw stem bound too
    assert mapping["form_b"].endswith("form_b.pdf")
    assert "not_a_pdf" not in mapping
    assert warnings == []
    # a missing/unset dir is an EMPTY map (the filled leg may not have run yet)
    assert cfd.build_pdf_map(str(tmp_path / "nope")) == ({}, [])
    assert cfd.build_pdf_map(None) == ({}, [])


def test_build_pdf_map_ambiguous_stem_warns_never_silently_rebinds(tmp_path):
    (tmp_path / "001_form_a.pdf").write_bytes(b"x")
    (tmp_path / "007_form_a.pdf").write_bytes(b"x")
    mapping, warnings = cfd.build_pdf_map(str(tmp_path))
    assert mapping["form_a"].endswith("001_form_a.pdf")  # first (sorted) kept
    assert warnings and "ambiguous" in warnings[0]


def test_select_form_records_matches_v2_prefix():
    recs = [
        {"bucket": "form-fit"},
        {"bucket": "form-fit-wide"},
        {"bucket": "authored"},
        {"bucket": None},
    ]
    assert len(cfd.select_form_records(recs)) == 2


def test_not_produced_record_is_skipped_not_unverified():
    rec = {
        "id": "withheld-1",
        "bucket": "form-fit",
        "produced": False,
        "input_path": "b.hwpx",
        "output_path": None,
        "withheld_reason": "open-safety pre-gate",
    }
    (res,) = cfd.evaluate_pairs([rec], blank_pdf_map={}, filled_pdf_map={})
    assert res["status"] == "skipped" and res["reasonKind"] == "not_produced"
    totals = cfd.aggregate([res])["totals"]
    assert totals["skippedNotProduced"] == 1 and totals["pairs"] == 0


# --- aggregation math (pure) --------------------------------------------------

def _vres(rid, *, tier="checked", overflow=0, layout=True, overlap=0):
    layout_overlap_ok = bool(layout and overlap == 0)
    checked = tier == "checked"
    return {
        "id": rid,
        "status": "verified",
        "reasonKind": None,
        "ok": layout_overlap_ok and (overflow == 0 if checked else True),
        "newOverflow": overflow,
        "layoutStable": layout,
        "newOverlap": overlap,
        "overflowChecked": checked,
        "blankClipDetectable": checked,
        "overflowTier": tier,
    }


def _ures(rid, kind):
    return {"id": rid, "status": "unverified", "reasonKind": kind}


def test_aggregate_math_and_cells():
    results = [
        _vres("a"),
        _vres("b"),
        _vres("c"),
        _vres("d", tier="clip_undetectable"),
        _ures("e", "no_render"),
        _ures("f", "render_failure"),
        {"id": "g", "status": "skipped", "reasonKind": "not_produced"},
    ]
    agg = cfd.aggregate(results)
    t = agg["totals"]
    assert t["records"] == 7
    assert t["pairs"] == 6 and t["skippedNotProduced"] == 1
    assert t["verified"] == 4 and t["unverified"] == 2
    assert t["unverifiedReasons"] == {"no_render": 1, "render_failure": 1}
    assert t["clipUndetectable"] == 1 and t["clipUndetectableLayoutOverlapPass"] == 1
    assert t["fullyVerified"] == 3 and t["passed"] == 3 and t["failed"] == 0
    assert t["passRate"] == 1.0
    assert t["passRateLowerBound"] == pytest.approx(0.0)  # 1 - 3/3, floored at 0
    cells = {c["name"]: c for c in agg["cells"]}
    assert (cells["new_overflow_zero"]["n"], cells["new_overflow_zero"]["passed"]) == (3, 3)
    assert (cells["layout_stable"]["n"], cells["layout_stable"]["passed"]) == (4, 4)
    assert (cells["new_overlap_zero"]["n"], cells["new_overlap_zero"]["passed"]) == (4, 4)
    assert (cells["all_pass"]["n"], cells["all_pass"]["passed"]) == (3, 3)
    assert cells["all_pass"]["allPass"] is True


def test_aggregate_observed_failure_gets_no_fabricated_bound():
    agg = cfd.aggregate([_vres("a"), _vres("b", overflow=2)])
    t = agg["totals"]
    assert t["passed"] == 1 and t["failed"] == 1 and t["passRate"] == 0.5
    assert t["passRateLowerBound"] is None  # rule of three is for all-pass cells only
    cells = {c["name"]: c for c in agg["cells"]}
    assert cells["new_overflow_zero"]["passed"] == 1
    assert cells["new_overflow_zero"]["ruleOfThreeLowerBound"] is None


def test_aggregate_never_folds_unverified_into_pass_or_fail():
    agg = cfd.aggregate([_ures(str(i), "no_render") for i in range(5)])
    t = agg["totals"]
    assert t["verified"] == 0 and t["unverified"] == 5
    assert t["passed"] == 0 and t["failed"] == 0 and t["passRate"] is None
    assert t["passRateLowerBound"] is None


def test_rule_of_three_lower_bound_contract():
    assert cfd.rule_of_three_lower_bound(100, 100) == pytest.approx(0.97)
    assert cfd.rule_of_three_lower_bound(300, 300) == pytest.approx(0.99)
    assert cfd.rule_of_three_lower_bound(99, 100) is None  # a failure -> observed rate only
    assert cfd.rule_of_three_lower_bound(0, 0) is None
    assert cfd.rule_of_three_lower_bound(2, 2) == pytest.approx(0.0)  # floored, never negative
