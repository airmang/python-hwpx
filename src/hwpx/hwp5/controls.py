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
from . import docinfo as di
from .binary import Builder, Cursor
from .errors import Hwp5Error, damaged


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
    # Master pages kept on the section's last paragraph (last page, optional
    # pages); those for both, even and odd pages are marked by props bits 29-31.
    last_paragraph_pages: int = 0
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
        b.u16(self.table_start).u16(self.equation_start).u16(self.language).u16(self.last_paragraph_pages)
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


@dataclass
class FieldCtrl:
    """A field control (``%hlk``, ``%clk``, ``%fmu``, ...).

    Properties (bit 0 editable in form mode, bit 15 dirty), one more property
    byte, the command string, the field's id and a word that carries a memo's
    z-order.
    """

    ctrl: str = "%unk"
    props: int = 0
    extra: int = 0
    command: str = ""
    instance_id: int = 0
    z_order: int = 0
    tail: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "FieldCtrl":
        c = Cursor(_padded(payload, 11), "field")
        value = cls(bt.ctrl_id(c.u32()), c.u32(), c.u8(), c.wstr())
        value.instance_id = c.u32() if c.left >= 4 else 0
        value.z_order = c.i32() if c.left >= 4 else 0
        value.tail = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word(self.ctrl)).u32(self.props).u8(self.extra).wstr(self.command)
        return b.u32(self.instance_id).i32(self.z_order).raw(self.tail).bytes()


#: A one-item parameter set naming a cell or a field.
NAME_SET_PREFIX = bytes.fromhex("1b020100000000400100")


def parameter_set_name(payload: bytes) -> str:
    """The name stored in a ``CTRL_DATA`` parameter set (empty when it holds none)."""

    if payload.startswith(NAME_SET_PREFIX) and len(payload) >= len(NAME_SET_PREFIX) + 2:
        return Cursor(payload[len(NAME_SET_PREFIX) :], "CTRL_DATA").wstr()
    return ""


def name_parameter_set(name: str) -> bytes:
    """The ``CTRL_DATA`` payload that names a field."""

    return Builder().raw(NAME_SET_PREFIX).wstr(name).bytes()


#: Attributes of ``hp:label`` (a label sheet's layout), by parameter item id
#: from 0x4000 up.
LABEL_ITEMS = (
    "topmargin",
    "leftmargin",
    "boxwidth",
    "boxlength",
    "boxmarginhor",
    "boxmarginver",
    "labelcols",
    "labelrows",
    "landscape",
    "pagewidth",
    "pageheight",
)
#: A one-item parameter set holding the label set, up to the label set's item count.
LABEL_SET_PREFIX = bytes.fromhex("1b0201000000420200804202")


def label_items(payload: bytes) -> dict[int, int] | None:
    """The integer items of a label sheet layout in a table's ``CTRL_DATA``, by
    item id; None when the record holds something else."""

    if not payload.startswith(LABEL_SET_PREFIX):
        return None
    c = Cursor(payload[len(LABEL_SET_PREFIX) :], "label")
    if c.left < 4:
        return None
    count = c.i16()
    c.u16()
    items: dict[int, int] = {}
    for _ in range(count):
        if c.left < 8:
            return None
        item, kind = c.u16(), c.u16()
        if not 2 <= kind <= 9:  # an integer item; each takes four bytes here
            return None
        items[item] = c.i32()
    return items if c.left == 0 else None


def label_values(payload: bytes) -> dict[str, int] | None:
    """The label sheet layout by ``hp:label`` attribute; None when the record
    holds something else. Items with no attribute are left out."""

    items = label_items(payload)
    if items is None:
        return None
    return {name: items[0x4000 + index] for index, name in enumerate(LABEL_ITEMS) if 0x4000 + index in items}


