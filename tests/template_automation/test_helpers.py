from __future__ import annotations

from .helpers import (
    find_normalized_range,
    load_scenario_cases,
    normalize_whitespace,
)


def test_normalize_whitespace_removes_irregular_spacing() -> None:
    assert normalize_whitespace("Han   River \t High") == "HanRiverHigh"


def test_find_normalized_range_maps_to_original_offsets() -> None:
    text = "School Name: Han   River    High"

    start, end = find_normalized_range(text, "Han River High") or (-1, -1)

    assert text[start:end] == "Han   River    High"


def test_fixture_loader_discovers_expected_fixture_ids() -> None:
    cases = load_scenario_cases()

    fixture_ids = {case.fixture_id for case in cases}

    assert fixture_ids == {
        "checkbox-toggle",
        "extract-repack",
        "header-footer-placeholder",
        "multi-section-placeholder",
        "nonstandard-rootfile",
        "repeated-placeholder",
        "simple-placeholder",
        "split-run-placeholder",
        "table-placeholder",
        "whitespace-variant",
    }
    assert len(cases) >= 12
