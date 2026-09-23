# SPDX-License-Identifier: Apache-2.0
"""Opening HWP 5.0 (``.hwp``) documents through ``HwpxDocument.open``.

Every document here is synthetic: records are built field by field with the
same codecs the reader uses.
"""

from __future__ import annotations

import io
import struct
import warnings
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.hwp5 import bodytext as bt
from hwpx.hwp5 import cfb
from hwpx.hwp5 import controls as ct
from hwpx.hwp5 import docinfo as di
from hwpx.hwp5 import records as rec
from hwpx.hwp5 import shapes as sh
from hwpx.hwp5.errors import Hwp5ConversionWarning, Hwp5Error
from hwpx.hwp5.fileheader import FileHeader

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _docinfo() -> list[rec.Record]:
    fonts = [di.FaceName(0x01, "함초롬바탕") for _ in range(7)]
    char_shapes = [di.CharShape(font_ids=[0] * 7), di.CharShape(font_ids=[0] * 7, props=0x2, text_color=0x0000FF)]
    fill = di.BorderFill(fill=di.Fill(di.FILL_SOLID, 0x00FFFFFF, 0, -1, additional=b"", alphas=b"\0"))
    para = di.ParaShape(props1=0x100)
    mappings = [0, 1, 1, 1, 1, 1, 1, 1, 2, len(char_shapes), 1, 0, 0, 1, 1, 0, 0, 0]
    records = [
        rec.Record(rec.DOCUMENT_PROPERTIES, 0, di.DocumentProperties().encode()),
        rec.Record(rec.ID_MAPPINGS, 0, struct.pack("<18i", *mappings)),
    ]
    records += [rec.Record(rec.FACE_NAME, 1, font.encode()) for font in fonts]
    records += [rec.Record(rec.BORDER_FILL, 1, di.BorderFill().encode()), rec.Record(rec.BORDER_FILL, 1, fill.encode())]
    records += [rec.Record(rec.CHAR_SHAPE, 1, shape.encode()) for shape in char_shapes]
    records += [rec.Record(rec.TAB_DEF, 1, di.TabDef().encode())]
    records += [rec.Record(rec.PARA_SHAPE, 1, para.encode())]
    records += [rec.Record(rec.STYLE, 1, di.Style("바탕글", "Normal").encode())]
    return records


def _para_header(chars: int, char_shapes: int, *, lines: int = 1, mask: int = 0, breaks: int = 0) -> bytes:
    return struct.pack("<IIHBBHHHIH", chars, mask, 0, 0, breaks, char_shapes, 0, lines, 0, 0)


def _control_mask(text: bytes) -> tuple[int, int]:
    """The control-character mask (paragraph break excluded) and section/column break bits."""

    chunks, _ = bt.split_text(text)
    mask = 0
    for chunk in chunks:
        if chunk.kind != "text" and chunk.code != 13:
            mask |= 1 << chunk.code
    ids = {chunk.control_id for chunk in chunks}
    return mask, (1 if "secd" in ids else 0) | (2 if "cold" in ids else 0)


def _extended(code: int, ctrl: str) -> bytes:
    return struct.pack("<HI", code, bt.ctrl_word(ctrl)) + b"\0" * 8 + struct.pack("<H", code)


def _line_seg() -> bytes:
    return struct.pack("<IiiiiiiiI", 0, 0, 1000, 1000, 850, 600, 0, 42520, 0x60000)


def _paragraph(level: int, text: bytes, shapes: list[tuple[int, int]], controls: list[rec.Record]) -> list[rec.Record]:
    units = len(text) // 2
    mask, breaks = _control_mask(text)
    out = [rec.Record(rec.PARA_HEADER, level, _para_header(units, len(shapes), mask=mask, breaks=breaks))]
    if units > 1:
        out.append(rec.Record(rec.PARA_TEXT, level + 1, text))
    out.append(rec.Record(rec.PARA_CHAR_SHAPE, level + 1, b"".join(struct.pack("<II", p, s) for p, s in shapes)))
    out.append(rec.Record(rec.PARA_LINE_SEG, level + 1, _line_seg()))
    out.extend(controls)
    return out


def _u16(value: int) -> bytes:
    return struct.pack("<H", value)


def _section() -> list[rec.Record]:
    secd = struct.pack("<IIHHHIHHHHH", bt.ctrl_word("secd"), 0, 1134, 0, 0, 8000, 1, 0, 0, 0, 0) + b"\0" * 19
    page = struct.pack("<9II", 59528, 84186, 8504, 8504, 5668, 4252, 4252, 4252, 0, 0)
    note = struct.pack("<IHHHHiHHHBBI", 0, 0, 0, ord(")"), 1, -1, 850, 567, 283, 1, 1, 0)
    border = struct.pack("<IHHHHH", 1, 1417, 1417, 1417, 1417, 1)
    cold = struct.pack("<IHHHBBI", bt.ctrl_word("cold"), 0x1004, 0, 0, 0, 0, 0)
    first = _paragraph(
        0,
        _extended(2, "secd") + _extended(2, "cold") + _u16(13),
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, secd),
            rec.Record(rec.PAGE_DEF, 2, page),
            rec.Record(rec.FOOTNOTE_SHAPE, 2, note),
            rec.Record(rec.FOOTNOTE_SHAPE, 2, note),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.PAGE_BORDER_FILL, 2, border),
            rec.Record(rec.CTRL_HEADER, 1, cold),
        ],
    )
    # A tab stores its width, leader and type, padded with three spaces.
    tab = _u16(9) + struct.pack("<IBB", 4000, 0, 0) + " ".encode("utf-16-le") * 3 + _u16(9)
    body = "가나다 ".encode("utf-16-le") + "abc".encode("utf-16-le") + tab + "끝".encode("utf-16-le") + _u16(10)
    body += "둘째 줄".encode("utf-16-le") + _u16(13)
    second = _paragraph(0, body, [(0, 0), (4, 1), (7, 0)], [])
    common = struct.pack("<IIiiIIihhhhIi", bt.ctrl_word("tbl "), 0x082A2211, 0, 0, 42000, 3600, 0, 0, 0, 0, 0, 77, 0)
    common += _u16(0) + _u16(0)  # empty description, then two reserved bytes
    table = struct.pack("<IHHH4HHHH", 2, 1, 2, 0, 510, 510, 141, 141, 2, 1, 0)
    cells: list[rec.Record] = []
    for col, label in enumerate(("셀1", "셀2")):
        header = ct.CellHeader(1, 0x00200000, 0, col, 0, 1, 1, 21000, 3600, (510, 510, 141, 141), 1, 21000).encode()
        cells.append(rec.Record(rec.LIST_HEADER, 2, header))
        cells += _paragraph(2, label.encode("utf-16-le") + _u16(13), [(0, 0)], [])
    third = _paragraph(
        0,
        _extended(11, "tbl ") + _u16(13),
        [(0, 0)],
        [rec.Record(rec.CTRL_HEADER, 1, common), rec.Record(rec.TABLE, 2, table), *cells],
    )
    return first + second + third


