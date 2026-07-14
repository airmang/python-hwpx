from __future__ import annotations

import copy
import hashlib
import json

import pytest

from hwpx.practice import (
    PRACTICE_RUN_EVENT_SCHEMA,
    PRACTICE_RUN_SCHEMA,
    TERMINAL_RUN_STATES,
    assert_receipt_safe,
    build_campaign_manifest,
    campaign_manifest_sha256,
    practice_run_id,
    redact_run_receipt,
    validate_campaign_manifest,
    validate_practice_run,
    validate_run_receipt,
    workflow_event_id,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _provenance() -> dict:
    return {
        "stack": {
            "core": {"version": "2.12.0.dev1", "sha256": _digest("core-wheel")},
            "server": {"version": "2.5.0.dev1", "sha256": _digest("server-wheel")},
            "skill": {"version": "0.1.9.dev1", "sha256": _digest("skill-bundle")},
        },
        # The generated installed ToolSpec currently exposes a 16-hex digest.
        "toolSpec": {"version": "tool-spec/v1", "sha256": "0123456789abcdef"},
        "evaluator": {
            "version": "practice-evaluator/v1",
            "sha256": _digest("evaluator-policy"),
        },
    }


def _budgets() -> dict:
    return {
        "toolCalls": 12,
        "attempts": 2,
        "repairRounds": 2,
        "elapsedSeconds": 300,
        "costMicrounits": 50_000,
        "artifactBytes": 4_000_000,
    }


def _evidence() -> dict:
    return {
        "semanticDiff": {"status": "passed", "receiptSha256": _digest("diff")},
        "openSafety": {"status": "passed", "receiptSha256": _digest("open")},
        "domainVerdicts": [
            {
                "verifierId": "VER-FORM-0001",
                "verifierSha256": _digest("form-verifier"),
                "status": "passed",
                "receiptSha256": _digest("form-receipt"),
            }
        ],
        "render": {
            "status": "unverified",
            "receiptSha256": None,
            "renderChecked": False,
            "provenance": "none",
        },
        "visual": {
            "status": "unverified",
            "receiptSha256": None,
            "allPagesChecked": False,
            "visualComplete": False,
        },
        "unresolvedReasonCodes": [],
    }


def _event(sequence: int = 0) -> dict:
    event = {
        "schema": PRACTICE_RUN_EVENT_SCHEMA,
        "sequence": sequence,
        "kind": "workflow_submit",
        "status": "succeeded",
        "idempotencyKey": f"IDEM-{sequence:020X}",
        "requestSha256": _digest(f"request-{sequence}"),
        "responseSha256": _digest(f"response-{sequence}"),
        "elapsedMilliseconds": 25,
    }
    event["eventId"] = workflow_event_id(event)
    return event


def _run(*, slot: int = 0, scenario_suffix: int = 1, state: str = "completed") -> dict:
    run = {
        "schema": PRACTICE_RUN_SCHEMA,
        "scenarioRef": {
            "scenarioId": f"SCN-{scenario_suffix:020X}",
            "scenarioSha256": _digest(f"scenario-{scenario_suffix}"),
            "runnerManifestSha256": _digest("runner-manifest"),
            "derivativeSha256": _digest(f"derivative-{scenario_suffix}"),
            "startArtifactId": f"ART-{scenario_suffix:04d}",
            "startArtifactSha256": _digest(f"start-{scenario_suffix}"),
        },
        "dispatch": {
            "slot": slot,
            "dispatchKey": f"DSP-{slot + 1:020X}",
            "seedSha256": _digest(f"dispatch-seed-{slot}"),
        },
        "provenance": _provenance(),
        "budgets": _budgets(),
        "state": state,
        "terminalReason": "VERIFIED" if state == "completed" else "RECOVERY_INCOMPLETE",
        "workflowEvents": [_event()],
        "artifacts": [
            {
                "artifactId": f"OUT-{scenario_suffix:020X}",
                "role": "output",
                "sha256": _digest(f"output-{scenario_suffix}"),
                "bytes": 1024,
            }
        ],
        "evidence": _evidence(),
        "usage": {
            "toolCalls": 1,
            "attempts": 1,
            "repairRounds": 0,
            "elapsedSeconds": 1,
            "costMicrounits": 125,
            "artifactBytes": 1024,
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
    return run


def _run_ref(run: dict, *, family: str = "known_form_fill") -> dict:
    return {
        "slot": run["dispatch"]["slot"],
        "runId": run["runId"],
        "scenarioId": run["scenarioRef"]["scenarioId"],
        "scenarioSha256": run["scenarioRef"]["scenarioSha256"],
        "runnerManifestSha256": run["scenarioRef"]["runnerManifestSha256"],
        "derivativeSha256": run["scenarioRef"]["derivativeSha256"],
        "startArtifactSha256": run["scenarioRef"]["startArtifactSha256"],
        "family": family,
        "difficulty": "routine",
        "budgets": run["budgets"],
    }


def _campaign(runs: list[dict] | None = None) -> dict:
    selected = runs or [_run()]
    return build_campaign_manifest(
        scenario_manifest_sha256=_digest("scenario-manifest"),
        selection={
            "seedSha256": _digest("campaign-seed"),
            "strategyVersion": "coverage-weakness/v1",
            "policySha256": _digest("selection-policy"),
        },
        provenance=_provenance(),
        budgets={
            "runs": len(selected),
            "toolCalls": sum(item["budgets"]["toolCalls"] for item in selected),
            "elapsedSeconds": 900,
            "costMicrounits": 100_000,
            "artifactBytes": 8_000_000,
        },
        runs=[_run_ref(item) for item in selected],
    )


def test_practice_run_identity_is_deterministic_and_immutable() -> None:
    run = _run()
    validated = validate_practice_run(run)
    assert validated["runId"] == practice_run_id(run)
    assert validated == validate_practice_run(json.loads(json.dumps(run, sort_keys=True)))

    resumed = copy.deepcopy(run)
    resumed["usage"]["elapsedSeconds"] = 2
    resumed["workflowEvents"].append(_event(1))
    assert practice_run_id(resumed) == run["runId"]

    changed_input = copy.deepcopy(run)
    changed_input["scenarioRef"]["derivativeSha256"] = _digest("other-derivative")
    assert practice_run_id(changed_input) != run["runId"]


@pytest.mark.parametrize("field", ["toolCalls", "attempts", "costMicrounits"])
def test_budget_contract_rejects_boolean_and_usage_overrun(field: str) -> None:
    run = _run()
    run["budgets"][field] = True
    run["runId"] = practice_run_id(run)
    with pytest.raises(ValueError, match="integer"):
        validate_practice_run(run)

    run = _run()
    run["usage"][field] = run["budgets"][field] + 1
    with pytest.raises(ValueError, match="exceeds fixed run budgets"):
        validate_practice_run(run)


def test_budget_and_provenance_are_fail_closed_and_exact() -> None:
    run = _run()
    run["budgets"]["repairRounds"] = 4
    run["runId"] = practice_run_id(run)
    with pytest.raises(ValueError, match="cannot exceed 3"):
        validate_practice_run(run)

    run = _run()
    run["provenance"]["stack"]["core"]["version"] = "candidate"
    run["runId"] = practice_run_id(run)
    with pytest.raises(ValueError, match="must be exact"):
        validate_practice_run(run)

    run = _run()
    run["provenance"]["toolSpec"]["sha256"] = "too-short"
    run["runId"] = practice_run_id(run)
    with pytest.raises(ValueError, match="16- or 64-hex"):
        validate_practice_run(run)


def test_actual_terminal_states_are_separate_and_reason_is_iff_terminal() -> None:
    assert "incomplete" in TERMINAL_RUN_STATES
    run = _run(state="incomplete")
    assert validate_practice_run(run)["terminalReason"] == "RECOVERY_INCOMPLETE"

    active = _run()
    active["state"] = "running"
    active["terminalReason"] = "STILL_RUNNING"
    with pytest.raises(ValueError, match="required iff"):
        validate_practice_run(active)
    active["terminalReason"] = None
    assert validate_practice_run(active)["state"] == "running"

    leaked_expectation = _run()
    leaked_expectation["expectedTerminalState"] = "completed"
    with pytest.raises(ValueError, match="forbidden private/evaluator field"):
        validate_practice_run(leaked_expectation)


def test_completed_requires_open_safety_and_domain_evidence() -> None:
    run = _run()
    run["evidence"]["openSafety"] = {"status": "failed", "receiptSha256": _digest("bad")}
    with pytest.raises(ValueError, match="completed runs require"):
        validate_practice_run(run)

    run = _run()
    run["evidence"]["domainVerdicts"] = []
    with pytest.raises(ValueError, match="completed runs require"):
        validate_practice_run(run)


def test_visual_complete_requires_full_page_real_hancom_evidence() -> None:
    run = _run()
    run["evidence"]["render"] = {
        "status": "passed",
        "receiptSha256": _digest("fixture-render"),
        "renderChecked": True,
        "provenance": "fixture",
    }
    run["evidence"]["visual"] = {
        "status": "passed",
        "receiptSha256": _digest("visual"),
        "allPagesChecked": True,
        "visualComplete": True,
    }
    with pytest.raises(ValueError, match="real-Hancom"):
        validate_practice_run(run)

    run["evidence"]["render"]["provenance"] = "real_hancom"
    assert validate_practice_run(run)["evidence"]["visual"]["visualComplete"] is True


@pytest.mark.parametrize(
    "leak",
    [
        {"sourcePath": "/Volumes/private/corpus"},
        {"outputFilename": "student-private.hwpx"},
        {"rawText": "private body"},
        {"goldVerifier": _digest("answer")},
        {"holdoutPartition": "frozen"},
        {"detail": "010-1234-5678"},
        {"detail": "person@example.com"},
    ],
)
def test_public_contract_structurally_rejects_private_content_and_evaluator_leaks(
    leak: dict,
) -> None:
    with pytest.raises(ValueError, match="public practice payload|redacted payload"):
        assert_receipt_safe({"safe": {"runId": _run()["runId"]}, "leak": leak})


def test_terminal_receipt_is_redacted_content_addressed_and_tamper_evident() -> None:
    receipt = redact_run_receipt(_run())
    assert receipt == redact_run_receipt(_run())
    assert validate_run_receipt(receipt) == receipt
    encoded = json.dumps(receipt, ensure_ascii=False)
    assert "/Volumes/" not in encoded
    assert ".hwpx" not in encoded
    assert "gold" not in encoded.casefold()
    assert "holdout" not in encoded.casefold()

    tampered = copy.deepcopy(receipt)
    tampered["usage"]["costMicrounits"] += 1
    with pytest.raises(ValueError, match="receiptSha256"):
        validate_run_receipt(tampered)

    active = _run()
    active["state"] = "running"
    active["terminalReason"] = None
    with pytest.raises(ValueError, match="terminal receipt"):
        redact_run_receipt(active)


def test_campaign_manifest_is_deterministic_and_self_hash_excluded() -> None:
    first = _campaign()
    second = _campaign()
    assert first == second
    assert first["manifestSha256"] == campaign_manifest_sha256(first)
    assert validate_campaign_manifest(first) == first

    self_fields_changed = copy.deepcopy(first)
    self_fields_changed["campaignId"] = "PCMP-FFFFFFFFFFFFFFFFFFFF"
    self_fields_changed["manifestSha256"] = "f" * 64
    assert campaign_manifest_sha256(self_fields_changed) == first["manifestSha256"]


def test_campaign_rejects_duplicate_or_reordered_membership() -> None:
    first = _run(slot=0, scenario_suffix=1)
    second = _run(slot=1, scenario_suffix=2)
    campaign = _campaign([first, second])

    duplicate = copy.deepcopy(campaign)
    duplicate["runs"][1]["runId"] = duplicate["runs"][0]["runId"]
    duplicate["manifestSha256"] = campaign_manifest_sha256(duplicate)
    duplicate["campaignId"] = f"PCMP-{duplicate['manifestSha256'][:20].upper()}"
    with pytest.raises(ValueError, match="run IDs must be unique"):
        validate_campaign_manifest(duplicate)

    reordered = copy.deepcopy(campaign)
    reordered["runs"].reverse()
    reordered["manifestSha256"] = campaign_manifest_sha256(reordered)
    reordered["campaignId"] = f"PCMP-{reordered['manifestSha256'][:20].upper()}"
    with pytest.raises(ValueError, match="slots must be contiguous, ordered"):
        validate_campaign_manifest(reordered)


def test_campaign_hash_detects_tampering_and_rejects_evaluator_fields() -> None:
    campaign = _campaign()
    tampered = copy.deepcopy(campaign)
    tampered["budgets"]["costMicrounits"] += 1
    with pytest.raises(ValueError, match="manifestSha256"):
        validate_campaign_manifest(tampered)

    leaked = copy.deepcopy(campaign)
    leaked["holdoutManifestSha256"] = _digest("private-evaluator")
    with pytest.raises(ValueError, match="forbidden private/evaluator field"):
        validate_campaign_manifest(leaked)
