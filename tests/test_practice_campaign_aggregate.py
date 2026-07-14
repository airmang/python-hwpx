from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from hwpx.practice.aggregate import (
    build_campaign_aggregate,
    campaign_aggregate_sha256,
    validate_campaign_aggregate,
)
from hwpx.practice.campaign import build_campaign_manifest, campaign_manifest_sha256
from hwpx.practice.domain import (
    abstention_inventory_authentication_key_id,
    build_domain_evaluation_bundle,
    build_domain_requirement,
    build_edit_domain_evidence,
    build_must_abstain_domain_evidence_from_receipt,
    must_abstain_verifier_policy_sha256,
)
from hwpx.practice.evaluator import (
    PACKAGE_BASE_CHECK_ORDER,
    SEMANTIC_BASE_CHECK_ORDER,
    SEMANTIC_POLICY_SCHEMA,
    build_package_policy,
    combine_evaluation_result,
    current_evaluator_code_sha256,
    domain_layer_from_bundle,
    evaluation_policy_sha256,
    make_check_receipt,
    make_layer_receipt,
    validate_evaluation_result,
)
from hwpx.practice.run import (
    PRACTICE_RUN_EVENT_SCHEMA,
    PRACTICE_RUN_SCHEMA,
    practice_run_id,
    redact_run_receipt,
    workflow_event_id,
)


_EVALUATOR_AUTH_KEY = b"aggregate-evaluator-authentication-key-v1"


def _payload(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_payload(value)).hexdigest()


def _domain_keys(expected_abstention: bool) -> dict[str, bytes] | None:
    if not expected_abstention:
        return None
    return {
        abstention_inventory_authentication_key_id(
            _EVALUATOR_AUTH_KEY
        ): _EVALUATOR_AUTH_KEY
    }


def _provenance() -> dict:
    return {
        "stack": {
            "core": {"version": "2.28.0.dev1", "sha256": _digest("core")},
            "server": {"version": "2.22.0.dev1", "sha256": _digest("server")},
            "skill": {"version": "0.1.29.dev1", "sha256": _digest("skill")},
        },
        "toolSpec": {"version": "tool-spec/v1", "sha256": "0123456789abcdef"},
        "evaluator": {
            "version": "practice-evaluator/v1",
            "sha256": current_evaluator_code_sha256(),
            "authenticationKeyId": (
                "EVK-"
                + hashlib.sha256(_EVALUATOR_AUTH_KEY).hexdigest()[:20].upper()
            ),
        },
    }


def _budgets() -> dict[str, int]:
    return {
        "toolCalls": 8,
        "attempts": 2,
        "repairRounds": 2,
        "elapsedSeconds": 120,
        "costMicrounits": 1000,
        "artifactBytes": 20_000,
    }


def _event(slot: int, *, abstained: bool = False) -> dict:
    event = {
        "schema": PRACTICE_RUN_EVENT_SCHEMA,
        "sequence": 0,
        "kind": "decision_gate" if abstained else "workflow_submit",
        "status": "abstained" if abstained else "succeeded",
        "idempotencyKey": f"IDEM-{slot + 1:020X}",
        "requestSha256": _digest(["request", slot]),
        "responseSha256": _digest(["response", slot]),
        "elapsedMilliseconds": 25,
    }
    event["eventId"] = workflow_event_id(event)
    return event


def _semantic_policy() -> dict:
    return {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {"required": False, "sha256": None},
        "allowedChangedMembers": [],
        "promisedUntouchedMembers": [],
        "revision": {
            "required": False,
            "expectedBefore": None,
            "expectedAfter": None,
        },
        "idempotency": {
            "required": False,
            "expectedMutationCount": None,
        },
    }


