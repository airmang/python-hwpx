# SPDX-License-Identifier: Apache-2.0
"""Shape/control/note domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import (
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
        raise ValueError("equation script must be a non-empty string")
    if len(text) > MAX_SOURCE_LENGTH:
        raise ValueError("equation script exceeds size limit")
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
                raise RuntimeError(
                    "created equation did not store its script verbatim"
                )
            return inline_object
    raise RuntimeError(
        "created equation was not recognized by the standard section scan"
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
        raise ValueError("chart_xml must be non-empty chartML")
    try:
        root = _etree.fromstring(data)
    except _etree.XMLSyntaxError as exc:
        raise ValueError(f"chart_xml is not well-formed XML: {exc}") from exc
    if root.tag != _CHART_SPACE:
        raise ValueError(
            "chart_xml root must be the ECMA-376 c:chartSpace element, "
            f"got {root.tag!r}"
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
                raise RuntimeError(
                    "created chart anchor does not reference its part"
                )
            return inline_object
    raise RuntimeError(
        "created chart was not recognized by the standard section scan"
    )
