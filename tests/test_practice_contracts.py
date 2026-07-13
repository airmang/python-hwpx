from __future__ import annotations

import hashlib
import json

import pytest

from hwpx.practice.lineage import LineageEdge, build_lineage_groups, validate_partition_closure
from hwpx.practice.registry import (
    PRIVATE_REGISTRY_SCHEMA,
    assert_redacted_payload,
    eligibility_status,
    opaque_document_id,
    redact_private_record,
    validate_private_record,
)
from hwpx.practice.scenario import PRACTICE_SCENARIO_SCHEMA, scenario_id, validate_scenario


ID_KEY = b"practice-contract-test-key-32bytes-minimum"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _document_id(label: str) -> str:
    return opaque_document_id(_digest(label), id_key=ID_KEY)


def _private_record(*, decision: str = "unreviewed", open_safety: bool = True) -> dict:
    privacy = {
        "detectorStatus": "none_detected",
        "decision": decision,
    }
    if decision != "unreviewed":
        privacy.update({"reviewedBy": "local-reviewer", "reviewedAt": "2026-07-13T00:00:00Z"})
    if decision == "approved_sanitized":
        privacy.update({"sanitizedDerivativeId": "DER-0001", "sanitizationReviewed": True})
    return {
        "schema": PRIVATE_REGISTRY_SCHEMA,
        "documentId": _document_id("source-a"),
        "source": {
            "path": "/private/source",
            "filename": "private-source.hwpx",
            "sha256": _digest("source-a"),
            "sizeBytes": 123,
        },
        "storage": {
            "authenticatedEncryption": True,
            "keyId": "local-key-1",
            "algorithm": "AES-256-GCM",
        },
        "privacy": privacy,
        "lineage": {"groupId": "LIN-0123456789ABCDEF0123"},
        "family": "form",
        "state": "blank_or_template",
        "complexity": "high",
        "suitability": "candidate_template",
        "openSafetyOk": open_safety,
    }


def test_keyed_document_id_is_stable_and_does_not_expose_source_hash() -> None:
    digest = _digest("source")
    first = opaque_document_id(digest, id_key=ID_KEY)
    assert first == opaque_document_id(digest, id_key=ID_KEY)
    assert first.startswith("HWC-")
    assert digest[:20].upper() not in first
    with pytest.raises(ValueError, match="at least 32 bytes"):
        opaque_document_id(digest, id_key=b"short")


def test_keyed_document_id_distinguishes_hidden_occurrences() -> None:
    digest = _digest("same-source")
    first = opaque_document_id(digest, id_key=ID_KEY, occurrence_key="copy-a.hwpx")
    second = opaque_document_id(digest, id_key=ID_KEY, occurrence_key="copy-b.hwpx")

    assert first != second
    assert opaque_document_id(
        digest,
        id_key=ID_KEY,
        occurrence_key="copy-a.hwpx",
    ) == first


def test_none_detected_is_not_eligibility_without_review() -> None:
    record = _private_record(decision="unreviewed")
    assert validate_private_record(record)["privacy"]["detectorStatus"] == "none_detected"
    assert eligibility_status(record) == "ineligible"

    approved = _private_record(decision="approved_local_only")
    assert eligibility_status(approved) == "normal"
    approved["privacy"].pop("reviewedBy")
    with pytest.raises(ValueError, match="reviewer provenance"):
        eligibility_status(approved)


def test_repair_required_documents_are_negative_controls_only() -> None:
    record = _private_record(decision="repair_negative", open_safety=False)
    assert eligibility_status(record) == "negative_control"


def test_private_registry_requires_authenticated_encryption() -> None:
    record = _private_record()
    record["storage"]["authenticatedEncryption"] = False
    with pytest.raises(ValueError, match="authenticated encryption"):
        validate_private_record(record)


def test_redacted_record_contains_no_private_source_coordinate() -> None:
    record = _private_record(decision="approved_local_only")
    redacted = redact_private_record(record)
    encoded = json.dumps(redacted, ensure_ascii=False)
    assert "private-source" not in encoded
    assert "/private/source" not in encoded
    assert _digest("source-a") not in encoded
    assert redacted["practiceEligibility"] == "normal"
    assert_redacted_payload(redacted, sensitive_values=["홍길동", "010-1234-5678"])


@pytest.mark.parametrize(
    "payload",
    [
        {"sourcePath": "/private/source"},
        {"sourceFilename": "secret.hwpx"},
        {"extractedText": "private body"},
        {"piiValues": ["010-1234-5678"]},
        {"outputName": "secret.hwpx"},
        {"location": "NAS:\\OpenClaw\\private.hwpx"},
    ],
)
def test_redacted_payload_rejects_raw_coordinates_and_private_fields(payload: dict) -> None:
    with pytest.raises(ValueError, match="redacted payload"):
        assert_redacted_payload(payload)


