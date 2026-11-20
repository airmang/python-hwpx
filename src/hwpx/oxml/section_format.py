# SPDX-License-Identifier: Apache-2.0
"""Owned section layout, numbering, and story-link behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence
import xml.etree.ElementTree as ET

from ._document_primitives import (
    _require_text,
    paragraph_attributes,
    _HP,
    _append_child,
    _apply_optional_attrs,
    _apply_optional_bool_attrs,
    _bool_str,
    _get_bool_attr,
    _get_int_attr,
    _normalize_color,
    _object_id,
    _optional_int_attr,
    _paragraph_id,
)
from ..objects.results import StartNumbers
from .numbering_kinds import number_format
from .utils import normalize_line_width
from .section_story import (
    HwpxOxmlSectionHeaderFooter,
    _section_story_elements,
    story_control_index,
)

if TYPE_CHECKING:
    from .section import HwpxOxmlSection
    from .simple_parts import HwpxOxmlMasterPage


#: ``hp:pagePr@landscape`` as Hancom writes it. Both values keep the paper's
#: portrait size (width <= height): ``WIDELY`` draws the page as stored, so it
#: is portrait, and ``NARROWLY`` turns it, so it is landscape. ``NARROWLY`` is
#: also the schema default, which a missing or unknown value falls back to.
#: ``PageSize.orientation`` is one of the two.
PAGE_PORTRAIT = "WIDELY"
PAGE_LANDSCAPE = "NARROWLY"
_PAGE_PORTRAIT = PAGE_PORTRAIT
_PAGE_LANDSCAPE = PAGE_LANDSCAPE
_PAGE_ORIENTATIONS = {
    "PORTRAIT": _PAGE_PORTRAIT,
    "NARROW": _PAGE_PORTRAIT,
    "WIDELY": _PAGE_PORTRAIT,
    "LANDSCAPE": _PAGE_LANDSCAPE,
    "WIDE": _PAGE_LANDSCAPE,
    "NARROWLY": _PAGE_LANDSCAPE,
}


def _page_orientation_value(value: str) -> str | None:
    """Return the ``landscape`` value for an orientation name, or ``None``."""

    return _PAGE_ORIENTATIONS.get(value.strip().upper())


def _drawn_page_size(width: int, height: int, landscape: str | None) -> tuple[int, int]:
    """Width and height of the page as Hancom draws it."""

    return (width, height) if landscape == _PAGE_PORTRAIT else (height, width)


#: What Hancom reads a page margin written with a minus sign as (it saves these back): the new-page margins.
_PAGE_MARGIN_FOR_MINUS = {"top": 5668, "bottom": 4252, "left": 8504, "right": 8504, "header": 4252, "footer": 4252,
                          "gutter": 0}


def _page_margin(value: str | int, side: str) -> int:
    """The *side* page margin (``hp:margin``) as Hancom reads it. A negative one is kept as an unsigned 32-bit
    number (a header margin of -1400 as 4294965896, as a converted .hwp has it) and counts as negative; one
    written with a minus sign is not a margin Hancom reads, and it takes the new-page margin for that side."""

    if isinstance(value, str) and value.strip().startswith("-"):
        return _PAGE_MARGIN_FOR_MINUS[side]
    margin = int(value)
    return margin - (1 << 32) if margin >= 1 << 31 else margin


def _hancom_page_orientation(
    page_pr: ET.Element, orientation: str, width: int | None, height: int | None
) -> tuple[str, int | None, int | None]:
    """Map *orientation* to Hancom's value and keep the paper's portrait size.

    Hancom stores both orientations with the shorter side as the width and
    lets ``NARROWLY`` turn the page. Unknown values pass through unchanged.
    """

    value = _page_orientation_value(orientation)
    if value is None:
        return orientation, width, height
    new_width = _get_int_attr(page_pr, "width", 0) if width is None else width
    new_height = _get_int_attr(page_pr, "height", 0) if height is None else height
    if new_width > new_height:
        return value, new_height, new_width
    return value, width, height


@dataclass(slots=True)
class PageSize:
    """Represents the size and orientation of a page.

    ``width``/``height``/``orientation`` are stored values: ``orientation`` is
    ``WIDELY`` for a portrait page and ``NARROWLY`` for a landscape page, and a
    landscape page keeps the paper's portrait width and height.
    ``drawn_width``/``drawn_height`` give the page as Hancom draws it.

    Read as the file has them: an attribute ``hp:pagePr`` leaves out is the schema's
    default (width 59528, height 84188, ``NARROWLY``, ``LEFT_ONLY``); a size that is
    not a number, or a section with no ``hp:pagePr``, reads ``None`` (never 0).
    """

    width: int | None
    height: int | None
    orientation: str
    gutter_type: str

    @property
    def drawn_width(self) -> int | None:
        """The page's width as drawn; ``None`` when width or height is not known."""
        if self.width is None or self.height is None:
            return None
        return _drawn_page_size(self.width, self.height, self.orientation)[0]

    @property
    def drawn_height(self) -> int | None:
        """The page's height as drawn; ``None`` when width or height is not known."""
        if self.width is None or self.height is None:
            return None
        return _drawn_page_size(self.width, self.height, self.orientation)[1]


@dataclass(slots=True)
class PageMargins:
    """Page margins (``hp:pagePr/hp:margin``) in HWP units, as the file has them.

    ``header``/``footer``/``gutter`` the file leaves out read the schema's default (4252,
    4252, 0). ``left``/``right``/``top``/``bottom`` have none (the schema requires them):
    left out, like a value that is not a number or a section with no ``hp:margin``, they
    read ``None`` -- never a 0 nobody wrote.
    """

    left: int | None
    right: int | None
    top: int | None
    bottom: int | None
    header: int | None
    footer: int | None
    gutter: int | None


def _stored_length(element: ET.Element, name: str, default: int | None) -> int | None:
    """The integer attribute *name* of *element*: *default* (the schema's) when left out, ``None``
    when it is not a number."""

    value = element.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(slots=True)
class SectionGrid:
    """Represents ``<hp:grid>`` — line/character grid alignment."""

    line_grid: int
    char_grid: int
    wonggoji_format: bool


@dataclass(slots=True)
class SectionVisibility:
    """Represents ``<hp:visibility>`` — first-page show/hide flags."""

    hide_first_header: bool
    hide_first_footer: bool
    hide_first_master_page: bool
    hide_first_page_num: bool
    hide_first_empty_line: bool
    show_line_number: bool
    border: str | None
    fill: str | None


@dataclass(slots=True)
class LineNumberShape:
    """Represents ``<hp:lineNumberShape>`` — line-numbering display."""

    restart_type: int | None
    count_by: int | None
    distance: int | None
    start_number: int | None


@dataclass(slots=True)
class PageBorderFill:
    """Represents one ``<hp:pageBorderFill>`` entry (keyed by ``page_type``)."""

    page_type: str
    border_fill_id_ref: str | None
    text_border: str | None
    header_inside: bool
    footer_inside: bool
    fill_area: str | None
    offset_left: int
    offset_right: int
    offset_top: int
    offset_bottom: int


@dataclass(slots=True)
class NoteAutoNumFormat:
    """Represents a note's ``<hp:autoNumFormat>`` — shared by foot/endnotes."""

    type: str
    user_char: str | None
    prefix_char: str | None
    suffix_char: str
    supscript: bool


@dataclass(slots=True)
class NoteLine:
    """Represents a note's ``<hp:noteLine>`` separator — shared by foot/endnotes."""

    length: int
    type: str
    width: str
    color: str


@dataclass(slots=True)
class NoteSpacing:
    """Represents a note's ``<hp:noteSpacing>`` — shared by foot/endnotes."""

    between_notes: int
    below_line: int
    above_line: int


