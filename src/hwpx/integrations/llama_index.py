# SPDX-License-Identifier: Apache-2.0
"""LlamaIndex reader for ``.hwpx`` and ``.hwp`` files.

Needs ``llama-index-core``: ``pip install "python-hwpx[llamaindex]"``.

    from hwpx.integrations.llama_index import HwpxReader

    docs = HwpxReader().load_data("계획.hwpx")

The reader is a thin layer over :mod:`hwpx.ingest`: the text is the Markdown
that :class:`hwpx.ingest.DocumentIngestor` produces (headings, lists and tables
kept), and the metadata is
:meth:`hwpx.ingest.DocumentIngestResult.flat_metadata`.
"""

from __future__ import annotations

from os import PathLike, fspath
from typing import Any

try:
    from llama_index.core.readers.base import BaseReader
    from llama_index.core.schema import Document
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "hwpx.integrations.llama_index needs llama-index-core. "
        'Install it with: pip install "python-hwpx[llamaindex]"'
    ) from exc

from ..ingest import DocumentIngestor

__all__ = ["HwpxReader"]


class HwpxReader(BaseReader):
    """Read one ``.hwpx`` or ``.hwp`` file as a single Markdown document.

    Use it on its own, or hand it to ``SimpleDirectoryReader`` for a folder::

        reader = HwpxReader()
        SimpleDirectoryReader("문서", file_extractor={".hwpx": reader, ".hwp": reader})

    Splitting is left to LlamaIndex's node parsers; the Markdown keeps ``#``
    headings, so ``MarkdownNodeParser`` can cut along the document's own
    sections.

    The metadata holds only strings and integers (``source``, ``source_format``,
    ``lossiness``, paragraph and table counts, …). ``lossiness`` and ``warnings``
    say what the Markdown leaves out, such as headers or memos. Keys given in
    *extra_info* (``SimpleDirectoryReader`` passes the file's name and dates)
    are added and win over the reader's own.

    A file that cannot be read (a password-protected document, HWP 3.x, a
    damaged file) raises :class:`hwpx.ingest.UnsupportedDocumentFormat` with the
    reason in the message.
    """

    def __init__(self, *, markdown_options: dict[str, Any] | None = None) -> None:
        """*markdown_options* are passed to ``doc.text.markdown(rich=True, ...)``."""

        super().__init__()
        self.markdown_options = dict(markdown_options or {})

    def load_data(
        self,
        file: str | PathLike[str],
        extra_info: dict[str, Any] | None = None,
        **load_kwargs: Any,
    ) -> list[Document]:
        result = DocumentIngestor.default().convert(
            fspath(file),
            markdown_options=self.markdown_options,
        )
        metadata: dict[str, Any] = dict(result.flat_metadata())
        metadata.update(extra_info or {})
        return [Document(text=result.markdown, metadata=metadata)]
