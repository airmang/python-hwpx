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
from .intake import (
    IntakeResult,
    ReviewDecision,
    apply_review_decision,
    intake_discovery_rows,
)
from .dossier import (
    SYNTHETIC_DOSSIER_SCHEMA,
    synthetic_dossier,
    validate_synthetic_dossier,
)
from .forge import (
    EVALUATOR_MANIFEST_SCHEMA,
    RUNNER_MANIFEST_SCHEMA,
    SCENARIO_PACK_SCHEMA,
    ForgeConfig,
    forge_scenario_pack,
    runner_view,
    validate_scenario_pack,
    write_scenario_pack,
)
from .mutations import (
    CONTROLLED_MUTATION_SCHEMA,
    apply_mutation,
    controlled_mutation,
    mutation_sha256,
    reverse_mutation,
    validate_controlled_mutation,
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
from .sanitize import DERIVATIVE_ID_PATTERN, sanitize_document_copy
from .split import SPLIT_MANIFEST_SCHEMA, build_split_manifest, validate_split_manifest

__all__ = [
    "LINEAGE_KINDS",
    "CONTROLLED_MUTATION_SCHEMA",
    "EVALUATOR_MANIFEST_SCHEMA",
    "DERIVATIVE_ID_PATTERN",
    "ForgeConfig",
    "PRIVATE_REGISTRY_SCHEMA",
    "PRACTICE_SCENARIO_SCHEMA",
    "REDACTED_REGISTRY_SCHEMA",
    "SOURCE_INTEGRITY_SCHEMA",
    "LineageEdge",
    "IntakeResult",
    "ReviewDecision",
    "RUNNER_MANIFEST_SCHEMA",
    "SCENARIO_PACK_SCHEMA",
    "SPLIT_MANIFEST_SCHEMA",
    "SYNTHETIC_DOSSIER_SCHEMA",
    "apply_mutation",
    "apply_review_decision",
    "assert_redacted_payload",
    "build_lineage_groups",
    "build_split_manifest",
    "build_source_integrity_receipt",
    "eligibility_status",
    "controlled_mutation",
    "forge_scenario_pack",
    "opaque_document_id",
    "mutation_sha256",
    "intake_discovery_rows",
    "redact_private_record",
    "scenario_id",
    "sanitize_document_copy",
    "runner_view",
    "reverse_mutation",
    "snapshot_source_tree",
    "validate_partition_closure",
    "validate_private_record",
    "validate_scenario",
    "synthetic_dossier",
    "validate_controlled_mutation",
    "validate_scenario_pack",
    "validate_synthetic_dossier",
    "validate_split_manifest",
    "validate_storage_roots",
    "write_scenario_pack",
]
