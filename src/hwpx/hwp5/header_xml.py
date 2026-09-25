# SPDX-License-Identifier: Apache-2.0
"""DocInfo of an HWP 5.0 document -> ``Contents/header.xml``.

Ids stay one-to-one with the DocInfo records: ``charPr``, ``paraPr``,
``tabPr`` and ``style`` ids are the record indexes, ``borderFill``,
``numbering``, ``bullet`` and ``memoPr`` ids are the record indexes plus one,
and a font id is its index within its language list.
"""

from __future__ import annotations

import base64
import struct
from datetime import datetime, timedelta

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import docinfo as di
from . import records as rec
from .errors import Hwp5Error
from .owpml import (
    ALIGN_H,
    ALIGN_V,
    BORDER_LINE,
    BORDER_WIDTH,
    BREAK_LATIN,
    BREAK_NON_LATIN,
    CHAR_LINE,
    FAMILY,
    FONT_TYPE,
    GRADATION,
    HATCH,
    HEADING,
    HP10,
    HWPUNITCHAR,
    IMAGE_MODE,
    LANG_ATTRS,
    LANGS,
    LINE_SPACING,
    LINE_WRAP,
    MEMO_TYPE,
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
    color,
    flag,
    image_effect,
    root,
    serialize,
    sub,
    token,
    xml_text,
)


def _bits(value: int, lo: int, width: int) -> int:
    return (value >> lo) & ((1 << width) - 1)


# -- fonts ------------------------------------------------------------------------------


def _font(parent: etree._Element, index: int, font: di.FaceName) -> None:
    element = sub(
        parent,
        "hh:font",
        (("id", index), ("face", font.name), ("type", FONT_TYPE.get(font.font_type, "TTF")), ("isEmbedded", 0)),
    )
    if font.props & di.FaceName.HAS_ALT:
        sub(
            element,
            "hh:substFont",
            (
                ("face", font.alt_name),
                ("type", FONT_TYPE.get(font.alt_type, "TTF") if font.alt_type else "TTF"),
                ("isEmbedded", 0),
                ("binaryItemIDRef", ""),
            ),
        )
    if font.props & di.FaceName.HAS_TYPE_INFO and len(font.type_info) >= 10:
        info = font.type_info
        attrs: list[tuple[str, object]] = []
        if info[0] < len(FAMILY):
            attrs.append(("familyType", FAMILY[info[0]]))
        attrs += [
            ("weight", info[2]),
            ("proportion", info[3]),
            ("contrast", info[4]),
            ("strokeVariation", info[5]),
            ("armStyle", info[6]),
            ("letterform", info[7]),
            ("midline", info[8]),
            ("xHeight", info[9]),
        ]
        sub(element, "hh:typeInfo", attrs)


def _fontfaces(parent: etree._Element, info: di.DocInfo) -> None:
    faces = sub(parent, "hh:fontfaces", (("itemCnt", len(LANGS)),))
    for lang, attr in zip(LANGS, LANG_ATTRS):
        fonts = info.fonts.get(attr, [])
        face = sub(faces, "hh:fontface", (("lang", lang), ("fontCnt", len(fonts))))
        for index, font in enumerate(fonts):
            _font(face, index, font)


# -- border and fill --------------------------------------------------------------------


def _line(parent: etree._Element, name: str, line: di.Line) -> None:
    sub(
        parent,
        name,
        (
            ("type", token(BORDER_LINE, line.kind)),
            ("width", token(BORDER_WIDTH, line.width)),
            ("color", color(line.color)),
        ),
    )


