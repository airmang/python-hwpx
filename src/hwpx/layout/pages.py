# SPDX-License-Identifier: Apache-2.0
"""Page estimate (experimental): the pages and line positions Hancom lays a document out on.

:func:`estimate_pages` follows every body paragraph onto its page and column, without Hancom:

* Lines: a paragraph keeps the lines of its own layout cache (``hp:linesegarray``) when the save
  path would keep that cache -- those are the lines Hancom drew, each as tall as its text and
  followed by its spacing (``textheight``, ``spacing``); so do the paragraphs of table cells, and a
  cache of lines with no height counts as none. Other paragraphs break like FormFit
  (:func:`hwpx.form_fit.measure.hancom_line_starts`) at the column width (a cell's paragraphs at the
  cell's inner width) less the paragraph's margins and first-line indent and its bullet or number
  label's room (a number's at the label Hancom draws there, counted in reading order), each
  character at its own size and with its own run's face, 장평
  and 자간; a line of several sizes is as tall as its largest character, and its line spacing is
  reckoned from that size. Composed characters and ruby text (``hp:compose``, ``hp:dutmal``) take
  their place in the text like characters of their run: a composed one as wide as a Hangul syllable
  when framed (circle, box ...) or spread, else as its widest character, and no taller than the
  text; ruby text as wide as its text (however long the ruby), its line as tall as the text with
  the ruby (its size ratio, half when 0) above it, or below it over the text's foot (91/100 of the
  em, both counted in 1/1800 inch), and spaced from that height.
* Height: a line advances by the paragraph's line spacing (percent, fixed, between lines, at
  least), paragraphs add their spacing before and after, and a line stays on the page while its
  bottom is above the body's foot (one ending right at it goes on to the next page). Page and
  column breaks, page break before, keep lines
  together, keep with next and widow/orphan control; columns of equal width, and columns of
  unequal width when every paragraph keeps a valid layout cache (its lines do not depend on the
  width then) and holds objects only as characters.
* Objects: an object in front of or behind the text takes no room: the lines go where they would
  without it, wherever it stands; one placed top and bottom from the paper's top keeps every line of
  its page out of its band (a line reaching it, in any paragraph on that page, goes below it and
  the lines after follow; with several columns, in each of them when it covers the text's whole
  width). A table or picture set as a character is one line as tall as it.
  A table's caption above or below it takes its lines and its gap there (a caption below goes on
  to the next page with the table's last row when both do not fit above the foot, as a row would).
  Among text, an object set as a character takes its width on its line like a character, and the
  line is at least as tall as the object; the line spacing is reckoned from the line's largest
  character, the object counted at its run's character size (a fixed spacing keeps the next line
  that far down), and for an object with only spaces beside it from the largest size of any run of
  its paragraph. A top-and-bottom object anchored to an empty paragraph pushes the
  next line below
  it; anchored in a paragraph of text (from the paragraph's top), it stands at the top of the line
  its place in the text falls on, and that line and the rest of the paragraph come below it --
  offset down, it stands that much lower, and the first line reaching it (in that paragraph or the
  ones after) and the lines after come below it -- a table flowing with the text flows from there
  over the page end, and that line goes below its end (so does the line of a paragraph holding only
  another such table, which then flows from there); a flowing table alone in its paragraph starts
  its offset below the paragraph's top, above the paragraph's spacing before (one offset up starts
  there), and the next paragraph goes below the table's end or below the paragraph's line and its
  own spacing before, whichever is lower;
  wrapped square at the left or right edge of the column or of its paragraph before a paragraph's
  text (or alone in its paragraph), the text on its other side or on both, it narrows the lines
  whose top is above its foot, in that paragraph and the ones after, by its width and outer
  margins (a drop cap is one) -- a table by the height
  of its rows -- and wrapped square with no room beside it, it pushes the text below it like a
  top-and-bottom object; a table flowing with the text is laid out row by row -- split between cell lines, moved row
  by row or moved whole -- with its header rows (any row with a header cell of its own)
  repeated; a cell merged over rows that is taller
  than them adds what they lack to the last of them, the cell that ends first first (a row with no
  cell of its own starts at 0); in a table moved row by row, rows joined by a cell merged over them
  move to the next page as one, and in one split between cell lines each of their cells keeps the
  lines that fit and the rest go on, the rows from the one the page end falls in as tall as their
  cells' rest (a cell declared taller than its text, whose first line fits, is cut like such a row,
  below). A table set as a character alone in a paragraph of a cell is one line as tall as it
  there, spaced like the text, and a row holding one splits between its cell's lines, each as tall
  as it is; a nested table among text, placed top and bottom or wrapped square is followed through
  the layout caches of its cell, as tall as Hancom drew it (down to such a table's foot; one placed
  up from its paragraph's top stands at that top). A flowing table's rows use
  the body only down to just above the page's foot (101 above it, or 2 in a table set not to be
  adjusted), less the table's bottom outer margin: a row, or a cell line of a row split between its
  lines, ending lower goes on to the next page (where the table goes on below its top outer margin;
  a row is split only when every cell's first line fits, otherwise it goes on whole), and a row
  declared taller than its text, holding
  such a table or not, is cut there; what is left of it goes on to the next page unless it is no
  taller than a 10 pt line
  with the default cell margins (the cell's own margins, alignment and character size change
  neither) and none of its text is left: the lines that do not fit go on with it, which is then at
  least as tall as they are with the cell's margins. A flowing table's anchor line that does not fit
  at the page end goes to the next page, and the table with it. When a table moved row by row has no
  room for its first row under its anchor line, it starts on the next page and the text after it
  goes on under the anchor, then below the table on the pages the table takes. Footnotes take
  room at the foot of the page and go on over the page end.

A table set as a character that the row model does not follow (merged rows, a nested table) keeps
the height Hancom saved for it (``hp:sz``) when every paragraph in it keeps a valid layout cache,
i.e. Hancom laid the table out as it is. Otherwise a table whose cells merge rows has its rows as
their tallest cells of one row, and each merged cell, the one that ends first first, gives the last
of its rows what they lack.

Anything else makes the estimate unsupported: endnotes, a paragraph without such a cache or an
object not set as a character in columns of unequal width, a column change inside a section (column
settings in a cell or a text box are that list's own), section settings after a section's first
paragraph (Hancom starts a new section there), a line or character grid, an object with text or
other objects in its paragraph (but objects set as characters, with line spacing in percent or
fixed, one top-and-bottom object placed from the paragraph's top, and one object wrapped square
at a column's or its paragraph's edge before any text; an object offset down, but a flowing table, or wrapped square
stays on one page with the lines above or beside it), footnotes in such a paragraph, two tables
starting past their
anchors on one page, rows merged together that do not fit under their table's anchor or on a
page, a nested table among text or not set as a character in a cell without such caches (in a table
Hancom has not laid out as it is), a page break in a flowing row holding a table beside a taller
cell, other objects placed on the page or the paper (but top and bottom from the paper's top on a
page without a flowing table), and in a paragraph without such a cache ruby text placed other than
above or below its text or with line spacing other than percent, and composed characters or ruby
text beside an object placed otherwise than as a character. ``pages`` is then ``None`` and
``unsupported`` says why, per section.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from ..form_fit.measure import char_advance, hancom_line_starts, indented_widths, text_style_from_refs
from ..oxml._document_primitives import _remove_stale_paragraph_layout_cache
from ..oxml.namespaces import HH, HP
from ..oxml.paragraph_heading import paragraph_heading
from ..oxml.section import _remove_short_paragraph_layout_cache
from ..oxml.header_part import HwpxOxmlHeader
from ..oxml.section_format import _drawn_page_size
from ..oxml.table_sizes import cell_margins_of

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = ["EstimatedLine", "PageEstimate", "estimate_pages"]

#: Objects in a run, placed by their ``hp:pos``.
_OBJECTS = frozenset({
    "tbl", "pic", "rect", "ellipse", "line", "arc", "polygon", "curve", "connectLine", "textart",
    "container", "ole", "equation", "video", "chart", "checkBtn", "radioBtn", "btn", "button",
    "comboBox", "edit", "listBox", "scrollBar",
})
#: How an object in front of or behind the text wraps it: it takes no room from the text.
_FLOATING = frozenset({"IN_FRONT_OF_TEXT", "BEHIND_TEXT"})
#: Run content that takes its place in the text like a character: composed characters and ruby text.
_MARKS = frozenset({"compose", "dutmal"})
#: A flowing table's rows use the body only down to this far above its foot: a row, or a cell line of
#: a row split between its lines, ending lower goes on to the next page, and a row whose declared
#: height leaves room under its text (CELL) is cut there. What is left of such a row goes on to the
#: next page unless it is _SPARE_DROPPED or less, which is dropped (the row ends at the page's foot).
#: Both in HWPUNIT, as Hancom lays such rows out whatever the cells' margins, vertical alignment and
#: character size. A table set not to be adjusted (hp:tbl@noAdjust) uses _SPARE_CUT_FIXED instead.
_SPARE_CUT = 101
_SPARE_CUT_FIXED = 2
_SPARE_DROPPED = 1282
#: The narrowest line FormFit breaks at, in HWPUNIT.
_MIN_LINE_WIDTH = 1440


@dataclass(frozen=True)
class EstimatedLine:
    """Where one line of a body paragraph goes."""

    #: 0-based page of the document.
    page: int
    #: 0-based column on that page.
    column: int
    #: Distance of the line's top from the top of the column, in HWPUNIT (as ``hp:lineseg@vertpos``).
    vertpos: int


@dataclass(frozen=True)
class PageEstimate:
    """The estimated layout of a document, from :func:`estimate_pages`."""

    #: Number of pages, or ``None`` when the estimate does not support the document.
    pages: int | None
    #: The lines of each body paragraph (``hs:sec/hp:p``), sections in order. A paragraph anchoring a
    #: table that flows with the text has one line, under the table's top. Empty when unsupported.
    lines: tuple[tuple[EstimatedLine, ...], ...]
    #: Why the estimate does not support the document, one reason per section it stopped at.
    unsupported: tuple[str, ...]


class _Unsupported(Exception):
    """Something the estimate does not follow."""


def estimate_pages(document: "HwpxDocument | bytes | str | os.PathLike[str]") -> PageEstimate:
    """Estimate the pages Hancom lays *document* out on, and where each body line goes.

    *document* is an :class:`~hwpx.document.HwpxDocument` (estimated as it is in memory) or the
    bytes or path of an HWPX file. See the module description for what the estimate follows.
    """

    root = getattr(_open(document), "_root")
    measure = _Measure(root)
    layouts: list[_SectionLayout] = []
    reasons: list[str] = []
    for number, section in enumerate(root.sections):
        try:
            layouts.append(_lay_section(measure, section.element))
        except _Unsupported as exc:
            reasons.append(f"section {number}: {exc}")
    if reasons:
        return PageEstimate(None, (), tuple(reasons))
    return _assemble(layouts)


def _open(document: Any) -> Any:
    from ..document import HwpxDocument

    if isinstance(document, HwpxDocument):
        return document
    if isinstance(document, (bytes, bytearray)):
        return HwpxDocument.open(bytes(document))
    return HwpxDocument.open(os.fspath(document))


# -- the paragraph model ------------------------------------------------------------------------


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(element: Any, name: str) -> Any:
    return next((child for child in element if _local(child) == name), None)


@dataclass(frozen=True)
class _Shape:
    """What the estimate reads from a paragraph shape (``hh:paraPr``)."""

    kind: str
    value: int
    prev: int
    next: int
    left: int
    right: int
    indent: int
    flags: dict[str, str]


def _para_shape(header: Any, para_pr_id: str) -> _Shape:
    shape = next((el for el in header.iter(f"{HH}paraPr") if el.get("id") == para_pr_id), None)
    if shape is None:
        raise _Unsupported(f"paragraph shape {para_pr_id} is missing")
    # The hp:case holding margin and lineSpacing: outline levels 8-10 put hh:heading in an earlier switch.
    case = next((c for c in shape.iter(f"{HP}case") if _child(c, "lineSpacing") is not None), None)
    holder = case if case is not None else shape
    spacing = _child(holder, "lineSpacing")
    margin = _child(holder, "margin")

    def value(name: str) -> int:
        element = _child(margin, name) if margin is not None else None
        return int(element.get("value", 0)) if element is not None else 0

    breaks = shape.find(f"{HH}breakSetting")
    kind, amount = ("PERCENT", 160)
    if spacing is not None:
        kind, amount = spacing.get("type", "PERCENT"), int(spacing.get("value", 160))
    return _Shape(kind, amount, value("prev"), value("next"), value("left"), value("right"), value("intent"),
                  dict(breaks.attrib) if breaks is not None else {})


def _pitch(kind: str, value: int, size: int) -> int:
    """The distance from one line's top to the next line's top in a paragraph."""

    if kind == "FIXED":
        return value
    if kind == "BETWEEN_LINES":
        return size + value
    if kind == "AT_LEAST":
        return max(size, value)
    # PERCENT: the spacing over the size is counted in 1/1800 inch from the em (height // 4), rounded.
    extra = (size // 4) * (value - 100) / 100
    units = int(abs(extra) + 0.5)
    return size + 4 * (units if extra >= 0 else -units)


def _on(flags: dict[str, str], name: str) -> bool:
    return flags.get(name) in ("1", "true")


def _t_text(text_element: Any) -> str:
    """The text of one ``hp:t``, with ``hp:lineBreak`` as a newline and ``hp:tab`` as a tab."""

    parts = [text_element.text or ""]
    for child in text_element:
        name = _local(child)
        parts.append("\n" if name == "lineBreak" else "\t" if name == "tab" else "")
        parts.append(child.tail or "")
    return "".join(parts)


def _indented(line: float, shape: _Shape, style: Any) -> list[float]:
    """The first line's and the other lines' room of a paragraph of *shape* *line* wide inside its margins: less
    its first-line indent (a hanging one narrows the other lines) and its bullet or number label's room
    (``style.head``, see :func:`hwpx.form_fit.measure.indented_widths`)."""

    if style is not None and style.head:
        return list(indented_widths(line, replace(style, indent=shape.indent)))
    return [line - max(shape.indent, 0), line - max(-shape.indent, 0)]


def _line_widths(shape: _Shape, width: int, style: Any = None) -> list[float]:
    """The first line's and the other lines' widths of a paragraph of *shape* in *width*: less its margins,
    its first-line indent (a hanging one narrows the other lines) and its label's room."""

    return [max(room, _MIN_LINE_WIDTH) for room in _indented(width - shape.left - shape.right, shape, style)]


