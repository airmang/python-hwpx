# SPDX-License-Identifier: Apache-2.0
"""Shape/control/note domain owner behind the HwpxDocument facade (S-084)."""

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
    """Insert an inline shape into a new paragraph."""

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
    """Insert a control inline object into a new paragraph."""

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
