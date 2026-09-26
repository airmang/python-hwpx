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
from datetime import datetime, timedelta

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import bodytext as bt
from . import controls as ct
from . import records as rec
from .header_xml import fill_brush
from .section_common import (
    ConversionReport,
    _bits,
    _u32,
    list_attrs,
    lists,
    object_attrs,
    object_layout,
)
from .shape_xml import ShapeReader
from .owpml import (
    BORDER_LINE,
    BORDER_WIDTH,
    NOTE_NUMBER_FORMAT,
    NS,
    NUMBER_FORMAT,
    color,
    flag,
    q,
    root,
    serialize,
    sub,
    token,
    xml_spaced,
    xml_text,
)


def _unit(raw: int) -> tuple[int, str]:
    return raw >> 1, "CHAR" if raw & 1 else "HWPUNIT"


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
#: Master pages kept under the section definition: the property bit that marks
#: each type, in the order their paragraph lists follow.
MASTER_PAGE_BITS = ((29, "BOTH"), (30, "EVEN"), (31, "ODD"))
#: The kind word (offset 18) of a master page list on a section's last
#: paragraph: this for the last page, plus the page number for an optional page.
MASTER_PAGE_LAST = 3
#: Presentation settings OWPML spells: the screen change effect and what the
#: settings apply to, by the codes met (0 for both).
PRESENTATION_EFFECT = {0: "none"}
PRESENTATION_APPLY_TO = {0: "WholeDoc"}


def presentation(parent: etree._Element, settings: ct.Presentation) -> bool:
    """``hp:presentation`` of a section; False, with nothing written, for an
    effect or target with no known name, a sound or an automatic show."""

    effect = PRESENTATION_EFFECT.get(settings.effect)
    apply_to = PRESENTATION_APPLY_TO.get(settings.apply_to)
    if effect is None or apply_to is None or settings.sound or settings.autoshow:
        return False
    element = sub(
        parent,
        "hp:presentation",
        (
            ("effect", effect),
            ("soundIDRef", ""),
            ("invertText", flag(settings.invert_text)),
            ("autoshow", 0),
            ("showtime", settings.show_time),
            ("applyto", apply_to),
        ),
    )
    fill_brush(element, settings.fill)
    return True