def _domain_bundle(
    *,
    scenario_sha256: str,
    artifact_sha256: str,
    family: str,
    terminal_state: str,
    expected_abstention: bool,
    passed: bool,
    terminal_receipt: dict | None = None,
    start_payload: bytes | None = None,
) -> dict:
    verifier_policy_sha256s = None
    inventory_key_id = abstention_inventory_authentication_key_id(
        _EVALUATOR_AUTH_KEY
    )
    if expected_abstention:
        verifier_policy_sha256s = {
            "must_abstain": must_abstain_verifier_policy_sha256(
                inventory_authentication_key_id=inventory_key_id
            )
        }
    requirement = build_domain_requirement(
        scenario_sha256=scenario_sha256,
        artifact_sha256=artifact_sha256,
        task_kind="must_abstain" if expected_abstention else "constrained_edit",
        family=family,
        verifier_policy_sha256s=verifier_policy_sha256s,
    )
    if expected_abstention:
        if terminal_receipt is None or start_payload is None:
            raise ValueError("abstention fixture requires exact terminal source")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            start = root / "start.hwpx"
            outputs = root / "outputs"
            start.write_bytes(start_payload)
            outputs.mkdir()
            if not passed:
                (outputs / "unexpected.hwpx").write_bytes(start_payload)
            evidence = build_must_abstain_domain_evidence_from_receipt(
                requirement,
                start,
                terminal_receipt,
                inventory_authentication_key=_EVALUATOR_AUTH_KEY,
                expected_scenario_id=terminal_receipt["scenarioId"],
                sandbox_output_root=outputs,
            )
    else:
        evidence = build_edit_domain_evidence(
            requirement,
            expected_change_pass=passed,
            forbidden_drift_absent=True,
            untouched_members_preserved=True,
            observed_terminal_state=terminal_state,
        )
    return build_domain_evaluation_bundle(
        requirement,
        [evidence],
        observed_terminal_state=terminal_state,
        oracle_authentication_keys=_domain_keys(expected_abstention),
    )


def _visual_layers(slot: int, artifact_sha256: str) -> tuple[dict, dict]:
    real_hancom = make_layer_receipt(
        "real_hancom",
        [
            make_check_receipt(
                "REAL_HANCOM_ORACLE", "passed", {"slot": slot, "pages": 1}
            )
        ],
        artifact_sha256=artifact_sha256,
        artifact_size_bytes=100,
    )
    visual = make_layer_receipt(
        "visual",
        [
            make_check_receipt(
                "VISUAL_ORACLE", "passed", {"slot": slot, "allPages": True}
            )
        ],
        artifact_sha256=artifact_sha256,
        artifact_size_bytes=100,
    )
    return real_hancom, visual


