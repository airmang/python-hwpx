# SPDX-License-Identifier: Apache-2.0
"""Markdown → HWPX: write a small, common Markdown subset into a document.

``markdown_export`` goes one way (HWPX → Markdown); this module goes the other.
It knows headings, paragraphs, lists, pipe tables and bold/italic.

One named look ships with the library, ``"report"``
(:meth:`MarkdownStyle.report`): a title in a banner with colour strips,
section headings in a numbered box, ruled tables, report typefaces and a page
number. A new document (:func:`from_markdown`) takes it unless another style
is given, so the first document a newcomer makes looks like a finished report.
Markdown added to a document that exists (:func:`append_markdown`) takes the
plain look (``"plain"``, :class:`MarkdownStyle` as it is) unless a style is
given, so that document keeps its own look. Everything a look does is a
:class:`MarkdownStyle` field.
Other genres (공문·가정통신문 …) stay with the application layer, which passes
its own :class:`MarkdownStyle`; the library holds no knowledge of what such a
document must contain.

Supported subset:

- ``#`` ~ ``######`` headings and Setext headings (``제목`` over ``===`` or
  ``---``). ``#####``/``######`` are drawn like ``####`` but numbered as levels
  of their own. Each heading takes the outline style of its level (``개요 1``
  …), so a table of contents and Hancom's outline find it; see
  :func:`from_markdown` for how its number is kept from being drawn twice.
- paragraphs (consecutive lines join with a space; two trailing spaces or a
  trailing ``\\`` is a line break)
- ``-``/``*``/``+`` bullets and ``1.``/``1)`` numbered lists, nested by
  indentation, as real Hancom lists numbered ``1.``, ``가.``, ``1)``, ``가)``,
  ``(1)``, ``(가)``, ``①`` by depth, as Hancom numbers a new list; ``- [ ]`` and
  ``- [x]`` items start with ``☐`` and ``☑``
- pipe tables, with or without the outer ``|``; a row followed by a ``|---|``
  separator is the header row (bold, shaded, centred, repeated on each page the
  table runs onto); ``:---``/``:---:``/``---:`` in the separator align a
  column; columns are as wide as their text needs; ``<br>`` in a cell is a
  line break
- inline ``**bold**``/``__bold__``, ``*italic*``/``_italic_``, ``***both***``,
  ``~~strike~~``, ``` `code` ``` (in ``MarkdownStyle.code_font``),
  ``[text](url)``, ``[text][ref]`` and ``<https://…>`` (hyperlinks), ``[^1]``
  with its ``[^1]: …`` definition (a footnote), ``\\`` escapes
- ``![description](path)``: a picture, read from a file under the folder given
  as ``base_dir``, with the description as its caption
- fenced code blocks become one paragraph per block in the code typeface, every
  character and line kept as written
- ``>`` block quotes are indented paragraphs (lists, code and tables in them too)

Rules (``---``) are dropped. HTML tags are kept as text. Unknown Markdown never
raises: what is not carried over (a picture that cannot be read, an HTML tag, a
footnote without its definition …) is named in one ``UserWarning`` per call.

New paragraphs never inherit the previous paragraph's style, so a heading or a
list item does not hand its outline or list numbering to the paragraph after it.
"""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..document import HwpxDocument
    from ..oxml import HwpxOxmlParagraph

__all__ = ["MarkdownStyle", "append_markdown", "from_markdown"]


