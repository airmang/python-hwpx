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
from . import controls as ct
from . import records as rec
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
        ("numberingType", token(NUMBERING_TYPE, _bits(p, 26, 3))),
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
            ("holdAnchorAndSO", flag(p & (1 << 29))),
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
#: Low nibble of the section direction word; bit 4 is textVerticalWidthHead.
SECTION_TEXT_DIRECTION = {0: "HORIZONTAL", 2: "VERTICAL", 4: "VERTICALALL"}


def _note_pr(parent: etree._Element, name: str, record: rec.Record | None, *, endnote: bool) -> None:
    element = sub(parent, name)
    note = ct.NoteShape.decode(record.payload if record is not None else b"")
    props = note.props
    sub(
        element,
        "hp:autoNumFormat",
        (
            ("type", token(NUMBER_FORMAT, _bits(props, 0, 8), "DIGIT")),
            ("userChar", chr(note.user_char) if note.user_char else ""),
            ("prefixChar", chr(note.prefix_char) if note.prefix_char else ""),
            ("suffixChar", chr(note.suffix_char) if note.suffix_char else ""),
            ("supscript", flag(props & (1 << 12))),
        ),
    )
    sub(
        element,
        "hp:noteLine",
        (
            ("length", note.line_length),
            ("type", token(BORDER_LINE, note.line_type)),
            ("width", token(BORDER_WIDTH, note.line_width)),
            ("color", color(note.line_color)),
        ),
    )
    sub(element, "hp:noteSpacing", (("betweenNotes", note.between), ("belowLine", note.below), ("aboveLine", note.above)))
    sub(element, "hp:numbering", (("type", token(NOTE_NUMBERING, _bits(props, 10, 2))), ("newNum", note.start)))
    places = ENDNOTE_PLACE if endnote else FOOTNOTE_PLACE
    sub(element, "hp:placement", (("place", token(places, _bits(props, 8, 2))), ("beneathText", flag(props & (1 << 13)))))


