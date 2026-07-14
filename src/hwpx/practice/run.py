"""Privacy-safe immutable contracts for durable practice runs.

The runner contract deliberately carries only opaque identifiers, hashes, fixed
budgets, and closed reason codes.  Free text, storage coordinates, evaluator
answers, and personal values belong in authenticated private storage, never in
this public/redacted form.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from hwpx.tools.pii import detect_pii

from .registry import SHA256_PATTERN, assert_redacted_payload
from .scenario import SCENARIO_ID_PATTERN

PRACTICE_RUN_SCHEMA = "hwpx.practice-run/v1"
PRACTICE_RUN_EVENT_SCHEMA = "hwpx.practice-run-event/v1"
PRACTICE_RUN_RECEIPT_SCHEMA = "hwpx.practice-run-receipt/v1"

RUN_ID_PATTERN = re.compile(r"^PRUN-[A-F0-9]{20}$")
EVENT_ID_PATTERN = re.compile(r"^EVT-[A-F0-9]{20}$")
OPAQUE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{3,79}$")
EVALUATOR_KEY_ID_PATTERN = re.compile(r"^EVK-[A-F0-9]{20}$")
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
TOOL_SPEC_HASH_PATTERN = re.compile(r"^(?:[a-f0-9]{16}|[a-f0-9]{64})$")
CONTENT_ADDRESSED_ID_PATTERN = re.compile(
    r"^(?:PRUN|PCMP|EVT|EVK|IDEM|OUT|VER|ART|DER|SCN|DSP|PSEL|EXP|PSBX)-"
    r"[A-Z0-9][A-Z0-9_-]{3,64}$"
)

ACTIVE_RUN_STATES = frozenset({"queued", "running", "cancelling"})
TERMINAL_RUN_STATES = frozenset(
    {
        "completed",
        "needs_review",
        "refused",
        "unverified",
        "failed",
        "cancelled",
        "budget_exhausted",
        "privacy_blocked",
        "provenance_mismatch",
        "source_write_refused",
        "incomplete",
    }
)
RUN_STATES = ACTIVE_RUN_STATES | TERMINAL_RUN_STATES
EVIDENCE_STATUSES = frozenset({"passed", "failed", "unverified", "not_run"})
EVENT_STATUSES = frozenset({"succeeded", "failed", "abstained"})

# Scenario expectations are a smaller evaluator-owned vocabulary.  They are
# intentionally not accepted as a public run field: actual cancellation,
# exhaustion, privacy, or recovery outcomes must not be rewritten as expected.
SCENARIO_EXPECTED_STATES = frozenset(
    {"completed", "needs_review", "failed", "unverified", "refused"}
)

RUN_BUDGET_FIELDS = (
    "toolCalls",
    "attempts",
    "repairRounds",
    "elapsedSeconds",
    "costMicrounits",
    "artifactBytes",
)

_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "answer",
        "answerkey",
        "body",
        "content",
        "description",
        "detail",
        "expectedanswer",
        "expectedterminalstate",
        "extractedcontent",
        "instruction",
        "lineagegroup",
        "message",
        "note",
        "prompt",
        "rawcontent",
        "rawtext",
        "sourcedocumentid",
        "split",
        "text",
        "title",
        "visibility",
    }
)
_ARTIFACT_ROLES = frozenset(
    {
        "start",
        "output",
        "semantic_diff",
        "package_receipt",
        "domain_receipt",
        "render_receipt",
        "visual_receipt",
    }
)
_PLACEHOLDER_VERSIONS = frozenset(
    {"candidate", "latest", "unknown", "unbound", "unbound-until-installed-leap"}
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], name: str
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise ValueError(
            f"{name} fields mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _require_int(value: object, name: str, *, minimum: int = 0) -> int:
    # bool is an int subclass and must not silently become a budget/usage value.
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _require_sha(value: object, name: str) -> str:
    digest = str(value or "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return digest


def assert_receipt_safe(
    value: object,
    *,
    sensitive_values: Sequence[str] = (),
) -> None:
    """Reject private coordinates/content, evaluator leakage, and detected PII.

    This is stricter than the general practice redaction helper: public durable
    run artifacts never carry free text at all.  A reason is a closed code and
    every substantive artifact is referred to by an opaque ID plus hash.
    """

    assert_redacted_payload(value, sensitive_values=sensitive_values)

    def visit(item: object, pointer: str, *, key_hint: str = "") -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = _normalized_key(key)
                if (
                    normalized in _FORBIDDEN_PUBLIC_KEYS
                    or "gold" in normalized
                    or "holdout" in normalized
                    or normalized.endswith("path")
                    or normalized.endswith("filename")
                ):
                    raise ValueError(
                        f"public practice payload contains forbidden private/evaluator field at {pointer}/{key}"
                    )
                visit(child, f"{pointer}/{key}", key_hint=normalized)
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{pointer}/{index}", key_hint=key_hint)
            return
        if isinstance(item, str):
            if item.casefold() in {"gold", "holdout"}:
                raise ValueError(
                    f"public practice payload contains evaluator partition data at {pointer}"
                )
            # Content digests are already format-checked by the surrounding
            # contract validators.  Running natural-language PII detection on
            # their random hex digits creates false resident-number matches.
            digest_value = bool(
                SHA256_PATTERN.fullmatch(item)
                or TOOL_SPEC_HASH_PATTERN.fullmatch(item)
                or re.fullmatch(r"sha256:[a-f0-9]{64}", item)
            )
            digest_key = key_hint.endswith("sha256") or key_hint.endswith("hash")
            if digest_key and digest_value:
                return
            opaque_key = key_hint.endswith("id") or key_hint.endswith("key")
            if opaque_key and CONTENT_ADDRESSED_ID_PATTERN.fullmatch(item):
                return
            if detect_pii(item):
                raise ValueError(f"public practice payload contains detected PII at {pointer}")

    visit(value, "$")


def validate_exact_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate exact core/server/skill, ToolSpec, and evaluator provenance."""

    raw = dict(_require_mapping(value, "provenance"))
    assert_receipt_safe(raw)
    _require_exact_keys(raw, {"stack", "toolSpec", "evaluator"}, "provenance")
    stack = dict(_require_mapping(raw["stack"], "provenance.stack"))
    _require_exact_keys(stack, {"core", "server", "skill"}, "provenance.stack")
    normalized_stack: dict[str, dict[str, str]] = {}
    for component in ("core", "server", "skill"):
        row = dict(_require_mapping(stack[component], f"provenance.stack.{component}"))
        _require_exact_keys(row, {"version", "sha256"}, f"provenance.stack.{component}")
        version = str(row["version"]).strip()
        if not version or version.casefold() in _PLACEHOLDER_VERSIONS:
            raise ValueError(f"provenance.stack.{component}.version must be exact")
        normalized_stack[component] = {
            "version": version,
            "sha256": _require_sha(row["sha256"], f"provenance.stack.{component}.sha256"),
        }

    tool_spec = dict(_require_mapping(raw["toolSpec"], "provenance.toolSpec"))
    _require_exact_keys(tool_spec, {"version", "sha256"}, "provenance.toolSpec")
    tool_version = str(tool_spec["version"]).strip()
    tool_hash = str(tool_spec["sha256"])
    if not tool_version or tool_version.casefold() in _PLACEHOLDER_VERSIONS:
        raise ValueError("provenance.toolSpec.version must be exact")
    if not TOOL_SPEC_HASH_PATTERN.fullmatch(tool_hash):
        raise ValueError("provenance.toolSpec.sha256 must be a 16- or 64-hex digest")

    evaluator = dict(_require_mapping(raw["evaluator"], "provenance.evaluator"))
    _require_exact_keys(
        evaluator,
        {"version", "sha256", "authenticationKeyId"},
        "provenance.evaluator",
    )
    evaluator_version = str(evaluator["version"]).strip()
    if not evaluator_version or evaluator_version.casefold() in _PLACEHOLDER_VERSIONS:
        raise ValueError("provenance.evaluator.version must be exact")
    evaluator_key_id = str(evaluator["authenticationKeyId"])
    if not EVALUATOR_KEY_ID_PATTERN.fullmatch(evaluator_key_id):
        raise ValueError("provenance.evaluator.authenticationKeyId must be exact")

    return {
        "stack": normalized_stack,
        "toolSpec": {"version": tool_version, "sha256": tool_hash},
        "evaluator": {
            "version": evaluator_version,
            "sha256": _require_sha(evaluator["sha256"], "provenance.evaluator.sha256"),
            "authenticationKeyId": evaluator_key_id,
        },
    }


