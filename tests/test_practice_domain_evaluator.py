from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

import hwpx.practice.domain as domain_module
from hwpx.practice.domain import (
    DOMAIN_EVIDENCE_SCHEMA,
    DOMAIN_EVALUATION_BUNDLE_SCHEMA,
    DOMAIN_REQUIREMENT_SCHEMA,
    DOMAIN_RESULT_SCHEMA,
    VERIFIER_CHECKS,
    abstention_inventory_authentication_key_id,
    authoring_verifier_policy_sha256,
    build_authoring_domain_evidence,
    build_domain_evidence,
    build_domain_evaluation_bundle,
    build_domain_requirement,
    build_edit_domain_evidence,
    build_edit_domain_evidence_from_semantic,
    build_exam_domain_evidence,
    build_exam_oracle_receipt,
    build_form_differential_receipt,
    build_form_target_policy,
    build_form_fill_domain_evidence,
    build_form_fill_domain_evidence_from_artifacts,
    build_must_abstain_domain_evidence,
    build_must_abstain_domain_evidence_from_receipt,
    build_official_document_domain_evidence,
    build_structural_table_domain_evidence,
    build_structural_table_domain_evidence_from_artifacts,
    domain_evidence_sha256,
    domain_evaluation_bundle_sha256,
    domain_requirement_sha256,
    domain_requirement_policy_projection,
    domain_row_sha256,
    domain_result_sha256,
    domain_value_sha256,
    exam_oracle_authentication_key_id,
    exam_verifier_policy_sha256,
    form_differential_oracle_provenance_sha256,
    form_differential_receipt_sha256,
    form_verifier_policy_sha256,
    must_abstain_verifier_policy_sha256,
    official_verifier_policy_sha256,
    serialize_form_differential_receipt,
    structural_verifier_policy_sha256,
    evaluate_domain,
    validate_domain_evidence,
    validate_domain_evaluation_bundle,
    validate_domain_requirement,
    validate_domain_result,
    validate_form_differential_receipt,
)
from hwpx.practice.run import (
    PRACTICE_RUN_EVENT_SCHEMA,
    PRACTICE_RUN_SCHEMA,
    assert_receipt_safe,
    practice_run_id,
    redact_run_receipt,
    workflow_event_id,
)


ABSTENTION_INVENTORY_KEY = b"abstention-inventory-test-key-32bytes!"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _write_form_differential_asset(
    blank: Path,
    output: Path,
    target: Path,
    *,
    verdict: str = "passed",
) -> tuple[str, dict]:
    backend = "tests.FrozenDifferentialOracle"
    receipt = {
        "schema": "hwpx.practice-form-differential-receipt/v1",
        "blankArtifact": {
            "sha256": hashlib.sha256(blank.read_bytes()).hexdigest(),
            "bytes": blank.stat().st_size,
        },
        "outputArtifact": {
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "bytes": output.stat().st_size,
        },
        "backend": backend,
        "oracleProvenanceSha256": form_differential_oracle_provenance_sha256(
            backend=backend
        ),
        "renderChecked": True,
        "overflowChecked": True,
        "overflowDetected": verdict != "passed",
        "overlapDetected": False,
        "layoutStable": True,
        "verdict": verdict,
    }
    receipt["receiptSha256"] = form_differential_receipt_sha256(receipt)
    payload = serialize_form_differential_receipt(receipt)
    target.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest(), receipt


def test_form_differential_receipt_builder_binds_snapshots_and_verdict(
    tmp_path, monkeypatch
) -> None:
    from types import SimpleNamespace

    import hwpx.form_fit.wordbox as wordbox_module
    from hwpx.document import HwpxDocument

    blank = tmp_path / "blank.hwpx"
    output = tmp_path / "output.hwpx"
    for path, value in ((blank, "BLANK"), (output, "SYNTHETIC")):
        document = HwpxDocument.new()
        table = document.add_table(1, 1)
        table.set_cell_text(0, 0, value)
        document.save_to_path(path)
        document.close()

    class FrozenOracle:
        pass

    oracle = FrozenOracle()

    def differential(blank_snapshot, output_snapshot, *, oracle):  # noqa: ANN001
        assert Path(blank_snapshot) != blank
        assert Path(output_snapshot) != output
        assert oracle is not None
        assert hashlib.sha256(Path(blank_snapshot).read_bytes()).hexdigest() == (
            hashlib.sha256(blank.read_bytes()).hexdigest()
        )
        assert hashlib.sha256(Path(output_snapshot).read_bytes()).hexdigest() == (
            hashlib.sha256(output.read_bytes()).hexdigest()
        )
        return SimpleNamespace(
            render_checked=True,
            overflow_checked=True,
            overflow_detected=False,
            overlap_detected=False,
            layout_stable=True,
        )

    monkeypatch.setattr(
        wordbox_module, "verify_form_fill_differential", differential
    )
    receipt = build_form_differential_receipt(blank, output, oracle=oracle)
    assert receipt["verdict"] == "passed"
    assert receipt["renderChecked"] is True
    assert validate_form_differential_receipt(receipt) == receipt
    assert hashlib.sha256(serialize_form_differential_receipt(receipt)).hexdigest()

    forged = copy.deepcopy(receipt)
    forged["overflowDetected"] = True
    forged["receiptSha256"] = form_differential_receipt_sha256(forged)
    with pytest.raises(ValueError, match="verdict mismatch"):
        validate_form_differential_receipt(forged)


def _must_policy() -> dict[str, str]:
    key_id = abstention_inventory_authentication_key_id(
        ABSTENTION_INVENTORY_KEY
    )
    return {
        "must_abstain": must_abstain_verifier_policy_sha256(
            inventory_authentication_key_id=key_id
        )
    }


def _requirement(
    task_kind: str = "constrained_edit",
    family: str = "meeting_minutes",
    *,
    artifact: str = "artifact",
) -> dict:
    verifier_policy_sha256s = None
    if task_kind == "must_abstain":
        verifier_policy_sha256s = _must_policy()
    return build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=_sha(artifact),
        task_kind=task_kind,
        family=family,
        verifier_policy_sha256s=verifier_policy_sha256s,
    )


