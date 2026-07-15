from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import hwpx.practice.evaluator as evaluator_module
import hwpx.practice.domain as domain_module
from hwpx.document import HwpxDocument
from hwpx.practice.domain import (
    abstention_inventory_authentication_key_id,
    build_domain_evaluation_bundle,
    build_domain_requirement,
    build_edit_domain_evidence,
    build_exam_domain_evidence,
    build_exam_oracle_receipt,
    build_must_abstain_domain_evidence,
    build_must_abstain_domain_evidence_from_receipt,
    build_structural_table_domain_evidence,
    exam_oracle_authentication_key_id,
    exam_verifier_policy_sha256,
    must_abstain_verifier_policy_sha256,
)
from hwpx.practice.evaluator import (
    EVALUATOR_RESULT_SCHEMA,
    MAX_EVALUATOR_ARCHIVE_BYTES,
    PACKAGE_BASE_CHECK_ORDER,
    SEMANTIC_POLICY_SCHEMA,
    build_idempotency_replay_receipt,
    build_package_policy,
    build_workflow_revision_receipt,
    combine_evaluation_result,
    current_evaluator_code_sha256,
    domain_layer_from_bundle,
    domain_projection_from_bundle,
    evaluate_package_layer,
    evaluate_semantic_layer,
    evaluator_authentication_key_id,
    evaluation_policy_sha256,
    make_check_receipt,
    make_layer_receipt,
    semantic_diff_sha256,
    validate_evaluation_result,
    validate_layer_receipt,
)
from hwpx.practice.run import (
    PRACTICE_RUN_EVENT_SCHEMA,
    PRACTICE_RUN_RECEIPT_SCHEMA,
    workflow_event_id,
)

