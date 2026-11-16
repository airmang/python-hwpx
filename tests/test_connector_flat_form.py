# SPDX-License-Identifier: Apache-2.0
"""Horizontal and vertical connectors written in the form Hancom gives a flat drawing object.

A connector whose ``orgSz`` has a 0 side Hancom 2024 draws nowhere: redrawing it from its shapes it divides by
that side and saves ``scaMatrix`` e4-e6 as ``-nan(ind)`` (objlim evidence keepsrc, grpconn). Hancom's own flat
lines keep their geometry in a 100 x 100 box and flatten it with ``scaMatrix`` (five in the public documents,
e.g. ``issue1858_paper_anchor_float_stack.hwpx``: orgSz 100x100, endPt (100, 100), scale 566.919983 and 0).
"""

from __future__ import annotations

import io

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.package_validator import validate_package

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _pair(doc, second_x, second_y):
    p = doc.add_paragraph("")
    a = p.add_rectangle(5000, 4000, treat_as_char=False)
    b = p.add_rectangle(5000, 4000, treat_as_char=False)
    b.set_position(horizontal_offset=second_x, vertical_offset=second_y)
    return p, a, b


def _form(connector):
    element = connector.element

    def box(tag):
        child = element.find(f"{HP}{tag}")
        return child.get("width"), child.get("height")

    scale = element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    turn = element.find(f"{HP}rotationInfo")
    ends = [(element.find(f"{HP}{tag}").get("x"), element.find(f"{HP}{tag}").get("y")) for tag in ("startPt", "endPt")]
    return {"orgSz": box("orgSz"), "curSz": box("curSz"), "sz": box("sz"),
            "scale": (scale.get("e1"), scale.get("e2"), scale.get("e4"), scale.get("e5")),
            "centre": (turn.get("centerX"), turn.get("centerY")), "ends": ends}


def test_a_horizontal_connector_keeps_a_100_box_flattened_by_its_scale() -> None:
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 14000, 0)  # right side of a (5000, 2000) to left side of b (14000, 2000)

    connector = p.add_connector(a, b)

    assert _form(connector) == {
        "orgSz": ("100", "100"), "curSz": ("9000", "0"), "sz": ("9000", "0"),
        "scale": ("90", "0", "0", "0"), "centre": ("4500", "0"), "ends": [("0", "0"), ("100", "100")],
    }
    again = HwpxDocument.open(io.BytesIO(doc.to_bytes()))
    again.validate()
    assert not [i for i in validate_package(doc.to_bytes()).issues if "connectLine" in i.message]


def test_a_vertical_connector_is_flattened_across() -> None:
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 0, 12000)  # bottom of a (2500, 4000) to top of b (2500, 12000)

    connector = p.add_connector(a, b, start_side="bottom", end_side="top")

    form = _form(connector)
    assert form["orgSz"] == ("100", "100") and form["sz"] == ("0", "8000") and form["curSz"] == ("0", "8000")
    assert form["scale"] == ("0", "0", "0", "80") and form["centre"] == ("0", "4000")
    assert form["ends"] == [("0", "0"), ("100", "100")]


def test_a_right_to_left_connector_keeps_its_direction_along_its_length() -> None:
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 14000, 0)

    connector = p.add_connector(b, a, start_side="left", end_side="right")

    assert _form(connector)["ends"] == [("100", "0"), ("0", "100")]


def test_a_diagonal_connector_keeps_its_own_box_as_hancom_saves_one() -> None:
    # Hancom's own connectors (tests/fixtures/hancom_saved/shape_curves_and_connectors.hwpx): orgSz = sz,
    # the scale plain, the ends in that box.
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 14000, 8000)

    connector = p.add_connector(a, b)

    form = _form(connector)
    assert form["orgSz"] == form["sz"] == ("9000", "8000")
    assert form["scale"] == ("1", "0", "0", "1")
    assert form["ends"] == [("0", "0"), ("9000", "8000")]


def test_a_connector_with_its_ends_at_one_point_is_refused() -> None:
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 5000, 0)  # right side of a meets left side of b
    with pytest.raises(HwpxValueError) as excinfo:
        p.add_connector(a, b)
    assert excinfo.value.code == "shape-connector-length-zero"


def test_validation_warns_about_a_connector_with_a_zero_side_without_blocking() -> None:
    doc = HwpxDocument.new()
    p, a, b = _pair(doc, 14000, 0)
    connector = p.add_connector(a, b)
    original = connector.element.find(f"{HP}orgSz")
    original.set("width", "9000")
    original.set("height", "0")  # as python-hwpx before 7.0 wrote it

    issues = [i for i in validate_package(doc.to_bytes()).issues if "connectLine" in i.message]

    assert len(issues) == 1 and not issues[0].is_error
    HwpxDocument.open(io.BytesIO(doc.to_bytes()))  # still reads and saves
