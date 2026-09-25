# SPDX-License-Identifier: Apache-2.0
"""``Contents/header.xml`` -> the DocInfo records of an HWP 5.0 document.

The inverse of :mod:`hwpx.hwp5.header_xml`. Values OWPML keeps twice (the
``hp:case``/``hp:default`` pair of margins and tab positions) are taken from
the HwpUnitChar case, which is what Hancom reads, and stored doubled with the
unit in bit 0. Records come out in the order and at the levels Hancom writes
them, in the 5.1.1.0 layouts.
"""

from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Mapping

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import docinfo as di
from . import records as rec
from .owpml import (
    ALIGN_H,
    ALIGN_V,
    BORDER_LINE,
    BORDER_WIDTH,
    BREAK_LATIN,
    BREAK_NON_LATIN,
    CHAR_LINE,
    FAMILY,
    GRADATION,
    HATCH,
    HEADING,
    IMAGE_EFFECT_CODES,
    IMAGE_MODE,
    LANG_ATTRS,
    LANGS,
    LINE_SPACING,
    LINE_WRAP,
    MEMO_TYPE,
    NS,
    NUMBER_FORMAT,
    OUTLINE,
    PARA_HEAD_ALIGN,
    SHADOW,
    SLASH,
    STYLE_TYPE,
    SYM_MARK,
    TAB_TYPE,
    TARGET_PROGRAM,
    TEXT_DIR,
    UNDERLINE_TYPE,
    colorref,
    index_of,
)

_HH = NS["hh"]
_HC = NS["hc"]
_HP = NS["hp"]
_SLASH = {token: code for code, token in SLASH.items()}
_GRADATION = {token: code for code, token in GRADATION.items()}
_FONT_TYPE = {"REP": 0, "TTF": 1, "HFT": 2}


def _int(element: etree._Element | None, name: str, default: int = 0) -> int:
    if element is None:
        return default
    value = element.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return int(float(value))


def _flag(element: etree._Element | None, name: str) -> int:
    if element is None:
        return 0
    return 1 if element.get(name) in ("1", "true") else 0


def _child(element: etree._Element, ns: str, name: str) -> etree._Element | None:
    return element.find(f"{{{ns}}}{name}")


def _lang_values(element: etree._Element | None, default: int) -> list[int]:
    return [_int(element, lang, default) for lang in LANG_ATTRS]


def _doubled(value: int, unit: str | None) -> int:
    """A length as HWP 5.0 stores it: doubled, with bit 0 set for character units."""

    raw = value * 2
    return raw + 1 if unit == "CHAR" else raw


def _switch_case(parent: etree._Element, name: str) -> list[etree._Element]:
    """Children called *name*: from ``hp:switch/hp:case`` when present, else direct."""

    out: list[etree._Element] = []
    for switch in parent.findall(f"{{{_HP}}}switch"):
        case = switch.find(f"{{{_HP}}}case")
        if case is not None:
            out.extend(case.findall(f"{{{_HH}}}{name}"))
    if not out:
        out = parent.findall(f"{{{_HH}}}{name}")
    return out


# -- records -------------------------------------------------------------------------


def face_name(font: etree._Element) -> di.FaceName:
    props = _FONT_TYPE.get(font.get("type", "TTF"), 1)
    item = di.FaceName(props, font.get("face", ""))
    subst = _child(font, _HH, "substFont")
    if subst is not None:
        item.props |= di.FaceName.HAS_ALT
        item.alt_type = _FONT_TYPE.get(subst.get("type", "TTF"), 1)
        item.alt_name = subst.get("face", "")
    info = _child(font, _HH, "typeInfo")
    if info is not None:
        item.props |= di.FaceName.HAS_TYPE_INFO
        item.type_info = bytes(
            [
                index_of(FAMILY, info.get("familyType"), 0),
                0,
                _int(info, "weight"),
                _int(info, "proportion"),
                _int(info, "contrast"),
                _int(info, "strokeVariation"),
                _int(info, "armStyle"),
                _int(info, "letterform"),
                _int(info, "midline"),
                _int(info, "xHeight"),
            ]
        )
    return item


