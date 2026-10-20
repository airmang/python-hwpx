# SPDX-License-Identifier: Apache-2.0
"""Write the line layout cache Hancom writes, for the paragraphs the page estimate lays out (experimental).

Hancom Office saves every paragraph with a line layout cache (``hp:linesegarray``): where each line starts in
the text, its place on the page and its metrics. python-hwpx writes new paragraphs without one, and Hancom lays
them out when it opens the document. :func:`write_line_caches` gives the body's plain text paragraphs the cache
Hancom would write for them, so the file is laid out as Hancom saves it and a viewer that draws from the cache
shows the lines where Hancom puts them.

Hancom takes a line's height, text height, baseline and spacing from the cache as written, and where each line
starts in the text too (a line short of a break is drawn with its text pressed together); it lays out a line's
place and width again. Those four are written as Hancom writes them: the character size, 85 % of it for
the baseline and the line spacing past it. The others come from :func:`hwpx.layout.pages.estimate_pages`. Hancom
also draws a tab as wide as its ``hp:tab`` says once the paragraph has a cache, so each tab gets its width.

Only a paragraph Hancom would lay out from its text alone gets a cache: a body paragraph of text runs in a
section of one column where no object lets text run beside it. Tabs to the default tab stops, line breaks,
controls that take no room on a line (a header, a footer, a page number, the section's own definitions in its
first paragraph), the start and end of a field (a hyperlink, a click-here field, a date, a mail merge field) anywhere in the text but
in a section's first paragraph, a
highlight and a hanging bullet or number label in the paragraph's size are fine. Its runs may differ in
face, each character taking its own run's advance, and in size: each line is then as tall as its largest
character, unless a larger one past the line's end may be the one that did not fit on it (Hancom writes the line as
tall as that one), and has no tab; a larger empty run ending the paragraph makes its last line's text as tall. A
paragraph that sets its characters at the top, the centre or the bottom of their lines gets the baseline Hancom
writes for that (0, half or all of the text height). A table's caption above or below it takes its lines and its
gap in the table's line, when the caption's paragraphs are laid out surely.

The cells of a table in such a section get caches the same way when every paragraph of the cell is one of
these: their lines go down from the top of the cell's text area, as wide as that area in whole layout units and
never narrower than Hancom's narrowest line. A paragraph holding nothing but a table set as a character gets its
one line, as tall as the table, and the table its rows' height (``hp:sz``), as Hancom saves them, when every
paragraph of its cells is laid out surely.

A paragraph is left for Hancom when its line breaks are less sure: a character no glyph table gives an advance
for, a word too long for a line, a line break that moves when every line is laid out :data:`_MARGIN` narrower or
wider (a line ending that close to its room may end elsewhere in Hancom), or a tab whose text before it is closer
to a tab stop than a layout unit for each character since the line's start or the last tab stop (at most
:data:`_MARGIN`). A paragraph that has a cache keeps it. A document mixing paragraphs with and without a cache is
laid out as one. Nothing is written when the estimate does not follow the document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..form_fit.measure import (
    _FIXED_SPACE,
    _GLYPH_SPACE,
    _GLYPHS,
    _HALF_EM_GLYPHS,
    _HALF_EM_SPACES,
    _design_units,
    _hancom_break_opportunities,
    _hangul_units,
    _laid_out_face,
    _line_origin,
    _width_after_tab,
    auto_space_gap,
    char_advance,
    classify_char,
    glyph_face_of,
    tab_reach,
)
from ..oxml.table_sizes import cell_margins_of, grid_widths_of
from . import pages as _pages
from .pages import HH, HP

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = ["LineCacheReport", "write_line_caches"]

#: A line of one segment (its first and its last): what Hancom writes for a line beside nothing.
_ONE_SEGMENT = 0x60000
#: The line takes the paragraph's indent (its first line for a positive one, the others for a hanging one, and
#: the lines after a bullet or number label that hangs).
_INDENTED = 0x100000
#: Hancom's layout unit (1/1800 inch) in HWPUNIT.
_LAYOUT_UNIT = 4
#: How far past a line's end the character that did not fit on it is looked for, at most.
_PAST_A_BREAK = 40
#: The line starts with the paragraph's bullet or number label.
_LABELLED = 0x200000
#: The baseline Hancom writes for a line of text *height* tall, by where its paragraph sets the characters in
#: their lines (``hh:align``'s ``vertical``).
_BASELINES = {
    "BASELINE": lambda height: (height * 85 + 50) // 100,
    "TOP": lambda height: 0,
    "CENTER": lambda height: height // 2,
    "BOTTOM": lambda height: height,
}
#: The faces whose glyphs Hancom Office 2024 was seen to lay out at the advances FormFit gives them, on the
#: desktop: a face Hancom may draw in another (one not installed, a name no table lists) is left for Hancom.
_SURE_FACES = frozenset({
    "함초롬바탕", "함초롬돋움", "맑은 고딕", "바탕", "바탕체", "돋움", "돋움체", "굴림", "굴림체", "궁서", "궁서체",
    "한컴 고딕", "HY헤드라인M", "HY견고딕", "HY울릉도M", "HY견명조", "HY동녘M", "휴먼명조", "휴먼고딕", "휴먼옛체",
    "한양중고딕", "한양신명조", "한양견고딕", "HCI Poppy", "HCI Hollyhock",
})
#: The faces whose bold characters FormFit lays out at Hancom's advances: their regular ones, or a twentieth of
#: an em wider in 한양신명조 and 한양중고딕. Some bold glyphs of 한양견고딕 and HCI Hollyhock Hancom lays out at
#: other advances: bold characters in them are left.
_BOLD_SURE_FACES = _SURE_FACES - {"한양견고딕", "HCI Hollyhock"}
#: The 장평 (%), 자간 (%) and 최소 공백 (%) Hancom was seen to lay lines out at as FormFit does, on the desktop.
_SURE_RATIOS = (50, 200)
_SURE_SPACINGS = (-30, 30)
_SURE_CONDENSE = 50
#: The glyphs other than Hangul syllables whose advances were seen on the desktop in those faces.
_SURE_GLYPHS = frozenset(_GLYPHS)
#: How much narrower or wider (HWPUNIT) every line may be laid out and still break at the same places for its
#: paragraph to get a cache: a width a little off from Hancom's must not move a line break.
_MARGIN = 100
#: How many characters a control (a section or column definition) takes in a line's text position.
_CONTROL_LENGTH = 8
#: The controls that take no room on a line: page headers and footers, page numbers and the page controls.
_PAGE_CONTROLS = frozenset({"header", "footer", "pageNum", "pageHiding", "pageNumCtrl", "newNum"})
#: The text children a cached paragraph may hold, as python-hwpx reads them into its text. With a cache Hancom
#: draws a tab as wide as its ``hp:tab`` says, so a tab gets the width Hancom lays it out at too.
_TEXT_MARKS = frozenset({"tab", "lineBreak", "nbSpace", "fwSpace"})
#: Marks in the text that take neither room on a line nor a text position: a highlight's start and end.
_EMPTY_MARKS = frozenset({"markpenBegin", "markpenEnd"})
#: The kinds of field whose start and end take no room on a line and eight characters each in a line's text position
#: wherever they stand (one standing where a line breaks starts the next line). A memo's field, or a field in a
#: section's first paragraph, Hancom was seen to save without a cache, so those are left for it.
_FIELD_KINDS = frozenset({"HYPERLINK", "CLICK_HERE", "DATE", "MAILMERGE"})
#: What Hancom writes on a tab that reaches a default tab stop: no leader, a left stop.
_DEFAULT_TAB = {"leader": "0", "type": "1"}


@dataclass(frozen=True)
class LineCacheReport:
    """What :func:`write_line_caches` did: the paragraphs it gave a cache, those it left for Hancom to lay out
    (``skipped``), those that kept their own, and why it wrote nothing (``unsupported``: the first section the
    estimate does not follow) when it did not
    follow the document."""

    written: int
    skipped: int
    kept: int
    unsupported: tuple[str, ...] = ()


def write_line_caches(document: "HwpxDocument") -> LineCacheReport:
    """Give the plain text paragraphs of *document*'s body and table cells the line layout cache Hancom writes
    (experimental).

    See the module description for the paragraphs that get one. The document is changed in memory; save it
    as usual.
    """

    root = document._root
    estimate = _pages._estimate(document, first_reason=True)  # any section not followed: nothing is written
    if estimate.unsupported:
        return LineCacheReport(0, 0, 0, tuple(estimate.unsupported))
    measure = _pages._Measure(root)
    written = skipped = kept = 0
    index = 0
    for section in root.sections:
        page = _pages._page(section.element)
        beside = _wraps_text(section.element)  # lines beside an object are narrower: left for Hancom
        paragraphs = section.element.findall(f"{HP}p")
        lines = estimate.lines[index:index + len(paragraphs)]
        index += len(paragraphs)
        changed = False
        for number, (paragraph, placed) in enumerate(zip(paragraphs, lines)):
            if paragraph.find(f"{HP}linesegarray") is not None:
                kept += 1
                continue
            laid = None if page.columns != 1 or beside else (
                _lines(measure, paragraph, page.column_width, first=number == 0)
                or _table_line(measure, paragraph, page.column_width))
            if laid is None or len(laid[0]) != len(placed):
                skipped += 1
                continue
            segments, tabs = laid
            for segment, where in zip(segments, placed):
                segment["vertpos"] = where.vertpos
            _append_cache(paragraph, segments, tabs)
            written += 1
            changed = True
        if page.columns == 1 and not beside:
            for table in (child for paragraph in paragraphs for run in paragraph.findall(f"{HP}run")
                          for child in run if _pages._local(child) == "tbl"):
                cells = _cell_caches(measure, table)
                written += cells[0]
                skipped += cells[1]
                kept += cells[2]
                changed = changed or bool(cells[0])
        if changed:
            section.mark_dirty()
    return LineCacheReport(written, skipped, kept)


def _table_line(measure: Any, paragraph: Any, width: int) -> tuple[list[dict[str, int]], list[int]] | None:
    """The one line of a paragraph holding nothing but a table set as a character, as Hancom writes it: as tall as
    the table and its outer margins, its baseline at 85 % of that, spaced as the paragraph's characters are; and the
    table's own height (``hp:sz``) set to its rows' height, as Hancom saves it. None for any other paragraph."""

    runs = paragraph.findall(f"{HP}run")
    table = _pages._table_alone(runs)
    if table is None or any(_pages._local(child) not in ("t", "tbl", "secPr", "ctrl") for run in runs for child in run):
        return None
    if any(_pages._local(child) == "ctrl" and not _takes_no_room(child, True) for run in runs for child in run):
        return None
    if not _cells_sure(measure, table):  # the rows are as tall as their cells' lines: those must be sure too
        return None
    if _vertical_align(measure, paragraph.get("paraPrIDRef")) != "BASELINE":
        return None
    if not _caption_sure(measure, table):
        return None
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # spaced from its largest characters
    rows = _pages._inline_table_height(measure, table)
    # a caption above or below the table takes its lines and its gap in the line too, one beside it none
    tall = rows + _pages._extent_margins(table) + sum(_pages._caption(measure, table))
    advance = _pages._object_pitch(shape, table, tall, size)
    table.find(f"{HP}sz").set("height", str(rows))
    room = width - shape.left - shape.right
    return [{
        "textpos": 0,
        "vertpos": 0,
        "vertsize": tall,
        "textheight": tall,
        "baseline": (tall * 85 + 50) // 100,
        "spacing": advance - tall,
        "horzpos": shape.left,
        "horzsize": room,
        "flags": _ONE_SEGMENT | (_LABELLED if measure.headed(paragraph) else 0),
    }], []


def _cells_sure(measure: Any, table: Any) -> bool:
    """Whether every paragraph of *table*'s cells is one this module lays out (none of them a table)."""

    widths = grid_widths_of(table)
    for cell in table.findall(f"{HP}tr/{HP}tc"):
        paragraphs = cell.findall(f"{HP}subList/{HP}p")
        sub_list = cell.find(f"{HP}subList")
        if not paragraphs or _pages._vertical(cell) or sub_list is None \
                or sub_list.get("lineWrap") in ("SQUEEZE", "KEEP"):
            return False
        margins = cell_margins_of(cell, table)
        inner = (widths.get(cell) or int(cell.find(f"{HP}cellSz").get("width", 0))) - margins.left - margins.right
        if any(_lines(measure, paragraph, inner, first=False, cell=True) is None for paragraph in paragraphs):
            return False
    return True


