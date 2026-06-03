# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_package
from hwpx.tools.validator import validate_document

from .report import BuilderSaveReport, ReopenReport


BuilderChild = (
    "Heading | Paragraph | Bullet | NumberedList | Table | Image | Toc | PageBreak"
)
_HWP_UNITS_PER_MM = 7200 / 25.4
_A4_HWP_SIZE = (59528, 84188)

# S-024 SPIKE: builder presets hook at Document.lower(), where a single
# preset context can be passed into Heading/Run/Bullet lowering without
# changing default node contracts or the plan-v1 authoring style-token path.


def _mm_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_MM)


def _computed_text(text: str) -> str:
    from hwpx.authoring import replace_computed_fields

    return replace_computed_fields(text)


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

    def as_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "author": self.author,
            "organization": self.organization,
        }


@dataclass(frozen=True)
class Run:
    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    font: str | None = None
    size: int | float | None = None
    highlight: str | None = None
    strike: bool = False


@dataclass(frozen=True)
class Paragraph:
    text: str = ""
    children: Sequence[Run | PageNumber] = field(default_factory=tuple)
    align: str | None = None
    style: str | None = None

    def lower(self, document: HwpxDocument) -> None:
        if self.children:
            paragraph = document.add_paragraph("", include_run=False, inherit_style=False)
            for run in self.children:
                if isinstance(run, PageNumber):
                    raise ValueError("PageNumber is only supported in Header/Footer content")
                paragraph.add_run(
                    _computed_text(run.text),
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    color=run.color,
                    font=run.font,
                    size=run.size,
                    highlight=run.highlight,
                    strike=True if run.strike else None,
                )
            return
        document.add_paragraph(_computed_text(self.text), inherit_style=False)


@dataclass(frozen=True)
class PageBreak:
    def lower(self, document: HwpxDocument) -> None:
        document.add_paragraph("", pageBreak="1", inherit_style=False)


@dataclass(frozen=True)
class Toc:
    title: str = "목차"
    entries: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        title_style = document.ensure_run_style(bold=True, size=14)
        entry_style = document.ensure_run_style()
        document.add_paragraph(
            _computed_text(self.title),
            section_index=section_index,
            char_pr_id_ref=title_style,
            inherit_style=False,
        )
        for entry in self.entries:
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            page = str(entry.get("page") or "").strip()
            line = f"{text}\t{page}" if page else text
            document.add_paragraph(
                _computed_text(line),
                section_index=section_index,
                char_pr_id_ref=entry_style,
                inherit_style=False,
            )


@dataclass(frozen=True)
class Heading:
    level: int
    text: str

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        if self.level < 1 or self.level > 3:
            raise ValueError("heading level must be between 1 and 3")
        size_by_level = {1: 18, 2: 15, 3: 13}
        char_pr_id = document.ensure_run_style(
            bold=True,
            size=size_by_level[self.level],
            font="함초롬바탕",
        )
        document.add_paragraph(
            _computed_text(self.text),
            section_index=section_index,
            char_pr_id_ref=char_pr_id,
            inherit_style=False,
        )


@dataclass(frozen=True)
class Bullet:
    items: Sequence[str]
    level: int = 0

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        level_count = max(self.level + 1, 1)
        refs = document.ensure_numbering(
            kind="bullet",
            levels=[{"char": char} for char in ("-", "○", "□", "•")[:level_count]],
        )
        para_pr_id = refs[self.level]
        for item in self.items:
            document.add_paragraph(
                _computed_text(item),
                section_index=section_index,
                para_pr_id_ref=para_pr_id,
                inherit_style=False,
            )


@dataclass(frozen=True)
class NumberedList:
    items: Sequence[str]
    level: int = 0

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        level_count = max(self.level + 1, 1)
        refs = document.ensure_numbering(kind="number", levels=[{} for _ in range(level_count)])
        para_pr_id = refs[self.level]
        for item in self.items:
            document.add_paragraph(
                _computed_text(item),
                section_index=section_index,
                para_pr_id_ref=para_pr_id,
                inherit_style=False,
            )


@dataclass(frozen=True)
class Table:
    header: Sequence[str] = field(default_factory=tuple)
    rows: Sequence[Sequence[str]] = field(default_factory=tuple)
    merges: Sequence[str] = field(default_factory=tuple)
    header_shading: str | None = None
    column_widths: Sequence[int | float] = field(default_factory=tuple)

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        table_rows: list[Sequence[str]] = []
        if self.header:
            table_rows.append(self.header)
        table_rows.extend(self.rows)
        if not table_rows:
            raise ValueError("table must contain a header or at least one row")
        column_count = max(len(row) for row in table_rows)
        table = document.add_table(
            len(table_rows),
            column_count,
            section_index=section_index,
        )
        for row_index, row in enumerate(table_rows):
            for col_index, value in enumerate(row):
                table.cell(row_index, col_index).text = _computed_text(str(value))
        for merge in self.merges:
            table.merge_cells(merge)
        if self.header and self.header_shading:
            for col_index in range(column_count):
                table.set_cell_shading(0, col_index, self.header_shading)
        if self.column_widths:
            table.set_column_widths(self.column_widths)


