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
from dataclasses import replace
from typing import Any

from ..oxml.namespaces import HP
from ..oxml.table_sizes import _grid_extents_of
from ._page_measure import (
    _DRAWINGS, _CellLine, _CellSlice, _FlowTable, _LineContent, _Row, _RowPart, _cell_spacing, _floating, _local,
    _page_break, _whole_rows,
)
from .pages import (
    AreaPlacement, EstimatedLine, LayoutEstimate, LinePlacement, ObjectPlacement, PageEstimate, PagePlacement,
    ParagraphPlacement, TableCaptionPlacement, TableCellLinePlacement, TableCellPlacement, TablePlacement,
    TableRowPlacement, _AreaFrame, _FrameTrace, _LineDetail, _ObjectFrame, _Page, _RunPositions, _SectionLayout,
    _TableCapture, _column_area, _run_positions,
)


def _placement_result(
    estimate: PageEstimate, sections: list[tuple[int, int, _SectionLayout]], sources: list[Any],
    inline_tables: dict[Any, _FlowTable], sizes: dict[Any, tuple[int | None, int]],
    untraced: dict[Any, str] | None = None,
) -> LayoutEstimate:
    pages: list[PagePlacement] = []
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
    nested_places: dict[Any, list[tuple[int, int]]] = {}
    for section, source in enumerate(body_sources):
        for index, paragraph in enumerate(source):
            numbers = {table: number for number, table in enumerate(paragraph.iter(f"{HP}tbl"))}
            for table, table_index in numbers.items():
                address = section, index, table_index
                if table in table_captures:
                    result = _table_placement(address, *table_captures[table], numbers, nested_places)
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
            objects.extend(_object_placement(section, index, ordinal, obj, sizes.get(obj), object_captures.get(obj), pages)
                           for ordinal, obj in enumerate(node for node in paragraph.iter()
                                                        if _local(node) in _DRAWINGS))
            for ordinal, area in enumerate(node for node in paragraph.iter() if _local(node) in _AREA_NAMES):
                found = area_captures.get(area)
                if found:
                    areas.extend(_area_placement(section, index, ordinal, *capture, pages) for capture in found)
                else:
                    areas.append(AreaPlacement(section, index, ordinal, _local(area),
                                               unavailable=("area placement not retained by the layout path",)))
    return LayoutEstimate(estimate, tuple(pages), tuple(paragraphs), tuple(tables), tuple(objects), tuple(areas))


_AREA_NAMES = frozenset(("header", "footer", "footNote", "endNote"))


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
    if x is None or top is None:
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
                     nested_places: dict[Any, list[tuple[int, int]]] | None = None) -> TablePlacement:
    """The placement of a table from the row parts the layout accepted. *numbers* gives the tables of its body
    paragraph their index there; *nested_places* collects, for each table standing on a line of one of its cells,
    the page and column of the row part showing that line."""

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
    for part in parts:
        first_in_frame.setdefault(part.frame, part.top)
        page, column, top = frame_place(part.frame, part.top)
        cells = _table_cells(part, outline, cells_by_row, cell_sources, grid, table, first_in_frame[part.frame],
                             place=(page, column), numbers=numbers, nested_places=nested_places)
        if table.doubt is not None:  # the rows are the row model's, which the layout did not take: no heights
            rows.append(TableRowPlacement(part.row, page, column, None, None, part.start, part.stop, part.repeated,
                                          cells))
            continue
        rows.append(TableRowPlacement(part.row, page, column, top, part.height,
                                      part.start, part.stop, part.repeated, cells, part.top - first_in_frame[part.frame]))
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
        if not measured_lines:
            unavailable.append("cell text line placements not retained by the layout path")
        elif any(line.top is None or line.content is None or line.content.text is None
                 for _, _, line in measured_lines):
            unavailable.append("cell text line coordinates or ranges unavailable")
        if x is None:
            unavailable.append("no measured cell grid origin")
        if height is None and slice_ is not None:
            unavailable.append("cell fragment rectangle not fully measured")
        styles = [_run_positions(paragraph) for paragraph in element.findall(f"{HP}subList/{HP}p")]
        top: int | None = part.top - frame_top + spacing
        if table.doubt is not None:  # where the rows stand in the table is the row model's too
            top, height, starts_cell = None, None, False
            unavailable.append(table.doubt)
        lines = tuple(_table_cell_line(p, i, line, starts_cell, styles[p], numbers)
                      for p, i, line in measured_lines if p < len(styles))
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


def _table_cell_line(paragraph: int, index: int, line: _CellLine, starts_cell: bool,
                     styles: _RunPositions | None, numbers: dict[Any, int] | None = None) -> TableCellLinePlacement:
    content = line.content
    return TableCellLinePlacement(
        paragraph, index, line.height, line.top if starts_cell else None,
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