def label_parameter_set(values: dict[str, int]) -> bytes:
    """The ``CTRL_DATA`` payload of a label sheet layout; items go from the last id down."""

    b = Builder().raw(LABEL_SET_PREFIX).i16(len(LABEL_ITEMS)).u16(0)
    for index in reversed(range(len(LABEL_ITEMS))):
        b.u16(0x4000 + index).u16(4).i32(values.get(LABEL_ITEMS[index], 0))
    return b.bytes()


#: Parameter item types: a string, signed and unsigned integers, a nested
#: set, an array (whose values each carry their own type) and binary data.
PIT_BSTR = 1
PIT_SIGNED = frozenset({2, 3, 4, 5})
PIT_UNSIGNED = frozenset({6, 7, 8, 9})
PIT_SET = 0x8000
PIT_ARRAY = 0x8001
PIT_BINARY = 0x8002


@dataclass
class ParameterItem:
    item_id: int
    kind: int
    value: "str | int | bytes | ParameterSet | ParameterArray"


@dataclass
class ParameterArray:
    """An array item: a count, a reserved word, then each value with its type."""

    values: list[tuple[int, "str | int | bytes | ParameterSet | ParameterArray"]] = field(default_factory=list)
    reserved: int = 0


@dataclass
class ParameterSet:
    """A ``CTRL_DATA`` parameter set: its id and items (strings, 32-bit
    integers, nested sets, arrays and binary data)."""

    set_id: int = 0
    items: list[ParameterItem] = field(default_factory=list)
    reserved: int = 0

    @classmethod
    def read(cls, c: Cursor) -> "ParameterSet":
        value = cls(c.u16())
        count = c.i16()
        value.reserved = c.u16()
        for _ in range(max(count, 0)):
            item_id, kind = c.u16(), c.u16()
            value.items.append(ParameterItem(item_id, kind, _read_value(c, kind)))
        return value

    @classmethod
    def decode(cls, payload: bytes) -> "ParameterSet | None":
        """The set a ``CTRL_DATA`` record holds; None when it holds more or something else."""

        c = Cursor(payload, "CTRL_DATA")
        try:
            value = cls.read(c)
        except Hwp5Error:
            return None
        return value if c.left == 0 else None

    def write(self, b: Builder) -> None:
        b.u16(self.set_id).i16(len(self.items)).u16(self.reserved)
        for item in self.items:
            b.u16(item.item_id).u16(item.kind)
            _write_value(b, item.kind, item.value)

    def encode(self) -> bytes:
        b = Builder()
        self.write(b)
        return b.bytes()

    def plain(self) -> bool:
        """Whether the set holds only strings, integers and plain nested sets,
        which is what ``hp:parameterset`` can hold."""

        return all(
            isinstance(item.value, (str, int)) or (isinstance(item.value, ParameterSet) and item.value.plain())
            for item in self.items
        )

    def find(self, *path: int) -> "str | int | bytes | ParameterSet | ParameterArray | None":
        """The value at a path of item ids through nested sets."""

        current: str | int | bytes | ParameterSet | ParameterArray | None = self
        for item_id in path:
            if not isinstance(current, ParameterSet):
                return None
            current = next((item.value for item in current.items if item.item_id == item_id), None)
        return current


def _read_value(c: Cursor, kind: int) -> "str | int | bytes | ParameterSet | ParameterArray":
    if kind == PIT_BSTR:
        return c.wstr()
    if kind in PIT_SIGNED:
        return c.i32()
    if kind in PIT_UNSIGNED:
        return c.u32()
    if kind == PIT_SET:
        return ParameterSet.read(c)
    if kind == PIT_ARRAY:
        count, reserved = c.u16(), c.u16()
        values: list[tuple[int, str | int | bytes | ParameterSet | ParameterArray]] = []
        for _ in range(count):
            value_kind = c.u16()
            values.append((value_kind, _read_value(c, value_kind)))
        return ParameterArray(values, reserved)
    if kind == PIT_BINARY:
        return c.raw(c.u16())
    raise damaged("CTRL_DATA has a parameter item of an unknown type", kind=kind)


