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
  unequal width (each its share of 32768 of the text width, ``hp:colSz``, rounded) holding objects only as
  characters: a paragraph without a valid layout cache breaks the lines a column holds at that
  column's width, and going on into a column of another width breaks its rest there again, from
  the first character that column holds.
* Column areas: a paragraph holding a column definition after the section's first starts a new area
  of columns (column settings in a cell or a text box are that list's own), on the page where the
  one before ends, 1134 (4 mm) below its lowest line whatever the spacing (on the next page's top
  when there is no room), its lines counted from the area's top on that page; an area followed by
  another has the columns of its last page balanced, as short as they can be with every line still
  on that page, and a column break in balanced columns (``BALANCED_NEWSPAPER``) starts such an area
  too. A definition behind its paragraph's text starts the area but not its columns.
* Objects: an object in front of or behind the text takes no room: the lines go where they would
  without it, wherever it stands; one placed top and bottom from the top or the bottom of the paper
  or of the page (its body) keeps every line of its page out of its band (a line reaching it, in any
  paragraph on that page, goes below it -- on to the next page when the band reaches the body's
  foot -- and the lines after follow; with several columns of equal width, in each column it
  reaches over from the paper's left, centre or right, the others running past it; in one column, when
  such a band reaching the body's foot keeps to its paragraph's page (pos@holdAnchorAndSO="1") and that
  paragraph's first line with its spacing reaches it there, the paragraph goes on to the next page's
  top with it and the lines above stay where they are), and so does one
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
  it (offset down from a paragraph holding nothing else, the empty line stays where it is and the first
  line reaching it after comes below it); anchored in a paragraph of text or of objects set as characters
  (from the paragraph's top),
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
  at the page end goes to the next page, and the table with it (to the page after when an earlier
  table that started past its anchor ends there too low for the line below it). When a table moved row by row has no
  room for its first row under its anchor line, it starts on the next page and the text after it
  goes on under the anchor, then below the table on the pages the table takes. Footnotes take
  room at the foot of the page (or right beneath the text, the same room) and go on over the page end.
  Endnotes go after the document's text (or, placed at each section's end, after their section's),
  below the foot of its last line (on the next page when footnotes take room on that page): the note
  area's spacing and separator, then the notes' lines one after another, a note's last line without
  the line spacing below it, going on over page ends.
* Sections: a later paragraph holding section settings starts a new section there, on a new page, with
  those settings; when a section's first paragraph holds none, the paragraphs before go on Hancom's
  default A4 page (59528 x 84188) with its default margins, in one column.
* Line grid: in a section with a line grid (``hp:grid@lineGrid``), a paragraph snapping to it
  (``snapToGrid``) has each line's height and advance and its spacing before and after take whole grid
  steps, rounded up, its first line going to the first step at or below where it would go. A character
  grid is followed through layout caches.

A table set as a character that the row model does not follow (merged rows, a nested table) keeps
the height Hancom saved for it (``hp:sz``) when every paragraph in it keeps a valid layout cache,
i.e. Hancom laid the table out as it is. Otherwise a table whose cells merge rows has its rows as
their tallest cells of one row, and each merged cell, the one that ends first first, gives the last
of its rows what they lack.

Anything else makes the estimate unsupported: endnotes placed otherwise than at the document's or the section's
end or after a section of several columns, an object not set as a character in columns
of unequal width, and there a paragraph without such a cache holding objects, composed characters,
ruby text or footnotes, footnotes or objects placed on the page or the paper in a section whose
columns change, section settings deeper than a run of a later paragraph, a line or character grid in
columns or with objects, tables or notes, a character grid in a paragraph without such a cache, an object with text or
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
import math
import os
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from lxml import etree

from ..form_fit.measure import (
    _DEFAULT_TAB_STOP,
    _GLYPH_SPACE,
    _TYPED_NO_BREAK_SPACE,
    char_advance,
    font_line_height,
    hancom_line_starts,
    in_char_units,
    indented_widths,
    margins_doubled,
    paragraph_label,
    text_style_from_refs,
)
from ..oxml._document_primitives import _remove_stale_paragraph_layout_cache
from ..oxml.header_part import HwpxOxmlHeader
from ..oxml.namespaces import HH, HP
from ..oxml.paragraph_heading import paragraph_heading
from ..oxml.section import _remove_short_paragraph_layout_cache
from ..oxml.section_format import COLUMN_SHARES, _drawn_page_size, _page_margin
from ..oxml.table_sizes import cell_margins_of, grid_widths_of
from ._page_flow import (
    _drawn_lines as _drawn_lines,
)
from ._page_flow import (
    _Paginator as _Paginator,
)
from ._page_flow import (
    _paragraph as _paragraph,
)
from ._page_flow import (
    _wrapped_paragraph as _wrapped_paragraph,
)

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
#: How tall Hancom makes a table's row that only cells merged over rows cover at least, unless the table is set
#: not to adjust its cells (``hp:tbl@noAdjust``): it starts the merged cells' heights from that.
_MERGED_ROW_LEAST = 100
#: the room a cell that never breaks its text into lines (``hp:subList@lineWrap`` SQUEEZE or KEEP) gives a line
_NO_WRAP = 1 << 40
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

    return _estimate(document)


def _estimate(document: Any, *, first_reason: bool = False) -> PageEstimate:
    """:func:`estimate_pages`; with *first_reason*, stop at the first section not followed (its reason the only
    one given) instead of laying every section out to name them all."""

    root = getattr(_open(document), "_root")
    if not root.headers:  # the shapes every paragraph names live there
        return PageEstimate(None, (), ("a document without a header part (Contents/header.xml)",))
    # a document kept compatible with MS Word Hancom lays out as Word would (line heights from the font, a
    # picture's line its height and the font's descent), which the estimate does not follow
    compatible = next(root.headers[0].element.iter(f"{HH}compatibleDocument"), None)
    if compatible is not None and compatible.get("targetProgram") == "MS_WORD":
        return PageEstimate(None, (), ("a document laid out for compatibility with MS Word",))
    measure = _Measure(root)
    layouts: list[_SectionLayout] = []
    reasons: list[str] = []
    part = None
    notes: list[Any] = []  # the endnotes going to the document's end
    for number, section in enumerate(root.sections):
        try:
            for part in _section_parts(measure, section.element):
                measure.tab_stop = _tab_stop(part) or _DEFAULT_TAB_STOP
                own = list(part.iter(f"{HP}endNote"))
                shape = _note_shape(part, "endNotePr") if own else None
                layouts.append(_lay_section(measure, _unswitched(part)))
                if shape is not None and shape.section_end:  # after the section's text, before the next section
                    layouts[-1] = _with_endnotes(measure, layouts[-1], shape, own)
                else:
                    notes += own
        except _Unsupported as exc:
            reasons.append(f"section {number}: {exc}")
            if first_reason:
                break
    if reasons:
        return PageEstimate(None, (), tuple(reasons))
    if notes:
        last = len(root.sections) - 1
        try:
            layouts[-1] = _with_endnotes(measure, layouts[-1], _note_shape(part, "endNotePr"), notes)
        except _Unsupported as exc:
            return PageEstimate(None, (), (f"section {last}: {exc}",))
    return _assemble(layouts)


def _with_endnotes(measure: _Measure, layout: _SectionLayout, shape: _NoteShape, notes: list[Any]) -> _SectionLayout:
    """The last section's layout with the document's endnotes after its text (or a section's with its own, placed at
    each section's end, ``hp:placement@place`` ``END_OF_SECTION``): below the foot of its last
    line (on the next page when footnotes take room on that page), the note area's spacing and separator,
    then each note's lines, the spacing between notes between them, going on over page ends line by line. A
    note's last line takes no line spacing below it (Hancom stacks one-line notes as tall as their text).
    Endnotes right beneath the text (``hp:placement@beneathText``) are laid out the same."""

    if layout.places is not None or layout.columns != 1 or layout.end is None:
        raise _Unsupported("endnotes after columns")
    frame, top = layout.end
    if layout.noted:
        frame, top = frame + 1, 0
    top += shape.above + shape.line + shape.below
    for number, note in enumerate(notes):
        if number:
            top += shape.between
        lines = measure.stack_lines(note.findall(f"{HP}subList/{HP}p"), layout.width, caches=False)
        for index, (height, advance) in enumerate(lines):
            if top + height > layout.body and top > 0:
                frame, top = frame + 1, 0
            top += height if index == len(lines) - 1 else advance
    return replace(layout, frames=max(layout.frames, frame + 1))


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


def _char_unit_height(header: Any) -> int:
    """The character size of the first paragraph style (바탕글), which margins in ``unit="CHAR"`` count in."""

    style = next((el for el in header.iter(f"{HH}style") if el.get("id") == "0"), None)
    ref = style.get("charPrIDRef") if style is not None else None
    shape = next((el for el in header.iter(f"{HH}charPr") if el.get("id") == ref), None) if ref is not None else None
    return int(shape.get("height", 1000)) if shape is not None else 1000


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
    font_line: bool = False  # its lines as tall as the font makes them (fontLineHeight)
    snap: bool = True  # its lines on the section's line grid (snapToGrid)


def _para_shape(header: Any, para_pr_id: str, doubled: bool = False) -> _Shape:
    """The paragraph shape *para_pr_id*. With *doubled* (a document an older Hancom saved, see
    :func:`~hwpx.form_fit.measure.margins_doubled`), margins and a line spacing in HWPUNIT outside
    ``hp:switch`` hold twice the values Hancom lays out with, as ``hp:default`` does."""

    shape = next((el for el in header.iter(f"{HH}paraPr") if el.get("id") == para_pr_id), None)
    if shape is None:
        raise _Unsupported(f"paragraph shape {para_pr_id} is missing")
    # The hp:case holding margin and lineSpacing: outline levels 8-10 put hh:heading in an earlier switch.
    case = next((c for c in shape.iter(f"{HP}case") if _child(c, "lineSpacing") is not None), None)
    holder = case if case is not None else shape
    spacing = _child(holder, "lineSpacing")
    margin = _child(holder, "margin")
    half = 2 if doubled and case is None else 1

    def value(name: str) -> int:
        element = _child(margin, name) if margin is not None else None
        if element is None:
            return 0
        if element.get("unit") == "CHAR":  # two-hundredths of 바탕글's character size
            return in_char_units(int(element.get("value", 0)), _char_unit_height(header)) // half
        return int(element.get("value", 0)) // half

    breaks = shape.find(f"{HH}breakSetting")
    kind, amount = ("PERCENT", 160)
    if spacing is not None:
        kind, amount = spacing.get("type", "PERCENT"), int(spacing.get("value", 160))
        if kind != "PERCENT" and spacing.get("unit") == "CHAR":  # as a margin in that unit
            amount = in_char_units(amount, _char_unit_height(header))
        elif kind != "PERCENT":
            amount //= half
    return _Shape(kind, amount, value("prev"), value("next"), value("left"), value("right"), value("intent"),
                  dict(breaks.attrib) if breaks is not None else {}, shape.get("fontLineHeight") in ("1", "true"),
                  shape.get("snapToGrid", "1") not in ("0", "false"))


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


def _object_pitch(shape: _Shape, obj: Any, tall: int, size: int) -> int:
    """The distance from the top of a line *tall* tall holding only *obj*, an object set as a character, to the
    next line's top in a paragraph of *shape* whose characters are *size*: a percentage spacing is the
    characters' unless the object is set to affect the line spacing (``hp:pos@affectLSpacing``), when it is the
    line's, as any other spacing is -- a fixed one keeps the next line that far down even below a taller object,
    an at-least one at the line's height when that is more."""

    if shape.kind == "PERCENT" and obj.find(f"{HP}pos").get("affectLSpacing") != "1":
        return tall + _pitch(shape.kind, shape.value, size) - size
    return _pitch(shape.kind, shape.value, tall)


def _on(flags: dict[str, str], name: str) -> bool:
    return flags.get(name) in ("1", "true")


def _t_text(text_element: Any) -> str:
    """The text of one ``hp:t``, with ``hp:lineBreak`` as a newline, ``hp:tab`` as a tab, ``hp:nbSpace`` as a
    no-break space (U+00A0) and ``hp:fwSpace`` as a fixed-width one (U+3000), as python-hwpx reads them; an
    ideographic space typed in the text is FormFit's ``_GLYPH_SPACE``, so it is not taken for a fixed-width one, and
    a no-break space typed in it ``_TYPED_NO_BREAK_SPACE``, which Hancom lays out at the font's own width.
    A table-of-contents mark (``hp:titleMark``) is a character of no width (U+200D): Hancom lays its line out as
    tall as the mark's run and spaces it from that size."""

    parts = [text_element.text or ""]
    for child in text_element:
        name = _local(child)
        parts.append({"lineBreak": "\n", "tab": "\t", "nbSpace": "\u00a0", "fwSpace": "\u3000",
                      "titleMark": "\u200d"}.get(name, ""))
        parts.append(child.tail or "")
    return "".join(part.replace("\u3000", _GLYPH_SPACE).replace("\u00a0", _TYPED_NO_BREAK_SPACE) if index % 2 == 0
                   else part for index, part in enumerate(parts))


def _indented(line: float, shape: _Shape, style: Any) -> list[float]:
    """The first line's and the other lines' room of a paragraph of *shape* *line* wide inside its margins: less
    its first-line indent (a hanging one narrows the other lines) and its bullet or number label's room
    (``style.head``, see :func:`hwpx.form_fit.measure.indented_widths`). Hancom drops an indent that leaves its
    line less room than its narrowest line (:data:`_MIN_LINE_WIDTH`): every line is *line* wide then. A
    paragraph whose shape squeezes it (``lineWrap`` SQUEEZE) is never broken into lines: Hancom presses it onto one."""

    if style is not None and getattr(style, "line_wrap", "BREAK") == "SQUEEZE":
        return [_NO_WRAP, _NO_WRAP]
    if style is not None and style.head:
        return list(indented_widths(line, replace(style, indent=shape.indent)))
    rooms = [line - max(shape.indent, 0), line - max(-shape.indent, 0)]
    return [line, line] if min(rooms) < _MIN_LINE_WIDTH else rooms


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
    """The shape lookups FormFit's text style reads, with the paragraph shapes and tab definitions read once:
    the document reads them from the header again on every lookup. (No ``_root`` attribute, so FormFit
    uses this object and not the document behind it.)"""

    def __init__(self, root: Any) -> None:
        self._document = root
        self.headers = root.headers
        self.version = root.version  # how the paragraph shapes' margins outside hp:switch read
        self.sections = root.sections  # the outline numbering of a paragraph's label
        self._paragraph_shapes: dict[str, Any] | None = None
        self._tab_definitions: dict[str, Any] | None = None

    def char_property(self, char_pr_id: Any) -> Any:
        return self._document.char_property(char_pr_id)

    def paragraph_property(self, para_pr_id: Any) -> Any:
        if self._paragraph_shapes is None:
            self._paragraph_shapes = self._document.paragraph_properties
        return HwpxOxmlHeader._lookup_by_id(self._paragraph_shapes, para_pr_id)

    def tab_property(self, tab_pr_id: Any) -> Any:
        if self._tab_definitions is None:
            self._tab_definitions = self._document.tab_properties
        return HwpxOxmlHeader._lookup_by_id(self._tab_definitions, tab_pr_id)


class _Measure:
    """Shapes and line breaking of one document."""

    def __init__(self, root: Any) -> None:
        self._root = root
        self._lookups = _Lookups(root)
        self._header = root.headers[0].element
        self._doubled = margins_doubled(root)
        self._shapes: dict[str, _Shape] = {}
        self._styles: dict[tuple[str, tuple[str, ...], str | None], Any] = {}
        self._drawn: dict[Any, str] | None = None
        self._numbered: dict[str, bool] = {}
        self._label_sizes: dict[str, int] = {}
        self._pictured: dict[str, bool] = {}
        #: how far apart the default tab stops of the section at hand are (see :func:`_tab_stop`)
        self.tab_stop = _DEFAULT_TAB_STOP

    def shape(self, para_pr_id: Any) -> _Shape:
        key = str(para_pr_id)
        if key not in self._shapes:
            self._shapes[key] = _para_shape(self._header, key, self._doubled)
        return self._shapes[key]

    def char_height(self, char_pr_id: Any) -> int:
        style = self._root.char_property(char_pr_id)
        return int(style.attributes.get("height", 1000)) if style is not None else 1000

    def font_line(self, size: int, style: Any) -> int:
        """How tall a line of characters *size* tall in *style* is in a paragraph taking its line height from
        the font (see :func:`~hwpx.form_fit.measure.font_line_height`); *size* for a face the glyph table does
        not list."""

        tall = font_line_height(getattr(style, "hangul_face", None), size)
        return size if tall is None else tall

    def headed(self, paragraph: Any) -> bool:
        """Whether Hancom heads *paragraph* with a bullet or number label."""

        if self._drawn is None:
            self._drawn = _drawn_labels(self._root)
        return bool(self._drawn.get(paragraph))

    def style(self, para_pr_id: Any, char_pr_ids: list[Any], paragraph: Any = None) -> Any:
        """FormFit's text style of a paragraph shape and its characters; with *paragraph*, a number's label
        takes the room of the label Hancom draws for that paragraph, and a label without a character shape of
        its own that of the paragraph's end."""

        drawn = None
        if paragraph is not None and self.numbered(para_pr_id):
            if self._drawn is None:
                self._drawn = _drawn_labels(self._root)
            drawn = self._drawn.get(paragraph)
        end = _end_ref(paragraph) if paragraph is not None else None
        key = (str(para_pr_id), tuple(str(ref) for ref in char_pr_ids), drawn, end, self.tab_stop)
        if key not in self._styles:
            style = text_style_from_refs(self._lookups, para_pr_id, char_pr_ids, drawn, end)
            if style is not None and style.tab_stop != self.tab_stop:
                style = replace(style, tab_stop=self.tab_stop)
            self._styles[key] = style
        return self._styles[key]

    def label_size(self, para_pr_id: Any, end: Any = None) -> int:
        """The character size of a paragraph shape's bullet or number label: in its own character shape
        (``hh:paraHead@charPrIDRef``), or without one in that of the paragraph's end (*end*); 0 when it has
        none, or no shape of its own and no *end*."""

        key = str(para_pr_id)
        if key not in self._label_sizes:
            label = paragraph_label(self._root, para_pr_id)
            ref = label[1].get("charPrIDRef") if label is not None else None
            own = ref is not None and ref != "4294967295" and self._root.char_property(ref) is not None
            self._label_sizes[key] = self.char_height(ref) if own else -1 if label is not None else 0
        size = self._label_sizes[key]
        return size if size >= 0 else self.char_height(end) if end is not None else 0

    def copied(self, copies: dict[Any, Any]) -> None:
        """Give each copied paragraph in *copies* (copy -> original) the label Hancom draws for its original."""

        if self._drawn is None:
            self._drawn = _drawn_labels(self._root)
        self._drawn.update({copy: self._drawn[original] for copy, original in copies.items()
                            if original in self._drawn})

    def pictured(self, para_pr_id: Any) -> bool:
        """Whether a paragraph shape heads its paragraphs with a picture bullet sized by its picture
        (``hh:paraHead@useInstWidth``), whose room was not measured: FormFit gives it none."""

        key = str(para_pr_id)
        if key not in self._pictured:
            shape = next((el for el in self._header.iter(f"{HH}paraPr") if el.get("id") == key), None)
            heading = paragraph_heading(shape) if shape is not None else None
            bullet = next((el for el in self._header.iter(f"{HH}bullet") if el.get("id") == heading.get("idRef")),
                          None) if heading is not None and heading.get("type") == "BULLET" else None
            head = bullet.find(f"{HH}paraHead") if bullet is not None else None
            self._pictured[key] = bullet is not None and bullet.get("useImage") in {"1", "true"} \
                and head is not None and head.get("useInstWidth") in {"1", "true"}
        return self._pictured[key]

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
        return sum(len(hancom_line_starts(line, widths if not index else widths[1:] or widths, size / 100, style,
                                          continued=bool(index))) if line else 1
                   for index, line in enumerate(text.split("\n")))  # the lines after a line break are no first line

    def line_starts(self, text: str, widths: list[float], size: int, style: Any,
                    sizes: list[int] | None = None, styles: list[Any] | None = None,
                    advances: dict[int, int] | None = None, objects: Collection[int] = ()) -> list[int]:
        """Where each line starts, as offsets into *text*; *sizes* and *styles* are each character's size
        and style when the text mixes them, *advances* the width of each object set as a character (or
        mark), *objects* the places of the objects."""

        starts: list[int] = []
        base = 0
        for number, line in enumerate(text.split("\n")):
            points = None if sizes is None else [height / 100 for height in sizes[base:base + len(line)]]
            looks = None if styles is None else styles[base:base + len(line)]
            fixed = None if advances is None else {
                index - base: width for index, width in advances.items() if base <= index < base + len(line)}
            placed = {index - base for index in objects if base <= index < base + len(line)}
            room = widths if not number else widths[1:] or widths  # the lines after a line break are no first line
            starts += [base + start for start in (hancom_line_starts(line, room, size / 100, style, points, looks,
                                                                     fixed, placed, continued=bool(number))
                                                  if line else [0])]
            base += len(line) + 1
        return starts

    def stack(self, paragraphs: list[Any], width: int, caches: bool,
              floating: bool = False, lead: int = 0) -> tuple[int, int, int, int]:
        """(height, lines, pitch, size) of *paragraphs* laid out one under another at *width*; pitch
        and size are the last paragraph's. With *caches* a paragraph keeps the lines of its cache. With
        *floating* (a cell's paragraphs) the height reaches down to the foot of any object in front of or
        behind the text placed from a paragraph's top (see :func:`_floating_reach`). *lead* is room above
        the first paragraph's lines (a cell's first paragraph's spacing before): Hancom places an object
        from that paragraph's top above it."""

        height, lines, pitch, size, pending, far = lead, 0, 0, 0, None, 0
        for paragraph in paragraphs:
            runs = paragraph.findall(f"{HP}run")
            size, refs, _ = _text_size(self, runs, paragraph)  # an empty run takes no room, as in the body
            shape = self.shape(paragraph.get("paraPrIDRef"))
            pitch = _pitch(shape.kind, shape.value, size)
            table = _table_alone(runs)
            alone = None if table is not None or caches and _cached_metrics(paragraph) else _object_alone(runs)
            spread = self.spread_lines(paragraph, runs, width, caches=caches) \
                if table is not None or alone is not None else ()
            if spread:  # spaces besides it, some of which go on to the next line
                table = alone = None
            if table is not None:  # one line as tall as the table, spaced like the text
                tall = _inline_table_height(self, table) + _extent_margins(table) + sum(_caption(self, table))
                count, size, pitch = 1, tall, _object_pitch(shape, table, tall, size)
            elif alone is not None:  # so with another object set as a character
                tall = _object_extent(alone, self)[1]
                count, size, pitch = 1, tall, _object_pitch(shape, alone, tall, size)
            else:
                cached = spread or (_cached_metrics(paragraph) if caches else ())
                cached = cached or self.pushed_lines(paragraph, runs, width) \
                    or self.marked_lines(paragraph, runs, width) or self.mixed_lines(paragraph, runs, shape, width)
                if cached:  # the lines Hancom laid out, each as tall as it drew it
                    anchor = height - lead if pending is None else height + pending + shape.prev
                    if pending is not None:
                        height += pending + shape.prev
                    top = height
                    far = max(far, anchor + _floating_reach(runs, self)) if floating else far
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
                # an empty line keeps the character size: Hancom makes only a line of characters as tall as
                # its font makes it
            anchor = height - lead if pending is None else height + pending + shape.prev
            if pending is not None:
                height += pending + shape.prev
            top = height
            far = max(far, anchor + _floating_reach(runs, self)) if floating else far
            height += (count - 1) * pitch + size
            pending = pitch - size + shape.next
            if top + _objects_reach(runs, self) > height:  # an object placed from the paragraph reaches lower
                height, pending = top + _objects_reach(runs, self), shape.next
            lines += count
        return max(height, far), lines, pitch, size

    def mixed_lines(self, paragraph: Any, runs: list[Any], shape: _Shape, width: int) -> tuple[tuple[int, int], ...]:
        """(height, advance) of each line of a paragraph whose characters differ in size or style, or that takes
        its line height from the font, laid out at *width* as in the body; empty for any other paragraph."""

        _, refs, sizes = _text_size(self, runs)
        looks = _char_styles(self, paragraph, runs)
        end = _end_size(self, runs, sizes)
        head = _head_size(self, paragraph, sizes)
        held = _held_sizes(self, runs, sizes)
        if len(set(sizes)) < 2 and looks is None and not end and not head and not held                 and not (shape.font_line and sizes):
            return ()
        style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        return _line_metrics(self, _run_text(runs), _line_widths(shape, width, style), sizes, style, shape, {}, looks,
                             end=end, head=head, held=held)

    def stack_lines(self, paragraphs: list[Any], width: int, caches: bool,
                    pieces: bool = False) -> tuple[tuple[int, int], ...]:
        """(height, advance to the next line's top) of every line of *paragraphs* laid out as in
        :meth:`stack`, a table set as a character alone in its paragraph as one line; with *pieces*, a table
        that splits on its own in a paragraph as its pieces (see :func:`_table_pieces`)."""

        metrics: list[tuple[int, int]] = []
        for paragraph in paragraphs:
            shape = self.shape(paragraph.get("paraPrIDRef"))
            if metrics:  # the gap between the paragraphs
                last_height, last_advance = metrics[-1]
                metrics[-1] = (last_height, last_advance + shape.prev)
            runs = paragraph.findall(f"{HP}run")
            split = _table_pieces(self, paragraph) if pieces else None
            if split is not None:  # a table placed top and bottom on its own: its rows (or their lines)
                lines = split[0]
                metrics += list(lines[:-1]) + [(lines[-1][0], lines[-1][1] + shape.next)]
                continue
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
        placed top and bottom from its top: the first line reaching the table (with a caption above or below
        it) and the lines after it go below it, and the paragraph reaches down to the table's foot at least;
        empty for any other paragraph."""

        obj = _object_before_text(runs, self.headed(paragraph))
        if obj is None or _local(obj) != "tbl" and obj.find(f"{HP}pos").get("flowWithText") == "0":
            return ()  # a picture or drawing that stays put pushes no line aside in a cell
        top = _down(obj.find(f"{HP}pos"))
        foot = top + (_cell_extent(self, obj) if _local(obj) == "tbl" else _extent(obj, "height", self))
        shape = self.shape(paragraph.get("paraPrIDRef"))
        lines = list(self.marked_lines(paragraph, runs, width) or self.mixed_lines(paragraph, runs, shape, width))
        if not lines:
            size, refs, _ = _text_size(self, runs, paragraph)
            style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
            count = max(1, self.lines(_run_text(runs), _line_widths(shape, width, style), size, style))
            lines = [(size, _pitch(shape.kind, shape.value, size))] * count  # an empty line keeps its size
        y = 0
        for index, (height, advance) in enumerate(lines):
            if y < foot and y + height > top:  # it reaches the table: below it, and the lines after it; it takes
                lines[index] = (height + foot - y, advance + foot - y)  # the room above it (and goes on to a next
                break  # page with the table)
            y += advance
        above = sum(advance for _, advance in lines[:-1])
        if above + lines[-1][0] < foot:  # every line above the table: the paragraph holds it
            lines[-1] = (foot - above, foot - above)
        return tuple(lines)

    def wrapped_lines(self, paragraphs: list[Any], width: int, tables: bool = False
                      ) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[_Reach, ...]]:
        """(height, advance) of every line of a cell's *paragraphs*, and the room above each when a part of the
        cell starts with it (a paragraph's spacing before at its first line), when one of them holds a picture
        or drawing placed top and bottom or square from its top that moves with the text (see
        :func:`_wraps_in_cell`; with *tables*, a table so placed, or in front of or behind the text, too);
        empty for any other cell. Hancom stands such an object its offset below the
        top of the line its control falls on (the paragraph laid out the cell's whole width), or of the
        paragraph, above its spacing before, when that is the first line (an offset up counts as none), and
        lays every line from there on, of that paragraph and the next ones, clear of it (see :func:`_clear_of`).
        The cell reaches down to the lowest object's foot, and to that of any object in front of or behind
        the text placed from a paragraph's top (see :func:`_floating_reach`; such a table stands from the top
        of the line its control falls on, as an object wrapped does, and pushes no line aside). A paragraph
        with a valid layout cache keeps its lines. With *tables*, also where each object stands among the lines
        (see :class:`_Reach`)."""

        owned = [[obj for run in paragraph.findall(f"{HP}run") for obj in run if _wraps_in_cell(obj, tables)]
                 for paragraph in paragraphs]
        floats = [[obj for run in paragraph.findall(f"{HP}run") for obj in run
                   if tables and _local(obj) == "tbl" and _floating(obj)] for paragraph in paragraphs]
        if not any(owned) and not any(floats) or any(len(objects) + len(over) > 1
                                                     for objects, over in zip(owned, floats)):
            return (), (), ()  # several in a paragraph: Hancom stacks them, which is not followed here (they
        # count as before)
        for table in (obj for over in floats for obj in over):
            pos = table.find(f"{HP}pos")
            if pos.get("flowWithText") == "0" or pos.get("vertRelTo") != "PARA" or pos.get("vertAlign", "TOP") != "TOP":
                raise _Unsupported("a table in front of or behind the text in a cell placed otherwise than from "
                                   "its paragraph's top, moving with the text")
        bands: list[tuple[int, int, int | None]] = []  # top, foot and room beside it (None: the lines go below)
        tops: list[int] = []
        heights: list[int] = []
        leads: list[int] = []
        reaches: list[_Reach] = []
        after = 0  # where the next paragraph's first line stands, above its spacing before
        far = 0  # the foot of the lowest object in front of or behind the text
        for paragraph, objects, over in zip(paragraphs, owned, floats):
            obj = objects[0] if objects else None
            shape = self.shape(paragraph.get("paraPrIDRef"))
            runs = paragraph.findall(f"{HP}run")
            text = _run_text(runs)
            empty = not text and not self.headed(paragraph)  # a label is text
            if obj is not None and _local(obj) == "tbl" and empty and obj.find(f"{HP}pos").get("allowOverlap") != "0":
                raise _Unsupported("a table that may overlap the text placed top and bottom or square in an empty "
                                   "cell paragraph")
            top = after + shape.prev if tops else 0
            far = max(far, top + _floating_reach(runs, self))
            place = 0 if obj is None and not over else _control_place(runs, obj if obj is not None else over[0])
            fixed = list(_cached_metrics(paragraph))  # Hancom keeps the lines of a valid cache
            simple = not fixed and _table_alone(runs) is None and not self.spread_lines(paragraph, runs, width) \
                and not self.marked_lines(paragraph, runs, width) \
                and not self.mixed_lines(paragraph, runs, shape, width)
            anchor = 0
            mixed: tuple[tuple[int, int], ...] = ()
            if not fixed and not simple:
                if obj is not None and obj.get("textWrap") == "TOP_AND_BOTTOM":
                    mixed = self.mixed_lines(paragraph, runs, shape, width)
                if obj is not None and not mixed:
                    raise _Unsupported("an object placed top and bottom or square beside text laid out otherwise "
                                       "in a cell")
                # one placed top and bottom narrows no line: the lines of characters differing in size or style
                # stand as they are, those up to the one its control falls on above it and the rest below
                fixed = list(mixed) if mixed else list(self.stack_lines([paragraph], width, caches=True))
                if mixed and place:
                    size, refs, sizes = _text_size(self, runs, paragraph)
                    style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
                    starts = self.line_starts(text, _line_widths(shape, width, style), size, style, sizes,
                                              _char_styles(self, paragraph, runs))
                    if len(starts) != len(fixed):
                        raise _Unsupported("an object placed top and bottom among text laid out otherwise in a cell")
                    anchor = sum(1 for start in starts[1:] if start < place)
                if mixed:
                    fixed[-1] = (fixed[-1][0], fixed[-1][1] + shape.next)
            elif fixed:
                fixed[-1] = (fixed[-1][0], fixed[-1][1] + shape.next)
            if fixed:
                if place and not mixed:
                    raise _Unsupported("an object placed top and bottom or square after the text of a paragraph "
                                       "with a layout cache in a cell")
                lines, narrow, own = _clear_of(self, fixed, top, shape.prev, anchor, obj, bands, empty, width)
                if narrow and not _cache_lines(paragraph):
                    raise _Unsupported("text laid out otherwise beside a square-wrapped object in a cell")
            else:
                size, refs, _ = _text_size(self, runs, paragraph)
                style = self.style(paragraph.get("paraPrIDRef"), refs, paragraph)
                pitch = _pitch(shape.kind, shape.value, size)  # an empty line keeps the character size
                full = _line_widths(shape, width, style)
                starts = self.line_starts(text, full, size, style) if text else [0]
                anchor = sum(1 for start in starts[1:] if start < place)
                narrow = {}
                for _ in range(10):  # FormFit breaks the lines, and which are beside an object follows from them
                    rooms = [(_line_widths(shape, narrow[index], style) if index in narrow else full)[min(index, 1)]
                             for index in range(max(narrow, default=0) + 2)]
                    count = len(self.line_starts(text, rooms, size, style)) if text else 1
                    metrics = [(size, pitch)] * (count - 1) + [(size, pitch + shape.next)]
                    lines, found, own = _clear_of(self, metrics, top, shape.prev, anchor, obj, bands, empty, width)
                    if found == narrow:
                        break
                    narrow = found
                else:
                    raise _Unsupported("lines beside a square-wrapped object in a cell that do not settle")
                if narrow and ("\n" in text or style.head):
                    raise _Unsupported("a paragraph with margins, a label or line breaks beside a square-wrapped "
                                       "object in a cell")
            if obj is not None and own is None:
                raise _Unsupported("an object placed top and bottom or square past its paragraph's lines in a cell")
            if own is not None:
                bands.append(own)
            anchor = min(anchor, len(lines) - 1)
            line = top if anchor == 0 else lines[anchor - 1][0] + lines[anchor - 1][2]  # where it would stand
            if own is not None and tables:
                if own[2] is None:  # it pushes the lines below it: the first of them, where it would stand
                    pushed = next(((index, top if index == 0 else lines[index - 1][0] + lines[index - 1][2])
                                   for index in range(anchor, len(lines))
                                   if lines[index][0] > (top if index == 0 else lines[index - 1][0] + lines[index - 1][2])),
                                  None)
                    reaches.append(_Reach(line, own[0], own[1], _table_first(self, obj),
                                          None if pushed is None else pushed[1],
                                          0 if pushed is None else lines[pushed[0]][1], *_split_rows(self, obj)))
                else:
                    reaches.append(_Reach(line, own[0], own[1]))
            for table in over:  # from the top of the line its control falls on, where that line would follow the
                # one before (of the paragraph, above its spacing before, on its first line)
                up = (top - shape.prev if anchor == 0 else line) + _down(table.find(f"{HP}pos"))
                far = max(far, up + _cell_extent(self, table))
                reaches.append(_Reach(line, up, up + _cell_extent(self, table)))
            for index, (line_top, height, advance) in enumerate(lines):
                if index == 0 and line_top > top:  # below an object: the line takes the room above it
                    height, line_top = height + line_top - top, top
                elif index and tables and line_top > lines[index - 1][0] + lines[index - 1][2]:  # so a later
                    # line (a table goes on over a page end with it)
                    follow = lines[index - 1][0] + lines[index - 1][2]
                    height, line_top = height + line_top - follow, follow
                tops.append(line_top)
                heights.append(height)
                leads.append(shape.prev if index == 0 else 0)
            after = lines[-1][0] + lines[-1][2]
        heights[-1] = max(heights[-1], max((foot for _, foot, _ in bands), default=0) - tops[-1], far - tops[-1])
        if any(later < earlier for earlier, later in zip(tops, tops[1:])):
            raise _Unsupported("lines in a cell placed up past an object placed top and bottom or square")
        return tuple((height, (nxt - line_top) if nxt is not None else height)
                     for height, line_top, nxt in zip(heights, tops, [*tops[1:], None])), tuple(leads), tuple(reaches)

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
        end = _end_size(self, runs, _text_size(self, runs)[2])  # an empty run ending it, as in the body
        return _line_metrics(self, text, _line_widths(shape, width, style), sizes, style, shape, placed,
                             looks if len(set(looks)) > 1 else None, marked, end)


@dataclass(frozen=True)
class _Reach:
    """Where an object placed from a cell paragraph stands among the cell's lines, from the top of its first line:
    where the line its control falls on would stand (``line``), the object's top and foot, and, for a table
    pushing the lines below it, how far below its top its first row ends (``first``; 0 for anything else), where
    the first line it pushes below it would stand (``unit``; ``line`` when it pushes that very line) and how
    tall that line is (``text``), and, for one that may split between its rows, the room above its first row,
    the pieces it splits into and the room below its last row (``above``, ``rows``, ``below``; see
    :func:`_split_rows`), with the table and its rows joined by merged cells, one piece each (where the
    first's piece stands among the pieces, its first and last row), which a page end splits cell by cell."""

    line: int
    top: int
    foot: int
    first: int = 0
    unit: int | None = None
    text: int = 0
    above: int = 0
    rows: tuple[tuple[int, int, int, int], ...] = ()
    below: int = 0
    table: _FlowTable | None = None
    blocks: tuple[tuple[int, int, int], ...] = ()


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
    #: its tables are placed top and bottom on their own and split (see :func:`_table_pieces`): its lines
    #: (those tables' pieces among them) split as any cell's
    pieces: bool = False
    #: the room each of those lines needs below it to stay above a page end: a table's piece a table's cut
    #: (101) more than a line of text
    cuts: tuple[int, ...] = ()
    #: rows of those tables joined by merged cells, one piece each: (where the first's piece stands among the
    #: lines, the table, its first and last row); a page end among them splits them cell by cell
    blocks: tuple[tuple[int, _FlowTable, int, int], ...] = ()
    #: the tables among its tallest cell's text placed top and bottom, square, or in front of or behind it
    #: (laid out by :meth:`_Measure.wrapped_lines`): a page end is not followed through them
    reaches: tuple[_Reach, ...] = ()


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
    as a row). A table's cell spacing (``hp:tbl@cellSpacing``) stands above each row: every cell is that much
    taller (a cell merged over rows spans the spacings between them), and the spacing below the last row is
    the table's (see :func:`_table_ends`)."""

    rows: dict[int, _Row] = {}
    merged: list[tuple[int, int, _Row]] = []  # (first row, rows spanned, the cell as a row)
    cells: list[tuple[int, int, _Row]] = []
    nested: set[int] = set()  # rows with a cell holding a table
    headers: set[int] = set()  # rows with a header cell of their own
    reached: set[int] = set()  # rows with a table among a cell's text (see _Reach)
    firsts: dict[int, int] = {}  # each row's tallest first line of a cell of its own
    tallest: dict[int, int] = {}  # each row's tallest cell of its own, and the most any fills with its text
    filled: dict[int, int] = {}
    widths = grid_widths_of(table)
    spacing = _cell_spacing(table)
    for tc in (tc for tr in table.findall(f"{HP}tr") for tc in tr.findall(f"{HP}tc")):
        row, span = _cell_row(measure, table, tc, widths.get(tc)), _row_span(tc)
        if spacing:  # the cell spacing above it, kept with its lines when it goes on over a page end
            row = replace(row, height=row.height + spacing, margins=row.margins + spacing)
        address = tc.find(f"{HP}cellAddr")
        first = int(address.get("rowAddr", 0)) if address is not None else len(rows)
        cells.append((first, span, row))
        if row.nested:
            nested.update(range(first, first + span))
        if row.header and span == 1:
            headers.add(first)
        if span == 1:
            firsts[first] = max(firsts.get(first, 0), row.first)
            tallest[first] = max(tallest.get(first, 0), row.height)
            filled[first] = max(filled.get(first, 0), row.height - row.spare)
        if span > 1 and row.reaches:
            raise _Unsupported("a table among the text of a cell merged over rows")
        if row.reaches:
            reached.add(first)
        if span > 1:
            merged.append((first, span, row))
        elif first not in rows or (row.height - row.spare, row.height, row.lines)                 > (rows[first].height - rows[first].spare, rows[first].height, rows[first].lines):
            rows[first] = row  # the cell its text fills most: its lines split the row over a page end
    for first in reached:  # one among the text of a cell that is not the tallest: no page end followed
        if not rows[first].reaches:
            rows[first] = replace(rows[first], reaches=(_Reach(-1, 0, 1 << 62),))
    for first in headers:  # a header row whatever cell is the tallest
        rows[first] = replace(rows[first], header=True)
    for first, line in firsts.items():
        rows[first] = replace(rows[first], first=line)
    for first, height in tallest.items():  # as tall as its tallest cell, with room to spare under the text
        rows[first] = replace(rows[first], height=height, spare=height - filled[first])  # filling one most
    least = 0 if _on(dict(table.attrib), "noAdjust") else _MERGED_ROW_LEAST
    for first, span, cell in merged:
        for index in range(first, first + span):
            if index not in rows:  # every cell over it is merged over rows
                rows[index] = replace(cell, height=least, lines=1, margins=0, spare=0)
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


def _cell_spacing(table: Any) -> int:
    """The room Hancom keeps between a table's cells and around them (``hp:tbl@cellSpacing``)."""

    spacing = int(table.get("cellSpacing", 0) or 0)
    return spacing if 0 < spacing < 1 << 31 else 0


def _table_ends(table: Any) -> tuple[int, int]:
    """The room a table that flows with the text keeps above its rows and below them on each page it goes on:
    its outer margins (``hp:outMargin`` top and bottom), and below the rows its cell spacing too."""

    margin = table.find(f"{HP}outMargin")
    top, bottom = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
    return top, bottom + _cell_spacing(table)


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


def _size_protected(table: Any) -> bool:
    """Whether *table* is set not to change size (``hp:sz@protect``): Hancom keeps its rows as declared, however
    tall their text."""

    size = table.find(f"{HP}sz")
    return size is not None and size.get("protect") == "1"


def _cell_height(size: Any) -> int:
    """A cell's stored height (hp:cellSz): a negative one, which the file keeps as an unsigned 32-bit number,
    counts as none -- Hancom gives that cell its top and bottom margins and grows it to fit its text."""

    height = int(size.get("height", 0)) if size is not None else 0
    return 0 if height >= 1 << 31 else height


def _margin(margin: Any, side: str) -> int:
    """One side of an object's outer margins (hp:outMargin): a negative one, which the file keeps as an
    unsigned 32-bit number, counts as none, as Hancom lays it out (and saves it)."""

    value = int(margin.get(side, 0))
    return 0 if value < 0 or value >= 1 << 31 else value


def _extent_margins(obj: Any) -> int:
    margin = obj.find(f"{HP}outMargin")
    return 0 if margin is None else _margin(margin, "top") + _margin(margin, "bottom")




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


def _pos_offset(pos: Any, name: str) -> int:
    """An object's ``vertOffset`` or ``horzOffset`` as Hancom reads it: the file keeps an offset up or left as
    an unsigned 32-bit number; one written with a minus sign Hancom reads as 0 (and saves so)."""

    value = pos.get(name, "0").strip()
    return 0 if value.startswith("-") else int(value)


def _down(pos: Any) -> int:
    """How far below its paragraph's top an object placed from there stands: one offset up (a negative
    offset, which the file keeps as an unsigned 32-bit number) stands at the paragraph's top."""

    offset = _pos_offset(pos, "vertOffset")
    return 0 if offset >= 1 << 31 else offset


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


def _split_before_text(paragraphs: list[Any]) -> bool:
    """Whether a cell's paragraphs hold a table placed top and bottom from its paragraph's top before its text
    where Hancom split the cell over a page end: their layout caches start over at the top of the next page at
    that paragraph or the next. Its declared height, as those caches, holds a part of it."""

    tops = [int(cache.get("vertpos", 0)) if cache is not None else None
            for cache in (paragraph.find(f"{HP}linesegarray/{HP}lineseg") for paragraph in paragraphs)]
    for index, paragraph in enumerate(paragraphs):
        table = _table_before_text(paragraph.findall(f"{HP}run"))
        if table is None or _local(table) != "tbl":
            continue
        for at in (index, index + 1):
            if 0 < at < len(tops) and tops[at] is not None and tops[at - 1] is not None and tops[at] < tops[at - 1]:
                return True
    return False


def _uncached(paragraph: Any) -> Any:
    """A copy of *paragraph* without its layout caches, its cells' paragraphs' among them."""

    copied = copy.deepcopy(paragraph)
    for cache in list(copied.iter(f"{HP}linesegarray")):
        cache.getparent().remove(cache)
    return copied


def _cell_row(measure: _Measure, table: Any, cell: Any, width: int | None = None) -> _Row:
    if _vertical(cell) or _size_protected(table) and _cell_height(cell.find(f"{HP}cellSz")):  # its lines go across
        # it, or its table is set not to change size (its text cut off below): the row as declared, one block, not split
        margins = cell_margins_of(cell, table)
        vertical = margins.top + margins.bottom
        height = max(_cell_height(cell.find(f"{HP}cellSz")), vertical)
        return _Row(height, 1, height - vertical, height - vertical, vertical, cell.get("header") == "1",
                    first=height - vertical)
    paragraphs = cell.findall(f"{HP}subList/{HP}p")
    if _split_before_text(paragraphs):  # the lines as Hancom drew them hold the parts: laid out anew
        paragraphs = [_uncached(paragraph) for paragraph in paragraphs]
    nested = _holds_table(cell)
    drawn: tuple[tuple[int, int], ...] = ()
    placed = [paragraph for paragraph in paragraphs if _placed_from(paragraph)
              or _holds_table(paragraph) and _table_alone(paragraph.findall(f"{HP}run")) is None]
    pieces = nested and bool(placed) and all(_table_pieces(measure, paragraph) is not None for paragraph in placed)
    size = cell.find(f"{HP}cellSz")
    margins = cell_margins_of(cell, table)
    inner = (int(size.get("width", 0)) if width is None else width) - margins.left - margins.right
    sub_list = cell.find(f"{HP}subList")
    squeezed = sub_list is not None and sub_list.get("lineWrap") in ("SQUEEZE", "KEEP")
    wrapped: tuple[tuple[int, int], ...] = ()
    wrapped_leads: tuple[int, ...] = ()
    reaches: tuple[_Reach, ...] = ()
    if nested and not pieces and any(_holds_table(paragraph) and _table_alone(paragraph.findall(f"{HP}run")) is None
                                     for paragraph in paragraphs):
        drawn, reaches = _drawn_lines(measure, paragraphs, cell=inner)  # among text, or not set as a character:
        # as Hancom drew it
        if not drawn and not all(_table_on_its_own(paragraph)
                                 or _table_before_text(paragraph.findall(f"{HP}run")) is not None
                                 or _objects_among(paragraph.findall(f"{HP}run"))  # laid out as in the body
                                 for paragraph in paragraphs
                                 if _holds_table(paragraph)
                                 and _table_alone(paragraph.findall(f"{HP}run")) is None):
            # placed top and bottom or square among or after the text, or in front of or behind it: clear of
            # it, as a picture so placed
            wrapped, wrapped_leads, reaches = ((), (), ()) if squeezed \
                else measure.wrapped_lines(paragraphs, inner, tables=True)
            if not wrapped:
                raise _Unsupported("a nested table")
    elif not pieces and any(_placed_from(paragraph) for paragraph in paragraphs):  # an object placed from a
        drawn = _drawn_lines(measure, paragraphs, inner)[0]  # paragraph: the lines as Hancom drew them, below it or
        # beside it
    if squeezed:  # never broken into lines:
        inner = _NO_WRAP  # each paragraph one line but for its line breaks, pressed into the cell when drawn
    # an object placed top and bottom or square from a paragraph without a layout cache: the lines clear of it
    if not (wrapped or drawn or nested or pieces or inner == _NO_WRAP):
        wrapped, wrapped_leads, _ = measure.wrapped_lines(paragraphs, inner)
    # Hancom starts the cell's first line below its first paragraph's spacing before (the lines as drawn
    # take that room already)
    before = 0 if drawn or not paragraphs else measure.shape(paragraphs[0].get("paraPrIDRef")).prev
    content, lines, pitch, char_size = measure.stack(paragraphs, inner, caches=True, floating=True, lead=before)
    if drawn:
        content, lines = sum(advance for _, advance in drawn[:-1]) + drawn[-1][0], len(drawn)
    elif wrapped:
        content, lines = before + sum(advance for _, advance in wrapped[:-1]) + wrapped[-1][0], len(wrapped)
    vertical = margins.top + margins.bottom
    height = max(_cell_height(size), vertical + content)
    first = drawn[0][0] if drawn else before + wrapped[0][0] if wrapped else \
        before + (measure.stack_lines(paragraphs[:1], inner, caches=True, pieces=pieces) or ((0, 0),))[0][0]
    several = not nested and len(paragraphs) > 1  # its lines split at their own places, spacing included
    metrics = (drawn or wrapped or measure.stack_lines(paragraphs, inner, caches=True, pieces=pieces)) \
        if nested or several else ()
    if nested and not (drawn or wrapped or pieces):
        reaches = _pushed_reaches(measure, paragraphs, inner, metrics)
    # its paragraphs, a table's among them, spaced apart (lines drawn as Hancom did hold their spacing already)
    spaced = several or nested and len(paragraphs) > 1 and not drawn
    leads = wrapped_leads if wrapped else _line_leads(measure, paragraphs, inner, pieces) \
        if spaced or before or pieces else ()
    if pieces and metrics:  # as tall as its lines and its tables' pieces: the caches of a cell Hancom split over a
        content = max(content, _lines_height(metrics, leads))  # page end hold its parts, each from the top
        height = max(height, vertical + content)
    return _Row(height, len(metrics) if pieces else lines, pitch, char_size, vertical,
                cell.get("header") == "1", spare=height - vertical - content, nested=nested, metrics=metrics,
                first=first, leads=leads if spaced or before or pieces else (), pieces=pieces, reaches=reaches,
                cuts=_line_cuts(measure, paragraphs, inner) if pieces else (),
                blocks=_line_blocks(measure, paragraphs, inner) if pieces else ())


def _table_first(measure: _Measure, obj: Any) -> int:
    """How far below its top a table's first row ends, its top outer margin and a caption above it included; 0 for
    an object that is not a table."""

    if _local(obj) != "tbl":
        return 0
    margin = obj.find(f"{HP}outMargin")
    rows = _rows(measure, obj)
    return (0 if margin is None else _margin(margin, "top")) + _caption(measure, obj)[0] + (rows[0].height if rows else 0)


def _split_rows(measure: _Measure, obj: Any) \
        -> tuple[int, tuple[tuple[int, int, int, int], ...], int, _FlowTable | None, tuple[tuple[int, int, int], ...]]:
    """How a table placed top and bottom in a cell may split over a page end: the room above its first row (its
    top outer margin and a caption above it), the pieces it splits into, and the room below its last row (a
    caption below it and its bottom outer margin). A piece is a row, or, split between lines (CELL), each
    line of a row of several, the first with the row's top cell margin, the last with its bottom one: its
    height, advance, the room it needs below it when a page ends after it (the bottom margin of a row going on)
    and the room above it when a page starts with it (the top margin of a row going on); rows joined by merged
    cells are a piece each, split cell by cell (see :func:`_block_rest`): last, the table and those rows (where
    the first's piece stands, the first and the last). No pieces for a table set not to split or not to be
    adjusted (``noAdjust``), with rows holding tables, or header rows it repeats, which is not followed."""

    margin = obj.find(f"{HP}outMargin")
    if _local(obj) != "tbl" or _page_break(obj) not in ("CELL", "TABLE") or obj.get("noAdjust") == "1":
        return 0, (), 0, None, ()
    rows, merged = _table_rows(measure, obj)
    if not rows or any(row.nested or row.header and obj.get("repeatHeader") == "1" for row in rows):
        return 0, (), 0, None, ()
    above, below = _caption(measure, obj)
    above += 0 if margin is None else _margin(margin, "top")
    below += 0 if margin is None else _margin(margin, "bottom")
    pieces: list[tuple[int, int, int, int]] = []
    blocks: list[tuple[int, int, int]] = []
    cells = [tr.find(f"{HP}tc") for tr in obj.findall(f"{HP}tr")]
    for index, (row, cell) in enumerate(zip(rows, cells)):
        if row.joined and not (index and rows[index - 1].joined):  # the first of rows joined by merged cells
            last = index
            while rows[last].joined and last + 1 < len(rows):
                last += 1
            blocks.append((len(pieces), index, last))
        joined = row.joined or index and rows[index - 1].joined
        lines = (row.metrics or ((row.size, row.pitch),) * row.lines) \
            if _page_break(obj) == "CELL" and not joined else ()
        if len(lines) < 2 or cell is None:
            pieces.append((row.height - (row.spare if index < len(rows) - 1 else 0), row.height, 0, 0))  # its text
            # fitting, the room it declares to spare under it is cut at the page end, as a flowing table's row's
            continue
        top = cell_margins_of(cell, obj).top
        bottom = row.margins - top
        last = row.height - top - sum(advance for _, advance in lines[:-1])
        pieces += [(top + lines[0][0], top + lines[0][1], bottom, 0)] \
            + [(height, advance, bottom, top) for height, advance in lines[1:-1]] + [(last, last, 0, top)]
    table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", _table_ends(obj), tuple(merged),
                       cut=_SPARE_CUT + below) if blocks else None
    return above, tuple(pieces), below, table, tuple(blocks)


def _pushed_reaches(measure: _Measure, paragraphs: list[Any], width: int,
                    metrics: tuple[tuple[int, int], ...]) -> tuple[_Reach, ...]:
    """Where the tables placed top and bottom before the text of a cell's paragraphs without a layout cache
    (see :meth:`_Measure.pushed_lines`) stand among the cell's lines *metrics* (see :class:`_Reach`): from the
    top of the paragraph's first line. Only those that may split between their rows (see :func:`_split_rows`):
    another goes on to the next page whole with the line below it, which is not checked against Hancom here."""

    reaches: list[_Reach] = []
    index = 0
    for paragraph in paragraphs:
        runs = paragraph.findall(f"{HP}run")
        obj = _object_before_text(runs, measure.headed(paragraph))
        if obj is not None and _local(obj) == "tbl" and measure.pushed_lines(paragraph, runs, width):
            count = len(measure.stack_lines([paragraph], width, caches=True))
            line = sum(advance for _, advance in metrics[:index])
            up = line + _down(obj.find(f"{HP}pos"))
            foot = up + _cell_extent(measure, obj)
            unit, text, y = None, 0, line  # the first line reaching it, which goes below it taking the room above
            for height, advance in metrics[index:index + count]:
                if y + height > up and y < foot:
                    unit, text = y, height - (foot - y)
                    break
                y += advance
            split = _split_rows(measure, obj)
            if split[1]:  # one that may not split goes on whole with its line, as it did before
                reaches.append(_Reach(line, up, foot, _table_first(measure, obj), unit, text, *split))
            index += count
            continue
        index += len(measure.stack_lines([paragraph], width, caches=True))
    return tuple(reaches)


def _line_leads(measure: _Measure, paragraphs: list[Any], width: int, pieces: bool = False) -> tuple[int, ...]:
    """The room above each line of *paragraphs* (as :meth:`_Measure.stack_lines` lays them out) when a part
    of their cell starts with it: a paragraph's spacing before at its first line, none at the others."""

    leads: list[int] = []
    for paragraph in paragraphs:
        prev = measure.shape(paragraph.get("paraPrIDRef")).prev
        split = _table_pieces(measure, paragraph) if pieces else None
        if split is not None:  # a table's: the room above each (a repeated header, a row's top margin)
            leads += [prev + split[1][0]] + list(split[1][1:])
            continue
        count = len(measure.stack_lines([paragraph], width, caches=True))
        leads += [prev] + [0] * (count - 1)
    return tuple(leads)


def _line_cuts(measure: _Measure, paragraphs: list[Any], width: int) -> tuple[int, ...]:
    """The room each line of *paragraphs* (as :meth:`_Measure.stack_lines` lays them out with tables' pieces)
    needs below it to stay above a page end: none for a line of text, a table's cut (101) for a piece of a
    table and its bottom margin under it but for the last (which holds it), as Hancom keeps a table's rows
    among a cell's text."""

    cuts: list[int] = []
    for paragraph in paragraphs:
        split = _table_pieces(measure, paragraph)
        if split is None:
            cuts += [0] * len(measure.stack_lines([paragraph], width, caches=True))
            continue
        table = next(child for run in paragraph.findall(f"{HP}run") for child in run if _local(child) == "tbl")
        below = _table_ends(table)[1]
        cuts += [_SPARE_CUT + below + room for room in split[3][:-1]] + [_SPARE_CUT]
    return tuple(cuts)


def _line_blocks(measure: _Measure, paragraphs: list[Any],
                 width: int) -> tuple[tuple[int, _FlowTable, int, int], ...]:
    """The rows joined by merged cells of the tables among the lines of *paragraphs* (as
    :meth:`_Measure.stack_lines` lays them out with tables' pieces): where the first's piece stands among those
    lines, the table, and its first and last row."""

    blocks: list[tuple[int, _FlowTable, int, int]] = []
    count = 0
    for paragraph in paragraphs:
        split = _table_pieces(measure, paragraph)
        if split is None:
            count += len(measure.stack_lines([paragraph], width, caches=True))
            continue
        table = next(child for run in paragraph.findall(f"{HP}run") for child in run if _local(child) == "tbl")
        rows, cells = _table_rows(measure, table)
        flowing = _FlowTable(rows, _page_break(table), table.get("repeatHeader") == "1", _table_ends(table),
                             tuple(cells), cut=_spare_cut(table))
        first = 0
        while first < len(rows):
            last = first
            while rows[last].joined and last + 1 < len(rows):
                last += 1
            if last > first:
                blocks.append((count + split[2][first], flowing, first, last))
            first = last + 1
        count += len(split[0])
    return tuple(blocks)


def _table_pieces(measure: _Measure, paragraph: Any) \
        -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]] | None:
    """How a table placed top and bottom on its own in a cell paragraph, from the paragraph's top, splits with
    its row over a page end: (height, advance) of each piece and the room above each when a part of the cell
    starts with it. Hancom splits such a table between its rows, one moved row by row (TABLE) as well as one
    split between lines (CELL), which splits a row of several lines between them too, the row's cell
    margins around each part; its top outer margin and a repeated header go above each part but the first.
    ``None`` for any other
    paragraph, and for a table set not to split (NONE), offset down, with a caption, or with rows holding
    tables that do not split so (a row holding one that does splits between its pieces as between lines, and
    one holding tables set as characters between its lines, a table one, as in the body).
    Rows joined by merged cells are a piece each (see :func:`_line_blocks`). Third: where each row's first
    piece stands among the pieces; fourth: the room each needs below it when a page ends after it (the bottom
    margin of a row going on)."""

    if not _table_on_its_own(paragraph):
        return None
    table = next(child for run in paragraph.findall(f"{HP}run") for child in run if _local(child) == "tbl")
    mode = _page_break(table)
    if mode not in ("CELL", "TABLE") or _down(table.find(f"{HP}pos")) or table.find(f"{HP}caption") is not None:
        return None
    rows = _rows(measure, table)
    cells = [tr.find(f"{HP}tc") for tr in table.findall(f"{HP}tr")]
    if len(rows) != len(cells) or any(row.nested and not (row.pieces or row.metrics and not row.reaches)
                                      for row in rows):
        return None
    header = sum(row.height for row in rows if row.header) if table.get("repeatHeader") == "1" else 0
    margin = table.find(f"{HP}outMargin")
    above, below = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
    pieces: list[tuple[int, int]] = []
    leads: list[int] = []
    starts: list[int] = []
    rooms: list[int] = []
    for index, (row, cell) in enumerate(zip(rows, cells)):
        starts.append(len(pieces))
        lead = 0 if row.header or not pieces else above + header  # a part going on: below its top margin again
        joined = row.joined or index and rows[index - 1].joined
        lines = (row.metrics or ((row.size, row.pitch),) * row.lines) if mode == "CELL" and not joined else ()
        if len(lines) < 2:
            pieces.append((row.height - (row.spare if index < len(rows) - 1 else 0), row.height))  # room to spare
            # under its text cut at the page end (see _split_rows)
            leads.append(lead)
            rooms.append(0)
            continue
        margins = cell_margins_of(cell, table)
        top = margins.top
        last = row.height - top - sum(advance for _, advance in lines[:-1])  # its foot, its room to spare
        pieces += [(top + lines[0][0], top + lines[0][1])] + list(lines[1:-1]) + [(last, last)]
        leads += [lead] + [lead + top] * (len(lines) - 1)
        rooms += [margins.bottom + (row.cuts[line] if row.cuts else 0)  # a part of the row ending there: its
                  for line in range(len(lines) - 1)]  # bottom margin under it, and what its own tables keep
        rooms.append(0)
        continue
    pieces[0] = (pieces[0][0] + above, pieces[0][1] + above)
    pieces[-1] = (pieces[-1][0] + below, pieces[-1][1] + below)
    return tuple(pieces), tuple(leads), tuple(starts), tuple(rooms)


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
    stays: bool = False       # that object does not flow with the text (pos@flowWithText="0")


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
    #: for each object anchored here and placed on the paper or the page: (top, bottom) in the body, whether it
    #: leaves a line's room beside it and the columns it reaches over (see :func:`_paper_bands`)
    paper: tuple[tuple[int, int, bool, tuple[int, ...]], ...] = ()
    #: the top of such a band that pushes the lines below it to the body's foot and that keeps the object on its
    #: paragraph's page (pos@holdAnchorAndSO="1"): when the first line with its spacing reaches it there, the
    #: paragraph goes on to the next page's top with the object, the lines above staying where they are
    held: int | None = None
    #: in columns of unequal width, a paragraph without a layout cache: its text, to break again
    reflow: _Reflow | None = None
    #: holding nothing, in a section hiding a page's first empty lines (see :meth:`_Paginator._paragraph`)
    hides: bool = False
    #: its lines are Hancom's own, from the paragraph's valid layout cache
    kept: bool = False
    #: the step of the line grid its lines snap to (see :func:`_on_grid`), 0 for none
    grid: int = 0
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
    #: holding nothing but a top-and-bottom object offset down from it (see :func:`_pushing_object`): its empty
    #: line stays where it is beside the object's band, which only the lines after reaching it go below
    bare: bool = False
    #: a top-and-bottom object offset from this paragraph (not a flowing table) pushes its lines below it:
    #: when its band would pass the body's foot, Hancom moves it to the next page's top instead
    wrap_push: bool = False
    #: how far such an object pushed the paragraph's first line down (its band's foot is measured from where
    #: that line stood before)
    wrap_shift: int = 0
    #: how far an earlier paragraph's top-and-bottom object pushed this paragraph's first line down (part of
    #: :attr:`prev`): going on to the next page, the line drops it and starts at that page's top
    lead: int = 0
    #: a table wrapped square anchored here, flowing with the text and allowed to split, that goes on over the
    #: page end: it as it flows, how far below the paragraph's first line it starts, and its band beside the
    #: text (see :meth:`_Paginator._span_bands`)
    spans: tuple[_FlowTable, int, _Wrap] | None = None
    #: such an object alone in this empty paragraph, its foot this far below the paragraph's top (the line is
    #: as tall as that): past the body's foot it goes on to the next page's top, the empty line staying when
    #: it fits there (*own* tall)
    moves: int = 0
    own: int = 0
    #: a top-and-bottom object alone in this empty paragraph, its foot this far below the line's top: the next
    #: paragraph starts no higher, but its spacing and this one's count only where the empty line's own advance
    #: with them reaches lower (Hancom's empty line stays beside the object, which the next line goes below)
    floor: int = 0
    #: a top-and-bottom object alone in this empty paragraph placed up from its top: (how far up, as a negative
    #: offset, how tall, and the paragraph's own line and advance) -- see :meth:`_Paginator._below_a_rising_object`
    rises: tuple[int, int, int, int] | None = None
    #: a flowing table alone in this empty paragraph, allowed to overlap and starting on the line: the line goes
    #: below it (see :meth:`_Paginator._flow`)
    under: bool = False

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
            if mixed or looks is not None or self.shape.font_line else ()
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
    #: a top-and-bottom object at its paragraph's top (offset 0) past the body's foot goes on to the next page's
    #: top alone, its paragraph's lines staying (off: with its paragraph, see :func:`_lay_section`)
    alone_at_top: bool = True


