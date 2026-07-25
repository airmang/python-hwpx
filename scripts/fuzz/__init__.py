# SPDX-License-Identifier: Apache-2.0
"""Seeded HWPX fuzzing helpers."""

from .catalog import (
    REPORT_SCHEMA_VERSION,
    REGRESSION_META_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    OperationSpec,
    canonical_json_bytes,
    derive_expected,
    operation_catalog,
    scenario_digest,
)
from .generator import generate_scenario
from .runner import (
    FuzzRunResult,
    run_scenario,
    run_seed_range,
    select_visual_review_samples,
)

__all__ = [
    "FuzzRunResult",
    "OperationSpec",
    "REPORT_SCHEMA_VERSION",
    "REGRESSION_META_SCHEMA_VERSION",
    "SCENARIO_SCHEMA_VERSION",
    "canonical_json_bytes",
    "derive_expected",
    "generate_scenario",
    "operation_catalog",
    "run_scenario",
    "run_seed_range",
    "scenario_digest",
    "select_visual_review_samples",
]
