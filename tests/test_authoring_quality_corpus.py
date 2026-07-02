# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the M9-full P3 authoring-quality corpus aggregator
(scripts/corpus_authoring_quality.py, specs/010-corpus-publication).

These prove the apparatus WITHOUT the real corpus, using tiny fixtures and fake
inspectors:

* plan/file alignment (id join, seed-mismatch refusal, plan-less v2 strata,
  relocated-path fallback),
* aggregation math (judged/coverage denominators, rule-of-three lower bound on
  all-pass cells, structure_pass over the gongmun cell only),
* gap histogram + proofing-status distribution (recorded verbatim, never coerced),
* fail-closed exit 3 when ZERO authored records match,
* the FR-006 honesty rule: a LOW pass rate does NOT gate (exit stays 0).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load scripts/corpus_authoring_quality.py as a module (scripts/ is not a package).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_authoring_quality", _SCRIPTS / "corpus_authoring_quality.py"
)
assert _spec and _spec.loader
caq = importlib.util.module_from_spec(_spec)
sys.modules["corpus_authoring_quality"] = caq
_spec.loader.exec_module(caq)


# --------------------------------------------------------------------------- #
# fixture helpers
# --------------------------------------------------------------------------- #

def _rec(rec_id, seed, *, bucket="authored", produced=True, output_path=None, sha=None):
    return {
        "id": rec_id,
        "bucket": bucket,
        "seed": seed,
        "requested": True,
        "produced": produced,
        "output_path": output_path,
        "output_sha256": sha,
        "withheld_reason": None if produced else "open-safety pre-gate",
    }


def _plan(doc_type):
    return {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "t",
        "metadata": {"document_type": doc_type},
        "blocks": [{"type": "paragraph", "text": "본문"}],
    }


def _quality_report(*, ok=True, gaps=(), proofing="unverified", embedded_structure=None):
    rep = {
        "pass": ok,
        "gaps": list(gaps),
        "korean_proofing_status": proofing,
        "gongmun_structure": (
            None
            if embedded_structure is None
            else {"structure_pass": embedded_structure}
        ),
    }
    return rep


def _lint_report(*, structure_pass=True, violations=()):
    return {
        "structure_pass": structure_pass,
        "violations": [
            {
                "rule": rule,
                "severity": severity,
                "paragraph_index": 0,
                "message": f"{rule} violated",
            }
            for rule, severity in violations
        ],
    }


def _touch(tmp_path: Path, rel: str, data: bytes = b"stub") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# --------------------------------------------------------------------------- #
# type derivation + alignment
# --------------------------------------------------------------------------- #

def test_authored_type_from_seed_and_id():
    assert caq.authored_type_from_seed("authored:gongmun:00") == "gongmun"
    assert caq.authored_type_from_seed("authored:bogoseo:14") == "bogoseo"
    assert caq.authored_type_from_seed("formfit:m2:short") is None
    assert caq.authored_type_from_seed(None) is None
    assert caq.authored_type_from_id("authored-gajeong-09") == "gajeong"
    assert caq.authored_type_from_id("mailmerge-award-00") is None


def test_match_records_joins_plan_by_id_and_seed(tmp_path):
    f = _touch(tmp_path, "authored/authored-gongmun-00.hwpx")
    manifest = {
        "records": [
            _rec("authored-gongmun-00", "authored:gongmun:00", output_path=str(f)),
            _rec("mailmerge-award-00", "mailmerge:award:row00", bucket="mail-merge",
                 output_path=str(_touch(tmp_path, "mail-merge/x.hwpx"))),
        ]
    }
    plans = {"authored-gongmun-00": ("authored:gongmun:00", _plan("공문"))}
    entries, alignment = caq.match_records(manifest, plans, corpus_root=tmp_path)
    assert alignment["matched"] == 1  # mail-merge bucket is NOT authored
    assert alignment["with_plan"] == 1
    assert alignment["seed_mismatches"] == []
    assert entries[0]["type"] == "gongmun"
    assert entries[0]["plan"] is not None