@dataclass(slots=True)
class NoteNumbering:
    """Represents a note's ``<hp:numbering>`` — CONTINUOUS/ON_SECTION(/ON_PAGE)."""

    type: str
    new_num: int


@dataclass(slots=True)
class NotePlacement:
    """Represents a note's ``<hp:placement>`` — footnote/endnote vocab differs."""

    place: str
    beneath_text: bool


@dataclass(slots=True)
class NoteShape:
    """Aggregate read view of a ``<hp:footNotePr>``/``<hp:endNotePr>``."""

    auto_num_format: NoteAutoNumFormat
    note_line: NoteLine
    note_spacing: NoteSpacing
    numbering: NoteNumbering
    placement: NotePlacement


def validate_new_number(number: object) -> int:
    """A ``hp:newNum/@num``: *number* as an int, checked to be in ``0 <= number <= 65535``. Hancom keeps it as
    an unsigned 16-bit number, reading -1 as 65535 and 65536 as 0."""

    from ..errors import HwpxValueError

    value = int(number)  # type: ignore[call-overload]
    if not 0 <= value < 2**16:
        raise HwpxValueError(
            f"number must be in 0 <= number <= 65535; got {number!r}",
            code="page-new-num-value",
            context={"value": repr(number)},
            suggestion="Pass the number the count restarts at, from 0 to 65535.",
        )
    return value


def validate_column_gap(gap: object) -> int:
    """The gap between columns of the same width (``hp:colPr/@sameGap``, HWPUNIT), checked to be an int in
    ``0 <= gap <= 32767``: Hancom reads it as a signed 16-bit number (32768 as -32768, the columns then
    overlapping; 65536 as 0) and a negative one written as text as 0."""

    from ..errors import HwpxValueError

    if isinstance(gap, bool) or not isinstance(gap, int) or not 0 <= gap < 2**15:
        raise HwpxValueError(
            f"same_gap must be an int in 0 <= same_gap <= 32767 (HWPUNIT); got {gap!r}",
            code="page-column-gap-value",
            context={"value": repr(gap)},
            suggestion="Pass the gap between columns in HWP units, e.g. 1200 (about 4 mm).",
        )
    return gap


#: Hancom keeps each column's width and gap (``hp:colSz``) as a share of the text width out of 32768 and lays a
#: column out ``width * text width / 32768`` wide, whatever the shares add up to; its own add up to 32768.
COLUMN_SHARES = 32768


