# SPDX-License-Identifier: Apache-2.0
"""Reusable helpers for HWPX table discovery and form-like navigation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from ..oxml import HwpxOxmlParagraph, HwpxOxmlTable
from ..oxml._document_primitives import _text_element_content

if TYPE_CHECKING:
    from ..document import HwpxDocument
    from ..form_fit.policy import FitPolicy

__all__ = [
    "PathDirection",
    "SearchDirection",
    "TableCellReference",
    "TableFillApplied",
    "TableFillFailed",
    "TableFillResult",
    "TableFormSlot",
    "TableFormSlotsResult",
    "TableLabelCandidate",
    "TableLabelMatch",
    "TableLabelSearchResult",
    "TableMapEntry",
    "TableMapResult",
    "fill_by_path",
    "find_cell_by_label",
    "form_slots",
    "get_table_map",
]

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
_WHITESPACE_RE = re.compile(r"\s+")
_HWPUNIT_PER_MM = 7200 / 25.4
#: ``label[2]``: the second cell, in document order, that the label matches.
_OCCURRENCE_RE = re.compile(r"^(?P<label>.*\S)\s*\[(?P<number>[1-9][0-9]*)\]$", re.DOTALL)

SearchDirection = Literal["right", "down"]
PathDirection = Literal["left", "right", "up", "down"]


class TableMapEntry(TypedDict):
    """Compact metadata describing a table in document order."""

    table_index: int
    paragraph_index: int
    location: dict[str, object]
    rows: int
    cols: int
    caption_text: str
    preceding_paragraph_text: str
    header_text: str
    first_row_preview: list[str]
    cells: list[dict[str, object]]
    is_empty: bool


class TableMapResult(TypedDict):
    """Collection of table metadata entries."""

    tables: list[TableMapEntry]


class TableCellReference(TypedDict):
    """A logical table cell position and its current text."""

    row: int
    col: int
    text: str


class TableLabelMatch(TypedDict):
    """A label cell and the cell reached from it."""

    table_index: int
    label_cell: TableCellReference
    target_cell: TableCellReference


class TableLabelSearchResult(TypedDict):
    """Result payload returned by :func:`find_cell_by_label`."""

    matches: list[TableLabelMatch]
    count: int


class _TableFillAppliedRequired(TypedDict):
    path: str
    table_index: int
    row: int
    col: int
    value: str


class TableFillApplied(_TableFillAppliedRequired, total=False):
    """A successfully applied path-based fill operation.

    ``fit`` is present when the fill was given a fit policy: the measured
    outcome for this cell (``FitResult.to_dict()``: lines, font size, style
    changes, warnings).
    """

    fit: dict[str, Any]


class TableLabelCandidate(TypedDict):
    """One of several cells a label matched, with the label spelling that picks it."""

    table_index: int
    row: int
    col: int
    text: str
    selector: str


class _TableFillFailedRequired(TypedDict):
    path: str
    reason: str


class TableFillFailed(_TableFillFailedRequired, total=False):
    """A failed path-based fill operation and its reason.

    ``candidates`` is present when the reason is ``"ambiguous label"``: every
    cell the label matched, each with the ``selector`` (``"성명[2]"``) to write
    in the path instead of the bare label. ``fit`` is present when the reason
    is ``"value does not fit"``: the measured outcome that refused the value.
    """

    candidates: list[TableLabelCandidate]
    fit: dict[str, Any]


class TableFormSlot(TypedDict):
    """An empty cell next to a cell with text, and the path that fills it."""

    label: str
    path: str | None
    direction: SearchDirection
    table_index: int
    label_cell: TableCellReference
    target_cell: TableCellReference
    width_mm: float | None


class TableFormSlotsResult(TypedDict):
    """Result payload returned by :func:`form_slots`."""

    slots: list[TableFormSlot]
    count: int


class TableFillResult(TypedDict):
    """Batch fill summary for :func:`fill_by_path`."""

    applied: list[TableFillApplied]
    failed: list[TableFillFailed]
    applied_count: int
    failed_count: int


@dataclass(frozen=True, slots=True)
class _AnchoredTable:
    table: HwpxOxmlTable
    paragraph_index: int
    caption_text: str
    preceding_paragraph_text: str
    header_text: str


@dataclass(frozen=True, slots=True)
class _IndexedTable:
    table_index: int
    table: HwpxOxmlTable
    paragraph_index: int
    caption_text: str
    preceding_paragraph_text: str
    header_text: str


@dataclass(frozen=True, slots=True)
class _LabelCandidate:
    table_index: int
    table: HwpxOxmlTable
    row: int
    col: int
    text: str


def _collapse_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _normalize_label_text(value: str) -> str:
    """The form two labels are compared in: no whitespace, no case, no trailing colon.

    Forms spread a short label over its cell with spaces ("성  명", "주    소") or
    wrap it over lines; a person reading the form writes "성명". Whitespace
    therefore never distinguishes two labels.
    """

    return _WHITESPACE_RE.sub("", value).casefold().rstrip(":：")


def _direct_paragraph_text(paragraph: HwpxOxmlParagraph) -> str:
    parts: list[str] = []
    for run in paragraph.element.findall(f"{_HP}run"):
        for child in run:
            if child.tag == f"{_HP}t":
                parts.append(_text_element_content(child))
    return _collapse_whitespace("".join(parts))


def _collect_tables_from_table(
    table: HwpxOxmlTable,
    *,
    anchor_paragraph_index: int,
    inherited_header_text: str,
    sink: list[_AnchoredTable],
) -> str:
    last_header_text = inherited_header_text
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                last_header_text = _collect_tables_from_paragraph(
                    paragraph,
                    anchor_paragraph_index=anchor_paragraph_index,
                    inherited_header_text=last_header_text,
                    sink=sink,
                )
    return last_header_text


def _collect_tables_from_paragraph(
    paragraph: HwpxOxmlParagraph,
    *,
    anchor_paragraph_index: int,
    inherited_header_text: str,
    sink: list[_AnchoredTable],
) -> str:
    paragraph_text_parts: list[str] = []
    last_header_text = inherited_header_text

    for run in paragraph.element.findall(f"{_HP}run"):
        for child in run:
            if child.tag == f"{_HP}t":
                if child.text:
                    paragraph_text_parts.append(child.text)
                continue
            if child.tag != f"{_HP}tbl":
                continue

            paragraph_prefix_text = _collapse_whitespace("".join(paragraph_text_parts))
            header_text = paragraph_prefix_text or last_header_text
            table = HwpxOxmlTable(child, paragraph)
            sink.append(
                _AnchoredTable(
                    table=table,
                    paragraph_index=anchor_paragraph_index,
                    caption_text=paragraph_prefix_text,
                    preceding_paragraph_text=last_header_text,
                    header_text=header_text,
                )
            )
            last_header_text = _collect_tables_from_table(
                table,
                anchor_paragraph_index=anchor_paragraph_index,
                inherited_header_text=header_text,
                sink=sink,
            )

    paragraph_text = _collapse_whitespace("".join(paragraph_text_parts))
    return paragraph_text or last_header_text


def _collect_document_tables(document: HwpxDocument) -> list[_IndexedTable]:
    anchored_tables: list[_AnchoredTable] = []
    last_top_level_text = ""

    for paragraph_index, paragraph in enumerate(document.paragraphs):
        _collect_tables_from_paragraph(
            paragraph,
            anchor_paragraph_index=paragraph_index,
            inherited_header_text=last_top_level_text,
            sink=anchored_tables,
        )
        paragraph_text = _direct_paragraph_text(paragraph)
        if paragraph_text:
            last_top_level_text = paragraph_text

    return [
        _IndexedTable(
            table_index=table_index,
            table=item.table,
            paragraph_index=item.paragraph_index,
            caption_text=item.caption_text,
            preceding_paragraph_text=item.preceding_paragraph_text,
            header_text=item.header_text,
        )
        for table_index, item in enumerate(anchored_tables)
    ]


def _text_of_cell(cell: object) -> str:
    paragraphs = list(getattr(cell, "paragraphs", []) or [])
    if paragraphs:
        return "\n".join(paragraph.text or "" for paragraph in paragraphs)
    return cell.text  # type: ignore[attr-defined]


def _cell_text(table: HwpxOxmlTable, row_index: int, col_index: int) -> str:
    return _text_of_cell(table.cell(row_index, col_index))


def _grid_cells(table: HwpxOxmlTable) -> list[tuple[int, int, object]]:
    """Every logical position with its cell, row by row, from one pass over the grid.

    A grid with a position no cell covers is read coordinate by coordinate instead, so the
    error names that position as ``table.cell`` does.
    """

    try:
        return [(position.row, position.column, position.cell) for position in table.iter_grid()]
    except IndexError:
        return [
            (row_index, col_index, table.cell(row_index, col_index))
            for row_index in range(table.row_count)
            for col_index in range(table.column_count)
        ]


def _table_is_empty(table: HwpxOxmlTable) -> bool:
    for _, _, cell in _grid_cells(table):
        if _text_of_cell(cell).strip():
            return False
    return True


def _first_row_preview(table: HwpxOxmlTable) -> list[str]:
    if table.row_count == 0:
        return []
    return [_cell_text(table, 0, col_index) for col_index in range(table.column_count)]


def _body_paragraph_location(paragraph_index: int) -> dict[str, object]:
    return {"kind": "body_paragraph", "paragraph_index": paragraph_index}


def _table_cell_paragraph_location(
    table_index: int,
    row_index: int,
    col_index: int,
    cell_paragraph_index: int,
) -> dict[str, object]:
    return {
        "kind": "table_cell_paragraph",
        "table_index": table_index,
        "row": row_index,
        "col": col_index,
        "cell_paragraph_index": cell_paragraph_index,
    }


def _table_cells(table_ref: _IndexedTable) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for row_index, col_index, cell in _grid_cells(table_ref.table):
        paragraphs = list(getattr(cell, "paragraphs", []) or [])
        paragraph_payloads: list[dict[str, object]] = []
        for cell_paragraph_index, paragraph in enumerate(paragraphs):
            paragraph_payloads.append(
                {
                    "cell_paragraph_index": cell_paragraph_index,
                    "text": paragraph.text or "",
                    "location": _table_cell_paragraph_location(
                        table_ref.table_index,
                        row_index,
                        col_index,
                        cell_paragraph_index,
                    ),
                }
            )
        cells.append(
            {
                "row": row_index,
                "col": col_index,
                "text": "\n".join(paragraph.text or "" for paragraph in paragraphs) if paragraphs else cell.text,  # type: ignore[attr-defined]
                "paragraphs": paragraph_payloads,
                "location": {
                    "kind": "table_cell",
                    "table_index": table_ref.table_index,
                    "row": row_index,
                    "col": col_index,
                },
            }
        )
    return cells


def _direction_delta(direction: PathDirection) -> tuple[int, int]:
    if direction == "right":
        return (0, 1)
    if direction == "left":
        return (0, -1)
    if direction == "down":
        return (1, 0)
    return (-1, 0)


def _move(
    table: HwpxOxmlTable,
    row_index: int,
    col_index: int,
    direction: PathDirection,
    grid: Any = None,
) -> tuple[int, int] | None:
    # A direction crosses the current physical cell's edge. Moving one grid
    # slot could otherwise stay inside a merged label and overwrite the label.
    if grid is None:
        grid = table.get_cell_map()
    current = grid[row_index][col_index]
    anchor_row, anchor_col = current.anchor
    row_delta, col_delta = _direction_delta(direction)
    target_row = anchor_row + (current.row_span if row_delta > 0 else row_delta)
    target_col = anchor_col + (current.col_span if col_delta > 0 else col_delta)
    if target_row < 0 or target_col < 0:
        return None
    if target_row >= table.row_count or target_col >= table.column_count:
        return None
    return grid[target_row][target_col].anchor


class _LabelIndex:
    """Every table cell by the label it would be found under, read once.

    A cell whose whole text is the label wins. Only when there is none does a
    cell match by one of its lines: a two-language label ("성  명" over "Name")
    is found by either line. Cells are kept in document order.
    """

    def __init__(self, tables: list[_IndexedTable]) -> None:
        self.whole: dict[str, list[_LabelCandidate]] = {}
        self.by_line: dict[str, list[_LabelCandidate]] = {}
        for table_ref in tables:
            # Count physical cells, not every logical slot occupied by a merge.
            # Distinct cells with the same label remain ambiguous.
            for position in table_ref.table.iter_grid():
                if not position.is_anchor:
                    continue
                row_index, col_index = position.anchor
                cell_text = _text_of_cell(position.cell)
                key = _normalize_label_text(cell_text)
                if not key:
                    continue
                candidate = _LabelCandidate(
                    table_index=table_ref.table_index,
                    table=table_ref.table,
                    row=row_index,
                    col=col_index,
                    text=cell_text,
                )
                self.whole.setdefault(key, []).append(candidate)
                if "\n" not in cell_text:
                    continue
                for line_key in dict.fromkeys(_normalize_label_text(line) for line in cell_text.splitlines()):
                    if line_key and line_key != key:
                        self.by_line.setdefault(line_key, []).append(candidate)

    def find(self, label_text: str) -> list[_LabelCandidate]:
        key = _normalize_label_text(label_text)
        if not key:
            raise ValueError("label_text must contain at least one non-whitespace character")
        return self.whole.get(key) or self.by_line.get(key) or []


def _find_label_candidates(
    tables: list[_IndexedTable],
    label_text: str,
) -> list[_LabelCandidate]:
    return _LabelIndex(tables).find(label_text)


def _select_label_candidates(
    index: _LabelIndex,
    label_text: str,
) -> tuple[list[_LabelCandidate], str | None]:
    """Candidates for a path's label token, honouring ``label[n]``.

    The token is tried as a label first, so a label that really ends in
    ``[1]`` still works. Returns ``(candidates, error)``.
    """

    candidates = index.find(label_text)
    if candidates:
        return candidates, None
    occurrence = _OCCURRENCE_RE.match(label_text)
    if occurrence is None:
        return [], None
    pool = index.find(occurrence["label"])
    number = int(occurrence["number"])
    if pool and number > len(pool):
        return [], f"label occurrence out of range: {number} of {len(pool)}"
    return pool[number - 1 : number], None


def _candidate_payload(label_text: str, candidates: list[_LabelCandidate]) -> list[TableLabelCandidate]:
    label = _collapse_whitespace(label_text)
    return [
        {
            "table_index": candidate.table_index,
            "row": candidate.row,
            "col": candidate.col,
            "text": candidate.text,
            "selector": f"{label}[{number}]",
        }
        for number, candidate in enumerate(candidates, start=1)
    ]


def _cell_is_blank(cell: object) -> bool:
    """No text and nothing else either: a cell holding a picture, a nested
    table or a form field has no text but is not a blank to write into."""

    if _text_of_cell(cell).strip():
        return False
    element = getattr(cell, "element", None)
    if element is None:
        return True
    for run in element.iter(f"{_HP}run"):
        for child in run:
            if child.tag != f"{_HP}t" or len(child):
                return False
    return True


def _cell_reference(
    table: HwpxOxmlTable,
    row_index: int,
    col_index: int,
) -> TableCellReference:
    return {
        "row": row_index,
        "col": col_index,
        "text": _cell_text(table, row_index, col_index),
    }


def _parse_path(path: str) -> tuple[str | None, list[str], str | None]:
    tokens = [token.strip() for token in path.split(">")]
    if not tokens or not tokens[0]:
        return (None, [], "path must start with a label")

    label_text = tokens[0]
    raw_directions = [token for token in tokens[1:] if token]
    if not raw_directions:
        return (label_text, [], "path must include at least one direction")
    return (label_text, raw_directions, None)


def get_table_map(document: HwpxDocument) -> TableMapResult:
    """Return compact metadata for every table in document order."""

    tables: list[TableMapEntry] = []
    for table_ref in _collect_document_tables(document):
        tables.append(
            {
                "table_index": table_ref.table_index,
                "paragraph_index": table_ref.paragraph_index,
                "location": _body_paragraph_location(table_ref.paragraph_index),
                "rows": table_ref.table.row_count,
                "cols": table_ref.table.column_count,
                "caption_text": table_ref.caption_text,
                "preceding_paragraph_text": table_ref.preceding_paragraph_text,
                "header_text": table_ref.header_text,
                "first_row_preview": _first_row_preview(table_ref.table),
                "cells": _table_cells(table_ref),
                "is_empty": _table_is_empty(table_ref.table),
            }
        )
    return {"tables": tables}


def find_cell_by_label(
    document: HwpxDocument,
    label_text: str,
    direction: SearchDirection = "right",
) -> TableLabelSearchResult:
    """Find label cells and return the adjacent target cells that remain in bounds."""

    if direction not in {"right", "down"}:
        raise ValueError("direction must be one of: right, down")

    matches: list[TableLabelMatch] = []
    for candidate in _find_label_candidates(_collect_document_tables(document), label_text):
        target = _move(candidate.table, candidate.row, candidate.col, direction)
        if target is None:
            continue
        target_row, target_col = target
        matches.append(
            {
                "table_index": candidate.table_index,
                "label_cell": {
                    "row": candidate.row,
                    "col": candidate.col,
                    "text": candidate.text,
                },
                "target_cell": _cell_reference(candidate.table, target_row, target_col),
            }
        )

    return {
        "matches": matches,
        "count": len(matches),
    }


def _cell_width_mm(cell: object) -> float | None:
    element = getattr(cell, "element", None)
    size = element.find(f"{_HP}cellSz") if element is not None else None
    try:
        return round(int(size.get("width")) / _HWPUNIT_PER_MM, 1)  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        return None


def form_slots(document: HwpxDocument, *, min_width_mm: float = 5.0) -> TableFormSlotsResult:
    """List the blanks of a form: empty cells right of, or below, a cell with text.

    Forms put thin empty cells between a label and its boxes as spacing; a
    value written there comes out one character per line. Cells narrower than
    *min_width_mm* (``width_mm`` of each slot) are therefore left out; pass
    ``0`` to list them too. A path still reaches a cell this list leaves out.

    Each slot carries the ``path`` that :func:`fill_by_path` takes to fill it
    (``"성명 > right"``; ``"성명[2] > right"`` when the label occurs more than
    once). A blank is offered once, by the cell to its left when that has text,
    otherwise by the cell above. ``path`` is None when the label cannot be
    written as a path (it contains ``>``, or is only a colon); the slot's
    ``table_index`` and ``target_cell`` still say where it is. ``table_index``
    counts tables as ``get_table_map`` does, tables inside cells included.

    This reads structure only. Whether a cell with text is a label, and what
    belongs in the blank, is for the caller to decide.
    """

    tables = _collect_document_tables(document)
    index = _LabelIndex(tables)

    slots: list[TableFormSlot] = []
    backwards: tuple[tuple[SearchDirection, PathDirection], ...] = (("right", "left"), ("down", "up"))
    for table_ref in tables:
        table = table_ref.table
        grid = table.get_cell_map()
        texts: dict[tuple[int, int], str] = {}
        widths: dict[tuple[int, int], float | None] = {}
        blanks: list[tuple[int, int]] = []
        for position in table.iter_grid():
            if not position.is_anchor:
                continue
            texts[position.anchor] = _text_of_cell(position.cell)
            if not _cell_is_blank(position.cell):
                continue
            width = _cell_width_mm(position.cell)
            if width is not None and width < min_width_mm:
                continue
            widths[position.anchor] = width
            blanks.append(position.anchor)
        for row_index, col_index in blanks:
            for direction, back in backwards:
                source = _move(table, row_index, col_index, back, grid)
                if source is None:
                    continue
                label_text = texts.get(source, "")
                if not label_text.strip():
                    continue
                # The path walks from the label; a merged label reaches only one
                # of the cells beside it.
                if _move(table, source[0], source[1], direction, grid) != (row_index, col_index):
                    continue
                label = _collapse_whitespace(label_text)
                path: str | None = None
                if ">" not in label and _normalize_label_text(label_text):
                    same = index.whole.get(_normalize_label_text(label_text), [])
                    selector = label
                    if len(same) > 1:
                        number = next(
                            number
                            for number, candidate in enumerate(same, start=1)
                            if candidate.table is table and (candidate.row, candidate.col) == source
                        )
                        selector = f"{label}[{number}]"
                    path = f"{selector} > {direction}"
                slots.append(
                    {
                        "label": label,
                        "path": path,
                        "direction": direction,
                        "table_index": table_ref.table_index,
                        "label_cell": {"row": source[0], "col": source[1], "text": label_text},
                        "target_cell": {"row": row_index, "col": col_index, "text": texts[(row_index, col_index)]},
                        "width_mm": widths[(row_index, col_index)],
                    }
                )
                break
    return {"slots": slots, "count": len(slots)}


def fill_by_path(
    document: HwpxDocument,
    mappings: Mapping[str, str],
    *,
    fit: "FitPolicy | None" = None,
) -> TableFillResult:
    """Fill multiple table cells using label-based navigation paths.

    A path is a label and one or more directions: ``"성명 > right"``. The label
    is compared without whitespace, case or a trailing colon, so ``"성명"``
    finds a cell that reads ``"성  명"``. When the label matches several cells
    the path fails as ``"ambiguous label"`` and lists them under
    ``candidates``; write ``"성명[2] > right"`` to pick the second in document
    order. :func:`form_slots` lists the blanks with their paths.

    Without *fit* a value is written as it is and Hancom grows the row when it
    needs more lines. With a :class:`~hwpx.form_fit.policy.FitPolicy` each
    value is measured against its cell: it wraps or shrinks as the policy
    allows, the outcome is reported under ``fit``, and a value the policy
    refuses fails as ``"value does not fit"`` with its cell left as it was.
    """

    # Labels are resolved against the document as it is when the call starts,
    # so the outcome does not depend on the order of the paths: a value written
    # for one path is never taken for the label of another.
    index = _LabelIndex(_collect_document_tables(document))
    grids: dict[int, Any] = {}
    applied: list[TableFillApplied] = []
    failed: list[TableFillFailed] = []

    for path, value in mappings.items():
        label_text, raw_directions, path_error = _parse_path(path)
        if path_error is not None or label_text is None:
            failed.append({"path": path, "reason": path_error or "invalid path"})
            continue

        try:
            candidates, selection_error = _select_label_candidates(index, label_text)
        except ValueError as exc:
            failed.append({"path": path, "reason": str(exc)})
            continue

        if selection_error is not None:
            failed.append({"path": path, "reason": selection_error})
            continue
        if not candidates:
            failed.append({"path": path, "reason": "label not found"})
            continue
        if len(candidates) > 1:
            failed.append(
                {
                    "path": path,
                    "reason": "ambiguous label",
                    "candidates": _candidate_payload(label_text, candidates),
                }
            )
            continue

        candidate = candidates[0]
        grid = grids.get(candidate.table_index)
        if grid is None:
            grid = grids[candidate.table_index] = candidate.table.get_cell_map()
        current_row = candidate.row
        current_col = candidate.col
        navigation_failed = False

        for raw_direction in raw_directions:
            direction = raw_direction.casefold()
            if direction not in {"left", "right", "up", "down"}:
                failed.append(
                    {
                        "path": path,
                        "reason": f"unsupported direction: {raw_direction}",
                    }
                )
                navigation_failed = True
                break

            next_position = _move(candidate.table, current_row, current_col, direction, grid)
            if next_position is None:
                failed.append({"path": path, "reason": "navigation out of bounds"})
                navigation_failed = True
                break

            current_row, current_col = next_position

        if navigation_failed:
            continue

        text_value = str(value)
        outcome = candidate.table.set_cell_text(
            current_row, current_col, text_value, logical=True, fit=fit
        )
        if outcome is not None and not outcome.ok:
            failed.append({"path": path, "reason": "value does not fit", "fit": outcome.to_dict()})
            continue
        entry: TableFillApplied = {
            "path": path,
            "table_index": candidate.table_index,
            "row": current_row,
            "col": current_col,
            "value": text_value,
        }
        if outcome is not None:
            entry["fit"] = outcome.to_dict()
        applied.append(entry)

    return {
        "applied": applied,
        "failed": failed,
        "applied_count": len(applied),
        "failed_count": len(failed),
    }