def _page(section: Any) -> _Page:
    page = next(section.iter(f"{HP}pagePr"), None)
    margin = page.find(f"{HP}margin") if page is not None else None
    if margin is None:
        raise _Unsupported("no page settings")
    width, height = _drawn_page_size(int(page.get("width", 0)), int(page.get("height", 0)), page.get("landscape"))
    # A negative margin is kept as an unsigned 32-bit number: Hancom reads it signed, the body growing by it.
    sides = {key: _page_margin(margin.get(key, 0), key) for key in ("top", "bottom", "header", "footer", "left",
                                                                   "right", "gutter")}
    body = height - sides["top"] - sides["bottom"] - sides["header"] - sides["footer"]
    text_width = width - sides["left"] - sides["right"] - sides["gutter"]
    if body <= 0 or text_width <= 0:
        raise _Unsupported("page margins leaving no room for the body")
    columns, column_width, widths, gap = _columns(section, text_width)
    visibility = next(section.iter(f"{HP}visibility"), None)
    return _Page(body, column_width, columns, sides["top"] + sides["header"],
                 sides["left"] + sides["gutter"], text_width, width, bool(widths),
                 widths, height,
                 visibility is not None and visibility.get("hideFirstEmptyLine") in ("1", "true"), gap)


def _columns(section: Any, text_width: int) -> tuple[int, int, tuple[int, ...], int]:
    """(count, width, widths, gap): the section's columns (its first ones when they change inside it, see
    :func:`_column_areas`), their width (the narrowest when they differ), when they differ each one's, and when
    they do not the gap between them."""

    return _column_layout(_first_columns(section), text_width)