def test_match_records_seed_mismatch_refuses_the_plan(tmp_path):
    f = _touch(tmp_path, "authored/authored-bogoseo-00.hwpx")
    manifest = {
        "records": [_rec("authored-bogoseo-00", "authored:bogoseo:00", output_path=str(f))]
    }
    # generator drifted: same id, different seed -> plan must NOT be used
    plans = {"authored-bogoseo-00": ("authored:bogoseo:99", _plan("보고서"))}
    entries, alignment = caq.match_records(manifest, plans, corpus_root=tmp_path)
    assert alignment["with_plan"] == 0
    assert alignment["seed_mismatches"] == [
        {
            "id": "authored-bogoseo-00",
            "manifest_seed": "authored:bogoseo:00",
            "plan_seed": "authored:bogoseo:99",
        }
    ]
    assert entries[0]["plan"] is None
    assert entries[0]["seed_mismatch"] is True


def test_match_records_plan_unmatched_is_listed(tmp_path):
    f = _touch(tmp_path, "authored/authored-gajeong-00.hwpx")
    manifest = {
        "records": [_rec("authored-gajeong-00", "authored:gajeong:00", output_path=str(f))]
    }
    entries, alignment = caq.match_records(manifest, {}, corpus_root=tmp_path)
    assert alignment["plan_unmatched"] == ["authored-gajeong-00"]
    assert entries[0]["plan"] is None
    assert entries[0]["seed_mismatch"] is False


def test_resolve_record_path_falls_back_to_relocated_root(tmp_path):
    # manifest carries a stale absolute path from the generation machine
    stale = "/nonexistent/machine/work/openrate-corpus/authored/authored-gongmun-03.hwpx"
    relocated = _touch(tmp_path, "authored/authored-gongmun-03.hwpx")
    rec = _rec("authored-gongmun-03", "authored:gongmun:03", output_path=stale)
    resolved = caq.resolve_record_path(rec, tmp_path, "authored")
    assert resolved == relocated
    assert caq.resolve_record_path({"output_path": None}, tmp_path, "authored") is None


def test_match_records_v2_authored_strata_plan_less(tmp_path):
    toc = _touch(tmp_path, "authored-toc/authoredtoc-00.hwpx")
    run = _touch(tmp_path, "reading-runformat/runformat-00.hwpx")
    v2 = {
        "records": [
            {"id": "authoredtoc-00", "stratum": "authored-toc", "bucket": "authored-toc",
             "seed": "authored-toc:00", "produced": True, "output_path": str(toc)},
            {"id": "runformat-00", "stratum": "reading-runformat", "bucket": "reading-runformat",
             "seed": "reading-runformat:00", "produced": True, "output_path": str(run)},
            {"id": "piimerge-00", "stratum": "pii-merge", "bucket": "pii-merge",
             "seed": "pii-merge:row00", "produced": True,
             "output_path": str(_touch(tmp_path, "pii-merge/p.hwpx"))},
        ]
    }
    entries, alignment = caq.match_records(
        {"records": []}, {}, corpus_root=tmp_path, v2_manifest=v2, v2_corpus_root=tmp_path
    )
    assert alignment["matched"] == 2  # pii-merge is NOT an authored stratum
    assert {e["type"] for e in entries} == {"authored-toc", "reading-runformat"}
    assert all(e["plan"] is None for e in entries)  # plan-less by design
    assert all(e["source"] == "v2" for e in entries)


# --------------------------------------------------------------------------- #
# evaluation rows (fake inspectors)
# --------------------------------------------------------------------------- #

def _entries_one(tmp_path, doc_type="gongmun", *, produced=True, exists=True, plan=True):
    rec_id = f"authored-{doc_type}-00"
    path = tmp_path / "authored" / f"{rec_id}.hwpx"
    if exists:
        _touch(tmp_path, f"authored/{rec_id}.hwpx")
    rec = _rec(rec_id, f"authored:{doc_type}:00", produced=produced,
               output_path=str(path) if produced else None)
    return [{
        "id": rec_id, "source": "v1", "type": doc_type, "record": rec,
        "plan": _plan("공문") if plan else None, "seed_mismatch": False,
        "path": path if produced else None,
    }]