def _field_end(ctrl: str, prop: int, editable: int, number: int = 0) -> bytes:
    params = struct.pack("<III", (bt.ctrl_word(ctrl) & 0xFFFFFF) | prop << 24, editable, number)
    return _u16(4) + params + _u16(4)


def _fields() -> list[rec.Record]:
    """A click-here field with a name and a hyperlink, each around some text."""

    text = _extended(3, "%clk") + "이름".encode("utf-16-le") + _field_end("%clk", 9, 1)
    text += " 링크 ".encode("utf-16-le") + _extended(3, "%hlk") + "누리집".encode("utf-16-le")
    text += _field_end("%hlk", 0, 0) + _u16(13)
    click = ct.FieldCtrl("%clk", 1, 9, "Clickhere:set:66:Direction:wstring:9:이름을 입력하세요 HelpState:wstring:0: ", 1234)
    link = ct.FieldCtrl("%hlk", 0, 0, "https\\://example.com/a;1;0;0;", 1235)
    return _paragraph(
        0,
        text,
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, click.encode()),
            rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("성명")),
            rec.Record(rec.CTRL_HEADER, 1, link.encode()),
        ],
    )


def _highlights(*, unmapped: bool = False) -> list[rec.Record]:
    """Two highlighter ranges in a paragraph of two runs; the first ends where
    the second run starts. *unmapped* adds a range tag kind OWPML has no form for."""

    text = "형광펜 칠한 글".encode("utf-16-le") + _u16(13)
    tags = [(0, 3, 2 << 24 | 0x00FFFF), (4, 7, 2 << 24 | 0xFFCCE5)]
    if unmapped:
        tags.insert(0, (0, 8, 0))
    records = _paragraph(0, text, [(0, 0), (3, 1)], [])
    header = bytearray(records[0].payload)
    struct.pack_into("<H", header, 14, len(tags))  # the range tag count
    records[0] = rec.Record(rec.PARA_HEADER, 0, bytes(header))
    records.append(rec.Record(rec.PARA_RANGE_TAG, 1, b"".join(struct.pack("<III", *tag) for tag in tags)))
    return records


def _markers() -> list[rec.Record]:
    """Page number place, page hiding, a new number, an auto number, a
    bookmark, an index mark, a dutmal and a title mark in one paragraph."""

    title_mark = _u16(8) + struct.pack("<I", bt.ctrl_word("Mtit")) + " ".encode("utf-16-le") * 4 + _u16(8)
    text = _extended(21, "pgnp") + _extended(21, "pghd") + _extended(21, "nwno") + _extended(18, "atno")
    text += "쪽".encode("utf-16-le") + title_mark + _extended(22, "bokm") + _extended(22, "idxm") + _extended(23, "tdut")
    text += _u16(13)
    controls = [
        rec.Record(rec.CTRL_HEADER, 1, ct.PageNumberPosition(0x600, side_char=ord("-")).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.PageHiding(0x18).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.NewNumber(4, 12).encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.AutoNumber(1, 1, suffix_char=ord(")")).encode()),
        rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bt.ctrl_word("bokm"))),
        rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("처음")),
        rec.Record(rec.CTRL_HEADER, 1, ct.IndexMark("가나", "다라").encode()),
        rec.Record(rec.CTRL_HEADER, 1, ct.Dutmal("협동조합", "coop", 1, 0, 0, 0, 1).encode()),
    ]
    return _paragraph(0, text, [(0, 0)], controls)


def _compose() -> list[rec.Record]:
    """Two characters set over each other in a rectangle, between text; the
    record's text starts with the rectangle's glyph."""

    text = "앞".encode("utf-16-le") + _extended(23, "tcps") + "뒤".encode("utf-16-le") + _u16(13)
    compose = ct.Compose("\u25a1가나", 3, -3, 1, [1, 0] + [ct.NO_CHAR_SHAPE] * 8)
    return _paragraph(0, text, [(0, 0)], [rec.Record(rec.CTRL_HEADER, 1, compose.encode())])