def validate_run_budgets(value: Mapping[str, Any]) -> dict[str, int]:
    """Validate fixed per-run ceilings in deterministic integer units."""

    raw = dict(_require_mapping(value, "budgets"))
    _require_exact_keys(raw, set(RUN_BUDGET_FIELDS), "budgets")
    result = {
        key: _require_int(raw[key], f"budgets.{key}", minimum=0)
        for key in RUN_BUDGET_FIELDS
    }
    if result["attempts"] < 1 or result["elapsedSeconds"] < 1:
        raise ValueError("budgets require at least one attempt and one elapsed second")
    if result["repairRounds"] > 3:
        raise ValueError("budgets.repairRounds cannot exceed 3")
    return result


def _validate_usage(value: Mapping[str, Any], budgets: Mapping[str, int]) -> dict[str, int]:
    raw = dict(_require_mapping(value, "usage"))
    _require_exact_keys(raw, set(RUN_BUDGET_FIELDS), "usage")
    result = {
        key: _require_int(raw[key], f"usage.{key}", minimum=0)
        for key in RUN_BUDGET_FIELDS
    }
    exceeded = [key for key in RUN_BUDGET_FIELDS if result[key] > budgets[key]]
    if exceeded:
        raise ValueError(f"usage exceeds fixed run budgets: {sorted(exceeded)}")
    return result


