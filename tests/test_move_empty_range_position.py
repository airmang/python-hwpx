"""An empty range moved within its paragraph answers the place it would land, as every other range edit
does (exec7/rv-ranges)."""
from __future__ import annotations

from hwpx import HwpxDocument


def test_an_empty_range_answers_where_it_lands() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("abcd")
    other = document.add_paragraph("xy")
    assert paragraph.move_range(1, 1, to=paragraph, offset=4) == (4, 4)
    assert paragraph.copy_range(1, 1, to=paragraph, offset=4) == (4, 4)
    assert paragraph.move_range(1, 1, to=other, offset=2) == (2, 2)
    assert paragraph.move_range(1, 3, to=paragraph, offset=3) == (1, 3)
    assert paragraph.text == "abcd"
