"""Reusable helpers for HWPX table discovery and form-like navigation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Literal, Mapping, TypedDict

from ..oxml import HwpxOxmlParagraph, HwpxOxmlTable

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = [
    "SearchDirection",
    "PathDirection",
    "TableCellReference",
    "TableFillApplied",
    "TableFillFailed",
    "TableFillResult",
    "TableLabelMatch",
    "TableLabelSearchResult",
    "TableMapEntry",
    "TableMapResult",
    "fill_by_path",
    "find_cell_by_label",
    "get_table_map",
]

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
_WHITESPACE_RE = re.compile(r"\s+")

SearchDirection = Literal["right", "down"]
PathDirection = Literal["left", "right", "up", "down"]


class TableMapEntry(TypedDict):
    """Compact metadata describing a table in document order."""

    table_index: int
    paragraph_index: int
    rows: int
    cols: int
    header_text: str
    first_row_preview: list[str]
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


class TableFillApplied(TypedDict):
    """A successfully applied path-based fill operation."""

    path: str
    table_index: int
    row: int
    col: int
    value: str


class TableFillFailed(TypedDict):
    """A failed path-based fill operation and its reason."""

    path: str
    reason: str


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
    header_text: str


@dataclass(frozen=True, slots=True)
class _IndexedTable:
    table_index: int
    table: HwpxOxmlTable
    paragraph_index: int
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
    normalized = _collapse_whitespace(value).casefold()
    while normalized.endswith((":", "：")):
        normalized = normalized[:-1].rstrip()
    return normalized


def _direct_paragraph_text(paragraph: HwpxOxmlParagraph) -> str:
    parts: list[str] = []
    for run in paragraph.element.findall(f"{_HP}run"):
        for child in run:
            if child.tag == f"{_HP}t" and child.text:
                parts.append(child.text)
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
            header_text=item.header_text,
        )
        for table_index, item in enumerate(anchored_tables)
    ]


def _cell_text(table: HwpxOxmlTable, row_index: int, col_index: int) -> str:
    return table.cell(row_index, col_index).text


def _table_is_empty(table: HwpxOxmlTable) -> bool:
    for row_index in range(table.row_count):
        for col_index in range(table.column_count):
            if _cell_text(table, row_index, col_index).strip():
                return False
    return True


def _first_row_preview(table: HwpxOxmlTable) -> list[str]:
    if table.row_count == 0:
        return []
    return [_cell_text(table, 0, col_index) for col_index in range(table.column_count)]


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
) -> tuple[int, int] | None:
    row_delta, col_delta = _direction_delta(direction)
    target_row = row_index + row_delta
    target_col = col_index + col_delta
    if target_row < 0 or target_col < 0:
        return None
    if target_row >= table.row_count or target_col >= table.column_count:
        return None
    return (target_row, target_col)


def _find_label_candidates(
    tables: list[_IndexedTable],
    label_text: str,
) -> list[_LabelCandidate]:
    normalized_label = _normalize_label_text(label_text)
    if not normalized_label:
        raise ValueError("label_text must contain at least one non-whitespace character")

    candidates: list[_LabelCandidate] = []
    for table_ref in tables:
        for row_index in range(table_ref.table.row_count):
            for col_index in range(table_ref.table.column_count):
                cell_text = _cell_text(table_ref.table, row_index, col_index)
                if _normalize_label_text(cell_text) != normalized_label:
                    continue
                candidates.append(
                    _LabelCandidate(
                        table_index=table_ref.table_index,
                        table=table_ref.table,
                        row=row_index,
                        col=col_index,
                        text=cell_text,
                    )
                )
    return candidates


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
                "rows": table_ref.table.row_count,
                "cols": table_ref.table.column_count,
                "header_text": table_ref.header_text,
                "first_row_preview": _first_row_preview(table_ref.table),
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


def fill_by_path(
    document: HwpxDocument,
    mappings: Mapping[str, str],
) -> TableFillResult:
    """Fill multiple table cells using label-based navigation paths."""

    indexed_tables = _collect_document_tables(document)
    applied: list[TableFillApplied] = []
    failed: list[TableFillFailed] = []

    for path, value in mappings.items():
        label_text, raw_directions, path_error = _parse_path(path)
        if path_error is not None or label_text is None:
            failed.append({"path": path, "reason": path_error or "invalid path"})
            continue

        try:
            candidates = _find_label_candidates(indexed_tables, label_text)
        except ValueError as exc:
            failed.append({"path": path, "reason": str(exc)})
            continue

        if not candidates:
            failed.append({"path": path, "reason": "label not found"})
            continue
        if len(candidates) > 1:
            failed.append({"path": path, "reason": "ambiguous label"})
            continue

        candidate = candidates[0]
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

            next_position = _move(candidate.table, current_row, current_col, direction)
            if next_position is None:
                failed.append({"path": path, "reason": "navigation out of bounds"})
                navigation_failed = True
                break

            current_row, current_col = next_position

        if navigation_failed:
            continue

        text_value = str(value)
        candidate.table.set_cell_text(current_row, current_col, text_value, logical=True)
        applied.append(
            {
                "path": path,
                "table_index": candidate.table_index,
                "row": current_row,
                "col": current_col,
                "value": text_value,
            }
        )

    return {
        "applied": applied,
        "failed": failed,
        "applied_count": len(applied),
        "failed_count": len(failed),
    }
