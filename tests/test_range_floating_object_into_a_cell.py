"""A floating object carried into a table cell by copy_range or move_range is placed as Hancom pastes one
there -- the rule shape.copy_to follows (measured from its paragraph) -- exec7/rv-ranges."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@pytest.mark.parametrize("operation", ["copy_range", "move_range", "shape.copy_to"])
def test_a_page_measured_object_lands_in_a_cell_measured_from_its_paragraph(operation: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("12")
    shape = paragraph.add_rectangle(width=1000, height=1000)
    shape.move_to(paragraph, offset=1)
    shape.set_position(treat_as_char=False, vertical_relative_to="PAGE", horizontal_relative_to="PAGE")
    target = document.add_table(1, 1).cell(0, 0).paragraphs[0]
    if operation == "shape.copy_to":
        shape.copy_to(target)
    else:
        getattr(paragraph, operation)(0, 2, to=target)
    again = HwpxDocument.open(document.to_bytes())
    cell = again.tables[0].cell(0, 0).element
    positions = [pos for rect in cell.iter(f"{_HP}rect") for pos in rect.iter(f"{_HP}pos")]
    assert [(pos.get("vertRelTo"), pos.get("horzRelTo")) for pos in positions] == [("PARA", "COLUMN")]