def _abstention_receipt(
    scenario_id: str,
    *,
    recorded_output: bytes | None = None,
    terminal_reason: str = "DECISION_REQUIRED",
    event_status: str = "abstained",
) -> dict:
    event = {
        "schema": PRACTICE_RUN_EVENT_SCHEMA,
        "sequence": 0,
        "kind": "decision_gate",
        "status": event_status,
        "idempotencyKey": "IDEM-00000000000000000001",
        "requestSha256": _sha("abstention-request"),
        "responseSha256": _sha("abstention-response"),
        "elapsedMilliseconds": 1,
    }
    event["eventId"] = workflow_event_id(event)
    budgets = {
        "toolCalls": 1,
        "attempts": 1,
        "repairRounds": 0,
        "elapsedSeconds": 10,
        "costMicrounits": 100,
        "artifactBytes": 1024,
    }
    run = {
        "schema": PRACTICE_RUN_SCHEMA,
        "scenarioRef": {
            "scenarioId": scenario_id,
            "scenarioSha256": _sha("abstention-scenario"),
            "runnerManifestSha256": _sha("abstention-runner"),
            "derivativeSha256": _sha("abstention-derivative"),
            "startArtifactId": "ART-00000000000000000001",
            "startArtifactSha256": _sha("abstention-start"),
        },
        "dispatch": {
            "slot": 0,
            "dispatchKey": "DSP-00000000000000000001",
            "seedSha256": _sha("abstention-seed"),
        },
        "provenance": {
            "stack": {
                "core": {"version": "2.12.0.dev1", "sha256": _sha("core")},
                "server": {"version": "2.5.0.dev1", "sha256": _sha("server")},
                "skill": {"version": "0.1.9.dev1", "sha256": _sha("skill")},
            },
            "toolSpec": {"version": "tool-spec/v1", "sha256": "0123456789abcdef"},
            "evaluator": {
                "version": "practice-evaluator/v1",
                "sha256": _sha("evaluator"),
                "authenticationKeyId": "EVK-0123456789ABCDEF0123",
            },
        },
        "budgets": budgets,
        "state": "refused",
        "terminalReason": terminal_reason,
        "workflowEvents": [event],
        "artifacts": (
            [
                {
                    "artifactId": "OUT-00000000000000000001",
                    "role": "output",
                    "sha256": hashlib.sha256(recorded_output).hexdigest(),
                    "bytes": len(recorded_output),
                }
            ]
            if recorded_output is not None
            else []
        ),
        "evidence": {
            "semanticDiff": {"status": "unverified", "receiptSha256": None},
            "openSafety": {"status": "unverified", "receiptSha256": None},
            "domainVerdicts": [],
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
            "unresolvedReasonCodes": ["DECISION_REQUIRED"],
        },
        "usage": {
            "toolCalls": 1,
            "attempts": 1,
            "repairRounds": 0,
            "elapsedSeconds": 1,
            "costMicrounits": 1,
            "artifactBytes": len(recorded_output) if recorded_output is not None else 0,
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
    return redact_run_receipt(run)


class _UnavailableOracle:
    def available(self) -> bool:
        return False

    def render_pdf(self, hwpx_path, out_pdf=None):  # pragma: no cover
        return None


EXAM_ORACLE_KEY = b"exam-oracle-owner-key-material-0001"


class _ExamOracleAdapter:
    def __init__(self, measurement: dict, *, provenance_sha256: str | None = None):
        self.provenance_sha256 = provenance_sha256 or _sha("exam-oracle")
        self._measurement = measurement

    def measure_exam(self, input_path: Path, output_path: Path) -> dict:
        assert input_path.is_file()
        assert output_path.is_file()
        return dict(self._measurement)


def test_task_and_document_family_bindings_are_fixed_and_content_addressed() -> None:
    expected = {
        "reverse_restore": "edit",
        "constrained_edit": "edit",
        "known_template_fill": "form_fill",
        "unknown_form_fill": "form_fill",
        "structural_edit": "structural_table",
        "typed_authoring": "authoring",
        "must_abstain": "must_abstain",
    }
    for task_kind, verifier_family in expected.items():
        requirement = _requirement(task_kind)
        assert requirement["schema"] == DOMAIN_REQUIREMENT_SCHEMA
        assert [row["verifierFamily"] for row in requirement["verifiers"]] == [
            verifier_family
        ]
        assert requirement["expectedAbstention"] is (
            task_kind == "must_abstain"
        )
        assert validate_domain_requirement(requirement) == requirement

    exam = _requirement("structural_edit", "exam_question_answer")
    assert [row["verifierFamily"] for row in exam["verifiers"]] == [
        "structural_table",
        "exam",
    ]
    official = _requirement(
        "typed_authoring", "official_document_draft_dispatch"
    )
    assert [row["verifierFamily"] for row in official["verifiers"]] == [
        "authoring",
        "official_document",
    ]
    abstain = _requirement("must_abstain", "exam_question_answer")
    assert [row["verifierFamily"] for row in abstain["verifiers"]] == [
        "must_abstain"
    ]
    with pytest.raises(ValueError, match="closed code"):
        _requirement("structural_edit", "시험지_문항_정답")

    changed_artifact = _requirement(artifact="changed")
    assert (
        official["verifiers"][0]["verifierId"]
        != changed_artifact["verifiers"][0]["verifierId"]
    )


def test_requirement_rejects_removed_or_reordered_checks_and_hash_tamper() -> None:
    requirement = _requirement("structural_edit")
    missing = copy.deepcopy(requirement)
    missing["verifiers"][0]["requiredChecks"].pop()
    missing["requirementSha256"] = domain_requirement_sha256(missing)
    with pytest.raises(ValueError, match="required domain checks"):
        validate_domain_requirement(missing)

    tampered = copy.deepcopy(requirement)
    tampered["artifactSha256"] = _sha("other")
    with pytest.raises(ValueError, match="content-bound|requirementSha256"):
        validate_domain_requirement(tampered)


def test_edit_evidence_passes_only_with_every_exact_required_check() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    assert evidence["schema"] == DOMAIN_EVIDENCE_SCHEMA
    assert evidence["status"] == "passed"
    assert validate_domain_evidence(evidence) == evidence
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="completed"
    )
    assert result["schema"] == DOMAIN_RESULT_SCHEMA
    assert result["status"] == "passed"
    assert result["reasonCode"] == "DOMAIN_PASSED"
    assert result["passedVerifierCount"] == 1
    assert validate_domain_result(result) == result

    with pytest.raises(ValueError, match="coverage is not exact"):
        build_domain_evidence(
            requirement,
            verifier_family="edit",
            checks={"expected_change_pass": True},
            observed_terminal_state="completed",
        )


@pytest.mark.parametrize(
    ("values", "expected_status", "expected_reason"),
    [
        ((True, False, True), "failed", "DOMAIN_VERIFIER_FAILED"),
        ((True, None, True), "unverified", "DOMAIN_VERIFIER_UNVERIFIED"),
        ((True, "not_run", True), "unverified", "DOMAIN_VERIFIER_UNVERIFIED"),
    ],
)
def test_failed_or_missing_measurements_never_become_success(
    values: tuple[object, object, object],
    expected_status: str,
    expected_reason: str,
) -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=values[0],
        forbidden_drift_absent=values[1],
        untouched_members_preserved=values[2],
        observed_terminal_state="completed",
    )
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="completed"
    )
    assert result["status"] == expected_status
    assert result["reasonCode"] == expected_reason

    missing = evaluate_domain(
        requirement, [], observed_terminal_state="completed"
    )
    assert missing["status"] == "unverified"
    assert missing["reasonCode"] == "DOMAIN_VERIFIER_MISSING"


