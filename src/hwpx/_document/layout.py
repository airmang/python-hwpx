# SPDX-License-Identifier: Apache-2.0
"""Formatting and page-layout domain owner behind the HwpxDocument facade (S-084)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from ..oxml.namespaces import HH
from ._units import _mm_to_hwp_units, _pt_to_hwp_units

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import (
        HwpxOxmlInlineObject,
        HwpxOxmlParagraph,
        HwpxOxmlSection,
        HwpxOxmlSectionHeaderFooter,
    )

_HH = HH


_PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B4": (257.0, 364.0),
    "B5": (182.0, 257.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
}


def _normalize_page_orientation(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    aliases = {
        "PORTRAIT": "PORTRAIT",
        "NARROW": "PORTRAIT",
        "NARROWLY": "PORTRAIT",
        "LANDSCAPE": "WIDELY",
        "WIDE": "WIDELY",
        "WIDELY": "WIDELY",
    }
    orientation = aliases.get(normalized)
    if orientation is None:
        raise ValueError(f"unsupported page orientation: {value}")
    return orientation


def _resolve_paragraph_targets(
    doc: "HwpxDocument",
    *,
    paragraph_index: int | None = None,
    paragraph_indexes: Sequence[int] | None = None,
) -> list[tuple[int, HwpxOxmlParagraph]]:
    paragraphs = doc.paragraphs
    if not paragraphs:
        raise ValueError("document does not contain any paragraphs")
    if paragraph_index is not None and paragraph_indexes is not None:
        raise ValueError("use either paragraph_index or paragraph_indexes, not both")

    if paragraph_indexes is None:
        indexes = list(range(len(paragraphs))) if paragraph_index is None else [paragraph_index]
    else:
        indexes = [int(index) for index in paragraph_indexes]
        if not indexes:
            raise ValueError("paragraph_indexes must not be empty")

    targets: list[tuple[int, HwpxOxmlParagraph]] = []
    for index in indexes:
        if index < 0 or index >= len(paragraphs):
            raise IndexError("paragraph index out of range")
        targets.append((index, paragraphs[index]))
    return targets


def set_paragraph_format(
    doc: "HwpxDocument",
    *,
    paragraph_index: int | None = None,
    paragraph_indexes: Sequence[int] | None = None,
    alignment: str | None = None,
    line_spacing_percent: int | float | None = None,
    indent_left_mm: float | None = None,
    indent_right_mm: float | None = None,
    first_line_indent_mm: float | None = None,
    spacing_before_pt: float | None = None,
    spacing_after_pt: float | None = None,
    outline_level: int | None = None,
    keep_with_next: bool | None = None,
    keep_lines: bool | None = None,
    page_break_before: bool | None = None,
    bottom_border: bool = False,
    border_color: str = "#BFBFBF",
    border_width: str = "0.12 mm",
) -> dict[str, Any]:
    """Apply paragraph-level formatting using human units.

    Millimetre inputs are converted to HWP units; paragraph spacing uses
    points; line spacing is stored as a percent value. ``keep_with_next`` /
    ``keep_lines`` / ``page_break_before`` set the paragraph's keep-together
    (``<hh:breakSetting>``) flags via a freshly minted paraPr.
    """

    if not doc._root.headers:
        raise ValueError("document does not contain any headers")
    header = doc._root.headers[0]

    if line_spacing_percent is not None and float(line_spacing_percent) <= 0:
        raise ValueError("line_spacing_percent must be positive")

    margins: dict[str, int] = {}
    if first_line_indent_mm is not None:
        margins["intent"] = _mm_to_hwp_units(float(first_line_indent_mm))
    if indent_left_mm is not None:
        margins["left"] = _mm_to_hwp_units(float(indent_left_mm))
    if indent_right_mm is not None:
        margins["right"] = _mm_to_hwp_units(float(indent_right_mm))
    if spacing_before_pt is not None:
        margins["prev"] = _pt_to_hwp_units(float(spacing_before_pt))
    if spacing_after_pt is not None:
        margins["next"] = _pt_to_hwp_units(float(spacing_after_pt))

    heading: dict[str, str | int] | None = None
    if outline_level is not None:
        level = int(outline_level)
        if level <= 0:
            heading = {"type": "NONE", "idRef": "0", "level": "0"}
        elif level <= 10:
            heading = {"type": "OUTLINE", "idRef": "0", "level": str(level - 1)}
        else:
            raise ValueError("outline_level must be between 0 and 10")

    break_setting: dict[str, bool] = {}
    if keep_with_next is not None:
        break_setting["keep_with_next"] = bool(keep_with_next)
    if keep_lines is not None:
        break_setting["keep_lines"] = bool(keep_lines)
    if page_break_before is not None:
        break_setting["page_break_before"] = bool(page_break_before)

    if (
        alignment is None
        and line_spacing_percent is None
        and not margins
        and heading is None
        and not bottom_border
        and not break_setting
    ):
        raise ValueError("at least one paragraph formatting option is required")

    border: dict[str, str] | None = None
    if bottom_border:
        border_fill_id = header.ensure_border_fill(
            border_color=border_color,
            border_width=border_width,
            active_borders=("bottom",),
        )
        border = {
            "borderFillIDRef": border_fill_id,
            "offsetLeft": "0",
            "offsetRight": "0",
            "offsetTop": "0",
            "offsetBottom": "0",
            "connect": "0",
            "ignoreMargin": "0",
        }

    targets = _resolve_paragraph_targets(doc,
        paragraph_index=paragraph_index,
        paragraph_indexes=paragraph_indexes,
    )
    formatted: list[dict[str, Any]] = []
    for index, paragraph in targets:
        para_pr_id = header.ensure_paragraph_format(
            base_para_pr_id=paragraph.para_pr_id_ref,
            alignment=alignment,
            line_spacing_percent=line_spacing_percent,
            margins=margins,
            heading=heading,
            border=border,
            break_setting=break_setting or None,
        )
        paragraph.para_pr_id_ref = para_pr_id
        formatted.append({"paragraph_index": index, "paraPrIDRef": para_pr_id})

    return {
        "formatted": len(formatted),
        "paragraphs": formatted,
        "units": {
            "indent": "mm",
            "paragraphSpacing": "pt",
            "lineSpacing": "%",
        },
    }


def set_list_format(
    doc: "HwpxDocument",
    *,
    paragraph_index: int | None = None,
    paragraph_indexes: Sequence[int] | None = None,
    kind: str = "bullet",
    level: int = 1,
    bullet_char: str | None = None,
    number_format: str | None = None,
    start: int | None = None,
) -> dict[str, Any]:
    """Apply bullet or numbered-list paragraph properties to paragraphs."""

    if level < 1:
        raise ValueError("level must be 1 or greater")
    if not doc._root.headers:
        raise ValueError("document does not contain any headers")

    level_specs: list[dict[str, str]] = [{} for _ in range(level)]
    if bullet_char:
        level_specs[level - 1]["char"] = str(bullet_char)
    if number_format:
        level_specs[level - 1]["format"] = str(number_format).upper()
    if start is not None:
        level_specs[level - 1]["start"] = str(max(1, int(start)))

    refs = doc._root.ensure_numbering(kind=kind, levels=level_specs)
    list_para_pr_id = refs[level - 1]
    header = doc._root.headers[0]
    list_para_pr = header.element.find(f".//{_HH}paraPr[@id='{list_para_pr_id}']")
    heading_element = list_para_pr.find(f"{_HH}heading") if list_para_pr is not None else None
    if heading_element is None:
        raise RuntimeError("failed to create list paragraph property")
    heading = {
        "type": heading_element.get("type", "NONE"),
        "idRef": heading_element.get("idRef", "0"),
        "level": heading_element.get("level", str(level - 1)),
    }
    targets = _resolve_paragraph_targets(doc,
        paragraph_index=paragraph_index,
        paragraph_indexes=paragraph_indexes,
    )

    formatted: list[dict[str, Any]] = []
    for index, paragraph in targets:
        para_pr_id = header.ensure_paragraph_format(
            base_para_pr_id=paragraph.para_pr_id_ref,
            heading=heading,
        )
        paragraph.para_pr_id_ref = para_pr_id
        formatted.append({"paragraph_index": index, "paraPrIDRef": para_pr_id})

    return {
        "formatted": len(formatted),
        "paragraphs": formatted,
        "kind": kind,
        "level": level,
        "paraPrIDRef": formatted[0]["paraPrIDRef"] if formatted else list_para_pr_id,
    }


def set_page_setup(
    doc: "HwpxDocument",
    *,
    paper_size: str | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    orientation: str | None = None,
    margins_mm: Mapping[str, float] | None = None,
    margin_left_mm: float | None = None,
    margin_right_mm: float | None = None,
    margin_top_mm: float | None = None,
    margin_bottom_mm: float | None = None,
    header_margin_mm: float | None = None,
    footer_margin_mm: float | None = None,
    gutter_mm: float | None = None,
    columns: int | None = None,
    column_gap_mm: float | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> dict[str, Any]:
    """Set page size, margins, orientation, and optional columns in human units."""

    normalized_orientation = _normalize_page_orientation(orientation)
    target_width_mm = width_mm
    target_height_mm = height_mm
    if paper_size:
        paper_key = paper_size.strip().upper()
        if paper_key not in _PAPER_SIZES_MM:
            raise ValueError(f"unsupported paper_size: {paper_size}")
        paper_width, paper_height = _PAPER_SIZES_MM[paper_key]
        target_width_mm = paper_width if target_width_mm is None else target_width_mm
        target_height_mm = paper_height if target_height_mm is None else target_height_mm

    if target_width_mm is not None and target_height_mm is not None:
        if normalized_orientation == "WIDELY" and target_width_mm < target_height_mm:
            target_width_mm, target_height_mm = target_height_mm, target_width_mm
        elif normalized_orientation == "PORTRAIT" and target_width_mm > target_height_mm:
            target_width_mm, target_height_mm = target_height_mm, target_width_mm

    width = _mm_to_hwp_units(float(target_width_mm)) if target_width_mm is not None else None
    height = _mm_to_hwp_units(float(target_height_mm)) if target_height_mm is not None else None
    if width is not None or height is not None or normalized_orientation is not None:
        doc.set_page_size(
            width=width,
            height=height,
            orientation=normalized_orientation,
            section=section,
            section_index=section_index,
        )

    margin_source = dict(margins_mm or {})
    margin_values = {
        "left": margin_left_mm if margin_left_mm is not None else margin_source.get("left"),
        "right": margin_right_mm if margin_right_mm is not None else margin_source.get("right"),
        "top": margin_top_mm if margin_top_mm is not None else margin_source.get("top"),
        "bottom": margin_bottom_mm if margin_bottom_mm is not None else margin_source.get("bottom"),
        "header": header_margin_mm if header_margin_mm is not None else margin_source.get("header"),
        "footer": footer_margin_mm if footer_margin_mm is not None else margin_source.get("footer"),
        "gutter": gutter_mm if gutter_mm is not None else margin_source.get("gutter"),
    }
    hwp_margins = {
        name: _mm_to_hwp_units(float(value))
        for name, value in margin_values.items()
        if value is not None
    }
    if hwp_margins:
        doc.set_page_margins(
            section=section,
            section_index=section_index,
            **hwp_margins,
        )

    column_result: dict[str, Any] | None = None
    if columns is not None:
        col_count = int(columns)
        if col_count < 1:
            raise ValueError("columns must be 1 or greater")
        gap = _mm_to_hwp_units(float(column_gap_mm or 0))
        doc.set_columns(
            col_count=col_count,
            same_gap=gap,
            section=section,
            section_index=section_index,
        )
        column_result = {"count": col_count, "gap": gap}

    return {
        "pageSize": {"width": width, "height": height, "orientation": normalized_orientation},
        "margins": hwp_margins,
        "columns": column_result,
        "units": {"page": "mm", "margins": "mm", "columnsGap": "mm"},
    }


def set_columns(
    doc: "HwpxDocument",
    col_count: int = 2,
    *,
    col_type: str = "NEWSPAPER",
    layout: str = "LEFT",
    same_size: bool = True,
    same_gap: int = 1200,
    column_widths: "Sequence[tuple[int, int]] | None" = None,
    separator_type: str | None = None,
    separator_width: str | None = None,
    separator_color: str | None = None,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a column definition control.

    This adds a ``<hp:ctrl><hp:colPr>`` element to the specified paragraph.
    Text that follows will be laid out in the specified number of columns.

    Args:
        col_count: Number of columns (1–255).
        col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
        same_gap: Gap in HWPUNIT (7200 = 1 inch).
        separator_type: Optional column separator line type (e.g. ``SOLID``).
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_column_definition(
        col_count,
        col_type=col_type,
        layout=layout,
        same_size=same_size,
        same_gap=same_gap,
        column_widths=column_widths,
        separator_type=separator_type,
        separator_width=separator_width,
        separator_color=separator_color,
    )


def add_bookmark(
    doc: "HwpxDocument",
    name: str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a bookmark marker in the document.

    Returns the ``<hp:ctrl>`` wrapper element.
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_bookmark(name)


def add_hyperlink(
    doc: "HwpxDocument",
    url: str,
    display_text: str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a hyperlink (fieldBegin + text + fieldEnd).

    Returns the ``<hp:ctrl>`` wrapper containing the ``<hp:fieldBegin>``.
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_hyperlink(url, display_text)


def _resolve_section(
    doc: "HwpxDocument",
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlSection:
    target_section = section
    if target_section is None and section_index is not None:
        target_section = doc._root.sections[section_index]
    if target_section is None:
        if not doc._root.sections:
            raise ValueError("document does not contain any sections")
        target_section = doc._root.sections[-1]
    return target_section


def set_page_size(
    doc: "HwpxDocument",
    *,
    width: int | None = None,
    height: int | None = None,
    orientation: str | None = None,
    gutter_type: str | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> None:
    """Set page dimensions on the requested section through the public facade."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    target_section.properties.set_page_size(
        width=width,
        height=height,
        orientation=orientation,
        gutter_type=gutter_type,
    )


