"""Independent, fail-closed evaluator ladder for durable practice runs.

The evaluator reads submitted artifacts and frozen verifier policy, but its
public receipts contain only opaque identifiers, counts, closed reason codes,
and content digests.  Package/open-safety is always evaluated before semantic
or domain evidence.  A missing or failed mandatory layer can therefore never
be averaged into a successful result.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

from hwpx.opc.security import (
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    HwpxSecurityError,
    guard_zip_file,
)
from hwpx.tools.doc_diff import doc_diff
from hwpx.tools.package_validator import (
    validate_editor_open_safety,
    validate_package,
)

from .campaign import CAMPAIGN_ID_PATTERN
from .registry import SHA256_PATTERN
from .run import (
    EVENT_ID_PATTERN,
    OPAQUE_ID_PATTERN,
    RUN_ID_PATTERN,
    TERMINAL_RUN_STATES,
    assert_receipt_safe,
    validate_run_receipt,
)
from .scenario import SCENARIO_ID_PATTERN

EVALUATOR_POLICY_VERSION = "practice-evaluator/v1"
EVALUATION_POLICY_SCHEMA = "hwpx.practice-evaluation-policy/v1"
EVALUATOR_AUTH_SCHEMA = "hwpx.practice-evaluator-auth/v1"
WORKFLOW_REVISION_RECEIPT_SCHEMA = "hwpx.practice-workflow-revision-receipt/v1"
IDEMPOTENCY_REPLAY_RECEIPT_SCHEMA = "hwpx.practice-idempotency-replay-receipt/v1"
EVALUATOR_LAYER_SCHEMA = "hwpx.practice-evaluator-layer/v1"
EVALUATOR_RESULT_SCHEMA = "hwpx.practice-evaluator-result/v1"
PACKAGE_POLICY_SCHEMA = "hwpx.practice-package-policy/v1"
SEMANTIC_POLICY_SCHEMA = "hwpx.practice-semantic-policy/v1"
SEMANTIC_POLICY_PROJECTION_SCHEMA = (
    "hwpx.practice-semantic-policy-projection/v1"
)

CHECK_STATUSES = frozenset({"passed", "failed", "unverified", "not_run"})
LAYER_STATUSES = frozenset({"passed", "failed", "unverified"})
LAYER_ORDER = (
    "package",
    "semantic",
    "domain",
    "real_hancom",
    "visual",
    "human_review",
)
MANDATORY_LAYERS = LAYER_ORDER[:3]
MAX_EVALUATOR_ARCHIVE_BYTES = MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
MAX_EVALUATOR_RESULT_BYTES = 8 * 1024 * 1024
EVALUATOR_KEY_ID_PATTERN = re.compile(r"^EVK-[A-F0-9]{20}$")

PACKAGE_BASE_CHECK_ORDER = (
    "INPUT_AVAILABLE",
    "ZIP_RESOURCE_GUARDS",
    "PACKAGE_VALIDATION",
    "REOPEN",
    "EDITOR_OPEN_SAFETY",
)
SEMANTIC_BASE_CHECK_ORDER = (
    "PACKAGE_PREREQUISITE",
    "FORBIDDEN_DRIFT",
    "BYTE_PRESERVATION",
)
_FIXED_LAYER_CHECKS = {
    "domain": ("DOMAIN_VERIFIER",),
    "real_hancom": ("REAL_HANCOM_ORACLE",),
    "visual": ("VISUAL_ORACLE",),
    "human_review": ("HUMAN_REVIEW",),
}

# This is intentionally closed.  Domain implementations bind their private,
# family-specific details behind DOMAIN_VERIFIER and its evidence digest.
CHECK_CODES = frozenset(
    {
        "INPUT_AVAILABLE",
        "ZIP_RESOURCE_GUARDS",
        "PACKAGE_VALIDATION",
        "REOPEN",
        "EDITOR_OPEN_SAFETY",
        "EXPECTED_ARTIFACT_HASH",
        "PACKAGE_PREREQUISITE",
        "SEMANTIC_DIFF",
        "FORBIDDEN_DRIFT",
        "BYTE_PRESERVATION",
        "REVISION",
        "IDEMPOTENCY",
        "DOMAIN_VERIFIER",
        "REAL_HANCOM_ORACLE",
        "VISUAL_ORACLE",
        "HUMAN_REVIEW",
    }
)

_CHECK_KEYS = frozenset({"code", "status", "evidenceSha256"})
_LAYER_KEYS = frozenset(
    {
        "schema",
        "layer",
        "status",
        "reasonCodes",
        "artifact",
        "inputArtifact",
        "checks",
        "layerReceiptSha256",
    }
)
_SCENARIO_REF_KEYS = frozenset(
    {
        "scenarioId",
        "scenarioSha256",
        "runnerManifestSha256",
        "derivativeSha256",
        "startArtifactId",
        "startArtifactSha256",
    }
)
_CAMPAIGN_REF_KEYS = frozenset(
    {"campaignId", "manifestSha256", "slot", "family", "difficulty"}
)
_RESULT_KEYS = frozenset(
    {
        "schema",
        "evaluatorVersion",
        "runId",
        "campaignRef",
        "scenarioRef",
        "terminalState",
        "terminalReceiptSha256",
        "overallStatus",
        "eligibleForSuccess",
        "evaluationPolicySha256",
        "evaluatorCodeSha256",
        "requiredLaterLayers",
        "domainVerdict",
        "packagePolicy",
        "semanticPolicy",
        "semanticEvidence",
        "domainBundle",
        "domainProjection",
        "layerStatuses",
        "criticalFailureCount",
        "missingEvidenceCount",
        "layers",
        "evaluatorResultSha256",
        "auth",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _payload_digest(value: Mapping[str, Any], hash_key: str) -> str:
    payload = dict(value)
    payload.pop(hash_key, None)
    return _digest(payload)


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], name: str
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise ValueError(
            f"{name} fields mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _require_sha(value: object, name: str) -> str:
    digest = str(value or "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return digest


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _authentication_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("evaluator authentication key must contain at least 32 bytes")
    return value


def _authentication_key_id(key: bytes) -> str:
    return f"EVK-{hashlib.sha256(key).hexdigest()[:20].upper()}"


def evaluator_authentication_key_id(authentication_key: bytes) -> str:
    """Return the closed identifier for an evaluator-owned authentication key."""

    return _authentication_key_id(_authentication_key(authentication_key))


def current_evaluator_code_sha256() -> str:
    """Hash the canonical installed practice evaluator component set."""

    root = Path(__file__).resolve(strict=True).parent
    digest = hashlib.sha256()
    for name in sorted(
        ("run.py", "campaign.py", "evaluator.py", "domain.py", "aggregate.py")
    ):
        target = root / name
        metadata = target.lstat()
        if target.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("evaluator component is not a strict regular file")
        payload = target.read_bytes()
        if len(payload) > 256 * 1024 * 1024:
            raise ValueError("evaluator component exceeds attestation limit")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _guard_result_shape(value: object) -> None:
    nodes = 0
    scalar_bytes = 0

    def visit(item: object, depth: int) -> None:
        nonlocal nodes, scalar_bytes
        nodes += 1
        if nodes > 100_000 or depth > 64:
            raise ValueError("evaluation result exceeds structural limits")
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key)
                if len(key_text) > 128:
                    raise ValueError("evaluation result key exceeds size limit")
                scalar_bytes += len(key_text.encode("utf-8"))
                visit(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 4096:
                raise ValueError("evaluation result string exceeds size limit")
            scalar_bytes += len(item.encode("utf-8"))
        elif isinstance(item, int) and not isinstance(item, bool):
            if item.bit_length() > 4096:
                raise ValueError("evaluation result integer exceeds size limit")
            scalar_bytes += max(1, (item.bit_length() + 2) // 3)
        elif item is not None and not isinstance(item, (bool, float)):
            raise ValueError("evaluation result contains an unsupported value")
        if scalar_bytes > MAX_EVALUATOR_RESULT_BYTES:
            raise ValueError("evaluation result exceeds unauthenticated size limit")

    visit(value, 0)


def _check(code: str, status: str, evidence: Mapping[str, Any]) -> dict[str, str]:
    if code not in CHECK_CODES:
        raise ValueError(f"unsupported evaluator check code: {code}")
    if status not in CHECK_STATUSES:
        raise ValueError(f"unsupported evaluator check status: {status}")
    # The evidence body remains evaluator-private.  Only a stable binding is
    # emitted, preventing document text, filenames, or exception messages from
    # escaping into durable/public results.
    return {"code": code, "status": status, "evidenceSha256": _digest(evidence)}


def make_check_receipt(
    code: str, status: str, evidence: Mapping[str, Any]
) -> dict[str, str]:
    """Bind private check evidence to a closed public check receipt."""

    if not isinstance(evidence, Mapping):
        raise ValueError("evaluator check evidence must be an object")
    return _check(code, status, evidence)


def _not_run(code: str, prerequisite: str) -> dict[str, str]:
    return _check(code, "not_run", {"prerequisite": prerequisite})


def build_package_policy(*, expected_sha256: str | None = None) -> dict[str, Any]:
    """Freeze whether the package artifact hash is a mandatory evaluator gate."""

    policy = {
        "schema": PACKAGE_POLICY_SCHEMA,
        "expectedArtifactHash": {
            "required": expected_sha256 is not None,
            "sha256": (
                _require_sha(expected_sha256, "expected_sha256")
                if expected_sha256 is not None
                else None
            ),
        },
    }
    assert_receipt_safe(policy)
    return policy


def _validate_package_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("package policy must be an object")
    raw = dict(value)
    _require_exact_keys(raw, {"schema", "expectedArtifactHash"}, "package policy")
    if raw.get("schema") != PACKAGE_POLICY_SCHEMA:
        raise ValueError("unsupported package policy schema")
    expected = raw.get("expectedArtifactHash")
    if not isinstance(expected, Mapping):
        raise ValueError("expectedArtifactHash must be an object")
    expected = dict(expected)
    _require_exact_keys(expected, {"required", "sha256"}, "expectedArtifactHash")
    if not isinstance(expected["required"], bool):
        raise ValueError("expectedArtifactHash.required must be boolean")
    digest = expected["sha256"]
    if digest is not None:
        digest = _require_sha(digest, "expectedArtifactHash.sha256")
    if expected["required"] != (digest is not None):
        raise ValueError("expected artifact hash requirement and sha256 disagree")
    result = {
        "schema": PACKAGE_POLICY_SCHEMA,
        "expectedArtifactHash": {
            "required": expected["required"],
            "sha256": digest,
        },
    }
    assert_receipt_safe(result)
    return result


def _package_check_codes(policy: Mapping[str, Any]) -> tuple[str, ...]:
    normalized = _validate_package_policy(policy)
    if normalized["expectedArtifactHash"]["required"]:
        return PACKAGE_BASE_CHECK_ORDER + ("EXPECTED_ARTIFACT_HASH",)
    return PACKAGE_BASE_CHECK_ORDER


def _semantic_check_codes(policy: Mapping[str, Any]) -> tuple[str, ...]:
    normalized = _normalize_semantic_policy_projection(policy)
    codes = ["PACKAGE_PREREQUISITE"]
    if (
        normalized["expectedDiff"]["required"]
        or normalized["expectedDiff"]["sha256"] is not None
    ):
        codes.append("SEMANTIC_DIFF")
    codes.extend(("FORBIDDEN_DRIFT", "BYTE_PRESERVATION"))
    if normalized["revision"]["required"]:
        codes.append("REVISION")
    if normalized["idempotency"]["required"]:
        codes.append("IDEMPOTENCY")
    return tuple(codes)


def semantic_policy_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    """Remove ZIP member names while binding their exact sorted sets."""

    policy = _validate_semantic_policy(value)
    projection = {
        "schema": SEMANTIC_POLICY_PROJECTION_SCHEMA,
        "expectedDiff": policy["expectedDiff"],
        "allowedChangedMembers": {
            "count": len(policy["allowedChangedMembers"]),
            "setSha256": _digest(policy["allowedChangedMembers"]),
        },
        "promisedUntouchedMembers": {
            "count": len(policy["promisedUntouchedMembers"]),
            "setSha256": _digest(policy["promisedUntouchedMembers"]),
        },
        "revision": policy["revision"],
        "idempotency": policy["idempotency"],
        "semanticPolicySha256": _digest(policy),
    }
    assert_receipt_safe(projection)
    return projection


def _validate_semantic_policy_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("semantic policy projection must be an object")
    raw = dict(value)
    _require_exact_keys(
        raw,
        {
            "schema",
            "expectedDiff",
            "allowedChangedMembers",
            "promisedUntouchedMembers",
            "revision",
            "idempotency",
            "semanticPolicySha256",
        },
        "semantic policy projection",
    )
    if raw.get("schema") != SEMANTIC_POLICY_PROJECTION_SCHEMA:
        raise ValueError("unsupported semantic policy projection schema")
    expected = raw.get("expectedDiff")
    if not isinstance(expected, Mapping):
        raise ValueError("semantic policy projection expectedDiff must be an object")
    expected = dict(expected)
    _require_exact_keys(expected, {"required", "sha256"}, "expectedDiff")
    if not isinstance(expected["required"], bool):
        raise ValueError("expectedDiff.required must be boolean")
    expected_sha = expected["sha256"]
    if expected_sha is not None:
        expected_sha = _require_sha(expected_sha, "expectedDiff.sha256")
    if expected["required"] and expected_sha is None:
        raise ValueError("required semantic diff needs an expected sha256")
    member_sets: dict[str, dict[str, Any]] = {}
    for key in ("allowedChangedMembers", "promisedUntouchedMembers"):
        row = raw.get(key)
        if not isinstance(row, Mapping):
            raise ValueError(f"{key} projection must be an object")
        row = dict(row)
        _require_exact_keys(row, {"count", "setSha256"}, f"{key} projection")
        member_sets[key] = {
            "count": _require_nonnegative_int(row["count"], f"{key}.count"),
            "setSha256": _require_sha(row["setSha256"], f"{key}.setSha256"),
        }
    revision = raw.get("revision")
    idempotency = raw.get("idempotency")
    if not isinstance(revision, Mapping) or not isinstance(idempotency, Mapping):
        raise ValueError("semantic projection revision/idempotency must be objects")
    revision = dict(revision)
    idempotency = dict(idempotency)
    _require_exact_keys(
        revision, {"required", "expectedBefore", "expectedAfter"}, "revision"
    )
    _require_exact_keys(
        idempotency, {"required", "expectedMutationCount"}, "idempotency"
    )
    if not isinstance(revision["required"], bool) or not isinstance(
        idempotency["required"], bool
    ):
        raise ValueError("semantic projection required flags must be boolean")
    for key in ("expectedBefore", "expectedAfter"):
        if revision[key] is not None:
            revision[key] = _require_nonnegative_int(revision[key], f"revision.{key}")
    if revision["required"] and (
        revision["expectedBefore"] is None or revision["expectedAfter"] is None
    ):
        raise ValueError("required revision projection is incomplete")
    if idempotency["expectedMutationCount"] is not None:
        idempotency["expectedMutationCount"] = _require_nonnegative_int(
            idempotency["expectedMutationCount"],
            "idempotency.expectedMutationCount",
        )
    if idempotency["required"] and idempotency["expectedMutationCount"] is None:
        raise ValueError("required idempotency projection is incomplete")
    result = {
        "schema": SEMANTIC_POLICY_PROJECTION_SCHEMA,
        "expectedDiff": {"required": expected["required"], "sha256": expected_sha},
        **member_sets,
        "revision": revision,
        "idempotency": idempotency,
        "semanticPolicySha256": _require_sha(
            raw["semanticPolicySha256"], "semanticPolicySha256"
        ),
    }
    assert_receipt_safe(result)
    return result


def _normalize_semantic_policy_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("schema") == SEMANTIC_POLICY_SCHEMA:
        return semantic_policy_projection(value)
    return _validate_semantic_policy_projection(value)


def evaluation_policy_sha256(
    package_policy: Mapping[str, Any],
    semantic_policy: Mapping[str, Any],
    domain_bundle: Mapping[str, Any],
    required_later_layers: Sequence[str] = (),
    *,
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> str:
    """Hash frozen evaluator policy without output-specific domain bindings."""

    from .domain import (
        domain_requirement_policy_projection,
        validate_domain_evaluation_bundle,
    )

    package = _validate_package_policy(package_policy)
    semantic = _normalize_semantic_policy_projection(semantic_policy)
    bundle = validate_domain_evaluation_bundle(
        domain_bundle,
        oracle_authentication_keys=domain_oracle_authentication_keys,
    )
    required_later = _validate_required_later_layers(required_later_layers)
    domain_policy = domain_requirement_policy_projection(bundle["requirement"])
    projection = {
        "schema": EVALUATION_POLICY_SCHEMA,
        "packagePolicy": package,
        "semanticPolicy": semantic,
        "domainPolicy": domain_policy,
        "requiredLaterLayers": list(required_later),
    }
    assert_receipt_safe(projection)
    return _digest(projection)


def _validate_required_later_layers(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError("requiredLaterLayers must be a sequence")
    required = tuple(str(item) for item in value)
    if required:
        raise ValueError(
            "requiredLaterLayers are unsupported without authenticated oracle receipts"
        )
    return ()


def _validate_layer_check_contract(
    layer: str,
    actual_codes: Sequence[str],
    required_check_codes: Sequence[str] | None,
) -> tuple[str, ...]:
    if layer in {"package", "semantic"}:
        if required_check_codes is None:
            raise ValueError(f"{layer} layer requires frozen check coverage")
        required = tuple(str(code) for code in required_check_codes)
        if layer == "package" and required not in {
            PACKAGE_BASE_CHECK_ORDER,
            PACKAGE_BASE_CHECK_ORDER + ("EXPECTED_ARTIFACT_HASH",),
        }:
            raise ValueError("package layer check contract is invalid")
        if layer == "semantic":
            allowed_order = (
                "PACKAGE_PREREQUISITE",
                "SEMANTIC_DIFF",
                "FORBIDDEN_DRIFT",
                "BYTE_PRESERVATION",
                "REVISION",
                "IDEMPOTENCY",
            )
            if (
                not all(code in allowed_order for code in required)
                or tuple(code for code in allowed_order if code in required) != required
                or not set(SEMANTIC_BASE_CHECK_ORDER).issubset(required)
            ):
                raise ValueError("semantic layer check contract is invalid")
    else:
        fixed = _FIXED_LAYER_CHECKS[layer]
        required = (
            fixed
            if required_check_codes is None
            else tuple(required_check_codes)
        )
        if required != fixed:
            raise ValueError(f"{layer} layer check contract is invalid")
    if tuple(actual_codes) != required:
        raise ValueError(
            f"{layer} layer check coverage/order mismatch: "
            f"expected {list(required)}, got {list(actual_codes)}"
        )
    return required


def make_layer_receipt(
    layer: str,
    checks: Sequence[Mapping[str, Any]],
    *,
    artifact_sha256: str | None = None,
    artifact_size_bytes: int | None = None,
    input_artifact_sha256: str | None = None,
    input_artifact_size_bytes: int | None = None,
    required_check_codes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create a closed, content-addressed, privacy-safe evaluator layer receipt."""

    if layer not in LAYER_ORDER:
        raise ValueError(f"unsupported evaluator layer: {layer}")
    normalized_checks: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, value in enumerate(checks):
        if not isinstance(value, Mapping):
            raise ValueError(f"checks[{index}] must be an object")
        row = dict(value)
        _require_exact_keys(row, _CHECK_KEYS, f"checks[{index}]")
        code = str(row["code"])
        status = str(row["status"])
        if code not in CHECK_CODES:
            raise ValueError(f"unsupported evaluator check code: {code}")
        if code in seen:
            raise ValueError(f"duplicate evaluator check code: {code}")
        if status not in CHECK_STATUSES:
            raise ValueError(f"unsupported evaluator check status: {status}")
        seen.add(code)
        normalized_checks.append(
            {
                "code": code,
                "status": status,
                "evidenceSha256": _require_sha(
                    row["evidenceSha256"], f"checks[{index}].evidenceSha256"
                ),
            }
        )
    if not normalized_checks:
        raise ValueError("an evaluator layer requires at least one check")
    _validate_layer_check_contract(
        layer,
        [row["code"] for row in normalized_checks],
        required_check_codes,
    )

    statuses = {row["status"] for row in normalized_checks}
    if "failed" in statuses:
        layer_status = "failed"
    elif statuses != {"passed"}:
        layer_status = "unverified"
    else:
        layer_status = "passed"

    if (artifact_sha256 is None) != (artifact_size_bytes is None):
        raise ValueError("artifact sha256 and size must be supplied together")
    artifact: dict[str, Any] | None = None
    if artifact_sha256 is not None:
        artifact = {
            "sha256": _require_sha(artifact_sha256, "artifact.sha256"),
            "sizeBytes": _require_nonnegative_int(
                artifact_size_bytes, "artifact.sizeBytes"
            ),
        }
    if (input_artifact_sha256 is None) != (input_artifact_size_bytes is None):
        raise ValueError("input artifact sha256 and size must be supplied together")
    input_artifact: dict[str, Any] | None = None
    if input_artifact_sha256 is not None:
        input_artifact = {
            "sha256": _require_sha(
                input_artifact_sha256, "inputArtifact.sha256"
            ),
            "sizeBytes": _require_nonnegative_int(
                input_artifact_size_bytes, "inputArtifact.sizeBytes"
            ),
        }

    receipt: dict[str, Any] = {
        "schema": EVALUATOR_LAYER_SCHEMA,
        "layer": layer,
        "status": layer_status,
        "reasonCodes": [
            row["code"] for row in normalized_checks if row["status"] != "passed"
        ],
        "artifact": artifact,
        "inputArtifact": input_artifact,
        "checks": normalized_checks,
    }
    receipt["layerReceiptSha256"] = _payload_digest(
        receipt, "layerReceiptSha256"
    )
    assert_receipt_safe(receipt)
    return receipt


