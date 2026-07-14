"""Content-addressed campaign manifest contract for durable practice."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .registry import SHA256_PATTERN
from .run import (
    OPAQUE_ID_PATTERN,
    RUN_ID_PATTERN,
    TERMINAL_RUN_STATES,
    assert_receipt_safe,
    validate_exact_provenance,
    validate_run_budgets,
)
from .scenario import SCENARIO_ID_PATTERN

PRACTICE_CAMPAIGN_MANIFEST_SCHEMA = "hwpx.practice-campaign-manifest/v1"
CAMPAIGN_ID_PATTERN = re.compile(r"^PCMP-[A-F0-9]{20}$")

ACTIVE_CAMPAIGN_STATES = frozenset({"queued", "running", "cancelling"})
TERMINAL_CAMPAIGN_STATES = frozenset(
    {"completed", "cancelled", "failed", "budget_exhausted", "incomplete"}
)
CAMPAIGN_STATES = ACTIVE_CAMPAIGN_STATES | TERMINAL_CAMPAIGN_STATES
CAMPAIGN_BUDGET_FIELDS = (
    "runs",
    "toolCalls",
    "elapsedSeconds",
    "costMicrounits",
    "artifactBytes",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise ValueError(
            f"{name} fields mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _require_int(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _require_sha(value: object, name: str) -> str:
    digest = str(value or "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return digest


def _validate_campaign_budgets(value: Mapping[str, Any], run_count: int) -> dict[str, int]:
    raw = dict(_require_mapping(value, "campaign budgets"))
    _require_exact_keys(raw, set(CAMPAIGN_BUDGET_FIELDS), "campaign budgets")
    result = {
        key: _require_int(raw[key], f"campaign budgets.{key}")
        for key in CAMPAIGN_BUDGET_FIELDS
    }
    if result["runs"] != run_count:
        raise ValueError("campaign budgets.runs must equal the frozen run count")
    if run_count and result["elapsedSeconds"] < 1:
        raise ValueError("a non-empty campaign requires an elapsed-time ceiling")
    return result


def _validate_selection(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "selection"))
    _require_exact_keys(
        raw, {"seedSha256", "strategyVersion", "policySha256"}, "selection"
    )
    strategy = str(raw["strategyVersion"]).strip()
    if not strategy or strategy.casefold() in {"candidate", "latest", "unknown"}:
        raise ValueError("selection.strategyVersion must be exact")
    return {
        "seedSha256": _require_sha(raw["seedSha256"], "selection.seedSha256"),
        "strategyVersion": strategy,
        "policySha256": _require_sha(raw["policySha256"], "selection.policySha256"),
    }


def _validate_run_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "campaign run reference"))
    expected = {
        "slot",
        "runId",
        "scenarioId",
        "scenarioSha256",
        "evaluationPolicySha256",
        "runnerManifestSha256",
        "derivativeSha256",
        "startArtifactId",
        "startArtifactSha256",
        "family",
        "difficulty",
        "budgets",
    }
    _require_exact_keys(raw, expected, "campaign run reference")
    slot = _require_int(raw["slot"], "campaign run slot")
    if not RUN_ID_PATTERN.fullmatch(str(raw["runId"])):
        raise ValueError("campaign runId must be opaque")
    if not SCENARIO_ID_PATTERN.fullmatch(str(raw["scenarioId"])):
        raise ValueError("campaign scenarioId must be opaque")
    if not OPAQUE_ID_PATTERN.fullmatch(str(raw["startArtifactId"])):
        raise ValueError("campaign startArtifactId must be opaque")
    family = str(raw["family"])
    difficulty = str(raw["difficulty"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", family):
        raise ValueError("campaign family must be a closed code")
    if difficulty not in {"routine", "intermediate", "advanced"}:
        raise ValueError("unsupported campaign difficulty")
    return {
        "slot": slot,
        "runId": str(raw["runId"]),
        "scenarioId": str(raw["scenarioId"]),
        "scenarioSha256": _require_sha(
            raw["scenarioSha256"], "campaign run scenarioSha256"
        ),
        "evaluationPolicySha256": _require_sha(
            raw["evaluationPolicySha256"],
            "campaign run evaluationPolicySha256",
        ),
        "runnerManifestSha256": _require_sha(
            raw["runnerManifestSha256"], "campaign run runnerManifestSha256"
        ),
        "derivativeSha256": _require_sha(
            raw["derivativeSha256"], "campaign run derivativeSha256"
        ),
        "startArtifactId": str(raw["startArtifactId"]),
        "startArtifactSha256": _require_sha(
            raw["startArtifactSha256"], "campaign run startArtifactSha256"
        ),
        "family": family,
        "difficulty": difficulty,
        "budgets": validate_run_budgets(raw["budgets"]),
    }


def _validate_privacy(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "campaign privacy"))
    expected = {
        "localOnly",
        "syntheticInputsOnly",
        "privateCoordinatesExposed",
        "evaluatorDataExposed",
    }
    _require_exact_keys(raw, expected, "campaign privacy")
    if raw != {
        "localOnly": True,
        "syntheticInputsOnly": True,
        "privateCoordinatesExposed": False,
        "evaluatorDataExposed": False,
    }:
        raise ValueError("campaign privacy boundary must be local, synthetic, and closed")
    return raw


def campaign_manifest_sha256(value: Mapping[str, Any]) -> str:
    """Hash canonical manifest content, excluding its self-address fields."""

    payload = dict(_require_mapping(value, "campaign manifest"))
    payload.pop("campaignId", None)
    payload.pop("manifestSha256", None)
    assert_receipt_safe(payload)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _campaign_id(value: Mapping[str, Any]) -> str:
    return f"PCMP-{campaign_manifest_sha256(value)[:20].upper()}"


def validate_campaign_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the frozen manifest and detect membership/order tampering."""

    raw = dict(_require_mapping(value, "campaign manifest"))
    assert_receipt_safe(raw)
    expected = {
        "schema",
        "campaignId",
        "manifestSha256",
        "scenarioManifestSha256",
        "selection",
        "provenance",
        "budgets",
        "runs",
        "expectedRunCount",
        "terminalStatePolicy",
        "campaignTerminalStatePolicy",
        "privacy",
    }
    _require_exact_keys(raw, expected, "campaign manifest")
    if raw["schema"] != PRACTICE_CAMPAIGN_MANIFEST_SCHEMA:
        raise ValueError("unsupported practice campaign manifest schema")
    raw["scenarioManifestSha256"] = _require_sha(
        raw["scenarioManifestSha256"], "scenarioManifestSha256"
    )
    raw["selection"] = _validate_selection(raw["selection"])
    raw["provenance"] = validate_exact_provenance(raw["provenance"])
    raw["privacy"] = _validate_privacy(raw["privacy"])

    runs_value = raw["runs"]
    if not isinstance(runs_value, list) or not runs_value:
        raise ValueError("campaign manifest requires at least one run")
    runs = [_validate_run_reference(item) for item in runs_value]
    expected_slots = list(range(len(runs)))
    if [item["slot"] for item in runs] != expected_slots:
        raise ValueError("campaign run slots must be contiguous, ordered, and unique")
    if len({item["runId"] for item in runs}) != len(runs):
        raise ValueError("campaign run IDs must be unique")
    if len({item["scenarioId"] for item in runs}) != len(runs):
        raise ValueError("campaign scenario IDs must be unique")
    raw["runs"] = runs
    expected_count = _require_int(raw["expectedRunCount"], "expectedRunCount")
    if expected_count != len(runs):
        raise ValueError("expectedRunCount must match frozen campaign membership")
    raw["budgets"] = _validate_campaign_budgets(raw["budgets"], len(runs))

    expected_run_states = sorted(TERMINAL_RUN_STATES)
    expected_campaign_states = sorted(TERMINAL_CAMPAIGN_STATES)
    if raw["terminalStatePolicy"] != expected_run_states:
        raise ValueError("terminalStatePolicy must freeze every actual run terminal state")
    if raw["campaignTerminalStatePolicy"] != expected_campaign_states:
        raise ValueError("campaignTerminalStatePolicy is incomplete or reordered")

    expected_hash = campaign_manifest_sha256(raw)
    supplied_hash = str(raw["manifestSha256"])
    if not SHA256_PATTERN.fullmatch(supplied_hash) or supplied_hash != expected_hash:
        raise ValueError("manifestSha256 does not match canonical campaign content")
    supplied_id = str(raw["campaignId"])
    if not CAMPAIGN_ID_PATTERN.fullmatch(supplied_id) or supplied_id != _campaign_id(raw):
        raise ValueError("campaignId does not match canonical campaign content")
    return raw