def test_evaluate_judged_row_captures_gaps_proofing_and_structure(tmp_path):
    entries = _entries_one(tmp_path)
    rows = caq.evaluate_entries(
        entries,
        quality_inspector=lambda p, plan: _quality_report(
            ok=False, gaps=["quality gate failed: minParagraphs"],
            proofing="unverified", embedded_structure=False,
        ),
        gongmun_lint=lambda p: _lint_report(
            structure_pass=False,
            violations=[("missing-sihaeng", "error"), ("attachment-notation", "warning")],
        ),
        verify_sha=False,
    )
    (row,) = rows
    assert row["status"] == "judged"
    assert row["quality_pass"] is False
    assert row["gaps"] == ["quality gate failed: minParagraphs"]
    assert row["korean_proofing_status"] == "unverified"  # recorded verbatim
    assert row["structure_pass"] is False
    assert [v["rule"] for v in row["lint_violations"]] == [
        "missing-sihaeng", "attachment-notation",
    ]
    assert row["gongmun_embedded_structure_pass"] is False


def test_evaluate_non_gongmun_never_calls_lint(tmp_path):
    entries = _entries_one(tmp_path, doc_type="bogoseo")

    def _boom(path):  # pragma: no cover - would fail the test if reached
        raise AssertionError("lint must not run for non-gongmun types")

    rows = caq.evaluate_entries(
        entries,
        quality_inspector=lambda p, plan: _quality_report(ok=True),
        gongmun_lint=_boom,
        verify_sha=False,
    )
    assert rows[0]["structure_pass"] is None
    assert rows[0]["quality_pass"] is True


def test_evaluate_withheld_missing_and_crash_rows(tmp_path):
    withheld = _entries_one(tmp_path, doc_type="gajeong", produced=False)
    missing = _entries_one(tmp_path, doc_type="bogoseo", exists=False)
    crash = _entries_one(tmp_path, doc_type="gongmun")

    def _crash_inspector(path, plan):
        raise ValueError("cannot open")

    rows = caq.evaluate_entries(
        withheld + missing + crash,
        quality_inspector=_crash_inspector,
        gongmun_lint=lambda p: _lint_report(),
        verify_sha=False,
    )
    statuses = {r["id"]: r["status"] for r in rows}
    assert statuses["authored-gajeong-00"] == "withheld"
    assert statuses["authored-bogoseo-00"] == "missing_file"
    assert statuses["authored-gongmun-00"] == "inspect_error"
    assert "ValueError" in rows[2]["error"]


def test_evaluate_sha_drift_is_flagged_not_fatal(tmp_path):
    entries = _entries_one(tmp_path)
    entries[0]["record"]["output_sha256"] = "0" * 64  # frozen hash != bytes on disk
    rows = caq.evaluate_entries(
        entries,
        quality_inspector=lambda p, plan: _quality_report(ok=True, embedded_structure=True),
        gongmun_lint=lambda p: _lint_report(),
        verify_sha=True,
    )
    assert rows[0]["sha_ok"] is False
    assert rows[0]["status"] == "judged"  # still measured, drift flagged honestly


# --------------------------------------------------------------------------- #
# aggregation math
# --------------------------------------------------------------------------- #

def _row(rec_id, doc_type, *, status="judged", quality=True, gaps=(),
         proofing="unverified", structure=None, lint=(), sha_ok=True):
    return {
        "id": rec_id, "source": "v1", "type": doc_type, "path": f"/x/{rec_id}.hwpx",
        "plan_used": True, "seed_mismatch": False, "status": status,
        "sha_ok": sha_ok, "quality_pass": quality if status == "judged" else None,
        "gaps": list(gaps), "korean_proofing_status": proofing if status == "judged" else None,
        "structure_pass": structure,
        "lint_violations": [
            {"rule": r, "severity": s, "paragraph_index": 0, "message": ""}
            for r, s in lint
        ],
        "gongmun_embedded_structure_pass": structure,
        "error": None if status == "judged" else status,
    }