def fill_brush(parent: etree._Element, fill: di.Fill) -> None:
    """``hc:fillBrush`` for a fill (nothing for an empty one)."""

    if not fill.kind:
        return
    brush = sub(parent, "hc:fillBrush")
    alphas = list(fill.alphas)

    def alpha() -> int:
        return alphas.pop(0) if alphas else 0

    if fill.kind & di.FILL_SOLID:
        attrs: list[tuple[str, object]] = [
            ("faceColor", color(fill.back_color)),
            ("hatchColor", color(fill.pattern_color)),
        ]
        if fill.pattern_type >= 0:
            attrs.append(("hatchStyle", token(HATCH, fill.pattern_type)))
        attrs.append(("alpha", alpha()))
        sub(brush, "hc:winBrush", attrs)
    if fill.kind & di.FILL_GRADATION:
        step_center = fill.additional[0] if fill.additional else 50
        gradation = sub(
            brush,
            "hc:gradation",
            (
                ("type", GRADATION.get(fill.grad_type, "LINEAR")),
                ("angle", fill.grad_angle),
                ("centerX", fill.grad_center_x),
                ("centerY", fill.grad_center_y),
                ("step", fill.grad_step),
                ("colorNum", len(fill.grad_colors)),
                ("stepCenter", step_center),
                ("alpha", alpha()),
            ),
        )
        for value in fill.grad_colors:
            sub(gradation, "hc:color", (("value", color(value)),))
    if fill.kind & di.FILL_IMAGE:
        image = sub(brush, "hc:imgBrush", (("mode", token(IMAGE_MODE, fill.image_mode)),))
        sub(
            image,
            "hc:img",
            (
                ("binaryItemIDRef", f"image{fill.image_bin_id}" if fill.image_bin_id else ""),
                ("bright", fill.image_bright),
                ("contrast", fill.image_contrast),
                *image_effect(fill.image_effect),
                ("alpha", alpha()),
            ),
        )


def _border_fill(parent: etree._Element, index: int, bf: di.BorderFill) -> None:
    props = bf.props
    element = sub(
        parent,
        "hh:borderFill",
        (
            ("id", index + 1),
            ("threeD", flag(props & 0x1)),
            ("shadow", flag(props & 0x2)),
            ("centerLine", "NONE"),
            ("breakCellSeparateLine", flag(props & (1 << 10))),
        ),
    )
    sub(
        element,
        "hh:slash",
        (
            ("type", SLASH.get(_bits(props, 2, 3), "NONE")),
            ("Crooked", flag(props & (1 << 8))),
            ("isCounter", flag(props & (1 << 11))),
        ),
    )
    sub(
        element,
        "hh:backSlash",
        (
            ("type", SLASH.get(_bits(props, 5, 3), "NONE")),
            ("Crooked", flag(props & (1 << 9))),
            ("isCounter", flag(props & (1 << 12))),
        ),
    )
    _line(element, "hh:leftBorder", bf.left)
    _line(element, "hh:rightBorder", bf.right)
    _line(element, "hh:topBorder", bf.top)
    _line(element, "hh:bottomBorder", bf.bottom)
    if bf.diagonal.kind:
        _line(element, "hh:diagonal", bf.diagonal)
    fill_brush(element, bf.fill)


# -- character shapes -------------------------------------------------------------------


def _lang_attrs(values: list[int]) -> list[tuple[str, object]]:
    return list(zip(LANG_ATTRS, values))


def _char_pr(parent: etree._Element, index: int, cs: di.CharShape) -> None:
    props = cs.props
    element = sub(
        parent,
        "hh:charPr",
        (
            ("id", index),
            ("height", cs.height),
            ("textColor", color(cs.text_color)),
            ("shadeColor", color(cs.shade_color)),
            ("useFontSpace", flag(props & (1 << 25))),
            ("useKerning", flag(props & (1 << 30))),
            ("symMark", token(SYM_MARK, _bits(props, 21, 4))),
            ("borderFillIDRef", cs.border_fill_id if cs.border_fill_id is not None else 0),
        ),
    )
    sub(element, "hh:fontRef", _lang_attrs(cs.font_ids))
    sub(element, "hh:ratio", _lang_attrs(cs.ratios))
    sub(element, "hh:spacing", _lang_attrs(cs.spacings))
    sub(element, "hh:relSz", _lang_attrs(cs.rel_sizes))
    sub(element, "hh:offset", _lang_attrs(cs.offsets))
    if props & 0x1:
        sub(element, "hh:italic")
    if props & 0x2:
        sub(element, "hh:bold")
    underline = _bits(props, 2, 2)
    # Type 2 (centre) is the old strikeout; OWPML keeps it only as a strikeout.
    if underline == 2:
        sub(element, "hh:underline", (("type", "NONE"), ("shape", "SOLID"), ("color", "#000000")))
    else:
        sub(
            element,
            "hh:underline",
            (
                ("type", token(UNDERLINE_TYPE, underline)),
                ("shape", token(CHAR_LINE, _bits(props, 4, 4))),
                ("color", color(cs.underline_color)),
            ),
        )
    strike = _bits(props, 18, 3)
    sub(
        element,
        "hh:strikeout",
        (
            ("shape", token(CHAR_LINE, _bits(props, 26, 4)) if strike else "NONE"),
            ("color", color(cs.strikeout_color if cs.strikeout_color is not None else 0)),
        ),
    )
    sub(element, "hh:outline", (("type", token(OUTLINE, _bits(props, 8, 3))),))
    sub(
        element,
        "hh:shadow",
        (
            ("type", token(SHADOW, _bits(props, 11, 2))),
            ("color", color(cs.shadow_color)),
            ("offsetX", cs.shadow_x),
            ("offsetY", cs.shadow_y),
        ),
    )
    if props & (1 << 13):
        sub(element, "hh:emboss")
    if props & (1 << 14):
        sub(element, "hh:engrave")
    if props & (1 << 15):
        sub(element, "hh:supscript")
    if props & (1 << 16):
        sub(element, "hh:subscript")


