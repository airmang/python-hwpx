# SPDX-License-Identifier: Apache-2.0
"""DocInfo of an HWP 5.0 document: the id-mapped tables the body refers to."""

from __future__ import annotations

import struct
from collections import Counter

from . import records as rec

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