def test_duplicate_failed_evidence_has_failure_precedence() -> None:
    requirement = _requirement()
    passed = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    failed = build_edit_domain_evidence(
        requirement,
        expected_change_pass=False,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    result = evaluate_domain(
        requirement, [passed, failed], observed_terminal_state="completed"
    )
    assert result["status"] == "failed"
    assert result["reasonCode"] == "DOMAIN_VERIFIER_FAILED"
    assert result["verdicts"][0]["failedChecks"] == ["expected_change_pass"]


def test_malformed_stale_and_duplicate_evidence_fail_closed() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )

    malformed = copy.deepcopy(evidence)
    malformed["evidenceSha256"] = _sha("forged")
    result = evaluate_domain(
        requirement, [evidence, malformed], observed_terminal_state="completed"
    )
    assert result["status"] == "unverified"
    assert result["reasonCode"] == "DOMAIN_EVIDENCE_MALFORMED"
    assert result["malformedEvidenceCount"] == 1

    duplicate = evaluate_domain(
        requirement, [evidence, evidence], observed_terminal_state="completed"
    )
    assert duplicate["status"] == "unverified"
    assert duplicate["reasonCode"] == "DOMAIN_VERIFIER_DUPLICATE"

    stale_requirement = _requirement(artifact="stale")
    stale = build_edit_domain_evidence(
        stale_requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    stale_result = evaluate_domain(
        requirement, [stale], observed_terminal_state="completed"
    )
    assert stale_result["status"] == "unverified"
    assert stale_result["reasonCode"] == "DOMAIN_EVIDENCE_BINDING_MISMATCH"


def test_all_explicit_task_verifiers_have_closed_check_contracts() -> None:
    form_requirement = _requirement("unknown_form_fill")
    form = build_form_fill_domain_evidence(
        form_requirement,
        mapping_complete=True,
        residue_absent=False,
        synthetic_values_verified=True,
        observed_terminal_state="completed",
    )
    assert form["status"] == "failed"
    assert [row["code"] for row in form["checks"]] == list(
        VERIFIER_CHECKS["form_fill"]
    )

    structural_requirement = _requirement("structural_edit")
    structural = build_structural_table_domain_evidence(
        structural_requirement,
        table_geometry_preserved=True,
        exact_values_pass=True,
        merged_cells_preserved=None,
        observed_terminal_state="completed",
    )
    assert structural["status"] == "unverified"


def test_exam_adapter_does_not_silently_pass_when_render_measurement_is_blind(
    tmp_path,
) -> None:
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"output")
    provenance_sha = _sha("exam-oracle")
    policy_sha = exam_verifier_policy_sha256(
        input_artifact_sha256=hashlib.sha256(b"input").hexdigest(),
        oracle_provenance_sha256=provenance_sha,
        oracle_authentication_key_id=exam_oracle_authentication_key_id(
            EXAM_ORACLE_KEY
        ),
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(b"output").hexdigest(),
        task_kind="structural_edit",
        family="exam_question_answer",
        verifier_policy_sha256s={"exam": policy_sha},
    )
    blind_receipt = build_exam_oracle_receipt(
        input_path,
        output_path,
        _ExamOracleAdapter(
            {
                "renderChecked": True,
                "questionSplits": None,
                "placeholdersOk": True,
                "examInvariantsPass": True,
            },
            provenance_sha256=provenance_sha,
        ),
        oracle_authentication_key=EXAM_ORACLE_KEY,
    )
    evidence = build_exam_domain_evidence(
        requirement,
        blind_receipt,
        oracle_authentication_key=EXAM_ORACLE_KEY,
        observed_terminal_state="completed",
    )
    assert evidence["status"] == "unverified"
    assert [row["status"] for row in evidence["checks"]] == [
        "unverified",
        "unverified",
        "passed",
    ]
    emitted = repr(evidence)
    assert "forbidden.hwpx" not in emitted
    assert "private finding" not in emitted

    measured_receipt = build_exam_oracle_receipt(
        input_path,
        output_path,
        _ExamOracleAdapter(
            {
                "renderChecked": True,
                "questionSplits": 0,
                "placeholdersOk": True,
                "examInvariantsPass": True,
            },
            provenance_sha256=provenance_sha,
        ),
        oracle_authentication_key=EXAM_ORACLE_KEY,
    )
    measured = build_exam_domain_evidence(
        requirement,
        measured_receipt,
        oracle_authentication_key=EXAM_ORACLE_KEY,
        observed_terminal_state="completed",
    )
    assert measured["status"] == "passed"
    key_id = exam_oracle_authentication_key_id(EXAM_ORACLE_KEY)
    assert measured["sourceEvidence"] == {
        "schema": domain_module.DOMAIN_SOURCE_EVIDENCE_SCHEMA,
        "receiptSha256": measured_receipt["receiptSha256"],
        "authenticationKeyId": key_id,
        "receipt": measured_receipt,
    }
    assert EXAM_ORACLE_KEY.hex() not in repr(measured)
    with pytest.raises(ValueError, match="authentication key is required"):
        validate_domain_evidence(measured)
    assert validate_domain_evidence(
        measured,
        oracle_authentication_keys={key_id: EXAM_ORACLE_KEY},
    ) == measured

    structural = build_structural_table_domain_evidence(
        requirement,
        table_geometry_preserved=True,
        exact_values_pass=True,
        merged_cells_preserved=True,
        observed_terminal_state="completed",
    )
    bundle = build_domain_evaluation_bundle(
        requirement,
        [structural, measured],
        observed_terminal_state="completed",
        oracle_authentication_keys={key_id: EXAM_ORACLE_KEY},
    )
    assert bundle["result"]["status"] == "passed"
    with pytest.raises(ValueError, match="authentication key is required"):
        validate_domain_evaluation_bundle(bundle)
    assert validate_domain_evaluation_bundle(
        bundle,
        oracle_authentication_keys={key_id: EXAM_ORACLE_KEY},
    ) == bundle

    tampered_source = copy.deepcopy(measured)
    tampered_source["sourceEvidence"]["receipt"]["examInvariantsPass"] = False
    tampered_source["evidenceSha256"] = domain_evidence_sha256(tampered_source)
    with pytest.raises(ValueError, match="authentication failed"):
        validate_domain_evidence(
            tampered_source,
            oracle_authentication_keys={key_id: EXAM_ORACLE_KEY},
        )

    rewritten_reference = copy.deepcopy(measured)
    rewritten_reference["sourceEvidence"]["receiptSha256"] = _sha(
        "rewritten-source-reference"
    )
    rewritten_reference["evidenceSha256"] = domain_evidence_sha256(
        rewritten_reference
    )
    with pytest.raises(ValueError, match="source evidence binding mismatch"):
        validate_domain_evidence(
            rewritten_reference,
            oracle_authentication_keys={key_id: EXAM_ORACLE_KEY},
        )


@pytest.mark.parametrize(
    ("splits", "placeholders"),
    [(False, True), (0, "false"), (-1, True), ("0", True)],
)
def test_exam_adapter_requires_exact_measured_types(
    splits: object, placeholders: object, tmp_path
) -> None:
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"output")
    with pytest.raises(ValueError, match="questionSplits|placeholdersOk"):
        build_exam_oracle_receipt(
            input_path,
            output_path,
            _ExamOracleAdapter(
                {
                    "renderChecked": True,
                    "questionSplits": splits,
                    "placeholdersOk": placeholders,
                    "examInvariantsPass": True,
                }
            ),
            oracle_authentication_key=EXAM_ORACLE_KEY,
        )


def test_exam_oracle_rejects_raw_measurements_wrong_keys_and_caller_chosen_keys(
    tmp_path,
) -> None:
    from hwpx.practice.evaluator import evaluator_authentication_key_id

    assert exam_oracle_authentication_key_id(EXAM_ORACLE_KEY).startswith("EOK-")
    assert exam_oracle_authentication_key_id(
        EXAM_ORACLE_KEY
    ) != evaluator_authentication_key_id(EXAM_ORACLE_KEY)
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"output")
    measurement = {
        "renderChecked": True,
        "questionSplits": 0,
        "placeholdersOk": True,
        "examInvariantsPass": True,
    }
    with pytest.raises(ValueError, match="adapter"):
        build_exam_oracle_receipt(
            input_path,
            output_path,
            measurement,
            oracle_authentication_key=EXAM_ORACLE_KEY,
        )

    provenance_sha = _sha("exam-oracle")
    honest_receipt = build_exam_oracle_receipt(
        input_path,
        output_path,
        _ExamOracleAdapter(measurement, provenance_sha256=provenance_sha),
        oracle_authentication_key=EXAM_ORACLE_KEY,
    )
    tampered = copy.deepcopy(honest_receipt)
    tampered["examInvariantsPass"] = False
    with pytest.raises(ValueError, match="authentication failed"):
        build_exam_domain_evidence(
            build_domain_requirement(
                scenario_sha256=_sha("scenario"),
                artifact_sha256=hashlib.sha256(b"output").hexdigest(),
                task_kind="structural_edit",
                family="exam_question_answer",
            ),
            tampered,
            oracle_authentication_key=EXAM_ORACLE_KEY,
            observed_terminal_state="completed",
        )
    policy_sha = exam_verifier_policy_sha256(
        input_artifact_sha256=hashlib.sha256(b"input").hexdigest(),
        oracle_provenance_sha256=provenance_sha,
        oracle_authentication_key_id=exam_oracle_authentication_key_id(
            EXAM_ORACLE_KEY
        ),
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(b"output").hexdigest(),
        task_kind="structural_edit",
        family="exam_question_answer",
        verifier_policy_sha256s={"exam": policy_sha},
    )
    wrong_key = b"wrong-exam-oracle-owner-key-000000"
    with pytest.raises(ValueError, match="key mismatch"):
        build_exam_domain_evidence(
            requirement,
            honest_receipt,
            oracle_authentication_key=wrong_key,
            observed_terminal_state="completed",
        )

    attacker_receipt = build_exam_oracle_receipt(
        input_path,
        output_path,
        _ExamOracleAdapter(measurement, provenance_sha256=provenance_sha),
        oracle_authentication_key=wrong_key,
    )
    attacker_evidence = build_exam_domain_evidence(
        requirement,
        attacker_receipt,
        oracle_authentication_key=wrong_key,
        observed_terminal_state="completed",
    )
    assert attacker_evidence["status"] == "unverified"
    assert all(
        row["status"] == "unverified" for row in attacker_evidence["checks"]
    )
    structural = build_structural_table_domain_evidence(
        requirement,
        table_geometry_preserved=True,
        exact_values_pass=True,
        merged_cells_preserved=True,
        observed_terminal_state="completed",
    )
    attacker_key_id = exam_oracle_authentication_key_id(wrong_key)
    with pytest.raises(ValueError, match="frozen verifier policy"):
        build_domain_evaluation_bundle(
            requirement,
            [structural, attacker_evidence],
            observed_terminal_state="completed",
            oracle_authentication_keys={attacker_key_id: wrong_key},
        )