@dataclass(frozen=True)
class Image:
    path: str | PathLike[str] | bytes
    width_mm: float | None = None
    align: str | None = None
    caption: str | None = None
    image_format: str | None = None

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        if isinstance(self.path, bytes):
            image_data = self.path
            image_format = self.image_format or "png"
        else:
            image_path = Path(self.path)
            image_data = image_path.read_bytes()
            image_format = self.image_format or image_path.suffix.lstrip(".") or "png"
        document.add_picture(
            image_data,
            image_format,
            width_mm=self.width_mm,
            align=self.align,
            section_index=section_index,
        )
        if self.caption:
            document.add_paragraph(_computed_text(self.caption), section_index=section_index, inherit_style=False)


@dataclass(frozen=True)
class PageNumber:
    format: str = "page"


@dataclass(frozen=True)
class Header:
    children: Sequence[Paragraph | PageNumber] = field(default_factory=tuple)

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        document.set_header_content(
            _header_footer_content_specs(self.children),
            section_index=section_index,
        )


@dataclass(frozen=True)
class Footer:
    children: Sequence[Paragraph | PageNumber] = field(default_factory=tuple)

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        document.set_footer_content(
            _header_footer_content_specs(self.children),
            section_index=section_index,
        )


def _run_content_spec(run: Run) -> dict[str, object]:
    return {
        "type": "run",
        "text": _computed_text(run.text),
        "bold": run.bold,
        "italic": run.italic,
        "underline": run.underline,
        "color": run.color,
        "font": run.font,
        "size": run.size,
        "highlight": run.highlight,
        "strike": run.strike,
    }


def _page_number_content_spec(page_number: PageNumber) -> dict[str, object]:
    return {"type": "page_number", "format": page_number.format}


def _paragraph_content_spec(paragraph: Paragraph) -> dict[str, object]:
    if paragraph.children:
        children: list[dict[str, object]] = []
        for child in paragraph.children:
            if isinstance(child, Run):
                children.append(_run_content_spec(child))
                continue
            if isinstance(child, PageNumber):
                children.append(_page_number_content_spec(child))
                continue
            raise ValueError(f"unsupported header/footer paragraph child: {type(child).__name__}")
    else:
        children = [{"type": "run", "text": _computed_text(paragraph.text)}]
    spec: dict[str, object] = {"children": children}
    if paragraph.align:
        spec["align"] = paragraph.align
    return spec