def _note_pr(parent: etree._Element, name: str, record: rec.Record | None, *, endnote: bool) -> None:
    element = sub(parent, name)
    note = ct.NoteShape.decode(record.payload if record is not None else b"")
    props = note.props
    sub(
        element,
        "hp:autoNumFormat",
        (
            ("type", NOTE_NUMBER_FORMAT.get(_bits(props, 0, 8), "DIGIT")),
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
            # Raised as the section's master pages are added (SectionWriter.master_page).
            ("masterPageCnt", 0),
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
    # The separator line comes first, then the width of each column.
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
    if cd.widths:
        # Width, gap, width, gap, ..., width: the last column has no gap.
        widths = [*cd.widths, 0] if len(cd.widths) % 2 else list(cd.widths)
        for index in range(0, len(widths) - 1, 2):
            sub(col, "hp:colSz", (("width", widths[index]), ("gap", widths[index + 1])))
    return wrapper


# -- the section writer -------------------------------------------------------------------

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
#: A hyperlink's target and how it opens, by the code in its command; any
#: other code reads as the first.
_HYPERLINK_TARGET = {
    "0": "HWPHYPERLINK_TARGET_BOOKMARK",
    "1": "HWPHYPERLINK_TARGET_OUTLINE",
    "2": "HWPHYPERLINK_TARGET_TABLE",
    "5": "HWPHYPERLINK_TARGET_HYPERLINK",
}
_HYPERLINK_JUMP = {
    "0": "HWPHYPERLINK_JUMP_CURRENTTAB",
    "1": "HWPHYPERLINK_JUMP_NEWTAB",
    "-1": "HWPHYPERLINK_JUMP_DONTCARE",
}


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
    """``Path``, ``Category``, ``TargetType``, ``DocOpenType`` and ``ToolTip``
    of a hyperlink command ``target|tooltip;kind;target type;open type;``."""

    parts = _split_escaped(command) if command else [""]
    fields = parts[1:] + ["", "", ""]
    kind = int(fields[0]) if fields[0].isdigit() else 0
    path, bar, tooltip = parts[0].partition("|")
    params: list[tuple[str, str, str]] = []
    if kind in (1, 2):
        params.append(("stringParam", "Path", path))
    params += [
        ("stringParam", "Category", _HYPERLINK_KIND[kind] if kind < len(_HYPERLINK_KIND) else _HYPERLINK_KIND[0]),
        ("stringParam", "TargetType", _HYPERLINK_TARGET.get(fields[1], _HYPERLINK_TARGET["0"])),
        ("stringParam", "DocOpenType", _HYPERLINK_JUMP.get(fields[2], _HYPERLINK_JUMP["0"])),
    ]
    if bar:
        params.append(("stringParam", "ToolTip", tooltip))
    return params


#: Hancom prints a memo's creation time in Korean time (UTC+9), marked ``Z``.
MEMO_TIME_OFFSET = timedelta(hours=9)


#: The memo shape reference of a memo whose command gives none.
MEMO_SHAPE_UNSET = 65535


def _memo_parameters(field: ct.FieldCtrl, shape: int | None) -> list[tuple[str, str, str]]:
    """``ID``, ``Number``, ``Author``, ``MemoShapeIDRef`` and ``CreateDateTime``
    of a memo: the number is the field's z-order, and the command
    ``MEMO/<memo shape>/<number>/<time low>/<time high>/<author>/...`` holds the rest."""

    parts = field.command.split("/")

    def part(index: int) -> str:
        return parts[index] if len(parts) > index else ""

    created = ""
    if part(3).isdigit() and part(4).isdigit():
        ticks = int(part(4)) << 32 | int(part(3))
        try:
            when = datetime(1601, 1, 1) + timedelta(microseconds=ticks // 10) + MEMO_TIME_OFFSET
            created = when.strftime("%Y-%m-%dT%H:%M:%SZ")
        except OverflowError:
            created = ""
    return [
        ("stringParam", "ID", f"memo{field.z_order}"),
        ("integerParam", "Number", str(field.z_order)),
        ("stringParam", "Author", part(5)),
        ("stringParam", "MemoShapeIDRef", part(1) or str(MEMO_SHAPE_UNSET)),
        ("stringParam", "CreateDateTime", created),
    ]


def field_parameters(text_id: str, field: ct.FieldCtrl, memo_shape: int | None = None) -> list[tuple[str, str, str]]:
    """``hp:parameters`` items for a field: ``Prop`` and ``Command``, then what
    Hancom spells out of the command for the kinds that have it."""

    # A control character in a command becomes a space, so its length
    # prefixes still count right.
    command = xml_spaced(field.command)
    params = [("integerParam", "Prop", str(field.extra))]
    if field.command or text_id == "%%me":
        params.append(("stringParam", "Command", command))
    if text_id == "%clk":
        values = _command_values(command)
        if values.get("Direction"):
            params.append(("stringParam", "Direction", values["Direction"]))
        if values.get("HelpState"):
            params.append(("stringParam", "HelpState", values["HelpState"]))
    elif text_id == "%hlk":
        params += _hyperlink_parameters(command)
    elif text_id == "%%me":
        params += _memo_parameters(field, memo_shape)
    elif text_id == "%pat":
        params.append(("stringParam", "Format", command))
    elif text_id == "%fmu" and "??" in command:
        # The formula ends where the first run of question marks leaves two:
        # a formula may end with a question mark of its own.
        index = command.find("??")
        while command[index + 2 : index + 3] == "?":
            index += 1
        formula, rest = command[:index], command[index + 2 :]
        result_format, _, last = rest.partition(";;")
        params += [
            ("stringParam", "Formula", formula),
            ("stringParam", "ResultFormat", result_format),
            ("stringParam", "LastResult", last),
        ]
    return params


CAPTION_SIDE = ("LEFT", "RIGHT", "TOP", "BOTTOM")
CHAR_ELEMENTS = {10: "hp:lineBreak", 24: "hp:hyphen", 30: "hp:nbSpace", 31: "hp:fwSpace"}
#: The range tag kind of a character style over the text; its low 24 bits
#: are the style's id.
RANGE_CHAR_STYLE = 1
#: The range tag kind of a highlighter (markpen) range; its low 24 bits are the color.
RANGE_MARKPEN = 2
#: Range tag kinds of tracked changes: an insertion or deletion becomes a pair
#: of marks in the text; a paragraph shape change has none (its change in the
#: header says what it made). The low 24 bits are the change's id.
TRACK_MARKS = {16: "insert", 17: "delete"}
TRACK_PARA_SHAPE = 19
#: A mark in the text: position, order at that position, element, attributes.
Mark = tuple[int, int, str, tuple[tuple[str, object], ...]]
#: The inline control of a title mark, and its words: ``Mtit`` is written
#: ``ignore="1"`` by Hancom and ``Mign`` ``ignore="0"``.
TITLE_MARK_CODE = 8
TITLE_MARK = "Mtit"
TITLE_MARK_IGNORED = "Mign"
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
#: Frames of overlapped characters, spelt as Hancom writes them ("TIRANGLE").
COMPOSE_CIRCLE = (
    "CHAR",
    "SHAPE_CIRCLE",
    "SHAPE_REVERSAL_CIRCLE",
    "SHAPE_RECTANGLE",
    "SHAPE_REVERSAL_RECTANGLE",
    "SHAPE_TRIANGLE",
    "SHAPE_REVERSAL_TIRANGLE",
    "SHAPE_LIGHT",
    "SHAPE_RHOMBUS",
    "SHAPE_REVERSAL_RHOMBUS",
    "SHAPE_ROUNDED_RECTANGLE",
    "SHAPE_EMPTY_CIRCULATE_TRIANGLE",
    "SHAPE_THIN_CIRCULATE_TRIANGLE",
    "SHAPE_THICK_CIRCULATE_TRIANGLE",
)
COMPOSE_TYPE = ("SPREAD", "OVERLAP")
#: The glyph an overlapped character's text starts with for its frame (by
#: circle type); Hancom's composeText leaves it out, the frame being circleType.
COMPOSE_FRAME_GLYPH = {
    0: "\u3000",
    1: "\u25ef",
    2: "\u25cf",
    3: "\u25a1",
    4: "\u25a0",
    5: "\u25b3",
    6: "\u25b2",
    7: "\u263c",
    8: "\u25c7",
    9: "\u25c6",
    10: "\u25a2",
    11: "\u2672",
    12: "\u267a",
    13: "\u267b",
}
#: Hancom's glyphs that stand for a digit and its frame together, by circle
#: type, and in a circle the tens and units glyphs of a two-digit number (only
#: the code points seen in its files).
COMPOSE_DIGIT_GLYPHS: dict[int, dict[int, str]] = {
    1: {n: chr(0x2460 + n - 1) for n in range(1, 10)},
    3: {n: chr(0xF02B1 + n - 1) for n in range(1, 8)},
    4: {n: chr(0xF02CE + n - 1) for n in range(1, 3)},
}
COMPOSE_TENS_GLYPHS = {n: chr(0xF0289 + n - 1) for n in range(1, 5)}
COMPOSE_UNITS_GLYPHS = {n: chr(0xF0292 + n) for n in range(10)}
#: composeText spells those glyphs as plain digits.
COMPOSE_FRAMED_DIGITS: dict[int, dict[int, str]] = {
    circle: {ord(glyph): str(n) for n, glyph in glyphs.items()} for circle, glyphs in COMPOSE_DIGIT_GLYPHS.items()
}
COMPOSE_FRAMED_DIGITS[1].update({ord(glyph): str(n) for n, glyph in COMPOSE_TENS_GLYPHS.items()})
COMPOSE_FRAMED_DIGITS[1].update({ord(glyph): str(n) for n, glyph in COMPOSE_UNITS_GLYPHS.items()})
#: The OWPML element of each form kind.
FORM_ELEMENTS = {"+cbt": "checkBtn", "+rbt": "radioBtn", "+pbt": "btn", "+edt": "edit", "+cob": "comboBox"}
FORM_VALUE = ("UNCHECKED", "CHECKED", "INDETERMINATE")
FORM_BACK_STYLE = ("TRANSPARENT", "OPAQUE")
EDIT_SCROLL_BARS = ("NONE", "VERTICAL", "HORIZONTAL", "BOTH")
EDIT_TAB_KEY = ("NEXT_OBJECT", "INSERT_TAB")
EDIT_ALIGN = ("LEFT", "CENTER", "RIGHT")
#: A form's common properties: OWPML attribute, property key and type, in
#: Hancom's order; colours are COLORREF numbers.
FORM_COMMON = (
    ("name", "Name", "wstring"),
    ("groupName", "GroupName", "wstring"),
    ("tabStop", "TabStop", "bool"),
    ("tabOrder", "TabOrder", "int"),
    ("command", "Command", "wstring"),
    ("editable", "Editable", "bool"),
    ("foreColor", "ForeColor", "int"),
    ("backColor", "BackColor", "int"),
    ("enabled", "Enabled", "bool"),
    ("borderTypeIDRef", "BorderType", "int"),
    ("drawFrame", "DrawFrame", "bool"),
    ("printable", "Printable", "bool"),
)
FORM_CHAR = (
    ("charPrIDRef", "CharShapeID", "int"),
    ("followContext", "FollowContext", "bool"),
    ("autoSz", "AutoSize", "bool"),
    ("wordWrap", "WordWrap", "bool"),
)
#: Each kind's own set: its name and items (attribute, key, type) in order.
FORM_OWN = {
    "checkBtn": ("ButtonSet", (("caption", "Caption", "wstring"), ("value", "Value", "int"), ("triState", "TriState", "bool"), ("backStyle", "BackStyle", "int"))),
    "radioBtn": (
        "ButtonSet",
        (
            ("caption", "Caption", "wstring"),
            ("radioGroupName", "RadioGroupName", "wstring"),
            ("value", "Value", "int"),
            ("triState", "TriState", "bool"),
            ("backStyle", "BackStyle", "int"),
        ),
    ),
    "btn": ("ButtonSet", (("caption", "Caption", "wstring"),)),
    "edit": (
        "EditSet",
        (
            ("text", "Text", "wstring"),
            ("multiLine", "MultiLine", "bool"),
            ("passwordChar", "PasswordChar", "wstring"),
            ("maxLength", "MaxLength", "int"),
            ("scrollBars", "ScrollBars", "int"),
            ("tabKeyBehavior", "TabKeyBehavior", "int"),
            ("numOnly", "Number", "bool"),
            ("readOnly", "ReadOnly", "bool"),
            ("alignText", "AlignText", "int"),
        ),
    ),
    # A combo box keeps no list: its text is the value of its one list item.
    "comboBox": (
        "ComboBoxSet",
        (
            ("listBoxRows", "ListBoxRows", "int"),
            ("text", "Text", "wstring"),
            ("listBoxWidth", "ListBoxWidth", "int"),
            ("editEnable", "EditEnable", "bool"),
        ),
    ),
}
#: The attributes of each form element in Hancom's order, with the value of
#: those its record has no item for; the common ones follow.
FORM_ATTRIBUTES = {
    "checkBtn": (("caption", ""), ("value", "UNCHECKED"), ("radioGroupName", ""), ("triState", "0"), ("backStyle", "OPAQUE")),
    "radioBtn": (("caption", ""), ("value", "UNCHECKED"), ("radioGroupName", ""), ("triState", "0"), ("backStyle", "OPAQUE")),
    "btn": (("caption", ""), ("radioGroupName", ""), ("triState", "0")),
    "edit": (
        ("multiLine", "0"),
        ("passwordChar", "*"),
        ("maxLength", "2147483647"),
        ("scrollBars", "NONE"),
        ("tabKeyBehavior", "NEXT_OBJECT"),
        ("numOnly", "0"),
        ("readOnly", "0"),
        ("alignText", "LEFT"),
    ),
    "comboBox": (("listBoxRows", "10"), ("listBoxWidth", "0"), ("editEnable", "0"), ("selectedValue", "")),
}
FORM_COMMON_ATTRIBUTES = (
    "name",
    "foreColor",
    "backColor",
    "groupName",
    "tabStop",
    "editable",
    "tabOrder",
    "enabled",
    "borderTypeIDRef",
    "drawFrame",
    "printable",
    "command",
)
#: Attributes whose number is a token, by attribute.
FORM_TOKENS = {
    "value": FORM_VALUE,
    "backStyle": FORM_BACK_STYLE,
    "scrollBars": EDIT_SCROLL_BARS,
    "tabKeyBehavior": EDIT_TAB_KEY,
    "alignText": EDIT_ALIGN,
}
#: Controls written as one element inside ``hp:ctrl``.
MARKERS = {
    "pgnp": "pageNum",
    "pghd": "pageHiding",
    "nwno": "newNum",
    "atno": "autoNum",
    "bokm": "bookmark",
    "idxm": "indexmark",
}


def _char(value: int) -> str:
    """A character code as text; nothing for 0 or a value that is not a character."""

    return chr(value) if 0 < value < 0xD800 or 0xE000 <= value < 0x110000 else ""


#: A character style over the text: start, end (both in the paragraph's
#: characters) and the style's id.
CharStyle = tuple[int, int, int]


def char_styles(record: rec.Record) -> list[CharStyle]:
    """The character styles the paragraph's range tags put on its text, in
    text order."""

    styles: list[CharStyle] = []
    for child in record.children:
        if child.tag != rec.PARA_RANGE_TAG:
            continue
        for offset in range(0, len(child.payload) - 11, 12):
            start, end, tag = struct.unpack_from("<III", child.payload, offset)
            if tag >> 24 == RANGE_CHAR_STYLE and start < end:
                styles.append((start, end, tag & 0xFFFFFF))
    return sorted(styles)


def _is_open(run: etree._Element, text: etree._Element | None) -> bool:
    """Whether *text* is the run's last child, so more text can go into it."""

    return text is not None and len(run) > 0 and run[-1] is text


def _place_marks(parent: etree._Element, marks: list[Mark], pending: int, position: int) -> int:
    """Append the marks due at *position* to *parent*; return the next pending mark."""

    while pending < len(marks) and marks[pending][0] <= position:
        _position, _order, name, attrs = marks[pending]
        sub(parent, name, attrs)
        pending += 1
    return pending


class SectionWriter(ShapeReader):
    """Writes the paragraphs of one BodyText section as OWPML."""

    def __init__(self, report: ConversionReport) -> None:
        self.report = report
        # Fields opened by a field-start control and not yet closed: (id, fieldid).
        self.open_fields: list[tuple[int, int]] = []
        # Memo bodies of the section (see collect_memos), taken in order by
        # its memo fields.
        self.memo_bodies: list[tuple[int, rec.Record, list[rec.Record]]] = []
        # The document's master pages so far, each the bytes of its
        # ``Contents/masterpage<N>.xml`` part (None: report them instead), and
        # the section properties that refer to them.
        self.master_pages: list[bytes] | None = None
        self.section_pr: etree._Element | None = None
        # The chart part of each OLE item that holds a chart.
        self.charts: dict[str, str] = {}
        # The change marks of the document so far (one count, shared by its
        # sections): a mark's id counts every change range tag before it.
        self.track_ids: list[int] = [0]

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
        self.runs(element, para, self.marks(record), char_styles(record))
        # Lists hung on the paragraph itself: memo bodies after MEMO_LIST (the
        # memo fields take them, see memo_bodies), or (on a section's last
        # paragraph) its last-page and optional-page master pages.
        memo = False
        for header, paragraphs in lists(record, rec.MEMO_LIST):
            if header.tag == rec.MEMO_LIST:
                memo = True
                continue
            if not memo:
                kind = struct.unpack_from("<H", header.payload.ljust(20, b"\0"), 18)[0]
                if kind == MASTER_PAGE_LAST:
                    self.master_page("LAST_PAGE", 0, header, paragraphs)
                elif kind > MASTER_PAGE_LAST:
                    self.master_page("OPTIONAL_PAGE", kind - MASTER_PAGE_LAST, header, paragraphs)
                else:
                    self.report.skip("master-page")
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

    def marks(self, record: rec.Record) -> list[Mark]:
        """Highlighter and change marks from the paragraph's range tags, in
        text order; at one position an end goes before a start. A change
        ending at the paragraph's end says so (``paraend``)."""

        chars = struct.unpack_from("<I", record.payload.ljust(4, b"\0"), 0)[0] & 0x7FFFFFFF
        events: list[Mark] = []
        for child in record.children:
            if child.tag != rec.PARA_RANGE_TAG:
                continue
            for offset in range(0, len(child.payload) - 11, 12):
                start, end, tag = struct.unpack_from("<III", child.payload, offset)
                kind = tag >> 24
                closing = 2 if end == start else 0
                if kind == RANGE_MARKPEN:
                    events.append((start, 1, "hp:markpenBegin", (("color", color(tag & 0xFFFFFF)),)))
                    events.append((end, closing, "hp:markpenEnd", ()))
                elif kind in TRACK_MARKS:
                    self.track_ids[0] += 1
                    name, ids = TRACK_MARKS[kind], (("Id", self.track_ids[0]), ("TcId", tag & 0xFFFFFF))
                    events.append((start, 1, f"hp:{name}Begin", ids))
                    events.append((end, closing, f"hp:{name}End", (*ids, ("paraend", flag(end >= chars)))))
                elif kind == TRACK_PARA_SHAPE:
                    self.track_ids[0] += 1
                    self.report.drop(f"range-tag-{kind}")
                elif kind == RANGE_CHAR_STYLE:
                    continue  # see char_styles
                elif kind == 0:
                    self.report.drop(f"range-tag-{kind}")
                else:
                    self.report.skip(f"range-tag-{kind}")
        events.sort(key=lambda event: (event[0], event[1]))
        return events

    def runs(
        self, element: etree._Element, para: bt.Paragraph, marks: list[Mark], styles: list[CharStyle] | None = None
    ) -> None:
        """The runs of a paragraph: one per character shape, text split where
        a mark or a character style begins or ends; styled text goes in text
        nodes of its own."""

        styles = styles or []
        edges = sorted({position for start, stop, _ in styles for position in (start, stop)})

        def style(position: int) -> int | None:
            return next((style_id for start, stop, style_id in styles if start <= position < stop), None)

        entries = para.char_shapes or [(0, 0)]
        # Hancom writes one run for consecutive entries of the same shape.
        shapes = [entry for index, entry in enumerate(entries) if index == 0 or entry[1] != entries[index - 1][1]]
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
                    if chunk.kind in ("text", "char") or (chunk.kind == "inline" and chunk.code == bt.TAB):
                        text = self._text(run, text, "", style(chunk.position))
                    target = text if text is not None and _is_open(run, text) else run
                    pending = _place_marks(target, marks, pending, chunk.position)
                    if target is text:
                        last = text
                if chunk.kind == "text":
                    limit = end
                    if pending < len(marks) and chunk.position < marks[pending][0] < limit:
                        limit = marks[pending][0]
                    edge = next((position for position in edges if position > chunk.position), limit)
                    limit = min(limit, edge)
                    split = limit - chunk.position
                    if chunk.width > split:
                        head, tail = _split_text(chunk, split)
                        chunks[index] = tail
                        chunk = head
                    else:
                        index += 1
                    text = self._text(run, text, chunk.text, style(chunk.position))
                    last = text
                    continue
                index += 1
                if chunk.kind == "char":
                    name = CHAR_ELEMENTS.get(chunk.code)
                    if name is None:
                        continue
                    text = self._text(run, text, "", style(chunk.position))
                    sub(text, name)
                    last = text
                elif chunk.kind == "inline":
                    if chunk.code == bt.TAB:
                        text = self._text(run, text, "", style(chunk.position))
                        width, leader, kind = struct.unpack_from("<IBB", chunk.params.ljust(6, b"\0"), 0)
                        sub(text, "hp:tab", (("width", width), ("leader", leader), ("type", kind)))
                        last = text
                    elif chunk.code == TITLE_MARK_CODE:
                        text = self._text(run, text, "", style(chunk.position))
                        word = bt.ctrl_id(struct.unpack_from("<I", chunk.params.ljust(4, b"\0"))[0])
                        sub(text, "hp:titleMark", (("ignore", flag(word == TITLE_MARK)),))
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
        end_style = style(para.char_count - 1)
        if run is not None and pending < len(marks):
            text = self._text(run, text, "", end_style)
            _place_marks(text, marks, pending, 1 << 31)
            last = text
        # A character style that ends before the paragraph's end closes its
        # text node there; Hancom opens an empty one for the rest.
        if run is not None and _is_open(run, text) and text is not None and text.get("charStyleIDRef") is not None:
            if end_style is None:
                text = last = sub(run, "hp:t")
        # Hancom closes a paragraph that ends on a control with an empty text
        # node: in the control's run, or in the run of the paragraph's end
        # when that one has nothing else.
        if last is not None and etree.QName(last).localname == "run":
            sub(last, "hp:t")
        elif last is not None and etree.QName(last).localname != "t":
            parent = last.getparent()
            if parent is not None:
                sub(parent, "hp:t")
        elif last is None and run is not None and len(run) == 0:
            filled = [r for r in element if etree.QName(r).localname == "run" and len(r)]
            if filled and etree.QName(filled[-1][-1]).localname != "t":
                sub(run, "hp:t")

    @staticmethod
    def _text(run: etree._Element, text: etree._Element | None, value: str, style: int | None = None) -> etree._Element:
        """The text node *value* goes on in: *text* while it is the run's last
        child and has the character style *style*, else a new one."""

        target = text
        wanted = None if style is None else str(style)
        if target is None or target.getparent() is not run or run[-1] is not target or target.get("charStyleIDRef") != wanted:
            target = sub(run, "hp:t", () if style is None else (("charStyleIDRef", style),))
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
            # The section definition's paragraph lists are the section's master
            # pages for both, even and odd pages, one per property bit set; its
            # parameter set holds the presentation settings, which come last.
            element = section_properties(run, ctrl)
            self.section_pr = element
            props = ct.SectionDef.decode(ctrl.payload).props
            types = [page_type for bit, page_type in MASTER_PAGE_BITS if props >> bit & 1]
            pages = lists(ctrl)
            for index, (header, paragraphs) in enumerate(pages):
                if len(pages) == len(types):
                    self.master_page(types[index], 0, header, paragraphs)
                else:
                    self.report.skip("master-page")
            for child in ctrl.children:
                if child.tag == rec.CTRL_DATA:
                    ps = ct.ParameterSet.decode(child.payload)
                    settings = ct.Presentation.from_set(ps) if ps is not None else None
                    if settings is None or not presentation(element, settings):
                        self.report.skip("presentation")
            return element
        if kind == "cold":
            return column_properties(run, ctrl)
        if kind == "tbl ":
            return self.table(run, ctrl)
        if kind in ("head", "foot"):
            return self.header_footer(run, ctrl, kind)
        if kind in ("fn  ", "en  "):
            return self.note(run, ctrl, kind)
        if kind == "tcmt":
            # A hidden comment is a paragraph list, like a note body.
            wrapper = sub(run, "hp:ctrl")
            self.body(sub(wrapper, "hp:hiddenComment"), ctrl)
            return wrapper
        if kind in MARKERS:
            return self.marker(run, ctrl, kind)
        if kind == "tdut":
            return self.dutmal(run, ctrl)
        if kind == "tcps":
            return self.compose(run, ctrl)
        if kind == "form":
            return self.form(run, ctrl)
        if kind == "gso ":
            return self.drawing(run, ctrl)
        if kind == "eqed":
            return self.equation(run, ctrl)
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
                    ("type", NOTE_NUMBER_FORMAT.get(_bits(an.props, 4, 8), "DIGIT")),
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

    def equation(self, run: etree._Element, ctrl: rec.Record) -> etree._Element | None:
        """``hp:equation``: the object layout, its comment and the script."""

        record = next((c for c in ctrl.children if c.tag == rec.EQEDIT), None)
        if record is None:
            self.report.skip("control-eqed")
            return None
        for child in ctrl.children:
            if child.tag == rec.LIST_HEADER:
                self.report.skip("equation-caption")
        common = ct.ObjectCommon.decode(ctrl.payload)
        eq = ct.EquationEdit.decode(record.payload)
        element = sub(
            run,
            "hp:equation",
            object_attrs(common)
            + [
                ("version", eq.version or ct.EQUATION_VERSION),
                ("baseLine", eq.baseline),
                ("textColor", color(eq.color)),
                ("baseUnit", eq.base_unit),
                ("lineMode", "LINE" if eq.props & 0x1 else "CHAR"),
                ("font", eq.font or ct.EQUATION_FONT),
            ],
        )
        object_layout(element, common)
        if common.description:
            sub(element, "hp:shapeComment").text = xml_text(common.description)
        # Hancom's HWPX leaves the carriage returns of a script out.
        sub(element, "hp:script").text = xml_text(eq.script.replace("\r", ""))
        return element

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

    def form(self, run: etree._Element, ctrl: rec.Record) -> etree._Element | None:
        """A form object (check box, radio button, push button, edit box,
        combo box) from its property text; the object header gives its size
        and place."""

        record = next((c for c in ctrl.children if c.tag == rec.FORM_OBJECT), None)
        if record is None:
            self.report.skip("control-form")
            return None
        value = ct.FormObject.decode(record.payload)
        name = FORM_ELEMENTS.get(value.kind)
        if name is None:
            self.report.skip(f"form-{value.kind.strip('+') or '?'}")
            return None
        sets = value.items()
        own_set, own_items = FORM_OWN[name]
        found: dict[str, str] = {}
        for items, table in ((sets.get("CommonSet", {}), FORM_COMMON), (sets.get("CharShapeSet", {}), FORM_CHAR), (sets.get(own_set, {}), own_items)):
            for attribute, key, _kind in table:
                if key in items:
                    found[attribute] = _form_value(attribute, items[key])
        attrs = [(attribute, found.get(attribute, default)) for attribute, default in FORM_ATTRIBUTES[name]]
        attrs += [(attribute, found.get(attribute, "")) for attribute in FORM_COMMON_ATTRIBUTES]
        element = sub(run, f"hp:{name}", attrs)
        sub(element, "hp:formCharPr", [(attribute, found.get(attribute, "0")) for attribute, _, _ in FORM_CHAR])
        if name == "edit":
            sub(element, "hp:text").text = xml_text(found.get("text", ""))
        elif name == "comboBox":
            sub(element, "hp:listItem", (("displayText", ""), ("value", found.get("text", ""))))
        object_layout(element, ct.ObjectCommon.decode(ctrl.payload))
        return element

    def compose(self, run: etree._Element, ctrl: rec.Record) -> etree._Element:
        """``hp:compose``: characters set over each other in a frame, with the
        char shape of each place."""

        value = ct.Compose.decode(ctrl.payload)
        if value.circle >= len(COMPOSE_CIRCLE) or value.kind >= len(COMPOSE_TYPE):
            self.report.skip("compose-frame")
        text = value.text
        if len(text) > 1 and text[0] == COMPOSE_FRAME_GLYPH.get(value.circle):
            text = text[1:]
        digits = COMPOSE_FRAMED_DIGITS.get(value.circle, {})
        text = "".join(digits.get(ord(ch), ch) for ch in text)
        element = sub(
            run,
            "hp:compose",
            (
                ("circleType", token(COMPOSE_CIRCLE, value.circle)),
                ("charSz", value.size),
                ("composeType", token(COMPOSE_TYPE, value.kind)),
                ("charPrCnt", len(value.char_shapes)),
                ("composeText", text),
            ),
        )
        for shape in value.char_shapes:
            sub(element, "hp:charPr", (("prIDRef", shape),))
        return element

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
        body = self.memo_bodies.pop(0) if text_id == "%%me" and self.memo_bodies else None
        params = field_parameters(text_id, field_ctrl, body[0] if body is not None else None)
        container = sub(begin, "hp:parameters", (("cnt", len(params)), ("name", "")))
        for kind, key, value in params:
            item = sub(container, f"hp:{kind}", (("name", key),))
            item.text = xml_text(value)
            if value != value.strip():
                item.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        if body is not None:
            _, header, paragraphs = body
            sub_list = sub(begin, "hp:subList", list_attrs(ct.ListHeader.decode(header.payload).props))
            self.paragraphs(sub_list, paragraphs)
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
            self.sized_list(parent, header, paragraphs)

    def sized_list(self, parent: etree._Element, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        """``hp:subList`` with the text size its list header holds."""

        list_header = ct.ListHeader.decode(header.payload)
        attrs = list_attrs(list_header.props)
        width, height = list_header.text_size
        attrs[6] = ("textWidth", width)
        attrs[7] = ("textHeight", height)
        self.paragraphs(sub(parent, "hp:subList", attrs), paragraphs)

    def master_page(self, page_type: str, number: int, header: rec.Record, paragraphs: list[rec.Record]) -> None:
        """A master page as its own part (``masterPage``, whose root has no
        namespace), referred to from the section properties. Offset 22 of its
        list header holds the duplicate (bit 0) and front (bit 1) flags."""

        if self.master_pages is None or self.section_pr is None:
            self.report.skip("master-page")
            return
        flags = struct.unpack_from("<H", header.payload.ljust(24, b"\0"), 22)[0]
        part_id = f"masterpage{len(self.master_pages)}"
        page = etree.Element("masterPage", nsmap=dict(NS))
        for key, value in (
            ("id", part_id),
            ("type", page_type),
            ("pageNumber", str(number)),
            ("pageDuplicate", flag(flags & 0x1)),
            ("pageFront", flag(flags & 0x2)),
        ):
            page.set(key, value)
        self.sized_list(page, header, paragraphs)
        self.master_pages.append(serialize(page))
        sub(self.section_pr, "hp:masterPage", (("idRef", part_id),))
        self.section_pr.set("masterPageCnt", str(len(self.section_pr.findall(q("hp:masterPage")))))

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


def _form_value(attribute: str, raw: str) -> str:
    """A form property as its OWPML attribute value: colours from COLORREF
    numbers, tokens from their numbers, the rest as written."""

    number = int(raw) if raw.lstrip("-").isdigit() else 0
    if attribute in ("foreColor", "backColor"):
        return color(number)
    table = FORM_TOKENS.get(attribute)
    return token(table, number) if table is not None else raw


def _split_text(chunk: bt.Chunk, units: int) -> tuple[bt.Chunk, bt.Chunk]:
    raw = chunk.text.encode("utf-16-le", errors="surrogatepass")
    head = raw[: units * 2].decode("utf-16-le", errors="surrogatepass")
    tail = raw[units * 2 :].decode("utf-16-le", errors="surrogatepass")
    return bt.Chunk("text", chunk.position, head), bt.Chunk("text", chunk.position + units, tail)


MemoBody = tuple[int, rec.Record, list[rec.Record]]


def memo_bodies(streams: list[rec.RecordStream]) -> list[MemoBody]:
    """The memo bodies of a document in record order: each ``MEMO_LIST``
    value, the list header after it and that list's paragraphs.

    They hang on one paragraph, often in the last section and away from their
    memo fields, which take them in the same order.
    """

    bodies: list[MemoBody] = []
    for stream in streams:
        for top in stream.roots:
            for record in top.walk():
                if record.tag != rec.PARA_HEADER:
                    continue
                value: int | None = None
                current: list[rec.Record] | None = None
                for child in record.children:
                    if child.tag == rec.MEMO_LIST:
                        value = struct.unpack_from("<I", child.payload + bytes(4))[0]
                    elif child.tag == rec.LIST_HEADER:
                        current = None
                        if value is not None:
                            current = []
                            bodies.append((value, child, current))
                            value = None
                    elif child.tag == rec.PARA_HEADER and current is not None:
                        current.append(child)
    return bodies


def build_section(
    stream: rec.RecordStream,
    report: ConversionReport,
    memos: list[MemoBody] | None = None,
    master_pages: list[bytes] | None = None,
    charts: dict[str, str] | None = None,
    track_ids: list[int] | None = None,
) -> bytes:
    """``Contents/section<N>.xml`` for one BodyText section.

    ``memos`` is the document's list of memo bodies (see :func:`memo_bodies`),
    shared by its sections; the memo fields of this section take theirs from
    its front. Without it the section's own bodies are used and any left over
    are reported.

    ``master_pages`` gathers the document's master pages: the section appends
    the part of each of its own, ``Contents/masterpage<N>.xml`` where N is the
    part's place in the list. Without it they are reported.

    ``charts`` maps each OLE item that holds a chart to the chart's part;
    such an object becomes the chart with the OLE object as its fallback.

    ``track_ids`` is the document's count of change marks so far (one item,
    shared by its sections); without it the section counts its own.
    """

    section = root("hs:sec")
    writer = SectionWriter(report)
    writer.memo_bodies = memos if memos is not None else memo_bodies([stream])
    writer.master_pages = master_pages
    writer.charts = charts or {}
    if track_ids is not None:
        writer.track_ids = track_ids
    writer.paragraphs(section, stream.roots)
    if memos is None:
        for _ in writer.memo_bodies:
            report.skip("memo-body")
    return serialize(section)
