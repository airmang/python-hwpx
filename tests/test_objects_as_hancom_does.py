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


# -- resizing groups and equations (o03 psizegrp, psizegrpturn, psizeeq) ------------------------------

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _o03_group(doc):
    from hwpx.oxml.container import ContainerMember

    group = doc.shapes.add_container([ContainerMember.rect(0, 0, 8000, 5000), ContainerMember.ellipse(9000, 0, 6000, 5000)],
                                     treat_as_char=False, paragraph=doc.add_paragraph("묶음"))
    group.set_position(vertical_relative_to="PARA", horizontal_relative_to="COLUMN", horizontal_offset=2000,
                       vertical_offset=1000)
    return group


def _scale(node):
    matrix = node.find(f"{HP}renderingInfo/{HC}scaMatrix")
    return [float(matrix.get(key)) for key in ("e1", "e2", "e3", "e4", "e5", "e6")]


def _box(node, tag):
    child = node.find(f"{HP}{tag}")
    return int(child.get("width")), int(child.get("height"))


def test_a_group_resized_is_stretched_with_its_members_as_hancom_does() -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)

    group.resize(24000, 9000)

    rect, ellipse = (child for child in group.element if child.find(f"{HP}renderingInfo") is not None)
    assert _box(group.element, "sz") == _box(group.element, "curSz") == (24000, 9000)
    assert _scale(group.element) == pytest.approx([1.6, 0, 0, 0, 1.8, 0])
    assert _scale(rect) == pytest.approx([1.6, 0, 0, 0, 1.8, 0])
    assert _scale(ellipse) == pytest.approx([1.6, 0, 5400, 0, 1.8, 0])
    assert (_box(rect, "curSz"), _box(ellipse, "curSz")) == ((12800, 9000), (9600, 9000))
    _reopen(doc)


def test_a_turned_group_resized_is_stretched_along_the_page_as_hancom_does() -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    group.rotation = 30
    assert _box(group.element, "sz") == (15490, 11830)

    group.resize(24000, 9000)

    rect, ellipse = (child for child in group.element if child.find(f"{HP}renderingInfo") is not None)
    linear = [1.352234, -0.341478, None, -0.341478, 0.95793, None]
    for node, move in ((group.element, (1189.375643, -686.669403)), (rect, (1189.375643, -686.669403)),
                       (ellipse, (4359.484423, -3759.969611))):
        expected = [move[0] if value is None and index == 2 else move[1] if value is None else value
                    for index, value in enumerate(linear)]
        assert _scale(node) == pytest.approx(expected, abs=0.02)
    assert _box(group.element, "sz") == (24000, 9000)
    assert _box(group.element, "curSz") == (20283, 4789)
    assert (_box(rect, "curSz"), _box(ellipse, "curSz")) == ((10817, 4789), (8113, 4789))
    assert group.rotation == 30
    _reopen(doc)


def test_a_stretched_turned_group_is_not_resized() -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    group.rotation = 30
    group.resize(24000, 9000)
    with pytest.raises(HwpxValueError) as excinfo:
        group.resize(20000, 9000)
    assert excinfo.value.code == "shape-rotation-unsupported"


def test_an_equation_is_not_resized_because_hancom_measures_it_again() -> None:
    doc = HwpxDocument.new()
    equation = doc.add_paragraph("").add_equation("x+y")
    before = doc.to_bytes()
    with pytest.raises(HwpxValueError) as excinfo:
        equation.resize(20000, 8000)
    assert excinfo.value.code == "shape-equation-resize-unsupported"
    assert doc.to_bytes() == before


def test_a_member_is_not_resized_alone() -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    with pytest.raises(HwpxValueError) as excinfo:
        group.members[0].resize(100, 100)
    assert excinfo.value.code == "shape-group-member-unsupported"