def test_redacted_payload_rejects_known_sensitive_values() -> None:
    with pytest.raises(ValueError, match="known sensitive value"):
        assert_redacted_payload(
            {"instruction": "담당자 홍길동으로 채우기"},
            sensitive_values=["홍길동"],
        )


def test_lineage_is_transitive_and_cannot_cross_a_split() -> None:
    first, second, third = (_document_id(name) for name in ("a", "b", "c"))
    edges = [
        LineageEdge(first, second, "exact_duplicate"),
        LineageEdge(second, third, "sanitized_derivative"),
    ]
    groups = build_lineage_groups([first, second, third], edges, id_key=ID_KEY)
    assert len(set(groups.values())) == 1
    validate_partition_closure({first: "practice", second: "practice", third: "practice"}, groups)
    with pytest.raises(ValueError, match="cross partitions"):
        validate_partition_closure(
            {first: "practice", second: "validation", third: "practice"},
            groups,
        )


def _scenario() -> dict:
    source_id = _document_id("scenario-source")
    base = {
        "schema": PRACTICE_SCENARIO_SCHEMA,
        "sourceDocumentId": source_id,
        "lineageGroup": "LIN-0123456789ABCDEF0123",
        "split": "holdout",
        "family": "known_form_fill",
        "taskKind": "known_template_fill",
        "difficulty": "routine",
        "instruction": "합성 담당자와 합성 날짜를 지정된 칸에 입력한다.",
        "syntheticInputs": {
            "schema": "hwpx.synthetic-dossier/v1",
            "synthetic": True,
            "fields": {"담당자": "합성-연습담당자", "날짜": "합성-일자-2099-01-01"},
        },
        "controlledMutation": {
            "schema": "hwpx.controlled-mutation/v1",
            "synthetic": True,
            "taskKind": "known_template_fill",
            "operation": "fill_known_fields",
            "target": {"kind": "declared_field_map"},
            "before": {},
            "after": {},
            "reversible": True,
        },
        "allowedWorkflow": "known_form_fill",
        "privacy": {"syntheticInputsOnly": True, "localOnly": True},
        "startArtifact": {"artifactId": "ART-0001", "sha256": _digest("artifact")},
        "budgets": {"toolCalls": 12, "attempts": 2, "repairRounds": 0, "elapsedSeconds": 120},
        "expectedTerminalState": "completed",
        "visibility": {"generatorCanReadGold": False, "runnerCanReadGold": False},
        "oracles": [
            {"kind": "form_residue", "required": True, "provenance": "deterministic"},
        ],
        "gold": {"kind": "verifier", "verifierId": "verify-form-v1"},
        "visualCompleteExpected": False,
        "provenance": {
            "generator": "test-generator",
            "evaluator": "test-evaluator",
            "core": "test-core",
            "server": "test-server",
            "skill": "test-skill",
            "toolSpecHash": "test-tool-spec",
        },
    }
    base["scenarioId"] = scenario_id(base)
    return base


def test_scenario_contract_is_deterministic_and_hides_gold() -> None:
    raw = _scenario()
    validated = validate_scenario(raw)
    assert validated["scenarioId"] == scenario_id(raw)
    assert validated["visibility"] == {
        "generatorCanReadGold": False,
        "runnerCanReadGold": False,
    }


def test_scenario_rejects_private_filename_and_holdout_gold_visibility() -> None:
    raw = _scenario()
    raw["startArtifact"]["filename"] = "private.hwpx"
    with pytest.raises(ValueError, match="redacted payload"):
        validate_scenario(raw)

    raw = _scenario()
    raw["visibility"]["generatorCanReadGold"] = True
    raw["scenarioId"] = scenario_id(raw)
    with pytest.raises(ValueError, match="holdout gold"):
        validate_scenario(raw)


def test_visual_completion_requires_real_hancom_provenance() -> None:
    raw = _scenario()
    raw["visualCompleteExpected"] = True
    raw["oracles"].append({"kind": "visual", "required": True, "provenance": "fixture"})
    raw["scenarioId"] = scenario_id(raw)
    with pytest.raises(ValueError, match="real-Hancom"):
        validate_scenario(raw)

    raw["oracles"].append(
        {"kind": "real_hancom", "required": True, "provenance": "real_hancom"}
    )
    raw["scenarioId"] = scenario_id(raw)
    assert validate_scenario(raw)["visualCompleteExpected"] is True


def test_repair_budget_is_bounded() -> None:
    raw = _scenario()
    raw["budgets"]["repairRounds"] = 4
    raw["scenarioId"] = scenario_id(raw)
    with pytest.raises(ValueError, match="cannot exceed 3"):
        validate_scenario(raw)