def _write_value(b: Builder, kind: int, value: "str | int | bytes | ParameterSet | ParameterArray") -> None:
    if isinstance(value, ParameterSet):
        value.write(b)
    elif isinstance(value, ParameterArray):
        b.u16(len(value.values)).u16(value.reserved)
        for value_kind, item in value.values:
            b.u16(value_kind)
            _write_value(b, value_kind, item)
    elif isinstance(value, bytes):
        b.u16(len(value)).raw(value)
    elif isinstance(value, str):
        b.wstr(value)
    elif kind in PIT_UNSIGNED:
        b.u32(value)
    else:
        b.i32(value - (1 << 32) if value >= 1 << 31 else value)


#: Presentation settings, the parameter set of a section definition: the
#: outer set holds the settings set, which holds the fill set.
PRESENTATION = 0x021B
PRESENTATION_SETTINGS = 0x0219
PRESENTATION_FILL = 0x0266
#: Items of the settings set: effect, sound, inverted text, automatic show,
#: what the settings apply to and the show time; 0x7001 has no OWPML form.
_SETTINGS_ITEMS = frozenset({0x4000, 0x4001, 0x4002, 0x4003, 0x4004, 0x4005, 0x7001, PRESENTATION_FILL})
#: Values an array of the fill set has room for (colours, positions).
_FILL_SLOTS = 10


@dataclass
class Presentation:
    """Presentation settings: the screen change effect, sound, inverted text,
    automatic show, what they apply to, the show time and the background
    fill (solid or gradation). :meth:`parameter_set` lays the items out the
    way Hancom writes them."""

    effect: int = 0
    sound: bytes = b""
    invert_text: int = 0
    autoshow: int = 0
    apply_to: int = 0
    show_time: int = 0
    fill: di.Fill = field(default_factory=di.Fill)

    @classmethod
    def from_set(cls, ps: ParameterSet) -> "Presentation | None":
        """The settings *ps* holds; None when it holds something else, an item
        this codec does not know or a fill it has no layout for."""

        settings = ps.find(PRESENTATION_SETTINGS)
        if ps.set_id != PRESENTATION or len(ps.items) != 1 or not isinstance(settings, ParameterSet):
            return None
        items = {item.item_id: item.value for item in settings.items}
        fill = items.get(PRESENTATION_FILL)
        sound = items.get(0x4001, b"")
        if not set(items) <= _SETTINGS_ITEMS or not isinstance(fill, ParameterSet) or not isinstance(sound, bytes):
            return None
        background = _presentation_fill(fill)
        if background is None:
            return None
        return cls(
            _number(items, 0x4000),
            sound,
            _number(items, 0x4002),
            _number(items, 0x4003),
            _number(items, 0x4004),
            _number(items, 0x4005) & 0xFFFFFFFF,
            background,
        )

    def parameter_set(self) -> ParameterSet:
        """The settings as a parameter set; the fill must be solid or a
        gradation of at most ten colours, and there is no sound."""

        fill = self.fill
        alpha = fill.alphas[0] if fill.alphas else 0
        if fill.kind == di.FILL_SOLID:
            fill_items = [
                ParameterItem(0x4001, 9, di.FILL_SOLID),
                ParameterItem(0x4018, 6, alpha),
                ParameterItem(0x4016, 5, fill.pattern_type),
                ParameterItem(0x4015, 9, fill.pattern_color & 0xFFFFFFFF),
                ParameterItem(0x4014, 9, fill.back_color & 0xFFFFFFFF),
                ParameterItem(0x402F, 6, 1),
                ParameterItem(0x4031, 6, 0),
                ParameterItem(0x4030, 6, 0),
            ]
        else:
            count = len(fill.grad_colors)
            positions = fill.grad_positions if count > 2 else []
            fill_items = [
                ParameterItem(0x400B, 6, alpha),
                ParameterItem(0x400A, 6, fill.additional[0] if fill.additional else 50),
                ParameterItem(0x4009, PIT_ARRAY, _slots(positions)),
                ParameterItem(0x4008, PIT_ARRAY, _slots(fill.grad_colors)),
                ParameterItem(0x4007, 5, count),
                ParameterItem(0x4006, 5, fill.grad_step),
                ParameterItem(0x4005, 5, fill.grad_center_y),
                ParameterItem(0x4004, 5, fill.grad_center_x),
                ParameterItem(0x4003, 5, fill.grad_angle),
                ParameterItem(0x4002, 5, fill.grad_type),
                ParameterItem(0x4001, 9, di.FILL_GRADATION),
                ParameterItem(0x402F, 6, 0),
                ParameterItem(0x4031, 6, 0),
                ParameterItem(0x4030, 6, 1),
            ]
        settings = [
            ParameterItem(0x4004, 9, self.apply_to),
            ParameterItem(0x4005, 9, self.show_time & 0xFFFFFFFF),
            ParameterItem(0x4003, 5, self.autoshow),
            ParameterItem(0x4002, 5, self.invert_text),
            ParameterItem(0x4000, 9, self.effect),
            ParameterItem(PRESENTATION_FILL, PIT_SET, ParameterSet(PRESENTATION_FILL, fill_items)),
        ]
        inner = ParameterSet(PRESENTATION_SETTINGS, settings)
        return ParameterSet(PRESENTATION, [ParameterItem(PRESENTATION_SETTINGS, PIT_SET, inner)])


