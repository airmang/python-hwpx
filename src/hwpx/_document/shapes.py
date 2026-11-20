# SPDX-License-Identifier: Apache-2.0
"""Shape/control/note domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from ._units import _mm_to_hwp_units
from ..errors import HwpxStateError, HwpxValueError, argument_type_error
from ._resolve import home_paragraph, note_home_paragraph, refused_leaves_no_paragraph
from ..oxml.objects import HwpxOxmlEquation, _closed_points
from ..oxml.shape_position import (
    equation_base_unit, validate_box_size, validate_equation_font, validate_equation_script,
    validate_original_size, validate_rect_ratio, validate_shape_size,
)

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..objects.highlight import ComposedCharacter, Ruby
    from ..objects.results import Alignment
    from ..oxml import (
        ContainerMember,
        HwpxOxmlInlineObject,
        HwpxOxmlNote,
        HwpxOxmlParagraph,
        HwpxOxmlSection,
        HwpxOxmlShape,
        Style,
    )


@refused_leaves_no_paragraph
def add_shape(
    doc: "HwpxDocument",
    shape_type: str,
    *,
    section: HwpxOxmlSection | None = None,
    attributes: dict[str, str] | None = None,
    para_pr_id_ref: str | int | None = None,
    style: "int | str | Style | None" = None,
    char_pr_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
    **extra_attrs: str,
) -> HwpxOxmlInlineObject:
    """Insert an inline shape into a new paragraph.

    Low-level escape hatch — writes only the element and attributes it is
    handed, so the result is not openable by Hancom until the required OWPML
    children are supplied.  Warns while they are missing.  Prefer
    :func:`add_line`, :func:`add_rectangle`, and :func:`add_ellipse`.
    """

    paragraph = note_home_paragraph(doc, doc._add_paragraph(  # 7.0: doc.add_paragraph takes no raw XML attributes
        "",
        section=section,
        para_pr_id_ref=para_pr_id_ref,
        style=style,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
        xml_attributes=extra_attrs,
    ))
    return paragraph.add_shape(
        shape_type,
        attributes=attributes,
        run_attributes=run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )


@refused_leaves_no_paragraph
def add_control(
    doc: "HwpxDocument",
    *,
    section: HwpxOxmlSection | None = None,
    attributes: dict[str, str] | None = None,
    control_type: str | None = None,
    para_pr_id_ref: str | int | None = None,
    style: "int | str | Style | None" = None,
    char_pr_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
    **extra_attrs: str,
) -> HwpxOxmlInlineObject:
    """Insert a control inline object into a new paragraph.

    Low-level escape hatch — an ``<hp:ctrl>`` means nothing without the child
    element that carries the control, and Hancom refuses to open a document
    containing an empty one, so this warns until a child is appended.
    """

    paragraph = note_home_paragraph(doc, doc._add_paragraph(  # 7.0: doc.add_paragraph takes no raw XML attributes
        "",
        section=section,
        para_pr_id_ref=para_pr_id_ref,
        style=style,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
        xml_attributes=extra_attrs,
    ))
    return paragraph.add_control(
        attributes=attributes,
        control_type=control_type,
        run_attributes=run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )


@refused_leaves_no_paragraph
def add_footnote(
    doc: "HwpxDocument",
    text: str,
    paragraph: HwpxOxmlParagraph | None = None,
    *,
    section: HwpxOxmlSection | None = None,
    char_pr_id_ref: str | int | None = None,
    offset: int | None = None,
) -> HwpxOxmlNote:
    """Add a footnote to an existing paragraph, or create a new one.

    When *paragraph* is ``None`` a new paragraph is appended to the given
    (or last) section.
    """

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "",
            section=section,
            include_run=False,
        )
    return paragraph.add_footnote(text, char_pr_id_ref=char_pr_id_ref, offset=offset)


@refused_leaves_no_paragraph
def add_endnote(
    doc: "HwpxDocument",
    text: str,
    paragraph: HwpxOxmlParagraph | None = None,
    *,
    section: HwpxOxmlSection | None = None,
    char_pr_id_ref: str | int | None = None,
    offset: int | None = None,
) -> HwpxOxmlNote:
    """Add an endnote to an existing paragraph, or create a new one."""

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "",
            section=section,
            include_run=False,
        )
    return paragraph.add_endnote(text, char_pr_id_ref=char_pr_id_ref, offset=offset)


@refused_leaves_no_paragraph
def add_line(
    doc: "HwpxDocument",
    start_x: int = 0,
    start_y: int = 0,
    end_x: int = 14400,
    end_y: int = 0,
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
) -> HwpxOxmlShape:
    """Insert a line drawing shape.

    Coordinates are in HWPUNIT (7200 per inch).
    """
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_line(
        start_x, start_y, end_x, end_y,
        line_color=line_color, line_width_mm=line_width_mm,
        treat_as_char=treat_as_char,
    )


@refused_leaves_no_paragraph
def add_composed_character(
    doc: "HwpxDocument",
    text: str,
    char_pr_id_refs: Sequence[str | int] | None = None,
    *,
    frame: str | None = None,
    inner_size: int | None = None,
    arrangement: str | None = None,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "ComposedCharacter":
    """Insert ``hp:compose`` (글자 겹치기/원문자) inline, in *paragraph* if
    given, else a freshly-appended one -- matching :func:`add_line`'s own
    "attach here, or make a home" contract (compose/dutmal are typically
    inline within a sentence, not their own standalone paragraph like a
    drawing shape usually is). Returns the live view ``doc.shapes.composed_characters``
    reads: *frame*, *inner_size* and *arrangement* are its ``circleType``, ``charSz`` and
    ``composeType``.
    """
    from ..objects.highlight import ComposedCharacter

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    inline = paragraph.add_composed_character(
        text,
        char_pr_id_refs,
        circle_type=frame,
        char_sz=inner_size,
        compose_type=arrangement,
        char_pr_id_ref=char_pr_id_ref,
    )
    return ComposedCharacter(inline.element, paragraph)


@refused_leaves_no_paragraph
def add_ruby(
    doc: "HwpxDocument",
    text: str,
    ruby_text: str,
    *,
    position: str = "TOP",
    alignment: "Alignment | str" = "CENTER",
    size_ratio: int | None = 0,
    option: int | None = 0,
    style_id_ref: str | int | None = None,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    char_pr_id_ref: str | int | None = None,
) -> "Ruby":
    """Insert ``hp:dutmal`` (덧말) inline, in *paragraph* if given, else a
    freshly-appended one, and return the live view ``doc.shapes.rubies`` reads: *text*,
    *ruby_text*, *position*, *alignment* and *size_ratio* are its ``mainText``, ``subText``,
    ``posType``, ``align`` and ``szRatio``. See ``HwpxOxmlParagraph.add_dutmal``'s docstring
    for the low-confidence-axis disclosure (single real-corpus sample).
    """
    from ..objects.highlight import Ruby

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    inline = paragraph.add_dutmal(
        text,
        ruby_text,
        pos_type=position,
        align=str(alignment),
        sz_ratio=size_ratio,
        option=option,
        style_id_ref=style_id_ref,
        char_pr_id_ref=char_pr_id_ref,
    )
    return Ruby(inline.element, paragraph)


@refused_leaves_no_paragraph
def add_rectangle(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 7200,
    *,
    ratio: int = 0,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    original_size: tuple[int, int] | None = None,
) -> HwpxOxmlShape:
    """Insert a rectangle drawing shape.

    Dimensions are in HWPUNIT.  *ratio* controls corner roundness
    (0 = sharp, 50 = semicircle).
    """
    validate_shape_size(width, height)
    validate_rect_ratio(ratio)
    validate_original_size(original_size)
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_rectangle(
        width, height, ratio=ratio,
        line_color=line_color, line_width_mm=line_width_mm,
        fill_color=fill_color, treat_as_char=treat_as_char,
        original_size=original_size,
    )


@refused_leaves_no_paragraph
def add_ellipse(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 7200,
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    original_size: tuple[int, int] | None = None,
) -> HwpxOxmlShape:
    """Insert an ellipse drawing shape.

    Dimensions are in HWPUNIT.
    """
    validate_shape_size(width, height)
    validate_original_size(original_size)
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_ellipse(
        width, height,
        line_color=line_color, line_width_mm=line_width_mm,
        fill_color=fill_color, treat_as_char=treat_as_char,
        original_size=original_size,
    )


@refused_leaves_no_paragraph
def add_arc(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 14400,
    *,
    corner: str = "TOP_LEFT",
    arc_type: str = "NORMAL",
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
) -> HwpxOxmlShape:
    """Insert a quarter-ellipse arc drawing shape.

    Dimensions are in HWPUNIT. Only ``corner="TOP_LEFT"`` is corpus-verified
    point-for-point (real-corpus contract — see ``_create_arc_element``); the
    other three corners mirror that pattern via ``hp:flip``, the same
    mechanism every other shape here already uses. *arc_type* is the
    schema's own ``NORMAL``/``PIE``/``CHORD`` passthrough.
    """
    validate_shape_size(width, height)
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_arc(
        width, height,
        corner=corner, arc_type=arc_type,
        line_color=line_color, line_width_mm=line_width_mm,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


@refused_leaves_no_paragraph
def add_polygon(
    doc: "HwpxDocument",
    points_mm: Sequence[tuple[float, float]],
    *,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    closed: bool = True,
) -> HwpxOxmlShape:
    """Insert a polygon drawing shape.

    The polygon is closed: the first vertex is repeated at the end, as Hancom
    writes a polygon, unless *closed* is false (an open line through the
    vertices).

    *points_mm* are millimetre vertex coordinates (3 or more). Hancom stores
    a polygon's vertices in its own top-left-anchored local coordinate space
    (real-corpus contract — see ``_create_polygon_element``), so the points
    are translated to that local space here: passing page-space coordinates
    does not itself position the shape on the page, only paragraph placement
    does that.
    """
    points = list(points_mm)
    if len(points) < 3:
        raise HwpxValueError(
            "add_polygon requires at least 3 points",
            code="shape-polygon-too-few-points",
            context={"count": len(points)},
            suggestion="Pass 3 or more (x, y) millimetre vertices.",
        )
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    hwp_points = [(_mm_to_hwp_units(x), _mm_to_hwp_units(y)) for x, y in points]
    if closed:
        hwp_points = _closed_points(hwp_points)
    return paragraph.add_polygon(
        hwp_points,
        line_color=line_color, line_width_mm=line_width_mm,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


@refused_leaves_no_paragraph
def add_curve(
    doc: "HwpxDocument",
    points_mm: Sequence[tuple[float, float]],
    *,
    closed: bool = False,
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
) -> HwpxOxmlShape:
    """Insert a curve through *points_mm* (millimetre anchors, 2 or more; 3 or more when *closed*).

    Hancom draws a curve through its anchors and does not size it itself: the box written is the one its
    own curves carry (see :mod:`hwpx.oxml.curves`), and the anchors are stored in that box's own
    top-left-anchored space, so they do not place the curve on the page -- its paragraph and position do.
    """
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_curve(
        [(_mm_to_hwp_units(x), _mm_to_hwp_units(y)) for x, y in points_mm],
        closed=closed, line_color=line_color, line_width_mm=line_width_mm,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


def add_connector(
    doc: "HwpxDocument",
    start: HwpxOxmlShape,
    end: HwpxOxmlShape,
    *,
    start_side: str = "right",
    end_side: str = "left",
    kind: str = "STRAIGHT",
    line_color: str = "#000000",
    line_width_mm: float = 0.12,
    paragraph: HwpxOxmlParagraph | None = None,
) -> HwpxOxmlShape:
    """Insert a connector attached to *start* and *end* at the middle of a side of each (``top``,
    ``right``, ``bottom``, ``left``), ``STRAIGHT`` or bent (``STROKE``), in *start*'s paragraph unless
    *paragraph* is given. Hancom redraws an attached connector from the shapes' boxes, so it follows them
    when they move or grow (see :mod:`hwpx.oxml.curves`)."""
    return (paragraph or start.paragraph).add_connector(
        start, end, start_side=start_side, end_side=end_side, kind=kind,
        line_color=line_color, line_width_mm=line_width_mm,
    )


@refused_leaves_no_paragraph
def add_container(
    doc: "HwpxDocument",
    members: Sequence["ContainerMember"],
    *,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
) -> HwpxOxmlShape:
    """Insert a group (``<hp:container>``) wrapping *members*.

    Each member is built with :class:`hwpx.oxml.ContainerMember`'s
    ``rect``/``ellipse``/``polygon``/``line``/``text_box``/``picture``/``group``
    classmethods, which take the member's
    position in the group's own local coordinate space (HWPUNIT, top-left
    anchored) alongside its usual shape parameters::

        doc.shapes.add_container([
            ContainerMember.rect(0, 0, 5000, 3000, fill_color="#FFCC00"),
            ContainerMember.ellipse(6000, 0, 4000, 4000),
        ])

    The group's own size is the union bounding box of its members — see
    :func:`hwpx.oxml.objects._create_container_element` for the real-corpus
    contract (member envelope, ``groupLevel``, shared ``id`` convention).
    Grouping already-placed shapes together (rather than building the
    group from scratch) is not supported by this entry point — build the
    members through ``ContainerMember`` instead.
    """
    from ..oxml.container import bind_member_ids

    # The members get their ids from this document as it takes them, before the paragraph that holds them.
    members = bind_member_ids(members, doc._root._id_source)
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    return paragraph.add_container(members, treat_as_char=treat_as_char)


@refused_leaves_no_paragraph
def add_equation(
    doc: "HwpxDocument",
    script: str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    font_size: float = 11.0,
    char_pr_id_ref: str | int | None = None,
    font: str = "HancomEQN",
    width: int | None = None,
    height: int | None = None,
) -> HwpxOxmlEquation:
    """Insert an inline equation and prove the standard reader recognizes it.

    The emitted XML follows the real-Hancom ``<hp:equation>`` contract
    (specs/054-equation-authoring/evidence/p0/equation-contract.md). After
    insertion the equation is re-read through the standard section scan —
    creation fails loudly if the script did not land verbatim (no
    special-casing by design). *font_size* is in pt (``baseUnit`` keeps 1/100 pt); a box side
    (*width*, *height*, HWPUNIT) left out is estimated from the script at that size.
    """
    from ..equation.authoring import estimate_equation_size
    from ..equation.eqedit import MAX_SOURCE_LENGTH
    from ..oxml.namespaces import HP

    if script is not None and not isinstance(script, str):
        raise argument_type_error("script", script, "str", suggestion="Pass the EqEdit script as a str.")
    text = (script or "").strip()
    if not text:
        raise HwpxValueError(
            "equation script must be a non-empty string",
            code="shape-equation-script-empty",
            suggestion="Pass an EqEdit script (convert LaTeX with hwpx.equation).",
        )
    if len(text) > MAX_SOURCE_LENGTH:
        raise HwpxValueError(
            "equation script exceeds size limit",
            code="shape-equation-script-too-large",
            context={"length": len(text), "limit": MAX_SOURCE_LENGTH},
            suggestion="Split the equation.",
        )
    validate_equation_script(text)  # before a paragraph is added for it
    base_unit = equation_base_unit(font_size)
    font = validate_equation_font(font)
    if width is not None and height is not None:
        width, height = validate_box_size((width, height), kind="equation")
    else:
        estimated_width, estimated_height = estimate_equation_size(text, font_size=base_unit / 100)
        if width is None and height is None:
            width, height = validate_shape_size(estimated_width, estimated_height)  # one measured at a huge size too
        else:
            width, height = validate_box_size(
                (estimated_width if width is None else width, estimated_height if height is None else height),
                kind="equation",
            )
    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    inline_object = paragraph.add_equation(
        text, font_size=base_unit / 100, width=width, height=height, char_pr_id_ref=char_pr_id_ref, font=font,
    )

    created_id = inline_object.element.get("id", "")
    for owning_section in doc.sections:
        for candidate in owning_section.element.iter(f"{HP}equation"):
            if candidate.get("id") != created_id:
                continue
            script_element = candidate.find(f"{HP}script")
            if script_element is None or (script_element.text or "") != text:
                raise HwpxStateError(
                    "created equation did not store its script verbatim",
                    code="shape-equation-not-verbatim",
                    suggestion="Check the script for characters XML cannot represent.",
                )
            return inline_object
    raise HwpxStateError(
        "created equation was not recognized by the standard section scan",
        code="shape-equation-not-created",
        suggestion="Check that this document has a standard section structure.",
    )


def equations(doc: "HwpxDocument") -> tuple[HwpxOxmlEquation, ...]:
    """Every equation in the body, in document order: in table cells, text boxes, notes, headers and
    footers too."""

    from ..oxml.namespaces import HP
    from .media import _enclosing_paragraph

    found: list[HwpxOxmlEquation] = []
    for section in doc._root.sections:
        for element in section.element.iter(f"{HP}equation"):
            paragraph = _enclosing_paragraph(element, section)
            if paragraph is not None:
                found.append(HwpxOxmlEquation(element, paragraph))
    return tuple(found)


_CHART_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
_CHART_AXES = tuple(f"{_CHART_NS}{name}" for name in ("catAx", "valAx", "dateAx", "serAx"))


#: Chart kinds drawn against axes: ECMA-376 gives each two (or three)
#: ``c:axId`` children naming axes defined in ``c:plotArea``. Pie, doughnut and
#: of-pie charts have none.
_AXIS_CHART_KINDS = tuple(
    f"{_CHART_NS}{name}"
    for name in (
        "barChart", "bar3DChart", "lineChart", "line3DChart", "areaChart", "area3DChart",
        "scatterChart", "radarChart", "bubbleChart", "stockChart", "surfaceChart", "surface3DChart",
    )
)


def _check_chart_axes(root: Any) -> None:
    """Reject a chart kind that needs axes when its two axes are missing.

    Without them Hancom draws a bar chart with no bars and crashes on the
    other kinds, rendering the page or saving the document; the same charts
    render once their axes are added. An axis id of 0 stands for "no axis"
    (a 3-D chart without a series axis) and is not checked.
    """

    defined = {
        ax_id.get("val")
        for axis in root.iter(*_CHART_AXES)
        for ax_id in axis.findall(f"{_CHART_NS}axId")
    }
    for chart in root.iter(*_AXIS_CHART_KINDS):
        kind = str(chart.tag).rsplit("}", 1)[-1]
        ax_ids = [ax_id.get("val") for ax_id in chart.findall(f"{_CHART_NS}axId")]
        named = [value for value in ax_ids if value != "0"]
        if len(named) < 2 or any(value not in defined for value in named):
            raise HwpxValueError(
                f"chart_xml has a c:{kind} without its axes; Hancom draws it empty or crashes on it",
                code="shape-chart-axes-missing",
                context={"chartKind": kind, "axIds": ax_ids,
                         "definedAxes": sorted(value for value in defined if value)},
                suggestion=(
                    f"Give c:{kind} two <c:axId val=...> children and define the axes they name in "
                    "c:plotArea (a c:catAx and a c:valAx; two c:valAx for scatter and bubble charts), "
                    "each naming the other in c:crossAx."
                ),
            )


#: The chart size (``hp:sz``) of the gold document ``HwpxOxmlParagraph.add_chart``
#: defaults to.
_DEFAULT_CHART_SIZE = (32250, 18750)


def _default_chart_size(paragraph: HwpxOxmlParagraph) -> tuple[int, int]:
    """The default chart size, scaled down to fit where the chart goes.

    Hancom clips an object at the edge of its table cell, so a default chart
    wider than the cell's usable width (or the text body) is narrowed, keeping
    its shape, as the default width of a nested table is.
    """
    width, height = _DEFAULT_CHART_SIZE
    usable = paragraph._context_table_width()
    if usable is not None and usable < width:
        return usable, round(height * usable / width)
    return width, height


@refused_leaves_no_paragraph
def add_chart(
    doc: "HwpxDocument",
    chart_xml: bytes | str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    treat_as_char: bool = False,
    char_pr_id_ref: str | int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> HwpxOxmlInlineObject:
    """Add a chartML part and its ``<hp:chart>`` anchor, then prove recognition.

    The part is stored under ``Chart/chartN.xml`` and addressed directly by
    the anchor's ``chartIDRef`` — real Hancom registers chart parts in no
    manifest and draws the chart from the ECMA-376 chartML alone
    (specs/055-chart-authoring/evidence/p0/chart-contract.md). The chartML is
    validated to parse and to carry the ``c:chartSpace`` root before any part
    is written; after insertion the anchor is re-read through the standard
    section scan — creation fails loudly if it did not land (no
    special-casing by design).

    Without *width* and *height* the chart takes the gold document's 32250x18750, scaled
    down (keeping its shape) to the usable width of the table cell or text
    body it goes into; Hancom clips an object at its cell's edge. One of the two given,
    the other is the gold document's.
    """
    from lxml import etree as _etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

    from ..oxml.namespaces import HP

    _CHART_SPACE = "{http://schemas.openxmlformats.org/drawingml/2006/chart}chartSpace"

    if not isinstance(chart_xml, (str, bytes, bytearray, memoryview)):
        raise argument_type_error(
            "chart_xml", chart_xml, "bytes or str",
            suggestion="Pass the ECMA-376 c:chartSpace document as bytes or a str.",
        )
    size: tuple[int, int] | None = None
    if width is not None or height is not None:
        size = validate_box_size(  # before the chart part is written
            (_DEFAULT_CHART_SIZE[0] if width is None else width, _DEFAULT_CHART_SIZE[1] if height is None else height),
            kind="chart",
        )
    data = chart_xml.encode("utf-8") if isinstance(chart_xml, str) else bytes(chart_xml)
    if not data.strip():
        raise HwpxValueError(
            "chart_xml must be non-empty chartML",
            code="shape-chart-xml-empty",
            suggestion="Pass an ECMA-376 c:chartSpace document.",
        )
    try:
        root = _etree.fromstring(data)
    except _etree.XMLSyntaxError as exc:
        raise HwpxValueError(
            f"chart_xml is not well-formed XML: {exc}",
            code="shape-chart-xml-malformed",
            suggestion="Check that it parses as XML first.",
        ) from exc
    if root.tag != _CHART_SPACE:
        raise HwpxValueError(
            f"chart_xml root must be the ECMA-376 c:chartSpace element, got {root.tag!r}",
            code="shape-chart-root-invalid",
            context={"root": str(root.tag)},
            suggestion="Pass the c:chartSpace document, not the whole chart part.",
        )
    _check_chart_axes(root)

    existing = {name for name in doc._package.part_names() if name.startswith("Chart/")}
    n = 1
    while f"Chart/chart{n}.xml" in existing:
        n += 1
    part_path = f"Chart/chart{n}.xml"

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section,
            include_run=False,
        )
    doc._package.write(part_path, data)
    width, height = size if size is not None else _default_chart_size(paragraph)
    inline_object = paragraph.add_chart(
        part_path,
        width=width,
        height=height,
        treat_as_char=treat_as_char,
        char_pr_id_ref=char_pr_id_ref,
    )

    created_id = inline_object.element.get("id", "")
    for owning_section in doc.sections:
        for candidate in owning_section.element.iter(f"{HP}chart"):
            if candidate.get("id") != created_id:
                continue
            if candidate.get("chartIDRef") != part_path:
                raise HwpxStateError(
                    "created chart anchor does not reference its part",
                    code="shape-chart-anchor-detached",
                    suggestion="Reopen the document and check the manifest.",
                )
            return inline_object
    raise HwpxStateError(
        "created chart was not recognized by the standard section scan",
        code="shape-chart-not-created",
        suggestion="Check that this document has a standard section structure.",
    )


def remove_unused_charts(doc: "HwpxDocument") -> tuple[str, ...]:
    """Remove every chart part (``Chart/...``) no chart points at and return
    the removed part names.

    Hancom drops such parts when it saves a document; a chart removed from the
    body (``section.clear_body()``, a deleted paragraph) leaves its part, with
    the chart's data, behind. A part is kept while a ``hp:chart`` anywhere in
    the document (sections, master pages, header, histories) names its file.
    """
    from pathlib import PurePosixPath

    from ..oxml.namespaces import HP
    from ..opc.relationships import normalize_part_name

    root = doc._root
    used = {
        PurePosixPath(normalize_part_name(anchor.get("chartIDRef", ""))).name
        for part in (*root.headers, *root.sections, *root.master_pages, *root.histories)
        for anchor in part.element.iter(f"{HP}chart")
    }
    removed: list[str] = []
    for part_name in doc._package.part_names():
        if part_name.startswith("Chart/") and PurePosixPath(part_name).name not in used:
            doc._package.remove_manifest_item(part_name)
            doc._package.delete(part_name)
            removed.append(part_name)
    return tuple(removed)


@refused_leaves_no_paragraph
def add_drop_cap(
    doc: "HwpxDocument",
    character: str,
    *,
    width: int,
    height: int,
    kind: str = "TripleLine",
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    char_pr_id_ref: str | int | None = None,
    para_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a drop cap (문단 첫 글자 장식), inferred from the one
    real-corpus example that carries a non-default ``dropcapstyle``
    (``error__20230809__test.hwpx`` -- see ``oxml.drop_cap``'s own
    docstring for the full structural format inference and why it
    supports ``kind="TripleLine"`` and ``"DoubleLine"`` only).

    Element construction (element-building validation included) happens in
    :func:`hwpx.oxml.drop_cap.create_drop_cap_element`; after insertion the
    anchor is re-read through the standard section scan, matching
    :func:`add_chart`'s own "creation fails loudly if it did not land"
    self-check.
    """

    from ..oxml.namespaces import HP

    if paragraph is None:
        paragraph = home_paragraph(
            doc, "", section=section, include_run=False,
        )
    inline_object = paragraph.add_drop_cap(
        character,
        width=width, height=height, style=kind,
        char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
    )

    created_id = inline_object.element.get("id", "")
    for owning_section in doc.sections:
        for candidate in owning_section.element.iter(f"{HP}rect"):
            if candidate.get("id") != created_id:
                continue
            if candidate.get("dropcapstyle") != kind:
                raise HwpxStateError(
                    "created drop cap does not carry the requested dropcapstyle",
                    code="shape-drop-cap-anchor-detached",
                    suggestion="Reopen the document and check the section structure.",
                )
            return inline_object
    raise HwpxStateError(
        "created drop cap was not recognized by the standard section scan",
        code="shape-drop-cap-not-created",
        suggestion="Check that this document has a standard section structure.",
    )