ROOT = Path(__file__).resolve().parents[1]
SKELETON = ROOT / "examples" / "Skeleton.hwpx"
AUTH_KEY = b"practice-evaluator-test-key-32bytes!!"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _content_sha(value: dict, hash_key: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(hash_key, None)
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _scenario_ref(artifact_sha: str) -> dict[str, str]:
    return {
        "scenarioId": "SCN-00000000000000000001",
        "scenarioSha256": _sha("scenario"),
        "runnerManifestSha256": _sha("runner-manifest"),
        "derivativeSha256": _sha("derivative"),
        "startArtifactId": "ART-00000000000000000001",
        "startArtifactSha256": artifact_sha,
    }


def _campaign_ref(
    *,
    family: str = "meeting_minutes",
    difficulty: str = "routine",
    slot: int = 0,
    manifest_sha256: str | None = None,
) -> dict[str, object]:
    manifest_sha = manifest_sha256 or _sha("campaign-manifest")
    return {
        "campaignId": f"PCMP-{manifest_sha[:20].upper()}",
        "manifestSha256": manifest_sha,
        "slot": slot,
        "family": family,
        "difficulty": difficulty,
    }


def _member_hashes(path: Path) -> dict[str, str]:
    with ZipFile(path) as archive:
        return {
            info.filename: hashlib.sha256(archive.read(info.filename)).hexdigest()
            for info in archive.infolist()
            if not info.is_dir()
        }


@pytest.fixture()
def edited_artifacts(tmp_path: Path) -> tuple[Path, Path, list[str]]:
    start = tmp_path / "start.hwpx"
    output = tmp_path / "output.hwpx"
    shutil.copyfile(SKELETON, start)
    with HwpxDocument.open(start) as document:
        document.add_paragraph("SYNTHETIC_PRACTICE_EVALUATOR_TOKEN")
        document.save_to_path(output)
    before = _member_hashes(start)
    after = _member_hashes(output)
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    assert changed
    return start, output, changed


def _policy(
    start: Path,
    output: Path,
    changed: list[str],
    *,
    expected_diff: str | None = None,
    allowed: list[str] | None = None,
    promised: list[str] | None = None,
    revision_required: bool = True,
    idempotency_required: bool = True,
) -> dict[str, object]:
    return {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {
            "required": expected_diff is not None,
            "sha256": expected_diff,
        },
        "allowedChangedMembers": sorted(changed if allowed is None else allowed),
        "promisedUntouchedMembers": sorted(
            ["mimetype"] if promised is None else promised
        ),
        "revision": {
            "required": revision_required,
            "expectedBefore": 4 if revision_required else None,
            "expectedAfter": 5 if revision_required else None,
        },
        "idempotency": {
            "required": idempotency_required,
            "expectedMutationCount": 1 if idempotency_required else None,
        },
    }


def _revision(before: int = 4, after: int = 5) -> dict[str, object]:
    return {"before": before, "after": after}


def _terminal_workflow_event(sequence: int) -> dict[str, object]:
    event: dict[str, object] = {
        "schema": PRACTICE_RUN_EVENT_SCHEMA,
        "sequence": sequence - 1,
        "kind": "workflow_submit",
        "status": "succeeded",
        "idempotencyKey": "IDEM-00000000000000000001",
        "requestSha256": _sha("same-idempotent-request"),
        "responseSha256": _sha(f"workflow-response-{sequence}"),
        "elapsedMilliseconds": sequence,
    }
    event["eventId"] = workflow_event_id(event)
    return event


def _workflow_event(sequence: int) -> dict[str, str]:
    event = _terminal_workflow_event(sequence)
    return {
        "eventId": str(event["eventId"]),
        "requestSha256": str(event["requestSha256"]),
        "idempotencyKey": str(event["idempotencyKey"]),
        "workflowReceiptSha256": _content_sha(event, "unused"),
    }


def _terminal_receipt(
    run_id: str,
    artifact_sha256: str,
    *,
    scenario_id: str = "SCN-00000000000000000001",
    events: list[dict[str, object]] | None = None,
    artifact_bytes: int = 17,
    state: str = "completed",
) -> dict[str, object]:
    retained_bytes = artifact_bytes if state == "completed" else 0
    receipt: dict[str, object] = {
        "schema": PRACTICE_RUN_RECEIPT_SCHEMA,
        "runId": run_id,
        "scenarioId": scenario_id,
        "state": state,
        "terminalReason": "VERIFIED" if state == "completed" else "DECLINED",
        "provenance": {
            "stack": {
                "core": {"version": "test-core/v1", "sha256": _sha("core")},
                "server": {"version": "test-server/v1", "sha256": _sha("server")},
                "skill": {"version": "test-skill/v1", "sha256": _sha("skill")},
            },
            "toolSpec": {"version": "test-tools/v1", "sha256": "0123456789abcdef"},
            "evaluator": {
                "version": "practice-evaluator/v1",
                "sha256": current_evaluator_code_sha256(),
                "authenticationKeyId": evaluator_authentication_key_id(AUTH_KEY),
            },
        },
        "budgets": {
            "toolCalls": 8,
            "attempts": 2,
            "repairRounds": 2,
            "elapsedSeconds": 120,
            "costMicrounits": 1000,
            "artifactBytes": 20000,
        },
        "usage": {
            "toolCalls": 1,
            "attempts": 1,
            "repairRounds": 0,
            "elapsedSeconds": 2,
            "costMicrounits": 10,
            "artifactBytes": retained_bytes,
        },
        "workflowEvents": events
        if events is not None
        else [_terminal_workflow_event(1), _terminal_workflow_event(2)],
        "artifacts": (
            [
                {
                    "artifactId": "OUT-00000000000000000001",
                    "role": "output",
                    "sha256": artifact_sha256,
                    "bytes": artifact_bytes,
                }
            ]
            if state == "completed"
            else []
        ),
        "evidence": {
            "semanticDiff": {"status": "passed", "receiptSha256": _sha("semantic")},
            "openSafety": {"status": "passed", "receiptSha256": _sha("open")},
            "domainVerdicts": [
                {
                    "verifierId": "VER-00000000000000000001",
                    "verifierSha256": _sha("verifier"),
                    "status": "passed",
                    "receiptSha256": _sha("domain"),
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
        },
        "privacy": {
            "localOnly": True,
            "syntheticInputsOnly": True,
            "highConfidencePiiCount": 0,
            "privateCoordinatesExposed": False,
            "evaluatorDataExposed": False,
        },
    }
    receipt["receiptSha256"] = _content_sha(receipt, "receiptSha256")
    return receipt


def _revision_receipt(
    start: Path,
    output: Path,
    *,
    observed_before: int = 4,
    observed_after: int = 5,
    run_id: str = "PRUN-00000000000000000001",
    workflow_sequence: int = 1,
) -> dict:
    return build_workflow_revision_receipt(
        run_id=run_id,
        workflow_event=_workflow_event(workflow_sequence),
        start_source=start,
        output_source=output,
        expected_before=4,
        expected_after=5,
        observed_before=observed_before,
        observed_after=observed_after,
        authentication_key=AUTH_KEY,
    )


def _replay_receipt(
    start: Path,
    output: Path,
    replay: Path,
    *,
    run_id: str = "PRUN-00000000000000000001",
    replay_sequence: int = 2,
) -> dict:
    return build_idempotency_replay_receipt(
        run_id=run_id,
        original_event=_workflow_event(1),
        replay_event=_workflow_event(replay_sequence),
        start_source=start,
        original_output_source=output,
        replay_output_source=replay,
        authentication_key=AUTH_KEY,
    )


def _domain_bundle(
    artifact_sha: str,
    *,
    terminal: str = "completed",
    task_kind: str = "constrained_edit",
    family: str = "meeting_minutes",
) -> dict:
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=artifact_sha,
        task_kind=task_kind,
        family=family,
    )
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state=terminal,
    )
    return build_domain_evaluation_bundle(
        requirement, [evidence], observed_terminal_state=terminal
    )


def _check_status(receipt: dict, code: str) -> str:
    return next(row["status"] for row in receipt["checks"] if row["code"] == code)


def _fake_semantic_policy() -> dict[str, object]:
    return {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {"required": True, "sha256": _sha("semantic-diff")},
        "allowedChangedMembers": [],
        "promisedUntouchedMembers": [],
        "revision": {"required": False, "expectedBefore": None, "expectedAfter": None},
        "idempotency": {"required": False, "expectedMutationCount": None},
    }


def _semantic_codes(policy: dict[str, object]) -> tuple[str, ...]:
    codes = ["PACKAGE_PREREQUISITE"]
    if (
        policy["expectedDiff"]["required"]  # type: ignore[index]
        or policy["expectedDiff"]["sha256"] is not None  # type: ignore[index]
    ):
        codes.append("SEMANTIC_DIFF")
    codes.extend(("FORBIDDEN_DRIFT", "BYTE_PRESERVATION"))
    if policy["revision"]["required"]:  # type: ignore[index]
        codes.append("REVISION")
    if policy["idempotency"]["required"]:  # type: ignore[index]
        codes.append("IDEMPOTENCY")
    return tuple(codes)


def _bound_layer(
    layer: str,
    code: str,
    status: str,
    artifact_sha: str,
    *,
    semantic_policy: dict[str, object] | None = None,
    start_artifact_sha: str | None = None,
) -> dict:
    required_codes = (
        PACKAGE_BASE_CHECK_ORDER
        if layer == "package"
        else _semantic_codes(semantic_policy or _fake_semantic_policy())
    )
    return make_layer_receipt(
        layer,
        [
            make_check_receipt(
                required_code,
                status if required_code == code else "passed",
                {"status": status, "code": required_code},
            )
            for required_code in required_codes
        ],
        artifact_sha256=artifact_sha,
        artifact_size_bytes=17,
        input_artifact_sha256=(
            start_artifact_sha or _sha("start") if layer == "semantic" else None
        ),
        input_artifact_size_bytes=17 if layer == "semantic" else None,
        required_check_codes=required_codes,
    )


def _policy_kwargs(
    bundle: dict,
    *,
    semantic_policy: dict[str, object] | None = None,
    package_policy: dict | None = None,
    workflow_revision_receipt: dict | None = None,
    idempotency_replay_receipt: dict | None = None,
    campaign_ref: dict[str, object] | None = None,
    run_id: str = "PRUN-00000000000000000001",
    terminal_receipt: dict[str, object] | None = None,
    domain_oracle_authentication_keys: dict[str, bytes] | None = None,
) -> dict:
    package = package_policy or build_package_policy()
    semantic = semantic_policy or _fake_semantic_policy()
    return {
        "package_policy": package,
        "semantic_policy": semantic,
        "domain_bundle": bundle,
        "expected_evaluation_policy_sha256": evaluation_policy_sha256(
            package,
            semantic,
            bundle,
            domain_oracle_authentication_keys=domain_oracle_authentication_keys,
        ),
        "authentication_key": AUTH_KEY,
        "evaluator_code_sha256": current_evaluator_code_sha256(),
        "terminal_receipt": terminal_receipt
        or _terminal_receipt(run_id, bundle["requirement"]["artifactSha256"]),
        "campaign_ref": campaign_ref
        or _campaign_ref(family=bundle["requirement"]["family"]),
        "domain_oracle_authentication_keys": domain_oracle_authentication_keys,
        "workflow_revision_receipt": workflow_revision_receipt,
        "idempotency_replay_receipt": idempotency_replay_receipt,
    }


def test_package_layer_runs_all_mandatory_guards_on_valid_hwpx() -> None:
    expected = hashlib.sha256(SKELETON.read_bytes()).hexdigest()
    receipt = evaluate_package_layer(SKELETON, expected_sha256=expected)
    assert receipt["status"] == "passed"
    assert [row["code"] for row in receipt["checks"]] == [
        "INPUT_AVAILABLE",
        "ZIP_RESOURCE_GUARDS",
        "PACKAGE_VALIDATION",
        "REOPEN",
        "EDITOR_OPEN_SAFETY",
        "EXPECTED_ARTIFACT_HASH",
    ]
    assert all(row["status"] == "passed" for row in receipt["checks"])
    assert receipt["artifact"] == {
        "sha256": expected,
        "sizeBytes": SKELETON.stat().st_size,
    }
    assert validate_layer_receipt(
        receipt,
        required_check_codes=PACKAGE_BASE_CHECK_ORDER
        + ("EXPECTED_ARTIFACT_HASH",),
    ) == receipt


def test_zip_guard_failure_stops_before_package_or_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = tmp_path / "hostile.hwpx"
    with ZipFile(hostile, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../escape.xml", b"<x/>")

    def must_not_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError(
            "later package/open-safety layer ran after ZIP guard failure"
        )

    monkeypatch.setattr(evaluator_module, "validate_package", must_not_run)
    monkeypatch.setattr(evaluator_module, "validate_editor_open_safety", must_not_run)
    receipt = evaluate_package_layer(hostile)
    assert receipt["status"] == "failed"
    assert _check_status(receipt, "ZIP_RESOURCE_GUARDS") == "failed"
    assert _check_status(receipt, "PACKAGE_VALIDATION") == "not_run"
    assert _check_status(receipt, "REOPEN") == "not_run"
    assert _check_status(receipt, "EDITOR_OPEN_SAFETY") == "not_run"
    assert receipt["artifact"] is None


def test_duplicate_members_and_oversized_archive_fail_the_first_layer(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.hwpx"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(duplicate, "w") as archive:
            archive.writestr("mimetype", b"application/hwp+zip")
            archive.writestr("mimetype", b"application/hwp+zip")
    duplicate_receipt = evaluate_package_layer(duplicate)
    assert duplicate_receipt["status"] == "failed"
    assert _check_status(duplicate_receipt, "ZIP_RESOURCE_GUARDS") == "failed"

    oversized = tmp_path / "oversized.hwpx"
    with oversized.open("wb") as stream:
        stream.truncate(MAX_EVALUATOR_ARCHIVE_BYTES + 1)
    oversized_receipt = evaluate_package_layer(oversized)
    assert oversized_receipt["status"] == "failed"
    assert _check_status(oversized_receipt, "ZIP_RESOURCE_GUARDS") == "failed"


def test_missing_artifact_is_unverified_without_exposing_path(tmp_path: Path) -> None:
    private_name = "secret-student-file.hwpx"
    receipt = evaluate_package_layer(tmp_path / private_name)
    assert receipt["status"] == "unverified"
    assert _check_status(receipt, "INPUT_AVAILABLE") == "unverified"
    assert private_name not in json.dumps(receipt, ensure_ascii=False)


def test_expected_artifact_hash_mismatch_is_a_hard_failure() -> None:
    receipt = evaluate_package_layer(SKELETON, expected_sha256=_sha("wrong"))
    assert receipt["status"] == "failed"
    assert _check_status(receipt, "EXPECTED_ARTIFACT_HASH") == "failed"


def test_semantic_layer_passes_exact_diff_lossless_revision_and_idempotency(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    package = evaluate_package_layer(output)
    policy = _policy(
        start,
        output,
        changed,
        expected_diff=semantic_diff_sha256(start, output),
    )
    semantic = evaluate_semantic_layer(
        start,
        output,
        policy,
        package,
        package_policy=build_package_policy(),
        workflow_revision_receipt=_revision_receipt(start, output),
        idempotency_replay_receipt=_replay_receipt(start, output, output),
        authentication_key=AUTH_KEY,
    )
    assert semantic["status"] == "passed"
    assert {row["code"] for row in semantic["checks"]} == {
        "PACKAGE_PREREQUISITE",
        "SEMANTIC_DIFF",
        "FORBIDDEN_DRIFT",
        "BYTE_PRESERVATION",
        "REVISION",
        "IDEMPOTENCY",
    }
    assert all(row["status"] == "passed" for row in semantic["checks"])


@pytest.mark.parametrize(
    ("case", "failed_code"),
    [
        ("semantic", "SEMANTIC_DIFF"),
        ("drift", "FORBIDDEN_DRIFT"),
        ("preservation", "BYTE_PRESERVATION"),
        ("revision", "REVISION"),
        ("idempotency", "IDEMPOTENCY"),
    ],
)
def test_each_semantic_lossless_gate_fails_closed(
    edited_artifacts: tuple[Path, Path, list[str]], case: str, failed_code: str
) -> None:
    start, output, changed = edited_artifacts
    expected_diff = semantic_diff_sha256(start, output)
    allowed = changed
    promised = ["mimetype"]
    revision_receipt = _revision_receipt(start, output)
    replay_receipt = _replay_receipt(start, output, output)
    if case == "semantic":
        expected_diff = _sha("different-diff")
    elif case == "drift":
        allowed = []
    elif case == "preservation":
        promised = [changed[0]]
    elif case == "revision":
        revision_receipt = _revision_receipt(
            start, output, observed_after=6
        )
    elif case == "idempotency":
        replay_receipt = _replay_receipt(start, output, start)
    semantic = evaluate_semantic_layer(
        start,
        output,
        _policy(
            start,
            output,
            changed,
            expected_diff=expected_diff,
            allowed=allowed,
            promised=promised,
        ),
        evaluate_package_layer(output),
        package_policy=build_package_policy(),
        workflow_revision_receipt=revision_receipt,
        idempotency_replay_receipt=replay_receipt,
        authentication_key=AUTH_KEY,
    )
    assert semantic["status"] == "failed"
    assert _check_status(semantic, failed_code) == "failed"


def test_required_revision_and_idempotency_evidence_cannot_be_averaged_away(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    semantic = evaluate_semantic_layer(
        start,
        output,
        _policy(
            start,
            output,
            changed,
            expected_diff=semantic_diff_sha256(start, output),
        ),
        evaluate_package_layer(output),
        package_policy=build_package_policy(),
        authentication_key=AUTH_KEY,
    )
    assert semantic["status"] == "unverified"
    assert _check_status(semantic, "REVISION") == "unverified"
    assert _check_status(semantic, "IDEMPOTENCY") == "unverified"


def test_failed_package_prevents_any_semantic_artifact_access(tmp_path: Path) -> None:
    failed_package = evaluate_package_layer(tmp_path / "missing-package.hwpx")
    policy = {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {"required": False, "sha256": None},
        "allowedChangedMembers": [],
        "promisedUntouchedMembers": [],
        "revision": {"required": False, "expectedBefore": None, "expectedAfter": None},
        "idempotency": {"required": False, "expectedMutationCount": None},
    }
    receipt = evaluate_semantic_layer(
        tmp_path / "does-not-exist-start.hwpx",
        tmp_path / "does-not-exist-output.hwpx",
        policy,
        failed_package,
        package_policy=build_package_policy(),
        authentication_key=AUTH_KEY,
    )
    assert receipt["status"] == "unverified"
    assert receipt["reasonCodes"] == [
        "PACKAGE_PREREQUISITE",
        "FORBIDDEN_DRIFT",
        "BYTE_PRESERVATION",
    ]
    assert receipt["checks"][0]["status"] == "not_run"


def test_semantic_policy_is_closed_and_requires_frozen_expected_diff(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    policy = _policy(
        start,
        output,
        changed,
        expected_diff=semantic_diff_sha256(start, output),
    )
    policy["freeText"] = "private"
    with pytest.raises(ValueError, match="fields mismatch"):
        evaluate_semantic_layer(
            start,
            output,
            policy,
            evaluate_package_layer(output),
            package_policy=build_package_policy(),
            authentication_key=AUTH_KEY,
        )
    policy = _policy(start, output, changed, expected_diff=None)
    policy["expectedDiff"] = {"required": True, "sha256": None}
    with pytest.raises(ValueError, match="expected sha256"):
        evaluate_semantic_layer(
            start,
            output,
            policy,
            evaluate_package_layer(output),
            package_policy=build_package_policy(),
            authentication_key=AUTH_KEY,
        )


def test_domain_projection_and_layer_are_exactly_bound() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    result = bundle["result"]
    projection = domain_projection_from_bundle(bundle)
    layer = domain_layer_from_bundle(bundle)
    assert projection == {
        "domainResultSha256": result["resultSha256"],
        "scenarioSha256": _sha("scenario"),
        "artifactSha256": artifact_sha,
        "status": "passed",
        "observedTerminalState": "completed",
        "verifierFamilies": ["edit"],
        "expectedAbstention": False,
        "observedAbstention": False,
        "passedMustAbstainVerifier": False,
        "mustAbstainTerminalReceiptSha256": None,
    }
    assert layer["status"] == "passed"


def test_combiner_requires_all_three_layers_and_preserves_corrupt_success(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    artifact_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    package = evaluate_package_layer(output)
    semantic_policy = _policy(
        start,
        output,
        changed,
        expected_diff=semantic_diff_sha256(start, output),
        allowed=[],
    )
    revision_receipt = _revision_receipt(start, output)
    replay_receipt = _replay_receipt(start, output, output)
    semantic = evaluate_semantic_layer(
        start,
        output,
        semantic_policy,
        package,
        package_policy=build_package_policy(),
        workflow_revision_receipt=revision_receipt,
        idempotency_replay_receipt=replay_receipt,
        authentication_key=AUTH_KEY,
    )
    domain_bundle = _domain_bundle(artifact_sha)
    combined = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(domain_bundle),
        run_id="PRUN-00000000000000000001",
        scenario_ref=_scenario_ref(hashlib.sha256(start.read_bytes()).hexdigest()),
        terminal_state="completed",
        **_policy_kwargs(
            domain_bundle,
            semantic_policy=semantic_policy,
            workflow_revision_receipt=revision_receipt,
            idempotency_replay_receipt=replay_receipt,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000001",
                artifact_sha,
                artifact_bytes=output.stat().st_size,
            ),
        ),
    )
    assert combined["schema"] == EVALUATOR_RESULT_SCHEMA
    assert combined["terminalState"] == "completed"
    assert combined["overallStatus"] == "failed"
    assert combined["eligibleForSuccess"] is False
    assert combined["domainVerdict"] == "passed"
    assert combined["criticalFailureCount"] >= 1
    assert validate_evaluation_result(
        combined,
        authentication_key=AUTH_KEY,
        terminal_receipt=_terminal_receipt(
            "PRUN-00000000000000000001",
            artifact_sha,
            artifact_bytes=output.stat().st_size,
        ),
    ) == combined


def test_missing_required_layer_evidence_remains_unverified_in_final_result() -> None:
    artifact_sha = _sha("artifact")
    semantic_policy = _fake_semantic_policy()
    semantic_policy["revision"] = {
        "required": True,
        "expectedBefore": 1,
        "expectedAfter": 2,
    }
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer(
        "semantic",
        "REVISION",
        "unverified",
        artifact_sha,
        semantic_policy=semantic_policy,
    )
    domain_bundle = _domain_bundle(artifact_sha)
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(domain_bundle),
        run_id="PRUN-00000000000000000002",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(
            domain_bundle,
            semantic_policy=semantic_policy,
            run_id="PRUN-00000000000000000002",
        ),
    )
    assert result["overallStatus"] == "unverified"
    assert result["eligibleForSuccess"] is False
    assert result["missingEvidenceCount"] == 1


def test_combiner_rejects_layer_reordering_domain_tamper_and_hash_tamper() -> None:
    artifact_sha = _sha("artifact")
    domain_bundle = _domain_bundle(artifact_sha)
    domain = domain_layer_from_bundle(domain_bundle)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    kwargs = {
        "run_id": "PRUN-00000000000000000003",
        "scenario_ref": _scenario_ref(_sha("start")),
        "terminal_state": "completed",
        **_policy_kwargs(
            domain_bundle, run_id="PRUN-00000000000000000003"
        ),
    }
    with pytest.raises(ValueError, match="order mismatch"):
        combine_evaluation_result(semantic, package, domain, **kwargs)

    tampered_domain = make_layer_receipt(
        "domain",
        [make_check_receipt("DOMAIN_VERIFIER", "passed", {"tampered": True})],
    )
    with pytest.raises(ValueError, match="domain layer"):
        combine_evaluation_result(package, semantic, tampered_domain, **kwargs)

    combined = combine_evaluation_result(package, semantic, domain, **kwargs)
    combined["evaluatorResultSha256"] = _sha("tampered")
    with pytest.raises(ValueError, match="authentication failed"):
        validate_evaluation_result(
            combined,
            authentication_key=AUTH_KEY,
            terminal_receipt=kwargs["terminal_receipt"],
        )


def test_combiner_rejects_unbound_or_cross_artifact_success_layers() -> None:
    artifact_sha = _sha("artifact")
    domain_bundle = _domain_bundle(artifact_sha)
    domain = domain_layer_from_bundle(domain_bundle)
    unbound_package = make_layer_receipt(
        "package",
        [
            make_check_receipt(code, "passed", {"ok": True, "code": code})
            for code in PACKAGE_BASE_CHECK_ORDER
        ],
        required_check_codes=PACKAGE_BASE_CHECK_ORDER,
    )
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    kwargs = {
        "run_id": "PRUN-00000000000000000005",
        "scenario_ref": _scenario_ref(_sha("start")),
        "terminal_state": "completed",
        **_policy_kwargs(
            domain_bundle, run_id="PRUN-00000000000000000005"
        ),
    }
    with pytest.raises(ValueError, match="requires artifact binding"):
        combine_evaluation_result(unbound_package, semantic, domain, **kwargs)

    wrong_package = _bound_layer(
        "package", "PACKAGE_VALIDATION", "passed", _sha("wrong-artifact")
    )
    with pytest.raises(ValueError, match="different output artifacts"):
        combine_evaluation_result(wrong_package, semantic, domain, **kwargs)


def test_standalone_validator_rejects_forged_projection_even_with_rehashed_result(
) -> None:
    artifact_sha = _sha("artifact")
    domain_bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    combined = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(domain_bundle),
        run_id="PRUN-00000000000000000006",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(
            domain_bundle, run_id="PRUN-00000000000000000006"
        ),
    )

    forged = copy.deepcopy(combined)
    forged_projection = copy.deepcopy(forged["domainProjection"])
    forged_projection["domainResultSha256"] = _sha("fabricated-domain-result")
    forged["domainProjection"] = forged_projection
    forged["layers"][2] = make_layer_receipt(
        "domain",
        [make_check_receipt("DOMAIN_VERIFIER", "passed", forged_projection)],
    )
    forged["evaluatorResultSha256"] = _content_sha(
        forged, "evaluatorResultSha256"
    )
    with pytest.raises(ValueError, match="authentication failed"):
        validate_evaluation_result(
            forged,
            authentication_key=AUTH_KEY,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000006", artifact_sha
            ),
        )


def test_result_schema_rejects_extra_fields_and_is_deterministically_addressed(
) -> None:
    artifact_sha = _sha("artifact")
    domain_bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    kwargs = {
        "run_id": "PRUN-00000000000000000004",
        "scenario_ref": _scenario_ref(_sha("start")),
        "terminal_state": "completed",
        **_policy_kwargs(
            domain_bundle, run_id="PRUN-00000000000000000004"
        ),
    }
    first = combine_evaluation_result(
        package, semantic, domain_layer_from_bundle(domain_bundle), **kwargs
    )
    second = combine_evaluation_result(
        package, semantic, domain_layer_from_bundle(domain_bundle), **kwargs
    )
    assert first == second
    assert first["overallStatus"] == "passed"
    assert first["eligibleForSuccess"] is True
    leaked = copy.deepcopy(first)
    leaked["message"] = "private evaluator text"
    with pytest.raises(ValueError, match="fields mismatch"):
        validate_evaluation_result(
            leaked,
            authentication_key=AUTH_KEY,
            terminal_receipt=kwargs["terminal_receipt"],
        )


def test_layer_receipts_reject_partial_or_reordered_mandatory_coverage() -> None:
    with pytest.raises(ValueError, match="check contract"):
        make_layer_receipt(
            "package",
            [make_check_receipt("INPUT_AVAILABLE", "passed", {"ok": True})],
            required_check_codes=("INPUT_AVAILABLE",),
        )
    with pytest.raises(ValueError, match="coverage/order mismatch"):
        make_layer_receipt(
            "semantic",
            [
                make_check_receipt("BYTE_PRESERVATION", "passed", {"ok": True}),
                make_check_receipt("FORBIDDEN_DRIFT", "passed", {"ok": True}),
                make_check_receipt("PACKAGE_PREREQUISITE", "passed", {"ok": True}),
            ],
            required_check_codes=(
                "PACKAGE_PREREQUISITE",
                "FORBIDDEN_DRIFT",
                "BYTE_PRESERVATION",
            ),
        )


def test_evaluator_authentication_is_mandatory_and_rejects_wrong_key() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id="PRUN-00000000000000000007",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(bundle, run_id="PRUN-00000000000000000007"),
    )
    with pytest.raises(ValueError, match="authentication key"):
        validate_evaluation_result(
            result,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000007", artifact_sha
            ),
        )
    with pytest.raises(ValueError, match="key id mismatch"):
        validate_evaluation_result(
            result,
            authentication_key=b"x" * 32,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000007", artifact_sha
            ),
        )