def _line(element: etree._Element | None) -> di.Line:
    if element is None:
        return di.Line()
    return di.Line(
        index_of(BORDER_LINE, element.get("type"), 0),
        index_of(BORDER_WIDTH, element.get("width"), 0),
        colorref(element.get("color")),
    )


def fill(brush: etree._Element | None, bin_ids: Mapping[str, int] | None = None) -> di.Fill:
    result = di.Fill()
    if brush is None:
        return result
    alphas: list[int] = []
    win = _child(brush, _HC, "winBrush")
    gradation = _child(brush, _HC, "gradation")
    image = _child(brush, _HC, "imgBrush")
    if win is not None:
        result.kind |= di.FILL_SOLID
        result.back_color = colorref(win.get("faceColor"))
        result.pattern_color = colorref(win.get("hatchColor"))
        hatch = win.get("hatchStyle")
        result.pattern_type = index_of(HATCH, hatch, -1) if hatch else -1
        alphas.append(_int(win, "alpha"))
    if gradation is not None:
        result.kind |= di.FILL_GRADATION
        result.grad_type = _GRADATION.get(gradation.get("type", "LINEAR"), 1)
        result.grad_angle = _int(gradation, "angle")
        result.grad_center_x = _int(gradation, "centerX")
        result.grad_center_y = _int(gradation, "centerY")
        result.grad_step = _int(gradation, "step", 255)
        result.grad_colors = [colorref(c.get("value")) for c in gradation.findall(f"{{{_HC}}}color")]
        if len(result.grad_colors) > 2:
            result.grad_positions = [0] * len(result.grad_colors)
        result.additional = bytes([_int(gradation, "stepCenter", 50) & 0xFF])
        alphas.append(_int(gradation, "alpha"))
    if image is not None:
        result.kind |= di.FILL_IMAGE
        result.image_mode = index_of(IMAGE_MODE, image.get("mode"), 0)
        img = _child(image, _HC, "img")
        if img is not None:
            result.image_bright = _int(img, "bright")
            result.image_contrast = _int(img, "contrast")
            result.image_effect = index_of(IMAGE_EFFECT_CODES, img.get("effect"), 0)
            result.image_bin_id = _bin_ref(img.get("binaryItemIDRef"), bin_ids)
            alphas.append(_int(img, "alpha"))
    if result.kind:
        result.alphas = bytes(a & 0xFF for a in alphas)
    else:
        result.additional = b""
    return result


def _bin_ref(value: str | None, bin_ids: Mapping[str, int] | None = None) -> int:
    """A binary item reference as its BinData number: the item's place among
    the binary items (``bin_ids``, 0 for an item not among them), or without
    that list the number in its id (``image7`` -> 7)."""

    if bin_ids is not None:
        return bin_ids.get(value or "", 0)
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return int(digits) if digits else 0


def border_fill(element: etree._Element, bin_ids: Mapping[str, int] | None = None) -> di.BorderFill:
    slash = _child(element, _HH, "slash")
    back = _child(element, _HH, "backSlash")
    props = _flag(element, "threeD") | (_flag(element, "shadow") << 1)
    props |= _SLASH.get(slash.get("type", "NONE") if slash is not None else "NONE", 0) << 2
    props |= _SLASH.get(back.get("type", "NONE") if back is not None else "NONE", 0) << 5
    props |= _flag(slash, "Crooked") << 8 | _flag(back, "Crooked") << 9
    props |= _flag(element, "breakCellSeparateLine") << 10
    props |= _flag(slash, "isCounter") << 11 | _flag(back, "isCounter") << 12
    # With no diagonal element there is no diagonal line: Hancom writes it as
    # kind 0, width 1, colour 0 (a drawn line here would show wherever a slash
    # or back slash is on).
    diagonal = _child(element, _HH, "diagonal")
    return di.BorderFill(
        props,
        _line(_child(element, _HH, "leftBorder")),
        _line(_child(element, _HH, "rightBorder")),
        _line(_child(element, _HH, "topBorder")),
        _line(_child(element, _HH, "bottomBorder")),
        _line(diagonal) if diagonal is not None else di.Line(0, 1, 0),
        fill(_child(element, _HC, "fillBrush"), bin_ids),
    )