def _validate_scenario_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "scenarioRef"))
    expected = {
        "scenarioId",
        "scenarioSha256",
        "runnerManifestSha256",
        "derivativeSha256",
        "startArtifactId",
        "startArtifactSha256",
    }
    _require_exact_keys(raw, expected, "scenarioRef")
    if not SCENARIO_ID_PATTERN.fullmatch(str(raw["scenarioId"])):
        raise ValueError("scenarioRef.scenarioId must be opaque")
    if not OPAQUE_ID_PATTERN.fullmatch(str(raw["startArtifactId"])):
        raise ValueError("scenarioRef.startArtifactId must be opaque")
    return {
        "scenarioId": str(raw["scenarioId"]),
        "scenarioSha256": _require_sha(raw["scenarioSha256"], "scenarioRef.scenarioSha256"),
        "runnerManifestSha256": _require_sha(
            raw["runnerManifestSha256"], "scenarioRef.runnerManifestSha256"
        ),
        "derivativeSha256": _require_sha(
            raw["derivativeSha256"], "scenarioRef.derivativeSha256"
        ),
        "startArtifactId": str(raw["startArtifactId"]),
        "startArtifactSha256": _require_sha(
            raw["startArtifactSha256"], "scenarioRef.startArtifactSha256"
        ),
    }


def _validate_dispatch(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "dispatch"))
    _require_exact_keys(raw, {"slot", "dispatchKey", "seedSha256"}, "dispatch")
    slot = _require_int(raw["slot"], "dispatch.slot")
    dispatch_key = str(raw["dispatchKey"])
    if not re.fullmatch(r"DSP-[A-F0-9]{20}", dispatch_key):
        raise ValueError("dispatch.dispatchKey must be opaque")
    return {
        "slot": slot,
        "dispatchKey": dispatch_key,
        "seedSha256": _require_sha(raw["seedSha256"], "dispatch.seedSha256"),
    }


