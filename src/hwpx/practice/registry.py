"""Private/redacted registry and source-integrity contracts.

Raw source coordinates exist only in an authenticated private record.  Anything
that leaves that boundary must pass :func:`assert_redacted_payload` and use a
keyed opaque document identifier instead of a source hash or filename.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PRIVATE_REGISTRY_SCHEMA = "hwpx.private-corpus-registry/v1"
REDACTED_REGISTRY_SCHEMA = "hwpx.private-corpus-registry-redacted/v1"
SOURCE_INTEGRITY_SCHEMA = "hwpx.private-corpus-source-integrity/v1"

DOCUMENT_ID_PATTERN = re.compile(r"^HWC-[A-F0-9]{20}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

PRIVACY_DECISIONS = frozenset({
    "unreviewed",
    "approved_local_only",
    "approved_sanitized",
    "quarantine",
    "repair_negative",
    "excluded_duplicate",
})
NORMAL_ELIGIBLE_DECISIONS = frozenset({"approved_local_only", "approved_sanitized"})

_FORBIDDEN_REDACTED_KEYS = frozenset({
    "filename",
    "filepath",
    "rawpath",
    "relativepath",
    "sourcefilename",
    "sourcehash",
    "sourcepath",
    "rawtext",
    "extractedtext",
    "pii",
    "piivalues",
    "personalvalues",
    "reversibletokenmap",
})


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_sha256(value: object, name: str) -> str:
    normalized = str(value or "").casefold()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def opaque_document_id(source_sha256: str, *, id_key: bytes) -> str:
    """Return a stable keyed identifier that does not expose the source digest."""
    digest = _require_sha256(source_sha256, "source_sha256")
    if not isinstance(id_key, bytes) or len(id_key) < 32:
        raise ValueError("id_key must contain at least 32 bytes")
    token = hmac.new(id_key, bytes.fromhex(digest), hashlib.sha256).hexdigest()[:20].upper()
    return f"HWC-{token}"


def _looks_like_private_coordinate(value: str) -> bool:
    stripped = value.strip()
    folded = stripped.casefold()
    return bool(
        stripped.startswith("/")
        or re.match(r"^[a-zA-Z]:[\\/]", stripped)
        or stripped.startswith("\\\\")
        or folded.startswith(("smb://", "file://"))
        or folded.endswith(".hwpx")
    )


def assert_redacted_payload(
    value: object,
    *,
    sensitive_values: Sequence[str] = (),
) -> None:
    """Reject private coordinates, raw fields, or known sensitive values recursively."""
    secrets = tuple(item for item in sensitive_values if item)

    def visit(item: object, pointer: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if _normalized_key(key) in _FORBIDDEN_REDACTED_KEYS:
                    raise ValueError(f"redacted payload contains forbidden key at {pointer}/{key}")
                visit(child, f"{pointer}/{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{pointer}/{index}")
            return
        if isinstance(item, str):
            if _looks_like_private_coordinate(item):
                raise ValueError(f"redacted payload contains a private coordinate at {pointer}")
            if any(secret in item for secret in secrets):
                raise ValueError(f"redacted payload contains a known sensitive value at {pointer}")

    visit(value, "$")


def validate_private_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the authenticated private form of one corpus record."""
    raw = dict(_require_mapping(value, "private record"))
    if raw.get("schema") != PRIVATE_REGISTRY_SCHEMA:
        raise ValueError("unsupported private registry schema")
    document_id = str(raw.get("documentId", ""))
    if not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise ValueError("documentId must be a keyed opaque HWC identifier")

    source = _require_mapping(raw.get("source"), "source")
    source_path = str(source.get("path", ""))
    source_filename = str(source.get("filename", ""))
    if not source_path or not Path(source_path).is_absolute():
        raise ValueError("private source.path must be absolute")
    if not source_filename.casefold().endswith(".hwpx") or Path(source_filename).name != source_filename:
        raise ValueError("private source.filename must be a basename ending in .hwpx")
    _require_sha256(source.get("sha256"), "source.sha256")
    if not isinstance(source.get("sizeBytes"), int) or source["sizeBytes"] < 0:
        raise ValueError("source.sizeBytes must be a non-negative integer")

    storage = _require_mapping(raw.get("storage"), "storage")
    if storage.get("authenticatedEncryption") is not True:
        raise ValueError("private registry requires authenticated encryption")
    if not storage.get("keyId") or not storage.get("algorithm"):
        raise ValueError("private registry storage requires keyId and algorithm")

    privacy = _require_mapping(raw.get("privacy"), "privacy")
    decision = str(privacy.get("decision", ""))
    if decision not in PRIVACY_DECISIONS:
        raise ValueError(f"unsupported privacy decision: {decision!r}")
    if not privacy.get("detectorStatus"):
        raise ValueError("privacy.detectorStatus is required")
    if decision != "unreviewed" and (not privacy.get("reviewedBy") or not privacy.get("reviewedAt")):
        raise ValueError("a non-unreviewed privacy decision requires reviewer provenance")
    if decision == "approved_sanitized" and (
        not privacy.get("sanitizedDerivativeId") or privacy.get("sanitizationReviewed") is not True
    ):
        raise ValueError("approved_sanitized requires a reviewed sanitized derivative")

    lineage = _require_mapping(raw.get("lineage"), "lineage")
    if not str(lineage.get("groupId", "")).startswith("LIN-"):
        raise ValueError("lineage.groupId is required")
    if not isinstance(raw.get("openSafetyOk"), bool):
        raise ValueError("openSafetyOk must be a boolean")
    return raw


