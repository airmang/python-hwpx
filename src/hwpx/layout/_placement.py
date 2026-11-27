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
    _DEFAULT_TAB_STOP, _GLYPH_SPACE, _HANGING_SPACES, _LAYOUT_UNIT, _TYPED_NO_BREAK_SPACE, _line_origin, _style_number,
    auto_space_gap, char_advance, paragraph_label, tab_reach,
)
from ..oxml.container import _outermost_factors, _unturned_box
from ..oxml.namespaces import HH, HP
from ..oxml.paragraph_heading import paragraph_heading
from ..oxml.table_sizes import _grid_extents_of, cell_margins_of
from ._page_measure import (
    _DRAWINGS, _NO_WRAP, _OBJECTS, _CellLine, _CellSlice, _FlowTable, _LineContent, _Measure, _Row, _RowPart,
    _Unsupported, _caption, _caption_beside, _cell_spacing, _cell_text_ranges, _drawn_height, _effect_room,
    _end_ref, _end_size, _extent, _extent_margins, _floating, _indented, _inline_content, _line_metrics, _line_widths,
    _local, _margin, _marks, _object_extent, _objects_among, _page_break, _shadow_drop, _table_alone, _text_size,
    _whole_rows,
)
from .pages import (
    AreaPlacement, EstimatedLine, LabelPlacement, LayoutEstimate, LinePlacement, ObjectPlacement, PageEstimate,
    PagePlacement,
    ParagraphPlacement, TableCaptionPlacement, TableCellLinePlacement, TableCellPlacement, TablePlacement,
    TableRowPlacement, TabPlacement, _AreaFrame, _FrameTrace, _LineDetail, _ObjectFrame, _Page, _RunPositions, _SectionLayout,
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
    labels = _Labels(measure) if measure is not None else None
    tabs = _Tabs(measure) if measure is not None else None
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
            if lines and labels is not None:
                lines[0] = labels.first_line(body_sources[section][index], lines[0])
            if tabs is not None and any(line.text and "\t" in line.text for line in lines):
                stop = _part_tab_stop(body_sources[section], index)
                lines = [tabs.line(body_sources[section][index], line, _body_room(pages), stop) for line in lines]
            paragraphs.append(ParagraphPlacement(section, index, tuple(lines)))
    tables: list[TablePlacement] = []
    table_sources: list[Any] = []
    objects: list[ObjectPlacement] = []
    areas: list[AreaPlacement] = []
    by_source: dict[Any, TablePlacement] = {}
    paragraph_origins = {(entry.section, entry.paragraph): entry.lines[0].position
                         for entry in paragraphs if entry.lines}
    paragraph_lines = {(entry.section, entry.paragraph): entry.lines for entry in paragraphs}
    nested_places: dict[Any, list[tuple[int, int]]] = {}
    object_places: dict[Any, ObjectPlacement] = {}
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
                    if measure is not None:
                        measure.tab_stop = _part_tab_stop(source, index)
                    result = _nested_table_placement(address, table, inline_tables[table], by_source, numbers,
                                                     nested_places, measure)
                else:
                    result = None
                if result is None:
                    reason = (untraced or {}).get(table) or _unplaced_table(table, table in inline_tables, by_source)
                    result = TablePlacement(*address, (), unavailable=(reason,))
                origin = paragraph_origins.get((section, index))
                position = table.find(f"{HP}pos")
                if result.rows and measure is not None and _NO_LEFT in result.unavailable and position is not None \
                        and position.get("treatAsChar") == "1" and table.getparent().getparent() is paragraph:
                    result = _table_on_text_line(result, table, measure, source, index,
                                                 paragraph_lines.get((section, index), ()), pages)
                if result.rows and origin is not None and table.getparent().getparent() is paragraph:
                    first = result.rows[0]
                    if (first.page, first.column) > (origin.page, origin.column):
                        result = replace(result, moved=True)
                    elif _left_behind(table, result, origin):
                        result = TablePlacement(*address, (), unavailable=(_LEFT_BEHIND,))
                if labels is not None and result.rows:
                    result = _labelled_cells(result, table, labels)
                if tabs is not None and result.rows:
                    result = _tabbed_cells(result, table, tabs, _part_tab_stop(source, index))
                by_source[table] = result
                tables.append(result)
                table_sources.append(table)
            for ordinal, obj in enumerate(node for node in paragraph.iter() if _local(node) in _DRAWINGS):
                placed = _object_placement(section, index, ordinal, obj, sizes.get(obj), object_captures.get(obj), pages)
                if placed.page is None:
                    placed = _held_object(placed, obj, object_places, by_source)
                    if placed.wrap == "AS_CHARACTER" and measure is not None:
                        placed = _in_cell(placed, obj, measure, by_source, pages, source, index)
                    placed = _group_member(placed, obj, object_places)
                elif placed.x is None and placed.wrap == "AS_CHARACTER" and measure is not None \
                        and obj.getparent() is not None and obj.getparent().getparent() is paragraph:
                    placed = _among_text(placed, obj, measure, source, index, paragraph_lines.get((section, index), ()),
                                         pages)
                if measure is not None and obj.find(f"{HP}drawText") is not None:
                    measure.tab_stop = _part_tab_stop(source, index)
                    held, why = _box_lines(measure, obj, None if None in (placed.width, placed.height)
                                           else (placed.width, placed.height))  # type: ignore[arg-type]
                    if labels is not None:
                        held = _labelled_lines(held, obj.findall(f"{HP}drawText/{HP}subList/{HP}p"), labels)
                    if tabs is not None and any(line.text and "\t" in line.text for line in held):
                        inside = _box_room(obj, None if None in (placed.width, placed.height)
                                           else (placed.width, placed.height))  # type: ignore[arg-type]
                        held = tabs.lines(held, obj.findall(f"{HP}drawText/{HP}subList/{HP}p"),
                                          _fixed_room(inside), measure.tab_stop)
                    placed = replace(placed, lines=held, unavailable=(*placed.unavailable, *why))
                object_places[obj] = placed
                objects.append(placed)
    # headers and footers after the tables: one in a table cell starts on the page of the part of its row showing it
    running, numbers_by_page = _running_areas(body_sources, paragraph_origins, pages, papers, measure, by_source,
                                              labels, tabs)
    pages[:] = [replace(page, number=number) for page, number in zip(pages, numbers_by_page)]
    held_by: dict[Any, list[TablePlacement]] = {}
    for shown, _ in running.values():
        for *_, held in shown:
            for source, placed in held:
                held_by.setdefault(source, []).append(placed)
    for at, source in enumerate(table_sources):
        if source in held_by:
            kind = _local(_table_holder(source))
            tables[at] = replace(tables[at], unavailable=(
                f"a table in a {kind}: placed with the {kind} on each page it is drawn on (AreaPlacement.tables)",
                *held_by[source][0].unavailable))
    for section, source in enumerate(body_sources):
        for index, paragraph in enumerate(source):
            for ordinal, area in enumerate(node for node in paragraph.iter() if _local(node) in _AREA_NAMES):
                found = area_captures.get(area)
                if found:
                    headed = labels is not None and any((held.get("paraPrIDRef") or "") in labels.kinds
                                                        for held in area.findall(f"{HP}subList/{HP}p"))
                    areas.extend(replace(placed, unavailable=(*placed.unavailable, _NOTE_LABEL)) if headed and
                                 placed.lines else placed
                                 for placed in (_note_tabs(_area_placement(section, index, ordinal, *capture, pages))
                                                for capture in found))
                elif area.getparent() is not None and _local(area.getparent()) == "secPr":
                    areas.append(AreaPlacement(section, index, ordinal, _local(area), unavailable=(_STORY_COPY,)))
                elif area in running:
                    shown, missing = running[area]
                    areas.extend(AreaPlacement(section, index, ordinal, _local(area), page, 0, *box, lines,
                                               unavailable=missing, tables=tuple(table for _, table in held))
                                 for page, box, lines, held in shown)
                    if not shown:
                        areas.append(AreaPlacement(section, index, ordinal, _local(area), unavailable=missing))
                else:
                    areas.append(AreaPlacement(section, index, ordinal, _local(area),
                                               unavailable=("area placement not retained by the layout path",)))
    return LayoutEstimate(estimate, tuple(pages), tuple(paragraphs), tuple(tables), tuple(objects), tuple(areas))


_AREA_NAMES = frozenset(("header", "footer", "footNote", "endNote"))


#: A header's or footer's pages, each with its room there (x, top, width, height on the paper), its lines and the
#: tables on them (each with its source).
_Shown = list[tuple[int, tuple[int, int, int, int], tuple[LinePlacement, ...], tuple[tuple[Any, TablePlacement], ...]]]


def _running_areas(sources: list[list[Any]], origins: dict[tuple[int, int], EstimatedLine],
                   pages: list[PagePlacement], papers: list[_Page], measure: _Measure | None = None,
                   tables: dict[Any, TablePlacement] | None = None, labels: _Labels | None = None,
                   tabs: _Tabs | None = None) -> tuple[dict[Any, tuple[_Shown, tuple[str, ...]]], list[int | None]]:
    """Each header and footer control of the body's paragraphs (in a run of the paragraph or in one of its table
    cells) -> the pages it is drawn on, with its room there (x, top, width, height on the paper) and its lines (see
    :func:`_running_lines`), and what is not given; and the number Hancom prints on each page (see
    :func:`_page_numbers`).

    A control takes effect on the page of its paragraph's first line, or, in a table cell, of the part of the
    cell's row showing the cell paragraph holding it (see :func:`_control_page`). On each page of its section
    Hancom draws the last control of a kind that applies there and has taken effect (python-hwpx writes a
    ``BOTH`` one ahead of the ``ODD``/``EVEN`` ones for that reason): ``BOTH`` on every page, ``ODD`` and ``EVEN``
    on the pages whose number is odd or even. It is left off the section's first page where the section hides it
    there (``hp:visibility``) and off a page whose paragraphs hide it (``hp:pageHiding``). Its room is the page's:
    above the body as tall as the header margin, below it as tall as the footer margin."""

    result: dict[Any, tuple[_Shown, tuple[str, ...]]] = {}
    numbers = _page_numbers(sources, origins, pages, tables or {})
    for section, paragraphs in enumerate(sources):
        own = [page.page for page in pages if page.section == section]
        hidden: dict[str, set[int]] = {"header": set(), "footer": set()}
        visibility = next(paragraphs[0].iter(f"{HP}visibility"), None) if paragraphs else None
        found: list[tuple[int, str, Any, int]] = []
        for index, paragraph in enumerate(paragraphs):
            origin = origins.get((section, index))
            if origin is None or not own:
                continue
            for control, node in _page_controls(paragraph, ("pageHiding", "header", "footer")):
                at = _control_page(control, paragraph, origin.page, tables or {})
                name = _local(node)
                if isinstance(at, str):
                    if name in hidden:
                        result[node] = ([], (f"{name} {at}",))
                elif name == "pageHiding":
                    for kind in hidden:
                        if node.get("hide" + kind.capitalize()) in ("1", "true"):
                            hidden[kind].add(at)
                else:
                    found.append((at, name, node, index))
        for kind in hidden:
            if own and visibility is not None and visibility.get("hideFirst" + kind.capitalize()) in ("1", "true"):
                hidden[kind].add(own[0])
        drawn: dict[Any, list[int]] = {node: [] for _, _, node, _ in found}
        unknown: set[Any] = set()
        for page in own:
            for kind, off in hidden.items():
                started = [entry for entry in found if entry[1] == kind and entry[0] <= page]
                ruling = None
                for entry in reversed(started):
                    applies = _applies(entry[2], numbers[page])
                    if applies is None:  # whether it, or one before it, shows here is not known
                        unknown.update(other[2] for other in started)
                        break
                    if applies:
                        ruling = entry
                        break
                if ruling is not None and page not in off:
                    drawn[ruling[2]].append(page)
        for _, kind, node, index in found:
            shown: _Shown = []
            why: str | None = None
            laid: dict[tuple[int, int], tuple[tuple[tuple[int, _LineDetail, _RunPositions | None, int, int], ...],
                                              str | None]] = {}
            standing: dict[tuple[int, int], list[_HeldTable]] = {}
            held = node.findall(f"{HP}subList/{HP}p")
            for page in drawn[node]:
                paper = papers[page]
                top, tall = (paper.top - paper.header, paper.header) if kind == "header" \
                    else (paper.top + paper.body, paper.footer)
                lines: tuple[LinePlacement, ...] = ()
                tables: tuple[tuple[Any, TablePlacement], ...] = ()
                why = f"{kind} lines are not laid out"
                if measure is not None:
                    if (paper.text_width, tall) not in laid:
                        measure.tab_stop = _part_tab_stop(paragraphs, index)
                        laid[paper.text_width, tall] = _running_lines(measure, node, kind, paper.text_width, tall)
                        standing[paper.text_width, tall] = _running_tables(measure, node, kind, paper.text_width, tall)
                    placed, why = laid[paper.text_width, tall]
                    lines = tuple(_placement_line(EstimatedLine(page, 0, top + y - paper.top), paper.top, detail,
                                                  styles) for y, detail, styles, _, _ in placed)
                    if labels is not None:
                        lines = tuple(labels.first_line(held[number], line) if not order and number < len(held)
                                      else line for line, (_, _, _, number, order) in zip(lines, placed))
                    stop = _part_tab_stop(paragraphs, index)
                    if tabs is not None and any(line.text and "\t" in line.text for line in lines):
                        lines = tuple(tabs.line(held[number], line, _fixed_room((0, paper.text_width)), stop)
                                      if number < len(held) else line
                                      for line, (_, _, _, number, _) in zip(lines, placed))
                    tables = _area_tables(section, index, paragraphs[index], standing[paper.text_width, tall], page,
                                          top, labels, tabs, stop)
                    if why == _HOLDS.format(kind=kind) and tables and all(
                            _complete(table) and _table_alone(source.getparent().getparent().findall(f"{HP}run"))
                            is source for source, table in tables) and not any(
                            _local(child) in _OBJECTS and child not in dict(tables)
                            for paragraph in held for child in paragraph.iter()):
                        why = None  # what it holds besides its text: tables alone on their lines, placed there
                shown.append((page, (paper.left, top, paper.text_width, tall), lines, tables))
            reasons = () if why is None else (why,)
            if node in unknown:
                reasons = ((f"{kind} for odd or even pages, or before one: the page numbers of its section are not "
                            "counted"), *reasons)
            elif not shown:
                reasons = ((f"{kind} drawn on no page: no page of its section from where it starts applies to it, "
                            f"or a later {kind} or a page hiding it takes each that does"),)
            result[node] = (shown, reasons)
    return result, numbers


#: A header or footer copy python-hwpx up to 6.x kept under the section settings besides its control.
_STORY_COPY = ("a header or footer kept under the section settings (hp:secPr): Hancom reads it from its control "
               "(hp:ctrl) only, placed there")
#: What holds a control of a body paragraph other than the paragraph's own runs.
_CONTROL_HOLDERS = frozenset(("tc", "drawText", "caption", "header", "footer", "footNote", "endNote", "secPr"))


def _page_controls(paragraph: Any, names: tuple[str, ...]) -> list[tuple[Any, Any]]:
    """(``hp:ctrl``, its child) of each control named in *names* of body *paragraph*: in its runs, and in the
    paragraphs of its table cells and text boxes, but not in a header, footer, note or caption it holds."""

    found = []
    for control in paragraph.iter(f"{HP}ctrl"):
        holder = next((up for up in control.iterancestors() if up is paragraph or _local(up) in _CONTROL_HOLDERS), None)
        if holder is not paragraph and (holder is None or _local(holder) not in ("tc", "drawText")):
            continue
        found += [(control, node) for node in control if _local(node) in names]
    return found


def _control_page(control: Any, paragraph: Any, page: int, tables: dict[Any, TablePlacement]) -> int | str:
    """The page a control of body *paragraph* takes effect on: *page* (its first line's) in one of its runs; in a
    table cell, the page of the first part of the cell's row showing a line of the cell paragraph holding it, or
    the one page the cell stands on; else why not."""

    cell = next((up for up in control.iterancestors() if up is paragraph or _local(up) in _CONTROL_HOLDERS), None)
    if cell is paragraph or cell is None:
        return page
    if _local(cell) != "tc":
        return "in a text box: the page it takes effect on is not followed"
    table = next(cell.iterancestors(f"{HP}tbl"), None)
    placement = tables.get(table)
    if placement is None or not placement.rows:
        return "in a table cell of a table without row placement: the page it takes effect on is not followed"
    number = next((at for at, other in enumerate(table.findall(f"{HP}tr/{HP}tc")) if other is cell), None)
    held = next((up for up in control.iterancestors(f"{HP}p")), None)
    order = next((at for at, other in enumerate(cell.findall(f"{HP}subList/{HP}p")) if other is held), None)
    parts = [(row.page, part) for row in placement.rows if not row.repeated
             for part in row.cells if part.source_index == number]
    showing = [at for at, part in parts if any(line.paragraph == order for line in part.lines or part.lines_with_tables)]
    if showing:
        return showing[0]
    if len({at for at, _ in parts}) == 1:
        return parts[0][0]
    return "in a table cell over several pages: the page of the cell line holding it is not laid out"


def _applies(node: Any, number: int | None) -> bool | None:
    """Whether a header or footer (*node*) applies to a page numbered *number*: ``BOTH`` always, ``ODD`` and
    ``EVEN`` by the number; ``None`` where the number is not known."""

    kind = node.get("applyPageType", "BOTH")
    if kind == "BOTH":
        return True
    if number is None:
        return None
    return (number % 2 == 1) == (kind == "ODD")


def _page_numbers(sources: list[list[Any]], origins: dict[tuple[int, int], EstimatedLine],
                  pages: list[PagePlacement], tables: dict[Any, TablePlacement]) -> list[int | None]:
    """The number Hancom prints on each page, as the section settings and controls say: the first page 1, or its
    section's ``hp:startNum@page`` when not 0 (0 goes on from the page before), each later page one more, a page
    holding an ``hp:newNum`` control of page numbers (``numType="PAGE"``) its ``num``. ``None`` from a section set
    to start on an odd or even page whose first number is not one (Hancom adds a page there that the layout does
    not), from a page holding a control the count does not follow (``hp:pageNumCtrl``, ``hp:newNum`` whose page is
    not known), and on."""

    numbers: list[int | None] = [None] * len(pages)
    number: int | None = 0
    for section, paragraphs in enumerate(sources):
        own = [page.page for page in pages if page.section == section]
        if not own:
            continue
        settings = next(paragraphs[0].iter(f"{HP}secPr"), None) if paragraphs else None
        start = settings.find(f"{HP}startNum") if settings is not None else None
        first = _stored_number(start.get("page", "0")) if start is not None else 0
        opening = first if first != 0 else None if number is None else number + 1
        side = start.get("pageStartsOn", "BOTH") if start is not None else "BOTH"
        if opening is not None and side != "BOTH" and (opening % 2 == 1) != (side == "ODD"):
            opening = None
        resets: dict[int, int | None] = {own[0]: opening}
        for index, paragraph in enumerate(paragraphs):
            origin = origins.get((section, index))
            if origin is None:
                continue
            for control, node in _page_controls(paragraph, ("newNum", "pageNumCtrl")):
                if _local(node) == "newNum" and node.get("numType", "PAGE") != "PAGE":
                    continue
                at = _control_page(control, paragraph, origin.page, tables)
                if isinstance(at, str):
                    resets[origin.page] = None
                else:
                    resets[at] = _stored_number(node.get("num", "")) if _local(node) == "newNum" else None
        for page in own:
            if page in resets:
                number = resets[page]
            elif number is not None:
                number += 1
            numbers[page] = number
    return numbers


def _stored_number(value: str) -> int | None:
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number >= 0 else None


def _box_lines(measure: _Measure, obj: Any, size: tuple[int, int] | None = None
               ) -> tuple[tuple[TableCellLinePlacement, ...], tuple[str, ...]]:
    """Placement tracing only: the lines of the text a rectangle holds (``hp:drawText``), laid out as a cell's are
    (see :func:`_sub_list_lines`) at the width of the box (``lastWidth``, else its own; a member of a group without
    a size of its own: *size*, as drawn in its group, when ``lastWidth`` says the same) inside its text margins,
    with their top and x relative to the box: below its top text margin, set at the top, centre or foot of the
    room the drawing's height (as the layout draws it, see :func:`~hwpx.layout._page_measure._drawn_height`)
    leaves as its text says (``hp:subList@vertAlign``); and what is not given. ``((), ())`` for a drawing
    holding no text."""

    box = obj.find(f"{HP}drawText")
    sub_list = box.find(f"{HP}subList") if box is not None else None
    paragraphs = sub_list.findall(f"{HP}p") if sub_list is not None else []
    if not paragraphs:
        return (), ()
    if _local(obj) != "rect":
        return (), ("text in a drawing other than a rectangle: where its lines stand is not laid out",)
    if sub_list.get("textDirection", "HORIZONTAL") != "HORIZONTAL":
        return (), ("text box text running down: its lines are not laid out",)
    if obj.find(f"{HP}sz") is None and (size is None or box.get("lastWidth", "0") not in ("0", str(size[0]))):
        return (), ("text box without a size of its own (hp:sz) or as drawn in its group: its lines are not laid "
                    "out",)
    margin = box.find(f"{HP}textMargin")
    left, right, top, bottom = (0, 0, 0, 0) if margin is None else (
        int(margin.get(side, 0)) for side in ("left", "right", "top", "bottom"))
    width = size[0] if obj.find(f"{HP}sz") is None and size is not None \
        else int(box.get("lastWidth", 0)) or int(obj.find(f"{HP}sz").get("width", 0))
    try:
        laid = _sub_list_lines(measure, paragraphs, width - left - right)
        tall = size[1] if obj.find(f"{HP}sz") is None and size is not None else _drawn_height(obj, measure)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return (), ("text box lines are not laid out",)
    tops, reach = _stacked_tops(measure, paragraphs, [(height, advance) for height, advance, *_ in laid])
    room = tall - top - reach - bottom
    shift = {"TOP": 0, "CENTER": room // 2, "BOTTOM": room}.get(sub_list.get("vertAlign", "TOP")) \
        if room >= 0 else None
    lines = tuple(TableCellLinePlacement(
        paragraph, line, height, None if shift is None else top + y + shift,
        None if content is None or content.x is None else content.x + left,
        content.width if content else None, content.start if content else None, content.end if content else None,
        content.text if content else None, content.source if content else None, _line_runs(content, styles))
        for y, (height, _, content, styles, paragraph, line) in zip(tops, laid))
    missing = []
    if shift is None:
        missing.append("text box text taller than the box: where its lines stand up and down is not laid out")
    if any(_local(child) in _OBJECTS for paragraph in paragraphs for child in paragraph.iter()):
        missing.append("a text box holding a table or a drawing: what it holds besides its text is not placed")
    elif any(line.text is None for line in lines):
        missing.append("text box line text ranges not fully retained")
    return lines, tuple(missing)


def _sub_list_lines(measure: _Measure, paragraphs: list[Any], width: int
                    ) -> list[tuple[int, int, _LineContent | None, _RunPositions | None, int, int]]:
    """Placement tracing only: the lines of the *paragraphs* of a header, a footer or a text box laid out *width*
    wide as a cell's are (:meth:`~hwpx.layout._page_measure._Measure.stack_lines`, keeping their layout caches),
    each as (height, advance to the next line's top, its text range, its runs, paragraph, line in it); the lines of
    a paragraph holding a table or a drawing have no text (their text is not all they hold, and what else they hold
    is not placed). Raises where the layout does not follow them."""

    metrics = measure.stack_lines(paragraphs, width, caches=True)
    found: list[tuple[_LineContent | None, _RunPositions | None, int, int]] = []
    for number, paragraph in enumerate(paragraphs):
        count = len(measure.stack_lines([paragraph], width, caches=True))
        runs = paragraph.findall(f"{HP}run")
        content = _cell_text_ranges(measure, paragraph, runs, width, count)
        # a paragraph holding a table or a drawing: its text is not all its lines hold, what else is not placed
        holds = any(_local(node) in _OBJECTS for node in paragraph.iter())
        styles = _run_positions(paragraph)
        found += [(None if not content else replace(content[line], text=None) if holds else content[line], styles,
                   number, line) for line in range(count)]
    if not metrics or len(found) != len(metrics):
        raise _Unsupported("lines not matched")
    return [(height, advance, *rest) for (height, advance), rest in zip(metrics, found)]


def _stacked_tops(measure: _Measure, paragraphs: list[Any], metrics: list[tuple[int, int]]) -> tuple[list[int], int]:
    """How far below the top of the text each line stands (the first below the first paragraph's spacing before,
    as in a cell), and how far down the last one reaches."""

    y, tops = measure.shape(paragraphs[0].get("paraPrIDRef")).prev, []
    for _, advance in metrics:
        tops.append(y)
        y += advance
    return tops, tops[-1] + metrics[-1][0]


#: Why a header's or footer's lines leave out what it holds besides its text (its tables are on
#: :attr:`~hwpx.layout.pages.AreaPlacement.tables`; a header holding only tables alone on their lines, all placed
#: there, leaves it out).
_HOLDS = "{kind} holds a table or a drawing: what it holds besides its text is not placed"


def _running_lines(measure: _Measure, node: Any, kind: str, width: int, tall: int
                   ) -> tuple[tuple[tuple[int, _LineDetail, _RunPositions | None, int, int], ...], str | None]:
    """Placement tracing only: the lines of a header or footer (*node*) laid out at the *width* of its room as a
    cell's lines are (see :func:`_sub_list_lines`), each with how far below its room's top it stands (set at the
    room's top, centre or foot as its text says, ``hp:subList@vertAlign``, the room *tall*), its paragraph and its
    place in it; and what is not given: a text taller than its room, or running otherwise than across, is not
    placed."""

    sub_list = node.find(f"{HP}subList")
    paragraphs = sub_list.findall(f"{HP}p") if sub_list is not None else []
    if not paragraphs:
        return (), f"{kind} holds no paragraph"
    if sub_list.get("textDirection", "HORIZONTAL") != "HORIZONTAL":
        return (), f"{kind} text running down: its lines are not laid out"
    try:
        laid = _sub_list_lines(measure, paragraphs, width)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return (), f"{kind} lines are not laid out"
    tops, reach = _stacked_tops(measure, paragraphs, [(height, advance) for height, advance, *_ in laid])
    room = tall - reach
    shift = {"TOP": 0, "CENTER": room // 2, "BOTTOM": room}.get(sub_list.get("vertAlign", "TOP"))
    if room < 0 or shift is None:
        return (), f"{kind} text taller than its room: where Hancom sets it is not laid out"
    lines = tuple((top + shift, _LineDetail(height, content), styles, number, order)
                  for top, (height, _, content, styles, number, order) in zip(tops, laid))
    if any(_local(child) in _OBJECTS for paragraph in paragraphs for child in paragraph.iter()):
        return lines, _HOLDS.format(kind=kind)
    complete = all(detail.content is not None and detail.content.text is not None for _, detail, *_ in lines)
    return lines, None if complete else "area line text ranges not fully retained"


#: A table on a line of a header or footer, as :func:`_running_tables` finds it: the table, its rows as the layout
#: measures them (``None``: not followed), its left edge right of the room's and its first row's top below the
#: room's top (``None``: not given), and why each of those is missing.
_HeldTable = tuple[Any, _FlowTable | None, float | None, int | None, str | None, str | None]


def _running_tables(measure: _Measure, node: Any, kind: str, width: int, tall: int) -> list[_HeldTable]:
    """Placement tracing only: each table a header or footer (*node*) holds in its own paragraphs, laid out at the
    *width* of its room *tall* as :func:`_running_lines` lays its lines, with where it stands there: a table set as
    a character on the line holding it, alone on it as one alone on a body line stands
    (:func:`~hwpx.layout.pages._on_its_line`), among text where an object so set stands (:func:`_x_on_line`, the
    line measured from the room's left edge), below its top outer margin and a caption above it when the line is as
    tall as it with them; and why what is missing is not given (see :data:`_HeldTable`)."""

    from .pages import _on_its_line, _traced_table  # placement tracing only

    sub_list = node.find(f"{HP}subList")
    paragraphs = sub_list.findall(f"{HP}p") if sub_list is not None else []
    held = [(number, table) for number, paragraph in enumerate(paragraphs) for run in paragraph.findall(f"{HP}run")
            for table in run.findall(f"{HP}tbl")]
    if not held:
        return []
    laid: list[tuple[int, int, _LineContent | None, int, int]] | None = None
    shift = None
    lost = f"{kind} lines are not laid out"
    if sub_list.get("textDirection", "HORIZONTAL") != "HORIZONTAL":
        lost = f"{kind} text running down: its lines are not laid out"
    else:
        try:
            lines = _sub_list_lines(measure, paragraphs, width)
            tops, reach = _stacked_tops(measure, paragraphs, [(height, advance) for height, advance, *_ in lines])
            laid = [(top, height, content, number, order)
                    for top, (height, _, content, _, number, order) in zip(tops, lines)]
            room = tall - reach
            shift = {"TOP": 0, "CENTER": room // 2, "BOTTOM": room}.get(sub_list.get("vertAlign", "TOP")) \
                if room >= 0 else None
        except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
            laid = None
    found: list[_HeldTable] = []
    for number, table in held:
        position = table.find(f"{HP}pos")
        if position is None or position.get("treatAsChar") != "1":
            why = (f"a table in a {kind} placed otherwise than as a character: where Hancom stands it in the {kind} "
                   "is not laid out")
            found.append((table, None, None, None, why, why))
            continue
        try:
            flow = measure.inline_tables.get(measure.source_control(table)) or _traced_table(measure, table)
            if flow is not None:
                flow = replace(flow, caption=_caption(measure, table))
        except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
            flow = None
        if flow is None:
            why = measure.untraced_tables.get(measure.source_control(table)) or \
                f"a table in a {kind}: its rows are not followed by the row model"
            found.append((table, None, None, None, why, why))
            continue
        if laid is None:
            found.append((table, flow, None, None, f"{_NO_LEFT}: {lost}", f"{_NO_ORIGIN}: {lost}"))
            continue
        paragraph = paragraphs[number]
        own = [(top, height, content, order) for top, height, content, at, order in laid if at == number]
        x: float | None = None
        drop: int | None = None
        line_top: int | None = None
        why_left: str | None = None
        try:
            if _table_alone(paragraph.findall(f"{HP}run")) is table and len(own) == 1:
                line_top, height, content, _ = own[0]
                placed = _on_its_line(measure, paragraph, table, flow, None if content is None else content.x,
                                      None if content is None else content.width, height)
                x, drop = placed.left, placed.drop
                if x is None:
                    why_left = (f"{_NO_LEFT}: a table set as a character alone on a line of a {kind} narrower than it "
                                "with its outer margins, or its line has no horizontal origin or width")
            else:
                standing = tuple(TableCellLinePlacement(
                    number, order, height, top, None if content is None else content.x,
                    None if content is None else content.width, None if content is None else content.start,
                    None if content is None else content.end, None, None if content is None else content.source)
                    for top, height, content, order in own)
                at = _x_on_line(table, measure, paragraph, standing, lambda _: (0, width))
                if isinstance(at, str):
                    why_left = f"{_NO_LEFT}: " + at.replace("object set as a character",
                                                            f"a table set as a character among the text of a {kind}")
                else:
                    x, line = at
                    line_top = line.top
                    margin = table.find(f"{HP}outMargin")
                    box = sum(row.height for row in flow.rows) + _cell_spacing(table) + _extent_margins(table) \
                        + sum(flow.caption)
                    drop = (0 if margin is None else _margin(margin, "top")) + flow.caption[0] \
                        if flow.doubt is None and box == line.height else None
        except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
            x, drop, line_top, why_left = None, None, None, f"{_NO_LEFT}: its line in the {kind} is not measured"
        top = None if None in (shift, drop, line_top) else line_top + shift + drop  # type: ignore[operator]
        why_top = None
        if top is None:
            why_top = f"{_NO_ORIGIN}: " + (
                f"{kind} text taller than its room: where Hancom sets it is not laid out" if shift is None else
                f"its line in the {kind} is not measured" if line_top is None else
                f"its line in the {kind} is taller than it, or its rows' heights are not measured")
        found.append((table, flow, x, top, why_left, why_top))
    return found


def _area_tables(section: int, index: int, paragraph: Any, held: list[_HeldTable], page: int, room_top: int,
                 labels: _Labels | None, tabs: _Tabs | None = None, tab_stop: int = _DEFAULT_TAB_STOP
                 ) -> tuple[tuple[Any, TablePlacement], ...]:
    """The tables of a header or footer standing in body paragraph *index* of *section* (*paragraph*), as
    :func:`_running_tables` finds them (*held*), on *page*, whose room for it starts *room_top* down the paper:
    each with its rows there (their tops on the paper, their left edge right of the room's)."""

    numbers = {table: number for number, table in enumerate(paragraph.iter(f"{HP}tbl"))}
    result = []
    for table, flow, x, top, why_left, why_top in held:
        address = section, index, numbers.get(table, -1)
        if flow is None:
            result.append((table, TablePlacement(*address, (), unavailable=tuple(
                dict.fromkeys(why for why in (why_left, why_top) if why)))))
            continue
        parts: list[_RowPart] = []
        _whole_rows(flow, 0, 0, 0, len(flow.rows), parts)
        capture = _TableCapture(flow, parts, 0, (0, sum(row.height for row in flow.rows)), absolute=top is not None,
                                vague=why_top or _NO_ORIGIN)
        placed = _table_placement(address, capture, _FrameTrace((), 1), page, room_top + (top or 0), numbers,
                                  None, None if x is None else (x, False))
        if why_left is not None:
            placed = replace(placed, unavailable=tuple(why_left if why == _NO_LEFT else why
                                                       for why in placed.unavailable))
        placed = replace(placed, moved=None)  # it stands on its line in the header or footer, which does not move
        if labels is not None and placed.rows:
            placed = _labelled_cells(placed, table, labels)
        if tabs is not None and placed.rows:
            placed = _tabbed_cells(placed, table, tabs, tab_stop)
        result.append((table, placed))
    return tuple(result)


def _complete(placed: TablePlacement) -> bool:
    return bool(placed.rows) and all(None not in (row.top, row.x, row.height) for row in placed.rows)


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

    def whole(line: Any) -> tuple[float, float] | None:  # the column the line stands in
        area = next((area for area in reversed(page.column_areas) if area.top <= line.top), None)
        return (0, area.widths[placed.column or 0]) if area is not None and (placed.column or 0) < len(area.widths) \
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
    margins, size = cell_margins_of(cell, table), cell.find(f"{HP}cellSz")
    inside = None if margins is None or size is None else (  # the room its paragraphs are laid out in, as a row's
        margins.left, int(size.get("width", 0)) - margins.left - margins.right)
    why = None
    for row in placement.rows:
        for part in row.cells if not row.repeated else ():
            lines = tuple(line for line in (part.lines or part.lines_with_tables) if line.paragraph == order)
            if part.source_index != number or not lines:
                continue
            found = _x_on_line(obj, measure, paragraph, lines, lambda line: inside)
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


def _object_line_content(measure: _Measure, paragraph: Any, runs: list[Any], width: int, count: int,
                         native: tuple[list[tuple[int, str]], int]) -> tuple[_LineContent, ...]:
    """Placement tracing only: the text range, start and room of each of the *count* lines of a cell, header,
    footer, text box or note paragraph without layout cache lines of its own that holds objects set as characters
    (a table alone among them), laid out *width* wide as the layout lays it out: on one line, all it holds; on
    several (objects among its text, or several of them: :meth:`~hwpx.layout._page_measure._Measure.marked_lines`),
    broken where :func:`~hwpx.layout._page_measure._line_metrics` breaks it, each object one character of its own
    width. A line's range runs from the Hancom text position of its first character or object to the next line's
    (:meth:`~hwpx.layout._page_measure._Measure.native_positions`), its text the characters in it; it starts where
    the room its line has (its paragraph's margins, indent and label, see ``_line_widths``) starts in *width*.
    ``()`` where an object is placed otherwise, the paragraph holds composed characters or ruby text, or the lines
    do not come out as *count*."""

    try:
        if _marks(runs) or any(_local(child) in _OBJECTS and (
                child.find(f"{HP}pos") is None or child.find(f"{HP}pos").get("treatAsChar") != "1")
                for run in runs for child in run):
            return ()
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        if count == 1:
            style = measure.style(paragraph.get("paraPrIDRef"), _text_size(measure, runs, paragraph)[1], paragraph)
            starts, text = [0], None
        elif _objects_among(runs):
            text, sizes, looks, placed, marked = _inline_content(measure, paragraph, runs)
            style = measure.style(paragraph.get("paraPrIDRef"), [run.get("charPrIDRef") for run in runs] or ["0"],
                                  paragraph)
            starts = []
            end = _end_size(measure, runs, _text_size(measure, runs)[2])
            if len(_line_metrics(measure, text, _line_widths(shape, width, style), sizes, style, shape, placed,
                                 looks if len(set(looks)) > 1 else None, marked, end, starts_out=starts)) != count:
                return ()
        else:
            return ()
        measured = _measured_text(measure, paragraph)
        if style is None or measured is None or text is not None and measured[0] != text:
            return ()
        positions = measured[4]
        widths = _line_widths(shape, width, style)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return ()
    pieces, length = native
    result = []
    for index, (start, stop) in enumerate(zip(starts, [*starts[1:], None])):
        low = 0 if start == 0 else positions[start] if start < len(positions) else length
        high = length if stop is None else positions[stop] if stop < len(positions) else length
        room = widths[min(index, len(widths) - 1)]
        line = "".join(value for position, value in pieces if low <= position < high)
        result.append(_LineContent(low, high, line, "engine", None if room == _NO_WRAP else width - shape.right - room,
                                   None if room == _NO_WRAP else room))
    return tuple(result)


def _pens(text: str, sizes: list[int], looks: list[Any], advances: dict[int, float], style: Any, start: int,
          stop: int, origin: float, room: float, reached: dict[int, tuple[int, str]] | None = None) -> list[float]:
    """Placement tracing only: how far right of its line's start each character of ``text[start:stop]`` begins,
    then how far the last one reaches, added up as :func:`~hwpx.form_fit.measure.hancom_line_starts` adds the
    line up when it breaks it: each character's advance at its own size and style and the automatic spacing after
    it (none after a space), a fixed width as given, a tab to where it reaches from *origin* (the line's start
    from the column's left edge) on a line *room* wide. *reached*, when given, gets the stop each tab reaching
    one reaches, by its place (see :func:`~hwpx.form_fit.measure.tab_reach`)."""

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
            chosen: list[tuple[int, str]] = []
            fixed = tab_reach(origin + used, origin + room, style, lambda point, at=at: after(at, point), chosen)
            if reached is not None and chosen:
                reached[at] = chosen[0]
        advance = char_advance(glyph, size, look) if fixed is None else fixed
        if glyph in _HANGING_SPACES:
            used += advance
            continue
        following = text[at + 1] if at + 1 < len(text) else "\n"
        used += advance + (auto_space_gap(glyph, following, size, style, look) if following != "\n" else 0.0)
    pens.append(used)
    return pens


def _x_on_line(obj: Any, measure: _Measure, paragraph: Any, lines: tuple[Any, ...],
               whole: Callable[[Any], tuple[float, float] | None]) -> tuple[float, Any] | str:
    """Placement tracing only: how far right of the left edge its *lines* are measured from (a body line's column,
    a cell line's cell) an object set as a character among text starts (its left outer margin outside), on the
    line holding its text position, with that line; else why not. *whole* gives where the room a line's
    paragraph is laid out in starts from that edge and how wide it is (its column; its cell's inside, past the
    cell's left margin), ``None`` where it is not known.

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
    text, positions, places = measured[0], measured[4], measured[5]
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
    frame = _line_pens(measure, paragraph, line, measured, start, stop, whole, "object set as a character")
    if isinstance(frame, str):
        return frame
    left, pens, shift, spread = frame
    pen = pens[at - start]
    if spread and pen:
        return _SPREAD.format(subject="object set as a character")
    return left + pen + shift + _object_margin(obj, "left"), line


#: Why something on a line Hancom spreads across its room does not stand where the layout measures it.
_SPREAD = ("{subject} on a line spread across its room (justified but the last, or distributed): where Hancom adds "
           "the room is not laid out")


def _line_pens(measure: _Measure, paragraph: Any, line: Any, measured: tuple[Any, ...], start: int, stop: int,
               whole: Callable[[Any], tuple[float, float] | None], subject: str,
               reached: dict[int, tuple[int, str]] | None = None) -> tuple[float, list[float], float, bool] | str:
    """Placement tracing only: *line* of *paragraph*, holding ``text[start:stop]`` of its *measured* text (see
    :func:`_measured_text`), as the layout lays it across: where its text starts from the edge its *x* is
    measured from, how far right of that each of its characters begins and the last one reaches (:func:`_pens`,
    filling *reached*), how far the paragraph's alignment moves it, and whether Hancom spreads it across its room;
    else why that is not laid out, said of *subject*. *whole* is as for :func:`_x_on_line`.

    The line starts where the layout starts it (a line Hancom saved in a paragraph with an indent or a label: as
    the layout indents its lines when the line has the paragraph's whole room). Set left, or on the last line set
    justified, the alignment does not move it; centred or to the end, by half or all of the room its characters
    leave. A line set centred or right that ends in spaces or in automatic spacing does not say where it stands,
    nor does one whose spaces shrink for its characters to fit, nor a paragraph pressed onto one line."""

    text, sizes, looks, _, _, _, style = measured
    if line.x is None or line.width is None:
        return f"{subject}: its line has no horizontal origin or width"
    first = start == 0
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    left, room = line.x, line.width
    if line.source == "cache" and (shape.indent or style.head):  # the cache keeps the paragraph's whole room
        area = whole(line)  # (Hancom saves a cell's lines in whole layout units, a little narrower than the cell)
        inner = None if area is None else area[1] - shape.left - shape.right
        if area is None or inner is None or left - area[0] != shape.left or not 0 <= inner - room < _LAYOUT_UNIT:
            return (f"{subject} on a saved line of an indented or labelled paragraph not as wide as the paragraph: "
                    "where the line's text starts is not laid out")
        room = _indented(inner, shape, style)[0 if first else 1]
        left = area[0] + area[1] - shape.right - room
    if room >= _NO_WRAP:
        return f"{subject} in a paragraph pressed onto one line: where it stands is not laid out"
    pens = _pens(text, sizes, looks, measured[3], style, start, stop, _line_origin(style, first), room, reached)
    end = stop
    while end > start and text[end - 1] == "\n":
        end -= 1
    content = end
    while content > start and text[content - 1] in _HANGING_SPACES:
        content -= 1
    used = pens[content - start]
    if used > room:
        return f"{subject} on a line whose spaces shrink to fit it: where it stands is not laid out"
    align = measure.align(paragraph.get("paraPrIDRef"))
    spread = align in ("JUSTIFY", "DISTRIBUTE", "DISTRIBUTE_SPACE") and (align != "JUSTIFY" or stop < len(text))
    shift = 0.0
    if align in ("CENTER", "RIGHT"):
        gap = content < len(text) and text[content] != "\n" and auto_space_gap(
            text[content - 1], text[content], sizes[content - 1] / 100, style, looks[content - 1])
        if content < end or gap:
            return (f"{subject} on a line set centred or right that ends in spaces or automatic spacing: whether "
                    "Hancom counts them is not laid out")
        shift = (room - used) / (2 if align == "CENTER" else 1)
    return left, pens, shift, spread


def _group_member(placed: ObjectPlacement, obj: Any, others: dict[Any, ObjectPlacement]) -> ObjectPlacement:
    """*placed*, a member of a group (``hp:container``), with its rectangle in the outermost group's where that
    group has its rectangle: the box python-hwpx reads for an unturned, unflipped member
    (:func:`~hwpx.oxml.container._unturned_box`: its original size through its own scaling, moved by its
    translation, in the outermost group's own space), drawn as the outermost group is scaled
    (:func:`~hwpx.oxml.container._outermost_factors`). Unchanged for any other object; a member that box does not
    say for keeps its page and says so."""

    if obj.getparent() is None or _local(obj.getparent()) != "container":
        return placed
    outer = obj
    for up in obj.iterancestors():
        if _local(up) != "container":
            break
        outer = up
    group = others.get(outer)
    rest = tuple(why for why in placed.unavailable if why not in (_OBJECT_HOLDERS["container"],
                                                                  "object size not measured"))
    if group is None or None in (group.page, group.x, group.top):
        return placed
    factors = _outermost_factors(outer)
    box = _unturned_box(obj, factors) if factors is not None else None
    if box is None:
        kept = tuple(why for why in placed.unavailable if why != _OBJECT_HOLDERS["container"])
        return replace(placed, unavailable=("a member of a group: a group or member turned, flipped or stretched "
                                            "otherwise than by scaling is not placed in the group", *kept))
    assert factors is not None and group.x is not None and group.top is not None
    left, top = round(box[0] * factors[0]), round(box[1] * factors[1])
    return replace(placed, page=group.page, column=group.column, x=group.x + left, top=group.top + top,
                   width=round(box[2] * factors[0]) - left, height=round(box[3] * factors[1]) - top, unavailable=rest)


def _scope_place(frame: int, scope: _FrameTrace, first_page: int) -> tuple[int, int, int]:
    page, column = divmod(frame, scope.columns)
    return first_page + scope.first_page + page, scope.column_start + column, scope.first_top if page == 0 else 0


def _column_origin(page: PagePlacement, column: int, area_top: int) -> int | None:
    if column == 0:
        return page.body[0]
    area = next((area for area in reversed(page.column_areas) if area.top <= area_top), None)
    if area is None or column >= len(area.widths) or len(area.gaps) != len(area.widths) - 1:
        return None
    return page.body[0] + sum(area.widths[:column]) + sum(area.gaps[:column])


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
                            nested_places: dict[Any, list[tuple[int, int]]] | None = None,
                            measure: _Measure | None = None) -> TablePlacement | None:
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
    top, left, why = None, None, "inline table origin not measured"
    if measure is not None:
        top, left, why = _nested_origin(table, cell, placements[parent], numbers or {}, measure, measured, page)
    capture = _TableCapture(measured, parts, 0, (0, sum(row.height for row in measured.rows)),
                            absolute=top is not None, vague=why)
    placed = _table_placement(address, capture, _FrameTrace((), 1, column_start=column), page, top or 0, numbers,
                              nested_places, None if left is None else (left, False))
    return replace(placed, moved=None)  # a table in a cell has no line of its own in the body to move from


def _nested_origin(table: Any, cell: Any, parent: TablePlacement, numbers: dict[Any, int], measure: _Measure,
                   measured: _FlowTable, page: int) -> tuple[int | None, float | None, str]:
    """Where a table set as a character that is all a line of a cell of a placed table (*parent*) holds stands:
    the top of its first row on the paper and its left edge right of its column's, from that line as the parent
    places it (the row's top, the cell's top and left edge in the row, the line's in the cell), the table on its
    line as one alone on a body line stands (:func:`~hwpx.layout.pages._on_its_line`: below its top outer margin
    and a caption above it on a line as tall as it, across the line as the paragraph's alignment sets it); and
    why what is missing is not given."""

    unknown = "inline table origin not measured"
    position = table.find(f"{HP}pos")
    if position is None or position.get("treatAsChar") != "1":
        return None, None, f"{unknown}: a table placed in a cell otherwise than as a character"
    number = numbers.get(table)
    index = next((at for at, other in enumerate(next(cell.iterancestors(f"{HP}tbl")).findall(f"{HP}tr/{HP}tc"))
                  if other is cell), None)
    standing = [(row, part, line) for row in parent.rows if not row.repeated and row.page == page
                for part in row.cells if part.source_index == index
                for line in part.lines_with_tables if number in line.tables]
    if number is None or len(standing) != 1:
        return None, None, f"{unknown}: " + ("no placed cell line is known to hold it" if not standing else
                                             "more than one placed cell line holds it")
    row, part, line = standing[0]
    paragraphs = cell.findall(f"{HP}subList/{HP}p")
    paragraph = paragraphs[line.paragraph] if line.paragraph < len(paragraphs) else None
    if paragraph is None:
        return None, None, f"{unknown}: a table among the text of a cell line"
    if _table_alone(paragraph.findall(f"{HP}run")) is not table:
        return _among_cell_text(table, cell, paragraph, row, part, line, measure, measured)
    try:
        from .pages import _on_its_line  # placement tracing only

        flow = _on_its_line(measure, paragraph, table, replace(measured, caption=_caption(measure, table)),
                            line.x, line.width, line.height)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return None, None, unknown
    top = None if None in (row.top, part.top, line.top, flow.drop) else \
        row.top - row.table_offset + part.top + line.top + flow.drop  # type: ignore[operator]
    left = None if None in (row.x, part.x, flow.left) else row.x + part.x + flow.left  # type: ignore[operator]
    why = "" if top is not None else f"{unknown}: its cell line's top on the page is not measured" \
        if None in (row.top, part.top, line.top) else f"{unknown}: its cell line is taller than it, or its rows' " \
        "heights are not measured"
    return top, left, why


def _among_cell_text(table: Any, cell: Any, paragraph: Any, row: TableRowPlacement, part: TableCellPlacement,
                     line: TableCellLinePlacement, measure: _Measure, measured: _FlowTable
                     ) -> tuple[int | None, float | None, str]:
    """:func:`_nested_origin` of a table set as a character among the text of a cell line: its left edge where an
    object so set stands on that line (see :func:`_x_on_line`, the line measured from the cell's left edge), its
    top below its top outer margin and a caption above it when the line is as tall as it with them."""

    unknown = "inline table origin not measured"
    margins, size = cell_margins_of(cell, next(cell.iterancestors(f"{HP}tbl"))), cell.find(f"{HP}cellSz")
    inside = None if margins is None or size is None else (  # the room its paragraphs are laid out in
        margins.left, int(size.get("width", 0)) - margins.left - margins.right)
    lines = tuple(other for other in part.lines_with_tables if other.paragraph == line.paragraph)
    try:
        found = _x_on_line(table, measure, paragraph, lines, lambda _: inside)
        caption = _caption(measure, table)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return None, None, f"{unknown}: a table among the text of a cell line"
    if isinstance(found, str):
        return None, None, f"{unknown}: " + found.replace("object set as a character",
                                                         "a table set as a character among the text of a cell line")
    x, standing = found
    if standing != line:
        return None, None, f"{unknown}: a table among the text of a cell line not the one its place in the text holds"
    margin = table.find(f"{HP}outMargin")
    tall = sum(row.height for row in measured.rows) + _cell_spacing(table) + _extent_margins(table) + sum(caption)
    drop = (0 if margin is None else _margin(margin, "top")) + caption[0] \
        if measured.doubt is None and tall == line.height else None
    top = None if None in (row.top, part.top, line.top, drop) else \
        row.top - row.table_offset + part.top + line.top + drop  # type: ignore[operator]
    left = None if None in (row.x, part.x) else row.x + part.x + x  # type: ignore[operator]
    why = "" if top is not None else f"{unknown}: its cell line's top on the page is not measured" \
        if None in (row.top, part.top, line.top) else f"{unknown}: a table set as a character among text on a line " \
        "taller than it, or its rows' heights are not measured"
    return top, left, why


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


#: Where a paragraph stands outside the reading order the labels are counted in (body, cells, text boxes, captions).
_UNCOUNTED = frozenset(("header", "footer", "footNote", "endNote"))


class _Labels:
    """Placement tracing only: the bullet or number Hancom draws before a paragraph's first line, on that line
    (:class:`~hwpx.layout.pages.LabelPlacement`), as the layout measures it when it breaks the paragraph's lines.

    Its text is the label counted in reading order (:func:`~hwpx.layout._page_measure._drawn_labels`, the count
    the layout measures a number's room by); a bullet outside that order its character. Its character shape is
    the paragraph head's own, else the paragraph end's, else the text's (as the layout sizes it). Its room is the
    one the layout takes off the line (``TextStyle.head``, :func:`~hwpx.form_fit.measure.label_room`): the box
    less the gap to the text (``textOffset``). The box starts where the paragraph's first line starts, past its
    left margin and a first-line indent (not a hanging one, nor with automatic hanging): a line the layout broke
    starts its text past the room (its *x* less the room), a line Hancom saved starts at the paragraph's left
    margin across its whole room (its *x* plus the indent)."""

    def __init__(self, measure: _Measure) -> None:
        self.measure = measure
        self.kinds: dict[str, tuple[str, str]] = {}
        for shape in measure._header.iter(f"{HH}paraPr"):
            heading = paragraph_heading(shape)
            kind = heading.get("type", "NONE") if heading is not None else "NONE"
            if kind in ("BULLET", "NUMBER", "OUTLINE"):
                self.kinds[shape.get("id") or ""] = (kind, heading.get("idRef") or "")  # type: ignore[union-attr]
        self.pictures = {bullet.get("id") for bullet in measure._header.iter(f"{HH}bullet")
                         if bullet.get("useImage") in ("1", "true")}
        self.outside: Any = None  # the labels of bullets outside the reading order, read when one is asked for

    def first_line(self, paragraph: Any, line: Any) -> Any:
        """*line* (a :class:`~hwpx.layout.pages.LinePlacement` or ``TableCellLinePlacement``), the first line of
        *paragraph*, with its label; unchanged for a paragraph without one."""

        if (paragraph.get("paraPrIDRef") or "") not in self.kinds:
            return line
        try:
            label = self._label(paragraph, line.x, line.source)
        except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
            label = LabelPlacement(None, None, None, None, unavailable=("label not measured",))
        return replace(line, label=label)

    def _label(self, paragraph: Any, x: float | None, source: str | None) -> LabelPlacement:
        measure, root = self.measure, self.measure._root
        para_pr = paragraph.get("paraPrIDRef")
        kind, ref = self.kinds[para_pr or ""]
        heading = paragraph_label(root, para_pr)
        head = heading[1] if heading is not None else {}
        missing = []
        text: str | None = None
        if kind == "BULLET" and ref in self.pictures:
            missing.append("a picture bullet: Hancom draws its picture")
        else:
            measure.headed(paragraph)  # reads every label in reading order once
            text = (measure._drawn or {}).get(paragraph) or None
            outside = any(_local(up) in _UNCOUNTED for up in paragraph.iterancestors())
            if text is None and kind == "BULLET" and outside:
                if self.outside is None:
                    from ..tools.exporter import _ListLabels

                    self.outside = _ListLabels(measure._header)
                text = self.outside.label(paragraph) or None
            if text is None:
                missing.append("a number in a header, footer or note: the count in reading order does not reach it"
                               if outside and kind != "BULLET" else
                               "a label in a number format, or at a level, the count does not write")

        def known(found: Any) -> bool:
            return found is not None and found != "4294967295" and root.char_property(found) is not None

        runs = paragraph.findall(f"{HP}run")
        refs = _text_size(measure, runs, paragraph)[1]
        own = next((found for found in (head.get("charPrIDRef"), _end_ref(paragraph), *refs) if known(found)), None)
        style = measure.style(para_pr, refs, paragraph)
        left = width = None
        if heading is None or style is None or not style.head:
            missing.append("its room is not measured: a picture bullet sized by its picture, or a numbering not "
                           "defined")
        else:
            em = measure.char_height(own) if own is not None else 1000
            offset = _style_number(head.get("textOffset"), 50.0)
            width = style.head - (offset if head.get("textOffsetType") == "HWPUNIT" else em * offset / 100)
            if x is None:
                missing.append("its line has no horizontal origin")
            else:
                left = x + (_line_origin(style, True) - style.margin_left - style.head if source == "cache"
                            else -style.head)
        return LabelPlacement(text, None if own is None else str(own), left, width, head.get("align", "LEFT"),
                              tuple(missing))


#: A note holding a paragraph with a bullet or number: its lines are not matched to their paragraphs.
_NOTE_LABEL = "a bullet or number in a note: its label is not placed"
#: A tab on a line of a note, whose lines are not matched to their paragraphs.
_NOTE_TAB = "a tab in a note: its line is not matched to its paragraph, so where the tab reaches is not laid out"


#: Where a line's room starts from the edge its x is measured from, and how wide it is (see :func:`_x_on_line`).
_Whole = Callable[[Any], tuple[float, float] | None]


class _Tabs:
    """Placement tracing only: where each tab of a line reaches (:class:`~hwpx.layout.pages.TabPlacement`), as the
    layout measures the line when it breaks it: past the characters before it on its line (:func:`_line_pens`, the
    tab reaching the stop :func:`~hwpx.form_fit.measure.tab_reach` finds for it), moved as the paragraph's alignment
    moves the line. A line Hancom spreads across its room (justified but its paragraph's last, or distributed)
    does not say where its tabs reach, nor does any line :func:`_line_pens` does not lay across."""

    def __init__(self, measure: _Measure) -> None:
        self.measure = measure
        self.texts: dict[tuple[Any, int], Any] = {}  # (paragraph, default tab stops) -> its measured text
        self.leaders: dict[str, dict[tuple[int, str], str]] = {}  # paragraph shape -> its stops' fills

    def line(self, paragraph: Any, line: Any, whole: _Whole, tab_stop: int) -> Any:
        """*line* (a :class:`~hwpx.layout.pages.LinePlacement` or ``TableCellLinePlacement``) of *paragraph*, laid
        out with default tab stops *tab_stop* apart, with its tabs; unchanged for a line without one in its text."""

        if not line.text or "\t" not in line.text:
            return line
        kept, self.measure.tab_stop = self.measure.tab_stop, tab_stop
        try:
            found = self._places(paragraph, line, whole)
        except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
            found = "tab not measured"
        finally:
            self.measure.tab_stop = kept
        if isinstance(found, str):
            found = (TabPlacement(None, unavailable=(found,)),) * line.text.count("\t")
        return replace(line, tabs=found)

    def lines(self, lines: tuple[Any, ...], paragraphs: list[Any], whole: _Whole, tab_stop: int) -> tuple[Any, ...]:
        """*lines* (a cell's or a text box's: ``TableCellLinePlacement``), each with its tabs."""

        return tuple(self.line(paragraphs[line.paragraph], line, whole, tab_stop)
                     if line.paragraph < len(paragraphs) else line for line in lines)

    def _places(self, paragraph: Any, line: Any, whole: _Whole) -> tuple[TabPlacement, ...] | str:
        key = paragraph, self.measure.tab_stop
        if key not in self.texts:
            self.texts[key] = _measured_text(self.measure, paragraph)
        measured = self.texts[key]
        if measured is None:
            return "tab: its paragraph's text is not measured with Hancom's text positions"
        text, positions = measured[0], measured[4]
        if line.text_start is None or line.text_end is None:
            return "tab: its line keeps no text range"
        start, stop = bisect_left(positions, line.text_start), bisect_left(positions, line.text_end)
        if text[start:stop].count("\t") != line.text.count("\t"):
            return "tab: the tabs of its line are not found in its paragraph's text as the layout measures it"
        reached: dict[int, tuple[int, str]] = {}
        frame = _line_pens(self.measure, paragraph, line, measured, start, stop, whole, "tab", reached)
        if isinstance(frame, str):
            return frame
        left, pens, shift, spread = frame
        if spread:
            return _SPREAD.format(subject="tab")
        leaders = self._leaders(paragraph.get("paraPrIDRef") or "")
        places = []
        for at in range(start, stop):
            if text[at] != "\t":
                continue
            stop_at = reached.get(at)
            kind = "NONE" if stop_at is None else stop_at[1]
            leader = "NONE" if stop_at is None else leaders.get(stop_at, "NONE")
            places.append(TabPlacement(left + pens[at + 1 - start] + shift, left + pens[at - start] + shift, kind,
                                       leader))
        return tuple(places)

    def _leaders(self, para_pr: str) -> dict[tuple[int, str], str]:
        """The fill of each of the paragraph shape's own tab stops, by ``(position, kind)`` as the layout reads
        them (the first item where two say the same)."""

        if para_pr not in self.leaders:
            found: dict[tuple[int, str], str] = {}
            root = self.measure._root
            shape = root.paragraph_property(para_pr)
            tabs = root.tab_property(getattr(shape, "tab_pr_id_ref", None)) if shape is not None else None
            for item in getattr(tabs, "tab_stops", None) or ():
                found.setdefault((int(item.pos), str(item.type or "LEFT").upper()), str(item.leader or "NONE"))
            self.leaders[para_pr] = found
        return self.leaders[para_pr]


def _fixed_room(room: tuple[float, float] | None) -> _Whole:
    """The room of every line of a cell, a text box, a header or a footer: *room*, whatever the line."""

    return lambda _: room


def _body_room(pages: list[PagePlacement]) -> _Whole:
    """Where the room of a body line starts from its column's left edge, and how wide it is: its column's."""

    def whole(line: Any) -> tuple[float, float] | None:
        if not 0 <= line.position.page < len(pages):
            return None
        column = line.position.column
        area = next((area for area in reversed(pages[line.position.page].column_areas) if area.top <= line.top),
                    None)
        return (0, area.widths[column]) if area is not None and column < len(area.widths) else None

    return whole


def _box_room(obj: Any, size: tuple[int, int] | None) -> tuple[float, float] | None:
    """Where the room of the text a rectangle holds starts from the box's left edge, and how wide it is, as
    :func:`_box_lines` lays its lines: inside its text margins, across the width it lays them at."""

    box = obj.find(f"{HP}drawText")
    margin = box.find(f"{HP}textMargin") if box is not None else None
    left, right = (0, 0) if margin is None else (int(margin.get("left", 0)), int(margin.get("right", 0)))
    if box is None or obj.find(f"{HP}sz") is None and size is None:
        return None
    width = size[0] if obj.find(f"{HP}sz") is None and size is not None \
        else int(box.get("lastWidth", 0)) or int(obj.find(f"{HP}sz").get("width", 0))
    return left, width - left - right


def _tabbed_cells(placed: TablePlacement, table: Any, tabs: _Tabs, tab_stop: int) -> TablePlacement:
    """*placed*, each line it shows with its tabs, a cell's lines measured from the cell's left edge (its room
    past its left margin, as the layout lays its paragraphs)."""

    cells = table.findall(f"{HP}tr/{HP}tc")
    rows = []
    for row in placed.rows:
        parts = []
        for part in row.cells:
            source = cells[part.source_index] if part.source_index is not None \
                and part.source_index < len(cells) else None
            if source is not None and any(line.text and "\t" in line.text
                                          for line in (*part.lines, *part.lines_with_tables)):
                held = source.findall(f"{HP}subList/{HP}p")
                margins, size = cell_margins_of(source, table), source.find(f"{HP}cellSz")
                inside = None if margins is None or size is None else (
                    margins.left, int(size.get("width", 0)) - margins.left - margins.right)
                room = _fixed_room(inside)
                part = replace(part, lines=tabs.lines(part.lines, held, room, tab_stop),
                               lines_with_tables=tabs.lines(part.lines_with_tables, held, room, tab_stop))
            parts.append(part)
        rows.append(replace(row, cells=tuple(parts)))
    return replace(placed, rows=tuple(rows))


def _note_tabs(placed: AreaPlacement) -> AreaPlacement:
    """*placed*, a note, each tab of its lines without a place: they are not matched to their paragraphs."""

    if not any(line.text and "\t" in line.text for line in placed.lines):
        return placed
    return replace(placed, lines=tuple(
        replace(line, tabs=(TabPlacement(None, unavailable=(_NOTE_TAB,)),) * line.text.count("\t"))
        if line.text and "\t" in line.text else line for line in placed.lines))


def _labelled_lines(lines: tuple[TableCellLinePlacement, ...], paragraphs: list[Any],
                    labels: _Labels) -> tuple[TableCellLinePlacement, ...]:
    """*lines* (a cell's or a text box's), the first line of each of its *paragraphs* with its label."""

    return tuple(labels.first_line(paragraphs[line.paragraph], line) if not line.line
                 and line.paragraph < len(paragraphs) else line for line in lines)


def _labelled_cells(placed: TablePlacement, table: Any, labels: _Labels) -> TablePlacement:
    """*placed*, the first line of each cell paragraph it shows with its label."""

    cells = table.findall(f"{HP}tr/{HP}tc")
    rows = []
    for row in placed.rows:
        parts = []
        for part in row.cells:
            source = cells[part.source_index] if part.source_index is not None \
                and part.source_index < len(cells) else None
            if source is not None:
                held = source.findall(f"{HP}subList/{HP}p")
                part = replace(part, lines=_labelled_lines(part.lines, held, labels),
                               lines_with_tables=_labelled_lines(part.lines_with_tables, held, labels))
            parts.append(part)
        rows.append(replace(row, cells=tuple(parts)))
    return replace(placed, rows=tuple(rows))


_NO_LEFT = "table left edge not measured"
_NO_ORIGIN = "inline table origin not measured"


def _table_on_text_line(placed: TablePlacement, table: Any, measure: _Measure, paragraphs: list[Any], index: int,
                        lines: tuple[LinePlacement, ...], pages: list[PagePlacement]) -> TablePlacement:
    """*placed*, a table set as a character in body paragraph *index* of *paragraphs* (its section's) whose rows
    have no left edge: among the paragraph's text, with its left edge where an object so set stands on the line
    holding its text position (see :func:`_x_on_line`), and its rows' tops below its top outer margin and a
    caption above it on that line when the line is as tall as it with them (as :func:`~hwpx.layout.pages.
    _among_its_line` stands an object); alone on its line, why its line does not place it across."""

    rows = placed.rows
    paragraph = paragraphs[index]
    margin = table.find(f"{HP}outMargin")
    page, column = pages[rows[0].page], rows[0].column
    area = next((area for area in reversed(page.column_areas) if rows[0].top is None or area.top <= rows[0].top),
                None)
    if _table_alone(paragraph.findall(f"{HP}run")) is table:
        para_pr = paragraph.get("paraPrIDRef")
        shape = measure.shape(para_pr)
        style = measure.style(para_pr, _text_size(measure, paragraph.findall(f"{HP}run"), paragraph)[1], paragraph)
        room = None if area is None or column >= len(area.widths) else \
            _indented(area.widths[column] - shape.left - shape.right, shape, style)[0]  # as the layout's line
        if measure.align(para_pr) in ("CENTER", "RIGHT") and room is not None and _extent(table, "width") > room:
            why = (f"{_NO_LEFT}: a table set as a character alone on a line narrower than it with its outer margins, "
                   "in a paragraph set centred or right: where Hancom sets it across the line is not laid out")
            return replace(placed, unavailable=tuple(why if found == _NO_LEFT else found
                                                     for found in placed.unavailable))
        return placed
    measure.tab_stop = _part_tab_stop(paragraphs, index)

    def whole(line: Any) -> tuple[float, float] | None:  # the column the line stands in
        area = next((area for area in reversed(page.column_areas) if area.top <= line.top), None)
        return (0, area.widths[column]) if area is not None and column < len(area.widths) else None

    try:
        found = _x_on_line(table, measure, paragraph, lines, whole)
    except Exception:  # noqa: BLE001 - tracing must not change whether the estimate answers
        return placed
    if isinstance(found, str):
        why = f"{_NO_LEFT}: " + found.replace("object set as a character", "a table set as a character among text")
        return replace(placed, unavailable=tuple(why if kept == _NO_LEFT else kept for kept in placed.unavailable))
    x, line = found
    if any((row.page, row.column) != (line.position.page, line.position.column) for row in rows):
        return placed
    kept = [why for why in placed.unavailable if why != _NO_LEFT]
    rows = tuple(replace(row, x=x) for row in rows)
    if any(row.top is None for row in rows) and _NO_ORIGIN in kept and all(row.height is not None for row in rows):
        caption = _caption(measure, table)
        tall = sum(row.height or 0 for row in rows if not row.repeated) + _cell_spacing(table) + sum(caption) \
            + _extent_margins(table)
        if tall == line.height:
            top = line.top + (0 if margin is None else _margin(margin, "top")) + caption[0]
            rows = tuple(replace(row, top=top + row.table_offset) for row in rows)
            kept.remove(_NO_ORIGIN)
        else:
            kept[kept.index(_NO_ORIGIN)] = (f"{_NO_ORIGIN}: a table set as a character among text on a line taller "
                                            "than it: where it stands up and down the line is not laid out")
    return replace(placed, rows=rows, unavailable=tuple(kept))