def test_aggregate_all_pass_cell_uses_rule_of_three_lower_bound():
    rows = [_row(f"authored-gajeong-{i:02d}", "gajeong") for i in range(10)]
    agg = caq.aggregate(rows)
    cell = agg["types"]["gajeong"]
    assert cell["judged"] == 10
    assert cell["quality"]["pass"] == 10
    assert cell["quality"]["rate"] == 1.0
    # k=0 in N=10 -> 1 - 3/10 = 0.7 ; the interval text never says 100%
    assert cell["quality"]["rate_lower_bound"] == pytest.approx(0.7)
    assert "100" not in cell["quality"]["rate_interval"]


def test_aggregate_math_denominators_and_structure_cell():
    rows = (
        [_row(f"authored-gongmun-{i:02d}", "gongmun", structure=True) for i in range(3)]
        + [_row("authored-gongmun-03", "gongmun", quality=False,
                gaps=["공문 structure gate failed"], structure=False,
                lint=[("missing-susin", "error")])]
        + [_row("authored-gongmun-04", "gongmun", status="missing_file")]
        + [_row("authored-bogoseo-00", "bogoseo")]
    )
    agg = caq.aggregate(rows)
    g = agg["types"]["gongmun"]
    assert g["records"] == 5
    assert g["produced"] == 5
    assert g["judged"] == 4                     # missing_file is NOT judged
    assert g["missing_file"] == 1
    assert g["coverage"] == pytest.approx(4 / 5)
    assert g["quality"]["pass"] == 3
    assert g["quality"]["rate"] == pytest.approx(0.75)
    s = g["structure"]
    assert s["judged"] == 4 and s["pass"] == 3 and s["fail"] == 1
    assert s["rate"] == pytest.approx(0.75)
    assert s["lint_violation_histogram"] == {"missing-susin:error": 1}
    # bogoseo carries no structure verdict -> no structure cell
    assert agg["types"]["bogoseo"]["structure"] is None
    # totals span both types
    assert agg["totals"]["records"] == 6
    assert agg["totals"]["judged"] == 5
    # the structure failure is a listed per-file failure with gap details
    fail_ids = [f["id"] for f in g["failures"]]
    assert "authored-gongmun-03" in fail_ids and "authored-gongmun-04" in fail_ids
    f3 = next(f for f in g["failures"] if f["id"] == "authored-gongmun-03")
    assert "structure hard-gate FAILED" in f3["reason"]
    assert "missing-susin" in f3["reason"]


def test_aggregate_gap_histogram_and_proofing_distribution():
    rows = [
        _row("authored-bogoseo-00", "bogoseo", quality=False,
             gaps=["quality gate failed: minTables", "quality gate failed: reopened"]),
        _row("authored-bogoseo-01", "bogoseo", quality=False,
             gaps=["quality gate failed: minTables"]),
        _row("authored-bogoseo-02", "bogoseo",
             proofing="llm_proofed_not_oracle_verified"),
    ]
    agg = caq.aggregate(rows)
    cell = agg["types"]["bogoseo"]
    assert cell["gap_histogram"] == {
        "quality gate failed: minTables": 2,
        "quality gate failed: reopened": 1,
    }
    # verbatim distribution — 'unverified' is expected and never rewritten
    assert cell["proofing_status"] == {
        "llm_proofed_not_oracle_verified": 1,
        "unverified": 2,
    }


def test_aggregate_withheld_lowers_produced_not_judged_rate():
    rows = [
        _row("authored-gajeong-00", "gajeong"),
        _row("authored-gajeong-01", "gajeong", status="withheld"),
    ]
    cell = caq.aggregate(rows)["types"]["gajeong"]
    assert cell["records"] == 2
    assert cell["withheld"] == 1
    assert cell["produced"] == 1
    assert cell["judged"] == 1
    assert cell["quality"]["rate"] == 1.0


