# SPDX-License-Identifier: Apache-2.0
"""High-level utilities for working with HWPX documents."""

from importlib.metadata import PackageNotFoundError, version as _metadata_version


def _resolve_version() -> str:
    """패키지 메타데이터에서 현재 배포 버전을 조회합니다."""
    try:
        return _metadata_version("python-hwpx")
    except PackageNotFoundError:
        return "0+unknown"

def __getattr__(name: str) -> object:
    """Resolve dynamic module attributes."""

    if name == "__version__":
        return _resolve_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

from .tools.text_extractor import (
    DEFAULT_NAMESPACES,
    ParagraphInfo,
    SectionInfo,
    TextExtractor,
)
from .tools.object_finder import FoundElement, ObjectFinder
from .tools.package_validator import (
    EditorOpenSafetyReport,
    PackageValidationReport,
    validate_editor_open_safety,
    validate_package,
)
from .document import HwpxDocument
from .package import HwpxPackage
from .authoring import (
    AUTHORING_REPORT_VERSION,
    DEFAULT_STYLE_PRESET,
    DOCUMENT_PLAN_SCHEMA_VERSION,
    DocumentBlock,
    DocumentPlan,
    DocumentStylePreset,
    PlanValidationIssue,
    PlanValidationReport,
    create_document_from_plan,
    inspect_document_authoring_quality,
    inspect_operating_plan_quality,
    normalize_document_plan,
    validate_document_plan,
)
from .template_formfit import (
    TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION,
    TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION,
    analyze_template_formfit,
    apply_template_formfit,
)

__all__ = [
    "__version__",
    "AUTHORING_REPORT_VERSION",
    "DEFAULT_NAMESPACES",
    "DEFAULT_STYLE_PRESET",
    "DOCUMENT_PLAN_SCHEMA_VERSION",
    "DocumentBlock",
    "DocumentPlan",
    "DocumentStylePreset",
    "EditorOpenSafetyReport",
    "ParagraphInfo",
    "PackageValidationReport",
    "PlanValidationReport",
    "SectionInfo",
    "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION",
    "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION",
    "TextExtractor",
    "FoundElement",
    "ObjectFinder",
    "PlanValidationIssue",
    "HwpxDocument",
    "HwpxPackage",
    "create_document_from_plan",
    "analyze_template_formfit",
    "apply_template_formfit",
    "inspect_document_authoring_quality",
    "inspect_operating_plan_quality",
    "normalize_document_plan",
    "validate_document_plan",
    "validate_editor_open_safety",
    "validate_package",
]