@dataclass(frozen=True)
class MarkdownStyle:
    """How :func:`append_markdown` draws each Markdown construct.

    The default is a neutral document look: ``#`` 16pt bold, ``##`` 12pt bold,
    ``###`` 11pt bold, ``####`` 10pt bold, body text at the document's base
    size, and a light grey, centred header row in tables. Sizes are points;
    ``None`` keeps the document's base character shape.

    ``table_fit_columns`` shares the table's width out by what each column's
    longest line needs, so a column of short labels is narrow and the text
    column wide; ``False`` gives every column the same width.
    ``table_header_align`` aligns header cells whose column has no alignment of
    its own in the Markdown (``"center"``, ``"left"``, ``"right"`` or ``None``
    to leave them as body cells are).

    ``title_align``, ``title_rule`` and ``title_space_after_pt`` draw ``#``
    apart from the other headings. ``heading_numbers`` puts a number before
    each heading of a level: one of ``"1."``, ``"가."``, ``"1)"``, ``"가)"``,
    ``"(1)"``, ``"(가)"``, ``"①"``, ``"Ⅰ."`` per level, ``None`` for no number.
    A level's numbers start again under each heading above it, and a heading
    that already starts with a number of its own (``## 1. 개요``) is left as it
    is. ``bullet_chars`` gives the bullet for each list depth (the last one
    repeats); ``bullet_char`` is one bullet for every depth. Each list depth
    below the first is indented by ``list_indent_mm`` (``None``: one and a half
    characters of the body size; ``0``: no indent). ``table_size`` is
    the size of text in tables (``None``: ``body_size``). ``page_number`` puts
    the page number at the bottom centre of a document made by
    :func:`from_markdown`; :func:`append_markdown` never touches the footer of
    the document it is given. ``page_number_side`` is a character drawn on each
    side of it (``"-"`` gives ``- 1 -``).

    ``heading_bold`` is one value for every heading or four, one per level.
    ``heading_fonts`` (per level), ``body_font`` and ``table_font`` name the
    typefaces; ``None`` keeps the document's. A heading without a font of its
    own takes ``body_font``. ``heading_indents_mm`` moves the headings of a
    level right, with the paragraphs under them, and ``list_first_indent_mm``
    the first list depth (deeper ones add ``list_indent_mm`` each).

    ``title_look="banner"`` draws ``#`` in a filled box (``banner_fill``) the
    width of the text, with two colour strips above and two below
    (``banner_colors``: top left, top right, bottom left, bottom right).
    ``section_look="box"`` draws ``##`` as a filled cell holding the heading's
    number and, next to it, the heading with a line under it
    (``section_colors``: the cell's fill, the lines, the heading's text). A
    number the heading carries itself (``## Ⅱ. 현황``) goes in the cell.
    ``table_look="ruled"`` draws tables open at the sides, with a heavy line
    above and below and a double line under the header row.
    ``table_row_height_mm`` is the least height of a table row.
    ``page_margins_mm`` is ``(left, right, top, bottom)`` or, with the header
    and footer margins after them, six values; like ``page_number`` it applies
    to a document made by :func:`from_markdown` only.

    ``byline_size``, ``byline_font`` and ``byline_bold`` draw the byline, the
    right-aligned line under the title that :func:`from_markdown` takes as
    ``byline=``; ``None`` is the body's size or typeface.

    ``sub_bullet_chars`` gives the bullets of a list under a ``####`` heading
    (empty: ``bullet_chars``). ``note_size`` and ``note_font`` draw a note, a
    paragraph that starts with ``※``. ``table_align="auto"`` aligns the body
    cells of a table by what they hold: a column whose cells each fit on one
    line is centred and one that wraps reads from the left; in a table of two
    columns the first is spread over its width, as labels are, and the second
    reads from the left; a column the Markdown aligns itself is left to it.
    ``list_fit_spacing`` keeps a list item that runs a little past its line on
    one line by narrowing its letter spacing, by that many percent at most
    (``0``: never). An item that would need more wraps as it is.

    ``code_font`` is the typeface of code, inline and fenced; ``None`` sets
    code in the text's own. The default, 돋움체, is a fixed-width face that
    Korean Windows ships.
    """

    heading_sizes: tuple[float, float, float, float] = (16.0, 12.0, 11.0, 10.0)
    heading_bold: bool | tuple[bool, bool, bool, bool] = True
    heading_space_before_pt: float | None = 6.0
    heading_space_after_pt: float | None = 3.0
    body_size: float | None = None
    table_header_shading: str | None = "#D9D9D9"
    table_header_bold: bool = True
    table_header_align: str | None = "center"
    table_fit_columns: bool = True
    bullet_char: str | None = None
    bullet_chars: tuple[str, ...] = ()
    list_indent_mm: float | None = None
    title_align: str | None = None
    title_rule: bool = False
    title_space_after_pt: float | None = None
    heading_numbers: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None)
    table_size: float | None = None
    page_number: bool = False
    page_number_side: str | None = None
    heading_fonts: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None)
    body_font: str | None = None
    table_font: str | None = None
    heading_indents_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    list_first_indent_mm: float | None = None
    title_look: str = "plain"
    banner_colors: tuple[str, str, str, str] = ("#0099FF", "#FFCC00", "#339900", "#FF3300")
    banner_fill: str = "#EFEFEF"
    section_look: str = "plain"
    section_colors: tuple[str, str, str] = ("#000066", "#88A1EB", "#1B1760")
    table_look: str = "grid"
    table_row_height_mm: float | None = None
    page_margins_mm: tuple[float, ...] | None = None
    byline_size: float | None = None
    byline_font: str | None = None
    byline_bold: bool = False
    sub_bullet_chars: tuple[str, ...] = ()
    note_size: float | None = None
    note_font: str | None = None
    table_align: str | None = None
    list_fit_spacing: int = 0
    code_font: str | None = "돋움체"

    @classmethod
    def report(cls) -> MarkdownStyle:
        """The ``"report"`` look: a Korean office report as schools and offices write it.

        ``#`` is the title, 21pt in a grey banner with colour strips above and
        below. ``##`` is a section: its number (``Ⅰ``, ``Ⅱ`` …) in a navy cell
        and the heading beside it, navy, with a line under it. ``###`` and
        ``####`` are numbered ``1.`` and ``가.``. Body text is 12pt 휴먼명조
        with ``□``, ``-``, ``·`` bullets by depth; headings are HY헤드라인M.
        Tables are 12pt 한컴산뜻돋움, open at the sides, with a pale blue
        header row over a double line. The page has 20 mm margins (15 mm at the
        bottom) and ``- 1 -`` at the bottom centre. A byline is 13pt bold
        한컴산뜻돋움. Hancom ships these typefaces; where one is missing the
        viewer substitutes its own.
        """

        return cls(
            heading_sizes=(21.0, 16.0, 14.0, 12.0),
            heading_bold=(True, True, False, False),
            heading_fonts=("HY헤드라인M", "HY헤드라인M", "HY헤드라인M", None),
            heading_space_before_pt=12.0,
            heading_space_after_pt=3.0,
            heading_numbers=(None, "Ⅰ.", "1.", "가."),
            heading_indents_mm=(0.0, 0.0, 0.0, 4.2),
            body_size=12.0,
            body_font="휴먼명조",
            bullet_chars=("□", "-", "·"),
            list_first_indent_mm=5.3,
            list_indent_mm=3.5,
            title_look="banner",
            title_space_after_pt=10.0,
            section_look="box",
            table_look="ruled",
            table_size=12.0,
            table_font="한컴산뜻돋움",
            table_header_shading="#DFE6F7",
            table_row_height_mm=9.2,
            page_margins_mm=(20.0, 20.0, 20.0, 15.0, 10.0, 10.0),
            page_number=True,
            page_number_side="-",
            byline_size=13.0,
            byline_font="한컴산뜻돋움",
            byline_bold=True,
            sub_bullet_chars=("◦", "-", "·"),
            note_size=10.0,
            note_font="한컴산뜻돋움",
            table_align="auto",
            list_fit_spacing=8,
        )

    def __post_init__(self) -> None:
        from ..errors import HwpxValueError

        if len(self.heading_sizes) != 4 or any(size <= 0 for size in self.heading_sizes):
            raise HwpxValueError(
                "heading_sizes must be four positive point sizes (# to ####)",
                code="text-markdown-style-invalid",
                context={"heading_sizes": tuple(self.heading_sizes)},
                suggestion="Give four positive point sizes, one per heading level # to ####.",
            )
        if self.body_size is not None and self.body_size <= 0:
            raise HwpxValueError(
                "body_size must be positive",
                code="text-markdown-style-invalid",
                context={"body_size": self.body_size},
                suggestion="Give a positive point size, or None to keep the document's body size.",
            )
        if self.table_header_align not in (None, "left", "center", "right"):
            raise HwpxValueError(
                "table_header_align must be 'left', 'center', 'right' or None",
                code="text-markdown-style-invalid",
                context={"table_header_align": self.table_header_align},
                suggestion="Use 'center', 'left' or 'right', or None to leave header cells as body cells are.",
            )
        if self.title_align not in (None, "left", "center", "right"):
            raise HwpxValueError(
                "title_align must be 'left', 'center', 'right' or None",
                code="text-markdown-style-invalid",
                context={"title_align": self.title_align},
                suggestion="Use 'center', 'left' or 'right', or None to leave the title as the body is aligned.",
            )
        if len(self.heading_numbers) != 4 or any(
            form is not None and form not in _NUMBER_FORMS for form in self.heading_numbers
        ):
            raise HwpxValueError(
                "heading_numbers must be four number forms (# to ####), each None or one of " + ", ".join(_NUMBER_FORMS),
                code="text-markdown-style-invalid",
                context={"heading_numbers": tuple(self.heading_numbers)},
                suggestion="Give four entries, one per heading level, each None or one of: " + ", ".join(_NUMBER_FORMS),
            )
        if any(not isinstance(char, str) or len(char) != 1 for char in self.bullet_chars):
            raise HwpxValueError(
                "bullet_chars must be single characters, one per list depth",
                code="text-markdown-style-invalid",
                context={"bullet_chars": tuple(self.bullet_chars)},
                suggestion="Give one character per list depth, for example ('○', '-', '·').",
            )
        for name in (
            "table_size",
            "title_space_after_pt",
            "list_indent_mm",
            "list_first_indent_mm",
            "table_row_height_mm",
            "byline_size",
            "note_size",
        ):
            value = getattr(self, name)
            positive = name in ("table_size", "table_row_height_mm", "byline_size", "note_size")
            if value is not None and (value < 0 or (value == 0 and positive)):
                raise HwpxValueError(
                    f"{name} must be positive" if positive else f"{name} must not be negative",
                    code="text-markdown-style-invalid",
                    context={name: value},
                    suggestion="Give a positive number, or None for the default.",
                )
        self._check_looks()

    def _check_looks(self) -> None:
        from ..errors import HwpxValueError

        def refuse(name: str, message: str, suggestion: str) -> None:
            raise HwpxValueError(
                message,
                code="text-markdown-style-invalid",
                context={name: repr(getattr(self, name))},
                suggestion=suggestion,
            )

        for name, allowed in (
            ("title_look", ("plain", "banner")),
            ("section_look", ("plain", "box")),
            ("table_look", ("grid", "ruled")),
            ("table_align", (None, "auto")),
        ):
            if getattr(self, name) not in allowed:
                names = ", ".join(str(value) for value in allowed)
                refuse(name, f"{name} must be one of: {names}", f"Use one of: {names}.")
        for name, lengths, text in (
            ("heading_fonts", (4,), True),
            ("heading_indents_mm", (4,), False),
            ("banner_colors", (4,), True),
            ("section_colors", (3,), True),
            ("page_margins_mm", (4, 6), False),
        ):
            values = getattr(self, name)
            if values is None and name == "page_margins_mm":
                continue
            good = isinstance(values, tuple) and len(values) in lengths
            for value in values if good else ():
                if text:
                    unset = value is None and name == "heading_fonts"
                    good = good and (unset or (isinstance(value, str) and bool(value.strip())))
                else:
                    good = good and not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0
            if not good:
                refuse(
                    name,
                    f"{name} must be a tuple of {' or '.join(str(length) for length in lengths)} "
                    + ("names" if text else "numbers that are not negative"),
                    "See MarkdownStyle for what each value of this field is.",
                )
        bold = self.heading_bold
        if not isinstance(bold, bool) and not (
            isinstance(bold, tuple) and len(bold) == 4 and all(isinstance(value, bool) for value in bold)
        ):
            refuse(
                "heading_bold",
                "heading_bold must be True, False or four of them (# to ####)",
                "Give one bool for every heading, or a tuple of four, one per level.",
            )
        side = self.page_number_side
        if side is not None and (not isinstance(side, str) or len(side) != 1):
            refuse(
                "page_number_side",
                "page_number_side must be one character or None",
                "Give the character drawn on each side of the page number, for example '-'.",
            )
        if any(not isinstance(char, str) or len(char) != 1 for char in self.sub_bullet_chars):
            refuse(
                "sub_bullet_chars",
                "sub_bullet_chars must be single characters, one per list depth",
                "Give one character per list depth, for example ('◦', '-', '·').",
            )
        fit = self.list_fit_spacing
        if isinstance(fit, bool) or not isinstance(fit, int) or not 0 <= fit <= _FIT_SPACING_MOST:
            refuse(
                "list_fit_spacing",
                f"list_fit_spacing must be a whole percent from 0 to {_FIT_SPACING_MOST}",
                "Give how far the letter spacing may be narrowed, in percent; 0 never narrows it.",
            )
        for name in ("body_font", "table_font", "byline_font", "note_font", "code_font", "banner_fill"):
            value = getattr(self, name)
            if (value is not None or name == "banner_fill") and (not isinstance(value, str) or not value.strip()):
                refuse(name, f"{name} must be a name that is not empty", "Name a typeface, or a colour as #RRGGBB.")


# --------------------------------------------------------------------------
# Heading numbers

_GANADA_INITIALS = (0, 2, 3, 5, 6, 7, 9, 11, 12, 14, 15, 16, 17, 18)  # 가 나 다 라 마 바 사 아 자 차 카 타 파 하
_GANADA_VOWELS = (0, 4, 8, 13, 18, 20)  # 가 거 고 구 그 기: the manual's order once 하 is passed


def _ganada(number: int) -> str:
    """가, 나, … 하, 거, 너, … for 1, 2, …; a plain number once the syllables run out."""

    index = number - 1
    if not 0 <= index < len(_GANADA_INITIALS) * len(_GANADA_VOWELS):
        return str(number)
    vowel, initial = divmod(index, len(_GANADA_INITIALS))
    return chr(0xAC00 + (_GANADA_INITIALS[initial] * 21 + _GANADA_VOWELS[vowel]) * 28)


def _roman(number: int) -> str:
    return chr(0x2160 + number - 1) if 1 <= number <= 12 else str(number)


def _circled(number: int) -> str:
    return chr(0x2460 + number - 1) if 1 <= number <= 20 else f"({number})"


_NUMBER_FORMS = {
    "1.": lambda number: f"{number}.",
    "가.": lambda number: f"{_ganada(number)}.",
    "1)": lambda number: f"{number})",
    "가)": lambda number: f"{_ganada(number)})",
    "(1)": lambda number: f"({number})",
    "(가)": lambda number: f"({_ganada(number)})",
    "①": _circled,
    "Ⅰ.": lambda number: f"{_roman(number)}.",
}
#: A heading that already carries a number of its own: "1. 개요", "3.1 범위", "가. 목적", "A. 배경", "Ⅱ. 현황",
#: "(1) …", "① …", "제2장 …".
_OWN_NUMBER = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2})+\.?\s|\d{1,2}[.)]\s|[가나다라마바사아자차카타파하][.)]\s|[A-Za-z][.)]\s"
    r"|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+[.\s]|[IVX]+\.\s"
    r"|\(\d{1,2}\)|\([가나다라마바사아자차카타파하]\)|[①-⑳]|제\s*\d+\s*[장절관조항])"
)
#: The order Korean documents number their levels in. ``#####`` and ``######`` take the forms after the one
#: ``####`` takes, so the report look numbers them ``1)`` and ``가)``; a look whose ``####`` is not in this order,
#: or has no number, leaves them unnumbered.
_FORM_ORDER = ("Ⅰ.", "1.", "가.", "1)", "가)", "(1)", "(가)", "①")
#: The deepest heading level: ``######``.
_HEADING_LEVELS = 6


def _number_value(label: str, form: str) -> int | None:
    """The number *label* shows in *form* (``"Ⅲ"`` or ``"Ⅲ. 현황"`` is 3 in ``"Ⅰ."``), or ``None``."""

    make = _NUMBER_FORMS[form]
    label = label.strip()
    for number in range(1, 100):
        shown = make(number)
        if label in (shown, shown.removesuffix(".")) or label.startswith(shown + " "):
            return number
    return None
