"""Cell fields -- named table cells (``hp:tc@name``) -- read and filled through ``doc.fields``.

Filling follows Hancom's PutFieldText: a name fills every cell field with that name, and an
index (Hancom's ``name{{n}}``) fills one of them, counted in document order.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

FIXTURES = Path(__file__).parent / "fixtures"


def _form() -> HwpxDocument:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).field_name = "이름"
    table.cell(1, 0).field_name = "이름"
    table.cell(0, 1).field_name = "학년"
    table.cell(0, 0).text = "첫째"
    table.cell(1, 0).text = "둘째"
    return document


def _cell_with_a_table(text: str = "바깥"):
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    if text:
        cell.text = text
    inner = cell.paragraphs[0].add_table(1, 2)
    inner.cell(0, 0).text = "안쪽1"
    inner.cell(0, 1).text = "안쪽2"
    cell.field_name = "바깥칸"
    return document, cell, inner


def test_filling_a_cell_keeps_the_text_of_a_table_inside_it() -> None:
    document, cell, inner = _cell_with_a_table()

    document.fields.fill_cell("새 값", name="바깥칸")

    assert cell.text == "새 값"
    assert (inner.cell(0, 0).text, inner.cell(0, 1).text) == ("안쪽1", "안쪽2")


def test_a_cell_field_inside_a_filled_cell_keeps_its_value() -> None:
    document, _cell, inner = _cell_with_a_table()
    inner.cell(0, 1).field_name = "안칸"

    document.fields.fill_cell("새 값", name="바깥칸")

    assert [(field.name, field.text) for field in document.fields.cells] == [("바깥칸", "새 값"), ("안칸", "안쪽2")]


def test_a_cell_holding_only_a_table_gets_its_text_in_front_of_it() -> None:
    document, cell, inner = _cell_with_a_table(text="")

    document.fields.fill_cell("새 값", name="바깥칸")

    assert cell.text == "새 값"
    assert len(cell.paragraphs) == 1 and len(cell.paragraphs[0].tables) == 1
    assert (inner.cell(0, 0).text, inner.cell(0, 1).text) == ("안쪽1", "안쪽2")
    reopened = HwpxDocument.open(io.BytesIO(document.to_bytes()))
    assert [field.text for field in reopened.fields.cells] == ["새 값"]


def test_named_cells_are_listed_in_document_order() -> None:
    document = _form()

    fields = document.fields.cells

    assert [(field.name, field.text) for field in fields] == [("이름", "첫째"), ("학년", ""), ("이름", "둘째")]
    assert [field.cell.address for field in fields] == [(0, 0), (0, 1), (1, 0)]


def test_a_name_fills_every_cell_field_with_that_name() -> None:
    document = _form()

    filled = document.fields.fill_cell("홍길동", name="이름")

    assert [field.cell.address for field in filled] == [(0, 0), (1, 0)]
    assert [field.text for field in document.fields.cells] == ["홍길동", "", "홍길동"]


def test_an_index_fills_one_cell_field() -> None:
    document = _form()

    filled = document.fields.fill_cell("둘째 값", name="이름", index=1)

    assert [field.cell.address for field in filled] == [(1, 0)]
    assert [field.text for field in document.fields.cells] == ["첫째", "", "둘째 값"]


@pytest.mark.parametrize("name, index", [("없는 이름", None), ("이름", 2), ("이름", -1), ("", None)])
def test_a_missing_cell_field_is_a_typed_error(name: str, index: int | None) -> None:
    document = _form()

    with pytest.raises(HwpxValueError) as caught:
        document.fields.fill_cell("값", name=name, index=index)

    assert caught.value.code == "field-cell-not-found"
    assert isinstance(caught.value, ValueError)


def test_click_here_fields_with_the_same_name_are_left_alone() -> None:
    document = _form()
    document.fields.add("이름", prompt="누름틀", paragraph=document.add_paragraph("누름틀: "))
    document.fields.fill("누름틀 값", name="이름")

    document.fields.fill_cell("홍길동", name="이름")

    assert [field.value for field in document.fields.all] == ["누름틀 값"]


def test_cells_inside_a_cell_are_found_after_their_outer_cell() -> None:
    document = HwpxDocument.new()
    outer = document.add_table(rows=1, cols=2)
    outer.cell(0, 0).field_name = "바깥"
    inner = outer.cell(0, 0).paragraphs[0].add_table(1, 1)
    inner.cell(0, 0).field_name = "안"
    outer.cell(0, 1).field_name = "옆"

    assert [field.name for field in document.fields.cells] == ["바깥", "안", "옆"]


def test_a_cell_field_name_is_saved_as_the_cell_name_and_can_be_cleared() -> None:
    document = _form()
    document.fields.fill_cell("홍길동", name="이름", index=0)

    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    assert len(re.findall(r'<hp:tc\b[^>]*\bname="이름"', xml)) == 2

    reopened = HwpxDocument.open(document.to_bytes())
    assert [(field.name, field.text) for field in reopened.fields.cells][0] == ("이름", "홍길동")
    reopened.fields.cells[1].cell.field_name = None
    assert [field.name for field in reopened.fields.cells] == ["이름", "이름"]


def test_cell_fields_in_a_hancom_document() -> None:
    document = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / "tool__textextractor__Table.hwpx")

    names = [field.name for field in document.fields.cells]

    assert {"name", "kor", "eng", "math"} <= set(names)
    first = next(field for field in document.fields.cells if field.name == "kor")
    document.fields.fill_cell("100", name="kor", index=0)
    assert first.text == "100"