def _run(
    slot: int,
    *,
    family: str,
    difficulty: str,
    state: str = "completed",
    reason: str = "VERIFIED",
    cost: int = 10,
    expected_abstention: bool = False,
    visual_complete: bool = False,
    observed_abstention: bool | None = None,
) -> tuple[dict, dict]:
    scenario_id = f"SCN-{slot + 1:020X}"
    output_sha = _digest(["output", slot])
    later_layers = _visual_layers(slot, output_sha) if visual_complete else ()
    evidence = {
        "semanticDiff": {
            "status": "passed" if state == "completed" else "unverified",
            "receiptSha256": _digest(["semantic", slot]) if state == "completed" else None,
        },
        "openSafety": {
            "status": "passed" if state == "completed" else "unverified",
            "receiptSha256": _digest(["open", slot]) if state == "completed" else None,
        },
        "domainVerdicts": [
            {
                "verifierId": f"VER-FORM-{slot + 1:04d}",
                "verifierSha256": _digest(["verifier", slot]),
                "status": "passed" if state == "completed" else "unverified",
                "receiptSha256": _digest(["domain", slot]) if state == "completed" else None,
            }
        ],
        "render": {
            "status": "passed" if visual_complete else "unverified",
            "receiptSha256": (
                later_layers[0]["layerReceiptSha256"] if visual_complete else None
            ),
            "renderChecked": visual_complete,
            "provenance": "real_hancom" if visual_complete else "none",
        },
        "visual": {
            "status": "passed" if visual_complete else "unverified",
            "receiptSha256": (
                later_layers[1]["layerReceiptSha256"] if visual_complete else None
            ),
            "allPagesChecked": visual_complete,
            "visualComplete": visual_complete,
        },
        "unresolvedReasonCodes": [] if state == "completed" else [reason],
    }
    run = {
        "schema": PRACTICE_RUN_SCHEMA,
        "scenarioRef": {
            "scenarioId": scenario_id,
            "scenarioSha256": _digest(["scenario", slot]),
            "runnerManifestSha256": _digest("runner"),
            "derivativeSha256": _digest(["derivative", slot]),
            "startArtifactId": f"ART-{slot + 1:04d}",
            "startArtifactSha256": _digest(["start", slot]),
        },
        "dispatch": {
            "slot": slot,
            "dispatchKey": f"DSP-{slot + 1:020X}",
            "seedSha256": _digest(["seed", slot]),
        },
        "provenance": _provenance(),
        "budgets": _budgets(),
        "state": state,
        "terminalReason": reason,
        "workflowEvents": [
            _event(
                slot,
                abstained=(
                    state in {"needs_review", "refused", "unverified"}
                    if observed_abstention is None
                    else observed_abstention
                ),
            )
        ],
        "artifacts": (
            []
            if state in {"needs_review", "refused", "unverified"}
            else [
                {
                    "artifactId": f"OUT-{slot + 1:020X}",
                    "role": "output",
                    "sha256": output_sha,
                    "bytes": 100,
                }
            ]
        ),
        "evidence": evidence,
        "usage": {
            "toolCalls": 1,
            "attempts": 1,
            "repairRounds": 0,
            "elapsedSeconds": 2,
            "costMicrounits": cost,
            "artifactBytes": 100,
        },
        "privacy": {
            "localOnly": True,
            "syntheticInputsOnly": True,
            "highConfidencePiiCount": 0,
            "privateCoordinatesExposed": False,
            "evaluatorDataExposed": False,
        },
    }
    run["runId"] = practice_run_id(run)
    terminal_receipt = redact_run_receipt(run)
    artifact_sha = (
        run["artifacts"][0]["sha256"]
        if run["artifacts"]
        else run["scenarioRef"]["startArtifactSha256"]
    )
    bundle = _domain_bundle(
        scenario_sha256=run["scenarioRef"]["scenarioSha256"],
        artifact_sha256=artifact_sha,
        family=family,
        terminal_state=state,
        expected_abstention=expected_abstention,
        passed=state == "completed" or expected_abstention,
        terminal_receipt=terminal_receipt,
        start_payload=_payload(["start", slot]),
    )
    package_policy = build_package_policy()
    semantic_policy = _semantic_policy()
    run_ref = {
        "slot": slot,
        "runId": run["runId"],
        "scenarioId": scenario_id,
        "scenarioSha256": run["scenarioRef"]["scenarioSha256"],
        "evaluationPolicySha256": evaluation_policy_sha256(
            package_policy,
            semantic_policy,
            bundle,
            domain_oracle_authentication_keys=_domain_keys(
                expected_abstention
            ),
        ),
        "runnerManifestSha256": run["scenarioRef"]["runnerManifestSha256"],
        "derivativeSha256": run["scenarioRef"]["derivativeSha256"],
        "startArtifactId": run["scenarioRef"]["startArtifactId"],
        "startArtifactSha256": run["scenarioRef"]["startArtifactSha256"],
        "family": family,
        "difficulty": difficulty,
        "budgets": _budgets(),
    }
    return terminal_receipt, run_ref


def _campaign(run_refs: list[dict]) -> dict:
    return build_campaign_manifest(
        scenario_manifest_sha256=_digest("scenario-manifest"),
        selection={
            "seedSha256": _digest("selection"),
            "strategyVersion": "coverage-weakness/v1",
            "policySha256": _digest("policy"),
        },
        provenance=_provenance(),
        budgets={
            "runs": len(run_refs),
            "toolCalls": sum(row["budgets"]["toolCalls"] for row in run_refs),
            "elapsedSeconds": sum(row["budgets"]["elapsedSeconds"] for row in run_refs),
            "costMicrounits": sum(row["budgets"]["costMicrounits"] for row in run_refs),
            "artifactBytes": sum(row["budgets"]["artifactBytes"] for row in run_refs),
        },
        runs=run_refs,
    )


