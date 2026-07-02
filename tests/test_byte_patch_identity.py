# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/corpus_byte_patch_identity.py (specs/010 P3).

Byte-identity axis: one deterministic paragraph_patch per doc; every zip part
NOT declared in ``changed_parts`` must stay byte-identical. Tiny fixtures are
built with the real builder/document helpers (see tests/test_kordoc_absorption.py);
no Hancom, no corpus files.
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from hwpx import HwpxDocument
from hwpx.tools.idempotence import IdempotenceReport

# Load scripts/corpus_byte_patch_identity.py as a module (scripts/ is not a package).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_byte_patch_identity", _SCRIPTS / "corpus_byte_patch_identity.py"
)
assert _spec is not None and _spec.loader is not None
bpi = importlib.util.module_from_spec(_spec)
sys.modules["corpus_byte_patch_identity"] = bpi
_spec.loader.exec_module(bpi)


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #

def _tiny_doc_bytes(text: str = "byte identity fixture") -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph(text)
    return document.to_bytes()


def _replace_zip_part(package_bytes: bytes, part_name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(package_bytes), "r") as source:
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for info in source.infolist():
                replacement = (
                    payload if info.filename == part_name else source.read(info.filename)
                )
                archive.writestr(
                    info.filename,
                    replacement,
                    compress_type=ZIP_STORED
                    if info.filename == "mimetype"
                    else info.compress_type,
                )
    return buffer.getvalue()


def _unpatchable_doc_bytes() -> bytes:
    """A package whose section paragraphs have no patchable run/text at all."""

    package_bytes = _tiny_doc_bytes()
    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        section = archive.read("Contents/section0.xml")
    stripped = re.sub(rb"<hp:run\b.*?</hp:run>", b"", section, flags=re.DOTALL)
    stripped = re.sub(rb"<hp:run\b[^>]*/>", b"", stripped)
    assert b"<hp:run" not in stripped
    return _replace_zip_part(package_bytes, "Contents/section0.xml", stripped)


# --------------------------------------------------------------------------- #
# Per-doc verdicts
# --------------------------------------------------------------------------- #

def test_applied_doc_pass_verdict_records_zip_method(tmp_path: Path) -> None:
    target = tmp_path / "fixture-a.hwpx"
    target.write_bytes(_tiny_doc_bytes())

    row = bpi.process_document(target, bucket="unit")

    assert row["status"] == "applied"
    assert row["applied_count"] == 1
    assert row["untouched_ok"] is True
    assert row["unexpected_changed_parts"] == []
    assert row["added_parts"] == []
    assert row["removed_parts"] == []
    # zip_method is recorded per doc — the write-path split is part of the claim.
    assert row["zip_method"] == "partial-local-record-copy"
    # A really-applied patch cannot be byte-identical to the source.
    assert row["byte_identical"] is False
    assert row["declared_changed_parts"] == ["Contents/section0.xml"]
    assert row["observed_changed_parts"] == ["Contents/section0.xml"]


def test_replacement_text_is_deterministic_and_basename_derived() -> None:
    a1 = bpi.replacement_text_for("doc-a.hwpx")
    a2 = bpi.replacement_text_for("doc-a.hwpx")
    b = bpi.replacement_text_for("doc-b.hwpx")
    assert a1 == a2
    assert a1 != b
    assert "\n" not in a1 and "\r" not in a1


def test_not_applicable_doc_is_excluded_from_denominator(tmp_path: Path) -> None:
    bad = tmp_path / "unpatchable.hwpx"
    bad.write_bytes(_unpatchable_doc_bytes())
    good = tmp_path / "patchable.hwpx"
    good.write_bytes(_tiny_doc_bytes())

    bad_row = bpi.process_document(bad, bucket="unit")
    good_row = bpi.process_document(good, bucket="unit")

    assert bad_row["status"] == "not_applicable"
    assert any("no patchable hp:run" in r for r in bad_row["reasons"])

    report = bpi.build_report([good_row, bad_row], source="unit")
    totals = report["totals"]
    # Denominator = applied docs ONLY (metric-vacuity guard).
    assert totals["docs_considered"] == 2
    assert totals["applied"] == 1
    assert totals["not_applicable"] == 1
    assert totals["untouched_ok"] == 1
    assert totals["untouched_ok_rate"] == 1.0
    # The excluded doc is listed separately with its reasons, never dropped.
    assert len(report["not_applicable"]) == 1
    assert report["not_applicable"][0]["path"] == str(bad)
    assert report["not_applicable"][0]["reasons"]


