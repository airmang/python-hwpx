# SPDX-License-Identifier: Apache-2.0
"""In a multi-column section a new table (and chart) defaults to the column's width (7.0 fix).

The default was the whole text width: in a two-column document Hancom drew the table across both
columns, over the text of the other one.
"""
from __future__ import annotations

import warnings

from hwpx import HwpxDocument
from hwpx._document.shapes import _DEFAULT_CHART_SIZE, _default_chart_size

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _width(table) -> int:
    return int(table.element.find(f"{HP}sz").get("width"))


def _text_width(doc: HwpxDocument) -> int:
    props = doc.sections[0].properties
    margins = props.page_margins
    return props.page_size.drawn_width - margins.left - margins.right - margins.gutter


def test_a_table_in_two_columns_is_one_column_wide() -> None:
    doc = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc.page.setup(columns=2, column_gap_mm=8)
    gap = int(doc.sections[0].element.find(f".//{HP}colPr").get("sameGap"))
    doc.add_paragraph("본문")
    table = doc.add_table(2, 3)
    assert _width(table) == (_text_width(doc) - gap) // 2


def test_three_columns_give_a_third() -> None:
    doc = HwpxDocument.new()
    doc.page.set_columns(3, same_gap=1134)
    table = doc.add_table(1, 2)
    assert _width(table) == (_text_width(doc) - 2 * 1134) // 3


def test_one_column_keeps_the_text_width() -> None:
    doc = HwpxDocument.new()
    assert _width(doc.add_table(1, 1)) == _text_width(doc)


def test_a_chart_in_two_columns_fits_the_column() -> None:
    doc = HwpxDocument.new()
    doc.page.set_columns(2, same_gap=1134)
    paragraph = doc.add_paragraph("차트 자리")
    column = (_text_width(doc) - 1134) // 2
    width, height = _default_chart_size(paragraph)
    assert width == min(column, _DEFAULT_CHART_SIZE[0])
    assert width < _DEFAULT_CHART_SIZE[0]
    assert height == round(_DEFAULT_CHART_SIZE[1] * width / _DEFAULT_CHART_SIZE[0])


def test_unequal_columns_give_the_narrowest() -> None:
    doc = HwpxDocument.new()
    doc.page.set_columns(2, same_size=False, column_widths=[(1, 0), (3, 0)])
    table = doc.add_table(1, 1)
    assert _width(table) == _text_width(doc) // 4