def _first_columns(section: Any) -> Any:
    # Column settings in a cell or a text box (an hp:subList) belong to that list, not the section.
    return next((cols for cols in section.iter(f"{HP}colPr") if not _in_sub_list(cols)), None)


def _true(value: Any) -> bool:
    """Whether an ``xs:boolean`` attribute *value* is true: ``1`` or ``true`` (Hancom writes ``1``)."""

    return value in ("1", "true")


def _column_layout(settings: Any, text_width: int) -> tuple[int, int, tuple[int, ...], int]:
    """:func:`_columns` of the column settings *settings* (``hp:colPr``; ``None``: one column)."""

    count = int(settings.get("colCount", "1")) if settings is not None else 1
    if count <= 1:  # one column as several: its width rounded down to whole layout units of 4
        width = text_width // 4 * 4
        if width <= 0:
            raise _Unsupported("column width leaving no room for the body")
        return 1, width, (), 0
    if not _true(settings.get("sameSz")):  # each column takes its share of 32768 of the text width (hp:colSz),
        sizes = settings.findall(f"{HP}colSz")  # rounded, whatever the shares add up to
        total = sum(int(size.get("width", 0)) + int(size.get("gap", 0)) for size in sizes)
        if len(sizes) != count or total <= 0:
            raise _Unsupported("columns of unequal width")
        widths = tuple((2 * int(size.get("width", 0)) * text_width + COLUMN_SHARES) // (2 * COLUMN_SHARES)
                       for size in sizes)
        return count, min(widths), widths, 0
    gap = int(settings.get("sameGap", 0))
    if gap >= 1 << 31:  # a signed 32-bit number written unsigned: Hancom takes a negative gap so
        gap -= 1 << 32
    return count, (text_width - (count - 1) * gap) // count // 4 * 4, (), gap