def _cell_caches(measure: Any, table: Any) -> tuple[int, int, int]:
    """Give the paragraphs of *table*'s cells their caches: (written, skipped, kept). A cell gets them when every
    one of its paragraphs is one this module writes; its lines go down from the top of the cell's text area, each
    paragraph's spacing before and after between them, as Hancom stacks them."""

    written = skipped = kept = 0
    widths = grid_widths_of(table)
    for cell in table.findall(f"{HP}tr/{HP}tc"):
        paragraphs = cell.findall(f"{HP}subList/{HP}p")
        if any(paragraph.find(f"{HP}linesegarray") is not None for paragraph in paragraphs):
            kept += len(paragraphs)
            continue
        sub_list = cell.find(f"{HP}subList")
        if not paragraphs or _pages._vertical(cell) or sub_list is None \
                or sub_list.get("lineWrap") in ("SQUEEZE", "KEEP"):
            skipped += len(paragraphs)
            continue
        margins = cell_margins_of(cell, table)
        size = cell.find(f"{HP}cellSz")
        inner = (widths.get(cell) or int(size.get("width", 0))) - margins.left - margins.right
        laid = [_lines(measure, paragraph, inner, first=False, cell=True) for paragraph in paragraphs]
        if any(lines is None for lines in laid):
            skipped += len(paragraphs)
            continue
        top, after = 0, None
        for paragraph, (segments, tabs) in zip(paragraphs, laid):  # type: ignore[misc]
            shape = measure.shape(paragraph.get("paraPrIDRef"))
            top += shape.prev if after is None else after + shape.prev
            for segment in segments:
                segment["vertpos"] = top
                top += segment.pop("advance")
            after = shape.next
            _append_cache(paragraph, segments, tabs)
            written += 1
    return written, skipped, kept