def workflow_event_id(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("eventId", None)
    return f"EVT-{_sha256(payload)[:20].upper()}"


def _validate_event(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "workflow event"))
    expected = {
        "schema",
        "eventId",
        "sequence",
        "kind",
        "status",
        "idempotencyKey",
        "requestSha256",
        "responseSha256",
        "elapsedMilliseconds",
    }
    _require_exact_keys(raw, expected, "workflow event")
    if raw["schema"] != PRACTICE_RUN_EVENT_SCHEMA:
        raise ValueError("unsupported practice run event schema")
    if not CODE_PATTERN.fullmatch(str(raw["kind"])):
        raise ValueError("workflow event kind must be a closed snake-case code")
    if raw["status"] not in EVENT_STATUSES:
        raise ValueError("unsupported workflow event status")
    if not OPAQUE_ID_PATTERN.fullmatch(str(raw["idempotencyKey"])):
        raise ValueError("workflow event idempotencyKey must be opaque")
    _require_int(raw["sequence"], "workflow event sequence")
    _require_int(raw["elapsedMilliseconds"], "workflow event elapsedMilliseconds")
    _require_sha(raw["requestSha256"], "workflow event requestSha256")
    if raw["responseSha256"] is not None:
        _require_sha(raw["responseSha256"], "workflow event responseSha256")
    expected_id = workflow_event_id(raw)
    if not EVENT_ID_PATTERN.fullmatch(str(raw["eventId"])) or raw["eventId"] != expected_id:
        raise ValueError("workflow eventId does not match its canonical payload")
    return raw


def _validate_artifact(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "artifact"))
    _require_exact_keys(raw, {"artifactId", "role", "sha256", "bytes"}, "artifact")
    if not OPAQUE_ID_PATTERN.fullmatch(str(raw["artifactId"])):
        raise ValueError("artifactId must be opaque")
    if raw["role"] not in _ARTIFACT_ROLES:
        raise ValueError("unsupported artifact role")
    _require_sha(raw["sha256"], "artifact.sha256")
    _require_int(raw["bytes"], "artifact.bytes")
    return raw


def _validate_retained_output_bytes(
    artifacts: Sequence[Mapping[str, Any]], usage: Mapping[str, int]
) -> None:
    """Require exact accounting whenever retained output metadata exists.

    A terminal run may account attempted output bytes after cleanup without
    retaining an output artifact.  Once an output artifact is retained in the
    receipt, however, its exact inventory must be the accounting source of
    truth so missing-evaluator aggregates cannot under-report it.
    """

    outputs = [item for item in artifacts if item["role"] == "output"]
    if outputs and usage["artifactBytes"] != sum(item["bytes"] for item in outputs):
        raise ValueError(
            "usage.artifactBytes must equal retained output artifact bytes"
        )