def _number(items: dict[int, "str | int | bytes | ParameterSet | ParameterArray"], key: int, default: int = 0) -> int:
    value = items.get(key, default)
    return value if isinstance(value, int) else default


def _slots(values: list[int]) -> ParameterArray:
    slots: list[tuple[int, str | int | bytes | ParameterSet | ParameterArray]] = [(5, value & 0xFFFFFFFF) for value in values]
    return ParameterArray(slots + [(5, 0)] * (_FILL_SLOTS - len(values)))


def _presentation_fill(ps: ParameterSet) -> di.Fill | None:
    """A solid or gradation fill from the fill set; None for any other fill,
    an image or a gradation whose colours the set does not hold."""

    items = {item.item_id: item.value for item in ps.items}
    kind = _number(items, 0x4001)
    if ps.set_id != PRESENTATION_FILL or kind not in (di.FILL_SOLID, di.FILL_GRADATION) or items.get(0x401E, b"") != b"":
        return None
    fill = di.Fill(kind)
    if kind == di.FILL_SOLID:
        fill.back_color = _number(items, 0x4014, 0xFFFFFF) & 0xFFFFFFFF
        fill.pattern_color = _number(items, 0x4015) & 0xFFFFFFFF
        fill.pattern_type = _number(items, 0x4016, -1)
        fill.alphas = bytes([_number(items, 0x4018) & 0xFF])
        return fill
    colors, positions, count = items.get(0x4008), items.get(0x4009), _number(items, 0x4007)
    if not isinstance(colors, ParameterArray) or not 0 <= count <= len(colors.values):
        return None
    fill.grad_type = _number(items, 0x4002)
    fill.grad_angle = _number(items, 0x4003)
    fill.grad_center_x = _number(items, 0x4004)
    fill.grad_center_y = _number(items, 0x4005)
    fill.grad_step = _number(items, 0x4006)
    fill.grad_colors = [value & 0xFFFFFFFF if isinstance(value, int) else 0 for _, value in colors.values[:count]]
    if count > 2 and isinstance(positions, ParameterArray):
        fill.grad_positions = [value if isinstance(value, int) else 0 for _, value in positions.values[:count]]
    fill.additional = bytes([_number(items, 0x400A, 50) & 0xFF])
    fill.alphas = bytes([_number(items, 0x400B) & 0xFF])
    return fill


@dataclass
class PageNumberPosition:
    """``pgnp``: number format (bits 0-7) and position (bits 8-11), then the
    user, prefix, suffix and side characters."""

    props: int = 0
    user_char: int = 0
    prefix_char: int = 0
    suffix_char: int = 0
    side_char: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "PageNumberPosition":
        c = Cursor(_padded(payload, 16), "pgnp")
        c.u32()
        value = cls(c.u32(), c.u16(), c.u16(), c.u16(), c.u16())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("pgnp")).u32(self.props).u16(self.user_char).u16(self.prefix_char)
        return b.u16(self.suffix_char).u16(self.side_char).raw(self.extra).bytes()


