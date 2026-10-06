# SPDX-License-Identifier: Apache-2.0
"""Tooling helpers, loaded on first use rather than on the first save."""

from __future__ import annotations

import sys as _sys
from types import ModuleType as _ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .exporter import (
        export_html,
        export_markdown,
        export_text,
    )
    from .layout_preview import (
        LayoutPreview,
        PreviewPage,
        render_layout_preview,
    )
    from .document_viewer import (
        DocumentViewer,
        FIDELITY_BADGE,
        render_document_viewer,
    )
    from .object_finder import FoundElement, ObjectFinder
    from .doc_diff import (
        DOC_DIFF_REPORT_VERSION,
        REFERENCE_CONSISTENCY_REPORT_VERSION,
        diff_paragraphs,
        doc_diff,
        inspect_reference_consistency,
    )
    from .mail_merge import (
        MAIL_MERGE_REPORT_VERSION,
        inspect_mail_merge_placeholders,
        load_mail_merge_rows,
        merge_template_rows,
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
    "inspect_reference_consistency",
    "doc_diff",
    "diff_paragraphs",
    "REFERENCE_CONSISTENCY_REPORT_VERSION",
    "DOC_DIFF_REPORT_VERSION",
    "merge_template_rows",
    "load_mail_merge_rows",
    "inspect_mail_merge_placeholders",
    "MAIL_MERGE_REPORT_VERSION",
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
    "EDITOR_OPEN_ADVISORY_ERROR_MARKERS",
    "EditorOpenSafetyReport",
    "PackageValidationIssue",
    "PackageValidationReport",
    "is_editor_open_blocking_issue",
    "validate_editor_open_safety",
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
    "LayoutPreview",
    "PreviewPage",
    "render_layout_preview",
    "DocumentViewer",
    "FIDELITY_BADGE",
    "render_document_viewer",
]


_EXPORTS_BY_MODULE = {
    "exporter": (
        "export_html",
        "export_markdown",
        "export_text",
    ),
    "layout_preview": (
        "LayoutPreview",
        "PreviewPage",
        "render_layout_preview",
    ),
    "document_viewer": (
        "DocumentViewer",
        "FIDELITY_BADGE",
        "render_document_viewer",
    ),
    "object_finder": (
        "FoundElement",
        "ObjectFinder",
    ),
    "doc_diff": (
        "DOC_DIFF_REPORT_VERSION",
        "REFERENCE_CONSISTENCY_REPORT_VERSION",
        "diff_paragraphs",
        "doc_diff",
        "inspect_reference_consistency",
    ),
    "mail_merge": (
        "MAIL_MERGE_REPORT_VERSION",
        "inspect_mail_merge_placeholders",
        "load_mail_merge_rows",
        "merge_template_rows",
    ),
    "package_validator": (
        "EDITOR_OPEN_ADVISORY_ERROR_MARKERS",
        "EditorOpenSafetyReport",
        "PackageValidationIssue",
        "PackageValidationReport",
        "is_editor_open_blocking_issue",
        "validate_editor_open_safety",
        "validate_package",
    ),
    "page_guard": (
        "DocumentMetrics",
        "collect_metrics",
        "compare_metrics",
    ),
    "text_extractor": (
        "DEFAULT_NAMESPACES",
        "ParagraphInfo",
        "SectionInfo",
        "TextExtractor",
        "build_parent_map",
        "describe_element_path",
        "strip_namespace",
    ),
    "table_navigation": (
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
    ),
    "validator": (
        "DocumentSchemas",
        "ValidationIssue",
        "ValidationReport",
        "load_default_schemas",
        "validate_document",
    ),
}
_EXPORT_OWNER = {
    name: module for module, names in _EXPORTS_BY_MODULE.items() for name in names
}


def __getattr__(name: str) -> object:
    """Resolve public exports and the historically reachable submodules."""
    owner = _EXPORT_OWNER.get(name, name)
    if owner == "exporter":
        import hwpx.tools.exporter as module
    elif owner == "layout_preview":
        import hwpx.tools.layout_preview as module
    elif owner == "document_viewer":
        import hwpx.tools.document_viewer as module
    elif owner == "object_finder":
        import hwpx.tools.object_finder as module
    elif owner == "doc_diff":
        from .doc_diff import doc_diff as value

        globals()["doc_diff"] = value
        module = _sys.modules[f"{__name__}.doc_diff"]
    elif owner == "mail_merge":
        import hwpx.tools.mail_merge as module
    elif owner == "package_validator":
        import hwpx.tools.package_validator as module
    elif owner == "page_guard":
        import hwpx.tools.page_guard as module
    elif owner == "text_extractor":
        import hwpx.tools.text_extractor as module
    elif owner == "table_navigation":
        import hwpx.tools.table_navigation as module
    elif owner == "validator":
        import hwpx.tools.validator as module
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = getattr(module, name) if name in _EXPORT_OWNER else module
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | set(_EXPORTS_BY_MODULE))


class _ToolsModule(_ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        # Python assigns a loaded child to its parent. Here the public doc_diff
        # function has always occupied that name. Preserve it even when someone
        # imports the child directly before any package export is resolved.
        if (
            name == "doc_diff"
            and isinstance(value, _ModuleType)
            and value.__name__ == f"{__name__}.doc_diff"
        ):
            value = value.doc_diff
        super().__setattr__(name, value)


_sys.modules[__name__].__class__ = _ToolsModule
