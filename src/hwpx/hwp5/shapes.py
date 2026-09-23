# SPDX-License-Identifier: Apache-2.0
"""Drawing objects (``gso ``) in HWP 5.0 BodyText: record codecs.

A drawing object is a ``CTRL_HEADER`` with the common object header and a
``SHAPE_COMPONENT`` record under it. The component names the kind of shape
and holds its place in a group, its original and current size, flip,
rotation and transformation matrices. A drawn shape goes on with its line,
fill and shadow (:class:`DrawingStyle`) and has a geometry record of its
kind, and a text box has a paragraph list; a container holds the components
of its shapes instead. Each codec re-encodes its payload byte for byte.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import bodytext as bt
from . import cfb
from . import docinfo as di
from . import records as rec
from .binary import Builder, Cursor
from .errors import Hwp5Error

Point = tuple[int, int]
Matrix = tuple[float, float, float, float, float, float]

#: OWPML element of each shape kind the reader converts.
SHAPE_ELEMENTS = {
    "$rec": "rect",
    "$ell": "ellipse",
    "$arc": "arc",
    "$pol": "polygon",
    "$lin": "line",
    "$cur": "curve",
    "$col": "connectLine",
    "$con": "container",
    "$pic": "pic",
    "$ole": "ole",
}
#: The geometry record of each shape kind.
GEOMETRY_TAGS = {
    "$rec": rec.SHAPE_COMPONENT_RECTANGLE,
    "$ell": rec.SHAPE_COMPONENT_ELLIPSE,
    "$arc": rec.SHAPE_COMPONENT_ARC,
    "$pol": rec.SHAPE_COMPONENT_POLYGON,
    "$lin": rec.SHAPE_COMPONENT_LINE,
    "$cur": rec.SHAPE_COMPONENT_CURVE,
    "$col": rec.SHAPE_COMPONENT_LINE,
    "$pic": rec.SHAPE_COMPONENT_PICTURE,
    "$ole": rec.SHAPE_COMPONENT_OLE,
}


def _matrix(c: Cursor) -> Matrix:
    values = struct.unpack("<6d", c.raw(48))
    return (values[0], values[1], values[2], values[3], values[4], values[5])


def _point(c: Cursor) -> Point:
    return c.i32(), c.i32()


def _points(b: Builder, points: list[Point]) -> None:
    for x, y in points:
        b.i32(x).i32(y)


@dataclass
class ShapeComponent:
    """``SHAPE_COMPONENT``: the kind, placement, size, flip, rotation and matrices.

    A top-level component repeats its kind id; one inside a container does not.
    ``matrices`` holds the translation, then scale and rotation pairs.
    """

    kind: str = "$rec"
    top: bool = True
    x: int = 0
    y: int = 0
    group_level: int = 0
    version: int = 1
    org_width: int = 0
    org_height: int = 0
    cur_width: int = 0
    cur_height: int = 0
    flags: int = 0
    angle: int = 0
    center_x: int = 0
    center_y: int = 0
    matrices: list[Matrix] = field(default_factory=list)
    rest: bytes = b""

    @classmethod
    def decode(cls, payload: bytes, *, top: bool) -> "ShapeComponent":
        c = Cursor(payload, "SHAPE_COMPONENT")
        value = cls(bt.ctrl_id(c.u32()), top)
        if top:
            c.u32()
        value.x, value.y = c.i32(), c.i32()
        value.group_level, value.version = c.u16(), c.u16()
        value.org_width, value.org_height = c.u32(), c.u32()
        value.cur_width, value.cur_height = c.u32(), c.u32()
        value.flags = c.u32()
        value.angle = c.i16()
        value.center_x, value.center_y = c.i32(), c.i32()
        pairs = c.u16()
        value.matrices = [_matrix(c) for _ in range(1 + 2 * pairs)]
        value.rest = c.rest()
        return value

    def encode(self) -> bytes:
        word = bt.ctrl_word(self.kind)
        b = Builder().u32(word)
        if self.top:
            b.u32(word)
        b.i32(self.x).i32(self.y).u16(self.group_level).u16(self.version)
        b.u32(self.org_width).u32(self.org_height).u32(self.cur_width).u32(self.cur_height)
        b.u32(self.flags).i16(self.angle).i32(self.center_x).i32(self.center_y)
        b.u16(max(len(self.matrices) - 1, 0) // 2)
        for matrix in self.matrices:
            b.raw(struct.pack("<6d", *matrix))
        return b.raw(self.rest).bytes()


@dataclass
class DrawingStyle:
    """What a drawn shape's component holds after its matrices: the line
    (colour, width, properties, outline style), the fill, the shadow (kind,
    colour, offsets), the instance id and the line and shadow alphas. Older
    records stop after the line or after the fill; the rest then keeps its
    defaults and ``raw_size`` the record's own length."""

    line_color: int = 0
    line_width: int = 0
    line_props: int = 0
    outline: int = 0
    fill: di.Fill = field(default_factory=di.Fill)
    shadow_type: int = 0
    shadow_color: int = 0xB2B2B2
    shadow_x: int = 0
    shadow_y: int = 0
    instance_id: int = 0
    line_alpha: int = 0
    shadow_alpha: int = 0
    extra: bytes = b""
    raw_size: int | None = None

    @classmethod
    def decode(cls, data: bytes) -> "DrawingStyle":
        c = Cursor(data, "SHAPE_COMPONENT")
        value = cls(c.u32(), c.i32(), c.u32(), c.u8())
        if c.left:
            value.fill = di.Fill.read(c)
        if not c.left:
            value.raw_size = len(data)
            return value
        value.shadow_type, value.shadow_color = c.u32(), c.u32()
        value.shadow_x, value.shadow_y = c.i32(), c.i32()
        value.instance_id = c.u32()
        value.line_alpha = c.u8() if c.left else 0
        value.shadow_alpha = c.u8() if c.left else 0
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.line_color).i32(self.line_width).u32(self.line_props).u8(self.outline)
        self.fill.write(b)
        b.u32(self.shadow_type).u32(self.shadow_color).i32(self.shadow_x).i32(self.shadow_y)
        out = b.u32(self.instance_id).u8(self.line_alpha).u8(self.shadow_alpha).raw(self.extra).bytes()
        return out[: self.raw_size] if self.raw_size is not None else out


