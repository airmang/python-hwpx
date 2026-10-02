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
  reckoned from that size; an empty run ending a paragraph makes its last line as tall as itself
  (one before the text does not), and a label in its own character shape is a character of that
  size on the paragraph's first line. Composed characters and ruby text (``hp:compose``, ``hp:dutmal``) take
  their place in the text like characters of their run: a composed one as wide as a Hangul syllable
  when framed (circle, box ...) or spread, else as its widest character, and no taller than the
  text; ruby text as wide as its text (however long the ruby), its line as tall as the text with
  the ruby (its size ratio, half when 0) above it, or below it over the text's foot (91/100 of the
  em, both counted in 1/1800 inch), and spaced from that height.
* Height: a line advances by the paragraph's line spacing (percent, fixed, between lines, at
  least), paragraphs add their spacing before and after, and a line stays on the page while its
  bottom is above the body's foot (one ending right at it goes on to the next page; in a section
  hiding a page's first empty lines, ``hp:visibility@hideFirstEmptyLine``, up to two paragraphs
  holding nothing that would start the next page or column stay below this one's foot, one on the
  other, and take no room). Page and
  column breaks, page break before, keep lines
  together, keep with next and widow/orphan control; columns of equal width, and columns of
  unequal width (each its share of the text width with the gaps, rounded) holding objects only as
  characters: a paragraph without a valid layout cache breaks the lines a column holds at that
  column's width, and going on into a column of another width breaks its rest there again, from
  the first character that column holds.
