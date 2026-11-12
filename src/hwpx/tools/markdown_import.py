# SPDX-License-Identifier: Apache-2.0
"""Markdown → HWPX: write a small, common Markdown subset into a document.

``markdown_export`` goes one way (HWPX → Markdown); this module goes the other.
It knows headings, paragraphs, lists, pipe tables and bold/italic. The default
look is genre-neutral. One named look ships with the library, ``"report"``
(:meth:`MarkdownStyle.report`): a centred title, numbered section headings,
larger body text and a page number, so the first document a newcomer makes
looks like a document. Everything it does is a :class:`MarkdownStyle` field.
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
    the document it is given.
    """

    heading_sizes: tuple[float, float, float, float] = (16.0, 12.0, 11.0, 10.0)
    heading_bold: bool = True
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

    @classmethod
    def report(cls) -> MarkdownStyle:
        """The ``"report"`` look: what a plain Korean report looks like.

        ``#`` is the centred title with a rule under it; ``##``, ``###`` and
        ``####`` are numbered ``1.``, ``가.`` and ``1)``, the order the
        administrative manual (행정업무운영 편람) gives for items; body text is
        12pt and table text 11pt; bullets are ``○``, ``-``, ``·`` by depth; the
        page number is at the bottom centre.
        """

        return cls(
            heading_sizes=(20.0, 15.0, 13.0, 12.0),
            heading_space_before_pt=10.0,
            heading_space_after_pt=4.0,
            body_size=12.0,
            bullet_chars=("○", "-", "·"),
            title_align="center",
            title_rule=True,
            title_space_after_pt=14.0,
            heading_numbers=(None, "1.", "가.", "1)"),
            table_size=11.0,
            page_number=True,
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
        for name in ("table_size", "title_space_after_pt", "list_indent_mm"):
            value = getattr(self, name)
            if value is not None and (value < 0 or (value == 0 and name == "table_size")):
                raise HwpxValueError(
                    f"{name} must not be negative" if name != "table_size" else "table_size must be positive",
                    code="text-markdown-style-invalid",
                    context={name: value},
                    suggestion="Give a positive number, or None for the default.",
                )


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
_NAMED_STYLES = {"report": MarkdownStyle.report, "보고서": MarkdownStyle.report}


def _resolve_style(style: MarkdownStyle | str | None) -> MarkdownStyle:
    if style is None:
        return MarkdownStyle()
    if isinstance(style, MarkdownStyle):
        return style
    maker = _NAMED_STYLES.get(style) if isinstance(style, str) else None
    if maker is None:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unknown Markdown style {style!r}",
            code="text-markdown-style-invalid",
            context={"style": style, "known": sorted(_NAMED_STYLES)},
            suggestion="Pass a MarkdownStyle, None for the neutral look, or the name 'report' (also '보고서').",
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
        self._char_ids: dict[tuple[bool, bool, float | None], str] = {}
        self._reuse = document.paragraphs[0] if reuse_first else None
        self._heading_counts = [0, 0, 0, 0]

    def char_id(self, bold: bool, italic: bool, size: float | None) -> str:
        key = (bold, italic, size)
        if key not in self._char_ids:
            self._char_ids[key] = self.doc.styles.ensure_run(bold=bold, italic=italic, size=size)
        return self._char_ids[key]

    def write_runs(
        self, paragraph: HwpxOxmlParagraph, text: str, *, bold: bool = False, size: float | None = None
    ) -> None:
        segments = parse_inline(_BR.sub("\n", text)) or [("", False, False)]
        for chunk, seg_bold, seg_italic in segments:
            paragraph.add_run(chunk, char_pr_id_ref=self.char_id(bold or seg_bold, seg_italic, size))

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
        for deeper in range(level, 4):
            self._heading_counts[deeper] = 0
        return _NUMBER_FORMS[form](self._heading_counts[level - 1]) + " "

    def heading(self, block: _Heading) -> None:
        paragraph = self.new_paragraph()
        size = self.style.heading_sizes[block.level - 1]
        number = self.heading_number(block.level, block.text)
        if number:
            paragraph.add_run(number, char_pr_id_ref=self.char_id(self.style.heading_bold, False, size))
        self.write_runs(paragraph, block.text, bold=self.style.heading_bold, size=size)
        title = block.level == 1
        space_after = self.style.heading_space_after_pt
        if title and self.style.title_space_after_pt is not None:
            space_after = self.style.title_space_after_pt
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph],
            alignment=self.style.title_align if title else None,
            spacing_before_pt=self.style.heading_space_before_pt,
            spacing_after_pt=space_after,
            keep_with_next=True,
            bottom_border=title and self.style.title_rule,
            border_color="#000000",
            border_width="0.4 mm",
        )

    def paragraph(self, block: _Paragraph) -> None:
        self.write_runs(self.new_paragraph(), block.text, size=self.style.body_size)

    def list(self, block: _List) -> None:
        groups: dict[tuple[str, int], list[int]] = {}
        starts: dict[tuple[str, int], int | None] = {}
        nested: dict[int, list[HwpxOxmlParagraph]] = {}
        for item in block.items:
            paragraph = self.new_paragraph()
            self.write_runs(paragraph, item.text, size=self.style.body_size)
            if item.level > 1:
                nested.setdefault(item.level, []).append(paragraph)
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
        if step > 0:
            for level, paragraphs in nested.items():
                self.doc.styles.apply_paragraph_format(paragraphs=paragraphs, indent_left_mm=step * (level - 1))

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
                )
                if is_header and self.style.table_header_shading:
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
    reuse_first_paragraph: bool = False,
) -> None:
    """Append *markdown* to the end of *document*'s last section.

    *style* is a :class:`MarkdownStyle`, ``None`` for the neutral look, or the
    name of a look the library ships: ``"report"`` (also ``"보고서"``). Heading
    numbers start at 1 on each call.

    ``reuse_first_paragraph=True`` writes the first heading, paragraph or list
    item into the document's first paragraph instead of a new one — what
    :func:`from_markdown` does with a blank document's empty first line. A table never takes that paragraph (it holds the section settings).
    """

    writer = _Writer(document, _resolve_style(style), reuse_first=reuse_first_paragraph)
    for block in parse_blocks(markdown):
        if isinstance(block, _Table):
            writer.table(block)
            writer.stop_reusing()
        elif isinstance(block, _Heading):
            writer.heading(block)
        elif isinstance(block, _List):
            writer.list(block)
        elif isinstance(block, _Paragraph):
            writer.paragraph(block)


def from_markdown(markdown: str, *, style: MarkdownStyle | str | None = None) -> HwpxDocument:
    """Return a new clean document holding *markdown*.

    ``from_markdown(text, style="report")`` gives the report look: a centred
    title, numbered section headings, 12pt body text and a page number.

    The document is made with ``HwpxDocument.new(inherit_style=False)`` and the
    first heading, paragraph or list item takes its empty first line. To add
    Markdown to a document you already have, use ``doc.text.append_markdown``.

    The 6.x root of :class:`HwpxDocument` has no free slot for another
    constructor, so this lives here rather than as ``HwpxDocument.from_markdown``.
    """

    from ..document import HwpxDocument

    resolved = _resolve_style(style)
    document = HwpxDocument.new(inherit_style=False)
    append_markdown(document, markdown, style=resolved, reuse_first_paragraph=True)
    if resolved.page_number:
        document.page.set_page_number()
    return document