def _validate_evidence_ref(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    raw = dict(_require_mapping(value, name))
    _require_exact_keys(raw, {"status", "receiptSha256"}, name)
    if raw["status"] not in EVIDENCE_STATUSES:
        raise ValueError(f"{name}.status is unsupported")
    if raw["receiptSha256"] is None:
        if raw["status"] in {"passed", "failed"}:
            raise ValueError(f"{name}.receiptSha256 is required for a verdict")
    else:
        _require_sha(raw["receiptSha256"], f"{name}.receiptSha256")
    return raw


def _validate_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "evidence"))
    expected = {
        "semanticDiff",
        "openSafety",
        "domainVerdicts",
        "render",
        "visual",
        "unresolvedReasonCodes",
    }
    _require_exact_keys(raw, expected, "evidence")
    semantic = _validate_evidence_ref(raw["semanticDiff"], "evidence.semanticDiff")
    open_safety = _validate_evidence_ref(raw["openSafety"], "evidence.openSafety")

    domains_value = raw["domainVerdicts"]
    if not isinstance(domains_value, list):
        raise ValueError("evidence.domainVerdicts must be a list")
    domains: list[dict[str, Any]] = []
    seen_verifiers: set[str] = set()
    for item in domains_value:
        row = dict(_require_mapping(item, "domain verdict"))
        _require_exact_keys(
            row,
            {"verifierId", "verifierSha256", "status", "receiptSha256"},
            "domain verdict",
        )
        verifier_id = str(row["verifierId"])
        if not OPAQUE_ID_PATTERN.fullmatch(verifier_id) or verifier_id in seen_verifiers:
            raise ValueError("domain verifier IDs must be opaque and unique")
        seen_verifiers.add(verifier_id)
        _require_sha(row["verifierSha256"], "domain verdict verifierSha256")
        verdict = _validate_evidence_ref(
            {"status": row["status"], "receiptSha256": row["receiptSha256"]},
            "domain verdict",
        )
        domains.append({
            "verifierId": verifier_id,
            "verifierSha256": row["verifierSha256"],
            **verdict,
        })

    render = dict(_require_mapping(raw["render"], "evidence.render"))
    _require_exact_keys(
        render,
        {"status", "receiptSha256", "renderChecked", "provenance"},
        "evidence.render",
    )
    render_ref = _validate_evidence_ref(
        {"status": render["status"], "receiptSha256": render["receiptSha256"]},
        "evidence.render",
    )
    if not isinstance(render["renderChecked"], bool):
        raise ValueError("evidence.render.renderChecked must be boolean")
    if render["provenance"] not in {"real_hancom", "fixture", "none"}:
        raise ValueError("unsupported render provenance")
    if render_ref["status"] == "passed" and not render["renderChecked"]:
        raise ValueError("passed render evidence requires renderChecked")

    visual = dict(_require_mapping(raw["visual"], "evidence.visual"))
    _require_exact_keys(
        visual,
        {"status", "receiptSha256", "allPagesChecked", "visualComplete"},
        "evidence.visual",
    )
    visual_ref = _validate_evidence_ref(
        {"status": visual["status"], "receiptSha256": visual["receiptSha256"]},
        "evidence.visual",
    )
    if not isinstance(visual["allPagesChecked"], bool) or not isinstance(
        visual["visualComplete"], bool
    ):
        raise ValueError("visual flags must be boolean")
    if visual["visualComplete"] and not (
        visual_ref["status"] == "passed"
        and visual["allPagesChecked"]
        and render_ref["status"] == "passed"
        and render["renderChecked"]
        and render["provenance"] == "real_hancom"
    ):
        raise ValueError("visual completion requires full-page real-Hancom evidence")

    unresolved = raw["unresolvedReasonCodes"]
    if not isinstance(unresolved, list) or any(
        not REASON_CODE_PATTERN.fullmatch(str(code)) for code in unresolved
    ):
        raise ValueError("unresolvedReasonCodes must contain closed reason codes")
    if unresolved != sorted(set(unresolved)):
        raise ValueError("unresolvedReasonCodes must be sorted and unique")
    return {
        "semanticDiff": semantic,
        "openSafety": open_safety,
        "domainVerdicts": domains,
        "render": {**render_ref, "renderChecked": render["renderChecked"], "provenance": render["provenance"]},
        "visual": {**visual_ref, "allPagesChecked": visual["allPagesChecked"], "visualComplete": visual["visualComplete"]},
        "unresolvedReasonCodes": list(unresolved),
    }


def _validate_privacy(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "privacy"))
    expected = {
        "localOnly",
        "syntheticInputsOnly",
        "highConfidencePiiCount",
        "privateCoordinatesExposed",
        "evaluatorDataExposed",
    }
    _require_exact_keys(raw, expected, "privacy")
    if (
        raw["localOnly"] is not True
        or raw["syntheticInputsOnly"] is not True
        or raw["privateCoordinatesExposed"] is not False
        or raw["evaluatorDataExposed"] is not False
        or _require_int(raw["highConfidencePiiCount"], "privacy.highConfidencePiiCount") != 0
    ):
        raise ValueError("practice run privacy gate must be closed and PII-free")
    return raw


def practice_run_id(value: Mapping[str, Any]) -> str:
    """Derive a stable run ID from immutable dispatch inputs only."""

    raw = dict(_require_mapping(value, "practice run"))
    identity = {
        "schema": raw.get("schema"),
        "scenarioRef": raw.get("scenarioRef"),
        "dispatch": raw.get("dispatch"),
        "provenance": raw.get("provenance"),
        "budgets": raw.get("budgets"),
    }
    assert_receipt_safe(identity)
    return f"PRUN-{_sha256(identity)[:20].upper()}"


