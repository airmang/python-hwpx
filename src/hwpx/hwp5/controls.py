# SPDX-License-Identifier: Apache-2.0
"""Field codecs for the BodyText control records of an HWP 5.0 document.

Section and column definitions, page definition, footnote/endnote shape,
page border fill, the common header of objects (tables, pictures, shapes),
the ``TABLE`` record and the list header of a table cell. Reading and
writing use the same classes, so ``encode(decode(payload)) == payload``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import bodytext as bt
from .binary import Builder, Cursor


def _padded(payload: bytes, size: int) -> bytes:
    return payload if len(payload) >= size else payload.ljust(size, b"\0")


@dataclass
class SectionDef:
    """``secd``: the 47-byte section definition control header."""

    props: int = 0
    space_columns: int = 1134
    line_grid: int = 0
    char_grid: int = 0
    tab_stop: int = 8000
    outline_numbering: int = 1
    page_start: int = 0
    picture_start: int = 0
    table_start: int = 0
    equation_start: int = 0
    language: int = 0
    master_pages: int = 0
    reserved: int = 0
    memo_shape: int = 0
    text_direction: int = 0
    line_number_restart: int = 0
    line_number_count_by: int = 0
    line_number_distance: int = 0
    line_number_start: int = 0
    extra: bytes = b""
    raw_size: int | None = None

    @classmethod
    def decode(cls, payload: bytes) -> "SectionDef":
        c = Cursor(_padded(payload, 47), "secd")
        c.u32()
        value = cls(
            c.u32(), c.u16(), c.u16(), c.u16(), c.u32(), c.u16(), c.u16(), c.u16(), c.u16(), c.u16(),
            c.u16(), c.u16(), c.u16(), c.u16(), c.u16(), c.u8(), c.u16(), c.u32(), c.u16(),
        )
        value.extra = c.rest()
        value.raw_size = len(payload) if len(payload) < 47 else None
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("secd")).u32(self.props)
        b.u16(self.space_columns).u16(self.line_grid).u16(self.char_grid).u32(self.tab_stop)
        b.u16(self.outline_numbering).u16(self.page_start).u16(self.picture_start)
        b.u16(self.table_start).u16(self.equation_start).u16(self.language).u16(self.master_pages)
        b.u16(self.reserved).u16(self.memo_shape).u16(self.text_direction)
        b.u8(self.line_number_restart).u16(self.line_number_count_by)
        b.u32(self.line_number_distance).u16(self.line_number_start)
        out = b.raw(self.extra).bytes()
        return out[: self.raw_size] if self.raw_size is not None else out


@dataclass
class PageDef:
    width: int = 59528
    height: int = 84188
    left: int = 8504
    right: int = 8504
    top: int = 5668
    bottom: int = 4252
    header: int = 4252
    footer: int = 4252
    gutter: int = 0
    props: int = 0

    @classmethod
    def decode(cls, payload: bytes) -> "PageDef":
        return cls(*struct.unpack_from("<10I", _padded(payload, 40), 0))

    def encode(self) -> bytes:
        return struct.pack(
            "<10I",
            self.width,
            self.height,
            self.left,
            self.right,
            self.top,
            self.bottom,
            self.header,
            self.footer,
            self.gutter,
            self.props,
        )


@dataclass
class NoteShape:
    """``FOOTNOTE_SHAPE`` (used for both footnotes and endnotes)."""

    props: int = 0
    user_char: int = 0
    prefix_char: int = 0
    suffix_char: int = ord(")")
    start: int = 1
    line_length: int = -1
    above: int = 850
    below: int = 567
    between: int = 283
    line_type: int = 1
    line_width: int = 1
    line_color: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "NoteShape":
        c = Cursor(_padded(payload, 28), "FOOTNOTE_SHAPE")
        value = cls(
            c.u32(), c.u16(), c.u16(), c.u16(), c.u16(), c.i32(), c.u16(), c.u16(), c.u16(), c.u8(), c.u8(), c.u32()
        )
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        return (
            Builder()
            .u32(self.props)
            .u16(self.user_char)
            .u16(self.prefix_char)
            .u16(self.suffix_char)
            .u16(self.start)
            .i32(self.line_length)
            .u16(self.above)
            .u16(self.below)
            .u16(self.between)
            .u8(self.line_type)
            .u8(self.line_width)
            .u32(self.line_color)
            .raw(self.extra)
            .bytes()
        )


@dataclass
class PageBorderFill:
    props: int = 1
    offsets: tuple[int, int, int, int] = (1417, 1417, 1417, 1417)
    border_fill: int = 1
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "PageBorderFill":
        c = Cursor(_padded(payload, 14), "PAGE_BORDER_FILL")
        value = cls(c.u32(), (c.u16(), c.u16(), c.u16(), c.u16()), c.u16())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.props)
        for offset in self.offsets:
            b.u16(offset)
        return b.u16(self.border_fill).raw(self.extra).bytes()


@dataclass
class ColumnDef:
    """``cold``: column count, layout, gap, widths and separator line."""

    props: int = 0x1004
    gap: int = 0
    widths: list[int] = field(default_factory=list)
    props2: int = 0
    line_type: int = 0
    line_width: int = 0
    line_color: int = 0
    extra: bytes = b""

    @property
    def count(self) -> int:
        return ((self.props >> 2) & 0xFF) or 1

    @property
    def same_width(self) -> bool:
        return bool(self.props & (1 << 12))

    @classmethod
    def decode(cls, payload: bytes) -> "ColumnDef":
        c = Cursor(_padded(payload, 16), "cold")
        c.u32()
        value = cls(c.u16(), c.u16())
        if not value.same_width and value.count > 1:
            value.widths = [c.u16() for _ in range(min(value.count * 2 - 1, c.left // 2))]
        if c.left >= 8:
            value.props2 = c.u16()
            value.line_type = c.u8()
            value.line_width = c.u8()
            value.line_color = c.u32()
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("cold")).u16(self.props).u16(self.gap)
        for width in self.widths:
            b.u16(width)
        b.u16(self.props2).u8(self.line_type).u8(self.line_width).u32(self.line_color)
        return b.raw(self.extra).bytes()


@dataclass
class ObjectCommon:
    """The shared header of a table, picture, shape or equation control."""

    ctrl: str
    props: int = 0
    vert_offset: int = 0
    horz_offset: int = 0
    width: int = 0
    height: int = 0
    z_order: int = 0
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)
    instance_id: int = 0
    prevent_page_break: int = 0
    description: str | None = ""
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "ObjectCommon":
        c = Cursor(payload, "CTRL_HEADER")
        obj = cls(bt.ctrl_id(c.u32()))
        if c.left < 40:
            obj.extra = c.rest()
            return obj
        obj.props = c.u32()
        obj.vert_offset = c.i32()
        obj.horz_offset = c.i32()
        obj.width = c.u32()
        obj.height = c.u32()
        obj.z_order = c.i32()
        obj.margins = (c.i16(), c.i16(), c.i16(), c.i16())
        obj.instance_id = c.u32()
        obj.prevent_page_break = c.i32() if c.left >= 4 else 0
        obj.description = c.wstr() if c.left >= 2 else None
        obj.extra = c.rest()
        return obj

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word(self.ctrl)).u32(self.props).i32(self.vert_offset).i32(self.horz_offset)
        b.u32(self.width).u32(self.height).i32(self.z_order)
        for margin in self.margins:
            b.i16(margin)
        b.u32(self.instance_id).i32(self.prevent_page_break)
        if self.description is not None:
            b.wstr(self.description)
        return b.raw(self.extra).bytes()


@dataclass
class TableProps:
    """The ``TABLE`` record: grid, spacing, inner margins, rows, zones."""

    props: int = 0
    rows: int = 1
    cols: int = 1
    spacing: int = 0
    inner: tuple[int, int, int, int] = (510, 510, 141, 141)
    row_sizes: list[int] = field(default_factory=list)
    border_fill: int = 1
    zones: list[tuple[int, int, int, int, int]] = field(default_factory=list)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "TableProps":
        c = Cursor(payload, "TABLE")
        value = cls(c.u32(), c.u16(), c.u16(), c.u16(), (c.u16(), c.u16(), c.u16(), c.u16()))
        value.row_sizes = [c.u16() for _ in range(min(value.rows, c.left // 2))]
        value.border_fill = c.u16() if c.left >= 2 else 0
        if c.left >= 2:
            count = c.u16()
            for _ in range(min(count, c.left // 10)):
                value.zones.append((c.u16(), c.u16(), c.u16(), c.u16(), c.u16()))
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.props).u16(self.rows).u16(self.cols).u16(self.spacing)
        for margin in self.inner:
            b.u16(margin)
        for size in self.row_sizes:
            b.u16(size)
        b.u16(self.border_fill).u16(len(self.zones))
        for zone in self.zones:
            for value in zone:
                b.u16(value)
        return b.raw(self.extra).bytes()


#: A named cell stores its name as a one-item parameter set after the width.
CELL_NAME_PREFIX = bytes.fromhex("ff1b020100000000400100")


@dataclass
class CellHeader:
    """The ``LIST_HEADER`` of a table cell.

    The list part is a paragraph count and a property word (text direction in
    bits 16-18, line wrap in bits 19-20, vertical alignment in bits 21-22),
    then the cell flags (0x1 own margins, 0x2 protect, 0x4 header row,
    0x8 editable in form mode, 0x10 dirty), address, span, size, margins,
    border fill, a width, and either nine zero bytes or the cell's name.
    """

    paragraphs: int = 1
    list_props: int = 0x00200000
    flags: int = 0
    col: int = 0
    row: int = 0
    col_span: int = 1
    row_span: int = 1
    width: int = 0
    height: int = 0
    margins: tuple[int, int, int, int] = (510, 510, 141, 141)
    border_fill: int = 1
    text_width: int = 0
    name: str = ""
    tail: bytes = b"\0" * 9
    raw_size: int | None = None

    @classmethod
    def decode(cls, payload: bytes) -> "CellHeader":
        c = Cursor(_padded(payload, 38), "cell")
        value = cls(c.u16(), c.u32(), c.u16(), c.u16(), c.u16(), c.u16(), c.u16(), c.u32(), c.u32())
        value.margins = (c.i16(), c.i16(), c.i16(), c.i16())
        value.border_fill = c.u16()
        value.text_width = c.u32()
        rest = c.rest()
        if rest.startswith(CELL_NAME_PREFIX) and len(rest) >= len(CELL_NAME_PREFIX) + 2:
            nc = Cursor(rest[len(CELL_NAME_PREFIX) :], "cell name")
            value.name = nc.wstr()
            value.tail = nc.rest()
        else:
            value.tail = rest
        value.raw_size = len(payload) if len(payload) < 38 else None
        return value

    def encode(self) -> bytes:
        b = Builder().u16(self.paragraphs).u32(self.list_props).u16(self.flags)
        b.u16(self.col).u16(self.row).u16(self.col_span).u16(self.row_span).u32(self.width).u32(self.height)
        for margin in self.margins:
            b.i16(margin)
        b.u16(self.border_fill).u32(self.text_width)
        if self.name:
            b.raw(CELL_NAME_PREFIX).wstr(self.name)
        b.raw(self.tail)
        out = b.bytes()
        return out[: self.raw_size] if self.raw_size is not None else out


@dataclass
class CaptionHeader:
    """The ``LIST_HEADER`` of an object caption (it precedes the ``TABLE`` record).

    Side in bits 0-1 of the caption word (0 left, 1 right, 2 top, 3 bottom)
    and full-size in bit 2, then width, gap and the last width.
    """

    paragraphs: int = 1
    list_props: int = 0
    flags: int = 0
    props: int = 3
    width: int = 8504
    gap: int = 850
    last_width: int = 0
    tail: bytes = bytes(8)

    @classmethod
    def decode(cls, payload: bytes) -> "CaptionHeader":
        c = Cursor(_padded(payload, 22), "caption")
        value = cls(c.u16(), c.u32(), c.u16(), c.u32(), c.u32(), c.u16(), c.u32())
        value.tail = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u16(self.paragraphs).u32(self.list_props).u16(self.flags).u32(self.props)
        return b.u32(self.width).u16(self.gap).u32(self.last_width).raw(self.tail).bytes()


@dataclass
class ListHeader:
    """The ``LIST_HEADER`` of a header, footer or note body: the paragraph
    count and the list property word; the rest is kept as it is."""

    paragraphs: int = 1
    props: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "ListHeader":
        c = Cursor(_padded(payload, 6), "LIST_HEADER")
        value = cls(c.u16(), c.u32())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        return Builder().u16(self.paragraphs).u32(self.props).raw(self.extra).bytes()

    @property
    def text_size(self) -> tuple[int, int]:
        """Text width and height of a header or footer body (zero for notes)."""

        if len(self.extra) >= 10:
            width, height = struct.unpack_from("<II", self.extra, 2)
            return int(width), int(height)
        return 0, 0


@dataclass
class HeaderFooterCtrl:
    """``head``/``foot``: the page type it applies to and its number."""

    ctrl: str = "head"
    props: int = 0
    number: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "HeaderFooterCtrl":
        c = Cursor(_padded(payload, 12), "head")
        value = cls(bt.ctrl_id(c.u32()), c.u32(), c.u32())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        return Builder().u32(bt.ctrl_word(self.ctrl)).u32(self.props).u32(self.number).raw(self.extra).bytes()


@dataclass
class NoteCtrl:
    """``fn  ``/``en  ``: note number, the characters around it and its instance id."""

    ctrl: str = "fn  "
    number: int = 1
    prefix_char: int = 0
    suffix_char: int = ord(")")
    reserved: int = 0
    instance_id: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "NoteCtrl":
        c = Cursor(_padded(payload, 20), "note")
        value = cls(bt.ctrl_id(c.u32()), c.u32(), c.u16(), c.u16(), c.u32(), c.u32())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word(self.ctrl)).u32(self.number).u16(self.prefix_char)
        return b.u16(self.suffix_char).u32(self.reserved).u32(self.instance_id).raw(self.extra).bytes()