def test_official_document_adapter_uses_bound_artifact_and_frozen_lint_policy(
    tmp_path,
) -> None:
    from hwpx.document import HwpxDocument

    source = tmp_path / "official.hwpx"
    document = HwpxDocument.new()
    for text in (
        "수신  합성수신자",
        "1. 합성 안건",
        "끝.",
        "합성학교장",
        "시행 합성-1",
        "공개",
    ):
        document.add_paragraph(text)
    document.save_to_path(source)
    document.close()
    policy_sha = official_verifier_policy_sha256(document_type="공문")
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        task_kind="constrained_edit",
        family="official_document_draft_dispatch",
        verifier_policy_sha256s={"official_document": policy_sha},
    )
    evidence = build_official_document_domain_evidence(
        requirement, source, observed_terminal_state="completed"
    )
    assert evidence["status"] == "passed"
    assert str(source) not in repr(evidence)
    assert all(set(row) == {"code", "status"} for row in evidence["checks"])
    assert_receipt_safe(evidence, sensitive_values=(str(source),))

    rewritten_policy = build_official_document_domain_evidence(
        requirement,
        source,
        observed_terminal_state="completed",
        document_type="일반문서",
    )
    assert rewritten_policy["status"] == "unverified"
    assert all(row["status"] == "unverified" for row in rewritten_policy["checks"])

    missing_path = "/Volumes/private/missing-official-output.hwpx"
    unavailable = build_official_document_domain_evidence(
        requirement, missing_path, observed_terminal_state="unverified"
    )
    assert unavailable["status"] == "unverified"
    assert all(row["status"] == "unverified" for row in unavailable["checks"])
    assert missing_path not in repr(unavailable)


def test_authoring_adapter_fails_closed_without_artifact_or_style_evidence() -> None:
    requirement = _requirement("typed_authoring")
    private_path = "/Volumes/private/missing-authoring-output.hwpx"
    evidence = build_authoring_domain_evidence(
        requirement,
        private_path,
        observed_terminal_state="unverified",
        style_reference=None,
    )
    assert evidence["status"] == "unverified"
    assert all(row["status"] == "unverified" for row in evidence["checks"])
    assert private_path not in repr(evidence)


def test_authoring_adapter_rejects_rewritten_plan_or_style_reference(tmp_path) -> None:
    from hwpx.document import HwpxDocument

    output = tmp_path / "authoring.hwpx"
    style = tmp_path / "style.hwpx"
    for path, text in ((output, "합성 작성 결과"), (style, "합성 스타일 기준")):
        document = HwpxDocument.new()
        document.add_paragraph(text)
        document.save_to_path(path)
        document.close()
    plan = {"schemaVersion": "hwpx.document_plan.v2", "preset": "default", "sections": []}
    policy_sha = authoring_verifier_policy_sha256(
        plan=plan,
        style_reference_sha256=hashlib.sha256(style.read_bytes()).hexdigest(),
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="typed_authoring",
        family="notice",
        verifier_policy_sha256s={"authoring": policy_sha},
    )

    rewritten = build_authoring_domain_evidence(
        requirement,
        output,
        observed_terminal_state="completed",
        plan={**plan, "preset": "government_report"},
        style_reference=style,
    )
    assert rewritten["status"] == "unverified"
    assert all(row["status"] == "unverified" for row in rewritten["checks"])

    omitted_style = build_authoring_domain_evidence(
        requirement,
        output,
        observed_terminal_state="completed",
        plan=plan,
        style_reference=None,
    )
    assert omitted_style["status"] == "unverified"
    assert all(row["status"] == "unverified" for row in omitted_style["checks"])


def test_correct_abstention_requires_exact_passed_evidence_not_id_inference() -> None:
    requirement = _requirement("must_abstain", "exam_question_answer")
    evidence = build_must_abstain_domain_evidence(
        requirement,
        no_mutation=True,
        decision_reason_present=True,
        observed_terminal_state="refused",
    )
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="refused"
    )
    assert result["status"] == "passed"
    assert result["expectedAbstention"] is True
    assert result["observedAbstention"] is True
    assert result["verdicts"] == [
        {
            "verifierFamily": "must_abstain",
            "verifierId": requirement["verifiers"][0]["verifierId"],
            "status": "passed",
            "reasonCode": "DOMAIN_VERIFIER_PASSED",
            "evidenceSha256": evidence["evidenceSha256"],
            "requiredChecks": list(VERIFIER_CHECKS["must_abstain"]),
            "passedChecks": list(VERIFIER_CHECKS["must_abstain"]),
            "failedChecks": [],
            "unverifiedChecks": [],
        }
    ]

    wrong_terminal = build_must_abstain_domain_evidence(
        requirement,
        no_mutation=True,
        decision_reason_present=True,
        observed_terminal_state="completed",
    )
    wrong = evaluate_domain(
        requirement, [wrong_terminal], observed_terminal_state="completed"
    )
    assert wrong["status"] == "failed"
    assert wrong["observedAbstention"] is False
    assert wrong["verdicts"][0]["failedChecks"] == ["terminal_state_allowed"]

    with pytest.raises(ValueError, match="contradicts"):
        build_domain_evidence(
            requirement,
            verifier_family="must_abstain",
            checks={
                "terminal_state_allowed": True,
                "no_mutation": True,
                "decision_reason_present": True,
            },
            observed_terminal_state="completed",
        )


def test_no_free_text_paths_pii_or_gold_leakage_in_durable_contracts() -> None:
    requirement = _requirement("must_abstain")
    evidence = build_must_abstain_domain_evidence(
        requirement,
        no_mutation=True,
        decision_reason_present=True,
        observed_terminal_state="needs_review",
    )
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="needs_review"
    )
    sensitive = (
        "/Volumes/private/source.hwpx",
        "900101-1234567",
        "private gold answer",
    )
    for value in (requirement, evidence, result):
        assert_receipt_safe(value, sensitive_values=sensitive)
        emitted = repr(value)
        assert not any(secret in emitted for secret in sensitive)

    extra = copy.deepcopy(result)
    extra["reasonCode"] = "because the source path was private"
    extra["resultSha256"] = domain_result_sha256(extra)
    with pytest.raises(ValueError, match="reasonCode is not closed"):
        validate_domain_result(extra)


def test_content_hashes_detect_tamper_and_result_precedence_cannot_be_rehashed() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=False,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    tampered_evidence = copy.deepcopy(evidence)
    tampered_evidence["checks"][0]["status"] = "passed"
    assert domain_evidence_sha256(tampered_evidence) != evidence["evidenceSha256"]
    with pytest.raises(ValueError):
        validate_domain_evidence(tampered_evidence)

    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="completed"
    )
    forged = copy.deepcopy(result)
    forged["status"] = "passed"
    forged["reasonCode"] = "DOMAIN_PASSED"
    forged["resultSha256"] = domain_result_sha256(forged)
    with pytest.raises(ValueError, match="precedence"):
        validate_domain_result(forged)


def test_requirement_hash_detects_self_address_tamper() -> None:
    requirement = _requirement()
    assert requirement["requirementSha256"] == domain_requirement_sha256(requirement)
    result = evaluate_domain(requirement, [], observed_terminal_state="failed")
    assert result["resultSha256"] == domain_result_sha256(result)


def test_standalone_bundle_embeds_exact_receipts_and_recomputes_result() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    bundle = build_domain_evaluation_bundle(
        requirement, [evidence], observed_terminal_state="completed"
    )
    assert bundle["schema"] == DOMAIN_EVALUATION_BUNDLE_SCHEMA
    assert bundle["requirement"] == requirement
    assert bundle["evidence"] == [evidence]
    assert bundle["result"]["status"] == "passed"
    assert bundle["bundleSha256"] == domain_evaluation_bundle_sha256(bundle)
    assert validate_domain_evaluation_bundle(bundle) == bundle


def test_bundle_rejects_forged_passed_result_with_nonexistent_receipt_hashes() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    bundle = build_domain_evaluation_bundle(
        requirement, [evidence], observed_terminal_state="completed"
    )
    forged = copy.deepcopy(bundle)
    forged["result"]["requirementSha256"] = _sha("nonexistent-requirement")
    forged["result"]["verdicts"][0]["evidenceSha256"] = _sha(
        "nonexistent-evidence"
    )
    forged["result"]["resultSha256"] = domain_result_sha256(forged["result"])
    forged["bundleSha256"] = domain_evaluation_bundle_sha256(forged)
    with pytest.raises(ValueError, match="recomputed evaluation"):
        validate_domain_evaluation_bundle(forged)

    # A bare result cannot satisfy the standalone bundle schema at all.
    with pytest.raises(ValueError, match="fields mismatch"):
        validate_domain_evaluation_bundle(forged["result"])