#: Names :func:`append_markdown` and :func:`from_markdown` take in place of a style.
_NAMED_STYLES = {"report": MarkdownStyle.report, "보고서": MarkdownStyle.report, "plain": MarkdownStyle}


def _resolve_style(style: MarkdownStyle | str | None, default: str = "plain") -> MarkdownStyle:
    """*style* as a :class:`MarkdownStyle`; ``None`` is the look named *default*."""

    if style is None:
        style = default
    if isinstance(style, MarkdownStyle):
        return style
    maker = _NAMED_STYLES.get(style) if isinstance(style, str) else None
    if maker is None:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unknown Markdown style {style!r}",
            code="text-markdown-style-invalid",
            context={"style": style, "known": sorted(_NAMED_STYLES)},
            suggestion="Pass a MarkdownStyle, or a name: 'report' (also '보고서') or 'plain'.",
        )
    return maker()


# --------------------------------------------------------------------------
# Inline: text → [(text, bold, italic)]

_ESCAPABLE = set("\\`*_{}[]()#+-.!|>~<")
_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+[\"'(][^\"')]*[\"')])?\s*\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
_NOTE_REF = re.compile(r"\[\^([^\]\s]+)\]")
_AUTOLINK = re.compile(r"<((?:https?|ftp)://[^\s<>]+|mailto:[^\s<>]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)>")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
#: An HTML tag other than ``<br>``, or an HTML comment: kept as text, and named in the warning.
_HTML_TAG = re.compile(r"<!--.*?-->|</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")

Segment = tuple[str, bool, bool]


@dataclass(frozen=True)
class _Span:
    """A piece of inline text and what it is: emphasis, code, a link, a footnote reference or a picture."""

    text: str
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False
    link: str | None = None
    #: A footnote reference: the label of its definition (the text is empty).
    note: str | None = None
    #: A picture: where it is (the text is its description).
    image: str | None = None


@dataclass
class _Refs:
    """What the Markdown defines apart from where it is used: footnotes and link references."""

    notes: dict[str, str] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)


def _underscore_closes(text: str, start: int) -> bool:
    """Whether a ``_`` at or after *start* can close an ``_italic_`` (not inside a word such as ``a_b``)."""

    end = text.find("_", start)
    while end != -1:
        after = text[end + 1 : end + 2]
        if not text[end - 1].isspace() and not after.isalnum() and after != "_":
            return True
        end = text.find("_", end + 1)
    return False


def _spans(text: str, refs: _Refs | None = None, *, link: str | None = None) -> list[_Span]:
    """Split *text* into :class:`_Span` pieces.

    A marker opens only when its closer appears later; an unmatched marker is
    kept as text. Code is kept exactly as written.
    """

    spans: list[_Span] = []
    buffer: list[str] = []
    bold = italic = strike = False
    italic_mark = "*"

    def add(span: _Span) -> None:
        last = spans[-1] if spans else None
        if (
            last is not None
            and span.note is None
            and span.image is None
            and last.note is None
            and last.image is None
            and replace(last, text="") == replace(span, text="")
        ):
            spans[-1] = replace(last, text=last.text + span.text)
        else:
            spans.append(span)

    def flush() -> None:
        if buffer:
            add(_Span("".join(buffer), bold, italic, strike, link=link))
            buffer.clear()

    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            buffer.append(text[i + 1])
            i += 2
            continue
        if char == "`":
            ticks = len(text) - len(text[i:].lstrip("`")) - i
            fence = "`" * ticks
            end = text.find(fence, i + ticks)
            while end != -1 and text[end + ticks : end + ticks + 1] == "`":  # a longer run does not close it
                end = text.find(fence, end + ticks + 1)
            if end == -1:
                buffer.append(fence)
                i += ticks
                continue
            code = text[i + ticks : end]
            if len(code) > 2 and code[0] == code[-1] == " " and code.strip():
                code = code[1:-1]
            flush()
            add(_Span(code, bold, italic, strike, code=True, link=link))
            i = end + ticks
            continue
        if char == "!" and text.startswith("![", i):
            match = _LINK.match(text, i + 1)
            if match:
                flush()
                add(_Span(match.group(1), image=match.group(2)))
                i = match.end()
                continue
        if char == "[":
            note = _NOTE_REF.match(text, i)
            if note and refs is not None and note.group(1) in refs.notes:
                flush()
                add(_Span("", note=note.group(1)))
                i = note.end()
                continue
            target: str | None = None
            match = _LINK.match(text, i) if link is None else None
            if match:
                target = match.group(2)
            elif link is None and refs is not None and refs.links:
                match = _REF_LINK.match(text, i)
                if match:
                    target = refs.links.get((match.group(2) or match.group(1)).strip().lower())
                    if target is None:
                        match = None
            if match:
                flush()
                for inner in _spans(match.group(1), refs, link=target or None):
                    add(replace(inner, bold=inner.bold or bold, italic=inner.italic or italic, strike=inner.strike or strike))
                i = match.end()
                continue
        if char == "<" and link is None:
            auto = _AUTOLINK.match(text, i)
            if auto:
                flush()
                url = auto.group(1)
                shown = url.removeprefix("mailto:")
                if "://" not in url and not url.startswith("mailto:"):
                    url = "mailto:" + url
                add(_Span(shown, bold, italic, strike, link=url))
                i = auto.end()
                continue
        marker = text[i : i + 2]
        if marker in ("**", "__"):
            opens = not bold and i + 2 < n and not text[i + 2].isspace() and text.find(marker, i + 2) > i + 2
            if bold or opens:
                flush()
                bold = not bold
                i += 2
                continue
        if marker == "~~":
            opens = not strike and i + 2 < n and not text[i + 2].isspace() and text.find("~~", i + 2) > i + 2
            if strike or opens:
                flush()
                strike = not strike
                i += 2
                continue
        if char == "*" and (not italic or italic_mark == "*"):
            opens = not italic and i + 1 < n and not text[i + 1].isspace() and text.find("*", i + 1) > i + 1
            if italic or opens:
                flush()
                italic, italic_mark = not italic, "*"
                i += 1
                continue
        if char == "_" and (not italic or italic_mark == "_"):
            if italic:
                closes = not text[i + 1 : i + 2].isalnum()
            else:
                closes = (
                    (i == 0 or not text[i - 1].isalnum())
                    and i + 1 < n
                    and not text[i + 1].isspace()
                    and _underscore_closes(text, i + 2)
                )
            if closes:
                flush()
                italic, italic_mark = not italic, "_"
                i += 1
                continue
        buffer.append(char)
        i += 1
    flush()
    return spans


def parse_inline(text: str) -> list[Segment]:
    """Split *text* into ``(text, bold, italic)`` segments.

    A marker opens only when its closer appears later; an unmatched marker is
    kept as text. A link is its text, code is kept as written and a picture is
    its description.
    """

    segments: list[Segment] = []
    for span in _spans(text):
        if not span.text:
            continue
        if segments and segments[-1][1:] == (span.bold, span.italic):
            segments[-1] = (segments[-1][0] + span.text, span.bold, span.italic)
        else:
            segments.append((span.text, span.bold, span.italic))
    return segments


# --------------------------------------------------------------------------
# Blocks


@dataclass
class _Heading:
    level: int
    text: str


@dataclass
class _Paragraph:
    text: str


@dataclass
class _ListItem:
    kind: str  # "bullet" | "number"
    level: int  # 1-based
    text: str
    number: int | None = None


@dataclass
class _List:
    items: list[_ListItem]


@dataclass
class _Table:
    rows: list[list[str]]
    header: bool
    #: Per column: "left", "center", "right", or None where the separator says nothing.
    aligns: list[str | None] = field(default_factory=list)


@dataclass
class _Code:
    text: str


@dataclass
class _Quote:
    blocks: list[object]


_HEADING = re.compile(r"^\s{0,3}(#{1,6})(?:\s+(.*?))?\s*?(?:\s#+)?\s*$")
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|(\d{1,9})[.)])\s+(.*)$")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_QUOTE = re.compile(r"^\s{0,3}>\s?")
_SETEXT_TITLE = re.compile(r"^\s{0,3}=+\s*$")
_SETEXT_SECTION = re.compile(r"^\s{0,3}-+\s*$")
_NOTE_DEFINITION = re.compile(r"^\s{0,3}\[\^([^\]\s]+)\]:\s?(.*)$")
_LINK_DEFINITION = re.compile(r"^\s{0,3}\[([^\]^][^\]]*)\]:\s*<?([^\s>]+)>?(?:\s+[\"'(].*[\"')])?\s*$")
_TASK = re.compile(r"^\[([ xX])\]\s+")


def _indent_width(prefix: str) -> int:
    return sum(4 if char == "\t" else 1 for char in prefix)


def _split_row(line: str) -> list[str]:
    body = line.strip()
    body = body.removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if body[i] == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(body[i])
        i += 1
    cells.append("".join(current).strip())
    return cells


def _separator_aligns(line: str) -> list[str | None]:
    """The alignment each cell of a ``|:---|:---:|---:|`` separator row asks for."""

    aligns: list[str | None] = []
    for cell in _split_row(line):
        left, right = cell.startswith(":"), cell.endswith(":")
        aligns.append("center" if left and right else "left" if left else "right" if right else None)
    return aligns


def _join_lines(lines: list[str]) -> str:
    text = ""
    for index, line in enumerate(lines):
        hard_break = line.endswith(("  ", "\\"))
        piece = line.rstrip()
        piece = piece.removesuffix("\\")
        piece = piece.strip()
        text += piece
        if index < len(lines) - 1:
            text += "\n" if hard_break else " "
    return text


