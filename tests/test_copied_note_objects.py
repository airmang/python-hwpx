"""An object in a copied footnote's text gets its own id and goes over the others, as a copied object does
(exec7/rv-ranges). Hancom writes note paragraphs with id 0 (all 138 of tests/fixtures/hancom_saved), so
those stay."""
from __future__ import annotations

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_a_copied_note_holds_objects_of_their_own() -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("ab")
    second = document.add_paragraph("12")
    note = document.notes.add_footnote("f", paragraph=first, offset=1)
    note.body_paragraph.add_rectangle(width=1000, height=1000)
    note.copy_to(second, offset=1)
    again = HwpxDocument.open(document.to_bytes())
    rects = [node for p in again.paragraphs for node in p.element.iter(f"{_HP}rect")]
    assert len(rects) == 2
    assert len({r.get("id") for r in rects}) == 2
    assert len({r.get("zOrder") for r in rects}) == 2