def _in_sub_list(element: Any) -> bool:
    return any(_local(ancestor) == "subList" for ancestor in element.iterancestors())


def _caption(measure: _Measure, table: Any) -> tuple[int, int]:
    """How much room a table's (or another object's) caption takes above it and below it: its first
    paragraph's spacing before (Hancom starts the caption's first line below it), its lines and its gap (a
    caption beside the object takes none)."""

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
    return _rows_height(measure, table)


def _rows_height(measure: _Measure, table: Any) -> int:
    """How tall a table's rows make it: the rows (see :func:`_rows`, each with the cell spacing above it) and
    the spacing below the last."""

    return sum(row.height for row in _rows(measure, table)) + _cell_spacing(table)


@dataclass(frozen=True)
class _NoteShape:
    above: int = 0     # hp:noteSpacing@aboveLine
    line: int = 0      # the separator's width
    below: int = 0     # hp:noteSpacing@belowLine
    between: int = 0   # hp:noteSpacing@betweenNotes
    section_end: bool = False  # endnotes placed at each section's end (hp:placement@place END_OF_SECTION)

    def area(self, height: int, count: int) -> int:
        return 0 if count == 0 else self.above + self.line + self.below + height + self.between * (count - 1)


def _note_shape(section: Any, kind: str = "footNotePr") -> _NoteShape:
    """The note area of the section's footnotes (or, with *kind* ``endNotePr``, of its endnotes). Footnotes right
    beneath the text (``hp:placement@beneathText``) take the same room on their page as at its foot."""

    settings = next(section.iter(f"{HP}{kind}"), None)
    if settings is None:
        return _NoteShape()
    placement = settings.find(f"{HP}placement")
    place = placement.get("place", "END_OF_DOCUMENT") if placement is not None else "END_OF_DOCUMENT"
    if kind == "endNotePr" and place not in {"END_OF_DOCUMENT", "END_OF_SECTION"}:
        raise _Unsupported("endnotes placed otherwise than at the document's or the section's end")
    spacing = settings.find(f"{HP}noteSpacing")
    rule = settings.find(f"{HP}noteLine")
    millimetres = float((rule.get("width", "0 mm") if rule is not None else "0 mm").split()[0])

    def value(name: str) -> int:
        return int(spacing.get(name, 0)) if spacing is not None else 0

    return _NoteShape(value("aboveLine"), round(millimetres * 7200 / 25.4), value("belowLine"), value("betweenNotes"),
                      kind == "endNotePr" and place == "END_OF_SECTION")


#: The namespaces an hp:case Hancom Office 2024 lays out requires: the 2016 chart one (a chart, whose hp:default
#: holds the OLE object standing for it in older readers).
_CASE_NAMESPACES = frozenset({"http://www.hancom.co.kr/hwpml/2016/ooxmlchart"})


def _switched(section: Any) -> list[Any]:
    """The hp:switch elements of *section*'s runs holding an object (Hancom saves every chart in one)."""

    return [switch for switch in section.iter(f"{HP}switch")
            if _local(switch.getparent()) == "run" and any(
                _local(child) in _OBJECTS for branch in switch for child in branch)]


def _unswitched(section: Any) -> Any:
    """*section*, or a copy of it in which each run's hp:switch holding an object gives way to the branch Hancom
    lays out: its hp:case requiring a namespace Hancom knows (a chart), else its hp:default."""

    if not _switched(section):
        return section
    section = copy.deepcopy(section)
    for switch in _switched(section):
        branch = next((case for case in switch.findall(f"{HP}case")
                       if case.get(f"{HP}required-namespace") in _CASE_NAMESPACES), switch.find(f"{HP}default"))
        run = switch.getparent()
        at = list(run).index(switch)
        for child in reversed(list(branch) if branch is not None else []):
            run.insert(at, child)
        run.remove(switch)
    return section


def _check_section(measure: _Measure, section: Any, page: _Page) -> None:
    paragraphs = section.findall(f"{HP}p")
    grid = next(section.iter(f"{HP}grid"), None)
    if grid is not None and (_grid_step(grid, "lineGrid") or _grid_step(grid, "charGrid")):
        if page.columns != 1 or _column_areas(section) or any(map(_holds_object, paragraphs)):
            raise _Unsupported("a line or character grid in columns or with objects, tables or notes")
        # a character grid widens each character to whole steps: FormFit does not break lines so
        if _grid_step(grid, "charGrid") and not all(_cached_metrics(paragraph) for paragraph in paragraphs):
            raise _Unsupported("a character grid in a paragraph without a layout cache")
    # Each later paragraph holding section settings starts a section of its own (see :func:`_section_parts`);
    # settings deeper in a paragraph are not followed.
    if any(next(paragraph.iter(f"{HP}secPr"), None) is not None for paragraph in paragraphs[1:]):
        raise _Unsupported("section settings (hp:secPr) after the first paragraph")


def _grid_step(grid: Any, name: str) -> int:
    """The step of the section's line or character grid (``hp:grid@lineGrid``, ``@charGrid``), in HWPUNIT; 0 for
    none."""

    return max(0, int(grid.get(name, 0) or 0)) if grid is not None else 0


def _holds_object(paragraph: Any) -> bool:
    """Whether a body paragraph holds an object, a table or a note."""

    return any(_local(child) in _OBJECTS or _local(child) == "ctrl" and any(
        _local(item) in {"footNote", "endNote"} for item in child) for run in paragraph.findall(f"{HP}run")
        for child in run)


