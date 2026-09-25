# SPDX-License-Identifier: Apache-2.0
"""OWPML names and value tables shared by the HWP 5.0 <-> HWPX converters.

The tables map the integer codes of HWP 5.0 records to the tokens OWPML uses,
in both directions, so reading and writing cannot drift apart.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

NS: dict[str, str] = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

HWPUNITCHAR = NS["hwpunitchar"]
HP10 = NS["hp10"]

XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'

_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def q(name: str) -> str:
    """Clark name for ``prefix:local``."""

    prefix, local = name.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def root(name: str) -> etree._Element:
    """A root element that declares every OWPML prefix, the way Hancom writes parts."""

    return etree.Element(q(name), nsmap=dict(NS))


def xml_spaced(value: object) -> str:
    """*value* as text XML 1.0 can hold, each character it cannot hold
    written as a space, as Hancom writes a field's command."""

    text = str(value)
    return _NOT_XML.sub(" ", text) if _NOT_XML.search(text) else text


def xml_text(value: object) -> str:
    """*value* as text XML 1.0 can hold: control characters and lone surrogates dropped."""

    text = str(value)
    return _NOT_XML.sub("", text) if _NOT_XML.search(text) else text


def sub(parent: etree._Element, name: str, attrs: Sequence[tuple[str, object]] = ()) -> etree._Element:
    element = etree.SubElement(parent, q(name))
    for key, value in attrs:
        element.set(q(key) if ":" in key else key, xml_text(value))
    return element


def serialize(element: etree._Element) -> bytes:
    return XML_DECLARATION + etree.tostring(element, encoding="UTF-8")


def flag(value: object) -> str:
    return "1" if value else "0"


# -- colours ----------------------------------------------------------------------------

NO_COLOR = 0xFFFFFFFF


def color(value: int | None) -> str:
    """COLORREF (0xAABBGGRR) as ``#RRGGBB``, and ``none`` for ``0xFFFFFFFF``.

    With a non-zero top byte the value is ARGB in hex without leading zeros,
    as Hancom writes it (``#A10FCA0`` for alpha 0x0A).
    """

    if value is None or value == NO_COLOR:
        return "none"
    rgb = (value & 0xFF) << 16 | (value & 0xFF00) | (value >> 16) & 0xFF
    alpha = (value >> 24) & 0xFF
    return f"#{alpha << 24 | rgb:X}" if alpha else f"#{rgb:06X}"


def colorref(text: str | None) -> int:
    """Inverse of :func:`color`."""

    if not text or text == "none" or not text.startswith("#"):
        return NO_COLOR
    digits = text[1:]
    alpha = 0
    if len(digits) in (7, 8):
        try:
            alpha, digits = int(digits[:-6], 16), digits[-6:]
        except ValueError:
            return NO_COLOR
    if len(digits) != 6:
        return NO_COLOR
    try:
        rgb = int(digits, 16)
    except ValueError:
        return NO_COLOR
    return (alpha << 24) | ((rgb & 0xFF) << 16) | (rgb & 0xFF00) | ((rgb >> 16) & 0xFF)


# -- enumerations ---------------------------------------------------------------------


def token(table: Sequence[str], index: int, default: str | None = None) -> str:
    if 0 <= index < len(table):
        return table[index]
    return default if default is not None else table[0]


