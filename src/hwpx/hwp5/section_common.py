# SPDX-License-Identifier: Apache-2.0
"""Pieces the section readers share: the conversion report, the common
properties of objects (tables, pictures, shapes, equations) and paragraph
lists (``hp:subList``)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import controls as ct
from . import records as rec
from .owpml import flag, sub, token


@dataclass
class ConversionReport:
    """What a conversion could not express, by kind and count.

    ``unconverted`` is content OWPML can hold but the conversion does not write
    yet. ``dropped`` is data OWPML has no element for (Hancom's own HWPX leaves
    it out too), such as range tags other than highlighter and change marks.
    """

    unconverted: Counter[str] = field(default_factory=Counter)
    dropped: Counter[str] = field(default_factory=Counter)

    def skip(self, kind: str) -> None:
        self.unconverted[kind] += 1

    def drop(self, kind: str) -> None:
        self.dropped[kind] += 1


def _bits(value: int, lo: int, width: int) -> int:
    return (value >> lo) & ((1 << width) - 1)


def _u32(value: int) -> int:
    """A signed 16/32-bit value the way Hancom prints it: unsigned 32-bit."""

    return value & 0xFFFFFFFF


# -- object common properties (tables, pictures, shapes, equations) -----------------

VERT_REL = ("PAPER", "PAGE", "PARA")
HORZ_REL = ("PAPER", "PAGE", "COLUMN", "PARA")
VERT_ALIGN = ("TOP", "CENTER", "BOTTOM", "INSIDE", "OUTSIDE")
HORZ_ALIGN = ("LEFT", "CENTER", "RIGHT", "INSIDE", "OUTSIDE")
WIDTH_REL = ("PAPER", "PAGE", "COLUMN", "PARA", "ABSOLUTE")
HEIGHT_REL = ("PAPER", "PAGE", "ABSOLUTE")
TEXT_WRAP = ("SQUARE", "TOP_AND_BOTTOM", "BEHIND_TEXT", "IN_FRONT_OF_TEXT")
TEXT_FLOW = ("BOTH_SIDES", "LEFT_ONLY", "RIGHT_ONLY", "LARGEST_ONLY")
NUMBERING_TYPE = ("NONE", "PICTURE", "TABLE", "EQUATION")


def object_attrs(common: ct.ObjectCommon) -> list[tuple[str, object]]:
    p = common.props
    return [
        ("id", common.instance_id),
        ("zOrder", common.z_order),
        ("numberingType", token(NUMBERING_TYPE, _bits(p, 26, 2))),  # bit 28 has no OWPML form
        ("textWrap", token(TEXT_WRAP, _bits(p, 21, 3))),
        ("textFlow", token(TEXT_FLOW, _bits(p, 24, 2))),
        ("lock", flag(p & (1 << 30))),
        ("dropcapstyle", "None"),
    ]


def object_layout(element: etree._Element, common: ct.ObjectCommon) -> None:
    """``hp:sz``, ``hp:pos`` and ``hp:outMargin`` of an object."""

    p = common.props
    sub(
        element,
        "hp:sz",
        (
            ("width", common.width),
            ("widthRelTo", token(WIDTH_REL, _bits(p, 15, 3))),
            ("height", common.height),
            ("heightRelTo", token(HEIGHT_REL, _bits(p, 18, 2))),
            ("protect", flag(p & (1 << 20))),
        ),
    )
    sub(
        element,
        "hp:pos",
        (
            ("treatAsChar", flag(p & 0x1)),
            ("affectLSpacing", flag(p & 0x4)),
            ("flowWithText", flag(p & (1 << 13))),
            ("allowOverlap", flag(p & (1 << 14))),
            ("holdAnchorAndSO", flag(common.prevent_page_break)),
            ("vertRelTo", token(VERT_REL, _bits(p, 3, 2))),
            ("horzRelTo", token(HORZ_REL, _bits(p, 8, 2))),
            ("vertAlign", token(VERT_ALIGN, _bits(p, 5, 3))),
            ("horzAlign", token(HORZ_ALIGN, _bits(p, 10, 3))),
            ("vertOffset", _u32(common.vert_offset)),
            ("horzOffset", _u32(common.horz_offset)),
        ),
    )
    left, right, top, bottom = common.margins
    sub(
        element,
        "hp:outMargin",
        (("left", _u32(left)), ("right", _u32(right)), ("top", _u32(top)), ("bottom", _u32(bottom))),
    )


# -- paragraph lists --------------------------------------------------------------------

TEXT_DIRECTION = ("HORIZONTAL", "VERTICAL", "VERTICALALL")
LINE_WRAP = ("BREAK", "SQUEEZE", "KEEP")
LIST_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM")


def list_attrs(props: int) -> list[tuple[str, object]]:
    """``hp:subList`` attributes from a list property word (bits 16-22)."""

    return [
        ("id", ""),
        ("textDirection", token(TEXT_DIRECTION, _bits(props, 16, 3))),
        ("lineWrap", token(LINE_WRAP, _bits(props, 19, 2))),
        ("vertAlign", token(LIST_VERT_ALIGN, _bits(props, 21, 2))),
        ("linkListIDRef", 0),
        ("linkListNextIDRef", 0),
        ("textWidth", 0),
        ("textHeight", 0),
        ("hasTextRef", 0),
        ("hasNumRef", 0),
    ]


def lists(owner: rec.Record) -> list[tuple[rec.Record, list[rec.Record]]]:
    """The paragraph lists inside a control: each ``LIST_HEADER`` and the
    ``PARA_HEADER`` records that follow it at the same level (a cell, a header
    or footer body, a note body)."""

    out: list[tuple[rec.Record, list[rec.Record]]] = []
    for record in owner.children:
        if record.tag == rec.LIST_HEADER:
            out.append((record, []))
        elif record.tag == rec.PARA_HEADER and out:
            out[-1][1].append(record)
    return out
