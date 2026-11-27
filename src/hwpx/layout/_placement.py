# SPDX-License-Identifier: Apache-2.0
"""What the page estimate's trace says: the third part of :mod:`hwpx.layout.pages`.

:func:`hwpx.layout.pages.estimate_layout` lays a document out with the trace on and hands what the layout kept
(the lines of every paragraph, the row parts of every table, the frames of objects and notes) to
:func:`_placement_result`, which turns it into the public placement objects. Those classes, and everything that
lays out, stay in :mod:`~hwpx.layout.pages` and :mod:`~hwpx.layout._page_measure`; this module only reads their
results. It lives apart because the two halves of the estimate are near the size a plugin directory reads of one
file (``tests/test_distribution_file_sizes.py``). Nothing here changes a page estimate.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise
from typing import Any

from ..form_fit.measure import (
    _DEFAULT_TAB_STOP, _GLYPH_SPACE, _HANGING_SPACES, _TYPED_NO_BREAK_SPACE, _line_origin, auto_space_gap,
    char_advance, tab_reach,
)
from ..oxml.namespaces import HP
from ..oxml.table_sizes import _grid_extents_of
from ._page_measure import (
    _DRAWINGS, _NO_WRAP, _OBJECTS, _CellLine, _CellSlice, _FlowTable, _LineContent, _Measure, _Row, _RowPart,
    _caption, _caption_beside, _cell_spacing, _drawn_height, _effect_room, _floating, _indented, _inline_content,
    _local, _object_extent, _page_break, _shadow_drop, _text_size, _whole_rows,
)
from .pages import (
    AreaPlacement, EstimatedLine, LayoutEstimate, LinePlacement, ObjectPlacement, PageEstimate, PagePlacement,
    ParagraphPlacement, TableCaptionPlacement, TableCellLinePlacement, TableCellPlacement, TablePlacement,
    TableRowPlacement, _AreaFrame, _FrameTrace, _LineDetail, _ObjectFrame, _Page, _RunPositions, _SectionLayout,
    _TableCapture, _column_area, _object_margin, _run_positions, _tab_stop,
)


def _placement_result(
    estimate: PageEstimate, sections: list[tuple[int, int, _SectionLayout]], sources: list[Any],
    inline_tables: dict[Any, _FlowTable], sizes: dict[Any, tuple[int | None, int]],
    untraced: dict[Any, str] | None = None, lefts: dict[Any, tuple[int, bool]] | None = None,
    measure: _Measure | None = None,
) -> LayoutEstimate:
    pages: list[PagePlacement] = []
    papers: list[_Page] = []  # the page settings of each of them
    paragraphs: list[ParagraphPlacement] = []
    table_captures: dict[Any, tuple[_TableCapture, _FrameTrace, int, int]] = {}
    object_captures: dict[Any, tuple[_ObjectFrame, _FrameTrace, int, _Page]] = {}
    area_captures: dict[Any, list[tuple[_AreaFrame, _FrameTrace, int, _Page]]] = {}
    body_sources = [source.findall(f"{HP}p") for source in sources]
    line_groups = iter(estimate.lines)
    for section, first, layout in sections:
        paper = layout.paper
        details = layout.details
        assert paper is not None and details is not None and len(details) == len(layout.lines)
        body = paper.left, paper.top, paper.text_width, paper.body
        for scope in layout.placement_frames:
            untraced = {**(untraced or {}), **dict(scope.untraced)}
            for capture in scope.captures:
                table_captures[capture.table.source] = (capture, scope, len(pages), paper.top)
            for captured in scope.objects:
                object_captures[captured.source] = (captured, scope, len(pages), paper)
            for area in scope.areas:
                area_captures.setdefault(area.source, []).append((area, scope, len(pages), paper))
        total_pages = layout.pages if layout.places is not None else (layout.frames - 1) // layout.columns + 1
        default_area = (_column_area(paper),)
        for local_page in range(total_pages):
            areas = tuple(layout.areas.get(local_page, ())) if layout.areas is not None else default_area
            pages.append(PagePlacement(len(pages), section, paper.paper_width, paper.paper_height, body, areas))
            papers.append(paper)
        line_index = 0
        for index in range(first, first + len(layout.counts)):
            lines = []
            styles = _run_positions(body_sources[section][index])
            for position in next(line_groups):
                area_top = 0 if layout.area_tops is None else layout.area_tops[line_index]
                lines.append(_placement_line(position, paper.top + area_top, details[line_index], styles))
                line_index += 1
            paragraphs.append(ParagraphPlacement(section, index, tuple(lines)))
    tables: list[TablePlacement] = []
    objects: list[ObjectPlacement] = []
    areas: list[AreaPlacement] = []
    by_source: dict[Any, TablePlacement] = {}
    paragraph_origins = {(entry.section, entry.paragraph): entry.lines[0].position
                         for entry in paragraphs if entry.lines}
    paragraph_lines = {(entry.section, entry.paragraph): entry.lines for entry in paragraphs}
    nested_places: dict[Any, list[tuple[int, int]]] = {}
    object_places: dict[Any, ObjectPlacement] = {}
    running = _running_areas(body_sources, paragraph_origins, pages, papers)
    for section, source in enumerate(body_sources):
        for index, paragraph in enumerate(source):
            numbers = {table: number for number, table in enumerate(paragraph.iter(f"{HP}tbl"))}
            for table, table_index in numbers.items():
                address = section, index, table_index
                if table in table_captures:
                    result = _table_placement(address, *table_captures[table], numbers, nested_places,
                                              (lefts or {}).get(table), pages)
                elif table in inline_tables and _in_text_box(table):
                    result = _boxed_table_placement(address, inline_tables[table],
                                                    object_captures.get(_table_holder(table).getparent()), pages,
                                                    numbers, nested_places)
                elif table in inline_tables:
                    result = _nested_table_placement(address, table, inline_tables[table], by_source, numbers,
                                                     nested_places)
                else:
                    result = None
                if result is None:
                    reason = (untraced or {}).get(table) or _unplaced_table(table, table in inline_tables, by_source)
                    result = TablePlacement(*address, (), unavailable=(reason,))
                origin = paragraph_origins.get((section, index))
                if result.rows and origin is not None and table.getparent().getparent() is paragraph:
                    first = result.rows[0]
                    if (first.page, first.column) > (origin.page, origin.column):
                        result = replace(result, moved=True)
                    elif _left_behind(table, result, origin):
                        result = TablePlacement(*address, (), unavailable=(_LEFT_BEHIND,))
                by_source[table] = result
                tables.append(result)
            for ordinal, obj in enumerate(node for node in paragraph.iter() if _local(node) in _DRAWINGS):
                placed = _object_placement(section, index, ordinal, obj, sizes.get(obj), object_captures.get(obj), pages)
                if placed.page is None:
                    placed = _held_object(placed, obj, object_places, by_source)
                    if placed.wrap == "AS_CHARACTER" and measure is not None:
                        placed = _in_cell(placed, obj, measure, by_source, pages, source, index)
                elif placed.x is None and placed.wrap == "AS_CHARACTER" and measure is not None \
                        and obj.getparent() is not None and obj.getparent().getparent() is paragraph:
                    placed = _among_text(placed, obj, measure, source, index, paragraph_lines.get((section, index), ()),
                                         pages)
                object_places[obj] = placed
                objects.append(placed)
            for ordinal, area in enumerate(node for node in paragraph.iter() if _local(node) in _AREA_NAMES):
                found = area_captures.get(area)
                if found:
                    areas.extend(_area_placement(section, index, ordinal, *capture, pages) for capture in found)
                elif area in running:
                    shown, why = running[area]
                    areas.extend(AreaPlacement(section, index, ordinal, _local(area), page, 0, *box, unavailable=(why,))
                                 for page, box in shown)
                    if not shown:
                        areas.append(AreaPlacement(section, index, ordinal, _local(area), unavailable=(why,)))
                else:
                    areas.append(AreaPlacement(section, index, ordinal, _local(area),
                                               unavailable=("area placement not retained by the layout path",)))
    return LayoutEstimate(estimate, tuple(pages), tuple(paragraphs), tuple(tables), tuple(objects), tuple(areas))


_AREA_NAMES = frozenset(("header", "footer", "footNote", "endNote"))


def _running_areas(sources: list[list[Any]], origins: dict[tuple[int, int], EstimatedLine],
                   pages: list[PagePlacement], papers: list[_Page]
                   ) -> dict[Any, tuple[list[tuple[int, tuple[int, int, int, int]]], str]]:
    """Each header and footer of the body's paragraphs -> the pages it is drawn on, with its room there (x, top,
    width, height on the paper), and what is not given. A header or footer set for every page runs from the page
    of its paragraph's first line to the end of its section, or to the page where a later one of its kind starts;
    it is left off the section's first page where the section hides it there (``hp:visibility``) and off a page
    whose paragraphs hide it (``hp:pageHiding``). Its room is the page's: above the body as tall as the header
    margin, below it as tall as the footer margin. One for odd or for even pages is not given pages: the layout
    does not follow page numbers. The layout does not lay out its lines."""

    result: dict[Any, tuple[list[tuple[int, tuple[int, int, int, int]]], str]] = {}
    for section, paragraphs in enumerate(sources):
        own = [page.page for page in pages if page.section == section]
        hidden: dict[str, set[int]] = {"header": set(), "footer": set()}
        visibility = next(paragraphs[0].iter(f"{HP}visibility"), None) if paragraphs else None
        found: list[tuple[int, str, Any]] = []
        for index, paragraph in enumerate(paragraphs):
            origin = origins.get((section, index))
            if origin is None or not own:
                continue
            for control in paragraph.findall(f"{HP}run/{HP}ctrl"):
                for node in control:
                    name = _local(node)
                    if name == "pageHiding":
                        for kind in hidden:
                            if node.get("hide" + kind.capitalize()) in ("1", "true"):
                                hidden[kind].add(origin.page)
                    elif name in hidden:
                        found.append((origin.page, name, node))
        for kind in hidden:
            if own and visibility is not None and visibility.get("hideFirst" + kind.capitalize()) in ("1", "true"):
                hidden[kind].add(own[0])
        for at, (start, kind, node) in enumerate(found):
            if node.get("applyPageType", "BOTH") != "BOTH":
                result[node] = ([], f"{kind} for odd or even pages: the layout does not follow page numbers")
                continue
            stop = min((other for other, name, later in found[at + 1:]
                        if name == kind and later.get("applyPageType", "BOTH") == "BOTH"), default=own[-1] + 1)
            shown = []
            for page in own:
                if start <= page < stop and page not in hidden[kind]:
                    paper = papers[page]
                    top, tall = (paper.top - paper.header, paper.header) if kind == "header" \
                        else (paper.top + paper.body, paper.footer)
                    shown.append((page, (paper.left, top, paper.text_width, tall)))
            result[node] = (shown, f"{kind} lines are not laid out")
    return result


#: What holds an object other than a body paragraph, and how the placement names it.
_OBJECT_HOLDERS = {"container": "a member of a group: it stands relative to the group's rectangle",
                   "drawText": "an object in a text box: its place in the box is not laid out",
                   "tc": "an object in a table cell: its place in the cell is not laid out",
                   "caption": "an object in a caption is not placed", "header": "an object in a header is not placed",
                   "footer": "an object in a footer is not placed", "footNote": "an object in a footnote is not placed",
                   "endNote": "an object in an endnote is not placed"}


def _held_object(placed: ObjectPlacement, obj: Any, others: dict[Any, ObjectPlacement],
                 tables: dict[Any, TablePlacement]) -> ObjectPlacement:
    """*placed*, an object the layout keeps no page for, with what holds it: a member of a group and an object in
    a text box stand on the page of the group or of the box's drawing, an object in a table cell on the page of
    the one part of its row when that row stands whole there; its place there is not laid out. An object of the
    body in front of or behind the text placed from its paragraph says so."""

    holder = next((up for up in obj.iterancestors() if _local(up) in _OBJECT_HOLDERS), None)
    size = tuple(why for why in placed.unavailable if why == "object size not measured")
    if holder is None:
        if not _floating(obj):
            return placed
        return replace(placed, unavailable=("an object in front of or behind the text placed from its paragraph: "
                                            "its place is not computed", *size))
    page = column = None
    if _local(holder) == "tc":
        parent = next(holder.iterancestors(f"{HP}tbl"), None)
        index = next((at for at, cell in enumerate(parent.findall(f"{HP}tr/{HP}tc")) if cell is holder), None) \
            if parent is not None else None
        rows = tables[parent].rows if parent in tables else ()
        found = [(row.page, row.column) for row in rows if not row.repeated
                 for cell in row.cells if cell.source_index == index]
        if index is not None and len(found) == 1:
            page, column = found[0]
    else:
        where = others.get(holder if _local(holder) == "container" else holder.getparent())
        if where is not None:
            page, column = where.page, where.column
    return replace(placed, page=page, column=column, unavailable=(_OBJECT_HOLDERS[_local(holder)], *size))


#: Why an object set as a character among text has no left edge (it keeps its line's page).
_AMONG = "object set as a character: where it stands on its line is not laid out"
#: Why one with its left edge has no top: its line is taller than it, and Hancom stands it on the text's baseline.
_AMONG_TALL = ("object set as a character on a line taller than it: where it stands up and down the line is not "
               "laid out")


def _among_text(placed: ObjectPlacement, obj: Any, measure: _Measure, paragraphs: list[Any], index: int,
                lines: tuple[LinePlacement, ...], pages: list[PagePlacement]) -> ObjectPlacement:
    """*placed*, an object set as a character among the text of body paragraph *index* of *paragraphs* (its
    section's), with its left edge on the line holding its text position (see :func:`_x_on_line`), or the reason
    that line does not give it."""

    rest = tuple(why for why in placed.unavailable if why != _AMONG)
    measure.tab_stop = _part_tab_stop(paragraphs, index)
    page = pages[placed.page]

    def whole(line: Any) -> int | None:  # the column the line stands in
        area = next((area for area in reversed(page.column_areas) if area.top <= line.top), None)
        return area.widths[placed.column or 0] if area is not None and (placed.column or 0) < len(area.widths) \
            else None

    found = _x_on_line(obj, measure, paragraphs[index], lines, whole)
    if isinstance(found, str):
        return replace(placed, unavailable=(found, *rest))
    x, line = found
    if (line.position.page, line.position.column) != (placed.page, placed.column):
        return replace(placed, unavailable=("object set as a character: its line stands elsewhere than its frame",
                                            *rest))
    origin = _column_origin(pages[placed.page], placed.column or 0, line.top)
    if origin is None:
        return replace(placed, unavailable=("object set as a character: its column's left edge is not measured",
                                            *rest))
    return replace(placed, x=int(origin + x), unavailable=(*(() if placed.top is not None else (_AMONG_TALL,)),
                                                           *rest))


def _in_cell(placed: ObjectPlacement, obj: Any, measure: _Measure, tables: dict[Any, TablePlacement],
             pages: list[PagePlacement], paragraphs: list[Any], index: int) -> ObjectPlacement:
    """*placed*, an object set as a character among the text of a paragraph of a table cell (the table in body
    paragraph *index* of *paragraphs*), with its left edge on the cell line holding its text position in the part
    of its row showing that line (see :func:`_x_on_line`; the line measured from the cell's left edge, the cell
    from the table's, the table from its column's), and its top below its top outer margin on that line when the
    line is as tall as it. Unchanged where the cell's lines are not placed."""

    cell = next((up for up in obj.iterancestors() if _local(up) in _OBJECT_HOLDERS), None)
    paragraph = obj.getparent().getparent() if obj.getparent() is not None else None
    if cell is None or _local(cell) != "tc" or paragraph is None or paragraph.getparent() is None \
            or paragraph.getparent().getparent() is not cell:
        return placed
    table = next(cell.iterancestors(f"{HP}tbl"), None)
    placement = tables.get(table)
    if placement is None or not placement.rows:
        return placed
    number = next((at for at, other in enumerate(table.findall(f"{HP}tr/{HP}tc")) if other is cell), None)
    order = next((at for at, other in enumerate(cell.findall(f"{HP}subList/{HP}p")) if other is paragraph), None)
    measure.tab_stop = _part_tab_stop(paragraphs, index)
    held = _OBJECT_HOLDERS["tc"]
    rest = tuple(why for why in placed.unavailable if why != held)
    why = None
    for row in placement.rows:
        for part in row.cells if not row.repeated else ():
            lines = tuple(line for line in (part.lines or part.lines_with_tables) if line.paragraph == order)
            if part.source_index != number or not lines:
                continue
            found = _x_on_line(obj, measure, paragraph, lines, lambda line: None)
            if isinstance(found, str):
                why = why if found.startswith("object set as a character: no line") and why else found
                continue
            x, line = found
            origin = None if not 0 <= row.page < len(pages) else _column_origin(
                pages[row.page], row.column, row.top if row.top is not None else pages[row.page].body[1])
            if origin is None or row.x is None or part.x is None:
                why = "object set as a character in a table cell: the cell's left edge on the page is not measured"
                continue
            top = None
            if row.top is not None and part.top is not None and line.top is not None \
                    and _object_extent(obj, measure)[1] == line.height:
                top = row.top - row.table_offset + part.top + line.top + _object_margin(obj, "top") \
                    + _caption(measure, obj)[0]
            missing = () if top is not None else (_AMONG_TALL if line.top is not None and row.top is not None
                                                  and part.top is not None else
                                                  "object set as a character in a table cell: its line's top on the "
                                                  "page is not measured",)
            return replace(placed, page=row.page, column=row.column, x=int(origin + row.x + part.x + x), top=top,
                           unavailable=(*missing, *rest))
    return replace(placed, unavailable=(why, *rest)) if why is not None else placed


def _part_tab_stop(paragraphs: list[Any], index: int) -> int:
    """The default tab stops of the part of a section paragraph *index* is laid out in (see
    :func:`~hwpx.layout.pages._section_parts`): those of the last paragraph up to it holding section settings."""

    for paragraph in reversed(paragraphs[:index + 1]):
        if paragraph.find(f"{HP}run/{HP}secPr") is not None:
            return _tab_stop(paragraph) or _DEFAULT_TAB_STOP
    return _DEFAULT_TAB_STOP


def _measured_text(measure: _Measure, paragraph: Any) -> tuple[
        str, list[int], list[Any], dict[int, float], list[int], dict[Any, int], Any] | None:
    """Placement tracing only: the paragraph's text as the layout breaks it with objects set as characters among
    it (:func:`~hwpx.layout._page_measure._inline_content`: each object, composed character, ruby text and shown
    control one character of its own width), each character's size and style as the layout measures it, those
    fixed widths by place, each character's Hancom text position, each object's place, and the paragraph's style.
    ``None`` where its characters do not line up with Hancom's positions or are not measured so."""

    runs = paragraph.findall(f"{HP}run")
    if any(_local(child) == "switch" for run in runs for child in run):
        return None
    apart = tuple(child for run in runs for child in run if _local(child) in _OBJECTS and (
        child.find(f"{HP}pos") is None or child.find(f"{HP}pos").get("treatAsChar") != "1"))
    held: dict[int, Any] = {}
    places: dict[Any, int] = {}
    try:
        text, sizes, looks, objects, marks = _inline_content(measure, paragraph, runs, None, apart, controls=held)
        native = measure.native_positions(paragraph, controls=places)
        style = measure.style(paragraph.get("paraPrIDRef"), _text_size(measure, runs, paragraph)[1], paragraph)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return None
    if native is None or style is None:
        return None
    characters = iter((position, value) for position, value in native[0] if value)
    positions: list[int] = []
    for at, glyph in enumerate(text):
        if at in held:
            place = places.get(held[at])
            if place is None:
                return None
        else:
            source = next(characters, None)
            if source is None or source[1] != glyph.replace(_GLYPH_SPACE, "　").replace(
                    _TYPED_NO_BREAK_SPACE, " "):
                return None
            place = source[0]
        positions.append(place)
    if next(characters, None) is not None or any(a > b for a, b in pairwise(positions)):
        return None
    advances ={at: float(width) for at, (width, _) in objects.items()}
    advances.update((at, float(width)) for at, width in marks.items())
    return (text, sizes, looks if len(set(looks)) > 1 else [style] * len(text), advances, positions,
            {held[at]: at for at in held}, style)


def _pens(text: str, sizes: list[int], looks: list[Any], advances: dict[int, float], style: Any, start: int,
          stop: int, origin: float, room: float) -> list[float]:
    """Placement tracing only: how far right of its line's start each character of ``text[start:stop]`` begins,
    then how far the last one reaches, added up as :func:`~hwpx.form_fit.measure.hancom_line_starts` adds the
    line up when it breaks it: each character's advance at its own size and style and the automatic spacing after
    it (none after a space), a fixed width as given, a tab to where it reaches from *origin* (the line's start
    from the column's left edge) on a line *room* wide."""

    def after(tab: int, point: bool) -> float:  # the text after a tab up to the next tab or the line's end
        stop_at = min((found for found in (text.find("\t", tab + 1), text.find("\n", tab + 1)) if found >= 0),
                      default=len(text))
        if point:
            dot = text.rfind(".", tab + 1, stop_at)
            stop_at = stop_at if dot < 0 else dot
        return sum(advances[at] if at in advances else char_advance(text[at], sizes[at] / 100, looks[at])
                   for at in range(tab + 1, stop_at))

    used, pens = 0.0, []
    for at in range(start, stop):
        pens.append(used)
        glyph, size, look = text[at], sizes[at] / 100, looks[at]
        fixed = advances.get(at)
        if fixed is None and glyph == "\t" and (style.tab_stop or style.tab_stops or style.auto_tab_right):
            fixed = tab_reach(origin + used, origin + room, style, lambda point, at=at: after(at, point))
        advance = char_advance(glyph, size, look) if fixed is None else fixed
        if glyph in _HANGING_SPACES:
            used += advance
            continue
        following = text[at + 1] if at + 1 < len(text) else "\n"
        used += advance + (auto_space_gap(glyph, following, size, style, look) if following != "\n" else 0.0)
    pens.append(used)
    return pens


def _x_on_line(obj: Any, measure: _Measure, paragraph: Any, lines: tuple[Any, ...],
               whole: Callable[[Any], float | None]) -> tuple[float, Any] | str:
    """Placement tracing only: how far right of the left edge its *lines* are measured from (a body line's column,
    a cell line's cell) an object set as a character among text starts (its left outer margin outside), on the
    line holding its text position, with that line; else why not. *whole* gives the width a line's paragraph is
    laid out in (its column, its cell's inside), ``None`` where it is not known.

    The line starts where the layout starts it (a line Hancom saved in a paragraph with an indent or a label: as
    the layout indents its lines when the line has the paragraph's whole room); the object stands past the
    characters before it on that line, measured as the layout measures them (:func:`_pens`), moved as the
    paragraph's alignment moves the line: not at all set left, or on the last line set justified; centred or to
    the end by the room the line's characters leave. A line Hancom spreads (justified but its last, distributed)
    does not say where it stands but at the line's start, nor does a line set centred or right that ends in spaces
    or in automatic spacing, or one whose spaces shrink for its characters to fit. An object with a shadow, an
    effect taking room or a caption beside it is not placed in its box."""

    if _shadow_drop(obj) or _caption_beside(obj) or any(
            _effect_room(obj, int(obj.find(f"{HP}sz").get("width", 0)), _drawn_height(obj, measure))):
        return ("object set as a character with a shadow, an effect or a caption beside it: where it stands in "
                "its box is not laid out")
    measured = _measured_text(measure, paragraph)
    if measured is None:
        return "object set as a character: its paragraph's text is not measured with Hancom's text positions"
    text, sizes, looks, advances, positions, places, style = measured
    at = places.get(obj)
    if at is None:
        return "object set as a character: its place in its paragraph's text is not found"
    line = next((line for line in lines if line.text_start is not None and line.text_end is not None
                 and line.text_start <= positions[at] < line.text_end), None)
    if line is None and len(lines) == 1:  # a paragraph of one line: everything is on it
        line, start, stop = lines[0], 0, len(text)
    elif line is None:
        return ("object set as a character: no line of its paragraph holds its text position" if any(
            other.text_start is not None for other in lines) else
                "object set as a character: the lines of its paragraph keep no text ranges")
    else:
        start, stop = bisect_left(positions, line.text_start), bisect_left(positions, line.text_end)
    if line.x is None or line.width is None:
        return "object set as a character: its line has no horizontal origin or width"
    first = start == 0
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    left, room = line.x, line.width
    if line.source == "cache" and (shape.indent or style.head):  # the cache keeps the paragraph's whole room
        column = whole(line)
        if column is None or (left, room) != (shape.left, column - shape.left - shape.right):
            return ("object set as a character on a saved line of an indented or labelled paragraph not as wide as "
                    "the paragraph: where the line's text starts is not laid out")
        room = _indented(room, shape, style)[0 if first else 1]
        left = column - shape.right - room
    if room >= _NO_WRAP:
        return "object set as a character in a paragraph pressed onto one line: where it stands is not laid out"
    pens = _pens(text, sizes, looks, advances, style, start, stop, _line_origin(style, first), room)
    end = stop
    while end > start and text[end - 1] == "\n":
        end -= 1
    content = end
    while content > start and text[content - 1] in _HANGING_SPACES:
        content -= 1
    pen, used = pens[at - start], pens[content - start]
    if used > room:
        return "object set as a character on a line whose spaces shrink to fit it: where it stands is not laid out"
    align = measure.align(paragraph.get("paraPrIDRef"))
    if align in ("JUSTIFY", "DISTRIBUTE", "DISTRIBUTE_SPACE") and pen and (align != "JUSTIFY" or stop < len(text)):
        return ("object set as a character on a line spread across its room (justified but the last, or "
                "distributed): where Hancom adds the room is not laid out")
    shift = 0.0
    if align in ("CENTER", "RIGHT"):
        gap = content < len(text) and text[content] != "\n" and auto_space_gap(
            text[content - 1], text[content], sizes[content - 1] / 100, style, looks[content - 1])
        if content < end or gap:
            return ("object set as a character on a line set centred or right that ends in spaces or automatic "
                    "spacing: whether Hancom counts them is not laid out")
        shift = (room - used) / (2 if align == "CENTER" else 1)
    return left + pen + shift + _object_margin(obj, "left"), line


def _scope_place(frame: int, scope: _FrameTrace, first_page: int) -> tuple[int, int, int]:
    page, column = divmod(frame, scope.columns)
    return first_page + scope.first_page + page, scope.column_start + column, scope.first_top if page == 0 else 0


def _column_origin(page: PagePlacement, column: int, area_top: int) -> int | None:
    if column == 0:
        return page.body[0]
    area = next((area for area in reversed(page.column_areas) if area.top <= area_top), None)
    if area is None or area.gap is None or column >= len(area.widths):
        return None
    return page.body[0] + sum(area.widths[:column]) + column * area.gap


def _object_placement(section: int, paragraph: int, ordinal: int, obj: Any, size: tuple[int | None, int] | None,
                      capture: tuple[_ObjectFrame, _FrameTrace, int, _Page] | None,
                      pages: list[PagePlacement]) -> ObjectPlacement:
    pos = obj.find(f"{HP}pos")
    wrap = "AS_CHARACTER" if pos is not None and pos.get("treatAsChar") == "1" else obj.get("textWrap", "UNKNOWN")
    width, height = size if size is not None else (None, None)
    position = column = top = x = None
    if capture is not None:
        frame, scope, first_page, paper = capture
        page, column, offset = _scope_place(frame.frame, scope, first_page)
        if 0 <= page < len(pages):
            position = page
            top = paper.top + offset + frame.y if frame.y is not None else None
            origin = 0 if frame.paper_x else _column_origin(pages[page], column, paper.top + offset)
            x = origin + frame.x if origin is not None and frame.x is not None else None
        else:
            column = None
    unavailable = []
    if position is None:
        unavailable.append("object page not retained by the layout path")
    if (x is None or top is None) and wrap == "AS_CHARACTER" and position is not None:
        unavailable.append(_AMONG if x is None else _AMONG_TALL)
    elif x is None or top is None:
        unavailable.append("object origin not measured")
    if width is None or height is None:
        unavailable.append("object size not measured")
    return ObjectPlacement(section, paragraph, ordinal, _local(obj), wrap, position, column, x, top,
                           width, height, tuple(unavailable))


def _area_placement(section: int, paragraph: int, ordinal: int, frame: _AreaFrame, scope: _FrameTrace,
                    first_page: int, paper: _Page, pages: list[PagePlacement]) -> AreaPlacement:
    page, column, offset = _scope_place(frame.frame, scope, first_page)
    kind = _local(frame.source)
    if not 0 <= page < len(pages):
        return AreaPlacement(section, paragraph, ordinal, kind, unavailable=("area page not retained",))
    x = _column_origin(pages[page], column, paper.top + offset)
    top = paper.top + offset + frame.y if frame.y is not None else None
    lines = tuple(_placement_line(EstimatedLine(page, column, y), paper.top + offset, detail, styles)
                  for y, detail, styles in frame.lines)
    unavailable = []
    if top is None or x is None:
        unavailable.append("area origin not measured")
    if not lines or any(line.text is None for line in lines):
        unavailable.append("area line text ranges not fully retained")
    return AreaPlacement(section, paragraph, ordinal, kind, page, column, x, top, frame.width,
                         frame.height, lines, tuple(unavailable))


def _table_placement(address: tuple[int, int, int], capture: _TableCapture, scope: _FrameTrace,
                     first_page: int, paper_top: int, numbers: dict[Any, int] | None = None,
                     nested_places: dict[Any, list[tuple[int, int]]] | None = None,
                     left: tuple[float, bool] | None = None, pages: list[PagePlacement] | None = None) -> TablePlacement:
    """The placement of a table from the row parts the layout accepted. *numbers* gives the tables of its body
    paragraph their index there; *nested_places* collects, for each table standing on a line of one of its cells,
    the page and column of the row part showing that line. *left*: how far right the table's left edge stands,
    of its column's left edge or (True) of the paper's on *pages*."""

    table, parts = capture.table, capture.rows
    unavailable = []
    if not capture.absolute:
        unavailable.append(capture.vague)
    if table.doubt is not None:
        unavailable.append(table.doubt)
    if any(part.start is None for part in parts):
        unavailable.append("some split rows do not have a single measured line range")

    def frame_place(frame: int, y: int) -> tuple[int, int, int | None]:
        page, column, offset = _scope_place(frame, scope, first_page)
        lift = capture.lift if frame == capture.start_frame else 0
        top = paper_top + offset + y - lift
        return page, column, top if capture.absolute else None

    outline = {(part.frame, part.row, part.repeated): part for part in parts}
    elements = table.source.findall(f"{HP}tr/{HP}tc")
    grid = _grid_extents_of(table.source)
    cell_sources = [(element, row, span, measured)
                    for element, (row, span, measured) in zip(elements, table.cells)]
    cells_by_row: dict[int, list[int]] = {}
    for index, (_, row, _, _) in enumerate(cell_sources):
        cells_by_row.setdefault(row, []).append(index)
    first_in_frame: dict[int, int] = {}
    rows = []
    missing_left = False
    if left is None and table.left is not None:
        left = (table.left, False)
    for part in parts:
        first_in_frame.setdefault(part.frame, part.top)
        page, column, top = frame_place(part.frame, part.top)
        cells = _table_cells(part, outline, cells_by_row, cell_sources, grid, table, first_in_frame[part.frame],
                             place=(page, column), numbers=numbers, nested_places=nested_places)
        x = left[0] if left is not None else None
        if left is not None and left[1]:  # from the paper's left: less where the row's column starts
            origin = _column_origin(pages[page], column, top if top is not None else pages[page].body[1]) \
                if pages is not None and 0 <= page < len(pages) else None
            x = None if origin is None else left[0] - origin
        missing_left = missing_left or x is None
        if table.doubt is not None:  # the rows are the row model's, which the layout did not take: no heights
            rows.append(TableRowPlacement(part.row, page, column, None, None, part.start, part.stop, part.repeated,
                                          cells, x=x))
            continue
        rows.append(TableRowPlacement(part.row, page, column, top, part.height, part.start, part.stop,
                                      part.repeated, cells, part.top - first_in_frame[part.frame], x))
    if missing_left:
        unavailable.append("table left edge not measured")
    captions = []
    if parts and table.caption[0]:
        first = parts[0]
        page, column, top = frame_place(first.frame, first.top - table.caption[0])
        if first.frame != capture.start_frame:
            top = None  # the moved table starts from the margin; the caption's new origin was not measured
        captions.append(TableCaptionPlacement("top", page, column, top, table.caption[0]))
    if parts and table.caption[1]:
        captions.append(TableCaptionPlacement("bottom", *frame_place(*capture.finish), table.caption[1]))
    original = [part for part in parts if not part.repeated]
    split = None
    if len({part.frame for part in original}) > 1:
        split = "cell-lines" if len({part.row for part in original}) < len(original) or any(
            part.start not in (None, 0) or any(cell.start > 0 for cell in part.cells or ()) for part in original
        ) else "rows"
    moved = parts[0].frame != capture.start_frame if parts and capture.absolute else None
    return TablePlacement(*address, tuple(rows), tuple(captions), moved, split, tuple(unavailable))


def _nested_table_placement(address: tuple[int, int, int], table: Any, measured: _FlowTable,
                            placements: dict[Any, TablePlacement], numbers: dict[Any, int] | None = None,
                            nested_places: dict[Any, list[tuple[int, int]]] | None = None) -> TablePlacement | None:
    """A table in a cell of a placed table, its rows on the page of the part of the parent's row that holds it:
    the part showing the cell line it stands on (a table set as a character), or, where the cell's lines were not
    followed, the one part of a row that stayed whole on its page."""

    cell = _table_holder(table)
    if cell is None or _local(cell) != "tc":
        return None
    parent = next(cell.iterancestors(f"{HP}tbl"), None)
    if parent is None or parent not in placements or not placements[parent].rows:
        return None
    held = (nested_places or {}).get(table, [])
    if len(held) == 1:
        page, column = held[0]
    else:
        index = next((at for at, source in enumerate(parent.findall(f"{HP}tr/{HP}tc")) if source is cell), None)
        found = [(row.page, row.column, rectangle) for row in placements[parent].rows if not row.repeated
                 for rectangle in row.cells if rectangle.source_index == index]
        if held or index is None or len(found) != 1 or found[0][2].line_start != 0 or found[0][2].line_end is None:
            return None
        page, column = found[0][:2]
    parts: list[_RowPart] = []
    _whole_rows(measured, 0, 0, 0, len(measured.rows), parts)
    capture = _TableCapture(measured, parts, 0, (0, sum(row.height for row in measured.rows)), absolute=False)
    return _table_placement(address, capture, _FrameTrace((), 1, column_start=column), page, 0, numbers,
                            nested_places)


def _boxed_table_placement(address: tuple[int, int, int], measured: _FlowTable,
                           box: tuple[_ObjectFrame, _FrameTrace, int, _Page] | None, pages: list[PagePlacement],
                           numbers: dict[Any, int] | None,
                           nested_places: dict[Any, list[tuple[int, int]]] | None) -> TablePlacement | None:
    """A table in a text box, its rows on the page the layout keeps for the drawing holding the box (*box*; a
    text box does not split). ``None`` when the layout keeps no page for that drawing."""

    if box is None:
        return None
    frame, scope, first_page, _ = box
    page, column, _ = _scope_place(frame.frame, scope, first_page)
    if not 0 <= page < len(pages):
        return None
    parts: list[_RowPart] = []
    _whole_rows(measured, 0, 0, 0, len(measured.rows), parts)
    capture = _TableCapture(measured, parts, 0, (0, sum(row.height for row in measured.rows)), absolute=False,
                            vague="table origin in its text box not measured")
    return _table_placement(address, capture, _FrameTrace((), 1, column_start=column), page, 0, numbers,
                            nested_places)


#: The layout sets objects placed from an empty paragraph down where they fit and its line below them, on the next
#: page when it has no room there. Hancom's pages show a table set not to split on its line's page then: where the
#: layout leaves such a table is not what Hancom draws, so its rows are not given.
_LEFT_BEHIND = ("a table set not to split is left on the page before its paragraph's line: the layout does not "
                "follow it going on with that line")


def _left_behind(table: Any, placed: TablePlacement, line: EstimatedLine) -> bool:
    """Whether *table*, set not to split and placed from its paragraph, stands whole on a page before the page of
    that paragraph's first *line* (see :data:`_LEFT_BEHIND`)."""

    position = table.find(f"{HP}pos")
    return (position is not None and position.get("treatAsChar") != "1" and position.get("vertRelTo") == "PARA"
            and _page_break(table) == "NONE" and all(row.page < line.page for row in placed.rows))


#: What holds a table other than a body paragraph: a cell, a text box, a caption, or a header, footer or note.
_TABLE_HOLDERS = frozenset(("tc", "drawText", "caption", "header", "footer", "footNote", "endNote"))


def _unplaced_table(table: Any, measured: bool, placements: dict[Any, TablePlacement]) -> str:
    """Why the layout path keeps no rows for *table* (*measured*: its rows were read)."""

    holder = _table_holder(table)
    if holder is not None and _local(holder) != "tc":
        kind = {"drawText": "a text box", "caption": "a caption", "header": "a header", "footer": "a footer",
                "footNote": "a footnote", "endNote": "an endnote"}[_local(holder)]
        if kind == "a text box":
            return "a table in a text box: " + ("the layout keeps no page for the drawing holding it" if measured
                                                else "the box is laid out without reading the table's rows")
        return f"a table in {kind}: what {kind} holds is not placed row by row"
    if holder is None:
        if _floating(table):
            return "a table in front of or behind the text takes no room in the layout: its place is not computed"
        return "table placement not retained by the layout path"
    parent = placements.get(next(holder.iterancestors(f"{HP}tbl"), None))
    if parent is None or not parent.rows:
        return "the table holding it has no row placement"
    if not measured:
        return "its cell is laid out without reading the table's rows"
    position = table.find(f"{HP}pos")
    if position is not None and position.get("treatAsChar") == "1":
        return "its parent's row does not stand whole on one page, and the cell line the table stands on is not followed"
    return "its parent's row does not stand whole on one page, and the table is followed through its cell's lines, not row by row"


def _in_text_box(table: Any) -> bool:
    holder = _table_holder(table)
    return holder is not None and _local(holder) == "drawText"


def _table_holder(table: Any) -> Any:
    """The nearest cell, text box, caption, header, footer or note holding *table*; ``None`` in the body."""

    return next((up for up in table.iterancestors() if _local(up) in _TABLE_HOLDERS), None)


def _table_cells(part: _RowPart, outline: dict[tuple[int, int, bool], _RowPart],
                 cells_by_row: dict[int, list[int]], cell_sources: list[tuple[Any, int, int, _Row]],
                 grid: dict[Any, tuple[int, int]],
                 table: _FlowTable, frame_top: int, *, place: tuple[int, int] | None = None,
                 numbers: dict[Any, int] | None = None,
                 nested_places: dict[Any, list[tuple[int, int]]] | None = None) -> tuple[TableCellPlacement, ...]:
    result = []
    spacing = _cell_spacing(table.source)
    own = cells_by_row.get(part.row, [])
    selected: list[tuple[int, _CellSlice | None]] = (
        [(cell.source_cell, cell) for cell in part.cells] if part.cells is not None else
        [(index, None) for index in own]
    )
    for source_index, slice_ in selected:
        element, source_row, span, measured = cell_sources[source_index]
        if slice_ is not None:
            span = slice_.rows
        address = element.find(f"{HP}cellAddr")
        cell_span = element.find(f"{HP}cellSpan")
        column = int(address.get("colAddr", 0)) if address is not None else 0
        columns = int(cell_span.get("colSpan", 1)) if cell_span is not None else 1
        x, width = grid.get(element, (None, None))
        fragments = [outline.get((part.frame, row, part.repeated)) for row in range(part.row, part.row + span)]
        whole = all(piece is not None and piece.height is not None and piece.start == 0
                    and piece.stop == table.rows[piece.row].lines for piece in fragments)
        height = sum(piece.height for piece in fragments if piece is not None and piece.height is not None) - spacing \
            if whole else None
        # A single-cell split uses that cell's measured line sequence directly.
        representative = span == 1 and (len(own) == 1 or bool(measured.detail)
                                         and measured.detail is table.rows[part.row].detail)
        measured_lines = tuple((p, i, line) for p, details in enumerate(measured.detail)
                               for i, line in enumerate(details))
        unavailable = []
        starts_cell = whole or part.start == 0
        low, high = (0, measured.lines) if whole else (None, None)
        if slice_ is not None:
            low, high = slice_.start, slice_.stop
            measured_lines = measured_lines[slice_.start:slice_.stop]
            starts_cell = slice_.start == 0
            if all(piece is not None and piece.height is not None for piece in fragments):
                height = sum(piece.height for piece in fragments if piece is not None and piece.height is not None) - spacing
        elif not whole:
            if representative and part.start is not None and part.stop is not None and part.height is not None:
                low, high = part.start, part.stop
                measured_lines = measured_lines[part.start:part.stop]
                height = part.height - spacing
            else:
                measured_lines = ()
                unavailable.append("individual cell split extent not measured")
        if not measured.detail:  # the cell keeps no lines at all
            unavailable.append(measured.undetailed or "cell text line placements not retained by the layout path")
        if x is None:
            unavailable.append("no measured cell grid origin")
        if height is None and slice_ is not None:
            unavailable.append("cell fragment rectangle not fully measured")
        styles = [_run_positions(paragraph) for paragraph in element.findall(f"{HP}subList/{HP}p")]
        top: int | None = part.top - frame_top + spacing
        if table.doubt is not None:  # where the rows stand in the table is the row model's too
            top, height, starts_cell = None, None, False
            unavailable.append(table.doubt)
        shift = None if table.doubt is not None else _line_shift(measured, measured_lines, whole, height, spacing,
                                                                 starts_cell)
        lines = tuple(_table_cell_line(p, i, line, None if shift is None or line.top is None else line.top + shift,
                                       styles[p], numbers)
                      for p, i, line in measured_lines if p < len(styles))
        if any(line.text_start is None or line.text is None and not line.tables for line in lines):
            unavailable.append("cell text line ranges unavailable")
        if any(line.top is None for line in lines) and table.doubt is None:
            unavailable.append(_NO_LINE_TOPS if shift is None and not whole and measured.valign != "TOP"
                               else "cell line tops not measured")
        among: tuple[TableCellLinePlacement, ...] = ()
        if measured.nested and lines:
            lines, among = (), lines
            unavailable.append("the cell holds tables: its lines are in lines_with_tables")
        if nested_places is not None and place is not None and not part.repeated:
            for _, _, line in measured_lines:
                for held in line.tables:
                    nested_places.setdefault(held, []).append(place)
        result.append(TableCellPlacement(source_row, column, span, columns, x, top,
                                         width, height, lines, tuple(unavailable), source_index, low, high, among))
    return tuple(sorted(result, key=lambda cell: cell.column))


#: A cell split over a page end that sets its lines at its centre or foot: where Hancom stands them in each part
#: is not laid out.
_NO_LINE_TOPS = "cell line tops not measured: the cell is split over pages and not set at its top"


def _line_shift(cell: _Row, shown: tuple[tuple[int, int, _CellLine], ...], whole: bool, height: int | None,
                spacing: int, starts: bool) -> int | None:
    """What to add to the tops of a cell's lines (:attr:`_CellLine.top`, as in the whole cell set at its top) to
    stand them in the part of the cell *shown*, *height* tall when the cell is *whole* there: a whole cell sets
    its lines at its top, or leaves half the room its height has to spare above them (centre, rounded down), or
    all of it (bottom); a part of a split cell set at its top starts its first line below the cell's top margin
    and the room that line keeps above it (*starts*: the cell's first part, as the whole cell). ``None`` where
    the layout does not say: a split cell not set at its top, a line whose top or room above is not read."""

    if not shown or not cell.detail or not cell.detail[0]:
        return None
    if whole and height is not None:
        room = height + spacing - cell.height + cell.spare  # the cell's inner height less its lines
        return {"TOP": 0, "CENTER": room // 2, "BOTTOM": room}.get(cell.valign) if room >= 0 else None
    if cell.valign != "TOP":
        return None
    if starts:
        return 0
    origin, first = cell.detail[0][0], shown[0][2]
    if None in (origin.top, origin.lead, first.top, first.lead):
        return None
    return origin.top - origin.lead + first.lead - first.top  # type: ignore[operator]


def _table_cell_line(paragraph: int, index: int, line: _CellLine, top: int | None,
                     styles: _RunPositions | None, numbers: dict[Any, int] | None = None) -> TableCellLinePlacement:
    content = line.content
    return TableCellLinePlacement(
        paragraph, index, line.height, top,
        content.x if content else None, content.width if content else None,
        content.start if content else None, content.end if content else None, content.text if content else None,
        content.source if content else None,
        _line_runs(content, styles),
        tuple(numbers[held] for held in line.tables if held in numbers) if numbers else (),
    )


def _line_runs(content: _LineContent | None, styles: _RunPositions | None) -> tuple[tuple[str, str], ...]:
    if not content or not content.text or content.start is None or content.end is None or styles is None:
        return ()
    start, stop = bisect_left(styles.positions, content.start), bisect_left(styles.positions, content.end)
    if "".join(styles.characters[start:stop]) != content.text:
        return ()
    runs: list[tuple[str, list[str]]] = []
    for ref, text in zip(styles.references[start:stop], styles.characters[start:stop]):
        if not text:
            continue
        if not runs or ref != runs[-1][0]:
            runs.append((ref, []))
        runs[-1][1].append(text)
    return tuple((ref, "".join(text)) for ref, text in runs)


def _placement_line(position: EstimatedLine, top: int, detail: _LineDetail, styles: _RunPositions | None = None
                    ) -> LinePlacement:
    content = detail.content
    missing = []
    if content is None or content.text is None:
        missing.append(detail.text_unavailable or "no character range in this layout path")
    if content is None or content.x is None:
        missing.append("no horizontal origin in this layout path")
    if content is None or content.width is None:
        missing.append("no finite line width in this layout path")
    return LinePlacement(
        position, top + position.vertpos, detail.height,
        content.x if content is not None else None, content.width if content is not None else None,
        content.start if content is not None else None, content.end if content is not None else None,
        content.text if content is not None else None, content.source if content is not None else None,
        detail.hidden, tuple(missing), _line_runs(content, styles),
    )