_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _text_box() -> list[rec.Record]:
    """A rectangle text box: the object header, its shape component with the
    line, fill and shadow, a named paragraph list and the corners."""

    common = ct.ObjectCommon("gso ", 0x000A2211, 0, 0, 20000, 10000, 0, (0, 0, 0, 0), 185, 0, "", b"\0\0")
    fill = di.Fill(di.FILL_SOLID, 0x00FFE5CC, 0x00FFFFFF, -1, additional=b"", alphas=b"\0")
    style = sh.DrawingStyle(0, 283, 0xC0000041, 0, fill, 0, 0xB2B2B2, 0, 0, 185)
    component = sh.ShapeComponent(
        "$rec", True, 0, 0, 0, 1, 20000, 10000, 20000, 10000, 1 << 19 | 1 << 24, 0, 10000, 5000,
        [_IDENTITY, _IDENTITY, _IDENTITY], style.encode(),
    )
    box = sh.TextBox(1, 0x00200000, 0, (283, 283, 283, 283), 20000, bytes(8), 0, "상자")
    corners = sh.Rectangle(0, [(0, 0), (20000, 0), (20000, 10000), (0, 10000)])
    return _paragraph(
        0,
        _extended(11, "gso ") + _u16(13),
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, common.encode()),
            rec.Record(rec.SHAPE_COMPONENT, 2, component.encode()),
            rec.Record(rec.LIST_HEADER, 3, box.encode()),
            *_paragraph(3, "글상자 안".encode("utf-16-le") + _u16(13), [(0, 0)], []),
            rec.Record(rec.SHAPE_COMPONENT_RECTANGLE, 3, corners.encode()),
        ],
    )


def _picture_effects() -> list[rec.Record]:
    """The captioned picture again, now with a shadow, a glow whose colour is
    saturated, a soft edge and a reflection."""

    records = _picture()
    index = next(i for i, r in enumerate(records) if r.tag == rec.SHAPE_COMPONENT_PICTURE)
    picture = sh.Picture.decode(records[index].payload)
    picture.effect_list = sh.PictureEffects(
        sh.ShadowEffect(0, 0.5, 600.0, 180.0, 600.0, 4, (0.0, 0.0), (1.0, 1.0), 0, sh.EffectColor(0, 0x000000)),
        sh.GlowEffect(0.5, 500.0, sh.EffectColor(0, 0xE9AE2B, [(516, 1.75)])),
        300.0,
        sh.ReflectionEffect(6, 50.0, 90.0, 0.0, (0.0, 0.0), (1.0, -1.0), 0, (0.5, 0.0), (0.997, 0.5), 90.0),
    )
    picture.effects = picture.effect_list.flags
    records[index] = rec.Record(rec.SHAPE_COMPONENT_PICTURE, records[index].level, picture.encode())
    return records


def _hidden_comment() -> list[rec.Record]:
    """A hidden comment: a paragraph list under its control, like a note body."""

    text = "본문".encode("utf-16-le") + _extended(15, "tcmt") + _u16(13)
    body = ct.ListHeader(1, 0, bytes(10)).encode()
    return _paragraph(
        0,
        text,
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bt.ctrl_word("tcmt"))),
            rec.Record(rec.LIST_HEADER, 2, body),
            *_paragraph(2, "숨은 설명".encode("utf-16-le") + _u16(13), [(0, 0)], []),
        ],
    )


def _forms() -> list[rec.Record]:
    """A checked check box, a number-only edit box and a combo box, as Hancom
    writes them."""

    common = [
        ("Name", "wstring", "chk"), ("GroupName", "wstring", ""), ("TabStop", "bool", "1"), ("TabOrder", "int", "0"),
        ("Command", "wstring", ""), ("Editable", "bool", "1"), ("ForeColor", "int", "0"), ("BackColor", "int", "16777215"),
        ("Enabled", "bool", "1"), ("BorderType", "int", "0"), ("DrawFrame", "bool", "1"), ("Printable", "bool", "1"),
    ]
    char = [("CharShapeID", "int", "0"), ("FollowContext", "bool", "0"), ("AutoSize", "bool", "0"), ("WordWrap", "bool", "0")]
    check = ct.FormObject("+cbt", [
        ("CommonSet", common),
        ("CharShapeSet", char),
        ("ButtonSet", [("Caption", "wstring", "동의함"), ("Value", "int", "1"), ("TriState", "bool", "0"), ("BackStyle", "int", "1")]),
    ])
    edit = ct.FormObject("+edt", [
        ("CommonSet", [("Name", "wstring", "num")] + common[1:6] + [("ForeColor", "int", "15003635")] + common[7:]),
        ("CharShapeSet", char),
        ("EditSet", [
            ("Text", "wstring", "1234"), ("MultiLine", "bool", "0"), ("PasswordChar", "wstring", "X"),
            ("MaxLength", "int", "2147483647"), ("ScrollBars", "int", "0"), ("TabKeyBehavior", "int", "0"),
            ("Number", "bool", "1"), ("ReadOnly", "bool", "0"), ("AlignText", "int", "2"),
        ]),
    ])
    combo = ct.FormObject("+cob", [
        ("CommonSet", [("Name", "wstring", "pick")] + common[1:]),
        ("CharShapeSet", char),
        ("ComboBoxSet", [("ListBoxRows", "int", "10"), ("Text", "wstring", "가"), ("ListBoxWidth", "int", "0"), ("EditEnable", "bool", "1")]),
    ])
    controls: list[rec.Record] = []
    for value in (check, edit, combo):
        header = ct.ObjectCommon("form", 0x002A6211, 0, 0, 9921, 1984, 0, (0, 0, 0, 0), 0, 0, "", b"\0\0")
        controls += [rec.Record(rec.CTRL_HEADER, 1, header.encode()), rec.Record(rec.FORM_OBJECT, 2, value.encode())]
    return _paragraph(0, _extended(11, "form") * 3 + _u16(13), [(0, 0)], controls)


