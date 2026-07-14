"""Reproducible benchmark contracts for the installed HWPX stack."""

from .blind_eval import (
    BENCHMARK_SCHEMA,
    REQUIRED_FAMILIES,
    build_result_projections,
    canonical_sha256,
    check_projection_drift,
    measure_fixture_benchmark,
    validate_fixture_manifest,
    validate_fixture_result_manifest,
    wilson_interval,
)

__all__ = [
    "BENCHMARK_SCHEMA",
    "REQUIRED_FAMILIES",
    "build_result_projections",
    "canonical_sha256",
    "check_projection_drift",
    "measure_fixture_benchmark",
    "validate_fixture_manifest",
    "validate_fixture_result_manifest",
    "wilson_interval",
]