def _take_definitions(lines: list[str], refs: _Refs) -> list[str]:
    """*lines* without the footnote (``[^1]: …``) and link reference (``[id]: url``) definitions, which go
    into *refs*. Lines in a fenced code block are never definitions."""

    kept: list[str] = []
    fence: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        opening = _FENCE.match(line)
        if fence is not None or opening:
            if fence is None and opening:
                fence = opening.group(1)
            elif fence is not None and line.strip().startswith(fence):
                fence = None
            kept.append(line)
            i += 1
            continue
        note = _NOTE_DEFINITION.match(line)
        if note:
            parts = [note.group(2).strip()]
            i += 1
            while i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip():
                parts.append(lines[i].strip())  # an indented line goes on with the note
                i += 1
            refs.notes.setdefault(note.group(1), " ".join(part for part in parts if part))
            continue
        target = _LINK_DEFINITION.match(line)
        if target:
            refs.links.setdefault(target.group(1).strip().lower(), target.group(2))
            i += 1
            continue
        kept.append(line)
        i += 1
    return kept


def _is_bare_table(lines: list[str], i: int) -> bool:
    """Whether line *i* is the header row of a table written without the outer ``|`` (``a | b`` over ``---|---``)."""

    if i + 1 >= len(lines) or "|" not in lines[i] or "|" not in lines[i + 1]:
        return False
    if not _TABLE_SEPARATOR.match(lines[i + 1]):
        return False
    return len(_split_row(lines[i])) == len(_split_row(lines[i + 1]))


def _task(text: str) -> str:
    """A task list item's ``[ ]``/``[x]`` as the box Hancom draws as text."""

    match = _TASK.match(text)
    if not match:
        return text
    return ("☐ " if match.group(1) == " " else "☑ ") + text[match.end() :]


def parse_blocks(markdown: str) -> Iterator[object]:
    """Yield the blocks of *markdown* in order."""

    yield from _parse(markdown)[0]