def char_shape(element: etree._Element) -> di.CharShape:
    shape = di.CharShape(
        font_ids=_lang_values(_child(element, _HH, "fontRef"), 0),
        ratios=_lang_values(_child(element, _HH, "ratio"), 100),
        spacings=_lang_values(_child(element, _HH, "spacing"), 0),
        rel_sizes=_lang_values(_child(element, _HH, "relSz"), 100),
        offsets=_lang_values(_child(element, _HH, "offset"), 0),
        height=_int(element, "height", 1000),
        text_color=colorref(element.get("textColor", "#000000")),
        shade_color=colorref(element.get("shadeColor", "none")),
        border_fill_id=_int(element, "borderFillIDRef", 0),
    )
    props = 0
    if _child(element, _HH, "italic") is not None:
        props |= 0x1
    if _child(element, _HH, "bold") is not None:
        props |= 0x2
    underline = _child(element, _HH, "underline")
    strike = _child(element, _HH, "strikeout")
    strike_shape = strike.get("shape", "NONE") if strike is not None else "NONE"
    underline_type = index_of(UNDERLINE_TYPE, underline.get("type") if underline is not None else None, 0)
    underline_shape = index_of(CHAR_LINE, underline.get("shape") if underline is not None else None, 0)
    strike_as_underline = False
    if strike_shape != "NONE":
        props |= 1 << 18
        props |= (index_of(CHAR_LINE, strike_shape, 0) & 0xF) << 26
        if underline_type == 0:
            # Hancom also records a strikeout in the old centre-underline
            # bits, in the strikeout's colour.
            underline_type, underline_shape = 2, index_of(CHAR_LINE, strike_shape, 0)
            strike_as_underline = True
    props |= (underline_type & 0x3) << 2 | (underline_shape & 0xF) << 4
    shape.underline_color = colorref(underline.get("color", "#000000")) if underline is not None else 0
    if strike_as_underline and strike is not None:
        shape.underline_color = colorref(strike.get("color", "#000000"))
    shape.strikeout_color = colorref(strike.get("color", "#000000")) if strike is not None else 0
    outline = _child(element, _HH, "outline")
    props |= index_of(OUTLINE, outline.get("type") if outline is not None else None, 0) << 8
    shadow = _child(element, _HH, "shadow")
    if shadow is not None:
        props |= index_of(SHADOW, shadow.get("type"), 0) << 11
        shape.shadow_color = colorref(shadow.get("color", "#B2B2B2"))
        shape.shadow_x = _int(shadow, "offsetX", 10)
        shape.shadow_y = _int(shadow, "offsetY", 10)
    for bit, name in ((13, "emboss"), (14, "engrave"), (15, "supscript"), (16, "subscript")):
        if _child(element, _HH, name) is not None:
            props |= 1 << bit
    props |= index_of(SYM_MARK, element.get("symMark"), 0) << 21
    props |= _flag(element, "useFontSpace") << 25
    props |= _flag(element, "useKerning") << 30
    shape.props = props
    return shape


def tab_def(element: etree._Element) -> di.TabDef:
    tab = di.TabDef(_flag(element, "autoTabLeft") | _flag(element, "autoTabRight") << 1)
    for item in _switch_case(element, "tabItem"):
        position = _doubled(_int(item, "pos"), item.get("unit"))
        tab.items.append(
            di.TabItem(position, index_of(TAB_TYPE, item.get("type"), 0), index_of(BORDER_LINE, item.get("leader"), 0))
        )
    return tab


