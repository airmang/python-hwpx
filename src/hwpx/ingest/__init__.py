# SPDX-License-Identifier: Apache-2.0
"""Document ingest primitives for HWPX-first Markdown conversion."""

from .base import (
    ConversionAttempt,
    DocumentConverter,
    DocumentIngestError,
    DocumentIngestResult,
    DocumentIngestor,
    DocumentSourceInfo,
    UnsupportedDocumentFormat,
    normalize_markdown,
)
from .hwpx_converter import HwpxMarkdownConverter

__all__ = [
    "ConversionAttempt",
    "DocumentConverter",
    "DocumentIngestError",
    "DocumentIngestResult",
    "DocumentIngestor",
    "DocumentSourceInfo",
    "HwpxMarkdownConverter",
    "UnsupportedDocumentFormat",
    "normalize_markdown",
]
