"""Privacy-gated contracts for deterministic HWPX practice corpora.

The package deliberately starts with contracts and fail-closed validators.  Real
corpus intake and document mutation are added only after these boundaries are
covered by tests.
"""

from .lineage import (
    LINEAGE_KINDS,
    LineageEdge,
    build_lineage_groups,
    validate_partition_closure,
)
from .registry import (
    PRIVATE_REGISTRY_SCHEMA,
    REDACTED_REGISTRY_SCHEMA,
    SOURCE_INTEGRITY_SCHEMA,
    assert_redacted_payload,
    build_source_integrity_receipt,
    eligibility_status,
    opaque_document_id,
    redact_private_record,
    snapshot_source_tree,
    validate_private_record,
    validate_storage_roots,
)
from .scenario import PRACTICE_SCENARIO_SCHEMA, scenario_id, validate_scenario

__all__ = [
    "LINEAGE_KINDS",
    "PRIVATE_REGISTRY_SCHEMA",
    "PRACTICE_SCENARIO_SCHEMA",
    "REDACTED_REGISTRY_SCHEMA",
    "SOURCE_INTEGRITY_SCHEMA",
    "LineageEdge",
    "assert_redacted_payload",
    "build_lineage_groups",
    "build_source_integrity_receipt",
    "eligibility_status",
    "opaque_document_id",
    "redact_private_record",
    "scenario_id",
    "snapshot_source_tree",
    "validate_partition_closure",
    "validate_private_record",
    "validate_scenario",
    "validate_storage_roots",
]