def _lines(measure: Any, paragraph: Any, width: int, *, first: bool,
           cell: bool = False) -> tuple[list[dict[str, int]], list[int]] | None:
    """The line segments Hancom writes for *paragraph* laid out *width* wide (a column, or a cell's text area), but
    for their places down the page, and the width of each of its tabs; None when it is not one this module
    writes. Each segment also holds how far down the next line starts (``advance``)."""

    runs = paragraph.findall(f"{HP}run")
    controls = _control_places(runs, first)
    if controls is None:
        return None
    headed = measure.headed(paragraph)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    vertical = _vertical_align(measure, paragraph.get("paraPrIDRef"))
    if shape.font_line or vertical not in _BASELINES or not _bold_sure(measure, paragraph, runs):
        return None
    size, refs, sizes = _pages._text_size(measure, runs)
    end = _pages._end_size(measure, runs, sizes)
    mixed = len(set(sizes)) > 1 or bool(end)  # each line as tall as its largest character
    looks = _pages._char_styles(measure, paragraph, runs)  # runs of another face, 장평 or 자간: each its own
    if headed and (_pages._head_size(measure, paragraph, sizes) or shape.indent):  # a label of its own size
        return None
    text = _pages._run_text(runs)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    if style is not None and style.head and not (headed and style.head_hangs):
        return None
    if style is not None and style.line_wrap == "SQUEEZE":
        return None  # Hancom presses the paragraph onto one line, as wide as its text: left for it
    if style is not None and (style.auto_space_latin or style.auto_space_digit) and any(
            look.spacing or look.script_size != 1 for look in set(looks or [style])) and any(
            auto_space_gap(a, b, 10, style) for a, b in zip(text, text[1:])):
        return None  # automatic spacing under 자간 or beside a superscript: how Hancom sizes the gap was not pinned down
    room = width - shape.left - shape.right
    widths = _pages._line_widths(shape, width, style) if cell else _pages._indented(room, shape, style)
    if mixed or looks is not None:
        if mixed and "\t" in text:  # a tab among characters of several sizes: its width is less sure
            return None
        def lay_out(room: list[float]) -> list[int]:
            return _pages._metric_starts(measure, text, room, sizes, style, {}, looks)
        starts = lay_out(widths)
        metrics = _pages._line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end)
    else:
        def lay_out(room: list[float]) -> list[int]:
            return measure.line_starts(text, room, size, style) if text else [0]
        starts = lay_out(widths)
        metrics = ((size, _pages._pitch(shape.kind, shape.value, size)),) * len(starts)
    if len(metrics) != len(starts):
        return None
    if mixed and _taller_past_a_break(text, sizes, starts, metrics):
        return None
    if not _sure_of(text, starts, style, looks):
        return None
    if any(lay_out([room + shift for room in widths]) != starts for shift in (-_MARGIN, _MARGIN)):
        return None  # a line break this close to a line's end may fall elsewhere in Hancom
    tabs = _tab_widths(text, starts, widths, size, style, looks) if "\t" in text else []
    if tabs is None:
        return None
    indented = min(widths) < room  # else Hancom dropped the indent: no line takes it
    segments = []
    ends = [*starts[1:], len(text)]
    for line, (start, (height, advance)) in enumerate(zip(starts, metrics)):
        drawn = [sizes[index] for index in range(start, ends[line]) if text[index] != "\n"] if mixed else []
        if end and line == len(starts) - 1:
            drawn.append(end)  # the paragraph's end, larger than its text: the last line's text is as tall
        text_height = max(drawn) if drawn else height  # a line break larger than the text makes the line taller
        if vertical == "CENTER" and text_height % 2:
            return None  # half an odd text height: which way Hancom rounds it was not seen
        takes_indent = (indented and (shape.indent > 0 if line == 0 else shape.indent < 0)) or (headed and line > 0)
        segments.append({
            "textpos": _hancom_offset(text, start, controls) if line else 0,  # the first line starts at 0
            "vertpos": 0,
            "vertsize": height,
            "textheight": text_height,
            "baseline": _BASELINES[vertical](text_height),
            "spacing": advance - height,
            "horzpos": shape.left,
            # a cell's lines in whole layout units, and never narrower than Hancom's narrowest line
            "horzsize": max(room - room % _LAYOUT_UNIT, _pages._MIN_LINE_WIDTH) if cell else room,
            "flags": _ONE_SEGMENT | (_INDENTED if takes_indent else 0) | (_LABELLED if headed and line == 0 else 0),
            "advance": advance,
        })
    if not cell:
        for segment in segments:
            del segment["advance"]
    return segments, tabs


