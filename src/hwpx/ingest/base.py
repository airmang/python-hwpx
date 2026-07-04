# SPDX-License-Identifier: Apache-2.0
"""Small MarkItDown-style ingest dispatcher."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO, TextIOBase
import mimetypes
from pathlib import Path
import re
from typing import Any, BinaryIO, Iterable, Protocol


@dataclass(frozen=True, kw_only=True)
class DocumentSourceInfo:
    """Metadata known or inferred about an input document."""

    mimetype: str | None = None
    extension: str | None = None
    charset: str | None = None
    filename: str | None = None
    local_path: str | None = None
    url: str | None = None

    def copy_and_update(self, *others: "DocumentSourceInfo", **kwargs: Any) -> "DocumentSourceInfo":
        data = asdict(self)
        for other in others:
            data.update({key: val for key, val in asdict(other).items() if val is not None})
        data.update({key: val for key, val in kwargs.items() if val is not None})
        return DocumentSourceInfo(**data)


@dataclass(frozen=True, kw_only=True)
class ConversionAttempt:
    """One converter decision or failure."""

    converter: str
    accepted: bool
    error_type: str | None = None
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: val for key, val in asdict(self).items() if val is not None}


@dataclass(kw_only=True)
class DocumentIngestResult:
    """Normalized Markdown plus structured conversion metadata."""

    markdown: str
    source_info: DocumentSourceInfo
    source_format: str
    engine: str
    engine_version: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sections: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    attempts: list[ConversionAttempt] = field(default_factory=list)
    lossiness: str = "unknown"

    @property
    def text_content(self) -> str:
        """Compatibility alias matching common Markdown conversion APIs."""

        return self.markdown

    def as_dict(self) -> dict[str, Any]:
        return {
            "markdown": self.markdown,
            "sourceInfo": asdict(self.source_info),
            "sourceFormat": self.source_format,
            "engine": self.engine,
            "engineVersion": self.engine_version,
            "title": self.title,
            "metadata": self.metadata,
            "sections": self.sections,
            "tables": self.tables,
            "warnings": self.warnings,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "lossiness": self.lossiness,
        }


class DocumentIngestError(RuntimeError):
    """Base class for ingest failures with converter-attempt diagnostics."""

    def __init__(self, message: str, *, attempts: Iterable[ConversionAttempt] = ()) -> None:
        super().__init__(message)
        self.attempts = list(attempts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "message": str(self),
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }


class UnsupportedDocumentFormat(DocumentIngestError):
    """Raised when no registered converter accepts the source."""


class DocumentConverter(Protocol):
    """Converter contract for a specific source family."""

    name: str

    def accepts(self, file_stream: BinaryIO, source_info: DocumentSourceInfo) -> bool:
        """Return True if this converter should attempt conversion."""

    def convert(
        self,
        file_stream: BinaryIO,
        source_info: DocumentSourceInfo,
        **kwargs: Any,
    ) -> DocumentIngestResult:
        """Convert the source into normalized Markdown."""


def normalize_markdown(markdown: str) -> str:
    """Normalize whitespace in generated Markdown without changing content meaning."""

    text = "\n".join(line.rstrip() for line in re.split(r"\r?\n", markdown or ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class DocumentIngestor:
    """Priority-ordered converter dispatcher."""

    def __init__(self, converters: Iterable[DocumentConverter] | None = None) -> None:
        self._converters: list[tuple[float, int, DocumentConverter]] = []
        self._sequence = 0
        if converters is not None:
            for converter in converters:
                self.register_converter(converter)

    @classmethod
    def default(cls) -> "DocumentIngestor":
        from .hwpx_converter import HwpxMarkdownConverter

        ingestor = cls()
        ingestor.register_converter(HwpxMarkdownConverter(), priority=0.0)
        return ingestor

    def register_converter(self, converter: DocumentConverter, *, priority: float = 0.0) -> None:
        self._converters.append((priority, self._sequence, converter))
        self._sequence += 1

    def convert(
        self,
        source: str | Path | bytes | BinaryIO,
        *,
        source_info: DocumentSourceInfo | None = None,
        **kwargs: Any,
    ) -> DocumentIngestResult:
        stream, inferred = _source_to_stream(source)
        info = inferred if source_info is None else inferred.copy_and_update(source_info)
        attempts: list[ConversionAttempt] = []
        start_pos = stream.tell()

        for _priority, _seq, converter in sorted(self._converters, key=lambda item: (item[0], item[1])):
            name = getattr(converter, "name", type(converter).__name__)
            stream.seek(start_pos)
            try:
                accepted = bool(converter.accepts(stream, info))
            except Exception as exc:
                attempts.append(
                    ConversionAttempt(
                        converter=name,
                        accepted=False,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
                continue
            finally:
                stream.seek(start_pos)

            attempts.append(ConversionAttempt(converter=name, accepted=accepted))
            if not accepted:
                continue

            try:
                result = converter.convert(stream, info, **kwargs)
            except Exception as exc:
                attempts[-1] = ConversionAttempt(
                    converter=name,
                    accepted=True,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                stream.seek(start_pos)
                continue
            result.markdown = normalize_markdown(result.markdown)
            result.attempts = attempts
            return result

        raise UnsupportedDocumentFormat("no registered converter accepted the document", attempts=attempts)


def _source_to_stream(source: str | Path | bytes | BinaryIO) -> tuple[BinaryIO, DocumentSourceInfo]:
    if isinstance(source, bytes):
        return BytesIO(source), DocumentSourceInfo()
    if isinstance(source, Path):
        return _path_to_stream(source)
    if isinstance(source, str):
        if source.startswith(("http:", "https:", "file:", "data:")):
            raise UnsupportedDocumentFormat("URI sources are not implemented in python-hwpx ingest")
        return _path_to_stream(Path(source))
    if hasattr(source, "read") and callable(source.read) and not isinstance(source, TextIOBase):
        stream = source
        if not stream.seekable():
            stream = BytesIO(stream.read())
        return stream, DocumentSourceInfo()
    raise TypeError(f"unsupported document source type: {type(source).__name__}")


def _path_to_stream(path: Path) -> tuple[BinaryIO, DocumentSourceInfo]:
    resolved = path.expanduser().resolve()
    mimetype, charset = mimetypes.guess_type(str(resolved), strict=False)
    info = DocumentSourceInfo(
        mimetype=mimetype,
        charset=charset,
        extension=resolved.suffix.lower() or None,
        filename=resolved.name,
        local_path=str(resolved),
    )
    return BytesIO(resolved.read_bytes()), info