def column_shares(column_widths: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """*column_widths*, a ``(width, gap)`` pair per column in any one unit (HWP units adding up to the text width,
    or plain proportions), as the ``hp:colSz`` shares Hancom keeps: in the same proportions, adding up to
    :data:`COLUMN_SHARES`, so that the columns and their gaps fill the text width. Every value must be an int of
    0 or more, not all of them 0."""

    from ..errors import HwpxValueError

    pairs = [tuple(pair) for pair in column_widths]
    values = [value for pair in pairs for value in pair]
    if (
        any(len(pair) != 2 for pair in pairs)
        or not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values)
        or sum(values) <= 0
    ):
        raise HwpxValueError(
            f"column_widths must be (width, gap) pairs of ints, 0 or more and not all 0; got {column_widths!r}",
            code="page-column-widths-value",
            context={"value": repr(column_widths)},
            suggestion="Pass a (width, gap) pair per column, e.g. [(20000, 1000), (21520, 0)] in HWP units.",
        )
    total, run, edges = sum(values), 0, [0]
    for value in values:  # rounded at each edge, so that the shares add up to COLUMN_SHARES
        run += value
        edges.append((2 * run * COLUMN_SHARES + total) // (2 * total))
    shares = [end - start for start, end in zip(edges, edges[1:])]
    return list(zip(shares[::2], shares[1::2]))


#: ``hp:pagePr/@gutterType``, ``hp:pageBorderFill/@type`` and ``@fillArea``: Hancom reads another value as its
#: default (LEFT_ONLY, PAPER).
GUTTER_TYPES = ("LEFT_ONLY", "LEFT_RIGHT", "TOP_BOTTOM")
PAGE_BORDER_FILL_TYPES = ("BOTH", "EVEN", "ODD")
PAGE_BORDER_FILL_AREAS = ("PAPER", "PAGE", "BORDER")


def _checked(argument: str, value: object, high: int, code: str) -> int:
    """*value* checked to be an int in ``0 <= value <= high``, as Hancom keeps it (refused with *code*)."""

    from ..errors import HwpxValueError

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= high:
        raise HwpxValueError(
            f"{argument} must be an int in 0 <= {argument} <= {high}; got {value!r}",
            code=code,
            context={"argument": argument, "value": repr(value), "high": high},
            suggestion=f"Pass {argument} from 0 to {high}: Hancom reads another value as something else.",
        )
    return value


def _choice(argument: str, value: object, allowed: Sequence[str], code: str) -> str:
    """*value* checked to be one of *allowed* (refused with *code*)."""

    from ..errors import HwpxValueError

    if value not in allowed:
        raise HwpxValueError(
            f"{argument} must be one of {', '.join(allowed)}; got {value!r}",
            code=code,
            context={"argument": argument, "value": repr(value), "allowed": list(allowed)},
            suggestion=f"Pass one of {', '.join(allowed)}: Hancom reads another value as its default.",
        )
    return str(value)


def _master_page_id(master_page: object) -> str:
    """The id of *master_page*: a master page id as it is, or a ``MasterPage``'s ``id``."""

    found = master_page if isinstance(master_page, str) else getattr(master_page, "id", None)
    if not isinstance(found, str):
        from ..errors import argument_type_error

        raise argument_type_error("master_page_id", master_page, "a master page id (str) or a MasterPage")
    return found


def _check_page_size(width: object, height: object, gutter_type: object) -> None:
    """A page's size (0 to 2**31 - 1) and gutter type, checked before anything changes."""

    for argument, size in (("width", width), ("height", height)):
        if size is not None:
            _checked(argument, size, 2**31 - 1, "page-size-value")
    if gutter_type is not None:
        _choice("gutter_type", gutter_type, GUTTER_TYPES, "page-gutter-type-invalid")


class HwpxOxmlSectionProperties:
    """Provides convenient access to ``<hp:secPr>`` configuration."""

    def __init__(self, element: ET.Element, section: "HwpxOxmlSection"):
        self.element = element
        self.section = section

    # -- page configuration -------------------------------------------------
    def _page_pr_element(self, create: bool = False) -> ET.Element | None:
        page_pr = self.element.find(f"{_HP}pagePr")
        if page_pr is None and create:
            page_pr = _append_child(
                self.element,
                f"{_HP}pagePr",
                {"landscape": _PAGE_PORTRAIT, "width": "0", "height": "0", "gutterType": "LEFT_ONLY"},
            )
            self.section.mark_dirty()
        return page_pr

    def _margin_element(self, create: bool = False) -> ET.Element | None:
        page_pr = self._page_pr_element(create=create)
        if page_pr is None:
            return None
        margin = page_pr.find(f"{_HP}margin")
        if margin is None and create:
            margin = _append_child(
                page_pr,
                f"{_HP}margin",
                {
                    "left": "0",
                    "right": "0",
                    "top": "0",
                    "bottom": "0",
                    "header": "0",
                    "footer": "0",
                    "gutter": "0",
                },
            )
            self.section.mark_dirty()
        return margin

    @property
    def page_size(self) -> PageSize:
        """The page size as the file has it (:class:`PageSize`; ``None`` for a size not written or not a number)."""
        page_pr = self._page_pr_element()
        if page_pr is None:
            return PageSize(width=None, height=None, orientation=_PAGE_LANDSCAPE, gutter_type="LEFT_ONLY")
        return PageSize(
            width=_stored_length(page_pr, "width", 59528),  # the schema's defaults
            height=_stored_length(page_pr, "height", 84188),
            orientation=page_pr.get("landscape", _PAGE_LANDSCAPE),
            gutter_type=page_pr.get("gutterType", "LEFT_ONLY"),
        )

    def set_page_size(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        orientation: str | None = None,
        gutter_type: str | None = None,
    ) -> None:
        """Set the page size; ``orientation`` decides how Hancom draws the page.

        ``orientation`` takes ``PORTRAIT``/``LANDSCAPE`` (or ``WIDELY``/
        ``NARROWLY``) and is written as Hancom writes it, with the paper's
        portrait size whichever order ``width`` and ``height`` come in. Other
        values are written as given.
        """
        _check_page_size(width, height, gutter_type)
        page_pr = self._page_pr_element(create=True)
        if page_pr is None:
            return
        if orientation is not None:
            orientation, width, height = _hancom_page_orientation(page_pr, orientation, width, height)

        changed = False
        if width is not None:
            value = str(width)
            if page_pr.get("width") != value:
                page_pr.set("width", value)
                changed = True
        if height is not None:
            value = str(height)
            if page_pr.get("height") != value:
                page_pr.set("height", value)
                changed = True
        if orientation is not None and page_pr.get("landscape") != orientation:
            page_pr.set("landscape", orientation)
            changed = True
        if gutter_type is not None and page_pr.get("gutterType") != gutter_type:
            page_pr.set("gutterType", gutter_type)
            changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def page_margins(self) -> PageMargins:
        """The page margins as the file has them (:class:`PageMargins`; ``None`` for one not known)."""
        margin = self._margin_element()
        if margin is None:
            return PageMargins(left=None, right=None, top=None, bottom=None, header=None, footer=None, gutter=None)
        return PageMargins(
            left=_stored_length(margin, "left", None),  # required by the schema: no default
            right=_stored_length(margin, "right", None),
            top=_stored_length(margin, "top", None),
            bottom=_stored_length(margin, "bottom", None),
            header=_stored_length(margin, "header", 4252),  # the schema's defaults
            footer=_stored_length(margin, "footer", 4252),
            gutter=_stored_length(margin, "gutter", 0),
        )

    def set_page_margins(
        self,
        *,
        left: int | None = None,
        right: int | None = None,
        top: int | None = None,
        bottom: int | None = None,
        header: int | None = None,
        footer: int | None = None,
        gutter: int | None = None,
    ) -> None:
        margins = (("left", left), ("right", right), ("top", top), ("bottom", bottom), ("header", header),
                   ("footer", footer), ("gutter", gutter))
        for name, value in margins:
            if value is not None:
                _checked(name, value, 2**31 - 1, "page-size-value")
        margin = self._margin_element(create=True)
        if margin is None:
            return

        changed = False
        for name, value in margins:
            if value is None:
                continue
            safe_value = str(value)
            if margin.get(name) != safe_value:
                margin.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    # -- columns --------------------------------------------------------------
    def _column_control(self) -> ET.Element | None:
        """The ``hp:ctrl`` holding the section's own ``hp:colPr``.

        Hancom keeps it in the run that carries ``hp:secPr``; one is added
        right after ``hp:secPr`` when that run has none.
        """

        carrier = next(
            (run for run in self.section.element.iter(f"{_HP}run") if any(child is self.element for child in run)),
            None,
        )
        if carrier is None:
            return None
        for ctrl in carrier.findall(f"{_HP}ctrl"):
            if ctrl.find(f"{_HP}colPr") is not None:
                return ctrl
        ctrl = carrier.makeelement(f"{_HP}ctrl", {})
        carrier.insert(list(carrier).index(self.element) + 1, ctrl)
        _append_child(ctrl, f"{_HP}colPr", {
            "id": "", "type": "NEWSPAPER", "layout": "LEFT", "colCount": "1", "sameSz": "1", "sameGap": "0",
        })
        return ctrl

    def set_columns(
        self,
        col_count: int,
        *,
        col_type: str = "NEWSPAPER",
        layout: str = "LEFT",
        same_size: bool = True,
        same_gap: int = 0,
        column_widths: Sequence[tuple[int, int]] | None = None,
        separator_type: str | None = None,
        separator_width: str | None = None,
        separator_color: str | None = None,
    ) -> ET.Element | None:
        """Rewrite the section's own column layout in place.

        That is the ``hp:colPr`` next to ``hp:secPr``, which lays out the
        whole section. Any separator argument adds a column line; the others
        take Hancom's defaults (``SOLID``, ``0.12 mm``, ``#000000``). Returns
        the ``hp:ctrl`` holding it, or ``None`` when no run carries
        ``hp:secPr``.
        """

        if same_size:
            validate_column_gap(same_gap)  # checked before anything changes, as the separator below
        sizes = column_shares(column_widths) if column_widths and not same_size else []
        line = None
        if separator_type or separator_width or separator_color:
            # checked before anything changes: a refused value leaves the columns as they were
            line = {
                "type": separator_type or "SOLID",
                "width": normalize_line_width(separator_width or "0.12 mm"),
                "color": _normalize_color(separator_color) or "#000000",
            }
        ctrl = self._column_control()
        col_pr = None if ctrl is None else ctrl.find(f"{_HP}colPr")
        if ctrl is None or col_pr is None:
            return None
        col_pr.set("type", col_type)
        col_pr.set("layout", layout)
        col_pr.set("colCount", str(col_count))
        col_pr.set("sameSz", "1" if same_size else "0")
        col_pr.set("sameGap", str(same_gap) if same_size else "0")
        for child in list(col_pr):
            col_pr.remove(child)
        if line is not None:
            _append_child(col_pr, f"{_HP}colLine", line)
        for width, gap in sizes:
            _append_child(col_pr, f"{_HP}colSz", {"width": str(width), "gap": str(gap)})
        self.section.mark_dirty()
        return ctrl

    # -- numbering ----------------------------------------------------------
    @property
    def outline_shape_id_ref(self) -> str | None:
        """The id of the numbering this section draws its outline numbers with (개요 번호 모양,
        ``outlineShapeIDRef``) as written, ``None`` when the section names none. Read the
        definition with ``doc.styles.numbering(id)``; change a level with
        ``doc.styles.set_numbering_level(id, level, text=...)``."""
        value = (self.element.get("outlineShapeIDRef") or "").strip()
        return value or None

    @property
    def memo_shape_id_ref(self) -> str | None:
        """The memo shape (``hh:memoPr``) this section's memos are drawn with (``memoShapeIDRef``),
        ``None`` for Hancom's built-in one (``0``, or not written). Hancom keeps a memo's shape here, per
        section: every MEMO field it writes says ``MemoShapeIDRef=65535`` (Hangul 2024; the sections of
        ``hwpxlib_corpus/error__20251107__test`` point at memo shapes 1 and 2). Read the shape with
        ``doc.styles.memo_shape(id)``; make one with ``doc.styles.ensure_memo_shape(...)``.

        Set it to a memo shape's id (``None`` or ``"0"``: the built-in one). An id the header does
        not define is refused (``note-memo-shape-not-found``)."""

        value = (self.element.get("memoShapeIDRef") or "").strip()
        return None if value in ("", "0") else value

    @memo_shape_id_ref.setter
    def memo_shape_id_ref(self, value: "str | int | None") -> None:
        from ..errors import HwpxLookupError, argument_type_error

        if isinstance(value, bool) or not isinstance(value, (str, int, type(None))):
            raise argument_type_error("memo_shape_id_ref", value, "a memo shape id (str or int) or None")
        text = "0" if value is None else str(value).strip() or "0"
        if text != "0":
            document = getattr(self.section, "document", None)
            if document is None or document.memo_shape(text) is None:
                raise HwpxLookupError(
                    f"the header defines no memo shape {text!r}",
                    code="note-memo-shape-not-found",
                    context={"requested": text},
                    suggestion="Make one with doc.styles.ensure_memo_shape(...) and pass its id.",
                )
        if self.element.get("memoShapeIDRef") != text:
            self.element.set("memoShapeIDRef", text)
            self.section.mark_dirty()

    @property
    def start_numbers(self) -> StartNumbers:
        """Where the section's counts start (``hp:startNum``): pages, pictures, tables and
        equations, and the kind of page the section starts on; 0 goes on from the section
        before. The value ``doc.page.start_numbers()`` gives."""
        start_num = self.element.find(f"{_HP}startNum")
        if start_num is None:
            return StartNumbers(
                page_starts_on="BOTH",
                page=0,
                picture=0,
                table=0,
                equation=0,
            )
        return StartNumbers(
            page_starts_on=start_num.get("pageStartsOn", "BOTH"),
            page=_get_int_attr(start_num, "page", 0),
            picture=_get_int_attr(start_num, "pic", 0),
            table=_get_int_attr(start_num, "tbl", 0),
            equation=_get_int_attr(start_num, "equation", 0),
        )

    def set_start_numbers(
        self,
        *,
        page_starts_on: str | None = None,
        page: int | None = None,
        picture: int | None = None,
        table: int | None = None,
        equation: int | None = None,
    ) -> None:
        """Change where the section's counts start (:attr:`start_numbers`); a value left out stays.
        Numbers are 0..65535 (0: go on from the section before)."""
        numbers = (("page", page), ("pic", picture), ("tbl", table), ("equation", equation))
        for name, value in numbers:  # Hancom keeps each as 16 bits unsigned (0: go on from the section before)
            if value is not None:
                _checked(name, value, 0xFFFF, "page-number-value")
        start_num = self.element.find(f"{_HP}startNum")
        if start_num is None:
            start_num = _append_child(
                self.element,
                f"{_HP}startNum",
                {
                    "pageStartsOn": "BOTH",
                    "page": "0",
                    "pic": "0",
                    "tbl": "0",
                    "equation": "0",
                },
            )
            self.section.mark_dirty()

        changed = False
        if page_starts_on is not None and start_num.get("pageStartsOn") != page_starts_on:
            start_num.set("pageStartsOn", page_starts_on)
            changed = True

        for name, value in numbers:
            if value is None:
                continue
            safe_value = str(value)
            if start_num.get(name) != safe_value:
                start_num.set(name, safe_value)
                changed = True

        if changed:
            self.section.mark_dirty()

    # -- grid / visibility / line numbering ----------------------------------
    # ``<hp:grid>``, ``<hp:visibility>``, ``<hp:lineNumberShape>`` are direct
    # ``<hp:secPr>`` children (schema: ``SectionDefinitionType``) that ship on
    # every generated document (166/166 real-corpus files per the coverage
    # ledger) but previously had no edit API — only whatever the Skeleton
    # template happened to carry forward untouched.

    @property
    def grid(self) -> SectionGrid:
        element = self.element.find(f"{_HP}grid")
        if element is None:
            return SectionGrid(line_grid=0, char_grid=0, wonggoji_format=False)
        return SectionGrid(
            line_grid=_get_int_attr(element, "lineGrid", 0),
            char_grid=_get_int_attr(element, "charGrid", 0),
            wonggoji_format=_get_bool_attr(element, "wonggojiFormat", False),
        )

    def set_grid(
        self,
        *,
        line_grid: int | None = None,
        char_grid: int | None = None,
        wonggoji_format: bool | None = None,
    ) -> None:
        element = self.element.find(f"{_HP}grid")
        if element is None:
            element = _append_child(
                self.element,
                f"{_HP}grid",
                {"lineGrid": "0", "charGrid": "0", "wonggojiFormat": "0"},
            )
            self.section.mark_dirty()

        changed = False
        for name, value in (("lineGrid", line_grid), ("charGrid", char_grid)):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if wonggoji_format is not None:
            wonggoji_value = _bool_str(wonggoji_format)
            if _get_bool_attr(element, "wonggojiFormat", False) != wonggoji_format:
                element.set("wonggojiFormat", wonggoji_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def text_direction(self) -> str:
        """How the section's text runs (``hp:secPr/@textDirection``): ``"HORIZONTAL"``, ``"VERTICAL"``
        or ``"VERTICALALL"`` — the same words a table cell's ``text_direction`` reads."""

        return self.element.get("textDirection", "HORIZONTAL")

    @property
    def vertical_header_footer(self) -> bool:
        """Whether headers and footers are written vertically too (``hp:secPr/@textVerticalWidthHead``)."""

        return _get_bool_attr(self.element, "textVerticalWidthHead", False)

    def set_text_direction(
        self,
        direction: str | None = None,
        *,
        vertical_header_footer: bool | None = None,
    ) -> None:
        # Raw pass-through, no enum validation -- matches set_page_size's
        # orientation/gutter_type (validation for direction lives at the
        # doc.page.set_text_direction call site, same split as
        # _normalize_page_orientation does for orientation).
        changed = False
        if direction is not None and self.element.get("textDirection", "HORIZONTAL") != direction:
            self.element.set("textDirection", direction)
            changed = True
        if vertical_header_footer is not None:
            current = _get_bool_attr(self.element, "textVerticalWidthHead", False)
            if current != vertical_header_footer:
                self.element.set("textVerticalWidthHead", _bool_str(vertical_header_footer))
                changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def master_page_refs(self) -> tuple[str, ...]:
        """이 절이 참조하는 바탕쪽(``hp:masterPage/@idRef``) 목록.

        6.13 트레인㊻ -- 실제 예시(`error__20250808__...hwpx`)에서 이
        요소는 `hp:secPr`의 자식 시퀀스 맨 끝(pageBorderFill들 뒤)에
        온다 -- ``add_master_page_reference``가 그냥 append하는 이유.
        """
        return tuple(
            child.get("idRef", "")
            for child in self.element.findall(f"{_HP}masterPage")
        )

    def add_master_page_reference(self, master_page_id: "str | HwpxOxmlMasterPage") -> None:
        """바탕쪽 파트(``masterPageN``, id 나 ``MasterPage``)를 이 절에서 참조하도록 등록한다.

        중복 idRef는 다시 추가하지 않는다(멱등). ``masterPageCnt``를
        실제 자식 개수로 동기화한다 -- 실 예시 1건에서 `masterPageCnt="1"`
        이 `hp:masterPage` 자식 1개와 정확히 일치함을 확인했다.

        이 절이 같은 쪽(양쪽·홀수·짝수·마지막 쪽, 또는 같은 번호의 한 쪽)에
        이미 바탕쪽을 두고 있으면 ``HwpxValueError``
        (``master-page-pages-taken``)를 낸다.
        """
        id_ref = self._check_master_page_reference(master_page_id)
        if id_ref is None:
            return
        _append_child(self.element, f"{_HP}masterPage", {"idRef": id_ref})
        self.element.set("masterPageCnt", str(len(self.master_page_refs)))
        self.section.mark_dirty()

    def _check_master_page_reference(self, master_page_id: "str | HwpxOxmlMasterPage") -> str | None:
        """What :meth:`add_master_page_reference` refuses, without writing: the id to add, or ``None``
        when this section uses the master page already. ``doc.page.set_master_page(section="all")``
        asks every section first, so a section that refuses does not leave the ones before it changed."""

        id_ref = _master_page_id(master_page_id)
        if id_ref in self.master_page_refs:
            return None
        document = self.section.document
        if document is not None:
            from .master_page_authoring import refuse_pages_taken

            refuse_pages_taken(document, self.master_page_refs, id_ref)
        return id_ref

    def remove_master_page_reference(self, master_page_id: "str | HwpxOxmlMasterPage") -> bool:
        """이 절이 바탕쪽 *master_page_id* (id 나 ``MasterPage``)를 쓰는 연결(``hp:masterPage/@idRef``)을
        끊는다. 끊었으면 True.

        바탕쪽 파트는 그대로 둔다. ``masterPageCnt`` 를 남은 개수로 맞춘다.
        """
        wanted = _master_page_id(master_page_id)
        removed = False
        for child in list(self.element.findall(f"{_HP}masterPage")):
            if child.get("idRef", "") == wanted:
                self.element.remove(child)
                removed = True
        if removed:
            self.element.set("masterPageCnt", str(len(self.master_page_refs)))
            self.section.mark_dirty()
        return removed

    @property
    def visibility(self) -> SectionVisibility:
        element = self.element.find(f"{_HP}visibility")
        if element is None:
            return SectionVisibility(
                hide_first_header=False,
                hide_first_footer=False,
                hide_first_master_page=False,
                hide_first_page_num=False,
                hide_first_empty_line=False,
                show_line_number=False,
                border=None,
                fill=None,
            )
        return SectionVisibility(
            hide_first_header=_get_bool_attr(element, "hideFirstHeader", False),
            hide_first_footer=_get_bool_attr(element, "hideFirstFooter", False),
            hide_first_master_page=_get_bool_attr(element, "hideFirstMasterPage", False),
            hide_first_page_num=_get_bool_attr(element, "hideFirstPageNum", False),
            hide_first_empty_line=_get_bool_attr(element, "hideFirstEmptyLine", False),
            show_line_number=_get_bool_attr(element, "showLineNumber", False),
            border=element.get("border"),
            fill=element.get("fill"),
        )

    def set_visibility(
        self,
        *,
        hide_first_header: bool | None = None,
        hide_first_footer: bool | None = None,
        hide_first_master_page: bool | None = None,
        hide_first_page_num: bool | None = None,
        hide_first_empty_line: bool | None = None,
        show_line_number: bool | None = None,
        border: str | None = None,
        fill: str | None = None,
    ) -> None:
        element = self.element.find(f"{_HP}visibility")
        if element is None:
            element = _append_child(
                self.element,
                f"{_HP}visibility",
                {
                    "hideFirstHeader": "false",
                    "hideFirstFooter": "false",
                    "hideFirstMasterPage": "false",
                    "hideFirstPageNum": "false",
                    "hideFirstEmptyLine": "false",
                    "showLineNumber": "false",
                },
            )
            self.section.mark_dirty()

        changed = False
        for name, value in (
            ("hideFirstHeader", hide_first_header),
            ("hideFirstFooter", hide_first_footer),
            ("hideFirstMasterPage", hide_first_master_page),
            ("hideFirstPageNum", hide_first_page_num),
            ("hideFirstEmptyLine", hide_first_empty_line),
            ("showLineNumber", show_line_number),
        ):
            if value is None:
                continue
            if _get_bool_attr(element, name, False) != value:
                element.set(name, _bool_str(value))
                changed = True
        for name, text_value in (("border", border), ("fill", fill)):
            if text_value is None:
                continue
            if element.get(name) != text_value:
                element.set(name, text_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def line_number_shape(self) -> LineNumberShape:
        element = self.element.find(f"{_HP}lineNumberShape")
        if element is None:
            return LineNumberShape(
                restart_type=None, count_by=None, distance=None, start_number=None
            )
        return LineNumberShape(
            restart_type=_optional_int_attr(element, "restartType"),
            count_by=_optional_int_attr(element, "countBy"),
            distance=_optional_int_attr(element, "distance"),
            start_number=_optional_int_attr(element, "startNumber"),
        )

    def set_line_number_shape(
        self,
        *,
        restart_type: int | None = None,
        count_by: int | None = None,
        distance: int | None = None,
        start_number: int | None = None,
    ) -> None:
        # Hancom keeps the count step and the start as 16 bits unsigned, the distance as 32 bits
        shape = (("restartType", restart_type, 2**31 - 1), ("countBy", count_by, 0xFFFF),
                 ("distance", distance, 2**31 - 1), ("startNumber", start_number, 0xFFFF))
        for name, value, high in shape:
            if value is not None:
                _checked(name, value, high, "page-number-value")
        element = self.element.find(f"{_HP}lineNumberShape")
        if element is None:
            element = _append_child(self.element, f"{_HP}lineNumberShape", {})
            self.section.mark_dirty()

        changed = False
        for name, value, _high in shape:
            if value is None:
                continue
            safe_value = str(value)
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    # -- page border/fill -----------------------------------------------
    # ``<hp:pageBorderFill>`` can repeat up to 3 times (schema
    # ``maxOccurs="3"``), keyed by its own ``type`` attribute
    # (BOTH/EVEN/ODD) — same shape as header/footer page-type variants.

    def _page_border_fill_element(
        self, page_type: str = "BOTH", *, create: bool = False
    ) -> ET.Element | None:
        for element in self.element.findall(f"{_HP}pageBorderFill"):
            if element.get("type", "BOTH") == page_type:
                return element
        if not create:
            return None
        element = _append_child(self.element, f"{_HP}pageBorderFill", {"type": page_type})
        _append_child(element, f"{_HP}offset", {"left": "1417", "right": "1417", "top": "1417", "bottom": "1417"})
        self.section.mark_dirty()
        return element

    def page_border_fill(self, page_type: str = "BOTH") -> PageBorderFill | None:
        element = self._page_border_fill_element(page_type)
        if element is None:
            return None
        offset = element.find(f"{_HP}offset")
        return PageBorderFill(
            page_type=element.get("type", "BOTH"),
            border_fill_id_ref=element.get("borderFillIDRef"),
            text_border=element.get("textBorder"),
            header_inside=_get_bool_attr(element, "headerInside", False),
            footer_inside=_get_bool_attr(element, "footerInside", False),
            fill_area=element.get("fillArea"),
            offset_left=_get_int_attr(offset, "left", 1417) if offset is not None else 1417,
            offset_right=_get_int_attr(offset, "right", 1417) if offset is not None else 1417,
            offset_top=_get_int_attr(offset, "top", 1417) if offset is not None else 1417,
            offset_bottom=_get_int_attr(offset, "bottom", 1417) if offset is not None else 1417,
        )

    def set_page_border_fill(
        self,
        *,
        page_type: str = "BOTH",
        border_fill_id_ref: str | int | None = None,
        text_border: str | None = None,
        header_inside: bool | None = None,
        footer_inside: bool | None = None,
        fill_area: str | None = None,
        offset_left: int | None = None,
        offset_right: int | None = None,
        offset_top: int | None = None,
        offset_bottom: int | None = None,
    ) -> None:
        """Create or update the ``page_type`` (BOTH/EVEN/ODD) page border/fill.

        *page_type* selects which of up to 3 entries to touch — it is not a
        "leave unchanged" field like the rest. Everything else follows the
        established convention: omitted (``None``) keyword args leave the
        existing value alone. Hancom keeps each offset as 16 bits signed:
        one is refused unless it is from 0 to 32767.
        """

        _choice("page_type", page_type, PAGE_BORDER_FILL_TYPES, "page-border-fill-invalid")
        if fill_area is not None:
            _choice("fill_area", fill_area, PAGE_BORDER_FILL_AREAS, "page-border-fill-invalid")
        for name, value in (("offset_left", offset_left), ("offset_right", offset_right),
                            ("offset_top", offset_top), ("offset_bottom", offset_bottom)):
            if value is not None:
                _checked(name, value, 0x7FFF, "page-border-fill-invalid")
        element = self._page_border_fill_element(page_type, create=True)
        if element is None:  # pragma: no cover - defensive branch
            return

        changed = _apply_optional_attrs(
            element,
            (
                ("borderFillIDRef", None if border_fill_id_ref is None else str(border_fill_id_ref)),
                ("textBorder", text_border),
                ("fillArea", fill_area),
            ),
        )
        changed = (
            _apply_optional_bool_attrs(
                element,
                (("headerInside", header_inside), ("footerInside", footer_inside)),
            )
            or changed
        )
        changed = (
            self._apply_page_border_fill_offset(
                element, offset_left, offset_right, offset_top, offset_bottom
            )
            or changed
        )

        if changed:
            self.section.mark_dirty()

    def _apply_page_border_fill_offset(
        self,
        element: ET.Element,
        left: int | None,
        right: int | None,
        top: int | None,
        bottom: int | None,
    ) -> bool:
        offset_values = (("left", left), ("right", right), ("top", top), ("bottom", bottom))
        if not any(value is not None for _name, value in offset_values):
            return False

        offset = element.find(f"{_HP}offset")
        created = offset is None
        if offset is None:
            offset = _append_child(element, f"{_HP}offset",
                                   {"left": "1417", "right": "1417", "top": "1417", "bottom": "1417"})
        safe_pairs = tuple((name, None if value is None else str(value)) for name, value in offset_values)
        return _apply_optional_attrs(offset, safe_pairs) or created

    # -- footnote / endnote shape --------------------------------------
    # ``<hp:footNotePr>``/``<hp:endNotePr>`` share ``NoteShapeType``'s three
    # mandatory children (autoNumFormat/noteLine/noteSpacing) and each adds
    # its own numbering/placement vocabulary. Every setter here updates
    # exactly one nested block — the other four are never touched, so a
    # caller that only wants to change e.g. the separator line never
    # perturbs autoNumFormat/numbering/etc. on a real document (required for
    # safe round-tripping of Hancom-authored notes).

    _NOTE_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
        "footNotePr": {
            "numbering": {"type": "CONTINUOUS", "newNum": "1"},
            "placement": {"place": "EACH_COLUMN", "beneathText": "false"},
        },
        "endNotePr": {
            "numbering": {"type": "CONTINUOUS", "newNum": "1"},
            "placement": {"place": "END_OF_DOCUMENT", "beneathText": "false"},
        },
    }

    def _note_pr_element(self, tag: str, *, create: bool = False) -> ET.Element | None:
        element = self.element.find(f"{_HP}{tag}")
        if element is not None or not create:
            return element
        # NoteShapeType의 5개 자식 전부 minOccurs 생략(=1, 필수) — 하나라도
        # 빠지면 스키마 위반이라 생성 시 다섯 개를 한 번에 원자적으로 만든다.
        element = _append_child(self.element, f"{_HP}{tag}", {})
        _append_child(
            element, f"{_HP}autoNumFormat", {"type": "DIGIT", "suffixChar": ")", "supscript": "false"}
        )
        _append_child(
            element,
            f"{_HP}noteLine",
            {"length": "0", "type": "SOLID", "width": "0.12 mm", "color": "#000000"},
        )
        _append_child(
            element,
            f"{_HP}noteSpacing",
            {"betweenNotes": "850", "belowLine": "567", "aboveLine": "567"},
        )
        _append_child(element, f"{_HP}numbering", dict(self._NOTE_DEFAULTS[tag]["numbering"]))
        _append_child(element, f"{_HP}placement", dict(self._NOTE_DEFAULTS[tag]["placement"]))
        self.section.mark_dirty()
        return element

    def _note_shape(self, tag: str) -> NoteShape | None:
        parent = self._note_pr_element(tag)
        if parent is None:
            return None
        auto_num = parent.find(f"{_HP}autoNumFormat")
        note_line = parent.find(f"{_HP}noteLine")
        note_spacing = parent.find(f"{_HP}noteSpacing")
        numbering = parent.find(f"{_HP}numbering")
        placement = parent.find(f"{_HP}placement")
        return NoteShape(
            auto_num_format=NoteAutoNumFormat(
                type=(auto_num.get("type", "DIGIT") if auto_num is not None else "DIGIT"),
                user_char=(auto_num.get("userChar") if auto_num is not None else None),
                prefix_char=(auto_num.get("prefixChar") if auto_num is not None else None),
                suffix_char=(auto_num.get("suffixChar", ")") if auto_num is not None else ")"),
                supscript=(
                    _get_bool_attr(auto_num, "supscript", False) if auto_num is not None else False
                ),
            ),
            note_line=NoteLine(
                length=(_get_int_attr(note_line, "length", 0) if note_line is not None else 0),
                type=(note_line.get("type", "SOLID") if note_line is not None else "SOLID"),
                width=(note_line.get("width", "0.12 mm") if note_line is not None else "0.12 mm"),
                color=(note_line.get("color", "#000000") if note_line is not None else "#000000"),
            ),
            note_spacing=NoteSpacing(
                between_notes=(
                    _get_int_attr(note_spacing, "betweenNotes", 850) if note_spacing is not None else 850
                ),
                below_line=(
                    _get_int_attr(note_spacing, "belowLine", 567) if note_spacing is not None else 567
                ),
                above_line=(
                    _get_int_attr(note_spacing, "aboveLine", 567) if note_spacing is not None else 567
                ),
            ),
            numbering=NoteNumbering(
                type=(numbering.get("type", "CONTINUOUS") if numbering is not None else "CONTINUOUS"),
                new_num=(_get_int_attr(numbering, "newNum", 1) if numbering is not None else 1),
            ),
            placement=NotePlacement(
                place=(
                    placement.get("place", self._NOTE_DEFAULTS[tag]["placement"]["place"])
                    if placement is not None
                    else self._NOTE_DEFAULTS[tag]["placement"]["place"]
                ),
                beneath_text=(
                    _get_bool_attr(placement, "beneathText", False) if placement is not None else False
                ),
            ),
        )

    def _set_note_auto_num_format(
        self,
        tag: str,
        *,
        type: str | None = None,
        user_char: str | None = None,
        prefix_char: str | None = None,
        suffix_char: str | None = None,
        supscript: bool | None = None,
    ) -> None:
        if type is not None:
            type = number_format(type, note=True)
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}autoNumFormat") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        for name, value in (
            ("type", type),
            ("userChar", user_char),
            ("prefixChar", prefix_char),
            ("suffixChar", suffix_char),
        ):
            if value is not None and element.get(name) != value:
                element.set(name, value)
                changed = True
        if supscript is not None and _get_bool_attr(element, "supscript", False) != supscript:
            element.set("supscript", _bool_str(supscript))
            changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_line(
        self,
        tag: str,
        *,
        length: int | None = None,
        type: str | None = None,
        width: str | None = None,
        color: str | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}noteLine") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if length is not None:
            value = str(length)
            if element.get("length") != value:
                element.set("length", value)
                changed = True
        if type is not None and element.get("type") != type:
            element.set("type", type)
            changed = True
        if width is not None and element.get("width") != width:
            element.set("width", width)
            changed = True
        if color is not None and element.get("color") != color:
            element.set("color", color)
            changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_spacing(
        self,
        tag: str,
        *,
        between_notes: int | None = None,
        below_line: int | None = None,
        above_line: int | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}noteSpacing") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        for name, value in (
            ("betweenNotes", between_notes),
            ("belowLine", below_line),
            ("aboveLine", above_line),
        ):
            if value is None:
                continue
            safe_value = str(max(value, 0))
            if element.get(name) != safe_value:
                element.set(name, safe_value)
                changed = True
        if changed:
            self.section.mark_dirty()

    def _set_note_numbering(
        self,
        tag: str,
        *,
        type: str | None = None,
        new_num: int | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}numbering") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if type is not None and element.get("type") != type:
            element.set("type", type)
            changed = True
        if new_num is not None:
            value = str(max(new_num, 1))
            if element.get("newNum") != value:
                element.set("newNum", value)
                changed = True
        if changed:
            self.section.mark_dirty()
            # the notes of the kind are written with the numbers they have now (they kept the old ones)
            from .note_authoring import renumber_notes

            renumber_notes(self.section, tag[: -len("Pr")] if tag.endswith("Pr") else tag)

    def _set_note_placement(
        self,
        tag: str,
        *,
        place: str | None = None,
        beneath_text: bool | None = None,
    ) -> None:
        parent = self._note_pr_element(tag, create=True)
        element = parent.find(f"{_HP}placement") if parent is not None else None
        if element is None:  # pragma: no cover - defensive branch, schema-mandatory
            return
        changed = False
        if place is not None and element.get("place") != place:
            element.set("place", place)
            changed = True
        if beneath_text is not None and _get_bool_attr(element, "beneathText", False) != beneath_text:
            element.set("beneathText", _bool_str(beneath_text))
            changed = True
        if changed:
            self.section.mark_dirty()

    @property
    def footnote_shape(self) -> NoteShape | None:
        return self._note_shape("footNotePr")

    def set_footnote_auto_num_format(self, **kwargs: Any) -> None:
        self._set_note_auto_num_format("footNotePr", **kwargs)

    def set_footnote_note_line(self, **kwargs: Any) -> None:
        self._set_note_line("footNotePr", **kwargs)

    def set_footnote_note_spacing(self, **kwargs: Any) -> None:
        self._set_note_spacing("footNotePr", **kwargs)

    def set_footnote_numbering(self, **kwargs: Any) -> None:
        """Set how footnotes are numbered: ``type`` (``CONTINUOUS``, ``ON_SECTION``
        or ``ON_PAGE``) and ``new_num``, the first number.

        Hancom starts the numbers at ``new_num`` only with ``ON_SECTION``. With
        ``CONTINUOUS`` and ``ON_PAGE`` it numbers from 1; the value stays in the
        file.
        """
        self._set_note_numbering("footNotePr", **kwargs)

    def set_footnote_placement(self, **kwargs: Any) -> None:
        self._set_note_placement("footNotePr", **kwargs)

    @property
    def endnote_shape(self) -> NoteShape | None:
        return self._note_shape("endNotePr")

    def set_endnote_auto_num_format(self, **kwargs: Any) -> None:
        self._set_note_auto_num_format("endNotePr", **kwargs)

    def set_endnote_note_line(self, **kwargs: Any) -> None:
        self._set_note_line("endNotePr", **kwargs)

    def set_endnote_note_spacing(self, **kwargs: Any) -> None:
        self._set_note_spacing("endNotePr", **kwargs)

    def set_endnote_numbering(self, **kwargs: Any) -> None:
        """Set how endnotes are numbered: ``type`` (``CONTINUOUS``, ``ON_SECTION``
        or ``ON_PAGE``) and ``new_num``, the first number.

        Hancom starts the numbers at ``new_num`` only with ``ON_SECTION``. With
        ``CONTINUOUS`` and ``ON_PAGE`` it numbers from 1; the value stays in the
        file.
        """
        self._set_note_numbering("endNotePr", **kwargs)

    def set_endnote_placement(self, **kwargs: Any) -> None:
        self._set_note_placement("endNotePr", **kwargs)

    # -- header/footer helpers ---------------------------------------------
    def _apply_id_attributes(self, tag: str) -> tuple[str, ...]:
        base = "header" if tag == "header" else "footer"
        return ("idRef", f"{base}IDRef", f"{base}IdRef", f"{base}Ref")

    def _apply_elements(self, tag: str) -> list[ET.Element]:
        return self.element.findall(f"{_HP}{tag}Apply")

    def _apply_reference(self, apply: ET.Element, tag: str) -> str | None:
        candidate_keys = {name.lower() for name in self._apply_id_attributes(tag)}
        for attr, value in apply.attrib.items():
            if attr.lower() in candidate_keys and value:
                return value
        return None

    def _match_apply_for_element(self, tag: str, element: ET.Element | None) -> ET.Element | None:
        if element is None:
            return None

        target_id = element.get("id")
        if target_id:
            for apply in self._apply_elements(tag):
                if self._apply_reference(apply, tag) == target_id:
                    return apply

        page_type = element.get("applyPageType", "BOTH")
        for apply in self._apply_elements(tag):
            if apply.get("applyPageType", "BOTH") == page_type:
                return apply
        return None

    def _remove_header_footer_apply(
        self,
        tag: str,
        page_type: str,
        element: ET.Element | None = None,
    ) -> bool:
        apply = self._match_apply_for_element(tag, element)
        if apply is None:
            for candidate in self._apply_elements(tag):
                if candidate.get("applyPageType", "BOTH") == page_type:
                    apply = candidate
                    break
        if apply is None and element is not None:
            target_id = element.get("id")
            if target_id:
                for candidate in self._apply_elements(tag):
                    if self._apply_reference(candidate, tag) == target_id:
                        apply = candidate
                        break
        if apply is None:
            return False
        self.element.remove(apply)
        return True

    def _find_header_footer(self, tag: str, page_type: str) -> ET.Element | None:
        for element in self.element.findall(f"{_HP}{tag}"):
            if element.get("applyPageType", "BOTH") == page_type:
                return element
        return None

    def _first_paragraph_stories(self, tag: str, page_type: str) -> list[tuple[ET.Element, ET.Element, ET.Element]]:
        """``(run, hp:ctrl, story)`` for each *tag* story of *page_type* in the section's first paragraph.

        Hancom keeps a section's headers and footers there, in a run of their own after the
        settings. A control later in the body changes the header from its page on; it is not one
        of these.
        """

        found = []
        for run in self._first_paragraph_runs():
            for ctrl in run.findall(f"{_HP}ctrl"):
                story = ctrl.find(f"{_HP}{tag}")
                if story is not None and story.get("applyPageType", "BOTH") == page_type:
                    found.append((run, ctrl, story))
        return found

    def _story_to_write(
        self, tag: str, page_type: str
    ) -> tuple[ET.Element, tuple[ET.Element, ET.Element] | None]:
        """The one ``hp:ctrl`` story that *tag* on *page_type* pages is written to, and
        ``(run, hp:ctrl)`` for the control made for it when there was none (else ``None``).

        Hancom reads a header or footer only from an ``hp:ctrl`` in the body and saves it nowhere
        else: no story under ``hp:secPr`` and no ``hp:headerApply`` (all 68 Hangul-saved documents
        with one in the public corpus). python-hwpx up to 6.x also kept a copy under ``hp:secPr``
        with an ``hp:headerApply`` pointing at it; that copy of this page type goes, and its control
        copy is the one written. A second control of the same page type in the first paragraph
        goes too (Hancom draws only the last one on a page). A new control goes in the first run of
        the first paragraph, ahead of a field that starts there (Hancom drops a header or footer
        control inside a field's span) and, for ``BOTH``, ahead of the ``ODD``/``EVEN`` ones: Hancom
        draws the last applicable control on a page, so ``BOTH`` after ``ODD`` would hide it.
        """

        from .note_authoring import note_kinds_in, renumber_note_kinds

        changed = False
        gone: list[ET.Element] = []  # what is tidied away: the notes in it go, and the rest count again
        legacy = self._find_header_footer(tag, page_type)
        if legacy is not None:
            self._remove_header_footer_apply(tag, page_type, legacy)
            self.element.remove(legacy)
            gone.append(legacy)
            changed = True
        stories = self._first_paragraph_stories(tag, page_type)
        for run, ctrl, _story in stories[1:]:
            if len(ctrl) == 1:
                run.remove(ctrl)
                gone.append(ctrl)
                changed = True
        renumber_note_kinds(self.section, note_kinds_in(gone))
        created: tuple[ET.Element, ET.Element] | None = None
        if stories:
            story = stories[0][2]
            if not story.get("id"):
                story.set("id", _object_id(self.section._ids))
                changed = True
        else:
            run = self._header_footer_control_run()
            story_id = (legacy.get("id") if legacy is not None else None) or _object_id(self.section._ids)
            ctrl = run.makeelement(f"{_HP}ctrl", {})
            story = ctrl.makeelement(f"{_HP}{tag}", {"id": story_id, "applyPageType": page_type})
            ctrl.append(story)
            specific = [
                existing
                for existing in run.findall(f"{_HP}ctrl")
                if (other := existing.find(f"{_HP}{tag}")) is not None
                and other.get("applyPageType", "BOTH") != "BOTH"
            ]
            before = specific[0] if page_type == "BOTH" and specific else None
            run.insert(story_control_index(run, before), ctrl)
            created = (run, ctrl)
            changed = True
        if changed:
            self.section.mark_dirty()
        return story, created

    def _write_story(self, tag: str, page_type: str, fill: Any) -> HwpxOxmlSectionHeaderFooter:
        """Write *tag* for *page_type* pages with *fill* (given the story object) in its one place."""

        element, created = self._story_to_write(tag, page_type)
        wrapper = HwpxOxmlSectionHeaderFooter(element, self)
        try:
            fill(wrapper)
        except Exception:
            if created is not None and any(child is created[1] for child in created[0]):
                # a header or footer with no hp:subList keeps Hancom from opening the document
                created[0].remove(created[1])
            raise
        return wrapper

    def _header_footer_control_run(self) -> ET.Element:
        paragraph = self.section.element.find(f"{_HP}p")
        if paragraph is None:
            paragraph = _append_child(
                self.section.element,
                f"{_HP}p",
                paragraph_attributes(_paragraph_id(self.section._ids)),
            )
        run = paragraph.find(f"{_HP}run")
        if run is None:
            run = _append_child(paragraph, f"{_HP}run", {"charPrIDRef": "0"})
        return run

    def _first_paragraph_runs(self) -> list[ET.Element]:
        paragraph = self.section.element.find(f"{_HP}p")
        return [] if paragraph is None else paragraph.findall(f"{_HP}run")

    def _remove_header_footer_controls(self, tag: str, page_type: str | None = None) -> bool:
        """Remove the ``hp:ctrl`` stories of *tag*; only *page_type*'s when given."""
        removed = False
        for run in self.section.element.findall(f".//{_HP}run"):
            for ctrl in list(run.findall(f"{_HP}ctrl")):
                story = ctrl.find(f"{_HP}{tag}")
                if story is None:
                    continue
                if page_type is not None and story.get("applyPageType", "BOTH") != page_type:
                    continue
                run.remove(ctrl)
                removed = True
        return removed

    @property
    def headers(self) -> tuple[HwpxOxmlSectionHeaderFooter, ...]:
        """The section's headers, one per page type it has (``doc.page.headers()``'s value)."""
        return tuple(
            HwpxOxmlSectionHeaderFooter(element, self, self._match_apply_for_element("header", element))
            for element in _section_story_elements(self, "header")
        )

    @property
    def footers(self) -> tuple[HwpxOxmlSectionHeaderFooter, ...]:
        """The section's footers, one per page type it has (``doc.page.footers()``'s value)."""
        return tuple(
            HwpxOxmlSectionHeaderFooter(element, self, self._match_apply_for_element("footer", element))
            for element in _section_story_elements(self, "footer")
        )

    def header(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        """The header drawn on *page_type* pages (``BOTH``, ``EVEN``, ``ODD``, ...), or ``None``."""

        return self._get_story("header", page_type)

    def footer(self, page_type: str = "BOTH") -> Optional[HwpxOxmlSectionHeaderFooter]:
        """The footer drawn on *page_type* pages (``BOTH``, ``EVEN``, ``ODD``, ...), or ``None``."""

        return self._get_story("footer", page_type)

    def _get_story(self, kind: str, page_type: str) -> Optional[HwpxOxmlSectionHeaderFooter]:
        from ..errors import HwpxValueError

        matches = [s for s in _section_story_elements(self, kind)
                   if s.get("applyPageType", "BOTH") == page_type]
        if len(matches) > 1:
            raise HwpxValueError(
                "multiple stories match the page type", code="story-ambiguous",
                suggestion="Inspect the complete story list and select one native ID.",
            )
        if not matches:
            return None
        element = matches[0]
        return HwpxOxmlSectionHeaderFooter(element, self, self._match_apply_for_element(kind, element))

    # The header and footer setters write the one ``hp:ctrl`` story Hancom reads and saves
    # (see :meth:`_story_to_write`); up to 6.x python-hwpx wrote a second copy under ``hp:secPr``.

    # What is to be written is checked before the story is looked for: finding it also tidies the
    # section (a second header for the same pages goes), and a refused text or content used to leave
    # the section tidied -- a header gone -- with nothing written.
    def set_header_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        _require_text(text)
        return self._write_story("header", page_type, lambda story: setattr(story, "text", text))

    def set_footer_text(self, text: str, page_type: str = "BOTH") -> HwpxOxmlSectionHeaderFooter:
        _require_text(text)
        return self._write_story("footer", page_type, lambda story: setattr(story, "text", text))

    def set_header_content(
        self,
        content: Sequence[Mapping[str, Any]],
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        HwpxOxmlSectionHeaderFooter._check_content(content)
        return self._write_story("header", page_type, lambda story: story.set_content(content))

    def set_footer_content(
        self,
        content: Sequence[Mapping[str, Any]],
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        HwpxOxmlSectionHeaderFooter._check_content(content)
        return self._write_story("footer", page_type, lambda story: story.set_content(content))

    def remove_header(self, page_type: str = "BOTH") -> None:
        from .note_authoring import note_kinds_in, renumber_note_kinds

        element = self._find_header_footer("header", page_type)
        # the notes in what goes leave the count: looked for before, counted again after
        note_kinds = note_kinds_in([
            story for story in self.section.element.iterfind(f".//{_HP}run/{_HP}ctrl/{_HP}header")
            if page_type is None or story.get("applyPageType", "BOTH") == page_type
        ] + ([element] if element is not None else []))
        removed = False
        if element is not None:
            self.element.remove(element)
            removed = True
        if self._remove_header_footer_apply("header", page_type, element):
            removed = True
        if self._remove_header_footer_controls("header", page_type):
            removed = True
        if removed:
            self.section.mark_dirty()
            renumber_note_kinds(self.section, note_kinds)

    def remove_footer(self, page_type: str = "BOTH") -> None:
        from .note_authoring import note_kinds_in, renumber_note_kinds

        element = self._find_header_footer("footer", page_type)
        # the notes in what goes leave the count: looked for before, counted again after
        note_kinds = note_kinds_in([
            story for story in self.section.element.iterfind(f".//{_HP}run/{_HP}ctrl/{_HP}footer")
            if page_type is None or story.get("applyPageType", "BOTH") == page_type
        ] + ([element] if element is not None else []))
        removed = False
        if element is not None:
            self.element.remove(element)
            removed = True
        if self._remove_header_footer_apply("footer", page_type, element):
            removed = True
        if self._remove_header_footer_controls("footer", page_type):
            removed = True
        if removed:
            self.section.mark_dirty()
            renumber_note_kinds(self.section, note_kinds)
