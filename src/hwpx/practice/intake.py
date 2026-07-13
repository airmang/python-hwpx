"""Read-only discovery intake and explicit local privacy disposition."""
from __future__ import annotations

import copy
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .lineage import LineageEdge, build_lineage_groups
from .registry import (
    PRIVATE_REGISTRY_SCHEMA,
    build_source_integrity_receipt,
    opaque_document_id,
    redact_private_record,
    snapshot_source_tree,
    validate_private_record,
    validate_storage_roots,
)

_DISCOVERY_GROUPS = {
    "x_group": "exact_duplicate",
    "t_group": "normalized_text_duplicate",
    "near_group": "near_content",
}
_SYSTEM_DISPOSITIONS = {
    "quarantine_privacy": "quarantine",
    "hold_repair_required": "repair_negative",
    "exclude_exact_duplicate": "excluded_duplicate",
}
_REVIEW_BASIS_REQUIRED = frozenset({"local_pii_scan", "content_review"})


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision: str
    reviewed_by: str
    reviewed_at: str
    review_basis: tuple[str, ...]
    sanitized_derivative_id: str | None = None
    sanitization_reviewed: bool = False


@dataclass(frozen=True, slots=True)
class IntakeResult:
    private_records: tuple[dict[str, Any], ...]
    redacted_records: tuple[dict[str, Any], ...]
    lineage_groups: Mapping[str, str]
    lineage_edges: tuple[LineageEdge, ...]
    source_integrity: Mapping[str, Any]