# -- tabs, numbering, bullets -------------------------------------------------------------


def _unit_value(raw: int) -> tuple[int, str]:
    """A length stored doubled with the unit in bit 0 (1 means character
    units); a negative one is shifted like any other (-799 is -400 characters)."""

    return raw >> 1, "CHAR" if raw & 1 else "HWPUNIT"


def _tab_pr(parent: etree._Element, index: int, tab: di.TabDef) -> None:
    element = sub(
        parent,
        "hh:tabPr",
        (("id", index), ("autoTabLeft", flag(tab.props & 0x1)), ("autoTabRight", flag(tab.props & 0x2))),
    )
    for item in tab.items:
        value, unit = _unit_value(item.position)
        switch = sub(element, "hp:switch")
        case = sub(switch, "hp:case", (("hp:required-namespace", HWPUNITCHAR),))
        kind = token(TAB_TYPE, item.kind)
        leader = token(BORDER_LINE, item.fill)
        sub(case, "hh:tabItem", (("pos", value), ("type", kind), ("leader", leader), ("unit", unit)))
        default = sub(switch, "hp:default")
        sub(default, "hh:tabItem", (("pos", item.position), ("type", kind), ("leader", leader)))


def _para_head(
    parent: etree._Element, head: di.ParaHead, level: int, start: int | None, text: str | None
) -> None:
    props = head.props
    attrs: list[tuple[str, object]] = []
    if start is not None:
        attrs.append(("start", start))
    attrs += [
        ("level", level),
        ("align", token(PARA_HEAD_ALIGN, _bits(props, 0, 2))),
        ("useInstWidth", flag(props & 0x4)),
        ("autoIndent", flag(props & 0x8)),
        ("widthAdjust", head.width_adjust),
        ("textOffsetType", "HWPUNIT" if props & 0x10 else "PERCENT"),
        ("textOffset", head.text_offset),
        ("numFormat", token(NUMBER_FORMAT, _bits(props, 5, 4))),
        ("charPrIDRef", head.char_shape_id),
        # Hancom reports checkable from bit 5, the low bit of the number format.
        ("checkable", flag(props & (1 << 5))),
    ]
    element = sub(parent, "hh:paraHead", attrs)
    if text is not None:
        element.text = xml_text(text)


def _numbering(parent: etree._Element, index: int, numbering: di.Numbering) -> None:
    element = sub(parent, "hh:numbering", (("id", index + 1), ("start", numbering.start)))
    starts = list(numbering.level_starts or [1] * 7) + list(numbering.extended_starts or [1] * 3)
    heads = numbering.heads + numbering.extended_heads
    for level, head in enumerate(heads):
        _para_head(element, head, level + 1, starts[level] if level < len(starts) else 1, head.format)
    # Records written before levels 8-10 existed get plain digit levels.
    for level in range(len(heads) + 1, 11):
        _para_head(element, di.ParaHead(0, 0, 0, 0), level, 1, None)


def _bullet(parent: etree._Element, index: int, bullet: di.Bullet) -> None:
    use_image = bool(bullet.image_id)
    element = sub(
        parent,
        "hh:bullet",
        (("id", index + 1), ("char", chr(bullet.char) if bullet.char else ""), ("useImage", flag(use_image))),
    )
    if bullet.check_char:
        element.set("checkedChar", chr(bullet.check_char))
    if use_image and len(bullet.image_props) >= 4:
        props = bullet.image_props
        sub(
            element,
            "hc:img",
            (
                ("binaryItemIDRef", f"image{props[3]}"),
                ("bright", struct.unpack("<b", props[0:1])[0]),
                ("contrast", struct.unpack("<b", props[1:2])[0]),
                *image_effect(props[2]),
                ("alpha", 0),
            ),
        )
    _para_head(element, bullet.head, 0, None, None)


# -- paragraph shapes -------------------------------------------------------------------