def _sure_of(text: str, starts: list[int], style: Any, looks: list[Any] | None = None) -> bool:
    """Whether the line breaks at *starts* can be trusted to be Hancom's: every character is set in a face of
    :data:`_SURE_FACES` at 장평, 자간 and 최소 공백 within those seen on the desktop, takes an advance a glyph table gives (not a class
    average) and is a Hangul syllable or one of :data:`_SURE_GLYPHS`, and no line starts inside a word that did not
    fit on a line of its own, nor in a paragraph that breaks inside Latin words (where Hancom's breaks beside closing marks
    and wide brackets were not pinned down). Hancom takes the line breaks from a cache as written (a line short of a break is
    drawn with its text pressed together), so a paragraph laid out less surely is left for Hancom."""

    if style is None or style.condense > _SURE_CONDENSE or style.break_latin_word != "KEEP_WORD":
        return False
    if " " in text and (style.condense or any(
            look.spacing or any(spacing for _, _, spacing in look.scripts) for look in set(looks or [style]))):
        return False  # a no-break space among spaces that shrink, or with 자간 (it takes none), is left
    for look in set(looks or [style]):
        if any(not _SURE_RATIOS[0] <= ratio <= _SURE_RATIOS[1] or not _SURE_SPACINGS[0] <= spacing <= _SURE_SPACINGS[1]
               for ratio, spacing in [(look.ratio, look.spacing), *((r, sp) for _, r, sp in look.scripts)]):
            return False  # 장평 and 자간 past those seen on the desktop
        if look.hangul_face not in _SURE_FACES or look.use_font_space and look.glyph_face not in _SURE_FACES:
            return False  # a space of the font's own width in faces that differ by script: not seen
    for ch, look in set(zip(text, looks or [style] * len(text))):
        if ch in "\t\n" or ch in _HALF_EM_SPACES or ch in _HALF_EM_GLYPHS or ch in (_FIXED_SPACE, _GLYPH_SPACE):
            continue
        if classify_char(ch) == "hangul":
            if _hangul_units(_laid_out_face(look.hangul_face), ch) is None:
                return False
        elif (ch not in _SURE_GLYPHS or glyph_face_of(ch, look) not in _SURE_FACES
              or _design_units(_laid_out_face(glyph_face_of(ch, look)), ch) is None):
            return False  # each glyph in its own script's face (see glyph_face_of)
    breaks = _hancom_break_opportunities(text, style)
    return all(start in breaks or text[start - 1] == "\n" for start in starts[1:])