def _evaluation(
    receipt: dict,
    run_ref: dict,
    campaign: dict,
    *,
    status: str = "passed",
    expected_abstention: bool = False,
) -> dict:
    terminal_state = receipt["state"]
    artifact_sha = (
        next(
            row["sha256"] for row in receipt["artifacts"] if row["role"] == "output"
        )
        if any(row["role"] == "output" for row in receipt["artifacts"])
        else run_ref["startArtifactSha256"]
    )
    bundle = _domain_bundle(
        scenario_sha256=run_ref["scenarioSha256"],
        artifact_sha256=artifact_sha,
        family=run_ref["family"],
        terminal_state=terminal_state,
        expected_abstention=expected_abstention,
        passed=status == "passed",
        terminal_receipt=receipt,
        start_payload=_payload(["start", run_ref["slot"]]),
    )
    package_status = "passed" if status == "passed" else "failed"
    package_policy = build_package_policy()
    package = make_layer_receipt(
        "package",
        [
            make_check_receipt(
                code,
                package_status if code == "PACKAGE_VALIDATION" else "passed",
                {"slot": run_ref["slot"], "code": code},
            )
            for code in PACKAGE_BASE_CHECK_ORDER
        ],
        artifact_sha256=artifact_sha,
        artifact_size_bytes=100,
        required_check_codes=PACKAGE_BASE_CHECK_ORDER,
    )
    semantic_policy = _semantic_policy()
    semantic = make_layer_receipt(
        "semantic",
        [
            make_check_receipt(
                code,
                package_status if code == "FORBIDDEN_DRIFT" else "passed",
                {"slot": run_ref["slot"], "code": code},
            )
            for code in SEMANTIC_BASE_CHECK_ORDER
        ],
        artifact_sha256=artifact_sha,
        artifact_size_bytes=100,
        input_artifact_sha256=run_ref["startArtifactSha256"],
        input_artifact_size_bytes=100,
        required_check_codes=SEMANTIC_BASE_CHECK_ORDER,
    )
    domain = domain_layer_from_bundle(
        bundle,
        domain_oracle_authentication_keys=_domain_keys(expected_abstention),
    )
    scenario_ref = {
        "scenarioId": run_ref["scenarioId"],
        "scenarioSha256": run_ref["scenarioSha256"],
        "runnerManifestSha256": run_ref["runnerManifestSha256"],
        "derivativeSha256": run_ref["derivativeSha256"],
        "startArtifactId": f"ART-{run_ref['slot'] + 1:04d}",
        "startArtifactSha256": run_ref["startArtifactSha256"],
    }
    return combine_evaluation_result(
        package,
        semantic,
        domain,
        run_id=receipt["runId"],
        campaign_ref={
            "campaignId": campaign["campaignId"],
            "manifestSha256": campaign["manifestSha256"],
            "slot": run_ref["slot"],
            "family": run_ref["family"],
            "difficulty": run_ref["difficulty"],
        },
        scenario_ref=scenario_ref,
        terminal_state=terminal_state,
        terminal_receipt=receipt,
        package_policy=package_policy,
        semantic_policy=semantic_policy,
        domain_bundle=bundle,
        expected_evaluation_policy_sha256=run_ref["evaluationPolicySha256"],
        evaluator_code_sha256=current_evaluator_code_sha256(),
        authentication_key=_EVALUATOR_AUTH_KEY,
    )


def test_aggregate_is_deterministic_content_addressed_and_stratified() -> None:
    first, first_ref = _run(0, family="form", difficulty="routine", cost=10)
    abstained, abstained_ref = _run(
        1,
        family="official_document",
        difficulty="advanced",
        state="needs_review",
        reason="UNSUPPORTED_INTENT",
        cost=20,
        expected_abstention=True,
    )
    failed, failed_ref = _run(
        2,
        family="form",
        difficulty="intermediate",
        state="failed",
        reason="DOMAIN_VERIFIER_FAILED",
        cost=30,
    )
    campaign = _campaign([first_ref, abstained_ref, failed_ref])
    evaluations = [
        _evaluation(first, first_ref, campaign),
        _evaluation(
            abstained,
            abstained_ref,
            campaign,
            expected_abstention=True,
        ),
        _evaluation(failed, failed_ref, campaign, status="failed"),
    ]

    aggregate = build_campaign_aggregate(
        campaign,
        [failed, first, abstained],
        evaluation_results=list(reversed(evaluations)),
        evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
    )
    repeated = build_campaign_aggregate(
        campaign,
        [abstained, failed, first],
        evaluation_results=evaluations,
        evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
    )

    assert aggregate == repeated
    assert aggregate["aggregateSha256"] == campaign_aggregate_sha256(aggregate)
    assert validate_campaign_aggregate(aggregate) == aggregate
    assert aggregate["totals"]["scheduledCount"] == 3
    assert aggregate["totals"]["failureStateCount"] == 1
    assert aggregate["totals"]["abstention"] == {
        "count": 1,
        "correctCount": 1,
        "incorrectCount": 0,
        "unverifiedCount": 0,
    }
    assert aggregate["totals"]["evaluation"] == {
        "passedCount": 2,
        "failedCount": 1,
        "unverifiedCount": 0,
        "missingCount": 0,
    }
    assert aggregate["totals"]["usage"]["costMicrounits"] == 60
    assert [row["family"] for row in aggregate["byFamily"]] == [
        "form",
        "official_document",
    ]
    assert aggregate["coverage"]["familyUniverseComplete"] is False
    assert aggregate["coverage"]["unrepresentedFamilyCount"] is None
    assert aggregate["coverage"]["missingFamilyDifficulty"]
    assert aggregate["experimentLocalCurriculum"]["adoptionAuthorized"] is False
    assert aggregate["experimentLocalCurriculum"]["installedBehaviorChanged"] is False


