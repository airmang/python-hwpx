# SPDX-License-Identifier: Apache-2.0
"""칸 영역(``hp:cellzone``) 만들기·고치기·지우기, and the zones of a Hangul-saved table following
row and column edits made through the object model.

A cell zone is what Hancom saves when a border, a diagonal or a fill is given to several cells "as
one cell": ``hp:cellzoneList`` sits after ``hp:inMargin`` and before the rows, each zone names a
rectangle of cells (``start/endRowAddr``, ``start/endColAddr``) and a border fill of the header.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import CellZone

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
ZONES = Path(__file__).parent / "fixtures" / "m3_gongmun_gold" / "mfds_admin_notice.hwpx"
HANCOM_ZONE = CellZone(4, 0, 8, 3, "33")


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _table():
    document = HwpxDocument.open(ZONES)
    table = document.tables[0]
    assert table.cell_zones == (HANCOM_ZONE,)
    return document, table


# -- making, changing, removing ------------------------------------------------------------------


def test_add_cell_zone_on_a_hangul_saved_table() -> None:
    document, table = _table()
    before = document.to_bytes()
    zone = table.add_cell_zone("A10:B12", border_fill_id_ref="33")
    assert zone == CellZone(9, 0, 11, 1, "33") and table.cell_zones == (HANCOM_ZONE, zone)
    holder = table.element.find(f"{HP}cellzoneList")
    names = [etree.QName(child).localname for child in table.element]
    assert names.index("cellzoneList") == names.index("inMargin") + 1 < names.index("tr")
    assert len(holder) == 2
    assert _reopen(document).tables[0].cell_zones == (HANCOM_ZONE, zone)
    assert _changed_parts(before, document.to_bytes()) == {table.paragraph.section.part_name}


def test_a_zone_is_taken_on_the_grid_as_written() -> None:
    document, table = _table()
    # Hancom's own zone (rows 4-8, columns 0-3) cuts through the merged cell at (4, 1), which runs
    # over columns 1-4: a zone is a rectangle of the grid, not of whole cells.
    merged = next(e for e in table.iter_grid() if e.is_anchor and e.anchor == (4, 1))
    assert merged.span == (1, 4) and HANCOM_ZONE.end_col == 3
    zone = table.add_cell_zone("B6:D8", border_fill_id_ref=1)
    assert (zone.row, zone.col, zone.end_row, zone.end_col) == (5, 1, 7, 3)


def test_a_new_table_gets_its_first_zone_list_before_its_rows() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 3)
    fill = document.styles.ensure_border_fill(fill_color="#FFF2CC")
    zone = table.add_cell_zone("A1:B2", border_fill_id_ref=fill)
    assert zone == CellZone(0, 0, 1, 1, fill)
    names = [etree.QName(child).localname for child in table.element]
    assert names.index("cellzoneList") < names.index("tr")
    assert _reopen(document).tables[0].cell_zones == (zone,)


def test_set_cell_zone_moves_it_and_gives_it_another_border_fill() -> None:
    document, table = _table()
    moved = table.set_cell_zone(0, cell_range="A6:C8")
    assert moved == CellZone(5, 0, 7, 2, "33")
    refilled = table.set_cell_zone(-1, border_fill_id_ref="1")
    assert refilled == CellZone(5, 0, 7, 2, "1")
    before = document.to_bytes()
    table.set_cell_zone(0, border_fill_id_ref="1")  # the same: nothing changes
    assert document.to_bytes() == before
    assert _reopen(document).tables[0].cell_zones == (refilled,)


def test_remove_cell_zone_and_the_list_with_the_last() -> None:
    document, table = _table()
    table.add_cell_zone("A1", border_fill_id_ref="1")
    table.remove_cell_zone(0)
    assert table.cell_zones == (CellZone(0, 0, 0, 0, "1"),)
    table.remove_cell_zone(0)
    assert table.cell_zones == () and table.element.find(f"{HP}cellzoneList") is None
    _reopen(document)


@pytest.mark.parametrize(
    ("call", "code"),
    [
        (lambda t: t.add_cell_zone("A1:B2", border_fill_id_ref="999"), "table-cell-zone-border-fill-unknown"),
        (lambda t: t.add_cell_zone("A1:B2", border_fill_id_ref=True), "table-cell-zone-border-fill-unknown"),
        (lambda t: t.add_cell_zone("A1:Z99", border_fill_id_ref="1"), None),
        (lambda t: t.set_cell_zone(3, border_fill_id_ref="1"), "table-cell-zone-not-found"),
        (lambda t: t.remove_cell_zone(1), "table-cell-zone-not-found"),
        (lambda t: t.set_cell_zone(0, border_fill_id_ref="999"), "table-cell-zone-border-fill-unknown"),
    ],
)
def test_bad_zone_arguments_are_refused_before_anything_changes(call, code) -> None:
    document, table = _table()
    before = document.to_bytes()
    with pytest.raises(HwpxError) as excinfo:
        call(table)
    if code is not None:
        assert excinfo.value.code == code
    assert excinfo.value.suggestion
    assert document.to_bytes() == before


# -- zones follow row and column edits -------------------------------------------------------------


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda t: t.insert_rows(0, 2, side="above"), (6, 0, 10, 3)),     # above the zone: it moves
        (lambda t: t.insert_rows(5, 1), (4, 0, 9, 3)),                   # inside: it grows
        (lambda t: t.insert_rows(4, 1, side="above"), (5, 0, 9, 3)),     # at its top, above: it moves
        (lambda t: t.insert_rows(10, 1), (4, 0, 8, 3)),                  # below it: it stays
        (lambda t: t.delete_rows([0, 1]), (2, 0, 6, 3)),                 # above it: it moves up
        (lambda t: t.delete_rows([5, 6]), (4, 0, 6, 3)),                 # inside: it shrinks
        (lambda t: t.insert_columns(0, 1, side="left"), (4, 1, 8, 4)),   # left of it: it moves
        (lambda t: t.delete_columns([4]), (4, 0, 8, 3)),                 # right of it: it stays
    ],
)
def test_the_hancom_zone_follows_row_and_column_edits(edit, expected) -> None:
    document, table = _table()
    edit(table)
    zone = table.cell_zones[0]
    assert (zone.row, zone.col, zone.end_row, zone.end_col) == expected
    assert zone.border_fill_id_ref == "33"
    assert _reopen(document).tables[0].cell_zones == (zone,)


def test_deleting_every_row_of_a_zone_takes_the_zone_away() -> None:
    document, table = _table()
    table.delete_rows(range(4, 9))
    assert table.cell_zones == () and table.element.find(f"{HP}cellzoneList") is None
    _reopen(document)


def test_zones_follow_column_edits_inside_them_and_merges() -> None:
    document = HwpxDocument.new()
    table = document.add_table(4, 4)
    table.add_cell_zone("B2:C3", border_fill_id_ref=1)
    table.insert_columns(1, 1)  # right of B: the zone runs across it and grows
    assert (table.cell_zones[0].col, table.cell_zones[0].end_col) == (1, 3)
    table.delete_columns([2])
    assert (table.cell_zones[0].col, table.cell_zones[0].end_col) == (1, 2)
    table.merge_cells("A1:A4")  # rows stay (other columns still start cells there)
    assert (table.cell_zones[0].row, table.cell_zones[0].end_row) == (1, 2)
    table.split_cell(1, 1, cols=2)  # B2 into two columns: the zone keeps its x range
    zone = table.cell_zones[0]
    assert (zone.col, zone.end_col) == (1, 3)
    _reopen(document)
