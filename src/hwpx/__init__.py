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
from .document import HwpxDocument
from .package import HwpxPackage

__all__ = [
    "__version__",
    "DEFAULT_NAMESPACES",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "FoundElement",
    "ObjectFinder",
    "HwpxDocument",
    "HwpxPackage",
]
