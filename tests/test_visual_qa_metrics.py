from pathlib import Path

from hwpx.visual.fixture_corpus import load_fixture_manifest
from hwpx.visual.qa_metrics import measure_fixture_corpus


def test_frozen_fixture_metrics_pass_and_remain_unverified() -> None:
    manifest = Path(__file__).parent / "fixtures" / "visual_qa_v1" / "manifest.json"
    report = measure_fixture_corpus(load_fixture_manifest(manifest))
    assert report["gatePassed"] is True
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