def build_campaign_manifest(
    *,
    scenario_manifest_sha256: str,
    selection: Mapping[str, Any],
    provenance: Mapping[str, Any],
    budgets: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic campaign manifest from already selected run refs."""

    manifest: dict[str, Any] = {
        "schema": PRACTICE_CAMPAIGN_MANIFEST_SCHEMA,
        "scenarioManifestSha256": scenario_manifest_sha256,
        "selection": dict(selection),
        "provenance": dict(provenance),
        "budgets": dict(budgets),
        "runs": [dict(item) for item in runs],
        "expectedRunCount": len(runs),
        "terminalStatePolicy": sorted(TERMINAL_RUN_STATES),
        "campaignTerminalStatePolicy": sorted(TERMINAL_CAMPAIGN_STATES),
        "privacy": {
            "localOnly": True,
            "syntheticInputsOnly": True,
            "privateCoordinatesExposed": False,
            "evaluatorDataExposed": False,
        },
    }
    assert_receipt_safe(manifest)
    manifest["manifestSha256"] = campaign_manifest_sha256(manifest)
    manifest["campaignId"] = _campaign_id(manifest)
    return validate_campaign_manifest(manifest)


__all__ = [
    "ACTIVE_CAMPAIGN_STATES",
    "CAMPAIGN_BUDGET_FIELDS",
    "CAMPAIGN_STATES",
    "PRACTICE_CAMPAIGN_MANIFEST_SCHEMA",
    "TERMINAL_CAMPAIGN_STATES",
    "build_campaign_manifest",
    "campaign_manifest_sha256",
    "validate_campaign_manifest",
]
