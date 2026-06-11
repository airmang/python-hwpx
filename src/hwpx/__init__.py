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
from .tools.advanced_generators import (
    build_image_grid,
    build_meeting_nameplates,
    build_organization_chart,
)
from .tools.doc_diff import (
    DOC_DIFF_REPORT_VERSION,
    REFERENCE_CONSISTENCY_REPORT_VERSION,
    build_comparison_table_plan,
    diff_paragraphs,
    doc_diff,
    inspect_reference_consistency,
)
from .tools.mail_merge import (
    MAIL_MERGE_REPORT_VERSION,
    inspect_mail_merge_placeholders,
    load_mail_merge_rows,
    mail_merge,
)
from .tools.table_compute import (
    TABLE_COMPUTE_REPORT_VERSION,
    table_compute,
)
from .tools.official_lint import (
    OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION,
    inspect_official_document_style,
)
from .tools.package_validator import (
    EditorOpenSafetyReport,
    PackageValidationReport,
    validate_editor_open_safety,
    validate_package,
)
from .tools.layout_preview import (
    LayoutPreview,
    PreviewPage,
    render_layout_preview,
)
from .patch import (
    BytePreservingPatchResult,
    ParagraphTextPatch,
    PatchApplied,
    PatchSkipped,
    paragraph_patch,
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
from .builder import approval_box
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
    "BytePreservingPatchResult",
    "PlanValidationReport",
    "ParagraphTextPatch",
    "PatchApplied",
    "PatchSkipped",
    "LayoutPreview",
    "PreviewPage",
    "SectionInfo",
    "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION",
    "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION",
    "TextExtractor",
    "FoundElement",
    "ObjectFinder",
    "OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION",
    "DOC_DIFF_REPORT_VERSION",
    "REFERENCE_CONSISTENCY_REPORT_VERSION",
    "MAIL_MERGE_REPORT_VERSION",
    "TABLE_COMPUTE_REPORT_VERSION",
    "build_comparison_table_plan",
    "build_image_grid",
    "build_meeting_nameplates",
    "build_organization_chart",
    "diff_paragraphs",
    "doc_diff",
    "PlanValidationIssue",
    "HwpxDocument",
    "HwpxPackage",
    "create_document_from_plan",
    "analyze_template_formfit",
    "apply_template_formfit",
    "approval_box",
    "inspect_document_authoring_quality",
    "inspect_mail_merge_placeholders",
    "inspect_official_document_style",
    "inspect_reference_consistency",
    "inspect_operating_plan_quality",
    "load_mail_merge_rows",
    "mail_merge",
    "normalize_document_plan",
    "validate_document_plan",
    "validate_editor_open_safety",
    "validate_package",
    "paragraph_patch",
    "render_layout_preview",
    "table_compute",
]