def _drawings() -> list[rec.Record]:
    """A closed curve of a line and two curved segments, and a connector with
    two control points between the shapes of instance ids 185 and 186."""

    records: list[rec.Record] = []
    for kind, geometry_tag, geometry, fill in (
        (
            "$cur",
            rec.SHAPE_COMPONENT_CURVE,
            sh.Curve([(0, 0), (8000, 0), (8000, 6000), (0, 0)], [0, 1, 1]),
            di.Fill(di.FILL_SOLID, 0x00FFFFFF, 0, -1, additional=b"", alphas=b"\0"),
        ),
        (
            "$col",
            rec.SHAPE_COMPONENT_LINE,
            sh.ConnectLine((0, 0), (8000, 6000), 1, 185, 1, 186, 2, [(0, 0, 3), (0, 6000, 26)]),
            di.Fill(),
        ),
    ):
        common = ct.ObjectCommon("gso ", 0x000A2211, 0, 0, 8000, 6000, 0, (0, 0, 0, 0), 190, 0, "", b"\0\0")
        style = sh.DrawingStyle(0, 33, 0xC0000041, 0, fill, 0, 0xB2B2B2, 0, 0, 190)
        component = sh.ShapeComponent(
            kind, True, 0, 0, 0, 1, 8000, 6000, 8000, 6000, 1 << 19, 0, 4000, 3000,
            [_IDENTITY, _IDENTITY, _IDENTITY], style.encode(),
        )
        records += _paragraph(
            0,
            _extended(11, "gso ") + _u16(13),
            [(0, 0)],
            [
                rec.Record(rec.CTRL_HEADER, 1, common.encode()),
                rec.Record(rec.SHAPE_COMPONENT, 2, component.encode()),
                rec.Record(geometry_tag, 3, geometry.encode()),
            ],
        )
    return records


def _memo() -> list[rec.Record]:
    """A memo field; its body hangs on the paragraph after a ``MEMO_LIST`` record."""

    text = _extended(3, "%%me") + "검토".encode("utf-16-le") + _field_end("%%me", 0, 1, 1) + _u16(13)
    memo = ct.FieldCtrl("%unk", 1, 0, "", 4321, 1)
    records = _paragraph(0, text, [(0, 0)], [rec.Record(rec.CTRL_HEADER, 1, memo.encode())])
    body = ct.ListHeader(1, 0, bytes(10)).encode()
    records += [rec.Record(rec.MEMO_LIST, 1, struct.pack("<I", 1)), rec.Record(rec.LIST_HEADER, 1, body)]
    return records + _paragraph(1, "메모 내용".encode("utf-16-le") + _u16(13), [(0, 0)], [])


def _picture() -> list[rec.Record]:
    """A captioned picture with a first-letter decoration parameter set."""

    common = ct.ObjectCommon("gso ", 0x240A2211, 0, 0, 10000, 8000, 0, (0, 0, 0, 0), 297, 0, "그림입니다.", bytes(2))
    component = sh.ShapeComponent(
        "$pic", True, 0, 0, 0, 1, 10000, 8000, 10000, 8000, 0x24080000, 0, 5000, 4000, [_IDENTITY, _IDENTITY, _IDENTITY]
    )
    corners = [(0, 0), (10000, 0), (10000, 8000), (0, 8000)]
    picture = sh.Picture(0, 0, 0, corners, (0, 0, 10000, 8000), (0, 0, 0, 0), 0, 0, 0, 0, 0, 297, 0, (10000, 8000), bytes(1))
    caption = ct.CaptionHeader(1, 0, 0, 1, 8504, 850, 8504).encode()
    dropcap = ct.ParameterSet(0x021B, [ct.ParameterItem(0x3003, ct.PIT_SET, ct.ParameterSet(0x3003, [ct.ParameterItem(0x7001, 9, 2)]))])
    return _paragraph(
        0,
        _extended(11, "gso ") + _u16(13),
        [(0, 0)],
        [
            rec.Record(rec.CTRL_HEADER, 1, common.encode()),
            rec.Record(rec.CTRL_DATA, 2, dropcap.encode()),
            rec.Record(rec.LIST_HEADER, 2, caption),
            *_paragraph(2, "그림 1".encode("utf-16-le") + _u16(13), [(0, 0)], []),
            rec.Record(rec.SHAPE_COMPONENT, 2, component.encode()),
            rec.Record(rec.SHAPE_COMPONENT_PICTURE, 3, picture.encode()),
        ],
    )


def _master_list(level: int, text: str, *, kind: int = 0, flags: int = 0) -> list[rec.Record]:
    """A master page's paragraph list. Its header holds the text size, where
    the page applies (offset 18: 0 under the section definition, 3 plus the
    page number for an optional page) and its flags (offset 22)."""

    header = struct.pack("<HIHIIHHHH", 1, 0, 0, 42520, 65762, 0, kind, 0, flags) + bytes(10)
    return [rec.Record(rec.LIST_HEADER, level, header), *_paragraph(level, text.encode("utf-16-le") + _u16(13), [(0, 0)], [])]


