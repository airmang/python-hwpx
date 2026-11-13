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

- ``#`` ~ ``####`` headings (``#####``/``######`` are drawn like ``####``)
- paragraphs (consecutive lines join with a space; two trailing spaces or a
  trailing ``\\`` is a line break)
- ``-``/``*``/``+`` bullets and ``1.``/``1)`` numbered lists, nested by
  indentation, as real Hancom lists (:meth:`doc.styles.apply_list_format`)
- pipe tables; a row followed by a ``|---|`` separator is the header row
  (bold, shaded, centred); ``:---``/``:---:``/``---:`` in the separator align
  a column; columns are as wide as their text needs; ``<br>`` in a cell is a
  line break
- inline ``**bold**``/``__bold__``, ``*italic*``, ``***both***``,
  ``` `code` ``` (kept as text), ``[text](url)`` (the text), ``\\`` escapes
- fenced code blocks become one paragraph per block, lines kept

Anything else — block quotes, rules, HTML — is written as plain text or dropped
(rules). Unknown Markdown never raises.

New paragraphs never inherit the previous paragraph's style, so a heading or a
list item does not hand its outline or list numbering to the paragraph after it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
        ):
            value = getattr(self, name)
            positive = name in ("table_size", "table_row_height_mm", "byline_size")
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
        ):
            if getattr(self, name) not in allowed:
                refuse(name, f"{name} must be one of: {', '.join(allowed)}", f"Use one of: {', '.join(allowed)}.")
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
        for name in ("body_font", "table_font", "byline_font", "banner_fill"):
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
#: A heading that already carries a number of its own: "1. 개요", "가. 목적", "Ⅱ. 현황", "(1) …", "① …", "제2장 …".
_OWN_NUMBER = re.compile(
    r"^(?:\d{1,2}[.)]\s|[가나다라마바사아자차카타파하][.)]\s|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+[.\s]|[IVX]+\.\s"
    r"|\(\d{1,2}\)|\([가나다라마바사아자차카타파하]\)|[①-⑳]|제\s*\d+\s*[장절관조항])"
)
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

_ESCAPABLE = set("\\`*_{}[]()#+-.!|>~")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

Segment = tuple[str, bool, bool]


def parse_inline(text: str) -> list[Segment]:
    """Split *text* into ``(text, bold, italic)`` segments.

    A marker opens only when its closer appears later; an unmatched marker is
    kept as text.
    """

    segments: list[Segment] = []
    buffer: list[str] = []
    bold = italic = False

    def flush() -> None:
        if buffer:
            chunk = "".join(buffer)
            if segments and segments[-1][1:] == (bold, italic):
                segments[-1] = (segments[-1][0] + chunk, bold, italic)
            else:
                segments.append((chunk, bold, italic))
            buffer.clear()

    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            buffer.append(text[i + 1])
            i += 2
            continue
        if char == "`":
            end = text.find("`", i + 1)
            if end > i:
                buffer.append(text[i + 1 : end])
                i = end + 1
                continue
        if char == "[":
            match = _LINK.match(text, i)
            if match:
                buffer.append(match.group(1))
                i = match.end()
                continue
        marker = text[i : i + 2]
        if marker in ("**", "__"):
            opens = not bold and i + 2 < n and not text[i + 2].isspace() and text.find(marker, i + 2) > i + 2
            if bold or opens:
                flush()
                bold = not bold
                i += 2
                continue
        if char == "*":
            opens = not italic and i + 1 < n and not text[i + 1].isspace() and text.find("*", i + 1) > i + 1
            if italic or opens:
                flush()
                italic = not italic
                i += 1
                continue
        buffer.append(char)
        i += 1
    flush()
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


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|(\d{1,9})[.)])\s+(.*)$")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_QUOTE = re.compile(r"^\s{0,3}>\s?")


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


def parse_blocks(markdown: str) -> Iterator[object]:
    """Yield the blocks of *markdown* in order."""

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
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
            yield _Paragraph("\n".join(body))
            continue
        heading = _HEADING.match(line)
        if heading:
            yield from end_paragraph()
            yield _Heading(min(len(heading.group(1)), 4), heading.group(2))
            i += 1
            continue
        if _RULE.match(line):  # a rule wins over a "- - -" list item, as in CommonMark
            yield from end_paragraph()
            i += 1
            continue
        if line.lstrip().startswith("|"):
            yield from end_paragraph()
            rows: list[list[str]] = []
            header = False
            aligns: list[str | None] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
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
                            text=match.group(4).strip(),
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
        quote = _QUOTE.match(line)
        paragraph.append(line[quote.end() :] if quote else line)
        i += 1
    yield from end_paragraph()


# --------------------------------------------------------------------------
# Writing


