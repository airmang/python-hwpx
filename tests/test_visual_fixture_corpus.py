from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx.visual.fixture_corpus import load_fixture_manifest
from hwpx.visual.qa_contracts import DefectCategory, VerdictStatus
from hwpx.visual.page_qa import inspect_fixture_case, inspect_page_set


CORPUS = Path(__file__).parent / "fixtures" / "visual_qa_v1"


def test_frozen_manifest_loads_and_fixture_receipt_is_honest() -> None:
    corpus = load_fixture_manifest(CORPUS / "manifest.json")
    assert {case.classification for case in corpus.cases} == {"clean", "natural", "injected"}
    receipt = corpus.receipt(corpus.cases[0])
    assert receipt["assurance"] == "fixture"
    assert receipt["renderChecked"] is False
    assert receipt["realHancom"] is False


def test_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    raw = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    raw["cases"][0]["pages"][0]["path"] = "bad.png"
    (tmp_path / "bad.png").write_bytes((CORPUS / "clean_page.png").read_bytes())
    raw["cases"][0]["pages"][0]["sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_fixture_manifest(path)


def test_manifest_rejects_taxonomy_drift(tmp_path: Path) -> None:
    raw = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    raw["taxonomyVersion"] = "future"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="taxonomy version"):
        load_fixture_manifest(path, verify_hashes=False)


def test_adjudicated_annotation_requires_two_labelers(tmp_path: Path) -> None:
    raw = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    annotation = raw["cases"][1]["annotations"][0]
    annotation["labelStatus"] = "adjudicated"
    annotation["labelers"] = ["only-one"]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="two independent labelers"):
        load_fixture_manifest(path, verify_hashes=False)


def test_deterministic_detectors_match_frozen_cases() -> None:
    corpus = load_fixture_manifest(CORPUS / "manifest.json")
    by_id = {case.case_id: inspect_fixture_case(case) for case in corpus.cases}
    assert by_id["clean-layout-001"].status is VerdictStatus.PASS

    natural = by_id["natural-overprint-001"]
    assert natural.status is VerdictStatus.FAIL
    assert DefectCategory.TEXT_CLIPPING_OVERLAP in {finding.category for finding in natural.findings}

    clipped = by_id["injected-edge-clip-001"]
    assert clipped.status is VerdictStatus.FAIL
    assert any(finding.bbox.x1 == 1.0 for finding in clipped.findings)

    blank = by_id["injected-blank-001"]
    assert blank.status is VerdictStatus.FAIL
    assert {finding.category for finding in blank.findings} == {
        DefectCategory.UNEXPECTED_BLANK_PAGE
    }

    for verdict in by_id.values():
        assert verdict.assurance == "fixture"
        assert verdict.render_checked is False


def test_full_page_coverage_unreadable_page_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "not-a-png.png"
    bad.write_text("not an image", encoding="utf-8")
    verdict = inspect_page_set(
        {0: CORPUS / "clean_page.png", 1: bad},
        expected_pages=[0, 1], assurance="fixture", render_checked=False,
    )
    assert verdict.status is VerdictStatus.UNVERIFIED
    assert verdict.missing_pages == (1,)