def set_page_margins(
    doc: "HwpxDocument",
    *,
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
    header: int | None = None,
    footer: int | None = None,
    gutter: int | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> None:
    """Set page margins on the requested section through the public facade."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    target_section.properties.set_page_margins(
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        header=header,
        footer=footer,
        gutter=gutter,
    )


def set_header_text(
    doc: "HwpxDocument",
    text: str,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> HwpxOxmlSectionHeaderFooter:
    """Ensure the requested section contains a header for *page_type* and set its text."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    return target_section.properties.set_header_text(text, page_type=page_type)


def set_footer_text(
    doc: "HwpxDocument",
    text: str,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> HwpxOxmlSectionHeaderFooter:
    """Ensure the requested section contains a footer for *page_type* and set its text."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    return target_section.properties.set_footer_text(text, page_type=page_type)


def set_header_content(
    doc: "HwpxDocument",
    content: Sequence[Mapping[str, Any]],
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> HwpxOxmlSectionHeaderFooter:
    """Ensure the requested section contains a rich header for *page_type*."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    return target_section.properties.set_header_content(content, page_type=page_type)


def set_footer_content(
    doc: "HwpxDocument",
    content: Sequence[Mapping[str, Any]],
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> HwpxOxmlSectionHeaderFooter:
    """Ensure the requested section contains a rich footer for *page_type*."""

    target_section = _resolve_section(doc, section=section, section_index=section_index)
    return target_section.properties.set_footer_content(content, page_type=page_type)


def set_header_footer(
    doc: "HwpxDocument",
    *,
    kind: str,
    text: str | None = None,
    content: Sequence[Mapping[str, Any]] | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> HwpxOxmlSectionHeaderFooter:
    """Set a header or footer using plain text or rich content specs."""

    normalized = kind.strip().lower()
    if normalized not in {"header", "footer"}:
        raise ValueError("kind must be 'header' or 'footer'")
    if content is not None and text is not None:
        raise ValueError("use either text or content, not both")
    if content is not None:
        if normalized == "header":
            return doc.set_header_content(
                content,
                section=section,
                section_index=section_index,
                page_type=page_type,
            )
        return doc.set_footer_content(
            content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    value = "" if text is None else text
    if normalized == "header":
        return doc.set_header_text(
            value,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )
    return doc.set_footer_text(
        value,
        section=section,
        section_index=section_index,
        page_type=page_type,
    )


def set_page_number(
    doc: "HwpxDocument",
    *,
    target: str = "footer",
    page_type: str = "BOTH",
    format: str = "page",
    align: str = "CENTER",
    position: str = "BOTTOM_CENTER",
    prefix: str = "",
    suffix: str = "",
    format_type: str | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlSectionHeaderFooter:
    """Replace header/footer content with an automatic page-number field."""

    children: list[dict[str, Any]] = []
    if prefix:
        children.append({"type": "run", "text": prefix})
    children.append(
        {
            "type": "page_number",
            "page_number": format,
            "position": position,
            "formatType": format_type,
        }
    )
    if suffix:
        children.append({"type": "run", "text": suffix})

    return doc.set_header_footer(
        kind=target,
        content=[{"align": align, "children": children}],
        section=section,
        section_index=section_index,
        page_type=page_type,
    )


def remove_header(
    doc: "HwpxDocument",
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> None:
    """Remove the header linked to *page_type* from the requested section if present."""

    target_section = section
    if target_section is None and section_index is not None:
        target_section = doc._root.sections[section_index]
    if target_section is None:
        if not doc._root.sections:
            return
        target_section = doc._root.sections[-1]
    target_section.properties.remove_header(page_type=page_type)


def remove_footer(
    doc: "HwpxDocument",
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    page_type: str = "BOTH",
) -> None:
    """Remove the footer linked to *page_type* from the requested section if present."""

    target_section = section
    if target_section is None and section_index is not None:
        target_section = doc._root.sections[section_index]
    if target_section is None:
        if not doc._root.sections:
            return
        target_section = doc._root.sections[-1]
    target_section.properties.remove_footer(page_type=page_type)