class _Writer:
    def __init__(self, document: HwpxDocument, style: MarkdownStyle, *, reuse_first: bool) -> None:
        self.doc = document
        self.style = style
        self._char_ids: dict[tuple[bool, bool, float | None, str | None, str | None], str] = {}
        self._border_ids: dict[tuple[object, ...], str] = {}
        self._reuse = document.paragraphs[0] if reuse_first else None
        self._heading_counts = [0, 0, 0, 0]
        #: How far right the heading above stands; the paragraphs under it stand as far.
        self._body_indent_mm = 0.0

    def char_id(
        self, bold: bool, italic: bool, size: float | None, font: str | None = None, color: str | None = None
    ) -> str:
        key = (bold, italic, size, font, color)
        if key not in self._char_ids:
            self._char_ids[key] = self.doc.styles.ensure_run(bold=bold, italic=italic, size=size, font=font, color=color)
        return self._char_ids[key]

    def write_runs(
        self,
        paragraph: HwpxOxmlParagraph,
        text: str,
        *,
        bold: bool = False,
        size: float | None = None,
        font: str | None = None,
        color: str | None = None,
    ) -> None:
        segments = parse_inline(_BR.sub("\n", text)) or [("", False, False)]
        for chunk, seg_bold, seg_italic in segments:
            paragraph.add_run(chunk, char_pr_id_ref=self.char_id(bold or seg_bold, seg_italic, size, font, color))

    def heading_bold(self, level: int) -> bool:
        bold = self.style.heading_bold
        return bold if isinstance(bold, bool) else bold[level - 1]

    def heading_font(self, level: int) -> str | None:
        return self.style.heading_fonts[level - 1] or self.style.body_font

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

    def heading_number(self, level: int, text: str) -> str:
        """The number to write before a heading of *level*, or ``""``."""

        form = self.style.heading_numbers[level - 1]
        if form is None or _OWN_NUMBER.match(text):
            return ""
        self._heading_counts[level - 1] += 1
        return _NUMBER_FORMS[form](self._heading_counts[level - 1]) + " "

    def heading(self, block: _Heading) -> HwpxOxmlParagraph:
        """Write a heading and return the body paragraph that holds it."""

        # The levels below start again under every heading, numbered by the look or by its writer.
        for deeper in range(block.level, 4):
            self._heading_counts[deeper] = 0
        self._body_indent_mm = float(self.style.heading_indents_mm[block.level - 1])
        if block.level == 1 and self.style.title_look == "banner":
            return self.banner(block)
        if block.level == 2 and self.style.section_look == "box":
            return self.section_box(block)
        paragraph = self.new_paragraph()
        size = self.style.heading_sizes[block.level - 1]
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
            indent_left_mm=self.style.heading_indents_mm[block.level - 1] or None,
            spacing_before_pt=self.style.heading_space_before_pt,
            spacing_after_pt=space_after,
            keep_with_next=True,
            bottom_border=title and self.style.title_rule,
            border_color="#000000",
            border_width="0.4 mm",
        )
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

    def paragraph(self, block: _Paragraph) -> None:
        paragraph = self.new_paragraph()
        self.write_runs(paragraph, block.text, size=self.style.body_size, font=self.style.body_font)
        if self._body_indent_mm > 0:
            self.doc.styles.apply_paragraph_format(paragraphs=[paragraph], indent_left_mm=self._body_indent_mm)

    def list(self, block: _List) -> None:
        groups: dict[tuple[str, int], list[int]] = {}
        starts: dict[tuple[str, int], int | None] = {}
        by_level: dict[int, list[HwpxOxmlParagraph]] = {}
        for item in block.items:
            paragraph = self.new_paragraph()
            self.write_runs(paragraph, item.text, size=self.style.body_size, font=self.style.body_font)
            by_level.setdefault(item.level, []).append(paragraph)
            index = self._index_of(paragraph)
            key = (item.kind, item.level)
            if key not in groups:
                groups[key] = []
                starts[key] = item.number
            groups[key].append(index)
        numbered = False
        for (kind, level), indexes in sorted(groups.items(), key=lambda entry: entry[1][0]):
            if kind == "number":
                start = starts[(kind, level)]
                self.doc.styles.apply_list_format(
                    paragraph_indexes=indexes,
                    kind="number",
                    level=level,
                    start=None if numbered or start in (None, 1) else start,
                    continue_list=numbered,
                )
                numbered = True
            else:
                chars = self.style.bullet_chars
                bullet = chars[min(level, len(chars)) - 1] if chars else self.style.bullet_char
                self.doc.styles.apply_list_format(paragraph_indexes=indexes, kind="bullet", level=level, bullet_char=bullet)
        step = self.style.list_indent_mm
        if step is None:
            step = (self.style.body_size or _BASE_SIZE_PT) * _LIST_INDENT_CHARS * _MM_PER_PT
        first = self.style.list_first_indent_mm or 0.0
        for level, paragraphs in by_level.items():
            left = first + step * (level - 1)
            if left > 0:
                self.doc.styles.apply_paragraph_format(paragraphs=paragraphs, indent_left_mm=left)

    def _index_of(self, paragraph: HwpxOxmlParagraph) -> int:
        element = paragraph.element
        for index, candidate in enumerate(self.doc.paragraphs):
            if candidate.element is element:
                return index
        raise AssertionError("paragraph is not in the body")  # pragma: no cover

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
        for align, paragraphs in aligned.items():
            self.doc.styles.apply_paragraph_format(paragraphs=paragraphs, alignment=align)
        if self.style.table_fit_columns and cols > 1:
            total = sum(table.cell(0, col_index).width for col_index in range(cols))
            table.set_column_widths(_column_weights(block.rows, cols, size or _BASE_SIZE_PT, total))
        if self.style.table_row_height_mm:
            table.set_row_heights([round(self.style.table_row_height_mm * _HWPUNIT_PER_MM)] * len(block.rows))

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