def test_terminal_receipt_hash_is_required_and_authenticated() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    run_id = "PRUN-00000000000000000015"
    terminal_receipt = _terminal_receipt(run_id, artifact_sha)
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id=run_id,
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(
            bundle, run_id=run_id, terminal_receipt=terminal_receipt
        ),
    )
    assert result["terminalReceiptSha256"] == terminal_receipt["receiptSha256"]

    tampered = copy.deepcopy(result)
    tampered["terminalReceiptSha256"] = _sha("different-terminal-receipt")
    with pytest.raises(ValueError, match="authentication failed"):
        validate_evaluation_result(
            tampered,
            authentication_key=AUTH_KEY,
            terminal_receipt=terminal_receipt,
        )

    invalid_terminal = copy.deepcopy(terminal_receipt)
    invalid_terminal["artifacts"][0]["sha256"] = _sha("other-artifact")
    kwargs = _policy_kwargs(
        bundle, run_id=run_id, terminal_receipt=invalid_terminal
    )
    with pytest.raises(ValueError, match="receiptSha256"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            **kwargs,
        )

    undercounted_output = copy.deepcopy(terminal_receipt)
    undercounted_output["artifacts"][0]["bytes"] = 1
    undercounted_output["usage"]["artifactBytes"] = 1
    undercounted_output["receiptSha256"] = _content_sha(
        undercounted_output, "receiptSha256"
    )
    undercounted_kwargs = _policy_kwargs(
        bundle, run_id=run_id, terminal_receipt=undercounted_output
    )
    with pytest.raises(ValueError, match="evaluator artifact binding"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            **undercounted_kwargs,
        )

    undercounted_usage = copy.deepcopy(terminal_receipt)
    undercounted_usage["usage"]["artifactBytes"] = 1
    undercounted_usage["receiptSha256"] = _content_sha(
        undercounted_usage, "receiptSha256"
    )
    usage_kwargs = _policy_kwargs(
        bundle, run_id=run_id, terminal_receipt=undercounted_usage
    )
    with pytest.raises(ValueError, match="retained.*bytes"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            **usage_kwargs,
        )

    abstained_event = _terminal_workflow_event(1)
    abstained_event["kind"] = "decision_gate"
    abstained_event["status"] = "abstained"
    abstained_event["eventId"] = workflow_event_id(abstained_event)
    abstained_terminal = _terminal_receipt(
        run_id, artifact_sha, events=[abstained_event]
    )
    abstention_kwargs = _policy_kwargs(
        bundle, run_id=run_id, terminal_receipt=abstained_terminal
    )
    wrong_abstention_result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id=run_id,
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **abstention_kwargs,
    )
    assert wrong_abstention_result["domainProjection"]["observedAbstention"] is False
    assert wrong_abstention_result["eligibleForSuccess"] is True
    assert validate_evaluation_result(
        wrong_abstention_result,
        authentication_key=AUTH_KEY,
        terminal_receipt=abstained_terminal,
    ) == wrong_abstention_result