def _parse(markdown: str) -> tuple[list[object], _Refs]:
    """The blocks of *markdown* and what it defines apart from them (footnotes, link references)."""

    refs = _Refs()
    lines = _take_definitions(markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"), refs)
    return list(_blocks(lines)), refs


def _blocks(lines: list[str]) -> Iterator[object]:
    paragraph: list[str] = []
    i = 0

    def end_paragraph() -> Iterator[object]:
        if paragraph:
            yield _Paragraph(_join_lines(paragraph))
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            yield from end_paragraph()
            i += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            yield from end_paragraph()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                body.append(lines[i])
                i += 1
            i += 1  # the closing fence (or the end)
            yield _Code("\n".join(body))
            continue
        if paragraph and (_SETEXT_TITLE.match(line) or (len(paragraph) == 1 and _SETEXT_SECTION.match(line))):
            text = _join_lines(paragraph).replace("\n", " ")
            paragraph.clear()
            yield _Heading(1 if "=" in line else 2, text)
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            yield from end_paragraph()
            if (heading.group(2) or "").strip():
                yield _Heading(len(heading.group(1)), heading.group(2).strip())
            i += 1
            continue
        if _RULE.match(line):  # a rule wins over a "- - -" list item, as in CommonMark
            yield from end_paragraph()
            i += 1
            continue
        if _QUOTE.match(line):
            yield from end_paragraph()
            inner: list[str] = []
            while i < len(lines):
                quoted = _QUOTE.match(lines[i])
                if not quoted:
                    break
                inner.append(lines[i][quoted.end() :])
                i += 1
            yield _Quote(list(_blocks(inner)))
            continue
        if line.lstrip().startswith("|") or _is_bare_table(lines, i):
            yield from end_paragraph()
            rows: list[list[str]] = []
            header = False
            aligns: list[str | None] = []
            bare = not line.lstrip().startswith("|")
            while i < len(lines) and (
                lines[i].lstrip().startswith("|") or (bare and lines[i].strip() and "|" in lines[i])
            ):
                if _TABLE_SEPARATOR.match(lines[i]):
                    if len(rows) == 1 and not header:
                        header = True
                        aligns = _separator_aligns(lines[i])
                else:
                    rows.append(_split_row(lines[i]))
                i += 1
            yield _Table(rows, header, aligns)
            continue
        item = _LIST_ITEM.match(line)
        if item:
            # A list item interrupts a paragraph: models often write "다음과 같다:" then "- …".
            yield from end_paragraph()
            items: list[_ListItem] = []
            indents: list[int] = []
            while i < len(lines):
                current = lines[i]
                match = _LIST_ITEM.match(current)
                if match:
                    width = _indent_width(match.group(1))
                    while indents and width < indents[-1]:
                        indents.pop()
                    if not indents or width > indents[-1]:
                        indents.append(width)
                    number = match.group(3)
                    items.append(
                        _ListItem(
                            kind="number" if number is not None else "bullet",
                            level=min(len(indents), 10),
                            text=_task(match.group(4).strip()),
                            number=int(number) if number is not None else None,
                        )
                    )
                    i += 1
                    continue
                if current.strip() and current[:1].isspace() and items:
                    items[-1].text += " " + current.strip()  # a continuation line
                    i += 1
                    continue
                break
            yield _List(items)
            continue
        paragraph.append(line)
        i += 1
    yield from end_paragraph()


# --------------------------------------------------------------------------
# Writing


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _outline_heads(document: HwpxDocument) -> dict[int, Any]:
    """The heads (``hh:paraHead``) of the numbering the last section numbers its outline with, by level."""

    sections = document.oxml.sections
    headers = document.oxml.headers
    if not sections or not headers:
        return {}
    sec_pr = next((node for node in sections[-1].element.iter() if _local(node) == "secPr"), None)
    shape = sec_pr.get("outlineShapeIDRef") if sec_pr is not None else None
    numbering = next(
        (node for node in headers[0].element.iter() if _local(node) == "numbering" and node.get("id") == shape),
        None,
    )
    if numbering is None:
        return {}
    heads: dict[int, Any] = {}
    for head in numbering:
        if _local(head) == "paraHead":
            try:
                heads[int(head.get("level") or 0)] = head
            except ValueError:  # pragma: no cover - defensive
                continue
    return heads


def _unnumber_outline(document: HwpxDocument) -> None:
    """Make the outline numbering of *document* draw no number at any level.

    Hancom's own blank document leaves the heads of outline levels 9 and 10 empty, and draws no number there;
    this empties the others too. The Markdown headings write their numbers as text (``Ⅰ``, ``1.``, ``가.``), so
    an outline number drawn as well would show each number twice.
    """

    heads = _outline_heads(document)
    for head in heads.values():
        head.text = None
    if heads:
        document.oxml.headers[0].mark_dirty()


#: How many of each loss the warning names by example.
_LOSS_EXAMPLES = 3
#: The most a picture file may weigh.
_IMAGE_MOST_BYTES = 20 * 1024 * 1024
#: A picture's pixels are taken at 96 to the inch: 7200 HWPUNIT / 96.
_HWPUNIT_PER_PIXEL = 75


def _image_info(data: bytes) -> tuple[str, int, int] | None:
    """``(format, width, height)`` in pixels of a PNG, JPEG, GIF or BMP picture, or ``None``."""

    import struct

    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", data[16:24])
            return "png", width, height
        if data[:6] in (b"GIF87a", b"GIF89a"):
            width, height = struct.unpack("<HH", data[6:10])
            return "gif", width, height
        if data[:2] == b"BM":
            width, height = struct.unpack("<ii", data[18:26])
            return "bmp", abs(width), abs(height)
        if data[:2] == b"\xff\xd8":
            index = 2
            while index + 9 < len(data):
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                    index += 1 if marker == 0xFF else 2
                    continue
                length = struct.unpack(">H", data[index + 2 : index + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    height, width = struct.unpack(">HH", data[index + 5 : index + 9])
                    return "jpg", width, height
                index += 2 + length
            return None
    except struct.error:
        return None
    return None


class _Writer:
    def __init__(
        self,
        document: HwpxDocument,
        style: MarkdownStyle,
        *,
        reuse_first: bool,
        refs: _Refs | None = None,
        base_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.doc = document
        self.style = style
        self.refs = refs or _Refs()
        self.base_dir = base_dir
        self._char_ids: dict[tuple[object, ...], str] = {}
        self._border_ids: dict[tuple[object, ...], str] = {}
        self._reuse = document.paragraphs[0] if reuse_first else None
        self._heading_counts = [0] * _HEADING_LEVELS
        #: How far right the heading above stands; the paragraphs under it stand as far.
        self._body_indent_mm = 0.0
        #: The level of the heading above (0: none yet).
        self._heading_level = 0
        #: How many block quotes the text being written stands in.
        self._quote_depth = 0
        #: What could not be carried over: a kind, and examples of it.
        self.losses: dict[str, list[str]] = {}
        self._used_notes: set[str] = set()
        self._outline_styles = self._find_outline_styles()
        heads = _outline_heads(document)
        #: The outline levels the document draws no number for: a heading there can be an outline paragraph.
        self._silent_outline = {
            level for level in range(1, _HEADING_LEVELS + 1) if level in heads and not (heads[level].text or "").strip()
        }
        self._text_width: int | None = None
        self._looks: dict[tuple[object, ...], tuple[Any, float]] = {}
        self._advances: dict[tuple[object, ...], dict[str, float]] = {}

    # -- what is lost --------------------------------------------------------

    def lose(self, kind: str, example: str = "") -> None:
        examples = self.losses.setdefault(kind, [])
        examples.append(example)

    def report(self) -> str | None:
        """One sentence naming what was not carried over, or ``None``."""

        unused = sorted(set(self.refs.notes) - self._used_notes)
        for label in unused:
            self.lose("footnote-unused", f"[^{label}]")
        if not self.losses:
            return None
        names = {
            "image": "picture(s) not read, written as their description",
            "image-in-text": "picture(s) in a heading, list item or table cell, written as their description",
            "html": "HTML tag(s) kept as text",
            "footnote-missing": "footnote reference(s) without a definition, kept as text",
            "footnote-unused": "footnote definition(s) no text refers to, left out",
        }
        parts = []
        for kind, examples in self.losses.items():
            shown = [example for example in examples if example][:_LOSS_EXAMPLES]
            detail = f" ({'; '.join(shown)}{'; …' if len(examples) > len(shown) and shown else ''})" if shown else ""
            parts.append(f"{len(examples)} {names.get(kind, kind)}{detail}")
        return "Markdown not carried over: " + ", ".join(parts) + "."

    def count_unread(self, text: str) -> None:
        """Note what plain text still holds of the Markdown: HTML tags, footnote references with no definition."""

        for tag in _HTML_TAG.findall(text):
            self.lose("html", tag)
        for label in _NOTE_REF.findall(text):
            self.lose("footnote-missing", f"[^{label}]")

    # -- outline -------------------------------------------------------------

    def _find_outline_styles(self) -> dict[int, str]:
        """The id of the outline style of each heading level the document has (``개요 1`` …)."""

        from .._document.headings import resolve_heading_style
        from ..errors import HwpxError

        found: dict[int, str] = {}
        for level in range(1, _HEADING_LEVELS + 1):
            try:
                found[level] = str(resolve_heading_style(self.doc, level=level).id)
            except (HwpxError, LookupError, ValueError):
                continue
        return found

    def outline(self, paragraph: HwpxOxmlParagraph, level: int) -> None:
        """Make *paragraph* a heading of *level*: the outline style of the level, and its outline level where the
        document draws no outline number for it (elsewhere Hancom would draw its number before the one the
        heading writes; the style alone still finds it for a table of contents made by its styles)."""

        style_id = self._outline_styles.get(level)
        if style_id is not None:
            paragraph.style_id_ref = style_id
        if level in self._silent_outline:
            self.doc.styles.apply_paragraph_format(paragraphs=[paragraph], outline_level=level)

    def resume_counts(self) -> None:
        """Take up the heading numbers where the document's headings leave them.

        The headings are the paragraphs in an outline style, a boxed section heading included; the number a
        heading shows, in the form the look numbers its level in, is the count its level goes on from.
        """

        levels = {style_id: level for level, style_id in self._outline_styles.items()}
        if not levels:
            return
        for paragraph in self.doc.paragraphs:
            found = self._heading_of(paragraph, levels)
            if found is None:
                continue
            level, label = found
            for deeper in range(level, _HEADING_LEVELS):
                self._heading_counts[deeper] = 0
            form = self.number_form(level)
            value = _number_value(label, form) if form else None
            if value is not None:
                self._heading_counts[level - 1] = value

    @staticmethod
    def _heading_of(paragraph: HwpxOxmlParagraph, levels: dict[str, int]) -> tuple[int, str] | None:
        """``(level, the text that shows its number)`` of a heading paragraph, or ``None``."""

        level = levels.get(str(paragraph.style_id_ref))
        if level is not None:
            return level, paragraph.text
        for table in paragraph.tables:
            if table.row_count > 3:
                continue
            for row in table.rows:
                cells = row.cells
                for index, cell in enumerate(cells):
                    inner = cell.paragraphs[0] if cell.paragraphs else None
                    level = levels.get(str(inner.style_id_ref)) if inner is not None else None
                    if level is not None:
                        # a boxed section heading shows its number in the cell before it
                        return level, cells[0].text if index == 1 else cell.text
        return None

    # -- runs ----------------------------------------------------------------

    def char_id(
        self,
        bold: bool,
        italic: bool,
        size: float | None,
        font: str | None = None,
        color: str | None = None,
        *,
        strike: bool = False,
        link: bool = False,
    ) -> str:
        key = (bold, italic, size, font, color, strike, link)
        if key not in self._char_ids:
            extra: dict[str, Any] = {}
            if strike:
                extra["strike"] = True
            if link:
                extra.update(color=_LINK_COLOR, underline=True, underline_color=_LINK_COLOR)
            else:
                extra["color"] = color
            self._char_ids[key] = self.doc.styles.ensure_run(bold=bold, italic=italic, size=size, font=font, **extra)
        return self._char_ids[key]

    def spans(self, text: str) -> list[_Span]:
        return _spans(_BR.sub("\n", text), self.refs)

    def write_runs(
        self,
        paragraph: HwpxOxmlParagraph,
        text: str,
        *,
        bold: bool = False,
        size: float | None = None,
        font: str | None = None,
        color: str | None = None,
        spans: list[_Span] | None = None,
    ) -> None:
        if spans is None:
            spans = self.spans(text)
        if not spans:
            spans = [_Span("")]
        for span in spans:
            if span.note is not None:
                self._used_notes.add(span.note)
                note = "".join(chunk for chunk, _bold, _italic in parse_inline(self.refs.notes[span.note]))
                self.doc.notes.add_footnote(note, paragraph)  # type: ignore[arg-type]
                continue
            if span.image is not None:  # where a picture cannot stand: its description stands for it
                self.lose("image-in-text", span.image)
            if not span.code:
                self.count_unread(span.text)
            face = (self.style.code_font or font) if span.code else font
            char = self.char_id(
                bold or span.bold, span.italic, size, face, color, strike=span.strike, link=span.link is not None
            )
            if span.link is not None and span.text:
                paragraph.add_hyperlink(span.link, span.text, char_pr_id_ref=char)
            else:
                paragraph.add_run(span.text, char_pr_id_ref=char)

    def heading_bold(self, level: int) -> bool:
        bold = self.style.heading_bold
        return bold if isinstance(bold, bool) else bold[min(level, 4) - 1]

    def heading_font(self, level: int) -> str | None:
        return self.style.heading_fonts[min(level, 4) - 1] or self.style.body_font

    def border_id(
        self,
        *,
        color: str = "#000000",
        width: str = "0.12 mm",
        fill: str | None = None,
        sides: tuple[tuple[str, str] | None, tuple[str, str] | None, tuple[str, str] | None, tuple[str, str] | None]
        | None = None,
    ) -> str:
        """A border/fill id: *sides* is ``(left, right, top, bottom)``, each ``(type, width)`` or ``None`` for no
        line; without *sides* all four are solid lines of *width*."""

        key = (color, width, fill, sides)
        if key not in self._border_ids:
            lines = None
            if sides is not None:
                lines = {
                    name: None if line is None else {"type": line[0], "width": line[1]}
                    for name, line in zip(("left", "right", "top", "bottom"), sides)
                }
            self._border_ids[key] = self.doc.styles.ensure_border_fill(
                border_color=color, border_width=width, fill_color=fill, sides=lines
            )
        return self._border_ids[key]

    def stop_reusing(self) -> None:
        self._reuse = None

    def new_paragraph(self) -> HwpxOxmlParagraph:
        if self._reuse is not None:
            paragraph, self._reuse = self._reuse, None
            return paragraph
        return self.doc.add_paragraph("", include_run=False, inherit_style=False)

    def number_form(self, level: int) -> str | None:
        """The number form of headings of *level*; ``#####`` and ``######`` take the forms after ``####``'s."""

        if level <= 4:
            return self.style.heading_numbers[level - 1]
        form = self.style.heading_numbers[3]
        if form not in _FORM_ORDER:
            return None
        position = _FORM_ORDER.index(form) + level - 4
        return _FORM_ORDER[position] if position < len(_FORM_ORDER) else None

    def heading_number(self, level: int, text: str) -> str:
        """The number to write before a heading of *level*, or ``""``."""

        form = self.number_form(level)
        if form is None or _OWN_NUMBER.match(text):
            return ""
        self._heading_counts[level - 1] += 1
        return _NUMBER_FORMS[form](self._heading_counts[level - 1]) + " "

    def heading(self, block: _Heading) -> HwpxOxmlParagraph:
        """Write a heading and return the body paragraph that holds it."""

        # The levels below start again under every heading, numbered by the look or by its writer.
        for deeper in range(block.level, _HEADING_LEVELS):
            self._heading_counts[deeper] = 0
        drawn = min(block.level, 4)  # ##### and ###### are drawn like ####
        self._heading_level = block.level
        self._body_indent_mm = float(self.style.heading_indents_mm[drawn - 1])
        if block.level == 1 and self.style.title_look == "banner":
            return self.banner(block)
        if block.level == 2 and self.style.section_look == "box":
            return self.section_box(block)
        paragraph = self.new_paragraph()
        size = self.style.heading_sizes[drawn - 1]
        bold, font = self.heading_bold(block.level), self.heading_font(block.level)
        number = self.heading_number(block.level, block.text)
        if number:
            paragraph.add_run(number, char_pr_id_ref=self.char_id(bold, False, size, font))
        self.write_runs(paragraph, block.text, bold=bold, size=size, font=font)
        title = block.level == 1
        space_after = self.style.heading_space_after_pt
        if title and self.style.title_space_after_pt is not None:
            space_after = self.style.title_space_after_pt
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph],
            alignment=self.style.title_align if title else None,
            indent_left_mm=self.style.heading_indents_mm[drawn - 1] or None,
            spacing_before_pt=self.style.heading_space_before_pt,
            spacing_after_pt=space_after,
            keep_with_next=True,
            bottom_border=title and self.style.title_rule,
            border_color="#000000",
            border_width="0.4 mm",
        )
        self.outline(paragraph, block.level)
        return paragraph

    def byline(self, text: str, title: HwpxOxmlParagraph | None) -> None:
        """The line naming who wrote the document, right-aligned under *title* (``None``: no title)."""

        style = self.style
        paragraph = self.new_paragraph()
        self.write_runs(
            paragraph,
            text,
            bold=style.byline_bold,
            size=style.byline_size or style.body_size,
            font=style.byline_font or style.body_font,
        )
        gap = style.title_space_after_pt if style.title_space_after_pt is not None else style.heading_space_after_pt
        self.doc.styles.apply_paragraph_format(paragraphs=[paragraph], alignment="right", spacing_after_pt=gap)
        if title is not None and gap is not None:  # the space under the title is now the space under this line
            self.doc.styles.apply_paragraph_format(paragraphs=[title], spacing_after_pt=0, keep_with_next=True)

    def banner(self, block: _Heading) -> HwpxOxmlParagraph:
        """The title in a filled box the width of the text, colour strips above and below."""

        style = self.style
        size = style.heading_sizes[0]
        paragraph = self.new_paragraph()
        table = paragraph.add_table(3, 2, border_fill_id_ref=self.border_id(sides=(None, None, None, None)))
        tiny = self.char_id(False, False, _STRIP_FONT_PT)  # an empty line no taller than the strip
        for (row, col), color in zip(((0, 0), (0, 1), (2, 0), (2, 1)), style.banner_colors):
            table.set_cell_border_fill(row, col, self.border_id(fill=color, sides=(None, None, None, None)))
            for run in table.cell(row, col).paragraphs[0].runs:
                run.char_pr_id_ref = tiny
        table.merge_cells(1, 0, 1, 1)
        table.set_cell_border_fill(1, 0, self.border_id(fill=style.banner_fill, sides=(None, None, None, None)))
        title = table.cell(1, 0).paragraphs[0]
        self.write_runs(title, block.text, bold=self.heading_bold(1), size=size, font=self.heading_font(1))
        self.doc.styles.apply_paragraph_format(paragraphs=[title], alignment="center", line_spacing_percent=120)
        self.outline(title, 1)
        table.set_row_heights([_STRIP_HEIGHT, round(size * 100 * _BANNER_HEIGHT_EMS), _STRIP_HEIGHT])
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph],
            spacing_after_pt=style.title_space_after_pt
            if style.title_space_after_pt is not None
            else style.heading_space_after_pt,
            keep_with_next=True,
        )
        return paragraph

    def section_box(self, block: _Heading) -> HwpxOxmlParagraph:
        """A section heading: its number in a filled cell, the heading beside it over a line."""

        from ..form_fit.measure import estimate_text_width

        style = self.style
        fill, line, ink = style.section_colors
        size = style.heading_sizes[1]
        em = estimate_text_width("가", size)
        number, text = self.box_number(block.text)
        paragraph = self.new_paragraph()
        available = paragraph._context_table_width() or _FALLBACK_TEXT_WIDTH
        number_width = 0
        if number:
            needed = estimate_text_width(number, size + 2) + _CELL_SIDE_PADDING + em / 4
            number_width = round(max(em * _BOX_NUMBER_EMS, needed))
        plain = "".join(chunk for chunk, _bold, _italic in parse_inline(_BR.sub("\n", text)))
        longest = max(estimate_text_width(piece, size) for piece in plain.split("\n")) * _BOX_TITLE_WIDER
        title_width = round(min(longest + em * _BOX_TITLE_SLACK_EMS + _CELL_SIDE_PADDING, available - number_width))
        open_box = self.border_id(color=line, sides=(("SOLID", "0.4 mm"), None, None, ("SOLID", "0.4 mm")))
        table = paragraph.add_table(
            1, 2 if number else 1, width=number_width + title_width, border_fill_id_ref=open_box
        )
        if number:
            table.set_column_widths([number_width, title_width])
            table.set_cell_border_fill(0, 0, self.border_id(color=line, width="0.4 mm", fill=fill))
            label = table.cell(0, 0).paragraphs[0]
            label.add_run(number, char_pr_id_ref=self.char_id(True, False, size + 2, style.body_font, "#FFFFFF"))
            self.doc.styles.apply_paragraph_format(paragraphs=[label], alignment="center")
        heading = table.cell(0, 1 if number else 0).paragraphs[0]
        self.write_runs(heading, text, bold=self.heading_bold(2), size=size, font=self.heading_font(2), color=ink)
        self.doc.styles.apply_paragraph_format(
            paragraphs=[heading], indent_left_mm=_BOX_TITLE_INDENT_MM, line_spacing_percent=130
        )
        self.outline(heading, 2)
        table.set_row_heights([round(size * 100 * _BOX_HEIGHT_EMS)])
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph],
            spacing_before_pt=style.heading_space_before_pt,
            spacing_after_pt=style.heading_space_after_pt,
            keep_with_next=True,
        )
        return paragraph

    def box_number(self, text: str) -> tuple[str, str]:
        """``(number, heading)`` for a boxed section heading; no number draws the heading alone.

        A number the heading carries (``Ⅱ. 현황``, ``2. 현황``) is the one shown; ``제2장 …`` is kept in the
        heading, which is then drawn without a number cell.
        """

        own = _OWN_NUMBER.match(text)
        if own:
            mark, rest = own.group(0).strip(), text[own.end() :].strip()
            if rest and mark[-1:] in ".)" and not mark.startswith("("):
                return mark[:-1], rest
            if rest and not mark.startswith("제"):
                return mark, rest
            return "", text
        return self.heading_number(2, text).strip().removesuffix("."), text

    def quote_step_mm(self) -> float:
        """How far a block quote stands in from the text around it: as far as a list's first depth."""

        if self.style.list_first_indent_mm:
            return float(self.style.list_first_indent_mm)
        return self.list_step_mm()

    def list_step_mm(self) -> float:
        step = self.style.list_indent_mm
        if step is None:
            step = (self.style.body_size or _BASE_SIZE_PT) * _LIST_INDENT_CHARS * _MM_PER_PT
        return float(step)

    def text_indent_mm(self) -> float:
        """How far right body text stands: under the heading above it, and in from each quote around it."""

        quoted = self.quote_step_mm() * self._quote_depth if self._quote_depth else 0.0
        return self._body_indent_mm + quoted

    def paragraph(self, block: _Paragraph, *, bold: bool = False) -> None:
        style = self.style
        pictures: list[tuple[str, tuple[bytes, str, int, int]]] = []
        spans: list[_Span] = []
        for span in self.spans(block.text):
            if span.image is not None:
                loaded = self.load_image(span.image)
                if loaded is not None:
                    pictures.append((span.text, loaded))
                    continue
                span = replace(span, image=None)  # its description stands in its place
            spans.append(span)
        if any(span.text.strip() or span.note for span in spans) or not pictures:
            paragraph = self.new_paragraph()
            note = block.text.lstrip().startswith(_NOTE_MARK)  # a note is set smaller, as the look gives it
            self.write_runs(
                paragraph,
                block.text,
                bold=bold,
                size=(style.note_size if note else None) or style.body_size,
                font=(style.note_font if note else None) or style.body_font,
                spans=spans,
            )
            indent = self.text_indent_mm()
            if indent > 0:
                self.doc.styles.apply_paragraph_format(paragraphs=[paragraph], indent_left_mm=indent)
        for description, loaded in pictures:
            self.picture(description, loaded)

    def load_image(self, source: str) -> tuple[bytes, str, int, int] | None:
        """``(data, format, width, height)`` of the picture file *source* names, or ``None`` (and why, noted).

        Only a file under ``base_dir`` is read: Markdown from elsewhere must not pull any file of the machine
        into the document.
        """

        from pathlib import Path

        if not source or _SCHEME.match(source):  # a URL (a drive letter is one letter, a scheme more)
            self.lose("image", f"not a file: {source[:60]}")
            return None
        if self.base_dir is None:
            self.lose("image", f"no base_dir to read {source} from")
            return None
        from urllib.parse import unquote

        base = Path(self.base_dir).resolve()
        path = (base / unquote(source)).resolve()
        if path != base and base not in path.parents:
            self.lose("image", f"outside base_dir: {source}")
            return None
        try:
            if path.stat().st_size > _IMAGE_MOST_BYTES:
                self.lose("image", f"too large: {source}")
                return None
            data = path.read_bytes()
        except OSError:
            self.lose("image", f"not found: {source}")
            return None
        info = _image_info(data)
        if info is None or info[1] <= 0 or info[2] <= 0:
            self.lose("image", f"not a PNG, JPEG, GIF or BMP picture: {source}")
            return None
        return data, *info

    def text_width(self) -> int:
        if self._text_width is None:
            try:
                size, margins = self.doc.page.size(), self.doc.page.margins()
                self._text_width = int(size.width - margins.left - margins.right)
            except Exception:  # pragma: no cover - a page the facade cannot read
                self._text_width = _FALLBACK_TEXT_WIDTH
            if self._text_width <= 0:  # pragma: no cover - defensive
                self._text_width = _FALLBACK_TEXT_WIDTH
        return self._text_width

    def picture(self, description: str, loaded: tuple[bytes, str, int, int]) -> None:
        """A picture in a paragraph of its own, centred, as wide as its pixels (no wider than the text), with
        *description* as its caption under it and as its alternative text."""

        data, image_format, width_px, height_px = loaded
        width = width_px * _HWPUNIT_PER_PIXEL
        most = self.text_width() - round(self.text_indent_mm() * _HWPUNIT_PER_MM)
        if width > most > 0:
            width = most
        height = max(1, round(width * height_px / width_px))
        self.stop_reusing()
        picture = self.doc.add_picture(
            data, image_format, width=width, height=height, align="CENTER", para_pr_id_ref="0", style=0
        )
        description = description.strip()
        if description:
            comment = next((node for node in picture.element if _local(node) == "shapeComment"), None)
            if comment is not None:
                comment.text = description
            picture.set_caption(description, side="BOTTOM")

    def code(self, block: _Code) -> None:
        """A fenced code block: one paragraph, its lines kept, every character as written, in the code typeface."""

        paragraph = self.new_paragraph()
        face = self.style.code_font or self.style.body_font
        paragraph.add_run(block.text, char_pr_id_ref=self.char_id(False, False, self.style.body_size, face))
        indent = self.text_indent_mm()
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph], alignment="left", indent_left_mm=indent if indent > 0 else None
        )

    def quote(self, block: _Quote) -> None:
        """A block quote: what it holds, standing in from the text around it."""

        self._quote_depth += 1
        try:
            for inner in block.blocks:
                if isinstance(inner, _Heading):  # a heading in a quote is no heading of the document
                    self.paragraph(_Paragraph(inner.text), bold=True)
                else:
                    self.block(inner)
        finally:
            self._quote_depth -= 1

    def block(self, block: object) -> None:
        if isinstance(block, _Table):
            self.table(block)
            self.stop_reusing()
        elif isinstance(block, _Heading):
            self.heading(block)
        elif isinstance(block, _List):
            self.list(block)
        elif isinstance(block, _Paragraph):
            self.paragraph(block)
        elif isinstance(block, _Code):
            self.code(block)
        elif isinstance(block, _Quote):
            self.quote(block)

    def fit_on_one_line(self, paragraph: HwpxOxmlParagraph) -> None:
        """Narrow the letter spacing of a list item that runs a little past its line, so that it stays on one.

        The spacing is narrowed by whole percents, no further than ``list_fit_spacing``, to the first value at
        which the text is measured to fit with a little room to spare. An item that would need more keeps its
        spacing and wraps. A measure that turns out too short costs nothing but a wrapped line: the spacing is
        a fixed one, never Hancom's fit-to-one-line, which presses a line as far as it takes.
        """

        from ..form_fit.measure import char_advance, indented_widths, text_style_from_refs

        limit = self.style.list_fit_spacing
        runs = [run for run in paragraph.runs if run.text]
        text = "".join(run.text for run in runs).rstrip()
        if not limit or not text or "\n" in text:
            return
        key = (paragraph.para_pr_id_ref, runs[0].char_pr_id_ref, runs[-1].char_pr_id_ref)
        if key not in self._looks:  # items alike measure alike: a long list read its look once per item
            look = text_style_from_refs(
                self.doc, paragraph.para_pr_id_ref, [runs[0].char_pr_id_ref], end_char_pr_id_ref=runs[-1].char_pr_id_ref
            )
            line = (paragraph._context_table_width() or _FALLBACK_TEXT_WIDTH) - look.margin_left - look.margin_right
            self._looks[key] = (look, indented_widths(line, look)[0])
        look, room = self._looks[key]
        points = self.style.body_size or _BASE_SIZE_PT

        def width(spacing: int) -> float:
            advances = self._advances.setdefault((key, spacing), {})
            spaced = None
            total = 0.0
            for char in text:
                advance = advances.get(char)
                if advance is None:
                    spaced = spaced or replace(look, spacing=float(spacing))
                    advance = advances[char] = char_advance(char, points, spaced)
                total += advance
            return total

        if room <= 0 or width(0) <= room:
            return
        for spacing in range(-1, -limit - 1, -1):
            if width(spacing) <= room * (1 - _FIT_SPARE):
                for run in runs:
                    run.char_pr_id_ref = self.doc.styles.ensure_run(
                        base_char_pr_id=run.char_pr_id_ref, letter_spacing=spacing
                    )
                return

    def list(self, block: _List) -> None:
        by_level: dict[int, list[HwpxOxmlParagraph]] = {}
        written: list[tuple[_ListItem, HwpxOxmlParagraph]] = []
        for item in block.items:
            paragraph = self.new_paragraph()
            self.write_runs(paragraph, item.text, size=self.style.body_size, font=self.style.body_font)
            by_level.setdefault(item.level, []).append(paragraph)
            written.append((item, paragraph))
        # One definition for the numbered items of the list and one bullet a depth: Hancom numbers on through
        # a definition, so the list is numbered as one and the next list starts again.
        heads: dict[tuple[str, int], dict[str, str]] = {}
        numbered = [item for item, _paragraph in written if item.kind == "number"]
        if numbered:
            first = numbered[0]
            levels = [dict(spec) for spec in _LIST_NUMBER_LEVELS]
            if first.number not in (None, 1):
                levels[first.level - 1]["start"] = str(first.number)
            self.list_heads(heads, "number", self.doc.styles.ensure_numbering(kind="number", levels=levels))
        bulleted = [item for item, _paragraph in written if item.kind == "bullet"]
        if bulleted:
            chars = (self.style.sub_bullet_chars if self._heading_level >= 4 else ()) or self.style.bullet_chars
            specs: list[dict[str, str]] = []
            for level in range(1, max(item.level for item in bulleted) + 1):
                bullet = chars[min(level, len(chars)) - 1] if chars else self.style.bullet_char
                specs.append({"char": bullet} if bullet else {})
            self.list_heads(heads, "bullet", self.doc.styles.ensure_numbering(kind="bullet", levels=specs))
        step = self.list_step_mm()
        first_indent = (self.style.list_first_indent_mm or 0.0) + (
            self.quote_step_mm() * self._quote_depth if self._quote_depth else 0.0
        )
        # One paragraph shape for the items alike (as a rule all of a depth): finding or making a shape for each
        # item made a long list slow.
        shapes: dict[tuple[object, ...], str] = {}
        for item, paragraph in written:
            left = first_indent + step * (item.level - 1)
            key = (paragraph.para_pr_id_ref, item.kind, item.level, left)
            if key not in shapes:
                shapes[key] = self.doc.styles.ensure_paragraph_format(
                    base_para_pr_id=paragraph.para_pr_id_ref,
                    heading=heads[(item.kind, item.level)],
                    margins={"left": round(left * _HWPUNIT_PER_MM)} if left > 0 else None,
                )
            paragraph.para_pr_id_ref = shapes[key]
        if self.style.list_fit_spacing:  # once each item has its margins and its bullet
            for paragraphs in by_level.values():
                for paragraph in paragraphs:
                    self.fit_on_one_line(paragraph)

    def list_heads(self, heads: dict[tuple[str, int], dict[str, str]], kind: str, refs: list[str]) -> None:
        """The list head (``hh:heading``) of each depth of a *kind* list, from its paragraph shapes *refs*."""

        for level, ref in enumerate(refs, start=1):
            heading = self.doc.styles.paragraph_property(ref).heading
            heads[(kind, level)] = {"type": str(heading.type), "idRef": str(heading.id_ref), "level": str(level - 1)}

    def table(self, block: _Table) -> None:
        if not block.rows:
            return
        cols = max(len(row) for row in block.rows)
        table = self.doc.add_table(len(block.rows), cols)
        size = self.style.table_size or self.style.body_size
        font = self.style.table_font or self.style.body_font
        ruled = self.style.table_look == "ruled"
        aligned: dict[str, list[HwpxOxmlParagraph]] = {}
        for row_index, row in enumerate(block.rows):
            is_header = block.header and row_index == 0
            for col_index in range(cols):
                text = row[col_index] if col_index < len(row) else ""
                cell = table.cell(row_index, col_index)
                self.write_runs(
                    cell.paragraphs[0],
                    text,
                    bold=is_header and self.style.table_header_bold,
                    size=size,
                    font=font,
                )
                if ruled:
                    table.set_cell_border_fill(
                        row_index, col_index, self.ruled_border(row_index, col_index, len(block.rows), cols, block.header)
                    )
                elif is_header and self.style.table_header_shading:
                    table.set_cell_shading(row_index, col_index, self.style.table_header_shading)
                align = block.aligns[col_index] if col_index < len(block.aligns) else None
                if align is None and is_header:
                    align = self.style.table_header_align
                if align in ("center", "right"):
                    aligned.setdefault(align, []).append(cell.paragraphs[0])
        if self.style.table_fit_columns and cols > 1:
            total = sum(table.cell(0, col_index).width for col_index in range(cols))
            table.set_column_widths(_column_weights(block.rows, cols, size or _BASE_SIZE_PT, total))
        if self.style.table_align == "auto":
            widths = [table.cell(0, col_index).width for col_index in range(cols)]
            by_column = _body_aligns(block, cols, size or _BASE_SIZE_PT, widths)
            for row_index in range(1 if block.header else 0, len(block.rows)):
                for col_index, align in enumerate(by_column):
                    if align:
                        aligned.setdefault(align, []).append(table.cell(row_index, col_index).paragraphs[0])
        for align, paragraphs in aligned.items():
            self.doc.styles.apply_paragraph_format(paragraphs=paragraphs, alignment=align)
        if self.style.table_row_height_mm:
            table.set_row_heights([round(self.style.table_row_height_mm * _HWPUNIT_PER_MM)] * len(block.rows))
        if block.header and len(block.rows) > 1:
            # Hancom draws the header row again at the top of each page a long table runs onto.
            table.element.set("repeatHeader", "1")
            for col_index in range(cols):
                table.cell(0, col_index).element.set("header", "1")
            table.mark_dirty()

    def ruled_border(self, row: int, col: int, rows: int, cols: int, header: bool) -> str:
        """The border of one cell of a ruled table: open sides, a heavy line above and below the table, a
        double line under the header row and thin lines between cells."""

        heavy, thin, double = ("SOLID", "0.4 mm"), ("SOLID", "0.15 mm"), ("DOUBLE_SLIM", "0.5 mm")
        under_header = header and rows > 1
        return self.border_id(
            fill=self.style.table_header_shading if header and row == 0 else None,
            sides=(
                None if col == 0 else thin,
                None if col == cols - 1 else thin,
                heavy if row == 0 else double if under_header and row == 1 else thin,
                heavy if row == rows - 1 else double if under_header and row == 0 else thin,
            ),
        )


