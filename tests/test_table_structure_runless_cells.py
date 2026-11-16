"""Row/column insertion and cell splits next to cells whose paragraph has no run.

Hancom saves an empty cell's paragraph as ``<hp:p .../>`` with no run when nothing was ever typed
there (``tests/fixtures/hancom_saved/fill_image_*.hwpx``: a 2 x 3 table whose cells only carry a
fill image). The empty cell an insertion makes from such a cell reused that self-closing tag and
appended ``</hp:p>``, so ``insert_rows`` (empty rows, the 7.0 default), ``insert_columns`` and
``split_cell`` raised a raw ``XMLSyntaxError``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
RUNLESS = sorted(HANCOM.glob("fill_image_*.hwpx"))


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


def test_the_fixtures_hold_runless_cell_paragraphs() -> None:
    assert len(RUNLESS) == 4
    for path in RUNLESS:
        table = HwpxDocument.open(path).tables.all[0]
        paragraph = table.cell(0, 0).paragraphs[0].element
        assert paragraph.find(f"{HP}run") is None


@pytest.mark.parametrize("path", RUNLESS, ids=lambda p: p.stem)
@pytest.mark.parametrize("copy_content", [False, True])
@pytest.mark.parametrize("side", ["below", "above"])
def test_insert_rows_next_to_runless_cells(path: Path, copy_content: bool, side: str) -> None:
    doc = HwpxDocument.open(path)
    table = doc.tables.all[0]
    rows, cols = table.row_count, table.column_count
    doc.tables.insert_rows(table, rows - 1, 2, side=side, copy_content=copy_content)
    assert table.row_count == rows + 2
    again = _reopen(doc).tables.all[0]
    assert (again.row_count, again.column_count) == (rows + 2, cols)
    new_row = rows if side == "below" else rows - 1
    for col in range(cols):
        cell = again.cell(new_row, col)
        assert cell.text == ""
        assert cell.border_fill_id_ref == table.cell(rows - 1 if side == "below" else rows + 1, col).border_fill_id_ref


@pytest.mark.parametrize("path", RUNLESS, ids=lambda p: p.stem)
@pytest.mark.parametrize("copy_content", [False, True])
def test_insert_columns_next_to_runless_cells(path: Path, copy_content: bool) -> None:
    doc = HwpxDocument.open(path)
    table = doc.tables.all[0]
    rows, cols = table.row_count, table.column_count
    doc.tables.insert_columns(table, 0, 1, copy_content=copy_content)
    again = _reopen(doc).tables.all[0]
    assert (again.row_count, again.column_count) == (rows, cols + 1)


@pytest.mark.parametrize("path", RUNLESS, ids=lambda p: p.stem)
def test_split_a_runless_cell(path: Path) -> None:
    doc = HwpxDocument.open(path)
    table = doc.tables.all[0]
    doc.tables.split_cell(table, 0, 0, rows=2, cols=2)
    _reopen(doc)


def test_new_cells_take_fresh_paragraph_ids() -> None:
    doc = HwpxDocument.open(RUNLESS[0])
    table = doc.tables.all[0]
    doc.tables.insert_rows(table, 1, 2)
    ids = [p.get("id") for p in table.element.iter(f"{HP}p")]
    new = ids[-6:]
    assert len(set(new)) == 6 and "0" not in new
