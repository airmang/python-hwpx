# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from typing import Sequence

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_package
from hwpx.tools.validator import validate_document

from .report import BuilderSaveReport, ReopenReport


BuilderChild = (
    "Heading | Paragraph | Bullet | NumberedList | Table | Image | PageBreak"
)


@dataclass(frozen=True)
class PageSize:
    width_mm: float
    height_mm: float
    orientation: str = "PORTRAIT"


PageSize.A4 = PageSize(width_mm=210, height_mm=297)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Margins:
    top_mm: float = 20
    right_mm: float = 20
    bottom_mm: float = 20
    left_mm: float = 20
    header_mm: float = 10
    footer_mm: float = 10
    gutter_mm: float = 0


@dataclass(frozen=True)
class Metadata:
    title: str = ""
    author: str = ""
    organization: str = ""


@dataclass(frozen=True)
class Run:
    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass(frozen=True)
class Paragraph:
    text: str = ""
    children: Sequence[Run] = field(default_factory=tuple)
    align: str | None = None

    def lower(self, document: HwpxDocument) -> None:
        if self.children:
            paragraph = document.add_paragraph("", include_run=False, inherit_style=False)
            for run in self.children:
                paragraph.add_run(
                    run.text,
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                )
            return
        document.add_paragraph(self.text, inherit_style=False)


@dataclass(frozen=True)
class PageBreak:
    def lower(self, document: HwpxDocument) -> None:
        document.add_paragraph("", pageBreak="1", inherit_style=False)


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Bullet:
    items: Sequence[str]
    level: int = 0


@dataclass(frozen=True)
class NumberedList:
    items: Sequence[str]
    level: int = 0


@dataclass(frozen=True)
class Table:
    header: Sequence[str] = field(default_factory=tuple)
    rows: Sequence[Sequence[str]] = field(default_factory=tuple)


@dataclass(frozen=True)
class Image:
    path: str | PathLike[str]
    width_mm: float | None = None
    align: str | None = None
    caption: str | None = None


@dataclass(frozen=True)
class PageNumber:
    format: str = "page"


@dataclass(frozen=True)
class Header:
    children: Sequence[Paragraph | PageNumber] = field(default_factory=tuple)


@dataclass(frozen=True)
class Footer:
    children: Sequence[Paragraph | PageNumber] = field(default_factory=tuple)


@dataclass(frozen=True)
class Section:
    children: Sequence[Heading | Paragraph | Bullet | NumberedList | Table | Image | PageBreak] = field(
        default_factory=tuple
    )
    page: PageSize | None = None
    margins: Margins | None = None
    header: Header | None = None
    footer: Footer | None = None

    def lower(self, document: HwpxDocument) -> None:
        for child in self.children:
            if isinstance(child, (Paragraph, PageBreak)):
                child.lower(document)
                continue
            raise NotImplementedError(f"{type(child).__name__} lowering is not implemented yet")


@dataclass(frozen=True)
class Document:
    sections: Sequence[Section] = field(default_factory=lambda: (Section(),))
    metadata: Metadata | None = None

    def lower(self) -> HwpxDocument:
        document = HwpxDocument.new()
        for section in self.sections:
            section.lower(document)
        return document

    def save_to_path(self, path: str | PathLike[str]) -> BuilderSaveReport:
        document = self.lower()
        document.save_to_path(path)
        package_report = validate_package(path)
        document_report = validate_document(path)
        try:
            reopened_document = HwpxDocument.open(path)
            reopen_report = ReopenReport(ok=True, document=reopened_document)
        except Exception as exc:  # pragma: no cover - failure is surfaced in report
            reopen_report = ReopenReport(ok=False, error=f"{type(exc).__name__}: {exc}")
        return BuilderSaveReport(
            path=path,
            validate_package=package_report,
            validate_document=document_report,
            reopened=reopen_report,
        )
