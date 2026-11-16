# SPDX-License-Identifier: Apache-2.0
"""Tooling helpers, loaded on first use rather than on the first save.

7.0 moved the converting and guessing helpers this package used to re-export
(Markdown/HTML export, the layout preview and document viewer, mail merge, the
reference consistency lint, label-guided table filling) to python-hwpx-automation.
Asking for one of those names raises an ``ImportError`` that names its new place
(:data:`hwpx._moved_modules.MOVED_IN_7_0_NAMES`).
"""

from __future__ import annotations

import sys as _sys
from types import ModuleType as _ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .exporter import export_text
    from .object_finder import FoundElement, ObjectFinder
    from .doc_diff import (
        DOC_DIFF_REPORT_VERSION,
        diff_paragraphs,
        doc_diff,
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
        TableMapEntry,
        TableMapResult,
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
    "doc_diff",
    "diff_paragraphs",
    "DOC_DIFF_REPORT_VERSION",
    "DEFAULT_NAMESPACES",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "build_parent_map",
    "describe_element_path",
    "strip_namespace",
    "TableMapEntry",
    "TableMapResult",
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
]


_EXPORTS_BY_MODULE = {
    "exporter": ("export_text",),
    "object_finder": (
        "FoundElement",
        "ObjectFinder",
    ),
    "doc_diff": (
        "DOC_DIFF_REPORT_VERSION",
        "diff_paragraphs",
        "doc_diff",
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
        "TableMapEntry",
        "TableMapResult",
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
    elif owner == "object_finder":
        import hwpx.tools.object_finder as module
    elif owner == "doc_diff":
        from .doc_diff import doc_diff as value

        globals()["doc_diff"] = value
        module = _sys.modules[f"{__name__}.doc_diff"]
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
        from .._moved_modules import moved_name_error

        moved = moved_name_error(__name__, name)
        if moved is not None:
            raise moved
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
