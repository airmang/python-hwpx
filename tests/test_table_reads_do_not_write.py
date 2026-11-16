"""Reading a table never changes the document.

A read that creates the element it looks for (``hp:cellSz``, ``hp:cellSpan`` …) turns a
read-only pass into an edit: the section is rewritten on save and code that only looked at a
form finds its file changed. Every read-only property of tables, rows, columns and cells is
read here on Hancom-saved documents and on cells stripped of their size and span, and the
section XML must come out byte for byte the same.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree as ET

from hwpx import HwpxDocument

FIXTURES = Path(__file__).parent / "fixtures"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

TABLE_READS = (
    "row_count", "column_count", "width", "column_widths", "row_heights", "alignment",
    "text_wrap", "in_margins", "page_break", "repeat_header", "no_adjust", "header_rows",
    "cell_zones", "caption",
)
CELL_READS = (
    "address", "span", "width", "height", "text", "margins", "field_name", "vert_align",
    "is_header", "border_fill_id_ref",
)


def _documents_with_tables(limit: int = 40) -> list[Path]:
    found: list[Path] = []
    for path in sorted((FIXTURES / "hancom_saved").glob("*.hwpx")):
        if "tbl" in path.name or "table" in path.name or "cell" in path.name:
            found.append(path)
        if len(found) >= limit:
            break
    return found


def _section_bytes(doc: HwpxDocument) -> list[bytes]:
    return [ET.tostring(section.element) for section in doc.oxml.sections]


def _read_everything(doc: HwpxDocument) -> int:
    count = 0
    for table in doc.tables.all:
        for name in TABLE_READS:
            if hasattr(table, name):
                getattr(table, name)
                count += 1
        for row in table.rows:
            for cell in row.cells:
                for name in CELL_READS:
                    if hasattr(cell, name):
                        getattr(cell, name)
                        count += 1
        for column in getattr(table, "columns", ()):
            column.width
            column.cells
        table.cell_map
    return count


@pytest.mark.parametrize("path", _documents_with_tables(), ids=lambda p: p.name)
def test_reading_hancom_tables_changes_nothing(path: Path) -> None:
    doc = HwpxDocument.open(path)
    before = _section_bytes(doc)
    assert _read_everything(doc) > 0
    assert _section_bytes(doc) == before


def test_reading_a_cell_without_size_or_span_does_not_add_them() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    for tc in table.element.iter(f"{HP}tc"):
        for tag in ("cellSz", "cellSpan"):
            child = tc.find(f"{HP}{tag}")
            if child is not None:
                tc.remove(child)
    before = _section_bytes(doc)
    cell = table.cell(0, 0)
    assert cell.span == (1, 1)
    assert cell.width == 0
    assert cell.height == 0
    assert _section_bytes(doc) == before