def test_subset_violation_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An observed change OUTSIDE the declared changed_parts must fail the verdict."""

    target = tmp_path / "fixture-v.hwpx"
    target.write_bytes(_tiny_doc_bytes())

    def fake_pair(first: bytes, second: bytes) -> IdempotenceReport:
        return IdempotenceReport(
            ok=False,
            changed_parts=("Contents/header.xml", "Contents/section0.xml"),
        )

    monkeypatch.setattr(bpi, "check_idempotent_pair", fake_pair)
    row = bpi.process_document(target, bucket="unit")

    assert row["status"] == "applied"
    assert row["untouched_ok"] is False
    assert row["unexpected_changed_parts"] == ["Contents/header.xml"]

    report = bpi.build_report([row], source="unit")
    assert report["totals"]["violations"] == 1
    assert report["totals"]["untouched_ok_rate"] == 0.0
    assert report["violations"][0]["path"] == str(target)


def test_added_or_removed_parts_fail_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fixture-add.hwpx"
    target.write_bytes(_tiny_doc_bytes())

    def fake_pair(first: bytes, second: bytes) -> IdempotenceReport:
        return IdempotenceReport(
            ok=False,
            changed_parts=("Contents/section0.xml",),
            added_parts=("Contents/ghost.xml",),
        )

    monkeypatch.setattr(bpi, "check_idempotent_pair", fake_pair)
    row = bpi.process_document(target, bucket="unit")
    assert row["status"] == "applied"
    assert row["untouched_ok"] is False
    assert row["added_parts"] == ["Contents/ghost.xml"]


# --------------------------------------------------------------------------- #
# Report math
# --------------------------------------------------------------------------- #

def test_rule_of_three_math() -> None:
    assert bpi.rule_of_three_lower_bound(0, 100) == pytest.approx(0.97)
    assert bpi.rule_of_three_lower_bound(0, 10) == pytest.approx(0.7)
    assert bpi.rule_of_three_lower_bound(1, 10) == pytest.approx(0.6)
    assert bpi.rule_of_three_lower_bound(0, 0) is None
    # The interval text carries the bound — the headline never prints a bare 100%.
    assert ">=" in bpi.rule_of_three_text(0, 50)
    assert "N/A" in bpi.rule_of_three_text(0, 0)


def test_report_zip_method_distribution_and_metric_note(tmp_path: Path) -> None:
    rows = []
    for name in ("m1.hwpx", "m2.hwpx"):
        target = tmp_path / name
        target.write_bytes(_tiny_doc_bytes())
        rows.append(bpi.process_document(target, bucket="unit"))

    report = bpi.build_report(rows, source="unit")
    assert report["totals"]["zip_method_distribution"] == {
        "partial-local-record-copy": 2
    }
    # The explicit claim-scope note must be published verbatim.
    assert report["metric"]["granularityNote"] == (
        "part-content granularity; full-save path out-of-claim (random hp:p ids)"
    )
    assert report["metric"]["claimScope"] == "PATCH-PATH ONLY (hwpx.patch.paragraph_patch)"


# --------------------------------------------------------------------------- #
# CLI fail-closed exits
# --------------------------------------------------------------------------- #

def test_main_glob_run_passes_and_writes_report(tmp_path: Path) -> None:
    (tmp_path / "d1.hwpx").write_bytes(_tiny_doc_bytes("one"))
    (tmp_path / "d2.hwpx").write_bytes(_tiny_doc_bytes("two"))
    out = tmp_path / "report.json"

    code = bpi.main(["--glob", str(tmp_path / "*.hwpx"), "--out", str(out)])

    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals"]["applied"] == 2
    assert report["totals"]["untouched_ok"] == 2
    assert report["totals"]["violations"] == 0
    assert report["generatedAt"] is None


def test_main_exits_2_on_untouched_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "d1.hwpx").write_bytes(_tiny_doc_bytes())
    out = tmp_path / "report.json"

    def fake_pair(first: bytes, second: bytes) -> IdempotenceReport:
        return IdempotenceReport(
            ok=False,
            changed_parts=("Contents/header.xml", "Contents/section0.xml"),
        )

    monkeypatch.setattr(bpi, "check_idempotent_pair", fake_pair)
    code = bpi.main(["--glob", str(tmp_path / "*.hwpx"), "--out", str(out)])

    assert code == 2
    captured = capsys.readouterr()
    assert "BYTE_IDENTITY_VIOLATION" in captured.err
    # The report is still written for inspection.
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals"]["violations"] == 1


def test_main_exits_3_when_nothing_applied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "unpatchable.hwpx").write_bytes(_unpatchable_doc_bytes())
    out = tmp_path / "report.json"

    code = bpi.main(["--glob", str(tmp_path / "*.hwpx"), "--out", str(out)])

    assert code == 3
    captured = capsys.readouterr()
    assert "METRIC_VACUOUS" in captured.err
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals"]["applied"] == 0
    assert report["totals"]["not_applicable"] == 1
    assert report["totals"]["untouched_ok_rate"] is None


def test_manifest_mode_resolves_paths_and_reports(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "authored").mkdir(parents=True)
    doc = corpus / "authored" / "authored-x-00.hwpx"
    doc.write_bytes(_tiny_doc_bytes())
    manifest = {
        "schemaVersion": "hwpx.openrate.frozen-manifest.v1",
        "records": [
            {
                "id": "authored-x-00",
                "bucket": "authored",
                "produced": True,
                "output_path": str(doc),
            },
            {
                "id": "authored-x-01",
                "bucket": "authored",
                "produced": False,
                "output_path": None,
            },
        ],
    }
    manifest_path = corpus / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "report.json"

    code = bpi.main(
        [
            "--corpus-root",
            str(corpus),
            "--manifest",
            str(manifest_path),
            "--out",
            str(out),
        ]
    )

    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["totals"]["applied"] == 1
    assert report["totals"]["not_applicable"] == 1
    reasons = report["not_applicable"][0]["reasons"]
    assert any("withheld" in r for r in reasons)
    strata = {s["bucket"]: s for s in report["strata"]}
    assert strata["authored"]["applied"] == 1
