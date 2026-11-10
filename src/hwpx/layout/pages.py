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
  (1440) on either side of it across the text; one that leaves more (in one column) narrows each line
  of its page whose top is above its foot and whose characters reach below its top, in any paragraph
  on that page (those before its own too), by what it takes, or splits it in two pieces at one height
  with room on both sides, as a square-wrapped object flowing with the text does -- a line running from
  the paragraph's margin to the object or from the object to the margin, the margin on the object's
  side taking no more (the rest of a
  paragraph going on to the next page is broken there as if it were not there); a line keeping its
  layout cache that reaches it stays where it is (beside it); a table or an object reaching it, a
  paragraph holding objects or notes, or one beside two such bands, is not followed. An
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
import math  # noqa: F401
import os
from collections.abc import Collection  # noqa: F401
from dataclasses import dataclass, field, replace  # noqa: F401
from typing import TYPE_CHECKING, Any

from lxml import etree

from ..form_fit.measure import (_DEFAULT_TAB_STOP, _GLYPH_SPACE, _TYPED_NO_BREAK_SPACE, char_advance,  # noqa: F401
                                font_line_height, hancom_line_starts, in_char_units, indented_widths, margins_doubled, paragraph_label, text_style_from_refs)
from ..oxml._document_primitives import _remove_stale_paragraph_layout_cache  # noqa: F401
from ..oxml.namespaces import HH, HP
from ..oxml.paragraph_heading import paragraph_heading  # noqa: F401
from ..oxml.section import _remove_short_paragraph_layout_cache  # noqa: F401
from ..oxml.header_part import HwpxOxmlHeader  # noqa: F401
from ..oxml.section_format import COLUMN_SHARES, _drawn_page_size, _page_margin
from ..oxml.table_sizes import cell_margins_of, grid_widths_of  # noqa: F401

# The imports above are as they were before the split, used below or not: a name they bring stays reachable
# as hwpx.layout.pages.<name>.
# The lower half of the model (see its description). Every name it defines is imported here, used below or
# not: hwpx.layout.pages stays the one namespace the estimate is reached through.
from ._page_measure import (  # noqa: F401
    _OBJECTS, _FLOATING, _MARKS, _SPARE_CUT, _SPARE_CUT_FIXED, _SPARE_DROPPED, _MIN_LINE_WIDTH, _MERGED_ROW_LEAST,
    _NO_WRAP, _MIN_SIDE, _Unsupported, _local, _child, _char_unit_height, _Shape, _para_shape, _pitch, _object_pitch,
    _on, _t_text, _indented, _line_widths, _drawn_labels, _run_text, _cache_lines, _cached_metrics, _Lookups,
    _Measure, _Reach, _Row, _FlowTable, _rows, _table_rows, _cell_spacing, _table_ends, _row_span, _object_alone,
    _objects_among, _table_alone, _size_protected, _cell_height, _margin, _extent_margins, _drawn_lines, _holds_table,
    _pos_offset, _down, _vertical, _page_break, _split_before_text, _uncached, _cell_row, _table_first, _split_rows,
    _pushed_reaches, _line_leads, _line_cuts, _line_blocks, _table_pieces, _Wrap, _Anchor, _Band, _Stacked, _Para,
    _Reflow, _caption, _inline_table_height, _rows_height, _objects_reach, _floating_reach, _wraps_in_cell,
    _cell_extent, _control_place, _cell_band, _BothSides, _beside_one_side, _clear_of, _placed_top_and_bottom,
    _placed_from, _object_before_text, _beside_floating, _table_on_its_own, _table_before_text, _placed_objects,
    _marks, _check_ruby_spacing, _mark_extent, _on_paper, _floating, _text_size, _end_size, _end_ref, _head_size,
    _held_sizes, _char_styles, _line_sizes, _metric_starts, _line_metrics, _drawn_height, _SHADOW_DISTANCE,
    _shadow_drop, _SHADOW_BLUR_STEP, _effect_room, _object_extent, _caption_beside, _inline_content, _shown_control,
    _anchor_line, _extent, _wraps_top_and_bottom, _wrapped_widths, _at_one_height, _lines_of, _repeated_header,
    _spare_cut, _starts_later, _header_moves, _flow_table, _split_block, _block_rest, _lists_lines, _cell_rest,
    _flow_row, _reached, _joined_stays, _split_joined, _lines_fitting, _lines_height,
)

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = ["EstimatedLine", "PageEstimate", "estimate_pages"]


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


def _holds_nothing(runs: list[Any]) -> bool:
    """Whether the runs hold no character, object or control at all (a space is a character)."""

    return all(_local(child) == "t" and not child.text and not len(child) for run in runs for child in run)


def _paper_band(measure: _Measure, page: _Page, paragraph: Any) -> tuple[int, int, bool, tuple[int, ...]] | None:
    """The band of the first object of *paragraph* placed on the paper, if any (see :func:`_paper_bands`)."""

    bands = _paper_bands(measure, page, paragraph)
    return bands[0] if bands else None