def para_head(element: etree._Element) -> di.ParaHead:
    props = index_of(PARA_HEAD_ALIGN, element.get("align"), 0)
    props |= _flag(element, "useInstWidth") << 2
    props |= _flag(element, "autoIndent") << 3
    props |= (1 if element.get("textOffsetType") == "HWPUNIT" else 0) << 4
    props |= (index_of(NUMBER_FORMAT, element.get("numFormat"), 0) & 0xF) << 5
    return di.ParaHead(
        props,
        _int(element, "widthAdjust"),
        _int(element, "textOffset", 50),
        _int(element, "charPrIDRef", 0xFFFFFFFF) & 0xFFFFFFFF,
        element.text or "",
    )


def numbering(element: etree._Element) -> di.Numbering:
    heads = element.findall(f"{{{_HH}}}paraHead")
    result = di.Numbering(start=_int(element, "start", 0))
    parsed = [para_head(head) for head in heads]
    result.heads = (parsed + [di.ParaHead() for _ in range(7)])[:7]
    result.level_starts = [_int(head, "start", 1) for head in heads[:7]] + [1] * max(0, 7 - len(heads))
    result.extended_heads = (parsed[7:10] + [di.ParaHead() for _ in range(3)])[:3]
    result.extended_starts = [_int(head, "start", 1) for head in heads[7:10]] + [1] * max(0, 3 - len(heads[7:10]))
    return result


def bullet(element: etree._Element, bin_ids: Mapping[str, int] | None = None) -> di.Bullet:
    head_element = _child(element, _HH, "paraHead")
    head = para_head(head_element) if head_element is not None else di.ParaHead()
    head.format = ""
    char = element.get("char") or ""
    checked = element.get("checkedChar") or ""
    result = di.Bullet(head, ord(char[0]))
    result.check_char = ord(checked[0]) if checked else 0
    image = _child(element, _HC, "img")
    if _flag(element, "useImage") and image is not None:
        result.image_id = 1
        result.image_props = bytes(
            [
                _int(image, "bright") & 0xFF,
                _int(image, "contrast") & 0xFF,
                index_of(IMAGE_EFFECT_CODES, image.get("effect"), 0),
                _bin_ref(image.get("binaryItemIDRef"), bin_ids) & 0xFF,
            ]
        )
    return result


