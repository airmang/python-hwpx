# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, Sequence

from hwpx.document import HwpxDocument
from hwpx.tools.id_integrity import check_id_integrity
from hwpx.tools.idempotence import IdempotenceReport, check_idempotent_pair
from hwpx.tools.package_reconcile import reconcile_package_with_document
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools.package_validator import validate_package
from hwpx.tools.validator import validate_document

from .report import BuilderSaveReport, BuilderVerifyReport, ReopenReport


BuilderChild = (
    "Heading | Paragraph | Bullet | NumberedList | Table | Image | Toc | NativeToc | PageBreak"
)
_HWP_UNITS_PER_MM = 7200 / 25.4
_A4_HWP_SIZE = (59528, 84188)

# S-024 SPIKE: builder presets hook at Document.lower(), where a single
# preset context can be passed into Heading/Run/Bullet lowering without
# changing default node contracts or the plan-v1 authoring style-token path.


def _outline_style_refs(document: HwpxDocument, level: int) -> dict[str, str | int]:
    """Return paragraph style refs for the built-in HWP outline level, if present."""

    safe_level = min(10, max(1, int(level)))
    for style in document.styles.values():
        name = str(style.name or "")
        eng_name = str(style.eng_name or "")
        if name == f"개요 {safe_level}" or eng_name == f"Outline {safe_level}":
            refs: dict[str, str | int] = {}
            style_id = style.raw_id if style.raw_id is not None else style.id
            if style_id is None:
                continue
            refs["style_id_ref"] = style_id
            if style.para_pr_id_ref is not None:
                refs["para_pr_id_ref"] = int(style.para_pr_id_ref)
            return refs
    return {}


@dataclass(frozen=True)
class _BuilderPreset:
    name: str = "default"

    @property
    def is_government_report(self) -> bool:
        return self.name == "government_report"

    def heading_style(self, level: int) -> dict[str, object]:
        if self.is_government_report:
            size_by_level = {1: 16, 2: 14, 3: 12}
            color_by_level = {1: "1F4E79", 2: "2F5597", 3: "404040"}
            return {
                "bold": True,
                "underline": level == 1,
                "size": size_by_level[level],
                "font": "함초롬바탕",
                "color": color_by_level[level],
            }
        size_by_level = {1: 18, 2: 15, 3: 13}
        return {
            "bold": True,
            "size": size_by_level[level],
            "font": "함초롬바탕",
        }

    def paragraph_style(self, style: str | None) -> dict[str, object] | None:
        if not self.is_government_report:
            return None
        normalized = (style or "").strip().lower()
        if normalized == "callout":
            return {
                "bold": True,
                "color": "1F4E79",
                "font": "함초롬바탕",
                "highlight": "EAF1FB",
            }
        if normalized in {"emphasis", "gov_emphasis"}:
            return {"bold": True, "color": "1F4E79", "font": "함초롬바탕"}
        return None

    def run_style(self, run: "Run") -> dict[str, object]:
        color = run.color
        font = run.font
        if self.is_government_report:
            if run.bold and color is None:
                color = "1F4E79"
        if (run.bold or run.underline or run.highlight) and font is None:
            font = "함초롬바탕"
        return {
            "bold": run.bold,
            "italic": run.italic,
            "underline": run.underline,
            "color": color,
            "font": font,
            "size": run.size,
            "highlight": run.highlight,
            "strike": True if run.strike else None,
        }

    def bullet_char(self, *, level: int, style: str | None = None) -> str:
        if self.is_government_report:
            style_chars = {
                "default": "•",
                "square": "□",
                "circle": "○",
                "dash": "-",
                "note": "※",
                "star": "*",
            }
            normalized = (style or "default").strip().lower().replace("-", "_")
            if normalized not in style_chars:
                raise ValueError(f"unknown government_report bullet style: {style!r}")
            return style_chars[normalized]
        default_chars = ("-", "○", "□", "•")
        return default_chars[level % len(default_chars)]