def _on_grid(para: _Para, step: int) -> _Para:
    """*para* on a line grid *step* apart, in a paragraph snapping to it (``hh:paraPr@snapToGrid``): its first
    line goes to the first step at or below where it would go, and each line's height, its advance (its height
    with its spacing) and the paragraph's spacing before and after each take whole steps, rounded up (a line stays
    on its page while its top and rounded height are above the body's foot)."""

    def up(value: int) -> int:
        return -(-value // step) * step if value > 0 else value

    return replace(para, size=up(para.size), pitch=up(para.pitch), prev=up(para.prev), next=up(para.next), grid=step,
                   cached=tuple((up(height), up(advance)) for height, advance in para.cached))


#: The section settings Hancom lays out the paragraphs before a section's first settings with (its first paragraph
#: holding none, a later one some): its default A4 page (59528 x 84188) and margins, one column, its default notes.
_DEFAULT_SECTION = (
    f'<hp:secPr xmlns:hp="{HP[1:-1]}"><hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>'
    '<hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY"><hp:margin header="4252" '
    'footer="4252" gutter="0" left="8504" right="8504" top="5668" bottom="4252"/></hp:pagePr><hp:footNotePr>'
    '<hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="283" '
    'belowLine="567" aboveLine="850"/><hp:placement place="EACH_COLUMN" beneathText="0"/></hp:footNotePr>'
    '<hp:endNotePr><hp:noteLine length="14692344" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing '
    'betweenNotes="0" belowLine="567" aboveLine="850"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/>'
    '</hp:endNotePr></hp:secPr>'
)


def _section_settings(paragraph: Any) -> Any:
    return paragraph.find(f"{HP}run/{HP}secPr")


def _tab_stop(section: Any) -> int | None:
    """How far apart (HWPUNIT) *section*'s default tab stops are, from the column's left edge
    (``hp:secPr@tabStopVal``): Hancom's 4,000 when it gives none, None when it gives them in another unit."""

    settings = next(section.iter(f"{HP}secPr"), None)
    value = settings.get("tabStopVal") if settings is not None else None
    if value is None:
        return _DEFAULT_TAB_STOP
    if settings.get("tabStopUnit", "HWPUNIT") != "HWPUNIT" or not value.isdigit() or not int(value):
        return None
    return int(value)


def _section_parts(measure: _Measure, section: Any) -> list[Any]:
    """*section* as the sections Hancom lays it out as: a paragraph after its first holding section settings
    (``hp:secPr`` in a run) starts a new section there, on a new page, with those settings (Hancom saves it as a
    section of its own), and when the first paragraph holds none, the paragraphs before go on Hancom's default
    page (:data:`_DEFAULT_SECTION`). The parts are copies, their paragraphs labelled as the originals; *section*
    itself when there is one part."""

    paragraphs = section.findall(f"{HP}p")
    starts = [index for index, paragraph in enumerate(paragraphs)
              if index and _section_settings(paragraph) is not None]
    if not starts:
        return [section]
    parts, copies = [], {}
    for first, end in zip([0, *starts], [*starts, len(paragraphs)]):
        part = section.makeelement(section.tag, section.attrib, section.nsmap)
        for paragraph in paragraphs[first:end]:
            duplicate = copy.deepcopy(paragraph)
            copies.update(zip(duplicate.iter(f"{HP}p"), paragraph.iter(f"{HP}p")))
            part.append(duplicate)
        parts.append(part)
    if _section_settings(paragraphs[0]) is None:
        lead = parts[0][0]
        run = lead.find(f"{HP}run")
        if run is None:
            run = lead.makeelement(f"{HP}run", {})
            lead.insert(0, run)
        run.insert(0, etree.fromstring(_DEFAULT_SECTION))
    measure.copied(copies)
    return parts


def _objects_reach(runs: list[Any], measure: _Measure) -> int:
    """How far below the top of their paragraph in a cell, holding no text, the pictures and drawings placed
    from it reach: top and bottom or square, not set as a character, moving with the text, their outer margins
    included (the cell holds them, and its row grows to; one that stays put does not count). So do the tables
    placed top and bottom from it, as tall as their rows and a caption above or below them (one placed up
    stands at the paragraph's top)."""

    reach = 0
    if _run_text(runs).strip():  # text goes on below such an object: not followed here
        return reach
    for obj in (child for run in runs for child in run):
        name, pos = _local(obj), obj.find(f"{HP}pos")
        if name == "tbl" and _placed_top_and_bottom(obj):
            reach = max(reach, _down(pos) + _inline_table_height(measure, obj) + _extent_margins(obj)
                        + sum(_caption(measure, obj)))
            continue
        if name not in _OBJECTS or name == "tbl" or pos is None or obj.find(f"{HP}sz") is None \
                or pos.get("treatAsChar") == "1" or obj.get("textWrap") not in ("TOP_AND_BOTTOM", "SQUARE") \
                or pos.get("flowWithText") == "0" or pos.get("vertRelTo") != "PARA" \
                or pos.get("vertAlign", "TOP") != "TOP":
            continue
        reach = max(reach, _down(pos) + _extent(obj, "height", measure))  # one placed up stands at the top
    return reach


def _floating_reach(runs: list[Any], measure: _Measure) -> int:
    """How far below the top of their paragraph in a cell the pictures and drawings in front of or behind the
    text placed from it reach, when they move with the text (pos@flowWithText not "0"), their outer margins
    included: they push no line aside, but the cell grows to hold them. One that stays put does not."""

    reach = 0
    for obj in (child for run in runs for child in run):
        pos = obj.find(f"{HP}pos")
        if _local(obj) not in _OBJECTS or _local(obj) == "tbl" or pos is None or obj.find(f"{HP}sz") is None                 or not _floating(obj) or pos.get("flowWithText") == "0" or pos.get("vertRelTo") != "PARA"                 or pos.get("vertAlign", "TOP") != "TOP":
            continue
        reach = max(reach, _down(pos) + _extent(obj, "height", measure))  # one placed up stands at the top
    return reach


def _wraps_in_cell(obj: Any, tables: bool = False) -> bool:
    """A picture or drawing (with *tables*, a table too) placed top and bottom or square from the top of its
    paragraph, not set as a character, that moves with the text: in a cell, one that stays put
    (pos@flowWithText="0") pushes no line aside and leaves the row as it is."""

    pos = obj.find(f"{HP}pos")
    return _local(obj) in _OBJECTS and (tables or _local(obj) != "tbl") and pos is not None \
        and obj.find(f"{HP}sz") is not None \
        and pos.get("treatAsChar") != "1" and obj.get("textWrap") in ("TOP_AND_BOTTOM", "SQUARE") \
        and pos.get("flowWithText") != "0" and pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"


def _cell_extent(measure: _Measure, obj: Any) -> int:
    """How tall an object placed from a cell paragraph stands, its outer margins included: a table as its rows
    (see :func:`_inline_table_height`) with a caption above or below it (its lines and its gap; one beside it is
    not followed), anything else as Hancom draws it."""

    if _local(obj) != "tbl":
        return _extent(obj, "height", measure)
    caption = obj.find(f"{HP}caption")
    if caption is not None and caption.get("side") not in ("TOP", "BOTTOM"):
        raise _Unsupported("a table in a cell with a caption beside it")
    return _inline_table_height(measure, obj) + _extent_margins(obj) + sum(_caption(measure, obj))


def _control_place(runs: list[Any], obj: Any) -> int:
    """How many characters of the paragraph's text come before *obj*'s control."""

    place = 0
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t":
            place += len(_t_text(child))
    return place


def _cell_band(measure: _Measure, obj: Any, top: int, width: int) -> tuple[int, int, int | None]:
    """The band an object wrapped in a cell *width* wide (see :func:`_wraps_in_cell`) placed from *top* takes:
    its top and foot, its outer margins included, and the room beside it, ``None`` when it pushes the lines
    below it (top and bottom, or less than 1440 beside it). Placed from the paragraph's or the column's left or
    right, it stands from the cell's text area's."""

    pos = obj.find(f"{HP}pos")
    up = top + _down(pos)  # one placed up stands at that top
    foot = up + _cell_extent(measure, obj)
    if _wraps_top_and_bottom(obj, width):
        return up, foot, None
    if pos.get("horzRelTo") not in ("PARA", "COLUMN") or pos.get("horzAlign") not in ("LEFT", "RIGHT") \
            or obj.get("textFlow", "BOTH_SIDES") not in ("BOTH_SIDES", "LARGEST_ONLY", "LEFT_ONLY", "RIGHT_ONLY"):
        raise _Unsupported(f"{_local(obj)} wrapped square elsewhere than at a cell's edge")
    wide, offset = _extent(obj, "width"), _pos_offset(pos, "horzOffset")
    if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
        offset -= 1 << 32
    start = offset if pos.get("horzAlign") == "LEFT" else width - wide - offset
    left, right = start, width - start - wide
    flow = obj.get("textFlow", "BOTH_SIDES")
    if flow == "LARGEST_ONLY":
        flow = "LEFT_ONLY" if left > right else "RIGHT_ONLY"
    left = left if left >= _MIN_SIDE and flow != "RIGHT_ONLY" else 0
    right = right if right >= _MIN_SIDE and flow != "LEFT_ONLY" else 0
    if left and right:
        raise _Unsupported(f"text on both sides of {_local(obj)} wrapped square in a cell")
    return up, foot, (left or right) or None


def _clear_of(measure: _Measure, metrics: list[tuple[int, int]], top: int, prev: int, anchor: int, obj: Any,
              bands: list[tuple[int, int, int | None]], empty: bool, width: int
              ) -> tuple[list[tuple[int, int, int]], dict[int, int], tuple[int, int, int | None] | None]:
    """(top, height, advance) of each line of a cell paragraph whose lines are *metrics* (height, advance), its
    first line's top *top* below its spacing before *prev*, laid out clear of the *bands* of the objects above
    and of the band of its own object *obj* (see :func:`_cell_band`), whose control is on line *anchor*: a
    line reaching a band with no room beside it goes below its foot, and one in a square object's band takes
    the room beside it (returned by the line's index), as does *obj*'s band. An *empty* paragraph's line stays
    beside its own object when that may not overlap the text (pos@allowOverlap="0")."""

    placed: list[tuple[int, int, int]] = []
    narrow: dict[int, int] = {}
    own = None
    for index, (height, advance) in enumerate(metrics):
        y = placed[-1][0] + placed[-1][2] if placed else top
        if obj is not None and index == anchor:
            own = _cell_band(measure, obj, y - (prev if index == 0 else 0), width)
        stays = own if empty and index == 0 and obj is not None \
            and obj.find(f"{HP}pos").get("allowOverlap") == "0" else None
        around = [*bands, *(() if own is None else (own,))]
        moved = True
        while moved:
            moved = False
            for band in around:
                if band is not stays and band[2] is None and y < band[1] and y + height > band[0]:
                    y, moved = band[1], True
        beside = [band[2] for band in around if band[2] is not None and y < band[1] and y + height > band[0]]
        if beside:
            narrow[index] = min(beside)
        placed.append((y, height, advance))
    return placed, narrow, own


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


def _below_the_band(measure: _Measure, runs: list[Any], wrap: _Wrap) -> bool:
    """Whether every line of a paragraph goes below the band of a square-wrapped object anchored before it
    (*wrap*, as the paragraph sees it): its one object placed top and bottom from its top before its text,
    which Hancom sets at its own offset whatever the band (drawn over it), reaches its first line, which goes
    below it with the lines after, and its foot is no higher than the band's."""

    obj = _object_before_text(runs)
    if obj is None:
        return False
    offset = _down(obj.find(f"{HP}pos"))
    if offset >= _text_size(measure, runs)[0]:  # the first line stands above it
        return False
    tall = _extent(obj, "height", measure)
    if _local(obj) == "tbl":  # as tall as its rows
        tall += sum(row.height for row in _rows(measure, obj)) - int(obj.find(f"{HP}sz").get("height", 0))
    return offset + tall >= wrap.bottom


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
    """A top-and-bottom object placed from the top or the bottom of the paper or of the page, or centred on it,
    not set as a character: it takes no room in its paragraph but keeps every line of its page out of its band.
    One wrapped square there counts as well (see :func:`_paper_band`)."""

    pos = obj.find(f"{HP}pos")
    return (pos is not None and pos.get("treatAsChar") != "1" and obj.get("textWrap") in ("TOP_AND_BOTTOM", "SQUARE")
            and pos.get("vertRelTo") in ("PAPER", "PAGE")
            and pos.get("vertAlign", "TOP") in ("TOP", "CENTER", "BOTTOM"))


def _paper_band(measure: _Measure, page: _Page, paragraph: Any) -> tuple[int, int, bool, tuple[int, ...]] | None:
    """The band of the first object of *paragraph* placed on the paper, if any (see :func:`_paper_bands`)."""

    bands = _paper_bands(measure, page, paragraph)
    return bands[0] if bands else None


def _paper_bands(measure: _Measure, page: _Page, paragraph: Any) -> tuple[tuple[int, int, bool, tuple[int, ...]], ...]:
    """For each object of *paragraph* placed on the paper, each on its own as if anchored apart: (top, bottom) in
    the body, whether it is wrapped square leaving a line's room beside it (Hancom sets the text reaching it
    beside it, which is not followed, and the text above or below it as if it were not there), and the columns
    it keeps the lines out of."""

    return tuple(_object_paper_band(measure, page, child) for run in paragraph.findall(f"{HP}run") for child in run
                 if _local(child) in _OBJECTS and _on_paper(child))


def _object_paper_band(measure: _Measure, page: _Page, obj: Any) -> tuple[int, int, bool, tuple[int, ...]]:
    """The band of *obj*, placed on the paper (see :func:`_paper_bands`)."""

    square = obj.get("textWrap") == "SQUARE"  # no line beside it: less than a line's room on each side
    across = _across_the_text(obj, page, _MIN_SIDE - 1 if square else 0)
    columns = tuple(range(page.columns)) if across or page.columns == 1 else () if square \
        else _columns_reached(obj, page)
    if not columns:
        raise _Unsupported("objects placed on the paper")
    tall = _extent(obj, "height", measure)
    if _local(obj) == "tbl":  # as tall as its rows
        tall += _rows_height(measure, obj) - int(obj.find(f"{HP}sz").get("height", 0))
    pos = obj.find(f"{HP}pos")
    offset = _pos_offset(pos, "vertOffset")
    align = pos.get("vertAlign", "TOP")
    height, base = (page.body, 0) if pos.get("vertRelTo") == "PAGE" else (page.paper_height, -page.top)
    if align == "CENTER":  # centred, then moved down by the offset (up when negative, kept unsigned)
        top = (height - tall) // 2 + (offset - (1 << 32) if offset >= 1 << 31 else offset) + base
    else:  # from the body's (the paper's) top or foot
        top = (offset if align == "TOP" else height - offset - tall) + base
    return top, top + tall, square and not across, columns


def _held_top(page: _Page, paragraph: Any, band: tuple[int, int, bool, tuple[int, ...]]) -> int | None:
    """The top of *band*, the band of *paragraph*'s object placed on the paper or the page, when it pushes the
    lines reaching it below the body's foot and the object keeps to its paragraph's page (see
    :attr:`_Para.held`) -- in one column only; otherwise ``None``."""

    top, bottom, room, _ = band
    obj = next(child for run in paragraph.findall(f"{HP}run") for child in run
               if _local(child) in _OBJECTS and _on_paper(child))
    if room or page.columns != 1 or bottom < page.body or obj.find(f"{HP}pos").get("holdAnchorAndSO") != "1":
        return None
    return top


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
    width, offset = _extent(obj, "width"), _pos_offset(pos, "horzOffset")
    return {"LEFT": offset, "CENTER": (page.paper_width - width) // 2 + offset,
            "RIGHT": page.paper_width - width - offset}.get(pos.get("horzAlign", "LEFT"))


def _floating(obj: Any) -> bool:
    """An object in front of or behind the text, not set as a character: the text flows as if it were not
    there."""

    pos = obj.find(f"{HP}pos")
    return obj.get("textWrap") in _FLOATING and (pos is None or pos.get("treatAsChar") != "1")


def _text_size(measure: _Measure, runs: list[Any], paragraph: Any = None) -> tuple[int, list[Any], list[int]]:
    """The paragraph's character size (its smallest), the character shapes of its runs holding text
    (the style comes from the first), and each character's size. An empty run takes no room; a paragraph
    without text is as tall as the largest of its runs holding controls or objects and its last run, and,
    given the *paragraph*, as the number label Hancom draws for it (in its own character shape; a bullet's
    takes the paragraph's end's, see :meth:`_Measure.label_size`)."""

    lengths = [sum(len(_t_text(text)) for text in run.findall(f"{HP}t")) for run in runs]
    refs = [run.get("charPrIDRef") for run, length in zip(runs, lengths) if length]
    refs = refs or [run.get("charPrIDRef") for run in runs if run.find(f"{HP}t") is not None]
    refs = refs or [run.get("charPrIDRef") for run in runs] or ["0"]
    sizes: list[int] = []
    for run, length in zip(runs, lengths):
        sizes += [measure.char_height(run.get("charPrIDRef"))] * length
    if not sizes and runs:  # no text: as tall as its runs holding controls or objects, and its end (the last run)
        held = [run.get("charPrIDRef") for run in runs[:-1] if any(child.tag != f"{HP}t" for child in run)]
        tall = max(measure.char_height(ref) for ref in [*held, runs[-1].get("charPrIDRef")])
        if paragraph is not None and measure.headed(paragraph):
            tall = max(tall, measure.label_size(paragraph.get("paraPrIDRef"), runs[-1].get("charPrIDRef")))
        return tall, refs, sizes
    return min(sizes or [measure.char_height(ref) for ref in refs]), refs, sizes


def _end_size(measure: _Measure, runs: list[Any], sizes: list[int]) -> int:
    """The size the paragraph's end gives its last line: an empty run ending a paragraph with text makes that
    line as tall as itself when it is larger than the line's text, whatever the lines before it hold (an empty
    run before the text does not); 0 when it is no larger than any character."""

    if not runs or not sizes or any(len(child) or child.tag != f"{HP}t" or child.text for child in runs[-1]):
        return 0
    size = measure.char_height(runs[-1].get("charPrIDRef"))
    return size if size > min(sizes) else 0


def _end_ref(paragraph: Any) -> Any:
    """The character shape of a paragraph's end: its last run's, or None without runs."""

    runs = paragraph.findall(f"{HP}run")
    return runs[-1].get("charPrIDRef") if runs else None


def _head_size(measure: _Measure, paragraph: Any, sizes: list[int]) -> int:
    """The size a bullet or number label (in its own character shape, or without one in that of the
    paragraph's end), or a run holding nothing but controls before the text (a section's or columns'
    definition, a page number: an empty run takes no room) or an object not set as a character, gives its
    paragraph's first line: a character of that size there (it counts when it is larger than the smallest
    character); 0 when not."""

    if not sizes:
        return 0
    size = measure.label_size(paragraph.get("paraPrIDRef"), _end_ref(paragraph))
    for run in paragraph.findall(f"{HP}run"):
        if any(child.text or len(child) for child in run.findall(f"{HP}t")):  # the text starts
            break
        if run.find(f"{HP}ctrl") is not None or run.find(f"{HP}secPr") is not None or any(
                _local(child) in _OBJECTS and (child.find(f"{HP}pos") is None
                                              or child.find(f"{HP}pos").get("treatAsChar") != "1")
                for child in run):
            size = max(size, measure.char_height(run.get("charPrIDRef")))
    return size if size > min(sizes) else 0


def _held_sizes(measure: _Measure, runs: list[Any], sizes: list[int]) -> dict[int, int]:
    """Where in the text a run holding a control shown on a line (see :func:`_shown_control`; not a note) or an
    object not set as a character stands after the first character -> that run's size, when it is larger than the
    smallest character: Hancom sets it as a character of no width, the line it falls on as tall as its run's
    characters (those before the text, see :func:`_head_size`)."""

    if not sizes:
        return {}
    place, held = 0, {}
    for run in runs:
        for child in run:
            name = _local(child)
            if name == "t":
                place += len(_t_text(child))
            elif place and (_shown_control(child) and not any(_local(kind) in ("footNote", "endNote") for kind in child)
                            or name in _OBJECTS and (child.find(f"{HP}pos") is None
                                                     or child.find(f"{HP}pos").get("treatAsChar") != "1")):
                size = measure.char_height(run.get("charPrIDRef"))
                if size > min(sizes):
                    held[place] = max(held.get(place, 0), size)
    return held


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


def _line_sizes(measure: _Measure, sizes: list[int], style: Any, styles: list[Any] | None, shape: _Shape) -> list[int]:
    """Each character's size as its line's height counts it: the size, or in a paragraph taking its line height
    from the font (``fontLineHeight``) the height the character's face gives a line of that size."""

    if not shape.font_line:
        return sizes
    return [measure.font_line(size, styles[index] if styles else style) for index, size in enumerate(sizes)]


def _metric_starts(measure: _Measure, text: str, widths: list[float], sizes: list[int], style: Any,
                   objects: dict[int, tuple[int, int]], styles: list[Any] | None = None,
                   marks: dict[int, int] | None = None) -> list[int]:
    """Where each line :func:`_line_metrics` lays out starts in *text*."""

    advances = {**{index: width for index, (width, _) in objects.items()}, **(marks or {})} or None
    return measure.line_starts(text, widths, min(sizes), style, sizes if len(set(sizes)) > 1 else None, styles,
                               advances, set(objects))


def _line_metrics(measure: _Measure, text: str, widths: list[float], sizes: list[int], style: Any,
                  shape: _Shape, objects: dict[int, tuple[int, int]], styles: list[Any] | None = None,
                  marks: dict[int, int] | None = None, end: int = 0, head: int = 0,
                  held: dict[int, int] | None = None) -> tuple[tuple[int, int], ...]:
    """(height, advance) of each line FormFit breaks *text* into, every character at its own size: a line
    is as tall as its largest character, its line spacing reckoned from that size. An object set as a
    character (*objects*: its place in *text* -> its width and height) takes its width on its line and
    makes the line at least as tall as itself; its run's size counts for the line spacing alone, not for the
    line's height (Hancom: as tall as its characters and objects, spaced from its largest size); a fixed line spacing
    keeps the next line that far down. A composed character or ruby text (*marks*: its place -> its
    width) is a character of its size in *sizes*. The last line is at least as tall as the paragraph's
    end (*end*, see :func:`_end_size`), and the first as its label (*head*, see :func:`_head_size`); a control or
    an object not set as a character after the first character (*held*: its place -> its run's size, see
    :func:`_held_sizes`) makes the line it falls on as tall as a character of that size. In a
    paragraph taking its line height from the font each of them counts as tall as its face makes a line
    (:func:`_line_sizes`)."""

    starts = _metric_starts(measure, text, widths, sizes, style, objects, styles, marks)
    heights = _line_sizes(measure, sizes, style, styles, shape)
    if shape.font_line:
        end, head = measure.font_line(end, style), measure.font_line(head, style)
        held = {place: measure.font_line(tall, style) for place, tall in (held or {}).items()}
    metrics = []
    for start, stop in zip(starts, [*starts[1:], len(text)]):
        span = range(start, stop) if stop > start else range(len(text) - 1, len(text))
        edges = ([end] if stop == len(text) else []) + ([head] if start == 0 else [])             + [tall for place, tall in (held or {}).items() if start < place <= stop]
        size = max([heights[index] for index in span] + edges)
        glyphs = [heights[index] for index in span if index not in objects] + edges
        height = max([max(glyphs) if glyphs else size] + [objects[index][1] for index in span if index in objects])
        advance = _pitch(shape.kind, shape.value, size)
        metrics.append((height, advance if shape.kind == "FIXED" else height + advance - size))
    return tuple(metrics)


def _drawn_height(obj: Any, measure: _Measure) -> int:
    """How tall Hancom draws *obj*: a drawing holding a text box (hp:drawText) as tall as the box's text and
    its margins when that is taller than hp:sz -- Hancom grows the drawing to hold them, writing the grown size
    to hp:curSz alone (negative for a drawing scaled upside down), at times one less, which makes that a lower
    bound within a unit or two; a grown size further off was written for other fonts or text, and Hancom lays the
    text out anew. When the text cannot be laid out, the grown size stands. Any other object (a table too) as
    hp:sz."""

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
        return max(height, grown)
    laid = top + content + bottom
    # Hancom lays the box's text out anew: a grown size written for other fonts or text does not hold
    return max(height, laid, grown if abs(grown - laid) <= 2 else 0)


#: How far each parallel shadow moves from its object before its own offset: Hancom draws a bottom shadow
#: ``offsetY + 600`` down and a top one ``offsetY - 600`` (down positive), whatever the object's size or line.
_SHADOW_DISTANCE = 600


def _shadow_drop(obj: Any) -> int:
    """How far the parallel shadow of *obj* (``hp:shadow``) is moved up or down from it: an object set as a
    character is that much taller (drawn lower when the shadow goes up). 0 without one; other shadows are not
    followed."""

    shadow = obj.find(f"{HP}shadow")
    kind = "" if shadow is None else shadow.get("type", "NONE")
    if not kind.startswith(("PARELLEL_", "PARALLEL_")):
        return 0
    offset = int(shadow.get("offsetY", 0))  # written as signed text, as Hancom reads it
    if not -(1 << 31) <= offset < 1 << 31:
        raise _Unsupported("a shadow offset past 32 bits")
    return abs(offset + _SHADOW_DISTANCE if kind.endswith("BOTTOM") else offset - _SHADOW_DISTANCE)


#: A picture's shadow spreads in whole pixels at 96 per inch (75 HWPUNIT): a radius of 400 spreads as 450.
_SHADOW_BLUR_STEP = 75


def _effect_room(obj: Any, width: int, height: int) -> tuple[int, int, int, int]:
    """(left, right, top, bottom): how much farther than its *width* x *height* a picture's effects
    (``hp:effects``) reach, which Hancom lays it out with: a glow its ``radius`` on each side, and an outer
    shadow the picture (with its glow) moved ``distance`` in its ``direction`` (degrees clockwise on the page
    from the right) and spread by its ``radius`` on each side, rounded up to whole pixels (see
    :data:`_SHADOW_BLUR_STEP`); each reach is cut to a whole HWPUNIT. An inner shadow and a soft edge take no room.
    A reflection reaches below about its ``pos`` share of the picture (with its glow, and a pixel on each side)
    less a pixel, and its ``distance``: within about a pixel of Hancom's, the extra not followed."""

    effects = obj.find(f"{HP}effects")
    if effects is None or len(effects) == 0:
        return 0, 0, 0, 0
    glow = effects.find(f"{HP}glow")
    reach = 0 if glow is None else max(0, int(float(glow.get("radius", 0))))
    left, top, right, bottom = -reach, -reach, width + reach, height + reach
    shadow = effects.find(f"{HP}shadow")
    if shadow is not None and shadow.get("style", "OUTSIDE") != "INSIDE":
        angle = math.radians(float(shadow.get("direction", 0)))
        distance, blur = float(shadow.get("distance", 0)), max(0.0, float(shadow.get("radius", 0)))
        blur = math.ceil(blur / _SHADOW_BLUR_STEP) * _SHADOW_BLUR_STEP  # in whole pixels, as Hancom spreads it
        dx, dy = round(distance * math.cos(angle), 9), round(distance * math.sin(angle), 9)  # 0 at 90, 180 ...
        left, right = min(left, left + dx - blur), max(right, right + dx + blur)
        top, bottom = min(top, top + dy - blur), max(bottom, bottom + dy + blur)
    room = [math.floor(-left), math.floor(right - width), math.floor(-top), math.floor(bottom - height)]
    reflection = effects.find(f"{HP}reflection")
    share = None if reflection is None else reflection.find(f"{HP}pos")
    size = 0.0 if share is None else float(share.get("end", 0)) - float(share.get("start", 0))
    if reflection is not None and size > 0:  # about that much of the picture (with its glow, a pixel round it)
        below = (size * (height + 2 * reach + 2 * _SHADOW_BLUR_STEP) - _SHADOW_BLUR_STEP
                 + max(0.0, float(reflection.get("distance", 0))))
        room[3] = max(room[3], math.floor(below) - room[2])
    return room[0], room[1], room[2], room[3]


def _object_extent(obj: Any, measure: _Measure) -> tuple[int, int]:
    """(width, height) an object set as a character takes, its outer margins included; a table as tall
    as its rows, a drawing with its shadow's move (see :func:`_shadow_drop`), a picture with the room its
    effects take (see :func:`_effect_room`). Set as a character, any object's caption takes room as a
    table's does: above or below it, its lines and its gap in the height (see :func:`_caption`); beside it, its
    width and its gap in the width, the height staying the object's however tall the caption runs."""

    size = obj.find(f"{HP}sz")
    margin = obj.find(f"{HP}outMargin")
    extra = (0, 0, 0, 0) if margin is None else tuple(_margin(margin, side) for side in ("left", "right", "top", "bottom"))
    tac = obj.find(f"{HP}pos").get("treatAsChar") == "1"
    height = _inline_table_height(measure, obj) + sum(_caption(measure, obj)) if _local(obj) == "tbl" \
        else _drawn_height(obj, measure) + (_shadow_drop(obj) if tac else 0)
    width = int(size.get("width", 0))
    left, right, top, bottom = _effect_room(obj, width, height) if tac else (0, 0, 0, 0)
    if tac and _local(obj) != "tbl":
        height += sum(_caption(measure, obj))
        width += _caption_beside(obj)
    return width + extra[0] + extra[1] + left + right, height + extra[2] + extra[3] + top + bottom


def _caption_beside(obj: Any) -> int:
    """How much wider an object set as a character is for its caption beside it: the caption's width and its
    gap (none for a caption above or below it)."""

    caption = obj.find(f"{HP}caption")
    if caption is None or caption.get("side", "LEFT") not in ("LEFT", "RIGHT"):
        return 0
    return int(caption.get("width", 0)) + int(caption.get("gap", 0))


def _inline_content(measure: _Measure, paragraph: Any, runs: list[Any], anchored: Any = None,
                    placed: tuple[Any, ...] = ()) -> tuple[
        str, list[int], list[Any], dict[int, tuple[int, int]], dict[int, int]]:
    """The paragraph's text with each object set as a character, composed character and ruby text in its
    place (U+FFFC), each character's size and style (ruby text's is the height of its line), each
    object's place -> its width and height, and each composed character's or ruby text's place -> its
    width. A control shown on a line (see :func:`_shown_control`) after the first character is an object of no
    width as tall as its run's characters (those before it stand on the first line, see :func:`_head_size`).
    Objects placed otherwise (but *anchored* and *placed*, laid out apart), and line spacing between
    lines or at least with an object among text, are not followed."""

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
            if name in _OBJECTS and (_floating(child) or _on_paper(child) or child is anchored
                                     or any(child is obj for obj in placed)):
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
            elif text and _shown_control(child):  # a character of no width as tall as its run's, on the line it
                objects[len(text)] = (0, height)  # falls on: an object's that fits, the next past one wider than it
                part = "￼"
            else:
                continue
            text += part
            sizes += [height] * len(part)
            looks += [look] * len(part)
    return "".join(text), sizes, looks, objects, marks


def _shown_control(child: Any) -> bool:
    """Whether *child* of a run is a control Hancom sets on a line as a character (a page number, a field, a
    bookmark and so on -- not a column or section definition)."""

    return _local(child) == "ctrl" and any(_local(kind) not in ("colPr",) for kind in child)


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
    offset = _pos_offset(pos, "vertOffset")
    if pos.get("vertRelTo") != "PARA" or pos.get("vertAlign", "TOP") != "TOP" \
            or (_down(pos) if _local(obj) == "tbl" else offset):  # a table placed up stands at the top
        return None
    return obj


def _inline_place(runs: list[Any], obj: Any, apart: tuple[Any, ...]) -> int:
    """*obj*'s place in the text :func:`_inline_content` makes of *runs* (it and *apart* laid out apart)."""

    place = 0
    for child in (child for run in runs for child in run):
        name = _local(child)
        if child is obj:
            return place
        if name in _OBJECTS:
            place += not (_floating(child) or _on_paper(child) or any(child is other for other in apart))
        elif name in _MARKS or place and _shown_control(child):
            place += 1
        elif name == "t":
            place += len(_t_text(child))
    return place


def _apart_from_wide(measure: _Measure, text: str, widths: list[float], sizes: list[int], style: Any,
                     objects: dict[int, tuple[int, int]], styles: list[Any] | None, marks: dict[int, int] | None,
                     metrics: tuple[tuple[int, int], ...], size: int, shape: _Shape,
                     place: int) -> tuple[tuple[tuple[int, int], ...], int | None]:
    """Hancom lays an object set as a character that is wider than its line on that line alone: the object
    placed top and bottom anchored before it at the paragraph's start stands on that line, and one after it at
    the paragraph's end on an empty line of its own below it, as tall as the paragraph's characters (*size*).
    *text* holds the paragraph's characters and objects set as characters, not the anchored one, whose place in
    it is *place*. (*metrics* with that line, its index.)

    Otherwise the anchor stands on the line holding the character before it (the first line when it comes
    first), as Hancom keeps it at the end of that line when the next one starts after it: (*metrics*, that line).
    (*metrics*, ``None``) when *text* holds no object set as a character."""

    if not text or not objects:
        return metrics, None
    starts = _metric_starts(measure, text, widths, sizes, style, objects, styles, marks)

    def wide(index: int) -> bool:
        line = max(number for number, start in enumerate(starts) if start <= index)
        return index in objects and objects[index][0] > widths[min(line, len(widths) - 1)]

    empty = (size, _pitch(shape.kind, shape.value, size))
    if place == 0 and wide(0):  # the anchor first: on the object's line, no line of its own
        return metrics, 0
    if place == len(text) and wide(len(text) - 1):  # the anchor last: its empty line below
        return (*metrics, empty), len(metrics)
    return metrics, max((number for number, start in enumerate(starts) if start < place), default=0)


def _anchor_line(measure: _Measure, paragraph: Any, runs: list[Any], text: str, obj: Any, widths: list[float],
                 size: int, style: Any, cached: tuple[tuple[int, int], ...], count: int) -> int:
    """The line *obj*'s place in the text falls on: in a line cache, where Hancom counts every object and
    control as eight characters, the last line starting at or before it; otherwise the line holding the
    character before it."""

    place = objects = 0
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t":
            place += len(_t_text(child))
        elif _local(child) in _OBJECTS or _local(child) == "ctrl":  # every object and control takes eight
            objects += 1
    segments = paragraph.findall(f"{HP}linesegarray/{HP}lineseg") if cached else []
    if segments:  # lines Hancom laid out (not ones laid out here)
        starts = [int(segment.get("textpos", 0)) for segment in segments]
        place += 8 * objects  # its own place in the cache, before its own eight
    else:
        starts = measure.line_starts(text, widths, size, style)
        return max((index for index, start in enumerate(starts[:count]) if start < place), default=0)
    return max((index for index, start in enumerate(starts[:count]) if start <= place), default=0)


def _anchor(measure: _Measure, paragraph: Any, runs: list[Any], text: str, obj: Any, widths: list[float], size: int,
            style: Any, cached: tuple[tuple[int, int], ...], count: int, line: int | None = None) -> _Anchor:
    """Where *obj* stands in the paragraph: at the top of the line its place in the text falls on (*line*)."""

    if line is None:
        line = _anchor_line(measure, paragraph, runs, text, obj, widths, size, style, cached, count)
    margin = obj.find(f"{HP}outMargin")
    top, bottom = (0, 0) if margin is None else (_margin(margin, "top"), _margin(margin, "bottom"))
    if _local(obj) == "tbl":
        rows, cells = _table_rows(measure, obj)
        table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", _table_ends(obj),
                           tuple(cells), caption=_caption(measure, obj), cut=_spare_cut(obj))
        return _Anchor(line, table, 0)
    return _Anchor(line, None, _drawn_height(obj, measure) + top + bottom,
                   obj.find(f"{HP}pos").get("flowWithText") == "0")


