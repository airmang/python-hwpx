# SPDX-License-Identifier: Apache-2.0
"""Layout-oriented HTML preview rendering for HWPX packages.

This renderer is intentionally approximate: it exposes page boxes, margins,
paragraph alignment, table geometry, and table borders so agents can cheaply
inspect layout before the final Hancom viewer check.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import io
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
_HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
_HP = f"{{{_HP_NS}}}"
_HH = f"{{{_HH_NS}}}"
_HC = f"{{{_HC_NS}}}"
_HS = f"{{{_HS_NS}}}"

_HWP_UNITS_PER_MM = 7200 / 25.4
_DEFAULT_PAGE_WIDTH_MM = 210.0
_DEFAULT_PAGE_HEIGHT_MM = 297.0
_DEFAULT_MARGINS_MM = {
    "left": 30.0,
    "right": 30.0,
    "top": 20.0,
    "bottom": 15.0,
    "header": 15.0,
    "footer": 15.0,
    "gutter": 0.0,
}


@dataclass(frozen=True)
class PreviewPage:
    """Metadata for one rendered preview page."""

    index: int
    section_index: int
    page_id: str
    width_mm: float
    height_mm: float
    margins_mm: Mapping[str, float]
    paragraph_count: int
    table_count: int

    @property
    def content_width_mm(self) -> float:
        return max(0.0, self.width_mm - self.margins_mm["left"] - self.margins_mm["right"])

    @property
    def content_height_mm(self) -> float:
        return max(0.0, self.height_mm - self.margins_mm["top"] - self.margins_mm["bottom"])

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sectionIndex": self.section_index,
            "pageId": self.page_id,
            "widthMm": round(self.width_mm, 2),
            "heightMm": round(self.height_mm, 2),
            "marginsMm": {key: round(value, 2) for key, value in self.margins_mm.items()},
            "contentWidthMm": round(self.content_width_mm, 2),
            "contentHeightMm": round(self.content_height_mm, 2),
            "paragraphCount": self.paragraph_count,
            "tableCount": self.table_count,
        }


@dataclass(frozen=True)
class LayoutPreview:
    """Rendered layout preview HTML plus machine-readable page metadata."""

    html: str
    pages: tuple[PreviewPage, ...]
    warnings: tuple[str, ...]
    mode: str
    page_fragments: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "html": self.html,
            "mode": self.mode,
            "pages": [page.as_dict() for page in self.pages],
            "pageCount": len(self.pages),
            "warnings": list(self.warnings),
        }

    def page_html_documents(self, *, title: str = "HWPX Layout Preview") -> list[str]:
        """Return standalone HTML documents, one per rendered preview page."""

        return [
            _document_html(
                title=f"{title} - page {index + 1}",
                mode=self.mode,
                body=fragment,
                screenshot=True,
            )
            for index, fragment in enumerate(self.page_fragments)
        ]


def _hwp_to_mm(value: str | int | float | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value) / _HWP_UNITS_PER_MM
    except (TypeError, ValueError):
        return default


def _char_height_to_pt(value: str | int | float | None, default: float = 10.0) -> float:
    if value is None:
        return default
    try:
        return max(1.0, float(value) / 100)
    except (TypeError, ValueError):
        return default


def _fmt_mm(value: float) -> str:
    return f"{value:.2f}mm"


def _fmt_pt(value: float) -> str:
    return f"{value:.2f}pt"


def _css_color(value: str | None, default: str = "#000000") -> str:
    if not value or value.lower() == "none":
        return default
    return value if value.startswith("#") else f"#{value}"


def _safe_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


def _read_package_parts(source: str | Path | bytes) -> tuple[dict[str, bytes], list[str]]:
    warnings: list[str] = []
    try:
        if isinstance(source, bytes):
            archive = io.BytesIO(source)
        else:
            archive = Path(source)
        with ZipFile(archive) as zf:
            return {name: zf.read(name) for name in zf.namelist()}, warnings
    except (BadZipFile, FileNotFoundError, OSError) as exc:
        raise ValueError(f"unable to read HWPX package: {exc}") from exc


def _parse_xml(parts: Mapping[str, bytes], name: str, warnings: list[str]) -> ET.Element | None:
    payload = parts.get(name)
    if payload is None:
        warnings.append(f"missing XML part: {name}")
        return None
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        warnings.append(f"unable to parse XML part {name}: {exc}")
        return None


def _section_names(parts: Mapping[str, bytes]) -> list[str]:
    return sorted(
        name
        for name in parts
        if name.startswith("Contents/section") and name.endswith(".xml")
    )


def _find_text_in_run(run: ET.Element) -> str:
    parts: list[str] = []
    for child in list(run):
        if child.tag == f"{_HP}t" and child.text:
            parts.append(child.text)
        elif child.tag == f"{_HP}tab" or (
            child.tag == f"{_HP}ctrl" and (child.get("id") or "").lower() == "tab"
        ):
            parts.append("\t")
        elif child.tag == f"{_HP}lineBreak":
            parts.append("\n")
    return "".join(parts)


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(_find_text_in_run(run) for run in paragraph.findall(f"{_HP}run"))


def _collect_style_maps(header: ET.Element | None) -> dict[str, dict[str, Any]]:
    para: dict[str, Any] = {}
    chars: dict[str, Any] = {}
    borders: dict[str, Any] = {}
    if header is None:
        return {"para": para, "char": chars, "border": borders}

    for node in header.findall(f".//{_HH}paraPr"):
        para[node.get("id", "")] = _parse_para_style(node)
    for node in header.findall(f".//{_HH}charPr"):
        chars[node.get("id", "")] = {
            "font_size_pt": _char_height_to_pt(node.get("height")),
            "color": _css_color(node.get("textColor")),
        }
    for node in header.findall(f".//{_HH}borderFill"):
        borders[node.get("id", "")] = _parse_border_fill(node)
    return {"para": para, "char": chars, "border": borders}


def _parse_para_style(node: ET.Element) -> dict[str, Any]:
    align = node.find(f"{_HH}align")
    horizontal = (align.get("horizontal") if align is not None else "LEFT") or "LEFT"
    line_spacing = node.find(f".//{_HH}lineSpacing")
    margin = node.find(f".//{_HH}margin")
    margins = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0, "indent": 0.0}
    if margin is not None:
        for child in list(margin):
            key = {
                f"{_HC}left": "left",
                f"{_HC}right": "right",
                f"{_HC}prev": "top",
                f"{_HC}next": "bottom",
                f"{_HC}intent": "indent",
            }.get(child.tag)
            if key:
                margins[key] = _hwp_to_mm(child.get("value"))
    return {
        "align": horizontal.lower().replace("both", "justify"),
        "line_spacing_percent": _safe_int(
            line_spacing.get("value") if line_spacing is not None else None,
            160,
        ),
        "margins_mm": margins,
    }


def _parse_border_fill(node: ET.Element) -> dict[str, Any]:
    sides: dict[str, str] = {}
    for side, tag in {
        "left": "leftBorder",
        "right": "rightBorder",
        "top": "topBorder",
        "bottom": "bottomBorder",
    }.items():
        border = node.find(f"{_HH}{tag}")
        if border is None or (border.get("type") or "NONE").upper() == "NONE":
            sides[side] = "none"
            continue
        width = border.get("width") or "0.1 mm"
        color = _css_color(border.get("color"))
        sides[side] = f"{width} solid {color}"

    fill = "transparent"
    win_brush = node.find(f".//{_HC}winBrush")
    if win_brush is not None:
        face = win_brush.get("faceColor")
        if face and face.lower() != "none":
            fill = _css_color(face, default="transparent")

    return {"sides": sides, "fill": fill}


def _page_spec(section: ET.Element) -> tuple[float, float, dict[str, float]]:
    page_pr = section.find(f".//{_HP}pagePr")
    if page_pr is None:
        return _DEFAULT_PAGE_WIDTH_MM, _DEFAULT_PAGE_HEIGHT_MM, dict(_DEFAULT_MARGINS_MM)
    width = _hwp_to_mm(page_pr.get("width"), _DEFAULT_PAGE_WIDTH_MM)
    height = _hwp_to_mm(page_pr.get("height"), _DEFAULT_PAGE_HEIGHT_MM)
    margin_node = page_pr.find(f"{_HP}margin")
    margins = dict(_DEFAULT_MARGINS_MM)
    if margin_node is not None:
        for key in margins:
            margins[key] = _hwp_to_mm(margin_node.get(key), margins[key])
    return width, height, margins


def _style_attr(items: Mapping[str, str | float | int | None]) -> str:
    pairs = [
        f"{key}: {value}"
        for key, value in items.items()
        if value is not None and str(value) != ""
    ]
    return html.escape("; ".join(pairs), quote=True)


def _render_inline_runs(paragraph: ET.Element, styles: Mapping[str, Any]) -> str:
    spans: list[str] = []
    char_styles = styles["char"]
    for run in paragraph.findall(f"{_HP}run"):
        text = _find_text_in_run(run)
        if not text:
            continue
        char_style = char_styles.get(run.get("charPrIDRef") or "0", {})
        style = _style_attr(
            {
                "font-size": _fmt_pt(char_style.get("font_size_pt", 10.0)),
                "color": char_style.get("color", "#000000"),
            }
        )
        spans.append(f'<span style="{style}">{html.escape(text)}</span>')
    return "".join(spans)


def _paragraph_style(paragraph: ET.Element, styles: Mapping[str, Any]) -> str:
    para_styles = styles["para"]
    style = para_styles.get(paragraph.get("paraPrIDRef") or "0", {})
    margins = style.get("margins_mm", {})
    return _style_attr(
        {
            "text-align": style.get("align", "left"),
            "line-height": f"{style.get('line_spacing_percent', 160)}%",
            "margin-top": _fmt_mm(margins.get("top", 0.0)),
            "margin-right": _fmt_mm(margins.get("right", 0.0)),
            "margin-bottom": _fmt_mm(margins.get("bottom", 1.6)),
            "margin-left": _fmt_mm(margins.get("left", 0.0)),
            "text-indent": _fmt_mm(margins.get("indent", 0.0)),
        }
    )


def _border_style(border_ref: str | None, styles: Mapping[str, Any]) -> dict[str, str]:
    border = styles["border"].get(border_ref or "", {})
    sides = border.get("sides") or {}
    return {
        "border-left": sides.get("left", "1px solid #b9c0c7"),
        "border-right": sides.get("right", "1px solid #b9c0c7"),
        "border-top": sides.get("top", "1px solid #b9c0c7"),
        "border-bottom": sides.get("bottom", "1px solid #b9c0c7"),
        "background": border.get("fill", "transparent"),
    }


def _render_table(table: ET.Element, styles: Mapping[str, Any]) -> str:
    size = table.find(f"{_HP}sz")
    table_width = _hwp_to_mm(size.get("width") if size is not None else None)
    table_style = _style_attr(
        {
            "width": _fmt_mm(table_width) if table_width > 0 else "100%",
            "border-collapse": "collapse",
            "table-layout": "fixed",
            "margin": "1.5mm 0",
        }
    )
    rows: list[str] = []
    for tr in table.findall(f"{_HP}tr"):
        cells: list[str] = []
        for tc in tr.findall(f"{_HP}tc"):
            cell_size = tc.find(f"{_HP}cellSz")
            cell_margin = tc.find(f"{_HP}cellMargin")
            width = _hwp_to_mm(cell_size.get("width") if cell_size is not None else None)
            height = _hwp_to_mm(cell_size.get("height") if cell_size is not None else None)
            padding = {
                key: _hwp_to_mm(cell_margin.get(key), 0.5) if cell_margin is not None else 0.5
                for key in ("top", "right", "bottom", "left")
            }
            css = _border_style(tc.get("borderFillIDRef") or table.get("borderFillIDRef"), styles)
            css.update(
                {
                    "width": _fmt_mm(width) if width > 0 else None,
                    "min-height": _fmt_mm(height) if height > 0 else None,
                    "padding": (
                        f"{_fmt_mm(padding['top'])} {_fmt_mm(padding['right'])} "
                        f"{_fmt_mm(padding['bottom'])} {_fmt_mm(padding['left'])}"
                    ),
                    "vertical-align": "middle",
                }
            )
            body_parts = []
            for para in tc.findall(f".//{_HP}p"):
                body_parts.append(_render_paragraph(para, styles, include_tables=False))
            if not body_parts:
                body_parts.append("&nbsp;")
            span = tc.find(f"{_HP}cellSpan")
            colspan = _safe_int(span.get("colSpan") if span is not None else None, 1)
            rowspan = _safe_int(span.get("rowSpan") if span is not None else None, 1)
            attrs = [
                f'style="{_style_attr(css)}"',
                f'data-border-fill-id="{html.escape(tc.get("borderFillIDRef") or "")}"',
            ]
            if colspan > 1:
                attrs.append(f'colspan="{colspan}"')
            if rowspan > 1:
                attrs.append(f'rowspan="{rowspan}"')
            cells.append(f"<td {' '.join(attrs)}>{''.join(body_parts)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="hwpx-table" style="{table_style}"><tbody>{"".join(rows)}</tbody></table>'


def _render_paragraph(
    paragraph: ET.Element,
    styles: Mapping[str, Any],
    *,
    include_tables: bool = True,
) -> str:
    text_html = _render_inline_runs(paragraph, styles)
    css = _paragraph_style(paragraph, styles)
    classes = ["hwpx-paragraph"]
    if not text_html:
        classes.append("hwpx-empty-paragraph")
        text_html = "&nbsp;"
    result = [f'<p class="{" ".join(classes)}" style="{css}">{text_html}</p>']
    if include_tables:
        for table in paragraph.findall(f".//{_HP}tbl"):
            result.append(_render_table(table, styles))
    return "".join(result)


def _split_section_pages(section: ET.Element) -> list[list[ET.Element]]:
    pages: list[list[ET.Element]] = [[]]
    for paragraph in section.findall(f"{_HP}p"):
        if paragraph.get("pageBreak") == "1" and pages[-1]:
            pages.append([])
        pages[-1].append(paragraph)
    return [page for page in pages if page]


def _render_page(
    page_index: int,
    section_index: int,
    paragraphs: list[ET.Element],
    section: ET.Element,
    styles: Mapping[str, Any],
) -> tuple[str, PreviewPage]:
    width_mm, height_mm, margins_mm = _page_spec(section)
    page_id = f"hwpx-preview-page-{page_index + 1}"
    page_style = _style_attr(
        {
            "width": _fmt_mm(width_mm),
            "min-height": _fmt_mm(height_mm),
            "padding": (
                f"{_fmt_mm(margins_mm['top'])} {_fmt_mm(margins_mm['right'])} "
                f"{_fmt_mm(margins_mm['bottom'])} {_fmt_mm(margins_mm['left'])}"
            ),
        }
    )
    body = "".join(_render_paragraph(p, styles) for p in paragraphs)
    table_count = sum(len(p.findall(f".//{_HP}tbl")) for p in paragraphs)
    page = PreviewPage(
        index=page_index,
        section_index=section_index,
        page_id=page_id,
        width_mm=width_mm,
        height_mm=height_mm,
        margins_mm=margins_mm,
        paragraph_count=len(paragraphs),
        table_count=table_count,
    )
    html_page = (
        f'<section id="{page_id}" class="hwpx-preview-page" '
        f'data-page-index="{page_index}" data-section-index="{section_index}" '
        f'style="{page_style}">{body}</section>'
    )
    return html_page, page


def _base_css(mode: str) -> str:
    long_page_css = ""
    if mode == "long":
        long_page_css = ".hwpx-preview-page { min-height: auto !important; }\n"
    return (
        "html { background: #f2f3f5; }\n"
        "body { margin: 0; padding: 12mm; color: #111827; "
        "font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; }\n"
        ".hwpx-preview-page { box-sizing: border-box; background: #fff; "
        "margin: 0 auto 10mm; box-shadow: 0 0 0 1px #cfd4dc, "
        "0 6px 18px rgba(15, 23, 42, 0.16); overflow: hidden; }\n"
        ".hwpx-paragraph { white-space: pre-wrap; word-break: break-word; }\n"
        ".hwpx-empty-paragraph { min-height: 1em; }\n"
        ".hwpx-table { font-size: 10pt; }\n"
        ".hwpx-table td { box-sizing: border-box; overflow-wrap: anywhere; }\n"
        "@media print { body { padding: 0; background: #fff; } "
        ".hwpx-preview-page { margin: 0; box-shadow: none; page-break-after: always; } }\n"
        f"{long_page_css}"
    )


def _document_html(
    *,
    title: str,
    mode: str,
    body: str,
    screenshot: bool = False,
) -> str:
    extra_css = ""
    if screenshot:
        extra_css = (
            "html, body { background: #fff; }\n"
            "body { padding: 0; }\n"
            ".hwpx-preview-page { margin: 0; box-shadow: none; }\n"
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        f"  <title>{html.escape(title)}</title>\n"
        f"  <style>{_base_css(mode)}{extra_css}</style>\n"
        "</head>\n"
        f'<body data-hwpx-preview-mode="{html.escape(mode)}">\n'
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def render_layout_preview(
    source: str | Path | bytes,
    *,
    mode: str = "pages",
    title: str = "HWPX Layout Preview",
) -> LayoutPreview:
    """Render an HWPX package into layout-aware HTML.

    Args:
        source: HWPX file path or raw HWPX bytes.
        mode: ``"pages"`` for page boxes or ``"long"`` for a scroll-friendly
            continuous page view.
        title: HTML document title.
    """

    if mode not in {"pages", "long"}:
        raise ValueError("mode must be 'pages' or 'long'")

    parts, warnings = _read_package_parts(source)
    header = _parse_xml(parts, "Contents/header.xml", warnings)
    styles = _collect_style_maps(header)
    pages_html: list[str] = []
    pages: list[PreviewPage] = []
    for section_index, name in enumerate(_section_names(parts)):
        section = _parse_xml(parts, name, warnings)
        if section is None:
            continue
        split_pages = _split_section_pages(section)
        if mode == "long":
            split_pages = [section.findall(f"{_HP}p")]
        for paragraphs in split_pages:
            page_html, page = _render_page(
                len(pages),
                section_index,
                paragraphs,
                section,
                styles,
            )
            pages_html.append(page_html)
            pages.append(page)

    if not pages:
        warnings.append("no renderable HWPX sections were found")

    document = _document_html(title=title, mode=mode, body="".join(pages_html))
    return LayoutPreview(
        html=document,
        pages=tuple(pages),
        warnings=tuple(warnings),
        mode=mode,
        page_fragments=tuple(pages_html),
    )


__all__ = ["LayoutPreview", "PreviewPage", "render_layout_preview"]
