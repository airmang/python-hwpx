# SPDX-License-Identifier: Apache-2.0
"""Moving and copying a table's rows (``table.move_rows``, ``table.copy_rows``).

A row of HWPX is an ``hp:tr``; each of its cells says where it stands (``hp:cellAddr`` ``colAddr``/``rowAddr``)
and how far it reaches (``hp:cellSpan``). A block of rows moves or copies whole: every ``hp:tr`` of the block
goes, and every cell's ``rowAddr`` and the table's ``rowCnt`` are numbered again after. A merged cell reaching
across the block's top or bottom edge, or across the place the block goes to, would be torn: refused before
anything changes (``table-rows-merge-crossed``)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, cast

from ..errors import HwpxValueError
from ._document_primitives import _HP, _clear_paragraph_layout_cache


def _rows(table: Any) -> list[Any]:
    return [child for child in table if child.tag == f"{_HP}tr"]


def _cells(row: Any) -> list[Any]:
    return [child for child in row if child.tag == f"{_HP}tc"]


def _int(node: Any, name: str, default: int) -> int:
    try:
        return int(node.get(name, default)) if node is not None else default
    except ValueError:
        return default


def _reach(table: Any) -> list[tuple[int, int]]:
    """Each cell's ``(first row, last row + 1)``, by the row it is written in and its ``rowSpan``."""

    reach = []
    for index, row in enumerate(_rows(table)):
        for cell in _cells(row):
            span = max(1, _int(cell.find(f"{_HP}cellSpan"), "rowSpan", 1))
            reach.append((index, index + span))
    return reach


def _block(table: Any, rows: "int | Iterable[int]") -> tuple[int, int]:
    """*rows* as ``(first, last + 1)`` of the table's rows: whole numbers in range, one run of rows."""

    count = len(_rows(table))
    try:
        given: Any = rows
        single = isinstance(given, int) and not isinstance(given, bool)
        wanted = sorted({given} if single else set(cast("Iterable[int]", given)))
    except TypeError:
        wanted = []
    if not wanted or any(isinstance(row, bool) or not isinstance(row, int) or not 0 <= row < count for row in wanted) \
            or wanted != list(range(wanted[0], wanted[-1] + 1)):
        raise HwpxValueError(
            f"rows must be row numbers 0..{count - 1} next to each other; got {rows!r}",
            code="table-rows-invalid",
            context={"rows": repr(rows), "rowCount": count},
            suggestion="Pass one row number or a run of them, e.g. range(2, 4).",
        )
    return wanted[0], wanted[-1] + 1


def _check_to(table: Any, to: object) -> int:
    count = len(_rows(table))
    if isinstance(to, bool) or not isinstance(to, int) or not 0 <= to <= count:
        raise HwpxValueError(
            f"to must be a row number 0..{count} (the row the rows go in front of; {count}: the end); got {to!r}",
            code="table-rows-invalid",
            context={"to": repr(to), "rowCount": count},
            suggestion="Pass the number of the row to put them in front of, or the row count for the end.",
        )
    return to


def _crosses(reach: list[tuple[int, int]], line: int) -> bool:
    """Whether a merged cell reaches across the line between row ``line - 1`` and row ``line``."""

    return any(first < line < last for first, last in reach)


def _merge_crossed(where: str, line: int) -> HwpxValueError:
    return HwpxValueError(
        f"a merged cell reaches across the {where} (between rows {line - 1} and {line})",
        code="table-rows-merge-crossed",
        context={"where": where, "line": line},
        suggestion="Take the merged cell's rows along, split the cell first, or pick another place.",
    )


def _check_block(table: Any, block: tuple[int, int], to: int | None) -> None:
    reach = _reach(table)
    first, last = block
    for line, where in ((first, "rows' top"), (last, "rows' bottom")):
        if _crosses(reach, line):
            raise _merge_crossed(where, line)
    if to is not None and _crosses(reach, to):
        raise _merge_crossed("place they go", to)