def test_missing_evaluator_results_are_honest_not_inferred_success() -> None:
    completed, run_ref = _run(0, family="form", difficulty="routine")
    campaign = _campaign([run_ref])

    aggregate = build_campaign_aggregate(campaign, [completed])

    assert aggregate["completeness"]["evaluationBijectionComplete"] is False
    assert aggregate["completeness"]["missingEvaluationResultCount"] == 1
    assert aggregate["totals"]["completedCount"] == 1
    assert aggregate["totals"]["evaluation"]["missingCount"] == 1
    assert aggregate["totals"]["evaluation"]["passedCount"] == 0


def test_unverified_without_an_abstained_decision_gate_is_a_failure_state() -> None:
    receipt, run_ref = _run(
        0,
        family="form",
        difficulty="routine",
        state="unverified",
        reason="DOMAIN_VERIFIER_UNVERIFIED",
        observed_abstention=False,
    )
    aggregate = build_campaign_aggregate(_campaign([run_ref]), [receipt])
    assert aggregate["totals"]["failureStateCount"] == 1
    assert aggregate["totals"]["abstention"]["count"] == 0


def test_abstention_requires_exact_independent_binding() -> None:
    incorrect_receipt, incorrect_ref = _run(
        0,
        family="official_document",
        difficulty="advanced",
        state="refused",
        reason="DESTRUCTIVE_INTENT",
    )
    incorrect_campaign = _campaign([incorrect_ref])

    missing = build_campaign_aggregate(incorrect_campaign, [incorrect_receipt])
    assert missing["totals"]["abstention"]["unverifiedCount"] == 1

    incorrect = build_campaign_aggregate(
        incorrect_campaign,
        [incorrect_receipt],
        evaluation_results=[
            _evaluation(
                incorrect_receipt,
                incorrect_ref,
                incorrect_campaign,
                expected_abstention=False,
            )
        ],
        evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
    )
    assert incorrect["totals"]["abstention"]["incorrectCount"] == 1

    correct_receipt, correct_ref = _run(
        0,
        family="official_document",
        difficulty="advanced",
        state="refused",
        reason="DESTRUCTIVE_INTENT",
        expected_abstention=True,
    )
    correct_campaign = _campaign([correct_ref])
    correct_evaluation = _evaluation(
        correct_receipt,
        correct_ref,
        correct_campaign,
        expected_abstention=True,
    )
    correct = build_campaign_aggregate(
        correct_campaign,
        [correct_receipt],
        evaluation_results=[correct_evaluation],
        evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
    )
    assert correct["totals"]["abstention"]["correctCount"] == 1

    altered_receipt = copy.deepcopy(correct_receipt)
    altered_receipt["artifacts"] = [
        {
            "artifactId": "OUT-00000000000000000001",
            "role": "output",
            "sha256": _digest("unexpected-abstention-output"),
            "bytes": 100,
        }
    ]
    altered_receipt["usage"]["artifactBytes"] = 100
    altered_receipt["receiptSha256"] = _digest(
        {
            key: value
            for key, value in altered_receipt.items()
            if key != "receiptSha256"
        }
    )
    with pytest.raises(ValueError, match="terminal receipt.*binding"):
        build_campaign_aggregate(
            correct_campaign,
            [altered_receipt],
            evaluation_results=[correct_evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )


def test_receipts_must_be_an_exact_campaign_bijection() -> None:
    first, first_ref = _run(0, family="form", difficulty="routine")
    second, second_ref = _run(1, family="exam", difficulty="intermediate")
    campaign = _campaign([first_ref, second_ref])

    with pytest.raises(ValueError, match="bijection"):
        build_campaign_aggregate(campaign, [first])
    with pytest.raises(ValueError, match="duplicate"):
        build_campaign_aggregate(campaign, [first, first])

    outsider, _ = _run(2, family="form", difficulty="routine")
    with pytest.raises(ValueError, match="bijection"):
        build_campaign_aggregate(campaign, [first, outsider])


def test_receipt_and_evaluation_tampering_fail_closed() -> None:
    receipt, run_ref = _run(0, family="form", difficulty="routine")
    campaign = _campaign([run_ref])

    tampered_receipt = copy.deepcopy(receipt)
    tampered_receipt["usage"]["costMicrounits"] += 1
    with pytest.raises(ValueError, match="receiptSha256"):
        build_campaign_aggregate(campaign, [tampered_receipt])

    evaluation = _evaluation(receipt, run_ref, campaign)
    with pytest.raises(ValueError, match="authentication key"):
        build_campaign_aggregate(
            campaign, [receipt], evaluation_results=[evaluation]
        )
    with pytest.raises(ValueError, match="campaign provenance"):
        build_campaign_aggregate(
            campaign,
            [receipt],
            evaluation_results=[evaluation],
            evaluator_authentication_key=b"wrong-aggregate-evaluator-auth-key-32",
        )
    tampered_evaluation = copy.deepcopy(evaluation)
    tampered_evaluation["overallStatus"] = "failed"
    with pytest.raises(ValueError, match="authentication|content/hash"):
        validate_evaluation_result(
            tampered_evaluation,
            authentication_key=_EVALUATOR_AUTH_KEY,
            terminal_receipt=receipt,
        )

    skewed_ref = copy.deepcopy(run_ref)
    skewed_ref["runnerManifestSha256"] = _digest("other runner manifest")
    wrong_binding = _evaluation(receipt, skewed_ref, campaign)
    with pytest.raises(ValueError, match="scenario binding"):
        build_campaign_aggregate(
            campaign,
            [receipt],
            evaluation_results=[wrong_binding],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )

    policy_skew = copy.deepcopy(run_ref)
    policy_skew["evaluationPolicySha256"] = _digest("other evaluation policy")
    with pytest.raises(ValueError, match="evaluation policy"):
        build_campaign_aggregate(
            _campaign([policy_skew]),
            [receipt],
            evaluation_results=[evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )

    family_skew = copy.deepcopy(run_ref)
    family_skew["family"] = "other_family"
    with pytest.raises(ValueError, match="campaign binding"):
        build_campaign_aggregate(
            _campaign([family_skew]),
            [receipt],
            evaluation_results=[evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )

    difficulty_skew = copy.deepcopy(run_ref)
    difficulty_skew["difficulty"] = "advanced"
    with pytest.raises(ValueError, match="campaign binding"):
        build_campaign_aggregate(
            _campaign([difficulty_skew]),
            [receipt],
            evaluation_results=[evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )


def test_manifest_provenance_budgets_and_campaign_budget_are_rechecked() -> None:
    receipt, run_ref = _run(0, family="form", difficulty="routine")
    campaign = _campaign([run_ref])

    skewed = copy.deepcopy(receipt)
    skewed["provenance"]["stack"]["core"]["version"] = "2.28.1.dev1"
    skewed["receiptSha256"] = _digest(
        {key: value for key, value in skewed.items() if key != "receiptSha256"}
    )
    with pytest.raises(ValueError, match="provenance"):
        build_campaign_aggregate(campaign, [skewed])

    skewed = copy.deepcopy(receipt)
    skewed["budgets"]["costMicrounits"] += 1
    skewed["receiptSha256"] = _digest(
        {key: value for key, value in skewed.items() if key != "receiptSha256"}
    )
    with pytest.raises(ValueError, match="budgets"):
        build_campaign_aggregate(campaign, [skewed])

    overrun_campaign = copy.deepcopy(campaign)
    overrun_campaign["budgets"]["costMicrounits"] = 1
    overrun_campaign["manifestSha256"] = campaign_manifest_sha256(overrun_campaign)
    overrun_campaign["campaignId"] = (
        f"PCMP-{overrun_campaign['manifestSha256'][:20].upper()}"
    )
    with pytest.raises(ValueError, match="aggregate usage exceeds"):
        build_campaign_aggregate(overrun_campaign, [receipt])


def test_aggregate_hash_and_closed_privacy_schema_detect_output_tampering() -> None:
    receipt, run_ref = _run(0, family="form", difficulty="routine")
    aggregate = build_campaign_aggregate(_campaign([run_ref]), [receipt])

    tampered = copy.deepcopy(aggregate)
    tampered["totals"]["completedCount"] = 0
    with pytest.raises(ValueError, match="state counts|aggregateSha256"):
        validate_campaign_aggregate(tampered)

    leaked = copy.deepcopy(aggregate)
    leaked["sourcePath"] = "/private/corpus/document.hwpx"
    with pytest.raises(ValueError, match="forbidden"):
        validate_campaign_aggregate(leaked)

    adopted = copy.deepcopy(aggregate)
    adopted["experimentLocalCurriculum"]["adoptionAuthorized"] = True
    adopted["aggregateSha256"] = campaign_aggregate_sha256(adopted)
    with pytest.raises(ValueError, match="experiment-local"):
        validate_campaign_aggregate(adopted)


def test_family_difficulty_cells_must_match_both_marginals() -> None:
    first, first_ref = _run(0, family="form", difficulty="routine")
    second, second_ref = _run(
        1,
        family="official_document",
        difficulty="advanced",
        state="failed",
        reason="DOMAIN_VERIFIER_FAILED",
    )
    aggregate = build_campaign_aggregate(
        _campaign([first_ref, second_ref]), [first, second]
    )

    tampered = copy.deepcopy(aggregate)
    left = tampered["byFamilyDifficulty"][0]
    right = tampered["byFamilyDifficulty"][1]
    metric_keys = set(left) - {"family", "difficulty"}
    left_metrics = {key: copy.deepcopy(left[key]) for key in metric_keys}
    right_metrics = {key: copy.deepcopy(right[key]) for key in metric_keys}
    for key in metric_keys:
        left[key] = right_metrics[key]
        right[key] = left_metrics[key]
    tampered["experimentLocalCurriculum"]["weights"] = [
        {
            "family": row["family"],
            "difficulty": row["difficulty"],
            "weight": row["experimentLocalWeaknessWeightMilliunits"],
        }
        for row in tampered["byFamilyDifficulty"]
    ]
    tampered["aggregateSha256"] = campaign_aggregate_sha256(tampered)

    with pytest.raises(ValueError, match="byFamilyDifficulty"):
        validate_campaign_aggregate(tampered)


def test_visual_completion_is_exactly_bound_to_authenticated_later_layers() -> None:
    receipt, run_ref = _run(
        0,
        family="form",
        difficulty="advanced",
        visual_complete=True,
    )
    campaign = _campaign([run_ref])
    evaluation = _evaluation(receipt, run_ref, campaign)

    with pytest.raises(ValueError, match="real-Hancom receipt|content/hash"):
        build_campaign_aggregate(
            campaign,
            [receipt],
            evaluation_results=[evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )

    skewed = copy.deepcopy(receipt)
    skewed["evidence"]["render"]["receiptSha256"] = _digest(
        "unbound-real-hancom-receipt"
    )
    skewed["receiptSha256"] = _digest(
        {key: value for key, value in skewed.items() if key != "receiptSha256"}
    )
    with pytest.raises(ValueError, match="real-Hancom receipt|content/hash"):
        build_campaign_aggregate(
            campaign,
            [skewed],
            evaluation_results=[evaluation],
            evaluator_authentication_key=_EVALUATOR_AUTH_KEY,
        )