def _builder_preset(value: str | None) -> _BuilderPreset:
    normalized = (value or "default").strip().lower().replace("-", "_")
    if normalized in {"", "default", "standard", "standard_korean_business"}:
        return _BuilderPreset()
    if normalized in {"government_report", "gov_report", "공문보고서"}:
        return _BuilderPreset(name="government_report")
    raise ValueError(f"unknown builder preset: {value!r}")


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

    def lower(self, document: HwpxDocument, *, preset: _BuilderPreset | None = None) -> None:
        style_preset = preset or _BuilderPreset()
        if self.children:
            paragraph = document.add_paragraph("", include_run=False, inherit_style=False)
            for run in self.children:
                if isinstance(run, PageNumber):
                    raise ValueError("PageNumber is only supported in Header/Footer content")
                paragraph.add_run(_computed_text(run.text), **style_preset.run_style(run))
            return
        style_kwargs = style_preset.paragraph_style(self.style)
        if style_kwargs is None:
            document.add_paragraph(_computed_text(self.text), inherit_style=False)
            return
        char_pr_id = document.ensure_run_style(**style_kwargs)
        document.add_paragraph(
            _computed_text(self.text),
            char_pr_id_ref=char_pr_id,
            inherit_style=False,
        )


@dataclass(frozen=True)
class PageBreak:
    def lower(self, document: HwpxDocument) -> None:
        document.add_paragraph("", pageBreak="1", inherit_style=False)


@dataclass(frozen=True)
class Toc:
    title: str = "목차"
    entries: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
        style_preset = preset or _BuilderPreset()
        title_style = (
            document.ensure_run_style(**style_preset.heading_style(2))
            if style_preset.is_government_report
            else document.ensure_run_style(bold=True, size=14)
        )
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
class NativeToc:
    """Hancom-native TABLEOFCONTENTS field block (M7 / S-062 contract).

    Unlike :class:`Toc` (a static ``text\\tpage`` plaintext list), this lowers
    to the measured native field region via
    :func:`hwpx.tools.toc_author.add_native_toc` AFTER the whole document is
    composed: the region is inserted at the paragraph position where this
    block appeared, entries are generated from the document's outline
    (개요-styled) headings, and ``dirty=True`` (default, measured semantics)
    makes Hancom regenerate entries/styles/page numbers on its next open.

    Composition also enforces the measured ContentsStyles trap first: body
    text on the collected style 0 (바탕글) is routed onto 본문/Body via
    :func:`hwpx.tools.toc_author.ensure_body_styles_not_collected`, or the
    lowering fails loudly rather than emit a TOC that swallows body text.
    """

    title: str = "<제목 차례>"
    level: int = 2
    leader: int = 3
    hyperlink: bool = True
    dirty: bool = True


def _apply_native_tocs(
    document: HwpxDocument,
    pending: Sequence[tuple[int, NativeToc]],
) -> None:
    """Insert deferred native TOC regions into the fully composed document."""

    if not pending:
        return
    if len(pending) > 1:
        raise ValueError(
            "only one native TOC per document is supported "
            "(the M7 contract measured a single TABLEOFCONTENTS field)"
        )
    from hwpx.tools.toc_author import add_native_toc, ensure_body_styles_not_collected

    at_index, node = pending[0]
    # Measured trap first: body text must leave the collected style 0 BEFORE
    # the region is inserted, so the region's own style-0 paragraphs (gold
    # contract) are not rerouted.
    ensure_body_styles_not_collected(document)
    add_native_toc(
        document,
        at_index=at_index,
        title=_computed_text(node.title),
        level=node.level,
        leader=node.leader,
        hyperlink=node.hyperlink,
        dirty=node.dirty,
    )


@dataclass(frozen=True)
class Heading:
    level: int
    text: str

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
        if self.level < 1 or self.level > 3:
            raise ValueError("heading level must be between 1 and 3")
        style_preset = preset or _BuilderPreset()
        char_pr_id = document.ensure_run_style(**style_preset.heading_style(self.level))
        document.add_paragraph(
            _computed_text(self.text),
            section_index=section_index,
            char_pr_id_ref=char_pr_id,
            inherit_style=False,
            **_outline_style_refs(document, self.level),
        )


