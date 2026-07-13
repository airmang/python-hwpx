from __future__ import annotations

import copy
import hashlib
import os
from collections import Counter
from pathlib import Path

import pytest

from hwpx.practice import (
    ForgeConfig,
    build_split_manifest,
    forge_scenario_pack,
    validate_scenario_pack,
    write_scenario_pack,
)
from hwpx.practice.registry import REDACTED_REGISTRY_SCHEMA


def _record(index: int, family: str, eligibility: str = "normal") -> dict:
    return {
        "schema": REDACTED_REGISTRY_SCHEMA,
        "documentId": f"HWC-{index:020X}",
        "family": family,
        "state": "template" if index % 2 else "clean",
        "complexity": ("low", "medium", "high")[index % 3],
        "privacyDisposition": (
            "repair_negative" if eligibility == "negative_control" else "approved_local_only"
        ),
        "practiceEligibility": eligibility,
        "lineageGroup": f"LIN-{index:020X}",
        "suitability": "candidate_template",
        "openSafetyOk": eligibility == "normal",
    }


def _fixture() -> tuple[dict, dict, ForgeConfig]:
    records = []
    index = 0
    for family_index in range(10):
        family = f"safe-family-{family_index:02d}"
        records.extend((_record(index, family), _record(index + 1, family)))
        index += 2
        if family_index in {0, 1}:
            records.append(_record(index, family, "negative_control"))
            index += 1
    records.extend(
        (
            _record(index, "negative-only-photo", "negative_control"),
            _record(index + 1, "negative-only-repair", "negative_control"),
        )
    )
    manifest = build_split_manifest(records, seed="split-seed", corpus_version="fixture-v1")
    catalog = {
        entry["documentId"]: {
            "artifactId": f"ART-{entry['documentId'][4:]}",
            "sha256": hashlib.sha256(entry["documentId"].encode()).hexdigest(),
        }
        for entry in manifest["entries"]
    }
    return manifest, catalog, ForgeConfig(seed="scenario-seed")


def test_forge_builds_deterministic_balanced_120_scenario_pack() -> None:
    manifest, catalog, config = _fixture()
    first = forge_scenario_pack(manifest, catalog, config=config)
    second = forge_scenario_pack(manifest, dict(reversed(list(catalog.items()))), config=config)

    assert first == second
    assert validate_scenario_pack(first, config=config) == first
    summary = first["summary"]
    assert summary["scenarioCount"] == 120
    assert len(summary["representedFamilies"]) == 10
    assert set(summary["missingFamilyCoverage"]) == {
        "negative-only-photo",
        "negative-only-repair",
    }
    assert max(summary["byFamily"].values()) == 12
    assert summary["maximumFamilyShare"] == 0.1
    assert summary["byTaskKind"] == {
        "constrained_edit": 18,
        "known_template_fill": 24,
        "must_abstain": 12,
        "reverse_restore": 24,
        "structural_edit": 12,
        "typed_authoring": 12,
        "unknown_form_fill": 18,
    }


def test_runner_manifest_hides_gold_split_lineage_and_expected_state() -> None:
    manifest, catalog, config = _fixture()
    pack = forge_scenario_pack(manifest, catalog, config=config)
    forbidden = {
        "gold",
        "expectedTerminalState",
        "lineageGroup",
        "sourceDocumentId",
        "sourceEligibility",
        "split",
        "visibility",
    }
    for work_order in pack["runnerManifest"]["scenarios"]:
        assert not forbidden & set(work_order)


def test_task_oracles_and_negative_control_rules_are_fail_closed() -> None:
    manifest, catalog, config = _fixture()
    scenarios = forge_scenario_pack(manifest, catalog, config=config)["evaluatorManifest"]["scenarios"]
    by_task = {task: [item for item in scenarios if item["taskKind"] == task] for task in Counter(item["taskKind"] for item in scenarios)}

    assert all(
        item["gold"]["sha256"] == item["startArtifact"]["sha256"]
        for item in by_task["reverse_restore"]
    )
    assert all(
        {"form_mapping", "form_residue"}
        <= {oracle["kind"] for oracle in item["oracles"]}
        for task in ("known_template_fill", "unknown_form_fill")
        for item in by_task[task]
    )
    assert all(
        item["expectedTerminalState"] == "unverified"
        and item["visualCompleteExpected"] is True
        and any(
            oracle == {"kind": "real_hancom", "required": True, "provenance": "real_hancom"}
            for oracle in item["oracles"]
        )
        for item in by_task["typed_authoring"]
    )
    assert all(
        item["taskKind"] == "must_abstain"
        for item in scenarios
        if item["sourceEligibility"] == "negative_control"
    )


def test_pack_hashes_and_summary_tampering_are_detected() -> None:
    manifest, catalog, config = _fixture()
    pack = forge_scenario_pack(manifest, catalog, config=config)
    tampered = copy.deepcopy(pack)
    tampered["summary"]["scenarioCount"] = 121
    with pytest.raises(ValueError, match="summary count"):
        validate_scenario_pack(tampered, config=config)

    tampered = copy.deepcopy(pack)
    tampered["runnerManifest"]["scenarios"][0]["gold"] = {"verifierId": "leak"}
    with pytest.raises(ValueError, match="runner manifest hash"):
        validate_scenario_pack(tampered, config=config)


def test_write_pack_separates_runner_and_evaluator_files(tmp_path: Path) -> None:
    manifest, catalog, config = _fixture()
    pack = forge_scenario_pack(manifest, catalog, config=config)
    evaluator = tmp_path / "private" / "evaluator.json"
    runner = tmp_path / "runner" / "manifest.json"
    summary = tmp_path / "summary.json"
    write_scenario_pack(
        pack,
        evaluator_path=evaluator,
        runner_path=runner,
        summary_path=summary,
        config=config,
    )

    assert '"gold"' in evaluator.read_text(encoding="utf-8")
    assert '"gold"' not in runner.read_text(encoding="utf-8")
    assert os.stat(evaluator).st_mode & 0o777 == 0o600
    assert os.stat(runner).st_mode & 0o777 == 0o600