def _with_master_pages(section: list[rec.Record]) -> list[rec.Record]:
    """Master pages for even and odd pages under the section definition (its
    property bits 30 and 31) and one for page 2 on the section's last
    paragraph, ahead of any memo bodies there, which the definition counts at
    offset 30."""

    out = list(section)
    index = next(i for i, r in enumerate(out) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    secd = bytearray(out[index].payload)
    struct.pack_into("<I", secd, 4, struct.unpack_from("<I", secd, 4)[0] | 1 << 30 | 1 << 31)
    struct.pack_into("<H", secd, 30, 1)
    out[index] = rec.Record(rec.CTRL_HEADER, 1, bytes(secd))
    last_fill = max(i for i, r in enumerate(out) if r.tag == rec.PAGE_BORDER_FILL)
    out[last_fill + 1 : last_fill + 1] = _master_list(2, "짝수 쪽") + _master_list(2, "홀수 쪽", flags=0x2)
    memos = next((i for i, r in enumerate(out) if r.tag == rec.MEMO_LIST), len(out))
    out[memos:memos] = _master_list(1, "둘째 쪽", kind=3 + 2, flags=0x1)
    return out


def make_hwp(
    *,
    flags: int = 1,
    extra_controls: list[rec.Record] | None = None,
    fields: bool = False,
    highlights: bool = False,
    unmapped_range: bool = False,
    memo: bool = False,
    master_page: bool = False,
    label: bool = False,
    markers: bool = False,
    text_box: bool = False,
    picture: bool = False,
    compose: bool = False,
    drawings: bool = False,
    forms: bool = False,
    hidden_comment: bool = False,
    picture_effects: bool = False,
) -> bytes:
    section = _section()
    if picture_effects:
        section += _picture_effects()
    if hidden_comment:
        section += _hidden_comment()
    if forms:
        section += _forms()
    if drawings:
        section += _drawings()
    if compose:
        section += _compose()
    if text_box:
        section += _text_box()
    if picture:
        section += _picture()
    if markers:
        section += _markers()
    if label:
        # A label sheet: the table carries the sheet layout as a parameter set.
        layout = dict(zip(ct.LABEL_ITEMS, (5670, 5670, 28346, 28346, 850, 850, 1, 2, 0, 59528, 84188)))
        index = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tbl ")
        section.insert(index + 1, rec.Record(rec.CTRL_DATA, 2, ct.label_parameter_set(layout)))
    if extra_controls:
        text = _extended(11, "gso ") + _u16(13)
        section += _paragraph(0, text, [(0, 0)], extra_controls)
    if fields:
        section += _fields()
    if highlights:
        section += _highlights(unmapped=unmapped_range)
    if memo:
        section += _memo()
    if master_page:
        section = _with_master_pages(section)
    return _compound(section, flags=flags)


def _compound(section: list[rec.Record], *, flags: int = 1) -> bytes:
    compressed = bool(flags & 1)

    def pack(records: list[rec.Record]) -> bytes:
        raw = rec.serialize_records(records)
        return rec.deflate(raw) if compressed else raw

    return cfb.build_compound_file(
        [
            ("FileHeader", FileHeader((5, 1, 1, 0), flags).to_bytes()),
            ("DocInfo", pack(_docinfo())),
            ("BodyText/Section0", pack(section)),
            ("PrvText", "미리보기".encode("utf-16-le")),
        ]
    )


@pytest.mark.parametrize("flags", [0, 1])
def test_open_hwp_builds_the_document_model(flags: int) -> None:
    document = HwpxDocument.open(make_hwp(flags=flags))

    texts = ["".join(p.itertext()) for p in document.sections[0].element.iter(f"{HP}p")]
    assert "가나다 abc끝둘째 줄" in texts
    tab = next(document.sections[0].element.iter(f"{HP}tab"))
    assert tab.get("width") == "4000"
    assert tab.tail == "끝"
    assert len(document.sections) == 1
    [table] = [t for s in document.sections for t in s.element.iter(f"{HP}tbl")]
    assert table.get("rowCnt") == "1" and table.get("colCnt") == "2"
    cells = ["".join(tc.itertext()) for tc in table.iter(f"{HP}tc")]
    assert cells == ["셀1", "셀2"]
    assert document._hwp5_report is not None and not document._hwp5_report.unconverted


def test_runs_follow_the_char_shape_boundaries() -> None:
    document = HwpxDocument.open(make_hwp())
    section = document.sections[0].element
    paragraph = [p for p in section.iter(f"{HP}p") if "abc" in "".join(p.itertext())][0]
    runs = [(r.get("charPrIDRef"), "".join(r.itertext())) for r in paragraph.iter(f"{HP}run")]
    assert runs == [("0", "가나다 "), ("1", "abc"), ("0", "끝둘째 줄")]
    header = etree.fromstring(document.package.read("Contents/header.xml"))
    bold = header.find(f".//{HH}charPr[@id='1']")
    assert bold is not None and bold.find(f"{HH}bold") is not None
    assert bold.get("textColor") == "#FF0000"


def test_first_paragraph_carries_the_section_setup() -> None:
    document = HwpxDocument.open(make_hwp())
    first = next(document.sections[0].element.iter(f"{HP}p"))
    page = first.find(f"{HP}run/{HP}secPr/{HP}pagePr")
    assert page is not None and page.get("width") == "59528" and page.get("height") == "84186"
    col = first.find(f"{HP}run/{HP}ctrl/{HP}colPr")
    assert col is not None and col.get("colCount") == "1"


def test_open_from_a_path_and_a_stream(tmp_path: Path) -> None:
    data = make_hwp()
    path = tmp_path / "문서.hwp"
    path.write_bytes(data)
    assert HwpxDocument.open(path).paragraphs
    assert HwpxDocument.open(io.BytesIO(data)).paragraphs
    assert HwpxDocument.open(str(path)).paragraphs


def test_unconverted_controls_are_reported_not_dropped_silently() -> None:
    shape = rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bt.ctrl_word("gso ")) + b"\0" * 44)
    with pytest.warns(Hwp5ConversionWarning, match="control-gso x1"):
        document = HwpxDocument.open(make_hwp(extra_controls=[shape]))
    assert document._hwp5_report.unconverted["control-gso"] == 1