def section_properties(parent: etree._Element, ctrl: rec.Record) -> etree._Element:
    """``hp:secPr`` from a ``secd`` control and its child records."""

    sd = ct.SectionDef.decode(ctrl.payload)
    props = sd.props
    tab_value, tab_unit = _unit(sd.tab_stop)
    direction = SECTION_TEXT_DIRECTION.get(sd.text_direction & 0xF, "HORIZONTAL")
    element = sub(
        parent,
        "hp:secPr",
        (
            ("id", ""),
            ("textDirection", direction),
            ("spaceColumns", sd.space_columns),
            ("tabStop", sd.tab_stop),
            ("tabStopVal", tab_value),
            ("tabStopUnit", tab_unit),
            ("outlineShapeIDRef", sd.outline_numbering),
            ("memoShapeIDRef", sd.memo_shape),
            ("textVerticalWidthHead", flag(sd.text_direction & 0x10)),
            ("masterPageCnt", sd.master_pages),
        ),
    )
    sub(element, "hp:grid", (("lineGrid", sd.line_grid), ("charGrid", sd.char_grid), ("wonggojiFormat", flag(props & (1 << 22)))))
    sub(
        element,
        "hp:startNum",
        (
            ("pageStartsOn", token(PAGE_STARTS_ON, _bits(props, 20, 2))),
            ("page", sd.page_start),
            ("pic", sd.picture_start),
            ("tbl", sd.table_start),
            ("equation", sd.equation_start),
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
    sub(
        element,
        "hp:lineNumberShape",
        (
            ("restartType", sd.line_number_restart),
            ("countBy", sd.line_number_count_by),
            ("distance", sd.line_number_distance),
            ("startNumber", sd.line_number_start),
        ),
    )
    page_record = next((r for r in ctrl.children if r.tag == rec.PAGE_DEF), None)
    page = ct.PageDef.decode(page_record.payload if page_record is not None else b"")
    page_pr = sub(
        element,
        "hp:pagePr",
        (
            ("landscape", "NARROWLY" if page.props & 0x1 else "WIDELY"),
            ("width", page.width),
            ("height", page.height),
            ("gutterType", token(GUTTER, _bits(page.props, 1, 2))),
        ),
    )
    sub(
        page_pr,
        "hp:margin",
        (
            ("header", page.header),
            ("footer", page.footer),
            ("gutter", page.gutter),
            ("left", page.left),
            ("right", page.right),
            ("top", page.top),
            ("bottom", page.bottom),
        ),
    )
    notes = [r for r in ctrl.children if r.tag == rec.FOOTNOTE_SHAPE]
    _note_pr(element, "hp:footNotePr", notes[0] if notes else None, endnote=False)
    _note_pr(element, "hp:endNotePr", notes[1] if len(notes) > 1 else None, endnote=True)
    borders: list[rec.Record | None] = [r for r in ctrl.children if r.tag == rec.PAGE_BORDER_FILL]
    for kind, record in zip(PAGE_BORDER_TYPES, borders or [None, None, None]):
        border = ct.PageBorderFill.decode(record.payload if record is not None else b"")
        fill_element = sub(
            element,
            "hp:pageBorderFill",
            (
                ("type", kind),
                ("borderFillIDRef", border.border_fill),
                ("textBorder", "PAPER" if border.props & 0x1 else "CONTENT"),
                ("headerInside", flag(border.props & 0x2)),
                ("footerInside", flag(border.props & 0x4)),
                ("fillArea", token(FILL_AREA, _bits(border.props, 3, 2))),
            ),
        )
        left, right, top, bottom = border.offsets
        sub(fill_element, "hp:offset", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
    return element


def column_properties(parent: etree._Element, ctrl: rec.Record) -> etree._Element:
    """``hp:ctrl/hp:colPr`` from a ``cold`` control."""

    cd = ct.ColumnDef.decode(ctrl.payload)
    wrapper = sub(parent, "hp:ctrl")
    col = sub(
        wrapper,
        "hp:colPr",
        (
            ("id", ""),
            ("type", token(COL_TYPE, _bits(cd.props, 0, 2))),
            ("layout", token(COL_LAYOUT, _bits(cd.props, 10, 2))),
            ("colCount", cd.count),
            ("sameSz", flag(cd.same_width)),
            ("sameGap", cd.gap if cd.same_width else 0),
        ),
    )
    if cd.widths:
        # Width, gap, width, gap, ..., width: the last column has no gap.
        widths = [*cd.widths, 0] if len(cd.widths) % 2 else list(cd.widths)
        for index in range(0, len(widths) - 1, 2):
            sub(col, "hp:colSz", (("width", widths[index]), ("gap", widths[index + 1])))
    if cd.line_type:
        sub(
            col,
            "hp:colLine",
            (
                ("type", token(BORDER_LINE, cd.line_type)),
                ("width", token(BORDER_WIDTH, cd.line_width)),
                ("color", color(cd.line_color)),
            ),
        )
    return wrapper


# -- the section writer -------------------------------------------------------------------

TEXT_DIRECTION = ("HORIZONTAL", "VERTICAL", "VERTICALALL")
LINE_WRAP = ("BREAK", "SQUEEZE", "KEEP")
LIST_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM")
TABLE_PAGE_BREAK = ("NONE", "TABLE", "CELL")
CAPTION_SIDE = ("LEFT", "RIGHT", "TOP", "BOTTOM")
CHAR_ELEMENTS = {10: "hp:lineBreak", 24: "hp:hyphen", 30: "hp:nbSpace", 31: "hp:fwSpace"}


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
        for (_start, shape_id), end in zip(shapes, bounds):
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
                    name = CHAR_ELEMENTS.get(chunk.code)
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
                    last = self.control(run, ctrl)
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
            parent = last.getparent()
            if parent is not None:
                sub(parent, "hp:t")

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

    def control(self, run: etree._Element, ctrl: rec.Record) -> etree._Element | None:
        kind = bt.record_ctrl_id(ctrl) or "?"
        if kind == "secd":
            return section_properties(run, ctrl)
        if kind == "cold":
            return column_properties(run, ctrl)
        if kind == "tbl ":
            return self.table(run, ctrl)
        if kind in ("head", "foot"):
            return self.header_footer(run, ctrl, kind)
        if kind in ("fn  ", "en  "):
            return self.note(run, ctrl, kind)
        self.report.skip(f"control-{kind.strip() or kind}")
        return None

    def body(self, parent: etree._Element, ctrl: rec.Record) -> None:
        """The single paragraph list of a header, footer or note."""

        for header, paragraphs in lists(ctrl)[:1]:
            list_header = ct.ListHeader.decode(header.payload)
            attrs = list_attrs(list_header.props)
            width, height = list_header.text_size
            attrs[6] = ("textWidth", width)
            attrs[7] = ("textHeight", height)
            element = sub(parent, "hp:subList", attrs)
            self.paragraphs(element, paragraphs)

    def header_footer(self, run: etree._Element, ctrl: rec.Record, kind: str) -> etree._Element:
        hf = ct.HeaderFooterCtrl.decode(ctrl.payload)
        wrapper = sub(run, "hp:ctrl")
        element = sub(
            wrapper,
            "hp:header" if kind == "head" else "hp:footer",
            (("id", hf.number), ("applyPageType", token(PAGE_BORDER_TYPES, _bits(hf.props, 0, 2)))),
        )
        self.body(element, ctrl)
        return wrapper

    def note(self, run: etree._Element, ctrl: rec.Record, kind: str) -> etree._Element:
        nc = ct.NoteCtrl.decode(ctrl.payload)
        wrapper = sub(run, "hp:ctrl")
        attrs: list[tuple[str, object]] = [("number", nc.number)]
        if nc.prefix_char:
            attrs.append(("prefixChar", chr(nc.prefix_char)))
        attrs += [("suffixChar", chr(nc.suffix_char) if nc.suffix_char else ""), ("instId", nc.instance_id)]
        element = sub(wrapper, "hp:footNote" if kind == "fn  " else "hp:endNote", attrs)
        self.body(element, ctrl)
        return wrapper

    # tables --------------------------------------------------------------------------

    def table(self, run: etree._Element, ctrl: rec.Record) -> etree._Element:
        common = ct.ObjectCommon.decode(ctrl.payload)
        table_record = next((r for r in ctrl.children if r.tag == rec.TABLE), None)
        tp = ct.TableProps.decode(table_record.payload) if table_record is not None else ct.TableProps()
        attrs = object_attrs(common) + [
            ("pageBreak", token(TABLE_PAGE_BREAK, _bits(tp.props, 0, 2))),
            ("repeatHeader", flag(tp.props & 0x4)),
            ("rowCnt", tp.rows),
            ("colCnt", tp.cols),
            ("cellSpacing", tp.spacing),
            ("borderFillIDRef", tp.border_fill),
            ("noAdjust", flag(tp.props & 0x8)),
        ]
        table = sub(run, "hp:tbl", attrs)
        object_layout(table, common)
        caption, cells = table_lists(ctrl)
        if caption is not None:
            self.caption(table, *caption)
        left, right, top, bottom = tp.inner
        sub(table, "hp:inMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
        if tp.zones:
            zone_list = sub(table, "hp:cellzoneList")
            for start_row, start_col, end_row, end_col, fill in tp.zones:
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
        position = 0
        for row_size in tp.row_sizes or [len(cells)]:
            tr = sub(table, "hp:tr")
            for header, paragraphs in cells[position : position + row_size]:
                self.cell(tr, header, paragraphs)
            position += row_size
        return table

    def caption(self, parent: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        cap = ct.CaptionHeader.decode(header.payload)
        element = sub(
            parent,
            "hp:caption",
            (
                ("side", token(CAPTION_SIDE, _bits(cap.props, 0, 2))),
                ("fullSz", flag(cap.props & 0x4)),
                ("width", cap.width),
                ("gap", cap.gap),
                ("lastWidth", cap.last_width),
            ),
        )
        sub_list = sub(element, "hp:subList", list_attrs(cap.list_props))
        self.paragraphs(sub_list, paragraphs)

    def cell(self, tr: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        cell = ct.CellHeader.decode(header.payload)
        flags = cell.flags
        tc = sub(
            tr,
            "hp:tc",
            (
                ("name", cell.name),
                ("header", flag(flags & 0x4)),
                ("hasMargin", flag(flags & 0x1)),
                ("protect", flag(flags & 0x2)),
                ("editable", flag(flags & 0x8)),
                ("dirty", flag(flags & 0x10)),
                ("borderFillIDRef", cell.border_fill),
            ),
        )
        sub_list = sub(tc, "hp:subList", list_attrs(cell.list_props))
        self.paragraphs(sub_list, paragraphs)
        sub(tc, "hp:cellAddr", (("colAddr", cell.col), ("rowAddr", cell.row)))
        sub(tc, "hp:cellSpan", (("colSpan", cell.col_span), ("rowSpan", cell.row_span)))
        sub(tc, "hp:cellSz", (("width", cell.width), ("height", cell.height)))
        left, right, top, bottom = cell.margins
        sub(
            tc,
            "hp:cellMargin",
            (("left", _u32(left)), ("right", _u32(right)), ("top", _u32(top)), ("bottom", _u32(bottom))),
        )


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


def table_lists(
    ctrl: rec.Record,
) -> tuple[tuple[rec.Record, list[rec.Record]] | None, list[tuple[rec.Record, list[rec.Record]]]]:
    """A table's caption list (before the ``TABLE`` record) and its cell lists (after it)."""

    caption: tuple[rec.Record, list[rec.Record]] | None = None
    cells: list[tuple[rec.Record, list[rec.Record]]] = []
    seen_table = False
    for record in ctrl.children:
        if record.tag == rec.TABLE:
            seen_table = True
        elif record.tag == rec.LIST_HEADER:
            if seen_table:
                cells.append((record, []))
            else:
                caption = (record, [])
        elif record.tag == rec.PARA_HEADER:
            target = cells[-1] if seen_table and cells else caption
            if target is not None:
                target[1].append(record)
    return caption, cells


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
