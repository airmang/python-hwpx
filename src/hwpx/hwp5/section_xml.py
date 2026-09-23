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
from . import shapes as sh
from .errors import Hwp5Error, damaged
from .header_xml import IMAGE_EFFECT, fill_brush
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
            ("showLineNumber", flag(props & (1 << 24))),
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

#: Field kinds by the control id the paragraph text carries.
FIELD_TYPES = {
    "%clk": "CLICK_HERE",
    "%hlk": "HYPERLINK",
    "%fmu": "FORMULA",
    "%bmk": "BOOKMARK",
    "%dte": "DATE",
    "%ddt": "DOC_DATE",
    "%pat": "PATH",
    "%toc": "TABLEOFCONTENTS",
    "%mmg": "MAILMERGE",
    "%xrf": "CROSSREF",
    "%sum": "SUMMARY",
    "%usr": "USER_INFO",
    "%%me": "MEMO",
    "%%*d": "PROOFREADING_MARKS_DELETE",
    "%sig": "PROOFREADING_MARKS_SIGN",
    "%unk": "UNKNOWN",
}


def _command_values(command: str) -> dict[str, str]:
    """``Name:type:length:value`` entries of a ``Kind:set:<n>:`` command string."""

    parts = command.split(":", 3)
    if len(parts) < 4 or parts[1] != "set":
        return {}
    rest = parts[3]
    values: dict[str, str] = {}
    while rest:
        fields = rest.split(":", 2)
        if len(fields) < 3:
            break
        key, kind, tail = fields
        if kind == "wstring":
            length_text, _, tail = tail.partition(":")
            if not length_text.isdigit():
                break
            length = int(length_text)
            values[key.strip()] = tail[:length]
            rest = tail[length:].lstrip(" ")
        else:
            value, _, rest = tail.partition(" ")
            values[key.strip()] = value
    return values


_HYPERLINK_KIND = ("HWPHYPERLINK_TYPE_HWP", "HWPHYPERLINK_TYPE_URL", "HWPHYPERLINK_TYPE_EMAIL")


def _split_escaped(command: str) -> list[str]:
    """Split on ``;`` that is not backslash-escaped, and unescape each part."""

    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in command:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ";":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _hyperlink_parameters(command: str) -> list[tuple[str, str, str]]:
    """``Path``, ``Category``, ``TargetType`` and ``DocOpenType`` of a hyperlink
    command ``target;kind;outline;new-tab;``."""

    parts = _split_escaped(command) if command else [""]
    fields = parts[1:] + ["", "", ""]
    kind = int(fields[0]) if fields[0].isdigit() else 0
    params: list[tuple[str, str, str]] = []
    if kind in (1, 2):
        params.append(("stringParam", "Path", parts[0]))
    params += [
        ("stringParam", "Category", _HYPERLINK_KIND[kind] if kind < len(_HYPERLINK_KIND) else _HYPERLINK_KIND[0]),
        (
            "stringParam",
            "TargetType",
            "HWPHYPERLINK_TARGET_OUTLINE" if fields[1] == "1" else "HWPHYPERLINK_TARGET_BOOKMARK",
        ),
        (
            "stringParam",
            "DocOpenType",
            "HWPHYPERLINK_JUMP_NEWTAB" if fields[2] == "1" else "HWPHYPERLINK_JUMP_CURRENTTAB",
        ),
    ]
    return params


def field_parameters(text_id: str, field: ct.FieldCtrl) -> list[tuple[str, str, str]]:
    """``hp:parameters`` items for a field: ``Prop`` and ``Command``, then what
    Hancom spells out of the command for the kinds that have it."""

    params = [("integerParam", "Prop", str(field.extra))]
    if field.command:
        params.append(("stringParam", "Command", field.command))
    if text_id == "%clk":
        values = _command_values(field.command)
        if "Direction" in values:
            params.append(("stringParam", "Direction", values["Direction"]))
        if values.get("HelpState"):
            params.append(("stringParam", "HelpState", values["HelpState"]))
    elif text_id == "%hlk":
        params += _hyperlink_parameters(field.command)
    elif text_id == "%pat":
        params.append(("stringParam", "Format", field.command))
    elif text_id == "%fmu" and "??" in field.command:
        formula, _, rest = field.command.partition("??")
        result_format, _, last = rest.partition(";;")
        params += [
            ("stringParam", "Formula", formula),
            ("stringParam", "ResultFormat", result_format),
            ("stringParam", "LastResult", last),
        ]
    return params


