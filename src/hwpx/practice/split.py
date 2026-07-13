"""Deterministic, lineage-closed practice/validation/holdout manifests."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .lineage import PARTITIONS, validate_partition_closure
from .registry import (
    DOCUMENT_ID_PATTERN,
    REDACTED_REGISTRY_SCHEMA,
    assert_redacted_payload,
)

SPLIT_MANIFEST_SCHEMA = "hwpx.private-corpus-split/v1"
_PARTITION_ORDER = ("practice", "validation", "holdout")
_TARGET_RATIOS = {"practice": 0.60, "validation": 0.20, "holdout": 0.20}
_ELIGIBLE = frozenset({"normal", "negative_control"})
_GLOBAL_RATIO_WEIGHT = 1000.0


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_hash(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "manifestSha256"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _seed_token(seed: str, group_id: str) -> str:
    return hashlib.sha256(f"{seed}\n{group_id}".encode("utf-8")).hexdigest()


def _validate_redacted_record(value: Mapping[str, Any]) -> dict[str, str]:
    raw = dict(value)
    assert_redacted_payload(raw)
    if raw.get("schema") != REDACTED_REGISTRY_SCHEMA:
        raise ValueError("split input must use the redacted registry schema")
    document_id = str(raw.get("documentId", ""))
    if not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise ValueError("split input documentId must be opaque")
    lineage_group = str(raw.get("lineageGroup", ""))
    if not lineage_group.startswith("LIN-"):
        raise ValueError("split input lineageGroup is required")
    eligibility = str(raw.get("practiceEligibility", ""))
    if eligibility not in _ELIGIBLE | {"ineligible"}:
        raise ValueError("split input practiceEligibility is invalid")
    return {
        "documentId": document_id,
        "lineageGroup": lineage_group,
        "family": str(raw.get("family", "unknown")),
        "state": str(raw.get("state", "unknown")),
        "complexity": str(raw.get("complexity", "unknown")),
        "practiceEligibility": eligibility,
    }


def _stratum(entry: Mapping[str, str]) -> str:
    return "|".join(
        (
            entry["practiceEligibility"],
            entry["family"],
            entry["state"],
            entry["complexity"],
        )
    )


def _assignment_score(
    partition: str,
    group_counts: Counter[str],
    group_size: int,
    *,
    partition_counts: Mapping[str, int],
    stratum_counts: Mapping[str, Counter[str]],
    total_documents: int,
    totals_by_stratum: Counter[str],
) -> tuple[float, float, int]:
    """Return a deterministic cost favoring global and per-stratum targets."""
    global_after = dict(partition_counts)
    global_after[partition] += group_size
    global_cost = sum(
        (
            global_after[candidate]
            - (total_documents * _TARGET_RATIOS[candidate])
        )
        ** 2
        for candidate in _PARTITION_ORDER
    ) / max(1.0, float(total_documents**2))
    stratum_cost = 0.0
    for name, increment in group_counts.items():
        total = totals_by_stratum[name]
        after = dict(stratum_counts[name])
        after[partition] = after.get(partition, 0) + increment
        stratum_cost += sum(
            (after.get(candidate, 0) - (total * _TARGET_RATIOS[candidate])) ** 2
            for candidate in _PARTITION_ORDER
        ) / max(1.0, float(total**2))
    # A group can contain several rare strata.  Average their cost so group
    # diversity cannot overwhelm the requested 60/20/20 global allocation.
    stratum_cost /= max(1, len(group_counts))
    # Prefer a partition with more remaining global capacity when costs tie.
    remaining = (
        total_documents * _TARGET_RATIOS[partition]
        - partition_counts[partition]
    )
    return (
        (_GLOBAL_RATIO_WEIGHT * global_cost) + stratum_cost,
        -remaining,
        _PARTITION_ORDER.index(partition),
    )


def build_split_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    seed: str,
    corpus_version: str,
) -> dict[str, Any]:
    """Build a path-free 60/20/20 manifest while keeping lineage atomic."""
    if not seed or not corpus_version:
        raise ValueError("seed and corpus_version are required")
    normalized = [_validate_redacted_record(record) for record in records]
    ids = [record["documentId"] for record in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("split input documentIds must be unique")
    eligible = [record for record in normalized if record["practiceEligibility"] in _ELIGIBLE]
    if not eligible:
        raise ValueError("split input has no eligible documents")

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in eligible:
        groups[record["lineageGroup"]].append(record)
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), _seed_token(seed, item[0])),
    )
    totals_by_stratum: Counter[str] = Counter(_stratum(item) for item in eligible)
    partition_counts = {partition: 0 for partition in _PARTITION_ORDER}
    stratum_counts: dict[str, Counter[str]] = defaultdict(Counter)
    assignments: dict[str, str] = {}

    for group_id, members in ordered_groups:
        counts = Counter(_stratum(member) for member in members)
        partition = min(
            _PARTITION_ORDER,
            key=lambda candidate: _assignment_score(
                candidate,
                counts,
                len(members),
                partition_counts=partition_counts,
                stratum_counts=stratum_counts,
                total_documents=len(eligible),
                totals_by_stratum=totals_by_stratum,
            ),
        )
        partition_counts[partition] += len(members)
        for name, count in counts.items():
            stratum_counts[name][partition] += count
        for member in members:
            assignments[member["documentId"]] = partition

    lineage = {record["documentId"]: record["lineageGroup"] for record in eligible}
    validate_partition_closure(assignments, lineage)
    entries = [
        {
            **record,
            "split": assignments[record["documentId"]],
        }
        for record in sorted(eligible, key=lambda item: item["documentId"])
    ]
    represented = sorted({record["family"] for record in eligible})
    manifest: dict[str, Any] = {
        "schema": SPLIT_MANIFEST_SCHEMA,
        "corpusVersion": corpus_version,
        "seedSha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "targetRatios": dict(_TARGET_RATIOS),
        "counts": {
            "input": len(normalized),
            "eligible": len(eligible),
            "ineligible": len(normalized) - len(eligible),
            "lineageGroups": len(groups),
            "bySplit": partition_counts,
        },
        "representedFamilies": represented,
        "missingFamilyCoverage": [],
        "entries": entries,
    }
    manifest["manifestSha256"] = _manifest_hash(manifest)
    assert_redacted_payload(manifest)
    return manifest


def validate_split_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate hash, aggregate counts, and lineage closure of a split manifest."""
    raw = dict(value)
    assert_redacted_payload(raw)
    if raw.get("schema") != SPLIT_MANIFEST_SCHEMA:
        raise ValueError("unsupported split manifest schema")
    if raw.get("manifestSha256") != _manifest_hash(raw):
        raise ValueError("split manifest hash mismatch")
    entries_value = raw.get("entries")
    if not isinstance(entries_value, list) or not entries_value:
        raise ValueError("split manifest entries must be a non-empty list")
    entries: list[dict[str, str]] = []
    assignments: dict[str, str] = {}
    lineage: dict[str, str] = {}
    for item in entries_value:
        if not isinstance(item, Mapping):
            raise ValueError("split manifest entries must be objects")
        entry = _validate_redacted_record({
            "schema": REDACTED_REGISTRY_SCHEMA,
            **item,
        })
        partition = str(item.get("split", ""))
        if partition not in PARTITIONS:
            raise ValueError("split manifest entry has an invalid split")
        if entry["practiceEligibility"] not in _ELIGIBLE:
            raise ValueError("split manifest cannot contain ineligible entries")
        document_id = entry["documentId"]
        if document_id in assignments:
            raise ValueError("split manifest documentIds must be unique")
        assignments[document_id] = partition
        lineage[document_id] = entry["lineageGroup"]
        entries.append(entry)
    validate_partition_closure(assignments, lineage)
    counts = raw.get("counts")
    if not isinstance(counts, Mapping):
        raise ValueError("split manifest counts are required")
    actual_by_split = Counter(assignments.values())
    expected_by_split = counts.get("bySplit")
    if not isinstance(expected_by_split, Mapping) or any(
        int(expected_by_split.get(partition, -1)) != actual_by_split[partition]
        for partition in _PARTITION_ORDER
    ):
        raise ValueError("split manifest aggregate counts do not match entries")
    if int(counts.get("eligible", -1)) != len(entries):
        raise ValueError("split manifest eligible count does not match entries")
    return raw


__all__ = [
    "SPLIT_MANIFEST_SCHEMA",
    "build_split_manifest",
    "validate_split_manifest",
]
