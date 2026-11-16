"""Cells written vertically, protected and editable cells, a table's cell spacing and its own border fill, and
the placement reads tables share with objects (position, z_order, locked, numbering_type)."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import BorderFillInfo, ObjectPosition
from hwpx.oxml.namespaces import HP

FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _tables(doc: HwpxDocument):
    return [o for s in doc.sections for p in s.paragraphs for o in p.objects if o.element.tag == f"{HP}tbl"]


def _has_cache(element) -> bool:
    return element.find(f"{HP}linesegarray") is not None


# -- cells ---------------------------------------------------------------------------------------------


def test_text_direction_reads_hancom_vertical_cells_and_writes_one() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_table_vertical_cells_over_the_page_end.hwpx")
    cells = [cell for table in _tables(doc) for row in table.rows for cell in row.cells]
    assert {cell.text_direction for cell in cells} >= {"VERTICAL"}
    vertical = next(cell for cell in cells if cell.text_direction == "VERTICAL")
    vertical.text_direction = "HORIZONTAL"
    assert vertical.element.find(f"{HP}subList").get("textDirection") == "HORIZONTAL"

    new = HwpxDocument.new()
    table = new.add_table(1, 2)
    table.cell(0, 0).text = "세로로 쓴 칸"
    cell = table.cell(0, 0)
    assert cell.text_direction == "HORIZONTAL"
    cell.text_direction = "VERTICAL"
    again = _reopen(new)
    assert _tables(again)[0].cell(0, 0).text_direction == "VERTICAL"
    assert _tables(again)[0].cell(0, 1).text_direction == "HORIZONTAL"


def test_text_direction_drops_the_cell_and_table_paragraph_caches() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_table_vertical_cells_over_the_page_end.hwpx")
    table = _tables(doc)[0]
    cell = table.cell(0, 0)
    paragraph = cell.paragraphs[0].element
    assert _has_cache(paragraph) and _has_cache(table.paragraph.element)
    cell.text_direction = "HORIZONTAL" if cell.text_direction == "VERTICAL" else "VERTICAL"
    assert not _has_cache(paragraph) and not _has_cache(table.paragraph.element)


@pytest.mark.parametrize("value", ["vertical", "UP", None, 1])
def test_text_direction_refuses_other_values(value) -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    with pytest.raises(HwpxValueError) as caught:
        cell.text_direction = value
    assert caught.value.code == "table-cell-text-direction-value"
    assert cell.element.find(f"{HP}subList").get("textDirection") != "VERTICAL"


def test_protected_and_editable_read_hancom_cells_and_write() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    assert (cell.protected, cell.editable) == (False, False)
    cell.protected = True
    cell.editable = True
    assert (cell.element.get("protect"), cell.element.get("editable")) == ("1", "1")
    again = _tables(_reopen(doc))[0].cell(0, 0)
    assert (again.protected, again.editable) == (True, True)
    for name in ("protected", "editable"):
        with pytest.raises(HwpxValueError) as caught:
            setattr(cell, name, 1)
        assert caught.value.code == "table-cell-flag-value"


# -- cell spacing ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["inline", "cell", "table"])
def test_cell_spacing_grows_the_table_as_hancom_saved_it(kind: str) -> None:
    doc = HwpxDocument.open(HANCOM / f"pages_table_cell_spacing_200_{kind}.hwpx")
    hancom = HwpxDocument.open(HANCOM / f"pages_table_cell_spacing_850_{kind}.hwpx")
    table, wanted = _tables(doc)[0], _tables(hancom)[0]
    assert table.cell_spacing == 200 and wanted.cell_spacing == 850
    before = _parts(doc.to_bytes())
    table.cell_spacing = 850
    size, hancom_size = table.element.find(f"{HP}sz"), wanted.element.find(f"{HP}sz")
    assert (size.get("width"), size.get("height")) == (hancom_size.get("width"), hancom_size.get("height"))
    assert table.column_widths == wanted.column_widths and table.row_heights == wanted.row_heights
    assert not _has_cache(table.paragraph.element)
    after = _parts(_reopen(doc).to_bytes())
    assert {name for name in before if before[name] != after.get(name)} <= {"Contents/section0.xml"}


@pytest.mark.parametrize("value", [-1, 32768, 1.5, True, "200"])
def test_cell_spacing_refuses_other_values(value) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    with pytest.raises(HwpxValueError) as caught:
        table.cell_spacing = value
    assert caught.value.code == "table-cell-spacing-value"
    assert table.cell_spacing == 0


# -- the table's own border fill -------------------------------------------------------------------------


def test_border_fill_of_the_table_reads_and_writes() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    assert isinstance(table.border_fill, BorderFillInfo)
    assert table.border_fill.id == table.border_fill_id_ref
    cell_refs = [cell.border_fill_id_ref for row in table.rows for cell in row.cells]
    frame = doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.7, fill_color="#FFFF00")
    table.border_fill_id_ref = frame
    assert table.border_fill_id_ref == str(frame)
    assert table.border_fill.fill == "#FFFF00"
    assert [cell.border_fill_id_ref for row in table.rows for cell in row.cells] == cell_refs
    again = _tables(_reopen(doc))[0]
    assert again.border_fill_id_ref == str(frame)


@pytest.mark.parametrize("value", ["999", 999, None, True])
def test_border_fill_of_the_table_refuses_an_unknown_id(value) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    before = table.border_fill_id_ref
    with pytest.raises(HwpxValueError) as caught:
        table.border_fill_id_ref = value
    assert caught.value.code == "table-border-fill-not-found"
    assert table.border_fill_id_ref == before


# -- placement reads shared with objects -------------------------------------------------------------------


def test_a_floating_hancom_table_reads_its_place_as_objects_do() -> None:
    doc = HwpxDocument.open(FIXTURES / "exam" / "A_form.hwpx")
    floating = [t for t in _tables(doc) if not t.position.treat_as_char]
    assert floating
    table = floating[0]
    raw = table.element
    position = table.position
    assert isinstance(position, ObjectPosition)
    pos = raw.find(f"{HP}pos")
    assert position.horizontal_offset == int(pos.get("horzOffset"))
    assert position.vertical_offset == int(pos.get("vertOffset"))
    assert position.text_flow == raw.get("textFlow")
    assert table.z_order == int(raw.get("zOrder"))
    assert table.locked is (raw.get("lock") == "1")
    assert table.numbering_type == raw.get("numberingType") == "TABLE"
    assert any(t.locked for t in floating)


def test_tables_and_objects_share_the_placement_reads() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    picture_paragraph = doc.add_paragraph("")
    shape = picture_paragraph.add_rectangle(3000, 1500)
    equation = picture_paragraph.add_equation("x")
    assert (table.locked, shape.locked, equation.locked) == (False, False, False)
    assert (table.numbering_type, shape.numbering_type, equation.numbering_type) == ("TABLE", "NONE", "EQUATION")
    assert type(table).position is type(shape).position  # the same read, not a look-alike
    assert type(table).z_order is type(shape).z_order