#: The blank document's body size, used to judge how wide a column's text is.
_BASE_SIZE_PT = 10.0
#: How far each list depth below the first moves right, in characters of the body size.
_LIST_INDENT_CHARS = 1.5
_MM_PER_PT = 25.4 / 72
#: A table cell's left and right padding together (1.8 mm each side), in HWPUNIT.
_CELL_SIDE_PADDING = 2 * 510
#: A column is never judged narrower than this many full-width characters.
_MIN_COLUMN_CHARS = 3
#: Room left beyond the measured text, in full-width characters, so a line that
#: just fits by the estimate does not wrap in Hancom.
_COLUMN_SLACK_CHARS = 1.0
_HWPUNIT_PER_MM = 7200 / 25.4
#: The text width of the blank document, for a paragraph whose page cannot be measured.
_FALLBACK_TEXT_WIDTH = 42520
#: A banner's colour strip: its height, and the size of the empty line inside it.
_STRIP_HEIGHT = 430
_STRIP_FONT_PT = 1.0
#: The heights of the banner's title cell and of a boxed section heading, in lines of their text size.
_BANNER_HEIGHT_EMS = 1.7
_BOX_HEIGHT_EMS = 2.2
#: A boxed section heading: the number cell's least width and the room kept after the heading, in
#: characters of its size, and how far the heading stands from the line on its left.
_BOX_NUMBER_EMS = 2.1
_BOX_TITLE_SLACK_EMS = 4.0
_BOX_TITLE_INDENT_MM = 3.0
#: A bold heading typeface runs wider than the estimate, which is made for body text.
_BOX_TITLE_WIDER = 1.05
#: A paragraph that starts with this mark is a note.
_NOTE_MARK = "※"
#: The share of its line a list item is measured to leave free before its narrowed spacing is taken to fit.
_FIT_SPARE = 0.01
#: The most a look may narrow the letter spacing of a list item, in percent: past it the letters crowd.
_FIT_SPACING_MOST = 10
#: The colour Hancom writes link text in.
_LINK_COLOR = "#0000FF"
#: A URL's scheme (``https:``, ``data:``): two letters at least, so a drive letter (``C:``) is not one.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+:")
#: The number of each depth of a numbered list, as Hancom numbers a new list: 1. 가. 1) 가) (1) (가) ① ㉮ ㄱ ⅰ.
_LIST_NUMBER_LEVELS: tuple[dict[str, str], ...] = (
    {"text": "^1.", "format": "DIGIT"},
    {"text": "^2.", "format": "HANGUL_SYLLABLE"},
    {"text": "^3)", "format": "DIGIT"},
    {"text": "^4)", "format": "HANGUL_SYLLABLE"},
    {"text": "(^5)", "format": "DIGIT"},
    {"text": "(^6)", "format": "HANGUL_SYLLABLE"},
    {"text": "^7", "format": "CIRCLED_DIGIT"},
    {"text": "^8", "format": "CIRCLED_HANGUL_SYLLABLE"},
    {"text": "^9", "format": "HANGUL_JAMO"},
    {"text": "^10", "format": "ROMAN_SMALL"},
)