def test_fields_open_as_field_begin_and_end() -> None:
    document = HwpxDocument.open(make_hwp(fields=True))
    section = document.sections[0].element
    begins = list(section.iter(f"{HP}fieldBegin"))
    assert [(b.get("type"), b.get("name"), b.get("editable")) for b in begins] == [
        ("CLICK_HERE", "성명", "1"),
        ("HYPERLINK", "", "0"),
    ]
    params = [{p.get("name"): p.text for p in b.find(f"{HP}parameters")} for b in begins]
    assert params[0]["Prop"] == "9" and params[0]["Direction"] == "이름을 입력하세요"
    assert params[1]["Path"] == "https://example.com/a"
    assert params[1]["Category"] == "HWPHYPERLINK_TYPE_URL"
    ends = [e.get("beginIDRef") for e in section.iter(f"{HP}fieldEnd")]
    assert ends == ["1234", "1235"]
    assert "이름 링크 누리집" in [paragraph.text for paragraph in document.paragraphs]
    assert not document._hwp5_report.unconverted


def test_highlights_open_as_markpen_marks_inside_the_text() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(highlights=True, unmapped_range=True))
    section = document.sections[0].element
    paragraph = [p for p in section.iter(f"{HP}p") if "형광펜" in "".join(p.itertext())][0]
    layout = []
    for run in paragraph.iter(f"{HP}run"):
        for t in run.iter(f"{HP}t"):
            parts = [t.text or ""]
            for child in t:
                parts += [etree.QName(child).localname + ":" + (child.get("color") or ""), child.tail or ""]
            layout.append((run.get("charPrIDRef"), [part for part in parts if part]))
    # The first range ends where the second run starts, so its end stays in the first run.
    assert layout == [
        ("0", ["markpenBegin:#FFFF00", "형광펜", "markpenEnd:"]),
        ("1", [" ", "markpenBegin:#E5CCFF", "칠한 ", "markpenEnd:", "글"]),
    ]
    # A range tag kind OWPML has no element for is counted, without a warning.
    assert document._hwp5_report.dropped == {"range-tag-0": 1}


def test_a_label_sheet_table_keeps_its_layout() -> None:
    document = HwpxDocument.open(make_hwp(label=True))
    [label] = list(document.sections[0].element.iter(f"{HP}label"))
    assert label.getparent().tag == f"{HP}tbl" and label.getparent()[-1] is label
    assert dict(label.attrib) == {
        "topmargin": "5670",
        "leftmargin": "5670",
        "boxwidth": "28346",
        "boxlength": "28346",
        "boxmarginhor": "850",
        "boxmarginver": "850",
        "labelcols": "1",
        "labelrows": "2",
        "landscape": "WIDELY",
        "pagewidth": "59528",
        "pageheight": "84188",
    }
    assert not document._hwp5_report.unconverted


def test_numbering_bookmark_index_and_dutmal_controls_open() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(markers=True))
    section = document.sections[0].element

    def one(name: str) -> etree._Element:
        [element] = list(section.iter(f"{HP}{name}"))
        return element

    assert dict(one("pageNum").attrib) == {"pos": "BOTTOM_RIGHT", "formatType": "DIGIT", "sideChar": "-"}
    hiding = one("pageHiding")
    assert [hiding.get(name) for name in ("hideHeader", "hideBorder", "hideFill")] == ["0", "1", "1"]
    assert dict(one("newNum").attrib) == {"num": "12", "numType": "TABLE"}
    auto = one("autoNum")
    assert (auto.get("num"), auto.get("numType")) == ("1", "FOOTNOTE")
    assert auto.find(f"{HP}autoNumFormat").get("suffixChar") == ")"
    assert one("bookmark").get("name") == "처음"
    assert [key.text for key in one("indexmark")] == ["가나", "다라"]
    dutmal = one("dutmal")
    assert (dutmal.get("posType"), dutmal.get("align")) == ("BOTTOM", "LEFT")
    assert one("titleMark").get("ignore") == "1"
    assert [dutmal.find(f"{HP}mainText").text, dutmal.find(f"{HP}subText").text] == ["협동조합", "coop"]


def test_overlapped_characters_open_as_compose_between_the_text() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(compose=True))
    [compose] = list(document.sections[0].element.iter(f"{HP}compose"))
    assert dict(compose.attrib) == {
        "circleType": "SHAPE_RECTANGLE",
        "charSz": "-3",
        "composeType": "OVERLAP",
        "charPrCnt": "10",
        "composeText": "가나",
    }
    assert [c.get("prIDRef") for c in compose.findall(f"{HP}charPr")] == ["1", "0"] + ["4294967295"] * 8
    run = compose.getparent()
    assert [(etree.QName(c).localname, c.text) for c in run] == [("t", "앞"), ("compose", None), ("t", "뒤")]


@pytest.mark.parametrize("keep", ["line", "fill"])
def test_an_older_drawing_style_that_stops_early_still_opens(keep: str) -> None:
    fill = di.Fill(di.FILL_SOLID, 0x00FFE5CC, 0x00FFFFFF, -1, additional=b"", alphas=b"")
    full = sh.DrawingStyle(0x00112233, 283, 0x1, 0, fill, 1, 0xB2B2B2, 283, 283, 185).encode()
    short = full[:13] if keep == "line" else full[: 13 + 16]
    style = sh.DrawingStyle.decode(short)
    assert style.encode() == short
    assert (style.line_color, style.line_width, style.shadow_type) == (0x00112233, 283, 0)
    assert (style.fill.kind == di.FILL_SOLID) == (keep == "fill")
    section = _section()
    records = _text_box()
    component = next(i for i, r in enumerate(records) if r.tag == rec.SHAPE_COMPONENT)
    shape = sh.ShapeComponent.decode(records[component].payload, top=True)
    shape.rest = short
    records[component] = rec.Record(rec.SHAPE_COMPONENT, 2, shape.encode())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(_compound(section + records))
    [rect] = list(document.sections[0].element.iter(f"{HP}rect"))
    assert rect.find(f"{HP}lineShape").get("color") == "#332211"
    assert rect.find(f"{HP}shadow").get("type") == "NONE"


