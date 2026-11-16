# SPDX-License-Identifier: Apache-2.0
"""Objects edited the way Hancom 2024 edits them: pasting into boxes, resizing, ungrouping, copying
between documents. Every expected value below was read from a document Hancom 2024 saved after doing the
same thing through its public automation API (objlim evidence, ``out/exec7/objlim/hancom*``: synthetic
documents with generic text only; the file name of each is in the test)."""

from __future__ import annotations

import io

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.namespaces import HP

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(io.BytesIO(doc.to_bytes()))
    again.validate()
    return again


def _pos(element):
    position = element.find(f"{HP}pos")
    return {name: position.get(name) for name in
            ("vertRelTo", "horzRelTo", "vertOffset", "horzOffset", "flowWithText", "allowOverlap")}


def _picture(doc, paragraph, vert, horz, flow, overlap):
    item = doc.media.add_image(PNG, "png")
    picture = paragraph.add_picture(str(item), width=6000, height=4000, treat_as_char=False)
    picture.set_position(vertical_relative_to=vert, horizontal_relative_to=horz, vertical_offset=3000,
                         horizontal_offset=5000)
    position = picture.element.find(f"{HP}pos")
    position.set("flowWithText", flow)
    position.set("allowOverlap", overlap)
    return picture


# -- pasting into a text box, a note, a caption (o10 tb0-tb5, o01) --------------------------------------

PASTED = [
    # (frames before), (what Hancom wrote) -- evidence tb0 .. tb4
    (("PARA", "COLUMN", "1", "1"), ("PARA", "COLUMN", "3000", "5000", "1", "1")),
    (("PARA", "PARA", "0", "1"), ("PARA", "PARA", "0", "5000", "1", "0")),
    (("PAPER", "PAPER", "1", "1"), ("PARA", "COLUMN", "0", "0", "1", "0")),
    (("PAGE", "COLUMN", "1", "1"), ("PARA", "COLUMN", "0", "5000", "1", "0")),
    (("PARA", "PAGE", "1", "1"), ("PARA", "COLUMN", "3000", "0", "1", "1")),
    (("PARA", "COLUMN", "0", "0"), ("PARA", "COLUMN", "0", "5000", "1", "0")),  # tb5 (a rectangle there)
]


@pytest.mark.parametrize("before, after", PASTED)
@pytest.mark.parametrize("box", ["text_box", "note", "caption"])
def test_an_object_pasted_into_a_box_takes_the_placement_hancom_gives_it(box, before, after) -> None:
    doc = HwpxDocument.new()
    picture = _picture(doc, doc.add_paragraph("원본"), *before)
    if box == "text_box":
        holder = doc.add_paragraph("").add_rectangle(30000, 12000)
        target = holder.set_draw_text("글상자 안").paragraphs[0]
    elif box == "note":
        target = doc.add_paragraph("각주").add_footnote("각주 글").paragraphs[0]
    else:
        item = doc.media.add_image(PNG, "png")
        captioned = doc.add_paragraph("").add_picture(str(item), width=3000, height=3000)
        target = captioned.set_caption("캡션 글").paragraphs[0]
    others = max(int(node.get("zOrder")) for node in doc.sections[0].element.iter() if node.get("zOrder"))

    copy = picture.copy_to(target)

    expected = dict(zip(("vertRelTo", "horzRelTo", "vertOffset", "horzOffset", "flowWithText", "allowOverlap"),
                        after))
    assert _pos(copy.element) == expected
    assert int(copy.element.get("zOrder")) == others + 1  # Hancom puts a pasted object over the others
    picture.move_to(target)
    assert _pos(picture.element) == expected
    _reopen(doc)


def test_cells_take_the_placements_hancom_could_open_again_only() -> None:
    # cl0, cl2, cl5 and recellpage2 / recellcol0 opened again; cl1 (PARA/PARA moved to its top) did not.
    doc = HwpxDocument.new()
    kept = _picture(doc, doc.add_paragraph("a"), "PARA", "COLUMN", "1", "1")
    paper = _picture(doc, doc.add_paragraph("b"), "PAPER", "PAPER", "1", "1")
    low = _picture(doc, doc.add_paragraph("c"), "PARA", "PARA", "0", "1")
    cell = doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]

    assert _pos(kept.copy_to(cell).element) == _pos(kept.element)
    assert _pos(paper.copy_to(cell).element)["horzRelTo"] == "COLUMN"
    with pytest.raises(HwpxValueError) as excinfo:
        low.copy_to(cell)
    assert excinfo.value.code == "shape-move-place-unsupported"
    assert "cl1" in excinfo.value.context["reason"]
    _reopen(doc)


def test_an_object_still_does_not_go_into_a_memo_or_a_master_page() -> None:
    doc = HwpxDocument.new()
    picture = _picture(doc, doc.add_paragraph("원본"), "PARA", "COLUMN", "1", "1")
    memo = doc.notes.add_memo("메모 글", paragraph=doc.add_paragraph("메모가 달린 문단"))
    with pytest.raises(HwpxValueError) as excinfo:
        picture.copy_to(memo.paragraphs[0])
    assert excinfo.value.code == "shape-move-place-unsupported"
