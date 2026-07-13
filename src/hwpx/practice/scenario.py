"""Versioned, privacy-safe deterministic practice-scenario contract."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .registry import DOCUMENT_ID_PATTERN, SHA256_PATTERN, assert_redacted_payload

PRACTICE_SCENARIO_SCHEMA = "hwpx.practice-scenario/v1"
SCENARIO_ID_PATTERN = re.compile(r"^SCN-[A-F0-9]{20}$")
LINEAGE_ID_PATTERN = re.compile(r"^LIN-[A-F0-9]{20}$")
TASK_KINDS = frozenset({
    "reverse_restore",
    "constrained_edit",
    "known_template_fill",
    "unknown_form_fill",
    "structural_edit",
    "typed_authoring",
    "must_abstain",
})
EXPECTED_TERMINAL_STATES = frozenset({
    "completed",
    "needs_review",
    "failed",
    "unverified",
    "refused",
})


def _canonical_payload(value: Mapping[str, Any]) -> bytes:
    payload = dict(value)
    payload.pop("scenarioId", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return encoded.encode("utf-8")


def scenario_id(value: Mapping[str, Any]) -> str:
    """Return a deterministic ID for a privacy-safe scenario payload."""
    assert_redacted_payload(value)
    token = hashlib.sha256(_canonical_payload(value)).hexdigest()[:20].upper()
    return f"SCN-{token}"


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def validate_scenario(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a scenario without reading source or holdout content."""
    raw = dict(_require_mapping(value, "scenario"))
    assert_redacted_payload(raw)
    if raw.get("schema") != PRACTICE_SCENARIO_SCHEMA:
        raise ValueError("unsupported practice scenario schema")
    if not DOCUMENT_ID_PATTERN.fullmatch(str(raw.get("sourceDocumentId", ""))):
        raise ValueError("sourceDocumentId must be opaque")
    if not LINEAGE_ID_PATTERN.fullmatch(str(raw.get("lineageGroup", ""))):
        raise ValueError("lineageGroup must be opaque")
    if raw.get("split") not in {"practice", "validation", "holdout"}:
        raise ValueError("unsupported scenario split")
    if raw.get("taskKind") not in TASK_KINDS:
        raise ValueError("unsupported taskKind")
    if not raw.get("family") or not raw.get("difficulty"):
        raise ValueError("family and difficulty are required")
    if not isinstance(raw.get("instruction"), str) or not raw["instruction"].strip():
        raise ValueError("a synthetic instruction is required")
    if raw.get("expectedTerminalState") not in EXPECTED_TERMINAL_STATES:
        raise ValueError("unsupported expectedTerminalState")

    privacy = _require_mapping(raw.get("privacy"), "privacy")
    if privacy.get("syntheticInputsOnly") is not True or privacy.get("localOnly") is not True:
        raise ValueError("practice scenarios require syntheticInputsOnly and localOnly")

    start = _require_mapping(raw.get("startArtifact"), "startArtifact")
    if not start.get("artifactId") or not SHA256_PATTERN.fullmatch(str(start.get("sha256", ""))):
        raise ValueError("startArtifact requires artifactId and sha256")

    budgets = _require_mapping(raw.get("budgets"), "budgets")
    for key in ("toolCalls", "attempts", "repairRounds", "elapsedSeconds"):
        if not isinstance(budgets.get(key), int) or budgets[key] < 0:
            raise ValueError(f"budgets.{key} must be a non-negative integer")
    if budgets["repairRounds"] > 3:
        raise ValueError("repairRounds cannot exceed 3")

    visibility = _require_mapping(raw.get("visibility"), "visibility")
    if visibility.get("runnerCanReadGold") is not False:
        raise ValueError("the runner cannot read gold answers")
    if raw["split"] == "holdout" and visibility.get("generatorCanReadGold") is not False:
        raise ValueError("the generator cannot read holdout gold answers")

    oracles = raw.get("oracles")
    if not isinstance(oracles, list) or not oracles:
        raise ValueError("at least one oracle is required")
    for oracle in oracles:
        row = _require_mapping(oracle, "oracle")
        if not row.get("kind") or not isinstance(row.get("required"), bool) or not row.get("provenance"):
            raise ValueError("each oracle requires kind, required, and provenance")

    if raw.get("visualCompleteExpected") is True and not any(
        oracle.get("kind") == "real_hancom"
        and oracle.get("required") is True
        and oracle.get("provenance") == "real_hancom"
        for oracle in oracles
    ):
        raise ValueError("visual completion requires a required real-Hancom oracle")

    gold = _require_mapping(raw.get("gold"), "gold")
    if not gold.get("kind") or not (gold.get("verifierId") or SHA256_PATTERN.fullmatch(str(gold.get("sha256", "")))):
        raise ValueError("gold requires kind plus verifierId or sha256")

    expected_id = scenario_id(raw)
    supplied_id = str(raw.get("scenarioId", ""))
    if supplied_id and (not SCENARIO_ID_PATTERN.fullmatch(supplied_id) or supplied_id != expected_id):
        raise ValueError("scenarioId does not match the canonical scenario payload")
    raw["scenarioId"] = expected_id
    return raw


__all__ = [
    "EXPECTED_TERMINAL_STATES",
    "PRACTICE_SCENARIO_SCHEMA",
    "SCENARIO_ID_PATTERN",
    "TASK_KINDS",
    "scenario_id",
    "validate_scenario",
]