def validate_practice_run(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete PracticeRun v1 record without private data access."""

    raw = dict(_require_mapping(value, "practice run"))
    assert_receipt_safe(raw)
    expected = {
        "schema",
        "runId",
        "scenarioRef",
        "dispatch",
        "provenance",
        "budgets",
        "state",
        "terminalReason",
        "workflowEvents",
        "artifacts",
        "evidence",
        "usage",
        "privacy",
    }
    _require_exact_keys(raw, expected, "practice run")
    if raw["schema"] != PRACTICE_RUN_SCHEMA:
        raise ValueError("unsupported PracticeRun schema")

    raw["scenarioRef"] = _validate_scenario_reference(raw["scenarioRef"])
    raw["dispatch"] = _validate_dispatch(raw["dispatch"])
    raw["provenance"] = validate_exact_provenance(raw["provenance"])
    raw["budgets"] = validate_run_budgets(raw["budgets"])
    raw["usage"] = _validate_usage(raw["usage"], raw["budgets"])
    raw["privacy"] = _validate_privacy(raw["privacy"])

    state = str(raw["state"])
    if state not in RUN_STATES:
        raise ValueError("unsupported actual run state")
    reason = raw["terminalReason"]
    if state in TERMINAL_RUN_STATES:
        if not isinstance(reason, str) or not REASON_CODE_PATTERN.fullmatch(reason):
            raise ValueError("terminalReason is required iff the run is terminal")
    elif reason is not None:
        raise ValueError("terminalReason is required iff the run is terminal")

    events_value = raw["workflowEvents"]
    if not isinstance(events_value, list):
        raise ValueError("workflowEvents must be a list")
    events = [_validate_event(item) for item in events_value]
    if [event["sequence"] for event in events] != list(range(len(events))):
        raise ValueError("workflow event sequence must be contiguous and ordered")
    if len({event["eventId"] for event in events}) != len(events):
        raise ValueError("workflow event IDs must be unique")
    raw["workflowEvents"] = events

    artifacts_value = raw["artifacts"]
    if not isinstance(artifacts_value, list):
        raise ValueError("artifacts must be a list")
    artifacts = [_validate_artifact(item) for item in artifacts_value]
    if len({item["artifactId"] for item in artifacts}) != len(artifacts):
        raise ValueError("artifact IDs must be unique")
    raw["artifacts"] = artifacts
    _validate_retained_output_bytes(raw["artifacts"], raw["usage"])
    raw["evidence"] = _validate_evidence(raw["evidence"])

    if state == "completed" and not (
        raw["evidence"]["openSafety"]["status"] == "passed"
        and raw["evidence"]["domainVerdicts"]
        and all(item["status"] == "passed" for item in raw["evidence"]["domainVerdicts"])
    ):
        raise ValueError("completed runs require passed open-safety and domain evidence")

    expected_id = practice_run_id(raw)
    supplied_id = str(raw["runId"])
    if not RUN_ID_PATTERN.fullmatch(supplied_id) or supplied_id != expected_id:
        raise ValueError("runId does not match immutable dispatch inputs")
    return raw


def _receipt_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("receiptSha256", None)
    return _sha256(payload)


def redact_run_receipt(
    value: Mapping[str, Any],
    *,
    sensitive_values: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a deterministic, content-addressed terminal receipt."""

    run = validate_practice_run(value)
    if run["state"] not in TERMINAL_RUN_STATES:
        raise ValueError("a terminal receipt cannot be created for an active run")
    receipt = {
        "schema": PRACTICE_RUN_RECEIPT_SCHEMA,
        "runId": run["runId"],
        "scenarioId": run["scenarioRef"]["scenarioId"],
        "state": run["state"],
        "terminalReason": run["terminalReason"],
        "provenance": run["provenance"],
        "budgets": run["budgets"],
        "usage": run["usage"],
        "workflowEvents": run["workflowEvents"],
        "artifacts": run["artifacts"],
        "evidence": run["evidence"],
        "privacy": run["privacy"],
    }
    assert_receipt_safe(receipt, sensitive_values=sensitive_values)
    receipt["receiptSha256"] = _receipt_sha256(receipt)
    return validate_run_receipt(receipt, sensitive_values=sensitive_values)


def validate_run_receipt(
    value: Mapping[str, Any],
    *,
    sensitive_values: Sequence[str] = (),
) -> dict[str, Any]:
    """Validate a redacted terminal receipt and its content address."""

    raw = dict(_require_mapping(value, "run receipt"))
    assert_receipt_safe(raw, sensitive_values=sensitive_values)
    expected = {
        "schema",
        "receiptSha256",
        "runId",
        "scenarioId",
        "state",
        "terminalReason",
        "provenance",
        "budgets",
        "usage",
        "workflowEvents",
        "artifacts",
        "evidence",
        "privacy",
    }
    _require_exact_keys(raw, expected, "run receipt")
    if raw["schema"] != PRACTICE_RUN_RECEIPT_SCHEMA:
        raise ValueError("unsupported practice run receipt schema")
    if not RUN_ID_PATTERN.fullmatch(str(raw["runId"])):
        raise ValueError("receipt runId must be opaque")
    if not SCENARIO_ID_PATTERN.fullmatch(str(raw["scenarioId"])):
        raise ValueError("receipt scenarioId must be opaque")
    if raw["state"] not in TERMINAL_RUN_STATES:
        raise ValueError("run receipt state must be terminal")
    if not REASON_CODE_PATTERN.fullmatch(str(raw["terminalReason"])):
        raise ValueError("run receipt terminalReason must be a closed code")
    raw["provenance"] = validate_exact_provenance(raw["provenance"])
    raw["budgets"] = validate_run_budgets(raw["budgets"])
    raw["usage"] = _validate_usage(raw["usage"], raw["budgets"])
    raw["privacy"] = _validate_privacy(raw["privacy"])
    if not isinstance(raw["workflowEvents"], list):
        raise ValueError("receipt workflowEvents must be a list")
    raw["workflowEvents"] = [_validate_event(item) for item in raw["workflowEvents"]]
    if [event["sequence"] for event in raw["workflowEvents"]] != list(
        range(len(raw["workflowEvents"]))
    ):
        raise ValueError("receipt event sequence must be contiguous and ordered")
    if len({item["eventId"] for item in raw["workflowEvents"]}) != len(
        raw["workflowEvents"]
    ):
        raise ValueError("receipt event IDs must be unique")
    if not isinstance(raw["artifacts"], list):
        raise ValueError("receipt artifacts must be a list")
    raw["artifacts"] = [_validate_artifact(item) for item in raw["artifacts"]]
    if len({item["artifactId"] for item in raw["artifacts"]}) != len(raw["artifacts"]):
        raise ValueError("receipt artifact IDs must be unique")
    _validate_retained_output_bytes(raw["artifacts"], raw["usage"])
    raw["evidence"] = _validate_evidence(raw["evidence"])
    if raw["state"] == "completed" and not (
        raw["evidence"]["openSafety"]["status"] == "passed"
        and raw["evidence"]["domainVerdicts"]
        and all(item["status"] == "passed" for item in raw["evidence"]["domainVerdicts"])
    ):
        raise ValueError("completed receipts require passed open-safety and domain evidence")
    supplied = str(raw["receiptSha256"])
    if not SHA256_PATTERN.fullmatch(supplied) or supplied != _receipt_sha256(raw):
        raise ValueError("receiptSha256 does not match the canonical receipt")
    return raw


__all__ = [
    "ACTIVE_RUN_STATES",
    "PRACTICE_RUN_EVENT_SCHEMA",
    "PRACTICE_RUN_RECEIPT_SCHEMA",
    "PRACTICE_RUN_SCHEMA",
    "RUN_BUDGET_FIELDS",
    "RUN_STATES",
    "SCENARIO_EXPECTED_STATES",
    "TERMINAL_RUN_STATES",
    "assert_receipt_safe",
    "practice_run_id",
    "redact_run_receipt",
    "validate_exact_provenance",
    "validate_practice_run",
    "validate_run_budgets",
    "validate_run_receipt",
    "workflow_event_id",
]