* Objects: an object in front of or behind the text takes no room: the lines go where they would
  without it, wherever it stands; one placed top and bottom from the top or the bottom of the paper
  or of the page (its body) keeps every line of its page out of its band (a line reaching it, in any
  paragraph on that page, goes below it -- on to the next page when the band reaches the body's
  foot -- and the lines after follow; with several columns of equal width, in each column it
  reaches over from the paper's left, centre or right, the others running past it), and so does one
  wrapped square there that leaves less than a line's room
  (1440) on either side of it across the text; one that leaves more (in one column) changes nothing
  when no line, table or object of its page reaches its band, and a line keeping its layout cache
  that reaches it stays where it is (beside it); anything else reaching it is not followed. An
  object anchored at the top of a paragraph's first line that such a band pushes down stands right
  below the band, the line below the object; a table flowing with the text alone in its paragraph
  stands there too, its paragraph's line below it. A table or picture set as a character is one
  line as tall as it.
  A table's caption above or below it takes its lines and its gap there (a caption below goes on
  to the next page with the table's last row when both do not fit above the foot, as a row would;
  when that row, split between cell lines, is declared taller than its text, its room to spare is
  cut above the caption instead, as it would be above the foot).
  Among text, an object set as a character takes its width on its line like a character, and the
  line is at least as tall as the object; the line spacing is reckoned from the line's largest
  character, the object counted at its run's character size (a fixed spacing keeps the next line
  that far down), and for an object with only spaces beside it from the largest size of any run of
  its paragraph. A top-and-bottom object anchored to an empty paragraph pushes the
  next line below
  it; anchored in a paragraph of text or of objects set as characters (from the paragraph's top),
  it stands at the top of the line
  its place in the text falls on, and that line and the rest of the paragraph come below it --
  offset down, it stands that much lower, and the first line reaching it (in that paragraph or the
  ones after) and the lines after come below it (a picture or drawing flowing with the text whose
  foot would pass the body's foot from where its paragraph stands goes on alone to the next page's
  top instead, whatever its offset, the lines of its own page as if it were not there and those
  reaching it there below it) -- a table flowing with the text flows from there
  over the page end, and that line goes below its end (so does the line of a paragraph holding only
  another such table, which then flows from there); offset down from a paragraph's first line that
  does not fit above the page's foot, it goes on to the next page with the line, and one whose top
  falls past the foot, or whose first row moved row by row does not fit under it, starts at the next
  page's top while the paragraph's lines go on under its line; a flowing table alone in its paragraph starts
  its offset below the paragraph's top, above the paragraph's spacing before (one offset up starts
  there), and the next paragraph goes below the table's end or below the paragraph's line and its
  own spacing before, whichever is lower; several anchored so to an empty paragraph (none up from it)
  go one by one to the first page, from the paragraph's on, where they fit below the earlier ones
  they overlap across (on the paragraph's page at their offset or below them, whichever is lower);
  the first, fitting there on none, flows from where it stands, and a later one starts at the top of
  the page after the last one used (a table taller than a page split over the pages after); the
  paragraph's line and the lines after take the first places clear of them;
  wrapped square anywhere across the column (from the column's, the paragraph's or the paper's left
  or right) before a paragraph's text (or alone in its paragraph), the text goes on each side of it
  at least 1440 wide that its text flow allows (both, the larger, the left or the right): a line
  whose top is above its foot, in that paragraph and the ones after, is narrower by what the object
  and its outer margins take (a drop cap is such an object), or, with text on both sides, is two
  pieces at one height, the left one first -- a table by the height
  of its rows; a picture or drawing, or a table set not to split, whose band passes the body's foot
  goes on alone to the next page's body top, whatever its offset: the lines of its own page are the
  whole width, and the lines on the next page whose top is above its foot go beside it (without
  layout caches, broken again there; a paragraph holding objects or a table there is not
  followed), while a table that may split is split over the page end as a flowing table, the lines
  on each page it reaches beside its part there (on a page it fills, all of them); a line beside an
  object with text on both sides is
  two pieces even when its text ends in the first or it has none (the second empty) -- and wrapped
  square with no room beside it (less than 1440 on each side its text flow
  allows), it pushes the text below it like a top-and-bottom object; a table flowing with the text is laid out row by row -- split between cell lines, moved row
  by row or moved whole -- with its header rows (any row with a header cell of its own)
  repeated; one set not to split takes its room under its anchor line when all its rows fit there,
  else it moves whole to the next page's top while the text after it goes on under its anchor line
  (anchored at the top of a paragraph of text, the paragraph goes on with it when the line below it
  does not fit either); a cell merged over rows that is taller
  than them adds what they lack to the last of them, the cell that ends first first (a row with no
  cell of its own starts at 0); in a table moved row by row, rows joined by a cell merged over them
  move to the next page as one, and in one split between cell lines each of their cells keeps the
  lines that fit and the rest go on, the rows from the one the page end falls in as tall as their
  cells' rest (a cell declared taller than its text, whose first line fits, is cut like such a row,
  below), a rest taller than a page split again at each page end the same way. A table set as a
  character alone in a paragraph of a cell is one line as tall as it
  there, spaced like the text, and a row holding one splits between its cell's lines, each as tall
  as it is; so is another object set as a character alone in a cell paragraph without a layout
  cache, and such objects among its text, or several of them, tables too, take their place in its
  lines as in the body (a table in a header, footer or note placed in a cell paragraph is laid out
  with that, not in the cell); a nested table among text, placed top and bottom or wrapped square
  is followed through
  the layout caches of its cell, as tall as Hancom drew it (down to such a table's foot; one placed
  up from its paragraph's top stands at that top; the caches of a row Hancom split over a page end
  start over at the next page's top, and are read as one run of lines, each line that goes back up
  where it would stand in the unsplit cell, a first line below such a table with the room above it,
  so the row splits again where it would). A picture or drawing placed top and bottom or wrapped
  square from a cell paragraph holding no text makes the cell reach its foot (outer margins
  included), and so does a table placed top and bottom from a cell paragraph holding nothing else,
  without such caches, as tall as its rows (one placed up from the paragraph's top stands at that
  top); what follows in the cell goes on below that foot. Before the paragraph's text, the first
  line reaching the table and the lines after it go below it. A flowing table's rows use
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

Anything else makes the estimate unsupported: endnotes, an object not set as a character in columns
of unequal width, and there a paragraph without such a cache holding objects, composed characters,
ruby text or footnotes, a column change inside a section (column
settings in a cell or a text box are that list's own), section settings after a section's first
paragraph (Hancom starts a new section there), a line or character grid, an object with text or
other objects in its paragraph (but objects set as characters, with line spacing in percent or
fixed, one top-and-bottom object placed from the paragraph's top, several so in an empty paragraph
(but in columns, or a picture or drawing past the page's foot), and one object wrapped square
across the column before any text; an object offset down, but a flowing table, or wrapped square
stays on one page with the lines above or beside it), footnotes in such a paragraph, two tables
starting past their
anchors on one page, rows merged together that do not fit under their table's anchor, or on a
page in a table moved row by row (split between cell lines: a cell no line of which fits a page),
a nested table not set as a character but one top and bottom in its paragraph,
before any text (two there are laid out otherwise), in a cell without such caches (in a table
Hancom has not laid out as it is), a page break in a flowing row holding a table beside a taller
cell, other objects placed on the page or the paper (but top and bottom from its top or bottom, a
flowing table on their page keeping clear of them), and in a paragraph without such a cache ruby text
placed other than above or below its text or with line spacing other than percent, and composed
characters or ruby text beside an object placed otherwise than as a character. ``pages`` is then
``None`` and
``unsupported`` says why, per section.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from ..form_fit.measure import (_GLYPH_SPACE, char_advance, hancom_line_starts, indented_widths, paragraph_label,
                                text_style_from_refs)
from ..oxml._document_primitives import _remove_stale_paragraph_layout_cache
from ..oxml.namespaces import HH, HP
from ..oxml.paragraph_heading import paragraph_heading
from ..oxml.section import _remove_short_paragraph_layout_cache
from ..oxml.header_part import HwpxOxmlHeader
from ..oxml.section_format import _drawn_page_size
from ..oxml.table_sizes import cell_margins_of, grid_widths_of

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
#: The narrowest side of a square-wrapped object text goes to (1/5 inch): Hancom leaves a narrower one empty.
_MIN_SIDE = 1440


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


class _BandMoves(Exception):
    """A square-wrapped object flowing with the text, anchored in paragraph *index* without a layout cache,
    passed the body's foot: the section is laid out again with it at the next page's top."""

    def __init__(self, index: int) -> None:
        super().__init__(index)
        self.index = index


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
    """The text of one ``hp:t``, with ``hp:lineBreak`` as a newline, ``hp:tab`` as a tab, ``hp:nbSpace`` as a
    no-break space (U+00A0) and ``hp:fwSpace`` as a fixed-width one (U+3000), as python-hwpx reads them; an
    ideographic space typed in the text is FormFit's ``_GLYPH_SPACE``, so it is not taken for a fixed-width one."""

    parts = [text_element.text or ""]
    for child in text_element:
        name = _local(child)
        parts.append({"lineBreak": "\n", "tab": "\t", "nbSpace": "\u00a0", "fwSpace": "\u3000"}.get(name, ""))
        parts.append(child.tail or "")
    return "".join(part.replace("\u3000", _GLYPH_SPACE) if index % 2 == 0 else part
                   for index, part in enumerate(parts))


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
    segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
    for segment, following in zip(segments, [*segments[1:], None]):
        height = int(segment.get("textheight", segment.get("vertsize", 0)))
        if height <= 0:  # a cache of empty lines is none
            return ()
        beside = following is not None and following.get("vertpos") == segment.get("vertpos") \
            and int(following.get("horzpos", 0)) > int(segment.get("horzpos", 0))  # two pieces of one line
        metrics.append((height, 0 if beside else height + int(segment.get("spacing", 0))))
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
        self._label_sizes: dict[str, int] = {}

    def shape(self, para_pr_id: Any) -> _Shape:
        key = str(para_pr_id)
        if key not in self._shapes:
            self._shapes[key] = _para_shape(self._header, key)
        return self._shapes[key]

    def char_height(self, char_pr_id: Any) -> int:
        style = self._root.char_property(char_pr_id)
        return int(style.attributes.get("height", 1000)) if style is not None else 1000

    def headed(self, paragraph: Any) -> bool:
        """Whether Hancom heads *paragraph* with a bullet or number label."""

        if self._drawn is None:
            self._drawn = _drawn_labels(self._root)
        return bool(self._drawn.get(paragraph))

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

    def label_size(self, para_pr_id: Any) -> int:
        """The character size of a paragraph shape's bullet or number label in its own character shape
        (``hh:paraHead@charPrIDRef``); 0 when it has none or takes its paragraph's."""

        key = str(para_pr_id)
        if key not in self._label_sizes:
            label = paragraph_label(self._root, para_pr_id)
            ref = label[1].get("charPrIDRef") if label is not None else None
            own = ref is not None and ref != "4294967295" and self._root.char_property(ref) is not None
            self._label_sizes[key] = self.char_height(ref) if own else 0
        return self._label_sizes[key]

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
                    advances: dict[int, int] | None = None, objects: Collection[int] = ()) -> list[int]:
        """Where each line starts, as offsets into *text*; *sizes* and *styles* are each character's size
        and style when the text mixes them, *advances* the width of each object set as a character (or
        mark), *objects* the places of the objects."""

        starts: list[int] = []
        base = 0
        for line in text.split("\n"):
            points = None if sizes is None else [height / 100 for height in sizes[base:base + len(line)]]
            looks = None if styles is None else styles[base:base + len(line)]
            fixed = None if advances is None else {
                index - base: width for index, width in advances.items() if base <= index < base + len(line)}
            placed = {index - base for index in objects if base <= index < base + len(line)}
            starts += [base + start for start in (hancom_line_starts(line, widths, size / 100, style, points, looks,
                                                                     fixed, placed) if line else [0])]
            base += len(line) + 1
        return starts

    def stack(self, paragraphs: list[Any], width: int, caches: bool) -> tuple[int, int, int, int]:
        """(height, lines, pitch, size) of *paragraphs* laid out one under another at *width*; pitch
        and size are the last paragraph's. With *caches* a paragraph keeps the lines of its cache."""

        height, lines, pitch, size, pending = 0, 0, 0, 0, None
        for paragraph in paragraphs:
            runs = paragraph.findall(f"{HP}run")
            size, refs, _ = _text_size(self, runs)  # an empty run takes no room, as in the body
            shape = self.shape(paragraph.get("paraPrIDRef"))
            pitch = _pitch(shape.kind, shape.value, size)
            table = _table_alone(runs)
            alone = None if table is not None or caches and _cached_metrics(paragraph) else _object_alone(runs)
            spread = self.spread_lines(paragraph, runs, width, caches=caches) \
                if table is not None or alone is not None else ()
            if spread:  # spaces besides it, some of which go on to the next line
                table = alone = None
            if table is not None:  # one line as tall as the table, spaced like the text
                tall = _inline_table_height(self, table) + _extent_margins(table)
                count, size, pitch = 1, tall, tall + pitch - size
            elif alone is not None:  # so with another object set as a character
                tall = _object_extent(alone, self)[1]
                count, size, pitch = 1, tall, tall + pitch - size
            else:
                cached = spread or (_cached_metrics(paragraph) if caches else ())
                cached = cached or self.pushed_lines(paragraph, runs, width) \
                    or self.marked_lines(paragraph, runs, width) or self.mixed_lines(paragraph, runs, shape, width)
                if cached:  # the lines Hancom laid out, each as tall as it drew it
                    if pending is not None:
                        height += pending + shape.prev
                    top = height
                    height += sum(advance for _, advance in cached[:-1]) + cached[-1][0]
                    size, pitch = cached[-1]
                    pending = pitch - size + shape.next
                    if top + _objects_reach(runs, self) > height:  # an object placed from it reaches lower
                        height, pending = top + _objects_reach(runs, self), shape.next
                    lines += len(cached)
                    continue
                style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
                count = (_cache_lines(paragraph) if caches else 0) or self.lines(
                    _run_text(runs), _line_widths(shape, width, style), size, style
                )
            if pending is not None:
                height += pending + shape.prev
            top = height
            height += (count - 1) * pitch + size
            pending = pitch - size + shape.next
            if top + _objects_reach(runs, self) > height:  # an object placed from the paragraph reaches lower
                height, pending = top + _objects_reach(runs, self), shape.next
            lines += count
        return height, lines, pitch, size

    def mixed_lines(self, paragraph: Any, runs: list[Any], shape: _Shape, width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph whose characters differ in size or style, laid out at
        *width* as in the body; empty for one whose characters do not."""

        _, refs, sizes = _text_size(self, runs)
        looks = _char_styles(self, paragraph, runs)
        end = _end_size(self, runs, sizes)
        head = _head_size(self, paragraph, sizes)
        if len(set(sizes)) < 2 and looks is None and not end and not head:
            return ()
        style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        return _line_metrics(self, _run_text(runs), _line_widths(shape, width, style), sizes, style, shape, {}, looks,
                             end=end, head=head)

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
            cached = cached or self.spread_lines(paragraph, runs, width, caches=caches)
            if not cached and _table_alone(runs) is None:  # each line as tall as stack makes it
                cached = self.pushed_lines(paragraph, runs, width) or self.marked_lines(paragraph, runs, width) \
                    or self.mixed_lines(paragraph, runs, shape, width)
            if cached:
                metrics += list(cached[:-1]) + [(cached[-1][0], cached[-1][1] + shape.next)]
                continue
            height, count, pitch, size = self.stack([paragraph], width, caches)
            last = height - (count - 1) * pitch  # down to the foot of an object placed from it: the next below
            metrics += [(size, pitch)] * (count - 1) + [(last, (last if last > size else pitch) + shape.next)]
        return tuple(metrics)

    def spread_lines(self, paragraph: Any, runs: list[Any], width: int, end: int = 0, head: int = 0,
                     caches: bool = False) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph holding one object set as a character and, besides it,
        only spaces or line breaks, when Hancom lays it out on several lines: a space before the object is text
        (the object goes on to the next line when it does not fit after it), the two spaces right after it hang
        past the margin and a further one starting there begins the next line, and a line break begins one (an
        empty line before the object goes down as a line of text); empty for any other paragraph, or one of a
        line. With *caches* a paragraph with a valid layout cache keeps Hancom's lines."""

        objects = _placed_objects(runs)
        text = _run_text(runs)
        if len(objects) != 1 or not text or text.strip() or objects[0].find(f"{HP}pos").get("treatAsChar") != "1":
            return ()
        own = _cached_metrics(paragraph) if caches else ()
        if own:
            return own if len(own) > 1 else ()
        shape = self.shape(paragraph.get("paraPrIDRef"))
        if shape.kind not in ("PERCENT", "FIXED"):
            return ()
        inline, sizes, looks, placed, marked = _inline_content(self, paragraph, runs)
        style = self.style(paragraph.get("paraPrIDRef"), [run.get("charPrIDRef") for run in runs] or ["0"], paragraph)
        lines = _line_metrics(self, inline, _line_widths(shape, width, style), sizes, style, shape, placed,
                              looks if len(set(looks)) > 1 else None, marked, end, head)
        return lines if len(lines) > 1 else ()

    def pushed_lines(self, paragraph: Any, runs: list[Any], width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a cell paragraph without a layout cache whose text follows a table
        placed top and bottom from its top: the first line reaching the table and the lines after it go below
        it, and the paragraph reaches down to the table's foot at least; empty for any other paragraph."""

        obj = _object_before_text(runs, self.headed(paragraph))
        if obj is None:
            return ()
        top = _down(obj.find(f"{HP}pos"))
        foot = top + (_inline_table_height(self, obj) + _extent_margins(obj) if _local(obj) == "tbl"
                      else _extent(obj, "height", self))
        shape = self.shape(paragraph.get("paraPrIDRef"))
        lines = list(self.marked_lines(paragraph, runs, width) or self.mixed_lines(paragraph, runs, shape, width))
        if not lines:
            size, refs, _ = _text_size(self, runs)
            style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
            count = max(1, self.lines(_run_text(runs), _line_widths(shape, width, style), size, style))
            lines = [(size, _pitch(shape.kind, shape.value, size))] * count
        y = 0
        for index, (height, advance) in enumerate(lines):
            if y < foot and y + height > top:  # it reaches the table: below it, and the lines after it
                if index:
                    lines[index - 1] = (lines[index - 1][0], lines[index - 1][1] + foot - y)
                else:  # the first line takes the room above it
                    lines[0] = (height + foot - y, advance + foot - y)
                break
            y += advance
        above = sum(advance for _, advance in lines[:-1])
        if above + lines[-1][0] < foot:  # every line above the table: the paragraph holds it
            lines[-1] = (foot - above, foot - above)
        return tuple(lines)

    def marked_lines(self, paragraph: Any, runs: list[Any], width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph holding composed characters, ruby text, or objects
        set as characters among its text or several of them, laid out at *width* as in the body; empty for
        a paragraph holding none of them."""

        if not _marks(runs) and not _objects_among(runs):
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
    #: (height, advance) of each line of the row's tallest cell when it holds a table or several paragraphs
    metrics: tuple[tuple[int, int], ...] = ()
    first: int = 0        # the tallest first line of any of its cells
    #: the room above each of those lines when a part of the cell starts with it (a paragraph's spacing
    #: before its first line, none before the others)
    leads: tuple[int, ...] = ()


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
    widths = grid_widths_of(table)
    for tc in (tc for tr in table.findall(f"{HP}tr") for tc in tr.findall(f"{HP}tc")):
        row, span = _cell_row(measure, table, tc, widths.get(tc)), _row_span(tc)
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


def _object_alone(runs: list[Any]) -> Any:
    """The object set as a character, not a table, that is all a paragraph holds (but objects in front of or
    behind the text), or ``None``."""

    objects = _placed_objects(runs)
    if len(objects) != 1 or _local(objects[0]) == "tbl" or _run_text(runs).strip():
        return None
    return objects[0] if objects[0].find(f"{HP}pos").get("treatAsChar") == "1" else None


def _objects_among(runs: list[Any]) -> bool:
    """Whether the runs hold objects set as characters, and nothing else placed, among text or several."""

    objects = _placed_objects(runs)
    return bool(objects) and (len(objects) > 1 or bool(_run_text(runs).strip())) and all(
        obj.find(f"{HP}pos").get("treatAsChar") == "1" for obj in objects)


def _table_alone(runs: list[Any]) -> Any:
    """The table set as a character that is all a paragraph holds (but objects in front of or behind the text,
    which take no room), or ``None``."""

    children = [child for run in runs for child in run if _local(child) not in ("t", "secPr", "ctrl")
                and not (_local(child) in _OBJECTS and _floating(child))]
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
    A row that went on over a page end has its cell's lines start over at the top of the next page: a
    line above where it would follow the one before (that one's height and spacing below it, or the
    paragraph's top for a paragraph's first line, the part starting at that top) stands where it would
    in the unsplit cell. A paragraph's first line below an object placed from its top takes the room
    above it. Empty otherwise."""

    if not paragraphs or not all(_cached_metrics(paragraph) for paragraph in paragraphs):
        return ()
    tops: list[int] = []
    heights: list[int] = []
    foot, after, base = 0, 0, 0  # after: where the next paragraph's first line would stand
    for paragraph in paragraphs:
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        top = after + shape.prev if tops else 0
        for obj in (child for run in paragraph.findall(f"{HP}run") for child in run if _local(child) in _OBJECTS):
            pos = obj.find(f"{HP}pos")
            if pos is None or pos.get("treatAsChar") == "1" or _floating(obj):
                continue
            if obj.get("textWrap") not in ("TOP_AND_BOTTOM", "SQUARE") or pos.get("vertRelTo") != "PARA":
                return ()
            foot = max(foot, top + _down(pos) + _extent(obj, "height", measure))
        segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
        below = top  # where the paragraph's next line would stand
        for index, segment in enumerate(segments):
            vertpos = int(segment.get("vertpos", 0))
            if tops and vertpos + base < below:  # the next page's part of a split row: the lines start over
                base = (top if index == 0 else below) - (0 if index == 0 else vertpos)
            tops.append(vertpos + base)
            heights.append(int(segment.get("textheight", segment.get("vertsize", 0))))
            below = tops[-1] + int(segment.get("vertsize", 0)) + int(segment.get("spacing", 0))
            if index == 0 and tops[-1] > top:  # below an object placed from the paragraph's top: the line
                heights[-1] += tops[-1] - top  # takes the room above it, and goes on to a next page with it
                tops[-1] = top
        last = segments[-1]
        after = int(last.get("vertpos", 0)) + base + int(last.get("textheight", 0)) + int(last.get("spacing", 0)) \
            + shape.next
    if any(later < earlier for earlier, later in zip(tops, tops[1:])):
        return ()
    heights[-1] = max(heights[-1], foot - tops[-1])
    return tuple((height, (nxt - top) if nxt is not None else height)
                 for height, top, nxt in zip(heights, tops, [*tops[1:], None]))


def _holds_table(element: Any) -> bool:
    """Whether *element* (a cell, a paragraph or a table) holds a table laid out in its text: one in a header,
    footer or note control placed in it is laid out with that, elsewhere."""

    for table in element.iter(f"{HP}tbl"):
        if table is element:
            continue
        for up in table.iterancestors():
            if up is element:
                return True
            if _local(up) == "ctrl":
                break
    return False


def _down(pos: Any) -> int:
    """How far below its paragraph's top an object placed from there stands: one offset up (a negative
    offset, which the file keeps as an unsigned 32-bit number) stands at the paragraph's top."""

    offset = int(pos.get("vertOffset", 0))
    return 0 if offset < 0 or offset >= 1 << 31 else offset


def _vertical(cell: Any) -> bool:
    """Whether *cell* holds vertical text (``hp:subList@textDirection``): Hancom lays its lines down the
    cell's height, side by side across it, cuts what does not fit and never makes its row taller."""

    sub_list = cell.find(f"{HP}subList")
    return sub_list is not None and sub_list.get("textDirection", "HORIZONTAL") != "HORIZONTAL"


def _page_break(table: Any) -> str:
    """How a flowing table goes over a page end (``hp:tbl@pageBreak``): one holding a cell of vertical text
    does not split, as if set not to (NONE): it moves to the next page whole."""

    if any(_vertical(cell) for row in table.findall(f"{HP}tr") for cell in row.findall(f"{HP}tc")):
        return "NONE"
    return table.get("pageBreak", "CELL")


def _cell_row(measure: _Measure, table: Any, cell: Any, width: int | None = None) -> _Row:
    if _vertical(cell):  # its lines go across it, the row as declared: one block, not split
        margins = cell_margins_of(cell, table)
        vertical = margins.top + margins.bottom
        height = max(int(cell.find(f"{HP}cellSz").get("height", 0)), vertical)
        return _Row(height, 1, height - vertical, height - vertical, vertical, cell.get("header") == "1",
                    first=height - vertical)
    paragraphs = cell.findall(f"{HP}subList/{HP}p")
    nested = _holds_table(cell)
    drawn: tuple[tuple[int, int], ...] = ()
    if nested and any(_holds_table(paragraph) and _table_alone(paragraph.findall(f"{HP}run")) is None
                      for paragraph in paragraphs):
        drawn = _drawn_lines(measure, paragraphs)  # among text, or not set as a character: as Hancom drew it
        if not drawn and not all(_table_on_its_own(paragraph)
                                 or _table_before_text(paragraph.findall(f"{HP}run")) is not None
                                 or _objects_among(paragraph.findall(f"{HP}run"))  # laid out as in the body
                                 for paragraph in paragraphs
                                 if _holds_table(paragraph)
                                 and _table_alone(paragraph.findall(f"{HP}run")) is None):
            raise _Unsupported("a nested table")
    elif any(_placed_from(paragraph) for paragraph in paragraphs):  # an object placed from a paragraph: the
        drawn = _drawn_lines(measure, paragraphs)  # lines as Hancom drew them, below it or beside it
    size = cell.find(f"{HP}cellSz")
    margins = cell_margins_of(cell, table)
    inner = (int(size.get("width", 0)) if width is None else width) - margins.left - margins.right
    content, lines, pitch, char_size = measure.stack(paragraphs, inner, caches=True)
    # Hancom starts the cell's first line below its first paragraph's spacing before (the lines as drawn
    # take that room already)
    before = 0 if drawn or not paragraphs else measure.shape(paragraphs[0].get("paraPrIDRef")).prev
    content += before
    if drawn:
        content, lines = sum(advance for _, advance in drawn[:-1]) + drawn[-1][0], len(drawn)
    vertical = margins.top + margins.bottom
    height = max(int(size.get("height", 0)), vertical + content)
    first = drawn[0][0] if drawn else \
        before + (measure.stack_lines(paragraphs[:1], inner, caches=True) or ((0, 0),))[0][0]
    several = not nested and len(paragraphs) > 1  # its lines split at their own places, spacing included
    return _Row(height, lines, pitch, char_size, vertical, cell.get("header") == "1",
                spare=height - vertical - content, nested=nested,
                metrics=(drawn or measure.stack_lines(paragraphs, inner, caches=True)) if nested or several else (),
                first=first, leads=_line_leads(measure, paragraphs, inner) if several or before else ())


def _line_leads(measure: _Measure, paragraphs: list[Any], width: int) -> tuple[int, ...]:
    """The room above each line of *paragraphs* (as :meth:`_Measure.stack_lines` lays them out) when a part
    of their cell starts with it: a paragraph's spacing before at its first line, none at the others."""

    leads: list[int] = []
    for paragraph in paragraphs:
        count = len(measure.stack_lines([paragraph], width, caches=True))
        leads += [measure.shape(paragraph.get("paraPrIDRef")).prev] + [0] * (count - 1)
    return tuple(leads)


@dataclass(frozen=True)
class _Wrap:
    """The band a square-wrapped object takes beside the text, from *top* to *bottom* below the top of
    the first line of the paragraph at hand; a line in it is *cut* narrower. A top-and-bottom object's
    band (*push*) has no room beside it: the first line reaching it goes below it instead."""

    top: int
    bottom: int
    cut: int
    push: bool = False
    #: with text on both sides: the left piece's width (a line in the band is two pieces at one height,
    #: the right one the line's width less *cut* and this)
    split: int = 0
    #: its object does not flow with the text (pos@flowWithText="0"): it stays on its page past the
    #: body's foot, and the band goes no further than that page
    stays: bool = False

    def lower(self, by: int) -> "_Wrap | None":
        """The band seen from *by* further down, or ``None`` once it is above."""

        return replace(self, top=self.top - by, bottom=self.bottom - by) if self.bottom > by else None


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
class _Stacked:
    """An object placed top and bottom in a paragraph holding nothing else but more such objects: its
    offset below the paragraph's top (above its spacing), its span across the column and its height, outer
    margins included (a table as tall as its rows), and a table's rows, which split over the pages when
    it is taller than a page."""

    offset: int
    left: int
    right: int
    height: int
    table: _FlowTable | None = None


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
    #: the paragraph keeps its layout cache and such a band is a square-wrapped object's, which takes no
    #: line's height: where the object goes moves none of its lines
    wrap_fixed: bool = False
    #: the band's object does not flow with the text (pos@flowWithText="0"): past the body's foot it stays
    #: on its page, overflowing it, instead of going on to the next
    wrap_stays: bool = False
    #: beside such a staying band, its lines do not depend on the band (it keeps its layout cache or holds no
    #: text): a page break among them puts the rest on the next page, where Hancom lays them out whole
    wrap_free: bool = False
    #: the line the object laid out around the text (the caller's) stands on
    wrap_anchor: int = 0
    band: _Band | None = None
    #: (top, bottom) in the body of an object anchored here and placed on the paper or the page, whether it
    #: leaves a line's room beside it and the columns it reaches over (see :func:`_paper_band`)
    paper: tuple[int, int, bool, tuple[int, ...]] | None = None
    #: in columns of unequal width, a paragraph without a layout cache: its text, to break again
    reflow: _Reflow | None = None
    #: holding nothing, in a section hiding a page's first empty lines (see :meth:`_Paginator._paragraph`)
    hides: bool = False
    #: its lines are Hancom's own, from the paragraph's valid layout cache
    kept: bool = False
    #: an object anchored in this paragraph holding nothing else but spaces on one line: a table of it starting
    #: on the next page goes there as when the paragraph holds it alone, the paragraph's line staying
    spaced: bool = False
    #: the top-and-bottom objects stacked in this paragraph, which holds nothing else (see :func:`_stack`)
    stack: tuple[_Stacked, ...] = ()
    #: a square-wrapped object anchored here and flowing with the text went past the body's foot: Hancom sets
    #: it at the next page's body top, whatever its offset (this band, from there)
    moved: _Wrap | None = None
    #: holding no text: its line goes beside such a band as it is
    blank: bool = False
    #: a top-and-bottom object offset from this paragraph (not a flowing table) pushes its lines below it:
    #: when its band would pass the body's foot, Hancom moves it to the next page's top instead
    wrap_push: bool = False
    #: how far such an object pushed the paragraph's first line down (its band's foot is measured from where
    #: that line stood before)
    wrap_shift: int = 0
    #: a table wrapped square anchored here, flowing with the text and allowed to split, that goes on over the
    #: page end: it as it flows, how far below the paragraph's first line it starts, and its band beside the
    #: text (see :meth:`_Paginator._span_bands`)
    spans: tuple[_FlowTable, int, _Wrap] | None = None
    #: such an object alone in this empty paragraph, its foot this far below the paragraph's top (the line is
    #: as tall as that): past the body's foot it goes on to the next page's top, the empty line staying
    moves: int = 0

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
class _Reflow:
    """A paragraph without a layout cache in columns of unequal width, its lines broken at a column
    *width* from *offset* in its text on (*starts*: where each of them starts, from *offset*)."""

    measure: _Measure
    text: str
    sizes: tuple[int, ...]
    looks: tuple[Any, ...] | None
    style: Any
    shape: _Shape
    width: int = 0
    offset: int = 0
    starts: tuple[int, ...] = ()
    end: int = 0   # the paragraph's end (see :func:`_end_size`)
    head: int = 0  # its label (see :func:`_head_size`)

    def at(self, para: _Para, width: int, line: int) -> _Para:
        """*para* with its lines from line *line* on (the lines before it laid out already) broken
        again at a column *width* wide: Hancom breaks the text a column holds at that column's width,
        the paragraph's first line less its first-line indent, the others less a hanging one."""

        offset = self.offset + (self.starts[line] if line else 0)
        text = self.text[offset:]  # empty only after a line break ending the paragraph
        sizes = list(self.sizes[offset:] or self.sizes[-1:])
        looks = None if self.looks is None else list(self.looks[offset:] or self.looks[-1:])
        room = width - self.shape.left - self.shape.right
        widths: list[float] = [room - max(self.shape.indent, 0), room - max(-self.shape.indent, 0)]
        if offset:  # the rest: none of its lines is the paragraph's first
            widths = widths[1:]
        mixed = len(set(sizes)) > 1
        starts = self.measure.line_starts(text, widths, min(sizes), self.style, sizes if mixed else None, looks)
        cached = _line_metrics(self.measure, text, widths, sizes, self.style, self.shape, {}, looks) \
            if mixed or looks is not None else ()
        return replace(para, lines=len(starts), cached=cached,
                       reflow=replace(self, width=width, offset=offset, starts=tuple(starts)))

    def banded(self, para: _Para, line: int, wrap: _Wrap) -> _Para:
        """*para* with its lines from line *line* on (the lines before it laid out already) broken again
        beside *wrap*'s band, as seen from that line's top: a line whose top is above the band's foot is as
        wide as the room beside the object, or two pieces at one height with text on both sides; the lines
        below are the whole width."""

        mixed = len(set(self.sizes)) > 1
        widths = _indented(self.width - self.shape.left - self.shape.right, self.shape, self.style)
        starts = self.starts
        if line and not starts:  # where its lines start as laid out so far
            starts = tuple(self.measure.line_starts(self.text, widths, min(self.sizes), self.style,
                                                    list(self.sizes) if mixed else None,
                                                    None if self.looks is None else list(self.looks)))
            if len(starts) != para.lines:
                raise _Unsupported("lines beside a square-wrapped object moved to the next page")
        offset = self.offset + (starts[line] if line else 0)
        text = self.text[offset:]
        if not text:  # only a line break ending the paragraph is left
            return para
        sizes = list(self.sizes[offset:])
        looks = None if self.looks is None else list(self.looks[offset:])
        if offset:  # the rest: none of its lines is the paragraph's first
            widths = [widths[1], widths[1]]
        several = sizes if len(set(sizes)) > 1 else None
        lines, firsts = _wrapped_widths(self.measure, text, widths, min(sizes), self.style, self.shape, wrap,
                                        several, looks)
        pieces = self.measure.line_starts(text, lines, min(sizes), self.style, several, looks)
        metrics = _at_one_height(_line_metrics(self.measure, text, lines, sizes, self.style, self.shape, {}, looks,
                                               end=self.end, head=0 if offset else self.head), firsts)
        return replace(para, lines=len(metrics), cached=metrics,
                       reflow=replace(self, offset=offset, starts=tuple(pieces)))


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
    widths: tuple[int, ...] = ()  # then each column's width
    paper_height: int = 0
    hide_empty: bool = False  # hp:visibility@hideFirstEmptyLine: a page's first empty lines are hidden
    gap: int = 0  # between columns of equal width
    #: an object went on to the next page's top: the paragraphs without a layout cache keep their text, to
    #: break again beside its band there
    rebreak: bool = False


def _page(section: Any) -> _Page:
    page = next(section.iter(f"{HP}pagePr"), None)
    margin = page.find(f"{HP}margin") if page is not None else None
    if margin is None:
        raise _Unsupported("no page settings")
    width, height = _drawn_page_size(int(page.get("width", 0)), int(page.get("height", 0)), page.get("landscape"))
    body = height - sum(int(margin.get(key, 0)) for key in ("top", "bottom", "header", "footer"))
    text_width = width - sum(int(margin.get(key, 0)) for key in ("left", "right", "gutter"))
    columns, column_width, widths, gap = _columns(section, text_width)
    visibility = next(section.iter(f"{HP}visibility"), None)
    return _Page(body, column_width, columns, int(margin.get("top", 0)) + int(margin.get("header", 0)),
                 int(margin.get("left", 0)) + int(margin.get("gutter", 0)), text_width, width, bool(widths),
                 widths, height,
                 visibility is not None and visibility.get("hideFirstEmptyLine") in ("1", "true"), gap)


def _columns(section: Any, text_width: int) -> tuple[int, int, tuple[int, ...], int]:
    """(count, width, widths, gap): the section's columns, their width (the narrowest when they differ),
    when they differ each one's, and when they do not the gap between them."""

    # Column settings in a cell or a text box (an hp:subList) belong to that list, not the section.
    settings = [cols for cols in section.iter(f"{HP}colPr") if not _in_sub_list(cols)]
    if len(settings) > 1:
        raise _Unsupported("the columns change inside the section")
    count = int(settings[0].get("colCount", "1")) if settings else 1
    if count <= 1:
        return 1, text_width, (), 0
    if settings[0].get("sameSz") != "1":  # each column takes its share of the width with the gaps (hp:colSz),
        sizes = settings[0].findall(f"{HP}colSz")  # rounded
        total = sum(int(size.get("width", 0)) + int(size.get("gap", 0)) for size in sizes)
        if len(sizes) != count or total <= 0:
            raise _Unsupported("columns of unequal width")
        widths = tuple((2 * int(size.get("width", 0)) * text_width + total) // (2 * total) for size in sizes)
        return count, min(widths), widths, 0
    gap = int(settings[0].get("sameGap", 0))
    return count, (text_width - (count - 1) * gap) // count // 4 * 4, (), gap


def _in_sub_list(element: Any) -> bool:
    return any(_local(ancestor) == "subList" for ancestor in element.iterancestors())


def _caption(measure: _Measure, table: Any) -> tuple[int, int]:
    """How much room a table's caption takes above it and below it: its first paragraph's spacing before
    (Hancom starts the caption's first line below it), its lines and its gap (a caption beside the table
    takes none)."""

    caption = table.find(f"{HP}caption")
    if caption is None or caption.get("side") not in ("TOP", "BOTTOM"):
        return (0, 0)
    paragraphs = caption.findall(f"{HP}subList/{HP}p")
    width = int(caption.get("lastWidth", 0)) or int(table.find(f"{HP}sz").get("width", 0))
    before = measure.shape(paragraphs[0].get("paraPrIDRef")).prev if paragraphs else 0
    tall = before + measure.stack(paragraphs, width, caches=True)[0] + int(caption.get("gap", 0))
    return (tall, 0) if caption.get("side") == "TOP" else (0, tall)


def _inline_table_height(measure: _Measure, table: Any) -> int:
    """A table set as a character (or placed top and bottom in a cell): its rows as the estimate measures
    them. When the row model does not follow the table (merged rows, a nested table) but every paragraph in
    it keeps a valid layout cache, Hancom laid it out as it is, and the height it saved (hp:sz) is the height
    it draws."""

    if _holds_table(table) or any(_row_span(tc) != 1 for tc in table.iter(f"{HP}tc")):
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


def _objects_reach(runs: list[Any], measure: _Measure) -> int:
    """How far below the top of their paragraph in a cell, holding no text, the pictures and drawings placed
    from it reach: top and bottom or square, not set as a character, their outer margins included (the cell
    holds them, and its row grows to). So do the tables placed top and bottom from it, as tall as their rows
    (one placed up stands at the paragraph's top)."""

    reach = 0
    if _run_text(runs).strip():  # text goes on below such an object: not followed here
        return reach
    for obj in (child for run in runs for child in run):
        name, pos = _local(obj), obj.find(f"{HP}pos")
        if name == "tbl" and _placed_top_and_bottom(obj):
            reach = max(reach, _down(pos) + _inline_table_height(measure, obj) + _extent_margins(obj))
            continue
        if name not in _OBJECTS or name == "tbl" or pos is None or obj.find(f"{HP}sz") is None \
                or pos.get("treatAsChar") == "1" or obj.get("textWrap") not in ("TOP_AND_BOTTOM", "SQUARE") \
                or pos.get("vertRelTo") != "PARA" or pos.get("vertAlign", "TOP") != "TOP":
            continue
        reach = max(reach, _down(pos) + _extent(obj, "height", measure))  # one placed up stands at the top
    return reach


def _placed_top_and_bottom(obj: Any) -> bool:
    """An object placed top and bottom from its paragraph's top, not set as a character."""

    pos = obj.find(f"{HP}pos")
    return pos is not None and pos.get("treatAsChar") != "1" and obj.get("textWrap") == "TOP_AND_BOTTOM" \
        and pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"


def _placed_from(paragraph: Any) -> bool:
    """Whether *paragraph* holds an object placed from it in the text's flow: not set as a character, nor in
    front of or behind the text."""

    return any(_local(child) in _OBJECTS and child.find(f"{HP}pos") is not None
               and child.find(f"{HP}pos").get("treatAsChar") != "1" and not _floating(child)
               for run in paragraph.findall(f"{HP}run") for child in run)


def _object_before_text(runs: list[Any], headed: bool = False) -> Any:
    """The object placed top and bottom from its paragraph's top (a table, picture or drawing) that is all the
    runs hold but text after it -- a space is text, and so is the bullet or number of a *headed* paragraph or
    an object in front of or behind the text beside it (see :func:`_beside_floating`) -- or ``None``."""

    objects = [child for run in runs for child in run if _local(child) in _OBJECTS and not _floating(child)]
    if len(objects) != 1 or not _placed_top_and_bottom(objects[0]) \
            or not (_run_text(runs) or headed or _beside_floating(runs)):
        return None
    for child in (child for run in runs for child in run):
        if child is objects[0]:
            return child
        if _local(child) == "t" and _t_text(child).strip():  # text before it
            return None
    return None


def _beside_floating(runs: list[Any]) -> bool:
    """Whether the runs hold an object in front of or behind the text: beside an object placed top and bottom
    from the paragraph's top in a paragraph of no text, it sends the paragraph's empty line below that object,
    as the whole width, as a space or a label does."""

    return any(_local(child) in _OBJECTS and _floating(child) for run in runs for child in run)


def _table_on_its_own(paragraph: Any) -> bool:
    """Whether a cell paragraph holds no text, not even a space, and nothing but one table placed top and
    bottom from its top (Hancom sets the empty line below two of them, not beside them, and so with an object
    in front of or behind the text beside it)."""

    runs = paragraph.findall(f"{HP}run")
    objects = [child for run in runs for child in run if _local(child) in _OBJECTS]
    return not _run_text(runs) and len(objects) == 1 and _local(objects[0]) == "tbl" \
        and _placed_top_and_bottom(objects[0])


def _table_before_text(runs: list[Any]) -> Any:
    """The table placed top and bottom from its paragraph's top that is all the runs hold but text after it
    (text, a space being enough, or an object in front of or behind the text beside it), or ``None``."""

    objects = [child for run in runs for child in run if _local(child) in _OBJECTS and not _floating(child)]
    if len(objects) != 1 or _local(objects[0]) != "tbl" or not _placed_top_and_bottom(objects[0]) \
            or not (_run_text(runs) or _beside_floating(runs)):
        return None
    for child in (child for run in runs for child in run):
        if child is objects[0]:
            return child
        if _local(child) == "t" and _t_text(child).strip():  # text before it
            return None
    return None


def _placed_objects(runs: list[Any]) -> list[Any]:
    """The objects of the runs."""

    objects = [child for run in runs for child in run if _local(child) in _OBJECTS]
    for obj in objects:
        if obj.find(f"{HP}pos") is None or obj.find(f"{HP}sz") is None:
            raise _Unsupported(f"{_local(obj)} without a position")
    return [obj for obj in objects if not _floating(obj) and not _on_paper(obj)]


def _holds_nothing(runs: list[Any]) -> bool:
    """Whether the runs hold no character, object or control at all (a space is a character)."""

    return all(_local(child) == "t" and not child.text and not len(child) for run in runs for child in run)


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
    """A top-and-bottom object placed from the top or the bottom of the paper or of the page, not set as a
    character: it takes no room in its paragraph but keeps every line of its page out of its band. One
    wrapped square there counts as well (see :func:`_paper_band`)."""

    pos = obj.find(f"{HP}pos")
    return (pos is not None and pos.get("treatAsChar") != "1" and obj.get("textWrap") in ("TOP_AND_BOTTOM", "SQUARE")
            and pos.get("vertRelTo") in ("PAPER", "PAGE") and pos.get("vertAlign", "TOP") in ("TOP", "BOTTOM"))


def _paper_band(measure: _Measure, page: _Page, paragraph: Any) -> tuple[int, int, bool, tuple[int, ...]] | None:
    """(top, bottom) in the body of the object of *paragraph* placed on the paper, if any, whether it is
    wrapped square leaving a line's room beside it (Hancom sets the text reaching it beside it, which is
    not followed, and the text above or below it as if it were not there), and the columns it keeps the
    lines out of."""

    placed = [child for run in paragraph.findall(f"{HP}run") for child in run
              if _local(child) in _OBJECTS and _on_paper(child)]
    if not placed:
        return None
    square = placed[0].get("textWrap") == "SQUARE"  # no line beside it: less than a line's room on each side
    across = _across_the_text(placed[0], page, _MIN_SIDE - 1 if square else 0)
    columns = tuple(range(page.columns)) if across or page.columns == 1 else () if square \
        else _columns_reached(placed[0], page)
    if len(placed) > 1 or not columns:
        raise _Unsupported("objects placed on the paper")
    obj = placed[0]
    tall = _extent(obj, "height", measure)
    if _local(obj) == "tbl":  # as tall as its rows
        tall += sum(row.height for row in _rows(measure, obj)) - int(obj.find(f"{HP}sz").get("height", 0))
    pos = obj.find(f"{HP}pos")
    offset = int(pos.get("vertOffset", 0))
    if pos.get("vertRelTo") == "PAGE":  # from the body's top or foot
        top = offset if pos.get("vertAlign", "TOP") == "TOP" else page.body - offset - tall
    else:  # from the paper's top or bottom
        top = (offset if pos.get("vertAlign", "TOP") == "TOP" else page.paper_height - offset - tall) - page.top
    return top, top + tall, square and not across, columns


def _across_the_text(obj: Any, page: _Page, slack: int = 0) -> bool:
    """Whether an object placed from the paper's left covers the text's whole width (every column), but for
    *slack* on either side."""

    left = _paper_left(obj, page)
    return left is not None and left <= page.left + slack \
        and left + _extent(obj, "width") >= page.left + page.text_width - slack


def _columns_reached(obj: Any, page: _Page) -> tuple[int, ...]:
    """The columns of equal width that an object placed from the paper's left reaches over, its outer margins
    included."""

    left = _paper_left(obj, page)
    if left is None or page.unequal:
        return ()
    right = left + _extent(obj, "width")
    starts = [page.left + index * (page.column_width + page.gap) for index in range(page.columns)]
    return tuple(index for index, start in enumerate(starts) if left < start + page.column_width and right > start)


def _paper_left(obj: Any, page: _Page) -> int | None:
    """How far right of the paper's left edge an object placed from the paper's left, centre or right stands;
    ``None`` for one placed otherwise."""

    pos = obj.find(f"{HP}pos")
    if pos.get("horzRelTo") != "PAPER":
        return None
    width, offset = _extent(obj, "width"), int(pos.get("horzOffset", 0))
    return {"LEFT": offset, "CENTER": (page.paper_width - width) // 2 + offset,
            "RIGHT": page.paper_width - width - offset}.get(pos.get("horzAlign", "LEFT"))


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


def _end_size(measure: _Measure, runs: list[Any], sizes: list[int]) -> int:
    """The size the paragraph's end gives its last line: an empty run ending a paragraph with text makes that
    line as tall as itself when it is larger than the line's text, whatever the lines before it hold (an empty
    run before the text does not); 0 when it is no larger than any character."""

    if not runs or not sizes or any(len(child) or child.tag != f"{HP}t" or child.text for child in runs[-1]):
        return 0
    size = measure.char_height(runs[-1].get("charPrIDRef"))
    return size if size > min(sizes) else 0


def _head_size(measure: _Measure, paragraph: Any, sizes: list[int]) -> int:
    """The size a bullet or number label in its own character shape gives its paragraph's first line: it is
    a character of that size there (it counts when it is larger than the smallest character); 0 when not."""

    size = measure.label_size(paragraph.get("paraPrIDRef")) if sizes else 0
    return size if size > min(sizes or [0]) else 0


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
                  marks: dict[int, int] | None = None, end: int = 0, head: int = 0) -> tuple[tuple[int, int], ...]:
    """(height, advance) of each line FormFit breaks *text* into, every character at its own size: a line
    is as tall as its largest character, its line spacing reckoned from that size. An object set as a
    character (*objects*: its place in *text* -> its width and height) takes its width on its line and
    makes the line at least as tall as itself, and counts at its run's size for the spacing; a fixed line spacing
    keeps the next line that far down. A composed character or ruby text (*marks*: its place -> its
    width) is a character of its size in *sizes*. The last line is at least as tall as the paragraph's
    end (*end*, see :func:`_end_size`), and the first as its label (*head*, see :func:`_head_size`)."""

    advances = {**{index: width for index, (width, _) in objects.items()}, **(marks or {})} or None
    starts = measure.line_starts(text, widths, min(sizes), style, sizes if len(set(sizes)) > 1 else None, styles,
                                 advances, set(objects))
    metrics = []
    for start, stop in zip(starts, [*starts[1:], len(text)]):
        span = range(start, stop) if stop > start else range(len(text) - 1, len(text))
        size = max([sizes[index] for index in span] + ([end] if stop == len(text) else [])
                   + ([head] if start == 0 else []))
        height = max([size] + [objects[index][1] for index in span if index in objects])
        advance = _pitch(shape.kind, shape.value, size)
        metrics.append((height, advance if shape.kind == "FIXED" else height + advance - size))
    return tuple(metrics)


def _drawn_height(obj: Any, measure: _Measure) -> int:
    """How tall Hancom draws *obj*: a drawing holding a text box (hp:drawText) as tall as the box's text and
    its margins when that is taller than hp:sz -- Hancom grows the drawing to hold them, writing the grown size
    to hp:curSz alone (negative for a drawing scaled upside down), at times one less, which makes that a lower
    bound; any other object (a table too) as hp:sz."""

    height = int(obj.find(f"{HP}sz").get("height", 0))
    box = obj.find(f"{HP}drawText")
    if box is None:
        return height
    current = obj.find(f"{HP}curSz")
    grown = 0 if current is None else int(current.get("height", 0))
    if grown >= 1 << 31:  # negative, kept unsigned: as tall upside down
        grown = (1 << 32) - grown
    if grown >= 1 << 30:
        grown = 0
    paragraphs = box.findall(f"{HP}subList/{HP}p")
    if not paragraphs:
        return max(height, grown)
    margin = box.find(f"{HP}textMargin")
    left, right, top, bottom = (0, 0, 0, 0) if margin is None else (
        int(margin.get(side, 0)) for side in ("left", "right", "top", "bottom"))
    width = int(box.get("lastWidth", 0)) or int(obj.find(f"{HP}sz").get("width", 0))
    try:  # its first line below the first paragraph's spacing before, as in a cell
        content = measure.shape(paragraphs[0].get("paraPrIDRef")).prev \
            + measure.stack(paragraphs, width - left - right, caches=True)[0]
    except _Unsupported:
        content = 0
    return max(height, grown, top + content + bottom)


def _object_extent(obj: Any, measure: _Measure) -> tuple[int, int]:
    """(width, height) an object set as a character takes, its outer margins included; a table as tall
    as its rows."""

    size = obj.find(f"{HP}sz")
    margin = obj.find(f"{HP}outMargin")
    extra = (0, 0, 0, 0) if margin is None else tuple(_margin(margin, side) for side in ("left", "right", "top", "bottom"))
    height = _inline_table_height(measure, obj) + sum(_caption(measure, obj)) if _local(obj) == "tbl" \
        else _drawn_height(obj, measure)
    return int(size.get("width", 0)) + extra[0] + extra[1], height + extra[2] + extra[3]


def _inline_content(measure: _Measure, paragraph: Any, runs: list[Any], anchored: Any = None) -> tuple[
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
            if name in _OBJECTS and (_floating(child) or _on_paper(child) or child is anchored):
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


def _anchored_object(objects: list[Any], text: str, column: int, headed: bool = False) -> Any:
    """The one object not set as a character of a paragraph of text (a space is text, and so is the bullet or
    number label of a *headed* paragraph: its line goes below the object; *headed* is also set for an empty
    paragraph holding an object in front of or behind the text beside it, its empty line going below the object
    as the whole width) or of objects set as characters that is placed top and bottom from the paragraph's top
    (offset 0), or ``None``."""

    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    if len(placed) != 1 or not (text or headed or len(objects) > 1):
        return None
    obj = placed[0]
    pos = obj.find(f"{HP}pos")
    if not _wraps_top_and_bottom(obj, column):
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
        table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", (top, bottom),
                           tuple(cells), caption=_caption(measure, obj), cut=_spare_cut(obj))
        return _Anchor(line, table, 0)
    return _Anchor(line, None, _drawn_height(obj, measure) + top + bottom)


def _object_line(
    measure: _Measure, obj: Any, count: int, size: int, pitch: int, column: int
) -> tuple[int, int, int, _FlowTable | None]:
    """(lines, size, pitch, flowing table) of a paragraph holding *obj* and nothing else."""

    pos = obj.find(f"{HP}pos")
    out_margin = obj.find(f"{HP}outMargin")
    top, bottom = (0, 0)
    if out_margin is not None:
        top, bottom = _margin(out_margin, "top"), _margin(out_margin, "bottom")
    tall = _drawn_height(obj, measure) + top + bottom
    name = _local(obj)
    if pos.get("treatAsChar") == "1":  # as tall as it, or as the paragraph's characters when they are taller
        if name == "tbl":
            tall = _inline_table_height(measure, obj) + top + bottom + sum(_caption(measure, obj))
        tall = max(tall, size)
        return 1, tall, tall + pitch - size, None
    on_paragraph = pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"
    if _wraps_top_and_bottom(obj, column) and on_paragraph:
        if name == "tbl":
            rows, cells = _table_rows(measure, obj)
            offset = int(pos.get("vertOffset", 0))  # one up (a negative offset, kept unsigned) starts at the line
            table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", (top, bottom),
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
               square: Any = None, stacked: tuple[Any, ...] = ()) -> _Para:
    runs = paragraph.findall(f"{HP}run")
    objects = [obj for obj in _placed_objects(runs)
               if obj is not square and all(obj is not other for other in stacked)]
    if page.unequal and any(obj.find(f"{HP}pos").get("treatAsChar") != "1" for obj in objects):
        raise _Unsupported("an object not set as a character in columns of unequal width")
    reflow = page.unequal and not _cached_metrics(paragraph)  # its lines depend on the column's width
    if reflow and (objects or _marks(runs) or _note_anchors(runs)):
        raise _Unsupported("objects, composed characters, ruby text or footnotes in a paragraph without a "
                           "layout cache in columns of unequal width")
    text = _run_text(runs)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    headed = bool(objects) and not text and measure.headed(paragraph)  # its label is text too
    beside = bool(objects) and not text and _beside_floating(runs)  # its empty line goes below the object
    anchored = _anchored_object(objects, text, page.column_width, headed or beside)
    marks = _marks(runs) and not _cached_metrics(paragraph)  # to lay out like characters
    if marks:
        if anchored is not None or wrap is not None or square is not None:
            raise _Unsupported("composed characters or ruby text beside an object placed otherwise")
        _check_ruby_spacing(runs, shape)
    among = anchored is None and (marks or bool(objects) and (len(objects) > 1 or bool(text.strip())))
    beside = anchored is not None and len(objects) > 1  # objects set as characters on the lines below it
    alone = bool(objects) and not among and anchored is None  # an object with no text: one line as tall
    cached = () if alone else _cached_metrics(paragraph)
    size, refs, sizes = _text_size(measure, runs)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    widths: list[float] = _indented(page.column_width - shape.left - shape.right, shape, style)
    end = _end_size(measure, runs, sizes)
    head = _head_size(measure, paragraph, sizes)
    mixed = len(set(sizes)) > 1 or bool(end) or bool(head)
    looks = _char_styles(measure, paragraph, runs)
    lead = 0  # how far the paragraph's first line goes down below a square-wrapped object's band
    if alone and wrap is None:  # spaces besides it, those that do not fit going on to the next line
        spread = measure.spread_lines(paragraph, runs, page.column_width, end, head, caches=True)
        alone, cached = (False, spread) if spread else (alone, cached)
    if among or beside:
        inline_text, inline_sizes, inline_looks, placed, marked = _inline_content(measure, paragraph, runs, anchored)
        if wrap is not None:
            if beside or wrap.split or marked:
                raise _Unsupported("objects set as characters among text beside a square-wrapped object")
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            lines, lead = _banded_object_lines(measure, inline_text, widths, inline_sizes, style, shape, wrap, placed,
                                               looks_or_none, end, head)
            cached = _cached_jumps(paragraph, cached) if cached else lines
        elif not cached:
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            cached = _line_metrics(measure, inline_text, widths, inline_sizes, style, shape, placed, looks_or_none,
                                   marked, end, head)
    elif not cached and wrap is not None and not alone and text:
        if anchored is not None:
            raise _Unsupported("a top-and-bottom object beside a square-wrapped object")
        widths, firsts = _wrapped_widths(measure, text, widths, size, style, shape, wrap, sizes if mixed else None,
                                         looks)
        cached = _at_one_height(_line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end,
                                              head=head), firsts)
    elif not cached and not alone and (mixed or looks is not None):
        cached = _line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end, head=head)
    count = len(cached) or measure.lines(text, widths, size, style)
    pitch = _pitch(shape.kind, shape.value, size)
    table, moves = None, 0
    if alone:
        if wrap is not None:
            raise _Unsupported("an object beside a square-wrapped object")
        if objects[0].find(f"{HP}pos").get("treatAsChar") == "1":  # spaced from the largest character size
            size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # of any of its runs
            pitch = _pitch(shape.kind, shape.value, size)
        count, size, pitch, table = _object_line(measure, objects[0], count, size, pitch, page.column_width)
        beside = _page_number_beside(objects[0], runs, widths[0])
        if beside is not None:  # a page number beside a table too wide for the line: an empty line of its own,
            side, run = beside  # as tall as the control's characters
            empty = measure.char_height(run.get("charPrIDRef"))
            line = (empty, _pitch(shape.kind, shape.value, empty))
            count, cached = 2, (line, (size, pitch)) if side < 0 else ((size, pitch), line)
        pos = objects[0].find(f"{HP}pos")
        if table is None and pos.get("treatAsChar") != "1" and pos.get("flowWithText") != "0" \
                and 0 < int(pos.get("vertOffset", 0)) < 1 << 31:  # below the paragraph's line
            moves = size
    anchor = None if anchored is None else _anchor(measure, paragraph, runs, text, anchored, widths, size, style,
                                                   cached, count)
    around = 0 if square is None or not text else _anchor_line(measure, paragraph, runs, text, square, widths,
                                                                size, style, cached, count)
    if among and _note_anchors(runs):
        raise _Unsupported("footnotes in a paragraph with objects among its text")
    notes = _anchored_notes(measure, runs, text, widths, size, style, page.column_width, sizes if mixed else None,
                            looks)
    flags = shape.flags
    para = _Para(count, size, pitch, shape.prev + lead, shape.next, _on(flags, "pageBreakBefore"),
                 _on(flags, "keepLines"), _on(flags, "keepWithNext"), _on(flags, "widowOrphan"),
                 paragraph.get("pageBreak") == "1",
                 paragraph.get("columnBreak") == "1", table, notes, cached, anchor, wrap_anchor=around,
                 hides=page.hide_empty and _holds_nothing(runs))
    if anchored is not None and text and not text.strip(" ") and para.lines == 1:
        para = replace(para, spaced=True)
    if reflow and text:
        again = _Reflow(measure, text, tuple(sizes), None if looks is None else tuple(looks), style, shape)
        return again.at(para, page.column_width, 0)
    if moves:
        para = replace(para, moves=moves)
    if page.rebreak and not _cached_metrics(paragraph) and not objects and not marks and not notes:
        if not text:
            return replace(para, blank=True)
        return replace(para, reflow=_Reflow(measure, text, tuple(sizes), None if looks is None else tuple(looks),
                                            style, shape, width=page.column_width, end=end, head=head))
    return para


def _page_number_beside(obj: Any, runs: list[Any], width: float) -> tuple[int, Any] | None:
    """(-1, its run) when a page-number control (``hp:ctrl/hp:pageNum``) stands before *obj*, a table set as a
    character wider than the line (*width*), in its paragraph, (1, its run) when it stands after it, else
    ``None``: Hancom sets the two on lines of their own, the control's an empty line as tall as its run's
    characters."""

    if _local(obj) != "tbl" or obj.find(f"{HP}pos").get("treatAsChar") != "1" or _extent(obj, "width") <= width:
        return None
    seen = False
    for run in runs:
        for child in run:
            if child is obj:
                seen = True
            elif _local(child) == "ctrl" and child.find(f"{HP}pageNum") is not None:
                return (1 if seen else -1), run
    return None


def _extent(obj: Any, side: str, measure: _Measure | None = None) -> int:
    """An object's width or height (*side*), its outer margins included; given *measure*, the height as Hancom
    draws it (:func:`_drawn_height`)."""

    margin = obj.find(f"{HP}outMargin")
    ends = ("left", "right") if side == "width" else ("top", "bottom")
    extra = 0 if margin is None else sum(_margin(margin, end) for end in ends)
    if side == "height" and measure is not None:
        return _drawn_height(obj, measure) + extra
    return int(obj.find(f"{HP}sz").get(side, 0)) + extra


def _wraps_top_and_bottom(obj: Any, column: int) -> bool:
    """Top and bottom, or square with no line's room beside it: an object as wide as the column, or one
    placed from the column's or its paragraph's left or right that leaves less than 1440 of it on either
    side (the text going to either side, or to the wider), pushes the text below it either way."""

    wrap = obj.get("textWrap")
    if wrap == "TOP_AND_BOTTOM":
        return True
    width = _extent(obj, "width")
    if wrap != "SQUARE" or width >= column:
        return wrap == "SQUARE"
    pos = obj.find(f"{HP}pos")
    if pos is None or pos.get("horzRelTo") not in ("COLUMN", "PARA") or pos.get("horzAlign") not in ("LEFT", "RIGHT") \
            or obj.get("textFlow", "BOTH_SIDES") not in ("BOTH_SIDES", "LARGEST_ONLY"):
        return False
    offset = int(pos.get("horzOffset", 0))
    if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
        offset -= 1 << 32
    start = offset if pos.get("horzAlign") == "LEFT" else column - width - offset
    return start < _MIN_SIDE and column - start - width < _MIN_SIDE


def _square_object(objects: list[Any], runs: list[Any], column: int,
                   on_first_line: Callable[[Any], bool] | None = None) -> Any:
    """The one object of a paragraph wrapped square across the column from the paragraph's top, before
    any text or after text that *on_first_line* says ends on the paragraph's first line (Hancom places it from
    the top of the line its control falls on, the paragraph laid out the column's whole width), or ``None``
    (:func:`_square_sides` says where the text goes beside it)."""

    if len(objects) != 1:
        return None
    obj = objects[0]
    pos = obj.find(f"{HP}pos")
    if pos.get("treatAsChar") == "1" or obj.get("textWrap") != "SQUARE" or _wraps_top_and_bottom(obj, column):
        return None
    if (pos.get("vertRelTo"), pos.get("vertAlign", "TOP")) != ("PARA", "TOP") \
            or pos.get("horzRelTo") not in ("COLUMN", "PARA", "PAPER") or pos.get("horzAlign") not in ("LEFT", "RIGHT") \
            or obj.get("textFlow", "BOTH_SIDES") not in ("BOTH_SIDES", "LARGEST_ONLY", "LEFT_ONLY", "RIGHT_ONLY"):
        raise _Unsupported(f"{_local(obj)} wrapped square elsewhere than at a column edge")
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t" and _t_text(child):
            if on_first_line is None or not on_first_line(obj):
                raise _Unsupported(f"{_local(obj)} wrapped square after text")
            break
    return obj


def _on_first_line(measure: _Measure, page: _Page, paragraph: Any, runs: list[Any], obj: Any) -> bool:
    """Whether *obj*'s control falls on the paragraph's first line laid out the column's whole width (FormFit's
    lines, the object taking no room in them)."""

    place = 0
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t":
            place += len(_t_text(child))
    size, refs, _ = _text_size(measure, runs)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    starts = measure.line_starts(_run_text(runs), _line_widths(shape, page.column_width, style), size, style)
    return all(start > place for start in starts[1:])


def _square_sides(obj: Any, page: _Page) -> tuple[int, int]:
    """How wide the text beside a square-wrapped object is on its left and on its right in the column: a
    side narrower than 1440, or one its text flow leaves out, takes none (0). Placed from the column,
    the paragraph or the paper's left or right (from the paper only in one column)."""

    pos = obj.find(f"{HP}pos")
    width, offset = _extent(obj, "width"), int(pos.get("horzOffset", 0))
    if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
        offset -= 1 << 32
    if pos.get("horzRelTo") == "PAPER":
        if page.columns > 1:
            raise _Unsupported(f"{_local(obj)} wrapped square from the paper in columns")
        start = offset - page.left if pos.get("horzAlign") == "LEFT" else page.paper_width - width - offset - page.left
    else:
        start = offset if pos.get("horzAlign") == "LEFT" else page.column_width - width - offset
    left, right = start, page.column_width - start - width
    flow = obj.get("textFlow", "BOTH_SIDES")
    if flow == "LARGEST_ONLY":
        flow = "LEFT_ONLY" if left > right else "RIGHT_ONLY"
    left = left if left >= _MIN_SIDE and flow != "RIGHT_ONLY" else 0
    right = right if right >= _MIN_SIDE and flow != "LEFT_ONLY" else 0
    return left, right


def _spans(measure: _Measure, page: _Page, table: Any) -> tuple[_FlowTable, int, _Wrap]:
    """A table wrapped square that splits over the page end: it as a flowing table, its offset below its
    paragraph's first line, and its band beside the text (top and bottom set page by page)."""

    offset = int(table.find(f"{HP}pos").get("vertOffset", 0))
    if offset < 0 or offset >= 1 << 31:
        raise _Unsupported("a square-wrapped table placed up from its paragraph past the page foot")
    rows, cells = _table_rows(measure, table)
    margin = table.find(f"{HP}outMargin")
    ends = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
    flowing = _FlowTable(rows, table.get("pageBreak", "CELL"), table.get("repeatHeader") == "1", ends,
                         tuple(cells), caption=_caption(measure, table), cut=_spare_cut(table))
    left, right = _square_sides(table, page)
    return flowing, offset, _Wrap(0, 0, page.column_width - left - right, split=left if left and right else 0)


def _wrapped_paragraph(measure: _Measure, page: _Page, paragraph: Any, wrap: _Wrap | None, moved: bool = False) -> tuple[_Para, _Wrap | None]:
    """The paragraph with the lines beside a square-wrapped object's band narrower, and the band as the
    next paragraph sees it. With *moved*, the object went on to the next page's top: none here."""

    runs = paragraph.findall(f"{HP}run")
    objects = _placed_objects(runs)
    stacked = _stacked_objects(objects, runs, page.column_width)
    if stacked:
        if wrap is not None or page.unequal:
            raise _Unsupported("objects placed top and bottom one below another beside other objects")
        para = _paragraph(measure, page, paragraph, stacked=tuple(stacked))
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        return replace(para, stack=_stack(measure, stacked, page.column_width, shape)), None
    square = _square_object(objects, runs, page.column_width,
                            lambda obj: _on_first_line(measure, page, paragraph, runs, obj))
    pusher = _pushing_object(objects, _run_text(runs), page.column_width)
    if moved:  # the object went on to the next page's top: the paragraph's lines as if it were not there
        # the object: wrapped square, pushing the lines below it, or alone below the empty line (a table that
        # may split goes on over the page end instead; of tables, only one wrapped square set not to split is
        # followed)
        alone = objects[0] if len(objects) == 1 and objects[0].find(f"{HP}pos").get("treatAsChar") != "1" else None
        obj = square if square is not None else pusher if pusher is not None else alone
        if obj is not None and obj is square and wrap is None and _local(obj) == "tbl" \
                and obj.get("pageBreak", "CELL") != "NONE":  # it splits over the page end instead
            return replace(_paragraph(measure, page, paragraph, None, obj), spans=_spans(measure, page, obj)), None
        if obj is None or wrap is not None or _local(obj) == "tbl" and (obj is not square
                                                                 or obj.get("pageBreak", "CELL") != "NONE"):
            raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        tall = _extent(obj, "height", measure)
        if _local(obj) == "tbl":  # as tall as its rows
            tall += sum(row.height for row in _rows(measure, obj)) - int(obj.find(f"{HP}sz").get("height", 0))
        if obj is square:
            left, right = _square_sides(square, page)
            band = _Wrap(0, tall, page.column_width - left - right, split=left if left and right else 0)
        else:  # the lines reaching it go below it
            band = _Wrap(0, tall, 0, push=True)
        return replace(_paragraph(measure, page, paragraph, None, obj), moved=band), None
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    if wrap is not None:
        wrap = wrap.lower(shape.prev)
        if wrap is not None and (square is not None or pusher is not None or (wrap.push and placed)
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
            table = _FlowTable(rows, _page_break(pusher), pusher.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_caption(measure, pusher), cut=_spare_cut(pusher))
            return replace(para, band=_Band(para.wrap_anchor, offset, table)), None
        top = para.span(0, para.wrap_anchor) + offset
        tall = _extent(pusher, "height", measure)
        if _local(pusher) == "tbl":  # as tall as its rows
            tall += sum(row.height for row in _rows(measure, pusher)) - int(pusher.find(f"{HP}sz").get("height", 0))
        return _push(para, _Wrap(top, top + tall, 0, push=True), starts=True)
    if wrap is not None and wrap.push:  # objects set as characters on a line reaching it go below it with it
        return _push(_paragraph(measure, page, paragraph), wrap, starts=False)
    if wrap is not None and objects and not placed and not _run_text(runs).strip():
        para = _paragraph(measure, page, paragraph)  # one object set as a character, alone
        if len(objects) > 1:
            raise _Unsupported("objects set as characters beside a square-wrapped object")
        if _object_extent(objects[0], measure)[0] > _room_beside(wrap, page.column_width - shape.left - shape.right):
            pushed, after = _push(para, replace(wrap, push=True), starts=False)  # below it, the whole width
            return replace(pushed, wrap_stays=wrap.stays, wrap_free=wrap.stays), after
        beside = sum(1 for line in range(para.lines) if para.span(0, line) < wrap.bottom)
        return replace(para, wrap_lines=beside, wrap_stays=wrap.stays, wrap_free=wrap.stays), \
            wrap.lower(para.span(0, para.lines) + para.next)
    starts = square is not None
    if square is not None:
        top = int(square.find(f"{HP}pos").get("vertOffset", 0))
        left, right = _square_sides(square, page)
        if not left and not right:
            raise _Unsupported(f"{_local(square)} wrapped square leaving little room for text")
        tall = _extent(square, "height", measure)
        if _local(square) == "tbl":  # as tall as its rows
            tall += sum(row.height for row in _rows(measure, square)) - int(square.find(f"{HP}sz").get("height", 0))
        stays = square.find(f"{HP}pos").get("flowWithText") == "0"
        if left and right:
            wrap = _Wrap(top, top + tall, page.column_width - left - right, split=left, stays=stays)
        else:
            wrap = _Wrap(top, top + tall, page.column_width - left - right, stays=stays)
    para = _paragraph(measure, page, paragraph, wrap, square)
    if wrap is not None and (para.anchor is not None or para.table is not None):
        raise _Unsupported("an object beside a square-wrapped object")
    if wrap is None:
        return para, None
    lead = para.prev - shape.prev  # its first line moved below the band
    if wrap.split and not para.cached and para.lines == 1 and lead < wrap.bottom and not _run_text(runs) \
            and all(obj is square for obj in objects):  # an empty line beside it: two empty pieces
        para = _in_two_pieces(para)
    beside = sum(1 for line in range(para.lines) if lead + para.span(0, line) < wrap.bottom)
    para = replace(para, wrap_lines=beside, wrap_bottom=wrap.bottom if starts else 0,
                   wrap_fixed=bool(_cached_metrics(paragraph)), wrap_stays=wrap.stays,
                   wrap_free=wrap.stays and (bool(_cached_metrics(paragraph)) or not _run_text(runs).strip()))
    return para, wrap.lower(lead + para.span(0, para.lines) + para.next)


def _pushing_object(objects: list[Any], text: str, column: int) -> Any:
    """The one object of a paragraph of text placed top and bottom below the line it stands on (an
    offset down from the paragraph's top), or ``None``. In a paragraph holding no text, the objects set
    as characters are that line."""

    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    lined = not text.strip() and len(objects) > len(placed)  # no text: the objects set as characters its line
    if len(placed) != 1 or not (lined or (len(objects) == 1 and text.strip())):
        return None
    obj = placed[0]
    pos = obj.find(f"{HP}pos")
    if not _wraps_top_and_bottom(obj, column) or pos.get("vertRelTo") != "PARA" \
            or pos.get("vertAlign", "TOP") != "TOP":
        return None
    offset = int(pos.get("vertOffset", 0))
    if offset <= 0 or lined and offset >= 1 << 31:  # at the paragraph's top (see _anchored_object), or placed up
        return None
    return obj


def _stacked_objects(objects: list[Any], runs: list[Any], column: int) -> list[Any]:
    """The objects of a paragraph holding nothing else when there are several and each is placed top and
    bottom from the paragraph's top (none up from it), from the column's or the paragraph's left or right;
    none otherwise."""

    if len(objects) < 2 or _run_text(runs).strip() or _marks(runs) or _note_anchors(runs):
        return []
    for obj in objects:
        pos = obj.find(f"{HP}pos")
        if pos.get("treatAsChar") == "1" or not _wraps_top_and_bottom(obj, column) \
                or (pos.get("vertRelTo"), pos.get("vertAlign", "TOP")) != ("PARA", "TOP") \
                or int(pos.get("vertOffset", 0)) >= 1 << 31 or pos.get("horzRelTo") not in ("COLUMN", "PARA") \
                or pos.get("horzAlign", "LEFT") not in ("LEFT", "RIGHT"):
            return []
    return objects


def _stack(measure: _Measure, objects: list[Any], column: int, shape: _Shape) -> tuple[_Stacked, ...]:
    """*objects*, stacked in a paragraph holding nothing else, as :meth:`_Paginator._stacked` places them."""

    stacked: list[_Stacked] = []
    for obj in objects:
        pos = obj.find(f"{HP}pos")
        width, height = _object_extent(obj, measure)
        offset = int(pos.get("horzOffset", 0))
        if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
            offset -= 1 << 32
        indent = (shape.left, shape.right) if pos.get("horzRelTo") == "PARA" else (0, 0)
        left = indent[0] + offset if pos.get("horzAlign", "LEFT") == "LEFT" else column - indent[1] - width - offset
        table = None
        if _local(obj) == "tbl":
            rows, cells = _table_rows(measure, obj)
            margin = obj.find(f"{HP}outMargin")
            ends = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
            table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_caption(measure, obj), cut=_spare_cut(obj))
        stacked.append(_Stacked(int(pos.get("vertOffset", 0)), left, left + width, height, table))
    return tuple(stacked)


def _room_beside(wrap: _Wrap, width: int) -> int:
    """How wide a line of *width* is beside a square-wrapped object's band: its wider piece when the text
    goes on both sides."""

    return max(wrap.split, width - wrap.cut - wrap.split) if wrap.split else width - wrap.cut


def _push(para: _Para, band: _Wrap, *, starts: bool) -> tuple[_Para, _Wrap | None]:
    """*para* with the first line reaching a top-and-bottom object's *band* moved below it (the lines
    after follow), and the band as the next paragraph sees it (``None`` once a line went below it).
    The object stays on one page with the lines above it (*starts*: its band starts in *para*)."""

    if para.anchor is not None or para.table is not None:
        raise _Unsupported("an object beside a top-and-bottom object's band")
    metrics = list(para.cached) or [(para.size, para.pitch)] * para.lines
    top, rest, shifted = 0, None, 0
    for index, (height, advance) in enumerate(metrics):
        if top < band.bottom and top + height > band.top:
            shift = band.bottom - top
            if index == 0:
                pushed, shifted = replace(para, prev=para.prev + shift), shift
            else:
                metrics[index - 1] = (metrics[index - 1][0], metrics[index - 1][1] + shift)
                pushed = replace(para, cached=tuple(metrics))
            break
        top += advance
    else:
        pushed, rest = para, band.lower(top + para.next)
    beside = sum(1 for line in range(para.lines) if para.span(0, line) < band.bottom)
    return replace(pushed, wrap_lines=beside, wrap_bottom=band.bottom if starts else 0, wrap_push=starts,
                   wrap_shift=shifted if starts else 0), rest


def _wrapped_widths(measure: _Measure, text: str, widths: list[float], size: int, style: Any, shape: _Shape,
                    wrap: _Wrap, sizes: list[int] | None, looks: list[Any] | None) -> tuple[list[float], set[int]]:
    """Each FormFit line's width with the lines whose top is in *wrap*'s band cut narrower, or split in two
    pieces at one height beside an object with text on both sides, and the FormFit lines that are such a
    line's first piece (FormFit breaks the lines, and which lines are in the band follows from their
    heights; repeated until it settles)."""

    narrow: set[int] = set()  # lines in the band, as the lines Hancom draws
    for _ in range(8):
        lines: list[float] = []
        firsts: set[int] = set()
        for index in range(max(narrow, default=0) + 2):
            full = widths[min(index, 1)]
            if index in narrow and wrap.split:
                firsts.add(len(lines))
                lines += [wrap.split, full - wrap.cut - wrap.split]
            else:
                lines.append(full - (wrap.cut if index in narrow else 0))
        starts = measure.line_starts(text, lines, size, style, sizes, looks)
        top, found, index, piece = 0, set(), 0, 0
        while piece < len(starts):
            pieces = 2 if piece in firsts and piece + 1 < len(starts) else 1
            start, end = starts[piece], starts[piece + pieces] if piece + pieces < len(starts) else len(text)
            height = max((sizes or [size])[start:end] or [size]) if sizes else size
            if top < wrap.bottom and top + height > wrap.top:
                found.add(index)
            top += _pitch(shape.kind, shape.value, height)
            index, piece = index + 1, piece + pieces
        if found == narrow:
            return lines, firsts
        narrow = found
    raise _Unsupported("lines beside a square-wrapped object that do not settle")


def _in_two_pieces(para: _Para) -> _Para:
    """*para*, one empty line, as Hancom writes it beside an object with text on both sides: two pieces at
    one height."""

    return replace(para, lines=2, cached=((para.size, 0), (para.size, para.pitch)))


def _at_one_height(metrics: tuple[tuple[int, int], ...], firsts: set[int]) -> tuple[tuple[int, int], ...]:
    """*metrics* with each line of two pieces (*firsts*: its first piece) as tall as its taller piece, the
    second piece at the first's height. When the text ends in a line's first piece, Hancom writes the second
    one empty, at that height."""

    lines = list(metrics)
    for first in sorted(firsts):
        if first + 1 < len(lines):
            (height, advance), (other, after) = lines[first], lines[first + 1]
            lines[first], lines[first + 1] = (max(height, other), 0), (max(height, other), max(advance, after))
        elif first == len(lines) - 1:  # the text ends in it: an empty second piece
            height, advance = lines[first]
            lines[first:] = [(height, 0), (height, advance)]
    return tuple(lines)


def _banded_object_lines(measure: _Measure, text: str, widths: list[float], sizes: list[int], style: Any,
                         shape: _Shape, wrap: _Wrap, objects: dict[int, tuple[int, int]], looks: list[Any] | None,
                         end: int, head: int) -> tuple[tuple[tuple[int, int], ...], int]:
    """(height, advance) of each line of text holding objects set as characters (*objects*: place -> width and
    height) beside a square-wrapped object's band, and how far the first line goes down. A line whose top is in
    the band is as wide as the room beside the object, but the first one holding an object wider than that room
    goes below the band, the whole width, the rest of the room left empty (its line before spaced that much
    more). Every line taken as narrow at first, the lines are broken again until the narrow ones settle."""

    advances = {index: width for index, (width, _) in objects.items()} or None
    mixed = sizes if len(set(sizes)) > 1 else None
    narrow = set(range(len(text) + 1))
    for _ in range(8):
        widths_by_line = [widths[min(line, 1)] - (wrap.cut if line in narrow else 0)
                          for line in range(min(max(narrow, default=0), len(text)) + 2)]
        starts = measure.line_starts(text, widths_by_line, min(sizes), style, mixed, looks, advances)
        metrics: list[tuple[int, int]] = []
        found: set[int] = set()
        top = lead = 0
        for line, (start, stop) in enumerate(zip(starts, [*starts[1:], len(text)])):
            span = range(start, stop) if stop > start else range(len(text) - 1, len(text))
            size = max([sizes[index] for index in span] + ([end] if stop == len(text) else [])
                       + ([head] if start == 0 else []))
            height = max([size] + [objects[index][1] for index in span if index in objects])
            pitch = _pitch(shape.kind, shape.value, size)
            advance = pitch if shape.kind == "FIXED" else height + pitch - size
            if top < wrap.bottom and top + height > wrap.top:
                room = widths[min(line, 1)] - wrap.cut
                if any(objects[index][0] > room for index in span if index in objects):  # below the band
                    if metrics:
                        metrics[-1] = (metrics[-1][0], metrics[-1][1] + wrap.bottom - top)
                    else:
                        lead = wrap.bottom - top
                    top = wrap.bottom
                else:
                    found.add(line)
            metrics.append((height, advance))
            top += advance
        if found == narrow:
            return tuple(metrics), lead
        narrow = found
    raise _Unsupported("lines beside a square-wrapped object that do not settle")


def _cached_jumps(paragraph: Any, metrics: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    """*metrics* from the paragraph's layout cache with each line spaced down to where the cache puts the next
    one on its page when that is lower (a line Hancom moved below a square-wrapped object's band)."""

    tops = [int(segment.get("vertpos", 0)) for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]
    lines = list(metrics)
    for line, (above, below) in enumerate(zip(tops, tops[1:])):
        if line < len(lines) and below - above > lines[line][1]:
            lines[line] = (lines[line][0], below - above)
    return tuple(lines)


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
    """Whether a table moved row by row (TABLE) has no room for its first row from *y*, or one set not to
    split (NONE) no room for all its rows, so it starts on the next page. At the top of a page it is
    drawn anyway."""

    if table.mode not in ("TABLE", "NONE") or not table.rows:
        return False
    first = sum(row.height for row in table.rows) if table.mode == "NONE" else table.rows[0].height
    return y + first > body - table.margins[1] - table.cut \
        and y != _repeated_header(table) + table.margins[0]


def _flow_table(table: _FlowTable, frame: int, y: int, body: int) -> tuple[int, int]:
    """Lay the rows out from vertical position *y*; the frame and position where the table ends."""

    body -= table.margins[1]  # the rows keep the table's bottom margin above the page end
    header = _repeated_header(table) + table.margins[0]  # and go on below its top margin on the next page
    foot = body - table.cut
    if table.mode == "NONE":  # set not to split: its rows move as one, drawn anyway at a page's top
        height = sum(row.height for row in table.rows)
        if y + height > foot and y != header:
            frame, y = frame + 1, header
        return frame, y + height
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
            frame, y = _split_block(table, index, end, frame, y, body, header)
            index = end + 1
            continue
        before, start = frame, y
        above = index == len(rows) - 1 and table.caption[1] and table.mode == "CELL" and rows[index].spare \
            and not rows[index].nested  # a caption below keeps its room: the row's room to spare is cut above it
        frame, y = _flow_row(table.mode, rows[index], frame, y, body - (table.caption[1] if above else 0), header,
                             table.cut)
        if rows[index].merged and frame != before:
            raise _Unsupported("a page break among rows merged in a flowing table")
        if index == len(rows) - 1 and table.caption[1] and not above and frame == before and start != header \
                and y + table.caption[1] > foot:  # a caption below goes on with the last row
            frame, y = frame + 1, header + rows[index].height
        index += 1
    return frame, y


def _split_block(table: _FlowTable, first: int, last: int, frame: int, y: int, body: int,
                 header: int) -> tuple[int, int]:
    """Rows *first*..*last*, joined by merged cells and starting at *y*, in a table split between cell
    lines when the page end falls among them: each page keeps the lines that fit, and what is left goes on
    below the next page's *header*, split again at that page's end until it fits. The frame and position
    where they end."""

    foot, before = body - table.cut, None
    while True:
        cut, heights, cells = _block_rest(table, first, last, y, body)
        rest = sum(heights.values())
        if not rest:  # every cell done above the page end, what it declares below dropped: they end there
            return frame, body
        if header + rest <= foot:
            return frame + 1, header + rest
        if before is not None and rest >= before:  # nothing of it fits a page
            raise _Unsupported("rows merged together taller than a page")
        rows = list(table.rows)
        for index, height in heights.items():
            rows[index] = replace(rows[index], height=height)
        table, first, frame, y, before = replace(table, rows=rows, cells=tuple(cells)), cut, frame + 1, header, rest


def _block_rest(table: _FlowTable, first: int, last: int, top: int,
                body: int) -> tuple[int, dict[int, int], list[tuple[int, int, _Row]]]:
    """What goes on to the next page of rows *first*..*last*, joined by merged cells, when the page end
    falls among them in a table split between cell lines: every cell keeps the lines that fit above
    the page end and the rest go on. From the row the page end falls in, each row is as tall as the
    rest of its cells of one row (the rows after it whole), then each merged cell's rest, the one
    ending first first, adds what its rows lack to the last of them. The row the page end falls in,
    each row's height from it on, and the cells that go on, each as tall as its rest with the lines
    it has left."""

    rows, tops, y, foot = table.rows, {}, top, body - table.cut
    for index in range(first, last + 1):
        tops[index] = y
        y += rows[index].height
    cut = next(index for index in range(first, last + 1) if tops[index] + rows[index].height > foot)
    heights = dict.fromkeys(range(cut, last + 1), 0)
    rests: list[tuple[int, int, int]] = []
    cells: list[tuple[int, int, _Row]] = []
    for start, span, cell in table.cells:
        end = start + span - 1
        if start < first or start > last or end < cut:
            continue  # another row, or done above the page end
        part = (cell.height, cell.lines) if start > cut else _cell_rest(cell, tops[start], foot)
        if part is None:
            continue
        rest, begin = part[0], max(start, cut)
        cells.append((begin, end - begin + 1, replace(cell, height=rest, lines=part[1])))
        if span == 1:
            heights[start] = max(heights[start], rest)
        else:
            rests.append((begin, end, rest))
    for start, end, rest in sorted(rests, key=lambda item: (item[1], item[0])):
        lacking = rest - sum(heights[index] for index in range(start, end + 1))
        heights[end] += max(lacking, 0)
    return cut, heights, cells


def _cell_rest(cell: _Row, top: int, foot: int) -> tuple[int, int] | None:
    """How tall the part of a cell starting at *top* that goes on past the page end *foot* is, and how many
    lines it holds; ``None`` when nothing of it goes on."""

    fitting = 0
    while fitting < cell.lines and top + cell.margins + fitting * cell.pitch + cell.size <= foot:
        fitting += 1
    if cell.spare and (fitting or not cell.lines):  # its text (or what is left: none) starts above the page end:
        # the declared room is cut like a row's, and the lines that do not fit go on with it, which is then
        # at least as tall as they are with the cell's margins
        rest, left = top + cell.height - foot, cell.lines - fitting
        if left:
            return max(rest, cell.margins + (left - 1) * cell.pitch + cell.size), left
        return (rest, 0) if rest > _SPARE_DROPPED else None
    if cell.spare:  # none of it fits: it goes on whole
        return cell.height, cell.lines
    if fitting == cell.lines:
        return None
    return cell.margins + (cell.lines - fitting - 1) * cell.pitch + cell.size, cell.lines - fitting


def _flow_row(mode: str, row: _Row, frame: int, y: int, body: int, header: int,
              cut: int = _SPARE_CUT) -> tuple[int, int]:
    """A row that does not fit even a fresh page is drawn there anyway, cut at the paper's edge;
    CELL breaks a row between its lines, or a row taller than its text just above the page's foot."""

    remaining, height, metrics, nested, leads = row.lines, row.height, row.metrics, row.nested, row.leads
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
            lines = metrics or ((row.size, row.pitch),) * remaining
            fitting = _lines_fitting(lines, leads, y + row.margins, foot)
            if fitting and len(lines) == row.lines and y + row.margins + row.first > foot:
                fitting = 0  # every cell's first line must fit, or the row goes on whole
            if fitting and (row.spare or fitting == len(lines)):  # room under its lines: cut like a row's
                rest = height - (foot - y)
                if fitting < len(lines) and y + height - row.spare > foot:  # its text does not all fit:
                    rest = max(rest, row.margins + _lines_height(lines[fitting:], leads[fitting:]))  # it goes on
                elif rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y = frame + 1, header
                remaining, height, metrics, leads = 1, rest, (), ()
                continue
            if fitting:
                metrics, leads = lines[fitting:], leads[fitting:]
                remaining, height = len(metrics), row.margins + _lines_height(metrics, leads)
            elif fresh:
                return frame, y + height
        elif fresh:
            return frame, y + height
        frame, y = frame + 1, header


def _lines_fitting(lines: tuple[tuple[int, int], ...], leads: tuple[int, ...], top: int, foot: int) -> int:
    """How many of *lines* ((height, advance) each; *leads*: the room above each when it starts a part) fit
    from *top* above *foot*."""

    fitting, y = 0, top + (leads[0] if leads else 0)
    while fitting < len(lines) and y + lines[fitting][0] <= foot:
        y += lines[fitting][1]
        fitting += 1
    return fitting


def _lines_height(lines: tuple[tuple[int, int], ...], leads: tuple[int, ...]) -> int:
    """How tall *lines* are as a part of their cell: the room above the first, then down to the last's foot."""

    return (leads[0] if leads else 0) + sum(advance for _, advance in lines[:-1]) + lines[-1][0]


class _Paginator:
    """Frames (a page's columns, in order) and vertical positions of every line of a section."""

    def __init__(self, body: int, columns: int, notes: _NoteShape,
                 bands: dict[int, list[tuple[int, int]]] | None = None, widths: tuple[int, ...] = (),
                 sides: dict[int, list[tuple[int, int]]] | None = None) -> None:
        self.body = body
        self.widths = widths  # each column's width when they differ
        #: frame -> (top, bottom) of the objects placed on the paper there: no line in them
        self.bands = {frame: list(found) for frame, found in (bands or {}).items()}  # stacked objects add theirs
        #: frame -> left, right, top, bottom of the objects stacked in empty paragraphs that went there
        self.stacked: dict[int, list[tuple[int, int, int, int]]] = {}
        #: frame -> (top, bottom) of the ones leaving a line's room beside them, and whether a line without
        #: a layout cache, a table or an object reaches one of them (set beside it by Hancom, which is not
        #: followed: a line keeping its cache stays where it is)
        self.sides = sides or {}
        self.beside = False
        self.columns = columns
        self.notes = notes
        self.out: list[tuple[int, int]] = []
        self.counts: list[int] = []  # lines per paragraph
        self.laid: _Para | None = None  # the paragraph _lay placed last, as it broke its last lines
        self.frame = 0
        self.last_vp: int | None = None
        self.last_pitch = 0
        self.pending_next = 0
        self.table_end = 0      # the last frame a flowing table reaches
        self.reserved: dict[int, int] = {}  # frames a table starting past its anchor takes: where text starts
        self.wrap_frame = -1                  # the frame a square-wrapped object's band is on
        self.wrap_moved = False  # that band passed the body's foot: the object went on to the next page
        #: frame -> the bands of square-wrapped objects there that the text there is broken beside: one that
        #: went on to its top (see :attr:`_Para.moved`), the parts of tables split over its ends
        self.squares: dict[int, list[_Wrap]] = {}
        #: a flowing table's band no line has reached yet: its frame, top, bottom there (None when it goes
        #: on over the page end), and the frame and position where the lines after it go on
        self.band: tuple[int, int, int | None, int, int] | None = None
        self.page_notes = [0, 0]  # height and count of the notes on the current page
        self.carry = 0          # height of notes going on over the page end
        self.floor: int | None = None  # where the next paragraph starts at the highest: a table's end
        self.under: int | None = None  # where the next paragraph starts, whatever its spacing: a table's end
        self.hidden = 0  # empty paragraphs just hidden below the current frame's foot

    def run(self, paras: list[_Para]) -> int:
        """Lay *paras* out; the number of frames used."""

        for index, para in enumerate(paras):
            first = len(self.out)
            self._paragraph(index, paras, para)
            self.counts.append(len(self.out) - first)
        return max(self.out[-1][0] if self.out else 0, self.table_end) + 1

    def _paragraph(self, index: int, paras: list[_Para], para: _Para) -> None:
        hidden, self.hidden = self.hidden, 0
        start = para.prev if self.last_vp is None else self.last_vp + self.last_pitch + self.pending_next + para.prev
        if self.under is not None:  # the table before went on past its anchor line's page: the line reaching it
            # goes right under its end, as under any object's band, and a column break lands there, in the
            # column after the anchor line's (or the first one clear of the table)
            start, self.under = self.under, None
            if para.column_break and not para.page_break and not para.break_before:
                para = replace(para, column_break=False)
        if self.floor is not None:
            start, self.floor = max(start, self.floor), None
        if (para.stack or para.band is not None or para.table is not None or para.anchor is not None) \
                and (self.frame in self.squares or self.frame + 1 in self.squares):
            raise _Unsupported("objects or a table beside a square-wrapped object moved to the next page")
        if para.stack:
            self._stacked(index, paras, para, start)
            return
        if para.band is not None or self.band is not None:
            self._banded(index, paras, para, start)
            return
        if para.anchor is not None:
            self._anchored(index, paras, para, start)
            return
        start, broke = self._breaks(para, start)  # a flowing table in the paragraph starts there too
        if para.hides and not broke and hidden < 2 and self.last_vp is not None and not self._fits(start, 1, para):
            # Hancom hides an empty paragraph that would start the next page or column, and a second one after
            # it, where it would stand below this one's foot: it takes no room and starts no page.
            self.out.append((self.frame, start))
            self.hidden = hidden + 1
            return
        table = para.table
        if table is not None:
            self._flow(para, table, start)
            return
        reach = para.wrap_bottom - para.wrap_shift if para.wrap_push else para.moves
        if reach and start + reach > self.body and self.columns == 1:
            raise _BandMoves(index)  # its object goes on to the next page's top, its lines stay
        first = len(self.out)
        if self._lay(index, paras, para, start, broke):
            last = self.laid or para
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], last.advance(last.lines - 1), para.next
        if para.wrap_bottom:  # the band starts here: it stays on this page
            self.wrap_frame = self.out[first][0]
            self.wrap_moved = self.out[first][1] + para.wrap_bottom - para.wrap_shift > self.body \
                and not para.wrap_stays
        if self.wrap_moved and not para.wrap_fixed and (para.wrap_bottom or para.wrap_lines):
            if para.wrap_bottom and self.columns == 1:  # its object goes on to the next page's top: again
                raise _BandMoves(index)
            raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        beside = self.out[first:first + para.wrap_lines]
        if not para.wrap_fixed and not para.wrap_free and any(frame != self.wrap_frame for frame, _ in beside):
            raise _Unsupported("a page break beside a square-wrapped or offset top-and-bottom object")

    def _flow(self, para: _Para, table: _FlowTable, start: int) -> None:
        if self.last_vp is not None and start + para.height(0) > self.body:  # the anchor line goes on
            start = self._next_frame(para, 0, True)                         # to the next page
        if self._below_bands(start) != start:
            self._flow_below_band(para, table, self._below_bands(start))
            return
        self.out.append((self.frame, start))  # the anchor paragraph's line, under the table's top
        if not para.kept:
            self._reach(self.frame, start, start + para.height(0))
        before = self.frame
        top = start - para.prev + table.offset + table.above  # from the paragraph's top, above its spacing
        frame, end = _flow_table(table, self.frame, top, self.body)
        self._clear_of_paper(before, frame, start, end)
        self.table_end = max(self.table_end, frame)
        if start + para.height(0) <= self.body and _starts_later(table, top, self.body):
            self._starts_next_page(para, table, start, frame, end)
            return
        self.frame = frame
        if self.frame != before:
            self.page_notes = [0, 0]
            self.last_vp, self.last_pitch, self.pending_next = end + table.below, 0, para.next
            self.under = end + table.below
        else:  # the next paragraph goes below the anchor line or the table, whichever is lower
            self.last_vp, self.last_pitch, self.pending_next = start, para.advance(0), para.next
            self.floor = end + table.below

    def _flow_below_band(self, para: _Para, table: _FlowTable, top: int) -> None:
        """A band of an object placed on the paper pushed the table's anchor line down to *top*: the table
        stands there, and the line goes below the table."""

        frame, end = _flow_table(table, self.frame, top + table.offset + table.above, self.body)
        self._clear_of_paper(self.frame, frame, top, end, below=True)
        line = end + table.below
        self.page_notes = [0, 0] if frame != self.frame else self.page_notes
        self.frame, self.table_end = frame, max(self.table_end, frame)
        self.out.append((self.frame, line))
        if not para.kept:
            self._reach(self.frame, line, line + para.height(0))
        self.last_vp, self.last_pitch, self.pending_next = line, para.advance(0), para.next

    def _stacked(self, index: int, paras: list[_Para], para: _Para, start: int) -> None:
        """Objects stacked in a paragraph holding nothing else go one by one to the first page, from the
        paragraph's on, where they fit below the earlier ones there they overlap across (see
        :meth:`_stack_spot`), those of earlier such paragraphs included. The first, not fitting on the
        paragraph's page, flows from where it stands (a table split at the page's foot, going on at the next
        page's top whatever is there); a later one, fitting on no page holding objects, starts at the top of
        the page after, a table taller than a page split over the pages after. A page a table goes on from is
        full. No line goes into them: the paragraph's line takes the first place clear of them, on a later
        page when its own has none, and the lines after follow it."""

        if self.columns > 1:
            raise _Unsupported("objects placed top and bottom one below another in columns")
        if self.band is not None or para.notes or self.page_notes[1]:
            raise _Unsupported("objects placed top and bottom one below another beside notes or a table's band")
        start, _ = self._breaks(para, start)
        if self.last_vp is not None and start + para.height(0) > self.body:  # its line goes on to the next
            start = self._next_frame(para, 0, True)                         # page, the objects with it
        home, top = self.frame, start - para.prev
        placed = {frame: list(boxes) for frame, boxes in self.stacked.items() if frame >= home}
        last = home
        for number, obj in enumerate(para.stack):
            end = last if number == 0 else max([last, *placed])
            spot = self._stack_spot(placed, obj, home, end, top)
            if spot is None:  # the first from where it stands, a later one from the top of the page after
                spot = (end + 1, 0) if number else (home, max([top + obj.offset] + self._below(placed, obj, home)))
                if obj.table is None and spot[1] + obj.height > self.body:
                    raise _Unsupported("an object placed top and bottom past the page's foot")
            frame, y = spot
            end_frame, bottom = frame, y + obj.height
            if bottom > self.body:  # a table split over the pages from there
                assert obj.table is not None
                end_frame, end = _flow_table(obj.table, frame, y + obj.table.above, self.body)
                bottom = end + obj.table.below
            for page in range(frame, end_frame + 1):
                placed.setdefault(page, []).append(
                    (obj.left, obj.right, y if page == frame else 0, bottom if page == end_frame else self.body))
            last = max(last, end_frame)
        for frame, boxes in placed.items():
            if self.bands.get(frame) and frame not in self.stacked or self.sides.get(frame) \
                    or frame != home and self.reserved.get(frame):
                raise _Unsupported("objects placed top and bottom one below another on a page with other objects")
            self.bands[frame] = [(above, below) for _, _, above, below in boxes]
            self.stacked[frame] = boxes
        self.table_end = max(self.table_end, last)
        frame, y, height = home, start, para.height(0)
        while True:  # the paragraph's line, at the first place clear of them
            hits = [below for above, below in self.bands.get(frame, ()) if y < below and y + height > above]
            if hits:
                y = max(hits)
            elif y + height <= self.body:
                break
            else:
                frame, y = frame + 1, self.reserved.get(frame + 1, 0) + para.prev
        if frame != home:
            self.page_notes = [0, 0]
        self.frame, self.laid = frame, para
        self.out.append((frame, y))
        self._reach(frame, y, y + height)
        self.last_vp, self.last_pitch, self.pending_next = y, para.advance(0), para.next

    def _stack_spot(self, placed: dict[int, list[tuple[int, int, int, int]]], obj: _Stacked, home: int, last: int,
                    top: int) -> tuple[int, int] | None:
        """The first of the pages *home* to *last* where *obj* fits below the objects *placed* there it overlaps
        across (on *home* at its offset below *top* or lower, on a later page from its top), and where; ``None``
        when it fits on none."""

        for frame in range(home, last + 1):
            y = max([top + obj.offset if frame == home else 0] + self._below(placed, obj, frame))
            if y + obj.height <= self.body:
                return frame, y
        return None

    @staticmethod
    def _below(placed: dict[int, list[tuple[int, int, int, int]]], obj: _Stacked, frame: int) -> list[int]:
        """The bottoms of the objects *placed* on *frame* that *obj* overlaps across."""

        return [box[3] for box in placed.get(frame, ()) if box[0] < obj.right and obj.left < box[1]]

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
        else:  # at the top of the paragraph's first line: below an object placed on the paper, as the line
            top = self._below_bands(top)
        if anchor.table is not None:
            table = anchor.table
            later = _starts_later(table, top + table.above, self.body)
            if later and para.spaced and not head.lines:  # spaces only: as the table alone in its paragraph
                self._flow(replace(para, anchor=None, table=table), table, start)
                return
            if table.mode == "NONE" and not head.lines and top != self.reserved.get(self.frame, 0) + para.prev \
                    and (later or top + table.above + sum(row.height for row in table.rows) + table.below
                         + tail.height(0) > self.body):  # set not to split: it goes on with the line below it
                top, later = self._next_frame(para, 0, True), False
            if later:
                raise _Unsupported("a top-and-bottom table anchored in text that starts on the next page")
            frame, end = _flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame, top, end, below=True)
            self.frame, self.table_end, end = frame, max(self.table_end, frame), end + table.below
        else:
            if top + anchor.height > self.body and top > 0:
                raise _Unsupported("a top-and-bottom object anchored in text at a page end")
            end = top + anchor.height
            self._reach(self.frame, top, end)
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
            if not band.line and self.last_vp is not None and start + para.height(0) > self.body:
                start = self._next_frame(para, 0, True)  # the line goes on to the next page, its table with it
            top = start + para.span(0, band.line) + band.offset
            if start + para.span(0, band.line) + para.height(band.line) > self.body:
                raise _Unsupported("a top-and-bottom table offset down from a line at a page end")
            if top + table.above >= self.body or _starts_later(table, top + table.above, self.body):
                if band.line:
                    raise _Unsupported("a top-and-bottom table offset down from a line at a page end")
                self._band_on_next_page(index, paras, para, table, top, start, broke)
                return
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

    def _band_on_next_page(self, index: int, paras: list[_Para], para: _Para, table: _FlowTable, top: int,
                           start: int, broke: bool) -> None:
        """A table offset down from a paragraph's first line whose top falls past the page's foot, or whose first
        row (moved row by row) does not fit under it: it starts at the next page's top, and the paragraph's lines
        go on under its line, on the pages the table takes below the table."""

        frame, end = _flow_table(table, self.frame, top + table.above, self.body)
        self._clear_of_paper(self.frame + 1, frame)
        taken = range(self.frame + 1, frame + 1)
        if frame == self.frame or any(page in self.reserved for page in taken):
            raise _Unsupported("a top-and-bottom table offset down from a line at a page end")
        self.reserved.update(dict.fromkeys(taken, self.body))
        self.reserved[frame] = end + table.below
        self.table_end = max(self.table_end, frame)
        if self._lay(index, paras, para, start, broke):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.advance(para.lines - 1), para.next

    def _clear_of_paper(self, first: int, last: int, top: int = 0, end: int | None = None,
                        below: bool = False) -> None:
        """A table from its anchor line's *top* in frame *first* to *end* in frame *last* (the whole frames
        without them) reaching the band of an object placed on the paper or the page, or starting right
        below one (but for a table moved *below* it), is not followed."""

        for frame in range(first, last + 1):
            low = top if frame == first else 0
            high = end if frame == last and end is not None else self.body
            self._reach(frame, low, high)
            touching = below and frame == first
            if any(above < high and (low < bottom if touching else low <= bottom)
                   for above, bottom in self.bands.get(frame, ())):
                stacked = frame in self.stacked
                raise _Unsupported("a table on a page with objects stacked in an empty paragraph" if stacked
                                   else "a table on a page with an object placed on the paper")

    def _reach(self, frame: int, top: int, bottom: int) -> None:
        """Note whether something from *top* to *bottom* in *frame* reaches the band of an object placed on
        the paper that leaves a line's room beside it."""

        if any(top < foot and bottom > head for head, foot in self.sides.get(frame, ())):
            self.beside = True

    def _below_bands(self, top: int) -> int:
        """*top* in the current frame, below the band of any object placed on the paper that it falls in."""

        for above, bottom in sorted(self.bands.get(self.frame, ())):
            if above <= top < bottom:
                top = bottom
        return top

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

        if para.spans is not None:  # a table wrapped square going on over the page end: its bands, page by page
            self._span_bands(para.spans, start)
            para = replace(para, spans=None)
        para = self._at_band(self._at_width(para, 0), 0, start)
        remaining, first_chunk = para.lines, True
        fresh = self.last_vp is None or broke
        below = False  # the next line was moved below an object's band
        while remaining:
            done = para.lines - remaining
            hit = self._band_hit(para, done, remaining, start)
            if hit is not None and hit[0] == 0:  # the line reaches an object placed on the paper: below it
                start, below = hit[1], True
                continue
            count = self._chunk(index, paras, para, start, remaining, done, first_chunk)
            if count == 0 and (self.last_vp is None or fresh) and not below and not self.reserved.get(self.frame):
                count = 1  # a line taller than the page still takes an empty page (and overflows it)
            if para.moved is not None:  # its object goes on to the next page's top
                if count == 0:
                    raise _Unsupported("a square-wrapped object past the page foot, its paragraph on the next page")
                self._move_band(para.moved)
                para = replace(para, moved=None)
            if hit is not None and hit[0] < count:  # the lines above it stay, the next goes below it
                count = hit[0]
                self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
                self._place(para, done, count)
                remaining, start, first_chunk, below = remaining - count, hit[1], False, True
                continue
            self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
            self._place(para, done, count)
            remaining -= count
            if not remaining and self.carry:  # the page ends with this paragraph's notes
                self.frame += 1
                self.page_notes = [self.carry, 1]
                self.last_vp, self.last_pitch, self.pending_next = None, 0, 0
                self.laid = para
                return False
            if remaining:
                start, below = self._next_frame(para, count, first_chunk), False
                line = para.lines - remaining
                again = self._at_width(para, line)
                if again is not para:
                    para, remaining, line = again, again.lines, 0
                again = self._at_band(para, line, start)
                if again is not para:
                    para, remaining = again, again.lines
            fresh = bool(remaining)
            first_chunk = False
        self.laid = para
        return True

    def _at_width(self, para: _Para, line: int) -> _Para:
        """*para* with its lines from *line* on broken at the width of the current frame's column, when
        the columns differ in width and the paragraph has no layout cache."""

        if para.reflow is None or not self.widths:
            return para
        width = self.widths[self.frame % self.columns]
        return para if width == para.reflow.width else para.reflow.at(para, width, line)

    def _at_band(self, para: _Para, line: int, start: int) -> _Para:
        """*para* with its lines from *line* on, laid from *start* down, broken again beside the band of a
        square-wrapped object set at the current frame's top when they reach it."""

        bands = sorted((band for band in self.squares.get(self.frame, ()) if band.bottom > start),
                       key=lambda band: band.top)
        if not bands:
            return para
        band = bands[0]
        if para.blank:  # an empty line reaching it: two empty pieces beside an object with text on both sides
            reaches = start + para.height(line) > band.top
            return _in_two_pieces(para) if reaches and band.split and para.lines == 1 and not para.cached else para
        if para.reflow is None:
            raise _Unsupported("objects, notes or a layout cache beside a square-wrapped object moved to the next page")
        again = para.reflow.banded(para, line, replace(band, top=band.top - start, bottom=band.bottom - start))
        if len(bands) > 1 and start + again.span(0, again.lines) > bands[1].top:
            raise _Unsupported("a paragraph beside two square-wrapped objects on a page")
        return again

    def _span_bands(self, spans: tuple[_FlowTable, int, _Wrap], start: int) -> None:
        """The bands of a table wrapped square, anchored in the paragraph being laid from *start*, that goes
        on over the page end: it flows as a flowing table from its top, and on each page it reaches the lines
        go beside its part there -- on its first page from its top to the foot, on a page it fills the whole
        page, on its last page from the top down to its end."""

        table, offset, band = spans
        top = start + offset
        last, end = _flow_table(table, self.frame, top + table.above, self.body)
        for frame in range(self.frame, last + 1):
            part = replace(band, top=top if frame == self.frame else 0,
                           bottom=end + table.below if frame == last else self.body)
            if self.bands.get(frame) or self.sides.get(frame) or frame in self.reserved \
                    or any(other.top < part.bottom and part.top < other.bottom for other in self.squares.get(frame, ())):
                raise _Unsupported("a square-wrapped table going on over the page end beside other objects")
            self.squares.setdefault(frame, []).append(part)
        self.table_end = max(self.table_end, last)

    def _move_band(self, band: _Wrap) -> None:
        """A square-wrapped object anchored in the paragraph being laid, flowing with the text, went past the
        body's foot: Hancom sets it at the next page's body top whatever its offset, the lines there whose top
        is above its foot beside it, and that page is used even when no line goes there."""

        target = self.frame + 1
        if band.bottom > self.body or self.bands.get(target) or self.sides.get(target) or target in self.reserved \
                or any(other.top < band.bottom for other in self.squares.get(target, ())):
            raise _Unsupported("an object going on to the next page's top beside other objects")
        if band.push:  # a top-and-bottom one: the lines reaching it go below it
            self.bands[target] = [(band.top, band.bottom)]
        else:
            self.squares.setdefault(target, []).append(band)
        self.table_end = max(self.table_end, target)

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
        """Count the notes of *count* lines from line *first*, just placed."""

        for line, (frame, top) in zip(range(first, first + count), self.out[len(self.out) - count:]):
            note_height, notes, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes[0] += note_height
            self.page_notes[1] += notes
            if not para.kept:
                self._reach(frame, top, top + para.height(line))


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
    moved: set[int] = set()  # the paragraphs whose square-wrapped object went on to the next page's top
    while True:
        try:
            return _paginate(measure, section, replace(page, rebreak=True) if moved else page, notes, moved)
        except _BandMoves as signal:
            if signal.index in moved or len(moved) >= 16:
                raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot") from None
            moved.add(signal.index)


def _paginate(measure: _Measure, section: Any, page: _Page, notes: _NoteShape, moved: set[int]) -> _SectionLayout:
    paras = []
    wrap: _Wrap | None = None
    for index, paragraph in enumerate(section.findall(f"{HP}p")):
        para, wrap = _wrapped_paragraph(measure, page, paragraph, wrap, index in moved)
        band = _paper_band(measure, page, paragraph)
        para = replace(para, kept=bool(_cached_metrics(paragraph)))
        paras.append(para if band is None else replace(para, paper=band))
    paper = {index: para.paper for index, para in enumerate(paras) if para.paper is not None}
    bands: dict[int, list[tuple[int, int]]] = {}
    sides: dict[int, list[tuple[int, int]]] = {}
    for _ in range(4):  # an object placed on the paper acts on the page its paragraph lands on
        paginator = _Paginator(page.body, page.columns, notes, bands, page.widths, sides)
        frames = paginator.run(paras)
        firsts = [0]
        for count in paginator.counts:
            firsts.append(firsts[-1] + count)
        placed: dict[int, list[tuple[int, int]]] = {}
        beside: dict[int, list[tuple[int, int]]] = {}
        for index, (top, bottom, room, columns) in paper.items():  # on the columns of the page it reaches over
            first = paginator.out[firsts[index]][0] // page.columns * page.columns
            for column in columns:
                (beside if room else placed).setdefault(first + column, []).append((top, bottom))
        if placed == bands and beside == sides:
            break
        bands, sides = placed, beside
    else:
        raise _Unsupported("objects placed on the paper whose pages do not settle")
    if paginator.beside:
        raise _Unsupported("text beside an object placed on the paper")
    return _SectionLayout(page.columns, frames, paginator.out, paginator.counts)


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