def _header_footer_content_specs(
    children: Sequence[Paragraph | PageNumber],
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for child in children:
        if isinstance(child, Paragraph):
            specs.append(_paragraph_content_spec(child))
            continue
        if isinstance(child, PageNumber):
            specs.append({"children": [_page_number_content_spec(child)]})
            continue
        raise ValueError(f"unsupported header/footer child: {type(child).__name__}")
    return specs


def _children_contain_page_number(children: Sequence[Paragraph | PageNumber]) -> bool:
    for child in children:
        if isinstance(child, PageNumber):
            return True
        if isinstance(child, Paragraph) and any(isinstance(grandchild, PageNumber) for grandchild in child.children):
            return True
    return False


def _run_is_rich(run: Run) -> bool:
    return any(
        (
            run.bold,
            run.italic,
            run.underline,
            run.color,
            run.font,
            run.size,
            run.highlight,
            run.strike,
        )
    )


def _children_contain_rich_run(children: Sequence[Paragraph | PageNumber]) -> bool:
    for child in children:
        if not isinstance(child, Paragraph):
            continue
        if any(isinstance(grandchild, Run) and _run_is_rich(grandchild) for grandchild in child.children):
            return True
    return False


def _section_feature_flags(section: "Section") -> dict[str, bool]:
    flags = {
        "metadata": False,
        "page_setup": section.page is not None or section.margins is not None,
        "header_footer": section.header is not None or section.footer is not None,
        "page_number": False,
        "heading": False,
        "rich_run": False,
        "list": False,
        "table": False,
        "image": False,
        "toc": False,
        "page_break": False,
    }
    if section.header is not None and _children_contain_page_number(section.header.children):
        flags["page_number"] = True
    if section.footer is not None and _children_contain_page_number(section.footer.children):
        flags["page_number"] = True
    if section.header is not None and _children_contain_rich_run(section.header.children):
        flags["rich_run"] = True
    if section.footer is not None and _children_contain_rich_run(section.footer.children):
        flags["rich_run"] = True
    for child in section.children:
        if isinstance(child, Heading):
            flags["heading"] = True
        elif isinstance(child, Paragraph):
            if any(isinstance(run, Run) and _run_is_rich(run) for run in child.children):
                flags["rich_run"] = True
        elif isinstance(child, (Bullet, NumberedList)):
            flags["list"] = True
        elif isinstance(child, Table):
            flags["table"] = True
        elif isinstance(child, Image):
            flags["image"] = True
        elif isinstance(child, Toc):
            flags["toc"] = True
        elif isinstance(child, PageBreak):
            flags["page_break"] = True
    return flags


def _merge_flags(*flag_sets: dict[str, bool]) -> dict[str, bool]:
    merged: dict[str, bool] = {}
    for flags in flag_sets:
        for key, value in flags.items():
            merged[key] = merged.get(key, False) or value
    return merged


def _hard_gates(package_report: object, document_report: object, reopen_report: ReopenReport) -> dict[str, str]:
    document_warnings = getattr(document_report, "warnings", ())
    return {
        "package_validation": "pass" if getattr(package_report, "ok", False) else "fail",
        "document_errors": "pass" if getattr(document_report, "ok", False) else "fail",
        "schema_lint": "warning" if document_warnings else "pass",
        "reopen": "pass" if reopen_report.ok else "fail",
        "id_integrity": "unavailable",
    }


@dataclass(frozen=True)
class Section:
    children: Sequence[Heading | Paragraph | Bullet | NumberedList | Table | Image | Toc | PageBreak] = field(
        default_factory=tuple
    )
    page: PageSize | None = None
    margins: Margins | None = None
    header: Header | None = None
    footer: Footer | None = None

    def lower(self, document: HwpxDocument, *, section_index: int = 0) -> None:
        if self.page is not None:
            if self.page == PageSize.A4:
                width, height = _A4_HWP_SIZE
            else:
                width = _mm_to_hwp_units(self.page.width_mm)
                height = _mm_to_hwp_units(self.page.height_mm)
            document.set_page_size(
                width=width,
                height=height,
                orientation=self.page.orientation,
                section_index=section_index,
            )
        if self.margins is not None:
            document.set_page_margins(
                left=_mm_to_hwp_units(self.margins.left_mm),
                right=_mm_to_hwp_units(self.margins.right_mm),
                top=_mm_to_hwp_units(self.margins.top_mm),
                bottom=_mm_to_hwp_units(self.margins.bottom_mm),
                header=_mm_to_hwp_units(self.margins.header_mm),
                footer=_mm_to_hwp_units(self.margins.footer_mm),
                gutter=_mm_to_hwp_units(self.margins.gutter_mm),
                section_index=section_index,
            )
        if self.header is not None:
            self.header.lower(document, section_index=section_index)
        if self.footer is not None:
            self.footer.lower(document, section_index=section_index)
        for child in self.children:
            if isinstance(child, (Paragraph, PageBreak)):
                child.lower(document)
                continue
            if isinstance(child, Heading):
                child.lower(document, section_index=section_index)
                continue
            if isinstance(child, (Bullet, NumberedList)):
                child.lower(document, section_index=section_index)
                continue
            if isinstance(child, Table):
                child.lower(document, section_index=section_index)
                continue
            if isinstance(child, Image):
                child.lower(document, section_index=section_index)
                continue
            if isinstance(child, Toc):
                child.lower(document, section_index=section_index)
                continue
            raise NotImplementedError(f"{type(child).__name__} lowering is not implemented yet")


@dataclass(frozen=True)
class Document:
    sections: Sequence[Section] = field(default_factory=lambda: (Section(),))
    metadata: Metadata | None = None
    visual_review_required: bool | None = None

    def feature_flags(self) -> dict[str, bool]:
        flags = _merge_flags(*(_section_feature_flags(section) for section in self.sections))
        flags["metadata"] = self.metadata is not None
        layout_sensitive = any(
            flags.get(key, False)
            for key in ("header_footer", "page_number", "table", "image", "page_break")
        )
        flags["layout_sensitive"] = layout_sensitive
        return flags

    def lower(self) -> HwpxDocument:
        document = HwpxDocument.new()
        if self.metadata is not None:
            for label, value in (
                ("제목", self.metadata.title),
                ("작성자", self.metadata.author),
                ("기관", self.metadata.organization),
            ):
                if value:
                    document.add_paragraph(f"{label}: {value}", inherit_style=False)
        for index, section in enumerate(self.sections):
            section.lower(document, section_index=index)
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
        feature_flags = self.feature_flags()
        visual_review_required = (
            self.visual_review_required
            if self.visual_review_required is not None
            else feature_flags["layout_sensitive"]
        )
        report = BuilderSaveReport(
            path=path,
            validate_package=package_report,
            validate_document=document_report,
            reopened=reopen_report,
            metadata=self.metadata.as_dict() if self.metadata is not None else {},
            hard_gates=_hard_gates(package_report, document_report, reopen_report),
            visual_review_required=visual_review_required,
            feature_flags=feature_flags,
        )
        return report
