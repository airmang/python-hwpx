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
from datetime import datetime, timedelta
from typing import Callable

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import controls as ct
from . import records as rec
from . import shapes as sh
from .docinfo_writer import fill as fill_from_brush
from .header_xml import IMAGE_EFFECT
from .owpml import BORDER_LINE, BORDER_WIDTH, NS, NUMBER_FORMAT, colorref, index_of
from .section_common import (
    HEIGHT_REL,
    HORZ_ALIGN,
    HORZ_REL,
    LINE_WRAP,
    LIST_VERT_ALIGN,
    NUMBERING_TYPE,
    TEXT_DIRECTION,
    TEXT_FLOW,
    TEXT_WRAP,
    VERT_ALIGN,
    VERT_REL,
    WIDTH_REL,
)
from .section_xml import (
    CAPTION_SIDE,
    COL_LAYOUT,
    COL_TYPE,
    COMPOSE_CIRCLE,
    COMPOSE_FRAME_GLYPH,
    COMPOSE_TYPE,
    DUTMAL_ALIGN,
    DUTMAL_POS,
    ENDNOTE_PLACE,
    FIELD_TYPES,
    FILL_AREA,
    FOOTNOTE_PLACE,
    GUTTER,
    LABEL_LANDSCAPE,
    MASTER_PAGE_BITS,
    MASTER_PAGE_LAST,
    NOTE_NUMBERING,
    NUMBER_TYPE,
    PAGE_BORDER_TYPES,
    PAGE_HIDING,
    PAGE_NUM_POS,
    PAGE_STARTS_ON,
    RANGE_MARKPEN,
    TABLE_PAGE_BREAK,
    TITLE_MARK,
    TITLE_MARK_CODE,
    TITLE_MARK_IGNORED,
)
from .shape_xml import (
    ARC_TYPE,
    ARROW,
    ARROW_SIZE,
    DROPCAP,
    DROPCAP_PATH,
    ELLIPSE_POINTS,
    END_CAP,
    HYPERLINK_PATH,
    LINE_STYLE,
    OUTLINE_STYLE,
    ROTATE_IMAGE,
    SHADOW,
)

_HP = NS["hp"]
_HC = NS["hc"]
_CHAR_CODES = {"lineBreak": 10, "hyphen": 24, "nbSpace": 30, "fwSpace": 31}
_TAB_PADDING = b"\x20\x00" * 3
_SECTION_DIRECTION = {"HORIZONTAL": 0, "VERTICAL": 2, "VERTICALALL": 4}
#: The control id a field's text carries, by field type.
_FIELD_TEXT_ID = {kind: text_id for text_id, kind in FIELD_TYPES.items() if kind != "UNKNOWN"}
#: Field types whose control record is headed ``%unk`` while the text keeps the real id.
_FIELD_HEAD_UNKNOWN = frozenset({"MEMO", "PROOFREADING_MARKS_DELETE", "PROOFREADING_MARKS_SIGN"})
#: Field types written with property bit 1 set.
_FIELD_PROPS_BIT1 = frozenset({"MAILMERGE", "CROSSREF"})
#: ``hp:ctrl`` children written as one control: the control character code and id.
_MARKERS = {
    "pageNum": (21, "pgnp"),
    "pageHiding": (21, "pghd"),
    "newNum": (21, "nwno"),
    "autoNum": (18, "atno"),
    "bookmark": (22, "bokm"),
    "indexmark": (22, "idxm"),
}


#: The shape kind of each drawing object element.
_SHAPE_KINDS = {name: kind for kind, name in sh.SHAPE_ELEMENTS.items()}
#: Shape component flags with no OWPML attribute of their own: a text box, a
#: picture, a container, and a shape inside a container. Hancom sets them so.
_FLAG_TEXT_BOX = 1 << 24
_FLAG_PICTURE = (1 << 26) | (1 << 29)
_FLAG_GROUP = 1 << 16
_FLAG_GROUP_MEMBER = 1 << 17
_IDENTITY: sh.Matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
#: Children of a container that are not shapes.
_CONTAINER_PARTS = frozenset({"offset", "orgSz", "curSz", "flip", "rotationInfo", "renderingInfo", "sz", "pos", "outMargin", "shapeComment", "caption", "parameterset"})


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