def _margin_block(
    parent: etree._Element, ps: di.ParaShape, *, doubled: bool
) -> None:
    margin = sub(parent, "hh:margin")
    for name, raw in (
        ("intent", ps.indent),
        ("left", ps.left),
        ("right", ps.right),
        ("prev", ps.prev),
        ("next", ps.next),
    ):
        value, unit = _unit_value(raw)
        if doubled:
            value, unit = raw, "HWPUNIT"
        sub(margin, f"hc:{name}", (("value", value), ("unit", unit)))
    spacing_type = _bits(ps.props3, 0, 5) if ps.props3 is not None else _bits(ps.props1, 0, 2)
    spacing = ps.line_spacing if ps.line_spacing is not None else ps.line_spacing_old
    kind = token(LINE_SPACING, spacing_type)
    if kind != "PERCENT" and not doubled:
        value, unit = _unit_value(spacing)
    else:
        value, unit = spacing, "HWPUNIT"
    sub(parent, "hh:lineSpacing", (("type", kind), ("value", value), ("unit", unit)))


def _heading(parent: etree._Element, ps: di.ParaShape) -> None:
    kind = _bits(ps.props1, 23, 2)
    level = ps.level if ps.level is not None else _bits(ps.props1, 25, 3)
    if level > 6:
        switch = sub(parent, "hp:switch")
        case = sub(switch, "hp:case", (("hp:required-namespace", HP10),))
        sub(case, "hh:heading", (("type", token(HEADING, kind)), ("idRef", ps.numbering_id), ("level", level)))
        default = sub(switch, "hp:default")
        sub(default, "hh:heading", (("type", "NONE"), ("idRef", 0), ("level", 0)))
    else:
        sub(parent, "hh:heading", (("type", token(HEADING, kind)), ("idRef", ps.numbering_id), ("level", level)))


def _para_pr(parent: etree._Element, index: int, ps: di.ParaShape) -> None:
    p1 = ps.props1
    p2 = ps.props2 or 0
    element = sub(
        parent,
        "hh:paraPr",
        (
            ("id", index),
            ("tabPrIDRef", ps.tab_def_id),
            ("condense", _bits(p1, 9, 7)),
            ("fontLineHeight", flag(p1 & (1 << 22))),
            ("snapToGrid", flag(p1 & (1 << 8))),
            ("suppressLineNumbers", flag(p2 & (1 << 6))),
            ("checked", flag(p2 & (1 << 7))),
            ("textDir", token(TEXT_DIR, _bits(p2, 2, 2))),
        ),
    )
    sub(element, "hh:align", (("horizontal", token(ALIGN_H, _bits(p1, 2, 3))), ("vertical", token(ALIGN_V, _bits(p1, 20, 2)))))
    _heading(element, ps)
    sub(
        element,
        "hh:breakSetting",
        (
            ("breakLatinWord", token(BREAK_LATIN, _bits(p1, 5, 2))),
            ("breakNonLatinWord", token(BREAK_NON_LATIN, _bits(p1, 7, 1))),
            ("widowOrphan", flag(p1 & (1 << 16))),
            ("keepWithNext", flag(p1 & (1 << 17))),
            ("keepLines", flag(p1 & (1 << 18))),
            ("pageBreakBefore", flag(p1 & (1 << 19))),
            ("lineWrap", token(LINE_WRAP, _bits(p2, 0, 2))),
        ),
    )
    sub(element, "hh:autoSpacing", (("eAsianEng", flag(p2 & (1 << 4))), ("eAsianNum", flag(p2 & (1 << 5)))))
    switch = sub(element, "hp:switch")
    _margin_block(sub(switch, "hp:case", (("hp:required-namespace", HWPUNITCHAR),)), ps, doubled=False)
    _margin_block(sub(switch, "hp:default"), ps, doubled=True)
    offsets = ps.border_offsets
    sub(
        element,
        "hh:border",
        (
            ("borderFillIDRef", ps.border_fill_id),
            ("offsetLeft", offsets[0]),
            ("offsetRight", offsets[1]),
            ("offsetTop", offsets[2]),
            ("offsetBottom", offsets[3]),
            ("connect", flag(p1 & (1 << 28))),
            ("ignoreMargin", flag(p1 & (1 << 29))),
        ),
    )


# -- styles and memo shapes -----------------------------------------------------------