def _object_line(
    measure: _Measure, obj: Any, count: int, size: int, pitch: int, column: int, shape: _Shape
) -> tuple[int, int, int, _FlowTable | None]:
    """(lines, size, pitch, flowing table) of a paragraph of *shape* holding *obj* and nothing else."""

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
        else:
            tall += _shadow_drop(obj)
            room = _effect_room(obj, int(obj.find(f"{HP}sz").get("width", 0)), _drawn_height(obj, measure))
            tall += room[2] + room[3] + sum(_caption(measure, obj))  # as in _object_extent
        tall = max(tall, size)
        return 1, tall, _object_pitch(shape, obj, tall, size), None
    on_paragraph = pos.get("vertRelTo") == "PARA" and pos.get("vertAlign", "TOP") == "TOP"
    if _wraps_top_and_bottom(obj, column) and on_paragraph:
        if name == "tbl":
            rows, cells = _table_rows(measure, obj)
            offset = _pos_offset(pos, "vertOffset")  # one up (a negative offset, kept unsigned) starts at the line
            table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", _table_ends(obj),
                               tuple(cells), 0 if offset < 0 or offset >= 1 << 31 else offset,
                               _caption(measure, obj), _spare_cut(obj))
            return count, size, pitch, table
        offset = _pos_offset(pos, "vertOffset")
        below = offset + tall
        if shape.prev and offset < 1 << 31:  # down from the paragraph's top, above its spacing before: that much
            below = max(below - shape.prev, size)  # less below its line's top, the line no shorter than its characters
        if offset >= 1 << 31:  # one up, kept as an unsigned 32-bit number: Hancom draws it that far above, the
            below = max(offset - (1 << 32) + tall, size)  # paragraph's line no shorter than its characters
        return 1, below, below, None
    raise _Unsupported(f"{name} placed {obj.get('textWrap')} relative to {pos.get('vertRelTo')}")


def _note_anchors(runs: list[Any], in_tables: bool = False) -> list[tuple[int, Any]]:
    """(text offset, hp:footNote) of each footnote in the runs; *in_tables*: with those in the cells of the tables
    the runs hold, at the table's place."""

    offset, anchors = 0, []
    for run in runs:
        for child in run:
            name = _local(child)
            if name == "t":
                offset += len(_t_text(child))
            elif name == "ctrl" and child.find(f"{HP}footNote") is not None:
                anchors.append((offset, child.find(f"{HP}footNote")))
            elif in_tables and name == "tbl":
                anchors += [(offset, note) for note in child.iter(f"{HP}footNote")]
    return anchors


def _anchored_notes(measure: _Measure, runs: list[Any], text: str, widths: list[float], size: int, style: Any,
                    width: int, sizes: list[int] | None = None,
                    styles: list[Any] | None = None) -> dict[int, tuple[int, int, int]]:
    anchors = _note_anchors(runs, in_tables=True)  # Hancom sets a table's notes at the foot as its paragraph's
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




def _rises(obj: Any, column: int) -> bool:
    """Whether *obj* is placed top and bottom up from the top of its paragraph: a negative ``vertOffset``, which
    the file keeps as an unsigned 32-bit number."""

    pos = obj.find(f"{HP}pos")
    return (pos is not None and pos.get("treatAsChar") != "1" and pos.get("vertRelTo") == "PARA"
            and pos.get("vertAlign", "TOP") == "TOP" and _pos_offset(pos, "vertOffset") >= 1 << 31
            and _wraps_top_and_bottom(obj, column))