def _paper_bands(measure: _Measure, page: _Page, paragraph: Any
                 ) -> tuple[tuple[int, int, bool, tuple[int, ...], _Wrap | None], ...]:
    """For each object of *paragraph* placed on the paper, each on its own as if anchored apart: (top, bottom) in
    the body, whether it is wrapped square leaving a line's room beside it (Hancom sets the text reaching it
    beside it, and the text above or below it as if it were not there), the columns it keeps the lines out of,
    and, in one column, the band the lines of its page reaching it are broken in, those of the paragraphs before
    its own too (one leaving a line's room on neither side of it that its text flow allows has none: the text
    reaching it is not followed)."""

    return tuple(_object_paper_band(measure, page, child) for run in paragraph.findall(f"{HP}run") for child in run
                 if _local(child) in _OBJECTS and _on_paper(child))


def _object_paper_band(measure: _Measure, page: _Page, obj: Any
                       ) -> tuple[int, int, bool, tuple[int, ...], _Wrap | None]:
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
    wrap = None
    if square and not across and page.columns == 1:
        left, right = _square_sides(obj, page)
        if left or right:
            wrap = _Wrap(top, top + tall, page.column_width - left - right, split=left if left and right else 0,
                         paper=True, room=(left, right), column=page.column_width)
    return top, top + tall, square and not across, columns, wrap