def test_campaign_ref_is_closed_authenticated_and_domain_bound() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id="PRUN-00000000000000000016",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(bundle, run_id="PRUN-00000000000000000016"),
    )
    assert result["campaignRef"] == _campaign_ref()

    skewed_values = (
        {"difficulty": "advanced"},
        {"slot": 7},
        {
            "manifestSha256": _sha("different-campaign-manifest"),
            "campaignId": (
                f"PCMP-{_sha('different-campaign-manifest')[:20].upper()}"
            ),
        },
    )
    for skew in skewed_values:
        tampered = copy.deepcopy(result)
        tampered["campaignRef"].update(skew)
        with pytest.raises(ValueError, match="authentication failed"):
            validate_evaluation_result(
                tampered,
                authentication_key=AUTH_KEY,
                terminal_receipt=_terminal_receipt(
                    "PRUN-00000000000000000016", artifact_sha
                ),
            )

    family_kwargs = _policy_kwargs(
        bundle,
        campaign_ref=_campaign_ref(family="other_family"),
        run_id="PRUN-00000000000000000016",
    )
    with pytest.raises(ValueError, match="domain family"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id="PRUN-00000000000000000016",
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            **family_kwargs,
        )

    bad_identity = _campaign_ref()
    bad_identity["manifestSha256"] = _sha("other-manifest")
    identity_kwargs = _policy_kwargs(
        bundle,
        campaign_ref=bad_identity,
        run_id="PRUN-00000000000000000016",
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id="PRUN-00000000000000000016",
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            **identity_kwargs,
        )


