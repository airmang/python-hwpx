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

Only a paragraph Hancom would lay out from its text alone gets a cache: a body paragraph of text runs in one
look (face, 장평, 자간) -- tabs to the default tab stops, line breaks, the section's own controls in the first
paragraph, and a hanging bullet or number label in the paragraph's size included -- in a section of one column
where no object lets text run beside it. Its runs may differ in size: each line is then as tall as its largest
character, unless a larger one past the line's end may be the one that did not fit on it (Hancom writes the line
as tall as that one), and the paragraph has no tab. The cells of a table in such a section get caches the
same way when every paragraph of the cell is one of these: their lines go down from the top of the cell's text
area, as wide as that area in whole layout units and never narrower than Hancom's narrowest line. A paragraph
holding nothing but a table set as a character gets its one line, as tall as the table, and the table its rows'
height (``hp:sz``), as Hancom saves them. A paragraph is
also left when its line breaks are less sure: a character no glyph table gives an advance for, or a word too long
for a line. A paragraph that has a cache keeps it. The others are left for Hancom;
a document mixing both is laid out as one. Nothing is written when the estimate does not follow the document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..form_fit.measure import (
    _FIXED_SPACE,
    _GLYPH_SPACE,
    _HALF_EM_GLYPHS,
    _HALF_EM_SPACES,
    _design_units,
    _hancom_break_opportunities,
    _hangul_units,
    _laid_out_face,
    _line_origin,
    _width_after_tab,
    char_advance,
    classify_char,
    tab_reach,
)
from ..oxml.table_sizes import cell_margins_of, grid_widths_of
from . import pages as _pages
from .pages import HP

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
#: How many characters a control (a section or column definition) takes in a line's text position.
_CONTROL_LENGTH = 8
#: The text children a cached paragraph may hold, as python-hwpx reads them into its text. With a cache Hancom
#: draws a tab as wide as its ``hp:tab`` says, so a tab gets the width Hancom lays it out at too.
_TEXT_MARKS = frozenset({"tab", "lineBreak", "nbSpace", "fwSpace"})
#: What Hancom writes on a tab that reaches a default tab stop: no leader, a left stop.
_DEFAULT_TAB = {"leader": "0", "type": "1"}


