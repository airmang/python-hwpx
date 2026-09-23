# SPDX-License-Identifier: Apache-2.0
"""BodyText section records of an HWP 5.0 document -> ``Contents/section<N>.xml``.

A paragraph becomes ``hp:p``; each ``PARA_CHAR_SHAPE`` entry opens a
``hp:run``; text goes into ``hp:t`` with line breaks, tabs and fixed-width
or non-breaking spaces as child elements; and each extended control becomes
the element OWPML uses for it. Controls this module does not convert are
counted in the :class:`ConversionReport` instead of disappearing silently.
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import records as rec
from .binary import Cursor
from .owpml import (
    BORDER_LINE,
    BORDER_WIDTH,
    NUMBER_FORMAT,
    color,
    flag,
    root,
    serialize,
    sub,
    token,
    xml_text,
)


@dataclass
class ConversionReport:
    """What a conversion could not express, by kind and count."""

    unconverted: Counter[str] = field(default_factory=Counter)

    def skip(self, kind: str) -> None:
        self.unconverted[kind] += 1


def _bits(value: int, lo: int, width: int) -> int:
    return (value >> lo) & ((1 << width) - 1)


def _unit(raw: int) -> tuple[int, str]:
    return raw >> 1, "CHAR" if raw & 1 else "HWPUNIT"


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
    description: str = ""
    extra: bytes = b""

    @classmethod
    def decode(cls, payload: bytes) -> "ObjectCommon":
        c = Cursor(payload, "CTRL_HEADER")
        ctrl = bt.ctrl_id(c.u32())
        obj = cls(ctrl)
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
        if c.left >= 2:
            obj.description = c.wstr()
        obj.extra = c.rest()
        return obj

    def write(self, element: etree._Element, *, size_protect: bool = True) -> None:
        p = self.props
        sub(
            element,
            "hp:sz",
            (
                ("width", self.width),
                ("widthRelTo", token(WIDTH_REL, _bits(p, 15, 3))),
                ("height", self.height),
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
                ("holdAnchorAndSO", flag(p & (1 << 29))),
                ("vertRelTo", token(VERT_REL, _bits(p, 3, 2))),
                ("horzRelTo", token(HORZ_REL, _bits(p, 8, 2))),
                ("vertAlign", token(VERT_ALIGN, _bits(p, 5, 3))),
                ("horzAlign", token(HORZ_ALIGN, _bits(p, 10, 3))),
                ("vertOffset", self.vert_offset),
                ("horzOffset", self.horz_offset),
            ),
        )
        left, right, top, bottom = self.margins
        sub(element, "hp:outMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))

    def attrs(self) -> list[tuple[str, object]]:
        p = self.props
        return [
            ("id", self.instance_id),
            ("zOrder", self.z_order),
            ("numberingType", token(NUMBERING_TYPE, _bits(p, 26, 3))),
            ("textWrap", token(TEXT_WRAP, _bits(p, 21, 3))),
            ("textFlow", token(TEXT_FLOW, _bits(p, 24, 2))),
            ("lock", flag(p & (1 << 30))),
            ("dropcapstyle", "None"),
        ]


# -- sections and columns -------------------------------------------------------------

PAGE_STARTS_ON = ("BOTH", "EVEN", "ODD")
GUTTER = ("LEFT_ONLY", "LEFT_RIGHT", "TOP_BOTTOM")
NOTE_NUMBERING = ("CONTINUOUS", "ON_SECTION", "ON_PAGE")
FOOTNOTE_PLACE = ("EACH_COLUMN", "MERGED_COLUMN", "RIGHT_MOST_COLUMN")
ENDNOTE_PLACE = ("END_OF_DOCUMENT", "END_OF_SECTION")
PAGE_BORDER_TYPES = ("BOTH", "EVEN", "ODD")
FILL_AREA = ("PAPER", "PAGE", "BORDER")
COL_TYPE = ("NEWSPAPER", "BALANCED_NEWSPAPER", "PARALLEL")
COL_LAYOUT = ("LEFT", "RIGHT", "MIRROR")


def _note_pr(parent: etree._Element, name: str, record: rec.Record | None, *, endnote: bool) -> None:
    element = sub(parent, name)
    payload = record.payload if record is not None else b""
    c = Cursor(payload.ljust(28, b"\0"), "FOOTNOTE_SHAPE")
    props = c.u32()
    user, prefix, suffix = c.u16(), c.u16(), c.u16()
    start = c.u16()
    length = c.i32()
    above, below, between = c.u16(), c.u16(), c.u16()
    line_type, line_width = c.u8(), c.u8()
    line_color = c.u32()
    sub(
        element,
        "hp:autoNumFormat",
        (
            ("type", token(NUMBER_FORMAT, _bits(props, 0, 8), "DIGIT")),
            ("userChar", chr(user) if user else ""),
            ("prefixChar", chr(prefix) if prefix else ""),
            ("suffixChar", chr(suffix) if suffix else ""),
            ("supscript", flag(props & (1 << 12))),
        ),
    )
    sub(
        element,
        "hp:noteLine",
        (
            ("length", length),
            ("type", token(BORDER_LINE, line_type)),
            ("width", token(BORDER_WIDTH, line_width)),
            ("color", color(line_color)),
        ),
    )
    sub(element, "hp:noteSpacing", (("betweenNotes", between), ("belowLine", below), ("aboveLine", above)))
    sub(element, "hp:numbering", (("type", token(NOTE_NUMBERING, _bits(props, 10, 2))), ("newNum", start)))
    places = ENDNOTE_PLACE if endnote else FOOTNOTE_PLACE
    sub(element, "hp:placement", (("place", token(places, _bits(props, 8, 2))), ("beneathText", flag(props & (1 << 13)))))


def section_properties(parent: etree._Element, ctrl: rec.Record) -> etree._Element:
    """``hp:secPr`` from a ``secd`` control and its child records."""

    c = Cursor(ctrl.payload.ljust(28, b"\0"), "secd")
    c.u32()
    props = c.u32()
    space_columns = c.u16()
    line_grid = c.u16()
    char_grid = c.u16()
    tab_stop = c.u32()
    outline = c.u16()
    page_start, pic_start, tbl_start, eq_start = c.u16(), c.u16(), c.u16(), c.u16()
    tab_value, tab_unit = _unit(tab_stop)
    element = sub(
        parent,
        "hp:secPr",
        (
            ("id", ""),
            ("textDirection", "VERTICAL" if props & (1 << 16) else "HORIZONTAL"),
            ("spaceColumns", space_columns),
            ("tabStop", tab_stop),
            ("tabStopVal", tab_value),
            ("tabStopUnit", tab_unit),
            ("outlineShapeIDRef", outline),
            ("memoShapeIDRef", 0),
            ("textVerticalWidthHead", 0),
            ("masterPageCnt", 0),
        ),
    )
    sub(element, "hp:grid", (("lineGrid", line_grid), ("charGrid", char_grid), ("wonggojiFormat", flag(props & (1 << 22)))))
    sub(
        element,
        "hp:startNum",
        (
            ("pageStartsOn", token(PAGE_STARTS_ON, _bits(props, 20, 2))),
            ("page", page_start),
            ("pic", pic_start),
            ("tbl", tbl_start),
            ("equation", eq_start),
        ),
    )
    sub(
        element,
        "hp:visibility",
        (
            ("hideFirstHeader", flag(props & 0x1)),
            ("hideFirstFooter", flag(props & 0x2)),
            ("hideFirstMasterPage", flag(props & 0x4)),
            ("border", "SHOW_FIRST" if props & (1 << 8) else ("HIDE_FIRST" if props & 0x8 else "SHOW_ALL")),
            ("fill", "SHOW_FIRST" if props & (1 << 9) else ("HIDE_FIRST" if props & 0x10 else "SHOW_ALL")),
            ("hideFirstPageNum", flag(props & 0x20)),
            ("hideFirstEmptyLine", flag(props & (1 << 19))),
            ("showLineNumber", 0),
        ),
    )
    sub(element, "hp:lineNumberShape", (("restartType", 0), ("countBy", 0), ("distance", 0), ("startNumber", 0)))
    page = next((r for r in ctrl.children if r.tag == rec.PAGE_DEF), None)
    pc = Cursor((page.payload if page is not None else b"").ljust(40, b"\0"), "PAGE_DEF")
    width, height = pc.u32(), pc.u32()
    left, right, top, bottom, header, footer, gutter = (pc.u32() for _ in range(7))
    page_props = pc.u32()
    page_pr = sub(
        element,
        "hp:pagePr",
        (
            ("landscape", "NARROWLY" if page_props & 0x1 else "WIDELY"),
            ("width", width),
            ("height", height),
            ("gutterType", token(GUTTER, _bits(page_props, 1, 2))),
        ),
    )
    sub(
        page_pr,
        "hp:margin",
        (
            ("header", header),
            ("footer", footer),
            ("gutter", gutter),
            ("left", left),
            ("right", right),
            ("top", top),
            ("bottom", bottom),
        ),
    )
    notes = [r for r in ctrl.children if r.tag == rec.FOOTNOTE_SHAPE]
    _note_pr(element, "hp:footNotePr", notes[0] if notes else None, endnote=False)
    _note_pr(element, "hp:endNotePr", notes[1] if len(notes) > 1 else None, endnote=True)
    borders: list[rec.Record | None] = [r for r in ctrl.children if r.tag == rec.PAGE_BORDER_FILL]
    for kind, record in zip(PAGE_BORDER_TYPES, borders or [None, None, None]):
        bc = Cursor((record.payload if record is not None else b"").ljust(14, b"\0"), "PAGE_BORDER_FILL")
        border_props = bc.u32()
        offsets = (bc.u16(), bc.u16(), bc.u16(), bc.u16())
        fill_id = bc.u16()
        fill_element = sub(
            element,
            "hp:pageBorderFill",
            (
                ("type", kind),
                ("borderFillIDRef", fill_id),
                ("textBorder", "PAPER" if border_props & 0x1 else "CONTENT"),
                ("headerInside", flag(border_props & 0x2)),
                ("footerInside", flag(border_props & 0x4)),
                ("fillArea", token(FILL_AREA, _bits(border_props, 3, 2))),
            ),
        )
        sub(
            fill_element,
            "hp:offset",
            (("left", offsets[0]), ("right", offsets[1]), ("top", offsets[2]), ("bottom", offsets[3])),
        )
    return element


def column_properties(parent: etree._Element, ctrl: rec.Record) -> None:
    """``hp:ctrl/hp:colPr`` from a ``cold`` control."""

    c = Cursor(ctrl.payload, "cold")
    c.u32()
    props = c.u16() if c.left >= 2 else 0
    count = _bits(props, 2, 8) or 1
    same = bool(props & (1 << 12))
    gap = c.u16() if c.left >= 2 else 0
    widths: list[int] = []
    if not same and count > 1:
        widths = [c.u16() for _ in range(min(count * 2, c.left // 2))]
    wrapper = sub(parent, "hp:ctrl")
    col = sub(
        wrapper,
        "hp:colPr",
        (
            ("id", ""),
            ("type", token(COL_TYPE, _bits(props, 0, 2))),
            ("layout", token(COL_LAYOUT, _bits(props, 10, 2))),
            ("colCount", count),
            ("sameSz", flag(same)),
            ("sameGap", gap if same else 0),
        ),
    )
    if widths:
        for index in range(0, len(widths) - 1, 2):
            sub(col, "hp:colSz", (("width", widths[index]), ("gap", widths[index + 1])))
    if c.left >= 8:
        c.u16()
        line_type, line_width = c.u8(), c.u8()
        line_color = c.u32()
        if line_type:
            sub(
                col,
                "hp:colLine",
                (
                    ("type", token(BORDER_LINE, line_type)),
                    ("width", token(BORDER_WIDTH, line_width)),
                    ("color", color(line_color)),
                ),
            )


# -- the section writer -------------------------------------------------------------------

TEXT_DIRECTION = ("HORIZONTAL", "VERTICAL", "VERTICALALL")
LINE_WRAP = ("BREAK", "SQUEEZE", "KEEP")
LIST_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM")
TABLE_PAGE_BREAK = ("NONE", "TABLE", "CELL")


class SectionWriter:
    """Writes the paragraphs of one BodyText section as OWPML."""

    def __init__(self, report: ConversionReport) -> None:
        self.report = report

    # paragraphs ----------------------------------------------------------------------

    def paragraphs(self, parent: etree._Element, records: list[rec.Record]) -> None:
        for record in records:
            if record.tag == rec.PARA_HEADER:
                self.paragraph(parent, record)

    def paragraph(self, parent: etree._Element, record: rec.Record) -> None:
        para = bt.parse_paragraph(record)
        element = sub(
            parent,
            "hp:p",
            (
                ("id", para.instance_id),
                ("paraPrIDRef", para.para_shape_id),
                ("styleIDRef", para.style_id),
                ("pageBreak", flag(para.break_type & 0x4)),
                ("columnBreak", flag(para.break_type & 0x8)),
                ("merged", flag(para.merge_flag)),
            ),
        )
        self.runs(element, para)
        segs = next((r for r in record.children if r.tag == rec.PARA_LINE_SEG), None)
        if segs is not None and len(segs.payload) >= 36:
            array = sub(element, "hp:linesegarray")
            for offset in range(0, len(segs.payload) - 35, 36):
                values = struct.unpack_from("<IiiiiiiiI", segs.payload, offset)
                sub(
                    array,
                    "hp:lineseg",
                    (
                        ("textpos", values[0]),
                        ("vertpos", values[1]),
                        ("vertsize", values[2]),
                        ("textheight", values[3]),
                        ("baseline", values[4]),
                        ("spacing", values[5]),
                        ("horzpos", values[6]),
                        ("horzsize", values[7]),
                        ("flags", values[8]),
                    ),
                )

    def runs(self, element: etree._Element, para: bt.Paragraph) -> None:
        shapes = para.char_shapes or [(0, 0)]
        bounds = [start for start, _ in shapes[1:]] + [1 << 31]
        controls = iter(para.controls)
        chunks = list(para.chunks)
        index = 0
        last: etree._Element | None = None
        for (start, shape_id), end in zip(shapes, bounds):
            run = sub(element, "hp:run", (("charPrIDRef", shape_id),))
            text: etree._Element | None = None
            last = None
            while index < len(chunks) and chunks[index].position < end:
                chunk = chunks[index]
                if chunk.kind == "text":
                    split = end - chunk.position
                    if chunk.width > split:
                        head, tail = _split_text(chunk, split)
                        chunks[index] = tail
                        chunk = head
                    else:
                        index += 1
                    text = self._text(run, text, chunk.text)
                    last = text
                    continue
                index += 1
                if chunk.kind == "char":
                    if chunk.code == bt.PARA_BREAK:
                        continue
                    name = {10: "hp:lineBreak", 24: "hp:hyphen", 30: "hp:nbSpace", 31: "hp:fwSpace"}.get(chunk.code)
                    if name is None:
                        continue
                    text = self._text(run, text, "")
                    sub(text, name)
                    last = text
                elif chunk.kind == "inline":
                    if chunk.code == bt.TAB:
                        text = self._text(run, text, "")
                        width, leader, kind = struct.unpack_from("<IBB", chunk.params.ljust(6, b"\0"), 0)
                        sub(text, "hp:tab", (("width", width), ("leader", leader), ("type", kind)))
                        last = text
                    elif chunk.code == 4:
                        self.report.skip("field-end")
                    else:
                        self.report.skip(f"inline-{chunk.code}")
                else:
                    ctrl = next(controls, None)
                    text = None
                    if ctrl is None:
                        self.report.skip("control-without-record")
                        continue
                    last = self.control(run, ctrl, chunk)
                    # Section and column definitions keep a run of their own.
                    if chunk.control_id in ("secd", "cold"):
                        following = chunks[index] if index < len(chunks) else None
                        if (
                            following is not None
                            and following.position < end
                            and following.control_id not in ("secd", "cold")
                        ):
                            run = sub(element, "hp:run", (("charPrIDRef", shape_id),))
                            last = run
        # Hancom closes a paragraph that ends on a control with an empty text node.
        if last is not None and etree.QName(last).localname == "run":
            sub(last, "hp:t")
        elif last is not None and etree.QName(last).localname != "t":
            sub(last.getparent(), "hp:t")

    @staticmethod
    def _text(run: etree._Element, text: etree._Element | None, value: str) -> etree._Element:
        target = text
        if target is None or target.getparent() is not run or run[-1] is not target:
            target = sub(run, "hp:t")
        value = xml_text(value)
        if not value:
            return target
        if len(target):
            tail = target[-1]
            tail.tail = (tail.tail or "") + value
        else:
            target.text = (target.text or "") + value
        return target

    # controls ------------------------------------------------------------------------

    def control(self, run: etree._Element, ctrl: rec.Record, chunk: bt.Chunk) -> etree._Element | None:
        kind = bt.record_ctrl_id(ctrl) or "?"
        if kind == "secd":
            return section_properties(run, ctrl)
        if kind == "cold":
            column_properties(run, ctrl)
            return run[-1]
        if kind == "tbl ":
            return self.table(run, ctrl)
        if kind in ("head", "foot"):
            return self.header_footer(run, ctrl, kind)
        if kind in ("fn  ", "en  "):
            return self.note(run, ctrl, kind)
        self.report.skip(f"control-{kind.strip() or kind}")
        return None

    def sub_list(self, parent: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        props = struct.unpack_from("<I", header.payload.ljust(8, b"\0"), 4)[0] if len(header.payload) >= 8 else 0
        attrs: list[tuple[str, object]] = [
            ("id", ""),
            ("textDirection", token(TEXT_DIRECTION, _bits(props, 0, 3))),
            ("lineWrap", token(LINE_WRAP, _bits(props, 3, 2))),
            ("vertAlign", token(LIST_VERT_ALIGN, _bits(props, 5, 2))),
            ("linkListIDRef", 0),
            ("linkListNextIDRef", 0),
            ("textWidth", 0),
            ("textHeight", 0),
            ("hasTextRef", 0),
            ("hasNumRef", 0),
        ]
        element = sub(parent, "hp:subList", attrs)
        self.paragraphs(element, paragraphs)

    def header_footer(self, run: etree._Element, ctrl: rec.Record, kind: str) -> etree._Element:
        c = Cursor(ctrl.payload.ljust(8, b"\0"), kind)
        c.u32()
        props = c.u32()
        wrapper = sub(run, "hp:ctrl")
        element = sub(
            wrapper,
            "hp:header" if kind == "head" else "hp:footer",
            (("id", 0), ("applyPageType", token(PAGE_BORDER_TYPES, _bits(props, 0, 2)))),
        )
        for header, paragraphs in lists(ctrl)[:1]:
            self.sub_list(element, header, paragraphs)
        return wrapper

    def note(self, run: etree._Element, ctrl: rec.Record, kind: str) -> etree._Element:
        c = Cursor(ctrl.payload.ljust(12, b"\0"), kind)
        c.u32()
        number = c.u32()
        wrapper = sub(run, "hp:ctrl")
        element = sub(
            wrapper,
            "hp:footNote" if kind == "fn  " else "hp:endNote",
            (("number", number), ("suffixChar", ")"), ("instId", 0)),
        )
        for header, paragraphs in lists(ctrl)[:1]:
            self.sub_list(element, header, paragraphs)
        return wrapper

    # tables --------------------------------------------------------------------------

    def table(self, run: etree._Element, ctrl: rec.Record) -> etree._Element:
        common = ObjectCommon.decode(ctrl.payload)
        table_record = next((r for r in ctrl.children if r.tag == rec.TABLE), None)
        tc = Cursor((table_record.payload if table_record is not None else b"").ljust(22, b"\0"), "TABLE")
        props = tc.u32()
        rows, cols = tc.u16(), tc.u16()
        spacing = tc.u16()
        inner = (tc.u16(), tc.u16(), tc.u16(), tc.u16())
        row_sizes = [tc.u16() for _ in range(min(rows, tc.left // 2))]
        border_fill = tc.u16() if tc.left >= 2 else 0
        zones: list[tuple[int, int, int, int, int]] = []
        if tc.left >= 2:
            count = tc.u16()
            for _ in range(min(count, tc.left // 10)):
                zones.append((tc.u16(), tc.u16(), tc.u16(), tc.u16(), tc.u16()))
        attrs = common.attrs() + [
            ("pageBreak", token(TABLE_PAGE_BREAK, _bits(props, 0, 2))),
            ("repeatHeader", flag(props & 0x4)),
            ("rowCnt", rows),
            ("colCnt", cols),
            ("cellSpacing", spacing),
            ("borderFillIDRef", border_fill),
            ("noAdjust", flag(props & 0x8)),
        ]
        table = sub(run, "hp:tbl", attrs)
        common.write(table)
        sub(table, "hp:inMargin", (("left", inner[0]), ("right", inner[1]), ("top", inner[2]), ("bottom", inner[3])))
        if zones:
            zone_list = sub(table, "hp:cellzoneList")
            for start_col, start_row, end_col, end_row, fill in zones:
                sub(
                    zone_list,
                    "hp:cellzone",
                    (
                        ("startRowAddr", start_row),
                        ("startColAddr", start_col),
                        ("endRowAddr", end_row),
                        ("endColAddr", end_col),
                        ("borderFillIDRef", fill),
                    ),
                )
        cells = lists(ctrl)
        position = 0
        for row_size in row_sizes or [len(cells)]:
            tr = sub(table, "hp:tr")
            for header, paragraphs in cells[position : position + row_size]:
                self.cell(tr, header, paragraphs)
            position += row_size
        return table

    def cell(self, tr: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        c = Cursor(header.payload.ljust(34, b"\0"), "cell")
        c.u32()
        props = c.u32()
        col, row, col_span, row_span = c.u16(), c.u16(), c.u16(), c.u16()
        width, height = c.u32(), c.u32()
        # An unset margin is -1; Hancom writes it as the unsigned 32-bit value.
        margins = tuple(value & 0xFFFFFFFF for value in (c.i16(), c.i16(), c.i16(), c.i16()))
        fill = c.u16()
        tc = sub(
            tr,
            "hp:tc",
            (
                ("name", ""),
                ("header", flag(props & (1 << 18))),
                ("hasMargin", flag(props & (1 << 16))),
                ("protect", flag(props & (1 << 17))),
                ("editable", flag(props & (1 << 19))),
                ("dirty", flag(props & (1 << 20))),
                ("borderFillIDRef", fill),
            ),
        )
        self.sub_list(tc, header, paragraphs)
        sub(tc, "hp:cellAddr", (("colAddr", col), ("rowAddr", row)))
        sub(tc, "hp:cellSpan", (("colSpan", col_span), ("rowSpan", row_span)))
        sub(tc, "hp:cellSz", (("width", width), ("height", height)))
        sub(tc, "hp:cellMargin", (("left", margins[0]), ("right", margins[1]), ("top", margins[2]), ("bottom", margins[3])))


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


def _split_text(chunk: bt.Chunk, units: int) -> tuple[bt.Chunk, bt.Chunk]:
    raw = chunk.text.encode("utf-16-le", errors="surrogatepass")
    head = raw[: units * 2].decode("utf-16-le", errors="surrogatepass")
    tail = raw[units * 2 :].decode("utf-16-le", errors="surrogatepass")
    return bt.Chunk("text", chunk.position, head), bt.Chunk("text", chunk.position + units, tail)


def build_section(stream: rec.RecordStream, report: ConversionReport) -> bytes:
    """``Contents/section<N>.xml`` for one BodyText section."""

    section = root("hs:sec")
    SectionWriter(report).paragraphs(section, stream.roots)
    return serialize(section)
