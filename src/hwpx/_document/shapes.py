# SPDX-License-Identifier: Apache-2.0
"""Shape/control/note domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence, cast

from ._units import _mm_to_hwp_units
from ..errors import HwpxStateError, HwpxValueError

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import (
        ContainerMember,
        HwpxOxmlInlineObject,
        HwpxOxmlNote,
        HwpxOxmlParagraph,
        HwpxOxmlSection,
        HwpxOxmlShape,
    )


def add_shape(
    doc: "HwpxDocument",
    shape_type: str,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    attributes: dict[str, str] | None = None,
    para_pr_id_ref: str | int | None = None,
    style_id_ref: str | int | None = None,
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

    paragraph = doc.add_paragraph(
        "",
        section=section,
        section_index=section_index,
        para_pr_id_ref=para_pr_id_ref,
        style_id_ref=style_id_ref,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
        **cast(Any, extra_attrs),
    )
    return paragraph.add_shape(
        shape_type,
        attributes=attributes,
        run_attributes=run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )


def add_control(
    doc: "HwpxDocument",
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    attributes: dict[str, str] | None = None,
    control_type: str | None = None,
    para_pr_id_ref: str | int | None = None,
    style_id_ref: str | int | None = None,
    char_pr_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
    **extra_attrs: str,
) -> HwpxOxmlInlineObject:
    """Insert a control inline object into a new paragraph.

    Low-level escape hatch — an ``<hp:ctrl>`` means nothing without the child
    element that carries the control, and Hancom refuses to open a document
    containing an empty one, so this warns until a child is appended.
    """

    paragraph = doc.add_paragraph(
        "",
        section=section,
        section_index=section_index,
        para_pr_id_ref=para_pr_id_ref,
        style_id_ref=style_id_ref,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
        **cast(Any, extra_attrs),
    )
    return paragraph.add_control(
        attributes=attributes,
        control_type=control_type,
        run_attributes=run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )


def add_footnote(
    doc: "HwpxDocument",
    text: str,
    paragraph: HwpxOxmlParagraph | None = None,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlNote:
    """Add a footnote to an existing paragraph, or create a new one.

    When *paragraph* is ``None`` a new paragraph is appended to the given
    (or last) section.
    """

    if paragraph is None:
        paragraph = doc.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            include_run=False,
        )
    return paragraph.add_footnote(text, char_pr_id_ref=char_pr_id_ref)


def add_endnote(
    doc: "HwpxDocument",
    text: str,
    paragraph: HwpxOxmlParagraph | None = None,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlNote:
    """Add an endnote to an existing paragraph, or create a new one."""

    if paragraph is None:
        paragraph = doc.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            include_run=False,
        )
    return paragraph.add_endnote(text, char_pr_id_ref=char_pr_id_ref)


def add_line(
    doc: "HwpxDocument",
    start_x: int = 0,
    start_y: int = 0,
    end_x: int = 14400,
    end_y: int = 0,
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert a line drawing shape.

    Coordinates are in HWPUNIT (7200 per inch).
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_line(
        start_x, start_y, end_x, end_y,
        line_color=line_color, line_width=line_width,
        treat_as_char=treat_as_char,
    )


def add_composed_character(
    doc: "HwpxDocument",
    compose_text: str,
    char_pr_id_refs: Sequence[str | int] | None = None,
    *,
    circle_type: str | None = None,
    char_sz: int | None = None,
    compose_type: str | None = None,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert ``hp:compose`` (글자 겹치기/원문자) inline, in *paragraph* if
    given, else a freshly-appended one -- matching :func:`add_line`'s own
    "attach here, or make a home" contract (compose/dutmal are typically
    inline within a sentence, not their own standalone paragraph like a
    drawing shape usually is).
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_composed_character(
        compose_text,
        char_pr_id_refs,
        circle_type=circle_type,
        char_sz=char_sz,
        compose_type=compose_type,
        char_pr_id_ref=char_pr_id_ref,
    )


def add_dutmal(
    doc: "HwpxDocument",
    main_text: str,
    sub_text: str,
    *,
    pos_type: str = "TOP",
    align: str = "CENTER",
    sz_ratio: int | None = 0,
    option: int | None = 0,
    style_id_ref: str | int | None = None,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert ``hp:dutmal`` (덧말) inline, in *paragraph* if given, else a
    freshly-appended one. See ``HwpxOxmlParagraph.add_dutmal``'s docstring
    for the low-confidence-axis disclosure (single real-corpus sample).
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_dutmal(
        main_text,
        sub_text,
        pos_type=pos_type,
        align=align,
        sz_ratio=sz_ratio,
        option=option,
        style_id_ref=style_id_ref,
        char_pr_id_ref=char_pr_id_ref,
    )


def add_rectangle(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 7200,
    *,
    ratio: int = 0,
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert a rectangle drawing shape.

    Dimensions are in HWPUNIT.  *ratio* controls corner roundness
    (0 = sharp, 50 = semicircle).
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_rectangle(
        width, height, ratio=ratio,
        line_color=line_color, line_width=line_width,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


def add_ellipse(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 7200,
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert an ellipse drawing shape.

    Dimensions are in HWPUNIT.
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_ellipse(
        width, height,
        line_color=line_color, line_width=line_width,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


def add_arc(
    doc: "HwpxDocument",
    width: int = 14400,
    height: int = 14400,
    *,
    corner: str = "TOP_LEFT",
    arc_type: str = "NORMAL",
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert a quarter-ellipse arc drawing shape.

    Dimensions are in HWPUNIT. Only ``corner="TOP_LEFT"`` is corpus-verified
    point-for-point (real-corpus contract — see ``_create_arc_element``); the
    other three corners mirror that pattern via ``hp:flip``, the same
    mechanism every other shape here already uses. *arc_type* is the
    schema's own ``NORMAL``/``PIE``/``CHORD`` passthrough.
    """
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_arc(
        width, height,
        corner=corner, arc_type=arc_type,
        line_color=line_color, line_width=line_width,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


def add_polygon(
    doc: "HwpxDocument",
    points_mm: Sequence[tuple[float, float]],
    *,
    line_color: str = "#000000",
    line_width: str = "283",
    fill_color: str | None = None,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert a polygon drawing shape.

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
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    hwp_points = [(_mm_to_hwp_units(x), _mm_to_hwp_units(y)) for x, y in points]
    return paragraph.add_polygon(
        hwp_points,
        line_color=line_color, line_width=line_width,
        fill_color=fill_color, treat_as_char=treat_as_char,
    )


def add_container(
    doc: "HwpxDocument",
    members: Sequence["ContainerMember"],
    *,
    treat_as_char: bool = True,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
) -> HwpxOxmlShape:
    """Insert a group (``<hp:container>``) wrapping *members*.

    Each member is built with :class:`hwpx.oxml.ContainerMember`'s
    ``rect``/``ellipse``/``polygon`` classmethods, which take the member's
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
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    return paragraph.add_container(members, treat_as_char=treat_as_char)


def add_equation(
    doc: "HwpxDocument",
    script: str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    base_unit: int = 1100,
    size: tuple[int, int] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert an inline equation and prove the standard reader recognizes it.

    The emitted XML follows the real-Hancom ``<hp:equation>`` contract
    (specs/054-equation-authoring/evidence/p0/equation-contract.md). After
    insertion the equation is re-read through the standard section scan —
    creation fails loudly if the script did not land verbatim (no
    special-casing by design).
    """
    from ..equation.authoring import estimate_equation_size
    from ..equation.eqedit import MAX_SOURCE_LENGTH
    from ..oxml.namespaces import HP

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
    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    if size is None:
        size = estimate_equation_size(text, base_unit=base_unit)
    inline_object = paragraph.add_equation(
        text, base_unit=base_unit, size=size, char_pr_id_ref=char_pr_id_ref,
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


def add_chart(
    doc: "HwpxDocument",
    chart_xml: bytes | str,
    *,
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    size: tuple[int, int] | None = None,
    treat_as_char: bool = False,
    char_pr_id_ref: str | int | None = None,
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
    """
    from lxml import etree as _etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

    from ..oxml.namespaces import HP

    _CHART_SPACE = "{http://schemas.openxmlformats.org/drawingml/2006/chart}chartSpace"

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

    existing = {name for name in doc._package.part_names() if name.startswith("Chart/")}
    n = 1
    while f"Chart/chart{n}.xml" in existing:
        n += 1
    part_path = f"Chart/chart{n}.xml"

    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index,
            include_run=False,
        )
    doc._package.write(part_path, data)
    inline_object = paragraph.add_chart(
        part_path,
        size=size,
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


def add_drop_cap(
    doc: "HwpxDocument",
    character: str,
    *,
    width: int,
    height: int,
    style: str = "TripleLine",
    paragraph: HwpxOxmlParagraph | None = None,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    char_pr_id_ref: str | int | None = None,
    para_pr_id_ref: str | int | None = None,
) -> HwpxOxmlInlineObject:
    """Insert a drop cap (문단 첫 글자 장식), reverse-engineered from the one
    real-corpus example that carries a non-default ``dropcapstyle``
    (``error__20230809__test.hwpx`` -- see ``oxml.drop_cap``'s own
    docstring for the full structural reverse engineering and why v1
    supports only ``style="TripleLine"``).

    Element construction (element-building validation included) happens in
    :func:`hwpx.oxml.drop_cap.create_drop_cap_element`; after insertion the
    anchor is re-read through the standard section scan, matching
    :func:`add_chart`'s own "creation fails loudly if it did not land"
    self-check.
    """

    from ..oxml.namespaces import HP

    if paragraph is None:
        paragraph = doc.add_paragraph(
            "", section=section, section_index=section_index, include_run=False,
        )
    inline_object = paragraph.add_drop_cap(
        character,
        width=width, height=height, style=style,
        char_pr_id_ref=char_pr_id_ref, para_pr_id_ref=para_pr_id_ref,
    )

    created_id = inline_object.element.get("id", "")
    for owning_section in doc.sections:
        for candidate in owning_section.element.iter(f"{HP}rect"):
            if candidate.get("id") != created_id:
                continue
            if candidate.get("dropcapstyle") != style:
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
