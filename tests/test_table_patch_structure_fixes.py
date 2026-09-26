"""table_patch structure ops on tables that real documents often have.

- a table in a paragraph that also holds the section setup (``hp:secPr`` with
  ``hp:pagePr`` / ``hp:pageBorderFill`` before the table), text or another
  table: the ops touch only the table there,
- a table with a nested table (autofit refuses like the other structure edits),
- a row whose right-hand column is covered by a cell merged down from above,
- deleting the top row of a vertical merge.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.table_patch import apply_table_ops
from hwpx.tools.package_validator import validate_package


def _fill(table, rows: int, cols: int) -> None:
    for row in range(rows):
        for col in range(cols):
            table.cell(row, col).text = f"r{row}c{col}"


def _first_paragraph_table(rows: int = 4, cols: int = 2) -> bytes:
    """A table in the section's first paragraph, after its ``hp:secPr``."""
    doc = HwpxDocument.new()
    _fill(doc.paragraphs[0].add_table(rows, cols), rows, cols)
    doc.add_paragraph("after the table")
    return doc.to_bytes()


def _reopen(result) -> HwpxDocument:
    assert not result.skipped, [skip.reason for skip in result.skipped]
    return HwpxDocument.open(io.BytesIO(result.data))


def _section_xml(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _shapes(document: HwpxDocument) -> list[tuple[int, int, str]]:
    return [(t.row_count, t.column_count, t.cell(0, 0).text) for t in document.tables.all]


def _two_tables_in_one_paragraph(text: str = "intro text") -> bytes:
    """A paragraph with *text*, a 2x2 table A and a 4x2 table B."""
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph(text)
    _fill(paragraph.add_table(2, 2), 2, 2)
    _fill(paragraph.add_table(4, 2), 4, 2)
    return doc.to_bytes()


@pytest.mark.parametrize(
    "op",
    [
        {"op": "delete_table", "table_index": 0},
        {"op": "clone_table", "table_index": 0},
        {"op": "split_table", "table_index": 0, "split_row": 2},
    ],
)
def test_the_section_setup_stays_single_and_in_place(op: dict) -> None:
    result = apply_table_ops(_first_paragraph_table(), [op])

    xml = _section_xml(result.data)
    assert [xml.count(f"<hp:{tag}") for tag in ("secPr", "colPr", "pagePr")] == [1, 1, 1]
    assert validate_package(result.data).ok
    reopened = _reopen(result)
    assert reopened.oxml.sections[0].properties.page_size.width > 0
    assert "after the table" in reopened.text.plain()


def test_deleting_one_of_two_tables_in_a_paragraph_keeps_the_rest() -> None:
    result = apply_table_ops(_two_tables_in_one_paragraph(), [{"op": "delete_table", "table_index": 1}])

    reopened = _reopen(result)
    assert _shapes(reopened) == [(2, 2, "r0c0")]
    assert reopened.text.plain().startswith("intro text")


def test_splitting_the_second_table_of_a_paragraph_leaves_the_first_alone() -> None:
    result = apply_table_ops(
        _two_tables_in_one_paragraph(), [{"op": "split_table", "table_index": 1, "split_row": 2}]
    )

    assert _shapes(_reopen(result)) == [(2, 2, "r0c0"), (2, 2, "r0c0"), (2, 2, "r2c0")]
    assert _section_xml(result.data).count("intro text") == 1


def test_cloning_the_second_table_of_a_paragraph_copies_only_it() -> None:
    result = apply_table_ops(_two_tables_in_one_paragraph(), [{"op": "clone_table", "table_index": 1}])

    assert _shapes(_reopen(result)) == [(2, 2, "r0c0"), (4, 2, "r0c0"), (4, 2, "r0c0")]
    assert _section_xml(result.data).count("intro text") == 1


def test_merging_two_tables_of_one_paragraph_joins_them_once() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    _fill(paragraph.add_table(2, 2), 2, 2)
    _fill(paragraph.add_table(2, 2), 2, 2)

    result = apply_table_ops(doc.to_bytes(), [{"op": "merge_table", "table_index": 0}])

    (merged,) = _reopen(result).tables.all
    assert (merged.row_count, merged.column_count) == (4, 2)


def test_text_between_two_tables_of_one_paragraph_refuses_the_merge() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    _fill(paragraph.add_table(2, 2), 2, 2)
    paragraph.add_run("between")
    _fill(paragraph.add_table(2, 2), 2, 2)
    source = doc.to_bytes()

    result = apply_table_ops(source, [{"op": "merge_table", "table_index": 0}])

    assert [skip.reason for skip in result.skipped] == [
        "merge_table: merge_table: real content (non-empty text) sits between the two tables "
        "-- refusing (would silently discard it)"
    ]
    assert result.data == source


def test_split_table_in_the_section_setup_paragraph() -> None:
    result = apply_table_ops(_first_paragraph_table(), [{"op": "split_table", "table_index": 0, "split_row": 2}])

    tables = _reopen(result).tables.all
    assert [(t.row_count, t.column_count) for t in tables] == [(2, 2), (2, 2)]
    assert tables[1].cell(0, 0).text == "r2c0"


def test_delete_and_clone_table_in_the_section_setup_paragraph() -> None:
    source = _first_paragraph_table()

    deleted = _reopen(apply_table_ops(source, [{"op": "delete_table", "table_index": 0}]))
    cloned = _reopen(apply_table_ops(source, [{"op": "clone_table", "table_index": 0}]))

    assert deleted.tables.all == []
    assert "after the table" in deleted.text.plain()
    assert [t.row_count for t in cloned.tables.all] == [4, 4]


def test_merge_table_after_a_table_in_the_section_setup_paragraph() -> None:
    doc = HwpxDocument.new()
    _fill(doc.paragraphs[0].add_table(2, 2), 2, 2)
    _fill(doc.add_table(3, 2), 3, 2)

    result = apply_table_ops(doc.to_bytes(), [{"op": "merge_table", "table_index": 0}])

    tables = _reopen(result).tables.all
    assert [(t.row_count, t.column_count) for t in tables] == [(5, 2)]


def test_autofit_refuses_a_table_with_a_nested_table() -> None:
    # the nested table is narrower than the outer one
    doc = HwpxDocument.new()
    table = doc.add_table(2, 6)
    _fill(table, 2, 6)
    _fill(table.cell(0, 0).add_table(1, 4), 1, 4)

    result = apply_table_ops(doc.to_bytes(), [{"op": "autofit_columns", "table_index": 0}])

    assert [skip.reason for skip in result.skipped] == [
        "autofit_columns: nested tables are unsupported for structure edits"
    ]


def test_delete_column_when_rows_below_a_merge_miss_the_last_column() -> None:
    # row 0: A1:B1 merged + C1; column C merged down over all three rows, so
    # rows 1 and 2 hold one-column cells for A and B only
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    doc.tables.merge_cells(table, "A1:B1")
    doc.tables.merge_cells(table, "C1:C3")

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_column", "table_index": 0, "col": 2}])

    (after,) = _reopen(result).tables.all
    assert (after.row_count, after.column_count) == (3, 2)
    assert after.cell(1, 1).text == "r1c1"


def test_delete_row_moves_a_vertical_merge_down() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    merged = doc.tables.merge_cells(table, "A1:A2")
    merged.text = "merged"
    height = merged.height

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_row", "table_index": 0, "row": 0}])

    (after,) = _reopen(result).tables.all
    assert (after.row_count, after.column_count) == (2, 3)
    cell = after.cell(0, 0)
    assert cell.text == "merged"
    assert cell.address == (0, 0)
    assert cell.span == (1, 1)
    assert cell.height < height
    assert [after.cell(0, col).text for col in (1, 2)] == ["r1c1", "r1c2"]
    assert [after.cell(1, col).text for col in range(3)] == ["r2c0", "r2c1", "r2c2"]


def test_delete_row_below_the_top_of_a_merge_still_shrinks_it() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    _fill(table, 3, 3)
    doc.tables.merge_cells(table, "A1:A2").text = "merged"

    result = apply_table_ops(doc.to_bytes(), [{"op": "delete_row", "table_index": 0, "row": 1}])

    (after,) = _reopen(result).tables.all
    assert after.row_count == 2
    assert after.cell(0, 0).text == "merged"
    assert after.cell(0, 0).span == (1, 1)
