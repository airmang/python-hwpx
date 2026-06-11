# SPDX-License-Identifier: Apache-2.0
"""Tooling helpers for inspecting HWPX archives."""

from .exporter import (
    export_html,
    export_markdown,
    export_text,
)
from .advanced_generators import (
    build_image_grid,
    build_meeting_nameplates,
    build_organization_chart,
)
from .doc_diff import (
    DOC_DIFF_REPORT_VERSION,
    REFERENCE_CONSISTENCY_REPORT_VERSION,
    build_comparison_table_plan,
    diff_paragraphs,
    doc_diff,
    inspect_reference_consistency,
)
from .mail_merge import (
    MAIL_MERGE_REPORT_VERSION,
    inspect_mail_merge_placeholders,
    load_mail_merge_rows,
    mail_merge,
)
from .table_compute import (
    TABLE_COMPUTE_REPORT_VERSION,
    table_compute,
)
from .layout_preview import (
    LayoutPreview,
    PreviewPage,
    render_layout_preview,
)
from .object_finder import FoundElement, ObjectFinder
from .official_lint import (
    OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION,
    inspect_official_document_style,
)
from .package_validator import (
    EDITOR_OPEN_ADVISORY_ERROR_MARKERS,
    EditorOpenSafetyReport,
    PackageValidationIssue,
    PackageValidationReport,
    is_editor_open_blocking_issue,
    validate_editor_open_safety,
    validate_package,
)
from .style_profile import (
    STYLE_PROFILE_COMPARISON_SCHEMA_VERSION,
    STYLE_PROFILE_SCHEMA_VERSION,
    TEMPLATE_REGISTRY_SCHEMA_VERSION,
    apply_style_profile_to_plan,
    compare_style_profiles,
    describe_template,
    extract_style_profile,
    list_templates,
    placeholder_fill_report,
    register_template,
)
from .page_guard import (
    DocumentMetrics,
    collect_metrics,
    compare_metrics,
)
from .text_extractor import (
    DEFAULT_NAMESPACES,
    ParagraphInfo,
    SectionInfo,
    TextExtractor,
    build_parent_map,
    describe_element_path,
    strip_namespace,
)
from .table_navigation import (
    TableCellReference,
    TableFillApplied,
    TableFillFailed,
    TableFillResult,
    TableLabelMatch,
    TableLabelSearchResult,
    TableMapEntry,
    TableMapResult,
    fill_by_path,
    find_cell_by_label,
    get_table_map,
)
from .validator import (
    DocumentSchemas,
    ValidationIssue,
    ValidationReport,
    load_default_schemas,
    validate_document,
)

__all__ = [
    "DEFAULT_NAMESPACES",
    "build_image_grid",
    "build_meeting_nameplates",
    "build_organization_chart",
    "DOC_DIFF_REPORT_VERSION",
    "REFERENCE_CONSISTENCY_REPORT_VERSION",
    "build_comparison_table_plan",
    "diff_paragraphs",
    "doc_diff",
    "inspect_reference_consistency",
    "MAIL_MERGE_REPORT_VERSION",
    "inspect_mail_merge_placeholders",
    "load_mail_merge_rows",
    "mail_merge",
    "TABLE_COMPUTE_REPORT_VERSION",
    "table_compute",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "build_parent_map",
    "describe_element_path",
    "strip_namespace",
    "TableCellReference",
    "TableFillApplied",
    "TableFillFailed",
    "TableFillResult",
    "TableLabelMatch",
    "TableLabelSearchResult",
    "TableMapEntry",
    "TableMapResult",
    "fill_by_path",
    "find_cell_by_label",
    "get_table_map",
    "FoundElement",
    "ObjectFinder",
    "OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION",
    "inspect_official_document_style",
    "EDITOR_OPEN_ADVISORY_ERROR_MARKERS",
    "EditorOpenSafetyReport",
    "PackageValidationIssue",
    "PackageValidationReport",
    "is_editor_open_blocking_issue",
    "validate_editor_open_safety",
    "validate_package",
    "STYLE_PROFILE_COMPARISON_SCHEMA_VERSION",
    "STYLE_PROFILE_SCHEMA_VERSION",
    "TEMPLATE_REGISTRY_SCHEMA_VERSION",
    "apply_style_profile_to_plan",
    "compare_style_profiles",
    "describe_template",
    "extract_style_profile",
    "list_templates",
    "placeholder_fill_report",
    "register_template",
    "DocumentMetrics",
    "collect_metrics",
    "compare_metrics",
    "DocumentSchemas",
    "ValidationIssue",
    "ValidationReport",
    "load_default_schemas",
    "validate_document",
    "export_text",
    "export_html",
    "export_markdown",
    "LayoutPreview",
    "PreviewPage",
    "render_layout_preview",
]
