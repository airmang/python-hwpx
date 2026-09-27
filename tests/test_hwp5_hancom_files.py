# SPDX-License-Identifier: Apache-2.0
"""HWP 5.0 files that Hancom saved (author, version and dates removed): they
open with the values Hancom wrote and save back to the same records."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import records as rec
from hwpx.hwp5.package import convert
from hwpx.hwp5.reader import read_hwp5
from hwpx.hwp5.writer import write_hwp5

FIXTURES = Path(__file__).parent / "fixtures" / "hwp5"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def _objects(data: bytes) -> list[ct.ObjectCommon]:
    doc = read_hwp5(data)
    return [
        ct.ObjectCommon.decode(r.payload)
        for s in doc.sections
        for r in s.records
        if r.tag == rec.CTRL_HEADER and r.payload[:4] == b" osg"
    ]


@pytest.mark.parametrize(
    "name",
    [
        "shadow_pers_leftbottom_28346x42520.hwp",  # past 16 bits
        "shadow_shear_righttop_offset_left.hwp",  # moved to the left
        "shadow_pers_leftbottom_8000x1000.hwp",  # a lean that rounds up
    ],
)
def test_a_shadowed_shape_opens_with_its_own_margin_and_saves_back(name: str) -> None:
    data = (FIXTURES / name).read_bytes()
    files = convert(data).files
    [shape] = list(etree.fromstring(files["Contents/section0.xml"]).iter(f"{HP}rect"))
    margin = shape.find(f"{HP}outMargin")
    assert margin is not None
    assert [margin.get(side) for side in ("left", "right", "top", "bottom")] == ["0", "0", "0", "0"]
    assert [o.margins for o in _objects(write_hwp5(files))] == [o.margins for o in _objects(data)]


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("border_doublewave.hwp", "DOUBLEWAVE"),
        ("border_thick3d.hwp", "THICK3D"),
        ("border_thickrev3d.hwp", "THICKREV3D"),
        ("border_3d.hwp", "3D"),
        ("border_rev3d.hwp", "REV3D"),
    ],
)
def test_a_border_line_opens_with_hancoms_name_and_saves_back(name: str, line: str) -> None:
    data = (FIXTURES / name).read_bytes()
    files = convert(data).files
    head = etree.fromstring(files["Contents/header.xml"])
    kinds = {side.get("type") for fill in head.iter(f"{HH}borderFill") for side in fill if etree.QName(side).localname in SIDES}
    assert line in kinds
    theirs = [r.payload for r in read_hwp5(data).docinfo.records if r.tag == rec.BORDER_FILL]
    ours = [r.payload for r in read_hwp5(write_hwp5(files)).docinfo.records if r.tag == rec.BORDER_FILL]
    assert ours == theirs


def test_an_object_with_no_width_basis_is_saved_as_hancom_saves_it() -> None:
    """Hancom saved this rectangle, which had no widthRelTo, as sized against the page."""

    data = (FIXTURES / "rect_no_width_rel_to.hwp").read_bytes()
    files = convert(data).files
    root = etree.fromstring(files["Contents/section0.xml"])
    [rect] = list(root.iter(f"{HP}rect"))
    size = rect.find(f"{HP}sz")
    assert size is not None and size.get("widthRelTo") == "PAGE"
    del size.attrib["widthRelTo"]
    files["Contents/section0.xml"] = etree.tostring(root)
    assert [o.props for o in _objects(write_hwp5(files))] == [o.props for o in _objects(data)]