#: Hancom prints a memo's creation time in Korean time (UTC+9).
_MEMO_TIME_OFFSET = timedelta(hours=9)


def _memo_command(number: int, params: dict[str, str]) -> str:
    """The command of a memo that has none: ``MEMO/<memo shape>/<number>/<time low>/<time
    high>/<author>/`` followed by Hancom's closing ``\\;;``."""

    ticks = 0
    created = params.get("CreateDateTime", "")
    try:
        when = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ") - _MEMO_TIME_OFFSET
        ticks = int((when - datetime(1601, 1, 1)).total_seconds() * 10_000_000)
    except ValueError:
        ticks = 0
    ticks = max(ticks, 0)
    author = params.get("Author", "")
    shape = params.get("MemoShapeIDRef") or "65535"
    return f"MEMO/{shape}/{number}/{ticks & 0xFFFFFFFF}/{ticks >> 32}/{author}/" + chr(92) + ";;"


def _matrix_value(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:  # Hancom's "-nan(ind)": the negative quiet NaN
        return float(struct.unpack("<d", struct.pack("<Q", 0xFFF8000000000000))[0])


def _parameter_items(element: etree._Element) -> list[ct.ParameterItem]:
    items: list[ct.ParameterItem] = []
    for child in element:
        name, item_id = _local(child), _int(child, "name") & 0xFFFF
        if name == "listParam":
            items.append(ct.ParameterItem(item_id, ct.PIT_SET, ct.ParameterSet(item_id, _parameter_items(child))))
        elif name == "stringParam":
            items.append(ct.ParameterItem(item_id, ct.PIT_BSTR, child.text or ""))
        elif name == "unsignedintegerParam":
            items.append(ct.ParameterItem(item_id, 9, _number(child.text) & 0xFFFFFFFF))
        elif name == "integerParam":
            items.append(ct.ParameterItem(item_id, 4, _i32(_number(child.text))))
    return items


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


def _char(element: etree._Element | None, name: str) -> int:
    value = element.get(name) if element is not None else None
    return ord(value[0]) if value else 0


def _char_code(element: etree._Element, name: str, default: int) -> int:
    """A character attribute given as its code (``41``) or as the character (``)``)."""

    value = element.get(name)
    if value is None:
        return default
    if value.isdigit():
        return int(value) & 0xFFFF
    return ord(value[0]) & 0xFFFF if value else 0


def _child_text(element: etree._Element, name: str) -> str:
    child = _find(element, name)
    return "".join(child.itertext()) if child is not None else ""



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
    # Hancom refuses an object whose caption list is not announced by bit 29.
    props |= (1 << 29) if _find(element, "caption") is not None else 0
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

    def __init__(
        self,
        bin_ids: dict[str, int] | None = None,
        master_page: Callable[[str], etree._Element | None] | None = None,
    ) -> None:
        self.unsupported: Counter[str] = Counter()
        # Memo bodies (their hp:subList) in the order of their memo fields; the
        # document keeps them all on the last paragraph of its last section.
        self.memo_bodies: list[tuple[int, etree._Element | None]] = []
        # BinData id of each binary item id, for pictures.
        self.bin_ids = bin_ids or {}
        # The master page part (its root) a manifest item id names.
        self.master_page = master_page or (lambda item_id: None)
        # The section's last-page and optional-page master pages, which hang
        # on its last paragraph.
        self.last_paragraph_pages: list[etree._Element] = []
        # Fields begun and not yet ended: the begin id and the field-end
        # characters to write (None when the begin itself was refused).
        self.open_fields: list[tuple[str, bytes | None]] = []

    def section(self, root: etree._Element) -> list[rec.Record]:
        paragraphs: list[etree._Element] = []
        for child in root:
            if not isinstance(child.tag, str):
                continue
            name = _local(child)
            if name == "p":
                paragraphs.append(child)
            elif name != "memogroup":
                self.unsupported[f"sec/{name}"] += 1
        # hp:memogroup repeats the bodies of the MEMO fields, whose own copies
        # Hancom keeps (even where the two differ); it has no records of its own.
        records = self.paragraph_list(paragraphs, 0)
        for page in self.last_paragraph_pages:
            records.extend(self.master_page_list(page, 1))
        return records

    def memo_records(self, bodies: list[tuple[int, etree._Element | None]]) -> list[rec.Record]:
        """The memo bodies of a document, to hang on its last paragraph: each
        ``MEMO_LIST`` (the memo's number), list header and paragraphs."""

        out: list[rec.Record] = []
        for number, sub_list in bodies:
            paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
            if not paragraphs:
                paragraphs = [etree.Element(f"{{{_HP}}}p")]
            header = ct.ListHeader(len(paragraphs), _list_props(sub_list), bytes(10))
            out.append(rec.Record(rec.MEMO_LIST, 1, struct.pack("<I", number)))
            out.append(rec.Record(rec.LIST_HEADER, 1, header.encode()))
            out.extend(self.paragraph_list(paragraphs, 1))
        return out

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
                        elif kind in _MARKERS:
                            code, ctrl_id = _MARKERS[kind]
                            units += _extended(code, ctrl_id)
                            codes.add(code)
                            controls.append(self.marker(item, kind, level + 1))
                        else:
                            self.unsupported[f"ctrl/{kind}"] += 1
                elif name == "tbl":
                    units += _extended(11, "tbl ")
                    codes.add(11)
                    controls.append(self.table(child, level + 1))
                elif name == "dutmal":
                    units += _extended(23, "tdut")
                    codes.add(23)
                    controls.append(self.dutmal(child, level + 1))
                elif name == "compose":
                    composed = self.compose(child, level + 1)
                    if composed is not None:
                        units += _extended(23, "tcps")
                        codes.add(23)
                        controls.append(composed)
                elif name in _SHAPE_KINDS:
                    units += _extended(11, "gso ")
                    codes.add(11)
                    controls.append(self.drawing(child, level + 1))
                elif name == "equation":
                    units += _extended(11, "eqed")
                    codes.add(11)
                    controls.append(self.equation(child, level + 1))
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
            elif name == "titleMark":
                word = bt.ctrl_word(TITLE_MARK if _flag(child, "ignore") else TITLE_MARK_IGNORED)
                units += struct.pack("<HI", TITLE_MARK_CODE, word) + _TAB_PADDING + b"\x20\x00"
                units += struct.pack("<H", TITLE_MARK_CODE)
                codes.add(TITLE_MARK_CODE)
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
        # Master pages for both, even and odd pages hang on the section
        # definition, each marked by a property bit; the others on the section's
        # last paragraph, which the definition counts.
        pages = self.section_master_pages(element)
        props |= sum(1 << bit for bit, page_type in MASTER_PAGE_BITS if page_type in pages)
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
            len(self.last_paragraph_pages),
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
        for _bit, page_type in MASTER_PAGE_BITS:
            if page_type in pages:
                out.extend(self.master_page_list(pages[page_type], level + 1))
        return out

    def section_master_pages(self, element: etree._Element) -> dict[str, etree._Element]:
        """The section's master pages for both, even and odd pages by type;
        its last-page and optional pages go to ``last_paragraph_pages``. A
        missing part, an unknown type or a second page for the same pages is
        unsupported."""

        pages: dict[str, etree._Element] = {}
        self.last_paragraph_pages = []
        applies: set[tuple[str | None, int]] = set()
        for ref in element.findall(f"{{{_HP}}}masterPage"):
            page = self.master_page(ref.get("idRef", ""))
            page_type = page.get("type") if page is not None else None
            number = _int(page, "pageNumber") if page_type == "OPTIONAL_PAGE" else 0
            if page is None or page_type in pages or (page_type, number) in applies:
                self.unsupported["masterPage"] += 1
            elif page_type == "LAST_PAGE" or (page_type == "OPTIONAL_PAGE" and number > 0):
                applies.add((page_type, number))
                self.last_paragraph_pages.append(page)
            elif page_type in PAGE_BORDER_TYPES:
                pages[page_type] = page
            else:
                self.unsupported[f"masterPage/{page_type}"] += 1
        return pages

    def master_page_list(self, page: etree._Element, level: int) -> list[rec.Record]:
        """A master page's list header and paragraphs. Offset 18 of the header
        says where the page applies (0 under the section definition, 3 on the
        last page, 3 plus its number on an optional page), offset 22 holds its
        duplicate and front flags."""

        sub_list = _find(page, "subList")
        paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
        if not paragraphs:
            paragraphs = [etree.Element(f"{{{_HP}}}p")]
        kind = 0
        if page.get("type") == "LAST_PAGE":
            kind = MASTER_PAGE_LAST
        elif page.get("type") == "OPTIONAL_PAGE":
            kind = MASTER_PAGE_LAST + _int(page, "pageNumber")
        flags = _flag(page, "pageDuplicate") | _flag(page, "pageFront") << 1
        width = _int(sub_list, "textWidth") & 0xFFFFFFFF
        height = _int(sub_list, "textHeight") & 0xFFFFFFFF
        extra = struct.pack("<HIIHHHH", 0, width, height, 0, kind & 0xFFFF, 0, flags) + bytes(10)
        header = ct.ListHeader(len(paragraphs), _list_props(sub_list), extra)
        return [rec.Record(rec.LIST_HEADER, level, header.encode()), *self.paragraph_list(paragraphs, level)]

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

    def marker(self, element: etree._Element, kind: str, level: int) -> list[rec.Record]:
        """The control record of a page number place, page hiding, numbering,
        bookmark or index mark."""

        if kind == "pageNum":
            props = index_of(NUMBER_FORMAT, element.get("formatType"), 0) & 0xFF
            props |= index_of(PAGE_NUM_POS, element.get("pos"), 0) << 8
            payload = ct.PageNumberPosition(props, side_char=_char(element, "sideChar")).encode()
        elif kind == "pageHiding":
            props = 0
            for bit, name in enumerate(PAGE_HIDING):
                props |= _flag(element, name) << bit
            payload = ct.PageHiding(props).encode()
        elif kind == "newNum":
            props = index_of(NUMBER_TYPE, element.get("numType"), 0)
            payload = ct.NewNumber(props, _int(element, "num", 1) & 0xFFFF).encode()
        elif kind == "autoNum":
            fmt = _find(element, "autoNumFormat")
            props = index_of(NUMBER_TYPE, element.get("numType"), 0)
            props |= (index_of(NUMBER_FORMAT, fmt.get("type") if fmt is not None else None, 0) & 0xFF) << 4
            props |= _flag(fmt, "supscript") << 12
            payload = ct.AutoNumber(
                props,
                _int(element, "num", 1) & 0xFFFF,
                _char(fmt, "userChar"),
                _char(fmt, "prefixChar"),
                _char(fmt, "suffixChar"),
            ).encode()
        elif kind == "bookmark":
            header = rec.Record(rec.CTRL_HEADER, level, struct.pack("<I", bt.ctrl_word("bokm")))
            return [header, rec.Record(rec.CTRL_DATA, level + 1, ct.name_parameter_set(element.get("name", "")))]
        else:
            payload = ct.IndexMark(_child_text(element, "firstKey"), _child_text(element, "secondKey")).encode()
        return [rec.Record(rec.CTRL_HEADER, level, payload)]

    def dutmal(self, element: etree._Element, level: int) -> list[rec.Record]:
        value = ct.Dutmal(
            _child_text(element, "mainText"),
            _child_text(element, "subText"),
            index_of(DUTMAL_POS, element.get("posType"), 0),
            _int(element, "szRatio"),
            _int(element, "option"),
            _int(element, "styleIDRef"),
            index_of(DUTMAL_ALIGN, element.get("align"), 0),
        )
        return [rec.Record(rec.CTRL_HEADER, level, value.encode())]

    def compose(self, element: etree._Element, level: int) -> list[rec.Record] | None:
        """Overlapped characters. The text starts with the frame's glyph, as
        Hancom writes it (with no frame, a lone character gets an ideographic
        space in front). A frame whose glyph is not known, or a size step or
        place count the record cannot hold, is unsupported."""

        circle = index_of(COMPOSE_CIRCLE, element.get("circleType", "SHAPE_CIRCLE"), -1)
        kind = index_of(COMPOSE_TYPE, element.get("composeType", "SPREAD"), -1)
        size = _int(element, "charSz")
        shapes = [_int(item, "prIDRef", ct.NO_CHAR_SHAPE) & 0xFFFFFFFF for item in element.findall(f"{{{_HP}}}charPr")]
        glyph = COMPOSE_FRAME_GLYPH.get(circle)
        if glyph is None or kind < 0 or not -128 <= size <= 127 or len(shapes) > 255:
            self.unsupported["compose"] += 1
            return None
        text = element.get("composeText", "")
        if circle != 0 or len(text) == 1:
            text = glyph + text
        value = ct.Compose(text, circle, size, kind, shapes)
        return [rec.Record(rec.CTRL_HEADER, level, value.encode())]

    def equation(self, element: etree._Element, level: int) -> list[rec.Record]:
        common = _object_common("eqed", element)
        comment = _find(element, "shapeComment")
        common.description = "".join(comment.itertext()) if comment is not None else ""
        script = _find(element, "script")
        equation = ct.EquationEdit(
            1 if element.get("lineMode") == "LINE" else 0,
            "".join(script.itertext()) if script is not None else "",
            _int(element, "baseUnit", 1000),
            colorref(element.get("textColor", "#000000")),
            _i32(_int(element, "baseLine")),
            element.get("version") or ct.EQUATION_VERSION,
            element.get("font") or ct.EQUATION_FONT,
        )
        return [rec.Record(rec.CTRL_HEADER, level, common.encode()), rec.Record(rec.EQEDIT, level + 1, equation.encode())]

    # drawing objects -----------------------------------------------------------------

    def drawing(self, element: etree._Element, level: int) -> list[rec.Record]:
        """A drawing object: the object header, its parameter sets and caption,
        then the shape component and what hangs under it."""

        common = _object_common("gso ", element)
        comment = _find(element, "shapeComment")
        common.description = "".join(comment.itertext()) if comment is not None else ""
        out = [rec.Record(rec.CTRL_HEADER, level, common.encode())]
        sets = [ct.ParameterSet(_int(p, "name") & 0xFFFF, _parameter_items(p)) for p in element.findall(f"{{{_HP}}}parameterset")]
        dropcap = index_of(DROPCAP, element.get("dropcapstyle"), 0)
        if dropcap and not any(isinstance(ps.find(*DROPCAP_PATH), int) for ps in sets):
            value = ct.ParameterSet(DROPCAP_PATH[0], [ct.ParameterItem(DROPCAP_PATH[1], 9, dropcap)])
            sets.append(ct.ParameterSet(0x021B, [ct.ParameterItem(DROPCAP_PATH[0], ct.PIT_SET, value)]))
        out += [rec.Record(rec.CTRL_DATA, level + 1, ps.encode()) for ps in sets]
        caption = _find(element, "caption")
        if caption is not None:
            out.extend(self.caption(caption, level + 1))
        out.extend(self.shape_records(element, level + 1, top=True))
        return out

    def shape_records(self, element: etree._Element, level: int, *, top: bool) -> list[rec.Record]:
        kind = _SHAPE_KINDS[_local(element)]
        offset, org, cur = _find(element, "offset"), _find(element, "orgSz"), _find(element, "curSz")
        flip, rotation, info = _find(element, "flip"), _find(element, "rotationInfo"), _find(element, "renderingInfo")
        draw_text = _find(element, "drawText")
        org_width, org_height = _int(org, "width"), _int(org, "height")
        flags = _flag(flip, "horizontal") | _flag(flip, "vertical") << 1
        flags |= ROTATE_IMAGE if _flag(rotation, "rotateimage") else 0
        flags |= _FLAG_TEXT_BOX if draw_text is not None else 0
        flags |= _FLAG_PICTURE if kind == "$pic" else 0
        flags |= _FLAG_GROUP if kind == "$con" or not top else 0
        flags |= _FLAG_GROUP_MEMBER if not top and kind != "$con" else 0
        matrices: list[sh.Matrix] = []
        for matrix in info if info is not None else ():
            values = [_matrix_value(matrix.get(f"e{i}")) for i in range(1, 7)]
            matrices.append((values[0], values[1], values[2], values[3], values[4], values[5]))
        if not matrices or len(matrices) % 2 == 0:
            matrices = [_IDENTITY, _IDENTITY, _IDENTITY]
        children: list[rec.Record] = []
        href = element.get("href", "")
        if href:
            # The component keeps the link with its colons escaped.
            link = ct.ParameterSet(HYPERLINK_PATH[0], [ct.ParameterItem(HYPERLINK_PATH[1], ct.PIT_BSTR, href.replace(":", chr(92) + ":"))])
            ps = ct.ParameterSet(0x021B, [ct.ParameterItem(HYPERLINK_PATH[0], ct.PIT_SET, link)])
            children.append(rec.Record(rec.CTRL_DATA, level + 1, ps.encode()))
        if kind == "$con":
            # Any other child is a shape the writer cannot write yet: refuse it
            # rather than leave it out of the container.
            for child in element:
                name = _local(child)
                if name not in _SHAPE_KINDS and name not in _CONTAINER_PARTS:
                    self.unsupported[name] += 1
            shapes = [child for child in element if _local(child) in _SHAPE_KINDS]
            kinds = [_SHAPE_KINDS[_local(child)] for child in shapes]
            rest = sh.ContainerChildren(kinds, _int(element, "instid") & 0xFFFFFFFF).encode()
            for child in shapes:
                children.extend(self.shape_records(child, level + 1, top=False))
        elif kind == "$pic":
            rest = b""
            children.append(rec.Record(rec.SHAPE_COMPONENT_PICTURE, level + 1, self.picture(element)))
        else:
            rest = self.drawing_style(element).encode()
            if draw_text is not None:
                children.extend(self.text_box(draw_text, level + 1))
            children.append(rec.Record(sh.GEOMETRY_TAGS[kind], level + 1, self.geometry(kind, element)))
        component = sh.ShapeComponent(
            kind,
            top,
            _i32(_int(offset, "x")),
            _i32(_int(offset, "y")),
            _int(element, "groupLevel") & 0xFFFF,
            1,
            org_width,
            org_height,
            _int(cur, "width") or org_width,
            _int(cur, "height") or org_height,
            flags,
            _i16(_int(rotation, "angle")),
            _i32(_int(rotation, "centerX")),
            _i32(_int(rotation, "centerY")),
            matrices,
            rest,
        )
        return [rec.Record(rec.SHAPE_COMPONENT, level, component.encode()), *children]

    @staticmethod
    def _line_props(line: etree._Element | None) -> int:
        if line is None:
            return 0
        props = index_of(LINE_STYLE, line.get("style"), 0)
        props |= index_of(END_CAP, line.get("endCap"), 0) << 6
        props |= index_of(ARROW, line.get("headStyle"), 0) << 10
        props |= index_of(ARROW, line.get("tailStyle"), 0) << 16
        props |= index_of(ARROW_SIZE, line.get("headSz"), 0) << 22
        props |= index_of(ARROW_SIZE, line.get("tailSz"), 0) << 26
        return props | _flag(line, "headfill") << 30 | _flag(line, "tailfill") << 31

    def drawing_style(self, element: etree._Element) -> sh.DrawingStyle:
        line, shadow = _find(element, "lineShape"), _find(element, "shadow")
        return sh.DrawingStyle(
            colorref(line.get("color")) if line is not None else 0,
            _i32(_int(line, "width")),
            self._line_props(line),
            index_of(OUTLINE_STYLE, line.get("outlineStyle") if line is not None else None, 0),
            fill_from_brush(element.find(f"{{{_HC}}}fillBrush")),
            index_of(SHADOW, shadow.get("type") if shadow is not None else None, 0),
            colorref(shadow.get("color")) if shadow is not None else 0xB2B2B2,
            _i32(_int(shadow, "offsetX")),
            _i32(_int(shadow, "offsetY")),
            _int(element, "instid") & 0xFFFFFFFF,
            _int(line, "alpha") & 0xFF,
            _int(shadow, "alpha") & 0xFF,
        )

    def text_box(self, draw_text: etree._Element, level: int) -> list[rec.Record]:
        sub_list = _find(draw_text, "subList")
        paragraphs = [p for p in sub_list if _local(p) == "p"] if sub_list is not None else []
        if not paragraphs:
            paragraphs = [etree.Element(f"{{{_HP}}}p")]
        margin = _find(draw_text, "textMargin")
        name = draw_text.get("name", "")
        box = sh.TextBox(
            len(paragraphs),
            _list_props(sub_list),
            0,
            (_int(margin, "left", 283), _int(margin, "right", 283), _int(margin, "top", 283), _int(margin, "bottom", 283)),
            _int(draw_text, "lastWidth"),
            bytes(8),
            _flag(draw_text, "editable"),
            name or None,
            b"" if name else bytes(1),
        )
        return [rec.Record(rec.LIST_HEADER, level, box.encode()), *self.paragraph_list(paragraphs, level)]

    @staticmethod
    def _point(element: etree._Element, name: str) -> sh.Point:
        point = element.find(f"{{{_HC}}}{name}")
        return _i32(_int(point, "x")), _i32(_int(point, "y"))

    def geometry(self, kind: str, element: etree._Element) -> bytes:
        if kind == "$rec":
            corners = [self._point(element, f"pt{i}") for i in range(4)]
            return sh.Rectangle(_int(element, "ratio") & 0xFF, corners).encode()
        if kind == "$ell":
            props = _flag(element, "intervalDirty") | _flag(element, "hasArcPr") << 1
            props |= index_of(ARC_TYPE, element.get("arcType"), 0) << 2
            return sh.Ellipse(props, [self._point(element, name) for name in ELLIPSE_POINTS]).encode()
        if kind == "$arc":
            points = [self._point(element, name) for name in ELLIPSE_POINTS[:3]]
            return sh.Arc(index_of(ARC_TYPE, element.get("type"), 0), points).encode()
        if kind == "$pol":
            points = [(_i32(_int(p, "x")), _i32(_int(p, "y"))) for p in element.findall(f"{{{_HC}}}pt")]
            return sh.Polygon(points, bytes(4)).encode()
        start, end = self._point(element, "startPt"), self._point(element, "endPt")
        return sh.Line(start, end, _flag(element, "isReverseHV")).encode()

    def picture(self, element: etree._Element) -> bytes:
        image, line = element.find(f"{{{_HC}}}img"), _find(element, "lineShape")
        corners_parent = _find(element, "imgRect")
        clip, margin, dim = _find(element, "imgClip"), _find(element, "inMargin"), _find(element, "imgDim")
        effects = _find(element, "effects")
        if effects is not None and len(effects):
            self.unsupported["pic/effects"] += 1
        ref = image.get("binaryItemIDRef", "") if image is not None else ""
        if ref and ref not in self.bin_ids:
            self.unsupported["pic/missing-image"] += 1
        corners = [self._point(corners_parent, f"pt{i}") if corners_parent is not None else (0, 0) for i in range(4)]
        return sh.Picture(
            colorref(line.get("color")) if line is not None else 0,
            _i32(_int(line, "width")),
            self._line_props(line),
            corners,
            (_int(clip, "left"), _int(clip, "top"), _int(clip, "right"), _int(clip, "bottom")),
            (_int(margin, "left"), _int(margin, "right"), _int(margin, "top"), _int(margin, "bottom")),
            max(-128, min(127, _int(image, "bright"))),
            max(-128, min(127, _int(image, "contrast"))),
            index_of(IMAGE_EFFECT, image.get("effect") if image is not None else None, 0),
            self.bin_ids.get(ref, 0),
            _int(image, "alpha") & 0xFF,
            _int(element, "instid") & 0xFFFFFFFF,
            0,
            (_int(dim, "dimwidth"), _int(dim, "dimheight")),
            bytes(1),
        ).encode()

    # fields --------------------------------------------------------------------------

    def field_begin(self, element: etree._Element, level: int) -> tuple[str, list[rec.Record]] | None:
        """The text id and records of a field start; None when the field is refused."""

        kind = element.get("type", "")
        begin_id = element.get("id", "")
        text_id = _FIELD_TEXT_ID.get(kind)
        memo = kind == "MEMO"
        sub_list = _find(element, "subList")
        # Fields of unknown kinds, and a paragraph list on anything but a memo,
        # are not written yet.
        if text_id is None or (sub_list is not None and not memo):
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
        z_order = max(_int(element, "zorder", -1), 0)
        command = params.get("Command")
        if memo:
            # A memo's number is its z-order; its body goes to the document's end.
            z_order = z_order or max(_number(params.get("Number")), 1)
            if command is None:
                command = _memo_command(z_order, params)
            self.memo_bodies.append((z_order, sub_list))
        value = ct.FieldCtrl(
            "%unk" if kind in _FIELD_HEAD_UNKNOWN else text_id,
            props,
            extra,
            command or "",
            instance_id,
            z_order,
        )
        records = [rec.Record(rec.CTRL_HEADER, level, value.encode())]
        name = element.get("name", "")
        if name or kind == "CLICK_HERE":
            records.append(rec.Record(rec.CTRL_DATA, level + 1, ct.name_parameter_set(name)))
        # The field end repeats the field's text id with the property byte, and
        # whether the field is editable.
        end_id = (bt.ctrl_word(text_id) & 0xFFFFFF) | extra << 24
        number = z_order if memo else 0
        self.open_fields.append((begin_id, struct.pack("<HIIIH", 4, end_id, props & 1, number, 4)))
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
        # Without ``flag`` the note repeats the number format and superscript
        # flag of the auto number inside it.
        number_format = next(element.iter(f"{{{_HP}}}autoNumFormat"), None)
        shape = index_of(NUMBER_FORMAT, number_format.get("type") if number_format is not None else None, 0) & 0xFF
        shape |= _flag(number_format, "supscript") << 8
        value = ct.NoteCtrl(
            "fn  " if kind == "footNote" else "en  ",
            _int(element, "number", 1),
            _char_code(element, "prefixChar", 0),
            _char_code(element, "suffixChar", ord(")")),
            _int(element, "flag", shape) & 0xFFFFFFFF,
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


def build_section_records(
    root: etree._Element, bin_ids: dict[str, int] | None = None
) -> tuple[list[rec.Record], Counter[str]]:
    """Records of one ``hs:sec`` and the counts of elements that could not be
    written; ``bin_ids`` maps binary item ids to their BinData ids."""

    writer = SectionRecords(bin_ids)
    return writer.section(root), writer.unsupported