def para_shape(element: etree._Element) -> di.ParaShape:
    shape = di.ParaShape()
    align = _child(element, _HH, "align")
    heading = _child(element, _HH, "heading")
    extended = element.find(f"{{{_HP}}}switch/{{{_HP}}}case/{{{_HH}}}heading")
    if extended is not None:
        heading = extended
    brk = _child(element, _HH, "breakSetting")
    auto = _child(element, _HH, "autoSpacing")
    border = _child(element, _HH, "border")
    # Lengths in the switch's case are halved; written with no switch they
    # are what HWP keeps, as Hancom reads them (the switch's default side).
    margin = None
    spacing = None
    plain = False
    for switch in element.findall(f"{{{_HP}}}switch"):
        case = switch.find(f"{{{_HP}}}case")
        if case is not None and case.find(f"{{{_HH}}}margin") is not None:
            margin = case.find(f"{{{_HH}}}margin")
            spacing = case.find(f"{{{_HH}}}lineSpacing")
    if margin is None:
        margin = _child(element, _HH, "margin")
        spacing = _child(element, _HH, "lineSpacing")
        plain = True
    heading_type = index_of(HEADING, heading.get("type") if heading is not None else None, 0)
    level = _int(heading, "level")
    spacing_type = index_of(LINE_SPACING, spacing.get("type") if spacing is not None else None, 0)
    p1 = min(spacing_type, 2)
    p1 |= index_of(ALIGN_H, align.get("horizontal") if align is not None else None, 0) << 2
    p1 |= index_of(BREAK_LATIN, brk.get("breakLatinWord") if brk is not None else None, 0) << 5
    p1 |= index_of(BREAK_NON_LATIN, brk.get("breakNonLatinWord") if brk is not None else None, 1) << 7
    p1 |= _flag(element, "snapToGrid") << 8
    p1 |= (_int(element, "condense") & 0x7F) << 9
    p1 |= _flag(brk, "widowOrphan") << 16 | _flag(brk, "keepWithNext") << 17
    p1 |= _flag(brk, "keepLines") << 18 | _flag(brk, "pageBreakBefore") << 19
    p1 |= index_of(ALIGN_V, align.get("vertical") if align is not None else None, 0) << 20
    p1 |= _flag(element, "fontLineHeight") << 22
    p1 |= heading_type << 23
    p1 |= min(level, 6) << 25
    p1 |= _flag(border, "connect") << 28 | _flag(border, "ignoreMargin") << 29
    shape.props1 = p1
    for name, attr in (("intent", "indent"), ("left", "left"), ("right", "right"), ("prev", "prev"), ("next", "next")):
        value = margin.find(f"{{{_HC}}}{name}") if margin is not None else None
        unit = value.get("unit") if value is not None else None
        amount = _int(value, "value")
        setattr(shape, attr, amount if plain and unit != "CHAR" else _doubled(amount, unit))
    line_value = _int(spacing, "value", 160)
    line_unit = spacing.get("unit") if spacing is not None else None
    raw_line = spacing_type == 0 or (plain and line_unit != "CHAR")
    line_spacing = line_value if raw_line else _doubled(line_value, line_unit)
    shape.line_spacing_old = line_spacing
    shape.line_spacing = line_spacing
    shape.tab_def_id = _int(element, "tabPrIDRef")
    shape.numbering_id = _int(heading, "idRef")
    shape.border_fill_id = _int(border, "borderFillIDRef")
    shape.border_offsets = [
        _int(border, "offsetLeft"),
        _int(border, "offsetRight"),
        _int(border, "offsetTop"),
        _int(border, "offsetBottom"),
    ]
    p2 = index_of(LINE_WRAP, brk.get("lineWrap") if brk is not None else None, 0)
    p2 |= index_of(TEXT_DIR, element.get("textDir"), 0) << 2
    p2 |= _flag(auto, "eAsianEng") << 4 | _flag(auto, "eAsianNum") << 5
    p2 |= _flag(element, "suppressLineNumbers") << 6 | _flag(element, "checked") << 7
    shape.props2 = p2
    shape.props3 = spacing_type
    shape.level = level
    return shape


def style(element: etree._Element) -> di.Style:
    kind = index_of(STYLE_TYPE, element.get("type"), 0)
    return di.Style(
        element.get("name", ""),
        element.get("engName", ""),
        kind | _flag(element, "lockForm") << 2,
        _int(element, "nextStyleIDRef"),
        _int(element, "langID", 1042),
        _int(element, "paraPrIDRef"),
        _int(element, "charPrIDRef"),
        0,
    )


def memo_shape(element: etree._Element) -> di.MemoShape:
    return di.MemoShape(
        _int(element, "width"),
        index_of(BORDER_LINE, element.get("lineType"), 1),
        _int(element, "lineWidth"),
        colorref(element.get("lineColor")),
        colorref(element.get("fillColor")),
        colorref(element.get("activeColor")),
        index_of(MEMO_TYPE, element.get("memoType"), 0),
    )


# -- the stream ---------------------------------------------------------------------


@dataclass
class DocInfoResult:
    records: list[rec.Record]
    section_count: int
    unsupported: list[str] = field(default_factory=list)


def forbidden_chars(head: etree._Element) -> di.ForbiddenChars | None:
    """The ``FORBIDDEN_CHAR`` record for the head's ``hh:forbiddenWordList``
    (a space stands for an empty list); four empty lists without one. None
    when the list does not hold four readable words."""

    listing = _child(head, _HH, "forbiddenWordList")
    if listing is None:
        return di.ForbiddenChars()
    words: list[str] = []
    for word in listing.findall(f"{{{_HH}}}forbiddenWord"):
        try:
            text = base64.b64decode("".join((word.text or "").split()), validate=True).decode("utf-16-le")
        except (binascii.Error, UnicodeDecodeError):
            return None
        words.append("" if text == " " else text)
    if len(words) != 4:
        return None
    return di.ForbiddenChars((words[0], words[1], words[2], words[3]))


