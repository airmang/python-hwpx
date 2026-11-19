"""A range holding a floating table goes into a cell, text box or note as ``table.copy_to``/``move_to`` puts that
table there, or is refused as there (``shape-move-place-unsupported``). Before, the range path wrote the table
into the cell measured from the page, where ``table.copy_to`` refused it."""
from __future__ import annotations

from typing import Any

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

_PLACEMENTS: dict[str, dict[str, Any]] = {
    "as a character": dict(treat_as_char=True),
    "page/page": dict(treat_as_char=False, vertical_relative_to="PAGE", horizontal_relative_to="PAGE"),
    "paper/paper": dict(treat_as_char=False, vertical_relative_to="PAPER", horizontal_relative_to="PAPER"),
    "para/page": dict(treat_as_char=False, vertical_relative_to="PARA", horizontal_relative_to="PAGE"),
    "para/para kept in the area": dict(treat_as_char=False, vertical_relative_to="PARA",
                                       horizontal_relative_to="PARA", flow_with_text=True),
    "para/column not kept": dict(treat_as_char=False, vertical_relative_to="PARA",
                                 horizontal_relative_to="COLUMN", flow_with_text=False),
}


def _document(placement: str) -> tuple[HwpxDocument, Any, Any, Any]:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("ab")
    table = paragraph.add_table(1, 1)
    table.move_to(paragraph, offset=1)
    table.set_position(**_PLACEMENTS[placement])
    target = document.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]
    return document, paragraph, table, target


def _outcome(call: Any) -> str:
    try:
        call()
    except HwpxValueError as refused:
        return refused.code or "?"
    return "ok"


@pytest.mark.parametrize("operation", ["copy_range", "move_range"])
@pytest.mark.parametrize("placement", sorted(_PLACEMENTS))
def test_a_range_puts_a_table_into_a_cell_as_the_table_api_does(placement: str, operation: str) -> None:
    document, _paragraph, table, target = _document(placement)
    direct = _outcome(lambda: table.copy_to(target))

    document, paragraph, table, target = _document(placement)
    before = document.to_bytes()
    ranged = _outcome(lambda: getattr(paragraph, operation)(0, 2, to=target))

    assert ranged == direct
    if ranged != "ok":
        assert ranged == "shape-move-place-unsupported"
        assert document.to_bytes() == before


def test_the_case_from_the_report_is_refused_and_writes_nothing() -> None:
    document, paragraph, _table, target = _document("page/page")
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        paragraph.copy_range(0, 2, to=target)
    assert refused.value.code == "shape-move-place-unsupported"
    assert document.to_bytes() == before
