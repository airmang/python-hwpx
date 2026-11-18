"""A highlight starting at a tab or line break starts there, not at the character before it, and reads back
with that character (exec7/rv-ranges)."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@pytest.mark.parametrize("atom", ["\t", "\n"])
def test_highlighting_only_a_tab_or_line_break(atom: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph(f"A{atom}B")
    made = document.text.highlight(paragraph, start=1, end=2)
    assert made.text == atom
    text = paragraph.element.find(f".//{_HP}t")
    names = [child.tag.rsplit("}", 1)[-1] for child in text]
    assert text.text == "A" and names[0] == "markpenBegin" and names[-1] == "markpenEnd"
    again = HwpxDocument.open(document.to_bytes())
    assert [h.text for h in again.text.highlights] == [atom]


@pytest.mark.parametrize(("start", "end", "expected"), [(1, 3, "B\t"), (0, 4, "AB\tC"), (2, 4, "\tC")])
def test_a_highlight_holding_a_tab_reads_it(start: int, end: int, expected: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("AB\tC")
    document.text.highlight(paragraph, start=start, end=end)
    again = HwpxDocument.open(document.to_bytes())
    assert [h.text for h in again.text.highlights] == [expected]
