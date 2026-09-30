# SPDX-License-Identifier: Apache-2.0
"""Curves and connectors written the way Hancom reads them (``doc.shapes.add_curve`` / ``add_connector``).

A curve's box is the one Hancom gives its own curves: the Catmull-Rom curve through the anchors, 16 straight
steps per segment. A connector attached to two shapes is stored at the middles of their boxes' sides, where
Hancom draws it (Hancom redraws it from the shapes whatever it stores).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.curves import curve_box

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
SIMPLE_CURVE = FIXTURES / "hwpxlib_corpus" / "reader_writer__SimpleCurve.hwpx"
SIMPLE_CONNECT = FIXTURES / "hwpxlib_corpus" / "reader_writer__SimpleConnectLine.hwpx"
AUTHORED = FIXTURES / "hancom_saved" / "shape_curves_and_connectors.hwpx"


def _section(path: Path) -> etree._Element:
    return etree.fromstring(zipfile.ZipFile(path).read("Contents/section0.xml"))


def _anchors(curve: etree._Element) -> list[tuple[int, int]]:
    return [(int(seg.get("x1")), int(seg.get("y1"))) for seg in curve.findall(f"{HP}seg")]


def _size(element: etree._Element, tag: str) -> tuple[int, int]:
    child = element.find(f"{HP}{tag}")
    return int(child.get("width")), int(child.get("height"))


def test_a_curve_s_box_is_the_one_hancom_gives_its_own_curve() -> None:
    curve = next(_section(SIMPLE_CURVE).iter(f"{HP}curve"))
    left, top, right, bottom = curve_box(_anchors(curve), closed=True)

    assert (int(left), int(top)) == (0, 0)  # its anchors sit in the box's own space
    assert (round(right), round(bottom)) == _size(curve, "sz") == _size(curve, "orgSz") == (16636, 21360)


def test_add_curve_writes_the_closed_curve_hancom_saved() -> None:
    saved = next(_section(SIMPLE_CURVE).iter(f"{HP}curve"))
    doc = HwpxDocument.new()
    curve = doc.add_paragraph("").add_curve(_anchors(saved), closed=True, treat_as_char=False).element

    assert _size(curve, "orgSz") == _size(curve, "sz") == _size(saved, "sz")
    assert [dict(seg.attrib) for seg in curve.findall(f"{HP}seg")] == [dict(seg.attrib) for seg in saved.findall(f"{HP}seg")]


def test_an_open_curve_runs_through_its_anchors_once() -> None:
    doc = HwpxDocument.new()
    curve = doc.shapes.add_curve([(10, 150), (40, 120), (70, 170)], treat_as_char=False).element
    segs = curve.findall(f"{HP}seg")

    # The curve rises 76 past its middle anchor (its ends take themselves for their missing neighbours), so
    # the anchors sit that far below the box's top.
    assert [(seg.get("x1"), seg.get("y1"), seg.get("x2"), seg.get("y2")) for seg in segs] == [
        ("0", "8580", "8504", "76"), ("8504", "76", "17008", "14249")]
    assert {seg.get("type") for seg in segs} == {"CURVE"}
    assert _size(curve, "sz") == _size(curve, "orgSz") == (17008, 14249)


def test_add_curve_refuses_too_few_anchors() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as caught:
        doc.shapes.add_curve([(0, 0), (10, 10)], closed=True)
    assert caught.value.code == "shape-curve-too-few-points"


def _placed(shape, x: int, y: int):
    shape.set_position(horizontal_offset=x, vertical_offset=y, horz_rel_to="PAPER", vert_rel_to="PAPER")
    return shape


def test_add_connector_joins_the_sides_where_hancom_draws_the_saved_one() -> None:
    # The fixture's rectangle and ellipse again; its connector leaves the rectangle's right side and meets the
    # ellipse's bottom, drawn from its position and points at curSz over orgSz.
    saved = next(_section(SIMPLE_CONNECT).iter(f"{HP}connectLine"))
    origin = saved.find(f"{HP}pos")
    scale = [cur / org for cur, org in zip(_size(saved, "curSz"), _size(saved, "orgSz"))]
    drawn = [(int(origin.get("horzOffset")) + int(saved.find(f"{HP}{tag}").get("x")) * scale[0],
              int(origin.get("vertOffset")) + int(saved.find(f"{HP}{tag}").get("y")) * scale[1])
             for tag in ("startPt", "endPt")]
    doc = HwpxDocument.new()
    rect = _placed(doc.shapes.add_rectangle(3575, 4375, treat_as_char=False), 15814, 18875)
    ellipse = _placed(doc.shapes.add_ellipse(6576, 3974, treat_as_char=False, paragraph=rect.paragraph), 26663, 12100)
    line = doc.shapes.add_connector(rect, ellipse, start_side="right", end_side="bottom", kind="STROKE").element
    position = line.find(f"{HP}pos")
    start, end = line.find(f"{HP}startPt"), line.find(f"{HP}endPt")

    assert line.get("type") == saved.get("type") == "STROKE_NOARROW"
    assert (position.get("horzRelTo"), position.get("vertRelTo")) == ("PAPER", "PAPER")
    assert (position.get("horzOffset"), position.get("vertOffset")) == (origin.get("horzOffset"), origin.get("vertOffset"))
    assert _size(line, "sz") == _size(saved, "sz") == (10562, 4988)
    assert (start.get("subjectIDRef"), start.get("subjectIdx")) == (rect.inst_id, "1")
    assert (end.get("subjectIDRef"), end.get("subjectIdx")) == (ellipse.inst_id, "2")
    mine = [(int(position.get("horzOffset")) + int(pt.get("x")), int(position.get("vertOffset")) + int(pt.get("y")))
            for pt in (start, end)]
    assert all(abs(a - b) < 1 for p, q in zip(mine, drawn) for a, b in zip(p, q))


def test_add_connector_refuses_what_hancom_would_not_draw_there() -> None:
    doc = HwpxDocument.new()
    inline = doc.shapes.add_rectangle(3000, 3000)
    rect = _placed(doc.shapes.add_rectangle(3000, 3000, treat_as_char=False), 1000, 1000)
    ellipse = _placed(doc.shapes.add_ellipse(3000, 3000, treat_as_char=False), 9000, 1000)
    elsewhere = doc.shapes.add_ellipse(3000, 3000, treat_as_char=False)  # from the column and its paragraph

    for start, end, options, code in [
        (inline, ellipse, {}, "shape-connector-target-inline"),
        (rect, elsewhere, {}, "shape-connector-frame"),
        (rect, ellipse, {"start_side": "middle"}, "shape-connector-side-invalid"),
        (rect, ellipse, {"kind": "ARC"}, "shape-connector-kind-unsupported"),
    ]:
        with pytest.raises(HwpxValueError) as caught:
            doc.shapes.add_connector(start, end, **options)
        assert caught.value.code == code


def _geometry(section: etree._Element) -> list[dict]:
    shapes = []
    for element in [*section.iter(f"{HP}curve"), *section.iter(f"{HP}connectLine")]:
        position = element.find(f"{HP}pos")
        shapes.append({
            "tag": element.tag, "type": element.get("type"),
            "sizes": [_size(element, tag) for tag in ("orgSz", "sz")],
            "place": [position.get(name) for name in ("horzRelTo", "vertRelTo", "horzOffset", "vertOffset")],
            "segs": [dict(seg.attrib) for seg in element.findall(f"{HP}seg")],
            "ends": [(pt.get("x"), pt.get("y"), pt.get("subjectIdx")) for pt in element if pt.tag in (f"{HP}startPt", f"{HP}endPt")],
        })
    return shapes


def test_hancom_keeps_the_curves_and_connectors_python_hwpx_writes() -> None:
    # A rectangle and an ellipse placed from the paper, joined by a straight and a bent connector, and an open
    # and a closed curve, written by python-hwpx and saved again by Hancom, which drew both connectors on the
    # shapes' sides. Hancom keeps every size, place, segment and end (curSz aside, which it writes as 0 for a
    # shape it did not resize).
    doc = HwpxDocument.new()
    doc.add_paragraph("곡선과 연결선")
    rect = _placed(doc.shapes.add_rectangle(6000, 4000, treat_as_char=False), 12000, 30000)
    ellipse = _placed(doc.shapes.add_ellipse(7000, 5000, treat_as_char=False, paragraph=rect.paragraph), 36000, 20000)
    doc.shapes.add_connector(rect, ellipse, start_side="right", end_side="left", kind="STRAIGHT")
    doc.shapes.add_connector(rect, ellipse, start_side="bottom", end_side="bottom", kind="STROKE")
    _placed(doc.shapes.add_curve([(10, 150), (40, 120), (70, 170), (100, 130), (130, 160)], treat_as_char=False),
            8000, 48000)
    _placed(doc.shapes.add_curve([(0, 20), (30, 0), (60, 25), (35, 55), (10, 50)], closed=True, fill_color="#FFE0C0",
                                 treat_as_char=False), 16000, 64000)
    mine = _geometry(etree.fromstring(zipfile.ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/section0.xml")))

    assert mine == _geometry(_section(AUTHORED))
    assert len(mine) == 4