def test_bundle_secondary_family_verifier_omission_cannot_be_forged_to_pass() -> None:
    requirement = _requirement(
        "constrained_edit", "official_document_draft_dispatch"
    )
    edit = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    honest = build_domain_evaluation_bundle(
        requirement, [edit], observed_terminal_state="completed"
    )
    assert honest["result"]["status"] == "unverified"
    assert [row["verifierFamily"] for row in honest["result"]["verdicts"]] == [
        "edit",
        "official_document",
    ]
    assert honest["result"]["verdicts"][1]["reasonCode"] == "DOMAIN_VERIFIER_MISSING"

    forged = copy.deepcopy(honest)
    forged["result"]["verdicts"] = forged["result"]["verdicts"][:1]
    forged["result"]["requiredVerifierCount"] = 1
    forged["result"]["passedVerifierCount"] = 1
    forged["result"]["status"] = "passed"
    forged["result"]["reasonCode"] = "DOMAIN_PASSED"
    forged["result"]["resultSha256"] = domain_result_sha256(forged["result"])
    forged["bundleSha256"] = domain_evaluation_bundle_sha256(forged)
    with pytest.raises(ValueError, match="recomputed evaluation|verifier coverage"):
        validate_domain_evaluation_bundle(forged)


def test_domain_policy_projection_is_frozen_but_excludes_output_artifact() -> None:
    first = _requirement(artifact="first-output")
    second = _requirement(artifact="second-output")
    projection = domain_requirement_policy_projection(first)
    assert projection == domain_requirement_policy_projection(second)
    assert "artifactSha256" not in repr(projection)
    assert "verifierId" not in repr(projection)
    assert projection["verifiers"] == [
        {
            "verifierFamily": "edit",
            "requiredChecks": list(VERIFIER_CHECKS["edit"]),
            "policySha256": first["verifiers"][0]["policySha256"],
        }
    ]
    assert len(projection["policySha256"]) == 64


def test_non_abstention_domain_cannot_pass_an_unsuccessful_terminal_state() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="refused",
    )
    assert evidence["status"] == "unverified"
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="refused"
    )
    assert result["status"] == "unverified"


def test_bare_result_validator_rejects_rehashed_pass_with_wrong_terminal() -> None:
    requirement = _requirement()
    evidence = build_edit_domain_evidence(
        requirement,
        expected_change_pass=True,
        forbidden_drift_absent=True,
        untouched_members_preserved=True,
        observed_terminal_state="completed",
    )
    result = evaluate_domain(
        requirement, [evidence], observed_terminal_state="completed"
    )
    forged = copy.deepcopy(result)
    forged["observedTerminalState"] = "refused"
    forged["resultSha256"] = domain_result_sha256(forged)
    with pytest.raises(ValueError, match="completed terminal"):
        validate_domain_result(forged)

    abstention_requirement = _requirement("must_abstain")
    abstention_evidence = build_must_abstain_domain_evidence(
        abstention_requirement,
        no_mutation=True,
        decision_reason_present=True,
        observed_terminal_state="refused",
    )
    abstention_result = evaluate_domain(
        abstention_requirement,
        [abstention_evidence],
        observed_terminal_state="refused",
    )
    forged_abstention = copy.deepcopy(abstention_result)
    forged_abstention["observedTerminalState"] = "completed"
    forged_abstention["observedAbstention"] = False
    forged_abstention["resultSha256"] = domain_result_sha256(forged_abstention)
    with pytest.raises(ValueError, match="allowed abstention terminal"):
        validate_domain_result(forged_abstention)


def test_production_adapters_cannot_pass_missing_artifacts_or_receipts(
    tmp_path,
) -> None:
    missing = tmp_path / "missing.hwpx"

    edit_requirement = _requirement("constrained_edit")
    edit = build_edit_domain_evidence_from_semantic(
        edit_requirement, {}, observed_terminal_state="completed"
    )
    assert edit["status"] == "unverified"

    target_policy = build_form_target_policy(
        blank_artifact_sha256=_sha("missing-blank"),
        bindings=[
            {
                "sectionIndex": 0,
                "tableIndex": 0,
                "row": 0,
                "col": 0,
                "blankValueSha256": domain_value_sha256("BLANK"),
                "expectedValueSha256": domain_value_sha256("SYNTHETIC"),
            }
        ],
    )
    missing_receipt_sha = _sha("missing-form-differential-receipt")
    form_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=_sha("missing-output"),
        task_kind="known_template_fill",
        family="notice",
        verifier_policy_sha256s={
            "form_fill": form_verifier_policy_sha256(
                target_policy_sha256=target_policy["policySha256"],
                differential_receipt_asset_sha256=missing_receipt_sha,
            )
        },
    )
    form = build_form_fill_domain_evidence_from_artifacts(
        form_requirement,
        missing,
        missing,
        target_policy=target_policy,
        frozen_differential_receipt_path=missing,
        frozen_differential_receipt_asset_sha256=missing_receipt_sha,
        observed_terminal_state="completed",
    )
    assert form["status"] == "unverified"

    expected_start_sha = _sha("missing-start")
    expected_row_sha = domain_row_sha256(["SYNTHETIC", "ROW"])
    expected_value_shas = [domain_value_sha256("SYNTHETIC")]
    structural_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=_sha("missing-output"),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "structural_table": structural_verifier_policy_sha256(
                expected_start_sha256=expected_start_sha,
                expected_row_sha256=expected_row_sha,
                expected_value_sha256s=expected_value_shas,
            )
        },
    )
    structural = build_structural_table_domain_evidence_from_artifacts(
        structural_requirement,
        missing,
        missing,
        expected_start_sha256=expected_start_sha,
        expected_row_sha256=expected_row_sha,
        expected_value_sha256s=expected_value_shas,
        observed_terminal_state="completed",
    )
    assert structural["status"] == "unverified"

    abstention_requirement = _requirement("must_abstain")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    abstention = build_must_abstain_domain_evidence_from_receipt(
        abstention_requirement,
        missing,
        {},
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id="SCN-00000000000000000001",
        sandbox_output_root=output_root,
    )
    assert abstention["status"] == "unverified"
    assert abstention["reasonCode"] == "DOMAIN_VERIFIER_UNVERIFIED"


def test_structural_production_adapter_measures_real_hwpX_row_insertion(tmp_path) -> None:
    from hwpx.document import HwpxDocument

    start = tmp_path / "start.hwpx"
    output = tmp_path / "output.hwpx"
    before = HwpxDocument.new()
    table = before.add_table(1, 2)
    table.set_cell_text(0, 0, "BASE")
    table.set_cell_text(0, 1, "ROW")
    before.save_to_path(start)
    before.close()

    after = HwpxDocument.new()
    table = after.add_table(2, 2)
    table.set_cell_text(0, 0, "BASE")
    table.set_cell_text(0, 1, "ROW")
    table.set_cell_text(1, 0, "SYNTHETIC")
    table.set_cell_text(1, 1, "VALUE")
    after.save_to_path(output)
    after.close()

    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    expected_row_sha = domain_row_sha256(["SYNTHETIC", "VALUE"])
    expected_value_shas = [
        domain_value_sha256("SYNTHETIC"),
        domain_value_sha256("VALUE"),
    ]
    policy_sha = structural_verifier_policy_sha256(
        expected_start_sha256=start_sha,
        expected_row_sha256=expected_row_sha,
        expected_value_sha256s=expected_value_shas,
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={"structural_table": policy_sha},
    )
    evidence = build_structural_table_domain_evidence_from_artifacts(
        requirement,
        start,
        output,
        expected_start_sha256=start_sha,
        expected_row_sha256=expected_row_sha,
        expected_value_sha256s=expected_value_shas,
        observed_terminal_state="completed",
    )
    assert evidence["status"] == "passed"
    assert all(item["status"] == "passed" for item in evidence["checks"])

    wrong_start_sha = _sha("wrong-start")
    wrong_policy_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "structural_table": structural_verifier_policy_sha256(
                expected_start_sha256=wrong_start_sha,
                expected_row_sha256=expected_row_sha,
                expected_value_sha256s=expected_value_shas,
            )
        },
    )
    stale_start = build_structural_table_domain_evidence_from_artifacts(
        wrong_policy_requirement,
        start,
        output,
        expected_start_sha256=wrong_start_sha,
        expected_row_sha256=expected_row_sha,
        expected_value_sha256s=expected_value_shas,
        observed_terminal_state="completed",
    )
    assert stale_start["status"] == "unverified"
    assert all(item["status"] == "unverified" for item in stale_start["checks"])


