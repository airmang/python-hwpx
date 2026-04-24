# SPDX-License-Identifier: Apache-2.0
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