def _bold_sure(measure: Any, paragraph: Any, runs: list[Any]) -> bool:
    """Whether every bold run of *paragraph* holding text is set in faces of :data:`_BOLD_SURE_FACES`."""

    bold = getattr(measure, "_line_cache_bold", None)
    if bold is None:
        bold = {shape.get("id"): shape.find(f"{HH}bold") is not None for shape in measure._header.iter(f"{HH}charPr")}
        measure._line_cache_bold = bold
    for run in runs:
        ref = run.get("charPrIDRef")
        if not bold.get(ref) or not _pages._run_text([run]):
            continue
        style = measure.style(paragraph.get("paraPrIDRef"), [ref], paragraph)
        if style is None or any(face not in _BOLD_SURE_FACES for face in (
                style.hangul_face, style.latin_face or style.glyph_face, style.symbol_face or style.glyph_face)):
            return False
    return True


def _vertical_align(measure: Any, para_pr_id: str | None) -> str | None:
    """Where a paragraph of the shape *para_pr_id* sets its characters in their lines (``hh:align``'s
    ``vertical``): BASELINE (the default), TOP, CENTER or BOTTOM; None for a shape not in the header."""

    aligned = getattr(measure, "_line_cache_vertical", None)
    if aligned is None:
        aligned = {}
        for shape in measure._header.iter(f"{HH}paraPr"):
            align = shape.find(f"{HH}align")
            aligned[shape.get("id")] = "BASELINE" if align is None else align.get("vertical", "BASELINE")
        measure._line_cache_vertical = aligned
    return aligned.get(para_pr_id)


