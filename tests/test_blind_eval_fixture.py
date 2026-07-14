from __future__ import annotations

from copy import deepcopy

import pytest

from hwpx.benchmark import (
    BENCHMARK_SCHEMA,
    REQUIRED_FAMILIES,
    build_result_projections,
    check_projection_drift,
    measure_fixture_benchmark,
    validate_fixture_manifest,
    validate_fixture_result_manifest,
)


def _protocol() -> dict:
    orders = []
    difficulties = ("routine", "ambiguous", "must_abstain")
    for index in range(60):
        orders.append({
            "workOrderId": f"wo-{index + 1:03d}",
            "family": REQUIRED_FAMILIES[index % len(REQUIRED_FAMILIES)],
            "difficulty": difficulties[index % len(difficulties)],
            "prompt": f"Frozen synthetic fixture work order {index + 1}",
        })
    return {
        "schema": BENCHMARK_SCHEMA,
        "benchmarkId": "s070-fixture-v1",
        "protocolVersion": "1.0",
        "promptVersion": "1.0",
        "rubricVersion": "1.0",
        "provenanceRandomizationSeed": "s070-public-fixture-seed-v1",
        "assurance": "fixture",
        "executionKind": "fixture_simulation",
        "humanControls": False,
        "humanJudges": False,
        "realAgentClients": False,
        "realHancomVerified": False,
        "humanLabels": False,
        "replacementClaimAllowed": False,
        "workOrders": orders,
        "clients": [
            {"clientId": f"fixture-client-{index}", "clientType": "fixture_agent_client", "hostSpecificHints": False}
            for index in range(1, 4)
        ],
    }


def _result() -> dict:
    protocol = _protocol()
    artifacts = []
    judgments = []
    rubric = {
        "semanticCorrectness": 5,
        "hwpxFidelity": 5,
        "visualQuality": 5,
        "koreanOfficeCompliance": 5,
        "taskCompleteness": 5,
        "manualEditNecessity": 5,
    }
    for order in protocol["workOrders"]:
        for client in protocol["clients"]:
            artifact_id = f"{order['workOrderId']}-{client['clientId']}"
            must_abstain = order["difficulty"] == "must_abstain"
            artifacts.append({
                "artifactId": artifact_id,
                "blindId": f"blind-{len(artifacts) + 1:03d}",
                "workOrderId": order["workOrderId"],
                "clientId": client["clientId"],
                "provenanceHiddenFromJudges": True,
                "filenameMetadataStripped": True,
                "transcriptExcludedFromJudges": True,
                "status": "abstained" if must_abstain else "completed",
                "repairRounds": 0,
                "reviewMinutes": None,
                "editMinutes": None,
                "cost": None,
            })
            for judge in ("fixture-judge-a", "fixture-judge-b"):
                judgments.append({
                    "artifactId": artifact_id,
                    "judgeId": judge,
                    "judgeType": "agent_judge",
                    "humanLabel": False,
                    "acceptedWithoutManualHwpxEdit": not must_abstain,
                    "criticalFailure": False,
                    "scores": rubric,
                })
    return {
        "schema": "hwpx.blind-real-work-eval-result/v1",
        "assurance": "fixture",
        "executionKind": "fixture_simulation",
        "humanControls": False,
        "humanJudges": False,
        "realAgentClients": False,
        "realHancomVerified": False,
        "humanLabels": False,
        "replacementClaimAllowed": False,
        "protocol": protocol,
        "artifacts": artifacts,
        "judgments": judgments,
    }


def test_strict_fixture_contract_covers_matrix_and_preserves_claim_boundary() -> None:
    result = validate_fixture_result_manifest(_result())
    assert len(result["protocol"]["workOrders"]) == 60
    assert len(result["artifacts"]) == 180
    assert len(result["judgments"]) == 360
    assert result["humanLabels"] is False
    assert result["replacementClaimAllowed"] is False


def test_fixture_metrics_publish_wilson_intervals_but_never_release_claim() -> None:
    report = measure_fixture_benchmark(_result())
    assert report["routineFirstPassAcceptance"]["rate"] == 1.0
    assert report["routineFirstPassAcceptance"]["rate95CI"] is not None
    assert report["mustAbstainQuality"]["rate"] == 1.0
    assert report["agreement"]["exactAcceptanceAgreement"] == 1.0
    assert report["benchmarkGatePassed"] is True
    assert report["releaseGatePassed"] is False
    assert report["replacementClaimAllowed"] is False
    assert report["humanJudges"] is False
    assert report["realAgentClients"] is False
    assert report["realHancomVerified"] is False
    assert set(report["perFamily"]) == set(REQUIRED_FAMILIES)


def test_projections_share_one_manifest_and_drift_fails_closed() -> None:
    report = measure_fixture_benchmark(_result())
    projections = build_result_projections(report)
    check_projection_drift(report, projections)
    drifted = deepcopy(projections)
    drifted["scorecard"]["replacementClaimAllowed"] = True
    with pytest.raises(ValueError, match="projection drift"):
        check_projection_drift(report, drifted)


def test_fixture_honesty_flags_and_complete_matrix_are_hard_requirements() -> None:
    protocol = _protocol()
    protocol["humanControls"] = True
    with pytest.raises(ValueError, match="humanControls=false"):
        validate_fixture_manifest(protocol)

    result = _result()
    result["artifacts"].pop()
    with pytest.raises(ValueError, match="every work-order/client pair"):
        validate_fixture_result_manifest(result)

    result = _result()
    result["judgments"] = result["judgments"][:-2]
    with pytest.raises(ValueError, match="two independent agent judges"):
        validate_fixture_result_manifest(result)
