"""Lineage closure rules for leakage-safe corpus partitioning."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping, Sequence

from .registry import DOCUMENT_ID_PATTERN

LINEAGE_KINDS = frozenset({
    "exact_duplicate",
    "normalized_text_duplicate",
    "near_content",
    "template_derived",
    "sanitized_derivative",
    "repaired_derivative",
})
PARTITIONS = frozenset({"practice", "validation", "holdout"})


@dataclass(frozen=True, slots=True)
class LineageEdge:
    parent_id: str
    child_id: str
    kind: str

    def __post_init__(self) -> None:
        if not DOCUMENT_ID_PATTERN.fullmatch(self.parent_id):
            raise ValueError("lineage parent_id must be an opaque document id")
        if not DOCUMENT_ID_PATTERN.fullmatch(self.child_id):
            raise ValueError("lineage child_id must be an opaque document id")
        if self.parent_id == self.child_id:
            raise ValueError("lineage edges cannot be self-referential")
        if self.kind not in LINEAGE_KINDS:
            raise ValueError(f"unsupported lineage kind: {self.kind!r}")


def _group_id(members: Sequence[str], *, id_key: bytes) -> str:
    if not isinstance(id_key, bytes) or len(id_key) < 32:
        raise ValueError("id_key must contain at least 32 bytes")
    payload = "\n".join(sorted(members)).encode("ascii")
    token = hmac.new(id_key, payload, hashlib.sha256).hexdigest()[:20].upper()
    return f"LIN-{token}"


def build_lineage_groups(
    document_ids: Sequence[str],
    edges: Sequence[LineageEdge],
    *,
    id_key: bytes,
) -> dict[str, str]:
    """Return document -> transitive keyed lineage group."""
    ids = list(document_ids)
    if len(ids) != len(set(ids)):
        raise ValueError("document_ids must be unique")
    if any(not DOCUMENT_ID_PATTERN.fullmatch(item) for item in ids):
        raise ValueError("document_ids must contain only opaque document ids")
    known = set(ids)
    parent = {item: item for item in ids}

    def find(item: str) -> str:
        root = parent[item]
        if root != item:
            parent[item] = find(root)
        return parent[item]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for edge in edges:
        if not isinstance(edge, LineageEdge):
            raise ValueError("edges must contain LineageEdge values")
        if edge.parent_id not in known or edge.child_id not in known:
            raise ValueError("lineage edge references an unknown document")
        union(edge.parent_id, edge.child_id)

    members_by_root: dict[str, list[str]] = {}
    for document_id in ids:
        members_by_root.setdefault(find(document_id), []).append(document_id)
    group_by_root = {
        root: _group_id(members, id_key=id_key) for root, members in members_by_root.items()
    }
    return {document_id: group_by_root[find(document_id)] for document_id in ids}


def validate_partition_closure(
    assignments: Mapping[str, str],
    lineage_groups: Mapping[str, str],
) -> None:
    """Fail when one lineage group appears in more than one partition."""
    if set(assignments) != set(lineage_groups):
        raise ValueError("partition assignments must cover exactly the lineage registry")
    by_group: dict[str, set[str]] = {}
    for document_id, partition in assignments.items():
        if partition not in PARTITIONS:
            raise ValueError(f"unsupported partition: {partition!r}")
        by_group.setdefault(lineage_groups[document_id], set()).add(partition)
    leaked = sorted(group for group, partitions in by_group.items() if len(partitions) != 1)
    if leaked:
        raise ValueError(f"lineage groups cross partitions: {len(leaked)}")


__all__ = [
    "LINEAGE_KINDS",
    "PARTITIONS",
    "LineageEdge",
    "build_lineage_groups",
    "validate_partition_closure",
]