def validate_layer_receipt(
    value: Mapping[str, Any],
    *,
    expected_layer: str | None = None,
    required_check_codes: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate an evaluator layer without trusting its supplied digest/status."""

    if not isinstance(value, Mapping):
        raise ValueError("evaluator layer receipt must be an object")
    raw = dict(value)
    _require_exact_keys(raw, _LAYER_KEYS, "evaluator layer receipt")
    if raw.get("schema") != EVALUATOR_LAYER_SCHEMA:
        raise ValueError("unsupported evaluator layer schema")
    layer = str(raw.get("layer"))
    if expected_layer is not None and layer != expected_layer:
        raise ValueError(
            f"evaluator layer order mismatch: expected {expected_layer}, got {layer}"
        )
    rebuilt = make_layer_receipt(
        layer,
        raw.get("checks") if isinstance(raw.get("checks"), Sequence) else (),
        artifact_sha256=(
            raw["artifact"].get("sha256")
            if isinstance(raw.get("artifact"), Mapping)
            else None
        ),
        artifact_size_bytes=(
            raw["artifact"].get("sizeBytes")
            if isinstance(raw.get("artifact"), Mapping)
            else None
        ),
        input_artifact_sha256=(
            raw["inputArtifact"].get("sha256")
            if isinstance(raw.get("inputArtifact"), Mapping)
            else None
        ),
        input_artifact_size_bytes=(
            raw["inputArtifact"].get("sizeBytes")
            if isinstance(raw.get("inputArtifact"), Mapping)
            else None
        ),
        required_check_codes=required_check_codes,
    )
    if rebuilt != raw:
        raise ValueError("evaluator layer receipt content/hash mismatch")
    return rebuilt


def _source_size(source: str | Path | bytes) -> int:
    if isinstance(source, bytes):
        return len(source)
    return Path(source).stat().st_size


def _source_sha256(source: str | Path | bytes) -> str:
    if isinstance(source, bytes):
        return hashlib.sha256(source).hexdigest()
    hasher = hashlib.sha256()
    with Path(source).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _open_zip(source: str | Path | bytes) -> ZipFile:
    if isinstance(source, bytes):
        return ZipFile(io.BytesIO(source), "r")
    return ZipFile(source, "r")


def _guard_evaluator_zip(archive: ZipFile, *, archive_size: int) -> None:
    if archive_size > MAX_EVALUATOR_ARCHIVE_BYTES:
        raise HwpxSecurityError("practice artifact exceeds evaluator archive limit")
    guard_zip_file(archive)
    infos = [info for info in archive.infolist() if not info.is_dir()]
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise HwpxSecurityError("practice artifact contains duplicate ZIP members")
    if any(info.flag_bits & 0x1 for info in infos):
        raise HwpxSecurityError("practice artifact contains encrypted ZIP members")


def evaluate_package_layer(
    output_source: str | Path | bytes,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Evaluate ZIP limits, package validity, reopen, and editor-open safety.

    ZIP metadata guards execute before artifact hashing, member reads, document
    reopen, or semantic evaluation.  Errors are converted to closed evidence;
    exception strings and paths never enter the receipt.
    """

    package_policy = build_package_policy(expected_sha256=expected_sha256)
    required_check_codes = _package_check_codes(package_policy)
    expected_artifact_sha = package_policy["expectedArtifactHash"]["sha256"]
    checks: list[dict[str, str]] = []
    artifact_sha: str | None = None
    artifact_size: int | None = None
    try:
        output_payload = _read_source_once(output_source)
        artifact_size = len(output_payload)
    except HwpxSecurityError:
        checks.append(_check("INPUT_AVAILABLE", "passed", {"available": True}))
        checks.append(
            _check("ZIP_RESOURCE_GUARDS", "failed", {"guardPassed": False})
        )
        checks.extend(
            _not_run(code, "ZIP_RESOURCE_GUARDS")
            for code in ("PACKAGE_VALIDATION", "REOPEN", "EDITOR_OPEN_SAFETY")
        )
        if expected_artifact_sha is not None:
            checks.append(_not_run("EXPECTED_ARTIFACT_HASH", "ZIP_RESOURCE_GUARDS"))
        return make_layer_receipt(
            "package", checks, required_check_codes=required_check_codes
        )
    except (OSError, TypeError, ValueError):
        checks.append(_check("INPUT_AVAILABLE", "unverified", {"available": False}))
        checks.extend(
            _not_run(code, "INPUT_AVAILABLE")
            for code in (
                "ZIP_RESOURCE_GUARDS",
                "PACKAGE_VALIDATION",
                "REOPEN",
                "EDITOR_OPEN_SAFETY",
            )
        )
        if expected_artifact_sha is not None:
            checks.append(_not_run("EXPECTED_ARTIFACT_HASH", "INPUT_AVAILABLE"))
        return make_layer_receipt(
            "package", checks, required_check_codes=required_check_codes
        )

    checks.append(_check("INPUT_AVAILABLE", "passed", {"available": True}))
    try:
        with ZipFile(io.BytesIO(output_payload), "r") as archive:
            _guard_evaluator_zip(archive, archive_size=artifact_size)
            zip_evidence = {
                "entryCount": len([i for i in archive.infolist() if not i.is_dir()]),
                "totalUncompressedBytes": sum(
                    i.file_size for i in archive.infolist() if not i.is_dir()
                ),
            }
    except (BadZipFile, HwpxSecurityError, OSError, ValueError):
        checks.append(
            _check("ZIP_RESOURCE_GUARDS", "failed", {"guardPassed": False})
        )
        checks.extend(
            _not_run(code, "ZIP_RESOURCE_GUARDS")
            for code in ("PACKAGE_VALIDATION", "REOPEN", "EDITOR_OPEN_SAFETY")
        )
        if expected_artifact_sha is not None:
            checks.append(_not_run("EXPECTED_ARTIFACT_HASH", "ZIP_RESOURCE_GUARDS"))
        return make_layer_receipt(
            "package", checks, required_check_codes=required_check_codes
        )

    checks.append(_check("ZIP_RESOURCE_GUARDS", "passed", zip_evidence))
    artifact_sha = hashlib.sha256(output_payload).hexdigest()

    try:
        package_report = validate_package(output_payload)
        package_ok = bool(package_report.ok)
        checks.append(
            _check(
                "PACKAGE_VALIDATION",
                "passed" if package_ok else "failed",
                {
                    "ok": package_ok,
                    "checkedPartCount": len(package_report.checked_parts),
                    "errorCount": len(package_report.errors),
                    "warningCount": len(package_report.warnings),
                },
            )
        )
    except Exception:  # noqa: BLE001 - fail closed; no exception text in receipt
        package_ok = False
        checks.append(
            _check("PACKAGE_VALIDATION", "unverified", {"completed": False})
        )

    if package_ok:
        try:
            open_report = validate_editor_open_safety(output_payload)
            reopen_ok = bool(open_report.reopen_ok)
            open_safe = bool(open_report.ok)
            checks.append(
                _check("REOPEN", "passed" if reopen_ok else "failed", {"ok": reopen_ok})
            )
            checks.append(
                _check(
                    "EDITOR_OPEN_SAFETY",
                    "passed" if open_safe else "failed",
                    {
                        "ok": open_safe,
                        "blockingPackageErrorCount": len(
                            open_report.blocking_package_errors
                        ),
                        "documentValidationAvailable": (
                            open_report.validate_document is not None
                        ),
                    },
                )
            )
        except Exception:  # noqa: BLE001 - fail closed; no exception text in receipt
            checks.append(_check("REOPEN", "unverified", {"completed": False}))
            checks.append(
                _check("EDITOR_OPEN_SAFETY", "unverified", {"completed": False})
            )
    else:
        checks.append(_not_run("REOPEN", "PACKAGE_VALIDATION"))
        checks.append(_not_run("EDITOR_OPEN_SAFETY", "PACKAGE_VALIDATION"))

    if expected_artifact_sha is not None:
        matches = artifact_sha == expected_artifact_sha
        checks.append(
            _check(
                "EXPECTED_ARTIFACT_HASH",
                "passed" if matches else "failed",
                {
                    "matches": matches,
                    "actualSha256": artifact_sha,
                    "expectedSha256": expected_artifact_sha,
                },
            )
        )
    return make_layer_receipt(
        "package",
        checks,
        artifact_sha256=artifact_sha,
        artifact_size_bytes=artifact_size,
        required_check_codes=required_check_codes,
    )


def _safe_member_name(value: object) -> str:
    name = str(value)
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not name or normalized != name or path.is_absolute() or ".." in path.parts:
        raise ValueError("member policy contains an unsafe ZIP member name")
    return name


def _validate_semantic_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("semantic policy must be an object")
    raw = dict(value)
    _require_exact_keys(
        raw,
        {
            "schema",
            "expectedDiff",
            "allowedChangedMembers",
            "promisedUntouchedMembers",
            "revision",
            "idempotency",
        },
        "semantic policy",
    )
    if raw.get("schema") != SEMANTIC_POLICY_SCHEMA:
        raise ValueError("unsupported semantic policy schema")

    expected_diff = raw.get("expectedDiff")
    if not isinstance(expected_diff, Mapping):
        raise ValueError("semantic policy expectedDiff must be an object")
    expected_diff = dict(expected_diff)
    _require_exact_keys(expected_diff, {"required", "sha256"}, "expectedDiff")
    if not isinstance(expected_diff["required"], bool):
        raise ValueError("expectedDiff.required must be a boolean")
    expected_diff_sha = expected_diff["sha256"]
    if expected_diff_sha is not None:
        expected_diff_sha = _require_sha(expected_diff_sha, "expectedDiff.sha256")
    if expected_diff["required"] and expected_diff_sha is None:
        raise ValueError("required semantic diff needs an expected sha256")

    member_sets: dict[str, list[str]] = {}
    for key in ("allowedChangedMembers", "promisedUntouchedMembers"):
        value_list = raw[key]
        if not isinstance(value_list, list):
            raise ValueError(f"{key} must be a list")
        normalized = [_safe_member_name(item) for item in value_list]
        if len(normalized) != len(set(normalized)) or normalized != sorted(normalized):
            raise ValueError(f"{key} must be unique and sorted")
        member_sets[key] = normalized

    revision = raw.get("revision")
    if not isinstance(revision, Mapping):
        raise ValueError("revision policy must be an object")
    revision = dict(revision)
    _require_exact_keys(
        revision, {"required", "expectedBefore", "expectedAfter"}, "revision"
    )
    if not isinstance(revision["required"], bool):
        raise ValueError("revision.required must be a boolean")
    for key in ("expectedBefore", "expectedAfter"):
        if revision[key] is not None:
            revision[key] = _require_nonnegative_int(revision[key], f"revision.{key}")
    if revision["required"] and (
        revision["expectedBefore"] is None or revision["expectedAfter"] is None
    ):
        raise ValueError("required revision policy needs both expected revisions")

    idempotency = raw.get("idempotency")
    if not isinstance(idempotency, Mapping):
        raise ValueError("idempotency policy must be an object")
    idempotency = dict(idempotency)
    _require_exact_keys(
        idempotency, {"required", "expectedMutationCount"}, "idempotency"
    )
    if not isinstance(idempotency["required"], bool):
        raise ValueError("idempotency.required must be a boolean")
    expected_mutations = idempotency["expectedMutationCount"]
    if expected_mutations is not None:
        expected_mutations = _require_nonnegative_int(
            expected_mutations, "idempotency.expectedMutationCount"
        )
    if idempotency["required"] and expected_mutations is None:
        raise ValueError("required idempotency policy needs expectedMutationCount")

    normalized_policy = {
        "schema": SEMANTIC_POLICY_SCHEMA,
        "expectedDiff": {
            "required": expected_diff["required"],
            "sha256": expected_diff_sha,
        },
        **member_sets,
        "revision": revision,
        "idempotency": {
            "required": idempotency["required"],
            "expectedMutationCount": expected_mutations,
        },
    }
    assert_receipt_safe(normalized_policy)
    return normalized_policy


def _read_source_once(source: str | Path | bytes) -> bytes:
    if isinstance(source, bytes):
        if len(source) > MAX_EVALUATOR_ARCHIVE_BYTES:
            raise HwpxSecurityError("practice artifact exceeds evaluator archive limit")
        return source
    with Path(source).open("rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("practice artifact must be a regular file")
        if metadata.st_size > MAX_EVALUATOR_ARCHIVE_BYTES:
            raise HwpxSecurityError("practice artifact exceeds evaluator archive limit")
        payload = stream.read(MAX_EVALUATOR_ARCHIVE_BYTES + 1)
    if len(payload) != metadata.st_size or len(payload) > MAX_EVALUATOR_ARCHIVE_BYTES:
        raise HwpxSecurityError("practice artifact changed or exceeded evaluator limit")
    return payload


def _guarded_zip_snapshot(
    source: str | Path | bytes,
) -> tuple[bytes, str, int, dict[str, str]]:
    """Bound, guard, hash, and inspect one stable file descriptor/byte snapshot."""

    payload = _read_source_once(source)
    size = len(payload)
    with ZipFile(io.BytesIO(payload), "r") as archive:
        _guard_evaluator_zip(archive, archive_size=size)
        members = {
            info.filename: hashlib.sha256(archive.read(info.filename)).hexdigest()
            for info in archive.infolist()
            if not info.is_dir()
        }
    return payload, hashlib.sha256(payload).hexdigest(), size, members


_WORKFLOW_EVENT_BINDING_KEYS = frozenset(
    {"eventId", "requestSha256", "idempotencyKey", "workflowReceiptSha256"}
)
_ARTIFACT_BINDING_KEYS = frozenset({"sha256", "sizeBytes"})


def _validate_workflow_event_binding(
    value: Mapping[str, Any], name: str
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    raw = dict(value)
    _require_exact_keys(raw, _WORKFLOW_EVENT_BINDING_KEYS, name)
    event_id = str(raw["eventId"])
    idempotency_key = str(raw["idempotencyKey"])
    if not EVENT_ID_PATTERN.fullmatch(event_id):
        raise ValueError(f"{name}.eventId must be opaque")
    if not OPAQUE_ID_PATTERN.fullmatch(idempotency_key):
        raise ValueError(f"{name}.idempotencyKey must be opaque")
    return {
        "eventId": event_id,
        "requestSha256": _require_sha(
            raw["requestSha256"], f"{name}.requestSha256"
        ),
        "idempotencyKey": idempotency_key,
        "workflowReceiptSha256": _require_sha(
            raw["workflowReceiptSha256"], f"{name}.workflowReceiptSha256"
        ),
    }


def _artifact_binding(sha256: str, size_bytes: int) -> dict[str, Any]:
    return {
        "sha256": _require_sha(sha256, "artifact binding sha256"),
        "sizeBytes": _require_nonnegative_int(size_bytes, "artifact binding sizeBytes"),
    }


def _validate_artifact_binding(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    raw = dict(value)
    _require_exact_keys(raw, _ARTIFACT_BINDING_KEYS, name)
    return _artifact_binding(raw["sha256"], raw["sizeBytes"])


def _seal_evaluator_receipt(
    payload: dict[str, Any], *, hash_field: str, authentication_key: bytes
) -> dict[str, Any]:
    key = _authentication_key(authentication_key)
    payload[hash_field] = _payload_digest(payload, hash_field)
    payload["auth"] = {
        "schema": EVALUATOR_AUTH_SCHEMA,
        "algorithm": "hmac-sha256",
        "keyId": _authentication_key_id(key),
        "macSha256": hmac.new(
            key, _canonical_bytes(payload), hashlib.sha256
        ).hexdigest(),
    }
    assert_receipt_safe(payload)
    return payload


def _validate_evaluator_receipt_auth(
    raw: Mapping[str, Any],
    *,
    hash_field: str,
    authentication_key: bytes,
) -> None:
    key = _authentication_key(authentication_key)
    auth = raw.get("auth")
    if not isinstance(auth, Mapping):
        raise ValueError("evaluator receipt authentication is missing")
    _require_exact_keys(
        auth,
        {"schema", "algorithm", "keyId", "macSha256"},
        "evaluator receipt auth",
    )
    if (
        auth.get("schema") != EVALUATOR_AUTH_SCHEMA
        or auth.get("algorithm") != "hmac-sha256"
        or auth.get("keyId") != _authentication_key_id(key)
    ):
        raise ValueError("evaluator receipt authentication key mismatch")
    content_addressed = dict(raw)
    content_addressed.pop("auth", None)
    if _require_sha(raw.get(hash_field), hash_field) != _payload_digest(
        content_addressed, hash_field
    ):
        raise ValueError(f"{hash_field} does not match receipt content")
    authenticated = dict(raw)
    authenticated.pop("auth", None)
    expected_mac = hmac.new(
        key, _canonical_bytes(authenticated), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(
        _require_sha(auth.get("macSha256"), "auth.macSha256"), expected_mac
    ):
        raise ValueError("evaluator receipt authentication failed")


def build_workflow_revision_receipt(
    *,
    run_id: str,
    workflow_event: Mapping[str, Any],
    start_source: str | Path | bytes,
    output_source: str | Path | bytes,
    expected_before: int,
    expected_after: int,
    observed_before: int,
    observed_after: int,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Seal revision evidence to one workflow event and measured artifacts."""

    if not RUN_ID_PATTERN.fullmatch(str(run_id)):
        raise ValueError("revision receipt runId must be opaque")
    event = _validate_workflow_event_binding(workflow_event, "workflowEvent")
    _, start_sha, start_size, _ = _guarded_zip_snapshot(start_source)
    _, output_sha, output_size, _ = _guarded_zip_snapshot(output_source)
    receipt = {
        "schema": WORKFLOW_REVISION_RECEIPT_SCHEMA,
        "runId": str(run_id),
        "workflowEvent": event,
        "startArtifact": _artifact_binding(start_sha, start_size),
        "outputArtifact": _artifact_binding(output_sha, output_size),
        "expectedRevision": {
            "before": _require_nonnegative_int(expected_before, "expected_before"),
            "after": _require_nonnegative_int(expected_after, "expected_after"),
        },
        "observedRevision": {
            "before": _require_nonnegative_int(observed_before, "observed_before"),
            "after": _require_nonnegative_int(observed_after, "observed_after"),
        },
    }
    return _seal_evaluator_receipt(
        receipt,
        hash_field="receiptSha256",
        authentication_key=authentication_key,
    )


def validate_workflow_revision_receipt(
    value: Mapping[str, Any], *, authentication_key: bytes
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("workflow revision receipt must be an object")
    raw = dict(value)
    _require_exact_keys(
        raw,
        {
            "schema",
            "runId",
            "workflowEvent",
            "startArtifact",
            "outputArtifact",
            "expectedRevision",
            "observedRevision",
            "receiptSha256",
            "auth",
        },
        "workflow revision receipt",
    )
    if raw.get("schema") != WORKFLOW_REVISION_RECEIPT_SCHEMA:
        raise ValueError("unsupported workflow revision receipt schema")
    if not RUN_ID_PATTERN.fullmatch(str(raw.get("runId", ""))):
        raise ValueError("workflow revision receipt runId is invalid")
    event = _validate_workflow_event_binding(raw["workflowEvent"], "workflowEvent")
    start = _validate_artifact_binding(raw["startArtifact"], "startArtifact")
    output = _validate_artifact_binding(raw["outputArtifact"], "outputArtifact")
    revisions: dict[str, dict[str, int]] = {}
    for field in ("expectedRevision", "observedRevision"):
        row = raw.get(field)
        if not isinstance(row, Mapping):
            raise ValueError(f"{field} must be an object")
        row = dict(row)
        _require_exact_keys(row, {"before", "after"}, field)
        revisions[field] = {
            "before": _require_nonnegative_int(row["before"], f"{field}.before"),
            "after": _require_nonnegative_int(row["after"], f"{field}.after"),
        }
    normalized = {
        "schema": WORKFLOW_REVISION_RECEIPT_SCHEMA,
        "runId": str(raw["runId"]),
        "workflowEvent": event,
        "startArtifact": start,
        "outputArtifact": output,
        **revisions,
        "receiptSha256": raw["receiptSha256"],
        "auth": raw["auth"],
    }
    _validate_evaluator_receipt_auth(
        normalized,
        hash_field="receiptSha256",
        authentication_key=authentication_key,
    )
    return normalized


def build_idempotency_replay_receipt(
    *,
    run_id: str,
    original_event: Mapping[str, Any],
    replay_event: Mapping[str, Any],
    start_source: str | Path | bytes,
    original_output_source: str | Path | bytes,
    replay_output_source: str | Path | bytes,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Seal distinct original/replay events and independently measured outputs."""

    if not RUN_ID_PATTERN.fullmatch(str(run_id)):
        raise ValueError("idempotency receipt runId must be opaque")
    original = _validate_workflow_event_binding(original_event, "originalEvent")
    replay = _validate_workflow_event_binding(replay_event, "replayEvent")
    _, start_sha, start_size, _ = _guarded_zip_snapshot(start_source)
    _, output_sha, output_size, _ = _guarded_zip_snapshot(original_output_source)
    _, replay_sha, replay_size, _ = _guarded_zip_snapshot(replay_output_source)
    receipt = {
        "schema": IDEMPOTENCY_REPLAY_RECEIPT_SCHEMA,
        "runId": str(run_id),
        "originalEvent": original,
        "replayEvent": replay,
        "startArtifact": _artifact_binding(start_sha, start_size),
        "originalOutputArtifact": _artifact_binding(output_sha, output_size),
        "replayOutputArtifact": _artifact_binding(replay_sha, replay_size),
    }
    return _seal_evaluator_receipt(
        receipt,
        hash_field="receiptSha256",
        authentication_key=authentication_key,
    )


def validate_idempotency_replay_receipt(
    value: Mapping[str, Any], *, authentication_key: bytes
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("idempotency replay receipt must be an object")
    raw = dict(value)
    _require_exact_keys(
        raw,
        {
            "schema",
            "runId",
            "originalEvent",
            "replayEvent",
            "startArtifact",
            "originalOutputArtifact",
            "replayOutputArtifact",
            "receiptSha256",
            "auth",
        },
        "idempotency replay receipt",
    )
    if raw.get("schema") != IDEMPOTENCY_REPLAY_RECEIPT_SCHEMA:
        raise ValueError("unsupported idempotency replay receipt schema")
    if not RUN_ID_PATTERN.fullmatch(str(raw.get("runId", ""))):
        raise ValueError("idempotency replay receipt runId is invalid")
    normalized = {
        "schema": IDEMPOTENCY_REPLAY_RECEIPT_SCHEMA,
        "runId": str(raw["runId"]),
        "originalEvent": _validate_workflow_event_binding(
            raw["originalEvent"], "originalEvent"
        ),
        "replayEvent": _validate_workflow_event_binding(
            raw["replayEvent"], "replayEvent"
        ),
        "startArtifact": _validate_artifact_binding(
            raw["startArtifact"], "startArtifact"
        ),
        "originalOutputArtifact": _validate_artifact_binding(
            raw["originalOutputArtifact"], "originalOutputArtifact"
        ),
        "replayOutputArtifact": _validate_artifact_binding(
            raw["replayOutputArtifact"], "replayOutputArtifact"
        ),
        "receiptSha256": raw["receiptSha256"],
        "auth": raw["auth"],
    }
    _validate_evaluator_receipt_auth(
        normalized,
        hash_field="receiptSha256",
        authentication_key=authentication_key,
    )
    return normalized


def semantic_diff_sha256(
    start_source: str | Path | bytes, output_source: str | Path | bytes
) -> str:
    """Return the frozen hash of the private semantic diff without disclosing text."""

    from hwpx.document import HwpxDocument

    if isinstance(start_source, bytes) or isinstance(output_source, bytes):
        start_payload = (
            start_source
            if isinstance(start_source, bytes)
            else _read_source_once(start_source)
        )
        output_payload = (
            output_source
            if isinstance(output_source, bytes)
            else _read_source_once(output_source)
        )
        with HwpxDocument.open(start_payload) as start_document:
            with HwpxDocument.open(output_payload) as output_document:
                return _digest(doc_diff(start_document, output_document))
    return _digest(doc_diff(start_source, output_source))


def evaluate_semantic_layer(
    start_source: str | Path | bytes,
    output_source: str | Path | bytes,
    policy: Mapping[str, Any],
    package_receipt: Mapping[str, Any],
    *,
    package_policy: Mapping[str, Any],
    workflow_revision_receipt: Mapping[str, Any] | None = None,
    idempotency_replay_receipt: Mapping[str, Any] | None = None,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Evaluate semantic/lossless, revision, and idempotency evidence."""

    normalized_policy = _validate_semantic_policy(policy)
    normalized_package_policy = _validate_package_policy(package_policy)
    package_check_codes = _package_check_codes(normalized_package_policy)
    semantic_check_codes = _semantic_check_codes(normalized_policy)
    package = validate_layer_receipt(
        package_receipt,
        expected_layer="package",
        required_check_codes=package_check_codes,
    )
    if package["status"] != "passed":
        checks = [_not_run("PACKAGE_PREREQUISITE", "package")]
        checks.extend(
            _not_run(code, "PACKAGE_PREREQUISITE")
            for code in semantic_check_codes[1:]
        )
        return make_layer_receipt(
            "semantic",
            checks,
            required_check_codes=semantic_check_codes,
        )

    try:
        output_payload, output_sha, output_size, output_members = _guarded_zip_snapshot(
            output_source
        )
    except (BadZipFile, HwpxSecurityError, OSError, TypeError, ValueError):
        checks = [
            _check("PACKAGE_PREREQUISITE", "failed", {"outputGuarded": False})
        ]
        checks.extend(
            _not_run(code, "PACKAGE_PREREQUISITE")
            for code in semantic_check_codes[1:]
        )
        return make_layer_receipt(
            "semantic",
            checks,
            required_check_codes=semantic_check_codes,
        )
    package_artifact = package.get("artifact")
    if not isinstance(package_artifact, Mapping) or package_artifact != {
        "sha256": output_sha,
        "sizeBytes": output_size,
    }:
        checks = [
            _check(
                "PACKAGE_PREREQUISITE",
                "failed",
                {"artifactBindingMatches": False},
            )
        ]
        checks.extend(
            _not_run(code, "PACKAGE_PREREQUISITE")
            for code in semantic_check_codes[1:]
        )
        return make_layer_receipt(
            "semantic",
            checks,
            artifact_sha256=output_sha,
            artifact_size_bytes=output_size,
            required_check_codes=semantic_check_codes,
        )
    try:
        start_payload, start_sha, start_size, start_members = _guarded_zip_snapshot(
            start_source
        )
    except (BadZipFile, HwpxSecurityError, OSError, TypeError, ValueError):
        checks = [
            _check("PACKAGE_PREREQUISITE", "unverified", {"startGuarded": False})
        ]
        checks.extend(
            _not_run(code, "PACKAGE_PREREQUISITE")
            for code in semantic_check_codes[1:]
        )
        return make_layer_receipt(
            "semantic",
            checks,
            artifact_sha256=output_sha,
            artifact_size_bytes=output_size,
            required_check_codes=semantic_check_codes,
        )

    checks: list[dict[str, str]] = [
        _check("PACKAGE_PREREQUISITE", "passed", {"packagePassed": True})
    ]

    diff_policy = normalized_policy["expectedDiff"]
    if diff_policy["required"] or diff_policy["sha256"] is not None:
        try:
            actual_diff_sha = semantic_diff_sha256(start_payload, output_payload)
            matches = actual_diff_sha == diff_policy["sha256"]
            checks.append(
                _check(
                    "SEMANTIC_DIFF",
                    "passed" if matches else "failed",
                    {
                        "matches": matches,
                        "actualSha256": actual_diff_sha,
                        "expectedSha256": diff_policy["sha256"],
                    },
                )
            )
        except Exception:  # noqa: BLE001 - no private parser details in receipt
            checks.append(
                _check("SEMANTIC_DIFF", "unverified", {"completed": False})
            )

    member_names = set(start_members) | set(output_members)
    changed = {
        name
        for name in member_names
        if start_members.get(name) != output_members.get(name)
    }
    allowed = set(normalized_policy["allowedChangedMembers"])
    unexpected = changed - allowed
    checks.append(
        _check(
            "FORBIDDEN_DRIFT",
            "failed" if unexpected else "passed",
            {
                "changedMemberCount": len(changed),
                "allowedChangedMemberCount": len(changed & allowed),
                "unexpectedChangedMemberCount": len(unexpected),
                "changedSetSha256": _digest(sorted(changed)),
            },
        )
    )

    promised = normalized_policy["promisedUntouchedMembers"]
    missing_promised = [
        name
        for name in promised
        if name not in start_members or name not in output_members
    ]
    changed_promised = [
        name
        for name in promised
        if name in start_members
        and name in output_members
        and start_members[name] != output_members[name]
    ]
    preservation_ok = not missing_promised and not changed_promised
    checks.append(
        _check(
            "BYTE_PRESERVATION",
            "passed" if preservation_ok else "failed",
            {
                "promisedMemberCount": len(promised),
                "missingMemberCount": len(missing_promised),
                "changedMemberCount": len(changed_promised),
                "promisedSetSha256": _digest(promised),
            },
        )
    )

    revision_policy = normalized_policy["revision"]
    if revision_policy["required"]:
        if workflow_revision_receipt is None:
            checks.append(_check("REVISION", "unverified", {"available": False}))
        else:
            try:
                observed = validate_workflow_revision_receipt(
                    workflow_revision_receipt,
                    authentication_key=authentication_key,
                )
                revision_ok = (
                    observed["startArtifact"]
                    == _artifact_binding(start_sha, start_size)
                    and observed["outputArtifact"]
                    == _artifact_binding(output_sha, output_size)
                    and observed["expectedRevision"]["before"]
                    == revision_policy["expectedBefore"]
                    and observed["expectedRevision"]["after"]
                    == revision_policy["expectedAfter"]
                    and observed["observedRevision"]
                    == observed["expectedRevision"]
                )
                checks.append(
                    _check(
                        "REVISION",
                        "passed" if revision_ok else "failed",
                        {"receiptSha256": observed["receiptSha256"]},
                    )
                )
            except ValueError:
                checks.append(
                    _check("REVISION", "unverified", {"receiptValid": False})
                )

    idempotency_policy = normalized_policy["idempotency"]
    if idempotency_policy["required"]:
        if idempotency_replay_receipt is None:
            checks.append(
                _check("IDEMPOTENCY", "unverified", {"evidenceComplete": False})
            )
        else:
            try:
                replay = validate_idempotency_replay_receipt(
                    idempotency_replay_receipt,
                    authentication_key=authentication_key,
                )
                idem_ok = (
                    replay["startArtifact"]
                    == _artifact_binding(start_sha, start_size)
                    and replay["originalOutputArtifact"]
                    == _artifact_binding(output_sha, output_size)
                    and replay["replayOutputArtifact"]
                    == replay["originalOutputArtifact"]
                    and replay["originalEvent"]["eventId"]
                    != replay["replayEvent"]["eventId"]
                    and replay["originalEvent"]["workflowReceiptSha256"]
                    != replay["replayEvent"]["workflowReceiptSha256"]
                    and replay["originalEvent"]["requestSha256"]
                    == replay["replayEvent"]["requestSha256"]
                    and replay["originalEvent"]["idempotencyKey"]
                    == replay["replayEvent"]["idempotencyKey"]
                    and idempotency_policy["expectedMutationCount"] == 1
                )
                checks.append(
                    _check(
                        "IDEMPOTENCY",
                        "passed" if idem_ok else "failed",
                        {"receiptSha256": replay["receiptSha256"]},
                    )
                )
            except (TypeError, ValueError):
                checks.append(
                    _check("IDEMPOTENCY", "unverified", {"receiptValid": False})
                )

    return make_layer_receipt(
        "semantic",
        checks,
        artifact_sha256=output_sha,
        artifact_size_bytes=output_size,
        input_artifact_sha256=start_sha,
        input_artifact_size_bytes=start_size,
        required_check_codes=semantic_check_codes,
    )


def domain_layer_from_bundle(
    value: Mapping[str, Any],
    *,
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Adapt a replay-validated domain bundle to the mandatory domain layer."""

    projection = domain_projection_from_bundle(
        value,
        domain_oracle_authentication_keys=domain_oracle_authentication_keys,
    )
    return make_layer_receipt(
        "domain", [_check("DOMAIN_VERIFIER", projection["status"], projection)]
    )


def domain_projection_from_bundle(
    value: Mapping[str, Any],
    *,
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Project aggregate-safe fields from a replay-validated domain bundle."""

    from .domain import validate_domain_evaluation_bundle

    bundle = validate_domain_evaluation_bundle(
        value,
        oracle_authentication_keys=domain_oracle_authentication_keys,
    )
    result = bundle["result"]
    verifier_families = sorted(
        str(row["verifierFamily"]) for row in result["verdicts"]
    )
    passed_must_abstain = any(
        row["verifierFamily"] == "must_abstain" and row["status"] == "passed"
        for row in result["verdicts"]
    )
    must_abstain_evidence = next(
        (
            row
            for row in bundle["evidence"]
            if row["verifierFamily"] == "must_abstain"
        ),
        None,
    )
    terminal_source = (
        must_abstain_evidence.get("sourceEvidence")
        if isinstance(must_abstain_evidence, Mapping)
        else None
    )
    must_abstain_terminal_receipt_sha = (
        terminal_source.get("receiptSha256")
        if isinstance(terminal_source, Mapping)
        else None
    )
    projection = {
        "domainResultSha256": result["resultSha256"],
        "scenarioSha256": result["scenarioSha256"],
        "artifactSha256": result["artifactSha256"],
        "status": result["status"],
        "observedTerminalState": result["observedTerminalState"],
        "verifierFamilies": verifier_families,
        "expectedAbstention": result["expectedAbstention"],
        "observedAbstention": result["observedAbstention"],
        "passedMustAbstainVerifier": passed_must_abstain,
        "mustAbstainTerminalReceiptSha256": must_abstain_terminal_receipt_sha,
    }
    return _validate_domain_projection(projection)


def _validate_domain_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("domain projection must be an object")
    raw = dict(value)
    _require_exact_keys(
        raw,
        {
            "domainResultSha256",
            "scenarioSha256",
            "artifactSha256",
            "status",
            "observedTerminalState",
            "verifierFamilies",
            "expectedAbstention",
            "observedAbstention",
            "passedMustAbstainVerifier",
            "mustAbstainTerminalReceiptSha256",
        },
        "domain projection",
    )
    for key in ("domainResultSha256", "scenarioSha256", "artifactSha256"):
        raw[key] = _require_sha(raw[key], f"domain projection {key}")
    if raw["mustAbstainTerminalReceiptSha256"] is not None:
        raw["mustAbstainTerminalReceiptSha256"] = _require_sha(
            raw["mustAbstainTerminalReceiptSha256"],
            "domain projection mustAbstainTerminalReceiptSha256",
        )
    if raw["status"] not in LAYER_STATUSES:
        raise ValueError("domain projection status is invalid")
    if raw["observedTerminalState"] not in TERMINAL_RUN_STATES:
        raise ValueError("domain projection terminal state is invalid")
    families = raw["verifierFamilies"]
    if (
        not isinstance(families, list)
        or not families
        or families != sorted(families)
        or len(families) != len(set(families))
        or any(
            not isinstance(item, str)
            or not item
            or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in item)
            for item in families
        )
    ):
        raise ValueError(
            "domain projection verifierFamilies must be closed, unique, and sorted"
        )
    for key in (
        "expectedAbstention",
        "observedAbstention",
        "passedMustAbstainVerifier",
    ):
        if not isinstance(raw[key], bool):
            raise ValueError(f"domain projection {key} must be boolean")
    if raw["observedAbstention"] and not (
        raw["expectedAbstention"]
        and raw["passedMustAbstainVerifier"]
        and "must_abstain" in families
    ):
        raise ValueError("observed abstention lacks an exact passed verifier binding")
    if raw["passedMustAbstainVerifier"] and not (
        raw["expectedAbstention"] and "must_abstain" in families
    ):
        raise ValueError("passed must-abstain projection is inconsistent")
    assert_receipt_safe(raw)
    return raw


def _validate_scenario_ref(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("scenarioRef must be an object")
    raw = dict(value)
    _require_exact_keys(raw, _SCENARIO_REF_KEYS, "scenarioRef")
    scenario_id = str(raw["scenarioId"])
    if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
        raise ValueError("scenarioRef.scenarioId must be opaque")
    start_id = str(raw["startArtifactId"])
    if not OPAQUE_ID_PATTERN.fullmatch(start_id):
        raise ValueError("scenarioRef.startArtifactId must be opaque")
    result = {"scenarioId": scenario_id, "startArtifactId": start_id}
    for key in (
        "scenarioSha256",
        "runnerManifestSha256",
        "derivativeSha256",
        "startArtifactSha256",
    ):
        result[key] = _require_sha(raw[key], f"scenarioRef.{key}")
    # Preserve the schema's deterministic field order.
    return {key: result[key] for key in _SCENARIO_REF_KEYS}


def _validate_campaign_ref(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("campaignRef must be an object")
    raw = dict(value)
    _require_exact_keys(raw, _CAMPAIGN_REF_KEYS, "campaignRef")
    manifest_sha = _require_sha(
        raw["manifestSha256"], "campaignRef.manifestSha256"
    )
    campaign_id = str(raw["campaignId"])
    if not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise ValueError("campaignRef.campaignId must be opaque")
    if campaign_id != f"PCMP-{manifest_sha[:20].upper()}":
        raise ValueError("campaignRef campaignId/manifestSha256 identity mismatch")
    slot = _require_nonnegative_int(raw["slot"], "campaignRef.slot")
    family = str(raw["family"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", family):
        raise ValueError("campaignRef.family must be a closed code")
    difficulty = str(raw["difficulty"])
    if difficulty not in {"routine", "intermediate", "advanced"}:
        raise ValueError("campaignRef.difficulty is unsupported")
    return {
        "campaignId": campaign_id,
        "manifestSha256": manifest_sha,
        "slot": slot,
        "family": family,
        "difficulty": difficulty,
    }


def combine_evaluation_result(
    package_receipt: Mapping[str, Any],
    semantic_receipt: Mapping[str, Any],
    domain_receipt: Mapping[str, Any],
    *,
    run_id: str,
    campaign_ref: Mapping[str, Any],
    scenario_ref: Mapping[str, Any],
    terminal_state: str,
    terminal_receipt: Mapping[str, Any],
    package_policy: Mapping[str, Any],
    semantic_policy: Mapping[str, Any],
    domain_bundle: Mapping[str, Any],
    expected_evaluation_policy_sha256: str,
    evaluator_code_sha256: str,
    authentication_key: bytes,
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
    workflow_revision_receipt: Mapping[str, Any] | None = None,
    idempotency_replay_receipt: Mapping[str, Any] | None = None,
    authentication_key_id: str | None = None,
    required_later_layers: Sequence[str] = (),
    later_layers: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Combine mandatory ordered gates into one content-addressed result.

    ``terminalState`` is the runner's actual terminal state and is preserved so
    aggregates can expose corrupt-success attempts.  ``overallStatus`` and
    ``eligibleForSuccess`` are evaluator-owned and can never become successful
    unless every mandatory layer passed.
    """

    if not RUN_ID_PATTERN.fullmatch(str(run_id)):
        raise ValueError("run_id must be an opaque PracticeRun identifier")
    if terminal_state not in TERMINAL_RUN_STATES:
        raise ValueError("terminal_state must be terminal")
    auth_key = _authentication_key(authentication_key)
    evaluator_code_sha = _require_sha(
        evaluator_code_sha256, "evaluator_code_sha256"
    )
    if evaluator_code_sha != current_evaluator_code_sha256():
        raise ValueError("evaluator code sha256 does not match installed evaluator")
    derived_key_id = _authentication_key_id(auth_key)
    if authentication_key_id is not None:
        supplied_key_id = str(authentication_key_id)
        if (
            not EVALUATOR_KEY_ID_PATTERN.fullmatch(supplied_key_id)
            or supplied_key_id != derived_key_id
        ):
            raise ValueError("evaluator authentication key id mismatch")
    normalized_campaign_ref = _validate_campaign_ref(campaign_ref)
    normalized_ref = _validate_scenario_ref(scenario_ref)
    normalized_terminal_receipt = validate_run_receipt(terminal_receipt)
    if normalized_terminal_receipt["runId"] != str(run_id):
        raise ValueError("terminal receipt run binding mismatch")
    if normalized_terminal_receipt["scenarioId"] != normalized_ref["scenarioId"]:
        raise ValueError("terminal receipt scenario binding mismatch")
    if normalized_terminal_receipt["state"] != terminal_state:
        raise ValueError("terminal receipt state binding mismatch")
    terminal_receipt_sha = normalized_terminal_receipt["receiptSha256"]

    from .domain import (
        abstention_inventory_authentication_key_id,
        validate_domain_evaluation_bundle,
    )

    # Must-abstain inventory evidence is authenticated with the evaluator key
    # under a distinct AOK namespace.  Only the derived key ID and MAC are
    # serialized; combine always replays source validation with the live key.
    effective_domain_authentication_keys = dict(
        domain_oracle_authentication_keys or {}
    )
    abstention_key_id = abstention_inventory_authentication_key_id(auth_key)
    effective_domain_authentication_keys.setdefault(abstention_key_id, auth_key)

    normalized_package_policy = _validate_package_policy(package_policy)
    normalized_semantic_policy = _normalize_semantic_policy_projection(
        semantic_policy
    )
    normalized_domain_bundle = validate_domain_evaluation_bundle(
        domain_bundle,
        oracle_authentication_keys=effective_domain_authentication_keys,
    )
    if (
        normalized_domain_bundle["requirement"]["family"]
        != normalized_campaign_ref["family"]
    ):
        raise ValueError("campaignRef family does not match domain family")
    terminal_outputs = [
        row
        for row in normalized_terminal_receipt["artifacts"]
        if row["role"] == "output"
    ]
    evaluated_artifact_sha = normalized_domain_bundle["result"]["artifactSha256"]
    terminal_output_binding: dict[str, Any] | None = None
    if terminal_state == "completed":
        if len(terminal_outputs) != 1:
            raise ValueError("completed terminal receipt requires one output artifact")
        terminal_output = terminal_outputs[0]
        terminal_output_binding = {
            "sha256": terminal_output["sha256"],
            "sizeBytes": terminal_output["bytes"],
        }
        if terminal_output["sha256"] != evaluated_artifact_sha:
            raise ValueError("terminal receipt output artifact binding mismatch")
        if (
            normalized_terminal_receipt["usage"]["artifactBytes"]
            != terminal_output["bytes"]
        ):
            raise ValueError(
                "terminal receipt retained output bytes do not match usage"
            )
    elif terminal_outputs:
        if len(terminal_outputs) != 1:
            raise ValueError(
                "non-completed terminal receipt permits at most one retained output artifact"
            )
        terminal_output = terminal_outputs[0]
        terminal_output_binding = {
            "sha256": terminal_output["sha256"],
            "sizeBytes": terminal_output["bytes"],
        }
        if terminal_output["sha256"] != evaluated_artifact_sha:
            raise ValueError("terminal receipt output artifact binding mismatch")
        if (
            normalized_terminal_receipt["usage"]["artifactBytes"]
            != terminal_output["bytes"]
        ):
            raise ValueError(
                "terminal receipt retained output bytes do not match usage"
            )
    elif evaluated_artifact_sha != normalized_ref["startArtifactSha256"]:
        raise ValueError("terminal receipt abstention artifact binding mismatch")
    normalized_required_later = _validate_required_later_layers(
        required_later_layers
    )
    expected_policy_sha = _require_sha(
        expected_evaluation_policy_sha256,
        "expected_evaluation_policy_sha256",
    )
    actual_policy_sha = evaluation_policy_sha256(
        normalized_package_policy,
        normalized_semantic_policy,
        normalized_domain_bundle,
        normalized_required_later,
        domain_oracle_authentication_keys=effective_domain_authentication_keys,
    )
    if actual_policy_sha != expected_policy_sha:
        raise ValueError("evaluation policy sha256 mismatch")
    normalized_domain_projection = domain_projection_from_bundle(
        normalized_domain_bundle,
        domain_oracle_authentication_keys=effective_domain_authentication_keys,
    )
    domain_terminal_receipt_sha = normalized_domain_projection[
        "mustAbstainTerminalReceiptSha256"
    ]
    if (
        domain_terminal_receipt_sha is not None
        and domain_terminal_receipt_sha != terminal_receipt_sha
    ):
        raise ValueError("must-abstain terminal receipt binding mismatch")
    if (
        normalized_domain_projection["passedMustAbstainVerifier"]
        and domain_terminal_receipt_sha is None
    ):
        raise ValueError(
            "passed must-abstain verifier requires terminal receipt source evidence"
        )
    terminal_observed_abstention = any(
        event["kind"] == "decision_gate" and event["status"] == "abstained"
        for event in normalized_terminal_receipt["workflowEvents"]
    )
    if (
        normalized_domain_projection["observedAbstention"]
        and not terminal_observed_abstention
    ):
        raise ValueError(
            "domain observed abstention is absent from terminal workflow events"
        )
    if (
        normalized_domain_projection["scenarioSha256"]
        != normalized_ref["scenarioSha256"]
    ):
        raise ValueError("domain projection scenario binding mismatch")
    if normalized_domain_projection["observedTerminalState"] != terminal_state:
        raise ValueError("domain projection terminal-state binding mismatch")
    expected_domain_layer = make_layer_receipt(
        "domain",
        [
            _check(
                "DOMAIN_VERIFIER",
                normalized_domain_projection["status"],
                normalized_domain_projection,
            )
        ],
    )

    layers = [
        validate_layer_receipt(
            package_receipt,
            expected_layer="package",
            required_check_codes=_package_check_codes(normalized_package_policy),
        ),
        validate_layer_receipt(
            semantic_receipt,
            expected_layer="semantic",
            required_check_codes=_semantic_check_codes(normalized_semantic_policy),
        ),
        validate_layer_receipt(domain_receipt, expected_layer="domain"),
    ]
    if layers[2] != expected_domain_layer:
        raise ValueError("domain layer does not match its content-bound projection")
    semantic_input = layers[1].get("inputArtifact")
    if layers[1]["status"] == "passed" and not isinstance(
        semantic_input, Mapping
    ):
        raise ValueError("a passed semantic layer requires start artifact binding")
    if (
        isinstance(semantic_input, Mapping)
        and semantic_input.get("sha256")
        != normalized_ref["startArtifactSha256"]
    ):
        raise ValueError("semantic layer start artifact binding mismatch")
    if layers[0].get("inputArtifact") is not None or layers[2].get(
        "inputArtifact"
    ) is not None:
        raise ValueError("only semantic layers may bind a start artifact")
    semantic_checks = {row["code"]: row for row in layers[1]["checks"]}
    terminal_event_bindings = [
        {
            "eventId": event["eventId"],
            "requestSha256": event["requestSha256"],
            "idempotencyKey": event["idempotencyKey"],
            "workflowReceiptSha256": _digest(event),
        }
        for event in normalized_terminal_receipt["workflowEvents"]
    ]
    revision_required = normalized_semantic_policy["revision"]["required"]
    idempotency_required = normalized_semantic_policy["idempotency"]["required"]
    if not revision_required and workflow_revision_receipt is not None:
        raise ValueError("unexpected workflow revision receipt")
    if not idempotency_required and idempotency_replay_receipt is not None:
        raise ValueError("unexpected idempotency replay receipt")
    revision_receipt = None
    if workflow_revision_receipt is not None:
        revision_receipt = validate_workflow_revision_receipt(
            workflow_revision_receipt, authentication_key=auth_key
        )
        if revision_receipt["runId"] != str(run_id):
            raise ValueError("workflow revision receipt run binding mismatch")
        if revision_receipt["workflowEvent"] not in terminal_event_bindings:
            raise ValueError("workflow revision event is absent from terminal receipt")
        if revision_receipt["startArtifact"]["sha256"] != normalized_ref[
            "startArtifactSha256"
        ]:
            raise ValueError("workflow revision receipt start binding mismatch")
        if revision_receipt["outputArtifact"]["sha256"] != normalized_domain_projection[
            "artifactSha256"
        ]:
            raise ValueError("workflow revision receipt output binding mismatch")
        expected_check = _check(
            "REVISION",
            semantic_checks["REVISION"]["status"],
            {"receiptSha256": revision_receipt["receiptSha256"]},
        )
        if semantic_checks["REVISION"] != expected_check:
            raise ValueError("revision check is not bound to its workflow receipt")
    elif revision_required and semantic_checks["REVISION"]["status"] == "passed":
        raise ValueError("passed revision check requires authenticated evidence")
    replay_receipt = None
    if idempotency_replay_receipt is not None:
        replay_receipt = validate_idempotency_replay_receipt(
            idempotency_replay_receipt, authentication_key=auth_key
        )
        if replay_receipt["runId"] != str(run_id):
            raise ValueError("idempotency replay receipt run binding mismatch")
        if (
            replay_receipt["originalEvent"] not in terminal_event_bindings
            or replay_receipt["replayEvent"] not in terminal_event_bindings
        ):
            raise ValueError("idempotency events are absent from terminal receipt")
        if replay_receipt["startArtifact"]["sha256"] != normalized_ref[
            "startArtifactSha256"
        ]:
            raise ValueError("idempotency replay receipt start binding mismatch")
        if (
            replay_receipt["originalOutputArtifact"]["sha256"]
            != normalized_domain_projection["artifactSha256"]
        ):
            raise ValueError("idempotency replay receipt output binding mismatch")
        expected_check = _check(
            "IDEMPOTENCY",
            semantic_checks["IDEMPOTENCY"]["status"],
            {"receiptSha256": replay_receipt["receiptSha256"]},
        )
        if semantic_checks["IDEMPOTENCY"] != expected_check:
            raise ValueError("idempotency check is not bound to its replay receipt")
    elif idempotency_required and semantic_checks["IDEMPOTENCY"]["status"] == "passed":
        raise ValueError(
            "passed idempotency check requires authenticated replay evidence"
        )
    expected_artifact_sha = normalized_package_policy["expectedArtifactHash"][
        "sha256"
    ]
    if (
        expected_artifact_sha is not None
        and expected_artifact_sha
        != normalized_domain_projection["artifactSha256"]
    ):
        raise ValueError("package expected hash does not match evaluated artifact")
    for layer in layers[:2]:
        artifact = layer.get("artifact")
        if layer["status"] == "passed" and not isinstance(artifact, Mapping):
            raise ValueError(
                "a passed package/semantic layer requires artifact binding"
            )
        if (
            isinstance(artifact, Mapping)
            and artifact.get("sha256")
            != normalized_domain_projection["artifactSha256"]
        ):
            raise ValueError("evaluator layers are bound to different output artifacts")
    package_artifact = layers[0].get("artifact")
    semantic_artifact = layers[1].get("artifact")
    if (
        isinstance(package_artifact, Mapping)
        and isinstance(semantic_artifact, Mapping)
        and package_artifact != semantic_artifact
    ):
        raise ValueError("package and semantic artifact bindings differ")
    if terminal_output_binding is not None and (
        package_artifact != terminal_output_binding
        or semantic_artifact != terminal_output_binding
    ):
        raise ValueError(
            "terminal receipt output artifact does not match evaluator artifact binding"
        )
    if len(later_layers) != len(normalized_required_later):
        raise ValueError("required later evaluator layer coverage is incomplete")
    for value, expected in zip(later_layers, normalized_required_later):
        later = validate_layer_receipt(value, expected_layer=expected)
        later_artifact = later.get("artifact")
        if later["status"] == "passed" and not isinstance(
            later_artifact, Mapping
        ):
            raise ValueError("passed later evaluator layer requires artifact binding")
        if (
            isinstance(later_artifact, Mapping)
            and later_artifact.get("sha256")
            != normalized_domain_projection["artifactSha256"]
        ):
            raise ValueError("later evaluator layer artifact binding mismatch")
        if later.get("inputArtifact") is not None:
            raise ValueError("later evaluator layers cannot bind a start artifact")
        layers.append(later)

    layer_statuses = {layer["layer"]: layer["status"] for layer in layers}
    required_names = MANDATORY_LAYERS + normalized_required_later
    required_statuses = [layer_statuses[name] for name in required_names]
    if "failed" in required_statuses:
        overall_status = "failed"
    elif set(required_statuses) == {"passed"}:
        overall_status = "passed"
    else:
        overall_status = "unverified"

    critical_failures = sum(
        1
        for layer in layers[: len(required_names)]
        for check in layer["checks"]
        if check["status"] == "failed"
    )
    missing_evidence = sum(
        1
        for layer in layers[: len(required_names)]
        for check in layer["checks"]
        if check["status"] in {"unverified", "not_run"}
    )
    result: dict[str, Any] = {
        "schema": EVALUATOR_RESULT_SCHEMA,
        "evaluatorVersion": EVALUATOR_POLICY_VERSION,
        "runId": str(run_id),
        "campaignRef": normalized_campaign_ref,
        "scenarioRef": normalized_ref,
        "terminalState": terminal_state,
        "terminalReceiptSha256": terminal_receipt_sha,
        "overallStatus": overall_status,
        "eligibleForSuccess": overall_status == "passed",
        "evaluationPolicySha256": actual_policy_sha,
        "evaluatorCodeSha256": evaluator_code_sha,
        "requiredLaterLayers": list(normalized_required_later),
        "domainVerdict": layer_statuses["domain"],
        "packagePolicy": normalized_package_policy,
        "semanticPolicy": normalized_semantic_policy,
        "semanticEvidence": {
            "workflowRevisionReceipt": revision_receipt,
            "idempotencyReplayReceipt": replay_receipt,
        },
        "domainBundle": normalized_domain_bundle,
        "domainProjection": normalized_domain_projection,
        "layerStatuses": layer_statuses,
        "criticalFailureCount": critical_failures,
        "missingEvidenceCount": missing_evidence,
        "layers": layers,
    }
    result["evaluatorResultSha256"] = _payload_digest(
        result, "evaluatorResultSha256"
    )
    result["auth"] = {
        "schema": EVALUATOR_AUTH_SCHEMA,
        "algorithm": "hmac-sha256",
        "keyId": derived_key_id,
        "macSha256": hmac.new(
            auth_key, _canonical_bytes(result), hashlib.sha256
        ).hexdigest(),
    }
    assert_receipt_safe(result)
    return result


def validate_evaluation_result(
    value: Mapping[str, Any],
    *,
    authentication_key: bytes | None = None,
    terminal_receipt: Mapping[str, Any],
    domain_oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Validate/rebuild a combined result, rejecting tampering and extra fields."""

    if not isinstance(value, Mapping):
        raise ValueError("evaluation result must be an object")
    auth_key = _authentication_key(authentication_key)
    raw = dict(value)
    _guard_result_shape(raw)
    _require_exact_keys(raw, _RESULT_KEYS, "evaluation result")
    if raw.get("schema") != EVALUATOR_RESULT_SCHEMA:
        raise ValueError("unsupported evaluation result schema")
    if raw.get("evaluatorVersion") != EVALUATOR_POLICY_VERSION:
        raise ValueError("unsupported evaluator version")
    layers_value = raw.get("layers")
    if not isinstance(layers_value, list) or len(layers_value) < 3:
        raise ValueError(
            "evaluation result requires package, semantic, and domain layers"
        )
    auth = raw.get("auth")
    if not isinstance(auth, Mapping):
        raise ValueError("evaluation result requires evaluator authentication")
    _require_exact_keys(
        auth,
        {"schema", "algorithm", "keyId", "macSha256"},
        "evaluation result auth",
    )
    if (
        auth.get("schema") != EVALUATOR_AUTH_SCHEMA
        or auth.get("algorithm") != "hmac-sha256"
    ):
        raise ValueError("unsupported evaluator authentication envelope")
    if auth.get("keyId") != _authentication_key_id(auth_key):
        raise ValueError("evaluator authentication key id mismatch")
    unsigned = dict(raw)
    unsigned.pop("auth", None)
    unsigned_bytes = _canonical_bytes(unsigned)
    if len(unsigned_bytes) > MAX_EVALUATOR_RESULT_BYTES:
        raise ValueError("evaluation result exceeds authenticated size limit")
    expected_mac = hmac.new(auth_key, unsigned_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(
        _require_sha(auth.get("macSha256"), "auth.macSha256"), expected_mac
    ):
        raise ValueError("evaluation result authentication failed")
    rebuilt = combine_evaluation_result(
        layers_value[0],
        layers_value[1],
        layers_value[2],
        run_id=str(raw.get("runId")),
        campaign_ref=raw.get("campaignRef"),
        scenario_ref=raw.get("scenarioRef"),
        terminal_state=str(raw.get("terminalState")),
        terminal_receipt=terminal_receipt,
        package_policy=raw.get("packagePolicy"),
        semantic_policy=raw.get("semanticPolicy"),
        domain_bundle=raw.get("domainBundle"),
        expected_evaluation_policy_sha256=str(
            raw.get("evaluationPolicySha256", "")
        ),
        evaluator_code_sha256=str(raw.get("evaluatorCodeSha256", "")),
        authentication_key=auth_key,
        domain_oracle_authentication_keys=domain_oracle_authentication_keys,
        workflow_revision_receipt=(
            raw.get("semanticEvidence", {}).get("workflowRevisionReceipt")
            if isinstance(raw.get("semanticEvidence"), Mapping)
            else None
        ),
        idempotency_replay_receipt=(
            raw.get("semanticEvidence", {}).get("idempotencyReplayReceipt")
            if isinstance(raw.get("semanticEvidence"), Mapping)
            else None
        ),
        authentication_key_id=str(auth.get("keyId", "")),
        required_later_layers=(
            raw.get("requiredLaterLayers")
            if isinstance(raw.get("requiredLaterLayers"), list)
            else ()
        ),
        later_layers=layers_value[3:],
    )
    if rebuilt != raw:
        raise ValueError("evaluation result content/hash mismatch")
    return rebuilt


__all__ = [
    "CHECK_CODES",
    "CHECK_STATUSES",
    "EVALUATOR_LAYER_SCHEMA",
    "EVALUATOR_AUTH_SCHEMA",
    "EVALUATOR_POLICY_VERSION",
    "EVALUATOR_RESULT_SCHEMA",
    "EVALUATION_POLICY_SCHEMA",
    "IDEMPOTENCY_REPLAY_RECEIPT_SCHEMA",
    "LAYER_ORDER",
    "WORKFLOW_REVISION_RECEIPT_SCHEMA",
    "SEMANTIC_POLICY_SCHEMA",
    "SEMANTIC_POLICY_PROJECTION_SCHEMA",
    "PACKAGE_POLICY_SCHEMA",
    "build_idempotency_replay_receipt",
    "build_package_policy",
    "build_workflow_revision_receipt",
    "combine_evaluation_result",
    "current_evaluator_code_sha256",
    "domain_layer_from_bundle",
    "domain_projection_from_bundle",
    "evaluator_authentication_key_id",
    "evaluate_package_layer",
    "evaluate_semantic_layer",
    "evaluation_policy_sha256",
    "make_layer_receipt",
    "make_check_receipt",
    "semantic_diff_sha256",
    "semantic_policy_projection",
    "validate_evaluation_result",
    "validate_idempotency_replay_receipt",
    "validate_layer_receipt",
    "validate_workflow_revision_receipt",
]