CAPTION_SIDE = ("LEFT", "RIGHT", "TOP", "BOTTOM")
CHAR_ELEMENTS = {10: "hp:lineBreak", 24: "hp:hyphen", 30: "hp:nbSpace", 31: "hp:fwSpace"}
#: The range tag kind of a highlighter (markpen) range; its low 24 bits are the color.
RANGE_MARKPEN = 2
#: ``hp:label`` orientation by the label set's ``landscape`` value.
LABEL_LANDSCAPE = ("WIDELY", "NARROWLY")
PAGE_NUM_POS = (
    "NONE",
    "TOP_LEFT",
    "TOP_CENTER",
    "TOP_RIGHT",
    "BOTTOM_LEFT",
    "BOTTOM_CENTER",
    "BOTTOM_RIGHT",
    "OUTSIDE_TOP",
    "OUTSIDE_BOTTOM",
    "INSIDE_TOP",
    "INSIDE_BOTTOM",
)
NUMBER_TYPE = ("PAGE", "FOOTNOTE", "ENDNOTE", "PICTURE", "TABLE", "EQUATION", "TOTAL_PAGE")
PAGE_HIDING = ("hideHeader", "hideFooter", "hideMasterPage", "hideBorder", "hideFill", "hidePageNum")
DUTMAL_POS = ("TOP", "BOTTOM", "CENTER")
DUTMAL_ALIGN = ("JUSTIFY", "LEFT", "RIGHT", "CENTER", "DISTRIBUTE", "DISTRIBUTE_SPACE")
#: Controls written as one element inside ``hp:ctrl``.
MARKERS = {
    "pgnp": "pageNum",
    "pghd": "pageHiding",
    "nwno": "newNum",
    "atno": "autoNum",
    "bokm": "bookmark",
    "idxm": "indexmark",
}


LINE_STYLE = (
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
)
END_CAP = ("ROUND", "FLAT")
ARROW = (
    "NORMAL",
    "ARROW",
    "SPEAR",
    "CONCAVE_ARROW",
    "EMPTY_DIAMOND",
    "EMPTY_CIRCLE",
    "EMPTY_BOX",
    "FILLED_DIAMOND",
    "FILLED_CIRCLE",
    "FILLED_BOX",
)
ARROW_SIZE = (
    "SMALL_SMALL",
    "SMALL_MEDIUM",
    "SMALL_LARGE",
    "MEDIUM_SMALL",
    "MEDIUM_MEDIUM",
    "MEDIUM_LARGE",
    "LARGE_SMALL",
    "LARGE_MEDIUM",
    "LARGE_LARGE",
)
OUTLINE_STYLE = ("NORMAL", "OUTER", "INNER")
#: Shadow kinds, spelled as Hancom writes them.
SHADOW = (
    "NONE",
    "PARELLEL_LEFTTOP",
    "PARELLEL_RIGHTTOP",
    "PARELLEL_LEFTBOTTOM",
    "PARELLEL_RIGHTBOTTOM",
    "SHEAR_LEFTTOP",
    "SHEAR_RIGHTTOP",
    "SHEAR_LEFTBOTTOM",
    "SHEAR_RIGHTBOTTOM",
    "PERS_LEFTTOP",
    "PERS_RIGHTTOP",
    "PERS_LEFTBOTTOM",
    "PERS_RIGHTBOTTOM",
    "SCALE_NARROW",
    "SCALE_ENLARGE",
)
ARC_TYPE = ("NORMAL", "PIE", "CHORD")
DROPCAP = ("None", "DoubleLine", "TripleLine", "Margin")
#: Item paths in a shape's parameter sets: the first-letter decoration kind
#: (object header) and the hyperlink (shape component).
DROPCAP_PATH = (0x3003, 0x7001)
HYPERLINK_PATH = (0x026F, 0x0265)
ELLIPSE_POINTS = ("center", "ax1", "ax2", "start1", "end1", "start2", "end2")
#: Flags bit of a shape component that becomes ``rotateimage``.
ROTATE_IMAGE = 1 << 19