def _held_top(page: _Page, paragraph: Any, band: tuple[int, int, bool, tuple[int, ...]]) -> int | None:
    """The top of *band*, the band of *paragraph*'s object placed on the paper or the page, when it pushes the
    lines reaching it below the body's foot and the object keeps to its paragraph's page (see
    :attr:`_Para.held`) -- in one column only; otherwise ``None``."""

    top, bottom, room, _, _ = band
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
    size, refs, sizes = _text_size(measure, runs, paragraph)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    widths: list[float] = _indented(page.column_width - shape.left - shape.right, shape, style)
    end = _end_size(measure, runs, sizes)
    head = _head_size(measure, paragraph, sizes)
    held = _held_sizes(measure, runs, sizes)
    mixed = len(set(sizes)) > 1 or bool(end) or bool(head) or bool(held) or (shape.font_line and bool(sizes))
    looks = _char_styles(measure, paragraph, runs)
    lead = 0  # how far the paragraph's first line goes down below a square-wrapped object's band
    anchor_line = None  # the line the anchored object stands at, when the lines laid out here put it there
    if alone and wrap is None:  # spaces besides it, those that do not fit going on to the next line
        spread = measure.spread_lines(paragraph, runs, page.column_width, end, head, caches=True)
        alone, cached = (False, spread) if spread else (alone, cached)
    if among or beside:
        apart = (*stacked, *(() if square is None else (square,)))
        inline_text, inline_sizes, inline_looks, placed, marked = _inline_content(measure, paragraph, runs, anchored,
                                                                                  apart)
        if wrap is not None:
            if beside or wrap.split or marked:
                raise _Unsupported("objects set as characters among text beside a square-wrapped object")
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            lines, lead = _banded_object_lines(measure, inline_text, widths, inline_sizes, style, shape, wrap, placed,
                                               looks_or_none, end, head)
            cached = _cached_jumps(paragraph, cached) if cached else lines
        elif not cached:
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            tall = _controls_after_wide(measure, runs, objects, widths[0])
            cached = _line_metrics(measure, inline_text, widths, inline_sizes, style, shape, placed, looks_or_none,
                                   marked, end, 0 if tall else head)
            if tall and len(cached) > 1 and tall > cached[1][0]:  # the controls on the line after the table
                cached = (cached[0], (tall, _pitch(shape.kind, shape.value, tall)), *cached[2:])
            if anchored is not None:
                cached, anchor_line = _apart_from_wide(measure, inline_text, widths, inline_sizes, style, placed,
                                                       looks_or_none, marked, cached, size, shape,
                                                       _inline_place(runs, anchored, apart))
    elif not cached and wrap is not None and not alone and text:
        if anchored is not None:
            raise _Unsupported("a top-and-bottom object beside a square-wrapped object")
        widths, firsts = _wrapped_widths(measure, text, widths, size, style, shape, wrap, sizes if mixed else None,
                                         looks)
        cached = _at_one_height(_line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end,
                                              head=head, held=held), firsts)
    elif not cached and not alone and (mixed or looks is not None):
        cached = _line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end, head=head, held=held)
    count = len(cached) or measure.lines(text, widths, size, style)
    pitch = _pitch(shape.kind, shape.value, size)
    table, moves, floor = None, 0, 0
    if alone:
        if wrap is not None:
            raise _Unsupported("an object beside a square-wrapped object")
        controls = _controls_beside(objects[0], runs, widths[0])
        if controls is not None:  # a table too wide for the line beside controls: spaced from its own run's
            size = max(measure.char_height(run.get("charPrIDRef"))  # characters, or those of the runs holding the
                       for run in (controls[0], *controls[1]))  # controls before it on its line when larger
            pitch = _pitch(shape.kind, shape.value, size)
        elif objects[0].find(f"{HP}pos").get("treatAsChar") == "1":  # spaced from the largest character size
            size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # of any of its runs
            pitch = _pitch(shape.kind, shape.value, size)
        own, own_pitch = size, pitch  # the paragraph's own line, as tall as its characters
        count, size, pitch, table = _object_line(measure, objects[0], count, size, pitch, page.column_width, shape)
        if controls is not None:  # the controls after it on an empty line of their own, as tall as the largest
            before, after = controls[1], controls[2]  # characters of the runs holding them; those before it too
            if not any(child.find(f"{HP}autoNum") is not None for run in before for child in run  # when they draw
                       if _local(child) == "ctrl"):  # a number, else they stand on the table's line
                before = []
            heights = [max(measure.char_height(run.get("charPrIDRef")) for run in side) if side else None
                       for side in (before, after)]
            empty = [None if height is None else (height, _pitch(shape.kind, shape.value, height))
                     for height in heights]
            cached = tuple(line for line in (empty[0], (size, pitch), empty[1]) if line is not None)
            count = len(cached)
        pos = objects[0].find(f"{HP}pos")
        offset = _pos_offset(pos, "vertOffset")
        if table is None and pos.get("treatAsChar") != "1" and 0 <= offset < 1 << 31:
            if pos.get("flowWithText") != "0":  # from the paragraph's top down: past the body's foot it goes on
                moves = size if offset or page.alone_at_top else 0  # to the next page's top alone, the line staying
                if controls is None and not cached and not text:
                    if pos.get("allowOverlap") == "1" and offset < own:  # starting on the line: it goes below its foot
                        lead, size, pitch = size, own, own_pitch
                    else:  # the empty line stays: the next paragraph comes below its foot or the line's advance
                        floor, pitch = size, own_pitch
            else:  # it stays on its page, past the foot if it must: only the paragraph's line has to fit there,
                cached = ((own, size),)  # the next paragraph coming below the object
                if controls is None and not text:
                    cached, floor = ((own, own_pitch),), size  # (_Para.floor)
    anchor = None if anchored is None else _anchor(measure, paragraph, runs, text, anchored, widths, size, style,
                                                   cached, count, anchor_line)
    around = 0 if square is None or not text else _anchor_line(measure, paragraph, runs, text, square, widths,
                                                                size, style, cached, count)
    if among and _note_anchors(runs, in_tables=True):
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
        para = replace(para, moves=moves, own=own)
    if floor:
        para = replace(para, floor=floor)
    if alone and table is not None and controls is None and not text and pos.get("allowOverlap") == "1"             and 0 <= offset < own:  # allowed to overlap, starting on the line: the line goes below it
        para = replace(para, under=True)
    if alone and table is None and controls is None and not text and _rises(objects[0], page.column_width):
        up = _pos_offset(objects[0].find(f"{HP}pos"), "vertOffset") - (1 << 32)
        para = replace(para, rises=(up, _extent(objects[0], "height", measure), own, own_pitch))
    if page.rebreak and not _cached_metrics(paragraph) and not objects and not marks and not notes:
        if not text:
            return replace(para, blank=True)
        return replace(para, reflow=_Reflow(measure, text, tuple(sizes), None if looks is None else tuple(looks),
                                            style, shape, width=page.column_width, end=end, head=head))
    return para


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
    number, a field, a bookmark, a header and so on -- but not a column definition, nor the end of a field, which
    takes no place on a line) stand beside it in its paragraph, else ``None``: Hancom sets the controls before it
    on the table's line (on an empty line of their own above it when they show a number) and the controls after it
    on the line after that."""

    if obj.find(f"{HP}pos").get("treatAsChar") != "1" or _extent(obj, "width") <= width:
        return None
    home, before, after = None, [], []
    for run in runs:
        for child in run:
            if child is obj:
                home = run
            elif _local(child) == "ctrl" and any(_local(kind) not in ("colPr", "fieldEnd") for kind in child):
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


def _square_object(objects: list[Any], runs: list[Any], column: int) -> Any:
    """The one object of a paragraph wrapped square across the column, from the top of the line its control
    falls on (:func:`_square_anchor_line`), or ``None`` (:func:`_square_sides` says where the text goes beside
    it)."""

    placed = [obj for obj in objects if obj.find(f"{HP}pos").get("treatAsChar") != "1"]
    if len(placed) != 1:  # objects set as characters stand on the lines beside it
        return None
    obj = placed[0]
    pos = obj.find(f"{HP}pos")
    if obj.get("textWrap") != "SQUARE" or _wraps_top_and_bottom(obj, column):
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
    the paragraph or the paper's left or right (from the paper only in one column, and from its centre too)."""

    pos = obj.find(f"{HP}pos")
    width, offset = _extent(obj, "width"), _pos_offset(pos, "horzOffset")
    if offset >= 1 << 31:  # kept unsigned: one placed out past the edge
        offset -= 1 << 32
    if pos.get("horzRelTo") == "PAPER":
        if page.columns > 1:
            raise _Unsupported(f"{_local(obj)} wrapped square from the paper in columns")
        start = _paper_left(obj, page)
        if start is None:
            raise _Unsupported(f"{_local(obj)} wrapped square from the paper otherwise than from its left, centre "
                               "or right")
        start -= page.left
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
    square = _square_object(objects, runs, page.column_width)
    bare = len(objects) == 1 and not _run_text(runs) and not _marks(runs) and not _note_anchors(runs) \
        and not measure.headed(paragraph)
    pusher = _pushing_object(objects, _run_text(runs), page.column_width, bare)
    if bare and pusher is not None and not _clear_of_its_band(measure, page, paragraph, pusher):
        pusher = None  # the next line reaches the object's band anyway: laid out as the object alone
    if moved:  # the object went on to the next page's top: the paragraph's lines as if it were not there
        # the object: wrapped square, pushing the lines below it, or alone below the empty line (a table that
        # may split goes on over the page end instead; of tables, only one set not to split, wrapped square or
        # alone at its paragraph's top, is followed)
        alone = objects[0] if len(objects) == 1 and objects[0].find(f"{HP}pos").get("treatAsChar") != "1" else None
        obj = square if square is not None else pusher if pusher is not None else alone
        if obj is not None and obj is square and wrap is None and _local(obj) == "tbl" \
                and obj.get("pageBreak", "CELL") != "NONE":  # it splits over the page end instead
            return replace(_paragraph(measure, page, paragraph, None, obj), spans=_spans(measure, page, obj)), None
        at_top = obj is alone and pusher is None
        kept = obj is not None and obj is pusher and _local(obj) == "tbl" and obj.get("pageBreak") == "NONE"
        # (a table not split, below the first line of a paragraph of text: the line stays where it fits and the
        # table goes on whole)
        if obj is None or wrap is not None or _local(obj) == "tbl" and not kept and (
                obj is not square and not at_top
                or obj.get("pageBreak", "CELL") not in ("NONE", "TABLE" if at_top else "NONE")):  # one moved row by
            # row goes on whole too, when it is its paragraph's top (see _Paginator._anchored)
            raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        tall = _extent(obj, "height", measure)
        if _local(obj) == "tbl":  # as tall as its rows
            tall += _rows_height(measure, obj) - int(obj.find(f"{HP}sz").get("height", 0))
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
        if wrap is not None and not wrap.push and square is None and _below_the_band(measure, runs, wrap):
            wrap = None  # every line of the paragraph goes below its object's foot, under the band
        if wrap is not None and (square is not None or pusher is not None or (wrap.push and placed)
                                 or _on(shape.flags, "pageBreakBefore")
                                 or paragraph.get("pageBreak") == "1" or paragraph.get("columnBreak") == "1"):
            raise _Unsupported("a page break or another object beside a square-wrapped object")
    if pusher is not None:
        para = replace(_paragraph(measure, page, paragraph, None, pusher), bare=bare)
        offset = _pos_offset(pusher.find(f"{HP}pos"), "vertOffset")
        if not para.wrap_anchor:  # on the first line: from the paragraph's top, above its spacing (on a later
            offset -= para.prev  # line, from that line's top)
        if _local(pusher) == "tbl" and pusher.get("pageBreak", "CELL") in ("CELL", "TABLE"):  # it flows
            rows, cells = _table_rows(measure, pusher)
            ends = _table_ends(pusher)
            table = _FlowTable(rows, _page_break(pusher), pusher.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_caption(measure, pusher), cut=_spare_cut(pusher))
            return replace(para, band=_Band(para.wrap_anchor, offset, table)), None
        top = para.span(0, para.wrap_anchor) + offset
        tall = _extent(pusher, "height", measure)
        if _local(pusher) == "tbl":  # as tall as its rows
            tall += _rows_height(measure, pusher) - int(pusher.find(f"{HP}sz").get("height", 0))
        return _push(para, _Wrap(top, top + tall, 0, push=True), starts=True)
    if wrap is not None and wrap.push:  # objects set as characters on a line reaching it go below it with it
        return _push(_paragraph(measure, page, paragraph), wrap, starts=False)
    if wrap is not None and objects and not placed and not _run_text(runs).strip():
        para = _paragraph(measure, page, paragraph)  # one object set as a character, alone: beside it, even
        if len(objects) > 1:  # wider than the room
            raise _Unsupported("objects set as characters beside a square-wrapped object")
        beside = sum(1 for line in range(para.lines) if para.span(0, line) < wrap.bottom)
        return replace(para, wrap_lines=beside, wrap_stays=wrap.stays, wrap_free=wrap.stays), \
            wrap.lower(para.span(0, para.lines) + para.next)
    starts = square is not None
    if square is not None:
        top = _pos_offset(square.find(f"{HP}pos"), "vertOffset")
        line = _square_anchor_line(measure, page, paragraph, runs, square)
        unwrapped = _paragraph(measure, page, paragraph, None, square)
        if line:  # after text: from the top of its line, the lines above it the column's whole width
            top += unwrapped.span(0, line)
        else:  # on the first line: from the paragraph's top, above its spacing
            top -= unwrapped.prev
        left, right = _square_sides(square, page)
        if not left and not right:
            raise _Unsupported(f"{_local(square)} wrapped square leaving little room for text")
        tall = _extent(square, "height", measure)
        if _local(square) == "tbl":  # as tall as its rows
            tall += _rows_height(measure, square) - int(square.find(f"{HP}sz").get("height", 0))
        stays = square.find(f"{HP}pos").get("flowWithText") == "0"
        if left and right:
            wrap = _Wrap(top, top + tall, page.column_width - left - right, split=left, stays=stays)
        else:
            wrap = _Wrap(top, top + tall, page.column_width - left - right, stays=stays)
    if square is not None and len(objects) > 1 and not _run_text(runs).strip():  # objects set as characters, alone:
        para = _paragraph(measure, page, paragraph, None, square)  # their line beside it, even wider than the room
        if len(objects) > 2:
            raise _Unsupported("objects set as characters beside a square-wrapped object")
        beside = sum(1 for line in range(para.lines) if para.span(0, line) < wrap.bottom)
        return replace(para, wrap_lines=beside, wrap_bottom=wrap.bottom, wrap_fixed=bool(_cached_metrics(paragraph)),
                       wrap_stays=wrap.stays, wrap_free=wrap.stays), wrap.lower(para.span(0, para.lines) + para.next)
    para = _paragraph(measure, page, paragraph, wrap, square)
    if wrap is not None and (para.anchor is not None or para.table is not None):
        raise _Unsupported("an object beside a square-wrapped object")
    if wrap is None:
        return para, None
    lead = para.prev - shape.prev  # its first line moved below the band
    if wrap.split and not para.cached and para.lines == 1 and lead < wrap.bottom and not _run_text(runs) \
            and lead + para.height(0) > wrap.top \
            and all(obj is square for obj in objects):  # an empty line beside it: two empty pieces
        para = _in_two_pieces(para)
    beside = sum(1 for line in range(para.lines) if lead + para.span(0, line) < wrap.bottom)
    para = replace(para, wrap_lines=beside, wrap_bottom=wrap.bottom if starts else 0,
                   wrap_fixed=bool(_cached_metrics(paragraph)), wrap_stays=wrap.stays,
                   wrap_free=wrap.stays and (bool(_cached_metrics(paragraph)) or not _run_text(runs).strip()))
    return para, wrap.lower(lead + para.span(0, para.lines) + para.next)


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


