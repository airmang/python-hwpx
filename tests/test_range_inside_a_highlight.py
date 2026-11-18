"""Part of a highlighted run copied or moved keeps its highlight where it lands, as a range reaching out of
a highlight does (the fragment's highlight is closed at its edges) -- exec7/rv-ranges."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument


@pytest.mark.parametrize(("operation", "left"), [("copy_range", 6), ("move_range", 4)])
def test_the_middle_of_a_highlight_keeps_it_where_it_lands(operation: str, left: int) -> None:
    document = HwpxDocument.new()
    source = document.add_paragraph("abcdef")
    target = document.add_paragraph("12")
    document.text.highlight(source, start=0, end=6)
    getattr(source, operation)(2, 4, to=target, offset=1)
    again = HwpxDocument.open(document.to_bytes())
    found = sorted((h.paragraph.text, h.text) for h in again.text.highlights)
    kept = "abcdef" if operation == "copy_range" else "abef"
    assert found == sorted([(kept, kept[:left]), ("1cd2", "cd")])
