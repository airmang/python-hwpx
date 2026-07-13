from pathlib import Path

import pytest

from hwpx.visual.fixture_corpus import load_fixture_manifest
from hwpx.visual.qa_metrics import measure_fixture_corpus


def test_frozen_fixture_metrics_fail_without_required_category_coverage() -> None:
    manifest = Path(__file__).parent / "fixtures" / "visual_qa_v1" / "manifest.json"
    report = measure_fixture_corpus(load_fixture_manifest(manifest))
    assert report["schema"] == "hwpx.visual-qa-metrics/v2"
    assert report["gatePassed"] is False
    assert report["criticalRecall"] >= 0.95
    assert report["criticalPrecision"] >= 0.90
    assert report["defectFalseAcceptanceRate"] <= 0.01
    assert report["cleanFalseRejectionRate"] <= 0.01
    assert report["renderChecked"] is False
    assert report["assurance"] == "fixture"
    assert report["criticalRecall95CI"]
    assert set(report["perCategory"]) == {
        "text_clipping_overlap", "cell_overflow", "unexpected_blank_page",
        "leftover_guidance_placeholder_sample", "empty_required_field",
        "orphan_bullet_heading", "table_grid_border_anomaly",
        "font_color_alignment_inconsistency", "image_seal_misplacement",
        "header_footer_page_number_loss", "implausible_whitespace_density",
    }
    assert report["perCategory"]["text_clipping_overlap"]["recall95CI"]
    assert report["perCategory"]["cell_overflow"]["sampleSufficient"] is False
    assert report["gateContract"]["requiredCoveragePassed"] is False
    assert report["gateContract"]["requiredRecallBoundsPassed"] is False
    assert report["gateContract"]["scopeProvenance"] == {
        "mode": "full_taxonomy",
        "taxonomyVersion": "hwpx-visual-defects/1.0",
    }
    assert len(report["gateContract"]["requiredCategories"]) == 11
    assert (
        "category:cell_overflow:minimum_samples"
        in report["gateContract"]["failedRequirements"]
    )
    assert (
        report["gateContract"]["aggregateBounds"]["criticalRecallLower"]
        is False
    )


def test_narrowed_required_categories_require_provenance() -> None:
    manifest = Path(__file__).parent / "fixtures" / "visual_qa_v1" / "manifest.json"
    corpus = load_fixture_manifest(manifest)

    with pytest.raises(ValueError, match="require provenance fields: reason, source"):
        measure_fixture_corpus(
            corpus,
            required_categories=["text_clipping_overlap", "unexpected_blank_page"],
        )


def test_narrowed_required_categories_preserve_provenance_but_not_false_pass() -> None:
    manifest = Path(__file__).parent / "fixtures" / "visual_qa_v1" / "manifest.json"
    report = measure_fixture_corpus(
        load_fixture_manifest(manifest),
        required_categories=["text_clipping_overlap", "unexpected_blank_page"],
        minimum_category_samples=1,
        required_categories_provenance={
            "reason": "detectors implemented by the fixture rail",
            "source": "specs/017-autonomous-operator-hardening/spec.md#us5",
        },
    )

    assert report["gatePassed"] is False
    assert report["gateContract"]["requiredCoveragePassed"] is True
    assert report["gateContract"]["scopeProvenance"]["mode"] == "explicitly_narrowed"
    assert report["gateContract"]["requiredRecallBoundsPassed"] is False
    assert any(
        requirement.endswith(":recall_lower_bound")
        for requirement in report["gateContract"]["failedRequirements"]
    )


def test_invalid_gate_contract_is_rejected() -> None:
    manifest = Path(__file__).parent / "fixtures" / "visual_qa_v1" / "manifest.json"
    corpus = load_fixture_manifest(manifest)

    with pytest.raises(ValueError, match="at least 1"):
        measure_fixture_corpus(corpus, minimum_category_samples=0)
    with pytest.raises(ValueError, match="cannot be empty"):
        measure_fixture_corpus(corpus, required_categories=[])
    with pytest.raises(ValueError, match="unsupported required"):
        measure_fixture_corpus(corpus, required_categories=["not_a_category"])
