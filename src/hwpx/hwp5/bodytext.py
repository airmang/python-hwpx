# SPDX-License-Identifier: Apache-2.0
"""Paragraphs of an HWP 5.0 BodyText section.

A paragraph is a ``PARA_HEADER`` record whose children carry its text
(``PARA_TEXT``), character shape runs (``PARA_CHAR_SHAPE``), line layout
(``PARA_LINE_SEG``), range tags (``PARA_RANGE_TAG``) and the controls
(``CTRL_HEADER``) its text refers to.

In the text, UTF-16 code units below 32 are control characters. A *char*
control takes one unit. An *inline* or *extended* control takes eight: the
code, twelve bytes of parameters, and the code again. An extended control's
parameters start with the id of the ``CTRL_HEADER`` record it stands for.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import records as rec

CHAR_CONTROLS = frozenset({0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31})
INLINE_CONTROLS = frozenset({4, 5, 6, 7, 8, 9, 19, 20})
EXTENDED_CONTROLS = frozenset({1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23})

PARA_BREAK = 13
LINE_BREAK = 10
TAB = 9


def ctrl_id(value: int) -> str:
    """The four-character control id of a 32-bit control id word."""

    return "".join(chr((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def ctrl_word(name: str) -> int:
    """The 32-bit word of a four-character control id (inverse of :func:`ctrl_id`)."""

    raw = name.encode("latin-1")
    return (raw[0] << 24) | (raw[1] << 16) | (raw[2] << 8) | raw[3]


@dataclass
class Chunk:
    """A run of plain text or one control character of a paragraph."""

    kind: str  # "text" | "char" | "inline" | "extended"
    position: int  # index of the first UTF-16 unit
    text: str = ""
    code: int = -1
    params: bytes = b""

    @property
    def width(self) -> int:
        """UTF-16 units the chunk takes in the paragraph text."""

        if self.kind == "text":
            return len(self.text.encode("utf-16-le")) // 2
        return 1 if self.kind == "char" else 8

    @property
    def control_id(self) -> str | None:
        if self.kind != "extended" or len(self.params) < 4:
            return None
        return ctrl_id(struct.unpack_from("<I", self.params, 0)[0])


def split_text(payload: bytes) -> tuple[list[Chunk], int]:
    """Split ``PARA_TEXT`` into chunks; return them and the count of malformed controls."""

    units = struct.unpack(f"<{len(payload) // 2}H", payload[: len(payload) // 2 * 2])
    chunks: list[Chunk] = []
    malformed = 0
    start = 0
    index = 0
    count = len(units)

    def flush(until: int) -> None:
        if until > start:
            raw = payload[start * 2 : until * 2]
            chunks.append(Chunk("text", start, raw.decode("utf-16-le", errors="surrogatepass")))

    while index < count:
        unit = units[index]
        if unit >= 32:
            index += 1
            continue
        flush(index)
        if unit in CHAR_CONTROLS:
            chunks.append(Chunk("char", index, code=unit))
            index += 1
        else:
            kind = "inline" if unit in INLINE_CONTROLS else "extended"
            end = index + 8
            if end > count or units[end - 1] != unit:
                malformed += 1
            params = payload[(index + 1) * 2 : (index + 7) * 2]
            chunks.append(Chunk(kind, index, code=unit, params=params))
            index = min(end, count)
        start = index
    flush(index)
    return chunks, malformed


@dataclass
class Paragraph:
    """One ``PARA_HEADER`` record, decoded."""

    record: rec.Record
    char_count: int
    last_in_list: bool
    control_mask: int
    para_shape_id: int
    style_id: int
    break_type: int
    char_shape_count: int
    range_tag_count: int
    line_seg_count: int
    instance_id: int
    merge_flag: int | None
    chunks: list[Chunk] = field(default_factory=list)
    char_shapes: list[tuple[int, int]] = field(default_factory=list)
    controls: list[rec.Record] = field(default_factory=list)
    text_record: rec.Record | None = None
    malformed_controls: int = 0

    @property
    def text_units(self) -> int:
        return sum(chunk.width for chunk in self.chunks)


_PARA_HEADER = struct.Struct("<IIHBBHHHI")


def parse_paragraph(record: rec.Record) -> Paragraph:
    """Decode a ``PARA_HEADER`` record and its children."""

    payload = record.payload
    if len(payload) < _PARA_HEADER.size:
        payload = payload.ljust(_PARA_HEADER.size, b"\0")
    (
        count,
        mask,
        para_shape,
        style,
        break_type,
        char_shape_count,
        range_tags,
        line_segs,
        instance,
    ) = _PARA_HEADER.unpack_from(payload, 0)
    merge = (
        struct.unpack_from("<H", record.payload, _PARA_HEADER.size)[0]
        if len(record.payload) >= _PARA_HEADER.size + 2
        else None
    )
    paragraph = Paragraph(
        record,
        count & 0x7FFFFFFF,
        bool(count & 0x80000000),
        mask,
        para_shape,
        style,
        break_type,
        char_shape_count,
        range_tags,
        line_segs,
        instance,
        merge,
    )
    for child in record.children:
        if child.tag == rec.PARA_TEXT:
            paragraph.text_record = child
            paragraph.chunks, paragraph.malformed_controls = split_text(child.payload)
        elif child.tag == rec.PARA_CHAR_SHAPE:
            pairs = len(child.payload) // 8
            flat = struct.unpack_from(f"<{pairs * 2}I", child.payload, 0)
            paragraph.char_shapes = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
        elif child.tag == rec.CTRL_HEADER:
            paragraph.controls.append(child)
    return paragraph


def iter_paragraphs(roots: list[rec.Record]) -> list[Paragraph]:
    """Every paragraph in *roots*, nested ones (cells, notes, text boxes) included."""

    out: list[Paragraph] = []
    for root in roots:
        for record in root.walk():
            if record.tag == rec.PARA_HEADER:
                out.append(parse_paragraph(record))
    return out


def record_ctrl_id(record: rec.Record) -> str | None:
    """The control id of a ``CTRL_HEADER`` record."""

    if record.tag != rec.CTRL_HEADER or len(record.payload) < 4:
        return None
    return ctrl_id(struct.unpack_from("<I", record.payload, 0)[0])
