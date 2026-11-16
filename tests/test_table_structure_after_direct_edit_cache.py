# SPDX-License-Identifier: Apache-2.0
"""A cell paragraph edited in the XML tree loses its old line cache when the table is restructured.

The save drops a cache the part was read with once its paragraph's content changed, pairing caches
by element identity. ``insert_rows``/``insert_columns``/``split_cell``/``delete_rows`` rebuild the
table's elements, so a cell paragraph edited directly (lxml, then ``mark_dirty()``) before them kept
its old ``hp:linesegarray``: Hancom then lays the new text into the old lines and draws it over
itself. The structure edits now judge those caches before rebuilding.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
DOCUMENTS = [
    "line_cache_table_cells.hwpx",
    "memos_in_fields.hwpx",
    "merge_3x3_a1c2.hwpx",
    "open_rules_base.hwpx",
    "pages_anchor_lines_past_a_moved_table.hwpx",
    "pages_band_at_zero_then_empty_paragraphs_then_band.hwpx",
]
OPERATIONS = {
    "insert_rows_below": lambda table: table.insert_rows(0),
    "insert_rows_above": lambda table: table.insert_rows(0, side="above"),
    "insert_columns_right": lambda table: table.insert_columns(0),
    "insert_columns_left": lambda table: table.insert_columns(0, side="left"),
    # the copies of the edited paragraph lose the old cache too
    "insert_rows_below_copy": lambda table: table.insert_rows(0, copy_content=True),
    "insert_columns_right_copy": lambda table: table.insert_columns(0, copy_content=True),
    "split_cell_columns": lambda table: table.split_cell(0, 0, cols=2),
    "split_cell_rows": lambda table: table.split_cell(0, 0, rows=2),
    "delete_last_row": lambda table: table.delete_rows(table.row_count - 1),
}
COMBINATIONS = [
    (document, operation) for document in DOCUMENTS for operation in OPERATIONS
] + [("line_cache_table_cells.hwpx", "insert_rows_below-no-mark-dirty")]  # 6 x 9 + 1 = 55


def _cached_cell_text(table) -> object:
    """The first cell paragraph of *table* (not of a table inside it) holding text and a line cache."""

    for paragraph in table.element.iter(f"{HP}p"):
        node = paragraph.find(f"{HP}run/{HP}t")
        if (
            paragraph.find(f"{HP}linesegarray") is not None
            and node is not None
            and len(node) == 0
            and (node.text or "")
            and next(paragraph.iterancestors(f"{HP}tbl")) is table.element
        ):
            return node
    raise AssertionError("fixture has no cached cell text")


@pytest.mark.parametrize(("document", "operation"), COMBINATIONS)
def test_a_directly_edited_cell_loses_its_old_cache(document: str, operation: str) -> None:
    doc = HwpxDocument.open(FIXTURES / document)
    table = doc.tables[0]
    node = _cached_cell_text(table)
    # Same length, other characters: the geometric stale check cannot see this one.
    edited = ("X" if node.text[0] != "X" else "Y") + node.text[1:]
    node.text = edited
    name = operation.removesuffix("-no-mark-dirty")
    if name == operation:
        doc.sections[0].mark_dirty()
    OPERATIONS[name](doc.tables[0])

    buffer = io.BytesIO()
    doc.save(buffer)
    again = HwpxDocument.open(buffer.getvalue())
    holders = [
        paragraph
        for section in again.sections
        for paragraph in section.element.iter(f"{HP}p")
        if (found := paragraph.find(f"{HP}run/{HP}t")) is not None and found.text == edited
    ]
    assert holders, "the edited text was saved"
    assert all(paragraph.find(f"{HP}linesegarray") is None for paragraph in holders)


def test_caches_of_cells_nobody_edited_stay() -> None:
    doc = HwpxDocument.open(FIXTURES / "line_cache_table_cells.hwpx")
    table = doc.tables[0]
    before = len(list(table.element.iter(f"{HP}linesegarray")))
    node = _cached_cell_text(table)
    node.text = ("X" if node.text[0] != "X" else "Y") + node.text[1:]
    doc.sections[0].mark_dirty()
    table.insert_columns(0, copy_content=True)
    after = len(list(doc.tables[0].element.iter(f"{HP}linesegarray")))
    assert 0 < after  # only the edited paragraph (and its copies) lost theirs
    assert before > 1