@dataclass(frozen=True)
class LineCacheReport:
    """What :func:`write_line_caches` did: the paragraphs it gave a cache, those it left for Hancom to lay out
    (``skipped``), those that kept their own, and why it wrote nothing (``unsupported``) when it did not
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
    estimate = _pages.estimate_pages(document)
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
    if any(_pages._local(child) == "ctrl" and not _only_columns(child) for run in runs for child in run):
        return None
    if not _cells_sure(measure, table):  # the rows are as tall as their cells' lines: those must be sure too
        return None
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # spaced from its largest characters
    rows = _pages._inline_table_height(measure, table)
    tall = rows + _pages._extent_margins(table)
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
    prefix = _control_prefix(runs, first)
    if prefix is None:
        return None
    headed = measure.headed(paragraph)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    if shape.font_line:
        return None
    size, refs, sizes = _pages._text_size(measure, runs)
    end = _pages._end_size(measure, runs, sizes)
    mixed = len(set(sizes)) > 1 or bool(end)  # each line as tall as its largest character
    if _pages._char_styles(measure, paragraph, runs) is not None:  # runs of another face, 장평 or 자간
        return None
    if headed and (_pages._head_size(measure, paragraph, sizes) or shape.indent):  # a label of its own size
        return None
    text = _pages._run_text(runs)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    if style is not None and style.head and not (headed and style.head_hangs):
        return None
    room = width - shape.left - shape.right
    widths = _pages._line_widths(shape, width, style) if cell else _pages._indented(room, shape, style)
    if mixed:
        if "\t" in text:
            return None
        starts = _pages._metric_starts(measure, text, widths, sizes, style, {})
        metrics = _pages._line_metrics(measure, text, widths, sizes, style, shape, {}, end=end)
    else:
        starts = measure.line_starts(text, widths, size, style) if text else [0]
        metrics = ((size, _pages._pitch(shape.kind, shape.value, size)),) * len(starts)
    if len(metrics) != len(starts):
        return None
    if mixed and _taller_past_a_break(text, sizes, starts, metrics):
        return None
    if not _sure_of(text, starts, style):
        return None
    tabs = _tab_widths(text, starts, widths, size, style) if "\t" in text else []
    if tabs is None:
        return None
    indented = min(widths) < room  # else Hancom dropped the indent: no line takes it
    segments = []
    ends = [*starts[1:], len(text)]
    for line, (start, (height, advance)) in enumerate(zip(starts, metrics)):
        drawn = [sizes[index] for index in range(start, ends[line]) if text[index] != "\n"] if mixed else []
        text_height = max(drawn) if drawn else height  # a line break larger than the text makes the line taller
        takes_indent = (indented and (shape.indent > 0 if line == 0 else shape.indent < 0)) or (headed and line > 0)
        segments.append({
            "textpos": prefix + _hancom_offset(text, start) if line else 0,  # the first line starts at 0
            "vertpos": 0,
            "vertsize": height,
            "textheight": text_height,
            "baseline": (text_height * 85 + 50) // 100,
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


def _sure_of(text: str, starts: list[int], style: Any) -> bool:
    """Whether the line breaks at *starts* can be trusted to be Hancom's: every character takes an advance a
    glyph table gives (not a class average), and no line starts inside a word that did not fit on a line of its
    own. Hancom takes the line breaks from a cache as written (a line short of a break is drawn with its text
    pressed together), so a paragraph laid out less surely is left for Hancom."""

    if style is None:
        return False
    face, hangul_face = _laid_out_face(style.glyph_face), _laid_out_face(style.hangul_face)
    for ch in set(text):
        if ch in "\t\n" or ch in _HALF_EM_SPACES or ch in _HALF_EM_GLYPHS or ch in (_FIXED_SPACE, _GLYPH_SPACE):
            continue
        if classify_char(ch) == "hangul":
            if _hangul_units(hangul_face, ch) is None:
                return False
        elif _design_units(face, ch) is None:
            return False
    breaks = _hancom_break_opportunities(text, style)
    return all(start in breaks or text[start - 1] == "\n" for start in starts[1:])


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


def _tab_widths(text: str, starts: list[int], widths: list[float], size: int, style: Any) -> list[int] | None:
    """The width of each tab of *text* as Hancom lays it out on the lines starting at *starts*, or None when a
    tab does not reach a default tab stop (the paragraph's own stops, a tab laid out as a glyph)."""

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
        used = 0.0
        for index in range(start, end):
            ch = text[index]
            if ch != "\t":
                used += char_advance(ch, points, style)
                continue
            at = index - logical
            reach = tab_reach(origin + used, origin + width, style,
                                   lambda point, at=at: _width_after_tab(own, at, points, style, None, None, None,
                                                                              point))
            if reach is None:
                return None
            found.append(round(reach))
            used += reach
    return found


def _wraps_text(section: Any) -> bool:
    """Whether an object of *section* not set as a character lets text run beside it (square, tight or through
    wrapping)."""

    for pos in section.iter(f"{HP}pos"):
        obj = pos.getparent()
        if pos.get("treatAsChar") != "1" and obj.get("textWrap") in ("SQUARE", "TIGHT", "THROUGH"):
            return True
    return False


def _control_prefix(runs: list[Any], first: bool) -> int | None:
    """How many characters the controls before the text take in the line's text position, or None when the
    paragraph holds anything but text (and, in a section's first paragraph, the section's own controls first)."""

    controls = 0
    seen_text = False
    for run in runs:
        for child in run:
            name = _pages._local(child)
            if name == "t":
                if any(_pages._local(mark) not in _TEXT_MARKS for mark in child):
                    return None
                if "\n" in (child.text or "") or any("\n" in (mark.tail or "") for mark in child):
                    return None  # a line break typed into the text, which Hancom writes as hp:lineBreak
                seen_text = seen_text or bool(_pages._t_text(child))
            elif first and not seen_text and (name == "secPr" or name == "ctrl" and _only_columns(child)):
                controls += 1
            else:
                return None
    return controls * _CONTROL_LENGTH


def _only_columns(ctrl: Any) -> bool:
    return len(ctrl) == 1 and _pages._local(ctrl[0]) == "colPr"


def _hancom_offset(text: str, start: int) -> int:
    """Where *start* (a place in python-hwpx's text) is in Hancom's line text positions: a tab takes eight
    characters there, a character past the Basic Multilingual Plane two."""

    head = text[:start]
    return start + 7 * head.count("\t") + sum(1 for ch in head if ord(ch) > 0xFFFF)


def _append_cache(paragraph: Any, segments: list[dict[str, int]], tabs: list[int]) -> None:
    for tab, width in zip(paragraph.iter(f"{HP}tab"), tabs):
        tab.attrib.update({"width": str(width), **_DEFAULT_TAB})
    array = paragraph.makeelement(f"{HP}linesegarray", {})
    for segment in segments:
        array.append(array.makeelement(f"{HP}lineseg", {key: str(value) for key, value in segment.items()}))
    paragraph.append(array)
