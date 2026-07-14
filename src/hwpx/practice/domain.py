"""Closed, privacy-safe domain-verifier contracts for practice evaluation.

The practice runner must not grade itself from prose.  This module binds each
task and supported document family to a fixed verifier family, content-binds
the resulting evidence to one scenario/output pair, and reduces only closed
check statuses to a fail-closed verdict.  Source paths, findings, extracted
text, gold values, and free-form explanations are deliberately absent from all
durable values returned here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from hwpx.opc.security import MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES, guard_zip_file

from .registry import SHA256_PATTERN
from .run import TERMINAL_RUN_STATES, assert_receipt_safe
from .scenario import SCENARIO_ID_PATTERN, TASK_KINDS

DOMAIN_REQUIREMENT_SCHEMA = "hwpx.practice-domain-requirement/v1"
DOMAIN_EVIDENCE_SCHEMA = "hwpx.practice-domain-evidence/v1"
DOMAIN_RESULT_SCHEMA = "hwpx.practice-domain-result/v1"
DOMAIN_EVALUATION_BUNDLE_SCHEMA = "hwpx.practice-domain-evaluation-bundle/v1"
DOMAIN_POLICY_PROJECTION_SCHEMA = "hwpx.practice-domain-policy/v1"
DOMAIN_SOURCE_EVIDENCE_SCHEMA = "hwpx.practice-domain-source-evidence/v1"
DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA = (
    "hwpx.practice-domain-terminal-source-evidence/v1"
)
FORM_TARGET_POLICY_SCHEMA = "hwpx.practice-form-target-policy/v1"
FORM_DIFFERENTIAL_RECEIPT_SCHEMA = (
    "hwpx.practice-form-differential-receipt/v1"
)
FORM_DIFFERENTIAL_SOURCE_EVIDENCE_SCHEMA = (
    "hwpx.practice-form-differential-source-evidence/v1"
)
EXAM_ORACLE_RECEIPT_SCHEMA = "hwpx.practice-exam-oracle-receipt/v1"
EXAM_ORACLE_AUTH_SCHEMA = "hwpx.practice-exam-oracle-auth/v1"
ABSTENTION_INVENTORY_AUTH_SCHEMA = "hwpx.practice-abstention-inventory-auth/v1"

DOMAIN_STATUSES = frozenset({"passed", "failed", "unverified"})
CHECK_STATUSES = frozenset({"passed", "failed", "unverified", "not_run"})
ABSTENTION_TERMINAL_STATES = frozenset({"needs_review", "refused", "unverified"})
DOMAIN_REASON_CODES = frozenset(
    {
        "DOMAIN_PASSED",
        "DOMAIN_VERIFIER_PASSED",
        "DOMAIN_VERIFIER_FAILED",
        "DOMAIN_VERIFIER_UNVERIFIED",
        "DOMAIN_VERIFIER_MISSING",
        "DOMAIN_VERIFIER_DUPLICATE",
        "DOMAIN_VERIFIER_UNEXPECTED",
        "DOMAIN_EVIDENCE_BINDING_MISMATCH",
        "DOMAIN_EVIDENCE_MALFORMED",
    }
)

VERIFIER_CHECKS: dict[str, tuple[str, ...]] = {
    "edit": (
        "expected_change_pass",
        "forbidden_drift_absent",
        "untouched_members_preserved",
    ),
    "form_fill": (
        "mapping_complete",
        "residue_absent",
        "synthetic_values_verified",
    ),
    "structural_table": (
        "table_geometry_preserved",
        "exact_values_pass",
        "merged_cells_preserved",
    ),
    "exam": (
        "question_split_absent",
        "placeholder_integrity_pass",
        "exam_invariants_pass",
    ),
    "official_document": (
        "official_lint_pass",
        "official_structure_pass",
        "reference_consistency_pass",
    ),
    "authoring": (
        "authoring_quality_pass",
        "style_profile_pass",
        "reference_consistency_pass",
    ),
    "must_abstain": (
        "terminal_state_allowed",
        "no_mutation",
        "decision_reason_present",
    ),
}

_TASK_VERIFIER = {
    "reverse_restore": "edit",
    "constrained_edit": "edit",
    "known_template_fill": "form_fill",
    "unknown_form_fill": "form_fill",
    "structural_edit": "structural_table",
    "typed_authoring": "authoring",
    "must_abstain": "must_abstain",
}
# Provisioning maps S-072's local Korean discovery labels to these canonical
# ASCII codes before constructing any public campaign/domain receipt.  Do not
# accept the private/raw labels here.
_EXAM_FAMILY_CODES = frozenset({"exam", "exam_question_answer"})
_OFFICIAL_FAMILY_CODES = frozenset(
    {"official_document", "official_notice", "official_document_draft_dispatch"}
)
_FAMILY_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_VERIFIER_ID_PATTERN = re.compile(r"^VER-[A-F0-9]{20}$")
_VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}/v[1-9][0-9]*$")
_EXAM_ORACLE_KEY_ID_PATTERN = re.compile(r"^EOK-[A-F0-9]{20}$")
_ABSTENTION_INVENTORY_KEY_ID_PATTERN = re.compile(r"^AOK-[A-F0-9]{20}$")
_FORM_RENDER_BACKEND_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_ZERO_SHA256 = "0" * 64
MAX_DOMAIN_ARTIFACT_BYTES = MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_bounded_snapshot(source: str | Path) -> bytes:
    """Read one immutable, bounded regular-file snapshot from one descriptor."""

    with Path(source).open("rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("domain artifact must be a regular file")
        if metadata.st_size > MAX_DOMAIN_ARTIFACT_BYTES:
            raise ValueError("domain artifact exceeds its size bound")
        payload = stream.read(MAX_DOMAIN_ARTIFACT_BYTES + 1)
    if len(payload) != metadata.st_size or len(payload) > MAX_DOMAIN_ARTIFACT_BYTES:
        raise ValueError("domain artifact changed or exceeded its size bound")
    return payload


def _read_hwpx_snapshot(source: str | Path) -> bytes:
    payload = _read_bounded_snapshot(source)
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(payload), "r") as archive:
        guard_zip_file(archive)
    return payload


@contextmanager
def _strict_snapshot_path(payload: bytes, *, suffix: str) -> Iterator[Path]:
    """Expose snapshot bytes only through an evaluator-owned private temp path."""

    with tempfile.TemporaryDirectory(prefix="hwpx-practice-domain-") as directory:
        os.chmod(directory, 0o700)
        path = Path(directory) / f"snapshot{suffix}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        yield path


def _normalized_synthetic_text(value: object) -> str:
    return " ".join(str(value).split())


def domain_value_sha256(value: object) -> str:
    """Hash one private/synthetic expected value without exposing its text."""

    normalized = _normalized_synthetic_text(value)
    if not normalized:
        raise ValueError("a domain value cannot be empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def domain_row_sha256(values: Sequence[object]) -> str:
    """Hash one ordered synthetic table row without exposing cell values."""

    normalized = [_normalized_synthetic_text(value) for value in values]
    if not normalized or any(not value for value in normalized):
        raise ValueError("a domain row requires non-empty ordered values")
    return _sha256(normalized)


def structural_verifier_policy_sha256(
    *,
    expected_start_sha256: str,
    expected_row_sha256: str,
    expected_value_sha256s: Sequence[str],
) -> str:
    values = sorted(
        {_require_sha(value, "expectedValueSha256") for value in expected_value_sha256s}
    )
    if not values:
        raise ValueError("structural policy requires expected values")
    return _sha256(
        {
            "schema": "hwpx.practice-structural-policy/v1",
            "startArtifactSha256": _require_sha(
                expected_start_sha256, "expectedStartSha256"
            ),
            "expectedRowSha256": _require_sha(
                expected_row_sha256, "expectedRowSha256"
            ),
            "expectedValueSha256s": values,
        }
    )


def form_differential_oracle_provenance_sha256(*, backend: str) -> str:
    """Identify the closed differential verifier/backend contract."""

    backend_name = str(backend)
    if not _FORM_RENDER_BACKEND_PATTERN.fullmatch(backend_name):
        raise ValueError("form render backend is invalid")
    return _sha256(
        {
            "schema": "hwpx.practice-form-differential-provenance/v1",
            "backend": backend_name,
            "verifier": "hwpx.form_fit.wordbox.verify_form_fill_differential",
            "contract": "blank-filled-overflow-overlap-layout/v1",
        }
    )


def form_differential_receipt_sha256(value: Mapping[str, Any]) -> str:
    """Hash the semantic content of one frozen differential receipt."""

    return _content_hash(
        _require_mapping(value, "form differential receipt"), "receiptSha256"
    )


def serialize_form_differential_receipt(value: Mapping[str, Any]) -> bytes:
    """Return the unique content-addressed byte representation for an asset."""

    return _canonical_bytes(validate_form_differential_receipt(value))


def form_verifier_policy_sha256(
    *,
    target_policy_sha256: str,
    differential_receipt_asset_sha256: str,
) -> str:
    """Bind cell targets and one exact frozen differential receipt asset."""

    return _sha256(
        {
            "schema": "hwpx.practice-form-verifier-policy/v1",
            "targetPolicySha256": _require_sha(
                target_policy_sha256, "targetPolicySha256"
            ),
            "differentialReceiptAssetSha256": _require_sha(
                differential_receipt_asset_sha256,
                "differentialReceiptAssetSha256",
            ),
        }
    )


def build_form_differential_receipt(
    blank_path: str | Path,
    output_path: str | Path,
    *,
    oracle: object,
) -> dict[str, Any]:
    """Measure and freeze a real blank→filled Hancom differential verdict.

    The API accepts artifacts and an oracle, never caller-supplied verdict
    booleans.  Both artifacts are snapshotted before the renderer sees them.
    Unavailable or incomplete rendering is rejected instead of producing a
    receipt that could later be mistaken for a pass.
    """

    if oracle is None:
        raise ValueError("a concrete form render oracle is required")
    backend = f"{type(oracle).__module__}.{type(oracle).__name__}"
    if not _FORM_RENDER_BACKEND_PATTERN.fullmatch(backend):
        raise ValueError("form render backend is invalid")
    blank_payload = _read_hwpx_snapshot(blank_path)
    output_payload = _read_hwpx_snapshot(output_path)
    from hwpx.form_fit.wordbox import verify_form_fill_differential

    with ExitStack() as stack:
        blank_snapshot = stack.enter_context(
            _strict_snapshot_path(blank_payload, suffix=".hwpx")
        )
        output_snapshot = stack.enter_context(
            _strict_snapshot_path(output_payload, suffix=".hwpx")
        )
        verdict = verify_form_fill_differential(
            str(blank_snapshot), str(output_snapshot), oracle=oracle
        )
    if verdict.render_checked is not True:
        raise ValueError("form differential render was not checked")
    if not isinstance(verdict.layout_stable, bool):
        raise ValueError("form differential layout verdict is incomplete")
    receipt: dict[str, Any] = {
        "schema": FORM_DIFFERENTIAL_RECEIPT_SCHEMA,
        "blankArtifact": {
            "sha256": hashlib.sha256(blank_payload).hexdigest(),
            "bytes": len(blank_payload),
        },
        "outputArtifact": {
            "sha256": hashlib.sha256(output_payload).hexdigest(),
            "bytes": len(output_payload),
        },
        "backend": backend,
        "oracleProvenanceSha256": form_differential_oracle_provenance_sha256(
            backend=backend
        ),
        "renderChecked": True,
        "overflowChecked": verdict.overflow_checked is True,
        "overflowDetected": verdict.overflow_detected is True,
        "overlapDetected": verdict.overlap_detected is True,
        "layoutStable": verdict.layout_stable,
    }
    receipt["verdict"] = (
        "passed"
        if receipt["overflowChecked"]
        and not receipt["overflowDetected"]
        and not receipt["overlapDetected"]
        and receipt["layoutStable"]
        else "failed"
    )
    assert_receipt_safe(receipt)
    receipt["receiptSha256"] = form_differential_receipt_sha256(receipt)
    return validate_form_differential_receipt(receipt)


def validate_form_differential_receipt(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact artifact/provenance/verdict bindings fail closed."""

    raw = dict(_require_mapping(value, "form differential receipt"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {
            "schema",
            "blankArtifact",
            "outputArtifact",
            "backend",
            "oracleProvenanceSha256",
            "renderChecked",
            "overflowChecked",
            "overflowDetected",
            "overlapDetected",
            "layoutStable",
            "verdict",
            "receiptSha256",
        },
        "form differential receipt",
    )
    if raw["schema"] != FORM_DIFFERENTIAL_RECEIPT_SCHEMA:
        raise ValueError("unsupported form differential receipt schema")
    for field in ("blankArtifact", "outputArtifact"):
        artifact = dict(_require_mapping(raw[field], field))
        _require_exact_keys(artifact, {"sha256", "bytes"}, field)
        size = artifact["bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("form differential artifact bytes must be positive")
        raw[field] = {
            "sha256": _require_sha(artifact["sha256"], f"{field}.sha256"),
            "bytes": size,
        }
    backend = str(raw["backend"])
    if not _FORM_RENDER_BACKEND_PATTERN.fullmatch(backend):
        raise ValueError("form render backend is invalid")
    raw["backend"] = backend
    if _require_sha(
        raw["oracleProvenanceSha256"], "oracleProvenanceSha256"
    ) != form_differential_oracle_provenance_sha256(backend=backend):
        raise ValueError("form render provenance mismatch")
    for field in (
        "renderChecked",
        "overflowChecked",
        "overflowDetected",
        "overlapDetected",
        "layoutStable",
    ):
        if not isinstance(raw[field], bool):
            raise ValueError(f"form differential {field} must be boolean")
    if raw["renderChecked"] is not True:
        raise ValueError("form differential receipt must be render checked")
    expected_verdict = (
        "passed"
        if raw["overflowChecked"]
        and not raw["overflowDetected"]
        and not raw["overlapDetected"]
        and raw["layoutStable"]
        else "failed"
    )
    if raw["verdict"] != expected_verdict:
        raise ValueError("form differential verdict mismatch")
    if _require_sha(raw["receiptSha256"], "receiptSha256") != (
        form_differential_receipt_sha256(raw)
    ):
        raise ValueError("form differential receipt hash mismatch")
    return raw


def exam_verifier_policy_sha256(
    *,
    input_artifact_sha256: str,
    oracle_provenance_sha256: str,
    oracle_authentication_key_id: str,
) -> str:
    key_id = str(oracle_authentication_key_id)
    if not _EXAM_ORACLE_KEY_ID_PATTERN.fullmatch(key_id):
        raise ValueError("exam oracle authentication key ID is invalid")
    return _sha256(
        {
            "schema": "hwpx.practice-exam-policy/v1",
            "inputArtifactSha256": _require_sha(
                input_artifact_sha256, "inputArtifactSha256"
            ),
            "oracleProvenanceSha256": _require_sha(
                oracle_provenance_sha256, "oracleProvenanceSha256"
            ),
            "oracleAuthenticationKeyId": key_id,
        }
    )


def official_verifier_policy_sha256(*, document_type: str) -> str:
    """Freeze the official-document lint profile without exposing its label."""

    normalized = str(document_type).strip()
    if not normalized or len(normalized) > 64:
        raise ValueError("official document type must be a bounded non-empty label")
    return _sha256(
        {
            "schema": "hwpx.practice-official-policy/v1",
            "documentTypeSha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        }
    )


def authoring_verifier_policy_sha256(
    *,
    plan: Mapping[str, Any] | None,
    style_reference_sha256: str | None,
) -> str:
    """Freeze plan content and style-reference presence/hash as one opaque digest."""

    style_present = style_reference_sha256 is not None
    style_digest = (
        _require_sha(style_reference_sha256, "styleReferenceSha256")
        if style_present
        else None
    )
    return _sha256(
        {
            "schema": "hwpx.practice-authoring-policy/v1",
            "planPresent": plan is not None,
            "planSha256": _sha256(dict(plan)) if plan is not None else None,
            "styleReferencePresent": style_present,
            "styleReferenceSha256": style_digest,
        }
    )


def _exam_oracle_receipt_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(_require_mapping(value, "exam oracle receipt"))
    payload.pop("receiptSha256", None)
    payload.pop("auth", None)
    assert_receipt_safe(payload)
    return _sha256(payload)


def _exam_oracle_authentication_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("exam oracle authentication key must contain at least 32 bytes")
    return value


def exam_oracle_authentication_key_id(oracle_authentication_key: bytes) -> str:
    """Return a key ID namespaced separately from evaluator authentication."""

    key = _exam_oracle_authentication_key(oracle_authentication_key)
    digest = hashlib.sha256(b"hwpx.practice-exam-oracle/v1\0" + key).hexdigest()
    return f"EOK-{digest[:20].upper()}"


def _abstention_inventory_authentication_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError(
            "abstention inventory authentication key must contain at least 32 bytes"
        )
    return value


def abstention_inventory_authentication_key_id(authentication_key: bytes) -> str:
    key = _abstention_inventory_authentication_key(authentication_key)
    digest = hashlib.sha256(b"hwpx.practice-abstention-inventory/v1\0" + key).hexdigest()
    return f"AOK-{digest[:20].upper()}"


def must_abstain_verifier_policy_sha256(
    *, inventory_authentication_key_id: str
) -> str:
    key_id = str(inventory_authentication_key_id)
    if not _ABSTENTION_INVENTORY_KEY_ID_PATTERN.fullmatch(key_id):
        raise ValueError("abstention inventory authentication key ID is invalid")
    return _sha256(
        {
            "schema": "hwpx.practice-must-abstain-policy/v1",
            "inventoryAuthenticationKeyId": key_id,
        }
    )


def _exam_measurement_from_adapter(
    oracle_adapter: object, input_path: Path, output_path: Path
) -> tuple[str, dict[str, Any]]:
    measure = getattr(oracle_adapter, "measure_exam", None)
    if not callable(measure):
        raise ValueError("exam oracle adapter must expose measure_exam")
    provenance_sha = _require_sha(
        getattr(oracle_adapter, "provenance_sha256", None),
        "oracleAdapter.provenanceSha256",
    )
    raw = dict(_require_mapping(measure(input_path, output_path), "exam measurement"))
    _require_exact_keys(
        raw,
        {
            "renderChecked",
            "questionSplits",
            "placeholdersOk",
            "examInvariantsPass",
        },
        "exam measurement",
    )
    for key in ("renderChecked", "examInvariantsPass"):
        if not isinstance(raw[key], bool):
            raise ValueError(f"exam measurement {key} must be boolean")
    if raw["questionSplits"] is not None and (
        isinstance(raw["questionSplits"], bool)
        or not isinstance(raw["questionSplits"], int)
        or raw["questionSplits"] < 0
    ):
        raise ValueError(
            "exam measurement questionSplits must be null or a non-negative integer"
        )
    if raw["placeholdersOk"] is not None and not isinstance(
        raw["placeholdersOk"], bool
    ):
        raise ValueError("exam measurement placeholdersOk must be null or boolean")
    return provenance_sha, raw


def build_exam_oracle_receipt(
    input_path: str | Path,
    output_path: str | Path,
    oracle_adapter: object,
    *,
    oracle_authentication_key: bytes,
) -> dict[str, Any]:
    """Seal measurements produced inside a trusted, authenticated oracle boundary.

    The production API deliberately accepts no caller-supplied measurement mapping
    or verdict booleans.  The adapter measures evaluator-owned snapshot paths and
    the oracle-owned key authenticates the resulting receipt.
    """

    key = _exam_oracle_authentication_key(oracle_authentication_key)
    input_payload = _read_bounded_snapshot(input_path)
    output_payload = _read_bounded_snapshot(output_path)
    with ExitStack() as stack:
        input_snapshot = stack.enter_context(
            _strict_snapshot_path(input_payload, suffix=Path(input_path).suffix or ".bin")
        )
        output_snapshot = stack.enter_context(
            _strict_snapshot_path(output_payload, suffix=Path(output_path).suffix or ".bin")
        )
        provenance_sha, measurement = _exam_measurement_from_adapter(
            oracle_adapter, input_snapshot, output_snapshot
        )
    receipt: dict[str, Any] = {
        "schema": EXAM_ORACLE_RECEIPT_SCHEMA,
        "inputArtifactSha256": hashlib.sha256(input_payload).hexdigest(),
        "outputArtifactSha256": hashlib.sha256(output_payload).hexdigest(),
        "oracleProvenanceSha256": provenance_sha,
        **measurement,
    }
    assert_receipt_safe(receipt)
    receipt["receiptSha256"] = _exam_oracle_receipt_sha256(receipt)
    receipt["auth"] = {
        "schema": EXAM_ORACLE_AUTH_SCHEMA,
        "algorithm": "hmac-sha256",
        "keyId": exam_oracle_authentication_key_id(key),
        "macSha256": hmac.new(
            key, _canonical_bytes(receipt), hashlib.sha256
        ).hexdigest(),
    }
    return validate_exam_oracle_receipt(
        receipt, oracle_authentication_key=key
    )


def validate_exam_oracle_receipt(
    value: Mapping[str, Any], *, oracle_authentication_key: bytes
) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "exam oracle receipt"))
    key = _exam_oracle_authentication_key(oracle_authentication_key)
    auth = dict(_require_mapping(raw.get("auth"), "exam oracle auth"))
    _require_exact_keys(
        auth,
        {"schema", "algorithm", "keyId", "macSha256"},
        "exam oracle auth",
    )
    if (
        auth.get("schema") != EXAM_ORACLE_AUTH_SCHEMA
        or auth.get("algorithm") != "hmac-sha256"
        or auth.get("keyId") != exam_oracle_authentication_key_id(key)
    ):
        raise ValueError("exam oracle authentication key mismatch")
    unsigned = dict(raw)
    unsigned.pop("auth", None)
    expected_mac = hmac.new(
        key, _canonical_bytes(unsigned), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(
        _require_sha(auth.get("macSha256"), "auth.macSha256"), expected_mac
    ):
        raise ValueError("exam oracle authentication failed")
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {
            "schema",
            "inputArtifactSha256",
            "outputArtifactSha256",
            "oracleProvenanceSha256",
            "renderChecked",
            "questionSplits",
            "placeholdersOk",
            "examInvariantsPass",
            "receiptSha256",
            "auth",
        },
        "exam oracle receipt",
    )
    if raw["schema"] != EXAM_ORACLE_RECEIPT_SCHEMA:
        raise ValueError("unsupported exam oracle receipt schema")
    for key in (
        "inputArtifactSha256",
        "outputArtifactSha256",
        "oracleProvenanceSha256",
        "receiptSha256",
    ):
        raw[key] = _require_sha(raw[key], key)
    for key in ("renderChecked", "examInvariantsPass"):
        if not isinstance(raw[key], bool):
            raise ValueError(f"exam oracle {key} must be boolean")
    if raw["questionSplits"] is not None and (
        isinstance(raw["questionSplits"], bool)
        or not isinstance(raw["questionSplits"], int)
        or raw["questionSplits"] < 0
    ):
        raise ValueError("exam questionSplits must be null or a non-negative integer")
    if raw["placeholdersOk"] is not None and not isinstance(raw["placeholdersOk"], bool):
        raise ValueError("exam placeholdersOk must be null or boolean")
    if raw["receiptSha256"] != _exam_oracle_receipt_sha256(raw):
        raise ValueError("exam oracle receipt hash mismatch")
    raw["auth"] = auth
    return raw


def form_target_policy_sha256(value: Mapping[str, Any]) -> str:
    return _content_hash(_require_mapping(value, "form target policy"), "policySha256")


def build_form_target_policy(
    *,
    blank_artifact_sha256: str,
    bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Freeze opaque cell coordinates to blank/expected synthetic value hashes."""

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(bindings):
        row = dict(_require_mapping(item, f"form bindings[{index}]"))
        _require_exact_keys(
            row,
            {
                "sectionIndex",
                "tableIndex",
                "row",
                "col",
                "blankValueSha256",
                "expectedValueSha256",
            },
            f"form bindings[{index}]",
        )
        coordinates: dict[str, Any] = {}
        for key in ("sectionIndex", "tableIndex", "row", "col"):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"form binding {key} must be a non-negative integer")
            coordinates[key] = value
        blank_sha = _require_sha(row["blankValueSha256"], "blankValueSha256")
        expected_sha = _require_sha(row["expectedValueSha256"], "expectedValueSha256")
        if blank_sha == expected_sha:
            raise ValueError("form target expected value must differ from the blank")
        target_id = f"TGT-{_sha256({**coordinates, 'blank': blank_sha, 'expected': expected_sha})[:20].upper()}"
        normalized.append(
            {
                "targetId": target_id,
                **coordinates,
                "blankValueSha256": blank_sha,
                "expectedValueSha256": expected_sha,
            }
        )
    if not normalized:
        raise ValueError("form target policy requires at least one binding")
    normalized.sort(
        key=lambda item: (
            item["sectionIndex"], item["tableIndex"], item["row"], item["col"]
        )
    )
    policy: dict[str, Any] = {
        "schema": FORM_TARGET_POLICY_SCHEMA,
        "blankArtifactSha256": _require_sha(
            blank_artifact_sha256, "blankArtifactSha256"
        ),
        "bindings": normalized,
    }
    assert_receipt_safe(policy)
    policy["policySha256"] = form_target_policy_sha256(policy)
    return validate_form_target_policy(policy)


def validate_form_target_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(_require_mapping(value, "form target policy"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {"schema", "blankArtifactSha256", "bindings", "policySha256"},
        "form target policy",
    )
    if raw["schema"] != FORM_TARGET_POLICY_SCHEMA:
        raise ValueError("unsupported form target policy schema")
    raw["blankArtifactSha256"] = _require_sha(
        raw["blankArtifactSha256"], "blankArtifactSha256"
    )
    rows = raw["bindings"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("form target policy requires bindings")
    normalized: list[dict[str, Any]] = []
    seen_coordinates: set[tuple[int, int, int, int]] = set()
    seen_targets: set[str] = set()
    for index, item in enumerate(rows):
        row = dict(_require_mapping(item, f"form bindings[{index}]"))
        _require_exact_keys(
            row,
            {
                "targetId",
                "sectionIndex",
                "tableIndex",
                "row",
                "col",
                "blankValueSha256",
                "expectedValueSha256",
            },
            f"form bindings[{index}]",
        )
        coords: list[int] = []
        for key in ("sectionIndex", "tableIndex", "row", "col"):
            coordinate = row[key]
            if isinstance(coordinate, bool) or not isinstance(coordinate, int) or coordinate < 0:
                raise ValueError("form target coordinates must be non-negative integers")
            coords.append(coordinate)
        coordinate_key = tuple(coords)
        blank_sha = _require_sha(row["blankValueSha256"], "blankValueSha256")
        expected_sha = _require_sha(row["expectedValueSha256"], "expectedValueSha256")
        expected_id = f"TGT-{_sha256({'sectionIndex': coords[0], 'tableIndex': coords[1], 'row': coords[2], 'col': coords[3], 'blank': blank_sha, 'expected': expected_sha})[:20].upper()}"
        if row["targetId"] != expected_id or blank_sha == expected_sha:
            raise ValueError("form target ID/value binding is invalid")
        if coordinate_key in seen_coordinates or expected_id in seen_targets:
            raise ValueError("form target bindings must be unique")
        seen_coordinates.add(coordinate_key)
        seen_targets.add(expected_id)
        normalized.append(
            {
                "targetId": expected_id,
                "sectionIndex": coords[0],
                "tableIndex": coords[1],
                "row": coords[2],
                "col": coords[3],
                "blankValueSha256": blank_sha,
                "expectedValueSha256": expected_sha,
            }
        )
    expected_order = sorted(
        normalized,
        key=lambda item: (
            item["sectionIndex"], item["tableIndex"], item["row"], item["col"]
        ),
    )
    if normalized != expected_order:
        raise ValueError("form target bindings must be canonically ordered")
    raw["bindings"] = normalized
    if _require_sha(raw["policySha256"], "policySha256") != form_target_policy_sha256(raw):
        raise ValueError("form target policy hash mismatch")
    return raw


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


def _require_sha(value: object, name: str) -> str:
    digest = str(value or "")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return digest


def _content_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    assert_receipt_safe(payload)
    return _sha256(payload)


def _verifier_id(
    scenario_sha256: str, artifact_sha256: str, verifier_family: str
) -> str:
    token = _sha256(
        {
            "scenarioSha256": scenario_sha256,
            "artifactSha256": artifact_sha256,
            "verifierFamily": verifier_family,
        }
    )[:20].upper()
    return f"VER-{token}"


def _default_verifier_policy_sha256(verifier_family: str) -> str:
    return _sha256(
        {"schema": "hwpx.practice-domain-default-policy/v1", "verifierFamily": verifier_family}
    )


def _bound_verifier_families(task_kind: str, family: str) -> tuple[str, ...]:
    primary = _TASK_VERIFIER[task_kind]
    # An abstention is graded solely by the frozen no-mutation/decision gate.
    # Running mutation-dependent family checks would turn a correct refusal into
    # missing evidence.
    if primary == "must_abstain":
        return (primary,)
    result = [primary]
    if family in _EXAM_FAMILY_CODES and "exam" not in result:
        result.append("exam")
    if family in _OFFICIAL_FAMILY_CODES and "official_document" not in result:
        result.append("official_document")
    return tuple(result)


def domain_requirement_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical content hash of a domain requirement."""

    return _content_hash(_require_mapping(value, "domain requirement"), "requirementSha256")


def build_domain_requirement(
    *,
    scenario_sha256: str,
    artifact_sha256: str,
    task_kind: str,
    family: str,
    verifier_policy_sha256s: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Bind one scenario/output pair to all mandatory domain verifiers."""

    scenario_digest = _require_sha(scenario_sha256, "scenarioSha256")
    artifact_digest = _require_sha(artifact_sha256, "artifactSha256")
    if task_kind not in TASK_KINDS:
        raise ValueError("unsupported taskKind")
    if not _FAMILY_CODE_PATTERN.fullmatch(family):
        raise ValueError("family must be a closed code")
    families = _bound_verifier_families(task_kind, family)
    policies = dict(verifier_policy_sha256s or {})
    if not set(policies).issubset(families):
        raise ValueError("verifier policy hashes contain an unbound verifier family")
    verifiers = [
        {
            "verifierFamily": verifier_family,
            "verifierId": _verifier_id(
                scenario_digest, artifact_digest, verifier_family
            ),
            "requiredChecks": list(VERIFIER_CHECKS[verifier_family]),
            "policySha256": _require_sha(
                policies.get(
                    verifier_family, _default_verifier_policy_sha256(verifier_family)
                ),
                f"{verifier_family}.policySha256",
            ),
        }
        for verifier_family in families
    ]
    result: dict[str, Any] = {
        "schema": DOMAIN_REQUIREMENT_SCHEMA,
        "scenarioSha256": scenario_digest,
        "artifactSha256": artifact_digest,
        "taskKind": task_kind,
        "family": family,
        "verifiers": verifiers,
        "expectedAbstention": task_kind == "must_abstain",
    }
    assert_receipt_safe(result)
    result["requirementSha256"] = domain_requirement_sha256(result)
    return validate_domain_requirement(result)


def validate_domain_requirement(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize a frozen domain requirement."""

    raw = dict(_require_mapping(value, "domain requirement"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {
            "schema",
            "scenarioSha256",
            "artifactSha256",
            "taskKind",
            "family",
            "verifiers",
            "expectedAbstention",
            "requirementSha256",
        },
        "domain requirement",
    )
    if raw["schema"] != DOMAIN_REQUIREMENT_SCHEMA:
        raise ValueError("unsupported domain requirement schema")
    raw["scenarioSha256"] = _require_sha(raw["scenarioSha256"], "scenarioSha256")
    raw["artifactSha256"] = _require_sha(raw["artifactSha256"], "artifactSha256")
    task_kind = str(raw["taskKind"])
    family = str(raw["family"])
    if task_kind not in TASK_KINDS:
        raise ValueError("unsupported taskKind")
    if not _FAMILY_CODE_PATTERN.fullmatch(family):
        raise ValueError("family must be a closed code")
    expected_families = _bound_verifier_families(task_kind, family)
    rows = raw["verifiers"]
    if not isinstance(rows, list) or len(rows) != len(expected_families):
        raise ValueError("domain verifier coverage is incomplete")
    normalized: list[dict[str, Any]] = []
    for index, (item, expected_family) in enumerate(zip(rows, expected_families)):
        row = dict(_require_mapping(item, f"verifiers[{index}]"))
        _require_exact_keys(
            row,
            {"verifierFamily", "verifierId", "requiredChecks", "policySha256"},
            f"verifiers[{index}]",
        )
        if row["verifierFamily"] != expected_family:
            raise ValueError("domain verifier order or family was altered")
        expected_id = _verifier_id(
            raw["scenarioSha256"], raw["artifactSha256"], expected_family
        )
        if not _VERIFIER_ID_PATTERN.fullmatch(str(row["verifierId"])) or row["verifierId"] != expected_id:
            raise ValueError("verifierId is not content-bound to the requirement")
        expected_checks = list(VERIFIER_CHECKS[expected_family])
        if row["requiredChecks"] != expected_checks:
            raise ValueError("required domain checks were altered")
        normalized.append(
            {
                "verifierFamily": expected_family,
                "verifierId": expected_id,
                "requiredChecks": expected_checks,
                "policySha256": _require_sha(
                    row["policySha256"], f"verifiers[{index}].policySha256"
                ),
            }
        )
    raw["verifiers"] = normalized
    if raw["expectedAbstention"] is not (task_kind == "must_abstain"):
        raise ValueError("expectedAbstention does not match taskKind")
    expected_hash = domain_requirement_sha256(raw)
    if _require_sha(raw["requirementSha256"], "requirementSha256") != expected_hash:
        raise ValueError("requirementSha256 does not match canonical content")
    return raw


def domain_requirement_policy_projection(
    requirement: Mapping[str, Any],
) -> dict[str, Any]:
    """Project frozen domain policy without the not-yet-produced output hash."""

    frozen = validate_domain_requirement(requirement)
    projection: dict[str, Any] = {
        "schema": DOMAIN_POLICY_PROJECTION_SCHEMA,
        "scenarioSha256": frozen["scenarioSha256"],
        "taskKind": frozen["taskKind"],
        "family": frozen["family"],
        "expectedAbstention": frozen["expectedAbstention"],
        "verifiers": [
            {
                "verifierFamily": row["verifierFamily"],
                "requiredChecks": list(row["requiredChecks"]),
                "policySha256": row["policySha256"],
            }
            for row in frozen["verifiers"]
        ],
    }
    assert_receipt_safe(projection)
    projection["policySha256"] = _sha256(projection)
    return projection


def _normalize_check_status(value: object) -> str:
    if value is True:
        return "passed"
    if value is False:
        return "failed"
    if value is None:
        return "unverified"
    status = str(value)
    if status not in CHECK_STATUSES:
        raise ValueError("domain check status is not closed")
    return status


def _verifier_policy_sha256(
    requirement: Mapping[str, Any], verifier_family: str
) -> str:
    frozen = validate_domain_requirement(requirement)
    for row in frozen["verifiers"]:
        if row["verifierFamily"] == verifier_family:
            return str(row["policySha256"])
    raise ValueError("verifier family is not bound by the requirement")


def _evidence_status(checks: Sequence[Mapping[str, str]]) -> str:
    statuses = {str(item["status"]) for item in checks}
    if "failed" in statuses:
        return "failed"
    if statuses & {"unverified", "not_run"}:
        return "unverified"
    return "passed"


def domain_evidence_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical content hash of one verifier receipt."""

    return _content_hash(_require_mapping(value, "domain evidence"), "evidenceSha256")


def build_domain_evidence(
    requirement: Mapping[str, Any],
    *,
    verifier_family: str,
    checks: Mapping[str, object],
    observed_terminal_state: str,
    verifier_version: str = "practice-domain/v1",
    source_evidence: Mapping[str, Any] | None = None,
    oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Build closed evidence from an independent verifier's measured checks.

    Boolean values are shorthand for passed/failed and ``None`` means
    unverified.  No finding text is accepted.
    """

    frozen = validate_domain_requirement(requirement)
    bindings = {
        row["verifierFamily"]: row for row in frozen["verifiers"]
    }
    if verifier_family not in bindings:
        raise ValueError("verifier family is not required by this scenario")
    if observed_terminal_state not in TERMINAL_RUN_STATES:
        raise ValueError("observed terminal state is not closed")
    if not _VERSION_PATTERN.fullmatch(verifier_version):
        raise ValueError("verifierVersion must be exact and closed")
    required = tuple(bindings[verifier_family]["requiredChecks"])
    if set(checks) != set(required):
        raise ValueError("domain evidence check coverage is not exact")
    normalized_checks = [
        {"code": code, "status": _normalize_check_status(checks[code])}
        for code in required
    ]
    if verifier_family == "must_abstain":
        actual = (
            "passed"
            if observed_terminal_state in ABSTENTION_TERMINAL_STATES
            else "failed"
        )
        if normalized_checks[0]["status"] != actual:
            raise ValueError("terminal_state_allowed contradicts the observed terminal state")
    elif observed_terminal_state != "completed" and all(
        item["status"] == "passed" for item in normalized_checks
    ):
        # Mutation-dependent evidence can be technically clean while the run
        # itself refused, failed, or remained unverified.  It must not become a
        # passed standalone domain bundle for that unsuccessful run.
        normalized_checks[0]["status"] = "unverified"
    status = _evidence_status(normalized_checks)
    result: dict[str, Any] = {
        "schema": DOMAIN_EVIDENCE_SCHEMA,
        "requirementSha256": frozen["requirementSha256"],
        "scenarioSha256": frozen["scenarioSha256"],
        "artifactSha256": frozen["artifactSha256"],
        "verifierFamily": verifier_family,
        "verifierId": bindings[verifier_family]["verifierId"],
        "verifierPolicySha256": bindings[verifier_family]["policySha256"],
        "verifierVersion": verifier_version,
        "observedTerminalState": observed_terminal_state,
        "status": status,
        "reasonCode": f"DOMAIN_VERIFIER_{status.upper()}",
        "checks": normalized_checks,
        "sourceEvidence": dict(source_evidence) if source_evidence is not None else None,
    }
    assert_receipt_safe(result)
    result["evidenceSha256"] = domain_evidence_sha256(result)
    return validate_domain_evidence(
        result,
        oracle_authentication_keys=oracle_authentication_keys,
    )


def _validate_domain_source_evidence(
    value: object,
    *,
    verifier_family: str,
    artifact_sha256: str,
    oracle_authentication_keys: Mapping[str, bytes] | None,
) -> dict[str, Any] | None:
    if verifier_family not in {"exam", "form_fill", "must_abstain"}:
        if value is not None:
            raise ValueError(
                "only form, exam, or must-abstain evidence may carry source evidence"
            )
        return None
    if verifier_family == "form_fill":
        if value is None:
            return None
        raw = dict(_require_mapping(value, "form differential source evidence"))
        _require_exact_keys(
            raw,
            {
                "schema",
                "assetSha256",
                "receiptSha256",
                "targetPolicySha256",
                "receipt",
            },
            "form differential source evidence",
        )
        if raw["schema"] != FORM_DIFFERENTIAL_SOURCE_EVIDENCE_SCHEMA:
            raise ValueError("unsupported form differential source evidence schema")
        receipt = validate_form_differential_receipt(
            _require_mapping(raw["receipt"], "form differential source receipt")
        )
        asset_sha = _require_sha(raw["assetSha256"], "sourceEvidence.assetSha256")
        target_policy_sha = _require_sha(
            raw["targetPolicySha256"], "sourceEvidence.targetPolicySha256"
        )
        receipt_sha = _require_sha(
            raw["receiptSha256"], "sourceEvidence.receiptSha256"
        )
        if (
            receipt_sha != receipt["receiptSha256"]
            or receipt["outputArtifact"]["sha256"] != artifact_sha256
        ):
            raise ValueError("form differential source evidence binding mismatch")
        return {
            "schema": FORM_DIFFERENTIAL_SOURCE_EVIDENCE_SCHEMA,
            "assetSha256": asset_sha,
            "receiptSha256": receipt_sha,
            "targetPolicySha256": target_policy_sha,
            "receipt": receipt,
        }
    if verifier_family == "must_abstain":
        if value is None:
            # Legacy/raw boolean evidence may remain structurally inspectable,
            # but production evaluator combine rejects a passed verifier without
            # the exact terminal-receipt reference.
            return None
        from .run import validate_run_receipt

        raw = dict(_require_mapping(value, "must-abstain source evidence"))
        _require_exact_keys(
            raw,
            {
                "schema",
                "receiptSha256",
                "scenarioId",
                "terminalReason",
                "workflowEventsSha256",
                "receiptOutputArtifactsSha256",
                "measuredOutputInventorySha256",
                "measuredOutputInventory",
                "inventoryAuthenticationKeyId",
                "inventoryAuth",
                "receipt",
            },
            "must-abstain source evidence",
        )
        if raw["schema"] != DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA:
            raise ValueError("unsupported terminal source evidence schema")
        receipt = validate_run_receipt(
            _require_mapping(raw["receipt"], "must-abstain terminal receipt")
        )
        inventory_value = raw["measuredOutputInventory"]
        if not isinstance(inventory_value, list):
            raise ValueError("measured output inventory must be a list")
        inventory: list[dict[str, Any]] = []
        for index, item in enumerate(inventory_value):
            row = dict(_require_mapping(item, f"measuredOutputInventory[{index}]"))
            _require_exact_keys(
                row,
                {"sha256", "bytes"},
                f"measuredOutputInventory[{index}]",
            )
            size = row["bytes"]
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError("measured output inventory bytes must be non-negative")
            inventory.append(
                {
                    "sha256": _require_sha(row["sha256"], "inventory.sha256"),
                    "bytes": size,
                }
            )
        if inventory != sorted(inventory, key=lambda row: (row["sha256"], row["bytes"])):
            raise ValueError("measured output inventory must be canonically ordered")
        key_id = str(raw["inventoryAuthenticationKeyId"])
        if not _ABSTENTION_INVENTORY_KEY_ID_PATTERN.fullmatch(key_id):
            raise ValueError("abstention inventory authentication key ID is invalid")
        if oracle_authentication_keys is None or key_id not in oracle_authentication_keys:
            raise ValueError(
                "abstention inventory authentication key is required for evidence validation"
            )
        key = _abstention_inventory_authentication_key(
            oracle_authentication_keys[key_id]
        )
        if abstention_inventory_authentication_key_id(key) != key_id:
            raise ValueError("abstention inventory authentication key mismatch")
        auth = dict(_require_mapping(raw["inventoryAuth"], "inventory auth"))
        _require_exact_keys(
            auth,
            {"schema", "algorithm", "keyId", "macSha256"},
            "inventory auth",
        )
        if (
            auth["schema"] != ABSTENTION_INVENTORY_AUTH_SCHEMA
            or auth["algorithm"] != "hmac-sha256"
            or auth["keyId"] != key_id
        ):
            raise ValueError("unsupported abstention inventory authentication")
        inventory_auth_payload = {
            "schema": DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA,
            "receiptSha256": raw["receiptSha256"],
            "scenarioId": raw["scenarioId"],
            "measuredOutputInventorySha256": raw[
                "measuredOutputInventorySha256"
            ],
            "measuredOutputInventory": inventory,
        }
        expected_mac = hmac.new(
            key, _canonical_bytes(inventory_auth_payload), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(
            _require_sha(auth["macSha256"], "inventoryAuth.macSha256"),
            expected_mac,
        ):
            raise ValueError("abstention inventory authentication failed")
        output_artifacts = sorted(
            (
                {
                    "artifactId": item["artifactId"],
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                }
                for item in receipt["artifacts"]
                if item["role"] == "output"
            ),
            key=lambda row: row["artifactId"],
        )
        if (
            _require_sha(raw["receiptSha256"], "sourceEvidence.receiptSha256")
            != receipt["receiptSha256"]
            or raw["scenarioId"] != receipt["scenarioId"]
            or raw["terminalReason"] != receipt["terminalReason"]
            or _require_sha(
                raw["workflowEventsSha256"], "sourceEvidence.workflowEventsSha256"
            )
            != _sha256(receipt["workflowEvents"])
            or _require_sha(
                raw["receiptOutputArtifactsSha256"],
                "sourceEvidence.receiptOutputArtifactsSha256",
            )
            != _sha256(output_artifacts)
            or _require_sha(
                raw["measuredOutputInventorySha256"],
                "sourceEvidence.measuredOutputInventorySha256",
            )
            != _sha256(inventory)
        ):
            raise ValueError("must-abstain source evidence binding mismatch")
        return {
            "schema": DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA,
            "receiptSha256": receipt["receiptSha256"],
            "scenarioId": receipt["scenarioId"],
            "terminalReason": receipt["terminalReason"],
            "workflowEventsSha256": _sha256(receipt["workflowEvents"]),
            "receiptOutputArtifactsSha256": _sha256(output_artifacts),
            "measuredOutputInventorySha256": _sha256(inventory),
            "measuredOutputInventory": inventory,
            "inventoryAuthenticationKeyId": key_id,
            "inventoryAuth": auth,
            "receipt": receipt,
        }
    raw = dict(_require_mapping(value, "exam source evidence"))
    _require_exact_keys(
        raw,
        {"schema", "receiptSha256", "authenticationKeyId", "receipt"},
        "exam source evidence",
    )
    if raw["schema"] != DOMAIN_SOURCE_EVIDENCE_SCHEMA:
        raise ValueError("unsupported domain source evidence schema")
    receipt_sha = _require_sha(raw["receiptSha256"], "sourceEvidence.receiptSha256")
    key_id = str(raw["authenticationKeyId"])
    if not _EXAM_ORACLE_KEY_ID_PATTERN.fullmatch(key_id):
        raise ValueError("exam source authentication key ID is invalid")
    if oracle_authentication_keys is None or key_id not in oracle_authentication_keys:
        raise ValueError("exam oracle authentication key is required for evidence validation")
    receipt = validate_exam_oracle_receipt(
        _require_mapping(raw["receipt"], "exam source receipt"),
        oracle_authentication_key=oracle_authentication_keys[key_id],
    )
    if (
        receipt["receiptSha256"] != receipt_sha
        or receipt["auth"]["keyId"] != key_id
        or receipt["outputArtifactSha256"] != artifact_sha256
    ):
        raise ValueError("exam source evidence binding mismatch")
    return {
        "schema": DOMAIN_SOURCE_EVIDENCE_SCHEMA,
        "receiptSha256": receipt_sha,
        "authenticationKeyId": key_id,
        "receipt": receipt,
    }


def validate_domain_evidence(
    value: Mapping[str, Any],
    *,
    oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Validate a content-bound verifier receipt without trusting its status."""

    raw = dict(_require_mapping(value, "domain evidence"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {
            "schema",
            "requirementSha256",
            "scenarioSha256",
            "artifactSha256",
            "verifierFamily",
            "verifierId",
            "verifierPolicySha256",
            "verifierVersion",
            "observedTerminalState",
            "status",
            "reasonCode",
            "checks",
            "sourceEvidence",
            "evidenceSha256",
        },
        "domain evidence",
    )
    if raw["schema"] != DOMAIN_EVIDENCE_SCHEMA:
        raise ValueError("unsupported domain evidence schema")
    for field in (
        "requirementSha256",
        "scenarioSha256",
        "artifactSha256",
        "evidenceSha256",
    ):
        raw[field] = _require_sha(raw[field], field)
    verifier_family = str(raw["verifierFamily"])
    if verifier_family not in VERIFIER_CHECKS:
        raise ValueError("unsupported verifier family")
    if not _VERIFIER_ID_PATTERN.fullmatch(str(raw["verifierId"])):
        raise ValueError("verifierId must be opaque")
    expected_id = _verifier_id(
        raw["scenarioSha256"], raw["artifactSha256"], verifier_family
    )
    if raw["verifierId"] != expected_id:
        raise ValueError("verifierId is not content-bound to the evidence")
    raw["verifierPolicySha256"] = _require_sha(
        raw["verifierPolicySha256"], "verifierPolicySha256"
    )
    if not _VERSION_PATTERN.fullmatch(str(raw["verifierVersion"])):
        raise ValueError("verifierVersion must be exact and closed")
    if raw["observedTerminalState"] not in TERMINAL_RUN_STATES:
        raise ValueError("observed terminal state is not closed")
    rows = raw["checks"]
    required = VERIFIER_CHECKS[verifier_family]
    if not isinstance(rows, list) or len(rows) != len(required):
        raise ValueError("domain evidence check coverage is incomplete")
    normalized: list[dict[str, str]] = []
    for index, (item, expected_code) in enumerate(zip(rows, required)):
        row = dict(_require_mapping(item, f"checks[{index}]"))
        _require_exact_keys(row, {"code", "status"}, f"checks[{index}]")
        if row["code"] != expected_code or row["status"] not in CHECK_STATUSES:
            raise ValueError("domain check order, code, or status is invalid")
        normalized.append({"code": expected_code, "status": str(row["status"])})
    raw["checks"] = normalized
    raw["sourceEvidence"] = _validate_domain_source_evidence(
        raw["sourceEvidence"],
        verifier_family=verifier_family,
        artifact_sha256=raw["artifactSha256"],
        oracle_authentication_keys=oracle_authentication_keys,
    )
    if verifier_family == "exam":
        receipt = raw["sourceEvidence"]["receipt"]
        receipt_policy_sha = exam_verifier_policy_sha256(
            input_artifact_sha256=receipt["inputArtifactSha256"],
            oracle_provenance_sha256=receipt["oracleProvenanceSha256"],
            oracle_authentication_key_id=raw["sourceEvidence"][
                "authenticationKeyId"
            ],
        )
        policy_bound = raw["verifierPolicySha256"] == receipt_policy_sha
        render_checked = receipt["renderChecked"] is True and policy_bound
        splits_measured = render_checked and receipt["questionSplits"] is not None
        derived_checks = [
            {
                "code": "question_split_absent",
                "status": _normalize_check_status(
                    receipt["questionSplits"] == 0 if splits_measured else None
                ),
            },
            {
                "code": "placeholder_integrity_pass",
                "status": _normalize_check_status(
                    receipt["placeholdersOk"] if splits_measured else None
                ),
            },
            {
                "code": "exam_invariants_pass",
                "status": _normalize_check_status(
                    receipt["examInvariantsPass"] if policy_bound else None
                ),
            },
        ]
        if normalized != derived_checks:
            raise ValueError("exam checks do not match authenticated oracle evidence")
    elif verifier_family == "form_fill":
        source = raw["sourceEvidence"]
        if source is None:
            if raw["status"] == "passed":
                raise ValueError(
                    "passed form evidence requires frozen differential evidence"
                )
        else:
            expected_policy_sha = form_verifier_policy_sha256(
                target_policy_sha256=source["targetPolicySha256"],
                differential_receipt_asset_sha256=source["assetSha256"],
            )
            policy_bound = raw["verifierPolicySha256"] == expected_policy_sha
            render_pass = (
                policy_bound and source["receipt"]["verdict"] == "passed"
            )
            synthetic = next(
                item
                for item in normalized
                if item["code"] == "synthetic_values_verified"
            )
            if synthetic["status"] == "passed" and not render_pass:
                raise ValueError(
                    "form synthetic pass contradicts frozen differential evidence"
                )
    elif verifier_family == "must_abstain" and raw["sourceEvidence"] is not None:
        source = raw["sourceEvidence"]
        receipt = source["receipt"]
        source_policy_sha = must_abstain_verifier_policy_sha256(
            inventory_authentication_key_id=source[
                "inventoryAuthenticationKeyId"
            ]
        )
        policy_bound = raw["verifierPolicySha256"] == source_policy_sha
        if receipt["state"] != raw["observedTerminalState"]:
            raise ValueError("must-abstain source terminal state mismatch")
        output_artifacts = [
            item for item in receipt["artifacts"] if item["role"] == "output"
        ]
        decision_event_present = any(
            item["kind"] == "decision_gate" and item["status"] == "abstained"
            for item in receipt["workflowEvents"]
        )
        derived_checks = [
            {
                "code": "terminal_state_allowed",
                "status": _normalize_check_status(
                    receipt["state"] in ABSTENTION_TERMINAL_STATES
                ),
            },
            {
                "code": "no_mutation",
                "status": _normalize_check_status(
                    (
                        not source["measuredOutputInventory"]
                        and not output_artifacts
                    )
                    if policy_bound
                    else None
                ),
            },
            {
                "code": "decision_reason_present",
                "status": _normalize_check_status(
                    receipt["terminalReason"] in ABSTENTION_REASON_CODES
                    and decision_event_present
                ),
            },
        ]
        if normalized != derived_checks:
            raise ValueError(
                "must-abstain checks do not match terminal receipt and inventory"
            )
    status = _evidence_status(normalized)
    if raw["status"] != status or raw["reasonCode"] != f"DOMAIN_VERIFIER_{status.upper()}":
        raise ValueError("domain evidence status does not match its checks")
    if verifier_family == "must_abstain":
        expected = (
            "passed"
            if raw["observedTerminalState"] in ABSTENTION_TERMINAL_STATES
            else "failed"
        )
        if normalized[0]["status"] != expected:
            raise ValueError("must-abstain evidence contradicts the terminal state")
    elif raw["observedTerminalState"] != "completed" and status == "passed":
        raise ValueError("non-abstention evidence cannot pass an unsuccessful run")
    if domain_evidence_sha256(raw) != raw["evidenceSha256"]:
        raise ValueError("evidenceSha256 does not match canonical content")
    return raw


def _verdict(
    binding: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    *,
    status: str,
    reason_code: str,
) -> dict[str, Any]:
    required = list(binding["requiredChecks"])
    statuses = (
        {row["code"]: row["status"] for row in evidence["checks"]}
        if evidence is not None
        else {}
    )
    return {
        "verifierFamily": binding["verifierFamily"],
        "verifierId": binding["verifierId"],
        "status": status,
        "reasonCode": reason_code,
        "evidenceSha256": evidence["evidenceSha256"] if evidence is not None else None,
        "requiredChecks": required,
        "passedChecks": [code for code in required if statuses.get(code) == "passed"],
        "failedChecks": [code for code in required if statuses.get(code) == "failed"],
        "unverifiedChecks": [
            code for code in required if statuses.get(code) in {None, "unverified", "not_run"}
        ],
    }


def domain_result_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical content hash of an aggregate domain verdict."""

    return _content_hash(_require_mapping(value, "domain result"), "resultSha256")


def domain_evaluation_bundle_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical content hash of a standalone domain bundle."""

    return _content_hash(
        _require_mapping(value, "domain evaluation bundle"), "bundleSha256"
    )


def evaluate_domain(
    requirement: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    *,
    observed_terminal_state: str,
    oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Reduce required evidence with failure-before-unverified precedence.

    Missing, malformed, duplicate, unexpected, stale, or unbound evidence is
    never converted to success.  A valid failed verifier remains a failure even
    when other verifier receipts are absent.
    """

    frozen = validate_domain_requirement(requirement)
    if observed_terminal_state not in TERMINAL_RUN_STATES:
        raise ValueError("observed terminal state is not closed")
    parsed: list[dict[str, Any]] = []
    malformed_count = 0
    for item in evidence:
        try:
            parsed.append(
                validate_domain_evidence(
                    item,
                    oracle_authentication_keys=oracle_authentication_keys,
                )
            )
        except (TypeError, ValueError):
            malformed_count += 1
    required_families = {row["verifierFamily"] for row in frozen["verifiers"]}
    unexpected_count = sum(
        1 for item in parsed if item["verifierFamily"] not in required_families
    )
    by_family: dict[str, list[dict[str, Any]]] = {}
    for item in parsed:
        by_family.setdefault(item["verifierFamily"], []).append(item)

    verdicts: list[dict[str, Any]] = []
    for binding in frozen["verifiers"]:
        candidates = by_family.get(binding["verifierFamily"], [])
        if not candidates:
            verdicts.append(
                _verdict(
                    binding,
                    None,
                    status="unverified",
                    reason_code="DOMAIN_VERIFIER_MISSING",
                )
            )
            continue
        if len(candidates) != 1:
            failed_candidate = next(
                (item for item in candidates if item["status"] == "failed"), None
            )
            verdicts.append(
                _verdict(
                    binding,
                    failed_candidate,
                    status="failed" if failed_candidate is not None else "unverified",
                    reason_code=(
                        "DOMAIN_VERIFIER_FAILED"
                        if failed_candidate is not None
                        else "DOMAIN_VERIFIER_DUPLICATE"
                    ),
                )
            )
            continue
        item = candidates[0]
        binding_fields = (
            ("requirementSha256", frozen["requirementSha256"]),
            ("scenarioSha256", frozen["scenarioSha256"]),
            ("artifactSha256", frozen["artifactSha256"]),
            ("verifierId", binding["verifierId"]),
            ("verifierPolicySha256", binding["policySha256"]),
            ("observedTerminalState", observed_terminal_state),
        )
        if any(item[field] != expected for field, expected in binding_fields):
            verdicts.append(
                _verdict(
                    binding,
                    None,
                    status="unverified",
                    reason_code="DOMAIN_EVIDENCE_BINDING_MISMATCH",
                )
            )
            continue
        verdicts.append(
            _verdict(
                binding,
                item,
                status=item["status"],
                reason_code=item["reasonCode"],
            )
        )

    failed = [item for item in verdicts if item["status"] == "failed"]
    unverified = [item for item in verdicts if item["status"] != "passed"]
    if failed:
        status = "failed"
        reason_code = failed[0]["reasonCode"]
    elif malformed_count:
        status = "unverified"
        reason_code = "DOMAIN_EVIDENCE_MALFORMED"
    elif unexpected_count:
        status = "unverified"
        reason_code = "DOMAIN_VERIFIER_UNEXPECTED"
    elif unverified:
        status = "unverified"
        reason_code = unverified[0]["reasonCode"]
    else:
        status = "passed"
        reason_code = "DOMAIN_PASSED"

    abstention_verdict = next(
        (item for item in verdicts if item["verifierFamily"] == "must_abstain"),
        None,
    )
    observed_abstention = bool(
        frozen["expectedAbstention"]
        and abstention_verdict is not None
        and abstention_verdict["status"] == "passed"
        and observed_terminal_state in ABSTENTION_TERMINAL_STATES
    )
    result: dict[str, Any] = {
        "schema": DOMAIN_RESULT_SCHEMA,
        "requirementSha256": frozen["requirementSha256"],
        "scenarioSha256": frozen["scenarioSha256"],
        "artifactSha256": frozen["artifactSha256"],
        "taskKind": frozen["taskKind"],
        "family": frozen["family"],
        "status": status,
        "reasonCode": reason_code,
        "observedTerminalState": observed_terminal_state,
        "expectedAbstention": frozen["expectedAbstention"],
        "observedAbstention": observed_abstention,
        "requiredVerifierCount": len(verdicts),
        "passedVerifierCount": sum(item["status"] == "passed" for item in verdicts),
        "malformedEvidenceCount": malformed_count,
        "unexpectedEvidenceCount": unexpected_count,
        "verdicts": verdicts,
    }
    assert_receipt_safe(result)
    result["resultSha256"] = domain_result_sha256(result)
    return validate_domain_result(result)


def validate_domain_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate result structure for an already trusted/recomputed bundle.

    This cannot prove that referenced requirement/evidence receipts exist.
    Untrusted standalone input must enter through
    :func:`validate_domain_evaluation_bundle`.
    """

    raw = dict(_require_mapping(value, "domain result"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {
            "schema",
            "requirementSha256",
            "scenarioSha256",
            "artifactSha256",
            "taskKind",
            "family",
            "status",
            "reasonCode",
            "observedTerminalState",
            "expectedAbstention",
            "observedAbstention",
            "requiredVerifierCount",
            "passedVerifierCount",
            "malformedEvidenceCount",
            "unexpectedEvidenceCount",
            "verdicts",
            "resultSha256",
        },
        "domain result",
    )
    if raw["schema"] != DOMAIN_RESULT_SCHEMA or raw["status"] not in DOMAIN_STATUSES:
        raise ValueError("unsupported domain result schema or status")
    if raw["reasonCode"] not in DOMAIN_REASON_CODES:
        raise ValueError("domain result reasonCode is not closed")
    for field in (
        "requirementSha256",
        "scenarioSha256",
        "artifactSha256",
        "resultSha256",
    ):
        raw[field] = _require_sha(raw[field], field)
    task_kind = str(raw["taskKind"])
    family_code = str(raw["family"])
    if task_kind not in TASK_KINDS:
        raise ValueError("domain result taskKind is unsupported")
    if not _FAMILY_CODE_PATTERN.fullmatch(family_code):
        raise ValueError("domain result family must be a closed code")
    if raw["observedTerminalState"] not in TERMINAL_RUN_STATES:
        raise ValueError("observed terminal state is not closed")
    for field in ("expectedAbstention", "observedAbstention"):
        if not isinstance(raw[field], bool):
            raise ValueError(f"{field} must be boolean")
    for field in (
        "requiredVerifierCount",
        "passedVerifierCount",
        "malformedEvidenceCount",
        "unexpectedEvidenceCount",
    ):
        if isinstance(raw[field], bool) or not isinstance(raw[field], int) or raw[field] < 0:
            raise ValueError(f"{field} must be a non-negative integer")
    rows = raw["verdicts"]
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) != raw["requiredVerifierCount"]
    ):
        raise ValueError("domain verdict coverage does not match its count")
    passed_count = 0
    seen_families: set[str] = set()
    seen_ids: set[str] = set()
    for index, item in enumerate(rows):
        row = _require_mapping(item, f"verdicts[{index}]")
        _require_exact_keys(
            row,
            {
                "verifierFamily",
                "verifierId",
                "status",
                "reasonCode",
                "evidenceSha256",
                "requiredChecks",
                "passedChecks",
                "failedChecks",
                "unverifiedChecks",
            },
            f"verdicts[{index}]",
        )
        family = str(row["verifierFamily"])
        if family not in VERIFIER_CHECKS or row["status"] not in DOMAIN_STATUSES:
            raise ValueError("domain verdict family or status is invalid")
        if row["reasonCode"] not in DOMAIN_REASON_CODES:
            raise ValueError("domain verdict reasonCode is not closed")
        if not _VERIFIER_ID_PATTERN.fullmatch(str(row["verifierId"])):
            raise ValueError("domain verdict verifierId is invalid")
        expected_id = _verifier_id(
            raw["scenarioSha256"], raw["artifactSha256"], family
        )
        if row["verifierId"] != expected_id:
            raise ValueError("domain verdict verifierId is not content-bound")
        if family in seen_families or row["verifierId"] in seen_ids:
            raise ValueError("domain verdict families and IDs must be unique")
        seen_families.add(family)
        seen_ids.add(str(row["verifierId"]))
        if row["evidenceSha256"] is not None:
            _require_sha(row["evidenceSha256"], f"verdicts[{index}].evidenceSha256")
        required = list(VERIFIER_CHECKS[family])
        if row["requiredChecks"] != required:
            raise ValueError("domain verdict required checks were altered")
        partitions = [row["passedChecks"], row["failedChecks"], row["unverifiedChecks"]]
        if any(not isinstance(part, list) for part in partitions):
            raise ValueError("domain verdict check partitions must be lists")
        flattened = [code for part in partitions for code in part]
        if len(flattened) != len(set(flattened)) or set(flattened) != set(required):
            raise ValueError("domain verdict check partitions are incomplete or overlapping")
        if row["status"] == "passed" and (
            row["failedChecks"] or row["unverifiedChecks"] or row["evidenceSha256"] is None
        ):
            raise ValueError("a passed domain verdict requires complete passed evidence")
        if row["status"] == "passed" and row["reasonCode"] != "DOMAIN_VERIFIER_PASSED":
            raise ValueError("a passed domain verdict has the wrong reason code")
        if row["status"] == "failed" and not row["failedChecks"]:
            raise ValueError("a failed domain verdict requires a failed check")
        if row["status"] == "failed" and row["reasonCode"] != "DOMAIN_VERIFIER_FAILED":
            raise ValueError("a failed domain verdict has the wrong reason code")
        if row["status"] == "unverified" and not row["unverifiedChecks"]:
            raise ValueError("an unverified domain verdict requires unverified checks")
        if row["status"] == "unverified" and row["reasonCode"] not in {
            "DOMAIN_VERIFIER_UNVERIFIED",
            "DOMAIN_VERIFIER_MISSING",
            "DOMAIN_VERIFIER_DUPLICATE",
            "DOMAIN_EVIDENCE_BINDING_MISMATCH",
        }:
            raise ValueError("an unverified domain verdict has the wrong reason code")
        passed_count += row["status"] == "passed"
    if passed_count != raw["passedVerifierCount"]:
        raise ValueError("passedVerifierCount does not match verdicts")
    expected_families = list(_bound_verifier_families(task_kind, family_code))
    if [item["verifierFamily"] for item in rows] != expected_families:
        raise ValueError("domain result verifier coverage does not match task/family")
    passed_abstention = any(
        item["verifierFamily"] == "must_abstain" and item["status"] == "passed"
        for item in rows
    )
    expected_observed_abstention = bool(
        raw["expectedAbstention"]
        and passed_abstention
        and raw["observedTerminalState"] in ABSTENTION_TERMINAL_STATES
    )
    if raw["observedAbstention"] is not expected_observed_abstention:
        raise ValueError("observedAbstention lacks exact passed must-abstain evidence")
    if raw["expectedAbstention"] is not (task_kind == "must_abstain"):
        raise ValueError("expectedAbstention does not match verifier coverage")
    if raw["status"] == "passed":
        if task_kind == "must_abstain":
            if raw["observedTerminalState"] not in ABSTENTION_TERMINAL_STATES:
                raise ValueError(
                    "passed must-abstain result requires an allowed abstention terminal"
                )
        elif raw["observedTerminalState"] != "completed":
            raise ValueError(
                "passed non-abstention result requires the completed terminal state"
            )
    failed_rows = [item for item in rows if item["status"] == "failed"]
    unverified_rows = [item for item in rows if item["status"] != "passed"]
    if failed_rows:
        expected_status = "failed"
        expected_reason = failed_rows[0]["reasonCode"]
    elif raw["malformedEvidenceCount"]:
        expected_status = "unverified"
        expected_reason = "DOMAIN_EVIDENCE_MALFORMED"
    elif raw["unexpectedEvidenceCount"]:
        expected_status = "unverified"
        expected_reason = "DOMAIN_VERIFIER_UNEXPECTED"
    elif unverified_rows:
        expected_status = "unverified"
        expected_reason = unverified_rows[0]["reasonCode"]
    else:
        expected_status = "passed"
        expected_reason = "DOMAIN_PASSED"
    if raw["status"] != expected_status or raw["reasonCode"] != expected_reason:
        raise ValueError("domain result status does not match fail-closed precedence")
    if domain_result_sha256(raw) != raw["resultSha256"]:
        raise ValueError("resultSha256 does not match canonical content")
    return raw


def build_domain_evaluation_bundle(
    requirement: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    *,
    observed_terminal_state: str,
    oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Seal exact requirement/evidence receipts with their recomputed result."""

    frozen_requirement = validate_domain_requirement(requirement)
    frozen_evidence = [
        validate_domain_evidence(
            item,
            oracle_authentication_keys=oracle_authentication_keys,
        )
        for item in evidence
    ]
    result = evaluate_domain(
        frozen_requirement,
        frozen_evidence,
        observed_terminal_state=observed_terminal_state,
        oracle_authentication_keys=oracle_authentication_keys,
    )
    bundle: dict[str, Any] = {
        "schema": DOMAIN_EVALUATION_BUNDLE_SCHEMA,
        "requirement": frozen_requirement,
        "evidence": frozen_evidence,
        "result": result,
    }
    assert_receipt_safe(bundle)
    bundle["bundleSha256"] = domain_evaluation_bundle_sha256(bundle)
    return validate_domain_evaluation_bundle(
        bundle,
        oracle_authentication_keys=oracle_authentication_keys,
    )


def validate_domain_evaluation_bundle(
    value: Mapping[str, Any],
    *,
    oracle_authentication_keys: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Re-run a standalone domain evaluation and require byte-exact equality.

    A bare result hash is not proof that its requirement or verifier receipts
    exist.  The bundle therefore carries those closed receipts and derives the
    result again during every validation.
    """

    raw = dict(_require_mapping(value, "domain evaluation bundle"))
    assert_receipt_safe(raw)
    _require_exact_keys(
        raw,
        {"schema", "requirement", "evidence", "result", "bundleSha256"},
        "domain evaluation bundle",
    )
    if raw["schema"] != DOMAIN_EVALUATION_BUNDLE_SCHEMA:
        raise ValueError("unsupported domain evaluation bundle schema")
    requirement = validate_domain_requirement(
        _require_mapping(raw["requirement"], "domain bundle requirement")
    )
    evidence_value = raw["evidence"]
    if not isinstance(evidence_value, list):
        raise ValueError("domain bundle evidence must be a list")
    evidence = [
        validate_domain_evidence(
            item,
            oracle_authentication_keys=oracle_authentication_keys,
        )
        for item in evidence_value
    ]
    for item in evidence:
        if item["verifierFamily"] == "exam":
            receipt = item["sourceEvidence"]["receipt"]
            expected_policy_sha = exam_verifier_policy_sha256(
                input_artifact_sha256=receipt["inputArtifactSha256"],
                oracle_provenance_sha256=receipt["oracleProvenanceSha256"],
                oracle_authentication_key_id=item["sourceEvidence"][
                    "authenticationKeyId"
                ],
            )
            if _verifier_policy_sha256(requirement, "exam") != expected_policy_sha:
                raise ValueError(
                    "exam source evidence does not match frozen verifier policy"
                )
        elif (
            item["verifierFamily"] == "form_fill"
            and item["sourceEvidence"] is not None
        ):
            source = item["sourceEvidence"]
            expected_policy_sha = form_verifier_policy_sha256(
                target_policy_sha256=source["targetPolicySha256"],
                differential_receipt_asset_sha256=source["assetSha256"],
            )
            if (
                _verifier_policy_sha256(requirement, "form_fill")
                != expected_policy_sha
            ):
                raise ValueError(
                    "form source evidence does not match frozen verifier policy"
                )
        elif (
            item["verifierFamily"] == "must_abstain"
            and item["sourceEvidence"] is not None
        ):
            expected_policy_sha = must_abstain_verifier_policy_sha256(
                inventory_authentication_key_id=item["sourceEvidence"][
                    "inventoryAuthenticationKeyId"
                ]
            )
            if (
                _verifier_policy_sha256(requirement, "must_abstain")
                != expected_policy_sha
            ):
                raise ValueError(
                    "must-abstain source evidence does not match frozen verifier policy"
                )
    supplied_result = dict(
        _require_mapping(raw["result"], "domain bundle result")
    )
    observed_terminal_state = str(supplied_result.get("observedTerminalState", ""))
    recomputed = evaluate_domain(
        requirement,
        evidence,
        observed_terminal_state=observed_terminal_state,
        oracle_authentication_keys=oracle_authentication_keys,
    )
    if supplied_result != recomputed:
        raise ValueError("domain bundle result does not match recomputed evaluation")
    expected_hash = domain_evaluation_bundle_sha256(raw)
    if _require_sha(raw["bundleSha256"], "bundleSha256") != expected_hash:
        raise ValueError("bundleSha256 does not match canonical content")
    return {
        "schema": DOMAIN_EVALUATION_BUNDLE_SCHEMA,
        "requirement": requirement,
        "evidence": evidence,
        "result": recomputed,
        "bundleSha256": expected_hash,
    }


def build_edit_domain_evidence(
    requirement: Mapping[str, Any],
    *,
    expected_change_pass: bool | None,
    forbidden_drift_absent: bool | None,
    untouched_members_preserved: bool | None,
    observed_terminal_state: str,
) -> dict[str, Any]:
    return build_domain_evidence(
        requirement,
        verifier_family="edit",
        checks={
            "expected_change_pass": expected_change_pass,
            "forbidden_drift_absent": forbidden_drift_absent,
            "untouched_members_preserved": untouched_members_preserved,
        },
        observed_terminal_state=observed_terminal_state,
    )


def build_form_fill_domain_evidence(
    requirement: Mapping[str, Any],
    *,
    mapping_complete: bool | None,
    residue_absent: bool | None,
    synthetic_values_verified: bool | None,
    observed_terminal_state: str,
) -> dict[str, Any]:
    return build_domain_evidence(
        requirement,
        verifier_family="form_fill",
        checks={
            "mapping_complete": mapping_complete,
            "residue_absent": residue_absent,
            "synthetic_values_verified": synthetic_values_verified,
        },
        observed_terminal_state=observed_terminal_state,
    )


def build_structural_table_domain_evidence(
    requirement: Mapping[str, Any],
    *,
    table_geometry_preserved: bool | None,
    exact_values_pass: bool | None,
    merged_cells_preserved: bool | None,
    observed_terminal_state: str,
) -> dict[str, Any]:
    return build_domain_evidence(
        requirement,
        verifier_family="structural_table",
        checks={
            "table_geometry_preserved": table_geometry_preserved,
            "exact_values_pass": exact_values_pass,
            "merged_cells_preserved": merged_cells_preserved,
        },
        observed_terminal_state=observed_terminal_state,
    )


def build_edit_domain_evidence_from_semantic(
    requirement: Mapping[str, Any],
    semantic_layer_receipt: Mapping[str, Any],
    *,
    observed_terminal_state: str,
) -> dict[str, Any]:
    """Derive edit-domain checks only from a validated semantic layer receipt."""

    checks: dict[str, object] = {
        "expected_change_pass": None,
        "forbidden_drift_absent": None,
        "untouched_members_preserved": None,
    }
    try:
        from .evaluator import validate_layer_receipt

        raw_checks = semantic_layer_receipt.get("checks")
        if not isinstance(raw_checks, list):
            raise ValueError("semantic checks are unavailable")
        required_codes = [str(item.get("code")) for item in raw_checks if isinstance(item, Mapping)]
        receipt = validate_layer_receipt(
            semantic_layer_receipt,
            expected_layer="semantic",
            required_check_codes=required_codes,
        )
        frozen = validate_domain_requirement(requirement)
        artifact = receipt.get("artifact")
        if not isinstance(artifact, Mapping) or artifact.get("sha256") != frozen["artifactSha256"]:
            raise ValueError("semantic artifact binding mismatch")
        statuses = {item["code"]: item["status"] for item in receipt["checks"]}

        def measured(code: str) -> str | None:
            status = statuses.get(code)
            return status if status in {"passed", "failed", "unverified"} else None

        checks = {
            "expected_change_pass": measured("SEMANTIC_DIFF"),
            "forbidden_drift_absent": measured("FORBIDDEN_DRIFT"),
            "untouched_members_preserved": measured("BYTE_PRESERVATION"),
        }
    except Exception:  # malformed, reduced, stale, or unavailable receipt
        pass
    return build_domain_evidence(
        requirement,
        verifier_family="edit",
        checks=checks,
        observed_terminal_state=observed_terminal_state,
        verifier_version="practice-semantic-evaluator/v1",
    )


def _bound_cell_value_sha256(path: str | Path, binding: Mapping[str, Any]) -> str:
    from hwpx.table_patch import (
        _iter_table_spans,
        _read_source_bytes,
        _sections,
        _text_of,
        build_grid,
    )

    sections = sorted(_sections(_read_source_bytes(path)).items())
    section_index = int(binding["sectionIndex"])
    if section_index >= len(sections):
        raise ValueError("form target section is missing")
    _section_name, section = sections[section_index]
    table_spans = _iter_table_spans(section)
    table_index = int(binding["tableIndex"])
    if table_index >= len(table_spans):
        raise ValueError("form target table is missing")
    start, end = table_spans[table_index]
    table = section[start:end]
    grid, report = build_grid(table)
    if not report.ok:
        raise ValueError("form target table grid is invalid")
    cell = grid.get((int(binding["row"]), int(binding["col"])))
    if cell is None:
        raise ValueError("form target cell is missing")
    value = _normalized_synthetic_text(_text_of(table[cell.start : cell.end]))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_form_fill_domain_evidence_from_artifacts(
    requirement: Mapping[str, Any],
    output_path: str | Path,
    blank_path: str | Path,
    *,
    target_policy: Mapping[str, Any],
    frozen_differential_receipt_path: str | Path,
    frozen_differential_receipt_asset_sha256: str,
    observed_terminal_state: str,
) -> dict[str, Any]:
    """Measure form-fill evidence against an exact frozen differential receipt.

    The runner cannot provide render booleans.  The evaluator reads one
    content-addressed receipt asset, validates its artifact/provenance/verdict
    contract, then independently measures targets and residue from private
    snapshots.  Any missing, stale, swapped, or malformed input leaves every
    check unverified.
    """

    policy = validate_form_target_policy(target_policy)
    expected_asset_sha = _require_sha(
        frozen_differential_receipt_asset_sha256,
        "frozenDifferentialReceiptAssetSha256",
    )
    checks: dict[str, object] = {
        "mapping_complete": None,
        "residue_absent": None,
        "synthetic_values_verified": None,
    }
    source_evidence: dict[str, Any] | None = None
    try:
        frozen = validate_domain_requirement(requirement)
        output_payload = _read_hwpx_snapshot(output_path)
        blank_payload = _read_hwpx_snapshot(blank_path)
        receipt_asset = _read_bounded_snapshot(
            frozen_differential_receipt_path
        )
        if hashlib.sha256(receipt_asset).hexdigest() != expected_asset_sha:
            raise ValueError("form differential receipt asset hash mismatch")
        receipt_value = json.loads(receipt_asset.decode("utf-8"))
        receipt = validate_form_differential_receipt(
            _require_mapping(receipt_value, "form differential receipt asset")
        )
        expected_policy_sha = form_verifier_policy_sha256(
            target_policy_sha256=policy["policySha256"],
            differential_receipt_asset_sha256=expected_asset_sha,
        )
        if (
            hashlib.sha256(output_payload).hexdigest() != frozen["artifactSha256"]
            or hashlib.sha256(blank_payload).hexdigest()
            != policy["blankArtifactSha256"]
            or _verifier_policy_sha256(frozen, "form_fill")
            != expected_policy_sha
            or receipt["blankArtifact"]
            != {
                "sha256": hashlib.sha256(blank_payload).hexdigest(),
                "bytes": len(blank_payload),
            }
            or receipt["outputArtifact"]
            != {
                "sha256": hashlib.sha256(output_payload).hexdigest(),
                "bytes": len(output_payload),
            }
        ):
            raise ValueError("form artifact binding mismatch")
        from hwpx.fill_residue import inspect_fill_residue

        with ExitStack() as stack:
            output_snapshot = stack.enter_context(
                _strict_snapshot_path(output_payload, suffix=".hwpx")
            )
            blank_snapshot = stack.enter_context(
                _strict_snapshot_path(blank_payload, suffix=".hwpx")
            )
            residue = inspect_fill_residue(output_snapshot, blank=blank_snapshot)
            mapping_complete = all(
                _bound_cell_value_sha256(blank_snapshot, binding)
                == binding["blankValueSha256"]
                for binding in policy["bindings"]
            )
            values_present = all(
                _bound_cell_value_sha256(output_snapshot, binding)
                == binding["expectedValueSha256"]
                for binding in policy["bindings"]
            )
        if residue.errors:
            residue_status: bool | None = False
        elif residue.needs_review:
            residue_status = None
        else:
            residue_status = True
        if not values_present:
            synthetic_status: bool | None = False
        else:
            synthetic_status = receipt["verdict"] == "passed"
        checks = {
            "mapping_complete": mapping_complete,
            "residue_absent": residue_status,
            "synthetic_values_verified": synthetic_status,
        }
        source_evidence = {
            "schema": FORM_DIFFERENTIAL_SOURCE_EVIDENCE_SCHEMA,
            "assetSha256": expected_asset_sha,
            "receiptSha256": receipt["receiptSha256"],
            "targetPolicySha256": policy["policySha256"],
            "receipt": receipt,
        }
    except Exception:  # missing/stale artifact or unavailable independent verifier
        pass
    return build_domain_evidence(
        requirement,
        verifier_family="form_fill",
        checks=checks,
        observed_terminal_state=observed_terminal_state,
        verifier_version="hwpx-form-differential/v1",
        source_evidence=source_evidence,
    )


def _structural_measurement(path: str | Path) -> dict[str, Any]:
    from hwpx.table_patch import (
        _direct_cells,
        _iter_table_spans,
        _read_source_bytes,
        _sections,
        _text_of,
        build_grid,
    )

    tables: list[dict[str, Any]] = []
    data = _read_source_bytes(path)
    for section_path, section in sorted(_sections(data).items()):
        for table_index, (start, end) in enumerate(_iter_table_spans(section)):
            table = section[start:end]
            _grid, report = build_grid(table)
            cells = _direct_cells(table)
            merge_signature = [
                [cell.row, cell.col, cell.row_span, cell.col_span]
                for cell in cells
                if cell.row_span > 1 or cell.col_span > 1
            ]
            row_values: dict[int, list[tuple[int, str]]] = {}
            for cell in cells:
                text = _normalized_synthetic_text(_text_of(table[cell.start : cell.end]))
                row_values.setdefault(cell.row, []).append((cell.col, text))
            row_hashes: list[str] = []
            row_value_hashes: list[list[str]] = []
            for row_index in sorted(row_values):
                ordered = [value for _column, value in sorted(row_values[row_index])]
                row_hashes.append(_sha256(ordered))
                row_value_hashes.append(
                    [domain_value_sha256(value) for value in ordered if value]
                )
            tables.append(
                {
                    "section": section_path,
                    "index": table_index,
                    "rows": report.row_count,
                    "cols": report.col_count,
                    "gridOk": report.ok,
                    "merges": sorted(merge_signature),
                    "mergeSha256": _sha256(
                        {
                            "section": section_path,
                            "tableIndex": table_index,
                            "merges": sorted(merge_signature),
                        }
                    ),
                    "rowHashes": row_hashes,
                    "rowValueHashes": row_value_hashes,
                }
            )
    return {"tables": tables}


def _merge_topology_preserved_after_row_insertion(
    before_merges: Sequence[Sequence[int]],
    after_merges: Sequence[Sequence[int]],
    *,
    inserted_row: int,
) -> bool:
    """Compare merge topology after one physical row insertion.

    Existing merges below the insertion move by one row, while a vertical merge
    crossing the insertion grows by one row.  A cloned source row may also add
    an exact copy of its horizontal merges on the inserted row.  No other merge
    addition, deletion, relocation, or span change is accepted.
    """

    if isinstance(inserted_row, bool) or not isinstance(inserted_row, int) or inserted_row < 1:
        return False

    before = sorted(tuple(int(value) for value in row) for row in before_merges)
    after = sorted(tuple(int(value) for value in row) for row in after_merges)
    if any(len(row) != 4 for row in before + after):
        return False

    shifted: list[tuple[int, int, int, int]] = []
    for row, col, row_span, col_span in before:
        if row >= inserted_row:
            row += 1
        elif row < inserted_row < row + row_span:
            row_span += 1
        shifted.append((row, col, row_span, col_span))
    shifted.sort()
    if after == shifted:
        return True

    source_row = inserted_row - 1
    cloned_horizontal = sorted(
        (inserted_row, col, 1, col_span)
        for row, col, row_span, col_span in before
        if row == source_row and row_span == 1 and col_span > 1
    )
    return bool(cloned_horizontal) and after == sorted(shifted + cloned_horizontal)


def build_structural_table_domain_evidence_from_artifacts(
    requirement: Mapping[str, Any],
    start_path: str | Path,
    output_path: str | Path,
    *,
    expected_start_sha256: str,
    expected_row_sha256: str,
    expected_value_sha256s: Sequence[str],
    observed_terminal_state: str,
) -> dict[str, Any]:
    """Measure one-row structural insertion from actual start/output HWPX files."""

    start_digest = _require_sha(expected_start_sha256, "expectedStartSha256")
    row_digest = _require_sha(expected_row_sha256, "expectedRowSha256")
    expected_values = {
        _require_sha(value, "expectedValueSha256") for value in expected_value_sha256s
    }
    if not expected_values:
        raise ValueError("structural evaluation requires expected synthetic values")
    checks: dict[str, object] = {
        "table_geometry_preserved": None,
        "exact_values_pass": None,
        "merged_cells_preserved": None,
    }
    try:
        frozen = validate_domain_requirement(requirement)
        start_payload = _read_hwpx_snapshot(start_path)
        output_payload = _read_hwpx_snapshot(output_path)
        policy_sha = structural_verifier_policy_sha256(
            expected_start_sha256=start_digest,
            expected_row_sha256=row_digest,
            expected_value_sha256s=sorted(expected_values),
        )
        if (
            hashlib.sha256(start_payload).hexdigest() != start_digest
            or hashlib.sha256(output_payload).hexdigest() != frozen["artifactSha256"]
            or _verifier_policy_sha256(frozen, "structural_table") != policy_sha
        ):
            raise ValueError("structural artifact binding mismatch")
        with ExitStack() as stack:
            start_snapshot = stack.enter_context(
                _strict_snapshot_path(start_payload, suffix=".hwpx")
            )
            output_snapshot = stack.enter_context(
                _strict_snapshot_path(output_payload, suffix=".hwpx")
            )
            before = _structural_measurement(start_snapshot)
            after = _structural_measurement(output_snapshot)
        before_tables = before["tables"]
        after_tables = after["tables"]
        same_count = bool(before_tables) and len(before_tables) == len(after_tables)
        deltas: list[int] = []
        columns_preserved = same_count
        grids_valid = same_count
        merges_preserved = same_count
        inserted_row_matches = False
        if same_count:
            for old, new in zip(before_tables, after_tables):
                columns_preserved = columns_preserved and old["cols"] == new["cols"]
                grids_valid = grids_valid and old["gridOk"] is True and new["gridOk"] is True
                delta = new["rows"] - old["rows"]
                deltas.append(delta)
                matching_insertion_indices: list[int] = []
                if delta == 1 and len(new["rowHashes"]) == len(old["rowHashes"]) + 1:
                    for inserted_index, candidate_hash in enumerate(new["rowHashes"]):
                        without_candidate = (
                            new["rowHashes"][:inserted_index]
                            + new["rowHashes"][inserted_index + 1 :]
                        )
                        if (
                            without_candidate == old["rowHashes"]
                            and candidate_hash == row_digest
                            and expected_values.issubset(
                                set(new["rowValueHashes"][inserted_index])
                            )
                        ):
                            matching_insertion_indices.append(inserted_index)
                            inserted_row_matches = True
                if delta == 0:
                    table_merges_preserved = old["merges"] == new["merges"]
                elif delta == 1:
                    table_merges_preserved = any(
                        _merge_topology_preserved_after_row_insertion(
                            old["merges"],
                            new["merges"],
                            inserted_row=inserted_index,
                        )
                        for inserted_index in matching_insertion_indices
                    )
                else:
                    table_merges_preserved = False
                merges_preserved = merges_preserved and table_merges_preserved
        geometry_pass = bool(
            same_count
            and columns_preserved
            and grids_valid
            and sum(deltas) == 1
            and deltas.count(1) == 1
            and all(delta in {0, 1} for delta in deltas)
        )
        exact_values = inserted_row_matches
        checks = {
            "table_geometry_preserved": geometry_pass,
            "exact_values_pass": exact_values,
            "merged_cells_preserved": bool(merges_preserved),
        }
    except Exception:  # missing/stale artifact or unreadable table structure
        pass
    return build_domain_evidence(
        requirement,
        verifier_family="structural_table",
        checks=checks,
        observed_terminal_state=observed_terminal_state,
        verifier_version="hwpx-structural-measure/v1",
    )


ABSTENTION_REASON_CODES = frozenset(
    {
        "AMBIGUOUS_TARGET",
        "DECISION_REJECTED",
        "DECISION_REQUIRED",
        "DESTRUCTIVE_INTENT",
        "PRIVACY_REVIEW_REQUIRED",
        "UNSAFE_SOURCE",
        "UNSUPPORTED_INTENT",
        "WORKFLOW_NEEDS_REVIEW",
    }
)


def _inventory_from_dirfd(
    directory_fd: int,
    *,
    prefix: str = "",
    budget: dict[str, int] | None = None,
) -> tuple[tuple[object, ...], ...]:
    """Take one bounded, no-follow recursive inventory from an open directory."""

    active_budget = budget if budget is not None else {"entries": 0, "bytes": 0}
    entries: list[tuple[object, ...]] = []
    for name in sorted(os.listdir(directory_fd)):
        active_budget["entries"] += 1
        if active_budget["entries"] > 1024:
            raise ValueError("abstention output inventory exceeds its entry bound")
        relative = f"{prefix}/{name}" if prefix else name
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("abstention output inventory contains a symlink")
        if stat.S_ISDIR(metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if (
                    opened.st_dev != metadata.st_dev
                    or opened.st_ino != metadata.st_ino
                    or not stat.S_ISDIR(opened.st_mode)
                ):
                    raise ValueError("abstention output directory changed during inventory")
                children = _inventory_from_dirfd(
                    child_fd,
                    prefix=relative,
                    budget=active_budget,
                )
                closed = os.fstat(child_fd)
                if (
                    closed.st_dev,
                    closed.st_ino,
                    closed.st_mtime_ns,
                ) != (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mtime_ns,
                ):
                    raise ValueError("abstention output directory was mutated during inventory")
                entries.append(
                    (
                        "directory",
                        relative,
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_mtime_ns,
                    )
                )
                entries.extend(children)
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("abstention output inventory contains an unsafe entry")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(name, flags, dir_fd=directory_fd)
        try:
            opened = os.fstat(file_fd)
            if (
                opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or not stat.S_ISREG(opened.st_mode)
            ):
                raise ValueError("abstention output file changed before inventory")
            active_budget["bytes"] += opened.st_size
            if active_budget["bytes"] > MAX_DOMAIN_ARTIFACT_BYTES:
                raise ValueError("abstention output inventory exceeds its byte bound")
            hasher = hashlib.sha256()
            remaining = opened.st_size
            while remaining:
                chunk = os.read(file_fd, min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("abstention output file changed during inventory")
                hasher.update(chunk)
                remaining -= len(chunk)
            if os.read(file_fd, 1):
                raise ValueError("abstention output file grew during inventory")
            closed = os.fstat(file_fd)
            if (
                closed.st_dev,
                closed.st_ino,
                closed.st_size,
                closed.st_mtime_ns,
                closed.st_ctime_ns,
            ) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            ):
                raise ValueError("abstention output file was mutated during inventory")
            entries.append(
                (
                    "file",
                    relative,
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                    hasher.hexdigest(),
                )
            )
        finally:
            os.close(file_fd)
    return tuple(entries)


def _stable_output_inventory(root: str | Path) -> tuple[tuple[str, int], ...]:
    """Require two identical dirfd inventories to reject rename/hide races."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    root_fd = os.open(Path(root), flags)
    try:
        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValueError("abstention output inventory root is not a directory")
        first = _inventory_from_dirfd(root_fd)
        midpoint = os.fstat(root_fd)
        second = _inventory_from_dirfd(root_fd)
        closed = os.fstat(root_fd)
        root_versions = {
            (item.st_dev, item.st_ino, item.st_mtime_ns)
            for item in (opened, midpoint, closed)
        }
        if first != second or len(root_versions) != 1:
            raise ValueError("abstention output inventory was not stable")
        return tuple(
            (str(item[7]), int(item[4]))
            for item in first
            if item[0] == "file"
        )
    finally:
        os.close(root_fd)


def build_must_abstain_domain_evidence_from_receipt(
    requirement: Mapping[str, Any],
    start_path: str | Path,
    terminal_receipt: Mapping[str, Any],
    *,
    inventory_authentication_key: bytes,
    expected_scenario_id: str,
    sandbox_output_root: str | Path,
) -> dict[str, Any]:
    """Derive abstention only from actual bytes and a validated terminal receipt."""

    observed_terminal_state = "unverified"
    no_mutation: bool | None = None
    decision_reason_present: bool | None = None
    source_evidence: dict[str, Any] | None = None
    inventory_key = _abstention_inventory_authentication_key(
        inventory_authentication_key
    )
    inventory_key_id = abstention_inventory_authentication_key_id(inventory_key)
    try:
        from .run import validate_run_receipt

        frozen = validate_domain_requirement(requirement)
        if not SCENARIO_ID_PATTERN.fullmatch(expected_scenario_id):
            raise ValueError("expected scenario ID must be opaque")
        receipt = validate_run_receipt(terminal_receipt)
        if receipt["scenarioId"] != expected_scenario_id:
            raise ValueError("terminal receipt scenario binding mismatch")
        observed_terminal_state = receipt["state"]
        start_payload = _read_bounded_snapshot(start_path)
        if hashlib.sha256(start_payload).hexdigest() != frozen["artifactSha256"]:
            raise ValueError("abstention start artifact binding mismatch")
        inventory = _stable_output_inventory(sandbox_output_root)
        output_artifacts = [
            item for item in receipt["artifacts"] if item["role"] == "output"
        ]
        # A refusal may not create even a byte-identical output copy.  Both the
        # independently measured sandbox and terminal receipt must be exactly empty.
        policy_bound = (
            _verifier_policy_sha256(frozen, "must_abstain")
            == must_abstain_verifier_policy_sha256(
                inventory_authentication_key_id=inventory_key_id
            )
        )
        no_mutation = (
            not inventory and not output_artifacts if policy_bound else None
        )
        decision_event_present = any(
            item["kind"] == "decision_gate" and item["status"] == "abstained"
            for item in receipt["workflowEvents"]
        )
        decision_reason_present = bool(
            receipt["terminalReason"] in ABSTENTION_REASON_CODES
            and decision_event_present
        )
        measured_inventory = sorted(
            (
                {"sha256": digest, "bytes": size}
                for digest, size in inventory
            ),
            key=lambda row: (row["sha256"], row["bytes"]),
        )
        receipt_outputs = sorted(
            (
                {
                    "artifactId": item["artifactId"],
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                }
                for item in output_artifacts
            ),
            key=lambda row: row["artifactId"],
        )
        receipt_sha = receipt["receiptSha256"]
        inventory_sha = _sha256(measured_inventory)
        inventory_auth_payload = {
            "schema": DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA,
            "receiptSha256": receipt_sha,
            "scenarioId": receipt["scenarioId"],
            "measuredOutputInventorySha256": inventory_sha,
            "measuredOutputInventory": measured_inventory,
        }
        source_evidence = {
            "schema": DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA,
            "receiptSha256": receipt_sha,
            "scenarioId": receipt["scenarioId"],
            "terminalReason": receipt["terminalReason"],
            "workflowEventsSha256": _sha256(receipt["workflowEvents"]),
            "receiptOutputArtifactsSha256": _sha256(receipt_outputs),
            "measuredOutputInventorySha256": inventory_sha,
            "measuredOutputInventory": measured_inventory,
            "inventoryAuthenticationKeyId": inventory_key_id,
            "inventoryAuth": {
                "schema": ABSTENTION_INVENTORY_AUTH_SCHEMA,
                "algorithm": "hmac-sha256",
                "keyId": inventory_key_id,
                "macSha256": hmac.new(
                    inventory_key,
                    _canonical_bytes(inventory_auth_payload),
                    hashlib.sha256,
                ).hexdigest(),
            },
            "receipt": receipt,
        }
    except Exception:  # missing/stale artifact or malformed/unbound receipt
        pass
    return build_domain_evidence(
        requirement,
        verifier_family="must_abstain",
        checks={
            "terminal_state_allowed": observed_terminal_state
            in ABSTENTION_TERMINAL_STATES,
            "no_mutation": no_mutation,
            "decision_reason_present": decision_reason_present,
        },
        observed_terminal_state=observed_terminal_state,
        verifier_version="practice-terminal-receipt/v1",
        source_evidence=source_evidence,
        oracle_authentication_keys={inventory_key_id: inventory_key},
    )


def build_exam_domain_evidence(
    requirement: Mapping[str, Any],
    oracle_receipt: Mapping[str, Any],
    *,
    oracle_authentication_key: bytes,
    observed_terminal_state: str,
) -> dict[str, Any]:
    """Reduce an artifact/provenance-bound exam oracle receipt."""

    receipt = validate_exam_oracle_receipt(
        oracle_receipt,
        oracle_authentication_key=oracle_authentication_key,
    )
    frozen = validate_domain_requirement(requirement)
    policy_sha = exam_verifier_policy_sha256(
        input_artifact_sha256=receipt["inputArtifactSha256"],
        oracle_provenance_sha256=receipt["oracleProvenanceSha256"],
        oracle_authentication_key_id=exam_oracle_authentication_key_id(
            oracle_authentication_key
        ),
    )
    bound = bool(
        receipt["outputArtifactSha256"] == frozen["artifactSha256"]
        and _verifier_policy_sha256(frozen, "exam") == policy_sha
    )
    render_checked = receipt["renderChecked"] is True and bound
    splits = receipt["questionSplits"]
    placeholders = receipt["placeholdersOk"]
    splits_measured = render_checked and splits is not None
    split_pass = (splits == 0) if splits_measured else None
    placeholder_pass = placeholders if splits_measured else None
    return build_domain_evidence(
        requirement,
        verifier_family="exam",
        checks={
            "question_split_absent": split_pass,
            "placeholder_integrity_pass": placeholder_pass,
            "exam_invariants_pass": receipt["examInvariantsPass"] if bound else None,
        },
        observed_terminal_state=observed_terminal_state,
        verifier_version="hwpx-exam-compose/v1",
        source_evidence={
            "schema": DOMAIN_SOURCE_EVIDENCE_SCHEMA,
            "receiptSha256": receipt["receiptSha256"],
            "authenticationKeyId": receipt["auth"]["keyId"],
            "receipt": receipt,
        },
        oracle_authentication_keys={
            receipt["auth"]["keyId"]: oracle_authentication_key
        },
    )


def build_official_document_domain_evidence(
    requirement: Mapping[str, Any],
    source: str | Path,
    *,
    observed_terminal_state: str,
    document_type: str = "공문",
) -> dict[str, Any]:
    """Run existing official-lint/reference validators and redact to booleans."""

    artifact_unavailable = True
    try:
        frozen = validate_domain_requirement(requirement)
        source_payload = _read_hwpx_snapshot(source)
        artifact_unavailable = bool(
            hashlib.sha256(source_payload).hexdigest() != frozen["artifactSha256"]
            or _verifier_policy_sha256(frozen, "official_document")
            != official_verifier_policy_sha256(document_type=document_type)
        )
    except (OSError, TypeError, ValueError):
        source_payload = b""
    try:
        if artifact_unavailable:
            raise FileNotFoundError
        from hwpx.tools.doc_diff import inspect_reference_consistency
        from hwpx.tools.official_lint import inspect_official_document_style

        with _strict_snapshot_path(source_payload, suffix=".hwpx") as source_snapshot:
            lint = inspect_official_document_style(
                source_snapshot, document_type=document_type
            )
            references = inspect_reference_consistency(source_snapshot)
        checks: dict[str, object] = {
            "official_lint_pass": lint.get("pass") is True,
            "official_structure_pass": lint.get("structure_pass") is True,
            "reference_consistency_pass": references.get("pass") is True,
        }
    except Exception:  # verifier/package skew is an unverified result, never success
        checks = {code: None for code in VERIFIER_CHECKS["official_document"]}
    return build_domain_evidence(
        requirement,
        verifier_family="official_document",
        checks=checks,
        observed_terminal_state=observed_terminal_state,
        verifier_version="hwpx-official-lint/v1",
    )


def build_authoring_domain_evidence(
    requirement: Mapping[str, Any],
    source: str | Path,
    *,
    observed_terminal_state: str,
    plan: Mapping[str, Any] | None = None,
    style_reference: str | Path | None = None,
) -> dict[str, Any]:
    """Run authoring/reference/style validators and emit only closed checks."""

    authoring_pass: bool | None = None
    reference_pass: bool | None = None
    style_pass: bool | None = None
    try:
        frozen = validate_domain_requirement(requirement)
        source_payload = _read_hwpx_snapshot(source)
        style_payload = (
            _read_hwpx_snapshot(style_reference)
            if style_reference is not None
            else None
        )
        plan_snapshot = (
            json.loads(_canonical_bytes(dict(plan))) if plan is not None else None
        )
        style_digest = (
            hashlib.sha256(style_payload).hexdigest()
            if style_payload is not None
            else None
        )
        policy_digest = authoring_verifier_policy_sha256(
            plan=plan_snapshot,
            style_reference_sha256=style_digest,
        )
        if (
            hashlib.sha256(source_payload).hexdigest() != frozen["artifactSha256"]
            or _verifier_policy_sha256(frozen, "authoring") != policy_digest
        ):
            raise ValueError("authoring artifact binding mismatch")
        from hwpx.authoring import inspect_document_authoring_quality
        from hwpx.tools.doc_diff import inspect_reference_consistency

        with ExitStack() as stack:
            source_snapshot = stack.enter_context(
                _strict_snapshot_path(source_payload, suffix=".hwpx")
            )
            style_snapshot = (
                stack.enter_context(_strict_snapshot_path(style_payload, suffix=".hwpx"))
                if style_payload is not None
                else None
            )
            try:
                authoring = inspect_document_authoring_quality(
                    source_snapshot, plan=plan_snapshot, verify_render=False
                )
                authoring_pass = authoring.get("pass") is True
            except Exception:
                pass
            try:
                references = inspect_reference_consistency(source_snapshot)
                reference_pass = references.get("pass") is True
            except Exception:
                pass
            if style_snapshot is None:
                # Absence alone is not evidence that the style-profile gate is
                # inapplicable.  A future closed N/A policy may make this pass;
                # until then the mandatory check stays honestly unverified.
                style_pass = None
            else:
                try:
                    from hwpx.tools.style_profile import compare_style_profiles

                    comparison = compare_style_profiles(
                        style_snapshot, source_snapshot
                    )
                    style_pass = comparison.get("pass") is True
                except Exception:
                    pass
    except Exception:  # malformed/stale artifacts and policy fail closed
        pass
    return build_domain_evidence(
        requirement,
        verifier_family="authoring",
        checks={
            "authoring_quality_pass": authoring_pass,
            "style_profile_pass": style_pass,
            "reference_consistency_pass": reference_pass,
        },
        observed_terminal_state=observed_terminal_state,
        verifier_version="hwpx-authoring-quality/v1",
    )


def build_must_abstain_domain_evidence(
    requirement: Mapping[str, Any],
    *,
    no_mutation: bool | None,
    decision_reason_present: bool | None,
    observed_terminal_state: str,
) -> dict[str, Any]:
    return build_domain_evidence(
        requirement,
        verifier_family="must_abstain",
        checks={
            "terminal_state_allowed": observed_terminal_state
            in ABSTENTION_TERMINAL_STATES,
            "no_mutation": no_mutation,
            "decision_reason_present": decision_reason_present,
        },
        observed_terminal_state=observed_terminal_state,
    )


__all__ = [
    "ABSTENTION_INVENTORY_AUTH_SCHEMA",
    "ABSTENTION_TERMINAL_STATES",
    "ABSTENTION_REASON_CODES",
    "CHECK_STATUSES",
    "DOMAIN_EVIDENCE_SCHEMA",
    "DOMAIN_EVALUATION_BUNDLE_SCHEMA",
    "DOMAIN_POLICY_PROJECTION_SCHEMA",
    "DOMAIN_REASON_CODES",
    "DOMAIN_REQUIREMENT_SCHEMA",
    "DOMAIN_RESULT_SCHEMA",
    "DOMAIN_SOURCE_EVIDENCE_SCHEMA",
    "DOMAIN_TERMINAL_SOURCE_EVIDENCE_SCHEMA",
    "DOMAIN_STATUSES",
    "EXAM_ORACLE_AUTH_SCHEMA",
    "EXAM_ORACLE_RECEIPT_SCHEMA",
    "FORM_DIFFERENTIAL_RECEIPT_SCHEMA",
    "FORM_DIFFERENTIAL_SOURCE_EVIDENCE_SCHEMA",
    "MAX_DOMAIN_ARTIFACT_BYTES",
    "VERIFIER_CHECKS",
    "abstention_inventory_authentication_key_id",
    "authoring_verifier_policy_sha256",
    "build_authoring_domain_evidence",
    "build_domain_evaluation_bundle",
    "build_domain_requirement",
    "build_edit_domain_evidence_from_semantic",
    "build_exam_domain_evidence",
    "build_exam_oracle_receipt",
    "build_form_differential_receipt",
    "build_form_target_policy",
    "build_form_fill_domain_evidence_from_artifacts",
    "build_must_abstain_domain_evidence_from_receipt",
    "build_official_document_domain_evidence",
    "build_structural_table_domain_evidence_from_artifacts",
    "domain_evidence_sha256",
    "domain_evaluation_bundle_sha256",
    "domain_requirement_sha256",
    "domain_requirement_policy_projection",
    "domain_row_sha256",
    "domain_result_sha256",
    "domain_value_sha256",
    "exam_oracle_authentication_key_id",
    "exam_verifier_policy_sha256",
    "evaluate_domain",
    "form_differential_oracle_provenance_sha256",
    "form_differential_receipt_sha256",
    "form_target_policy_sha256",
    "form_verifier_policy_sha256",
    "must_abstain_verifier_policy_sha256",
    "official_verifier_policy_sha256",
    "structural_verifier_policy_sha256",
    "serialize_form_differential_receipt",
    "validate_domain_evidence",
    "validate_domain_evaluation_bundle",
    "validate_domain_requirement",
    "validate_domain_result",
    "validate_exam_oracle_receipt",
    "validate_form_differential_receipt",
    "validate_form_target_policy",
]
