"""Merging cells keeps what the covered cells hold, in reading order."""

from __future__ import annotations

import io
import zipfile

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _texts(cell) -> list[str]:
    return [paragraph.text for paragraph in cell.paragraphs]


def test_covered_cell_text_moves_into_the_merged_cell() -> None:
    table = HwpxDocument.new().add_table(3, 3)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"

    merged = table.merge_cells(0, 0, 0, 1)

    assert _texts(merged) == ["A", "B"]


def test_cells_are_taken_in_reading_order() -> None:
    table = HwpxDocument.new().add_table(3, 3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"

    merged = table.merge_cells("B2:C3")

    assert _texts(merged) == ["r1c1", "r1c2", "r2c1", "r2c2"]
    assert table.cell(0, 0).text == "r0c0"


def test_every_paragraph_of_a_covered_cell_is_kept() -> None:
    table = HwpxDocument.new().add_table(2, 2)
    table.cell(0, 0).set_text("A1\nA2", split_paragraphs=True)
    table.cell(0, 1).set_text("B1\nB2", split_paragraphs=True)

    merged = table.merge_cells(0, 0, 0, 1)

    assert _texts(merged) == ["A1", "A2", "B1", "B2"]


def test_blank_cells_add_no_empty_lines() -> None:
    table = HwpxDocument.new().add_table(2, 3)
    table.cell(0, 1).text = "B"  # blank merged cell, filled covered cell
    table.cell(1, 0).text = "A"  # filled merged cell, blank covered cells

    assert _texts(table.merge_cells(0, 0, 0, 1)) == ["B"]
    assert _texts(table.merge_cells(1, 0, 1, 2)) == ["A"]


def test_merging_blank_cells_leaves_one_empty_line() -> None:
    table = HwpxDocument.new().add_table(2, 2)

    merged = table.merge_cells(0, 0, 1, 1)

    assert _texts(merged) == [""]


def test_a_covered_cell_holding_only_an_object_is_kept() -> None:
    table = HwpxDocument.new().add_table(1, 2)
    table.cell(0, 1).paragraphs[0].add_table(1, 1)

    merged = table.merge_cells(0, 0, 0, 1)

    assert len(merged.paragraphs) == 1
    assert len(merged.paragraphs[0].tables) == 1


def test_line_caches_of_the_merged_cell_are_dropped() -> None:
    table = HwpxDocument.new().add_table(1, 2)
    for col in range(2):
        cell = table.cell(0, col)
        cell.text = f"c{col}"
        for paragraph in cell.paragraphs:
            paragraph.element.append(paragraph.element.makeelement(f"{HP}linesegarray", {}))

    merged = table.merge_cells(0, 0, 0, 1)

    assert [p.element.find(f"{HP}linesegarray") for p in merged.paragraphs] == [None, None]


def test_text_set_after_merging_replaces_the_moved_lines() -> None:
    table = HwpxDocument.new().add_table(3, 3)
    for row in range(3):
        for col in range(3):
            table.cell(row, col).text = f"r{row}c{col}"
    merged = table.merge_cells(0, 0, 1, 0)

    merged.text = "merged"

    assert merged.text == "merged"
    assert _texts(merged) == ["merged"]


def test_setting_text_reads_back_from_a_cell_of_several_lines() -> None:
    table = HwpxDocument.new().add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_text("A1\nA2\nA3", split_paragraphs=True)

    cell.text = "x"

    assert _texts(cell) == ["x"]


def test_setting_text_keeps_blank_lines_and_objects() -> None:
    table = HwpxDocument.new().add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_text("서명\n\n", split_paragraphs=True)
    cell.paragraphs[1].add_table(1, 1)

    cell.text = "홍길동"

    assert len(cell.paragraphs) == 3
    assert cell.paragraphs[0].text == "홍길동"
    assert len(cell.paragraphs[1].tables) == 1
    assert cell.paragraphs[2].text == ""


def _rows(table) -> list[list[tuple[int, int, int, int, int]]]:
    return [
        [(c.address[0], c.address[1], c.span[0], c.span[1], c.height) for c in row.cells]
        for row in table.rows
    ]


def test_merging_whole_rows_leaves_one_row_of_their_height() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(3, 3)
    height = table.cell(0, 0).height

    merged = table.merge_cells("A1:C2")

    assert (table.row_count, table.column_count) == (2, 3)
    assert _rows(table) == [
        [(0, 0, 1, 3, 2 * height)],
        [(1, 0, 1, 1, height), (1, 1, 1, 1, height), (1, 2, 1, 1, height)],
    ]
    assert merged.address == (0, 0)
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert "<hp:tr/>" not in section and "<hp:tr></hp:tr>" not in section


def test_merging_a_whole_table_leaves_one_cell() -> None:
    table = HwpxDocument.new().add_table(2, 2)
    width, height = table.cell(0, 0).width, table.cell(0, 0).height

    merged = table.merge_cells("A1:B2")

    assert (table.row_count, table.column_count) == (1, 1)
    assert (merged.span, merged.width, merged.height) == ((1, 1), 2 * width, 2 * height)


def test_a_merge_inside_the_rows_keeps_the_grid() -> None:
    table = HwpxDocument.new().add_table(3, 3)

    table.merge_cells("A1:B2")

    assert (table.row_count, table.column_count) == (3, 3)
    assert table.cell(1, 2).address == (1, 2)


def test_merged_text_survives_saving() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    table.cell(0, 0).text = "A"
    table.cell(1, 0).text = "B"
    doc.tables.merge_cells(table, "A1:A2")

    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))

    assert reopened.tables.all[0].cell(1, 0).text == "A\nB"