def test_picture_effects_open_with_their_values() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(picture_effects=True))
    [pic] = list(document.sections[0].element.iter(f"{HP}pic"))
    effects = pic.find(f"{HP}effects")
    assert [etree.QName(c).localname for c in effects] == ["shadow", "glow", "softEdge", "reflection"]
    shadow = effects.find(f"{HP}shadow")
    assert [shadow.get(n) for n in ("style", "alpha", "radius", "alignStyle")] == ["OUTSIDE", "0.5", "600", "CENTER"]
    color = effects.find(f"{HP}glow/{HP}effectsColor")
    assert dict(color.find(f"{HP}rgb").attrib) == {"r": "233", "g": "174", "b": "43"}
    assert dict(color.find(f"{HP}effect").attrib) == {"type": "SAT_MOD", "value": "1.75"}
    reflection = effects.find(f"{HP}reflection")
    assert (reflection.get("alignStyle"), reflection.find(f"{HP}alpha").get("end")) == ("BOTTOM_LEFT", "0.997")


def test_a_hidden_comment_opens_with_its_paragraphs() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(hidden_comment=True))
    [comment] = list(document.sections[0].element.iter(f"{HP}hiddenComment"))
    assert etree.QName(comment.getparent()).localname == "ctrl"
    assert "".join(comment.itertext()) == "숨은 설명"
    assert comment.find(f"{HP}subList").get("textWidth") == "0"


def test_form_objects_open_with_their_properties() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(forms=True))
    section = document.sections[0].element
    [check] = list(section.iter(f"{HP}checkBtn"))
    assert list(check.attrib.items())[:6] == [
        ("caption", "동의함"),
        ("value", "CHECKED"),
        ("radioGroupName", ""),
        ("triState", "0"),
        ("backStyle", "OPAQUE"),
        ("name", "chk"),
    ]
    assert (check.get("backColor"), check.get("tabStop"), check.get("command")) == ("#FFFFFF", "1", "")
    [edit] = list(section.iter(f"{HP}edit"))
    assert [edit.get(n) for n in ("passwordChar", "numOnly", "alignText", "foreColor", "name")] == ["X", "1", "RIGHT", "#F3EFE4", "num"]
    assert [etree.QName(c).localname for c in edit] == ["formCharPr", "text", "sz", "pos", "outMargin"]
    assert edit.find(f"{HP}text").text == "1234"
    [combo] = list(section.iter(f"{HP}comboBox"))
    assert [combo.get(n) for n in ("listBoxRows", "editEnable", "selectedValue", "name")] == ["10", "1", "", "pick"]
    assert [dict(item.attrib) for item in combo.findall(f"{HP}listItem")] == [{"displayText": "", "value": "가"}]


def test_curves_and_connectors_open_with_their_segments_and_ends() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(drawings=True))
    section = document.sections[0].element
    [curve] = list(section.iter(f"{HP}curve"))
    segments = [(s.get("type"), s.get("x1"), s.get("y1"), s.get("x2"), s.get("y2")) for s in curve.findall(f"{HP}seg")]
    assert segments == [
        ("LINE", "0", "0", "8000", "0"),
        ("CURVE", "8000", "0", "8000", "6000"),
        ("CURVE", "8000", "6000", "0", "0"),
    ]
    [connector] = list(section.iter(f"{HP}connectLine"))
    assert connector.get("type") == "STRAIGHT_ONEWAY"
    ends = [dict(connector.find(f"{HP}{name}").attrib) for name in ("startPt", "endPt")]
    assert ends == [
        {"x": "0", "y": "0", "subjectIDRef": "185", "subjectIdx": "1"},
        {"x": "8000", "y": "6000", "subjectIDRef": "186", "subjectIdx": "2"},
    ]
    points = [dict(p.attrib) for p in connector.find(f"{HP}controlPoints")]
    assert points == [{"x": "0", "y": "0", "type": "3"}, {"x": "0", "y": "6000", "type": "26"}]
    assert connector.find("{http://www.hancom.co.kr/hwpml/2011/core}fillBrush") is None


@pytest.mark.parametrize(
    ("text", "circle", "expected"),
    [
        ("\u25a1가", 3, "가"),  # the rectangle's own glyph leads the text
        ("\u3000나", 0, "나"),
        ("\u2461", 1, "2"),  # a circled digit in a circle
        ("\U000f0289\U000f0294", 1, "12"),
        ("\u25a1가", 1, "\u25a1가"),  # not this frame's glyph
    ],
)
def test_the_text_of_overlapped_characters_leaves_out_their_frame(text: str, circle: int, expected: str) -> None:
    section = _section()
    code = _extended(23, "tcps") + _u16(13)
    compose = ct.Compose(text, circle, 0, 0)
    section += _paragraph(0, code, [(0, 0)], [rec.Record(rec.CTRL_HEADER, 1, compose.encode())])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(_compound(section))
    [element] = list(document.sections[0].element.iter(f"{HP}compose"))
    assert element.get("composeText") == expected


def test_a_table_name_is_counted_and_presentation_settings_are_reported() -> None:
    section = _section()
    table = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "tbl ")
    section.insert(table + 1, rec.Record(rec.CTRL_DATA, 2, ct.name_parameter_set("표 이름")))
    secd = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    # A presentation parameter set: set 0x021B holding the set 0x0219.
    section.insert(secd + 1, rec.Record(rec.CTRL_DATA, 2, bytes.fromhex("1b020100000019020080190200000000")))
    with pytest.warns(Hwp5ConversionWarning, match="presentation x1"):
        document = HwpxDocument.open(_compound(section))
    # The table name has no OWPML form: counted, not warned about.
    assert document._hwp5_report.dropped == {"table-name": 1}
    assert document._hwp5_report.unconverted == {"presentation": 1}