def test_structural_adapter_normalizes_preserved_merges_for_cloned_row(
    tmp_path,
) -> None:
    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import HP
    from hwpx.table_patch import apply_table_ops

    start = tmp_path / "merge-clone-start.hwpx"
    output = tmp_path / "merge-clone-output.hwpx"
    merge_loss = tmp_path / "merge-clone-loss.hwpx"

    before = HwpxDocument.new()
    table = before.add_table(3, 7)

    def merge_and_prune(target, row: int, start_col: int, end_col: int) -> None:
        target.merge_cells(row, start_col, row, end_col)
        row_element = list(target.element.findall(f"{HP}tr"))[row]
        for cell in list(row_element.findall(f"{HP}tc")):
            address = cell.find(f"{HP}cellAddr")
            column = int(address.get("colAddr", "-1")) if address is not None else -1
            if start_col < column <= end_col:
                row_element.remove(cell)
        target.mark_dirty()

    for col, value in enumerate(("BASE-A", "BASE-B", "BASE-C")):
        table.set_cell_text(0, col, value)
    merge_and_prune(table, 0, 2, 6)
    for col, value in enumerate(
        ("OLD-A", "OLD-B", "", "", "OLD-C", "OLD-D", "OLD-E")
    ):
        table.set_cell_text(1, col, value)
    merge_and_prune(table, 1, 1, 3)
    for col in range(7):
        table.set_cell_text(2, col, f"TAIL-{col}")
    before.save_to_path(start)
    before.close()

    expected_values = ("SYN-A", "SYN-B", "SYN-C")
    result = apply_table_ops(
        start,
        [
            {"op": "insert_row_by_clone", "table_index": 0, "ref_row": 0},
            *(
                {
                    "op": "fill_cell",
                    "table_index": 0,
                    "row": 1,
                    "col": col,
                    "text": value,
                }
                for col, value in enumerate(expected_values)
            ),
        ],
        output_path=output,
    )
    assert result.open_safety is not None and result.open_safety["ok"] is True

    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    row_sha = domain_row_sha256(expected_values)
    value_shas = [domain_value_sha256(value) for value in expected_values]
    policy_sha = structural_verifier_policy_sha256(
        expected_start_sha256=start_sha,
        expected_row_sha256=row_sha,
        expected_value_sha256s=value_shas,
    )

    def evaluate(path: Path) -> dict:
        requirement = build_domain_requirement(
            scenario_sha256=_sha("merge-clone-scenario"),
            artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            task_kind="structural_edit",
            family="lesson_materials",
            verifier_policy_sha256s={"structural_table": policy_sha},
        )
        return build_structural_table_domain_evidence_from_artifacts(
            requirement,
            start,
            path,
            expected_start_sha256=start_sha,
            expected_row_sha256=row_sha,
            expected_value_sha256s=value_shas,
            observed_terminal_state="completed",
        )

    evidence = evaluate(output)
    assert evidence["status"] == "passed"
    assert all(item["status"] == "passed" for item in evidence["checks"])

    damaged = HwpxDocument.new()
    damaged_table = damaged.add_table(4, 7)
    for col, value in enumerate(("BASE-A", "BASE-B", "BASE-C")):
        damaged_table.set_cell_text(0, col, value)
    merge_and_prune(damaged_table, 0, 2, 6)
    for col, value in enumerate(expected_values):
        damaged_table.set_cell_text(1, col, value)
    merge_and_prune(damaged_table, 1, 2, 6)
    for col, value in enumerate(
        ("OLD-A", "OLD-B", "", "", "OLD-C", "OLD-D", "OLD-E")
    ):
        damaged_table.set_cell_text(2, col, value)
    for col in range(7):
        damaged_table.set_cell_text(3, col, f"TAIL-{col}")
    damaged.save_to_path(merge_loss)
    damaged.close()

    loss_evidence = evaluate(merge_loss)
    loss_statuses = {
        item["code"]: item["status"] for item in loss_evidence["checks"]
    }
    assert loss_statuses["merged_cells_preserved"] == "failed"
    assert loss_evidence["status"] == "failed"


def test_structural_adapter_requires_expected_values_in_newly_inserted_row(tmp_path) -> None:
    from hwpx.document import HwpxDocument

    start = tmp_path / "preexisting-value.hwpx"
    output = tmp_path / "blank-row-inserted.hwpx"
    before = HwpxDocument.new()
    table = before.add_table(1, 2)
    table.set_cell_text(0, 0, "SYNTHETIC")
    table.set_cell_text(0, 1, "VALUE")
    before.save_to_path(start)
    before.close()
    after = HwpxDocument.new()
    table = after.add_table(2, 2)
    table.set_cell_text(0, 0, "SYNTHETIC")
    table.set_cell_text(0, 1, "VALUE")
    after.save_to_path(output)
    after.close()

    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    row_sha = domain_row_sha256(["SYNTHETIC", "VALUE"])
    value_shas = [domain_value_sha256("SYNTHETIC"), domain_value_sha256("VALUE")]
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "structural_table": structural_verifier_policy_sha256(
                expected_start_sha256=start_sha,
                expected_row_sha256=row_sha,
                expected_value_sha256s=value_shas,
            )
        },
    )
    evidence = build_structural_table_domain_evidence_from_artifacts(
        requirement,
        start,
        output,
        expected_start_sha256=start_sha,
        expected_row_sha256=row_sha,
        expected_value_sha256s=value_shas,
        observed_terminal_state="completed",
    )
    statuses = {item["code"]: item["status"] for item in evidence["checks"]}
    assert statuses["table_geometry_preserved"] == "passed"
    assert statuses["exact_values_pass"] == "failed"
    assert evidence["status"] == "failed"


def test_structural_adapter_detects_relocated_merge_with_same_shape(tmp_path) -> None:
    from hwpx.document import HwpxDocument

    start = tmp_path / "merge-start.hwpx"
    output = tmp_path / "merge-relocated.hwpx"
    before = HwpxDocument.new()
    table = before.add_table(2, 2)
    table.set_cell_text(0, 0, "HEAD")
    table.set_cell_text(1, 0, "BASE")
    table.set_cell_text(1, 1, "ROW")
    table.merge_cells(0, 0, 0, 1)
    before.save_to_path(start)
    before.close()
    after = HwpxDocument.new()
    table = after.add_table(3, 2)
    table.set_cell_text(0, 0, "HEAD")
    table.set_cell_text(1, 0, "BASE")
    table.set_cell_text(2, 0, "SYNTHETIC")
    table.set_cell_text(2, 1, "VALUE")
    table.merge_cells(1, 0, 1, 1)
    after.save_to_path(output)
    after.close()

    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    row_sha = domain_row_sha256(["SYNTHETIC", "VALUE"])
    value_shas = [domain_value_sha256("SYNTHETIC"), domain_value_sha256("VALUE")]
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "structural_table": structural_verifier_policy_sha256(
                expected_start_sha256=start_sha,
                expected_row_sha256=row_sha,
                expected_value_sha256s=value_shas,
            )
        },
    )
    evidence = build_structural_table_domain_evidence_from_artifacts(
        requirement,
        start,
        output,
        expected_start_sha256=start_sha,
        expected_row_sha256=row_sha,
        expected_value_sha256s=value_shas,
        observed_terminal_state="completed",
    )
    statuses = {item["code"]: item["status"] for item in evidence["checks"]}
    assert statuses["merged_cells_preserved"] == "failed"
    assert evidence["status"] == "failed"


