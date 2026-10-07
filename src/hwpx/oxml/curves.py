# SPDX-License-Identifier: Apache-2.0
"""Curves (``hp:curve``) and connectors (``hp:connectLine``) written the way Hancom reads them.

A curve passes through its anchors: Hancom draws each ``hp:seg`` of type ``CURVE`` as a Catmull-Rom
segment (a cubic Bézier whose control points are an anchor plus a sixth of the vector between its
neighbours; a closed curve wraps its neighbours round, an open one repeats its end points). It draws
the segments at the shape's ``sz`` over its ``orgSz`` and never recomputes that box itself, so the
writer sets it: the box of the curve approximated by 16 straight steps per segment, as Hancom's own
curves have it. The anchors are stored in that box's own top-left-anchored space.

A connector attached to two shapes (``subjectIDRef`` = a shape's ``instid``) is redrawn by Hancom from
the shapes' current boxes and each end's ``subjectIdx`` -- the middle of the box's top (0), right (1),
bottom (2) or left (3) side -- whatever its stored points say; a straight one runs between the two
points, a bent (``STROKE``) one leaves each side square to it on a path Hancom chooses. The writer
stores the points at those side middles all the same, in the frame the two shapes share, so that other
readers see the connector where Hancom draws it. An arc (``ARC``) needs control points and is not
written, nor a curve with straight (``LINE``) segments or one inside a group, whose boxes Hancom's
curves do not follow.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence
import xml.etree.ElementTree as ET

from ..errors import HwpxValueError
from ._document_primitives import _HP, _append_child
from .objects import (
    HwpxOxmlShape,
    _build_drawing_object_children,
    _build_shape_base_children,
    _build_shape_common_children,
)

if TYPE_CHECKING:
    from .paragraph import HwpxOxmlParagraph

__all__ = ["CONNECTOR_KINDS", "CONNECTOR_SIDES", "curve_box"]

#: The connector shapes written: a straight line between the two points, or Hancom's bent path.
CONNECTOR_KINDS = {"STRAIGHT": "STRAIGHT_NOARROW", "STROKE": "STROKE_NOARROW"}
#: A connector end's side of its shape's box, as ``subjectIdx``.
CONNECTOR_SIDES = {"top": 0, "right": 1, "bottom": 2, "left": 3}
_CURVE_STEPS = 16


def curve_box(points: Sequence[tuple[float, float]], closed: bool) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of the curve Hancom draws through *points*, each Catmull-Rom segment
    approximated by 16 straight steps: the box Hancom's own curves carry."""

    count = len(points)

    def anchor(index: int) -> tuple[float, float]:
        return points[index % count] if closed else points[min(max(index, 0), count - 1)]

    xs: list[float] = []
    ys: list[float] = []
    for index in range(count if closed else count - 1):
        before, start, end, after = anchor(index - 1), anchor(index), anchor(index + 1), anchor(index + 2)
        first = (start[0] + (end[0] - before[0]) / 6, start[1] + (end[1] - before[1]) / 6)
        second = (end[0] - (after[0] - start[0]) / 6, end[1] - (after[1] - start[1]) / 6)
        for step in range(_CURVE_STEPS + 1):
            t = step / _CURVE_STEPS
            u = 1 - t
            weights = (u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t)
            xs.append(sum(w * p[0] for w, p in zip(weights, (start, first, second, end))))
            ys.append(sum(w * p[1] for w, p in zip(weights, (start, first, second, end))))
    return min(xs), min(ys), max(xs), max(ys)


def _create_curve_element(
    points: Sequence[tuple[int, int]],
    *,
    closed: bool,
    line_color: str,
    line_width: str,
    fill_color: str | None,
    treat_as_char: bool,
) -> ET.Element:
    """An ``hp:curve`` through *points* (HWPUNIT), closed back to the first one when *closed*."""

    left, top, right, bottom = curve_box(points, closed)
    shift_x, shift_y = math.floor(left), math.floor(top)
    width, height = round(right - shift_x), round(bottom - shift_y)
    local = [(x - shift_x, y - shift_y) for x, y in points]
    element = ET.Element(f"{_HP}curve")
    _build_shape_common_children(element, width, height, treat_as_char=treat_as_char)
    _build_drawing_object_children(element, line_color=line_color, line_width=line_width, fill_color=fill_color)
    pairs = list(zip(local, local[1:] + local[:1])) if closed else list(zip(local, local[1:]))
    for (x1, y1), (x2, y2) in pairs:
        _append_child(element, f"{_HP}seg", {"type": "CURVE", "x1": str(x1), "y1": str(y1),
                                             "x2": str(x2), "y2": str(y2)})
    _build_shape_base_children(element, width, height)
    return element