def _column_grid(table: Any, block: tuple[int, int]) -> list[list[tuple[int, int]]]:
    return [[(_int(cell.find(f"{_HP}cellAddr"), "colAddr", 0), _int(cell.find(f"{_HP}cellSpan"), "colSpan", 1))
             for cell in _cells(row)] for row in _rows(table)[block[0]:block[1]]]


def _renumber(table: Any) -> None:
    rows = _rows(table)
    for index, row in enumerate(rows):
        for cell in _cells(row):
            address = cell.find(f"{_HP}cellAddr")
            if address is not None:
                address.set("rowAddr", str(index))
    table.set("rowCnt", str(len(rows)))


def _place(table: Any, moving: list[Any], to: int) -> None:
    rows = _rows(table)
    if to < len(rows):
        anchor = rows[to]
        index = list(table).index(anchor)
    else:
        index = list(table).index(rows[-1]) + 1 if rows else len(table)
    for offset, row in enumerate(moving):
        table.insert(index + offset, row)


def _changed(table_object: Any, before: int | None) -> None:
    _renumber(table_object.element)
    table_object._grid_cache = None
    table_object._grow_height(before)
    _clear_paragraph_layout_cache(table_object.paragraph.element)
    section = table_object.paragraph.section
    section.mark_dirty()
    section._remove_outlived_layout_caches()


def _placed(table_object: Any, moved: list[Any]) -> tuple[Any, ...]:
    """The row objects of the table's rows *moved* (``hp:tr`` elements), in their order."""

    from .table import HwpxOxmlTableRow

    return tuple(HwpxOxmlTableRow(row, table_object) for row in moved)


def _require_table_in_document(table_object: Any, role: str) -> None:
    from ._paragraph_text_edit import in_document

    if not in_document(table_object.element, table_object.paragraph.section):
        raise HwpxValueError(
            f"the {role} is not in the document any more (removed, or in something taken out)",
            code="table-not-in-document",
            context={"role": role},
            suggestion="Take the table again from the document (doc.tables ...).",
        )


def _moved_zones(table: Any, block: tuple[int, int], to: int) -> list[tuple[Any, int, int]]:
    """Where each cell zone (``hp:cellzone``) of *table* goes when its rows ``block`` move before row *to*: a
    zone follows its rows, as one does when rows are deleted. Rows reordered inside one zone keep it whole (its
    rows stay one run); a zone whose rows would no longer be one run would come apart: that is refused."""

    count = len(_rows(table))
    order = [index for index in range(count) if not block[0] <= index < block[1]]
    at = to if to < block[0] else to - (block[1] - block[0])
    order[at:at] = list(range(block[0], block[1]))
    new = {old: position for position, old in enumerate(order)}
    moves: list[tuple[Any, int, int]] = []
    for zone in table.findall(f"{_HP}cellzoneList/{_HP}cellzone"):
        start, end = int(zone.get("startRowAddr") or 0), int(zone.get("endRowAddr") or 0)
        rows = sorted(new.get(index, index) for index in range(start, end + 1))
        if rows != list(range(rows[0], rows[-1] + 1)):
            raise HwpxValueError(
                f"the cell zone over rows {start}..{end} holds rows that move and rows that stay",
                code="table-rows-split-cell-zone",
                context={"startRow": start, "endRow": end, "rows": list(range(block[0], block[1]))},
                suggestion="Move every row of the zone, or none of them.",
            )
        moves.append((zone, rows[0], rows[-1]))
    return moves


def _make_room_in_zones(table: Any, to: int, count: int) -> None:
    """The cell zones of *table* after *count* rows go in front of row *to*, as ``insert_rows`` does: a zone
    from row *to* on moves down, one running on across the place grows over the new rows."""

    for zone in table.findall(f"{_HP}cellzoneList/{_HP}cellzone"):
        start, end = int(zone.get("startRowAddr") or 0), int(zone.get("endRowAddr") or 0)
        if end < to:
            continue
        if start >= to:
            zone.set("startRowAddr", str(start + count))
        zone.set("endRowAddr", str(end + count))


