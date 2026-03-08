"""Tooling helpers for inspecting HWPX archives."""

from .exporter import (
    export_html,
    export_markdown,
    export_text,
)
from .object_finder import FoundElement, ObjectFinder
from .package_validator import (
    PackageValidationIssue,
    PackageValidationReport,
    validate_package,
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
from .validator import (
    DocumentSchemas,
    ValidationIssue,
    ValidationReport,
    load_default_schemas,
    validate_document,
)

__all__ = [
    "DEFAULT_NAMESPACES",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "build_parent_map",
    "describe_element_path",
    "strip_namespace",
    "FoundElement",
    "ObjectFinder",
    "PackageValidationIssue",
    "PackageValidationReport",
    "validate_package",
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
]