@dataclass
class ContainerChildren:
    """What a container's component holds after its matrices: the kinds of its
    shapes and its instance id."""

    kinds: list[str] = field(default_factory=list)
    instance_id: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, data: bytes) -> "ContainerChildren":
        c = Cursor(data, "SHAPE_COMPONENT")
        value = cls([bt.ctrl_id(c.u32()) for _ in range(c.u16())])
        value.instance_id = c.u32() if c.left >= 4 else 0
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u16(len(self.kinds))
        for kind in self.kinds:
            b.u32(bt.ctrl_word(kind))
        return b.u32(self.instance_id).raw(self.extra).bytes()


@dataclass
class Rectangle:
    """``SHAPE_COMPONENT_RECTANGLE``: corner rounding (percent) and the four corners."""

    ratio: int = 0
    corners: list[Point] = field(default_factory=lambda: [(0, 0)] * 4)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Rectangle":
        c = Cursor(payload, "SHAPE_COMPONENT_RECTANGLE")
        value = cls(c.u8(), [_point(c) for _ in range(4)])
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u8(self.ratio)
        _points(b, self.corners)
        return b.raw(self.extra).bytes()


@dataclass
class Ellipse:
    """``SHAPE_COMPONENT_ELLIPSE``: properties, then the centre, the two axis
    ends and the start and end points of the two arcs."""

    props: int = 0
    points: list[Point] = field(default_factory=lambda: [(0, 0)] * 7)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Ellipse":
        c = Cursor(payload, "SHAPE_COMPONENT_ELLIPSE")
        value = cls(c.u32(), [_point(c) for _ in range(7)])
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.props)
        _points(b, self.points)
        return b.raw(self.extra).bytes()


@dataclass
class Arc:
    """``SHAPE_COMPONENT_ARC``: the arc kind, the centre and the two axis ends."""

    kind: int = 0
    points: list[Point] = field(default_factory=lambda: [(0, 0)] * 3)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Arc":
        c = Cursor(payload, "SHAPE_COMPONENT_ARC")
        value = cls(c.u8(), [_point(c) for _ in range(3)])
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u8(self.kind)
        _points(b, self.points)
        return b.raw(self.extra).bytes()