def matrix_number(value: float) -> str:
    """A matrix entry the way Hancom prints it: six decimals without trailing
    zeros, ``0`` for negative zero and ``-nan(ind)`` for NaN."""

    if value != value:
        return "-nan(ind)"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _unescape(text: str) -> str:
    """Drop the backslashes that escape characters in a hyperlink command."""

    out: list[str] = []
    escaped = False
    for char in text:
        if char == "\\" and not escaped:
            escaped = True
            continue
        out.append(char)
        escaped = False
    return "".join(out)


def parameter_set(parent: etree._Element, ps: ct.ParameterSet) -> etree._Element:
    """``hp:parameterset`` with its items; a nested set is an ``hp:listParam``."""

    element = sub(parent, "hp:parameterset", (("cnt", len(ps.items)), ("name", ps.set_id)))
    _parameter_items(element, ps.items)
    return element


def _parameter_items(parent: etree._Element, items: list[ct.ParameterItem]) -> None:
    for item in items:
        if isinstance(item.value, ct.ParameterSet):
            nested = sub(parent, "hp:listParam", (("cnt", len(item.value.items)), ("name", item.item_id)))
            _parameter_items(nested, item.value.items)
        elif isinstance(item.value, str):
            sub(parent, "hp:stringParam", (("name", item.item_id),)).text = xml_text(item.value)
        elif item.kind in ct.PIT_UNSIGNED:
            sub(parent, "hp:unsignedintegerParam", (("name", item.item_id),)).text = str(item.value)
        else:
            sub(parent, "hp:integerParam", (("name", item.item_id),)).text = str(item.value)


def _char(value: int) -> str:
    """A character code as text; nothing for 0 or a value that is not a character."""

    return chr(value) if 0 < value < 0xD800 or 0xE000 <= value < 0x110000 else ""


def _is_open(run: etree._Element, text: etree._Element | None) -> bool:
    """Whether *text* is the run's last child, so more text can go into it."""

    return text is not None and len(run) > 0 and run[-1] is text