def _in_two_pieces(para: _Para) -> _Para:
    """*para*, one empty line, as Hancom writes it beside an object with text on both sides: two pieces at
    one height."""

    return replace(para, lines=2, cached=((para.size, 0), (para.size, para.pitch)))


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


class _Paginator:
    """Frames (a page's columns, in order) and vertical positions of every line of a section."""

    def __init__(self, body: int, columns: int, notes: _NoteShape,
                 bands: dict[int, list[tuple[int, int]]] | None = None, widths: tuple[int, ...] = (),
                 sides: dict[int, list[tuple[int, int]]] | None = None, alone_at_top: bool = True,
                 squares: dict[int, list[_Wrap]] | None = None) -> None:
        self.body = body
        self.alone_at_top = alone_at_top  # see _Page.alone_at_top
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
        self.object_floor: tuple[int, int] | None = None  # (frame, where the next paragraph starts at the highest): an empty paragraph's object
        self.table_end = 0      # the last frame a flowing table reaches
        self.reserved: dict[int, int] = {}  # frames a table starting past its anchor takes: where text starts
        self.wrap_frame = -1                  # the frame a square-wrapped object's band is on
        self.wrap_moved = False  # that band passed the body's foot: the object went on to the next page
        #: frame -> the bands of square-wrapped objects there that the text there is broken beside: one that
        #: went on to its top (see :attr:`_Para.moved`), the parts of tables split over its ends, the objects
        #: placed on the paper leaving a line's room beside them (see :func:`_paper_bands`)
        self.squares: dict[int, list[_Wrap]] = {frame: list(found) for frame, found in (squares or {}).items()}
        #: frames whose band is a top-and-bottom object that went on to their top (see :meth:`_move_band`)
        self.moved_tops: set[int] = set()
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
        if para.grid:  # its first line on the line grid, at the first step from where it would go
            start = -(-start // para.grid) * para.grid
        if self.object_floor is not None and self.object_floor[0] == self.frame:  # below an empty paragraph's
            start = max(start, self.object_floor[1])                             # object (_Para.floor)
        self.object_floor = None
        if self.under is not None:  # the table before went on past its anchor line's page: the line reaching it
            # goes right under its end, as under any object's band, and a column break lands there, in the
            # column after the anchor line's (or the first one clear of the table)
            start, self.under = self.under, None
            if para.column_break and not para.page_break and not para.break_before:
                para = replace(para, column_break=False)
        if self.floor is not None:
            start, self.floor = max(start, self.floor), None
        if (para.stack or para.band is not None or para.table is not None or para.anchor is not None) \
                and any(not band.paper for frame in (self.frame, self.frame + 1) for band in self.squares.get(frame, ())):
            raise _Unsupported("objects or a table beside a square-wrapped object moved to the next page")
        if para.rises is not None and self.last_vp is not None:
            para, start = self._below_a_rising_object(index, paras, para, start)
        if para.stack:
            self._stacked(index, paras, para, start)
            return
        if self.band is not None and (para.page_break or para.break_before) and not para.column_break \
                and para.band is None and para.table is None and para.anchor is None and not para.notes \
                and not para.wrap_bottom:  # a page break before a table's band comes: the table stays where it
            # stands and the paragraph starts the page after the one the table ends on
            end_frame = self.band[3]
            self.band = None
            if end_frame != self.frame:
                self.frame, self.page_notes = end_frame, [0, 0]
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
        anchor = para.wrap_anchor if para.wrap_push else 0
        ahead = para.span(0, anchor)  # its anchor line below the paragraph's first, the object offset from it
        if anchor and start + para.span(0, anchor - 1) + para.height(anchor - 1) <= self.body \
                < start + ahead + para.height(anchor):  # the anchor line goes on to the next page, the object
            if self.reserved.get(self.frame + 1, 0) + reach - ahead > self.body:  # with it, from its top there
                raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        elif reach and start + reach > self.body and self.columns == 1 and start < self.body \
                and (para.wrap_push or start + para.own <= self.body):  # the empty line fits where it stands:
            raise _BandMoves(index)  # its object goes on to the next page's top, its lines stay (starting past
            # the foot, the paragraph goes on to the next page, the object with it)
        elif para.wrap_push and para.wrap_shift and not anchor and self.columns == 1 \
                and start + para.height(0) > self.body \
                and start - para.wrap_shift + para.height(0) <= self.body:  # its first line fits where
            raise _BandMoves(index)  # it stands, not below the object: the object goes on to the next page's top
        first = len(self.out)
        if self._lay(index, paras, para, start, broke):
            last = self.laid or para
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], last.advance(last.lines - 1), para.next
            if para.floor:
                self.object_floor = (self.out[-1][0], self.out[-1][1] + para.floor)
        if para.wrap_bottom:  # the band starts here: it stays on the page of its anchor line
            self.wrap_frame, line = self.out[first + anchor]
            self.wrap_moved = line - ahead + para.wrap_bottom - para.wrap_shift > self.body \
                and not para.wrap_stays
        if self.wrap_moved and not para.wrap_fixed and (para.wrap_bottom or para.wrap_lines):
            if para.wrap_bottom and self.columns == 1:  # its object goes on to the next page's top: again
                raise _BandMoves(index)
            raise _Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        beside = self.out[first + anchor:first + para.wrap_lines]  # (the lines before its anchor line above it)
        if not para.wrap_fixed and not para.wrap_free and any(frame != self.wrap_frame for frame, _ in beside):
            raise _Unsupported("a page break beside a square-wrapped or offset top-and-bottom object")

    def _below_a_rising_object(self, index: int, paras: list[_Para], para: _Para, start: int) -> tuple[_Para, int]:
        """Hancom places an object top and bottom up from its paragraph's top (``_Para.rises``) from where that
        top would be, and moves the lines before it on the page that reach into its band (their foot below its
        top) to its foot, the lines after them following as they stood; the paragraph's own line then comes
        after them, clear of the object. (The paragraph, where it starts.)"""

        up, tall, own, own_pitch = para.rises  # type: ignore[misc]
        top, foot = start + up, start + up + tall
        lines: list[tuple[int, int]] = []  # (place in self.out, its line's height), newest first
        at = len(self.out)
        for before in range(index - 1, -1, -1):
            count = self.counts[before]
            for line in range(count - 1, -1, -1):
                at -= 1
                lines.append((at, paras[before].height(line)))
            if at <= 0 or self.out[at][0] != self.frame or self.out[at][1] + paras[before].height(0) <= top:
                break
        reaching = [place for place, height in lines
                    if self.out[place][0] == self.frame and self.out[place][1] + height > top]
        if not reaching:
            return para, start
        first = min(reaching)
        moved = [place for place, _ in lines if place >= first]
        owners = {before for before in range(index) if sum(self.counts[:before]) <= max(moved)
                  and sum(self.counts[:before + 1]) > first}
        if any(paras[before].table is not None or paras[before].anchor is not None or paras[before].band is not None
               or paras[before].stack or paras[before].notes or paras[before].rises is not None for before in owners):
            raise _Unsupported("objects among the lines a top-and-bottom object placed up moves below it")
        shift = foot - self.out[first][1]
        heights = dict(lines)
        for place in moved:
            frame, line_top = self.out[place]
            if line_top + shift + heights[place] > self.body:
                raise _Unsupported("lines a top-and-bottom object placed up moves past the page foot")
            self.out[place] = (frame, line_top + shift)
        self.last_vp = self.out[-1][1]
        start = self.last_vp + self.last_pitch + self.pending_next + para.prev
        return replace(para, size=own, pitch=own_pitch), start

    def _flow(self, para: _Para, table: _FlowTable, start: int) -> None:
        if self.last_vp is not None and start + para.height(0) > self.body:  # the anchor line goes on
            start = self._next_frame(para, 0, True)                         # to the next page
            if self.reserved.get(self.frame) and start + para.height(0) > self.body:  # below a table started
                start = self._next_frame(para, 0, True)  # past its anchor there, ending too low for it: the page after
        if self._below_bands(start) != start:
            if self.frame not in self.moved_tops:
                self._flow_below_band(para, table, self._below_bands(start))
                return
            start = self._below_bands(start)  # below an object that went on to this page's top: as at the top
        if para.under and not _starts_later(table, start - para.prev + table.offset + table.above, self.body):
            self._flow_below_band(para, table, start - para.prev)  # from the paragraph's top, the line below it
            return
        self.out.append((self.frame, start))  # the anchor paragraph's line, under the table's top
        if not para.kept:
            self._reach(self.frame, start, start + para.height(0))
        before = self.frame
        top = start - para.prev + table.offset + table.above  # from the paragraph's top, above its spacing
        # the notes already on the page keep their room at its foot, all but the separator's width: the rows
        # end above them there, as if they started that much lower (on the pages after, the table goes on
        # below the header as ever)
        noted = self.notes.area(*self.page_notes) - (self.notes.line if self.page_notes[1] else 0)
        frame, end = _flow_table(table, self.frame, top + noted, self.body)
        if frame == self.frame:
            end -= noted
        later = start + para.height(0) <= self.body and _starts_later(table, top + noted, self.body)
        if self.frame + 1 in self.moved_tops and frame > self.frame and (later or (frame, end) == _flow_table(
                table, self.frame + 1, _repeated_header(table) + table.margins[0], self.body)):  # it goes on to
            below = max(bottom for _, bottom in self.bands[self.frame + 1])  # the next page whole: below the
            frame, end = _flow_table(table, self.frame + 1, below + table.above, self.body)  # object there
        if para.notes and frame == self.frame:
            height = self.page_notes[0] + sum(note[0] for note in para.notes.values())
            many = self.page_notes[1] + sum(note[1] for note in para.notes.values())
            if end > self.body - self.notes.area(height, many):
                raise _Unsupported("a flowing table overlapping its footnotes")
        self._clear_of_paper(before, frame, start, end)
        self.table_end = max(self.table_end, frame)
        if later:
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
            for height, many, _ in para.notes.values():  # the notes in its cells take room at the page's foot
                self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]

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
        else:  # at the top of the paragraph's first line: from the paragraph's top, above its spacing before,
            # below an object placed on the paper, as the line
            top = self._below_bands(top - para.prev)
        if anchor.table is not None:
            table = anchor.table
            later = _starts_later(table, top + table.above, self.body)
            if later and para.spaced and not head.lines:  # spaces only: as the table alone in its paragraph,
                line = para.cached[0][0] if para.cached else para.size  # its line staying where it fits
                if start + line <= self.body:
                    self._flow(replace(para, anchor=None, table=table), table, start)
                    return
                top, later = self._next_frame(para, 0, True) - para.prev, False  # where it does not: the line
                # goes on with the table, below it
            moves = not head.lines and top != self.reserved.get(self.frame, 0)
            whole = table.mode == "NONE" or later and table.mode in ("TABLE", "CELL")  # moved row by row or
            # split cell by cell, its first row with no room on this page: it goes on as one, as one set not to
            # split
            if moves and whole and later and self.alone_at_top and self.columns == 1 \
                    and top + tail.height(0) <= self.body:  # with no room below the line's top:
                raise _BandMoves(index)  # to the next page's top alone, the paragraph's lines staying
            if moves and whole:  # set not to split
                moves = later or top + table.above + sum(row.height for row in table.rows) + table.below \
                    + tail.height(0) > self.body
            elif moves:  # ending on this page (a row split by cells: its room to spare cut there) but not the line
                frame, end = _flow_table(table, self.frame, top + table.above, self.body)
                moves = frame == self.frame and end + table.below + tail.height(0) > self.body
            if moves:  # it goes on with the line below it
                top, later = self._next_frame(para, 0, True), False
            if later:
                raise _Unsupported("a top-and-bottom table anchored in text that starts on the next page")
            frame, end = _flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame, top, end, below=True)
            self.frame, self.table_end, end = frame, max(self.table_end, frame), end + table.below
        else:
            if top + anchor.height > self.body and top > 0:
                if self.alone_at_top and not anchor.stays and self.columns == 1 \
                        and top + tail.height(0) <= self.body:  # it goes on
                    raise _BandMoves(index)  # to the next page's top alone, the paragraph's lines staying
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
                or (self.band is not None and (para.page_break or para.break_before or para.column_break)):
            raise _Unsupported("a page break or another object beside a top-and-bottom table's band")
        start, broke = self._breaks(para, start)
        if self.band is not None and para.band is not None:  # its own table's band after another's
            frame, top, bottom, end_frame, end = self.band
            if self.frame != frame or start + para.height(0) <= top:
                raise _Unsupported("a page break or another object beside a top-and-bottom table's band")
            self.band = None
            if bottom is None or start < bottom:  # its first line reaches the other table: the paragraph goes
                if end_frame != self.frame:  # below that table's end, its own table placed from there
                    self.frame, self.page_notes = end_frame, [0, 0]
                start = end + para.prev
            self._banded(index, paras, para, start)
            return
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
                    and (bottom is None or start + para.span(0, line) < bottom)
                    and not (line == 0 and para.bare and para.band is not None)]  # its own empty line stays
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
            if frame in self.moved_tops:  # an object that went on to its top: a table starts below it, and one
                continue                  # going on from the page before goes on over it
            low = top if frame == first else 0
            high = end if frame == last and end is not None else self.body
            self._reach(frame, low, high)
            touching = below and frame == first
            if any(above < high and (low < bottom if touching else low <= bottom)
                   for above, bottom in self.bands.get(frame, ())):
                stacked = frame in self.stacked
                raise _Unsupported("a table on a page with objects stacked in an empty paragraph" if stacked
                                   else "a table on a page with an object placed on the paper")

    def _reach(self, frame: int, top: int, bottom: int, broken: bool = False) -> None:
        """Note whether something from *top* to *bottom* in *frame* reaches the band of an object placed on
        the paper that leaves a line's room beside it, other than a line *broken* beside it."""

        if any(top < foot and bottom > head for head, foot in self.sides.get(frame, ())) \
                or not broken and any(band.paper and top < band.bottom and bottom > band.top
                                      for band in self.squares.get(frame, ())):
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
        table takes, below the table. Another such table from the same page starts on the page after the last
        the one before it takes, at its top."""

        taken = range(self.frame + 1, frame + 1)
        if any(page in self.reserved for page in taken):  # one did before it from this page: it starts at the
            first = max(page for page in self.reserved if page > self.frame) + 1  # top of the page after that one's
            frame, end = _flow_table(table, first, table.margins[0], self.body)
            taken = range(first, frame + 1)
            self.table_end = max(self.table_end, frame)
        self.reserved.update(dict.fromkeys(taken, self.body))
        self.reserved[frame] = end + table.below
        self.last_vp, self.last_pitch, self.pending_next = start, para.advance(para.lines - 1), para.next

    def _breaks(self, para: _Para, start: int) -> tuple[int, bool]:
        if self.last_vp is None:
            return start, False
        if para.page_break or para.break_before:
            self.frame = (self.frame // self.columns + 1) * self.columns
            while self.frame in self.moved_tops or self.frame in self.reserved:  # a page an object or a table
                self.frame += self.columns  # started past its anchor went on to: the break starts after it
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
            if para.held is not None and first_chunk and not fresh and start < self.body \
                    and start + para.advance(0) > para.held:
                start, below = self.body, True  # its object's band, on this page, takes its first line: both go on
                continue
            hit = self._band_hit(para, done, remaining, start)
            if hit is not None and para.reflow is not None and para.reflow.wrapped:
                raise _Unsupported("lines beside a square-wrapped object reaching an object placed on the paper")
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
                if para.reflow is not None and para.reflow.wrapped:  # broken beside a band of the page before:
                    para = para.reflow.at(para, para.reflow.width, line)  # the rest as if it were not there
                    remaining, line = para.lines, 0
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
        if band.paper and (para.kept or start + para.span(line, para.lines - 1 - line) + para.height(para.lines - 1)
                           <= band.top):  # a line keeping its layout cache stays where it is
            return para
        if para.reflow is None and band.paper:
            raise _Unsupported("objects or notes beside a square-wrapped object placed on the paper")
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
            self.moved_tops.add(target)
        else:
            self.squares.setdefault(target, []).append(band)
        self.table_end = max(self.table_end, target)

    def _next_frame(self, para: _Para, count: int, first_chunk: bool) -> int:
        self.frame += 1
        self.page_notes = [self.carry, 1] if self.carry else [0, 0]
        return self._free_top() + (para.prev - para.lead if count == 0 and first_chunk else 0)

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
            count = self._keep_with_next(para, paras[index + 1:], start, remaining, count)
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

    def _keep_with_next(self, para: _Para, following: list[_Para], start: int, remaining: int, count: int) -> int:
        """*count*, or 0 when the paragraph set to stay with the next has to go on to the next frame. Its last
        line stays with the next paragraph's first line (two under the widow and orphan rule); so does each
        paragraph after it set so too (a chain). A paragraph of the chain that reaches the frame's foot
        splits there as any other, the chain before it staying; one that has to go on to the next frame
        whole takes the whole chain before it along. A paragraph at the frame's top stays."""

        if start == para.prev:
            return count
        saved, carry = list(self.page_notes), self.carry
        try:
            return self._chain_stays(para, following, start, remaining, count)
        finally:
            self.page_notes, self.carry = saved, carry

    def _chain_stays(self, para: _Para, following: list[_Para], start: int, remaining: int, count: int) -> int:
        for line in range(remaining):  # the notes of the lines placed take room below the chain
            height, many, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]
        after = start + para.span(0, remaining) + para.next
        for item in following:
            after += item.prev
            if not item.keep_next or item.table is not None or item.page_break or item.break_before \
                    or item is following[-1]:
                need = 2 if item.widow_orphan and item.lines > 1 else 1
                return count if self._fits(after, need, item) >= need else 0
            fit = self._fits(after, item.lines, item)
            if fit == item.lines:
                after += item.span(0, item.lines) + item.next
                for height, many, _ in item.notes.values():
                    self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]
                continue
            # it splits at the foot, its first lines staying with the paragraph before; or it goes on whole
            return count if fit and not item.keep_lines else 0
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
            limit = self.body - self.notes.area(height + note_height, many + notes)
            if bottom < limit or para.moves and para.own and start + para.own < limit and bottom == limit:
                # (an object alone in an empty paragraph may end at the foot, its own line not)
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
                self._reach(frame, top, top + para.height(line), broken=True)


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
    if not page.rebreak and any(band[4] is not None for objects in paper.values() for band in objects):
        return _paginate(measure, section, replace(page, rebreak=True), notes, moved)  # lines broken beside them
    bands: dict[int, list[tuple[int, int]]] = {}
    sides: dict[int, list[tuple[int, int]]] = {}
    squares: dict[int, list[_Wrap]] = {}
    # an object placed on the paper acts on the page its paragraph lands on (each settled one may move the pages
    # of those after it: a try more for each)
    for _ in range(max(4, min(len(paper) + 2, 24))):
        paginator = _Paginator(page.body, page.columns, notes, bands, page.widths, sides, page.alone_at_top,
                               squares)
        frames = paginator.run(paras)
        firsts = [0]
        for count in paginator.counts:
            firsts.append(firsts[-1] + count)
        placed: dict[int, list[tuple[int, int]]] = {}
        beside: dict[int, list[tuple[int, int]]] = {}
        wrapped: dict[int, list[_Wrap]] = {}
        for index, objects in paper.items():  # each on the columns of the page it reaches over
            first = paginator.out[firsts[index]][0] // page.columns * page.columns
            for top, bottom, room, columns, wrap in objects:
                for column in columns:
                    if wrap is not None:
                        wrapped.setdefault(first + column, []).append(wrap)
                    else:
                        (beside if room else placed).setdefault(first + column, []).append((top, bottom))
        if placed == bands and beside == sides and wrapped == squares:
            break
        bands, sides, squares = placed, beside, wrapped
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