@dataclass(frozen=True)
class Bullet:
    items: Sequence[str]
    level: int = 0
    style: str | None = None

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
        style_preset = preset or _BuilderPreset()
        level_count = max(self.level + 1, 1)
        levels = [
            {
                "char": style_preset.bullet_char(
                    level=index,
                    style=self.style if index == self.level else None,
                )
            }
            for index in range(level_count)
        ]
        refs = document.ensure_numbering(
            kind="bullet",
            levels=levels,
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

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
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


def approval_box(
    *,
    labels: Sequence[str] | None = None,
    approver_rows: int = 2,
    delegated: str | None = None,
    header_shading: str = "EAF1FB",
) -> Table:
    """Return a merged approval/sign-off table for official documents."""

    normalized_labels = tuple(str(label).strip() for label in (labels or ("기안", "검토", "결재", "전결")) if str(label).strip())
    if not normalized_labels:
        normalized_labels = ("기안", "검토", "결재", "전결")
    delegated_label = str(delegated or "").strip()
    if delegated_label and delegated_label not in normalized_labels:
        normalized_labels = (*normalized_labels, delegated_label)
    row_count = max(int(approver_rows), 1)
    rows = tuple(tuple("" for _ in normalized_labels) for _ in range(row_count))
    if row_count < 2:
        merges: tuple[str, ...] = ()
    else:
        merges = tuple(
            f"{_spreadsheet_column_name(index)}2:{_spreadsheet_column_name(index)}{row_count + 1}"
            for index in range(len(normalized_labels))
        )
    return Table(
        header=normalized_labels,
        rows=rows,
        merges=merges,
        header_shading=header_shading,
        column_widths=tuple(1 for _ in normalized_labels),
    )


def _spreadsheet_column_name(index: int) -> str:
    if index < 0:
        raise ValueError("column index must be non-negative")
    value = index + 1
    letters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


@dataclass(frozen=True)
class Image:
    path: str | PathLike[str] | bytes
    width_mm: float | None = None
    align: str | None = None
    caption: str | None = None
    image_format: str | None = None

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
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

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
        document.set_header_content(
            _header_footer_content_specs(self.children, preset=preset),
            section_index=section_index,
        )


@dataclass(frozen=True)
class Footer:
    children: Sequence[Paragraph | PageNumber] = field(default_factory=tuple)

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
    ) -> None:
        document.set_footer_content(
            _header_footer_content_specs(self.children, preset=preset),
            section_index=section_index,
        )


def _run_content_spec(run: Run, *, preset: _BuilderPreset | None = None) -> dict[str, object]:
    style_preset = preset or _BuilderPreset()
    style = style_preset.run_style(run)
    return {
        "type": "run",
        "text": _computed_text(run.text),
        "bold": style["bold"],
        "italic": style["italic"],
        "underline": style["underline"],
        "color": style["color"],
        "font": style["font"],
        "size": style["size"],
        "highlight": style["highlight"],
        "strike": run.strike,
    }


def _page_number_content_spec(page_number: PageNumber) -> dict[str, object]:
    return {"type": "page_number", "format": page_number.format}


def _paragraph_content_spec(
    paragraph: Paragraph,
    *,
    preset: _BuilderPreset | None = None,
) -> dict[str, object]:
    if paragraph.children:
        children: list[dict[str, object]] = []
        for child in paragraph.children:
            if isinstance(child, Run):
                children.append(_run_content_spec(child, preset=preset))
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
    *,
    preset: _BuilderPreset | None = None,
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for child in children:
        if isinstance(child, Paragraph):
            specs.append(_paragraph_content_spec(child, preset=preset))
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
        elif isinstance(child, (Toc, NativeToc)):
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