def _drawn_labels(root: Any) -> dict[Any, str]:
    """The label Hancom draws for each numbered, outline and bullet paragraph, counted in reading order: the body's
    paragraphs, each followed by those of the tables, text boxes and captions placed in it."""

    from ..tools.exporter import _ListLabels, _paragraph_pieces, _text_box_paragraphs

    labels = _ListLabels(root.headers[0].element if root.headers else None)
    drawn: dict[Any, str] = {}

    def visit(paragraph: Any) -> None:
        label = labels.label(paragraph)
        if label:
            drawn[paragraph] = label
        for piece in _paragraph_pieces(paragraph):
            if isinstance(piece, str):
                continue
            if piece.tag == f"{HP}tbl":
                for cell in piece.findall(f"{HP}tr/{HP}tc"):
                    for inner in cell.findall(f"{HP}subList/{HP}p"):
                        visit(inner)
            else:
                for inner in _text_box_paragraphs(piece):
                    visit(inner)

    for section in root.sections:
        labels.start_section(section.element)
        for paragraph in section.element.findall(f"{HP}p"):
            visit(paragraph)
    return drawn


def _run_text(runs: list[Any]) -> str:
    return "".join(_t_text(t) for run in runs for t in run.findall(f"{HP}t"))


def _cache_lines(paragraph: Any) -> int:
    """How many lines the paragraph's own layout cache holds; 0 when it has none or the save path
    would drop it as not matching the text."""

    segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
    if not segments:
        return 0
    probe = copy.deepcopy(paragraph)
    if _remove_stale_paragraph_layout_cache(probe) or _remove_short_paragraph_layout_cache(probe):
        return 0
    return len(segments)


def _cached_metrics(paragraph: Any) -> tuple[tuple[int, int], ...]:
    """(height, advance) of each line of the paragraph's own valid layout cache: the next line of a
    paragraph starts the line's text height plus its spacing lower (``vertsize`` can be larger, for a
    line an object set as a character follows). Empty without a valid cache."""

    if not _cache_lines(paragraph):
        return ()
    metrics = []
    for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg"):
        height = int(segment.get("textheight", segment.get("vertsize", 0)))
        if height <= 0:  # a cache of empty lines is none
            return ()
        metrics.append((height, height + int(segment.get("spacing", 0))))
    return tuple(metrics)


class _Lookups:
    """The shape lookups FormFit's text style reads, with the paragraph shapes read once: the document
    reads the header's paragraph shapes again on every lookup. (No ``_root`` attribute, so FormFit
    uses this object and not the document behind it.)"""

    def __init__(self, root: Any) -> None:
        self._document = root
        self.headers = root.headers
        self.sections = root.sections  # the outline numbering of a paragraph's label
        self._paragraph_shapes: dict[str, Any] | None = None

    def char_property(self, char_pr_id: Any) -> Any:
        return self._document.char_property(char_pr_id)

    def paragraph_property(self, para_pr_id: Any) -> Any:
        if self._paragraph_shapes is None:
            self._paragraph_shapes = self._document.paragraph_properties
        return HwpxOxmlHeader._lookup_by_id(self._paragraph_shapes, para_pr_id)