def test_form_production_adapter_binds_expected_values_to_exact_cells(tmp_path) -> None:
    from hwpx.document import HwpxDocument

    blank = tmp_path / "blank.hwpx"
    output = tmp_path / "filled.hwpx"
    swapped = tmp_path / "swapped.hwpx"

    def save_form(path: Path, left: str, right: str) -> None:
        document = HwpxDocument.new()
        table = document.add_table(1, 2)
        table.set_cell_text(0, 0, left)
        table.set_cell_text(0, 1, right)
        document.save_to_path(path)
        document.close()

    save_form(blank, "BLANK_NAME", "BLANK_DATE")
    save_form(output, "SYN_NAME", "SYN_DATE")
    save_form(swapped, "SYN_DATE", "SYN_NAME")
    policy = build_form_target_policy(
        blank_artifact_sha256=hashlib.sha256(blank.read_bytes()).hexdigest(),
        bindings=[
            {
                "sectionIndex": 0,
                "tableIndex": 0,
                "row": 0,
                "col": 0,
                "blankValueSha256": domain_value_sha256("BLANK_NAME"),
                "expectedValueSha256": domain_value_sha256("SYN_NAME"),
            },
            {
                "sectionIndex": 0,
                "tableIndex": 0,
                "row": 0,
                "col": 1,
                "blankValueSha256": domain_value_sha256("BLANK_DATE"),
                "expectedValueSha256": domain_value_sha256("SYN_DATE"),
            },
        ],
    )
    receipt_path = tmp_path / "filled-differential.json"
    receipt_sha, _receipt = _write_form_differential_asset(
        blank, output, receipt_path
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="known_template_fill",
        family="notice",
        verifier_policy_sha256s={
            "form_fill": form_verifier_policy_sha256(
                target_policy_sha256=policy["policySha256"],
                differential_receipt_asset_sha256=receipt_sha,
            )
        },
    )
    evidence = build_form_fill_domain_evidence_from_artifacts(
        requirement,
        output,
        blank,
        target_policy=policy,
        frozen_differential_receipt_path=receipt_path,
        frozen_differential_receipt_asset_sha256=receipt_sha,
        observed_terminal_state="completed",
    )
    statuses = {item["code"]: item["status"] for item in evidence["checks"]}
    assert statuses["mapping_complete"] == "passed"
    assert statuses["synthetic_values_verified"] == "passed"

    tampered_receipt_path = tmp_path / "tampered-differential.json"
    tampered_receipt_path.write_bytes(receipt_path.read_bytes() + b"\n")
    tampered = build_form_fill_domain_evidence_from_artifacts(
        requirement,
        output,
        blank,
        target_policy=policy,
        frozen_differential_receipt_path=tampered_receipt_path,
        frozen_differential_receipt_asset_sha256=receipt_sha,
        observed_terminal_state="completed",
    )
    assert tampered["status"] == "unverified"
    assert tampered["sourceEvidence"] is None

    swapped_receipt_path = tmp_path / "swapped-differential.json"
    swapped_receipt_sha, _swapped_receipt = _write_form_differential_asset(
        blank, swapped, swapped_receipt_path
    )
    swapped_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(swapped.read_bytes()).hexdigest(),
        task_kind="known_template_fill",
        family="notice",
        verifier_policy_sha256s={
            "form_fill": form_verifier_policy_sha256(
                target_policy_sha256=policy["policySha256"],
                differential_receipt_asset_sha256=swapped_receipt_sha,
            )
        },
    )
    swapped_evidence = build_form_fill_domain_evidence_from_artifacts(
        swapped_requirement,
        swapped,
        blank,
        target_policy=policy,
        frozen_differential_receipt_path=swapped_receipt_path,
        frozen_differential_receipt_asset_sha256=swapped_receipt_sha,
        observed_terminal_state="completed",
    )
    swapped_statuses = {
        item["code"]: item["status"] for item in swapped_evidence["checks"]
    }
    assert swapped_statuses["mapping_complete"] == "passed"
    assert swapped_statuses["synthetic_values_verified"] == "failed"
    assert swapped_evidence["status"] == "failed"

    stale_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(swapped.read_bytes()).hexdigest(),
        task_kind="known_template_fill",
        family="notice",
        verifier_policy_sha256s={
            "form_fill": form_verifier_policy_sha256(
                target_policy_sha256=policy["policySha256"],
                differential_receipt_asset_sha256=receipt_sha,
            )
        },
    )
    stale = build_form_fill_domain_evidence_from_artifacts(
        stale_requirement,
        swapped,
        blank,
        target_policy=policy,
        frozen_differential_receipt_path=receipt_path,
        frozen_differential_receipt_asset_sha256=receipt_sha,
        observed_terminal_state="completed",
    )
    assert stale["status"] == "unverified"
    assert stale["sourceEvidence"] is None


def test_must_abstain_adapter_detects_unrecorded_sandbox_outputs(tmp_path) -> None:
    start = tmp_path / "start.hwpx"
    start.write_bytes(b"immutable-start")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    (output_root / "unrecorded.hwpx").write_bytes(start.read_bytes())
    scenario_id = "SCN-00000000000000000001"
    receipt = _abstention_receipt(scenario_id)
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(start.read_bytes()).hexdigest(),
        task_kind="must_abstain",
        family="notice",
        verifier_policy_sha256s=_must_policy(),
    )
    evidence = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    statuses = {item["code"]: item["status"] for item in evidence["checks"]}
    assert statuses == {
        "terminal_state_allowed": "passed",
        "no_mutation": "failed",
        "decision_reason_present": "passed",
    }
    assert evidence["status"] == "failed"

    # Even a byte-identical copy that the terminal receipt records is still a
    # mutation for must-abstain; only exact-empty output sets may pass.
    recorded_receipt = _abstention_receipt(
        scenario_id,
        recorded_output=start.read_bytes(),
    )
    recorded_copy = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        recorded_receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    recorded_statuses = {
        item["code"]: item["status"] for item in recorded_copy["checks"]
    }
    assert recorded_statuses["no_mutation"] == "failed"
    assert recorded_copy["status"] == "failed"


def test_must_abstain_requires_exact_empty_and_rejects_inventory_race(
    tmp_path, monkeypatch
) -> None:
    start = tmp_path / "start.hwpx"
    start.write_bytes(b"immutable-start")
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    scenario_id = "SCN-00000000000000000001"
    receipt = _abstention_receipt(scenario_id)
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(start.read_bytes()).hexdigest(),
        task_kind="must_abstain",
        family="notice",
        verifier_policy_sha256s=_must_policy(),
    )
    empty = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    assert empty["status"] == "passed"
    assert empty["sourceEvidence"]["receiptSha256"] == receipt["receiptSha256"]
    assert empty["sourceEvidence"]["terminalReason"] == "DECISION_REQUIRED"
    assert empty["sourceEvidence"]["measuredOutputInventory"] == []
    inventory_key_id = abstention_inventory_authentication_key_id(
        ABSTENTION_INVENTORY_KEY
    )
    assert empty["sourceEvidence"]["inventoryAuthenticationKeyId"] == inventory_key_id
    assert empty["sourceEvidence"]["inventoryAuth"]["keyId"] == inventory_key_id
    assert "abstention-inventory-test-key" not in repr(empty)
    with pytest.raises(
        ValueError, match="abstention inventory authentication key is required"
    ):
        validate_domain_evidence(empty)
    wrong_key = b"wrong-abstention-inventory-key-32bytes"
    with pytest.raises(
        ValueError, match="abstention inventory authentication key mismatch"
    ):
        validate_domain_evidence(
            empty, oracle_authentication_keys={inventory_key_id: wrong_key}
        )
    assert validate_domain_evidence(
        empty,
        oracle_authentication_keys={inventory_key_id: ABSTENTION_INVENTORY_KEY},
    ) == empty

    # Rewriting a real non-empty measurement to a fabricated empty inventory
    # cannot produce authenticated evidence, even when the caller recomputes
    # every public content hash.
    measured_output = output_root / "fabricated-empty.hwpx"
    measured_output.write_bytes(start.read_bytes())
    nonempty = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    measured_output.unlink()
    fabricated_empty = copy.deepcopy(nonempty)
    fabricated_empty["sourceEvidence"]["measuredOutputInventory"] = []
    fabricated_empty["sourceEvidence"][
        "measuredOutputInventorySha256"
    ] = domain_module._sha256([])
    fabricated_empty["evidenceSha256"] = domain_evidence_sha256(fabricated_empty)
    with pytest.raises(
        ValueError, match="abstention inventory authentication failed"
    ):
        validate_domain_evidence(
            fabricated_empty,
            oracle_authentication_keys={
                inventory_key_id: ABSTENTION_INVENTORY_KEY
            },
        )

    attacker_key = b"attacker-abstention-inventory-key-32bytes"
    attacker_key_id = abstention_inventory_authentication_key_id(attacker_key)
    wrong_policy_source = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        receipt,
        inventory_authentication_key=attacker_key,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    assert wrong_policy_source["status"] == "unverified"
    with pytest.raises(
        ValueError, match="does not match frozen verifier policy"
    ):
        build_domain_evaluation_bundle(
            requirement,
            [wrong_policy_source],
            observed_terminal_state="refused",
            oracle_authentication_keys={attacker_key_id: attacker_key},
        )

    false_reason_receipt = _abstention_receipt(
        scenario_id,
        terminal_reason="NOT_AN_ABSTENTION_REASON",
    )
    false_reason = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        false_reason_receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    false_reason_statuses = {
        item["code"]: item["status"] for item in false_reason["checks"]
    }
    assert false_reason_statuses["decision_reason_present"] == "failed"
    assert false_reason["status"] == "failed"

    original_inventory = domain_module._inventory_from_dirfd
    calls = 0

    def create_between_inventory_passes(directory_fd, **kwargs):  # noqa: ANN001
        nonlocal calls
        result = original_inventory(directory_fd, **kwargs)
        if kwargs.get("prefix", "") == "" and calls == 0:
            (output_root / "hidden-race.hwpx").write_bytes(b"late-output")
        calls += 1
        return result

    monkeypatch.setattr(
        domain_module, "_inventory_from_dirfd", create_between_inventory_passes
    )
    raced = build_must_abstain_domain_evidence_from_receipt(
        requirement,
        start,
        receipt,
        inventory_authentication_key=ABSTENTION_INVENTORY_KEY,
        expected_scenario_id=scenario_id,
        sandbox_output_root=output_root,
    )
    statuses = {item["code"]: item["status"] for item in raced["checks"]}
    assert statuses["no_mutation"] == "unverified"
    assert raced["status"] == "unverified"


