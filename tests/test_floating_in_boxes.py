"""A floating object made with the default placement in a table cell, a text box, a note or a header is
placed as Hancom places one there: measured from its paragraph and kept in its area.

The body's default (``vertRelTo="PARA"``, ``horzRelTo="COLUMN"``, ``flowWithText="0"``) put a picture made
in a cell outside the table in Hancom, at the body's top left, with the table pushed aside.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.oxml.shape_position import _stays_in_box, fit_new_floating_object, paragraph_box


def new_object_box(paragraph) -> str:
    return paragraph_box(paragraph.element, paragraph.section.element)

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)
IN_A_BOX = {"vertRelTo": "PARA", "horzRelTo": "PARA", "flowWithText": "1", "allowOverlap": "0"}
BODY_DEFAULT = {"vertRelTo": "PARA", "horzRelTo": "COLUMN", "flowWithText": "0", "allowOverlap": "1"}


def _frames(obj) -> dict[str, str]:
    position = obj.element.find(f"{HP}pos")
    return {name: position.get(name) for name in IN_A_BOX}


def _makers(doc: HwpxDocument):
    item = str(doc.media.add_image(PNG, "png"))
    return {
        "picture": lambda p: p.add_picture(item, width=4000, height=2000, treat_as_char=False),
        "rectangle": lambda p: p.add_rectangle(3000, 1500, treat_as_char=False),
        "ellipse": lambda p: p.add_ellipse(3000, 1500, treat_as_char=False),
        "line": lambda p: p.add_line(0, 0, 3000, 0, treat_as_char=False),
        "polygon": lambda p: p.add_polygon([(0, 0), (2000, 0), (1000, 1500)], treat_as_char=False),
        "arc": lambda p: p.add_arc(2000, 2000, treat_as_char=False),
        "curve": lambda p: p.add_curve([(0, 0), (1000, 800), (2000, 0)], treat_as_char=False),
        "text box": lambda p: _text_box(p),
    }


def _text_box(paragraph):
    box = paragraph.add_rectangle(5000, 2000, treat_as_char=False)
    box.set_draw_text("글상자")
    return box


def _boxes(doc: HwpxDocument):
    table = doc.add_table(1, 1)
    outer = doc.add_paragraph("").add_rectangle(16000, 6000)
    note = doc.add_paragraph("각주가 달린 문단").add_footnote("각주")
    header = doc.page.set_header(text="머리말")
    return {
        "cell": table.cell(0, 0).paragraphs[0],
        "text_box": outer.set_draw_text("바깥 글상자").paragraphs[0],
        "note": note.paragraphs[0],
        "header_footer": header.paragraphs[0],
    }


@pytest.mark.parametrize("box", ["cell", "text_box", "note", "header_footer"])
def test_each_floating_kind_made_in_a_box_is_kept_in_it(box: str) -> None:
    doc = HwpxDocument.new()
    paragraph = _boxes(doc)[box]
    assert new_object_box(paragraph) == box
    for kind, make in _makers(doc).items():
        obj = make(paragraph)
        assert _frames(obj) == IN_A_BOX, kind
        assert obj.position.treat_as_char is False
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues


def test_the_body_keeps_its_default_and_a_character_object_is_left_alone() -> None:
    doc = HwpxDocument.new()
    body = doc.add_paragraph("")
    assert new_object_box(body) == "body"
    assert _frames(body.add_rectangle(3000, 1500, treat_as_char=False)) == BODY_DEFAULT
    cell = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    inline = cell.add_rectangle(3000, 1500)
    assert inline.position.treat_as_char is True
    assert inline.element.find(f"{HP}pos").get("horzRelTo") == "COLUMN"


def test_a_picture_placed_by_its_caller_keeps_that_placement() -> None:
    doc = HwpxDocument.new()
    item = str(doc.media.add_image(PNG, "png"))
    cell = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    picture = cell.add_picture(item, width=4000, height=2000, treat_as_char=False,
                               pos_overrides={"vertRelTo": "PAPER", "horzRelTo": "PAPER", "horzOffset": 1000})
    position = picture.element.find(f"{HP}pos")
    assert (position.get("vertRelTo"), position.get("horzRelTo"), position.get("flowWithText")) == (
        "PAPER", "PAPER", "0")


def test_a_connector_between_shapes_in_a_cell_keeps_their_frames() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    first = cell.add_rectangle(2000, 1000, treat_as_char=False)
    second = cell.add_rectangle(2000, 1000, treat_as_char=False)
    second.set_position(horizontal_offset=4000)
    connector = cell.add_connector(first, second)
    position = connector.element.find(f"{HP}pos")
    assert (position.get("horzRelTo"), position.get("vertRelTo")) == ("PARA", "PARA")
    assert position.get("flowWithText") == "1"
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues


def test_a_picture_added_to_a_cell_of_a_hancom_document_is_placed_in_the_cell() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_table_cell_picture_first.hwpx")
    before = {name: data for name, data in _parts(doc.to_bytes()).items() if name != "Contents/section0.xml"}
    table = next(o for s in doc.sections for p in s.paragraphs for o in p.objects if o.element.tag == f"{HP}tbl")
    item = str(doc.media.add_image(PNG, "png"))
    cell = table.cell(0, 0).paragraphs[0]
    picture = cell.add_picture(item, width=3000, height=1500, treat_as_char=False)
    assert _frames(picture) == IN_A_BOX
    after = _parts(doc.to_bytes())
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues
    changed = {name for name, data in before.items() if after.get(name) != data}
    assert changed <= {"Contents/content.hpf", "Contents/header.xml"}  # the new image's entries


def test_the_placement_satisfies_the_rule_moving_into_a_box_checks() -> None:
    # Moving or copying an object into a cell, text box or note asks for this (exec7/move):
    # measured down from its paragraph and kept in the page area.
    doc = HwpxDocument.new()
    shape = _boxes(doc)["cell"].add_rectangle(3000, 1500, treat_as_char=False)
    position = shape.element.find(f"{HP}pos")
    assert position.get("vertRelTo") == "PARA" and position.get("flowWithText") == "1"
    assert _stays_in_box(shape.element)
    fit_new_floating_object(shape.element, shape.paragraph)  # a second fit changes nothing
    assert _frames(shape) == IN_A_BOX
    # and it can be moved into another cell without being refused
    other = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    shape.move_to(other)
    assert shape.paragraph.element is other.element


def _parts(data: bytes) -> dict[str, bytes]:
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}
