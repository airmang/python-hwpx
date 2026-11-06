# SPDX-License-Identifier: Apache-2.0
"""Markdown → HWPX: write a small, common Markdown subset into a document.

``markdown_export`` goes one way (HWPX → Markdown); this module goes the other.
It is a genre-neutral writer: it knows headings, paragraphs, lists, pipe tables
and bold/italic, and nothing about reports, official letters or notices. Genre
presets (공문·가정통신문 …) belong to the application layer, which can pass its
own :class:`MarkdownStyle`.

Supported subset:

- ``#`` ~ ``####`` headings (``#####``/``######`` are drawn like ``####``)
- paragraphs (consecutive lines join with a space; two trailing spaces or a
  trailing ``\\`` is a line break)
- ``-``/``*``/``+`` bullets and ``1.``/``1)`` numbered lists, nested by
  indentation, as real Hancom lists (:meth:`doc.styles.apply_list_format`)
- pipe tables; a row followed by a ``|---|`` separator is the header row
  (bold, shaded); ``<br>`` in a cell is a line break
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
from dataclasses import dataclass
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
    size, and a light grey header row in tables. Sizes are points; ``None``
    keeps the document's base character shape.
    """

    heading_sizes: tuple[float, float, float, float] = (16.0, 12.0, 11.0, 10.0)
    heading_bold: bool = True
    heading_space_before_pt: float | None = 6.0
    heading_space_after_pt: float | None = 3.0
    body_size: float | None = None
    table_header_shading: str | None = "#D9D9D9"
    table_header_bold: bool = True
    bullet_char: str | None = None

    def __post_init__(self) -> None:
        if len(self.heading_sizes) != 4 or any(size <= 0 for size in self.heading_sizes):
            raise ValueError("heading_sizes must be four positive point sizes (# to ####)")
        if self.body_size is not None and self.body_size <= 0:
            raise ValueError("body_size must be positive")


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
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if _TABLE_SEPARATOR.match(lines[i]):
                    header = header or len(rows) == 1
                else:
                    rows.append(_split_row(lines[i]))
                i += 1
            yield _Table(rows, header)
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

    def heading(self, block: _Heading) -> None:
        paragraph = self.new_paragraph()
        self.write_runs(
            paragraph,
            block.text,
            bold=self.style.heading_bold,
            size=self.style.heading_sizes[block.level - 1],
        )
        self.doc.styles.apply_paragraph_format(
            paragraphs=[paragraph],
            spacing_before_pt=self.style.heading_space_before_pt,
            spacing_after_pt=self.style.heading_space_after_pt,
            keep_with_next=True,
        )

    def paragraph(self, block: _Paragraph) -> None:
        self.write_runs(self.new_paragraph(), block.text, size=self.style.body_size)

    def list(self, block: _List) -> None:
        groups: dict[tuple[str, int], list[int]] = {}
        starts: dict[tuple[str, int], int | None] = {}
        for item in block.items:
            paragraph = self.new_paragraph()
            self.write_runs(paragraph, item.text, size=self.style.body_size)
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
                self.doc.styles.apply_list_format(
                    paragraph_indexes=indexes, kind="bullet", level=level, bullet_char=self.style.bullet_char
                )

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
        for row_index, row in enumerate(block.rows):
            is_header = block.header and row_index == 0
            for col_index in range(cols):
                text = row[col_index] if col_index < len(row) else ""
                cell = table.cell(row_index, col_index)
                self.write_runs(
                    cell.paragraphs[0],
                    text,
                    bold=is_header and self.style.table_header_bold,
                    size=self.style.body_size,
                )
                if is_header and self.style.table_header_shading:
                    table.set_cell_shading(row_index, col_index, self.style.table_header_shading)


def append_markdown(
    document: HwpxDocument,
    markdown: str,
    *,
    style: MarkdownStyle | None = None,
    reuse_first_paragraph: bool = False,
) -> None:
    """Append *markdown* to the end of *document*'s last section.

    ``reuse_first_paragraph=True`` writes the first heading, paragraph or list
    item into the document's first paragraph instead of a new one — what
    :func:`from_markdown` does with a blank document's empty first line. A table never takes that paragraph (it holds the section settings).
    """

    writer = _Writer(document, style or MarkdownStyle(), reuse_first=reuse_first_paragraph)
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


def from_markdown(markdown: str, *, style: MarkdownStyle | None = None) -> HwpxDocument:
    """Return a new clean document holding *markdown*.

    The document is made with ``HwpxDocument.new(inherit_style=False)`` and the
    first heading, paragraph or list item takes its empty first line. To add
    Markdown to a document you already have, use ``doc.text.append_markdown``.

    The 6.x root of :class:`HwpxDocument` has no free slot for another
    constructor, so this lives here rather than as ``HwpxDocument.from_markdown``.
    """

    from ..document import HwpxDocument

    document = HwpxDocument.new(inherit_style=False)
    append_markdown(document, markdown, style=style, reuse_first_paragraph=True)
    return document
