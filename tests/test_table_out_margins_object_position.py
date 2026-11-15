# SPDX-License-Identifier: Apache-2.0
"""``table.set_out_margins`` and ``set_position`` on inline objects (7.0 additions).

Exam papers edited ``hp:outMargin`` and an equation's ``hp:pos``/``textWrap`` in the XML by hand.
"""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects.results import CellMargins

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_set_out_margins_writes_the_table_outer_margin() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    before = table.out_margins
    result = table.set_out_margins(top=1417, bottom=1417)
    assert result == CellMargins(before.left, before.right, 1417, 1417)
    own = table.element.find(f"{HP}outMargin")
    assert (own.get("top"), own.get("bottom")) == ("1417", "1417")
    assert table.out_margins == result
    assert table.set_out_margins() == result  # nothing given: nothing changes


@pytest.mark.parametrize("value", [-1, 1.5, True, 2**31])
def test_set_out_margins_refuses_bad_values_before_changing(value) -> None:
    table = HwpxDocument.new().add_table(1, 1)
    before = table.out_margins
    with pytest.raises(HwpxValueError) as excinfo:
        table.set_out_margins(left=value)
    assert excinfo.value.code == "table-margin-value"
    assert table.out_margins == before


def _equation(doc: HwpxDocument):
    paragraph = doc.add_paragraph("식: ")
    return doc.shapes.add_equation("a over b", paragraph=paragraph)


def test_an_equation_floats_with_text_above_and_below() -> None:
    doc = HwpxDocument.new()
    equation = _equation(doc)
    equation.set_position(
        treat_as_char=False, text_wrap="TOP_AND_BOTTOM", horizontal_offset=5669, vertical_offset=-100,
        horz_rel_to="PARA", vert_rel_to="PARA",
    )
    pos = equation.element.find(f"{HP}pos")
    assert pos.get("treatAsChar") == "0"
    assert equation.element.get("textWrap") == "TOP_AND_BOTTOM"
    assert pos.get("horzOffset") == "5669"
    assert pos.get("vertOffset") == str(-100 & 0xFFFFFFFF)
    assert equation.paragraph.element.find(f"{HP}linesegarray") is None


def test_back_to_a_character() -> None:
    doc = HwpxDocument.new()
    equation = _equation(doc)
    equation.set_position(treat_as_char=False)
    equation.set_position(treat_as_char=True)
    assert equation.element.find(f"{HP}pos").get("treatAsChar") == "1"


def test_offsets_on_a_character_object_are_refused() -> None:
    doc = HwpxDocument.new()
    equation = _equation(doc)
    with pytest.raises(HwpxValueError) as excinfo:
        equation.set_position(horizontal_offset=100)
    assert excinfo.value.code == "shape-position-unsupported"


def test_an_unknown_wrap_is_refused_before_anything_changes() -> None:
    doc = HwpxDocument.new()
    equation = _equation(doc)
    before = dict(equation.element.find(f"{HP}pos").attrib)
    with pytest.raises(HwpxValueError) as excinfo:
        equation.set_position(treat_as_char=False, text_wrap="AROUND")
    assert excinfo.value.code == "shape-position-frame"
    assert dict(equation.element.find(f"{HP}pos").attrib) == before


def test_a_picture_takes_the_same_call() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(b"\x89PNG\r\n\x1a\n" + b"0" * 40, "png", width=7200, height=7200)
    picture.set_position(treat_as_char=False, text_wrap="IN_FRONT_OF_TEXT", horz_rel_to="PAGE",
                         horz_align="RIGHT", horizontal_offset=0)
    assert picture.element.get("textWrap") == "IN_FRONT_OF_TEXT"
    assert picture.element.find(f"{HP}pos").get("horzAlign") == "RIGHT"
