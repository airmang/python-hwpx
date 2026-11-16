"""Table and cell look, size and flow members added in 7.0 (``hwpx.oxml.table_format`` and
``hwpx.oxml.table_sizes``): vertical and horizontal alignment, sizes, borders and shading, title
rows, page breaking, columns and ranges, cell zones, emptying a cell and copying a table.

Each edit is checked on a new document and on a Hangul-saved one, saved, reopened and validated;
parts the edit does not touch keep their bytes.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import BorderFillInfo, CellMargins, CellZone

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
VMERGE = FIXTURES / "hancom_saved" / "cell_border_vmerge_base.hwpx"
TITLE_ROWS = FIXTURES / "hancom_saved" / "pages_char_table_taller_than_a_page.hwpx"
ZONES = FIXTURES / "m3_gongmun_gold" / "mfds_admin_notice.hwpx"
FLOATING = FIXTURES / "hancom_saved" / "fill_image_left_bottom.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _grid_is_whole(table) -> None:
    """Every grid position resolves to one cell, addresses and counts agree with the rows."""
    entries = list(table.iter_grid())
    assert len(entries) == table.row_count * table.column_count
    assert int(table.element.get("rowCnt")) == len(table.element.findall(HP + "tr"))


# -- vertical alignment of a cell ---------------------------------------------------------------


def test_cell_vertical_alignment_reads_hangul_saved_value_and_writes_each_value() -> None:
    document = HwpxDocument.open(ZONES)
    table = document.tables[0]
    assert table.cell(0, 0).vertical_alignment == "TOP"
    assert {table.cell(r, 0).vertical_alignment for r in range(table.row_count)} <= {"TOP", "CENTER", "BOTTOM"}

    before = document.to_bytes()
    for value in ("CENTER", "BOTTOM", "TOP"):
        table.cell(1, 1).vertical_alignment = value
        assert table.cell(1, 1).vertical_alignment == value
    table.cell(1, 1).vertical_alignment = "BOTTOM"
    reopened = _reopen(document)
    assert reopened.tables[0].cell(1, 1).vertical_alignment == "BOTTOM"
    assert _changed(before, document.to_bytes()) == {table.paragraph.section.part_name}


def test_cell_vertical_alignment_refuses_other_spellings_before_changing_anything() -> None:
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    for bad in ("center", "MIDDLE", None, 1):
        with pytest.raises(HwpxError) as caught:
            cell.vertical_alignment = bad
        assert caught.value.code == "table-cell-vertical-alignment-value"
    assert cell.vertical_alignment == "CENTER"


def test_cell_vertical_alignment_drops_the_cells_line_caches() -> None:
    document = HwpxDocument.open(FIXTURES / "hancom_saved" / "line_cache_table_cells.hwpx")
    table = document.tables[0]
    cell = table.cell(0, 0)
    assert cell.paragraphs[0].element.find(HP + "linesegarray") is not None
    cell.vertical_alignment = "BOTTOM" if cell.vertical_alignment != "BOTTOM" else "TOP"
    assert cell.paragraphs[0].element.find(HP + "linesegarray") is None
    assert table.paragraph.element.find(HP + "linesegarray") is None


# -- horizontal alignment of a table ----------------------------------------------------------


def test_inline_table_alignment_is_its_paragraphs_alignment() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2, width=20000)
    assert table.treat_as_char and table.alignment == "LEFT"
    table.alignment = "CENTER"
    assert table.alignment == "CENTER"
    shape = document.oxml.paragraph_property(table.paragraph.element.get("paraPrIDRef"))
    assert shape.align.horizontal == "CENTER"
    assert table.element.find(HP + "pos").get("horzAlign") == "LEFT"  # inline: position stays
    table.alignment = "RIGHT"
    assert _reopen(document).tables[0].alignment == "RIGHT"


def test_floating_table_alignment_is_its_position_alignment() -> None:
    document = HwpxDocument.open(FLOATING)
    table = document.tables[0]
    assert not table.treat_as_char
    para_pr = table.paragraph.element.get("paraPrIDRef")
    table.alignment = "CENTER"
    assert table.element.find(HP + "pos").get("horzAlign") == "CENTER"
    assert table.paragraph.element.get("paraPrIDRef") == para_pr
    assert _reopen(document).tables[0].alignment == "CENTER"
    with pytest.raises(HwpxError) as caught:
        table.alignment = "JUSTIFY"
    assert caught.value.code == "table-alignment-value"


def test_table_set_position_takes_the_object_placement_vocabulary() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    assert table.text_wrap == "TOP_AND_BOTTOM"
    table.set_position(treat_as_char=False, text_wrap="SQUARE", horizontal_offset=1000, vertical_offset=0,
                       horz_rel_to="PARA", horz_align="RIGHT")
    assert (table.treat_as_char, table.text_wrap, table.alignment) == (False, "SQUARE", "RIGHT")
    _reopen(document)


# -- sizes --------------------------------------------------------------------------------------


def test_column_widths_and_row_heights_read_the_grid_of_a_merged_hangul_table() -> None:
    table = HwpxDocument.open(VMERGE).tables[0]
    assert table.column_widths == (13984, 13984, 13984)
    assert sum(table.column_widths) == table.width
    assert table.row_heights == (282, 282, 282)
    assert [column.width for column in table.columns] == list(table.column_widths)
    assert [row.height for row in table.rows] == list(table.row_heights)


def test_set_column_width_keeps_the_grid_and_widens_the_table_by_the_difference() -> None:
    document = HwpxDocument.open(VMERGE)
    table = document.tables[0]
    before_width = table.width
    table.set_column_width(1, 10000)
    assert table.column_widths == (13984, 10000, 13984)
    assert table.width == before_width - 3984
    _grid_is_whole(table)
    reopened = _reopen(document).tables[0]
    assert reopened.column_widths == (13984, 10000, 13984)
    _grid_is_whole(reopened)


def test_set_column_width_resizes_a_merged_cell_across_the_column() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 3, width=30000)
    merged = table.merge_cells("A1:B1")
    table.columns[1].width = 12000
    assert merged.width == table.column_widths[0] + 12000
    assert table.column_widths[1] == 12000
    _grid_is_whole(_reopen(document).tables[0])


def test_set_column_width_refuses_below_the_column_floor_and_bad_indexes() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    before = document.to_bytes()
    with pytest.raises(HwpxError) as caught:
        table.set_column_width(0, 500)
    assert caught.value.code == "table-column-width-value"
    with pytest.raises(HwpxError) as caught:
        table.set_column_width(5, 5000)
    assert caught.value.code == "table-cell-not-found"
    with pytest.raises(HwpxError):
        table.set_column_width(0, 5000.0)  # type: ignore[arg-type]
    assert document.to_bytes() == before


def test_set_row_height_grows_cells_spanning_the_row() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    merged = table.merge_cells("A1:A2")
    table.rows[1].height = 2000
    assert table.row_heights[1] == 2000
    assert merged.height == table.row_heights[0] + 2000
    assert table.element.find(HP + "sz").get("height") == str(sum(table.row_heights))
    with pytest.raises(HwpxError) as caught:
        table.set_row_height(0, 0)
    assert caught.value.code == "table-row-height-value"
    _reopen(document)


def test_set_width_scales_columns_or_gives_the_last_column_the_difference() -> None:
    document = HwpxDocument.open(VMERGE)
    table = document.tables[0]
    table.set_width(30000)
    assert table.width == 30000 and sum(table.column_widths) == 30000
    assert max(table.column_widths) - min(table.column_widths) <= 1
    table.set_width(36000, proportional=False)
    assert table.width == 36000 and table.column_widths[:2] == (10000, 10000)
    _grid_is_whole(_reopen(document).tables[0])
    with pytest.raises(HwpxError) as caught:
        table.set_width(-1)
    assert caught.value.code == "table-width-value"


def test_set_width_refuses_to_leave_a_nested_table_wider_than_its_cell() -> None:
    document = HwpxDocument.new()
    outer = document.add_table(1, 2, width=40000)
    outer.cell(0, 0).add_table(1, 1, width=18000)
    before = document.to_bytes()
    with pytest.raises(HwpxError):
        outer.set_width(20000)
    assert document.to_bytes() == before


# -- in margins ---------------------------------------------------------------------------------


def test_in_margins_read_and_write_and_cells_without_own_margins_follow() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    assert table.in_margins == CellMargins(510, 510, 141, 141)
    table.cell(0, 0).set_margins(left=100)
    assert table.set_in_margins(left=300, top=200) == CellMargins(300, 510, 200, 141)
    assert table.cell(1, 1).margins == CellMargins(300, 510, 200, 141)
    assert table.cell(0, 0).margins.left == 100
    with pytest.raises(HwpxError) as caught:
        table.set_in_margins(right=-1)
    assert caught.value.code == "table-margin-value"
    assert _reopen(document).tables[0].in_margins.left == 300


# -- borders and shading --------------------------------------------------------------------------


def test_set_borders_outline_only_leaves_inner_lines_and_sets_outside_neighbours() -> None:
    document = HwpxDocument.new()
    table = document.add_table(4, 4)
    table.set_borders("B2:C3", border_width_mm=0.4, color="#FF0000", inner=False)
    inner = table.cell(1, 1).border_fill
    assert isinstance(inner, BorderFillInfo)
    assert (inner.left.width_mm, inner.top.width_mm, inner.right.width_mm, inner.bottom.width_mm) == (0.4, 0.4, 0.12, 0.12)
    assert inner.left.color == "#FF0000"
    assert table.cell(2, 2).border_fill.right.width_mm == 0.4
    # the cell above the range shares its top line; the corner cell does not
    assert table.cell(0, 1).border_fill.bottom.width_mm == 0.4
    assert table.cell(0, 0).border_fill.bottom.width_mm == 0.12
    _reopen(document)


def test_set_borders_keeps_fill_and_other_sides_and_reuses_identical_definitions() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_shading("A1", color="#D9D9D9")
    table.set_borders("A1:B1", sides=("bottom",), line_type="DOUBLE_SLIM", border_width_mm=0.5)
    first = table.cell(0, 0).border_fill
    assert first.fill == "#D9D9D9" and first.bottom.type == "DOUBLE_SLIM" and first.top.type == "SOLID"
    assert table.cell(0, 1).border_fill.fill is None
    count = len(document.oxml.border_fills)
    table.set_borders("A1:B1", sides=("bottom",), line_type="DOUBLE_SLIM", border_width_mm=0.5)
    assert len(document.oxml.border_fills) == count


def test_set_borders_none_line_and_bad_values() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_borders(line_type="NONE")
    assert table.cell(1, 1).border_fill.left.type == "NONE"
    before = document.to_bytes()
    for kwargs in ({"sides": ("middle",)}, {"sides": "left"}, {"color": "red"}, {"line_type": "solid"},
                   {"border_width_mm": "1"}, {"inner": 1}):
        with pytest.raises(HwpxError) as caught:
            table.set_borders(**kwargs)  # type: ignore[arg-type]
        assert caught.value.code == "table-border-value"
    assert document.to_bytes() == before


def test_set_borders_on_a_hangul_saved_merged_table_touches_only_header_and_section() -> None:
    document = HwpxDocument.open(VMERGE)
    before = document.to_bytes()
    table = document.tables[0]
    table.set_borders(border_width_mm=0.5, inner=False)
    for cell in table.cells_in():
        (r0, c0), (_rs, cs) = cell.address, cell.span
        info = cell.border_fill
        if r0 == 0:
            assert info.top.width_mm == 0.5
        if c0 + cs == table.column_count:
            assert info.right.width_mm == 0.5
    assert _changed(before, document.to_bytes()) <= {"Contents/header.xml", "Contents/section0.xml"}
    _reopen(document)


def test_set_shading_and_set_cell_shading_keep_the_cells_lines() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_borders("A1", line_type="DASH", border_width_mm=0.3)
    table.set_cell_shading(0, 0, "#FFFF00")
    info = table.cell(0, 0).border_fill
    assert info.fill == "#FFFF00" and info.left.type == "DASH" and info.left.width_mm == 0.3
    table.set_shading("A1:B2", color=None)
    assert table.cell(0, 0).border_fill.fill is None
    assert table.cell(0, 0).border_fill.left.type == "DASH"
    with pytest.raises(HwpxError) as caught:
        table.set_shading(color="yellow")
    assert caught.value.code == "table-shading-value"


# -- title rows, page splitting --------------------------------------------------------------------


def test_title_rows_read_from_a_hangul_saved_table_and_rewritten() -> None:
    document = HwpxDocument.open(TITLE_ROWS)
    table = document.tables[0]
    assert (table.header_rows, table.repeat_header) == (1, True)
    assert table.cell(0, 0).is_header and not table.cell(1, 0).is_header
    table.set_header_rows(2)
    assert table.header_rows == 2 and table.cell(1, 0).is_header
    table.set_header_rows(0)
    assert (table.header_rows, table.repeat_header) == (0, False)
    table.set_header_rows(1, repeat=False)
    reopened = _reopen(document).tables[0]
    assert (reopened.header_rows, reopened.repeat_header) == (1, False)


def test_set_header_rows_refuses_a_cell_merged_across_its_last_line() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    table.merge_cells("A1:A2")
    before = document.to_bytes()
    with pytest.raises(HwpxError) as caught:
        table.set_header_rows(1)
    assert caught.value.code == "table-header-rows-value"
    with pytest.raises(HwpxError):
        table.set_header_rows(4)
    assert document.to_bytes() == before
    table.set_header_rows(2)
    assert table.header_rows == 2


def test_page_split_and_no_adjust() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    assert (table.page_split, table.no_adjust) == ("CELL", False)
    table.page_split = "NONE"
    table.no_adjust = True
    reopened = _reopen(document).tables[0]
    assert (reopened.page_split, reopened.no_adjust) == ("NONE", True)
    with pytest.raises(HwpxError) as caught:
        table.page_split = "cell"
    assert caught.value.code == "table-page-split-value"


# -- rows, columns, ranges, zones ---------------------------------------------------------------


def test_rows_and_columns_hold_each_cell_once() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    table.merge_cells("A2:B3")
    by_rows = [cell.address for row in table.rows for cell in row.cells]
    by_columns = [cell.address for column in table.columns for cell in column.cells]
    assert sorted(by_rows) == sorted(by_columns)
    assert len(by_rows) == len(set(by_rows)) == 6
    assert [row.index for row in table.rows] == [0, 1, 2]
    assert [column.index for column in table.columns] == [0, 1, 2]
    assert [cell.address for cell in table.columns[0].cells] == [(0, 0), (1, 0)]


def test_cells_in_grows_to_cover_merged_cells() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    table.merge_cells("A2:B3")
    assert [cell.address for cell in table.cells_in("B2")] == [(1, 0)]
    assert [cell.address for cell in table.cells_in("A1:C1")] == [(0, 0), (0, 1), (0, 2)]
    assert len(table.cells_in()) == 6
    with pytest.raises(HwpxError):
        table.cells_in("D9")


def test_cell_zones_read_from_a_hangul_saved_table() -> None:
    table = HwpxDocument.open(ZONES).tables[0]
    assert table.cell_zones == (CellZone(4, 0, 8, 3, "33"),)
    assert table.cell_zones[0].to_dict()["endCol"] == 3
    assert HwpxDocument.new().add_table(1, 1).cell_zones == ()


# -- cell content -----------------------------------------------------------------------------


def test_cell_clear_leaves_one_empty_paragraph_in_the_first_ones_shapes() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_text("one\ntwo", split_paragraphs=True)
    cell.paragraphs[0].element.set("paraPrIDRef", "3")
    cell.add_table(1, 1)
    cell.clear()
    assert len(cell.paragraphs) == 1 and cell.text == "" and cell.tables == ()
    assert cell.paragraphs[0].element.get("paraPrIDRef") == "3"
    _reopen(document)


def test_objects_go_straight_into_a_cell_paragraph() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    first = table.cell(0, 0).paragraphs[0]
    nested = first.add_table(2, 2)
    equation = table.cell(0, 1).paragraphs[0].add_equation("a over b")
    assert len(table.cell(0, 0).paragraphs) == 1 and table.cell(0, 0).tables[0].element is nested.element
    assert equation is not None
    reopened = _reopen(document).tables[0]
    assert len(reopened.cell(0, 0).tables) == 1


# -- copy -------------------------------------------------------------------------------------


def test_copy_after_puts_a_copy_with_fresh_ids_after_the_paragraph() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.cell(0, 0).paragraphs[0].add_form_field("성명")
    table.cell(1, 1).text = "값"
    copy = table.copy_after()
    tables = document.tables.all
    assert len(tables) == 2 and tables[1].element is copy.element
    assert copy.element.get("id") != table.element.get("id")
    old_ids = {node.get("id") for node in table.element.iter(HP + "fieldBegin")}
    new_ids = {node.get("id") for node in copy.element.iter(HP + "fieldBegin")}
    assert old_ids and new_ids and not old_ids & new_ids
    paragraph_ids = [p.get("id") for p in document.oxml.sections[0].element.iter(HP + "p")]
    assert len(paragraph_ids) == len(set(paragraph_ids))
    assert copy.cell(1, 1).text == "값"
    assert len(_reopen(document).tables) == 2


def test_copy_after_into_a_cell_and_by_index() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("앞")
    table = document.add_table(1, 1)
    host = document.add_table(1, 1)
    copy = table.copy_after(host.cell(0, 0).paragraphs[0])
    assert host.cell(0, 0).tables[0].element is copy.element
    table.copy_after(0)
    assert len(document.tables.all) == 3
    with pytest.raises(HwpxError):
        table.copy_after(999)
    _reopen(document)