def _hard_gates(
    package_report: object,
    document_report: object,
    reopen_report: ReopenReport,
    editor_open_safety_report: object | None = None,
) -> dict[str, str]:
    document_warnings = getattr(document_report, "warnings", ())
    editor_open_safety_ok = (
        True
        if editor_open_safety_report is None
        else bool(getattr(editor_open_safety_report, "ok", False))
    )
    return {
        "package_validation": "pass" if getattr(package_report, "ok", False) else "fail",
        "document_errors": "pass" if getattr(document_report, "ok", False) else "fail",
        "schema_lint": "warning" if document_warnings else "pass",
        "reopen": "pass" if reopen_report.ok else "fail",
        "editor_open_safety": "pass" if editor_open_safety_ok else "fail",
        "id_integrity": "unavailable",
    }


@dataclass(frozen=True)
class Section:
    children: Sequence[
        Heading | Paragraph | Bullet | NumberedList | Table | Image | Toc | NativeToc | PageBreak
    ] = field(default_factory=tuple)
    page: PageSize | None = None
    margins: Margins | None = None
    header: Header | None = None
    footer: Footer | None = None

    def lower(
        self,
        document: HwpxDocument,
        *,
        section_index: int = 0,
        preset: _BuilderPreset | None = None,
        native_toc_sink: list[tuple[int, NativeToc]] | None = None,
    ) -> None:
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
            self.header.lower(document, section_index=section_index, preset=preset)
        if self.footer is not None:
            self.footer.lower(document, section_index=section_index, preset=preset)
        pending_native_tocs = native_toc_sink if native_toc_sink is not None else []
        for child in self.children:
            if isinstance(child, (Paragraph, PageBreak)):
                if isinstance(child, Paragraph):
                    child.lower(document, preset=preset)
                else:
                    child.lower(document)
                continue
            if isinstance(child, Heading):
                child.lower(document, section_index=section_index, preset=preset)
                continue
            if isinstance(child, (Bullet, NumberedList)):
                if isinstance(child, Bullet):
                    child.lower(document, section_index=section_index, preset=preset)
                else:
                    child.lower(document, section_index=section_index)
                continue
            if isinstance(child, Table):
                child.lower(document, section_index=section_index, preset=preset)
                continue
            if isinstance(child, Image):
                child.lower(document, section_index=section_index, preset=preset)
                continue
            if isinstance(child, Toc):
                child.lower(document, section_index=section_index, preset=preset)
                continue
            if isinstance(child, NativeToc):
                if section_index != 0:
                    raise ValueError(
                        "native TOC is only supported in the first section "
                        "(the measured M7 contract inserts into section 0)"
                    )
                # Record the paragraph position where the block appeared; the
                # field region is inserted after the whole document is lowered
                # so the entry source (outline headings) is complete.
                pending_native_tocs.append(
                    (len(document.oxml.sections[0].paragraphs), child)
                )
                continue
            raise NotImplementedError(f"{type(child).__name__} lowering is not implemented yet")
        if native_toc_sink is None:
            # standalone Section.lower call: resolve deferred TOCs now
            _apply_native_tocs(document, pending_native_tocs)