def test_build_report_carries_honesty_notes_and_cross_reference():
    rows = [_row("authored-gongmun-00", "gongmun", structure=True)]
    report = caq.build_report(
        rows, {"matched": 1, "with_plan": 1, "seed_mismatches": [], "plan_unmatched": []},
        sources={"v1_manifest": "m.json", "v1_corpus_root": "root", "v2_manifest": None},
    )
    assert report["axis"] == "authoring"
    assert report["generatedAt"] is None
    assert "NO" in report["metric"]["honestyRule"]  # no regenerate-until-green
    assert "docs/openrate/report.json" in report["metric"]["opensCleanCrossReference"]
    assert "not re-claimed" in report["metric"]["opensCleanCrossReference"].lower()
    assert report["totals"]["judged"] == 1
    assert report["per_file"][0]["id"] == "authored-gongmun-00"


# --------------------------------------------------------------------------- #
# CLI exit codes (fail-closed on empty; NO gate on a low pass rate)
# --------------------------------------------------------------------------- #

def test_main_exit_3_when_zero_authored_records(tmp_path, capsys):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "records": [
            _rec("mailmerge-award-00", "mailmerge:award:row00", bucket="mail-merge",
                 output_path=str(_touch(tmp_path, "mail-merge/a.hwpx"))),
        ]
    }), encoding="utf-8")
    out = tmp_path / "report.json"
    rc = caq.main([
        "--corpus-root", str(tmp_path),
        "--manifest", str(manifest),
        "--out", str(out),
    ])
    assert rc == 3
    assert out.exists()  # report still written for inspection
    captured = capsys.readouterr()
    assert "FAIL-CLOSED" in captured.err
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["alignment"]["matched"] == 0


def test_main_exit_2_when_manifest_missing(tmp_path):
    with pytest.raises(SystemExit) as exc:
        caq.main(["--manifest", str(tmp_path / "nope.json")])
    assert exc.value.code == 2


def test_low_pass_rate_is_published_not_gated(tmp_path, capsys, monkeypatch):
    """FR-006: an all-fail corpus still exits 0 — the low number IS the deliverable."""

    f = _touch(tmp_path, "authored/authored-gongmun-00.hwpx")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "records": [_rec("authored-gongmun-00", "authored:gongmun:00", output_path=str(f))]
    }), encoding="utf-8")

    monkeypatch.setattr(caq, "_load_authored_plans", lambda: {
        "authored-gongmun-00": ("authored:gongmun:00", _plan("공문")),
    })
    monkeypatch.setattr(caq, "_real_inspectors", lambda: (
        lambda p, plan: _quality_report(
            ok=False, gaps=["quality gate failed: reopened"], embedded_structure=False
        ),
        lambda p: _lint_report(structure_pass=False,
                               violations=[("missing-sihaeng", "error")]),
    ))

    out = tmp_path / "report.json"
    rc = caq.main([
        "--corpus-root", str(tmp_path),
        "--manifest", str(manifest),
        "--out", str(out),
        "--no-sha-check",
    ])
    assert rc == 0  # NO exit-2 gate on a low pass rate
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals"]["quality"]["rate"] == 0.0
    assert report["types"]["gongmun"]["structure"]["rate"] == 0.0
    captured = capsys.readouterr()
    assert "FAILURES" in captured.out  # printed prominently
    assert "structure hard-gate FAILED" in captured.out


def test_main_end_to_end_with_real_inspectors_on_tiny_hwpx(tmp_path):
    """One real .hwpx through the real inspectors — integration smoke, no corpus."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("학부모님께 알립니다.")
    doc.add_paragraph("2026. 7. 3.")
    doc.add_paragraph("○○중학교장")
    target = tmp_path / "authored" / "authored-gajeong-00.hwpx"
    target.parent.mkdir(parents=True)
    doc.save_to_path(target)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "records": [_rec("authored-gajeong-00", "authored:gajeong:00",
                         output_path=str(target))]
    }), encoding="utf-8")
    out = tmp_path / "report.json"
    rc = caq.main([
        "--corpus-root", str(tmp_path),
        "--manifest", str(manifest),
        "--out", str(out),
        "--no-sha-check",
    ])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    cell = report["types"]["gajeong"]
    assert cell["judged"] == 1
    # the real inspector must return an honest proofing status, never a coerced pass
    assert report["per_file"][0]["korean_proofing_status"] == "unverified"
