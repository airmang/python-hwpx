"""Tooling helpers for inspecting HWPX archives."""

from .object_finder import FoundElement, ObjectFinder
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
    "DocumentSchemas",
    "ValidationIssue",
    "ValidationReport",
    "load_default_schemas",
    "validate_document",
]