def _style(parent: etree._Element, index: int, style: di.Style) -> None:
    sub(
        parent,
        "hh:style",
        (
            ("id", index),
            ("type", token(STYLE_TYPE, style.props & 0x3)),
            ("name", style.name),
            ("engName", style.eng_name),
            ("paraPrIDRef", style.para_shape_id),
            ("charPrIDRef", style.char_shape_id),
            ("nextStyleIDRef", style.next_id),
            ("langID", style.lang_id),
            ("lockForm", flag(style.props & 0x4)),
        ),
    )


def _memo_pr(parent: etree._Element, index: int, memo: di.MemoShape) -> None:
    sub(
        parent,
        "hh:memoPr",
        (
            ("id", index + 1),
            ("width", memo.width),
            ("lineWidth", memo.line_width),
            ("lineType", token(BORDER_LINE, memo.line_type)),
            ("lineColor", color(memo.line_color)),
            ("fillColor", color(memo.fill_color)),
            ("activeColor", color(memo.active_color)),
            ("memoType", token(MEMO_TYPE, memo.memo_type)),
        ),
    )


# -- the part -----------------------------------------------------------------------------


def _record(info: di.DocInfo, tag: int) -> rec.Record | None:
    for record in info.other:
        if record.tag == tag:
            return record
    return None


#: The OWPML type of each kind of tracked change.
TRACK_CHANGE_TYPE = {16: "Insert", 17: "Delete", 19: "ParaShape"}
#: A tracked change keeps local (Korean) time; OWPML writes it in UTC.
TRACK_TIME_OFFSET = timedelta(hours=9)


def track_changes(info: di.DocInfo) -> tuple[list[di.TrackChange], list[di.TrackChangeAuthor]] | None:
    """The document's tracked changes and their authors; None when a record
    cannot be read, a change is of a kind with no OWPML type or its time is
    no date."""

    try:
        changes = [di.TrackChange.decode(r.payload) for r in info.other if r.tag == rec.TRACK_CHANGE]
        authors = [di.TrackChangeAuthor.decode(r.payload) for r in info.other if r.tag == rec.TRACK_CHANGE_AUTHOR]
        for change in changes:
            datetime(*change.time)
    except (Hwp5Error, ValueError):
        return None
    if any(change.kind not in TRACK_CHANGE_TYPE for change in changes):
        return None
    return changes, authors


