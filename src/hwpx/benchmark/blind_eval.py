"""Contracts and measurements for the S-070 provenance-blind fixture rail.

This module intentionally distinguishes a reproducible fixture simulation from
evidence produced by real agent clients, human controls, human judges, or a
real Hancom renderer.  A fixture report can validate the benchmark machinery;
it can never authorize a human-replacement or release claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

BENCHMARK_SCHEMA = "hwpx.blind-real-work-eval/v1"
RESULT_SCHEMA = "hwpx.blind-real-work-eval-result/v1"
REQUIRED_FAMILIES = (
    "reading_extraction",
    "transactional_editing",
    "known_form_fill",
    "unfamiliar_form_fill",
    "typed_authoring",
    "batch_comparison",
)
_FALSE_FLAGS = (
    "humanControls",
    "humanJudges",
    "realAgentClients",
    "realHancomVerified",
    "humanLabels",
    "replacementClaimAllowed",
)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    """Hash JSON deterministically, excluding its self-referential hash field."""
    payload = dict(value)
    payload.pop("manifestSha256", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _require_fixture_honesty(raw: Mapping[str, Any]) -> None:
    if raw.get("assurance") != "fixture" or raw.get("executionKind") != "fixture_simulation":
        raise ValueError("fixture benchmark must declare fixture assurance and fixture_simulation")
    for key in _FALSE_FLAGS:
        if raw.get(key) is not False:
            raise ValueError(f"fixture benchmark requires {key}=false")


def validate_fixture_manifest(
    value: Mapping[str, Any] | str | Path, *, strict: bool = True
) -> dict[str, Any]:
    """Validate a frozen fixture protocol consumed by ``run_fixture_benchmark``."""
    raw = _load(value)
    if raw.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError(f"unsupported benchmark schema: {raw.get('schema')!r}")
    _require_fixture_honesty(raw)
    for key in ("benchmarkId", "protocolVersion", "promptVersion", "rubricVersion", "provenanceRandomizationSeed"):
        if not raw.get(key):
            raise ValueError(f"fixture benchmark requires {key}")
    digest = raw.get("manifestSha256")
    if digest and digest != canonical_sha256(raw):
        raise ValueError("fixture benchmark manifest hash mismatch")

    orders = raw.get("workOrders")
    clients = raw.get("clients")
    if not isinstance(orders, list) or not isinstance(clients, list):
        raise ValueError("workOrders and clients must be arrays")
    order_ids = [item.get("workOrderId") for item in orders]
    client_ids = [item.get("clientId") for item in clients]
    if None in order_ids or len(order_ids) != len(set(order_ids)):
        raise ValueError("workOrderId values must be present and unique")
    if None in client_ids or len(client_ids) != len(set(client_ids)):
        raise ValueError("clientId values must be present and unique")
    families = Counter(item.get("family") for item in orders)
    unknown = set(families) - set(REQUIRED_FAMILIES)
    if unknown:
        raise ValueError(f"unknown work-order families: {sorted(unknown)}")
    if strict and (len(orders) < 60 or any(families[name] == 0 for name in REQUIRED_FAMILIES)):
        raise ValueError("strict fixture benchmark requires >=60 orders across all six families")
    if strict and len(clients) < 3:
        raise ValueError("strict fixture benchmark requires at least three fixture clients")
    if any(item.get("clientType") != "fixture_agent_client" for item in clients):
        raise ValueError("fixture clients must use clientType=fixture_agent_client")
    if any(item.get("hostSpecificHints") is not False for item in clients):
        raise ValueError("fixture clients must explicitly disable host-specific hints")
    return raw


def validate_fixture_result_manifest(
    value: Mapping[str, Any] | str | Path, *, strict: bool = True
) -> dict[str, Any]:
    """Validate fixture artifacts and two independent agent-judge passes."""
    raw = _load(value)
    if raw.get("schema") != RESULT_SCHEMA:
        raise ValueError(f"unsupported result schema: {raw.get('schema')!r}")
    _require_fixture_honesty(raw)
    protocol = validate_fixture_manifest(raw.get("protocol", {}), strict=strict)
    order_ids = {item["workOrderId"] for item in protocol["workOrders"]}
    client_ids = {item["clientId"] for item in protocol["clients"]}
    artifacts = raw.get("artifacts")
    judgments = raw.get("judgments")
    if not isinstance(artifacts, list) or not isinstance(judgments, list):
        raise ValueError("artifacts and judgments must be arrays")
    artifact_ids = [item.get("artifactId") for item in artifacts]
    blind_ids = [item.get("blindId") for item in artifacts]
    if None in artifact_ids or len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("artifactId values must be present and unique")
    if None in blind_ids or len(blind_ids) != len(set(blind_ids)):
        raise ValueError("blindId values must be present and unique")
    if any(item.get("workOrderId") not in order_ids for item in artifacts):
        raise ValueError("artifact references an unknown work order")
    if any(item.get("clientId") not in client_ids for item in artifacts):
        raise ValueError("artifact references an unknown fixture client")
    if any(
        item.get("provenanceHiddenFromJudges") is not True
        or item.get("filenameMetadataStripped") is not True
        or item.get("transcriptExcludedFromJudges") is not True
        for item in artifacts
    ):
        raise ValueError("artifact judge packets must hide provenance, metadata, and transcripts")
    expected_pairs = {(order, client) for order in order_ids for client in client_ids}
    actual_pairs = {(item["workOrderId"], item["clientId"]) for item in artifacts}
    if strict and actual_pairs != expected_pairs:
        raise ValueError("strict result requires one artifact for every work-order/client pair")
    by_artifact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for judgment in judgments:
        if judgment.get("artifactId") not in set(artifact_ids):
            raise ValueError("judgment references an unknown artifact")
        if judgment.get("judgeType") != "agent_judge" or judgment.get("humanLabel") is not False:
            raise ValueError("fixture judgments must be agent_judge with humanLabel=false")
        scores = judgment.get("scores", {})
        if set(scores) != {"semanticCorrectness", "hwpxFidelity", "visualQuality", "koreanOfficeCompliance", "taskCompleteness", "manualEditNecessity"}:
            raise ValueError("judgment rubric scores are incomplete")
        if any(not isinstance(score, int) or not 0 <= score <= 5 for score in scores.values()):
            raise ValueError("rubric scores must be integers in [0, 5]")
        by_artifact[judgment["artifactId"]].append(judgment)
    for artifact_id in artifact_ids:
        rows = by_artifact[artifact_id]
        judges = {row.get("judgeId") for row in rows}
        if strict and (len(rows) < 2 or len(judges) < 2):
            raise ValueError(f"artifact {artifact_id} requires two independent agent judges")
    return raw


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _rate(successes: int, total: int) -> dict[str, Any]:
    return {"successes": successes, "total": total, "rate": successes / total if total else None,
            "rate95CI": wilson_interval(successes, total)}


def measure_fixture_benchmark(value: Mapping[str, Any] | str | Path, *, strict: bool = True) -> dict[str, Any]:
    """Aggregate the frozen fixture result without upgrading its assurance."""
    raw = validate_fixture_result_manifest(value, strict=strict)
    protocol = raw["protocol"]
    order_by_id = {item["workOrderId"]: item for item in protocol["workOrders"]}
    judgments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw["judgments"]:
        judgments[row["artifactId"]].append(row)

    rows: list[dict[str, Any]] = []
    for artifact in raw["artifacts"]:
        votes = judgments[artifact["artifactId"]]
        accepted_votes = sum(bool(item.get("acceptedWithoutManualHwpxEdit")) for item in votes)
        accepted = accepted_votes * 2 >= len(votes)
        rows.append({**artifact, "family": order_by_id[artifact["workOrderId"]]["family"], "accepted": accepted})

    routine = [row for row in rows if order_by_id[row["workOrderId"]].get("difficulty") == "routine"]
    first_pass = [row for row in routine if row["accepted"] and row.get("repairRounds", 0) == 0]
    after_repair = [row for row in routine if row["accepted"]]
    must_abstain = [row for row in rows if order_by_id[row["workOrderId"]].get("difficulty") == "must_abstain"]
    correct_abstain = [row for row in must_abstain if row.get("status") == "abstained"]
    critical_failures = sum(bool(item.get("criticalFailure")) for item in raw["judgments"])

    def grouped(key: str) -> dict[str, Any]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            buckets[str(row[key])].append(row)
        return {name: _rate(sum(item["accepted"] for item in items), len(items)) for name, items in sorted(buckets.items())}

    judge_pairs = 0
    agreements = 0
    for votes in judgments.values():
        for index, left in enumerate(votes):
            for right in votes[index + 1:]:
                judge_pairs += 1
                agreements += left.get("acceptedWithoutManualHwpxEdit") == right.get("acceptedWithoutManualHwpxEdit")

    observed = _rate(len(first_pass), len(routine))
    return {
        "schema": "hwpx.blind-real-work-eval-metrics/v1",
        "assurance": "fixture",
        "executionKind": "fixture_simulation",
        **{key: False for key in _FALSE_FLAGS},
        "benchmarkGatePassed": critical_failures == 0 and observed["rate"] is not None and observed["rate"] >= 0.90,
        "releaseGatePassed": False,
        "claimBoundary": "Fixture clients and agent judges validate the rail only; no human replacement claim is allowed.",
        "counts": {"workOrders": len(protocol["workOrders"]), "fixtureClients": len(protocol["clients"]),
                   "artifacts": len(rows), "agentJudgments": len(raw["judgments"]), "criticalFailures": critical_failures},
        "routineFirstPassAcceptance": observed,
        "routineAcceptanceAfterAutonomousRepair": _rate(len(after_repair), len(routine)),
        "mustAbstainQuality": _rate(len(correct_abstain), len(must_abstain)),
        "agreement": {"pairCount": judge_pairs, "exactAcceptanceAgreement": agreements / judge_pairs if judge_pairs else None},
        "humanInvolvement": {"reviewMinutes": None, "editMinutes": None, "measured": False},
        "cost": {"currency": None, "total": None, "measured": False},
        "perFamily": grouped("family"),
        "perClient": grouped("clientId"),
        "thresholds": {"routineFirstPassAcceptance": 0.90, "criticalFailures": 0},
    }


def build_result_projections(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Generate every public-facing fixture projection from one metrics object."""
    if metrics.get("schema") != "hwpx.blind-real-work-eval-metrics/v1":
        raise ValueError("unsupported metrics schema")
    summary = {
        "assurance": "fixture",
        "replacementClaimAllowed": False,
        "realHancomVerified": False,
        "releaseGatePassed": False,
        "routineFirstPassAcceptance": metrics["routineFirstPassAcceptance"],
        "perFamily": metrics["perFamily"],
        "counts": metrics["counts"],
    }
    return {
        "scorecard": {"schema": "hwpx.scorecard-benchmark-projection/v1", **summary},
        "roadmap": {"schema": "hwpx.roadmap-benchmark-projection/v1", **summary},
        "gallery": {"schema": "hwpx.gallery-benchmark-projection/v1", **summary},
        "releaseMetrics": {"schema": "hwpx.release-benchmark-projection/v1", **summary},
    }


def check_projection_drift(metrics: Mapping[str, Any], projections: Mapping[str, Any]) -> None:
    expected = build_result_projections(metrics)
    if projections != expected:
        raise ValueError("generated benchmark projection drift detected")


__all__ = [
    "BENCHMARK_SCHEMA", "RESULT_SCHEMA", "REQUIRED_FAMILIES", "canonical_sha256",
    "validate_fixture_manifest", "validate_fixture_result_manifest", "wilson_interval",
    "measure_fixture_benchmark", "build_result_projections", "check_projection_drift",
]
