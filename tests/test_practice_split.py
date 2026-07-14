from __future__ import annotations

import copy

import pytest

from hwpx.practice import build_split_manifest, validate_split_manifest
from hwpx.practice.registry import REDACTED_REGISTRY_SCHEMA


def _record(index: int, *, group: int | None = None, eligibility: str = "normal") -> dict:
    return {
        "schema": REDACTED_REGISTRY_SCHEMA,
        "documentId": f"HWC-{index:020X}",
        "family": f"family-{index % 4}",
        "state": "clean" if index % 2 else "template",
        "complexity": ("low", "medium", "high")[index % 3],
        "privacyDisposition": "approved_local_only",
        "practiceEligibility": eligibility,
        "lineageGroup": f"LIN-{(index if group is None else group):020X}",
        "suitability": "candidate_template",
        "openSafetyOk": True,
    }


def test_split_is_deterministic_stratified_and_lineage_closed() -> None:
    records = [_record(index) for index in range(30)]
    records[1]["lineageGroup"] = records[0]["lineageGroup"]
    records[2]["lineageGroup"] = records[0]["lineageGroup"]

    first = build_split_manifest(records, seed="corpus-v1", corpus_version="2026-07-13")
    second = build_split_manifest(
        list(reversed(records)), seed="corpus-v1", corpus_version="2026-07-13"
    )

    assert first == second
    assert validate_split_manifest(first) == first
    assert first["counts"]["eligible"] == 30
    assert sum(first["counts"]["bySplit"].values()) == 30
    assert abs(first["counts"]["bySplit"]["practice"] - 18) <= 3
    assert abs(first["counts"]["bySplit"]["validation"] - 6) <= 2
    assert abs(first["counts"]["bySplit"]["holdout"] - 6) <= 2
    assignments = {entry["documentId"]: entry["split"] for entry in first["entries"]}
    assert len({assignments[records[index]["documentId"]] for index in range(3)}) == 1
    assert not ({"source", "filename", "sha256"} & set(first["entries"][0]))


def test_split_excludes_ineligible_but_reports_count() -> None:
    records = [_record(index) for index in range(9)]
    records.extend(_record(index, eligibility="ineligible") for index in range(9, 12))
    manifest = build_split_manifest(records, seed="one", corpus_version="v1")
    assert manifest["counts"]["eligible"] == 9
    assert manifest["counts"]["ineligible"] == 3
    assert len(manifest["entries"]) == 9


def test_split_rejects_private_coordinates_and_duplicate_ids() -> None:
    private = _record(1)
    private["filename"] = "학생명부.hwpx"
    with pytest.raises(ValueError, match="forbidden key"):
        build_split_manifest([private], seed="one", corpus_version="v1")
    duplicate = _record(2)
    with pytest.raises(ValueError, match="unique"):
        build_split_manifest([duplicate, copy.deepcopy(duplicate)], seed="one", corpus_version="v1")


def test_validate_detects_hash_count_and_lineage_tampering() -> None:
    manifest = build_split_manifest(
        [_record(index, group=0 if index < 2 else None) for index in range(8)],
        seed="one",
        corpus_version="v1",
    )
    tampered = copy.deepcopy(manifest)
    tampered["counts"]["eligible"] += 1
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_split_manifest(tampered)

    tampered = copy.deepcopy(manifest)
    same_group = [entry for entry in tampered["entries"] if entry["lineageGroup"] == "LIN-00000000000000000000"]
    same_group[0]["split"] = "practice"
    same_group[1]["split"] = "holdout"
    # Recompute through the public builder is deliberately impossible; a copied
    # trusted hash must fail before the closure check.
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_split_manifest(tampered)
