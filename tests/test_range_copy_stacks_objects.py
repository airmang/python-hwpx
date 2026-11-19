"""Objects a range copy brings -- in the range, or in a note or text box it holds -- go over the others, each with a
``zOrder`` of its own, as ``note.copy_to`` and ``shape.copy_to`` stack a copy. Before, the copies kept the
originals' ``zOrder``: the saved document had two objects on one layer."""
from __future__ import annotations

from hwpx import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _objects(document: HwpxDocument) -> list[tuple[str, str]]:
    saved = HwpxDocument.open(document.to_bytes())
    return [(node.get("id"), node.get("zOrder")) for section in saved.oxml.sections for node in section.element.iter()
            if node.tag in (_HP + "rect", _HP + "ellipse")]


def _note_with_two_shapes(copy_with_range: bool) -> HwpxDocument:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("abc")
    target = document.add_paragraph("dd")
    note = paragraph.add_endnote("e", offset=1)
    note.body_paragraph.add_rectangle(300, 400)
    note.body_paragraph.add_ellipse(400, 600)
    if copy_with_range:
        paragraph.copy_range(0, 2, to=target)
    else:
        note.copy_to(target)
    return document


def test_a_note_copied_with_a_range_stacks_its_objects_as_note_copy_to_does() -> None:
    by_range = _objects(_note_with_two_shapes(True))
    by_note = _objects(_note_with_two_shapes(False))
    assert len(by_range) == 4
    assert len({z for _id, z in by_range}) == 4
    assert len({i for i, _z in by_range}) == 4
    assert sorted(z for _id, z in by_range) == sorted(z for _id, z in by_note)


def test_an_object_copied_with_a_range_goes_over_the_others() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("ab")
    paragraph.add_rectangle(300, 300).move_to(paragraph, offset=1)
    document.add_paragraph("x").add_ellipse(300, 300)
    target = document.add_paragraph("y")
    paragraph.copy_range(0, 2, to=target)
    objects = _objects(document)
    assert len({z for _id, z in objects}) == 3
    assert int(objects[-1][1]) == max(int(z) for _id, z in objects)