def eligibility_status(value: Mapping[str, Any]) -> str:
    """Return ``normal``, ``negative_control``, or ``ineligible`` fail-closed."""
    raw = validate_private_record(value)
    privacy = raw["privacy"]
    decision = privacy["decision"]
    if decision == "repair_negative":
        return "negative_control"
    if decision not in NORMAL_ELIGIBLE_DECISIONS:
        return "ineligible"
    if raw["openSafetyOk"] is not True:
        return "ineligible"
    # A detector-only none_detected result cannot satisfy the reviewer fields
    # that validate_private_record requires for either approved decision.
    return "normal"


def redact_private_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Produce the report-safe aggregate form without source fingerprints."""
    raw = validate_private_record(value)
    privacy = raw["privacy"]
    redacted = {
        "schema": REDACTED_REGISTRY_SCHEMA,
        "documentId": raw["documentId"],
        "family": raw.get("family", "unknown"),
        "state": raw.get("state", "unknown"),
        "complexity": raw.get("complexity", "unknown"),
        "privacyDisposition": privacy["decision"],
        "practiceEligibility": eligibility_status(raw),
        "lineageGroup": raw["lineage"]["groupId"],
        "suitability": raw.get("suitability", "unreviewed"),
        "openSafetyOk": raw["openSafetyOk"],
    }
    assert_redacted_payload(redacted)
    return redacted


def validate_storage_roots(source_root: str | Path, work_root: str | Path) -> tuple[Path, Path]:
    """Reject overlapping source/work roots before any filesystem operation."""
    source = Path(source_root).expanduser().resolve(strict=False)
    work = Path(work_root).expanduser().resolve(strict=False)
    if source == work or source in work.parents or work in source.parents:
        raise ValueError("source and work roots must be disjoint")
    return source, work


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_source_tree(source_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read and hash every source file without creating output or sidecars."""
    root = Path(source_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source root must be a directory")
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ValueError("source tree symlinks are not allowed")
        if not path.is_file():
            continue
        relative = unicodedata.normalize("NFC", path.relative_to(root).as_posix())
        if relative in snapshot:
            raise ValueError("source tree contains a Unicode-normalization path collision")
        snapshot[relative] = {"sha256": _file_sha256(path), "sizeBytes": path.stat().st_size}
    return snapshot


def _validate_snapshot(value: Mapping[str, Mapping[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relative, metadata in value.items():
        normalized_relative = unicodedata.normalize("NFC", str(relative).replace("\\", "/"))
        relative_path = Path(normalized_relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"{name} contains an unsafe relative path")
        if normalized_relative in result:
            raise ValueError(f"{name} contains a Unicode-normalization path collision")
        row = dict(_require_mapping(metadata, f"{name}[{relative!r}]"))
        result[normalized_relative] = {
            "sha256": _require_sha256(row.get("sha256"), f"{name}.sha256"),
            "sizeBytes": row.get("sizeBytes"),
        }
        if not isinstance(result[normalized_relative]["sizeBytes"], int) or result[normalized_relative]["sizeBytes"] < 0:
            raise ValueError(f"{name}.sizeBytes must be a non-negative integer")
    return result


def build_source_integrity_receipt(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    *,
    write_events: int = 0,
) -> dict[str, Any]:
    """Compare private snapshots and return a path-free integrity receipt."""
    if not isinstance(write_events, int) or write_events < 0:
        raise ValueError("write_events must be a non-negative integer")
    left = _validate_snapshot(before, "before")
    right = _validate_snapshot(after, "after")
    added = set(right) - set(left)
    removed = set(left) - set(right)
    changed = {name for name in set(left) & set(right) if left[name] != right[name]}
    unchanged = not added and not removed and not changed and write_events == 0
    receipt = {
        "schema": SOURCE_INTEGRITY_SCHEMA,
        "beforeManifestSha256": _canonical_sha256(left),
        "afterManifestSha256": _canonical_sha256(right),
        "sourceFileCountBefore": len(left),
        "sourceFileCountAfter": len(right),
        "addedCount": len(added),
        "removedCount": len(removed),
        "changedCount": len(changed),
        "writeEventCount": write_events,
        "unchanged": unchanged,
    }
    assert_redacted_payload(receipt)
    return receipt


__all__ = [
    "DOCUMENT_ID_PATTERN",
    "PRIVATE_REGISTRY_SCHEMA",
    "PRIVACY_DECISIONS",
    "REDACTED_REGISTRY_SCHEMA",
    "SHA256_PATTERN",
    "SOURCE_INTEGRITY_SCHEMA",
    "assert_redacted_payload",
    "build_source_integrity_receipt",
    "eligibility_status",
    "opaque_document_id",
    "redact_private_record",
    "snapshot_source_tree",
    "validate_private_record",
    "validate_storage_roots",
]
