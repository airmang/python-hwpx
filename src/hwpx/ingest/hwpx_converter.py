# SPDX-License-Identifier: Apache-2.0
"""HWPX ingest converter."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile

from hwpx.document import HwpxDocument

from .base import DocumentIngestResult, DocumentSourceInfo


class HwpxMarkdownConverter:
    """Convert HWPX packages to rich Markdown and lightweight structure metadata."""

    name = "HwpxMarkdownConverter"

    def accepts(self, file_stream: BinaryIO, source_info: DocumentSourceInfo) -> bool:
        extension = (source_info.extension or "").lower()
        if extension == ".hwpx":
            return True
        mimetype = (source_info.mimetype or "").lower()
        if mimetype in {"application/hwp+zip", "application/x-hwp+zip"}:
            return True
        return _looks_like_hwpx_package(file_stream)

    def convert(
        self,
        file_stream: BinaryIO,
        source_info: DocumentSourceInfo,
        **kwargs: Any,
    ) -> DocumentIngestResult:
        start_pos = file_stream.tell()
        data = file_stream.read()
        file_stream.seek(start_pos)

        markdown_kwargs = dict(kwargs.pop("markdown_options", {}) or {})
        markdown_kwargs.setdefault("detect_headings", True)

        doc = HwpxDocument.open(data)
        try:
            markdown = doc.export_rich_markdown(**markdown_kwargs)
            sections = _sections_payload(doc)
            tables = _tables_payload(doc)
            paragraph_count = len(list(doc.paragraphs))
        finally:
            doc.close()

        return DocumentIngestResult(
            markdown=markdown,
            source_info=source_info,
            source_format="hwpx",
            engine="python-hwpx",
            engine_version=_python_hwpx_version(),
            metadata={
                "section_count": len(sections),
                "paragraph_count": paragraph_count,
                "table_count": len(tables),
                "converter": self.name,
            },
            sections=sections,
            tables=tables,
            lossiness="low",
        )


def _looks_like_hwpx_package(file_stream: BinaryIO) -> bool:
    cur_pos = file_stream.tell()
    try:
        with ZipFile(file_stream) as archive:
            names = set(archive.namelist())
            if "mimetype" in names:
                try:
                    mimetype = archive.read("mimetype").decode("utf-8", "replace").strip()
                    if "hwp" in mimetype.lower() or "hwpx" in mimetype.lower():
                        return True
                except Exception:
                    pass
            return any(name.startswith("Contents/section") and name.endswith(".xml") for name in names)
    except (BadZipFile, OSError):
        return False
    finally:
        file_stream.seek(cur_pos)


def _sections_payload(doc: HwpxDocument) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for index, section in enumerate(doc.sections):
        paragraphs = list(section.paragraphs)
        sections.append(
            {
                "index": index,
                "paragraph_count": len(paragraphs),
                "text_preview": "\n".join(
                    (paragraph.text or "").strip()
                    for paragraph in paragraphs[:5]
                    if (paragraph.text or "").strip()
                )[:500],
            }
        )
    return sections


def _tables_payload(doc: HwpxDocument) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(doc.paragraphs):
        for table in paragraph.tables:
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            tables.append(
                {
                    "table_index": len(tables),
                    "paragraph_index": paragraph_index,
                    "rows": len(rows),
                    "cols": max((len(row) for row in rows), default=0),
                    "data": rows,
                }
            )
    return tables


def _python_hwpx_version() -> str:
    try:
        return package_version("python-hwpx")
    except PackageNotFoundError:
        return "0+unknown"
