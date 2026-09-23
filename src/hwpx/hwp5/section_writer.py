# SPDX-License-Identifier: Apache-2.0
"""``Contents/section<N>.xml`` -> the BodyText records of an HWP 5.0 section.

The inverse of :mod:`hwpx.hwp5.section_xml`. Each ``hp:p`` becomes a
``PARA_HEADER`` with its text, char shape runs, line segments and controls;
each element the writer cannot express is counted in ``unsupported`` so the
caller can refuse the save instead of dropping content silently.
"""

from __future__ import annotations

import struct
import zlib
from collections import Counter

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import controls as ct
from . import records as rec
from .owpml import BORDER_LINE, BORDER_WIDTH, NS, NUMBER_FORMAT, colorref, index_of
from .section_xml import (
    CAPTION_SIDE,
    COL_LAYOUT,
    COL_TYPE,
    ENDNOTE_PLACE,
    FIELD_TYPES,
    FILL_AREA,
    FOOTNOTE_PLACE,
    GUTTER,
    HEIGHT_REL,
    HORZ_ALIGN,
    HORZ_REL,
    LABEL_LANDSCAPE,
    LINE_WRAP,
    LIST_VERT_ALIGN,
    NOTE_NUMBERING,
    NUMBERING_TYPE,
    PAGE_BORDER_TYPES,
    PAGE_STARTS_ON,
    RANGE_MARKPEN,
    TABLE_PAGE_BREAK,
    TEXT_DIRECTION,
    TEXT_FLOW,
    TEXT_WRAP,
    VERT_ALIGN,
    VERT_REL,
    WIDTH_REL,
)

_HP = NS["hp"]
_CHAR_CODES = {"lineBreak": 10, "hyphen": 24, "nbSpace": 30, "fwSpace": 31}
_TAB_PADDING = b"\x20\x00" * 3
_SECTION_DIRECTION = {"HORIZONTAL": 0, "VERTICAL": 2, "VERTICALALL": 4}
#: The control id a field's text carries, by field type.
_FIELD_TEXT_ID = {kind: text_id for text_id, kind in FIELD_TYPES.items() if kind != "UNKNOWN"}
#: Field types whose control record is headed ``%unk`` while the text keeps the real id.
_FIELD_HEAD_UNKNOWN = frozenset({"MEMO", "PROOFREADING_MARKS_DELETE", "PROOFREADING_MARKS_SIGN"})
#: Field types written with property bit 1 set.
_FIELD_PROPS_BIT1 = frozenset({"MAILMERGE", "CROSSREF"})


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


