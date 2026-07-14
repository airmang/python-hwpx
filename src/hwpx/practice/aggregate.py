"""Deterministic, privacy-safe aggregates for one durable practice campaign.

The aggregate is deliberately a projection of a single validated campaign
manifest, its terminal receipts, and optional content-addressed independent
evaluation results.  It never guesses evaluator outcomes: absent evaluation
rows remain explicit missing coverage, and an abstention is correct only when
independent, must-abstain-specific evidence says so.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .campaign import CAMPAIGN_BUDGET_FIELDS, validate_campaign_manifest
from .evaluator import validate_evaluation_result
from .registry import SHA256_PATTERN
from .run import (
    RUN_BUDGET_FIELDS,
    TERMINAL_RUN_STATES,
    assert_receipt_safe,
    validate_run_receipt,
)


PRACTICE_CAMPAIGN_AGGREGATE_SCHEMA = "hwpx.practice-campaign-aggregate/v1"

_ABSTENTION_RUN_STATES = frozenset({"needs_review", "refused", "unverified"})
_DIFFICULTIES = ("routine", "intermediate", "advanced")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_FAMILY_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def _observed_abstention(receipt: Mapping[str, Any]) -> bool:
    return bool(
        receipt["state"] in _ABSTENTION_RUN_STATES
        and any(
            event["kind"] == "decision_gate" and event["status"] == "abstained"
            for event in receipt["workflowEvents"]
        )
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def _new_metrics() -> dict[str, Any]:
    return {
        "scheduledCount": 0,
        "terminalCount": 0,
        "completedCount": 0,
        "verifiedSuccessCount": 0,
        "firstPassSuccessCount": 0,
        "afterRepairSuccessCount": 0,
        "falseCompletionCount": 0,
        "failureStateCount": 0,
        "criticalFailureCount": 0,
        "missingEvidenceCount": 0,
        "abstention": {
            "count": 0,
            "correctCount": 0,
            "incorrectCount": 0,
            "unverifiedCount": 0,
        },
        "evaluation": {
            "passedCount": 0,
            "failedCount": 0,
            "unverifiedCount": 0,
            "missingCount": 0,
        },
        "usage": {field: 0 for field in RUN_BUDGET_FIELDS},
    }


def _add_metrics(
    metrics: dict[str, Any], receipt: Mapping[str, Any], evaluation: Mapping[str, Any] | None
) -> None:
    metrics["scheduledCount"] += 1
    metrics["terminalCount"] += 1
    state = receipt["state"]
    observed_abstention = _observed_abstention(receipt)
    if state == "completed":
        metrics["completedCount"] += 1
        if evaluation is not None and evaluation["eligibleForSuccess"] is True:
            metrics["verifiedSuccessCount"] += 1
            if receipt["usage"]["repairRounds"] == 0:
                metrics["firstPassSuccessCount"] += 1
            else:
                metrics["afterRepairSuccessCount"] += 1
        else:
            metrics["falseCompletionCount"] += 1
    elif not observed_abstention:
        metrics["failureStateCount"] += 1
    for field in RUN_BUDGET_FIELDS:
        metrics["usage"][field] += receipt["usage"][field]

    if evaluation is None:
        metrics["evaluation"]["missingCount"] += 1
        metrics["missingEvidenceCount"] += 1
    else:
        metrics["evaluation"][f"{evaluation['overallStatus']}Count"] += 1
        metrics["criticalFailureCount"] += evaluation["criticalFailureCount"]
        metrics["missingEvidenceCount"] += evaluation["missingEvidenceCount"]

    if not observed_abstention:
        return
    abstention = metrics["abstention"]
    abstention["count"] += 1
    if evaluation is None:
        abstention["unverifiedCount"] += 1
        return
    binding = evaluation["domainProjection"]
    # An actual abstention against an exact non-abstention requirement is
    # incorrect even if another mandatory layer is unavailable.
    if binding["expectedAbstention"] is False:
        abstention["incorrectCount"] += 1
        return
    if evaluation["overallStatus"] == "unverified" or binding["status"] == "unverified":
        abstention["unverifiedCount"] += 1
        return
    if (
        evaluation["overallStatus"] == "passed"
        and binding["status"] == "passed"
        and binding["expectedAbstention"] is True
        and binding["observedAbstention"] is True
        and binding["passedMustAbstainVerifier"] is True
        and "must_abstain" in binding["verifierFamilies"]
    ):
        abstention["correctCount"] += 1
    else:
        abstention["incorrectCount"] += 1


def _weakness_weight(metrics: Mapping[str, Any]) -> int:
    total = metrics["scheduledCount"]
    evaluation = metrics["evaluation"]
    unresolved = (
        metrics["failureStateCount"]
        + evaluation["failedCount"]
        + evaluation["unverifiedCount"]
        + evaluation["missingCount"]
        + metrics["abstention"]["incorrectCount"]
        + metrics["abstention"]["unverifiedCount"]
    )
    return (
        1000 if total == 0 else 1000 + min(4000, (4000 * unresolved + total - 1) // total)
    )


def _finalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    metrics["experimentLocalWeaknessWeightMilliunits"] = _weakness_weight(metrics)
    return metrics


def campaign_aggregate_sha256(value: Mapping[str, Any]) -> str:
    """Hash canonical aggregate content, excluding the self-address."""

    payload = dict(_require_mapping(value, "campaign aggregate"))
    payload.pop("aggregateSha256", None)
    assert_receipt_safe(payload)
    return _sha256(payload)


def build_campaign_aggregate(
    manifest: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    evaluation_results: Sequence[Mapping[str, Any]] = (),
    evaluator_authentication_key: bytes | None = None,
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Build one deterministic aggregate with fail-closed membership binding."""

    campaign = validate_campaign_manifest(manifest)
    if isinstance(receipts, (str, bytes)) or not isinstance(receipts, Sequence):
        raise ValueError("terminal receipts must be a sequence")
    validated_receipts = [validate_run_receipt(item) for item in receipts]
    expected_pairs = [(row["runId"], row["scenarioId"]) for row in campaign["runs"]]
    actual_pairs = [(row["runId"], row["scenarioId"]) for row in validated_receipts]
    if len(actual_pairs) != len(set(actual_pairs)):
        raise ValueError("terminal receipts contain duplicate run/scenario pairs")
    missing = sorted(set(expected_pairs) - set(actual_pairs))
    extra = sorted(set(actual_pairs) - set(expected_pairs))
    if missing or extra or len(actual_pairs) != len(expected_pairs):
        raise ValueError(
            f"terminal receipts are not a campaign bijection (missing={len(missing)}, extra={len(extra)})"
        )
    receipt_by_pair = {
        (row["runId"], row["scenarioId"]): row for row in validated_receipts
    }
    run_by_pair = {
        (row["runId"], row["scenarioId"]): row for row in campaign["runs"]
    }

    for run_ref in campaign["runs"]:
        receipt = receipt_by_pair[(run_ref["runId"], run_ref["scenarioId"])]
        if receipt["provenance"] != campaign["provenance"]:
            raise ValueError("terminal receipt provenance does not match the campaign")
        if receipt["budgets"] != run_ref["budgets"]:
            raise ValueError("terminal receipt budgets do not match the frozen run")

    if isinstance(evaluation_results, (str, bytes)) or not isinstance(
        evaluation_results, Sequence
    ):
        raise ValueError("evaluation results must be a sequence")
    if evaluation_results and evaluator_authentication_key is None:
        raise ValueError(
            "authenticated evaluation results require an evaluator authentication key"
        )
    if evaluation_results:
        if not isinstance(evaluator_authentication_key, bytes):
            raise ValueError("evaluator authentication key must be bytes")
        evaluator_key_id = (
            "EVK-"
            + hashlib.sha256(evaluator_authentication_key).hexdigest()[:20].upper()
        )
        if (
            evaluator_key_id
            != campaign["provenance"]["evaluator"]["authenticationKeyId"]
        ):
            raise ValueError(
                "evaluator authentication key does not match campaign provenance"
            )
    evaluations: list[dict[str, Any]] = []
    for item in evaluation_results:
        if not isinstance(item, Mapping):
            raise ValueError("evaluation result must be an object")
        scenario_ref = item.get("scenarioRef")
        scenario_id = (
            str(scenario_ref.get("scenarioId"))
            if isinstance(scenario_ref, Mapping)
            else ""
        )
        pair = (str(item.get("runId")), scenario_id)
        terminal_receipt = receipt_by_pair.get(pair)
        if terminal_receipt is None:
            raise ValueError("evaluation results contain runs outside the campaign")
        evaluations.append(
            validate_evaluation_result(
                item,
                authentication_key=evaluator_authentication_key,
                terminal_receipt=terminal_receipt,
                domain_oracle_authentication_keys=(
                    domain_oracle_authentication_keys
                ),
            )
        )
    evaluation_pairs = [
        (row["runId"], row["scenarioRef"]["scenarioId"]) for row in evaluations
    ]
    if len(evaluation_pairs) != len(set(evaluation_pairs)):
        raise ValueError("evaluation results contain duplicate run/scenario pairs")
    if not set(evaluation_pairs).issubset(set(expected_pairs)):
        raise ValueError("evaluation results contain runs outside the campaign")
    evaluation_by_pair = {
        (row["runId"], row["scenarioRef"]["scenarioId"]): row
        for row in evaluations
    }
    for pair, evaluation in evaluation_by_pair.items():
        receipt = receipt_by_pair[pair]
        run_ref = run_by_pair[pair]
        if (
            evaluation["evaluatorVersion"]
            != campaign["provenance"]["evaluator"]["version"]
        ):
            raise ValueError("evaluation version does not match campaign provenance")
        if (
            evaluation["evaluatorCodeSha256"]
            != campaign["provenance"]["evaluator"]["sha256"]
        ):
            raise ValueError("evaluation code does not match campaign provenance")
        if evaluation["terminalState"] != receipt["state"]:
            raise ValueError("evaluation terminal state does not match the receipt")
        if evaluation["terminalReceiptSha256"] != receipt["receiptSha256"]:
            raise ValueError("evaluation is not bound to the exact terminal receipt")
        if (
            evaluation["evaluationPolicySha256"]
            != run_ref["evaluationPolicySha256"]
        ):
            raise ValueError("evaluation policy does not match the frozen campaign run")
        campaign_ref = evaluation["campaignRef"]
        if campaign_ref != {
            "campaignId": campaign["campaignId"],
            "manifestSha256": campaign["manifestSha256"],
            "slot": run_ref["slot"],
            "family": run_ref["family"],
            "difficulty": run_ref["difficulty"],
        }:
            raise ValueError("evaluation campaign binding does not match the manifest")
        scenario_ref = evaluation["scenarioRef"]
        for key in (
            "scenarioId",
            "scenarioSha256",
            "runnerManifestSha256",
            "derivativeSha256",
            "startArtifactId",
            "startArtifactSha256",
        ):
            if scenario_ref[key] != run_ref[key]:
                raise ValueError("evaluation scenario binding does not match the campaign")
        projection = evaluation["domainProjection"]
        if projection["scenarioSha256"] != run_ref["scenarioSha256"]:
            raise ValueError("evaluation domain projection does not match the campaign")
        if evaluation["domainBundle"]["requirement"]["family"] != run_ref["family"]:
            raise ValueError("evaluation domain family does not match the campaign")
        observed = _observed_abstention(receipt)
        if projection["observedAbstention"] is True and not observed:
            raise ValueError("evaluation abstention observation disagrees with receipt state")
        artifact_sha = projection["artifactSha256"]
        receipt_artifact_hashes = {
            row["sha256"] for row in receipt["artifacts"] if row["role"] == "output"
        }
        artifact_bound = artifact_sha in receipt_artifact_hashes or (
            (
                projection["expectedAbstention"] is True
                or evaluation["eligibleForSuccess"] is False
            )
            and artifact_sha == run_ref["startArtifactSha256"]
        )
        if not artifact_bound:
            raise ValueError("evaluation artifact is not bound to the terminal receipt")
        layer_by_name = {row["layer"]: row for row in evaluation["layers"]}
        render = receipt["evidence"]["render"]
        visual = receipt["evidence"]["visual"]
        if (
            render["status"] == "passed"
            and render["renderChecked"] is True
            and render["provenance"] == "real_hancom"
        ):
            real_hancom = layer_by_name.get("real_hancom")
            if (
                real_hancom is None
                or real_hancom["status"] != "passed"
                or real_hancom["layerReceiptSha256"]
                != render["receiptSha256"]
            ):
                raise ValueError(
                    "real-Hancom receipt is not bound to authenticated evaluation"
                )
        if visual["status"] == "passed":
            visual_layer = layer_by_name.get("visual")
            if (
                visual_layer is None
                or visual_layer["status"] != "passed"
                or visual_layer["layerReceiptSha256"]
                != visual["receiptSha256"]
            ):
                raise ValueError(
                    "visual receipt is not bound to authenticated evaluation"
                )

    totals = _new_metrics()
    by_family: dict[str, dict[str, Any]] = {}
    by_difficulty: dict[str, dict[str, Any]] = {}
    by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    state_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    evaluation_failure_counts: Counter[str] = Counter()
    ordered_receipt_hashes: list[str] = []
    ordered_evaluation_hashes: list[str] = []

    for run_ref in campaign["runs"]:
        pair = (run_ref["runId"], run_ref["scenarioId"])
        receipt = receipt_by_pair[pair]
        evaluation = evaluation_by_pair.get(pair)
        family = run_ref["family"]
        difficulty = run_ref["difficulty"]
        for metrics in (
            totals,
            by_family.setdefault(family, _new_metrics()),
            by_difficulty.setdefault(difficulty, _new_metrics()),
            by_cell.setdefault((family, difficulty), _new_metrics()),
        ):
            _add_metrics(metrics, receipt, evaluation)
        state_counts[receipt["state"]] += 1
        if receipt["state"] != "completed":
            reason_counts[receipt["terminalReason"]] += 1
        if evaluation is not None:
            evaluation_failure_counts.update(
                code
                for layer in evaluation["layers"][
                    : 3 + len(evaluation["requiredLaterLayers"])
                ]
                for code in layer["reasonCodes"]
            )
        else:
            evaluation_failure_counts["EVALUATION_RESULT_MISSING"] += 1
        ordered_receipt_hashes.append(receipt["receiptSha256"])
        ordered_evaluation_hashes.append(
            evaluation["evaluatorResultSha256"] if evaluation is not None else "0" * 64
        )

    family_codes = sorted(by_family)
    missing_cells = [
        {"family": family, "difficulty": difficulty}
        for family in family_codes
        for difficulty in _DIFFICULTIES
        if (family, difficulty) not in by_cell
    ]
    missing_difficulties = [
        difficulty for difficulty in _DIFFICULTIES if difficulty not in by_difficulty
    ]

    result: dict[str, Any] = {
        "schema": PRACTICE_CAMPAIGN_AGGREGATE_SCHEMA,
        "campaignId": campaign["campaignId"],
        "manifestSha256": campaign["manifestSha256"],
        "terminalReceiptSetSha256": _sha256(ordered_receipt_hashes),
        "evaluationResultSetSha256": _sha256(ordered_evaluation_hashes),
        "completeness": {
            "scheduledCount": campaign["expectedRunCount"],
            "terminalReceiptCount": len(validated_receipts),
            "missingTerminalReceiptCount": 0,
            "evaluationResultCount": len(evaluations),
            "missingEvaluationResultCount": len(expected_pairs) - len(evaluations),
            "terminalBijectionComplete": True,
            "evaluationBijectionComplete": len(evaluations) == len(expected_pairs),
        },
        "totals": _finalize_metrics(totals),
        "byFamily": [
            {"family": key, **_finalize_metrics(by_family[key])}
            for key in family_codes
        ],
        "byDifficulty": [
            {"difficulty": key, **_finalize_metrics(by_difficulty[key])}
            for key in _DIFFICULTIES
            if key in by_difficulty
        ],
        "byFamilyDifficulty": [
            {
                "family": family,
                "difficulty": difficulty,
                **_finalize_metrics(by_cell[(family, difficulty)]),
            }
            for family, difficulty in sorted(by_cell)
        ],
        "stateCounts": [
            {"state": key, "count": state_counts[key]} for key in sorted(state_counts)
        ],
        "terminalReasonCounts": [
            {"code": key, "count": reason_counts[key]} for key in sorted(reason_counts)
        ],
        "evaluationFailureCodeCounts": [
            {"code": key, "count": evaluation_failure_counts[key]}
            for key in sorted(evaluation_failure_counts)
        ],
        "coverage": {
            "familyUniverse": "campaign_manifest_only",
            "familyUniverseComplete": False,
            "unrepresentedFamilyCount": None,
            "difficultyUniverse": list(_DIFFICULTIES),
            "missingDifficulties": missing_difficulties,
            "missingFamilyDifficulty": missing_cells,
        },
        "experimentLocalCurriculum": {
            "lane": "L0",
            "adoptionAuthorized": False,
            "installedBehaviorChanged": False,
            "weightUnit": "milliunit",
            "weights": [
                {
                    "family": row["family"],
                    "difficulty": row["difficulty"],
                    "weight": row["experimentLocalWeaknessWeightMilliunits"],
                }
                for row in [
                    {
                        "family": family,
                        "difficulty": difficulty,
                        **by_cell[(family, difficulty)],
                    }
                    for family, difficulty in sorted(by_cell)
                ]
            ],
        },
        "privacy": {
            "localOnly": True,
            "syntheticInputsOnly": True,
            "highConfidencePiiCount": 0,
            "privateCoordinatesExposed": False,
            "evaluatorDataExposed": False,
        },
    }
    common_budget_fields = set(CAMPAIGN_BUDGET_FIELDS) & set(RUN_BUDGET_FIELDS)
    exceeded = [
        field
        for field in sorted(common_budget_fields)
        if result["totals"]["usage"][field] > campaign["budgets"][field]
    ]
    if exceeded:
        raise ValueError(f"aggregate usage exceeds campaign budgets: {exceeded}")
    assert_receipt_safe(result)
    result["aggregateSha256"] = campaign_aggregate_sha256(result)
    return validate_campaign_aggregate(result)