class _Measure:
    """Shapes and line breaking of one document."""

    def __init__(self, root: Any) -> None:
        self._root = root
        self._lookups = _Lookups(root)
        self._header = root.headers[0].element
        self._shapes: dict[str, _Shape] = {}
        self._styles: dict[tuple[str, tuple[str, ...], str | None], Any] = {}
        self._drawn: dict[Any, str] | None = None
        self._numbered: dict[str, bool] = {}

    def shape(self, para_pr_id: Any) -> _Shape:
        key = str(para_pr_id)
        if key not in self._shapes:
            self._shapes[key] = _para_shape(self._header, key)
        return self._shapes[key]

    def char_height(self, char_pr_id: Any) -> int:
        style = self._root.char_property(char_pr_id)
        return int(style.attributes.get("height", 1000)) if style is not None else 1000

    def style(self, para_pr_id: Any, char_pr_ids: list[Any], paragraph: Any = None) -> Any:
        """FormFit's text style of a paragraph shape and its characters; with *paragraph*, a number's label
        takes the room of the label Hancom draws for that paragraph."""

        drawn = None
        if paragraph is not None and self.numbered(para_pr_id):
            if self._drawn is None:
                self._drawn = _drawn_labels(self._root)
            drawn = self._drawn.get(paragraph)
        key = (str(para_pr_id), tuple(str(ref) for ref in char_pr_ids), drawn)
        if key not in self._styles:
            self._styles[key] = text_style_from_refs(self._lookups, para_pr_id, char_pr_ids, drawn)
        return self._styles[key]

    def numbered(self, para_pr_id: Any) -> bool:
        """Whether a paragraph shape heads its paragraphs with a number (``NUMBER`` or ``OUTLINE``)."""

        key = str(para_pr_id)
        if key not in self._numbered:
            shape = next((el for el in self._header.iter(f"{HH}paraPr") if el.get("id") == key), None)
            heading = paragraph_heading(shape) if shape is not None else None
            self._numbered[key] = heading is not None and heading.get("type") in {"NUMBER", "OUTLINE"}
        return self._numbered[key]

    def lines(self, text: str, widths: list[float], size: int, style: Any) -> int:
        """How many lines FormFit breaks *text* into (a newline starts a line)."""

        if not text:
            return 1
        return sum(len(hancom_line_starts(line, widths, size / 100, style)) if line else 1
                   for line in text.split("\n"))

    def line_starts(self, text: str, widths: list[float], size: int, style: Any,
                    sizes: list[int] | None = None, styles: list[Any] | None = None,
                    advances: dict[int, int] | None = None) -> list[int]:
        """Where each line starts, as offsets into *text*; *sizes* and *styles* are each character's size
        and style when the text mixes them, *advances* the width of each object set as a character."""

        starts: list[int] = []
        base = 0
        for line in text.split("\n"):
            points = None if sizes is None else [height / 100 for height in sizes[base:base + len(line)]]
            looks = None if styles is None else styles[base:base + len(line)]
            fixed = None if advances is None else {
                index - base: width for index, width in advances.items() if base <= index < base + len(line)}
            starts += [base + start for start in (hancom_line_starts(line, widths, size / 100, style, points, looks,
                                                                     fixed) if line else [0])]
            base += len(line) + 1
        return starts

    def stack(self, paragraphs: list[Any], width: int, caches: bool) -> tuple[int, int, int, int]:
        """(height, lines, pitch, size) of *paragraphs* laid out one under another at *width*; pitch
        and size are the last paragraph's. With *caches* a paragraph keeps the lines of its cache."""

        height, lines, pitch, size, pending = 0, 0, 0, 0, None
        for paragraph in paragraphs:
            runs = paragraph.findall(f"{HP}run")
            refs = [run.get("charPrIDRef") for run in runs] or ["0"]
            size = self.char_height(refs[0])
            shape = self.shape(paragraph.get("paraPrIDRef"))
            pitch = _pitch(shape.kind, shape.value, size)
            table = _table_alone(runs)
            if table is not None:  # one line as tall as the table, spaced like the text
                tall = _inline_table_height(self, table) + _extent_margins(table)
                count, size, pitch = 1, tall, tall + pitch - size
            else:
                cached = _cached_metrics(paragraph) if caches else ()
                cached = cached or self.marked_lines(paragraph, runs, width) \
                    or self.mixed_lines(paragraph, runs, shape, width)
                if cached:  # the lines Hancom laid out, each as tall as it drew it
                    if pending is not None:
                        height += pending + shape.prev
                    height += sum(advance for _, advance in cached[:-1]) + cached[-1][0]
                    size, pitch = cached[-1]
                    pending = pitch - size + shape.next
                    lines += len(cached)
                    continue
                style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
                count = (_cache_lines(paragraph) if caches else 0) or self.lines(
                    _run_text(runs), _line_widths(shape, width, style), size, style
                )
            if pending is not None:
                height += pending + shape.prev
            height += (count - 1) * pitch + size
            pending = pitch - size + shape.next
            lines += count
        return height, lines, pitch, size

    def mixed_lines(self, paragraph: Any, runs: list[Any], shape: _Shape, width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph whose characters differ in size or style, laid out at
        *width* as in the body; empty for one whose characters do not."""

        _, refs, sizes = _text_size(self, runs)
        looks = _char_styles(self, paragraph, runs)
        if len(set(sizes)) < 2 and looks is None:
            return ()
        style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        return _line_metrics(self, _run_text(runs), _line_widths(shape, width, style), sizes, style, shape, {}, looks)

    def stack_lines(self, paragraphs: list[Any], width: int, caches: bool) -> tuple[tuple[int, int], ...]:
        """(height, advance to the next line's top) of every line of *paragraphs* laid out as in
        :meth:`stack`, a table set as a character alone in its paragraph as one line."""

        metrics: list[tuple[int, int]] = []
        for paragraph in paragraphs:
            shape = self.shape(paragraph.get("paraPrIDRef"))
            if metrics:  # the gap between the paragraphs
                last_height, last_advance = metrics[-1]
                metrics[-1] = (last_height, last_advance + shape.prev)
            runs = paragraph.findall(f"{HP}run")
            cached = () if _table_alone(runs) is not None or not caches else _cached_metrics(paragraph)
            if not cached and _table_alone(runs) is None:
                cached = self.marked_lines(paragraph, runs, width)
            if cached:
                metrics += list(cached[:-1]) + [(cached[-1][0], cached[-1][1] + shape.next)]
                continue
            height, count, pitch, size = self.stack([paragraph], width, caches)
            metrics += [(size, pitch)] * (count - 1) + [(height - (count - 1) * pitch, pitch + shape.next)]
        return tuple(metrics)

    def marked_lines(self, paragraph: Any, runs: list[Any], width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph holding composed characters or ruby text, laid
        out at *width* as in the body; empty for a paragraph holding neither."""

        if not _marks(runs):
            return ()
        shape = self.shape(paragraph.get("paraPrIDRef"))
        _check_ruby_spacing(runs, shape)
        text, sizes, looks, placed, marked = _inline_content(self, paragraph, runs)
        style = self.style(paragraph.get("paraPrIDRef"), [run.get("charPrIDRef") for run in runs] or ["0"], paragraph)
        return _line_metrics(self, text, _line_widths(shape, width, style), sizes, style, shape, placed,
                             looks if len(set(looks)) > 1 else None, marked)


@dataclass(frozen=True)
class _Row:
    height: int   # the row's full height
    lines: int    # lines of its tallest cell, for splitting between them
    pitch: int
    size: int
    margins: int  # top + bottom cell margins
    header: bool
    merged: bool = False  # under a cell merged over rows: no page break in or around it
    joined: bool = False  # a cell merged over rows joins it to the next row
    spare: int = 0        # room the row's declared height leaves under its text
    nested: bool = False  # a cell holds a table
    #: (height, advance) of each line of the row's tallest cell when it holds a table
    metrics: tuple[tuple[int, int], ...] = ()
    first: int = 0        # the tallest first line of any of its cells


@dataclass(frozen=True)
class _FlowTable:
    rows: list[_Row]
    mode: str                  # hp:tbl@pageBreak: CELL, TABLE or NONE
    repeat_header: bool
    margins: tuple[int, int]   # hp:outMargin top, bottom: kept above and below the table
    #: every cell as (the position of its first row in ``rows``, rows it spans, the cell as a row)
    cells: tuple[tuple[int, int, _Row], ...] = ()
    offset: int = 0            # alone in its paragraph: how far below the paragraph's line it starts
    caption: tuple[int, int] = (0, 0)  # a caption above it, below it: its lines and its gap
    cut: int = _SPARE_CUT      # how far above the body's foot its rows end at most

    @property
    def above(self) -> int:
        """Room above the first row: the top margin and a caption above."""

        return self.margins[0] + self.caption[0]

    @property
    def below(self) -> int:
        """Room below the last row: a caption below and the bottom margin."""

        return self.margins[1] + self.caption[1]


def _rows(measure: _Measure, table: Any) -> list[_Row]:
    """Each row as its tallest cell of one row: the cell's declared height or its content with its
    margins (a row with no cell of its own starts at 0). Then each cell merged over rows, the one
    ending first first, adds what its rows lack to the last of them."""

    return _table_rows(measure, table)[0]


def _table_rows(measure: _Measure, table: Any) -> tuple[list[_Row], list[tuple[int, int, _Row]]]:
    """The rows (see :func:`_rows`) and every cell as (its first row's position, rows spanned, the cell
    as a row)."""

    rows: dict[int, _Row] = {}
    merged: list[tuple[int, int, _Row]] = []  # (first row, rows spanned, the cell as a row)
    cells: list[tuple[int, int, _Row]] = []
    nested: set[int] = set()  # rows with a cell holding a table
    headers: set[int] = set()  # rows with a header cell of their own
    firsts: dict[int, int] = {}  # each row's tallest first line of a cell of its own
    for tc in (tc for tr in table.findall(f"{HP}tr") for tc in tr.findall(f"{HP}tc")):
        row, span = _cell_row(measure, table, tc), _row_span(tc)
        address = tc.find(f"{HP}cellAddr")
        first = int(address.get("rowAddr", 0)) if address is not None else len(rows)
        cells.append((first, span, row))
        if row.nested:
            nested.update(range(first, first + span))
        if row.header and span == 1:
            headers.add(first)
        if span == 1:
            firsts[first] = max(firsts.get(first, 0), row.first)
        if span > 1:
            merged.append((first, span, row))
        elif first not in rows or (row.height, row.lines) > (rows[first].height, rows[first].lines):
            rows[first] = row
    for first in headers:  # a header row whatever cell is the tallest
        rows[first] = replace(rows[first], header=True)
    for first, line in firsts.items():
        rows[first] = replace(rows[first], first=line)
    for first, span, cell in merged:
        for index in range(first, first + span):
            if index not in rows:  # every cell over it is merged over rows
                rows[index] = replace(cell, height=0, lines=1, margins=0, spare=0)
    for first, span, cell in sorted(merged, key=lambda cell: (cell[0] + cell[1], cell[0])):
        spanned = range(first, first + span)
        for index in spanned:
            rows[index] = replace(rows[index], merged=True, joined=rows[index].joined or index < first + span - 1)
        last = rows[first + span - 1]
        lacking = cell.height - sum(rows[index].height for index in spanned)
        rows[first + span - 1] = replace(last, height=last.height + max(lacking, 0))
    order = sorted(rows)  # a row address no cell covers is skipped
    place = {address: position for position, address in enumerate(order)}
    return ([replace(rows[address], nested=address in nested) for address in order],
            [(place[first], span, cell) for first, span, cell in cells])


def _row_span(cell: Any) -> int:
    span = cell.find(f"{HP}cellSpan")
    return 1 if span is None else int(span.get("rowSpan", 1))


def _table_alone(runs: list[Any]) -> Any:
    """The table set as a character that is all a paragraph holds, or ``None``."""

    children = [child for run in runs for child in run if _local(child) not in ("t", "secPr", "ctrl")]
    if len(children) != 1 or _local(children[0]) != "tbl" or _run_text(runs).strip():
        return None
    pos = children[0].find(f"{HP}pos")
    return children[0] if pos is not None and pos.get("treatAsChar") == "1" else None


def _margin(margin: Any, side: str) -> int:
    """One side of an object's outer margins (hp:outMargin): a negative one, which the file keeps as an
    unsigned 32-bit number, counts as none, as Hancom lays it out (and saves it)."""

    value = int(margin.get(side, 0))
    return 0 if value < 0 or value >= 1 << 31 else value


def _extent_margins(obj: Any) -> int:
    margin = obj.find(f"{HP}outMargin")
    return 0 if margin is None else _margin(margin, "top") + _margin(margin, "bottom")


def _drawn_lines(measure: _Measure, paragraphs: list[Any]) -> tuple[tuple[int, int], ...]:
    """(height, advance) of every line of *paragraphs* as Hancom placed them, when every paragraph keeps a
    valid layout cache; the last line reaches down to the foot of any top-and-bottom or square-wrapped
    object placed from its paragraph's top (where the paragraph's first line would stand without it).
    Empty otherwise."""

    if not paragraphs or not all(_cached_metrics(paragraph) for paragraph in paragraphs):
        return ()
    tops: list[int] = []
    heights: list[int] = []
    foot, after = 0, 0  # after: where the next paragraph's first line would stand
    for paragraph in paragraphs:
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        top = after + shape.prev if tops else 0
        for obj in (child for run in paragraph.findall(f"{HP}run") for child in run if _local(child) in _OBJECTS):
            pos = obj.find(f"{HP}pos")
            if pos is None or pos.get("treatAsChar") == "1" or _floating(obj):
                continue
            if obj.get("textWrap") not in ("TOP_AND_BOTTOM", "SQUARE") or pos.get("vertRelTo") != "PARA":
                return ()
            foot = max(foot, top + _down(pos) + _extent(obj, "height"))
        segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
        for segment in segments:
            tops.append(int(segment.get("vertpos", 0)))
            heights.append(int(segment.get("textheight", segment.get("vertsize", 0))))
        last = segments[-1]
        after = int(last.get("vertpos", 0)) + int(last.get("textheight", 0)) + int(last.get("spacing", 0)) \
            + shape.next
    if any(later < earlier for earlier, later in zip(tops, tops[1:])):
        return ()
    heights[-1] = max(heights[-1], foot - tops[-1])
    return tuple((height, (nxt - top) if nxt is not None else height)
                 for height, top, nxt in zip(heights, tops, [*tops[1:], None]))


def _down(pos: Any) -> int:
    """How far below its paragraph's top an object placed from there stands: one offset up (a negative
    offset, which the file keeps as an unsigned 32-bit number) stands at the paragraph's top."""

    offset = int(pos.get("vertOffset", 0))
    return 0 if offset < 0 or offset >= 1 << 31 else offset


def _cell_row(measure: _Measure, table: Any, cell: Any) -> _Row:
    paragraphs = cell.findall(f"{HP}subList/{HP}p")
    nested = cell.find(f".//{HP}tbl") is not None
    drawn: tuple[tuple[int, int], ...] = ()
    if nested and any(paragraph.find(f".//{HP}tbl") is not None
                      and _table_alone(paragraph.findall(f"{HP}run")) is None for paragraph in paragraphs):
        drawn = _drawn_lines(measure, paragraphs)  # among text, or not set as a character: as Hancom drew it
        if not drawn:
            raise _Unsupported("a nested table")
    size = cell.find(f"{HP}cellSz")
    margins = cell_margins_of(cell, table)
    inner = int(size.get("width", 0)) - margins.left - margins.right
    content, lines, pitch, char_size = measure.stack(paragraphs, inner, caches=True)
    if drawn:
        content, lines = sum(advance for _, advance in drawn[:-1]) + drawn[-1][0], len(drawn)
    vertical = margins.top + margins.bottom
    height = max(int(size.get("height", 0)), vertical + content)
    first = drawn[0][0] if drawn else (measure.stack_lines(paragraphs[:1], inner, caches=True) or ((0, 0),))[0][0]
    return _Row(height, lines, pitch, char_size, vertical, cell.get("header") == "1",
                spare=height - vertical - content, nested=nested,
                metrics=(drawn or measure.stack_lines(paragraphs, inner, caches=True)) if nested else (),
                first=first)


@dataclass(frozen=True)
class _Wrap:
    """The band a square-wrapped object takes beside the text, from *top* to *bottom* below the top of
    the first line of the paragraph at hand; a line in it is *cut* narrower. A top-and-bottom object's
    band (*push*) has no room beside it: the first line reaching it goes below it instead."""

    top: int
    bottom: int
    cut: int
    push: bool = False

    def lower(self, by: int) -> "_Wrap | None":
        """The band seen from *by* further down, or ``None`` once it is above."""

        return _Wrap(self.top - by, self.bottom - by, self.cut, self.push) if self.bottom > by else None


@dataclass(frozen=True)
class _Anchor:
    """A top-and-bottom object anchored in a paragraph of text: it stands at the top of line *line*,
    and that line and the rest of the paragraph come below it."""

    line: int
    table: _FlowTable | None  # a table flowing with the text, or
    height: int               # the height of any other object, its outer margins included


@dataclass(frozen=True)
class _Band:
    """A table flowing with the text, top and bottom in a paragraph of text and *offset* down from the top
    of line *line* (its outer margin above included): it flows from there over the page end, and the
    first line reaching it, in that paragraph or the ones after, and the lines after go below its end."""

    line: int
    offset: int
    table: _FlowTable


@dataclass(frozen=True)
class _Para:
    lines: int
    size: int
    pitch: int
    prev: int
    next: int
    break_before: bool
    keep_lines: bool
    keep_next: bool
    widow_orphan: bool
    page_break: bool = False     # hp:p@pageBreak
    column_break: bool = False   # hp:p@columnBreak
    table: _FlowTable | None = None
    #: line index -> (height of the notes anchored in it, how many, size of the first one's first line)
    notes: dict[int, tuple[int, int, int]] = field(default_factory=dict)
    #: (height, advance) of each line from the paragraph's valid layout cache, or of each line of a
    #: paragraph of several character sizes; empty when every line is ``size`` tall and ``pitch`` apart.
    cached: tuple[tuple[int, int], ...] = ()
    anchor: _Anchor | None = None
    #: a square-wrapped object's band starts in this paragraph, this far below its first line's top
    wrap_bottom: int = 0
    #: how many of the first lines are beside such a band (they must stay on the band's page)
    wrap_lines: int = 0
    #: the line the object laid out around the text (the caller's) stands on
    wrap_anchor: int = 0
    band: _Band | None = None
    #: (top, bottom) in the body of a top-and-bottom object anchored here and placed from the paper's top
    paper: tuple[int, int] | None = None

    def height(self, line: int) -> int:
        return self.cached[line][0] if self.cached else self.size

    def advance(self, line: int) -> int:
        return self.cached[line][1] if self.cached else self.pitch

    def span(self, first: int, count: int) -> int:
        """From the top of line *first* to the top of the line *count* lines further down."""

        if not self.cached:
            return count * self.pitch
        return sum(self.cached[line][1] for line in range(first, first + count))


@dataclass(frozen=True)
class _Page:
    body: int
    column_width: int
    columns: int
    top: int = 0  # the body's top below the paper's
    left: int = 0  # the text's left edge right of the paper's
    text_width: int = 0
    paper_width: int = 0
    unequal: bool = False  # columns of unequal width (column_width is the narrowest)


def _page(section: Any) -> _Page:
    page = next(section.iter(f"{HP}pagePr"), None)
    margin = page.find(f"{HP}margin") if page is not None else None
    if margin is None:
        raise _Unsupported("no page settings")
    width, height = _drawn_page_size(int(page.get("width", 0)), int(page.get("height", 0)), page.get("landscape"))
    body = height - sum(int(margin.get(key, 0)) for key in ("top", "bottom", "header", "footer"))
    text_width = width - sum(int(margin.get(key, 0)) for key in ("left", "right", "gutter"))
    columns, column_width, unequal = _columns(section, text_width)
    return _Page(body, column_width, columns, int(margin.get("top", 0)) + int(margin.get("header", 0)),
                 int(margin.get("left", 0)) + int(margin.get("gutter", 0)), text_width, width, unequal)


def _columns(section: Any, text_width: int) -> tuple[int, int, bool]:
    """(count, width, unequal): the section's columns, their width (the narrowest when they differ)."""

    # Column settings in a cell or a text box (an hp:subList) belong to that list, not the section.
    settings = [cols for cols in section.iter(f"{HP}colPr") if not _in_sub_list(cols)]
    if len(settings) > 1:
        raise _Unsupported("the columns change inside the section")
    count = int(settings[0].get("colCount", "1")) if settings else 1
    if count <= 1:
        return 1, text_width, False
    if settings[0].get("sameSz") != "1":  # each column takes its share of the width with the gaps (hp:colSz)
        sizes = settings[0].findall(f"{HP}colSz")
        total = sum(int(size.get("width", 0)) + int(size.get("gap", 0)) for size in sizes)
        if len(sizes) != count or total <= 0:
            raise _Unsupported("columns of unequal width")
        return count, min(int(size.get("width", 0)) * text_width // total for size in sizes), True
    gap = int(settings[0].get("sameGap", 0))
    return count, (text_width - (count - 1) * gap) // count // 4 * 4, False


def _in_sub_list(element: Any) -> bool:
    return any(_local(ancestor) == "subList" for ancestor in element.iterancestors())


def _caption(measure: _Measure, table: Any) -> tuple[int, int]:
    """How much room a table's caption takes above it and below it: its lines and its gap (a caption
    beside the table takes none)."""

    caption = table.find(f"{HP}caption")
    if caption is None or caption.get("side") not in ("TOP", "BOTTOM"):
        return (0, 0)
    paragraphs = caption.findall(f"{HP}subList/{HP}p")
    width = int(caption.get("lastWidth", 0)) or int(table.find(f"{HP}sz").get("width", 0))
    tall = measure.stack(paragraphs, width, caches=True)[0] + int(caption.get("gap", 0))
    return (tall, 0) if caption.get("side") == "TOP" else (0, tall)


def _inline_table_height(measure: _Measure, table: Any) -> int:
    """A table set as a character: its rows as the estimate measures them. When the row model does not
    follow the table (merged rows, a nested table) but every paragraph in it keeps a valid layout cache,
    Hancom laid it out as it is, and the height it saved (hp:sz) is the height it draws."""

    if table.find(f".//{HP}tbl") is not None or any(_row_span(tc) != 1 for tc in table.iter(f"{HP}tc")):
        paragraphs = list(table.iter(f"{HP}p"))
        if paragraphs and all(_cache_lines(paragraph) for paragraph in paragraphs):
            return int(table.find(f"{HP}sz").get("height", 0))
    return sum(row.height for row in _rows(measure, table))


@dataclass(frozen=True)
class _NoteShape:
    above: int = 0     # hp:noteSpacing@aboveLine
    line: int = 0      # the separator's width
    below: int = 0     # hp:noteSpacing@belowLine
    between: int = 0   # hp:noteSpacing@betweenNotes

    def area(self, height: int, count: int) -> int:
        return 0 if count == 0 else self.above + self.line + self.below + height + self.between * (count - 1)


def _note_shape(section: Any) -> _NoteShape:
    if next(section.iter(f"{HP}endNote"), None) is not None:
        raise _Unsupported("endnotes")
    settings = next(section.iter(f"{HP}footNotePr"), None)
    if settings is None:
        return _NoteShape()
    placement = settings.find(f"{HP}placement")
    if placement is not None and placement.get("beneathText") == "1":
        raise _Unsupported("footnotes beneath the text")
    spacing = settings.find(f"{HP}noteSpacing")
    rule = settings.find(f"{HP}noteLine")
    millimetres = float((rule.get("width", "0 mm") if rule is not None else "0 mm").split()[0])

    def value(name: str) -> int:
        return int(spacing.get(name, 0)) if spacing is not None else 0

    return _NoteShape(value("aboveLine"), round(millimetres * 7200 / 25.4), value("belowLine"), value("betweenNotes"))


def _check_section(section: Any) -> None:
    grid = next(section.iter(f"{HP}grid"), None)
    if grid is not None and (grid.get("lineGrid", "0") != "0" or grid.get("charGrid", "0") != "0"):
        raise _Unsupported("a line or character grid")
    # Hancom starts a new section, on a new page, at a later paragraph holding section settings.
    if any(next(paragraph.iter(f"{HP}secPr"), None) is not None for paragraph in section.findall(f"{HP}p")[1:]):
        raise _Unsupported("section settings (hp:secPr) after the first paragraph")


def _placed_objects(runs: list[Any]) -> list[Any]:
    """The objects of the runs."""

    objects = [child for run in runs for child in run if _local(child) in _OBJECTS]
    for obj in objects:
        if obj.find(f"{HP}pos") is None or obj.find(f"{HP}sz") is None:
            raise _Unsupported(f"{_local(obj)} without a position")
    return [obj for obj in objects if not _floating(obj) and not _on_paper(obj)]


def _marks(runs: list[Any]) -> bool:
    """Whether the runs hold composed characters or ruby text."""

    return any(_local(child) in _MARKS for run in runs for child in run)


def _check_ruby_spacing(runs: list[Any], shape: _Shape) -> None:
    """A line holding ruby text is spaced from its height in percent: other line spacing is not followed."""

    if shape.kind != "PERCENT" and any(_local(child) == "dutmal" for run in runs for child in run):
        raise _Unsupported("ruby text in a paragraph with line spacing other than percent")


def _mark_extent(mark: Any, size: int, style: Any) -> tuple[int, int]:
    """(width, height) a composed character or ruby text takes as a character of *size* and *style*. A
    composed one is as wide as a Hangul syllable when framed or spread, else as its widest character,
    and no taller than the text. Ruby text is as wide as its text, however long the ruby, and as tall as
    the text with the ruby above it, or below it over the text's foot, in 1/1800 inch."""

    points = size / 100
    if _local(mark) == "compose":
        text = mark.get("composeText", "")
        if mark.get("circleType", "CHAR") != "CHAR" or mark.get("composeType") == "SPREAD" or not text:
            return round(char_advance("\uac00", points, style)), size
        return round(max(char_advance(ch, points, style) for ch in text)), size
    position = mark.get("posType", "TOP")
    if position not in ("TOP", "BOTTOM"):
        raise _Unsupported(f"ruby text placed {position}")
    main = mark.find(f"{HP}mainText")
    width = round(sum(char_advance(ch, points, style) for ch in (main.text or "" if main is not None else "")))
    em, ruby = size // 4, size * (int(mark.get("szRatio") or 0) or 50) // 100 // 4
    return width, 4 * (em + ruby if position == "TOP" else em * 91 // 100 + ruby)


def _on_paper(obj: Any) -> bool:
    """A top-and-bottom object placed from the paper's top, not set as a character: it takes no room in
    its paragraph but keeps every line of its page out of its band."""

    pos = obj.find(f"{HP}pos")
    return (pos is not None and pos.get("treatAsChar") != "1" and obj.get("textWrap") == "TOP_AND_BOTTOM"
            and pos.get("vertRelTo") == "PAPER" and pos.get("vertAlign", "TOP") == "TOP")


def _paper_band(measure: _Measure, page: _Page, paragraph: Any) -> tuple[int, int] | None:
    """(top, bottom) in the body of the object of *paragraph* placed on the paper, if any."""

    placed = [child for run in paragraph.findall(f"{HP}run") for child in run
              if _local(child) in _OBJECTS and _on_paper(child)]
    if not placed:
        return None
    if len(placed) > 1 or (page.columns > 1 and not _across_the_text(placed[0], page)):
        raise _Unsupported("objects placed on the paper")
    obj = placed[0]
    tall = _extent(obj, "height")
    if _local(obj) == "tbl":  # as tall as its rows
        tall += sum(row.height for row in _rows(measure, obj)) - int(obj.find(f"{HP}sz").get("height", 0))
    top = int(obj.find(f"{HP}pos").get("vertOffset", 0)) - page.top
    return top, top + tall


def _across_the_text(obj: Any, page: _Page) -> bool:
    """Whether an object placed from the paper's left covers the text's whole width (every column)."""

    pos = obj.find(f"{HP}pos")
    if pos.get("horzRelTo") != "PAPER":
        return False
    width, offset = _extent(obj, "width"), int(pos.get("horzOffset", 0))
    left = {"LEFT": offset, "CENTER": (page.paper_width - width) // 2 + offset,
            "RIGHT": page.paper_width - width - offset}.get(pos.get("horzAlign", "LEFT"))
    return left is not None and left <= page.left and left + width >= page.left + page.text_width


def _floating(obj: Any) -> bool:
    """An object in front of or behind the text, not set as a character: the text flows as if it were not
    there."""

    pos = obj.find(f"{HP}pos")
    return obj.get("textWrap") in _FLOATING and (pos is None or pos.get("treatAsChar") != "1")


def _text_size(measure: _Measure, runs: list[Any]) -> tuple[int, list[Any], list[int]]:
    """The paragraph's character size (its smallest), the character shapes of its runs holding text
    (the style comes from the first), and each character's size. An empty run takes no room."""

    lengths = [sum(len(_t_text(text)) for text in run.findall(f"{HP}t")) for run in runs]
    refs = [run.get("charPrIDRef") for run, length in zip(runs, lengths) if length]
    refs = refs or [run.get("charPrIDRef") for run in runs if run.find(f"{HP}t") is not None]
    refs = refs or [run.get("charPrIDRef") for run in runs] or ["0"]
    sizes: list[int] = []
    for run, length in zip(runs, lengths):
        sizes += [measure.char_height(run.get("charPrIDRef"))] * length
    return min(sizes or [measure.char_height(ref) for ref in refs]), refs, sizes


def _char_styles(measure: _Measure, paragraph: Any, runs: list[Any]) -> list[Any] | None:
    """Each character's style from its own run when the runs holding text differ in face, 장평 or 자간;
    ``None`` when they do not."""

    para_pr = paragraph.get("paraPrIDRef")
    looks: list[Any] = []
    for run in runs:
        length = sum(len(_t_text(text)) for text in run.findall(f"{HP}t"))
        if length:
            looks += [measure.style(para_pr, [run.get("charPrIDRef")])] * length
    return looks if len(set(looks)) > 1 else None


def _line_metrics(measure: _Measure, text: str, widths: list[float], sizes: list[int], style: Any,
                  shape: _Shape, objects: dict[int, tuple[int, int]], styles: list[Any] | None = None,
                  marks: dict[int, int] | None = None) -> tuple[tuple[int, int], ...]:
    """(height, advance) of each line FormFit breaks *text* into, every character at its own size: a line
    is as tall as its largest character, its line spacing reckoned from that size. An object set as a
    character (*objects*: its place in *text* -> its width and height) takes its width on its line and
    makes the line at least as tall as itself, and counts at its run's size for the spacing; a fixed line spacing
    keeps the next line that far down. A composed character or ruby text (*marks*: its place -> its
    width) is a character of its size in *sizes*."""

    advances = {**{index: width for index, (width, _) in objects.items()}, **(marks or {})} or None
    starts = measure.line_starts(text, widths, min(sizes), style, sizes if len(set(sizes)) > 1 else None, styles,
                                 advances)
    metrics = []
    for start, end in zip(starts, [*starts[1:], len(text)]):
        span = range(start, end) if end > start else range(len(text) - 1, len(text))
        size = max(sizes[index] for index in span)
        height = max([size] + [objects[index][1] for index in span if index in objects])
        advance = _pitch(shape.kind, shape.value, size)
        metrics.append((height, advance if shape.kind == "FIXED" else height + advance - size))
    return tuple(metrics)


def _object_extent(obj: Any, measure: _Measure) -> tuple[int, int]:
    """(width, height) an object set as a character takes, its outer margins included; a table as tall
    as its rows."""

    size = obj.find(f"{HP}sz")
    margin = obj.find(f"{HP}outMargin")
    extra = (0, 0, 0, 0) if margin is None else tuple(_margin(margin, side) for side in ("left", "right", "top", "bottom"))
    height = _inline_table_height(measure, obj) + sum(_caption(measure, obj)) if _local(obj) == "tbl" \
        else int(size.get("height", 0))
    return int(size.get("width", 0)) + extra[0] + extra[1], height + extra[2] + extra[3]


def _inline_content(measure: _Measure, paragraph: Any, runs: list[Any]) -> tuple[
        str, list[int], list[Any], dict[int, tuple[int, int]], dict[int, int]]:
    """The paragraph's text with each object set as a character, composed character and ruby text in its
    place (U+FFFC), each character's size and style (ruby text's is the height of its line), each
    object's place -> its width and height, and each composed character's or ruby text's place -> its
    width. Objects placed otherwise, and line spacing between lines or at least with an object among
    text, are not followed."""

    shape = measure.shape(paragraph.get("paraPrIDRef"))
    text: list[str] = []
    sizes: list[int] = []
    looks: list[Any] = []
    objects: dict[int, tuple[int, int]] = {}
    marks: dict[int, int] = {}
    for run in runs:
        ref = run.get("charPrIDRef")
        height, look = measure.char_height(ref), measure.style(paragraph.get("paraPrIDRef"), [ref])
        for child in run:
            name = _local(child)
            if name in _OBJECTS and (_floating(child) or _on_paper(child)):
                continue
            if name in _OBJECTS:
                if child.find(f"{HP}pos").get("treatAsChar") != "1" or shape.kind not in ("PERCENT", "FIXED"):
                    raise _Unsupported("an object with text or other objects in its paragraph")
                objects[len(text)] = _object_extent(child, measure)
                part = "\ufffc"
            elif name in _MARKS:
                marks[len(text)], tall = _mark_extent(child, height, look)
                text.append("\ufffc")
                sizes.append(tall)
                looks.append(look)
                continue
            elif name == "t":
                part = _t_text(child)
            else:
                continue
            text += part
            sizes += [height] * len(part)
            looks += [look] * len(part)
    return "".join(text), sizes, looks, objects, marks


def _anchored_object(objects: list[Any], text: str, column: int) -> Any:
    """The one object of a paragraph of text that is placed top and bottom from the paragraph's top
    (offset 0), or ``None``."""

    if len(objects) != 1 or not text.strip():
        return None
    obj = objects[0]
    pos = obj.find(f"{HP}pos")
    if pos.get("treatAsChar") == "1" or not _wraps_top_and_bottom(obj, column):
        return None
    if pos.get("vertRelTo") != "PARA" or pos.get("vertAlign", "TOP") != "TOP" or int(pos.get("vertOffset", 0)):
        return None
    return obj


def _anchor_line(measure: _Measure, paragraph: Any, runs: list[Any], text: str, obj: Any, widths: list[float],
                 size: int, style: Any, cached: tuple[tuple[int, int], ...], count: int) -> int:
    """The line *obj*'s place in the text falls on (Hancom counts an object as eight characters in a
    line cache)."""

    place = 0
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t":
            place += len(_t_text(child))
    if cached:
        starts = [int(segment.get("textpos", 0)) for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]
        starts = [start if start <= place else start - 8 for start in starts]
    else:
        starts = measure.line_starts(text, widths, size, style)
    return max((index for index, start in enumerate(starts[:count]) if start <= place), default=0)


def _anchor(measure: _Measure, paragraph: Any, runs: list[Any], text: str, obj: Any, widths: list[float], size: int,
            style: Any, cached: tuple[tuple[int, int], ...], count: int) -> _Anchor:
    """Where *obj* stands in the paragraph: at the top of the line its place in the text falls on."""

    line = _anchor_line(measure, paragraph, runs, text, obj, widths, size, style, cached, count)
    margin = obj.find(f"{HP}outMargin")
    top, bottom = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
    if _local(obj) == "tbl":
        rows, cells = _table_rows(measure, obj)
        table = _FlowTable(rows, obj.get("pageBreak", "CELL"), obj.get("repeatHeader") == "1", (top, bottom),
                           tuple(cells), caption=_caption(measure, obj), cut=_spare_cut(obj))
        return _Anchor(line, table, 0)
    return _Anchor(line, None, int(obj.find(f"{HP}sz").get("height", 0)) + top + bottom)


def _object_line(
    measure: _Measure, obj: Any, count: int, size: int, pitch: int, column: int
) -> tuple[int, int, int, _FlowTable | None]:
    """(lines, size, pitch, flowing table) of a paragraph holding *obj* and nothing else."""

    pos = obj.find(f"{HP}pos")
    out_margin = obj.find(f"{HP}outMargin")
    top, bottom = (0, 0)
    if out_margin is not None:
        top, bottom = _margin(out_margin, "top"), _margin(out_margin, "bottom")
    tall = int(obj.find(f"{HP}sz").get("height", 0)) + top + bottom
    name = _local(obj)
    if pos.get("treatAsChar") == "1":
        if name == "tbl":
            tall = _inline_table_height(measure, obj) + top + bottom + sum(_caption(measure, obj))
        return 1, tall, tall + pitch - size, None
    on_paragraph = pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"
    if _wraps_top_and_bottom(obj, column) and on_paragraph:
        if name == "tbl":
            rows, cells = _table_rows(measure, obj)
            offset = int(pos.get("vertOffset", 0))  # one up (a negative offset, kept unsigned) starts at the line
            table = _FlowTable(rows, obj.get("pageBreak", "CELL"), obj.get("repeatHeader") == "1", (top, bottom),
                               tuple(cells), 0 if offset < 0 or offset >= 1 << 31 else offset,
                               _caption(measure, obj), _spare_cut(obj))
            return count, size, pitch, table
        below = int(pos.get("vertOffset", 0)) + tall
        return 1, below, below, None
    raise _Unsupported(f"{name} placed {obj.get('textWrap')} relative to {pos.get('vertRelTo')}")


def _note_anchors(runs: list[Any]) -> list[tuple[int, Any]]:
    """(text offset, hp:footNote) of each footnote in the runs."""

    offset, anchors = 0, []
    for run in runs:
        for child in run:
            name = _local(child)
            if name == "t":
                offset += len(_t_text(child))
            elif name == "ctrl" and child.find(f"{HP}footNote") is not None:
                anchors.append((offset, child.find(f"{HP}footNote")))
    return anchors


def _anchored_notes(measure: _Measure, runs: list[Any], text: str, widths: list[float], size: int, style: Any,
                    width: int, sizes: list[int] | None = None,
                    styles: list[Any] | None = None) -> dict[int, tuple[int, int, int]]:
    anchors = _note_anchors(runs)
    if not anchors:
        return {}
    starts = measure.line_starts(text, widths, size, style, sizes, styles)
    anchored: dict[int, tuple[int, int, int]] = {}
    for offset, note in anchors:
        line = max(index for index, start in enumerate(starts) if start <= max(offset - 1, 0))
        paragraphs = note.findall(f"{HP}subList/{HP}p")
        tall = measure.stack(paragraphs, width, caches=False)[0]
        first_runs = paragraphs[0].findall(f"{HP}run") if paragraphs else []
        head = measure.char_height(first_runs[0].get("charPrIDRef") if first_runs else "0")
        height, many, first = anchored.get(line, (0, 0, 0))
        anchored[line] = (height + tall, many + 1, first or head)
    return anchored


def _paragraph(measure: _Measure, page: _Page, paragraph: Any, wrap: _Wrap | None = None,
               square: Any = None) -> _Para:
    runs = paragraph.findall(f"{HP}run")
    if page.unequal and not _cached_metrics(paragraph):  # its lines would depend on the column's width
        raise _Unsupported("a paragraph without a layout cache in columns of unequal width")
    objects = [obj for obj in _placed_objects(runs) if obj is not square]
    if page.unequal and any(obj.find(f"{HP}pos").get("treatAsChar") != "1" for obj in objects):
        raise _Unsupported("an object not set as a character in columns of unequal width")
    text = _run_text(runs)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    anchored = _anchored_object(objects, text, page.column_width)
    marks = _marks(runs) and not _cached_metrics(paragraph)  # to lay out like characters
    if marks:
        if anchored is not None or wrap is not None or square is not None:
            raise _Unsupported("composed characters or ruby text beside an object placed otherwise")
        _check_ruby_spacing(runs, shape)
    among = anchored is None and (marks or bool(objects) and (len(objects) > 1 or bool(text.strip())))
    alone = bool(objects) and not among and anchored is None  # an object with no text: one line as tall
    cached = () if alone else _cached_metrics(paragraph)
    size, refs, sizes = _text_size(measure, runs)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    widths: list[float] = _indented(page.column_width - shape.left - shape.right, shape, style)
    mixed = len(set(sizes)) > 1
    looks = _char_styles(measure, paragraph, runs)
    if among:
        inline_text, inline_sizes, inline_looks, placed, marked = _inline_content(measure, paragraph, runs)
        if not cached:
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            cached = _line_metrics(measure, inline_text, widths, inline_sizes, style, shape, placed, looks_or_none,
                                   marked)
    elif not cached and wrap is not None and not alone and text:
        if anchored is not None:
            raise _Unsupported("a top-and-bottom object beside a square-wrapped object")
        widths = _wrapped_widths(measure, text, widths, size, style, shape, wrap, sizes if mixed else None, looks)
        cached = _line_metrics(measure, text, widths, sizes, style, shape, {}, looks)
    elif not cached and not alone and (mixed or looks is not None):
        cached = _line_metrics(measure, text, widths, sizes, style, shape, {}, looks)
    count = len(cached) or measure.lines(text, widths, size, style)
    pitch = _pitch(shape.kind, shape.value, size)
    table = None
    if alone:
        if wrap is not None:
            raise _Unsupported("an object beside a square-wrapped object")
        if objects[0].find(f"{HP}pos").get("treatAsChar") == "1":  # spaced from the largest character size
            size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # of any of its runs
            pitch = _pitch(shape.kind, shape.value, size)
        count, size, pitch, table = _object_line(measure, objects[0], count, size, pitch, page.column_width)
    anchor = None if anchored is None else _anchor(measure, paragraph, runs, text, anchored, widths, size, style,
                                                   cached, count)
    around = 0 if square is None or not text else _anchor_line(measure, paragraph, runs, text, square, widths,
                                                                size, style, cached, count)
    if among and _note_anchors(runs):
        raise _Unsupported("footnotes in a paragraph with objects among its text")
    notes = _anchored_notes(measure, runs, text, widths, size, style, page.column_width, sizes if mixed else None,
                            looks)
    flags = shape.flags
    return _Para(count, size, pitch, shape.prev, shape.next, _on(flags, "pageBreakBefore"), _on(flags, "keepLines"),
                 _on(flags, "keepWithNext"), _on(flags, "widowOrphan"), paragraph.get("pageBreak") == "1",
                 paragraph.get("columnBreak") == "1", table, notes, cached, anchor, wrap_anchor=around)


def _extent(obj: Any, side: str) -> int:
    """An object's width or height (*side*), its outer margins included."""

    margin = obj.find(f"{HP}outMargin")
    ends = ("left", "right") if side == "width" else ("top", "bottom")
    extra = 0 if margin is None else sum(_margin(margin, end) for end in ends)
    return int(obj.find(f"{HP}sz").get(side, 0)) + extra


def _wraps_top_and_bottom(obj: Any, column: int) -> bool:
    """Top and bottom, or square with no room beside it: an object as wide as the column pushes the
    text below it either way."""

    wrap = obj.get("textWrap")
    return wrap == "TOP_AND_BOTTOM" or (wrap == "SQUARE" and _extent(obj, "width") >= column)


def _square_object(objects: list[Any], runs: list[Any], column: int) -> Any:
    """The one object of a paragraph wrapped square at the left or right edge of the column or of the
    paragraph, from the paragraph's top, before any text (text flows on the other side, or may flow on
    both), or ``None``."""

    if len(objects) != 1:
        return None
    obj = objects[0]
    pos = obj.find(f"{HP}pos")
    if pos.get("treatAsChar") == "1" or obj.get("textWrap") != "SQUARE" or _wraps_top_and_bottom(obj, column):
        return None
    placed = (pos.get("vertRelTo"), pos.get("vertAlign", "TOP"), pos.get("horzRelTo"), pos.get("horzAlign"))
    beside = {"LEFT": "RIGHT_ONLY", "RIGHT": "LEFT_ONLY"}.get(placed[3] or "")  # the text's side of it
    if placed[:2] != ("PARA", "TOP") or placed[2] not in ("COLUMN", "PARA") or beside is None \
            or int(pos.get("horzOffset", 0)) or obj.get("textFlow", "BOTH_SIDES") not in ("BOTH_SIDES", beside):
        raise _Unsupported(f"{_local(obj)} wrapped square elsewhere than at a column edge")
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t" and _t_text(child):
            raise _Unsupported(f"{_local(obj)} wrapped square after text")
    return obj


def _wrapped_paragraph(measure: _Measure, page: _Page, paragraph: Any,
                       wrap: _Wrap | None) -> tuple[_Para, _Wrap | None]:
    """The paragraph with the lines beside a square-wrapped object's band narrower, and the band as the
    next paragraph sees it."""

    runs = paragraph.findall(f"{HP}run")
    objects = _placed_objects(runs)
    square = _square_object(objects, runs, page.column_width)
    pusher = _pushing_object(objects, _run_text(runs), page.column_width)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    if wrap is not None:
        wrap = wrap.lower(shape.prev)
        if wrap is not None and (square is not None or pusher is not None or (wrap.push and objects)
                                 or _on(shape.flags, "pageBreakBefore")
                                 or paragraph.get("pageBreak") == "1" or paragraph.get("columnBreak") == "1"):
            raise _Unsupported("a page break or another object beside a square-wrapped object")
    if pusher is not None:
        para = _paragraph(measure, page, paragraph, None, pusher)
        offset = int(pusher.find(f"{HP}pos").get("vertOffset", 0))
        if _local(pusher) == "tbl" and pusher.get("pageBreak", "CELL") in ("CELL", "TABLE"):  # it flows
            rows, cells = _table_rows(measure, pusher)
            margin = pusher.find(f"{HP}outMargin")
            ends = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
            table = _FlowTable(rows, pusher.get("pageBreak", "CELL"), pusher.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_caption(measure, pusher), cut=_spare_cut(pusher))
            return replace(para, band=_Band(para.wrap_anchor, offset, table)), None
        top = para.span(0, para.wrap_anchor) + offset
        tall = _extent(pusher, "height")
        if _local(pusher) == "tbl":  # as tall as its rows
            tall += sum(row.height for row in _rows(measure, pusher)) - int(pusher.find(f"{HP}sz").get("height", 0))
        return _push(para, _Wrap(top, top + tall, 0, push=True), starts=True)
    if wrap is not None and wrap.push:
        return _push(_paragraph(measure, page, paragraph), wrap, starts=False)
    starts = square is not None
    if square is not None:
        top = int(square.find(f"{HP}pos").get("vertOffset", 0))
        cut = _extent(square, "width")
        if page.column_width - cut < _MIN_LINE_WIDTH:
            raise _Unsupported(f"{_local(square)} wrapped square leaving little room for text")
        tall = _extent(square, "height")
        if _local(square) == "tbl":  # as tall as its rows
            tall += sum(row.height for row in _rows(measure, square)) - int(square.find(f"{HP}sz").get("height", 0))
        wrap = _Wrap(top, top + tall, cut)
    para = _paragraph(measure, page, paragraph, wrap, square)
    if wrap is not None and (para.anchor is not None or para.table is not None):
        raise _Unsupported("an object beside a square-wrapped object")
    if wrap is None:
        return para, None
    beside = sum(1 for line in range(para.lines) if para.span(0, line) < wrap.bottom)
    para = replace(para, wrap_lines=beside, wrap_bottom=wrap.bottom if starts else 0)
    return para, wrap.lower(para.span(0, para.lines) + para.next)


def _pushing_object(objects: list[Any], text: str, column: int) -> Any:
    """The one object of a paragraph of text placed top and bottom below the line it stands on (an
    offset down from the paragraph's top), or ``None``."""

    if len(objects) != 1 or not text.strip():
        return None
    obj = objects[0]
    pos = obj.find(f"{HP}pos")
    if pos.get("treatAsChar") == "1" or not _wraps_top_and_bottom(obj, column):
        return None
    if pos.get("vertRelTo") != "PARA" or pos.get("vertAlign", "TOP") != "TOP" or int(pos.get("vertOffset", 0)) <= 0:
        return None
    return obj


def _push(para: _Para, band: _Wrap, *, starts: bool) -> tuple[_Para, _Wrap | None]:
    """*para* with the first line reaching a top-and-bottom object's *band* moved below it (the lines
    after follow), and the band as the next paragraph sees it (``None`` once a line went below it).
    The object stays on one page with the lines above it (*starts*: its band starts in *para*)."""

    if para.anchor is not None or para.table is not None:
        raise _Unsupported("an object beside a top-and-bottom object's band")
    metrics = list(para.cached) or [(para.size, para.pitch)] * para.lines
    top, rest = 0, None
    for index, (height, advance) in enumerate(metrics):
        if top < band.bottom and top + height > band.top:
            shift = band.bottom - top
            if index == 0:
                pushed = replace(para, prev=para.prev + shift)
            else:
                metrics[index - 1] = (metrics[index - 1][0], metrics[index - 1][1] + shift)
                pushed = replace(para, cached=tuple(metrics))
            break
        top += advance
    else:
        pushed, rest = para, band.lower(top + para.next)
    beside = sum(1 for line in range(para.lines) if para.span(0, line) < band.bottom)
    return replace(pushed, wrap_lines=beside, wrap_bottom=band.bottom if starts else 0), rest


def _wrapped_widths(measure: _Measure, text: str, widths: list[float], size: int, style: Any, shape: _Shape,
                    wrap: _Wrap, sizes: list[int] | None, looks: list[Any] | None) -> list[float]:
    """Each line's width with the lines whose top is in *wrap*'s band cut narrower (FormFit breaks the
    lines, and which lines are in the band follows from their heights; repeated until it settles)."""

    narrow: set[int] = set()
    for _ in range(8):
        lines = [widths[min(index, 1)] - (wrap.cut if index in narrow else 0) for index in range(max(narrow, default=0) + 2)]
        starts = measure.line_starts(text, lines, size, style, sizes, looks)
        top, found = 0, set()
        for index, (start, end) in enumerate(zip(starts, [*starts[1:], len(text)])):
            height = max((sizes or [size])[start:end] or [size]) if sizes else size
            if top < wrap.bottom and top + height > wrap.top:
                found.add(index)
            top += _pitch(shape.kind, shape.value, height)
        if found == narrow:
            return lines
        narrow = found
    raise _Unsupported("lines beside a square-wrapped object that do not settle")


# -- laying the paragraphs out ---------------------------------------------------------------------


def _lines_of(para: _Para, first: int, count: int, *, prev: int, after: int) -> _Para:
    """Lines *first* .. *first* + *count* of *para* as a paragraph of their own."""

    cached = para.cached[first:first + count] if para.cached else ()
    return replace(para, lines=count, prev=prev, next=after, cached=cached, notes={}, anchor=None,
                   keep_next=False if after == 0 else para.keep_next)


def _repeated_header(table: _FlowTable) -> int:
    return sum(row.height for row in table.rows if row.header) if table.repeat_header else 0


def _spare_cut(table: Any) -> int:
    return _SPARE_CUT_FIXED if table.get("noAdjust") == "1" else _SPARE_CUT


def _starts_later(table: _FlowTable, y: int, body: int) -> bool:
    """Whether a table moved row by row (TABLE) has no room for its first row from *y*, so it starts on
    the next page. At the top of a page the row is drawn anyway."""

    if table.mode != "TABLE" or not table.rows:
        return False
    return y + table.rows[0].height > body - table.margins[1] - table.cut \
        and y != _repeated_header(table) + table.margins[0]


def _flow_table(table: _FlowTable, frame: int, y: int, body: int) -> tuple[int, int]:
    """Lay the rows out from vertical position *y*; the frame and position where the table ends."""

    body -= table.margins[1]  # the rows keep the table's bottom margin above the page end
    header = _repeated_header(table) + table.margins[0]  # and go on below its top margin on the next page
    foot = body - table.cut
    rows, index = table.rows, 0
    while index < len(rows):
        end = index
        while rows[end].joined and end + 1 < len(rows):
            end += 1
        if table.mode == "TABLE" and end > index:  # rows joined by merged cells move as one
            height = sum(row.height for row in rows[index:end + 1])
            if y + height > foot and y != header:
                if index == 0:
                    raise _Unsupported("a table whose first rows, merged together, have no room under its anchor")
                frame, y = frame + 1, header
            if y + height > foot:
                raise _Unsupported("rows merged together taller than a page")
            y, index = y + height, end + 1
            continue
        if table.mode == "CELL" and end > index and table.cells \
                and y + sum(row.height for row in rows[index:end + 1]) > foot:  # split cell by cell
            frame, y = frame + 1, header + _block_rest(table, index, end, y, body)
            if y > foot:
                raise _Unsupported("rows merged together taller than a page")
            index = end + 1
            continue
        before, start = frame, y
        frame, y = _flow_row(table.mode, rows[index], frame, y, body, header, table.cut)
        if rows[index].merged and frame != before:
            raise _Unsupported("a page break among rows merged in a flowing table")
        if index == len(rows) - 1 and table.caption[1] and frame == before and start != header \
                and y + table.caption[1] > foot:  # a caption below goes on with the last row
            frame, y = frame + 1, header + rows[index].height
        index += 1
    return frame, y


def _block_rest(table: _FlowTable, first: int, last: int, top: int, body: int) -> int:
    """How tall rows *first*..*last*, joined by merged cells, are on the next page when the page end
    falls among them in a table split between cell lines: every cell keeps the lines that fit above
    the page end and the rest go on. From the row the page end falls in, each row is as tall as the
    rest of its cells of one row (the rows after it whole), then each merged cell's rest, the one
    ending first first, adds what its rows lack to the last of them."""

    rows, tops, y, foot = table.rows, {}, top, body - table.cut
    for index in range(first, last + 1):
        tops[index] = y
        y += rows[index].height
    cut = next(index for index in range(first, last + 1) if tops[index] + rows[index].height > foot)
    heights = dict.fromkeys(range(cut, last + 1), 0)
    rests: list[tuple[int, int, int]] = []
    for start, span, cell in table.cells:
        end = start + span - 1
        if start < first or start > last or end < cut:
            continue  # another row, or done above the page end
        if start > cut:  # wholly on the next page
            rest = cell.height
        else:
            fitting = 0
            while fitting < cell.lines and tops[start] + cell.margins + fitting * cell.pitch + cell.size <= foot:
                fitting += 1
            if cell.spare and fitting:  # its text starts above the page end: the declared room is cut like a row's
                rest = tops[start] + cell.height - foot
                if rest <= _SPARE_DROPPED:
                    continue
            elif cell.spare:  # none of it fits: it goes on whole
                rest = cell.height
            elif fitting == cell.lines:
                continue
            else:
                rest = cell.margins + (cell.lines - fitting - 1) * cell.pitch + cell.size
        if span == 1:
            heights[start] = max(heights[start], rest)
        else:
            rests.append((max(start, cut), end, rest))
    for start, end, rest in sorted(rests, key=lambda item: (item[1], item[0])):
        lacking = rest - sum(heights[index] for index in range(start, end + 1))
        heights[end] += max(lacking, 0)
    return sum(heights.values())


def _flow_row(mode: str, row: _Row, frame: int, y: int, body: int, header: int,
              cut: int = _SPARE_CUT) -> tuple[int, int]:
    """A row that does not fit even a fresh page is drawn there anyway, cut at the paper's edge;
    CELL breaks a row between its lines, or a row taller than its text just above the page's foot."""

    remaining, height, metrics, nested = row.lines, row.height, row.metrics, row.nested
    foot = body - cut
    while True:
        if y + height <= foot:
            return frame, y + height
        fresh = y == header
        if mode == "CELL" and nested and row.spare:  # declared taller than its text: cut like any such row
            if y + row.margins + (metrics[0][0] if metrics else row.size) <= foot:  # once its first line fits
                rest = height - (foot - y)
                if rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y, nested = frame + 1, header, False
                remaining, height = 1, rest
                continue
            if fresh:
                return frame, y + height
            frame, y = frame + 1, header
            continue
        if mode == "CELL" and nested:  # between its lines, each as tall as it is (a table is one)
            if not metrics:
                raise _Unsupported("a page break in a flowing table row holding a table")
            fitting, top = 0, y + row.margins
            while fitting < len(metrics) and top + metrics[fitting][0] <= foot:
                top += metrics[fitting][1]
                fitting += 1
            if fitting:
                metrics = metrics[fitting:]
                height = row.margins + sum(advance for _, advance in metrics[:-1]) + metrics[-1][0]
            elif fresh:
                return frame, y + height
            frame, y = frame + 1, header
            continue
        if mode == "CELL":
            fitting = 0
            while fitting < remaining and y + row.margins + fitting * row.pitch + row.size <= foot:
                fitting += 1
            if fitting and remaining == row.lines and y + row.margins + row.first > foot:
                fitting = 0  # every cell's first line must fit, or the row goes on whole
            if fitting and row.spare:
                rest = height - (foot - y)
                if fitting < remaining and y + height - row.spare > foot:  # its text does not all fit:
                    rest = max(rest, row.margins + (remaining - fitting - 1) * row.pitch + row.size)  # it goes on
                elif rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y = frame + 1, header
                remaining, height = 1, rest
                continue
            if fitting:
                remaining -= fitting
                height = row.margins + (remaining - 1) * row.pitch + row.size
            elif fresh:
                return frame, y + height
        elif fresh:
            return frame, y + height
        frame, y = frame + 1, header


class _Paginator:
    """Frames (a page's columns, in order) and vertical positions of every line of a section."""

    def __init__(self, body: int, columns: int, notes: _NoteShape,
                 bands: dict[int, list[tuple[int, int]]] | None = None) -> None:
        self.body = body
        #: frame -> (top, bottom) of the objects placed on the paper there: no line in them
        self.bands = bands or {}
        self.columns = columns
        self.notes = notes
        self.out: list[tuple[int, int]] = []
        self.frame = 0
        self.last_vp: int | None = None
        self.last_pitch = 0
        self.pending_next = 0
        self.extra_frames = 0   # frames a table that does not split takes past the text
        self.table_end = 0      # the last frame a flowing table reaches
        self.reserved: dict[int, int] = {}  # frames a table starting past its anchor takes: where text starts
        self.wrap_frame = -1                  # the frame a square-wrapped object's band is on
        #: a flowing table's band no line has reached yet: its frame, top, bottom there (None when it goes
        #: on over the page end), and the frame and position where the lines after it go on
        self.band: tuple[int, int, int | None, int, int] | None = None
        self.page_notes = [0, 0]  # height and count of the notes on the current page
        self.carry = 0          # height of notes going on over the page end
        self.floor: int | None = None  # where the next paragraph starts at the highest: a table's end

    def run(self, paras: list[_Para]) -> int:
        """Lay *paras* out; the number of frames used."""

        for index, para in enumerate(paras):
            self._paragraph(index, paras, para)
        return max(self.out[-1][0] if self.out else 0, self.extra_frames, self.table_end) + 1

    def _paragraph(self, index: int, paras: list[_Para], para: _Para) -> None:
        start = para.prev if self.last_vp is None else self.last_vp + self.last_pitch + self.pending_next + para.prev
        if self.floor is not None:
            start, self.floor = max(start, self.floor), None
        if para.band is not None or self.band is not None:
            self._banded(index, paras, para, start)
            return
        if para.anchor is not None:
            self._anchored(index, paras, para, start)
            return
        start, broke = self._breaks(para, start)  # a flowing table in the paragraph starts there too
        table = para.table
        if table is not None and table.mode == "NONE" and start + sum(row.height for row in table.rows) > self.body:
            self.extra_frames = max(self.extra_frames, self.frame + 1)  # the table moves whole to the next page
        if table is not None and table.mode != "NONE":
            self._flow(para, table, start)
            return
        first = len(self.out)
        if self._lay(index, paras, para, start, broke):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.advance(para.lines - 1), para.next
        if para.wrap_bottom:  # the band starts here: it stays on this page
            self.wrap_frame = self.out[first][0]
            if self.out[first][1] + para.wrap_bottom > self.body:
                raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        if any(frame != self.wrap_frame for frame, _ in self.out[first:first + para.wrap_lines]):
            raise _Unsupported("a page break beside a square-wrapped or offset top-and-bottom object")

    def _flow(self, para: _Para, table: _FlowTable, start: int) -> None:
        if self.last_vp is not None and start + para.height(0) > self.body:  # the anchor line goes on
            start = self._next_frame(para, 0, True)                         # to the next page
        self.out.append((self.frame, start))  # the anchor paragraph's line, under the table's top
        before = self.frame
        top = start - para.prev + table.offset + table.above  # from the paragraph's top, above its spacing
        frame, end = _flow_table(table, self.frame, top, self.body)
        self._clear_of_paper(before, frame)
        self.table_end = max(self.table_end, frame)
        if start + para.height(0) <= self.body and _starts_later(table, top, self.body):
            self._starts_next_page(para, table, start, frame, end)
            return
        self.frame = frame
        if self.frame != before:
            self.page_notes = [0, 0]
            self.last_vp, self.last_pitch, self.pending_next = end + table.below, 0, para.next
        else:  # the next paragraph goes below the anchor line or the table, whichever is lower
            self.last_vp, self.last_pitch, self.pending_next = start, para.advance(0), para.next
            self.floor = end + table.below

    def _anchored(self, index: int, paras: list[_Para], para: _Para, start: int) -> None:
        """The lines before the anchor's line, the object at that line's top, then the rest of the
        paragraph below the object."""

        anchor = para.anchor
        assert anchor is not None
        if para.notes:
            raise _Unsupported("footnotes in a paragraph anchoring a top-and-bottom object")
        start, broke = self._breaks(para, start)
        head = _lines_of(para, 0, anchor.line, prev=para.prev, after=0)
        tail = _lines_of(para, anchor.line, para.lines - anchor.line, prev=0, after=para.next)
        top = start
        if head.lines:
            if not self._lay(index, paras, head, start, broke):
                raise _Unsupported("footnotes in a paragraph anchoring a top-and-bottom object")
            top = self.out[-1][1] + head.advance(head.lines - 1)
        if anchor.table is not None:
            table = anchor.table
            if _starts_later(table, top + table.above, self.body):
                raise _Unsupported("a top-and-bottom table anchored in text that starts on the next page")
            frame, end = _flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame)
            self.frame, self.table_end, end = frame, max(self.table_end, frame), end + table.below
        else:
            if top + anchor.height > self.body and top > 0:
                raise _Unsupported("a top-and-bottom object anchored in text at a page end")
            end = top + anchor.height
        self.last_vp, self.last_pitch, self.pending_next = end, 0, 0
        if self._lay(index, paras, tail, end, False):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], tail.advance(tail.lines - 1), para.next

    def _banded(self, index: int, paras: list[_Para], para: _Para, start: int) -> None:
        """A paragraph starting a flowing table's band (the table flows from its anchor line's top plus the
        offset), or one after it: its lines above the band stay, and the first line reaching the band and
        the lines after go on below the table's end."""

        if para.notes or para.anchor is not None or para.wrap_bottom \
                or (para.table is not None and (self.band is None or para.band is not None)) \
                or (self.band is not None and (para.band is not None or para.page_break or para.break_before
                                               or para.column_break)):
            raise _Unsupported("a page break or another object beside a top-and-bottom table's band")
        start, broke = self._breaks(para, start)
        if para.table is not None:  # a flowing table alone in its paragraph: its line goes below the band
            frame, top, bottom, end_frame, end = self.band
            if self.frame != frame or start + para.height(0) <= top or (bottom is not None and start >= bottom):
                raise _Unsupported("a page break or another object beside a top-and-bottom table's band")
            self.band = None
            if end_frame != self.frame:
                self.frame, self.page_notes = end_frame, [0, 0]
            self._flow(para, para.table, end + para.prev)
            return
        if para.band is not None:
            band, table = para.band, para.band.table
            top = start + para.span(0, band.line) + band.offset
            if start + para.span(0, band.line) + para.height(band.line) > self.body \
                    or top + table.above >= self.body or _starts_later(table, top + table.above, self.body):
                raise _Unsupported("a top-and-bottom table offset down from a line at a page end")
            frame, end = _flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame)
            self.table_end = max(self.table_end, frame)
            bottom = end + table.below
            self.band = (self.frame, top, bottom if frame == self.frame else None, frame, bottom)
        assert self.band is not None
        frame, top, bottom, end_frame, end = self.band
        if self.frame != frame:
            raise _Unsupported("a page break beside a top-and-bottom table's band")
        reaching = [line for line in range(para.lines)
                    if start + para.span(0, line) + para.height(line) > top
                    and (bottom is None or start + para.span(0, line) < bottom)]
        if not reaching:  # every line above the band, or past it
            if self._lay(index, paras, para, start, broke):
                self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.advance(para.lines - 1), \
                    para.next
            if self.frame != frame:
                raise _Unsupported("a page break beside a top-and-bottom table's band")
            if bottom is not None and start + para.span(0, para.lines - 1) >= bottom:
                self.band = None
            return
        first = reaching[0]
        head = _lines_of(para, 0, first, prev=para.prev, after=0)
        tail = _lines_of(para, first, para.lines - first, prev=0, after=para.next)
        if head.lines:
            self._lay(index, paras, head, start, broke)
            if self.frame != frame:
                raise _Unsupported("a page break beside a top-and-bottom table's band")
        self.band = None
        if end_frame != self.frame:
            self.frame, self.page_notes = end_frame, [0, 0]
        if self._lay(index, paras, tail, end, False):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], tail.advance(tail.lines - 1), para.next

    def _clear_of_paper(self, first: int, last: int) -> None:
        if any(frame in self.bands for frame in range(first, last + 1)):
            raise _Unsupported("a table on a page with an object placed on the paper")

    def _band_hit(self, para: _Para, first: int, count: int, start: int) -> tuple[int, int] | None:
        """(how many lines from line *first* come before it, its bottom) of the first object placed on the
        paper of this frame that one of *count* lines laid from *start* reaches, or ``None``."""

        bands = self.bands.get(self.frame)
        if not bands:
            return None
        for line in range(count):
            top = start + para.span(first, line)
            if top >= self.body:
                return None
            reached = [bottom for above, bottom in bands if top < bottom and top + para.height(first + line) > above]
            if reached:
                return line, max(reached)
        return None

    def _starts_next_page(self, para: _Para, table: _FlowTable, start: int, frame: int, end: int) -> None:
        """The anchor line fits but the table's first row does not, so the table starts on the next page
        and ends in *frame* at *end*. The text after it goes on under the anchor line, and on the pages the
        table takes, below the table."""

        taken = range(self.frame + 1, frame + 1)
        if any(page in self.reserved for page in taken):
            raise _Unsupported("two tables starting past their anchors on one page")
        self.reserved.update(dict.fromkeys(taken, self.body))
        self.reserved[frame] = end + table.below
        self.last_vp, self.last_pitch, self.pending_next = start, para.advance(para.lines - 1), para.next

    def _breaks(self, para: _Para, start: int) -> tuple[int, bool]:
        if self.last_vp is None:
            return start, False
        if para.page_break or para.break_before:
            self.frame = (self.frame // self.columns + 1) * self.columns
        elif para.column_break:
            self.frame += 1
        else:
            return start, False
        self.page_notes = [0, 0]
        return self._free_top() + para.prev, True

    def _lay(self, index: int, paras: list[_Para], para: _Para, start: int, broke: bool) -> bool:
        """Place the lines of *para*; False when its notes ended the page after it."""

        remaining, first_chunk = para.lines, True
        fresh = self.last_vp is None or broke
        while remaining:
            done = para.lines - remaining
            hit = self._band_hit(para, done, remaining, start)
            if hit is not None and hit[0] == 0:  # the line reaches an object placed on the paper: below it
                start = hit[1]
                continue
            count = self._chunk(index, paras, para, start, remaining, done, first_chunk)
            if count == 0 and (self.last_vp is None or fresh) and not self.reserved.get(self.frame):
                count = 1  # a line taller than the page still takes an empty page (and overflows it)
            if hit is not None and hit[0] < count:  # the lines above it stay, the next goes below it
                count = hit[0]
                self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
                self._place(para, done, count)
                remaining, start, first_chunk = remaining - count, hit[1], False
                continue
            self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
            self._place(para, done, count)
            remaining -= count
            if not remaining and self.carry:  # the page ends with this paragraph's notes
                self.frame += 1
                self.page_notes = [self.carry, 1]
                self.last_vp, self.last_pitch, self.pending_next = None, 0, 0
                return False
            if remaining:
                start = self._next_frame(para, count, first_chunk)
            fresh = bool(remaining)
            first_chunk = False
        return True

    def _next_frame(self, para: _Para, count: int, first_chunk: bool) -> int:
        self.frame += 1
        self.page_notes = [self.carry, 1] if self.carry else [0, 0]
        return self._free_top() + (para.prev if count == 0 and first_chunk else 0)

    def _free_top(self) -> int:
        """Where text starts in the current frame: below a table that starts past its anchor, the frames
        the table fills skipped."""

        while self.reserved.get(self.frame, 0) >= self.body:
            self.frame += 1
        return self.reserved.get(self.frame, 0)

    def _chunk(self, index: int, paras: list[_Para], para: _Para, start: int, remaining: int, done: int,
               first_chunk: bool) -> int:
        """How many of the paragraph's remaining lines stay in this frame."""

        count = self._fits(start, remaining, para, done)
        if not first_chunk:
            return count
        if count < remaining:
            count = self._keep_rules(para, start, remaining, count)
        if count == remaining and para.keep_next and index + 1 < len(paras):
            count = self._keep_with_next(para, paras[index + 1], start, remaining, count)
        return count

    def _keep_rules(self, para: _Para, start: int, remaining: int, count: int) -> int:
        if para.keep_lines and self._fits(para.prev, para.lines, para) == para.lines and start != para.prev:
            return 0
        if para.widow_orphan:
            if count == 1 and remaining > 1:
                return 0
            if remaining - count == 1 and count > 1:
                return count - 1
        return count

    def _keep_with_next(self, para: _Para, following: _Para, start: int, remaining: int, count: int) -> int:
        after = start + para.span(0, remaining) + para.next + following.prev
        need = 2 if following.widow_orphan and following.lines > 1 else 1
        if self._fits(after, need, following) < need and start != para.prev:
            return 0
        return count

    def _fits(self, start: int, count: int, para: _Para, first: int = 0) -> int:
        """How many of *count* lines (from line *first*) from *start* stay in the frame, each ending above
        the note area including the notes anchored in it. A line whose notes fit only in part (at least
        their first line) still stays, and ends the frame."""

        fitting, height, many = 0, self.page_notes[0], self.page_notes[1]
        self.carry = 0
        while fitting < count:
            note_height, notes, head = para.notes.get(first + fitting, (0, 0, 0))
            bottom = start + para.span(first, fitting) + para.height(first + fitting)
            if bottom < self.body - self.notes.area(height + note_height, many + notes):
                height, many, fitting = height + note_height, many + notes, fitting + 1
                continue
            if notes and bottom < self.body - self.notes.area(height + head, many + notes):
                room = self.body - bottom - self.notes.area(height, many + notes) + note_height
                self.carry = max(note_height - room, 0)
                fitting += 1
            break
        return fitting

    def _place(self, para: _Para, first: int, count: int) -> None:
        for line in range(first, first + count):
            note_height, notes, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes[0] += note_height
            self.page_notes[1] += notes


@dataclass(frozen=True)
class _SectionLayout:
    columns: int
    frames: int
    lines: list[tuple[int, int]]   # (frame, vertpos) of every line, in paragraph order
    counts: list[int]              # lines per paragraph


def _lay_section(measure: _Measure, section: Any) -> _SectionLayout:
    page = _page(section)
    notes = _note_shape(section)
    _check_section(section)
    paras = []
    wrap: _Wrap | None = None
    for paragraph in section.findall(f"{HP}p"):
        para, wrap = _wrapped_paragraph(measure, page, paragraph, wrap)
        band = _paper_band(measure, page, paragraph)
        paras.append(para if band is None else replace(para, paper=band))
    paper = {index: para.paper for index, para in enumerate(paras) if para.paper is not None}
    firsts = [sum(para.lines for para in paras[:index]) for index in range(len(paras))]
    bands: dict[int, list[tuple[int, int]]] = {}
    for _ in range(4):  # an object placed on the paper acts on the page its paragraph lands on
        paginator = _Paginator(page.body, page.columns, notes, bands)
        frames = paginator.run(paras)
        placed: dict[int, list[tuple[int, int]]] = {}
        for index, band in paper.items():  # on every column of the page
            first = paginator.out[firsts[index]][0] // page.columns * page.columns
            for frame in range(first, first + page.columns):
                placed.setdefault(frame, []).append(band)
        if placed == bands:
            break
        bands = placed
    else:
        raise _Unsupported("objects placed on the paper whose pages do not settle")
    return _SectionLayout(page.columns, frames, paginator.out, [para.lines for para in paras])


def _assemble(layouts: list[_SectionLayout]) -> PageEstimate:
    pages = 0
    lines: list[tuple[EstimatedLine, ...]] = []
    for layout in layouts:
        start = 0
        for count in layout.counts:
            lines.append(tuple(
                EstimatedLine(pages + frame // layout.columns, frame % layout.columns, vertpos)
                for frame, vertpos in layout.lines[start:start + count]
            ))
            start += count
        pages += (layout.frames - 1) // layout.columns + 1
    return PageEstimate(pages, tuple(lines), ())