def _normalize_relative(value: object) -> str:
    normalized = unicodedata.normalize("NFC", str(value or "").replace("\\", "/"))
    path = Path(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError("discovery relative_path must stay inside the source root")
    return normalized


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    folded = str(value or "").strip().casefold()
    if folded in {"true", "1", "yes"}:
        return True
    if folded in {"false", "0", "no"}:
        return False
    raise ValueError(f"expected a boolean value, got {value!r}")


def _system_privacy(row: Mapping[str, Any]) -> dict[str, Any]:
    recommendation = str(row.get("practice_suitability", "unreviewed"))
    decision = _SYSTEM_DISPOSITIONS.get(recommendation, "unreviewed")
    result: dict[str, Any] = {
        "detectorStatus": str(row.get("privacy_risk", "unknown")),
        "decision": decision,
        "recommendedDisposition": recommendation,
    }
    if decision != "unreviewed":
        result.update({
            "reviewedBy": "system:private-corpus-classification/v1",
            "reviewedAt": "2026-07-13T00:00:00Z",
            "reviewBasis": ["fail_closed_classification"],
        })
    return result


def _group_edges(
    rows: Sequence[Mapping[str, Any]],
    document_ids: Sequence[str],
) -> list[LineageEdge]:
    edges: list[LineageEdge] = []
    for field, kind in _DISCOVERY_GROUPS.items():
        buckets: dict[str, list[str]] = {}
        for row, document_id in zip(rows, document_ids):
            group = str(row.get(field, "")).strip()
            if group:
                buckets.setdefault(group, []).append(document_id)
        for members in buckets.values():
            first, *rest = members
            edges.extend(LineageEdge(first, member, kind) for member in rest)
    return edges


def intake_discovery_rows(
    *,
    source_root: str | Path,
    work_root: str | Path,
    rows: Sequence[Mapping[str, Any]],
    id_key: bytes,
    storage_key_id: str,
    storage_algorithm: str = "AES-256-GCM",
) -> IntakeResult:
    """Bind discovery metadata to current source bytes without writing either root."""
    source, _work = validate_storage_roots(source_root, work_root)
    if not rows:
        raise ValueError("discovery intake requires at least one row")
    normalized_rows = [dict(row) for row in rows]
    paths = [_normalize_relative(row.get("relative_path")) for row in normalized_rows]
    if len(paths) != len(set(paths)):
        raise ValueError("discovery rows contain duplicate or Unicode-colliding paths")
    expected: dict[str, dict[str, Any]] = {}
    for relative, row in zip(paths, normalized_rows):
        try:
            size = int(row.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ValueError("discovery size_bytes must be an integer") from exc
        expected[relative] = {"sha256": str(row.get("sha256", "")), "sizeBytes": size}
    actual = snapshot_source_tree(source)
    integrity = build_source_integrity_receipt(expected, actual)
    if integrity["unchanged"] is not True:
        raise ValueError("discovery metadata does not match the current source tree")

    ordered = sorted(
        zip(paths, normalized_rows),
        key=lambda item: item[0].casefold(),
    )
    document_ids = [
        opaque_document_id(
            str(row["sha256"]),
            id_key=id_key,
            occurrence_key=relative,
        )
        for relative, row in ordered
    ]
    ordered_rows = [row for _path, row in ordered]
    edges = _group_edges(ordered_rows, document_ids)
    groups = build_lineage_groups(document_ids, edges, id_key=id_key)

    records: list[dict[str, Any]] = []
    for (relative, row), document_id in zip(ordered, document_ids):
        source_path = source / relative
        record = {
            "schema": PRIVATE_REGISTRY_SCHEMA,
            "documentId": document_id,
            "source": {
                "path": str(source),
                "filename": source_path.name,
                "sha256": str(row["sha256"]),
                "sizeBytes": int(row["size_bytes"]),
            },
            "storage": {
                "authenticatedEncryption": True,
                "keyId": storage_key_id,
                "algorithm": storage_algorithm,
            },
            "privacy": _system_privacy(row),
            "lineage": {"groupId": groups[document_id]},
            "family": str(row.get("family", "unknown")),
            "state": str(row.get("state", "unknown")),
            "complexity": str(row.get("complexity", "unknown")),
            "suitability": str(row.get("practice_suitability", "unreviewed")),
            "openSafetyOk": _bool_value(row.get("open_safety_ok")),
        }
        records.append(validate_private_record(record))
    redacted = tuple(redact_private_record(record) for record in records)
    return IntakeResult(
        private_records=tuple(records),
        redacted_records=redacted,
        lineage_groups=dict(groups),
        lineage_edges=tuple(edges),
        source_integrity=dict(integrity),
    )


def apply_review_decision(
    value: Mapping[str, Any],
    decision: ReviewDecision,
) -> dict[str, Any]:
    """Apply a local review without allowing detector-only promotion."""
    raw = validate_private_record(value)
    if not decision.reviewed_by or not decision.reviewed_at:
        raise ValueError("privacy promotion requires reviewer provenance")
    basis = set(decision.review_basis)
    if decision.decision in {"approved_local_only", "approved_sanitized"}:
        missing = _REVIEW_BASIS_REQUIRED - basis
        if missing:
            raise ValueError("privacy promotion requires local_pii_scan and content_review")
        if raw["openSafetyOk"] is not True:
            raise ValueError("normal practice eligibility requires openSafetyOk=true")
    if decision.decision == "approved_sanitized" and (
        not decision.sanitized_derivative_id or decision.sanitization_reviewed is not True
    ):
        raise ValueError("approved_sanitized requires a reviewed derivative")

    updated = copy.deepcopy(raw)
    privacy = {
        "detectorStatus": raw["privacy"]["detectorStatus"],
        "decision": decision.decision,
        "recommendedDisposition": raw["privacy"].get("recommendedDisposition", "unreviewed"),
        "reviewedBy": decision.reviewed_by,
        "reviewedAt": decision.reviewed_at,
        "reviewBasis": sorted(basis),
    }
    if decision.decision == "approved_sanitized":
        privacy.update({
            "sanitizedDerivativeId": decision.sanitized_derivative_id,
            "sanitizationReviewed": True,
        })
    updated["privacy"] = privacy
    return validate_private_record(updated)


__all__ = [
    "IntakeResult",
    "ReviewDecision",
    "apply_review_decision",
    "intake_discovery_rows",
]
