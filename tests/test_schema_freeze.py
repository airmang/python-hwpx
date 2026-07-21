# SPDX-License-Identifier: Apache-2.0
"""S-091 P2 — versioned-contract schema freeze.

4.0.0 freezes the required-field set of every published versioned contract. The
freeze policy (docs/schema-freeze.md) is **additive-only**: a new field may be
added but must be Optional, so old payloads keep validating. Promoting an
existing field to required, or adding a new required field, is a breaking change
that needs a **new major + a new schema version string**.

These tests lock the current required set of each contract. If a future change
adds a required field, the minimal-valid fixture here (which carries exactly the
frozen keys) stops validating and the test fails — forcing the change to be
Optional or to bump the schema version deliberately.

Frozen contracts: ``hwpx.mutation-report/v1``, ``hwpx.document_plan.v1``/``v2``,
``hwpx.agent-batch/v1``, ``hwpx.mixed-form-plan/v1`` (public plan).
"""

from __future__ import annotations

import pytest

from hwpx.agent.model import (
    AGENT_BATCH_SCHEMA,
    AgentContractError,
    validate_agent_batch,
)
from hwpx.agent.form_plan import MIXED_FORM_PLAN_SCHEMA, validate_mixed_form_request
from hwpx.authoring import (
    DOCUMENT_PLAN_SCHEMA_VERSION,
    DOCUMENT_PLAN_V2_SCHEMA_VERSION,
    get_document_plan_schema,
)
from hwpx.mutation_report import (
    MUTATION_REPORT_SCHEMA,
    MutationReport,
    PreservationCounts,
    PreservationSummary,
    VerificationSummary,
)


# --------------------------------------------------------------------------- #
# hwpx.mutation-report/v1
# --------------------------------------------------------------------------- #
FROZEN_MUTATION_REPORT_KEYS = {
    "schemaVersion",
    "ok",
    "path",
    "requestedMode",
    "actualMode",
    "fallbackUsed",
    "changedParts",
    "preservation",
    "verification",
}


def _minimal_mutation_report() -> MutationReport:
    return MutationReport(
        requested_mode="auto",
        actual_mode="patch",
        fallback_used=False,
        changed_parts=(),
        preservation=PreservationSummary(
            untouched_part_payloads=PreservationCounts(verified=0, changed=0),
            untouched_local_zip_records=PreservationCounts(verified=0, changed=0),
            whole_package_identical=True,
        ),
        verification=VerificationSummary(
            package="passed",
            open_safety="passed",
            reopen="passed",
            visual="not_performed",
        ),
    )


def test_mutation_report_v1_top_level_keys_frozen() -> None:
    payload = _minimal_mutation_report().to_dict()

    assert set(payload) == FROZEN_MUTATION_REPORT_KEYS
    assert payload["schemaVersion"] == MUTATION_REPORT_SCHEMA == "hwpx.mutation-report/v1"


# --------------------------------------------------------------------------- #
# hwpx.document_plan.v1 / v2  (JSON-Schema contract)
# --------------------------------------------------------------------------- #
def test_document_plan_schema_required_frozen() -> None:
    schema = get_document_plan_schema()

    # Envelope: only schemaVersion + blocks are required (additive-only).
    assert schema["required"] == ["schemaVersion", "blocks"]
    # Each block requires only its `type`; bodies stay open (additionalProperties).
    assert schema["properties"]["blocks"]["items"]["required"] == ["type"]
    # The published version family is exactly v1 + v2.
    assert schema["properties"]["schemaVersion"]["enum"] == [
        DOCUMENT_PLAN_SCHEMA_VERSION,
        DOCUMENT_PLAN_V2_SCHEMA_VERSION,
    ]


# --------------------------------------------------------------------------- #
# hwpx.agent-batch/v1
# --------------------------------------------------------------------------- #
FROZEN_AGENT_BATCH_REQUIRED = {
    "schemaVersion",
    "input",
    "output",
    "commands",
    "expectedRevision",
    "idempotencyKey",
    "dryRun",
    "quality",
    "verificationRequirements",
}


def _minimal_valid_batch() -> dict[str, object]:
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": "input.hwpx"},
        "output": {"filename": "output.hwpx", "overwrite": False},
        "commands": [
            {
                "commandId": "c1",
                "op": "set",
                "path": "/section[1]/paragraph[1]",
                "properties": {"text": "x"},
            }
        ],
        "expectedRevision": None,
        "idempotencyKey": "schema-freeze-batch-1",
        "dryRun": True,
        "quality": "transparent",
        "verificationRequirements": ["package", "reopen", "openSafety", "semanticDiff"],
    }


def test_agent_batch_v1_required_fields_frozen() -> None:
    base = _minimal_valid_batch()

    # The exact frozen key set validates.
    validate_agent_batch(base)

    # Dropping any required key is rejected (missing) — none is optional.
    for key in FROZEN_AGENT_BATCH_REQUIRED:
        broken = {k: v for k, v in base.items() if k != key}
        with pytest.raises(AgentContractError) as exc:
            validate_agent_batch(broken)
        assert "missing" in str(exc.value) and key in str(exc.value)

    # A new unknown key is rejected (closed schema — additions must be planned).
    with pytest.raises(AgentContractError) as exc:
        validate_agent_batch({**base, "unexpectedField": 1})
    assert "extra" in str(exc.value)


# --------------------------------------------------------------------------- #
# hwpx.mixed-form-plan/v1 (P1-frozen public plan)
# --------------------------------------------------------------------------- #
FROZEN_MIXED_FORM_PLAN_PUBLIC_REQUIRED = {
    "schemaVersion",
    "source",
    "output",
    "expectedRevision",
    "idempotencyKey",
    "dryRun",
    "overwrite",
    "quality",
    "verificationRequirements",
    "operations",
}


def _minimal_public_plan() -> dict[str, object]:
    return {
        "schemaVersion": MIXED_FORM_PLAN_SCHEMA,
        "source": "in.hwpx",
        "output": "out.hwpx",
        "expectedRevision": None,
        "idempotencyKey": "schema-freeze-plan-1",
        "dryRun": True,
        "overwrite": True,
        "quality": "transparent",
        "verificationRequirements": ["package", "reopen", "openSafety"],
        "operations": [
            {
                "operationId": "op1",
                "target": {"kind": "nativeField", "fieldId": "240021"},
                "value": "x",
            }
        ],
    }


def test_mixed_form_plan_v1_public_required_fields_frozen() -> None:
    base = _minimal_public_plan()

    # The exact frozen key set passes structural validation (no file access here;
    # validate_mixed_form_request only checks the request envelope + operations).
    validate_mixed_form_request(base)

    # Dropping any required key is rejected. schemaVersion gates the dispatch, so
    # its removal fails at the version router; every other key fails the field set.
    for key in FROZEN_MIXED_FORM_PLAN_PUBLIC_REQUIRED:
        broken = {k: v for k, v in base.items() if k != key}
        with pytest.raises(AgentContractError) as exc:
            validate_mixed_form_request(broken)
        message = str(exc.value)
        if key == "schemaVersion":
            assert "unsupported mixed-form request schema" in message
        else:
            assert "missing" in message and key in message

    # A new unknown key is rejected (closed schema).
    with pytest.raises(AgentContractError) as exc:
        validate_mixed_form_request({**base, "unexpectedField": 1})
    assert "extra" in str(exc.value)
