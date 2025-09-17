
"""High-level utilities for working with HWPX documents."""

__version__ = "0.1.0"

from .tools.text_extractor import (
    DEFAULT_NAMESPACES,
    ParagraphInfo,
    SectionInfo,
    TextExtractor,
)
from .tools.object_finder import FoundElement, ObjectFinder

__all__ = [
    "__version__",
    "DEFAULT_NAMESPACES",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "FoundElement",
    "ObjectFinder",
]

