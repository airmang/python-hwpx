from __future__ import annotations

import hashlib

import pytest

from hwpx.visual.qa_contracts import (
    TAXONOMY_VERSION,
    DefectCategory,
    Evidence,
    FindingSeverity,
    NormalizedBBox,
    PageVerdict,
    Provenance,
    VerdictStatus,
    VisualFinding,
    VisualVerdict,
)


SHA = hashlib.sha256(b"page").hexdigest()
CROP_SHA = hashlib.sha256(b"crop").hexdigest()


def _finding(severity: FindingSeverity = FindingSeverity.CRITICAL) -> VisualFinding:
    bbox = NormalizedBBox(0.1, 0.2, 0.4, 0.5)
    return VisualFinding(
        "vf-test",
        0,
        bbox,
        DefectCategory.TEXT_CLIPPING_OVERLAP,
        severity,
        0.95,
        Evidence(SHA, CROP_SHA, bbox),
        Provenance("test-detector", "1.0.0"),
        "test finding",
    )


@pytest.mark.parametrize(
    "coords",
    [(-0.1, 0, 1, 1), (0, 0, 1.1, 1), (0.5, 0, 0.5, 1), (0, 0.8, 1, 0.2)],
)
def test_normalized_bbox_rejects_invalid_coordinates(coords) -> None:
    with pytest.raises(ValueError):
        NormalizedBBox(*coords)


def test_critical_finding_cannot_be_hidden_by_aggregate() -> None:
    page = PageVerdict.build(page=0, page_sha256=SHA, findings=[_finding()])
    verdict = VisualVerdict.build(
        expected_pages=[0], pages=[page], assurance="fixture", render_checked=False
    )
    assert verdict.taxonomy_version == TAXONOMY_VERSION
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.critical_count == 1
    assert verdict.needs_review is True


def test_missing_or_unexpected_page_fails_closed() -> None:
    missing = VisualVerdict.build(
        expected_pages=[0, 1], pages=[PageVerdict.build(page=0, page_sha256=SHA, findings=[])],
        assurance="fixture", render_checked=False,
    )
    assert missing.status is VerdictStatus.UNVERIFIED
    assert missing.missing_pages == (1,)

    unexpected = VisualVerdict.build(
        expected_pages=[0],
        pages=[
            PageVerdict.build(page=0, page_sha256=SHA, findings=[]),
            PageVerdict.build(page=1, page_sha256=SHA, findings=[]),
        ],
        assurance="fixture", render_checked=False,
    )
    assert unexpected.status is VerdictStatus.UNVERIFIED
    assert unexpected.unexpected_pages == (1,)


def test_fixture_can_never_claim_render_checked() -> None:
    with pytest.raises(ValueError, match="fixture evidence"):
        VisualVerdict.build(
            expected_pages=[0], pages=[], assurance="fixture", render_checked=True
        )


def test_verdict_requires_expected_pages_and_known_assurance() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        VisualVerdict.build(expected_pages=[], pages=[], assurance="fixture", render_checked=False)
    with pytest.raises(ValueError, match="unsupported visual assurance"):
        VisualVerdict.build(expected_pages=[0], pages=[], assurance="magic", render_checked=False)
    with pytest.raises(ValueError, match="non-fixture assurance"):
        VisualVerdict.build(
            expected_pages=[0], pages=[], assurance="real_hancom", render_checked=False
        )


def test_contract_serializes_enums_as_values() -> None:
    page = PageVerdict.build(page=0, page_sha256=SHA, findings=[_finding()])
    payload = page.to_dict()
    assert payload["status"] == "fail"
    assert payload["findings"][0]["category"] == "text_clipping_overlap"
