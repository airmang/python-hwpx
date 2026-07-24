# SPDX-License-Identifier: Apache-2.0
"""Generic public byte/XML primitives required by the MCP evalplan owner."""

from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

from hwpx.patch import paragraph_chunks, rewrite_package_parts
from hwpx.table_patch import (
    TableCell,
    cell_paragraph_spans,
    direct_table_cells,
    table_text,
)


def _table() -> bytes:
    return b"""<hp:tbl rowCnt="1" colCnt="1">
<hp:tr><hp:tc><hp:cellAddr colAddr="0" rowAddr="0"/>
<hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList>
<hp:p id="1"><hp:run><hp:t>alpha</hp:t></hp:run></hp:p>
<hp:p id="2"><hp:run><hp:t>beta</hp:t></hp:run></hp:p>
</hp:subList></hp:tc></hp:tr></hp:tbl>"""


def test_direct_table_cells_expose_stable_address_and_byte_spans() -> None:
    table = _table()
    cells = direct_table_cells(table)

    assert len(cells) == 1
    assert isinstance(cells[0], TableCell)
    assert (
        cells[0].row,
        cells[0].col,
        cells[0].row_span,
        cells[0].col_span,
    ) == (0, 0, 1, 1)
    assert table_text(table[cells[0].start : cells[0].end]) == "alphabeta"


def test_cell_and_section_paragraph_chunks_keep_document_order() -> None:
    table = _table()
    cell = direct_table_cells(table)[0]
    cell_xml = table[cell.start : cell.end]

    spans = cell_paragraph_spans(cell_xml)
    assert [table_text(cell_xml[start:end]) for start, end in spans] == [
        "alpha",
        "beta",
    ]
    assert [table_text(chunk) for chunk in paragraph_chunks(table)] == [
        "alpha",
        "beta",
    ]


def test_rewrite_package_parts_replaces_only_named_payloads() -> None:
    source_buffer = io.BytesIO()
    with ZipFile(source_buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", b"before")
        archive.writestr("version.xml", b"keep")

    rewritten = rewrite_package_parts(
        source_buffer.getvalue(),
        {"Contents/section0.xml": b"after"},
    )

    with ZipFile(io.BytesIO(rewritten)) as archive:
        assert archive.read("Contents/section0.xml") == b"after"
        assert archive.read("version.xml") == b"keep"