def index_of(table: Sequence[str] | Mapping[str, int], value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(table, Mapping):
        return table.get(value, default)
    try:
        return list(table).index(value)
    except ValueError:
        return default


#: Border and fill line types; 0 is no line.
BORDER_LINE = (
    "NONE",
    "SOLID",
    "DOT",
    "DASH",
    "DASH_DOT",
    "DASH_DOT_DOT",
    "LONG_DASH",
    "CIRCLE",
    "DOUBLE_SLIM",
    "SLIM_THICK",
    "THICK_SLIM",
    "SLIM_THICK_SLIM",
    "WAVE",
    "DOUBLE_WAVE",
    "THICK_3D",
    "THICK_3D_REVERS",
    "3D",
    "3D_REVERS",
)

#: Underline and strikeout shapes; 0 is a solid line.
CHAR_LINE = BORDER_LINE[1:]

BORDER_WIDTH = (
    "0.1 mm",
    "0.12 mm",
    "0.15 mm",
    "0.2 mm",
    "0.25 mm",
    "0.3 mm",
    "0.4 mm",
    "0.5 mm",
    "0.6 mm",
    "0.7 mm",
    "1.0 mm",
    "1.5 mm",
    "2.0 mm",
    "3.0 mm",
    "4.0 mm",
    "5.0 mm",
)

SLASH = {0: "NONE", 2: "CENTER", 3: "CENTER_BELOW", 6: "CENTER_ABOVE", 7: "ALL"}
HATCH = ("HORIZONTAL", "VERTICAL", "SLASH", "BACK_SLASH", "CROSS", "CROSS_DIAGONAL")
GRADATION = {1: "LINEAR", 2: "RADIAL", 3: "CONICAL", 4: "SQUARE"}
IMAGE_MODE = (
    "TILE",
    "TILE_HORZ_TOP",
    "TILE_HORZ_BOTTOM",
    "TILE_VERT_LEFT",
    "TILE_VERT_RIGHT",
    "TOTAL",
    "CENTER",
    "CENTER_TOP",
    "CENTER_BOTTOM",
    "LEFT_CENTER",
    "LEFT_TOP",
    "LEFT_BOTTOM",
    "RIGHT_CENTER",
    "RIGHT_TOP",
    "RIGHT_BOTTOM",
    "ZOOM",
)
#: Picture effects by their HWP code. OWPML also names PATTERN8x8, but Hancom
#: writes it to HWP as 0 (REAL_PIC), and leaves the effect out of OWPML for an
#: HWP code 3.
IMAGE_EFFECT = ("REAL_PIC", "GRAY_SCALE", "BLACK_WHITE")
#: The HWP code each OWPML picture effect is written as.
IMAGE_EFFECT_CODES: dict[str, int] = {**{name: code for code, name in enumerate(IMAGE_EFFECT)}, "PATTERN8x8": 0}


def image_effect(code: int) -> tuple[tuple[str, str], ...]:
    """The ``effect`` attribute of an ``hc:img``; none for a code OWPML has no name for."""

    return (("effect", IMAGE_EFFECT[code]),) if 0 <= code < len(IMAGE_EFFECT) else ()


UNDERLINE_TYPE = ("NONE", "BOTTOM", "CENTER", "TOP")
OUTLINE = ("NONE", "SOLID", "DOT", "THICK", "DASH", "DASH_DOT", "DASH_DOT_DOT")
SHADOW = ("NONE", "DROP", "CONTINUOUS")
SYM_MARK = (
    "NONE",
    "DOT_ABOVE",
    "RING_ABOVE",
    "TILDE",
    "CARON",
    "SIDE",
    "COLON",
    "GRAVE_ACCENT",
    "ACUTE_ACCENT",
    "CIRCUMFLEX",
    "MACRON",
    "HOOK_ABOVE",
    "DOT_BELOW",
)

ALIGN_H = ("JUSTIFY", "LEFT", "RIGHT", "CENTER", "DISTRIBUTE", "DISTRIBUTE_SPACE")
ALIGN_V = ("BASELINE", "TOP", "CENTER", "BOTTOM")
BREAK_LATIN = ("KEEP_WORD", "HYPHENATION", "BREAK_WORD")
BREAK_NON_LATIN = ("BREAK_WORD", "KEEP_WORD")
LINE_WRAP = ("BREAK", "SQUEEZE", "KEEP")
TEXT_DIR = ("AUTO", "RTL", "LTR")
HEADING = ("NONE", "OUTLINE", "NUMBER", "BULLET")
LINE_SPACING = ("PERCENT", "FIXED", "BETWEEN_LINES", "AT_LEAST")

TAB_TYPE = ("LEFT", "RIGHT", "CENTER", "DECIMAL")

FONT_TYPE = {0: "REP", 1: "TTF", 2: "HFT"}
FAMILY = (
    "FCAT_UNKNOWN",
    "FCAT_MYUNGJO",
    "FCAT_GOTHIC",
    "FCAT_SSERIF",
    "FCAT_BRUSHSCRIPT",
    "FCAT_DECORATIVE",
    "FCAT_NONRECTMJ",
    "FCAT_NONRECTGT",
)

PARA_HEAD_ALIGN = ("LEFT", "CENTER", "RIGHT")
NUMBER_FORMAT = (
    "DIGIT",
    "CIRCLED_DIGIT",
    "ROMAN_CAPITAL",
    "ROMAN_SMALL",
    "LATIN_CAPITAL",
    "LATIN_SMALL",
    "CIRCLED_LATIN_CAPITAL",
    "CIRCLED_LATIN_SMALL",
    "HANGUL_SYLLABLE",
    "CIRCLED_HANGUL_SYLLABLE",
    "HANGUL_JAMO",
    "CIRCLED_HANGUL_JAMO",
    "HANGUL_PHONETIC",
    "IDEOGRAPH",
    "CIRCLED_IDEOGRAPH",
    "DECAGON_CIRCLE",
    "DECAGON_CIRCLE_HANJA",
)
#: The number formats of notes and auto numbers by code: those above, then
#: four symbols in turn (0x80) and a character of the user's (0x81).
NOTE_NUMBER_FORMAT: dict[int, str] = {**dict(enumerate(NUMBER_FORMAT)), 0x80: "SYMBOL", 0x81: "USER_CHAR"}
NOTE_NUMBER_FORMAT_CODES: dict[str, int] = {name: code for code, name in NOTE_NUMBER_FORMAT.items()}
STYLE_TYPE = ("PARA", "CHAR")
MEMO_TYPE = ("NOMAL", "USER_INSERT", "USER_DELETE", "USER_UPDATE")
TARGET_PROGRAM = ("HWP201X", "HWP200X", "MS_WORD")

LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")
LANG_ATTRS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