def move_rows(table_object: Any, rows: "int | Iterable[int]", to: object, source: Any = None) -> tuple[Any, ...]:
    """``table.move_rows``."""

    _require_table_in_document(table_object, "table")

    if source is not None and source.element is not table_object.element:
        raise HwpxValueError(
            "rows move within their table: no Hancom-saved document shows rows moved into another table",
            code="table-rows-move-other-table",
            suggestion="Copy them there (table.copy_rows(rows, to=, source=)) and delete them here (delete_rows).",
        )
    table = table_object.element
    block = _block(table, rows)
    to = _check_to(table, to)
    _check_block(table, block, to)
    moving = _rows(table)[block[0]:block[1]]
    if block[0] <= to <= block[1]:
        return _placed(table_object, moving)  # in place
    zones = _moved_zones(table, block, to)  # checked before anything moves
    after = _rows(table)[to] if to < len(_rows(table)) else None
    for row in moving:
        table.remove(row)
    remaining = _rows(table)
    _place(table, moving, remaining.index(after) if after is not None else len(remaining))
    for zone, start, end in zones:
        zone.set("startRowAddr", str(start))
        zone.set("endRowAddr", str(end))
    _changed(table_object, None)
    return _placed(table_object, moving)


def copy_rows(table_object: Any, rows: "int | Iterable[int]", to: object, source: Any = None) -> tuple[Any, ...]:
    """``table.copy_rows``."""

    from ._document_primitives import _refresh_copied_paragraph_subtree_ids
    from ._paragraph_text_edit import renumber_copied_fields
    from .shape_position import unique_object_ids

    source = table_object if source is None else source
    _require_table_in_document(table_object, "table the rows go to")
    _require_table_in_document(source, "table the rows come from")
    target = table_object.element
    if source.paragraph.section.document is not table_object.paragraph.section.document:
        raise HwpxValueError(
            "rows are copied from a table of the same document",
            code="table-rows-other-document",
            suggestion="Copy the table into the document first (paragraph.copy_to or copy_range), then its rows.",
        )
    block = _block(source.element, rows)
    to = _check_to(target, to)
    _check_block(source.element, block, None)
    if _crosses(_reach(target), to):
        raise _merge_crossed("place they go", to)
    if source.element is not target:
        mine = sorted({column for row in _column_grid(target, (0, len(_rows(target)))) for column in row})
        theirs = sorted({column for row in _column_grid(source.element, block) for column in row})
        if target.get("colCnt") != source.element.get("colCnt") or not set(theirs) <= set(mine):
            raise HwpxValueError(
                "the source rows' columns differ from this table's",
                code="table-columns-differ",
                context={"colCnt": target.get("colCnt"), "sourceColCnt": source.element.get("colCnt")},
                suggestion="Copy rows between tables of the same columns (count, and each cell's column and span).",
            )
    from .memo import renew_copied_memos

    section = table_object.paragraph.section
    ids = section._ids
    sections = list(section.document.sections) if section.document is not None else [section]
    copies = [deepcopy(row) for row in _rows(source.element)[block[0]:block[1]]]
    for row in copies:
        _refresh_copied_paragraph_subtree_ids(row, ids=ids)
        renumber_copied_fields(row, ids=ids)
        renew_copied_memos(row, sections, section)
        for node in row.iter(f"{_HP}p"):
            _clear_paragraph_layout_cache(node)
    before = table_object._rows_height()
    _place(target, copies, to)
    _make_room_in_zones(target, to, len(copies))
    unique_object_ids(table_object.paragraph.section, copies)
    _changed(table_object, before)
    return _placed(table_object, copies)


__all__ = ["copy_rows", "move_rows"]