def _controls_beside(obj: Any, runs: list[Any], width: float) -> tuple[Any, list[Any], list[Any]] | None:
    """(*obj*'s run, the runs holding controls before it, those holding controls after it) when *obj* is an
    object (a table, a drawing ...) set as a character wider than the line (*width*) and controls (``hp:ctrl``, a page number, a hidden page
    number, a field, a bookmark, a header and so on -- but not a column definition) stand beside it in its
    paragraph, else ``None``: Hancom sets the controls before it on the table's line (on an empty line of their
    own above it when they show a number) and the controls after it on the line after that."""

    if obj.find(f"{HP}pos").get("treatAsChar") != "1" or _extent(obj, "width") <= width:
        return None
    home, before, after = None, [], []
    for run in runs:
        for child in run:
            if child is obj:
                home = run
            elif _local(child) == "ctrl" and any(_local(kind) != "colPr" for kind in child):
                side = before if home is None else after
                if not side or side[-1] is not run:
                    side.append(run)
    return (home, before, after) if before or after else None


def _controls_after_wide(measure: _Measure, runs: list[Any], objects: list[Any], width: float) -> int:
    """How tall the characters of the runs holding the controls after an object set as a character wider than the
    line (see :func:`_controls_beside`) are, when the paragraph starts with that object and has no controls before
    it: Hancom sets those controls on the line after the object's, not on its line; 0 for any other paragraph."""

    if not objects:
        return 0
    beside = _controls_beside(objects[0], runs, width)
    if beside is None or beside[1] or not beside[2]:
        return 0
    home = beside[0]
    if any(_run_text([run]) for run in runs[:runs.index(home)]):  # text before it: the table's line is another
        return 0
    return max(measure.char_height(run.get("charPrIDRef")) for run in beside[2])


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
    offset = _pos_offset(pos, "horzOffset")
    if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
        offset -= 1 << 32
    start = offset if pos.get("horzAlign") == "LEFT" else column - width - offset
    return start < _MIN_SIDE and column - start - width < _MIN_SIDE


def _square_object(objects: list[Any], runs: list[Any], column: int) -> Any:
    """The one object of a paragraph wrapped square across the column, from the top of the line its control
    falls on (:func:`_square_anchor_line`), or ``None`` (:func:`_square_sides` says where the text goes beside
    it)."""

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
    return obj


def _square_anchor_line(measure: _Measure, page: _Page, paragraph: Any, runs: list[Any], obj: Any) -> int:
    """The line *obj*'s control falls on, the paragraph laid out the column's whole width (FormFit's lines,
    the object taking no room in them): Hancom places a square-wrapped object from that line's top. A control
    right where a line starts, the line before full, falls on that line before, where its text ends."""

    place = 0
    for child in (child for run in runs for child in run):
        if child is obj:
            break
        if _local(child) == "t":
            place += len(_t_text(child))
    size, refs, _ = _text_size(measure, runs, paragraph)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    starts = measure.line_starts(_run_text(runs), _line_widths(shape, page.column_width, style), size, style)
    return sum(1 for start in starts[1:] if start < place)


def _square_sides(obj: Any, page: _Page) -> tuple[int, int]:
    """How wide the text beside a square-wrapped object is on its left and on its right in the column: a
    side narrower than 1440, or one its text flow leaves out, takes none (0). Placed from the column,
    the paragraph or the paper's left or right (from the paper only in one column)."""

    pos = obj.find(f"{HP}pos")
    width, offset = _extent(obj, "width"), _pos_offset(pos, "horzOffset")
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

    offset = _pos_offset(table.find(f"{HP}pos"), "vertOffset")
    if offset < 0 or offset >= 1 << 31:
        raise _Unsupported("a square-wrapped table placed up from its paragraph past the page foot")
    rows, cells = _table_rows(measure, table)
    ends = _table_ends(table)
    flowing = _FlowTable(rows, table.get("pageBreak", "CELL"), table.get("repeatHeader") == "1", ends,
                         tuple(cells), caption=_caption(measure, table), cut=_spare_cut(table))
    left, right = _square_sides(table, page)
    return flowing, offset, _Wrap(0, 0, page.column_width - left - right, split=left if left and right else 0)




def _clear_of_its_band(measure: _Measure, page: _Page, paragraph: Any, obj: Any) -> bool:
    """Whether the object of an empty paragraph holding nothing else starts its band below the paragraph's line
    (a table from the paragraph's top above its spacing, as a table alone, anything else from the line's top):
    only then can the next line stand above it, and does Hancom's rule of an empty line staying where it is
    differ from the paragraph laid out as the object alone."""

    para = _paragraph(measure, page, paragraph, None, obj)
    offset = _pos_offset(obj.find(f"{HP}pos"), "vertOffset") - (para.prev if _local(obj) == "tbl" else 0)
    return offset >= para.advance(0)


def _pushing_object(objects: list[Any], text: str, column: int, bare: bool = False) -> Any:
    """The one object of a paragraph of text (spaces are text) placed top and bottom below the line it stands
    on (an offset down from the paragraph's top), or ``None``. In a paragraph holding no text, the objects
    set as characters are that line; in one of text, they are among it; *bare*, the paragraph holds the object
    and nothing else, and its empty line stays where it is."""

    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    lined = not text.strip() and len(objects) > len(placed)  # no text: the objects set as characters its line
    if len(placed) != 1 or not (lined or text or bare):
        return None
    obj = placed[0]
    pos = obj.find(f"{HP}pos")
    if not _wraps_top_and_bottom(obj, column) or pos.get("vertRelTo") != "PARA" \
            or pos.get("vertAlign", "TOP") != "TOP":
        return None
    offset = _pos_offset(pos, "vertOffset")
    if offset <= 0 or offset >= 1 << 31:  # at the paragraph's top (see _anchored_object), or placed up (unsigned)
        return None
    return obj


def _stacked_objects(objects: list[Any], runs: list[Any], column: int) -> list[Any]:
    """The objects of a paragraph holding no text when there are several and each is placed top and bottom
    from the paragraph's top (one placed up from it stacks as if not moved, see :func:`_stack`), from the column's
    or the paragraph's left or right; none otherwise. Objects set as characters there are the paragraph's line,
    which goes below them."""

    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    if len(placed) < 2 or _run_text(runs).strip() or _marks(runs) or _note_anchors(runs):
        return []
    for obj in placed:
        pos = obj.find(f"{HP}pos")
        if not _wraps_top_and_bottom(obj, column) \
                or (pos.get("vertRelTo"), pos.get("vertAlign", "TOP")) != ("PARA", "TOP") \
                or pos.get("horzRelTo") not in ("COLUMN", "PARA") \
                or pos.get("horzAlign", "LEFT") not in ("LEFT", "RIGHT"):
            return []
    return placed


def _stack(measure: _Measure, objects: list[Any], column: int, shape: _Shape) -> tuple[_Stacked, ...]:
    """*objects*, stacked in a paragraph holding nothing else, as :meth:`_Paginator._stacked` places them."""

    stacked: list[_Stacked] = []
    for obj in objects:
        pos = obj.find(f"{HP}pos")
        width, height = _object_extent(obj, measure)
        offset = _pos_offset(pos, "horzOffset")
        if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
            offset -= 1 << 32
        indent = (shape.left, shape.right) if pos.get("horzRelTo") == "PARA" else (0, 0)
        left = indent[0] + offset if pos.get("horzAlign", "LEFT") == "LEFT" else column - indent[1] - width - offset
        table = None
        if _local(obj) == "tbl":
            rows, cells = _table_rows(measure, obj)
            ends = _table_ends(obj)
            table = _FlowTable(rows, _page_break(obj), obj.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_caption(measure, obj), cut=_spare_cut(obj))
        down = _pos_offset(pos, "vertOffset")  # placed up (kept unsigned): Hancom stacks it as if not moved
        stacked.append(_Stacked(down if down < 1 << 31 else 0, left, left + width, height, table))
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
    beside = sum(1 for line in range(para.lines) if para.span(0, line) < band.bottom)
    for index, (height, advance) in enumerate(metrics):
        if top < band.bottom and top + height > band.top and not (index == 0 and para.bare):
            shift = band.bottom - top
            if index == 0:
                pushed, shifted = replace(para, prev=para.prev + shift), shift
                if not starts:  # below an earlier paragraph's object: no line of it beside the band
                    pushed, beside = replace(pushed, lead=shift), 0
            else:  # the lines from it on go below the object, on a later page too
                metrics[index - 1] = (metrics[index - 1][0], metrics[index - 1][1] + shift)
                pushed, beside = replace(para, cached=tuple(metrics)), index
            break
        top += advance
    else:
        pushed, rest = para, band.lower(top + para.next)
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
            if shape.font_line:
                height = measure.font_line(height, style)
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
    the band is as wide as the room beside the object, one holding an object wider than that room too (the object
    alone on it, reaching past the room). Every line taken as narrow at first, the lines are broken again until
    the narrow ones settle."""

    advances = {index: width for index, (width, _) in objects.items()} or None
    mixed = sizes if len(set(sizes)) > 1 else None
    heights = _line_sizes(measure, sizes, style, looks, shape)
    if shape.font_line:
        end, head = measure.font_line(end, style), measure.font_line(head, style)
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
            size = max([heights[index] for index in span] + ([end] if stop == len(text) else [])
                       + ([head] if start == 0 else []))
            height = max([size] + [objects[index][1] for index in span if index in objects])
            pitch = _pitch(shape.kind, shape.value, size)
            advance = pitch if shape.kind == "FIXED" else height + pitch - size
            if top < wrap.bottom and top + height > wrap.top:
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
    """Whether a table moved row by row (TABLE) has no room for its first row from *y*, one set not to
    split (NONE) no room for all its rows, one split cell by cell (CELL) room for none of its first row's
    lines, or one moved row by row or split cell by cell no room for the header rows it repeats, so it starts
    on the next page. At the top of a page it is drawn anyway."""

    if table.mode not in ("TABLE", "NONE", "CELL") or not table.rows:
        return False
    if _header_moves(table, y, body - table.margins[1]):
        return True
    if table.mode == "CELL":  # its first row goes on whole
        top = _repeated_header(table) + table.margins[0]
        row = table.rows[0]
        return not row.joined and y != top \
            and _flow_row("CELL", row, 0, y, body - table.margins[1], top, table.cut) == (1, top + row.height)
    first = sum(row.height for row in table.rows) if table.mode == "NONE" else table.rows[0].height
    return y + first > body - table.margins[1] - table.cut \
        and y != _repeated_header(table) + table.margins[0]


def _header_moves(table: _FlowTable, y: int, body: int) -> bool:
    """Whether a table moved row by row or split cell by cell (TABLE, CELL) has no room from *y* above
    *body* for the header rows it repeats on every page: Hancom does not split them, so the table starts on
    the next page, the header rows at its top. At a page's top they are drawn anyway."""

    header = _repeated_header(table)
    return table.mode in ("TABLE", "CELL") and bool(header) and y + header > body - table.cut \
        and y > table.margins[0]


def _flow_table(table: _FlowTable, frame: int, y: int, body: int) -> tuple[int, int]:
    """Lay the rows out from vertical position *y*; the frame and position where the table ends."""

    body -= table.margins[1]  # the rows keep the table's bottom margin above the page end
    header = _repeated_header(table) + table.margins[0]  # and go on below its top margin on the next page
    foot = body - table.cut
    # split between cell lines, it keeps the room of a caption below it at the foot of every page it goes on from
    room = body - table.caption[1] if table.mode == "CELL" else body
    if _header_moves(table, y, body):  # its repeated header rows start the next page (drawn there once)
        frame, y = frame + 1, table.margins[0]
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
            frame, y = _split_block(table, index, end, frame, y, room, header)
            index = end + 1
            continue
        before, start = frame, y
        above = index == len(rows) - 1 and table.caption[1] and table.mode == "CELL" and rows[index].spare \
            and not rows[index].nested  # a caption below keeps its room: the row's room to spare is cut above it
        frame, y = _flow_row(table.mode, rows[index], frame, y,
                             body - (table.caption[1] if above else 0) if index == len(rows) - 1 else room, header,
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
    # a cell of the row the page end falls in keeping none of its lines above it sends the row's cells on whole
    whole = any(_cell_rest(cell, tops[cut], foot) == (cell.height, cell.lines) and cell.lines and not cell.spare
                for start, span, cell in table.cells if start == cut and span == 1)
    for start, span, cell in table.cells:
        end = start + span - 1
        if start < first or start > last or end < cut:
            continue  # another row, or done above the page end
        part = (cell.height, cell.lines) if start > cut or whole and start == cut and span == 1 \
            else _cell_rest(cell, tops[start], foot)
        if part is None:
            continue
        rest, begin = part[0], max(start, cut)
        left = part[1]  # the lines it has left are its last ones
        # Once a line was consumed, a uniform paragraph no longer starts below its original spacing before.
        cells.append((begin, end - begin + 1, replace(cell, height=rest, lines=left, **(
            {"metrics": cell.metrics[len(cell.metrics) - left:], "leads": cell.leads[len(cell.leads) - left:]}
            if _lists_lines(cell) else {"first": cell.size if left < cell.lines else cell.first}))))
        if span == 1:
            heights[start] = max(heights[start], rest)
        else:
            rests.append((begin, end, rest))
    for start, end, rest in sorted(rests, key=lambda item: (item[1], item[0])):
        lacking = rest - sum(heights[index] for index in range(start, end + 1))
        heights[end] += max(lacking, 0)
    return cut, heights, cells


def _lists_lines(cell: _Row) -> bool:
    """Whether *cell* lists the (height, advance) of each of its lines (``_Row.metrics``): one of several
    paragraphs, which may differ in size, holding no table."""

    return bool(cell.metrics) and len(cell.metrics) == cell.lines and not cell.nested and not cell.pieces


def _cell_rest(cell: _Row, top: int, foot: int) -> tuple[int, int] | None:
    """How tall the part of a cell starting at *top* that goes on past the page end *foot* is, and how many
    lines it holds; ``None`` when nothing of it goes on. Each line takes its own height and advance where the
    cell lists them (a line of a larger character size among others), else the cell's."""

    lines = cell.metrics if _lists_lines(cell) else ((cell.size, cell.pitch),) * cell.lines
    # the room above each line when a part of the cell starts with it: its paragraph's spacing before where the
    # cell lists its lines, else above its first line what that line takes beyond the character size (its first
    # paragraph's spacing before, or a taller first line)
    leads = cell.leads if _lists_lines(cell) and len(cell.leads) == cell.lines \
        else (max(cell.first - cell.size, 0),) + (0,) * (cell.lines - 1) if cell.lines else ()
    fitting, y = 0, top + cell.margins + (leads[0] if leads else 0)
    while fitting < cell.lines and y + lines[fitting][0] <= foot:
        y += lines[fitting][1]
        fitting += 1
    left = lines[fitting:]
    height = cell.margins + (leads[fitting] if leads and left else 0) \
        + sum(advance for _, advance in left[:-1]) + left[-1][0] if left else 0
    if cell.spare and (fitting or not cell.lines):  # its text (or what is left: none) starts above the page end:
        # the declared room is cut like a row's, and the lines that do not fit go on with it, which is then
        # at least as tall as they are with the cell's margins
        rest = top + cell.height - foot
        if left:
            return max(rest, height), len(left)
        return (rest, 0) if rest > _SPARE_DROPPED else None
    if cell.spare:  # none of it fits: it goes on whole
        return cell.height, cell.lines
    if not left:
        return None
    return height, len(left)


def _flow_row(mode: str, row: _Row, frame: int, y: int, body: int, header: int,
              cut: int = _SPARE_CUT) -> tuple[int, int]:
    """A row that does not fit even a fresh page is drawn there anyway, cut at the paper's edge;
    CELL breaks a row between its lines, or a row taller than its text just above the page's foot."""

    remaining, height, metrics, nested, leads = row.lines, row.height, row.metrics, row.nested, row.leads
    cuts, blocks = row.cuts, row.blocks
    foot = body - cut
    consumed = 0  # how far down the cell's lines the part on this page starts
    while True:
        if y + height <= foot:
            return frame, y + height
        fresh = y == header
        if mode == "CELL" and row.reaches and row.spare:
            raise _Unsupported("a page end in a row declared taller than its text holding a table among its text")
        if mode == "CELL" and nested and not row.pieces and row.spare:  # declared taller than its text: cut
            # like any such row (a row whose tables split goes on below as any cell's)
            if y + row.margins + (metrics[0][0] if metrics else row.size) <= foot:  # once its first line fits
                rest = height - (foot - y)
                fitting = _lines_fitting(metrics, leads, y + row.margins, foot) if metrics else 1
                if fitting < len(metrics):  # its lines do not all fit: those that do not go on, at least
                    rest = max(rest, row.margins + _lines_height(metrics[fitting:], leads[fitting:]))
                elif rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y, nested = frame + 1, header, False
                remaining, height = 1, rest
                continue
            if fresh:
                return frame, y + height
            frame, y = frame + 1, header
            continue
        if mode == "CELL" and nested and not row.pieces:  # between its lines, each as tall as it is (a table
            # is one)
            if not metrics:
                if consumed or y + row.margins + row.first <= foot:
                    raise _Unsupported("a page break in a flowing table row holding a table")
                if fresh:  # no cell's first line fits (the table one stands on): the row goes on whole
                    return frame, y + height
                frame, y = frame + 1, header
                continue
            fitting, top = 0, y + row.margins + (leads[0] if leads else 0)  # a part starts below its first
            # paragraph's spacing before, as any cell's
            while fitting < len(metrics) and top + metrics[fitting][0] <= foot:
                top += metrics[fitting][1]
                fitting += 1
            cut = consumed + sum(advance for _, advance in metrics[:fitting])  # where the line not fitting stands
            found = _reached(row, cut, top, foot, metrics[fitting], metrics[fitting + 1] if fitting + 1 < len(metrics)
                             else None) if row.reaches and fitting < len(metrics) else None
            if found is not None:  # a table among the text splits or goes on alone: what of it goes on, and that line
                piece, consumed = found
                metrics = (piece,) + metrics[fitting + 1:]
                leads = (0,) + leads[fitting + 1:] if leads else ()
                height = row.margins + _lines_height(metrics, leads)
                frame, y = frame + 1, header
                continue
            consumed = cut
            if fitting == len(metrics):  # every line fits, the cell's bottom margin not: cut like a row's
                rest = height - (foot - y)
                if rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y, nested = frame + 1, header, False
                remaining, height, metrics, leads = 1, rest, (), ()
                continue
            if fitting:
                metrics, leads = metrics[fitting:], leads[fitting:]
                height = row.margins + _lines_height(metrics, leads)
            elif fresh:
                return frame, y + height
            frame, y = frame + 1, header
            continue
        if mode == "CELL":
            lines = metrics or ((row.size, row.pitch),) * remaining
            fitting = _lines_fitting(lines, leads, y + row.margins, foot, cuts)
            if fitting and len(lines) == row.lines and y + row.margins + row.first > foot:
                fitting = 0  # every cell's first line must fit, or the row goes on whole
            split = _split_joined(lines, leads, cuts, blocks, fitting, y + row.margins, foot) \
                if blocks and fitting < len(lines) else None
            if split is not None:  # among a table's rows joined by merged cells: they split cell by cell
                metrics, leads, cuts, blocks = split
                remaining, height = len(metrics), row.margins + _lines_height(metrics, leads)
                frame, y = frame + 1, header
                continue
            if fitting and (row.spare or fitting == len(lines)):  # room under its lines: cut like a row's
                rest = height - (foot - y)
                if fitting < len(lines) and y + height - row.spare > foot:  # its text does not all fit:
                    rest = max(rest, row.margins + _lines_height(lines[fitting:], leads[fitting:]))  # it goes on
                elif rest <= _SPARE_DROPPED:
                    return frame, body
                frame, y = frame + 1, header
                remaining, height, metrics, leads, cuts, blocks = 1, rest, (), (), (), ()
                continue
            if fitting:
                metrics, leads, cuts = lines[fitting:], leads[fitting:], cuts[fitting:]
                blocks = tuple((start - fitting, *block) for start, *block in blocks if start >= fitting)
                remaining, height = len(metrics), row.margins + _lines_height(metrics, leads)
            elif fresh:
                return frame, y + height
        elif fresh:
            return frame, y + height
        frame, y = frame + 1, header


def _reached(row: _Row, cut: int, top: int, foot: int, line: tuple[int, int],
             after: tuple[int, int] | None) -> tuple[tuple[int, int], int] | None:
    """Check a page end before the row's *line* (height, advance), which stands *cut* below the top of the
    cell's lines (and would stand at *top* on the page), against the tables among its text (see
    :class:`_Reach`; *after*: the line after it, if any). Hancom moves such a table on to the next page with the
    line its control falls on when that line does not fit and the table would fit (a table that may split:
    its rows ending a table's cut, 101, above the foot with room for a caption below it), or would start past
    the page's foot. When the first line it pushes below it does not fit and the table would not, the table
    splits into its pieces (see :func:`_split_rows`): those so ending (a row going on with room for its bottom
    margin too) stay, the rest go on at the next page's top below the table's top margin again (a row going on
    below its own top margin again too) and
    that line below them. When no piece stays, the table goes on alone to the next page's top (whatever its offset): the line
    its control falls on stays where it is, and so does the line it pushes when that is the same, which then
    fits, the next line going below the table on the next page (if it does not fit either, the table goes on
    with it, as Hancom does from the line's top). Returned then: what of that line goes on, and where it starts
    in the cell's lines. A page end through a table or between it and the line it pushes, past a table on this
    page reaching the foot (with the cell's margins), before lines that would
    fit on this page once the table has gone on alone (Hancom keeps them there, as if the table were not
    there), or anything else about a table that may not split (or is not a table pushing the lines below it)
    is not followed."""

    found = None
    height, advance = line
    for reach in row.reaches:
        if reach.line < cut and cut != reach.unit and (cut < reach.foot or top - cut + reach.foot > foot):
            raise _Unsupported("a page end through a table among the text of a cell")
        start = top + reach.top - cut  # where the table would stand on this page
        if cut not in (reach.line, reach.unit) or start >= foot or (
                start + reach.above + sum(piece[1] for piece in reach.rows[:-1]) + reach.rows[-1][0]
                <= foot - _SPARE_CUT - reach.below
                if reach.rows else start + reach.foot - reach.top <= foot):
            continue  # it fits, or starts past the foot: it goes on with the line
        if cut != reach.unit or found is not None:
            raise _Unsupported("a page end through a table among the text of a cell")
        if not reach.rows:  # a table that may not split goes on with the line from the line's top
            if start + reach.first <= foot or top + reach.text <= foot or reach.top != cut:
                raise _Unsupported("a page end through a table among the text of a cell")
            continue
        y, kept = start + reach.above, 0
        while kept < len(reach.rows) and y + reach.rows[kept][0] + reach.rows[kept][2] \
                <= foot - _SPARE_CUT - reach.below:
            y += reach.rows[kept][1]
            kept += 1
        joined = _joined_stays(reach, kept, start, foot)
        if joined:  # among rows joined by merged cells, split cell by cell: what of them stays, the rest
            stays = reach.top - cut + joined - reach.above  # going on below the table's top margin again
            found = (height - stays, advance - stays), cut + stays
            continue
        if not kept and reach.line < cut and top + reach.text <= foot:  # the lines would fit without it
            raise _Unsupported("a page end past a table among the text of a cell going on alone")
        if kept or reach.line < cut:  # the rest goes on, the line below it
            stays = reach.top - cut + (sum(piece[1] for piece in reach.rows[:kept])  # the rest below the table's
                                       - reach.rows[kept][3] if kept else 0)  # top margin again
            found = (height - stays, advance - stays), cut + stays
        elif top + reach.text <= foot:  # the line stays, the table goes on alone, the next line below it
            if after is not None and top + advance - (reach.foot - cut) + after[0] <= foot:  # that one would fit
                raise _Unsupported("a page end past a table among the text of a cell going on alone")
            tall = reach.foot - reach.top
            found = (tall, tall), cut + advance - tall
        elif reach.top != cut:
            raise _Unsupported("a page end through a table among the text of a cell")
    return found


def _joined_stays(reach: _Reach, kept: int, start: int, foot: int) -> int:
    """How far below its top the part of a table pushing a cell's lines below it (see :func:`_reached`),
    standing at *start*, that stays above the page end *foot* reaches when that falls among rows joined by
    merged cells (piece *kept* the first not fitting): each of their cells keeps the lines that fit, a table's
    cut and the table's bottom margin above *foot* (see :func:`_block_rest`); 0 when it falls elsewhere or
    nothing of those rows stays."""

    for begin, first, last in reach.blocks:
        if begin <= kept <= begin + last - first:
            break
    else:
        return 0
    assert reach.table is not None
    rows = reach.table.rows
    top = reach.above + sum(piece[1] for piece in reach.rows[:begin])
    cut, heights, _ = _block_rest(reach.table, first, last, start + top, foot)
    if cut == first and all(heights[index] == rows[index].height for index in range(first, last + 1)):
        return 0
    return top + sum(row.height for row in rows[first:last + 1]) - sum(heights.values())


def _split_joined(lines: tuple[tuple[int, int], ...], leads: tuple[int, ...], cuts: tuple[int, ...],
                  blocks: tuple[tuple[int, _FlowTable, int, int], ...], fitting: int, top: int,
                  foot: int) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...],
                                      tuple[tuple[int, _FlowTable, int, int], ...]] | None:
    """A page end before line *fitting* of a cell's *lines* (from *top* down to *foot*) falling among a table's
    rows joined by merged cells (see :attr:`_Row.blocks`): each of their cells keeps the lines that fit above
    the page end, a table's cut (101) and the table's bottom margin above *foot* (see :func:`_line_cuts`), the
    rest going on (see :func:`_block_rest`). The lines, leads, cuts and blocks of what goes on to the next
    page; ``None`` when the page end falls elsewhere or nothing of those rows stays."""

    for start, table, first, last in blocks:
        if start <= fitting <= start + last - first:
            break
    else:
        return None
    y = top + (leads[0] if leads else 0) + sum(advance for _, advance in lines[:start]) \
        + (table.above if first == 0 else 0)
    cut, heights, _ = _block_rest(replace(table, cut=_SPARE_CUT + table.below), first, last, y, foot)
    if cut == first and all(heights[index] == table.rows[index].height for index in range(first, last + 1)):
        return None
    after = start + last - first + 1
    rest = [(heights[index], heights[index]) for index in range(cut, last + 1)]
    kept = [_SPARE_CUT + table.below] * len(rest)
    if last == len(table.rows) - 1:  # the table's last: its bottom margin, and the spacing after its paragraph
        height, advance = lines[after - 1]
        rest[-1] = (rest[-1][0] + table.below, rest[-1][0] + table.below + advance - height)
        kept[-1] = _SPARE_CUT
    return (tuple(rest) + lines[after:],
            ((table.margins[0] + _repeated_header(table),) * len(rest) + leads[after:]) if leads else (),
            tuple(kept) + cuts[after:],
            tuple((other - after + len(rest), *block) for other, *block in blocks if other >= after))