@dataclass(frozen=True)
class Document:
    sections: Sequence[Section] = field(default_factory=lambda: (Section(),))
    metadata: Metadata | None = None
    visual_review_required: bool | None = None
    preset: str | None = None

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
        preset = _builder_preset(self.preset)
        if self.metadata is not None:
            for label, value in (
                ("제목", self.metadata.title),
                ("작성자", self.metadata.author),
                ("기관", self.metadata.organization),
            ):
                if value:
                    document.add_paragraph(f"{label}: {value}", inherit_style=False)
        pending_native_tocs: list[tuple[int, NativeToc]] = []
        for index, section in enumerate(self.sections):
            section.lower(
                document,
                section_index=index,
                preset=preset,
                native_toc_sink=pending_native_tocs,
            )
        _apply_native_tocs(document, pending_native_tocs)
        return document

    def save_to_path(self, path: str | PathLike[str]) -> BuilderSaveReport:
        document = self.lower()
        # Funnel the write through the single SavePipeline and keep its uniform
        # report (plan §2 Phase B). Transparent policy -> behaviour-identical to
        # the prior ``document.save_to_path`` for a from-scratch (new) document.
        visual_complete = document.save_report(path)
        package_report = validate_package(path)
        document_report = validate_document(path)
        editor_open_safety_report = validate_editor_open_safety(path)
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
            hard_gates=_hard_gates(
                package_report,
                document_report,
                reopen_report,
                editor_open_safety_report,
            ),
            visual_review_required=visual_review_required,
            feature_flags=feature_flags,
            editor_open_safety=editor_open_safety_report,
            visual_complete=visual_complete,
        )
        return report

    def verify(self) -> BuilderVerifyReport:
        """Dry, no-disk pre-write verification of the built document.

        Lowers the document to bytes in memory and runs the save hard gates
        (package, document, editor-open-safety, reopen) *plus* id-integrity and
        a two-round idempotence check — a strictly stronger gate set than
        :meth:`save_to_path` (whose report leaves id-integrity to the reader and
        does not check idempotence) — without writing any file. Returns a
        compact signal so a caller can branch on ``ok`` and read a
        section/paragraph count before paying to materialize a real save.

        Serialization itself can fail (e.g. open-safety rejects the output); in
        that case this returns ``ok=False`` with ``serialize_error`` set rather
        than raising, so a caller (fuzz loop, agent) can always branch on the
        result.

        See :data:`hwpx.builder.report.FIDELITY_CONTRACT` for what a green
        verdict proves vs. does not prove.
        """

        try:
            lowered = self.lower()
            data = lowered.to_bytes()
        except Exception as exc:  # the document cannot even be serialized
            return BuilderVerifyReport(
                ok=False,
                reopen_ok=False,
                package_ok=False,
                document_ok=False,
                editor_open_safety_ok=False,
                id_integrity_ok=False,
                idempotent=False,
                sections_reconciled=False,
                serialize_error=f"{type(exc).__name__}: {exc}",
            )

        package_report = validate_package(data)
        document_report = validate_document(data)
        editor_open_safety_report = validate_editor_open_safety(data)

        reopened: HwpxDocument | None = None
        reopen_error: str | None = None
        try:
            reopened = HwpxDocument.open(data)
        except Exception as exc:  # surfaced in the report rather than raised
            reopen_error = f"{type(exc).__name__}: {exc}"

        id_integrity = (
            check_id_integrity(reopened) if reopened is not None else None
        )

        # Fixed-point check on the EXACT bytes the gates above validated (gen-1)
        # vs. their reopen-and-resave (gen-2), so the idempotence verdict refers
        # to the bytes we would actually write, not a later generation.
        idempotence: IdempotenceReport | None = None
        serialize_error: str | None = None
        try:
            idempotence = check_idempotent_pair(data, HwpxDocument.open(data).to_bytes())
        except Exception as exc:
            serialize_error = f"{type(exc).__name__}: {exc}"

        # Output-vs-intent: produced section parts must match the source model.
        reconcile = reconcile_package_with_document(data, lowered)

        package_ok = bool(getattr(package_report, "ok", False))
        document_ok = bool(getattr(document_report, "ok", False))
        editor_open_safety_ok = bool(getattr(editor_open_safety_report, "ok", False))
        id_integrity_ok = bool(getattr(id_integrity, "ok", False))
        idempotent = bool(idempotence is not None and idempotence.ok)
        reopen_ok = reopened is not None
        section_count = len(reopened.sections) if reopened is not None else 0
        paragraph_count = len(reopened.paragraphs) if reopened is not None else 0

        ok = (
            package_ok
            and document_ok
            and editor_open_safety_ok
            and id_integrity_ok
            and reopen_ok
            and idempotent
            and reconcile.ok
        )

        return BuilderVerifyReport(
            ok=ok,
            reopen_ok=reopen_ok,
            package_ok=package_ok,
            document_ok=document_ok,
            editor_open_safety_ok=editor_open_safety_ok,
            id_integrity_ok=id_integrity_ok,
            idempotent=idempotent,
            sections_reconciled=reconcile.ok,
            section_count=section_count,
            paragraph_count=paragraph_count,
            byte_length=len(data),
            reopen_error=reopen_error,
            serialize_error=serialize_error,
            idempotence=idempotence,
            reconcile=reconcile,
        )
