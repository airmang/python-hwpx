"""A range holding footnotes or endnotes, copied or moved, leaves the notes' stored numbers in document order
(1, 2, 3 ...), as moving or copying one note does -- exec7/rv-ranges."""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _stored(document: HwpxDocument, tag: str) -> list[str]:
    return [note.get("number") for section in document.sections for note in section.element.iter(f"{_HP}{tag}")]


@pytest.mark.parametrize("kind", ["footnote", "endnote"])
@pytest.mark.parametrize(("operation", "expected"), [("copy_range", ["1", "2", "3"]), ("move_range", ["1", "2"])])
def test_notes_in_a_range_are_numbered_again(kind: str, operation: str, expected: list[str]) -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("ab")
    second = document.add_paragraph("12")
    add = getattr(document.notes, f"add_{kind}")
    add("f", paragraph=first, offset=1)
    add("g", paragraph=second, offset=1)
    getattr(first, operation)(0, 2, to=second)
    tag = "footNote" if kind == "footnote" else "endNote"
    again = HwpxDocument.open(document.to_bytes())
    assert _stored(again, tag) == expected
