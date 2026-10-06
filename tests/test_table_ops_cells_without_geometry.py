"""Table structure edits refuse a table whose cells lack the address or size OWPML requires.

Such tables turn up in documents written by other programs: ``hp:tc`` holding paragraphs straight, with no
``hp:subList``, ``hp:cellAddr``, ``hp:cellSpan`` or ``hp:cellSz``. Every structure edit used to stop on an
``AssertionError`` there; it now reports the table as refused, as it does a table holding a table.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.table_patch import apply_table_ops

SECTION = "Contents/section0.xml"


def _document_with_bare_cells() -> bytes:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"
    source = io.BytesIO(document.to_bytes())
    target = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as rewritten:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == SECTION:
                text = data.decode("utf-8")
                text = re.sub(r"<hp:(cellAddr|cellSpan|cellSz|cellMargin)\b[^>]*/>", "", text)
                data = text.encode("utf-8")
            rewritten.writestr(info, data)
    return target.getvalue()


@pytest.mark.parametrize(
    "op",
    [
        {"op": "delete_column", "col": 1},
        {"op": "delete_row", "row": 1},
        {"op": "insert_row_by_clone", "ref_row": 0},
        {"op": "insert_block_by_clone", "ref_rows": [0, 1]},
        {"op": "insert_column_by_clone", "ref_col": 0},
        {"op": "set_column_widths", "widths": [1000, 2000, 3000]},
        {"op": "autofit_columns"},
        {"op": "reorder_rows", "order": [2, 1, 0]},
        {"op": "split_table", "split_row": 1},
    ],
)
def test_a_structure_edit_refuses_cells_without_an_address_or_a_size(op: dict) -> None:
    data = _document_with_bare_cells()

    result = apply_table_ops(data, [{**op, "table_index": 0}])

    assert not result.ok
    assert "without hp:cellAddr or hp:cellSz" in result.skipped[0].reason