@dataclass
class Polygon:
    """``SHAPE_COMPONENT_POLYGON``: the points."""

    points: list[Point] = field(default_factory=list)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Polygon":
        c = Cursor(payload, "SHAPE_COMPONENT_POLYGON")
        count = c.u32()
        value = cls([_point(c) for _ in range(min(count, c.left // 8))])
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(len(self.points))
        _points(b, self.points)
        return b.raw(self.extra).bytes()


@dataclass
class Curve:
    """``SHAPE_COMPONENT_CURVE``: the points, the kind of each segment between
    two of them (0 line, 1 curve), then four bytes OWPML has no place for."""

    points: list[Point] = field(default_factory=list)
    segments: list[int] = field(default_factory=list)
    extra: bytes = bytes(4)

    @classmethod
    def decode(cls, payload: bytes) -> "Curve":
        c = Cursor(payload, "SHAPE_COMPONENT_CURVE")
        count = c.u32()
        points = [_point(c) for _ in range(min(count, c.left // 8))]
        value = cls(points, list(c.raw(min(max(len(points) - 1, 0), c.left))))
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(len(self.points))
        _points(b, self.points)
        return b.raw(bytes(self.segments)).raw(self.extra).bytes()


#: A connector's control point: x, y and its kind.
ControlPoint = tuple[int, int, int]


@dataclass
class ConnectLine:
    """The ``SHAPE_COMPONENT_LINE`` of a connector: the start and end points,
    the connector type, the shape (instance id) and connection point each end
    is attached to, the control points, then a word OWPML has no place for."""

    start: Point = (0, 0)
    end: Point = (0, 0)
    kind: int = 0
    start_subject: int = 0
    start_index: int = 0
    end_subject: int = 0
    end_index: int = 0
    control_points: list[ControlPoint] = field(default_factory=list)
    extra: bytes = bytes(4)

    @classmethod
    def decode(cls, payload: bytes) -> "ConnectLine":
        c = Cursor(payload.ljust(40, b"\0"), "SHAPE_COMPONENT_LINE")
        value = cls(_point(c), _point(c), c.u32(), c.u32(), c.u32(), c.u32(), c.u32())
        count = c.u32()
        value.control_points = [(c.i32(), c.i32(), c.u16()) for _ in range(min(count, c.left // 10))]
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder()
        _points(b, [self.start, self.end])
        b.u32(self.kind).u32(self.start_subject).u32(self.start_index).u32(self.end_subject).u32(self.end_index)
        b.u32(len(self.control_points))
        for x, y, kind in self.control_points:
            b.i32(x).i32(y).u16(kind)
        return b.raw(self.extra).bytes()


@dataclass
class Line:
    """``SHAPE_COMPONENT_LINE``: the start and end points and whether the line
    was drawn from its end (``isReverseHV``)."""

    start: Point = (0, 0)
    end: Point = (0, 0)
    reverse: int | None = 0  # None: an older record without the word
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Line":
        c = Cursor(payload, "SHAPE_COMPONENT_LINE")
        value = cls(_point(c), _point(c))
        value.reverse = c.u32() if c.left >= 4 else None
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder()
        _points(b, [self.start, self.end])
        if self.reverse is not None:
            b.u32(self.reverse)
        return b.raw(self.extra).bytes()


@dataclass
class TextBox:
    """The ``LIST_HEADER`` of a shape's text: paragraph count, list
    properties, margins, the last line's width and the box's name."""

    paragraphs: int = 1
    props: int = 0
    reserved: int = 0
    margins: tuple[int, int, int, int] = (283, 283, 283, 283)
    last_width: int = 0
    reserved2: bytes = bytes(8)
    editable: int | None = 0  # editable in form mode (bit 0); None when the record ends before it
    name: str | None = None
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "TextBox":
        c = Cursor(payload, "LIST_HEADER")
        value = cls(c.u16(), c.u32(), c.u16())
        value.margins = (c.u16(), c.u16(), c.u16(), c.u16())
        value.last_width = c.u32()
        value.reserved2 = c.raw(min(8, c.left))
        value.editable = c.u32() if c.left >= 4 else None
        rest = c.rest()
        prefix = b"\xff" + NAME_SET
        if rest.startswith(prefix) and len(rest) >= len(prefix) + 2:
            tail = Cursor(rest[len(prefix) :], "LIST_HEADER")
            value.name = tail.wstr()
            rest = tail.rest()
        value.extra = rest
        return value

    def encode(self) -> bytes:
        b = Builder().u16(self.paragraphs).u32(self.props).u16(self.reserved)
        for margin in self.margins:
            b.u16(margin)
        b.u32(self.last_width).raw(self.reserved2)
        if self.editable is not None:
            b.u32(self.editable)
        if self.name is not None:
            b.raw(b"\xff" + NAME_SET).wstr(self.name)
        return b.raw(self.extra).bytes()


@dataclass
class EffectColor:
    """The colour of a picture effect: its type (0 RGB with the colour as
    0x00RRGGBB, 2 scheme and 3 system with their index as the value) and its
    colour effects, each a kind and an amount."""

    kind: int = 0
    value: int = 0
    effects: list[tuple[int, float]] = field(default_factory=list)

    @classmethod
    def read(cls, c: Cursor) -> "EffectColor":
        value = cls(c.u32(), c.u32())
        value.effects = [(c.u32(), c.f32()) for _ in range(c.u32())]
        return value

    def write(self, b: Builder) -> None:
        b.u32(self.kind).u32(self.value).u32(len(self.effects))
        for kind, amount in self.effects:
            b.u32(kind).f32(amount)


@dataclass
class ShadowEffect:
    style: int = 0
    alpha: float = 0.0
    radius: float = 0.0
    direction: float = 0.0
    distance: float = 0.0
    align: int = 0
    skew: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    rotation: int = 0
    color: EffectColor = field(default_factory=EffectColor)


@dataclass
class GlowEffect:
    alpha: float = 0.0
    radius: float = 0.0
    color: EffectColor = field(default_factory=EffectColor)


@dataclass
class ReflectionEffect:
    align: int = 0
    radius: float = 0.0
    direction: float = 0.0
    distance: float = 0.0
    skew: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    rotation: int = 0
    start: tuple[float, float] = (0.0, 0.0)  # alpha and position where it starts
    end: tuple[float, float] = (0.0, 0.0)  # and where it ends
    fade: float = 0.0


@dataclass
class PictureEffects:
    """A picture's effects, each present when its bit of the effects word is
    set: shadow (1), glow (2), soft edge (4) and reflection (8), in that order."""

    shadow: ShadowEffect | None = None
    glow: GlowEffect | None = None
    soft_edge: float | None = None
    reflection: ReflectionEffect | None = None

    @property
    def flags(self) -> int:
        return (
            (1 if self.shadow is not None else 0)
            | (2 if self.glow is not None else 0)
            | (4 if self.soft_edge is not None else 0)
            | (8 if self.reflection is not None else 0)
        )

    @classmethod
    def read(cls, c: Cursor, flags: int) -> "PictureEffects":
        value = cls()
        if flags & 1:
            value.shadow = ShadowEffect(c.u32(), c.f32(), c.f32(), c.f32(), c.f32(), c.u32())
            value.shadow.skew, value.shadow.scale = (c.f32(), c.f32()), (c.f32(), c.f32())
            value.shadow.rotation, value.shadow.color = c.u32(), EffectColor.read(c)
        if flags & 2:
            value.glow = GlowEffect(c.f32(), c.f32(), EffectColor.read(c))
        if flags & 4:
            value.soft_edge = c.f32()
        if flags & 8:
            value.reflection = ReflectionEffect(c.u32(), c.f32(), c.f32(), c.f32())
            reflection = value.reflection
            reflection.skew, reflection.scale = (c.f32(), c.f32()), (c.f32(), c.f32())
            reflection.rotation = c.u32()
            start_alpha, start_pos, end_alpha, end_pos = c.f32(), c.f32(), c.f32(), c.f32()
            reflection.start, reflection.end = (start_alpha, start_pos), (end_alpha, end_pos)
            reflection.fade = c.f32()
        return value

    def write(self, b: Builder) -> None:
        if self.shadow is not None:
            s = self.shadow
            b.u32(s.style).f32(s.alpha).f32(s.radius).f32(s.direction).f32(s.distance).u32(s.align)
            b.f32(s.skew[0]).f32(s.skew[1]).f32(s.scale[0]).f32(s.scale[1]).u32(s.rotation)
            s.color.write(b)
        if self.glow is not None:
            b.f32(self.glow.alpha).f32(self.glow.radius)
            self.glow.color.write(b)
        if self.soft_edge is not None:
            b.f32(self.soft_edge)
        if self.reflection is not None:
            r = self.reflection
            b.u32(r.align).f32(r.radius).f32(r.direction).f32(r.distance)
            b.f32(r.skew[0]).f32(r.skew[1]).f32(r.scale[0]).f32(r.scale[1]).u32(r.rotation)
            b.f32(r.start[0]).f32(r.start[1]).f32(r.end[0]).f32(r.end[1]).f32(r.fade)


@dataclass
class Picture:
    """``SHAPE_COMPONENT_PICTURE``: the border line (colour, width,
    properties), the image's four corners, the crop box (left, top, right,
    bottom), the inner margins, brightness, contrast, effect and binary item
    id, then the alpha, the instance id, the effects word, the effects it
    announces and the image's own size. Records of older versions end after
    the alpha or the instance id."""

    line_color: int = 0
    line_width: int = 0
    line_props: int = 0
    corners: list[Point] = field(default_factory=lambda: [(0, 0)] * 4)
    crop: tuple[int, int, int, int] = (0, 0, 0, 0)
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    bright: int = 0
    contrast: int = 0
    effect: int = 0
    bin_id: int = 0
    alpha: int | None = 0
    instance_id: int | None = 0
    effects: int | None = 0
    dim: tuple[int, int] | None = (0, 0)
    extra: bytes = b""
    # The effects the word announces; None when there are none or they could
    # not be read (their bytes then stay in ``extra``).
    effect_list: PictureEffects | None = None

    @classmethod
    def decode(cls, payload: bytes) -> "Picture":
        c = Cursor(payload, "SHAPE_COMPONENT_PICTURE")
        value = cls(c.u32(), c.i32(), c.u32(), [_point(c) for _ in range(4)])
        value.crop = (c.i32(), c.i32(), c.i32(), c.i32())
        value.margins = (c.u16(), c.u16(), c.u16(), c.u16())
        value.bright, value.contrast, value.effect, value.bin_id = c.i8(), c.i8(), c.u8(), c.u16()
        value.alpha = c.u8() if c.left else None
        value.instance_id = c.u32() if value.alpha is not None and c.left >= 4 else None
        value.effects = c.u32() if value.instance_id is not None and c.left >= 4 else None
        if value.effects:
            start = c.pos
            try:
                value.effect_list = PictureEffects.read(c, value.effects)
            except Hwp5Error:
                c.pos, value.effect_list = start, None
        # The image's own size follows the effects.
        value.dim = (c.u32(), c.u32()) if value.effects is not None and (value.effects == 0 or value.effect_list) and c.left >= 8 else None
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.line_color).i32(self.line_width).u32(self.line_props)
        _points(b, self.corners)
        for value in self.crop:
            b.i32(value)
        for margin in self.margins:
            b.u16(margin)
        b.i8(self.bright).i8(self.contrast).u8(self.effect).u16(self.bin_id)
        if self.alpha is not None:
            b.u8(self.alpha)
        if self.instance_id is not None:
            b.u32(self.instance_id)
        if self.effects is not None:
            b.u32(self.effects)
        if self.effect_list is not None:
            self.effect_list.write(b)
        if self.dim is not None:
            b.u32(self.dim[0]).u32(self.dim[1])
        return b.raw(self.extra).bytes()


@dataclass
class OleObject:
    """``SHAPE_COMPONENT_OLE``: the properties (draw aspect in bits 0-7, a
    moniker in bit 8, the baseline in bits 9-15, the object type in bits
    16-21), the object's own extent, the binary item id, the border line
    (colour, width, properties), then the instance id. Records of older
    versions end before the instance id."""

    props: int = 0
    extent: Point = (0, 0)
    bin_id: int = 0
    line_color: int = 0
    line_width: int = 0
    line_props: int = 0
    instance_id: int | None = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "OleObject":
        c = Cursor(payload, "SHAPE_COMPONENT_OLE")
        value = cls(c.u32(), _point(c), c.u16(), c.u32(), c.i32(), c.u32())
        value.instance_id = c.u32() if c.left >= 4 else None
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.props)
        _points(b, [self.extent])
        b.u16(self.bin_id).u32(self.line_color).i32(self.line_width).u32(self.line_props)
        if self.instance_id is not None:
            b.u32(self.instance_id)
        return b.raw(self.extra).bytes()


#: The class of a Hancom chart's OLE storage, {4C3DA137-DC90-47B9-9BED-59DAE352A280}.
HANCOM_CHART = bytes.fromhex("37a13d4c90dcb9479bed59dae352a280")
#: The stream of a Hancom chart's storage that holds the chart as chartML.
CHART_STREAM = "OOXMLChartContents"


def chart_xml(storage: bytes) -> bytes | None:
    """The chartML part of a Hancom chart, from its OLE storage (a length
    word, then the compound file); None for any other storage."""

    if storage[4:12] != cfb.SIGNATURE:
        return None
    try:
        compound = cfb.CompoundFile(storage[4:])
        if compound.root.clsid != HANCOM_CHART or not compound.has_stream(CHART_STREAM):
            return None
        return compound.read(CHART_STREAM)
    except Hwp5Error:
        return None


#: A one-item parameter set naming something (the same set cells and fields use).
NAME_SET = bytes.fromhex("1b020100000000400100")