#: The kind of each OWPML tracked change type.
_TRACK_CHANGE_KINDS = {"Insert": 16, "Delete": 17, "ParaShape": 19}
#: A tracked change keeps local (Korean) time; OWPML writes it in UTC.
_TRACK_TIME_OFFSET = timedelta(hours=9)


def _track_time(value: str) -> datetime | None:
    """The local time of a tracked change: a date in UTC (``Z``) moves by
    the offset, one without a zone is local already, as Hancom reads it."""

    for pattern, offset in (("%Y-%m-%dT%H:%M:%SZ", _TRACK_TIME_OFFSET), ("%Y-%m-%dT%H:%M:%S", None), ("%Y-%m-%d %H:%M:%S", None)):
        try:
            when = datetime.strptime(value, pattern)
        except ValueError:
            continue
        return when + offset if offset is not None else when
    return None


def track_changes(head: etree._Element) -> tuple[list[di.TrackChange], list[di.TrackChangeAuthor]] | None:
    """The head's tracked changes and their authors as Hancom writes them:
    the time to the minute, a deletion hidden, a paragraph shape change with
    its paragraph shape. None when a change has a type with no kind or a date
    that is no date."""

    changes: list[di.TrackChange] = []
    for element in head.iter(f"{{{_HH}}}trackChange"):
        kind = _TRACK_CHANGE_KINDS.get(element.get("type", ""))
        when = _track_time(element.get("date", ""))
        if kind is None or when is None:
            return None
        shape = kind == 19
        fourth = _int(element, "parashapeID") if shape else 1 if kind == 17 else _flag(element, "hide")
        changes.append(
            di.TrackChange(
                kind,
                (when.year, when.month, when.day, when.hour, when.minute),
                _int(element, "authorID") & 0xFFFF,
                (0, 4 if shape else 0, 0, fourth & 0xFFFF, 0),
                bytes(4) if shape else b"",
            )
        )
    authors = [
        di.TrackChangeAuthor(element.get("name", ""), _flag(element, "mark"), bytes(4))
        for element in head.iter(f"{{{_HH}}}trackChangeAuthor")
    ]
    return changes, authors