def test_observed_abstention_requires_terminal_abstained_decision() -> None:
    start_sha = _sha("start")
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=start_sha,
        task_kind="must_abstain",
        family="meeting_minutes",
    )
    evidence = build_must_abstain_domain_evidence(
        requirement,
        no_mutation=True,
        decision_reason_present=True,
        observed_terminal_state="refused",
    )
    bundle = build_domain_evaluation_bundle(
        requirement, [evidence], observed_terminal_state="refused"
    )
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", start_sha)
    semantic = _bound_layer(
        "semantic",
        "SEMANTIC_DIFF",
        "passed",
        start_sha,
        start_artifact_sha=start_sha,
    )
    run_id = "PRUN-00000000000000000017"
    non_abstained_terminal = _terminal_receipt(
        run_id,
        start_sha,
        state="refused",
        events=[_terminal_workflow_event(1)],
    )
    # Generic caller booleans have no terminal receipt source chain and may not
    # produce a passed must-abstain verifier in production combine.
    with pytest.raises(ValueError, match="terminal receipt source evidence"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(start_sha),
            terminal_state="refused",
            **_policy_kwargs(
                bundle,
                run_id=run_id,
                terminal_receipt=non_abstained_terminal,
            ),
        )


def test_must_abstain_combine_binds_exact_terminal_receipt_source(
    tmp_path: Path,
) -> None:
    start = tmp_path / "start.hwpx"
    start.write_bytes(b"immutable-start")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    run_id = "PRUN-00000000000000000019"
    event = _terminal_workflow_event(1)
    event["kind"] = "decision_gate"
    event["status"] = "abstained"
    event["eventId"] = workflow_event_id(event)
    terminal = _terminal_receipt(
        run_id,
        start_sha,
        state="refused",
        events=[event],
    )
    terminal["terminalReason"] = "DECISION_REQUIRED"
    terminal["receiptSha256"] = _content_sha(terminal, "receiptSha256")
    inventory_key_id = abstention_inventory_authentication_key_id(AUTH_KEY)
    domain_keys = {inventory_key_id: AUTH_KEY}
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=start_sha,
        task_kind="must_abstain",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "must_abstain": must_abstain_verifier_policy_sha256(
                inventory_authentication_key_id=inventory_key_id
            )
        },
    )
    evidence = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        terminal,
        inventory_authentication_key=AUTH_KEY,
        expected_scenario_id="SCN-00000000000000000001",
        sandbox_output_root=output_root,
    )
    assert evidence["status"] == "passed"
    bundle = build_domain_evaluation_bundle(
        requirement,
        [evidence],
        observed_terminal_state="refused",
        oracle_authentication_keys=domain_keys,
    )
    with pytest.raises(
        ValueError, match="abstention inventory authentication key is required"
    ):
        domain_projection_from_bundle(bundle)
    projection = domain_projection_from_bundle(
        bundle, domain_oracle_authentication_keys=domain_keys
    )
    assert (
        projection["mustAbstainTerminalReceiptSha256"]
        == terminal["receiptSha256"]
    )
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", start_sha)
    semantic = _bound_layer(
        "semantic",
        "SEMANTIC_DIFF",
        "passed",
        start_sha,
        start_artifact_sha=start_sha,
    )
    combine_kwargs = _policy_kwargs(
        bundle,
        run_id=run_id,
        terminal_receipt=terminal,
        domain_oracle_authentication_keys=domain_keys,
    )
    # The policy hash needs the authenticated bundle, but combine itself must
    # replay the AOK source with the live evaluator key, not a caller-held key.
    combine_kwargs["domain_oracle_authentication_keys"] = None
    combined = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(
            bundle, domain_oracle_authentication_keys=domain_keys
        ),
        run_id=run_id,
        scenario_ref=_scenario_ref(start_sha),
        terminal_state="refused",
        **combine_kwargs,
    )
    assert combined["domainProjection"]["observedAbstention"] is True
    wrong_combine_kwargs = dict(combine_kwargs)
    wrong_combine_kwargs["authentication_key"] = (
        b"wrong-live-evaluator-authentication-key!!"
    )
    with pytest.raises(
        ValueError, match="abstention inventory authentication key is required"
    ):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(
                bundle, domain_oracle_authentication_keys=domain_keys
            ),
            run_id=run_id,
            scenario_ref=_scenario_ref(start_sha),
            terminal_state="refused",
            **wrong_combine_kwargs,
        )

    swapped_terminal = copy.deepcopy(terminal)
    swapped_terminal["terminalReason"] = "DESTRUCTIVE_INTENT"
    swapped_terminal["receiptSha256"] = _content_sha(
        swapped_terminal, "receiptSha256"
    )
    with pytest.raises(ValueError, match="terminal receipt binding mismatch"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(
                bundle, domain_oracle_authentication_keys=domain_keys
            ),
            run_id=run_id,
            scenario_ref=_scenario_ref(start_sha),
            terminal_state="refused",
            **_policy_kwargs(
                bundle,
                run_id=run_id,
                terminal_receipt=swapped_terminal,
                domain_oracle_authentication_keys=domain_keys,
            ),
        )