def _lines_fitting(lines: tuple[tuple[int, int], ...], leads: tuple[int, ...], top: int, foot: int,
                   cuts: tuple[int, ...] = ()) -> int:
    """How many of *lines* ((height, advance) each; *leads*: the room above each when it starts a part; *cuts*:
    the room each needs below it) fit from *top* above *foot*."""

    fitting, y = 0, top + (leads[0] if leads else 0)
    while fitting < len(lines) and y + lines[fitting][0] + (cuts[fitting] if cuts else 0) <= foot:
        y += lines[fitting][1]
        fitting += 1
    return fitting


def _lines_height(lines: tuple[tuple[int, int], ...], leads: tuple[int, ...]) -> int:
    """How tall *lines* are as a part of their cell: the room above the first, then down to the last's foot."""

    return (leads[0] if leads else 0) + sum(advance for _, advance in lines[:-1]) + lines[-1][0]




@dataclass(frozen=True)
class _SectionLayout:
    columns: int
    frames: int
    lines: list[tuple[int, int]]   # (frame, vertpos) of every line, in paragraph order
    counts: list[int]              # lines per paragraph
    #: in a section whose columns change (see :func:`_lay_areas`), the page and the column of every line instead
    #: of its frame, and the section's pages
    places: list[tuple[int, int]] | None = None
    pages: int = 0
    #: where the section's text ends: the frame and the foot of its last line, whether footnotes take room on
    #: that page, and the page's body height and column width (for the endnotes that follow)
    end: tuple[int, int] | None = None
    noted: bool = False
    body: int = 0
    width: int = 0


def _lay_section(measure: _Measure, section: Any) -> _SectionLayout:
    page = _page(section)
    notes = _note_shape(section)
    _check_section(measure, section, page)
    areas = _column_areas(section)
    if areas:
        try:
            return _lay_areas(measure, section, page, notes, areas)
        except _BandMoves:
            raise _Unsupported("a square-wrapped object past the page foot in a section whose columns change") \
                from None
    moved: set[int] = set()  # the paragraphs whose square-wrapped object went on to the next page's top
    while True:
        try:
            return _paginate(measure, section, replace(page, rebreak=True) if moved else page, notes, moved)
        except _BandMoves as signal:
            if signal.index in moved or len(moved) >= 16:
                raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot") from None
            moved.add(signal.index)
        except _Unsupported:
            if not moved or not page.alone_at_top:
                raise
            # what follows an object at its paragraph's top that went on alone is not followed (a table flowing
            # past its band, say): again with such objects going on with their paragraphs
            page, moved = replace(page, alone_at_top=False), set()


def _paginate(measure: _Measure, section: Any, page: _Page, notes: _NoteShape, moved: set[int]) -> _SectionLayout:
    paras = []
    wrap: _Wrap | None = None
    step = _grid_step(next(section.iter(f"{HP}grid"), None), "lineGrid")
    for index, paragraph in enumerate(section.findall(f"{HP}p")):
        para, wrap = _wrapped_paragraph(measure, page, paragraph, wrap, index in moved)
        if step and measure.shape(paragraph.get("paraPrIDRef")).snap:
            para = _on_grid(para, step)
        on_paper = _paper_bands(measure, page, paragraph)
        para = replace(para, kept=bool(_cached_metrics(paragraph)))
        held = _held_top(page, paragraph, on_paper[0]) if len(on_paper) == 1 else None
        paras.append(replace(para, paper=on_paper, held=held) if on_paper else para)
    paper = {index: para.paper for index, para in enumerate(paras) if para.paper}
    bands: dict[int, list[tuple[int, int]]] = {}
    sides: dict[int, list[tuple[int, int]]] = {}
    for _ in range(4):  # an object placed on the paper acts on the page its paragraph lands on
        paginator = _Paginator(page.body, page.columns, notes, bands, page.widths, sides, page.alone_at_top)
        frames = paginator.run(paras)
        firsts = [0]
        for count in paginator.counts:
            firsts.append(firsts[-1] + count)
        placed: dict[int, list[tuple[int, int]]] = {}
        beside: dict[int, list[tuple[int, int]]] = {}
        for index, objects in paper.items():  # each on the columns of the page it reaches over
            first = paginator.out[firsts[index]][0] // page.columns * page.columns
            for top, bottom, room, columns in objects:
                for column in columns:
                    (beside if room else placed).setdefault(first + column, []).append((top, bottom))
        if placed == bands and beside == sides:
            break
        bands, sides = placed, beside
    else:
        raise _Unsupported("objects placed on the paper whose pages do not settle")
    if paginator.beside:
        raise _Unsupported("text beside an object placed on the paper")
    end = None
    last = max((index for index, count in enumerate(paginator.counts) if count), default=None)
    if last is not None and paginator.out:
        frame, top = paginator.out[-1]
        end = (frame, top + paras[last].height(paginator.counts[last] - 1))
    return _SectionLayout(page.columns, frames, paginator.out, paginator.counts, end=end,
                          noted=bool(paginator.page_notes[1]), body=page.body, width=page.column_width)


#: A column area starts this far below the lowest line of the one before it on its page (4 mm), whatever the
#: spacing after that line or before its own first line (which goes inside the area).
_COLUMN_AREA_GAP = 1134


def _column_areas(section: Any) -> list[tuple[int, Any]]:
    """Where the section's columns change: (the top-level paragraph, the ``hp:colPr`` of its columns) for each
    paragraph holding a column definition but the section's own, and for each one breaking the column in balanced
    columns (``BALANCED_NEWSPAPER``: it starts a new balanced block). Hancom starts a new area of columns there;
    a definition behind the paragraph's text starts the area but not its columns (``None``: those before go
    on)."""

    areas: list[tuple[int, Any]] = []
    current = _first_columns(section)
    for index, paragraph in enumerate(section.findall(f"{HP}p")):
        text = defined = False
        for child in (child for run in paragraph.findall(f"{HP}run") if run.find(f"{HP}secPr") is None
                      for child in run):
            if _local(child) == "t" and "".join(child.itertext()):
                text = True
            elif not defined and _local(child) == "ctrl" and child.find(f"{HP}colPr") is not None:
                defined = True  # the paragraph's first definition starts its area
                found = None if text else child.find(f"{HP}colPr")
                areas.append((index, found))
                current = found if found is not None else current
        if not defined and paragraph.get("columnBreak") == "1" and current is not None \
                and current.get("type") == "BALANCED_NEWSPAPER" and int(current.get("colCount", "1")) > 1:
            areas.append((index, current))
    return areas


def _lay_areas(measure: _Measure, section: Any, page: _Page, notes: _NoteShape,
               areas: list[tuple[int, Any]]) -> _SectionLayout:
    """Lay a section whose columns change out area by area (see :func:`_column_areas`). Each starts on the page
    where the one before ends, :data:`_COLUMN_AREA_GAP` below its lowest line, or at the next page's top when
    that leaves no room or its first paragraph starts a page; its lines are counted from its top there, as
    Hancom caches them. An area followed by another has the columns of its last page balanced."""

    paragraphs = section.findall(f"{HP}p")
    bounds: list[tuple[int, Any]] = [(0, _first_columns(section)), *areas]
    settings = None
    lines: list[tuple[int, int]] = []
    places: list[tuple[int, int]] = []
    counts: list[int] = []
    page_index, top = 0, 0
    for number, (start, found) in enumerate(bounds):
        end = bounds[number + 1][0] if number + 1 < len(bounds) else len(paragraphs)
        settings = found if found is not None else settings
        if start == end:
            continue
        count, width, widths, gap = _column_layout(settings, page.text_width)
        area = replace(page, columns=count, column_width=width, unequal=bool(widths), widths=widths, gap=gap)
        paras = _area_paragraphs(measure, area, paragraphs[start:end])
        if top and paras[0].page_break:
            page_index, top = page_index + 1, 0
        out, placed = _lay_area(area, notes, paras, top, balance=number + 1 < len(bounds))
        heights = [para.height(line) for para, many in zip(paras, placed) for line in range(many)]
        last = out[-1][0] // count
        bottom = max(vertpos + height for (frame, vertpos), height in zip(out, heights) if frame // count == last)
        lines.extend(out)
        places.extend((page_index + frame // count, frame % count) for frame, _ in out)
        counts.extend(placed)
        page_index += last
        top = (top if last == 0 else 0) + bottom + _COLUMN_AREA_GAP
        if top >= page.body:
            page_index, top = page_index + 1, 0
    return _SectionLayout(1, 0, lines, counts, places, max(page for page, _ in places) + 1)


def _area_paragraphs(measure: _Measure, area: _Page, paragraphs: list[Any]) -> list[_Para]:
    """The paragraphs of one column area, laid out in its columns: the first starts the area (it breaks no
    column)."""

    paras: list[_Para] = []
    wrap: _Wrap | None = None
    for paragraph in paragraphs:
        para, wrap = _wrapped_paragraph(measure, area, paragraph, wrap)
        if para.notes or _paper_band(measure, area, paragraph) is not None:
            raise _Unsupported("footnotes or an object placed on the page or the paper in a section whose "
                               "columns change")
        paras.append(replace(para, kept=bool(_cached_metrics(paragraph))))
    paras[0] = replace(paras[0], column_break=False)
    return paras


def _lay_area(area: _Page, notes: _NoteShape, paras: list[_Para], top: int,
              balance: bool) -> tuple[list[tuple[int, int]], list[int]]:
    """The (frame, vertpos) of every line of one column area starting *top* down its first page (its lines
    counted from there: its first page is that much shorter), and its lines per paragraph. With *balance*, the
    columns of its last page are as short as they can be with every line still on that page."""

    columns = area.columns
    first = {frame: [(area.body - top, area.body)] for frame in range(columns)} if top else {}
    paginator = _Paginator(area.body, columns, notes, first, area.widths, {})
    last = (paginator.run(paras) - 1) // columns
    if balance and columns > 1:
        low, high = 0, area.body - (top if last == 0 else 0)
        while low < high:
            middle = (low + high) // 2
            ends = {frame: [(middle, area.body)] for frame in range(last * columns, (last + 1) * columns)}
            trial = _Paginator(area.body, columns, notes, {**first, **ends}, area.widths, {})
            if (trial.run(paras) - 1) // columns == last:
                paginator, high = trial, middle
            else:
                low = middle + 1
    return paginator.out, paginator.counts


def _assemble(layouts: list[_SectionLayout]) -> PageEstimate:
    pages = 0
    lines: list[tuple[EstimatedLine, ...]] = []
    for layout in layouts:
        start = 0
        places = layout.places or [(frame // layout.columns, frame % layout.columns) for frame, _ in layout.lines]
        for count in layout.counts:
            lines.append(tuple(
                EstimatedLine(pages + page, column, vertpos)
                for (page, column), (_, vertpos) in zip(places[start:start + count], layout.lines[start:start + count])
            ))
            start += count
        pages += layout.pages if layout.places is not None else (layout.frames - 1) // layout.columns + 1
    return PageEstimate(pages, tuple(lines), ())


# Preserve the original import paths while keeping every source file inspectable.

_Paginator.__module__ = __name__
_drawn_lines.__module__ = __name__
_paragraph.__module__ = __name__
_wrapped_paragraph.__module__ = __name__