def _validate_metrics(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    raw = dict(_require_mapping(value, name))
    expected = {
        "scheduledCount",
        "terminalCount",
        "completedCount",
        "verifiedSuccessCount",
        "firstPassSuccessCount",
        "afterRepairSuccessCount",
        "falseCompletionCount",
        "failureStateCount",
        "criticalFailureCount",
        "missingEvidenceCount",
        "abstention",
        "evaluation",
        "usage",
        "experimentLocalWeaknessWeightMilliunits",
    }
    _require_exact_keys(raw, expected, name)
    for key in expected - {"abstention", "evaluation", "usage"}:
        _require_int(raw[key], f"{name}.{key}")
    abstention = dict(_require_mapping(raw["abstention"], f"{name}.abstention"))
    _require_exact_keys(
        abstention,
        {"count", "correctCount", "incorrectCount", "unverifiedCount"},
        f"{name}.abstention",
    )
    evaluation = dict(_require_mapping(raw["evaluation"], f"{name}.evaluation"))
    _require_exact_keys(
        evaluation,
        {"passedCount", "failedCount", "unverifiedCount", "missingCount"},
        f"{name}.evaluation",
    )
    usage = dict(_require_mapping(raw["usage"], f"{name}.usage"))
    _require_exact_keys(usage, set(RUN_BUDGET_FIELDS), f"{name}.usage")
    for group_name, group in (
        ("abstention", abstention),
        ("evaluation", evaluation),
        ("usage", usage),
    ):
        for key, item in group.items():
            _require_int(item, f"{name}.{group_name}.{key}")
    if raw["terminalCount"] != raw["scheduledCount"]:
        raise ValueError(f"{name} terminal coverage is incomplete")
    if (
        raw["completedCount"]
        + raw["failureStateCount"]
        + abstention["count"]
        != raw["scheduledCount"]
    ):
        raise ValueError(f"{name} terminal state counts are inconsistent")
    if (
        raw["firstPassSuccessCount"] + raw["afterRepairSuccessCount"]
        != raw["verifiedSuccessCount"]
    ):
        raise ValueError(f"{name} verified success counts are inconsistent")
    if (
        raw["verifiedSuccessCount"] + raw["falseCompletionCount"]
        != raw["completedCount"]
    ):
        raise ValueError(f"{name} completion classification is inconsistent")
    if sum(evaluation.values()) != raw["scheduledCount"]:
        raise ValueError(f"{name} evaluation counts do not cover scheduled runs")
    if (
        sum(
            abstention[key]
            for key in ("correctCount", "incorrectCount", "unverifiedCount")
        )
        != abstention["count"]
    ):
        raise ValueError(f"{name} abstention classification is incomplete")
    if raw["experimentLocalWeaknessWeightMilliunits"] != _weakness_weight(raw):
        raise ValueError(f"{name} experiment-local weakness weight is inconsistent")
    return raw


def _validate_metric_rows(
    value: object,
    *,
    name: str,
    dimensions: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    result: list[dict[str, Any]] = []
    keys: list[tuple[str, ...]] = []
    for index, item in enumerate(value):
        row = dict(_require_mapping(item, f"{name}[{index}]"))
        for dimension in dimensions:
            if dimension not in row:
                raise ValueError(f"{name}[{index}] lacks {dimension}")
        dimension_values = tuple(str(row[dimension]) for dimension in dimensions)
        if "family" in dimensions and not _FAMILY_CODE.fullmatch(
            str(row["family"])
        ):
            raise ValueError(f"{name}[{index}] family is not a closed code")
        if "difficulty" in dimensions and row["difficulty"] not in _DIFFICULTIES:
            raise ValueError(f"{name}[{index}] difficulty is invalid")
        metrics = _validate_metrics(
            {key: child for key, child in row.items() if key not in dimensions},
            f"{name}[{index}]",
        )
        if metrics["scheduledCount"] < 1:
            raise ValueError(f"{name}[{index}] cannot be an empty represented group")
        result.append({**{key: row[key] for key in dimensions}, **metrics})
        keys.append(dimension_values)
    expected_order = (
        [(difficulty,) for difficulty in _DIFFICULTIES if (difficulty,) in keys]
        if dimensions == ("difficulty",)
        else sorted(keys)
    )
    if keys != expected_order or len(keys) != len(set(keys)):
        raise ValueError(f"{name} dimensions must be sorted and unique")
    return result


def _assert_metric_partition(
    rows: Sequence[Mapping[str, Any]], totals: Mapping[str, Any], name: str
) -> None:
    scalar_fields = (
        "scheduledCount",
        "terminalCount",
        "completedCount",
        "verifiedSuccessCount",
        "firstPassSuccessCount",
        "afterRepairSuccessCount",
        "falseCompletionCount",
        "failureStateCount",
        "criticalFailureCount",
        "missingEvidenceCount",
    )
    for field in scalar_fields:
        if sum(row[field] for row in rows) != totals[field]:
            raise ValueError(f"{name} does not partition totals.{field}")
    for group in ("abstention", "evaluation", "usage"):
        for field in totals[group]:
            if sum(row[group][field] for row in rows) != totals[group][field]:
                raise ValueError(f"{name} does not partition totals.{group}.{field}")


def _validate_count_rows(
    value: object,
    *,
    name: str,
    key_name: str,
    allowed: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    rows: list[dict[str, Any]] = []
    codes: list[str] = []
    for index, item in enumerate(value):
        row = dict(_require_mapping(item, f"{name}[{index}]"))
        _require_exact_keys(row, {key_name, "count"}, f"{name}[{index}]")
        code = str(row[key_name])
        if allowed is not None:
            if code not in allowed:
                raise ValueError(f"{name}[{index}] contains an invalid {key_name}")
        elif not _REASON_CODE.fullmatch(code):
            raise ValueError(f"{name}[{index}] contains an invalid closed code")
        count = _require_int(row["count"], f"{name}[{index}].count", minimum=1)
        rows.append({key_name: code, "count": count})
        codes.append(code)
    if codes != sorted(codes) or len(codes) != len(set(codes)):
        raise ValueError(f"{name} codes must be sorted and unique")
    return rows


def validate_campaign_aggregate(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the closed aggregate schema and its content address."""

    raw = dict(_require_mapping(value, "campaign aggregate"))
    assert_receipt_safe(raw)
    expected = {
        "schema",
        "aggregateSha256",
        "campaignId",
        "manifestSha256",
        "terminalReceiptSetSha256",
        "evaluationResultSetSha256",
        "completeness",
        "totals",
        "byFamily",
        "byDifficulty",
        "byFamilyDifficulty",
        "stateCounts",
        "terminalReasonCounts",
        "evaluationFailureCodeCounts",
        "coverage",
        "experimentLocalCurriculum",
        "privacy",
    }
    _require_exact_keys(raw, expected, "campaign aggregate")
    if raw["schema"] != PRACTICE_CAMPAIGN_AGGREGATE_SCHEMA:
        raise ValueError("unsupported practice campaign aggregate schema")
    if not re.fullmatch(r"PCMP-[A-F0-9]{20}", str(raw["campaignId"])):
        raise ValueError("aggregate campaignId must be opaque")
    for key in (
        "manifestSha256",
        "terminalReceiptSetSha256",
        "evaluationResultSetSha256",
    ):
        _require_sha(raw[key], f"campaign aggregate {key}")
    completeness = dict(_require_mapping(raw["completeness"], "completeness"))
    _require_exact_keys(
        completeness,
        {
            "scheduledCount",
            "terminalReceiptCount",
            "missingTerminalReceiptCount",
            "evaluationResultCount",
            "missingEvaluationResultCount",
            "terminalBijectionComplete",
            "evaluationBijectionComplete",
        },
        "completeness",
    )
    for key in (
        "scheduledCount",
        "terminalReceiptCount",
        "missingTerminalReceiptCount",
        "evaluationResultCount",
        "missingEvaluationResultCount",
    ):
        _require_int(completeness[key], f"completeness.{key}")
    if completeness["terminalBijectionComplete"] is not True:
        raise ValueError("aggregate requires a complete terminal receipt bijection")
    if not isinstance(completeness["evaluationBijectionComplete"], bool):
        raise ValueError("evaluationBijectionComplete must be boolean")
    if (
        completeness["terminalReceiptCount"] != completeness["scheduledCount"]
        or completeness["missingTerminalReceiptCount"] != 0
    ):
        raise ValueError("aggregate terminal receipt counts are inconsistent")
    if (
        completeness["evaluationResultCount"]
        + completeness["missingEvaluationResultCount"]
        != completeness["scheduledCount"]
    ):
        raise ValueError("aggregate evaluation counts are inconsistent")
    if completeness["evaluationBijectionComplete"] is not (
        completeness["missingEvaluationResultCount"] == 0
    ):
        raise ValueError("aggregate evaluation completeness flag is inconsistent")

    totals = _validate_metrics(raw["totals"], "totals")
    if totals["scheduledCount"] != completeness["scheduledCount"]:
        raise ValueError("aggregate totals do not match completeness")
    if totals["evaluation"]["missingCount"] != completeness["missingEvaluationResultCount"]:
        raise ValueError("aggregate missing evaluation coverage is inconsistent")
    by_family = _validate_metric_rows(
        raw["byFamily"], name="byFamily", dimensions=("family",)
    )
    by_difficulty = _validate_metric_rows(
        raw["byDifficulty"], name="byDifficulty", dimensions=("difficulty",)
    )
    by_cell = _validate_metric_rows(
        raw["byFamilyDifficulty"],
        name="byFamilyDifficulty",
        dimensions=("family", "difficulty"),
    )
    for name, rows in (
        ("byFamily", by_family),
        ("byDifficulty", by_difficulty),
        ("byFamilyDifficulty", by_cell),
    ):
        _assert_metric_partition(rows, totals, name)
    for row in by_family:
        cells = [item for item in by_cell if item["family"] == row["family"]]
        _assert_metric_partition(
            cells, row, f"byFamilyDifficulty[{row['family']}]"
        )
    for row in by_difficulty:
        cells = [
            item for item in by_cell if item["difficulty"] == row["difficulty"]
        ]
        _assert_metric_partition(
            cells, row, f"byFamilyDifficulty[{row['difficulty']}]"
        )

    state_rows = _validate_count_rows(
        raw["stateCounts"],
        name="stateCounts",
        key_name="state",
        allowed=TERMINAL_RUN_STATES,
    )
    if sum(row["count"] for row in state_rows) != totals["scheduledCount"]:
        raise ValueError("stateCounts do not cover every scheduled run")
    state_counts = {row["state"]: row["count"] for row in state_rows}
    if state_counts.get("completed", 0) != totals["completedCount"]:
        raise ValueError("stateCounts completed total is inconsistent")
    if (
        totals["abstention"]["count"] + totals["failureStateCount"]
        != totals["scheduledCount"] - totals["completedCount"]
    ):
        raise ValueError("stateCounts non-completion classification is inconsistent")
    reason_rows = _validate_count_rows(
        raw["terminalReasonCounts"],
        name="terminalReasonCounts",
        key_name="code",
    )
    if sum(row["count"] for row in reason_rows) != (
        totals["scheduledCount"] - totals["completedCount"]
    ):
        raise ValueError("terminalReasonCounts do not cover every non-completed run")
    evaluation_failure_rows = _validate_count_rows(
        raw["evaluationFailureCodeCounts"],
        name="evaluationFailureCodeCounts",
        key_name="code",
    )
    if sum(row["count"] for row in evaluation_failure_rows) != (
        totals["criticalFailureCount"] + totals["missingEvidenceCount"]
    ):
        raise ValueError("evaluationFailureCodeCounts do not cover evaluator issues")

    families = [row["family"] for row in by_family]
    difficulties = [row["difficulty"] for row in by_difficulty]
    cell_keys = [(row["family"], row["difficulty"]) for row in by_cell]
    if {row["family"] for row in by_cell} != set(families):
        raise ValueError("family/difficulty coverage omits a represented family")
    if {row["difficulty"] for row in by_cell} != set(difficulties):
        raise ValueError("family/difficulty coverage omits a represented difficulty")

    coverage = dict(_require_mapping(raw["coverage"], "coverage"))
    _require_exact_keys(
        coverage,
        {
            "familyUniverse",
            "familyUniverseComplete",
            "unrepresentedFamilyCount",
            "difficultyUniverse",
            "missingDifficulties",
            "missingFamilyDifficulty",
        },
        "coverage",
    )
    if (
        coverage["familyUniverse"] != "campaign_manifest_only"
        or coverage["familyUniverseComplete"] is not False
        or coverage["unrepresentedFamilyCount"] is not None
    ):
        raise ValueError("aggregate cannot claim knowledge beyond campaign families")
    if coverage["difficultyUniverse"] != list(_DIFFICULTIES):
        raise ValueError("aggregate difficulty universe is not frozen")
    expected_missing_difficulties = [
        difficulty for difficulty in _DIFFICULTIES if difficulty not in difficulties
    ]
    if coverage["missingDifficulties"] != expected_missing_difficulties:
        raise ValueError("aggregate missing difficulty coverage is inaccurate")
    expected_missing_cells = [
        {"family": family, "difficulty": difficulty}
        for family in families
        for difficulty in _DIFFICULTIES
        if (family, difficulty) not in set(cell_keys)
    ]
    if coverage["missingFamilyDifficulty"] != expected_missing_cells:
        raise ValueError("aggregate missing family/difficulty coverage is inaccurate")

    privacy = dict(_require_mapping(raw["privacy"], "aggregate privacy"))
    if privacy != {
        "localOnly": True,
        "syntheticInputsOnly": True,
        "highConfidencePiiCount": 0,
        "privateCoordinatesExposed": False,
        "evaluatorDataExposed": False,
    }:
        raise ValueError("aggregate privacy boundary must remain closed")
    curriculum = dict(
        _require_mapping(raw["experimentLocalCurriculum"], "experiment curriculum")
    )
    _require_exact_keys(
        curriculum,
        {
            "lane",
            "adoptionAuthorized",
            "installedBehaviorChanged",
            "weightUnit",
            "weights",
        },
        "experiment curriculum",
    )
    if (
        curriculum["lane"] != "L0"
        or curriculum["adoptionAuthorized"] is not False
        or curriculum["installedBehaviorChanged"] is not False
        or curriculum["weightUnit"] != "milliunit"
    ):
        raise ValueError("aggregate curriculum weights must remain experiment-local")
    weights = curriculum["weights"]
    if not isinstance(weights, list):
        raise ValueError("experiment curriculum weights must be a list")
    expected_weights = [
        {
            "family": row["family"],
            "difficulty": row["difficulty"],
            "weight": row["experimentLocalWeaknessWeightMilliunits"],
        }
        for row in by_cell
    ]
    if weights != expected_weights:
        raise ValueError("experiment curriculum weights do not match aggregate cells")
    supplied = _require_sha(raw["aggregateSha256"], "aggregateSha256")
    if supplied != campaign_aggregate_sha256(raw):
        raise ValueError("aggregateSha256 does not match canonical aggregate content")
    return raw


__all__ = [
    "PRACTICE_CAMPAIGN_AGGREGATE_SCHEMA",
    "build_campaign_aggregate",
    "campaign_aggregate_sha256",
    "validate_campaign_aggregate",
]