def test_noncompleted_retained_output_bytes_are_exactly_accounted() -> None:
    artifact_sha = _sha("failed-retained-output")
    bundle = _domain_bundle(artifact_sha, terminal="failed")
    run_id = "PRUN-00000000000000000018"
    terminal = _terminal_receipt(run_id, artifact_sha, state="failed")
    terminal["artifacts"] = [
        {
            "artifactId": "OUT-00000000000000000018",
            "role": "output",
            "sha256": artifact_sha,
            "bytes": 17,
        }
    ]
    terminal["usage"]["artifactBytes"] = 1
    terminal["receiptSha256"] = _content_sha(terminal, "receiptSha256")

    with pytest.raises(ValueError, match="retained output artifact bytes"):
        combine_evaluation_result(
            _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha),
            _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha),
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="failed",
            **_policy_kwargs(bundle, run_id=run_id, terminal_receipt=terminal),
        )

    terminal["artifacts"][0]["bytes"] = 1
    terminal["receiptSha256"] = _content_sha(terminal, "receiptSha256")
    with pytest.raises(ValueError, match="evaluator artifact binding"):
        combine_evaluation_result(
            _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha),
            _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha),
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="failed",
            **_policy_kwargs(bundle, run_id=run_id, terminal_receipt=terminal),
        )


def test_fabricated_complete_receipts_cannot_validate_without_evaluator_key() -> None:
    artifact_sha = _sha("nonexistent-artifact")
    bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    forged = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id="PRUN-00000000000000000008",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(bundle, run_id="PRUN-00000000000000000008"),
    )
    forged["auth"]["macSha256"] = _sha("runner-authored-mac")
    forged["evaluatorResultSha256"] = _content_sha(
        forged, "evaluatorResultSha256"
    )
    with pytest.raises(ValueError, match="authentication failed"):
        validate_evaluation_result(
            forged,
            authentication_key=AUTH_KEY,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000008", artifact_sha
            ),
        )


def test_evaluation_policy_hash_binds_revision_idempotency_task_and_family() -> None:
    artifact_sha = _sha("artifact")
    package_policy = build_package_policy()
    semantic = _fake_semantic_policy()
    baseline_bundle = _domain_bundle(artifact_sha)
    baseline = evaluation_policy_sha256(
        package_policy, semantic, baseline_bundle
    )

    revision = copy.deepcopy(semantic)
    revision["revision"] = {
        "required": True,
        "expectedBefore": 1,
        "expectedAfter": 2,
    }
    idempotency = copy.deepcopy(semantic)
    idempotency["idempotency"] = {
        "required": True,
        "expectedMutationCount": 1,
    }
    task_bundle = _domain_bundle(artifact_sha, task_kind="reverse_restore")
    family_bundle = _domain_bundle(artifact_sha, family="school_minutes")
    assert baseline != evaluation_policy_sha256(
        package_policy, revision, baseline_bundle
    )
    assert baseline != evaluation_policy_sha256(
        package_policy, idempotency, baseline_bundle
    )
    assert baseline != evaluation_policy_sha256(
        package_policy, semantic, task_bundle
    )
    assert baseline != evaluation_policy_sha256(
        package_policy, semantic, family_bundle
    )

    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic_layer = _bound_layer(
        "semantic", "SEMANTIC_DIFF", "passed", artifact_sha
    )
    with pytest.raises(ValueError, match="evaluation policy sha256 mismatch"):
        combine_evaluation_result(
            package,
            semantic_layer,
            domain_layer_from_bundle(baseline_bundle),
            run_id="PRUN-00000000000000000009",
            campaign_ref=_campaign_ref(),
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            package_policy=package_policy,
            semantic_policy=revision,
            domain_bundle=baseline_bundle,
            expected_evaluation_policy_sha256=baseline,
            evaluator_code_sha256=current_evaluator_code_sha256(),
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000009", artifact_sha
            ),
            authentication_key=AUTH_KEY,
        )


def test_semantic_output_resource_guard_runs_before_hashing(
    tmp_path: Path,
) -> None:
    huge = tmp_path / "oversized-output.hwpx"
    with huge.open("wb") as stream:
        stream.truncate(MAX_EVALUATOR_ARCHIVE_BYTES + 1)
    package = evaluate_package_layer(SKELETON)
    policy = {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {"required": False, "sha256": None},
        "allowedChangedMembers": [],
        "promisedUntouchedMembers": [],
        "revision": {"required": False, "expectedBefore": None, "expectedAfter": None},
        "idempotency": {"required": False, "expectedMutationCount": None},
    }
    receipt = evaluate_semantic_layer(
        SKELETON,
        huge,
        policy,
        package,
        package_policy=build_package_policy(),
        authentication_key=AUTH_KEY,
    )
    assert receipt["status"] == "failed"
    assert _check_status(receipt, "PACKAGE_PREREQUISITE") == "failed"
    assert _check_status(receipt, "FORBIDDEN_DRIFT") == "not_run"


def test_idempotency_replay_is_size_and_zip_guarded_before_hashing(
    edited_artifacts: tuple[Path, Path, list[str]], tmp_path: Path
) -> None:
    start, output, _changed = edited_artifacts
    huge = tmp_path / "oversized-replay.hwpx"
    with huge.open("wb") as stream:
        stream.truncate(MAX_EVALUATOR_ARCHIVE_BYTES + 1)
    with pytest.raises(ValueError, match="archive limit"):
        _replay_receipt(start, output, huge)


def test_public_result_projects_identifying_member_names_to_digest_counts() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package_policy = build_package_policy()
    semantic_policy = _fake_semantic_policy()
    identifying = "BinData/hong_gildong_student_photo.jpg"
    promised = "Contents/private_class_roster.xml"
    semantic_policy["allowedChangedMembers"] = [identifying]
    semantic_policy["promisedUntouchedMembers"] = [promised]
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer(
        "semantic",
        "SEMANTIC_DIFF",
        "passed",
        artifact_sha,
        semantic_policy=semantic_policy,
    )
    policy_sha = evaluation_policy_sha256(
        package_policy, semantic_policy, bundle
    )
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id="PRUN-00000000000000000010",
        campaign_ref=_campaign_ref(),
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        package_policy=package_policy,
        semantic_policy=semantic_policy,
        domain_bundle=bundle,
        expected_evaluation_policy_sha256=policy_sha,
        evaluator_code_sha256=current_evaluator_code_sha256(),
        terminal_receipt=_terminal_receipt(
            "PRUN-00000000000000000010", artifact_sha
        ),
        authentication_key=AUTH_KEY,
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert identifying not in encoded
    assert promised not in encoded
    assert result["semanticPolicy"]["allowedChangedMembers"]["count"] == 1
    assert result["semanticPolicy"]["promisedUntouchedMembers"]["count"] == 1
    assert evaluation_policy_sha256(
        package_policy, result["semanticPolicy"], bundle
    ) == policy_sha
    assert validate_evaluation_result(
        result,
        authentication_key=AUTH_KEY,
        terminal_receipt=_terminal_receipt(
            "PRUN-00000000000000000010", artifact_sha
        ),
    ) == result


