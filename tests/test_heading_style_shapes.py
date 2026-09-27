# SPDX-License-Identifier: Apache-2.0
"""A heading starts from its outline style's paragraph and character shapes.

Hancom draws a paragraph by the shapes the paragraph itself points at, not by
its style, so a heading that only names the style looks like body text apart
from the outline number.
"""
from __future__ import annotations

from hwpx.document import HwpxDocument


HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _margins(document: HwpxDocument, para_pr_id: object) -> tuple[object, ...]:
    """Tab definition, condensing and every margin value of a paragraph shape."""
    element = next(
        el for el in document.oxml.headers[0].element.iter(f"{HH}paraPr") if el.get("id") == str(para_pr_id)
    )
    margins = tuple(
        (child.tag, child.get("value")) for margin in element.iter(f"{HH}margin") for child in margin
    )
    return element.get("tabPrIDRef"), element.get("condense"), margins


def test_a_heading_takes_the_indent_and_spacing_of_its_style() -> None:
    document = HwpxDocument.new()
    style = document.styles.resolve("개요 2")

    heading = document.add_heading("가. 추진 배경", level=2)

    assert heading.style_id_ref is not None and str(heading.style_id_ref) == str(style.id)
    assert _margins(document, heading.para_pr_id_ref) == _margins(document, style.para_pr_id_ref)


def test_a_heading_takes_the_character_shape_of_its_style_unless_one_is_given() -> None:
    document = HwpxDocument.new()
    style = document.styles.resolve("개요 1")
    big = document.styles.ensure_run(size=16)

    plain = document.add_heading("첫 제목", level=1)
    sized = document.add_heading("둘째 제목", level=1, char_pr_id_ref=big)

    assert plain.runs[0].char_pr_id_ref == str(style.char_pr_id_ref)
    assert sized.runs[0].char_pr_id_ref == str(big)


def test_a_heading_after_body_text_does_not_take_the_body_shapes() -> None:
    document = HwpxDocument.new()
    body_shape = document.styles.ensure_run(size=9, color="#555555")
    document.add_paragraph("본문", char_pr_id_ref=body_shape)
    style = document.styles.resolve("개요 1")

    heading = document.add_heading("제목", level=1)

    assert heading.runs[0].char_pr_id_ref == str(style.char_pr_id_ref)
    assert _margins(document, heading.para_pr_id_ref) == _margins(document, style.para_pr_id_ref)