def _track_changes(refs: etree._Element, changes: list[di.TrackChange], authors: list[di.TrackChangeAuthor]) -> None:
    if changes:
        items = sub(refs, "hh:trackChanges", (("itemCnt", len(changes)),))
        for index, change in enumerate(changes, 1):
            when = datetime(*change.time) - TRACK_TIME_OFFSET
            paragraph_shape = change.kind == 19
            attrs: list[tuple[str, object]] = [
                ("type", TRACK_CHANGE_TYPE[change.kind]),
                ("date", when.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ("authorID", change.author),
                ("hide", 0 if paragraph_shape else flag(change.words[3])),
                ("id", index),
            ]
            if paragraph_shape:
                attrs.append(("parashapeID", change.words[3]))
            sub(items, "hh:trackChange", attrs)
    if authors:
        items = sub(refs, "hh:trackChangeAuthors", (("itemCnt", len(authors)),))
        for index, author in enumerate(authors, 1):
            sub(items, "hh:trackChangeAuthor", (("name", author.name), ("mark", flag(author.mark)), ("id", index)))


def forbidden_words(info: di.DocInfo) -> tuple[str, str, str, str] | None:
    """The document's own lists of characters kept off the start or end of a
    line; None when it keeps Hancom's (four empty lists) or the record cannot
    be read."""

    record = _record(info, rec.FORBIDDEN_CHAR)
    if record is None:
        return None
    try:
        words = di.ForbiddenChars.decode(record.payload).words
    except Hwp5Error:
        return None
    return words if any(words) else None


def _forbidden_word_list(head: etree._Element, words: tuple[str, str, str, str]) -> None:
    """``hh:forbiddenWordList``: each list as base64 of its UTF-16 text in
    72-character lines, the way Hancom writes it; an empty list is a space."""

    listing = sub(head, "hh:forbiddenWordList", (("itemCnt", len(words)),))
    for word in words:
        text = base64.b64encode((word or " ").encode("utf-16-le", errors="surrogatepass")).decode("ascii")
        sub(listing, "hh:forbiddenWord").text = "\n".join(text[i : i + 72] for i in range(0, len(text), 72))


def build_header(
    info: di.DocInfo,
    section_count: int,
    *,
    link_doc: bytes | None = None,
    license_mark: tuple[str, int, int] | None = None,
) -> bytes:
    """``Contents/header.xml`` for *info*."""

    head = root("hh:head")
    head.set("version", "1.5")
    head.set("secCnt", str(section_count))
    props = info.properties
    sub(
        head,
        "hh:beginNum",
        (
            ("page", props.page_start),
            ("footnote", props.footnote_start),
            ("endnote", props.endnote_start),
            ("pic", props.picture_start),
            ("tbl", props.table_start),
            ("equation", props.equation_start),
        ),
    )
    refs = sub(head, "hh:refList")
    _fontfaces(refs, info)
    fills = sub(refs, "hh:borderFills", (("itemCnt", len(info.border_fills)),))
    for index, bf in enumerate(info.border_fills):
        _border_fill(fills, index, bf)
    chars = sub(refs, "hh:charProperties", (("itemCnt", len(info.char_shapes)),))
    for index, cs in enumerate(info.char_shapes):
        _char_pr(chars, index, cs)
    tabs = sub(refs, "hh:tabProperties", (("itemCnt", len(info.tab_defs)),))
    for index, tab in enumerate(info.tab_defs):
        _tab_pr(tabs, index, tab)
    if info.numberings:
        numberings = sub(refs, "hh:numberings", (("itemCnt", len(info.numberings)),))
        for index, numbering in enumerate(info.numberings):
            _numbering(numberings, index, numbering)
    if info.bullets:
        bullets = sub(refs, "hh:bullets", (("itemCnt", len(info.bullets)),))
        for index, bullet in enumerate(info.bullets):
            _bullet(bullets, index, bullet)
    paras = sub(refs, "hh:paraProperties", (("itemCnt", len(info.para_shapes)),))
    for index, ps in enumerate(info.para_shapes):
        _para_pr(paras, index, ps)
    styles = sub(refs, "hh:styles", (("itemCnt", len(info.styles)),))
    for index, style in enumerate(info.styles):
        _style(styles, index, style)
    if info.memo_shapes:
        memos = sub(refs, "hh:memoProperties", (("itemCnt", len(info.memo_shapes)),))
        for index, memo in enumerate(info.memo_shapes):
            _memo_pr(memos, index, memo)
    tracked = track_changes(info)
    if tracked is not None:
        _track_changes(refs, *tracked)
    words = forbidden_words(info)
    if words is not None:
        _forbidden_word_list(head, words)
    target = info.compatible_target or 0
    compatible = sub(head, "hh:compatibleDocument", (("targetProgram", token(TARGET_PROGRAM, target)),))
    sub(compatible, "hh:layoutCompatibility")
    option = sub(head, "hh:docOption")
    path, page_inherit, footnote_inherit = _link_doc(link_doc)
    sub(
        option,
        "hh:linkinfo",
        (("path", path), ("pageInherit", flag(page_inherit)), ("footnoteInherit", flag(footnote_inherit))),
    )
    if license_mark is not None:
        kind, license_flag, country = license_mark
        attrs: list[tuple[str, object]] = [("type", kind), ("flag", license_flag)]
        if country:
            attrs.append(("lang", country))
        sub(option, "hh:licensemark", attrs)
    # Hancom reports 4 for a document that carries the track-change settings
    # record whatever its value, and 56 for an older one without it.
    settings = _record(info, rec.TRACKCHANGE)
    config = sub(head, "hh:trackchageConfig", (("flags", 4 if settings is not None else 56),))
    # The last word names the algorithm of the change-tracking password: 4 is SHA1.
    if settings is not None and len(settings.payload) >= 8 and settings.payload[-4:] == TRACK_PASSWORD_SHA1:
        password = sub(config, "config:config-item-set", (("name", "TrackChangePasswordInfo"),))
        sub(password, "config:config-item", (("name", "algorithm-name"), ("type", "string"))).text = "SHA1"
    return serialize(head)


#: The last word of the change-tracking settings record when its password is
#: hashed with SHA1.
TRACK_PASSWORD_SHA1 = struct.pack("<I", 4)


def _link_doc(data: bytes | None) -> tuple[str, bool, bool]:
    """``DocOptions/_LinkDoc``: a 260-character path, then a flag word whose
    bit 0 inherits page numbers and bit 1 inherits footnote numbers."""

    if not data or len(data) < 520:
        return "", False, False
    path = data[:520].decode("utf-16-le", errors="replace").split("\0", 1)[0]
    flags = struct.unpack_from("<I", data, 520)[0] if len(data) >= 524 else 0
    return path, bool(flags & 0x1), bool(flags & 0x2)