def test_form_adapter_uses_one_private_snapshot_across_verifiers(
    tmp_path, monkeypatch
) -> None:
    import hwpx.fill_residue as residue_module
    from hwpx.document import HwpxDocument

    blank = tmp_path / "blank.hwpx"
    output = tmp_path / "output.hwpx"

    def save(path: Path, value: str) -> None:
        document = HwpxDocument.new()
        table = document.add_table(1, 1)
        table.set_cell_text(0, 0, value)
        document.save_to_path(path)
        document.close()

    save(blank, "BLANK")
    save(output, "SYNTHETIC")
    policy = build_form_target_policy(
        blank_artifact_sha256=hashlib.sha256(blank.read_bytes()).hexdigest(),
        bindings=[
            {
                "sectionIndex": 0,
                "tableIndex": 0,
                "row": 0,
                "col": 0,
                "blankValueSha256": domain_value_sha256("BLANK"),
                "expectedValueSha256": domain_value_sha256("SYNTHETIC"),
            }
        ],
    )
    receipt_path = tmp_path / "differential.json"
    receipt_sha, _receipt = _write_form_differential_asset(
        blank, output, receipt_path
    )
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="known_template_fill",
        family="notice",
        verifier_policy_sha256s={
            "form_fill": form_verifier_policy_sha256(
                target_policy_sha256=policy["policySha256"],
                differential_receipt_asset_sha256=receipt_sha,
            )
        },
    )
    real_residue = residue_module.inspect_fill_residue

    def swap_originals(produced, blank=None):  # noqa: ANN001
        assert Path(produced) != output
        assert Path(blank) != globals_blank
        output.write_bytes(b"swapped-output")
        globals_blank.write_bytes(b"swapped-blank")
        return real_residue(produced, blank=blank)

    globals_blank = blank
    monkeypatch.setattr(residue_module, "inspect_fill_residue", swap_originals)
    evidence = build_form_fill_domain_evidence_from_artifacts(
        requirement,
        output,
        blank,
        target_policy=policy,
        frozen_differential_receipt_path=receipt_path,
        frozen_differential_receipt_asset_sha256=receipt_sha,
        observed_terminal_state="completed",
    )
    assert evidence["status"] == "passed"


def test_structural_adapter_uses_one_private_snapshot_across_measurement(
    tmp_path, monkeypatch
) -> None:
    from hwpx.document import HwpxDocument

    start = tmp_path / "start.hwpx"
    output = tmp_path / "output.hwpx"
    before = HwpxDocument.new()
    table = before.add_table(1, 2)
    table.set_cell_text(0, 0, "BASE")
    table.set_cell_text(0, 1, "ROW")
    before.save_to_path(start)
    before.close()
    after = HwpxDocument.new()
    table = after.add_table(2, 2)
    table.set_cell_text(0, 0, "BASE")
    table.set_cell_text(0, 1, "ROW")
    table.set_cell_text(1, 0, "SYNTHETIC")
    table.set_cell_text(1, 1, "VALUE")
    after.save_to_path(output)
    after.close()
    start_sha = hashlib.sha256(start.read_bytes()).hexdigest()
    row_sha = domain_row_sha256(["SYNTHETIC", "VALUE"])
    values = [domain_value_sha256("SYNTHETIC"), domain_value_sha256("VALUE")]
    requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        task_kind="structural_edit",
        family="meeting_minutes",
        verifier_policy_sha256s={
            "structural_table": structural_verifier_policy_sha256(
                expected_start_sha256=start_sha,
                expected_row_sha256=row_sha,
                expected_value_sha256s=values,
            )
        },
    )
    real_measurement = domain_module._structural_measurement
    calls = 0

    def swap_originals(path):  # noqa: ANN001
        nonlocal calls
        assert Path(path) not in {start, output}
        if calls == 0:
            start.write_bytes(b"swapped-start")
            output.write_bytes(b"swapped-output")
        calls += 1
        return real_measurement(path)

    monkeypatch.setattr(domain_module, "_structural_measurement", swap_originals)
    evidence = build_structural_table_domain_evidence_from_artifacts(
        requirement,
        start,
        output,
        expected_start_sha256=start_sha,
        expected_row_sha256=row_sha,
        expected_value_sha256s=values,
        observed_terminal_state="completed",
    )
    assert evidence["status"] == "passed"


def test_official_and_authoring_adapters_verify_only_private_snapshots(
    tmp_path, monkeypatch
) -> None:
    import importlib

    import hwpx.authoring as authoring_module
    from hwpx.document import HwpxDocument

    diff_module = importlib.import_module("hwpx.tools.doc_diff")
    lint_module = importlib.import_module("hwpx.tools.official_lint")
    style_module = importlib.import_module("hwpx.tools.style_profile")

    official = tmp_path / "official.hwpx"
    authored = tmp_path / "authored.hwpx"
    style = tmp_path / "style.hwpx"
    for path, text in (
        (official, "1. 합성 안건\n끝."),
        (authored, "합성 작성 결과"),
        (style, "합성 스타일 기준"),
    ):
        document = HwpxDocument.new()
        for paragraph in text.splitlines():
            document.add_paragraph(paragraph)
        document.save_to_path(path)
        document.close()

    official_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(official.read_bytes()).hexdigest(),
        task_kind="constrained_edit",
        family="official_document_draft_dispatch",
        verifier_policy_sha256s={
            "official_document": official_verifier_policy_sha256(
                document_type="공문"
            )
        },
    )

    def official_lint(snapshot, **kwargs):  # noqa: ANN001
        assert Path(snapshot) != official
        official.write_bytes(b"swapped-official")
        return {"pass": True, "structure_pass": True}

    def references(snapshot):  # noqa: ANN001
        assert Path(snapshot) not in {official, authored}
        return {"pass": True}

    monkeypatch.setattr(lint_module, "inspect_official_document_style", official_lint)
    monkeypatch.setattr(diff_module, "inspect_reference_consistency", references)
    official_evidence = build_official_document_domain_evidence(
        official_requirement,
        official,
        observed_terminal_state="completed",
        document_type="공문",
    )
    assert official_evidence["status"] == "passed"

    plan = {"schemaVersion": "hwpx.document_plan.v2", "preset": "default", "sections": []}
    authoring_requirement = build_domain_requirement(
        scenario_sha256=_sha("scenario"),
        artifact_sha256=hashlib.sha256(authored.read_bytes()).hexdigest(),
        task_kind="typed_authoring",
        family="notice",
        verifier_policy_sha256s={
            "authoring": authoring_verifier_policy_sha256(
                plan=plan,
                style_reference_sha256=hashlib.sha256(style.read_bytes()).hexdigest(),
            )
        },
    )

    def authoring_quality(snapshot, **kwargs):  # noqa: ANN001
        assert Path(snapshot) != authored
        authored.write_bytes(b"swapped-authored")
        style.write_bytes(b"swapped-style")
        return {"pass": True}

    def compare_styles(style_snapshot, source_snapshot):  # noqa: ANN001
        assert Path(style_snapshot) != style
        assert Path(source_snapshot) != authored
        return {"pass": True}

    monkeypatch.setattr(
        authoring_module, "inspect_document_authoring_quality", authoring_quality
    )
    monkeypatch.setattr(style_module, "compare_style_profiles", compare_styles)
    authoring_evidence = build_authoring_domain_evidence(
        authoring_requirement,
        authored,
        observed_terminal_state="completed",
        plan=plan,
        style_reference=style,
    )
    assert authoring_evidence["status"] == "passed"


def test_raw_boolean_builders_are_not_exported_for_production_runtime() -> None:
    for name in (
        "build_domain_evidence",
        "build_edit_domain_evidence",
        "build_form_fill_domain_evidence",
        "build_structural_table_domain_evidence",
        "build_must_abstain_domain_evidence",
    ):
        assert name not in domain_module.__all__
