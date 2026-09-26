# SPDX-License-Identifier: Apache-2.0
"""HWP 5.0 data records: the tagged, levelled units of DocInfo and BodyText.

Every record starts with a 32-bit header: the tag in bits 0-9, the level in
bits 10-19 and the payload size in bits 20-31. A size of ``0xFFF`` means the
real size follows as another 32-bit word. A record belongs to the nearest
earlier record one level up, which makes the stream a tree.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .errors import damaged, limit_exceeded, write_unsupported

BEGIN = 0x010

# DocInfo
DOCUMENT_PROPERTIES = BEGIN
ID_MAPPINGS = BEGIN + 1
BIN_DATA = BEGIN + 2
FACE_NAME = BEGIN + 3
BORDER_FILL = BEGIN + 4
CHAR_SHAPE = BEGIN + 5
TAB_DEF = BEGIN + 6
NUMBERING = BEGIN + 7
BULLET = BEGIN + 8
PARA_SHAPE = BEGIN + 9
STYLE = BEGIN + 10
DOC_DATA = BEGIN + 11
DISTRIBUTE_DOC_DATA = BEGIN + 12
COMPATIBLE_DOCUMENT = BEGIN + 14
LAYOUT_COMPATIBILITY = BEGIN + 15
TRACKCHANGE = BEGIN + 16
MEMO_SHAPE = BEGIN + 76
FORBIDDEN_CHAR = BEGIN + 78
TRACK_CHANGE = BEGIN + 80
TRACK_CHANGE_AUTHOR = BEGIN + 81

# BodyText
PARA_HEADER = BEGIN + 50
PARA_TEXT = BEGIN + 51
PARA_CHAR_SHAPE = BEGIN + 52
PARA_LINE_SEG = BEGIN + 53
PARA_RANGE_TAG = BEGIN + 54
CTRL_HEADER = BEGIN + 55
LIST_HEADER = BEGIN + 56
PAGE_DEF = BEGIN + 57
FOOTNOTE_SHAPE = BEGIN + 58
PAGE_BORDER_FILL = BEGIN + 59
SHAPE_COMPONENT = BEGIN + 60
TABLE = BEGIN + 61
SHAPE_COMPONENT_LINE = BEGIN + 62
SHAPE_COMPONENT_RECTANGLE = BEGIN + 63
SHAPE_COMPONENT_ELLIPSE = BEGIN + 64
SHAPE_COMPONENT_ARC = BEGIN + 65
SHAPE_COMPONENT_POLYGON = BEGIN + 66
SHAPE_COMPONENT_CURVE = BEGIN + 67
SHAPE_COMPONENT_OLE = BEGIN + 68
SHAPE_COMPONENT_PICTURE = BEGIN + 69
SHAPE_COMPONENT_CONTAINER = BEGIN + 70
CTRL_DATA = BEGIN + 71
EQEDIT = BEGIN + 72
SHAPE_COMPONENT_TEXTART = BEGIN + 74
FORM_OBJECT = BEGIN + 75
MEMO_LIST = BEGIN + 77
CHART_DATA = BEGIN + 79
VIDEO_DATA = BEGIN + 82
SHAPE_COMPONENT_UNKNOWN = BEGIN + 99

TAG_NAMES: dict[int, str] = {
    value: name
    for name, value in list(globals().items())
    if name.isupper() and isinstance(value, int) and name not in ("BEGIN",)
}

MAX_RECORDS = 4_000_000
MAX_INFLATED_BYTES = 256 * 1024 * 1024
_HEADER = struct.Struct("<I")


@dataclass
class Record:
    """One record and the records nested under it."""

    tag: int
    level: int
    payload: bytes
    children: list["Record"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return TAG_NAMES.get(self.tag, f"TAG_{self.tag}")

    def walk(self) -> Iterator["Record"]:
        """This record and every record below it, in stream order."""

        stack: list[Record] = [self]
        while stack:
            record = stack.pop()
            yield record
            stack.extend(reversed(record.children))


@dataclass
class RecordStream:
    """The records of one stream: a flat list in order and the tree roots."""

    records: list[Record]
    roots: list[Record]
    level_jumps: int = 0


def inflate(data: bytes, what: str) -> bytes:
    """Decompress a raw-deflate stream, bounded by :data:`MAX_INFLATED_BYTES`."""

    inflater = zlib.decompressobj(-15)
    try:
        out = inflater.decompress(data, MAX_INFLATED_BYTES + 1)
    except zlib.error as exc:
        raise damaged(f"{what} is not a valid compressed stream", stream=what) from exc
    if len(out) > MAX_INFLATED_BYTES or inflater.unconsumed_tail:
        raise limit_exceeded(f"{what} inflates beyond the size limit", stream=what)
    try:
        out += inflater.flush()
    except zlib.error as exc:
        raise damaged(f"{what} is not a valid compressed stream", stream=what) from exc
    return out


def deflate(data: bytes) -> bytes:
    """Compress *data* as raw deflate, the form HWP 5.0 stores compressed streams in."""

    compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def parse_records(data: bytes, what: str) -> RecordStream:
    """Split *data* into records and link them into a tree by level."""

    records: list[Record] = []
    roots: list[Record] = []
    stack: list[Record] = []
    jumps = 0
    offset = 0
    end = len(data)
    view = memoryview(data)
    while offset < end:
        if offset + 4 > end:
            raise damaged(f"{what} ends inside a record header", stream=what, offset=offset)
        (word,) = _HEADER.unpack_from(data, offset)
        offset += 4
        tag = word & 0x3FF
        level = (word >> 10) & 0x3FF
        size = (word >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > end:
                raise damaged(f"{what} ends inside a record header", stream=what, offset=offset)
            (size,) = _HEADER.unpack_from(data, offset)
            offset += 4
        if offset + size > end:
            raise damaged(
                f"{what} has a record that runs past the end of the stream",
                stream=what,
                tag=tag,
                offset=offset,
                size=size,
            )
        record = Record(tag, level, bytes(view[offset : offset + size]))
        offset += size
        records.append(record)
        if len(records) > MAX_RECORDS:
            raise limit_exceeded(f"{what} has too many records", stream=what)
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            if level > stack[-1].level + 1:
                jumps += 1
            stack[-1].children.append(record)
        else:
            if level > 0:
                jumps += 1
            roots.append(record)
        stack.append(record)
    return RecordStream(records, roots, jumps)


def serialize_records(records: Iterable[Record]) -> bytes:
    """Write records (a flat list in stream order) back to bytes."""

    out = bytearray()
    for record in records:
        size = len(record.payload)
        if record.tag > 0x3FF or record.level > 0x3FF:
            raise write_unsupported("record tag or level out of range", tag=record.tag, level=record.level)
        if size >= 0xFFF:
            out += _HEADER.pack(record.tag | (record.level << 10) | (0xFFF << 20))
            out += _HEADER.pack(size)
        else:
            out += _HEADER.pack(record.tag | (record.level << 10) | (size << 20))
        out += record.payload
    return bytes(out)


def flatten(roots: Iterable[Record]) -> list[Record]:
    """The records of a tree in stream order."""

    out: list[Record] = []
    for root in roots:
        out.extend(root.walk())
    return out