def _caption_sure(measure: Any, table: Any) -> bool:
    """Whether *table*'s caption, if any, takes room Hancom lays out surely: none beside the table, and above or
    below it only when every paragraph of the caption is one this module lays out."""

    caption = table.find(f"{HP}caption")
    if caption is None or caption.get("side") in ("LEFT", "RIGHT"):
        return True
    if caption.get("side") not in ("TOP", "BOTTOM"):
        return False
    width = int(caption.get("lastWidth", 0)) or int(table.find(f"{HP}sz").get("width", 0))
    paragraphs = caption.findall(f"{HP}subList/{HP}p")
    return bool(paragraphs) and all(_lines(measure, p, width, first=False, cell=True) is not None for p in paragraphs)


def _taller_past_a_break(text: str, sizes: list[int], starts: list[int],
                         metrics: tuple[tuple[int, int], ...]) -> bool:
    """Whether a character past a line's end that may be the one that did not fit on it (the next line's first word
    and the character after it) is taller than the line: Hancom then writes the line as tall as that character (its
    text height stays the line's own), which the estimate does not follow."""

    for line, start in enumerate(starts[1:]):
        stop = start
        while stop < len(text) and text[stop] not in " \n" and stop - start < _PAST_A_BREAK:
            stop += 1
        if any(size > metrics[line][0] for size in sizes[start:stop + 1]):
            return True
    return False