@dataclass
class PageHiding:
    """``pghd``: bits 0-5 hide the header, footer, master page, border, fill and page number."""

    props: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "PageHiding":
        c = Cursor(_padded(payload, 8), "pghd")
        c.u32()
        return cls(c.u32(), c.rest())

    def encode(self) -> bytes:
        return Builder().u32(bt.ctrl_word("pghd")).u32(self.props).raw(self.extra).bytes()


@dataclass
class NewNumber:
    """``nwno``: the kind of number (bits 0-3) and the number to start from."""

    props: int = 0
    number: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "NewNumber":
        c = Cursor(_padded(payload, 10), "nwno")
        c.u32()
        return cls(c.u32(), c.u16(), c.rest())

    def encode(self) -> bytes:
        return Builder().u32(bt.ctrl_word("nwno")).u32(self.props).u16(self.number).raw(self.extra).bytes()


@dataclass
class AutoNumber:
    """``atno``: kind (bits 0-3), number format (bits 4-11) and superscript
    (bit 12); then the number and the user, prefix and suffix characters."""

    props: int = 0
    number: int = 0
    user_char: int = 0
    prefix_char: int = 0
    suffix_char: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "AutoNumber":
        c = Cursor(_padded(payload, 16), "atno")
        c.u32()
        value = cls(c.u32(), c.u16(), c.u16(), c.u16(), c.u16())
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("atno")).u32(self.props).u16(self.number).u16(self.user_char)
        return b.u16(self.prefix_char).u16(self.suffix_char).raw(self.extra).bytes()


@dataclass
class IndexMark:
    """``idxm``: the first and second keys, then four reserved bytes."""

    first: str = ""
    second: str = ""
    extra: bytes = bytes(4)

    @classmethod
    def decode(cls, payload: bytes) -> "IndexMark":
        c = Cursor(_padded(payload, 8), "idxm")
        c.u32()
        first = c.wstr()
        second = c.wstr() if c.left >= 2 else ""
        return cls(first, second, c.rest())

    def encode(self) -> bytes:
        return Builder().u32(bt.ctrl_word("idxm")).wstr(self.first).wstr(self.second).raw(self.extra).bytes()


@dataclass
class Dutmal:
    """``tdut``: the main and the sub text, then position, size ratio, option,
    style id and alignment."""

    main_text: str = ""
    sub_text: str = ""
    position: int = 0
    size_ratio: int = 0
    option: int = 0
    style_id: int = 0
    align: int = 0
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Dutmal":
        c = Cursor(_padded(payload, 8), "tdut")
        c.u32()
        main_text, sub_text = c.wstr(), c.wstr() if c.left >= 2 else ""
        t = Cursor(_padded(c.rest(), 20), "tdut")
        value = cls(main_text, sub_text, t.u32(), t.u32(), t.u32(), t.u32(), t.u32())
        value.extra = t.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("tdut")).wstr(self.main_text).wstr(self.sub_text).u32(self.position)
        return b.u32(self.size_ratio).u32(self.option).u32(self.style_id).u32(self.align).raw(self.extra).bytes()


#: A char shape place of an overlapped character that has none of its own.
NO_CHAR_SHAPE = 0xFFFFFFFF