def _column_weights(rows: list[list[str]], cols: int, font_pt: float, table_width: int) -> list[float]:
    """Width weights by what each column's longest line needs.

    A column needs its longest line of text plus the cell padding, and no less
    than a few characters. When the needs fit the table, the table's width is
    shared out in proportion to them. When they do not, the columns that need
    the most are cut down to a common width and wrap, and the others keep what
    they need: a column of short labels stays on one line next to a column of
    long text.
    """

    from ..form_fit.measure import estimate_text_width

    em = estimate_text_width("가", font_pt)
    floor = em * _MIN_COLUMN_CHARS + _CELL_SIDE_PADDING
    needs: list[float] = []
    for col_index in range(cols):
        longest = 0.0
        for row in rows:
            text = row[col_index] if col_index < len(row) else ""
            plain = "".join(chunk for chunk, _bold, _italic in parse_inline(_BR.sub("\n", text)))
            for line in plain.split("\n"):
                longest = max(longest, estimate_text_width(line, font_pt))
        needs.append(max(longest + em * _COLUMN_SLACK_CHARS + _CELL_SIDE_PADDING, floor))
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


def append_markdown(
    document: HwpxDocument,
    markdown: str,
    *,
    style: MarkdownStyle | str | None = None,
    byline: str | None = None,
    reuse_first_paragraph: bool = False,
) -> None:
    """Append *markdown* to the end of *document*'s last section.

    *style* is a :class:`MarkdownStyle` or the name of a look: ``"plain"``, or
    the one the library ships, ``"report"`` (also ``"보고서"``). ``None`` is
    the plain look, so the document keeps the look it has. Heading numbers
    start at 1 on each call.

    *byline* is a line naming who wrote the document (a department, a date).
    It is written right-aligned under the first ``#`` title, or as the first
    line when the Markdown has no title; ``\\n`` in it is a line break.

    ``reuse_first_paragraph=True`` writes the first heading, paragraph or list
    item into the document's first paragraph instead of a new one — what
    :func:`from_markdown` does with a blank document's empty first line. A
    table of the Markdown never takes that paragraph (it holds the section
    settings).
    """

    writer = _Writer(document, _resolve_style(style), reuse_first=reuse_first_paragraph)
    blocks = list(parse_blocks(markdown))
    pending = (byline or "").strip()
    if pending and not any(isinstance(block, _Heading) and block.level == 1 for block in blocks):
        writer.byline(pending, None)
        pending = ""
    for block in blocks:
        if isinstance(block, _Table):
            writer.table(block)
            writer.stop_reusing()
        elif isinstance(block, _Heading):
            title = writer.heading(block)
            if pending and block.level == 1:
                writer.byline(pending, title)
                pending = ""
        elif isinstance(block, _List):
            writer.list(block)
        elif isinstance(block, _Paragraph):
            writer.paragraph(block)


def from_markdown(
    markdown: str, *, style: MarkdownStyle | str | None = None, byline: str | None = None
) -> HwpxDocument:
    """Return a new clean document holding *markdown*.

    The document takes the report look (``"report"``, :meth:`MarkdownStyle.report`)
    unless *style* says otherwise: the title in a banner, section headings in
    a numbered box, ruled tables, 12pt body text, report page margins and a
    page number. ``style="plain"`` gives the undecorated look, and a
    :class:`MarkdownStyle` any look of your own.

    *byline* is a line naming who wrote the document (a department, a date),
    written right-aligned under the title; see :func:`append_markdown`.

    The document is made with ``HwpxDocument.new(inherit_style=False)`` and the
    first heading, paragraph or list item takes its empty first line. To add
    Markdown to a document you already have, use ``doc.text.append_markdown``.

    The 6.x root of :class:`HwpxDocument` has no free slot for another
    constructor, so this lives here rather than as ``HwpxDocument.from_markdown``.
    """

    from ..document import HwpxDocument

    resolved = _resolve_style(style, "report")
    document = HwpxDocument.new(inherit_style=False)
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
    append_markdown(document, markdown, style=resolved, byline=byline, reuse_first_paragraph=True)
    if resolved.page_number:
        side = resolved.page_number_side
        document.page.set_page_number(prefix=f"{side} " if side else "", suffix=f" {side}" if side else "")
    return document