def _tab_widths(text: str, starts: list[int], widths: list[float], size: int, style: Any,
                looks: list[Any] | None = None) -> list[int] | None:
    """The width of each tab of *text* as Hancom lays it out on the lines starting at *starts*, every character
    in its own look (*looks*) when they differ; None when a tab does not reach a default tab stop (the
    paragraph's own stops, a tab laid out as a glyph)."""

    if style is None or style.tab_stops or style.auto_tab_left or style.auto_tab_right or not style.tab_stop:
        return None
    points = size / 100
    found: list[int] = []
    ends = [*starts[1:], len(text)]
    for line, (start, end) in enumerate(zip(starts, ends)):
        logical = text.rfind("\n", 0, start) + 1  # the line break before: the text after it breaks on its own
        own = text[logical:text.find("\n", logical) if "\n" in text[logical:] else len(text)]
        visual = sum(1 for other in starts[:line] if other >= logical)  # its lines before this one
        room = widths if logical == 0 else widths[1:] or widths
        width = room[min(visual, len(room) - 1)]
        origin = _line_origin(style, logical == 0 and visual == 0)
        own_looks = None if looks is None else looks[logical:logical + len(own)]
        used = 0.0
        since = start  # the first character after the line's start or the last tab stop reached: exact places
        for index in range(start, end):
            ch = text[index]
            if ch != "\t":
                look = style if looks is None else looks[index]
                used += char_advance(ch, points, look)
                if index + 1 < len(text):  # automatic spacing goes with the character before it
                    used += auto_space_gap(ch, text[index + 1], points, style, look)
                continue
            at = index - logical

            def after(point: bool, at: int = at) -> float:
                return _width_after_tab(own, at, points, style, None, own_looks, None, point)

            reach = tab_reach(origin + used, origin + width, style, after)
            if reach is None:
                return None
            # text this close to a tab stop may reach another one in Hancom: a layout unit off for each character
            # since the line's start or the last tab stop, at most _MARGIN
            margin = min((index - since) * _LAYOUT_UNIT, _MARGIN)
            for shift in (-margin, margin) if margin else ():
                moved = tab_reach(origin + used + shift, origin + width, style, after)
                if moved is None or abs(shift + moved - reach) > 0.5:
                    return None
            found.append(round(reach))
            used += reach
            if reach:
                since = index + 1
    return found


def _wraps_text(section: Any) -> bool:
    """Whether an object of *section* not set as a character lets text run beside it (square, tight or through
    wrapping)."""

    for pos in section.iter(f"{HP}pos"):
        obj = pos.getparent()
        if pos.get("treatAsChar") != "1" and obj.get("textWrap") in ("SQUARE", "TIGHT", "THROUGH"):
            return True
    return False


def _control_places(runs: list[Any], first: bool) -> list[int] | None:
    """Where in the paragraph's text each of its controls stands, or None when the paragraph holds anything but
    text and controls that take no room on a line: a header, a footer, a page number and the other page controls
    (and in a section's first paragraph, the section's own definitions), all of them before the text, and the start
    and end of a field anywhere."""

    places: list[int] = []
    length = 0
    for run in runs:
        for child in run:
            name = _pages._local(child)
            if name == "t":
                if any(_pages._local(mark) not in _TEXT_MARKS | _EMPTY_MARKS for mark in child):
                    return None
                if "\n" in (child.text or "") or any("\n" in (mark.tail or "") for mark in child):
                    return None  # a line break typed into the text, which Hancom writes as hp:lineBreak
                length += len(_pages._t_text(child))
            elif (name == "secPr" and first or name == "ctrl" and _takes_no_room(child, first)) and not length:
                places.append(length)  # before the text only: one among it was seen to break the line elsewhere
            elif name == "ctrl" and not first and _field_mark(child):
                places.append(length)
            else:
                return None
    return places


def _field_mark(ctrl: Any) -> bool:
    """Whether *ctrl* holds only the start of a field of :data:`_FIELD_KINDS` or a field's end."""

    marks = list(ctrl)
    return bool(marks) and all(
        _pages._local(mark) == "fieldEnd" or _pages._local(mark) == "fieldBegin" and mark.get("type") in _FIELD_KINDS
        for mark in marks)


def _takes_no_room(ctrl: Any, first: bool) -> bool:
    kinds = {_pages._local(child) for child in ctrl}
    return bool(kinds) and kinds <= (_PAGE_CONTROLS | ({"colPr"} if first else set()))


def _hancom_offset(text: str, start: int, controls: list[int] = ()) -> int:  # type: ignore[assignment]
    """Where *start* (a place in python-hwpx's text) is in Hancom's line text positions: a tab takes eight
    characters there, a character past the Basic Multilingual Plane two, and a control before it eight."""

    head = text[:start]
    return (start + 7 * head.count("\t") + sum(1 for ch in head if ord(ch) > 0xFFFF)
            + _CONTROL_LENGTH * sum(1 for place in controls if place < start))


def _append_cache(paragraph: Any, segments: list[dict[str, int]], tabs: list[int]) -> None:
    for tab, width in zip(paragraph.iter(f"{HP}tab"), tabs):
        tab.attrib.update({"width": str(width), **_DEFAULT_TAB})
    array = paragraph.makeelement(f"{HP}linesegarray", {})
    for segment in segments:
        array.append(array.makeelement(f"{HP}lineseg", {key: str(value) for key, value in segment.items()}))
    paragraph.append(array)