def test_a_text_box_opens_as_a_rectangle_with_its_paragraphs() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(text_box=True))
    [rect] = list(document.sections[0].element.iter(f"{HP}rect"))
    assert (rect.get("instid"), rect.get("ratio")) == ("185", "0")
    assert rect.find(f"{HP}rotationInfo").get("rotateimage") == "1"
    assert rect.find(f"{HP}lineShape").get("width") == "283"
    face = rect.find("{http://www.hancom.co.kr/hwpml/2011/core}fillBrush/{http://www.hancom.co.kr/hwpml/2011/core}winBrush")
    assert face is not None and face.get("faceColor") == "#CCE5FF"
    draw_text = rect.find(f"{HP}drawText")
    assert draw_text.get("name") == "상자"
    assert "".join(draw_text.find(f"{HP}subList").itertext()) == "글상자 안"
    corners = [(p.get("x"), p.get("y")) for p in rect if etree.QName(p).localname.startswith("pt")]
    assert corners == [("0", "0"), ("20000", "0"), ("20000", "10000"), ("0", "10000")]
    assert rect.find(f"{HP}sz").get("width") == "20000"


def test_a_picture_opens_with_its_caption_comment_and_parameter_set() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(picture=True))
    [pic] = list(document.sections[0].element.iter(f"{HP}pic"))
    assert (pic.get("instid"), pic.get("dropcapstyle")) == ("297", "TripleLine")
    order = [etree.QName(child).localname for child in pic]
    assert order[6:12] == ["img", "imgRect", "imgClip", "inMargin", "imgDim", "effects"]
    assert order[-4:] == ["outMargin", "shapeComment", "caption", "parameterset"]
    clip = pic.find(f"{HP}imgClip")
    assert [clip.get(side) for side in ("left", "right", "top", "bottom")] == ["0", "10000", "0", "8000"]
    assert pic.find(f"{HP}imgDim").get("dimwidth") == "10000"
    assert pic.find(f"{HP}shapeComment").text == "그림입니다."
    assert "".join(pic.find(f"{HP}caption").itertext()) == "그림 1"
    value = pic.find(f"{HP}parameterset/{HP}listParam/{HP}unsignedintegerParam")
    assert value is not None and (value.get("name"), value.text) == ("28673", "2")


def test_a_memo_opens_with_its_body_beside_a_master_page() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(memo=True, master_page=True))
    [memo] = [b for b in document.sections[0].element.iter(f"{HP}fieldBegin") if b.get("type") == "MEMO"]
    params = {p.get("name"): p.text or "" for p in memo.find(f"{HP}parameters")}
    assert (params["ID"], params["Number"], params["MemoShapeIDRef"]) == ("memo1", "1", "65535")
    assert "".join(memo.find(f"{HP}subList").itertext()) == "메모 내용"
    assert [page.to_model().paragraph_texts for page in document.oxml.master_pages][-1] == ("둘째 쪽",)


def test_master_pages_open_as_parts_the_section_refers_to() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        document = HwpxDocument.open(make_hwp(master_page=True))
    [sec_pr] = list(document.sections[0].element.iter(f"{HP}secPr"))
    assert sec_pr.get("masterPageCnt") == "3"
    assert [ref.get("idRef") for ref in sec_pr.findall(f"{HP}masterPage")] == ["masterpage0", "masterpage1", "masterpage2"]
    pages = [page.to_model() for page in document.oxml.master_pages]
    assert [(p.id, p.type, p.page_number, p.page_duplicate, p.page_front) for p in pages] == [
        ("masterpage0", "EVEN", 0, False, False),
        ("masterpage1", "ODD", 0, False, True),
        ("masterpage2", "OPTIONAL_PAGE", 2, True, False),
    ]
    assert [p.paragraph_texts for p in pages] == [("짝수 쪽",), ("홀수 쪽",), ("둘째 쪽",)]
    sub_list = document.oxml.master_pages[0].element.find(f"{HP}subList")
    assert (sub_list.get("textWidth"), sub_list.get("textHeight")) == ("42520", "65762")


def test_master_pages_that_do_not_match_the_section_definition_are_reported() -> None:
    section = _with_master_pages(_section())
    # Only the odd-page bit set for the two lists under the definition, and a
    # list on the last paragraph whose kind names no page.
    index = next(i for i, r in enumerate(section) if r.tag == rec.CTRL_HEADER and bt.record_ctrl_id(r) == "secd")
    secd = bytearray(section[index].payload)
    struct.pack_into("<I", secd, 4, 1 << 31)
    section[index] = rec.Record(rec.CTRL_HEADER, 1, bytes(secd))
    section += _master_list(1, "알 수 없음", kind=1)
    with pytest.warns(Hwp5ConversionWarning, match="master-page x3"):
        document = HwpxDocument.open(_compound(section))
    assert [page.to_model().type for page in document.oxml.master_pages] == ["OPTIONAL_PAGE"]


def test_password_protected_hwp_is_refused_with_its_code() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(Hwp5Error) as info:
            HwpxDocument.open(make_hwp(flags=1 | 2))
    assert info.value.code == "hwp5-password"


def test_the_converted_package_saves_as_hwpx(tmp_path: Path) -> None:
    document = HwpxDocument.open(make_hwp())
    target = tmp_path / "out.hwpx"
    document.save_to_path(target)
    reopened = HwpxDocument.open(target)
    assert [p.text for p in reopened.paragraphs] == [p.text for p in document.paragraphs]