def build_docinfo(
    head: etree._Element,
    *,
    section_count: int,
    caret: tuple[int, int, int] = (0, 0, 0),
    bin_ids: Mapping[str, int] | None = None,
    doc_data: bytes | None = None,
) -> DocInfoResult:
    """DocInfo records for a parsed ``hh:head`` element; ``bin_ids`` maps
    binary item ids to their BinData numbers for fill and bullet images, and
    ``doc_data`` is the payload of the DOC_DATA record (the print settings)."""

    begin = _child(head, _HH, "beginNum")
    properties = di.DocumentProperties(
        section_count,
        _int(begin, "page", 1),
        _int(begin, "footnote", 1),
        _int(begin, "endnote", 1),
        _int(begin, "pic", 1),
        _int(begin, "tbl", 1),
        _int(begin, "equation", 1),
        *caret,
    )
    refs = _child(head, _HH, "refList")
    mapped: list[rec.Record] = []

    def collect(container: str, item: str, make: Callable[[etree._Element], object], tag: int) -> int:
        group = _child(refs, _HH, container) if refs is not None else None
        elements = group.findall(f"{{{_HH}}}{item}") if group is not None else []
        for element in elements:
            mapped.append(rec.Record(tag, 1, make(element).encode()))  # type: ignore[attr-defined]
        return len(elements)

    font_counts = []
    faces = _child(refs, _HH, "fontfaces") if refs is not None else None
    by_lang = {face.get("lang"): face for face in faces.findall(f"{{{_HH}}}fontface")} if faces is not None else {}
    for lang in LANGS:
        fonts = by_lang[lang].findall(f"{{{_HH}}}font") if lang in by_lang else []
        font_counts.append(len(fonts))
        for font in fonts:
            mapped.append(rec.Record(rec.FACE_NAME, 1, face_name(font).encode()))
    counts = {
        "border_fill": collect("borderFills", "borderFill", lambda e: border_fill(e, bin_ids), rec.BORDER_FILL),
        "char_shape": collect("charProperties", "charPr", char_shape, rec.CHAR_SHAPE),
        "tab_def": collect("tabProperties", "tabPr", tab_def, rec.TAB_DEF),
        "numbering": collect("numberings", "numbering", numbering, rec.NUMBERING),
        "bullet": collect("bullets", "bullet", lambda e: bullet(e, bin_ids), rec.BULLET),
        "para_shape": collect("paraProperties", "paraPr", para_shape, rec.PARA_SHAPE),
        "style": collect("styles", "style", style, rec.STYLE),
        "memo_shape": collect("memoProperties", "memoPr", memo_shape, rec.MEMO_SHAPE),
    }
    changes, authors = track_changes(head) or ([], [])
    bin_count = 0
    mappings = [bin_count, *font_counts, counts["border_fill"], counts["char_shape"], counts["tab_def"],
                counts["numbering"], counts["bullet"], counts["para_shape"], counts["style"],
                counts["memo_shape"], len(changes), len(authors)]
    records = [
        rec.Record(rec.DOCUMENT_PROPERTIES, 0, properties.encode()),
        rec.Record(rec.ID_MAPPINGS, 0, struct.pack(f"<{len(mappings)}i", *mappings)),
        *mapped,
        *(rec.Record(rec.TRACK_CHANGE_AUTHOR, 1, author.encode()) for author in authors),
        *(rec.Record(rec.TRACK_CHANGE, 1, change.encode()) for change in changes),
        # DOC_DATA follows the id-mapped lists, before the forbidden characters;
        # Hancom reads it nowhere else.
        *([rec.Record(rec.DOC_DATA, 0, doc_data)] if doc_data is not None else []),
        rec.Record(rec.FORBIDDEN_CHAR, 1, (forbidden_chars(head) or di.ForbiddenChars()).encode()),
    ]
    compatible = _child(head, _HH, "compatibleDocument")
    target = index_of(TARGET_PROGRAM, compatible.get("targetProgram") if compatible is not None else None, 0)
    records.append(rec.Record(rec.COMPATIBLE_DOCUMENT, 0, struct.pack("<I", target)))
    records.append(rec.Record(rec.LAYOUT_COMPATIBILITY, 1, b"\0" * 20))
    records.append(rec.Record(rec.TRACKCHANGE, 1, _track_settings(head)))
    return DocInfoResult(records, section_count)


def _track_settings(head: etree._Element) -> bytes:
    """The change-tracking settings record: 4 when the header has its settings
    (56 when not, as Hancom writes it), and the password algorithm last (4 for
    SHA1)."""

    config = _child(head, _HH, "trackchageConfig")
    sha1 = config is not None and any(
        item.get("name") == "algorithm-name" and (item.text or "").strip() == "SHA1"
        for item in config.iter(f"{{{NS['config']}}}config-item")
    )
    return struct.pack("<I", 4 if config is not None else 56) + b"\0" * 1024 + struct.pack("<I", 4 if sha1 else 0)


def set_bin_count(result: DocInfoResult, items: list[di.BinDataItem]) -> None:
    """Insert the ``BIN_DATA`` records (right after ``ID_MAPPINGS``) and their count."""

    mappings = result.records[1]
    counts = list(struct.unpack(f"<{len(mappings.payload) // 4}i", mappings.payload))
    counts[0] = len(items)
    mappings.payload = struct.pack(f"<{len(counts)}i", *counts)
    result.records[2:2] = [rec.Record(rec.BIN_DATA, 1, item.encode()) for item in items]
