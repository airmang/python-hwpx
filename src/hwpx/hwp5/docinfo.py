# SPDX-License-Identifier: Apache-2.0
"""DocInfo of an HWP 5.0 document: the id-mapped tables the body refers to.

Each record kind has a dataclass with ``decode(payload)`` and ``encode()``.
Record layouts grew over the 5.0.x versions (a char shape gained a border fill
id in 5.0.2.1 and a strikeout colour in 5.0.3.0, a para shape gained two more
property words and then a level word); the decoded object remembers which
layout it came from so ``encode`` reproduces the payload byte for byte, and
bytes past the known fields ride along in ``extra``.
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass, field

from . import records as rec
from .binary import Builder, Cursor
from .errors import damaged

#: ``ID_MAPPINGS`` counts, in stream order. Documents from before 5.0.2.1 stop
#: after ``style``; those from before 5.0.3.2 stop after ``memo_shape``.
ID_MAPPING_NAMES: tuple[str, ...] = (
    "bin_data",
    "font_hangul",
    "font_latin",
    "font_hanja",
    "font_japanese",
    "font_other",
    "font_symbol",
    "font_user",
    "border_fill",
    "char_shape",
    "tab_def",
    "numbering",
    "bullet",
    "para_shape",
    "style",
    "memo_shape",
    "track_change",
    "track_change_author",
)

FONT_LANGS: tuple[str, ...] = (
    "hangul",
    "latin",
    "hanja",
    "japanese",
    "other",
    "symbol",
    "user",
)

#: The record tag each ``ID_MAPPINGS`` count describes.
_MAPPED_TAGS: dict[str, int] = {
    "bin_data": rec.BIN_DATA,
    "border_fill": rec.BORDER_FILL,
    "char_shape": rec.CHAR_SHAPE,
    "tab_def": rec.TAB_DEF,
    "numbering": rec.NUMBERING,
    "bullet": rec.BULLET,
    "para_shape": rec.PARA_SHAPE,
    "style": rec.STYLE,
    "memo_shape": rec.MEMO_SHAPE,
}


def id_mappings(stream: rec.RecordStream) -> dict[str, int]:
    """The ``ID_MAPPINGS`` counts by name (only the ones the record holds)."""

    for record in stream.roots:
        if record.tag == rec.ID_MAPPINGS:
            count = min(len(record.payload) // 4, len(ID_MAPPING_NAMES))
            values = struct.unpack_from(f"<{count}i", record.payload, 0)
            return dict(zip(ID_MAPPING_NAMES, values))
    return {}


def mapping_mismatches(stream: rec.RecordStream) -> dict[str, tuple[int, int]]:
    """``{name: (declared, found)}`` where a count differs from the records present."""

    mappings = id_mappings(stream)
    found = Counter(record.tag for record in stream.records)
    out: dict[str, tuple[int, int]] = {}
    for name, tag in _MAPPED_TAGS.items():
        if name in mappings and mappings[name] != found.get(tag, 0):
            out[name] = (mappings[name], found.get(tag, 0))
    fonts = sum(mappings.get(f"font_{lang}", 0) for lang in FONT_LANGS)
    if mappings and fonts != found.get(rec.FACE_NAME, 0):
        out["face_name"] = (fonts, found.get(rec.FACE_NAME, 0))
    return out


# -- document properties ------------------------------------------------------------


@dataclass
class DocumentProperties:
    section_count: int = 1
    page_start: int = 1
    footnote_start: int = 1
    endnote_start: int = 1
    picture_start: int = 1
    table_start: int = 1
    equation_start: int = 1
    caret_list_id: int = 0
    caret_para_id: int = 0
    caret_pos: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "DocumentProperties":
        c = Cursor(payload, "DOCUMENT_PROPERTIES")
        props = cls()
        props.section_count = c.u16()
        props.page_start = c.u16()
        props.footnote_start = c.u16()
        props.endnote_start = c.u16()
        props.picture_start = c.u16()
        props.table_start = c.u16()
        props.equation_start = c.u16()
        props.caret_list_id = c.u32()
        props.caret_para_id = c.u32()
        props.caret_pos = c.u32()
        props.extra = c.rest()
        return props

    def encode(self) -> bytes:
        b = Builder()
        for value in (
            self.section_count,
            self.page_start,
            self.footnote_start,
            self.endnote_start,
            self.picture_start,
            self.table_start,
            self.equation_start,
        ):
            b.u16(value)
        return b.u32(self.caret_list_id).u32(self.caret_para_id).u32(self.caret_pos).raw(self.extra).bytes()


# -- binary data ----------------------------------------------------------------------

BIN_LINK = 0
BIN_EMBEDDING = 1
BIN_STORAGE = 2


@dataclass
class BinDataItem:
    """A ``BIN_DATA`` record: a linked file or an embedded ``BinData`` stream."""

    props: int
    abs_path: str = ""
    rel_path: str = ""
    bin_id: int = 0
    extension: str = ""
    extra: bytes = b""

    @property
    def kind(self) -> int:
        return self.props & 0xF

    @property
    def compression(self) -> int:
        """0 follows the document, 1 compresses, 2 stores."""

        return (self.props >> 4) & 0x3

    @property
    def stream_name(self) -> str:
        """The item's stream in ``BinData``; an item with no extension has a
        name with no dot."""

        name = f"BIN{self.bin_id:04X}"
        return f"{name}.{self.extension}" if self.extension else name

    @classmethod
    def decode(cls, payload: bytes) -> "BinDataItem":
        c = Cursor(payload, "BIN_DATA")
        item = cls(c.u16())
        if item.kind == BIN_LINK:
            item.abs_path = c.wstr()
            item.rel_path = c.wstr()
        else:
            item.bin_id = c.u16()
            if c.left >= 2:
                item.extension = c.wstr()
        item.extra = c.rest()
        return item

    def encode(self) -> bytes:
        b = Builder().u16(self.props)
        if self.kind == BIN_LINK:
            b.wstr(self.abs_path).wstr(self.rel_path)
        else:
            b.u16(self.bin_id)
            if self.kind in (BIN_EMBEDDING, BIN_STORAGE) or self.extension:
                b.wstr(self.extension)
        return b.raw(self.extra).bytes()


# -- fonts ------------------------------------------------------------------------------


@dataclass
class FaceName:
    """A ``FACE_NAME`` record: one font of one language list."""

    props: int
    name: str
    alt_type: int = 0
    alt_name: str = ""
    type_info: bytes = b""
    default_name: str = ""
    extra: bytes = b""

    HAS_ALT = 0x80
    HAS_TYPE_INFO = 0x40
    HAS_DEFAULT = 0x20

    @property
    def font_type(self) -> int:
        """1 is TrueType, 2 is a Hangul font (HFT)."""

        return self.props & 0x3

    @classmethod
    def decode(cls, payload: bytes) -> "FaceName":
        c = Cursor(payload, "FACE_NAME")
        font = cls(c.u8(), c.wstr())
        if font.props & cls.HAS_ALT:
            font.alt_type = c.u8()
            font.alt_name = c.wstr()
        if font.props & cls.HAS_TYPE_INFO:
            font.type_info = c.raw(10)
        if font.props & cls.HAS_DEFAULT:
            font.default_name = c.wstr()
        font.extra = c.rest()
        return font

    def encode(self) -> bytes:
        b = Builder().u8(self.props).wstr(self.name)
        if self.props & self.HAS_ALT:
            b.u8(self.alt_type).wstr(self.alt_name)
        if self.props & self.HAS_TYPE_INFO:
            b.raw(self.type_info.ljust(10, b"\0")[:10])
        if self.props & self.HAS_DEFAULT:
            b.wstr(self.default_name)
        return b.raw(self.extra).bytes()


# -- border and fill ------------------------------------------------------------------

FILL_SOLID = 0x1
FILL_IMAGE = 0x2
FILL_GRADATION = 0x4


@dataclass
class Line:
    kind: int = 0
    width: int = 0
    color: int = 0


@dataclass
class Fill:
    """``채우기 정보``: any mix of a solid/pattern, gradation and image fill."""

    kind: int = 0
    back_color: int = 0xFFFFFFFF
    pattern_color: int = 0
    pattern_type: int = -1
    grad_type: int = 0
    grad_angle: int = 0
    grad_center_x: int = 0
    grad_center_y: int = 0
    grad_step: int = 0
    grad_positions: list[int] = field(default_factory=list)
    grad_colors: list[int] = field(default_factory=list)
    image_mode: int = 0
    image_bright: int = 0
    image_contrast: int = 0
    image_effect: int = 0
    image_bin_id: int = 0
    additional: bytes | None = b""
    alphas: bytes = b""

    @classmethod
    def read(cls, c: Cursor) -> "Fill":
        fill = cls(c.u32())
        if fill.kind & FILL_SOLID:
            fill.back_color = c.u32()
            fill.pattern_color = c.u32()
            fill.pattern_type = c.i32()
        if fill.kind & FILL_GRADATION:
            fill.grad_type = c.u8()
            fill.grad_angle = c.i32()
            fill.grad_center_x = c.i32()
            fill.grad_center_y = c.i32()
            fill.grad_step = c.i32()
            count = c.i32()
            if count < 0 or count * 4 > c.left:
                raise damaged("BORDER_FILL gradation has an impossible colour count", count=count)
            if count > 2:
                fill.grad_positions = [c.i32() for _ in range(count)]
            fill.grad_colors = [c.u32() for _ in range(count)]
        if fill.kind & FILL_IMAGE:
            fill.image_mode = c.u8()
            fill.image_bright = c.i8()
            fill.image_contrast = c.i8()
            fill.image_effect = c.u8()
            fill.image_bin_id = c.u16()
        # Files from 5.0.0.x end the fill here, without the additional block.
        if c.left >= 4:
            size = c.u32()
            fill.additional = c.raw(size)
            kinds = bin(fill.kind & (FILL_SOLID | FILL_IMAGE | FILL_GRADATION)).count("1")
            fill.alphas = c.raw(min(kinds, c.left))
        else:
            fill.additional = None
        return fill

    def write(self, b: Builder) -> None:
        b.u32(self.kind)
        if self.kind & FILL_SOLID:
            b.u32(self.back_color).u32(self.pattern_color).i32(self.pattern_type)
        if self.kind & FILL_GRADATION:
            b.u8(self.grad_type).i32(self.grad_angle).i32(self.grad_center_x)
            b.i32(self.grad_center_y).i32(self.grad_step).i32(len(self.grad_colors))
            if len(self.grad_colors) > 2:
                positions = self.grad_positions or [0] * len(self.grad_colors)
                for position in positions:
                    b.i32(position)
            for color in self.grad_colors:
                b.u32(color)
        if self.kind & FILL_IMAGE:
            b.u8(self.image_mode).i8(self.image_bright).i8(self.image_contrast)
            b.u8(self.image_effect).u16(self.image_bin_id)
        if self.additional is not None:
            b.u32(len(self.additional)).raw(self.additional).raw(self.alphas)


@dataclass
class BorderFill:
    """A ``BORDER_FILL`` record: four borders, a diagonal and a fill."""

    props: int = 0
    left: Line = field(default_factory=Line)
    right: Line = field(default_factory=Line)
    top: Line = field(default_factory=Line)
    bottom: Line = field(default_factory=Line)
    diagonal: Line = field(default_factory=Line)
    fill: Fill = field(default_factory=Fill)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "BorderFill":
        c = Cursor(payload, "BORDER_FILL")
        props = c.u16()
        left, right, top, bottom, diagonal = (Line(c.u8(), c.u8(), c.u32()) for _ in range(5))
        fill = Fill.read(c)
        return cls(props, left, right, top, bottom, diagonal, fill, c.rest())

    def encode(self) -> bytes:
        b = Builder().u16(self.props)
        for line in (self.left, self.right, self.top, self.bottom, self.diagonal):
            b.u8(line.kind).u8(line.width).u32(line.color)
        self.fill.write(b)
        return b.raw(self.extra).bytes()


# -- character and paragraph shapes -------------------------------------------------


@dataclass
class CharShape:
    """A ``CHAR_SHAPE`` record (68, 70 or 74 bytes by version)."""

    font_ids: list[int] = field(default_factory=lambda: [0] * 7)
    ratios: list[int] = field(default_factory=lambda: [100] * 7)
    spacings: list[int] = field(default_factory=lambda: [0] * 7)
    rel_sizes: list[int] = field(default_factory=lambda: [100] * 7)
    offsets: list[int] = field(default_factory=lambda: [0] * 7)
    height: int = 1000
    props: int = 0
    shadow_x: int = 10
    shadow_y: int = 10
    text_color: int = 0
    underline_color: int = 0
    shade_color: int = 0xFFFFFFFF
    shadow_color: int = 0xB2B2B2
    border_fill_id: int | None = 2
    strikeout_color: int | None = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "CharShape":
        c = Cursor(payload, "CHAR_SHAPE")
        shape = cls(
            [c.u16() for _ in range(7)],
            [c.u8() for _ in range(7)],
            [c.i8() for _ in range(7)],
            [c.u8() for _ in range(7)],
            [c.i8() for _ in range(7)],
            c.i32(),
            c.u32(),
            c.i8(),
            c.i8(),
            c.u32(),
            c.u32(),
            c.u32(),
            c.u32(),
        )
        shape.border_fill_id = c.u16() if c.left >= 2 else None
        shape.strikeout_color = c.u32() if c.left >= 4 else None
        shape.extra = c.rest()
        return shape

    def encode(self) -> bytes:
        b = Builder()
        for value in self.font_ids:
            b.u16(value)
        for value in self.ratios:
            b.u8(value)
        for value in self.spacings:
            b.i8(value)
        for value in self.rel_sizes:
            b.u8(value)
        for value in self.offsets:
            b.i8(value)
        b.i32(self.height).u32(self.props).i8(self.shadow_x).i8(self.shadow_y)
        b.u32(self.text_color).u32(self.underline_color).u32(self.shade_color).u32(self.shadow_color)
        if self.border_fill_id is not None:
            b.u16(self.border_fill_id)
            if self.strikeout_color is not None:
                b.u32(self.strikeout_color)
        return b.raw(self.extra).bytes()


@dataclass
class ParaShape:
    """A ``PARA_SHAPE`` record (42, 46, 54 or 58 bytes by version)."""

    props1: int = 0
    left: int = 0
    right: int = 0
    indent: int = 0
    prev: int = 0
    next: int = 0
    line_spacing_old: int = 160
    tab_def_id: int = 0
    numbering_id: int = 0
    border_fill_id: int = 0
    border_offsets: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    props2: int | None = 0
    props3: int | None = 0
    line_spacing: int | None = 160
    level: int | None = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "ParaShape":
        c = Cursor(payload, "PARA_SHAPE")
        shape = cls(
            c.u32(),
            c.i32(),
            c.i32(),
            c.i32(),
            c.i32(),
            c.i32(),
            c.i32(),
            c.u16(),
            c.u16(),
            c.u16(),
            [c.i16() for _ in range(4)],
        )
        shape.props2 = c.u32() if c.left >= 4 else None
        if c.left >= 8:
            shape.props3 = c.u32()
            shape.line_spacing = c.u32()
        else:
            shape.props3 = shape.line_spacing = None
        shape.level = c.u32() if c.left >= 4 else None
        shape.extra = c.rest()
        return shape

    def encode(self) -> bytes:
        b = Builder().u32(self.props1)
        for value in (self.left, self.right, self.indent, self.prev, self.next, self.line_spacing_old):
            b.i32(value)
        b.u16(self.tab_def_id).u16(self.numbering_id).u16(self.border_fill_id)
        for value in self.border_offsets:
            b.i16(value)
        if self.props2 is not None:
            b.u32(self.props2)
            if self.props3 is not None and self.line_spacing is not None:
                b.u32(self.props3).u32(self.line_spacing)
                if self.level is not None:
                    b.u32(self.level)
        return b.raw(self.extra).bytes()


# -- tabs, numbering, bullets ------------------------------------------------------


@dataclass
class TabItem:
    position: int
    kind: int
    fill: int
    reserved: int = 0


@dataclass
class TabDef:
    props: int = 0
    items: list[TabItem] = field(default_factory=list)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "TabDef":
        c = Cursor(payload, "TAB_DEF")
        tab = cls(c.u32())
        count = c.i32()
        tab.items = [TabItem(c.i32(), c.u8(), c.u8(), c.u16()) for _ in range(max(count, 0))]
        tab.extra = c.rest()
        return tab

    def encode(self) -> bytes:
        b = Builder().u32(self.props).i32(len(self.items))
        for item in self.items:
            b.i32(item.position).u8(item.kind).u8(item.fill).u16(item.reserved)
        return b.raw(self.extra).bytes()


@dataclass
class ParaHead:
    """``문단 머리 정보``: the head of one numbering level or of a bullet."""

    props: int = 0
    width_adjust: int = 0
    text_offset: int = 50
    char_shape_id: int = 0xFFFFFFFF
    format: str = ""

    @classmethod
    def read(cls, c: Cursor) -> "ParaHead":
        return cls(c.u32(), c.i16(), c.i16(), c.u32())

    def write(self, b: Builder) -> None:
        b.u32(self.props).i16(self.width_adjust).i16(self.text_offset).u32(self.char_shape_id)


@dataclass
class Numbering:
    """A ``NUMBERING`` record: seven levels, then (newer versions) three more."""

    heads: list[ParaHead] = field(default_factory=list)
    start: int = 1
    level_starts: list[int] | None = None
    extended_heads: list[ParaHead] = field(default_factory=list)
    extended_starts: list[int] | None = None
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Numbering":
        c = Cursor(payload, "NUMBERING")
        numbering = cls()
        for _ in range(7):
            head = ParaHead.read(c)
            head.format = c.wstr()
            numbering.heads.append(head)
        numbering.start = c.u16()
        if c.left >= 28:
            numbering.level_starts = [c.u32() for _ in range(7)]
        # Levels 8-10: a head and format each, then their start numbers.
        if c.left >= 3 * 14:
            probe = Cursor(payload[c.pos :], "NUMBERING")
            try:
                heads = []
                for _ in range(3):
                    head = ParaHead.read(probe)
                    head.format = probe.wstr()
                    heads.append(head)
                starts = [probe.u32() for _ in range(3)] if probe.left >= 12 else None
            except Exception:
                heads, starts = [], None
            if heads:
                numbering.extended_heads = heads
                numbering.extended_starts = starts
                c.pos += probe.pos
        numbering.extra = c.rest()
        return numbering

    def encode(self) -> bytes:
        b = Builder()
        for head in self.heads:
            head.write(b)
            b.wstr(head.format)
        b.u16(self.start)
        if self.level_starts is not None:
            for value in self.level_starts:
                b.u32(value)
        for head in self.extended_heads:
            head.write(b)
            b.wstr(head.format)
        if self.extended_starts is not None:
            for value in self.extended_starts:
                b.u32(value)
        return b.raw(self.extra).bytes()


@dataclass
class Bullet:
    """A ``BULLET`` record."""

    head: ParaHead = field(default_factory=ParaHead)
    char: int = 0xF0B7
    image_id: int | None = 0
    image_props: bytes = b"\0\0\0\0"
    check_char: int | None = 0
    tail: int | None = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Bullet":
        c = Cursor(payload, "BULLET")
        bullet = cls(ParaHead.read(c), c.u16(), None, b"", None, None)
        if c.left >= 8:
            bullet.image_id = c.i32()
            bullet.image_props = c.raw(4)
            if c.left >= 3:
                bullet.check_char = c.u16()
            if c.left >= 1:
                bullet.tail = c.u8()
        bullet.extra = c.rest()
        return bullet

    def encode(self) -> bytes:
        b = Builder()
        self.head.write(b)
        b.u16(self.char)
        if self.image_id is not None:
            b.i32(self.image_id).raw(self.image_props.ljust(4, b"\0")[:4])
            if self.check_char is not None:
                b.u16(self.check_char)
            if self.tail is not None:
                b.u8(self.tail)
        return b.raw(self.extra).bytes()


# -- styles, memo shapes, compatibility ----------------------------------------------


@dataclass
class Style:
    """``STYLE``: the names, kind and next style, the language (16 bits,
    which OWPML writes unsigned), the paragraph and character shapes and the
    form lock."""

    name: str = ""
    eng_name: str = ""
    props: int = 0
    next_id: int = 0
    lang_id: int = 1042
    para_shape_id: int = 0
    char_shape_id: int = 0
    lock_form: int | None = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Style":
        c = Cursor(payload, "STYLE")
        style = cls(c.wstr(), c.wstr(), c.u8(), c.u8(), c.u16(), c.u16(), c.u16())
        style.lock_form = c.u16() if c.left >= 2 else None
        style.extra = c.rest()
        return style

    def encode(self) -> bytes:
        b = Builder().wstr(self.name).wstr(self.eng_name).u8(self.props).u8(self.next_id)
        b.u16(self.lang_id & 0xFFFF).u16(self.para_shape_id).u16(self.char_shape_id)
        if self.lock_form is not None:
            b.u16(self.lock_form)
        return b.raw(self.extra).bytes()


@dataclass
class MemoShape:
    width: int = 0
    line_type: int = 0
    line_width: int = 0
    line_color: int = 0
    fill_color: int = 0
    active_color: int = 0
    memo_type: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "MemoShape":
        c = Cursor(payload, "MEMO_SHAPE")
        return cls(c.u32(), c.u8(), c.u8(), c.u32(), c.u32(), c.u32(), c.u32(), c.rest())

    def encode(self) -> bytes:
        return (
            Builder()
            .u32(self.width)
            .u8(self.line_type)
            .u8(self.line_width)
            .u32(self.line_color)
            .u32(self.fill_color)
            .u32(self.active_color)
            .u32(self.memo_type)
            .raw(self.extra)
            .bytes()
        )


@dataclass
class ForbiddenChars:
    """``FORBIDDEN_CHAR``: four lists of characters kept off the start or
    end of a line, as their lengths (u32 each) and then their characters.
    Hancom writes four empty lists unless the document sets its own."""

    words: tuple[str, str, str, str] = ("", "", "", "")
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "ForbiddenChars":
        c = Cursor(payload, "FORBIDDEN_CHAR")
        lengths = [c.u32() for _ in range(4)]
        texts = [c.raw(2 * n).decode("utf-16-le", errors="surrogatepass") for n in lengths]
        return cls((texts[0], texts[1], texts[2], texts[3]), c.rest())

    def encode(self) -> bytes:
        units = [word.encode("utf-16-le", errors="surrogatepass") for word in self.words]
        return struct.pack("<4I", *(len(u) // 2 for u in units)) + b"".join(units) + self.extra


@dataclass
class TrackChange:
    """``TRACK_CHANGE``: one tracked change: its kind (16 insertion, 17
    deletion, 19 paragraph shape), the local time it was made (year, month,
    day, hour, minute), its author (1 first), then five words. The fourth is
    whether an insertion or deletion is hidden, or the paragraph shape a
    paragraph shape change made."""

    kind: int = 16
    time: tuple[int, int, int, int, int] = (1970, 1, 1, 0, 0)
    author: int = 1
    words: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "TrackChange":
        c = Cursor(payload, "TRACK_CHANGE")
        value = cls(c.u32())
        value.time = (c.u16(), c.u16(), c.u16(), c.u16(), c.u16())
        value.author = c.u16()
        value.words = (c.u16(), c.u16(), c.u16(), c.u16(), c.u16())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.kind)
        for value in (*self.time, self.author, *self.words):
            b.u16(value)
        return b.raw(self.extra).bytes()


@dataclass
class TrackChangeAuthor:
    """``TRACK_CHANGE_AUTHOR``: the author's name, whether the author's
    changes are marked, then a word OWPML has no place for."""

    name: str = ""
    mark: int = 1
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "TrackChangeAuthor":
        c = Cursor(payload, "TRACK_CHANGE_AUTHOR")
        name = c.raw(2 * c.u32()).decode("utf-16-le", errors="replace")
        value = cls(name, c.u32())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        units = self.name.encode("utf-16-le", errors="surrogatepass")
        return Builder().u32(len(units) // 2).raw(units).u32(self.mark).raw(self.extra).bytes()


@dataclass
class DocInfo:
    """Every DocInfo record kind, decoded, in id order."""

    properties: DocumentProperties
    mappings: dict[str, int]
    bin_data: list[BinDataItem]
    fonts: dict[str, list[FaceName]]
    border_fills: list[BorderFill]
    char_shapes: list[CharShape]
    tab_defs: list[TabDef]
    numberings: list[Numbering]
    bullets: list[Bullet]
    para_shapes: list[ParaShape]
    styles: list[Style]
    memo_shapes: list[MemoShape]
    compatible_target: int | None
    layout_compatibility: list[int] | None
    other: list[rec.Record]


DECODERS = {
    rec.DOCUMENT_PROPERTIES: DocumentProperties.decode,
    rec.BIN_DATA: BinDataItem.decode,
    rec.FACE_NAME: FaceName.decode,
    rec.BORDER_FILL: BorderFill.decode,
    rec.CHAR_SHAPE: CharShape.decode,
    rec.TAB_DEF: TabDef.decode,
    rec.NUMBERING: Numbering.decode,
    rec.BULLET: Bullet.decode,
    rec.PARA_SHAPE: ParaShape.decode,
    rec.STYLE: Style.decode,
    rec.MEMO_SHAPE: MemoShape.decode,
}


def decode_docinfo(stream: rec.RecordStream) -> DocInfo:
    """Decode every id-mapped DocInfo record; keep the rest as records."""

    mappings = id_mappings(stream)
    properties = DocumentProperties()
    fonts: dict[str, list[FaceName]] = {lang: [] for lang in FONT_LANGS}
    font_counts = [mappings.get(f"font_{lang}", 0) for lang in FONT_LANGS]
    face_index = 0
    info = DocInfo(properties, mappings, [], fonts, [], [], [], [], [], [], [], [], None, None, [])
    for record in stream.records:
        tag = record.tag
        if tag == rec.DOCUMENT_PROPERTIES:
            info.properties = DocumentProperties.decode(record.payload)
        elif tag == rec.ID_MAPPINGS:
            continue
        elif tag == rec.BIN_DATA:
            info.bin_data.append(BinDataItem.decode(record.payload))
        elif tag == rec.FACE_NAME:
            lang_index = 0
            running = face_index
            while lang_index < len(font_counts) - 1 and running >= font_counts[lang_index]:
                running -= font_counts[lang_index]
                lang_index += 1
            fonts[FONT_LANGS[lang_index]].append(FaceName.decode(record.payload))
            face_index += 1
        elif tag == rec.BORDER_FILL:
            info.border_fills.append(BorderFill.decode(record.payload))
        elif tag == rec.CHAR_SHAPE:
            info.char_shapes.append(CharShape.decode(record.payload))
        elif tag == rec.TAB_DEF:
            info.tab_defs.append(TabDef.decode(record.payload))
        elif tag == rec.NUMBERING:
            info.numberings.append(Numbering.decode(record.payload))
        elif tag == rec.BULLET:
            info.bullets.append(Bullet.decode(record.payload))
        elif tag == rec.PARA_SHAPE:
            info.para_shapes.append(ParaShape.decode(record.payload))
        elif tag == rec.STYLE:
            info.styles.append(Style.decode(record.payload))
        elif tag == rec.MEMO_SHAPE:
            info.memo_shapes.append(MemoShape.decode(record.payload))
        elif tag == rec.COMPATIBLE_DOCUMENT and len(record.payload) >= 4:
            info.compatible_target = int(struct.unpack_from("<I", record.payload, 0)[0])
            info.other.append(record)
        elif tag == rec.LAYOUT_COMPATIBILITY and len(record.payload) >= 20:
            info.layout_compatibility = list(struct.unpack_from("<5I", record.payload, 0))
            info.other.append(record)
        else:
            info.other.append(record)
    return info