@dataclass
class Compose:
    """``tcps``: the characters set over each other, the frame around them,
    the size step of the characters inside it (signed), whether they spread
    or overlap, then the char shape of each place (Hancom keeps ten)."""

    text: str = ""
    circle: int = 1
    size: int = 0
    kind: int = 0
    char_shapes: list[int] = field(default_factory=lambda: [NO_CHAR_SHAPE] * 10)
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "Compose":
        c = Cursor(_padded(payload, 6), "tcps")
        c.u32()
        text = c.wstr()
        t = Cursor(_padded(c.rest(), 4), "tcps")
        value = cls(text, t.u8(), t.i8(), t.u8())
        count = t.u8()
        value.char_shapes = [t.u32() for _ in range(min(count, t.left // 4))]
        value.extra = t.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(bt.ctrl_word("tcps")).wstr(self.text).u8(self.circle).i8(self.size).u8(self.kind)
        b.u8(len(self.char_shapes))
        for shape in self.char_shapes:
            b.u32(shape)
        return b.raw(self.extra).bytes()


#: One item of a form's property text: its key, type (``wstring``, ``int``,
#: ``bool``) and value.
FormItem = tuple[str, str, str]


@dataclass
class FormObject:
    """``FORM_OBJECT``: the form's kind (twice), then its properties as text:
    sets written ``Name:set:<length>:<items> ``, each item ``Key:type:value ``
    (a ``wstring`` value is preceded by its length)."""

    kind: str = "+cbt"
    sets: list[tuple[str, list[FormItem]]] = field(default_factory=list)

    @classmethod
    def decode(cls, payload: bytes) -> "FormObject":
        c = Cursor(payload, "FORM_OBJECT")
        value = cls(bt.ctrl_id(c.u32()))
        c.u32()
        c.u32()
        text = c.wstr()
        position = 0
        while position < len(text):
            if text[position] == " ":
                position += 1
                continue
            name, kind, length, _ = text[position:].split(":", 3)
            if kind != "set" or not length.isdigit():
                raise damaged("A form's property text is not a list of sets.", kind=kind)
            start = position + len(name) + len(kind) + len(length) + 3
            value.sets.append((name, _form_items(text[start : start + int(length)])))
            position = start + int(length)
        return value

    def items(self) -> dict[str, dict[str, str]]:
        return {name: {key: item for key, _, item in items} for name, items in self.sets}

    def encode(self) -> bytes:
        text = ""
        for name, items in self.sets:
            body = "".join(
                f"{key}:{kind}:{len(item)}:{item} " if kind == "wstring" else f"{key}:{kind}:{item} "
                for key, kind, item in items
            )
            text += f"{name}:set:{len(body)}:{body} "
        word = bt.ctrl_word(self.kind)
        return Builder().u32(word).u32(word).u32(len(text)).wstr(text).bytes()


def _form_items(body: str) -> list[FormItem]:
    items: list[FormItem] = []
    while body:
        key, kind, rest = body.split(":", 2)
        if kind == "wstring":
            length, _, rest = rest.partition(":")
            items.append((key, kind, rest[: int(length)]))
            body = rest[int(length) + 1 :]
        else:
            item, _, body = rest.partition(" ")
            items.append((key, kind, item))
    return items


#: What Hancom writes for an equation whose record leaves these out.
EQUATION_VERSION = "Equation Version 60"
EQUATION_FONT = "HYhwpEQ"


@dataclass
class EquationEdit:
    """``EQEDIT``: properties (bit 0: line mode), the script, the base unit
    (character size), colour, baseline, then the version and the font, which
    older records leave out."""

    props: int = 0
    script: str = ""
    base_unit: int = 1000
    color: int = 0
    baseline: int = 0
    version: str | None = EQUATION_VERSION
    font: str | None = EQUATION_FONT
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "EquationEdit":
        c = Cursor(payload, "EQEDIT")
        value = cls(c.u32(), c.wstr(), c.u32(), c.u32(), c.i32())
        value.version = c.wstr() if c.left >= 2 else None
        value.font = c.wstr() if value.version is not None and c.left >= 2 else None
        value.extra = c.rest()
        return value

    def encode(self) -> bytes:
        b = Builder().u32(self.props).wstr(self.script).u32(self.base_unit).u32(self.color).i32(self.baseline)
        if self.version is not None:
            b.wstr(self.version)
            if self.font is not None:
                b.wstr(self.font)
        return b.raw(self.extra).bytes()