def _paragraph_add_curve(
    self: "HwpxOxmlParagraph",
    points: Sequence[tuple[int, int]],
    *,
    closed: bool = False,
    line_color: str = "#000000",
    line_width: str = "33",
    fill_color: str | None = None,
    treat_as_char: bool = True,
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlShape:
    """Insert an ``<hp:curve>`` through *points* (HWPUNIT anchors, 2 or more; 3 or more when *closed*).

    The curve's box is the one Hancom gives its own curves (see :func:`curve_box`); the anchors are
    stored in that box's own space, so they do not place the curve on the page -- its paragraph and
    position do."""

    anchors = [(int(x), int(y)) for x, y in points]
    if len(anchors) < (3 if closed else 2):
        raise HwpxValueError(
            "add_curve requires 2 anchors, 3 when closed",
            code="shape-curve-too-few-points",
            context={"count": len(anchors), "closed": closed},
            suggestion="Pass 2 or more (x, y) anchors, or 3 or more for a closed curve.",
        )
    element = _create_curve_element(anchors, closed=closed, line_color=line_color, line_width=line_width,
                                    fill_color=fill_color, treat_as_char=treat_as_char)
    return self._insert_shape_element(element, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)


def _placed_box(shape: HwpxOxmlShape) -> tuple[tuple[str, str], int, int, int, int]:
    """(frame, left, top, width, height) of a floating shape placed from the left and top of its frame."""

    position = shape.element.find(f"{_HP}pos")
    size = shape.element.find(f"{_HP}sz")
    if position is None or size is None or position.get("treatAsChar") not in {"0", "false", "False"}:
        raise HwpxValueError(
            "a connector joins floating shapes",
            code="shape-connector-target-inline",
            suggestion="Place both shapes with treat_as_char=False and set their positions.",
        )
    if position.get("horzAlign", "LEFT") != "LEFT" or position.get("vertAlign", "TOP") != "TOP":
        raise HwpxValueError(
            "a connector joins shapes placed from the left and top of their frame",
            code="shape-connector-frame",
            context={"horzAlign": position.get("horzAlign"), "vertAlign": position.get("vertAlign")},
            suggestion="Place the shapes with horz_align='LEFT' and vert_align='TOP'.",
        )
    frame = (position.get("horzRelTo", "COLUMN"), position.get("vertRelTo", "PARA"))
    return (frame, _signed(position.get("horzOffset", 0)), _signed(position.get("vertOffset", 0)),
            int(size.get("width", 0)), int(size.get("height", 0)))


def _signed(value: str | int) -> int:
    """An offset Hancom writes as its unsigned 32-bit form (one up or left of its frame) as the number it is."""

    number = int(value) & 0xFFFFFFFF
    return number - (1 << 32) if number >= 1 << 31 else number


def _side_point(box: tuple[int, int, int, int], side: int) -> tuple[int, int]:
    left, top, width, height = box
    return [(left + width // 2, top), (left + width, top + height // 2),
            (left + width // 2, top + height), (left, top + height // 2)][side]


def _paragraph_add_connector(
    self: "HwpxOxmlParagraph",
    start: HwpxOxmlShape,
    end: HwpxOxmlShape,
    *,
    start_side: str = "right",
    end_side: str = "left",
    kind: str = "STRAIGHT",
    line_color: str = "#000000",
    line_width: str = "33",
    run_attributes: dict[str, str] | None = None,
    char_pr_id_ref: str | int | None = None,
) -> HwpxOxmlShape:
    """Insert an ``<hp:connectLine>`` attached to *start* and *end* at the middle of a side of each box.

    Both shapes float (not set as characters) from the left and top of one frame -- the paper, the page,
    or the column and paragraph of one paragraph. See the module's description for what Hancom redraws."""

    sides = []
    for side in (start_side, end_side):
        if side not in CONNECTOR_SIDES:
            raise HwpxValueError(
                f"connector side must be one of {', '.join(CONNECTOR_SIDES)}",
                code="shape-connector-side-invalid",
                context={"side": side},
                suggestion="Pass 'top', 'right', 'bottom' or 'left'.",
            )
        sides.append(CONNECTOR_SIDES[side])
    if kind not in CONNECTOR_KINDS:
        raise HwpxValueError(
            "connector kind must be STRAIGHT or STROKE",
            code="shape-connector-kind-unsupported",
            context={"kind": kind},
            suggestion="Pass kind='STRAIGHT' or kind='STROKE'; an arc connector needs control points.",
        )
    ends = []
    for shape in (start, end):
        if not shape.inst_id:
            raise HwpxValueError(
                "a connector joins shapes with an instance id",
                code="shape-connector-target-inline",
                suggestion="Join shapes made by doc.shapes (they carry instid).",
            )
        ends.append(_placed_box(shape))
    absolute = all(frame in {"PAPER", "PAGE"} for frame in ends[0][0])
    anchors = {id(shape.paragraph.element) for shape in (start, end)} | {id(self.element)}
    if ends[0][0] != ends[1][0] or (not absolute and len(anchors) > 1):
        raise HwpxValueError(
            "a connector joins shapes placed in one frame",
            code="shape-connector-frame",
            context={"start": ends[0][0], "end": ends[1][0]},
            suggestion="Place both shapes from the paper or the page, or in the connector's paragraph from its "
                       "column and itself.",
        )
    frame = ends[0][0]
    points = [_side_point(box[1:], side) for box, side in zip(ends, sides)]
    left, top = min(x for x, _ in points), min(y for _, y in points)
    width, height = max(x for x, _ in points) - left, max(y for _, y in points) - top
    element = ET.Element(f"{_HP}connectLine")
    element.set("textWrap", "IN_FRONT_OF_TEXT")
    _build_shape_common_children(element, width, height, treat_as_char=False)
    element.set("type", CONNECTOR_KINDS[kind])
    _build_drawing_object_children(element, line_color=line_color, line_width=line_width)
    for tag, (x, y), shape, side in zip(("startPt", "endPt"), points, (start, end), sides):
        _append_child(element, f"{_HP}{tag}", {"x": str(x - left), "y": str(y - top),
                                               "subjectIDRef": str(shape.inst_id), "subjectIdx": str(side)})
    _build_shape_base_children(element, width, height)
    position = element.find(f"{_HP}pos")
    assert position is not None
    position.set("horzRelTo", frame[0])
    position.set("vertRelTo", frame[1])
    position.set("horzOffset", str(left & 0xFFFFFFFF))  # a negative one as Hancom writes it: unsigned 32-bit
    position.set("vertOffset", str(top & 0xFFFFFFFF))
    return self._insert_shape_element(element, run_attributes=run_attributes, char_pr_id_ref=char_pr_id_ref)