def _number(value: str | None, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return default


def _int(element: etree._Element | None, name: str, default: int = 0) -> int:
    if element is None:
        return default
    return _number(element.get(name), default)


def _i16(value: int) -> int:
    """A 16-bit field Hancom may print as its unsigned 32-bit form (-1 as 4294967295)."""

    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def _flag(element: etree._Element | None, name: str) -> int:
    return 1 if element is not None and element.get(name) in ("1", "true") else 0


def _find(element: etree._Element, name: str) -> etree._Element | None:
    return element.find(f"{{{_HP}}}{name}")


def _extended(code: int, ctrl: str) -> bytes:
    return struct.pack("<HI", code, bt.ctrl_word(ctrl)) + bytes(8) + struct.pack("<H", code)


def _list_props(sub_list: etree._Element | None) -> int:
    if sub_list is None:
        return 0
    props = index_of(TEXT_DIRECTION, sub_list.get("textDirection"), 0) << 16
    props |= index_of(LINE_WRAP, sub_list.get("lineWrap"), 0) << 19
    props |= index_of(LIST_VERT_ALIGN, sub_list.get("vertAlign"), 0) << 21
    return props


def _object_common(ctrl: str, element: etree._Element) -> ct.ObjectCommon:
    sz = _find(element, "sz")
    pos = _find(element, "pos")
    margin = _find(element, "outMargin")
    props = _flag(pos, "treatAsChar") | _flag(pos, "affectLSpacing") << 2
    props |= index_of(VERT_REL, pos.get("vertRelTo") if pos is not None else None, 2) << 3
    props |= index_of(VERT_ALIGN, pos.get("vertAlign") if pos is not None else None, 0) << 5
    props |= index_of(HORZ_REL, pos.get("horzRelTo") if pos is not None else None, 2) << 8
    props |= index_of(HORZ_ALIGN, pos.get("horzAlign") if pos is not None else None, 0) << 10
    props |= _flag(pos, "flowWithText") << 13 | _flag(pos, "allowOverlap") << 14
    props |= index_of(WIDTH_REL, sz.get("widthRelTo") if sz is not None else None, 4) << 15
    props |= index_of(HEIGHT_REL, sz.get("heightRelTo") if sz is not None else None, 2) << 18
    props |= _flag(sz, "protect") << 20
    props |= index_of(TEXT_WRAP, element.get("textWrap"), 1) << 21
    props |= index_of(TEXT_FLOW, element.get("textFlow"), 0) << 24
    props |= index_of(NUMBERING_TYPE, element.get("numberingType"), 0) << 26
    props |= _flag(element, "lock") << 30
    return ct.ObjectCommon(
        ctrl,
        props,
        _i32(_int(pos, "vertOffset")),
        _i32(_int(pos, "horzOffset")),
        _int(sz, "width"),
        _int(sz, "height"),
        _int(element, "zOrder"),
        tuple(_i16(_int(margin, side)) for side in ("left", "right", "top", "bottom")),  # type: ignore[arg-type]
        _int(element, "id") & 0xFFFFFFFF,
        _flag(pos, "holdAnchorAndSO"),
        "",
        b"\0\0",
    )


class _Highlights:
    """Highlighter (markpen) ranges of a paragraph list, written as range tags."""

    def __init__(self) -> None:
        self.open: list[tuple[int, int]] = []  # (start, tag), in the order they began
        self.ranges: list[tuple[int, int, int]] = []

    def mark(self, element: etree._Element, position: int) -> None:
        if _local(element) == "markpenBegin":
            value = colorref(element.get("color")) & 0xFFFFFF
            self.open.append((position, RANGE_MARKPEN << 24 | value))
        elif self.open:
            start, tag = self.open.pop(0)
            self.ranges.append((start, position, tag))

    def take(self, end: int) -> list[tuple[int, int, int]]:
        """The ranges of the paragraph ending at *end*; a range still open ends
        there and goes on from the start of the next paragraph."""

        ranges = sorted(self.ranges + [(start, end, tag) for start, tag in self.open], key=lambda r: r[0])
        self.ranges = []
        self.open = [(0, tag) for _, tag in self.open]
        return ranges


class SectionRecords:
    """Builds the records of one section; ``unsupported`` counts what it could not write."""

    def __init__(self) -> None:
        self.unsupported: Counter[str] = Counter()
        # Fields begun and not yet ended: the begin id and the field-end
        # characters to write (None when the begin itself was refused).
        self.open_fields: list[tuple[str, bytes | None]] = []

    def section(self, root: etree._Element) -> list[rec.Record]:
        return self.paragraph_list([p for p in root if _local(p) == "p"], 0)

    def paragraph_list(self, paragraphs: list[etree._Element], level: int) -> list[rec.Record]:
        out: list[rec.Record] = []
        highlights = _Highlights()
        for index, paragraph in enumerate(paragraphs):
            out.extend(self.paragraph(paragraph, level, highlights, last=index == len(paragraphs) - 1))
        return out

    # paragraphs ------------------------------------------------------------------------

    def paragraph(
        self, element: etree._Element, level: int, highlights: _Highlights | None = None, *, last: bool
    ) -> list[rec.Record]:
        highlights = highlights if highlights is not None else _Highlights()
        units = bytearray()
        shapes: list[tuple[int, int]] = []
        controls: list[list[rec.Record]] = []
        codes: set[int] = set()
        has_secd = has_cold = False
        for run in element:
            if _local(run) != "run":
                continue
            position = len(units) // 2
            shape_id = _int(run, "charPrIDRef")
            if shapes and shapes[-1][0] == position:
                shapes[-1] = (position, shape_id)
            elif not shapes or shapes[-1][1] != shape_id:
                shapes.append((position, shape_id))
            for child in run:
                name = _local(child)
                if name == "t":
                    self.text(child, units, codes, highlights)
                elif name in ("markpenBegin", "markpenEnd"):
                    highlights.mark(child, len(units) // 2)
                elif name == "secPr":
                    units += _extended(2, "secd")
                    codes.add(2)
                    has_secd = True
                    controls.append(self.section_def(child, level + 1))
                elif name == "ctrl":
                    for item in child:
                        kind = _local(item)
                        if kind == "colPr":
                            units += _extended(2, "cold")
                            codes.add(2)
                            has_cold = True
                            controls.append(self.column_def(item, level + 1))
                        elif kind in ("header", "footer"):
                            units += _extended(16, "head" if kind == "header" else "foot")
                            codes.add(16)
                            controls.append(self.header_footer(item, kind, level + 1))
                        elif kind in ("footNote", "endNote"):
                            units += _extended(17, "fn  " if kind == "footNote" else "en  ")
                            codes.add(17)
                            controls.append(self.note(item, kind, level + 1))
                        elif kind == "fieldBegin":
                            field = self.field_begin(item, level + 1)
                            if field is not None:
                                units += _extended(3, field[0])
                                codes.add(3)
                                controls.append(field[1])
                        elif kind == "fieldEnd":
                            end = self.field_end(item)
                            if end is not None:
                                units += end
                                codes.add(4)
                        else:
                            self.unsupported[f"ctrl/{kind}"] += 1
                elif name == "tbl":
                    units += _extended(11, "tbl ")
                    codes.add(11)
                    controls.append(self.table(child, level + 1))
                else:
                    self.unsupported[name] += 1
        if not shapes:
            shapes.append((0, 0))
        units += struct.pack("<H", bt.PARA_BREAK)
        count = len(units) // 2
        mask = 0
        for code in codes:
            mask |= 1 << code
        break_type = (1 if has_secd else 0) | (2 if has_cold else 0)
        break_type |= 4 if element.get("pageBreak") == "1" else 0
        break_type |= 8 if element.get("columnBreak") == "1" else 0
        segs = [
            s for s in (element.find(f"{{{_HP}}}linesegarray") if element.find(f"{{{_HP}}}linesegarray") is not None else [])
            if _local(s) == "lineseg"
        ]
        ranges = highlights.take(count - 1)
        header = struct.pack(
            "<IIHBBHHHIH",
            count | (0x80000000 if last else 0),
            mask,
            _int(element, "paraPrIDRef"),
            _int(element, "styleIDRef") & 0xFF,
            break_type,
            len(shapes),
            len(ranges),
            len(segs),
            _int(element, "id") & 0xFFFFFFFF,
            _int(element, "merged"),
        )
        out = [rec.Record(rec.PARA_HEADER, level, header)]
        if count > 1:
            out.append(rec.Record(rec.PARA_TEXT, level + 1, bytes(units)))
        out.append(rec.Record(rec.PARA_CHAR_SHAPE, level + 1, b"".join(struct.pack("<II", p, s) for p, s in shapes)))
        if segs:
            payload = b"".join(
                struct.pack(
                    "<IiiiiiiiI",
                    _int(s, "textpos"),
                    _i32(_int(s, "vertpos")),
                    _i32(_int(s, "vertsize")),
                    _i32(_int(s, "textheight")),
                    _i32(_int(s, "baseline")),
                    _i32(_int(s, "spacing")),
                    _i32(_int(s, "horzpos")),
                    _i32(_int(s, "horzsize")),
                    _int(s, "flags") & 0xFFFFFFFF,
                )
                for s in segs
            )
            out.append(rec.Record(rec.PARA_LINE_SEG, level + 1, payload))
        if ranges:
            payload = b"".join(struct.pack("<III", start, end, tag) for start, end, tag in ranges)
            out.append(rec.Record(rec.PARA_RANGE_TAG, level + 1, payload))
        for control in controls:
            out.extend(control)
        return out

    def text(self, element: etree._Element, units: bytearray, codes: set[int], highlights: _Highlights) -> None:
        self._chars(element.text or "", units, codes)
        for child in element:
            name = _local(child)
            if name in ("markpenBegin", "markpenEnd"):
                highlights.mark(child, len(units) // 2)
            elif name == "tab":
                units += struct.pack(
                    "<HIBB", bt.TAB, _int(child, "width"), _int(child, "leader") & 0xFF, _int(child, "type") & 0xFF
                )
                units += _TAB_PADDING + struct.pack("<H", bt.TAB)
                codes.add(bt.TAB)
            elif name in _CHAR_CODES:
                units += struct.pack("<H", _CHAR_CODES[name])
                codes.add(_CHAR_CODES[name])
            else:
                self.unsupported[f"t/{name}"] += 1
            self._chars(child.tail or "", units, codes)

    def _chars(self, value: str, units: bytearray, codes: set[int]) -> None:
        for char in value:
            if char == "\t":
                units += struct.pack("<HIBB", bt.TAB, 4000, 0, 0) + _TAB_PADDING + struct.pack("<H", bt.TAB)
                codes.add(bt.TAB)
            elif char == "\n":
                units += struct.pack("<H", 10)
                codes.add(10)
            elif ord(char) < 32:
                continue
            else:
                units += char.encode("utf-16-le", errors="surrogatepass")

    # controls ------------------------------------------------------------------------

    def section_def(self, element: etree._Element, level: int) -> list[rec.Record]:
        grid = _find(element, "grid")
        start = _find(element, "startNum")
        visibility = _find(element, "visibility")
        numbers = _find(element, "lineNumberShape")
        props = _flag(visibility, "hideFirstHeader") | _flag(visibility, "hideFirstFooter") << 1
        props |= _flag(visibility, "hideFirstMasterPage") << 2
        border = visibility.get("border") if visibility is not None else "SHOW_ALL"
        fill = visibility.get("fill") if visibility is not None else "SHOW_ALL"
        props |= (1 << 3 if border == "HIDE_FIRST" else 0) | (1 << 8 if border == "SHOW_FIRST" else 0)
        props |= (1 << 4 if fill == "HIDE_FIRST" else 0) | (1 << 9 if fill == "SHOW_FIRST" else 0)
        props |= _flag(visibility, "hideFirstPageNum") << 5
        props |= _flag(visibility, "hideFirstEmptyLine") << 19
        props |= _flag(visibility, "showLineNumber") << 24
        props |= index_of(PAGE_STARTS_ON, start.get("pageStartsOn") if start is not None else None, 0) << 20
        props |= _flag(grid, "wonggojiFormat") << 22
        direction = element.get("textDirection", "HORIZONTAL")
        direction_word = _SECTION_DIRECTION.get(direction, 0) | _flag(element, "textVerticalWidthHead") << 4
        tab_raw = _int(element, "tabStopVal", 4000) * 2 + (1 if element.get("tabStopUnit") == "CHAR" else 0)
        # Master pages are not written yet; a count without the pages makes the
        # file unreadable, so the section refuses instead.
        master_pages = max(_int(element, "masterPageCnt"), len(element.findall(f"{{{_HP}}}masterPage")))
        if master_pages:
            self.unsupported["masterPage"] += master_pages
        sd = ct.SectionDef(
            props,
            _int(element, "spaceColumns", 1134),
            _int(grid, "lineGrid"),
            _int(grid, "charGrid"),
            tab_raw if element.get("tabStopVal") is not None else _int(element, "tabStop", 8000),
            _int(element, "outlineShapeIDRef", 1),
            _int(start, "page"),
            _int(start, "pic"),
            _int(start, "tbl"),
            _int(start, "equation"),
            0,
            0,
            0,
            _int(element, "memoShapeIDRef"),
            direction_word,
            _int(numbers, "restartType"),
            _int(numbers, "countBy"),
            _int(numbers, "distance"),
            _int(numbers, "startNumber"),
        )
        out = [rec.Record(rec.CTRL_HEADER, level, sd.encode())]
        page_pr = _find(element, "pagePr")
        margin = _find(page_pr, "margin") if page_pr is not None else None
        page = ct.PageDef(
            _int(page_pr, "width", 59528),
            _int(page_pr, "height", 84188),
            _int(margin, "left", 8504),
            _int(margin, "right", 8504),
            _int(margin, "top", 5668),
            _int(margin, "bottom", 4252),
            _int(margin, "header", 4252),
            _int(margin, "footer", 4252),
            _int(margin, "gutter"),
            (1 if page_pr is not None and page_pr.get("landscape") == "NARROWLY" else 0)
            | index_of(GUTTER, page_pr.get("gutterType") if page_pr is not None else None, 0) << 1,
        )
        out.append(rec.Record(rec.PAGE_DEF, level + 1, page.encode()))
        for name, places in (("footNotePr", FOOTNOTE_PLACE), ("endNotePr", ENDNOTE_PLACE)):
            out.append(rec.Record(rec.FOOTNOTE_SHAPE, level + 1, self.note_shape(_find(element, name), places).encode()))
        fills = {f.get("type"): f for f in element.findall(f"{{{_HP}}}pageBorderFill")}
        for kind in PAGE_BORDER_TYPES:
            item = fills.get(kind)
            offset = _find(item, "offset") if item is not None else None
            border_props = (1 if item is None or item.get("textBorder", "PAPER") == "PAPER" else 0)
            border_props |= _flag(item, "headerInside") << 1 | _flag(item, "footerInside") << 2
            border_props |= index_of(FILL_AREA, item.get("fillArea") if item is not None else None, 0) << 3
            value = ct.PageBorderFill(
                border_props,
                tuple(_int(offset, side, 1417) for side in ("left", "right", "top", "bottom")),  # type: ignore[arg-type]
                _int(item, "borderFillIDRef", 1),
            )
            out.append(rec.Record(rec.PAGE_BORDER_FILL, level + 1, value.encode()))
        return out

    def note_shape(self, element: etree._Element | None, places: tuple[str, ...]) -> ct.NoteShape:
        if element is None:
            return ct.NoteShape()
        fmt = _find(element, "autoNumFormat")
        line = _find(element, "noteLine")
        spacing = _find(element, "noteSpacing")
        numbering = _find(element, "numbering")
        placement = _find(element, "placement")
        props = index_of(NUMBER_FORMAT, fmt.get("type") if fmt is not None else None, 0)
        props |= index_of(places, placement.get("place") if placement is not None else None, 0) << 8
        props |= index_of(NOTE_NUMBERING, numbering.get("type") if numbering is not None else None, 0) << 10
        props |= _flag(fmt, "supscript") << 12 | _flag(placement, "beneathText") << 13

        def char(name: str) -> int:
            text = fmt.get(name, "") if fmt is not None else ""
            return ord(text[0]) if text else 0

        return ct.NoteShape(
            props,
            char("userChar"),
            char("prefixChar"),
            char("suffixChar"),
            _int(numbering, "newNum", 1),
            _i32(_int(line, "length", -1)),
            _int(spacing, "aboveLine", 850),
            _int(spacing, "belowLine", 567),
            _int(spacing, "betweenNotes", 283),
            index_of(BORDER_LINE, line.get("type") if line is not None else None, 1),
            index_of(BORDER_WIDTH, line.get("width") if line is not None else None, 1),
            colorref(line.get("color") if line is not None else "#000000"),
        )

    def column_def(self, element: etree._Element, level: int) -> list[rec.Record]:
        count = max(_int(element, "colCount", 1), 1)
        same = _flag(element, "sameSz") or count == 1
        props = index_of(COL_TYPE, element.get("type"), 0) | (count & 0xFF) << 2
        props |= index_of(COL_LAYOUT, element.get("layout"), 0) << 10
        props |= (1 << 12) if same else 0
        widths: list[int] = []
        if not same:
            for size in element.findall(f"{{{_HP}}}colSz"):
                widths += [_int(size, "width"), _int(size, "gap")]
            widths = widths[: count * 2 - 1]
        line = _find(element, "colLine")
        value = ct.ColumnDef(
            props,
            _int(element, "sameGap") if same else 0,
            widths,
            0,
            index_of(BORDER_LINE, line.get("type") if line is not None else None, 0),
            index_of(BORDER_WIDTH, line.get("width") if line is not None else None, 0),
            colorref(line.get("color") if line is not None else "#000000") if line is not None else 0,
        )
        return [rec.Record(rec.CTRL_HEADER, level, value.encode())]

    # fields --------------------------------------------------------------------------

    def field_begin(self, element: etree._Element, level: int) -> tuple[str, list[rec.Record]] | None:
        """The text id and records of a field start; None when the field is refused."""

        kind = element.get("type", "")
        begin_id = element.get("id", "")
        text_id = _FIELD_TEXT_ID.get(kind)
        # Memo bodies and fields of unknown kinds are not written yet.
        if text_id is None or kind == "MEMO" or _find(element, "subList") is not None:
            self.unsupported[f"field/{kind or '?'}"] += 1
            self.open_fields.append((begin_id, None))
            return None
        params: dict[str, str] = {}
        container = _find(element, "parameters")
        for item in container if container is not None else ():
            params.setdefault(item.get("name", ""), item.text or "")
        extra = _number(params.get("Prop")) & 0xFF
        props = _flag(element, "editable") | _flag(element, "dirty") << 15
        props |= 2 if kind in _FIELD_PROPS_BIT1 else 0
        try:
            instance_id = int(begin_id) & 0xFFFFFFFF
        except ValueError:
            instance_id = zlib.crc32(begin_id.encode("utf-8"))
        value = ct.FieldCtrl(
            "%unk" if kind in _FIELD_HEAD_UNKNOWN else text_id,
            props,
            extra,
            params.get("Command", ""),
            instance_id,
            max(_int(element, "zorder", -1), 0),
        )
        records = [rec.Record(rec.CTRL_HEADER, level, value.encode())]
        name = element.get("name", "")
        if name or kind == "CLICK_HERE":
            records.append(rec.Record(rec.CTRL_DATA, level + 1, ct.name_parameter_set(name)))
        # The field end repeats the field's text id with the property byte, and
        # whether the field is editable.
        end_id = (bt.ctrl_word(text_id) & 0xFFFFFF) | extra << 24
        self.open_fields.append((begin_id, struct.pack("<HIIIH", 4, end_id, props & 1, 0, 4)))
        return text_id, records

    def field_end(self, element: etree._Element) -> bytes | None:
        """The field-end characters for the field the end closes."""

        begin_id = element.get("beginIDRef", "")
        index = len(self.open_fields) - 1
        while index >= 0 and self.open_fields[index][0] != begin_id:
            index -= 1
        if index < 0:
            index = len(self.open_fields) - 1
        if index < 0:
            self.unsupported["fieldEnd-without-begin"] += 1
            return None
        return self.open_fields.pop(index)[1]

    def _body(self, element: etree._Element, level: int, *, sized: bool) -> list[rec.Record]:
        sub_list = _find(element, "subList")
        paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
        if not paragraphs:
            paragraphs = [etree.Element(f"{{{_HP}}}p")]
        extra = bytes(10) if not sized else struct.pack(
            "<HII", 0, _int(sub_list, "textWidth"), _int(sub_list, "textHeight")
        ) + bytes(18)
        header = ct.ListHeader(len(paragraphs), _list_props(sub_list), extra)
        return [rec.Record(rec.LIST_HEADER, level, header.encode()), *self.paragraph_list(paragraphs, level)]

    def header_footer(self, element: etree._Element, kind: str, level: int) -> list[rec.Record]:
        applies = index_of(PAGE_BORDER_TYPES, element.get("applyPageType"), 0)
        value = ct.HeaderFooterCtrl("head" if kind == "header" else "foot", applies, _int(element, "id"))
        return [rec.Record(rec.CTRL_HEADER, level, value.encode()), *self._body(element, level + 1, sized=True)]

    def note(self, element: etree._Element, kind: str, level: int) -> list[rec.Record]:
        suffix = element.get("suffixChar", ")")
        prefix = element.get("prefixChar", "")
        value = ct.NoteCtrl(
            "fn  " if kind == "footNote" else "en  ",
            _int(element, "number", 1),
            ord(prefix[0]) if prefix else 0,
            ord(suffix[0]) if suffix else 0,
            0,
            _int(element, "instId") & 0xFFFFFFFF,
        )
        return [rec.Record(rec.CTRL_HEADER, level, value.encode()), *self._body(element, level + 1, sized=False)]

    # tables --------------------------------------------------------------------------

    def table(self, element: etree._Element, level: int) -> list[rec.Record]:
        common = _object_common("tbl ", element)
        out = [rec.Record(rec.CTRL_HEADER, level, common.encode())]
        label = _find(element, "label")
        if label is not None:
            values = {name: _int(label, name) for name in ct.LABEL_ITEMS}
            values["landscape"] = index_of(LABEL_LANDSCAPE, label.get("landscape"), 0)
            out.append(rec.Record(rec.CTRL_DATA, level + 1, ct.label_parameter_set(values)))
        caption = _find(element, "caption")
        if caption is not None:
            out.extend(self.caption(caption, level + 1))
        rows = [tr for tr in element if _local(tr) == "tr"]
        inner = _find(element, "inMargin")
        zones = []
        zone_list = _find(element, "cellzoneList")
        if zone_list is not None:
            for zone in zone_list:
                zones.append(
                    (
                        _int(zone, "startRowAddr"),
                        _int(zone, "startColAddr"),
                        _int(zone, "endRowAddr"),
                        _int(zone, "endColAddr"),
                        _int(zone, "borderFillIDRef"),
                    )
                )
        props = index_of(TABLE_PAGE_BREAK, element.get("pageBreak"), 0)
        props |= _flag(element, "repeatHeader") << 2 | _flag(element, "noAdjust") << 3
        table = ct.TableProps(
            props,
            _int(element, "rowCnt", len(rows)),
            _int(element, "colCnt", 1),
            _int(element, "cellSpacing"),
            tuple(_int(inner, side, default) for side, default in (("left", 510), ("right", 510), ("top", 141), ("bottom", 141))),  # type: ignore[arg-type]
            [len([tc for tc in tr if _local(tc) == "tc"]) for tr in rows],
            _int(element, "borderFillIDRef", 1),
            zones,
        )
        out.append(rec.Record(rec.TABLE, level + 1, table.encode()))
        for tr in rows:
            for tc in tr:
                if _local(tc) == "tc":
                    out.extend(self.cell(tc, level + 1))
        return out

    def caption(self, element: etree._Element, level: int) -> list[rec.Record]:
        sub_list = _find(element, "subList")
        paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
        props = index_of(CAPTION_SIDE, element.get("side"), 3) | _flag(element, "fullSz") << 2
        header = ct.CaptionHeader(
            len(paragraphs),
            _list_props(sub_list),
            0,
            props,
            _int(element, "width", 8504),
            _int(element, "gap", 850),
            _int(element, "lastWidth"),
        )
        return [rec.Record(rec.LIST_HEADER, level, header.encode()), *self.paragraph_list(paragraphs, level)]

    def cell(self, element: etree._Element, level: int) -> list[rec.Record]:
        sub_list = _find(element, "subList")
        paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
        if not paragraphs:
            paragraphs = [etree.Element(f"{{{_HP}}}p")]
        addr = _find(element, "cellAddr")
        span = _find(element, "cellSpan")
        size = _find(element, "cellSz")
        margin = _find(element, "cellMargin")
        flags = _flag(element, "hasMargin") | _flag(element, "protect") << 1 | _flag(element, "header") << 2
        flags |= _flag(element, "editable") << 3 | _flag(element, "dirty") << 4
        width = _int(size, "width")
        cell = ct.CellHeader(
            len(paragraphs),
            _list_props(sub_list),
            flags,
            _int(addr, "colAddr"),
            _int(addr, "rowAddr"),
            _int(span, "colSpan", 1),
            _int(span, "rowSpan", 1),
            width,
            _int(size, "height"),
            tuple(_i16(_int(margin, side)) for side in ("left", "right", "top", "bottom")),  # type: ignore[arg-type]
            _int(element, "borderFillIDRef", 1),
            width,
            element.get("name", ""),
            bytes(8) if element.get("name") else bytes(9),
        )
        return [rec.Record(rec.LIST_HEADER, level, cell.encode()), *self.paragraph_list(paragraphs, level)]


def build_section_records(root: etree._Element) -> tuple[list[rec.Record], Counter[str]]:
    """Records of one ``hs:sec`` and the counts of elements that could not be written."""

    writer = SectionRecords()
    return writer.section(root), writer.unsupported
