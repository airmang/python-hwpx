# SPDX-License-Identifier: Apache-2.0
"""The table map: every table of a document in document order, with its cells' text.

Finding a cell by the label next to it (``find_cell_by_label``, ``form_slots``,
``fill_by_path``) guesses what a form means and moved to python-hwpx-automation in
7.0 (``hwpx_automation.forms``). The map stays: it reports what the file holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from ..oxml import HwpxOxmlParagraph, HwpxOxmlTable
from ..oxml._document_primitives import _text_element_content

if TYPE_CHECKING:
    from ..document import HwpxDocument

__all__ = [
    "TableMapEntry",
    "TableMapResult",
    "get_table_map",
]

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
_WHITESPACE_RE = re.compile(r"\s+")


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


def _collapse_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


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


def __getattr__(name: str) -> object:
    """이름표로 칸 찾기(7.0에서 ``hwpx_automation.forms``로 옮김)의 이름이면 새 자리를 알려 준다."""

    from .._moved_modules import moved_name_error

    moved = moved_name_error(__name__, name)
    if moved is not None:
        raise moved
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