def _plain_cell(text: str) -> str:
    return "".join(chunk for chunk, _bold, _italic in parse_inline(_BR.sub("\n", text)))


def _column_needs(rows: list[list[str]], cols: int, font_pt: float) -> tuple[list[float], float]:
    """The width each column needs for its longest line, cell padding included, and the least any column is
    given (a few characters)."""

    from ..form_fit.measure import estimate_text_width

    em = estimate_text_width("가", font_pt)
    floor = em * _MIN_COLUMN_CHARS + _CELL_SIDE_PADDING
    needs: list[float] = []
    for col_index in range(cols):
        longest = 0.0
        for row in rows:
            text = row[col_index] if col_index < len(row) else ""
            for line in _plain_cell(text).split("\n"):
                longest = max(longest, estimate_text_width(line, font_pt))
        needs.append(max(longest + em * _COLUMN_SLACK_CHARS + _CELL_SIDE_PADDING, floor))
    return needs, floor


def _body_aligns(block: _Table, cols: int, font_pt: float, widths: list[int]) -> list[str | None]:
    """How the look aligns the body cells of each column (``table_align="auto"``); ``None`` leaves them.

    A column whose cells each fit on one line is centred, and one that wraps reads from the left. A table of
    two columns is read as labels and what they name: the labels are spread over their column's width and
    the other column reads from the left. A column the Markdown aligns itself is left to it.
    """

    body = block.rows[1:] if block.header else block.rows
    if not body:
        return [None] * cols
    needs, _floor = _column_needs(body, cols, font_pt)
    labels = [_plain_cell(row[0]) if row else "" for row in body]
    spread = all("\n" not in label and len("".join(label.split())) >= 2 for label in labels)
    aligns: list[str | None] = []
    for col_index in range(cols):
        given = block.aligns[col_index] if col_index < len(block.aligns) else None
        if given is not None or needs[col_index] > widths[col_index] or (cols == 2 and col_index == 1):
            aligns.append(None)
        elif cols == 2 and spread:
            aligns.append("distribute")
        else:
            aligns.append("center")
    return aligns


