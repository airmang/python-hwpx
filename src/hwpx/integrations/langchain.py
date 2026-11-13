# SPDX-License-Identifier: Apache-2.0
"""LangChain document loader for ``.hwpx`` and ``.hwp`` files.

Needs ``langchain-core``: ``pip install "python-hwpx[langchain]"``.

    from hwpx.integrations.langchain import HwpxLoader

    docs = HwpxLoader("계획.hwpx").load()

The loader is a thin layer over :mod:`hwpx.ingest`: the page content is the
Markdown that :class:`hwpx.ingest.DocumentIngestor` produces (headings, lists
and tables kept), and the metadata is
:meth:`hwpx.ingest.DocumentIngestResult.flat_metadata`.
"""

from __future__ import annotations

from os import PathLike, fspath
from typing import Any, Iterator

try:
    from langchain_core.document_loaders import BaseLoader
    from langchain_core.documents import Document
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "hwpx.integrations.langchain needs langchain-core. "
        'Install it with: pip install "python-hwpx[langchain]"'
    ) from exc

from ..ingest import DocumentIngestor

__all__ = ["HwpxLoader"]


class HwpxLoader(BaseLoader):
    """Load one ``.hwpx`` or ``.hwp`` file as a single Markdown document.

    Splitting is left to LangChain's text splitters; the Markdown keeps ``#``
    headings, so ``MarkdownHeaderTextSplitter`` can cut along the document's
    own sections. For a folder, pass this class to ``DirectoryLoader`` as
    ``loader_cls``.

    The metadata holds only strings and integers (``source``, ``source_format``,
    ``lossiness``, paragraph and table counts, …). ``lossiness`` and ``warnings``
    say what the Markdown leaves out, such as headers or memos, so a pipeline can
    tell a complete text from a partial one.

    A file that cannot be read (a password-protected document, HWP 3.x, a
    damaged file) raises :class:`hwpx.ingest.UnsupportedDocumentFormat` with the
    reason in the message.
    """

    def __init__(
        self,
        file_path: str | PathLike[str],
        *,
        markdown_options: dict[str, Any] | None = None,
    ) -> None:
        """*markdown_options* are passed to ``doc.text.markdown(rich=True, ...)``."""

        self.file_path = fspath(file_path)
        self.markdown_options = dict(markdown_options or {})

    def lazy_load(self) -> Iterator[Document]:
        result = DocumentIngestor.default().convert(
            self.file_path,
            markdown_options=self.markdown_options,
        )
        yield Document(page_content=result.markdown, metadata=result.flat_metadata())