def test_package_and_semantic_use_one_stable_bytes_snapshot(
    edited_artifacts: tuple[Path, Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start, output, changed = edited_artifacts
    original_output_bytes = output.read_bytes()
    original_validate_package = evaluator_module.validate_package
    package_calls = 0

    def swap_during_package(source):  # noqa: ANN001
        nonlocal package_calls
        package_calls += 1
        assert isinstance(source, bytes)
        output.write_bytes(b"path-swapped-after-snapshot")
        return original_validate_package(source)

    monkeypatch.setattr(evaluator_module, "validate_package", swap_during_package)
    package = evaluate_package_layer(output)
    assert package_calls == 1
    assert package["status"] == "passed"

    # Restore a valid output, then swap its path while the semantic diff runs.
    output.write_bytes(original_output_bytes)
    restored = output
    restored_changed = changed
    original_diff = evaluator_module.semantic_diff_sha256

    def swap_during_diff(old_source, new_source):  # noqa: ANN001
        assert isinstance(old_source, bytes)
        assert isinstance(new_source, bytes)
        restored.write_bytes(b"second-path-swap")
        return original_diff(old_source, new_source)

    monkeypatch.setattr(evaluator_module, "semantic_diff_sha256", swap_during_diff)
    policy = _policy(
        start,
        restored,
        restored_changed or changed,
        expected_diff=original_diff(start, restored),
        revision_required=False,
        idempotency_required=False,
    )
    semantic = evaluate_semantic_layer(
        start,
        restored,
        policy,
        package,
        package_policy=build_package_policy(),
        authentication_key=AUTH_KEY,
    )
    assert semantic["status"] == "passed"


def test_authenticated_revision_and_replay_receipts_reject_forgery_and_reuse(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    policy = _policy(
        start,
        output,
        changed,
        expected_diff=semantic_diff_sha256(start, output),
    )
    forged_revision = _revision_receipt(start, output)
    forged_revision["observedRevision"]["after"] = 99
    reused_event_replay = _replay_receipt(
        start, output, output, replay_sequence=1
    )
    semantic = evaluate_semantic_layer(
        start,
        output,
        policy,
        evaluate_package_layer(output),
        package_policy=build_package_policy(),
        workflow_revision_receipt=forged_revision,
        idempotency_replay_receipt=reused_event_replay,
        authentication_key=AUTH_KEY,
    )
    assert _check_status(semantic, "REVISION") == "unverified"
    assert _check_status(semantic, "IDEMPOTENCY") == "failed"


def test_combiner_requires_semantic_events_in_terminal_receipt(
    edited_artifacts: tuple[Path, Path, list[str]],
) -> None:
    start, output, changed = edited_artifacts
    run_id = "PRUN-00000000000000000001"
    policy = _policy(
        start,
        output,
        changed,
        expected_diff=semantic_diff_sha256(start, output),
    )
    package = evaluate_package_layer(output)
    artifact_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    bundle = _domain_bundle(artifact_sha)
    terminal_receipt = _terminal_receipt(
        run_id, artifact_sha, artifact_bytes=output.stat().st_size
    )

    outside_revision = _revision_receipt(
        start, output, workflow_sequence=3
    )
    valid_replay = _replay_receipt(start, output, output)
    revision_semantic = evaluate_semantic_layer(
        start,
        output,
        policy,
        package,
        package_policy=build_package_policy(),
        workflow_revision_receipt=outside_revision,
        idempotency_replay_receipt=valid_replay,
        authentication_key=AUTH_KEY,
    )
    assert revision_semantic["status"] == "passed"
    with pytest.raises(ValueError, match="revision event is absent"):
        combine_evaluation_result(
            package,
            revision_semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(hashlib.sha256(start.read_bytes()).hexdigest()),
            terminal_state="completed",
            **_policy_kwargs(
                bundle,
                semantic_policy=policy,
                workflow_revision_receipt=outside_revision,
                idempotency_replay_receipt=valid_replay,
                terminal_receipt=terminal_receipt,
            ),
        )

    valid_revision = _revision_receipt(start, output)
    outside_replay = _replay_receipt(
        start, output, output, replay_sequence=3
    )
    replay_semantic = evaluate_semantic_layer(
        start,
        output,
        policy,
        package,
        package_policy=build_package_policy(),
        workflow_revision_receipt=valid_revision,
        idempotency_replay_receipt=outside_replay,
        authentication_key=AUTH_KEY,
    )
    assert replay_semantic["status"] == "passed"
    with pytest.raises(ValueError, match="idempotency events are absent"):
        combine_evaluation_result(
            package,
            replay_semantic,
            domain_layer_from_bundle(bundle),
            run_id=run_id,
            scenario_ref=_scenario_ref(hashlib.sha256(start.read_bytes()).hexdigest()),
            terminal_state="completed",
            **_policy_kwargs(
                bundle,
                semantic_policy=policy,
                workflow_revision_receipt=valid_revision,
                idempotency_replay_receipt=outside_replay,
                terminal_receipt=terminal_receipt,
            ),
        )


def test_combiner_rejects_alternate_semantic_start_binding(
    edited_artifacts: tuple[Path, Path, list[str]], tmp_path: Path
) -> None:
    original_start, output, _ = edited_artifacts
    alternate = tmp_path / "alternate-start.hwpx"
    with HwpxDocument.open(original_start) as document:
        document.add_paragraph("SYNTHETIC_ALTERNATE_START")
        document.save_to_path(alternate)
    before = _member_hashes(alternate)
    after = _member_hashes(output)
    changed = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    policy = _policy(
        alternate,
        output,
        changed,
        expected_diff=semantic_diff_sha256(alternate, output),
        revision_required=False,
        idempotency_required=False,
    )
    package = evaluate_package_layer(output)
    semantic = evaluate_semantic_layer(
        alternate,
        output,
        policy,
        package,
        package_policy=build_package_policy(),
        authentication_key=AUTH_KEY,
    )
    assert semantic["status"] == "passed"
    artifact_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    bundle = _domain_bundle(artifact_sha)
    with pytest.raises(ValueError, match="start artifact binding mismatch"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id="PRUN-00000000000000000011",
            scenario_ref=_scenario_ref(
                hashlib.sha256(original_start.read_bytes()).hexdigest()
            ),
            terminal_state="completed",
            **_policy_kwargs(
                bundle,
                semantic_policy=policy,
                run_id="PRUN-00000000000000000011",
            ),
        )


def test_unauthenticated_later_layer_receipts_cannot_enable_success() -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package_policy = build_package_policy()
    semantic_policy = _fake_semantic_policy()
    required = ("real_hancom", "visual")
    policy_sha = evaluation_policy_sha256(package_policy, semantic_policy, bundle)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    base = {
        "run_id": "PRUN-00000000000000000012",
        "campaign_ref": _campaign_ref(),
        "scenario_ref": _scenario_ref(_sha("start")),
        "terminal_state": "completed",
        "package_policy": package_policy,
        "semantic_policy": semantic_policy,
        "domain_bundle": bundle,
        "expected_evaluation_policy_sha256": policy_sha,
        "evaluator_code_sha256": current_evaluator_code_sha256(),
        "terminal_receipt": _terminal_receipt(
            "PRUN-00000000000000000012", artifact_sha
        ),
        "authentication_key": AUTH_KEY,
    }
    hancom = make_layer_receipt(
        "real_hancom",
        [make_check_receipt("REAL_HANCOM_ORACLE", "passed", {"ok": True})],
        artifact_sha256=artifact_sha,
        artifact_size_bytes=17,
    )
    visual = make_layer_receipt(
        "visual",
        [make_check_receipt("VISUAL_ORACLE", "passed", {"ok": True})],
        artifact_sha256=artifact_sha,
        artifact_size_bytes=17,
    )
    with pytest.raises(ValueError, match="authenticated oracle receipts"):
        evaluation_policy_sha256(
            package_policy, semantic_policy, bundle, required
        )
    with pytest.raises(ValueError, match="authenticated oracle receipts"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            required_later_layers=required,
            later_layers=(hancom, visual),
            **base,
        )
    with pytest.raises(ValueError, match="coverage is incomplete"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            later_layers=(hancom, visual),
            **base,
        )


def test_authenticated_exam_bundle_flows_through_evaluator_without_key_leak(
    tmp_path: Path,
) -> None:
    oracle_key = b"evaluator-exam-oracle-key-material-0001"
    wrong_key = b"wrong-exam-oracle-key-material-000001"
    key_id = exam_oracle_authentication_key_id(oracle_key)
    oracle_keys = {key_id: oracle_key}
    input_path = tmp_path / "exam-input.bin"
    output_path = tmp_path / "exam-output.bin"
    input_path.write_bytes(b"i" * 17)
    output_path.write_bytes(b"o" * 17)
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    output_sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
    provenance_sha = _sha("exam-oracle-provenance")

    class ExamOracle:
        provenance_sha256 = provenance_sha

        @staticmethod
        def measure_exam(input_snapshot: Path, output_snapshot: Path) -> dict:
            assert input_snapshot.read_bytes() == b"i" * 17
            assert output_snapshot.read_bytes() == b"o" * 17
            return {
                "renderChecked": True,
                "questionSplits": 0,
                "placeholdersOk": True,
                "examInvariantsPass": True,
            }

    exam_policy_sha = exam_verifier_policy_sha256(
        input_artifact_sha256=input_sha,
        oracle_provenance_sha256=provenance_sha,
        oracle_authentication_key_id=key_id,
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=output_sha,
        task_kind="structural_edit",
        family="exam_question_answer",
        verifier_policy_sha256s={"exam": exam_policy_sha},
    )
    oracle_receipt = build_exam_oracle_receipt(
        input_path,
        output_path,
        ExamOracle(),
        oracle_authentication_key=oracle_key,
    )
    structural = build_structural_table_domain_evidence(
        requirement,
        table_geometry_preserved=True,
        exact_values_pass=True,
        merged_cells_preserved=True,
        observed_terminal_state="completed",
    )
    exam = build_exam_domain_evidence(
        requirement,
        oracle_receipt,
        oracle_authentication_key=oracle_key,
        observed_terminal_state="completed",
    )
    bundle = build_domain_evaluation_bundle(
        requirement,
        [structural, exam],
        observed_terminal_state="completed",
        oracle_authentication_keys=oracle_keys,
    )
    package_policy = build_package_policy()
    semantic_policy = _fake_semantic_policy()
    package = _bound_layer(
        "package", "PACKAGE_VALIDATION", "passed", output_sha
    )
    semantic = _bound_layer(
        "semantic",
        "SEMANTIC_DIFF",
        "passed",
        output_sha,
        start_artifact_sha=input_sha,
    )
    domain = domain_layer_from_bundle(
        bundle, domain_oracle_authentication_keys=oracle_keys
    )
    run_id = "PRUN-00000000000000000018"
    terminal_receipt = _terminal_receipt(run_id, output_sha)
    campaign_ref = _campaign_ref(family="exam_question_answer")
    policy_sha = evaluation_policy_sha256(
        package_policy,
        semantic_policy,
        bundle,
        domain_oracle_authentication_keys=oracle_keys,
    )
    combine_kwargs = {
        "run_id": run_id,
        "campaign_ref": campaign_ref,
        "scenario_ref": _scenario_ref(input_sha),
        "terminal_state": "completed",
        "terminal_receipt": terminal_receipt,
        "package_policy": package_policy,
        "semantic_policy": semantic_policy,
        "domain_bundle": bundle,
        "expected_evaluation_policy_sha256": policy_sha,
        "evaluator_code_sha256": current_evaluator_code_sha256(),
        "authentication_key": AUTH_KEY,
    }
    with pytest.raises(ValueError, match="authentication key is required"):
        combine_evaluation_result(package, semantic, domain, **combine_kwargs)
    with pytest.raises(ValueError, match="authentication key mismatch"):
        combine_evaluation_result(
            package,
            semantic,
            domain,
            domain_oracle_authentication_keys={key_id: wrong_key},
            **combine_kwargs,
        )

    result = combine_evaluation_result(
        package,
        semantic,
        domain,
        domain_oracle_authentication_keys=oracle_keys,
        **combine_kwargs,
    )
    assert result["eligibleForSuccess"] is True
    assert oracle_key.hex() not in repr(result)
    with pytest.raises(ValueError, match="authentication key is required"):
        validate_evaluation_result(
            result,
            authentication_key=AUTH_KEY,
            terminal_receipt=terminal_receipt,
        )
    with pytest.raises(ValueError, match="authentication key mismatch"):
        validate_evaluation_result(
            result,
            authentication_key=AUTH_KEY,
            terminal_receipt=terminal_receipt,
            domain_oracle_authentication_keys={key_id: wrong_key},
        )
    assert validate_evaluation_result(
        result,
        authentication_key=AUTH_KEY,
        terminal_receipt=terminal_receipt,
        domain_oracle_authentication_keys=oracle_keys,
    ) == result


def test_code_sha_key_identity_and_early_raw_hmac_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_sha = _sha("artifact")
    bundle = _domain_bundle(artifact_sha)
    package = _bound_layer("package", "PACKAGE_VALIDATION", "passed", artifact_sha)
    semantic = _bound_layer("semantic", "SEMANTIC_DIFF", "passed", artifact_sha)
    result = combine_evaluation_result(
        package,
        semantic,
        domain_layer_from_bundle(bundle),
        run_id="PRUN-00000000000000000013",
        scenario_ref=_scenario_ref(_sha("start")),
        terminal_state="completed",
        **_policy_kwargs(bundle, run_id="PRUN-00000000000000000013"),
    )
    assert result["evaluatorCodeSha256"] == current_evaluator_code_sha256()
    assert result["auth"]["keyId"] == evaluator_authentication_key_id(AUTH_KEY)

    tampered = copy.deepcopy(result)
    tampered["domainBundle"]["bundleSha256"] = _sha("tampered")

    def expensive_validation_must_not_run(value):  # noqa: ANN001
        raise AssertionError("nested domain validation ran before raw HMAC")

    monkeypatch.setattr(
        domain_module,
        "validate_domain_evaluation_bundle",
        expensive_validation_must_not_run,
    )
    with pytest.raises(ValueError, match="authentication failed"):
        validate_evaluation_result(
            tampered,
            authentication_key=AUTH_KEY,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000013", artifact_sha
            ),
        )

    oversized = copy.deepcopy(result)
    oversized["domainBundle"] = "x" * 5000
    with pytest.raises(ValueError, match="string exceeds size limit"):
        validate_evaluation_result(
            oversized,
            authentication_key=AUTH_KEY,
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000013", artifact_sha
            ),
        )

    monkeypatch.undo()
    with pytest.raises(ValueError, match="evaluator code sha256"):
        combine_evaluation_result(
            package,
            semantic,
            domain_layer_from_bundle(bundle),
            run_id="PRUN-00000000000000000014",
            campaign_ref=_campaign_ref(),
            scenario_ref=_scenario_ref(_sha("start")),
            terminal_state="completed",
            package_policy=build_package_policy(),
            semantic_policy=_fake_semantic_policy(),
            domain_bundle=bundle,
            expected_evaluation_policy_sha256=evaluation_policy_sha256(
                build_package_policy(), _fake_semantic_policy(), bundle
            ),
            evaluator_code_sha256=_sha("wrong-code"),
            terminal_receipt=_terminal_receipt(
                "PRUN-00000000000000000014", artifact_sha
            ),
            authentication_key=AUTH_KEY,
        )