def _column_weights(rows: list[list[str]], cols: int, font_pt: float, table_width: int) -> list[float]:
    """Width weights by what each column's longest line needs.

    A column needs its longest line of text plus the cell padding, and no less
    than a few characters. When the needs fit the table, the table's width is
    shared out in proportion to them. When they do not, the columns that need
    the most are cut down to a common width and wrap, and the others keep what
    they need: a column of short labels stays on one line next to a column of
    long text.
    """

    needs, floor = _column_needs(rows, cols, font_pt)
    if sum(needs) <= table_width:
        return needs
    if floor * cols >= table_width:
        return [1.0] * cols  # too many columns to give each even the least: share alike
    # Cut the widest columns down to one level so that the widths add up to the table.
    remaining = float(table_width)
    level = 0.0
    ordered = sorted(needs)
    for position, need in enumerate(ordered):
        level = remaining / (cols - position)
        if need > level:
            break
        remaining -= need
    return [min(need, level) for need in needs]


def _check_markdown(markdown: object, caller: str) -> None:
    if not isinstance(markdown, str):
        from ..errors import HwpxTypeError

        raise HwpxTypeError(
            f"{caller} takes the Markdown as str, not {type(markdown).__name__}",
            context={"argument": "markdown", "type": type(markdown).__name__},
            suggestion="Pass the Markdown text; decode bytes first, e.g. data.decode('utf-8').",
        )


def _append(
    document: HwpxDocument,
    markdown: str,
    *,
    style: MarkdownStyle,
    byline: str | None,
    reuse_first: bool,
    base_dir: str | os.PathLike[str] | None,
    caller: str,
) -> None:
    blocks, refs = _parse(markdown)
    writer = _Writer(document, style, reuse_first=reuse_first, refs=refs, base_dir=base_dir)
    writer.resume_counts()
    pending = (byline or "").strip()
    if pending and not any(isinstance(block, _Heading) and block.level == 1 for block in blocks):
        writer.byline(pending, None)
        pending = ""
    for block in blocks:
        if isinstance(block, _Heading):
            title = writer.heading(block)
            if pending and block.level == 1:
                writer.byline(pending, title)
                pending = ""
        else:
            writer.block(block)
    message = writer.report()
    if message:
        # _append, then append_markdown or from_markdown, then the caller
        warnings.warn(f"{caller}: {message}", UserWarning, stacklevel=3)


def append_markdown(
    document: HwpxDocument,
    markdown: str,
    *,
    style: MarkdownStyle | str | None = None,
    byline: str | None = None,
    reuse_first_paragraph: bool = False,
    base_dir: str | os.PathLike[str] | None = None,
) -> None:
    """Append *markdown* to the end of *document*'s last section.

    *style* is a :class:`MarkdownStyle` or the name of a look: ``"plain"``, or
    the one the library ships, ``"report"`` (also ``"보고서"``). ``None`` is
    the plain look, so the document keeps the look it has. Heading numbers go
    on from the headings the document already has: a document made in parts
    numbers its sections ``Ⅰ``, ``Ⅱ``, ``Ⅲ`` across the calls.

    *byline* is a line naming who wrote the document (a department, a date).
    It is written right-aligned under the first ``#`` title, or as the first
    line when the Markdown has no title; ``\\n`` in it is a line break.

    ``reuse_first_paragraph=True`` writes the first heading, paragraph or list
    item into the document's first paragraph instead of a new one — what
    :func:`from_markdown` does with a blank document's empty first line. A
    table of the Markdown never takes that paragraph (it holds the section
    settings).

    *base_dir* is the folder pictures (``![설명](그림.png)``) are read from: a
    path is taken under it, and a file outside it is not read. Without it no
    picture file is read. A picture that is not read is written as its
    description.

    Headings take the outline style of their level. Where the document's
    outline numbering draws no number for the level (a document made by
    :func:`from_markdown`), the heading is an outline paragraph of that level
    too; elsewhere it keeps the style only, as an outline number drawn before
    the heading's own would show it twice.

    What the Markdown holds that is not carried over is named in one
    ``UserWarning``. *markdown* must be ``str`` (``HwpxTypeError``).
    """

    _check_markdown(markdown, "append_markdown")
    _append(
        document,
        markdown,
        style=_resolve_style(style),
        byline=byline,
        reuse_first=reuse_first_paragraph,
        base_dir=base_dir,
        caller="append_markdown",
    )


def from_markdown(
    markdown: str,
    *,
    style: MarkdownStyle | str | None = None,
    byline: str | None = None,
    base_dir: str | os.PathLike[str] | None = None,
) -> HwpxDocument:
    """Return a new clean document holding *markdown*.

    The document takes the report look (``"report"``, :meth:`MarkdownStyle.report`)
    unless *style* says otherwise: the title in a banner, section headings in
    a numbered box, ruled tables, 12pt body text, report page margins and a
    page number. ``style="plain"`` gives the undecorated look, and a
    :class:`MarkdownStyle` any look of your own.

    *byline* is a line naming who wrote the document (a department, a date),
    written right-aligned under the title; see :func:`append_markdown`.
    *base_dir* is the folder pictures are read from; see :func:`append_markdown`.

    The document is made with ``HwpxDocument.new(inherit_style=False)`` and the
    first heading, paragraph or list item takes its empty first line. To add
    Markdown to a document you already have, use ``doc.text.append_markdown``.

    Every heading is an outline paragraph of its level (``#`` is level 1), so a
    table of contents (``hwpx.tools.toc_author.add_native_toc``) and Hancom's
    outline find it. The headings write their numbers as text, so the
    document's outline numbering is made to draw none: a heading added later
    with ``doc.add_heading`` gets no number from Hancom either.

    The 6.x root of :class:`HwpxDocument` has no free slot for another
    constructor, so this lives here rather than as ``HwpxDocument.from_markdown``.
    """

    from ..document import HwpxDocument

    _check_markdown(markdown, "from_markdown")
    resolved = _resolve_style(style, "report")
    document = HwpxDocument.new(inherit_style=False)
    _unnumber_outline(document)
    if resolved.page_margins_mm:  # before the text: tables are made as wide as the text
        left, right, top, bottom, *edges = resolved.page_margins_mm
        document.page.setup(
            margin_left_mm=left,
            margin_right_mm=right,
            margin_top_mm=top,
            margin_bottom_mm=bottom,
            header_margin_mm=edges[0] if edges else None,
            footer_margin_mm=edges[1] if edges else None,
        )
    _append(
        document,
        markdown,
        style=resolved,
        byline=byline,
        reuse_first=True,
        base_dir=base_dir,
        caller="from_markdown",
    )
    if resolved.page_number:
        side = resolved.page_number_side
        document.page.set_page_number(prefix=f"{side} " if side else "", suffix=f" {side}" if side else "")
    return document
