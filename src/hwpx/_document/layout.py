# SPDX-License-Identifier: Apache-2.0
"""Formatting and page-layout domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from ..errors import HwpxStateError, HwpxTypeError, HwpxValueError
from ..objects.results import (
    ColumnLayout,
    ListFormatResult,
    PageMargins,
    PageSetup,
    PageSize,
    ParagraphFormatResult,
    Units,
)
from ..oxml._document_primitives import NEW_NUM_KINDS
from ..oxml.namespaces import HH, HP
from ..oxml.objects import HwpxOxmlInlineObject
from ..oxml.section_format import _PAGE_LANDSCAPE, _PAGE_PORTRAIT, _page_orientation_value
from ._units import _mm_to_hwp_units, _pt_to_hwp_units

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import (
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
    # PORTRAIT/NARROW -> WIDELY and LANDSCAPE/WIDE -> NARROWLY; the stored
    # values themselves keep Hancom's meaning (WIDELY is portrait).
    orientation = _page_orientation_value(value)
    if orientation is None:
        raise HwpxValueError(
            f"unsupported page orientation: {value}",
            code="page-orientation-unsupported",
            context={"requested": str(value)},
            suggestion="Pass 'PORTRAIT' or 'LANDSCAPE'.",
        )
    return orientation


#: Keys of ``set_paragraph_format(border=...)``.
_PARAGRAPH_BORDER_KEYS = frozenset(
    {"sides", "color", "width", "type", "connect", "offset_mm", "ignore_margin"}
)
_PARAGRAPH_BORDER_SIDES = ("left", "right", "top", "bottom")


def _paragraph_border_problem(
    spec: Mapping[str, Any], sides: tuple[str, ...], offsets: tuple[Any, ...]
) -> str | None:
    unknown = sorted(set(spec) - _PARAGRAPH_BORDER_KEYS)
    if unknown:
        return f"unknown paragraph border keys: {unknown}"
    if not sides or any(side not in _PARAGRAPH_BORDER_SIDES for side in sides):
        return f"unsupported paragraph border sides: {list(sides)}"
    if len(offsets) != 4 or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 for value in offsets
    ):
        return "offset_mm must be a non-negative number or four of them (left, right, top, bottom)"
    return None


def _paragraph_border_attrs(
    header: Any,
    border: Mapping[str, Any] | None,
    *,
    bottom_border: bool,
    border_color: str,
    border_width: str,
) -> dict[str, str] | None:
    """``hh:paraPr/hh:border`` attributes for ``border`` (or ``bottom_border``)."""

    if border is None and not bottom_border:
        return None
    spec: Mapping[str, Any] = (
        border if border is not None
        else {"sides": ("bottom",), "color": border_color, "width": border_width}
    )
    raw_sides = spec.get("sides", _PARAGRAPH_BORDER_SIDES)
    sides = tuple(str(side).strip().lower() for side in ((raw_sides,) if isinstance(raw_sides, str) else raw_sides))
    raw_offsets = spec.get("offset_mm", 0)
    offsets = tuple((raw_offsets,) * 4 if isinstance(raw_offsets, (int, float)) else raw_offsets)
    problem = (
        "pass either bottom_border or border, not both"
        if border is not None and bottom_border
        else _paragraph_border_problem(spec, sides, offsets)
    )
    if problem is not None:
        raise HwpxValueError(
            problem,
            code="paragraph-border-invalid",
            context={"border": {str(key): str(value) for key, value in spec.items()}},
            suggestion=(
                "border keys: sides, color, width, type, connect, offset_mm "
                "(mm, one number or left/right/top/bottom), ignore_margin."
            ),
        )
    border_fill_id = header.ensure_border_fill(
        border_color=str(spec.get("color", "#000000")),
        border_width=str(spec.get("width", "0.12 mm")),
        active_borders=sides,
        border_type=str(spec.get("type", "SOLID")),
    )
    left, right, top, bottom = (str(_mm_to_hwp_units(float(value))) for value in offsets)
    return {
        "borderFillIDRef": border_fill_id,
        "offsetLeft": left,
        "offsetRight": right,
        "offsetTop": top,
        "offsetBottom": bottom,
        "connect": "1" if spec.get("connect") else "0",
        "ignoreMargin": "1" if spec.get("ignore_margin") else "0",
    }


def _resolve_paragraph_targets(
    doc: "HwpxDocument",
    *,
    paragraph_index: int | None = None,
    paragraph_indexes: Sequence[int] | None = None,
) -> list[tuple[int, HwpxOxmlParagraph]]:
    paragraphs = doc.paragraphs
    if not paragraphs:
        raise HwpxValueError(
            "document does not contain any paragraphs",
            code="paragraph-missing",
            suggestion="Call doc.add_paragraph() first.",
        )
    if paragraph_index is not None and paragraph_indexes is not None:
        raise HwpxValueError(
            "use either paragraph_index or paragraph_indexes, not both",
            code="paragraph-argument-conflict",
            suggestion="Pass only one.",
        )

    if paragraph_indexes is None:
        indexes = list(range(len(paragraphs))) if paragraph_index is None else [paragraph_index]
    else:
        indexes = [int(index) for index in paragraph_indexes]
        if not indexes:
            raise HwpxValueError(
            "paragraph_indexes 가 비어 있습니다.",
            code="paragraph-indexes-empty",
            suggestion="서식을 적용할 문단 인덱스를 하나 이상 지정하세요.",
        )

    targets: list[tuple[int, HwpxOxmlParagraph]] = []
    for index in indexes:
        if index < 0 or index >= len(paragraphs):
            raise IndexError("paragraph index out of range")
        targets.append((index, paragraphs[index]))
    return targets


def _tree_root(element: Any) -> Any:
    if hasattr(element, "getparent"):
        while element.getparent() is not None:
            element = element.getparent()
    return element


def _resolve_paragraph_objects(
    doc: "HwpxDocument", paragraphs: Sequence[HwpxOxmlParagraph]
) -> list[HwpxOxmlParagraph]:
    """Check that every paragraph object belongs to *doc*, before anything changes.

    Body, table cell (nested too), header and footer paragraphs all live in a
    section's XML tree, so a paragraph belongs to the document when its element
    is inside one of the document's section elements.
    """

    from ..oxml import HwpxOxmlParagraph

    items = list(paragraphs)
    if not items:
        raise HwpxValueError(
            "paragraphs 가 비어 있습니다.",
            code="paragraph-indexes-empty",
            suggestion="서식을 적용할 문단을 하나 이상 지정하세요.",
        )
    roots = [section.element for section in doc.sections]
    resolved: list[HwpxOxmlParagraph] = []
    for position, paragraph in enumerate(items):
        if not isinstance(paragraph, HwpxOxmlParagraph):
            raise HwpxTypeError(
                f"paragraphs[{position}] 는 문단 객체가 아닙니다 — {type(paragraph).__name__}.",
                code="paragraph-invalid-type",
                context={"position": position, "type": type(paragraph).__name__},
                suggestion="doc.paragraphs, cell.paragraphs, header.paragraphs 의 문단을 넘기세요.",
            )
        element = paragraph.element
        root = _tree_root(element)
        inside = (
            any(root is section_root for section_root in roots)
            if hasattr(element, "getparent")
            else any(node is element for section_root in roots for node in section_root.iter())
        )
        if not inside:
            raise HwpxValueError(
                f"paragraphs[{position}] 는 이 문서에 속한 문단이 아닙니다.",
                code="paragraph-not-in-document",
                context={"position": position},
                suggestion="이 문서에서 얻은 문단(본문·셀·머리말·꼬리말)을 넘기세요. 지운 문단이나 다른 문서의 문단은 받지 않습니다.",
            )
        if all(element is not seen.element for seen in resolved):
            resolved.append(paragraph)
    return resolved


def set_paragraph_format(
    doc: "HwpxDocument",
    *,
    paragraph_index: int | None = None,
    paragraph_indexes: Sequence[int] | None = None,
    paragraphs: Sequence[HwpxOxmlParagraph] | None = None,
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
    column_break: bool | None = None,
    bottom_border: bool = False,
    border_color: str = "#BFBFBF",
    border_width: str = "0.12 mm",
    tab_stops: Sequence[Mapping[str, Any]] | None = None,
    auto_tab_left: bool | None = None,
    auto_tab_right: bool | None = None,
    border: Mapping[str, Any] | None = None,
) -> ParagraphFormatResult:
    """Apply paragraph-level formatting using human units.

    Targets are body paragraphs by index (``paragraph_index`` /
    ``paragraph_indexes``; neither means every body paragraph) or paragraph
    objects of this document (``paragraphs``): body, table cell (nested
    tables too), header and footer paragraphs. The result lists body indexes
    only; ``formatted`` counts every target.

    Millimetre inputs are converted to HWP units; paragraph spacing uses
    points; line spacing is stored as a percent value. ``keep_with_next`` /
    ``keep_lines`` / ``page_break_before`` set the paragraph's keep-together
    (``<hh:breakSetting>``) flags via a freshly minted paraPr. ``column_break``
    is a different mechanism -- ``hp:p``'s own ``columnBreak`` attribute, a
    per-paragraph-instance forced break (not a shared paraPr style property
    like ``page_break_before``) -- applied directly to each target paragraph.

    ``tab_stops`` is a sequence of ``{"pos_mm": ..., "type": "LEFT"|"RIGHT"|
    "CENTER"|"DECIMAL", "leader": "NONE"|...}`` mappings (``type``/``leader``
    default to the real-corpus-majority ``"LEFT"``/``"NONE"``) — order is
    meaningful, matching how real multi-stop documents list them
    position-ascending. Passing ``tab_stops``/``auto_tab_left``/
    ``auto_tab_right`` mints (or reuses — dedupe) a ``hh:tabPr`` and wires
    the paragraph's ``tabPrIDRef`` to it.

    ``border`` is a mapping for a paragraph border: ``sides`` (default all
    four of ``"left"``/``"right"``/``"top"``/``"bottom"``), ``color``
    (``"#000000"``), ``width`` (``"0.12 mm"``), ``type`` (``"SOLID"``),
    ``offset_mm`` (gap to the text in mm, one number or ``(left, right, top,
    bottom)``, default 0), ``connect`` and ``ignore_margin`` (default
    ``False``). With
    ``connect=True`` Hancom draws consecutive paragraphs that share the
    paragraph shape as one box, across columns and pages; give an empty
    paragraph inside the box the same format so it does not split the box.
    ``bottom_border=True`` is the older bottom-only form.
    """

    if not doc._root.headers:
        raise HwpxValueError(
            "document does not contain any headers",
            code="document-header-missing",
            suggestion="Check that this is an intact HWPX package.",
        )
    header = doc._root.headers[0]

    if line_spacing_percent is not None and float(line_spacing_percent) <= 0:
        raise HwpxValueError(
            "line_spacing_percent must be positive",
            code="paragraph-line-spacing-invalid",
            suggestion="100 is the default (100%).",
        )

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
            raise HwpxValueError(
                "outline_level must be between 0 and 10",
                code="paragraph-outline-level-out-of-range",
                context={"requested": level, "min": 0, "max": 10},
                suggestion="0 means no outline. Use doc.add_heading() for heading paragraphs.",
            )

    break_setting: dict[str, bool] = {}
    if keep_with_next is not None:
        break_setting["keep_with_next"] = bool(keep_with_next)
    if keep_lines is not None:
        break_setting["keep_lines"] = bool(keep_lines)
    if page_break_before is not None:
        break_setting["page_break_before"] = bool(page_break_before)

    wants_tab_definition = (
        tab_stops is not None or auto_tab_left is not None or auto_tab_right is not None
    )

    if (
        alignment is None
        and line_spacing_percent is None
        and not margins
        and heading is None
        and not bottom_border
        and border is None
        and not break_setting
        and not wants_tab_definition
        and column_break is None
    ):
        raise HwpxValueError(
            "at least one paragraph formatting option is required",
            code="paragraph-format-empty",
            suggestion="Pass alignment, line_spacing_percent, or another option to change.",
        )

    # Resolve every target before the header gains tab or border definitions,
    # so a bad target changes nothing.
    targets: list[tuple[int | None, HwpxOxmlParagraph]]
    if paragraphs is not None:
        if paragraph_index is not None or paragraph_indexes is not None:
            raise HwpxValueError(
                "use either paragraphs or paragraph_index/paragraph_indexes, not both",
                code="paragraph-argument-conflict",
                suggestion="Pass only one.",
            )
        objects = _resolve_paragraph_objects(doc, paragraphs)
        body = doc.paragraphs
        body_index = {paragraph.element: index for index, paragraph in enumerate(body)}
        targets = [(body_index.get(paragraph.element), paragraph) for paragraph in objects]
    else:
        targets = list(_resolve_paragraph_targets(doc,
            paragraph_index=paragraph_index,
            paragraph_indexes=paragraph_indexes,
        ))

    tab_pr_id: str | None = None
    if wants_tab_definition:
        converted_stops: list[dict[str, object]] = []
        for index, stop in enumerate(tab_stops or ()):
            if "pos_mm" not in stop or stop["pos_mm"] is None:
                raise HwpxValueError(
                    f"tab_stops[{index}] is missing 'pos_mm'",
                    code="paragraph-tab-pos-invalid",
                    context={"index": index},
                    suggestion="각 tab stop은 'pos_mm'(mm, 0 이상)가 필요합니다.",
                )
            converted_stops.append({
                "pos": _mm_to_hwp_units(float(stop["pos_mm"])),
                "type": stop.get("type"),
                "leader": stop.get("leader"),
            })
        tab_pr_id = header.ensure_tab_definition(
            tab_stops=converted_stops,
            auto_tab_left=bool(auto_tab_left),
            auto_tab_right=bool(auto_tab_right),
        )

    border_attrs = _paragraph_border_attrs(
        header,
        border,
        bottom_border=bottom_border,
        border_color=border_color,
        border_width=border_width,
    )

    # column_break bypasses paraPr entirely (it's hp:p's own attribute, not
    # a shared style) -- only mint a new paraPr when one of the *other*
    # options actually needs it, so a column_break-only call doesn't churn
    # a needless duplicate paraPr id.
    wants_para_pr_change = (
        alignment is not None
        or line_spacing_percent is not None
        or bool(margins)
        or heading is not None
        or border_attrs is not None
        or bool(break_setting)
        or wants_tab_definition
    )

    for paragraph in (paragraph for _, paragraph in targets):
        if wants_para_pr_change:
            para_pr_id = header.ensure_paragraph_format(
                base_para_pr_id=paragraph.para_pr_id_ref,
                alignment=alignment,
                line_spacing_percent=line_spacing_percent,
                margins=margins,
                heading=heading,
                border=border_attrs,
                break_setting=break_setting or None,
                tab_pr_id_ref=tab_pr_id,
            )
            paragraph.para_pr_id_ref = para_pr_id
        if column_break is not None:
            paragraph.column_break = column_break

    return ParagraphFormatResult(
        formatted=len(targets),
        paragraphs=tuple(index for index, _ in targets if index is not None),
        units=Units(indent="mm", paragraph_spacing="pt", line_spacing="%"),
    )


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
) -> ListFormatResult:
    """Apply bullet or numbered-list paragraph properties to paragraphs."""

    if level < 1:
        raise HwpxValueError(
            "level must be 1 or greater",
            code="style-list-level-invalid",
            context={"requested": level},
            suggestion="Levels start at 1.",
        )
    if not doc._root.headers:
        raise HwpxValueError(
            "document does not contain any headers",
            code="document-header-missing",
            suggestion="Check that this is an intact HWPX package.",
        )

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
        raise HwpxStateError(
            "failed to create list paragraph property",
            code="style-list-property-failed",
            suggestion="Check that the document header.xml is intact.",
        )
    heading = {
        "type": heading_element.get("type", "NONE"),
        "idRef": heading_element.get("idRef", "0"),
        "level": heading_element.get("level", str(level - 1)),
    }
    targets = _resolve_paragraph_targets(doc,
        paragraph_index=paragraph_index,
        paragraph_indexes=paragraph_indexes,
    )

    formatted: list[int] = []
    first_para_pr_id: str | None = None
    for index, paragraph in targets:
        para_pr_id = header.ensure_paragraph_format(
            base_para_pr_id=paragraph.para_pr_id_ref,
            heading=heading,
        )
        paragraph.para_pr_id_ref = para_pr_id
        formatted.append(index)
        if first_para_pr_id is None:
            first_para_pr_id = para_pr_id

    return ListFormatResult(
        formatted=len(formatted),
        paragraphs=tuple(formatted),
        kind=kind,
        level=level,
        para_pr_id_ref=first_para_pr_id if first_para_pr_id is not None else list_para_pr_id,
    )


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
) -> PageSetup:
    """Set page size, margins, orientation, and optional columns in human units.

    The page is written as Hancom writes it: ``WIDELY`` for portrait and
    ``NARROWLY`` for landscape, both with the paper's portrait size. The
    returned ``page_size`` reports the page as drawn (landscape is wider).
    """

    normalized_orientation = _normalize_page_orientation(orientation)
    target_width_mm = width_mm
    target_height_mm = height_mm
    if paper_size:
        paper_key = paper_size.strip().upper()
        if paper_key not in _PAPER_SIZES_MM:
            raise HwpxValueError(
            f"unsupported paper_size: {paper_size}",
            code="page-paper-size-unsupported",
            context={"requested": str(paper_size), "supported": sorted(_PAPER_SIZES_MM)},
            suggestion=f"Supported: {', '.join(sorted(_PAPER_SIZES_MM))}",
        )
        paper_width, paper_height = _PAPER_SIZES_MM[paper_key]
        target_width_mm = paper_width if target_width_mm is None else target_width_mm
        target_height_mm = paper_height if target_height_mm is None else target_height_mm

    if target_width_mm is not None and target_height_mm is not None:
        short_side, long_side = sorted((target_width_mm, target_height_mm))
        if normalized_orientation == _PAGE_LANDSCAPE:
            target_width_mm, target_height_mm = long_side, short_side
        elif normalized_orientation == _PAGE_PORTRAIT:
            target_width_mm, target_height_mm = short_side, long_side

    width = _mm_to_hwp_units(float(target_width_mm)) if target_width_mm is not None else None
    height = _mm_to_hwp_units(float(target_height_mm)) if target_height_mm is not None else None
    if width is not None or height is not None or normalized_orientation is not None:
        # Call the local primitives directly rather than `doc.set_page_size`/
        # `doc.set_page_margins`/`doc.set_columns` below — all three names
        # moved in 6.0 (design table rows 88/91/82 respectively), and going
        # through the facade would fire a DeprecationWarning on every
        # `set_page_setup` call even when reached via the new
        # `doc.page.setup` namespace path.
        set_page_size(
            doc,
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
        set_page_margins(
            doc,
            section=section,
            section_index=section_index,
            **hwp_margins,
        )

    column_layout: ColumnLayout | None = None
    if columns is not None:
        col_count = int(columns)
        if col_count < 1:
            raise HwpxValueError(
            "columns must be 1 or greater",
            code="page-columns-invalid",
            context={"requested": col_count},
            suggestion="Use columns=1 to remove columns.",
        )
        gap_mm = float(column_gap_mm or 0)
        gap = _mm_to_hwp_units(gap_mm)
        set_columns(
            doc,
            col_count=col_count,
            same_gap=gap,
            section=section,
            section_index=section_index,
        )
        column_layout = ColumnLayout(count=col_count, gap_mm=gap_mm)

    return PageSetup(
        page_size=PageSize(
            width_mm=target_width_mm,
            height_mm=target_height_mm,
            orientation=normalized_orientation,
        ),
        margins=PageMargins(**margin_values),
        columns=column_layout,
        units=Units(page="mm", margins="mm", columns_gap="mm"),
    )


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
    """Set the columns of a section, or start new columns at a paragraph.

    Without ``paragraph`` this rewrites the section's own column layout (the
    ``hp:colPr`` next to ``hp:secPr``) in place, so the whole section is laid
    out in ``col_count`` columns. With ``paragraph`` it adds a column
    definition control there, and the text from that paragraph on uses it.

    Args:
        col_count: Number of columns (1–255).
        col_type: ``NEWSPAPER``, ``BALANCED_NEWSPAPER``, or ``PARALLEL``.
        same_gap: Gap in HWPUNIT (7200 = 1 inch).
        separator_type: Optional column separator line type (e.g. ``SOLID``).
    """
    if not 1 <= col_count <= 255:
        raise HwpxValueError(
            "col_count must be between 1 and 255",
            code="page-columns-invalid",
            context={"requested": col_count},
            suggestion="Use columns=1 to remove columns.",
        )
    if paragraph is None:
        target_section = _resolve_section(doc, section=section, section_index=section_index)
        ctrl = target_section.properties.set_columns(
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
        if ctrl is not None:
            return HwpxOxmlInlineObject(ctrl, target_section.paragraphs[0])
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
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a hyperlink (fieldBegin + text + fieldEnd).

    The display text follows the Hancom convention (blue ``#0000FF`` text
    with a blue bottom underline — dominant styling across real-corpus
    hyperlinks) on the character look of the paragraph it goes into, unless
    ``char_pr_id_ref`` overrides it. ``paragraph.add_hyperlink`` picks that
    style, so a link looks the same whichever way it was added.

    Returns the ``<hp:ctrl>`` wrapper containing the ``<hp:fieldBegin>``.
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_hyperlink(url, display_text, char_pr_id_ref=char_pr_id_ref)


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
            raise HwpxValueError(
            "document does not contain any sections",
            code="section-missing",
            suggestion="Call doc.add_section() first.",
        )
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
        orientation=_normalize_page_orientation(orientation),
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
        raise HwpxValueError(
            "kind must be 'header' or 'footer'",
            code="page-kind-invalid",
            context={"requested": kind},
            suggestion="Use doc.page.set_header() / doc.page.set_footer().",
        )
    if content is not None and text is not None:
        raise HwpxValueError(
            "use either text or content, not both",
            code="page-argument-conflict",
            suggestion="Use text= for one line, content= for multiple paragraphs.",
        )
    # Call the local primitives directly rather than `doc.set_header_content`/
    # `doc.set_footer_content`/`doc.set_header_text`/`doc.set_footer_text` —
    # all four names moved in 6.0 (design table rows 83-86), and going
    # through the facade would fire a DeprecationWarning on every call even
    # when reached via the new `doc.page.set_header`/`set_footer` paths.
    if content is not None:
        if normalized == "header":
            return set_header_content(
                doc,
                content,
                section=section,
                section_index=section_index,
                page_type=page_type,
            )
        return set_footer_content(
            doc,
            content,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )

    value = "" if text is None else text
    if normalized == "header":
        return set_header_text(
            doc,
            value,
            section=section,
            section_index=section_index,
            page_type=page_type,
        )
    return set_footer_text(
        doc,
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

    # `set_header_footer` (local) rather than `doc.set_header_footer` — that
    # facade name is demoted (not just moved) in 6.0 (design table row 102),
    # so the shim warns too; calling the primitive directly avoids that on
    # every `set_page_number` call even via `doc.page.set_page_number`.
    return set_header_footer(
        doc,
        kind=target,
        content=[{"align": align, "children": children}],
        section=section,
        section_index=section_index,
        page_type=page_type,
    )


def restart_page_number(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    number: int = 1,
    kind: str = "PAGE",
) -> "HwpxOxmlInlineObject":
    """Restart *kind*'s running count at *number* from *paragraph* onward.

    Inserts ``<hp:ctrl><hp:newNum num="{number}" numType="{kind}"/></hp:ctrl>``
    — a section-mid restart point, distinct from ``set_page_number`` (which
    places the *display* field in a header/footer). ``kind`` defaults to
    ``"PAGE"``, the only value real corpus (hwpxlib_corpus) observes; the
    other six (``FOOTNOTE``/``ENDNOTE``/``PICTURE``/``TABLE``/``EQUATION``/
    ``TOTAL_PAGE``) are schema-legal but unattested.
    """

    normalized_kind = str(kind or "PAGE").upper()
    if normalized_kind not in NEW_NUM_KINDS:
        raise HwpxValueError(
            f"unsupported kind {kind!r}",
            code="page-new-num-kind-invalid",
            context={"kind": normalized_kind, "allowed": sorted(NEW_NUM_KINDS)},
            suggestion="Use one of: " + ", ".join(sorted(NEW_NUM_KINDS)),
        )
    return paragraph.add_new_num(number=number, kind=normalized_kind)


def hide_page_elements(
    doc: "HwpxDocument",
    paragraph: "HwpxOxmlParagraph",
    *,
    header: bool = False,
    footer: bool = False,
    master_page: bool = False,
    border: bool = False,
    fill: bool = False,
    page_num: bool = False,
) -> "HwpxOxmlInlineObject":
    """Hide the named page elements on *paragraph*'s page only.

    Inserts ``<hp:ctrl><hp:pageHiding .../></hp:ctrl>`` (``ParaList XML
    schema.xml:148-163`` — six independent booleans, all default unhidden).
    Hancom applies it to that page alone (its "hide on the current page
    only"); the next page shows the elements again. *page_num* hides
    Hancom's page-number control, not the header/footer number that
    ``set_page_number`` writes -- hide that one with *footer* (or *header*).
    """

    return paragraph.add_page_hiding(
        header=header,
        footer=footer,
        master_page=master_page,
        border=border,
        fill=fill,
        page_num=page_num,
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


def flow_table_taller_than_page(doc: "HwpxDocument", table: Any) -> None:
    """Let a new body *table* flow across pages when its rows alone outgrow a page.

    Hancom never breaks a table laid out as a character (``treatAsChar``, the
    ``add_table`` default) across pages: one taller than the page body is cut
    off at the paper's edge. Such a table becomes a flowing one instead
    (``Table.set_treat_as_char(False)``), which Hancom breaks between rows.
    """

    properties = table.paragraph.section.properties
    size, margins = properties.page_size, properties.page_margins
    body = size.drawn_height - margins.top - margins.bottom - margins.header - margins.footer
    if body > 0 and _table_min_height(doc, table.element) > body:
        table.set_treat_as_char(False)


def _table_min_height(doc: "HwpxDocument", table: Any) -> int:
    """A lower bound of the drawn height: every row is at least its tallest
    single-row cell, and a cell at least one line of its text plus its top and
    bottom margins."""

    total = 0
    for row in table.findall(f"{HP}tr"):
        tallest = 0
        for cell in row.findall(f"{HP}tc"):
            span = cell.find(f"{HP}cellSpan")
            if span is not None and span.get("rowSpan", "1") != "1":
                continue
            run = cell.find(f".//{HP}run")
            line = _char_height(doc, run.get("charPrIDRef") if run is not None else None)
            margin = cell.find(f"{HP}cellMargin")
            padding = _int_attr(margin, "top") + _int_attr(margin, "bottom")
            tallest = max(tallest, _int_attr(cell.find(f"{HP}cellSz"), "height"), line + padding)
        total += tallest
    return total


def _char_height(doc: "HwpxDocument", char_pr_id_ref: str | None) -> int:
    style = doc._root.char_property(char_pr_id_ref if char_pr_id_ref is not None else "0")
    try:
        return int(style.attributes.get("height", "1000")) if style is not None else 1000
    except ValueError:
        return 1000


def _int_attr(element: Any, name: str) -> int:
    if element is None:
        return 0
    try:
        return int(element.get(name, "0"))
    except ValueError:
        return 0