def _place_marks(parent: etree._Element, marks: list[tuple[int, int, str]], pending: int, position: int) -> int:
    """Append the marks due at *position* to *parent*; return the next pending mark."""

    while pending < len(marks) and marks[pending][0] <= position:
        colour = marks[pending][2]
        if colour:
            sub(parent, "hp:markpenBegin", (("color", colour),))
        else:
            sub(parent, "hp:markpenEnd")
        pending += 1
    return pending


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
        # Fields opened by a field-start control and not yet closed: (id, fieldid).
        self.open_fields: list[tuple[int, int]] = []

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
        self.runs(element, para, self.marks(record))
        # Lists hung on the paragraph itself: a memo body after MEMO_LIST, or
        # (on a section's last paragraph) a master page. Not converted yet.
        memo = False
        for child in record.children:
            if child.tag == rec.MEMO_LIST:
                memo = True
            elif child.tag == rec.LIST_HEADER:
                self.report.skip("memo-body" if memo else "master-page")
                memo = False
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

    def marks(self, record: rec.Record) -> list[tuple[int, int, str]]:
        """Highlighter starts and ends from the paragraph's range tags, in text
        order: (position, order, color), where an end has no color."""

        events: list[tuple[int, int, str]] = []
        for child in record.children:
            if child.tag != rec.PARA_RANGE_TAG:
                continue
            for offset in range(0, len(child.payload) - 11, 12):
                start, end, tag = struct.unpack_from("<III", child.payload, offset)
                kind = tag >> 24
                if kind == RANGE_MARKPEN:
                    events.append((start, 1, color(tag & 0xFFFFFF)))
                    events.append((end, 2 if end == start else 0, ""))
                elif kind in (0, 1):
                    self.report.drop(f"range-tag-{kind}")
                else:
                    self.report.skip(f"range-tag-{kind}")
        events.sort(key=lambda event: (event[0], event[1]))
        return events

    def runs(self, element: etree._Element, para: bt.Paragraph, marks: list[tuple[int, int, str]]) -> None:
        shapes = para.char_shapes or [(0, 0)]
        bounds = [start for start, _ in shapes[1:]] + [1 << 31]
        controls = iter(para.controls)
        chunks = list(para.chunks)
        index = 0
        pending = 0  # the next highlighter mark to place
        last: etree._Element | None = None
        run: etree._Element | None = None
        text: etree._Element | None = None
        for (_start, shape_id), end in zip(shapes, bounds):
            run = sub(element, "hp:run", (("charPrIDRef", shape_id),))
            text = None
            last = None
            while index < len(chunks) and chunks[index].position < end:
                chunk = chunks[index]
                if pending < len(marks) and marks[pending][0] <= chunk.position:
                    # A mark goes into the open text node, into a new one when
                    # text follows, or straight into the run before a control.
                    if not _is_open(run, text) and (
                        chunk.kind in ("text", "char") or (chunk.kind == "inline" and chunk.code == bt.TAB)
                    ):
                        text = self._text(run, text, "")
                    target = text if text is not None and _is_open(run, text) else run
                    pending = _place_marks(target, marks, pending, chunk.position)
                    if target is text:
                        last = text
                if chunk.kind == "text":
                    limit = end
                    if pending < len(marks) and chunk.position < marks[pending][0] < limit:
                        limit = marks[pending][0]
                    split = limit - chunk.position
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
                        text = None
                        last = self.field_end(run)
                    else:
                        self.report.skip(f"inline-{chunk.code}")
                else:
                    ctrl = next(controls, None)
                    text = None
                    if ctrl is None:
                        self.report.skip("control-without-record")
                        continue
                    last = self.control(run, ctrl, chunk.control_id)
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
            # A mark where the run ends stays in the run while its text node is open.
            if text is not None and _is_open(run, text):
                pending = _place_marks(text, marks, pending, end)
        if run is not None and pending < len(marks):
            text = self._text(run, text, "")
            _place_marks(text, marks, pending, 1 << 31)
            last = text
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

    def control(self, run: etree._Element, ctrl: rec.Record, text_id: str | None = None) -> etree._Element | None:
        kind = bt.record_ctrl_id(ctrl) or "?"
        if kind.startswith("%"):
            return self.field_begin(run, ctrl, text_id or kind)
        if kind == "secd":
            # Master pages may hang on the section definition as paragraph
            # lists; its parameter set holds the presentation settings.
            for child in ctrl.children:
                if child.tag == rec.LIST_HEADER:
                    self.report.skip("master-page")
                elif child.tag == rec.CTRL_DATA:
                    self.report.skip("presentation")
            return section_properties(run, ctrl)
        if kind == "cold":
            return column_properties(run, ctrl)
        if kind == "tbl ":
            return self.table(run, ctrl)
        if kind in ("head", "foot"):
            return self.header_footer(run, ctrl, kind)
        if kind in ("fn  ", "en  "):
            return self.note(run, ctrl, kind)
        if kind in MARKERS:
            return self.marker(run, ctrl, kind)
        if kind == "tdut":
            return self.dutmal(run, ctrl)
        if kind == "gso ":
            return self.drawing(run, ctrl)
        self.report.skip(f"control-{kind.strip() or kind}")
        return None

    def marker(self, run: etree._Element, ctrl: rec.Record, kind: str) -> etree._Element:
        """Page number place, page hiding, numbering, bookmark and index mark
        controls: one element in an ``hp:ctrl``."""

        wrapper = sub(run, "hp:ctrl")
        if kind == "pgnp":
            pn = ct.PageNumberPosition.decode(ctrl.payload)
            sub(
                wrapper,
                "hp:pageNum",
                (
                    ("pos", token(PAGE_NUM_POS, _bits(pn.props, 8, 4))),
                    ("formatType", token(NUMBER_FORMAT, _bits(pn.props, 0, 8), "DIGIT")),
                    ("sideChar", _char(pn.side_char)),
                ),
            )
        elif kind == "pghd":
            hiding = ct.PageHiding.decode(ctrl.payload).props
            sub(wrapper, "hp:pageHiding", [(name, flag(hiding & (1 << bit))) for bit, name in enumerate(PAGE_HIDING)])
        elif kind == "nwno":
            nn = ct.NewNumber.decode(ctrl.payload)
            sub(wrapper, "hp:newNum", (("num", nn.number), ("numType", token(NUMBER_TYPE, _bits(nn.props, 0, 4)))))
        elif kind == "atno":
            an = ct.AutoNumber.decode(ctrl.payload)
            element = sub(wrapper, "hp:autoNum", (("num", an.number), ("numType", token(NUMBER_TYPE, _bits(an.props, 0, 4)))))
            sub(
                element,
                "hp:autoNumFormat",
                (
                    ("type", token(NUMBER_FORMAT, _bits(an.props, 4, 8), "DIGIT")),
                    ("userChar", _char(an.user_char)),
                    ("prefixChar", _char(an.prefix_char)),
                    ("suffixChar", _char(an.suffix_char)),
                    ("supscript", flag(an.props & (1 << 12))),
                ),
            )
        elif kind == "bokm":
            name = next((ct.parameter_set_name(c.payload) for c in ctrl.children if c.tag == rec.CTRL_DATA), "")
            sub(wrapper, "hp:bookmark", (("name", name),))
        else:
            mark = ct.IndexMark.decode(ctrl.payload)
            element = sub(wrapper, "hp:indexmark")
            sub(element, "hp:firstKey").text = xml_text(mark.first)
            if mark.second:
                sub(element, "hp:secondKey").text = xml_text(mark.second)
        return wrapper

    def dutmal(self, run: etree._Element, ctrl: rec.Record) -> etree._Element:
        """``hp:dutmal``: text with a smaller text set above or below it."""

        d = ct.Dutmal.decode(ctrl.payload)
        element = sub(
            run,
            "hp:dutmal",
            (
                ("posType", token(DUTMAL_POS, d.position)),
                ("szRatio", d.size_ratio),
                ("option", d.option),
                ("styleIDRef", d.style_id),
                ("align", token(DUTMAL_ALIGN, d.align)),
            ),
        )
        sub(element, "hp:mainText").text = xml_text(d.main_text)
        sub(element, "hp:subText").text = xml_text(d.sub_text)
        return element

    # drawing objects -----------------------------------------------------------------

    def drawing(self, run: etree._Element, ctrl: rec.Record) -> etree._Element | None:
        """A drawing object; shapes this module does not convert are reported."""

        component = next((c for c in ctrl.children if c.tag == rec.SHAPE_COMPONENT), None)
        if component is None or len(component.payload) < 4:
            self.report.skip("control-gso")
            return None
        kind = bt.ctrl_id(struct.unpack_from("<I", component.payload)[0])
        if kind not in sh.SHAPE_ELEMENTS:
            self.report.skip(f"shape-{kind.strip('$') or kind}")
            return None
        sets: list[ct.ParameterSet] = []
        for child in ctrl.children:
            if child.tag == rec.CTRL_DATA:
                ps = ct.ParameterSet.decode(child.payload)
                if ps is None:
                    self.report.skip("shape-data")
                else:
                    sets.append(ps)
        # Build detached so a damaged component leaves nothing half written.
        holder = etree.Element("holder")
        try:
            element = self.shape(holder, component, ct.ObjectCommon.decode(ctrl.payload))
            for ps in sets:
                dropcap = ps.find(*DROPCAP_PATH)
                if isinstance(dropcap, int):
                    element.set("dropcapstyle", token(DROPCAP, dropcap))
            # A caption is the paragraph list of the object header itself.
            for header, paragraphs in lists(ctrl)[:1]:
                self.caption(element, header, paragraphs)
            for ps in sets:
                parameter_set(element, ps)
        except Hwp5Error:
            self.report.skip(f"shape-{kind.strip('$')}-damaged")
            return None
        run.append(element)
        return element

    def shape(self, parent: etree._Element, record: rec.Record, common: ct.ObjectCommon | None) -> etree._Element:
        """One shape from its component record: ``common`` is the object header
        of a top-level shape and None for a shape inside a container."""

        sc = sh.ShapeComponent.decode(record.payload, top=common is not None)
        name = sh.SHAPE_ELEMENTS.get(sc.kind)
        if name is None:
            raise damaged(f"unexpected shape kind {sc.kind!r}")
        if common is not None:
            attrs = object_attrs(common)
        else:
            attrs = [
                ("id", 0),
                ("zOrder", 0),
                ("numberingType", "NONE"),
                ("textWrap", "TOP_AND_BOTTOM"),
                ("textFlow", "BOTH_SIDES"),
                ("lock", 0),
                ("dropcapstyle", "None"),
            ]
        tag = sh.GEOMETRY_TAGS.get(sc.kind)
        geometry = next((c for c in record.children if c.tag == tag), None)
        href = ""
        for child in record.children:
            if child.tag == rec.CTRL_DATA:
                ps = ct.ParameterSet.decode(child.payload)
                link = ps.find(*HYPERLINK_PATH) if ps is not None else None
                if isinstance(link, str):
                    href = _unescape(link)
                else:
                    self.report.skip("shape-data")
        style: sh.DrawingStyle | None = None
        picture: sh.Picture | None = None
        if sc.kind == "$con":
            instance_id = sh.ContainerChildren.decode(sc.rest).instance_id
        elif sc.kind == "$pic":
            picture = sh.Picture.decode(geometry.payload) if geometry is not None else sh.Picture()
            instance_id = picture.instance_id or 0
        else:
            style = sh.DrawingStyle.decode(sc.rest)
            instance_id = style.instance_id
        attrs += [("href", href), ("groupLevel", sc.group_level), ("instid", instance_id)]
        attrs += self.shape_attrs(sc.kind, geometry)
        element = sub(parent, f"hp:{name}", attrs)
        self.shape_placement(element, sc)
        if picture is not None:
            self.picture(element, picture)
        if sc.kind == "$con":
            for child in record.children:
                if child.tag != rec.SHAPE_COMPONENT or len(child.payload) < 4:
                    continue
                child_kind = bt.ctrl_id(struct.unpack_from("<I", child.payload)[0])
                if child_kind in sh.SHAPE_ELEMENTS:
                    self.shape(element, child, None)
                else:
                    self.report.skip(f"shape-{child_kind.strip('$') or child_kind}")
        elif style is not None:
            self.shape_style(element, style)
            for header, paragraphs in lists(record)[:1]:
                self.text_box(element, header, paragraphs)
            self.shape_geometry(element, sc.kind, geometry)
        if common is not None:
            object_layout(element, common)
            if common.description:
                sub(element, "hp:shapeComment").text = xml_text(common.description)
        return element

    @staticmethod
    def shape_attrs(kind: str, geometry: rec.Record | None) -> list[tuple[str, object]]:
        if geometry is None:
            return []
        if kind == "$rec":
            return [("ratio", sh.Rectangle.decode(geometry.payload).ratio)]
        if kind == "$ell":
            props = sh.Ellipse.decode(geometry.payload).props
            return [
                ("intervalDirty", flag(props & 0x1)),
                ("hasArcPr", flag(props & 0x2)),
                ("arcType", token(ARC_TYPE, _bits(props, 2, 8))),
            ]
        if kind == "$arc":
            return [("type", token(ARC_TYPE, sh.Arc.decode(geometry.payload).kind))]
        if kind == "$lin":
            return [("isReverseHV", flag(sh.Line.decode(geometry.payload).reverse))]
        if kind == "$pic":
            return [("reverse", 0)]
        return []

    @staticmethod
    def shape_placement(element: etree._Element, sc: sh.ShapeComponent) -> None:
        """Offset in the group, sizes, flip, rotation and the transformation matrices."""

        sub(element, "hp:offset", (("x", _u32(sc.x)), ("y", _u32(sc.y))))
        sub(element, "hp:orgSz", (("width", sc.org_width), ("height", sc.org_height)))
        # Hancom writes 0 for a current size that equals the original one.
        width = 0 if sc.cur_width == sc.org_width else sc.cur_width
        height = 0 if sc.cur_height == sc.org_height else sc.cur_height
        sub(element, "hp:curSz", (("width", width), ("height", height)))
        sub(element, "hp:flip", (("horizontal", flag(sc.flags & 0x1)), ("vertical", flag(sc.flags & 0x2))))
        sub(
            element,
            "hp:rotationInfo",
            (
                ("angle", sc.angle),
                ("centerX", sc.center_x),
                ("centerY", sc.center_y),
                ("rotateimage", flag(sc.flags & ROTATE_IMAGE)),
            ),
        )
        info = sub(element, "hp:renderingInfo")
        for index, matrix in enumerate(sc.matrices):
            name = "hc:transMatrix" if index == 0 else ("hc:scaMatrix" if index % 2 else "hc:rotMatrix")
            sub(info, name, [(f"e{i + 1}", matrix_number(v)) for i, v in enumerate(matrix)])

    @staticmethod
    def line_shape(element: etree._Element, line_color: int, width: int, props: int, outline: int, alpha: int) -> None:
        sub(
            element,
            "hp:lineShape",
            (
                ("color", color(line_color)),
                ("width", _u32(width)),
                ("style", token(LINE_STYLE, _bits(props, 0, 6))),
                ("endCap", token(END_CAP, _bits(props, 6, 4))),
                ("headStyle", token(ARROW, _bits(props, 10, 6))),
                ("tailStyle", token(ARROW, _bits(props, 16, 6))),
                ("headfill", flag(props & (1 << 30))),
                ("tailfill", flag(props & (1 << 31))),
                ("headSz", token(ARROW_SIZE, _bits(props, 22, 4))),
                ("tailSz", token(ARROW_SIZE, _bits(props, 26, 4))),
                ("outlineStyle", token(OUTLINE_STYLE, outline)),
                ("alpha", alpha),
            ),
        )

    def picture(self, element: etree._Element, pic: sh.Picture) -> None:
        """The image, its border (when it has one), corners, crop box, margins and size."""

        sub(
            element,
            "hc:img",
            (
                ("binaryItemIDRef", f"image{pic.bin_id}" if pic.bin_id else ""),
                ("bright", pic.bright),
                ("contrast", pic.contrast),
                ("effect", token(IMAGE_EFFECT, pic.effect)),
                ("alpha", pic.alpha or 0),
            ),
        )
        if _bits(pic.line_props, 0, 6):
            self.line_shape(element, pic.line_color, pic.line_width, pic.line_props, 0, 0)
        corners = sub(element, "hp:imgRect")
        for index, (x, y) in enumerate(pic.corners):
            sub(corners, f"hc:pt{index}", (("x", x), ("y", y)))
        left, top, right, bottom = pic.crop
        sub(element, "hp:imgClip", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
        left, right, top, bottom = pic.margins
        sub(element, "hp:inMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))
        width, height = pic.dim or (0, 0)
        sub(element, "hp:imgDim", (("dimwidth", width), ("dimheight", height)))
        sub(element, "hp:effects")
        if pic.effects:
            self.report.skip("picture-effects")

    def shape_style(self, element: etree._Element, style: sh.DrawingStyle) -> None:
        self.line_shape(element, style.line_color, style.line_width, style.line_props, style.outline, style.line_alpha)
        fill_brush(element, style.fill)
        sub(
            element,
            "hp:shadow",
            (
                ("type", token(SHADOW, style.shadow_type)),
                ("color", color(style.shadow_color)),
                ("offsetX", style.shadow_x),
                ("offsetY", style.shadow_y),
                ("alpha", style.shadow_alpha),
            ),
        )

    def text_box(self, element: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        box = sh.TextBox.decode(header.payload)
        draw_text = sub(
            element,
            "hp:drawText",
            (("lastWidth", box.last_width), ("name", box.name or ""), ("editable", flag((box.editable or 0) & 0x1))),
        )
        sub_list = sub(draw_text, "hp:subList", list_attrs(box.props))
        self.paragraphs(sub_list, paragraphs)
        left, right, top, bottom = box.margins
        sub(draw_text, "hp:textMargin", (("left", left), ("right", right), ("top", top), ("bottom", bottom)))

    @staticmethod
    def shape_geometry(element: etree._Element, kind: str, geometry: rec.Record | None) -> None:
        if geometry is None:
            return
        points: list[tuple[str, tuple[int, int]]] = []
        if kind == "$rec":
            points = [(f"hc:pt{i}", p) for i, p in enumerate(sh.Rectangle.decode(geometry.payload).corners)]
        elif kind == "$ell":
            points = [(f"hc:{n}", p) for n, p in zip(ELLIPSE_POINTS, sh.Ellipse.decode(geometry.payload).points)]
        elif kind == "$arc":
            points = [(f"hc:{n}", p) for n, p in zip(ELLIPSE_POINTS, sh.Arc.decode(geometry.payload).points)]
        elif kind == "$pol":
            points = [("hc:pt", p) for p in sh.Polygon.decode(geometry.payload).points]
        elif kind == "$lin":
            line = sh.Line.decode(geometry.payload)
            points = [("hc:startPt", line.start), ("hc:endPt", line.end)]
        for name, (x, y) in points:
            sub(element, name, (("x", x), ("y", y)))

    # fields --------------------------------------------------------------------------

    def field_begin(self, run: etree._Element, ctrl: rec.Record, text_id: str) -> etree._Element:
        """``hp:fieldBegin`` from a field control; the kind comes from the text,
        which keeps it even where the control header says ``%unk``."""

        field_ctrl = ct.FieldCtrl.decode(ctrl.payload)
        name = ""
        for child in ctrl.children:
            if child.tag == rec.CTRL_DATA:
                name = ct.parameter_set_name(child.payload)
        field_id = bt.ctrl_word(text_id) if len(text_id) == 4 else bt.ctrl_word(field_ctrl.ctrl)
        wrapper = sub(run, "hp:ctrl")
        begin = sub(
            wrapper,
            "hp:fieldBegin",
            (
                ("id", field_ctrl.instance_id),
                ("type", FIELD_TYPES.get(text_id, "UNKNOWN")),
                ("name", name),
                ("editable", flag(field_ctrl.props & 0x1)),
                ("dirty", flag(field_ctrl.props & 0x8000)),
                ("zorder", field_ctrl.z_order if field_ctrl.z_order else -1),
                ("fieldid", field_id),
            ),
        )
        params = field_parameters(text_id, field_ctrl)
        container = sub(begin, "hp:parameters", (("cnt", len(params)), ("name", "")))
        for kind, key, value in params:
            item = sub(container, f"hp:{kind}", (("name", key),))
            item.text = xml_text(value)
            if value != value.strip():
                item.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        self.open_fields.append((field_ctrl.instance_id, field_id))
        return wrapper

    def field_end(self, run: etree._Element) -> etree._Element:
        begin_id, field_id = self.open_fields.pop() if self.open_fields else (0, 0)
        wrapper = sub(run, "hp:ctrl")
        sub(wrapper, "hp:fieldEnd", (("beginIDRef", begin_id), ("fieldid", field_id)))
        return wrapper

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
        # Hancom writes the note's characters as codes, and its number shape
        # word as ``flag`` when it is not zero.
        attrs: list[tuple[str, object]] = [("flag", nc.reserved)] if nc.reserved else []
        attrs.append(("number", nc.number))
        if nc.prefix_char:
            attrs.append(("prefixChar", nc.prefix_char))
        attrs += [("suffixChar", nc.suffix_char), ("instId", nc.instance_id)]
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
        for data in (r for r in ctrl.children if r.tag == rec.CTRL_DATA):
            if data.payload.startswith(ct.NAME_SET_PREFIX):
                # A table's name has no OWPML attribute; Hancom's HWPX leaves it out too.
                self.report.drop("table-name")
                continue
            items = ct.label_items(data.payload)
            values = ct.label_values(data.payload)
            if items is None or values is None:
                self.report.skip("table-data")
                continue
            for _ in range(len(items) - len(values)):
                self.report.drop("label-item")
            label: list[tuple[str, object]] = [(name, values.get(name, 0)) for name in ct.LABEL_ITEMS]
            label[8] = ("landscape", token(LABEL_LANDSCAPE, values.get("landscape", 0)))
            sub(table, "hp:label", label)
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
