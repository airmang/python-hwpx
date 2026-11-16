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


def test_cells_take_the_placements_hancom_gives_there() -> None:
    # cl0, cl2, cl5, cl1d and recellpage2 / recellcol0 / cl1s opened again in Hancom 2024.
    doc = HwpxDocument.new()
    kept = _picture(doc, doc.add_paragraph("a"), "PARA", "COLUMN", "1", "1")
    paper = _picture(doc, doc.add_paragraph("b"), "PAPER", "PAPER", "1", "1")
    low = _picture(doc, doc.add_paragraph("c"), "PARA", "PARA", "0", "1")
    cell = doc.add_paragraph("").add_table(1, 1).cell(0, 0).paragraphs[0]

    assert _pos(kept.copy_to(cell).element) == _pos(kept.element)
    assert _pos(paper.copy_to(cell).element)["horzRelTo"] == "COLUMN"
    assert _pos(low.copy_to(cell).element) == {  # cl1d
        "vertRelTo": "PARA", "horzRelTo": "PARA", "vertOffset": "0", "horzOffset": "5000", "flowWithText": "1",
        "allowOverlap": "0"}
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
    # Hancom keeps the rotation centres where they were (the group's own size over two, 7500x2500), its
    # resave of the engine's resized group too (objlim psizegrp, kresize).
    centres = [(node.find(f"{HP}rotationInfo").get("centerX"), node.find(f"{HP}rotationInfo").get("centerY"))
               for node in (group.element, rect, ellipse)]
    assert centres == [("7500", "2500"), ("4000", "2500"), ("3000", "2500")]
    _reopen(doc)


def _stretched_by_hancom(doc):
    """A group turned 30 degrees whose box Hancom's object properties stretched to 24000 x 9000 (psizegrpturn): the
    skewed form written by the internal ``resize_turned_group``, as ``resize`` does not write it."""

    from hwpx.oxml.shape_position import resize_turned_group

    group = _o03_group(doc)
    group.rotation = 30
    resize_turned_group(group, 24000, 9000)
    return group


def test_hancoms_stretch_of_a_turned_groups_box_is_the_skewed_form_it_saved() -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    group.rotation = 30
    assert _box(group.element, "sz") == (15490, 11830)
    group = _stretched_by_hancom(doc)

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


def test_a_turned_group_resized_takes_its_own_size_as_one_resized_and_then_turned() -> None:
    doc = HwpxDocument.new()
    turned_first, resized_first = _o03_group(doc), _o03_group(doc)
    turned_first.rotation = 30
    turned_first.resize(24000, 9000)
    resized_first.resize(24000, 9000)
    resized_first.rotation = 30
    rendering = [node.find(f"{HP}renderingInfo") for node in (turned_first.element, resized_first.element)]
    assert [[m.attrib for m in r] for r in rendering[:1]] == [[m.attrib for m in r] for r in rendering[1:]]
    assert _box(turned_first.element, "sz") == _box(resized_first.element, "sz")
    assert _scale(turned_first.element) == pytest.approx([1.6, 0, 0, 0, 1.8, 0])  # not skewed
    _reopen(doc)


def test_a_stretched_turned_group_is_not_resized() -> None:
    doc = HwpxDocument.new()
    group = _stretched_by_hancom(doc)
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


# -- ungrouping (o02 ungroup2/ungroup3, o03 ungroupstretch/ungroupstretch2/ungroupturned2/ungroupturned90) -----


def _signed(value: str) -> int:
    number = int(value)
    return number - 2**32 if number >= 2**31 else number


def _freed(shape):
    element = shape.element
    position = element.find(f"{HP}pos")
    trans = element.find(f"{HP}renderingInfo/{HC}transMatrix")
    turn = element.find(f"{HP}rotationInfo")
    return {
        "tag": element.tag.rsplit("}", 1)[-1],
        "pos": (_signed(position.get("horzOffset")), _signed(position.get("vertOffset"))),
        "sz": _box(element, "sz"), "curSz": _box(element, "curSz"),
        "trans": (round(float(trans.get("e3"))), round(float(trans.get("e6")))),
        "turn": (turn.get("angle"), turn.get("centerX"), turn.get("centerY")),
    }


UNGROUPED = {
    # The group (rectangle 8000x5000 + ellipse 6000x5000 at 9000) floats at (2000, 1000). Hancom hangs a
    # member on the paragraph where it starts; the positions below are measured from the group's paragraph
    # (Hancom's offset plus that paragraph's line position). A turned group was moved by its turn so its centre
    # stays on the page (rotate9), Hancom's and python-hwpx's alike: its members start from its moved place.
    "plain": [  # ungroup2
        {"tag": "ellipse", "pos": (11000, 1000), "sz": (6000, 5000), "curSz": (0, 0), "trans": (0, 0),
         "turn": ("0", "3000", "2500")},
        {"tag": "rect", "pos": (2000, 1000), "sz": (8000, 5000), "curSz": (0, 0), "trans": (0, 0),
         "turn": ("0", "4000", "2500")},
    ],
    "stretched": [  # ungroupstretch, 24000x9000
        {"tag": "ellipse", "pos": (16400, 1000), "sz": (9600, 9000), "curSz": (9600, 9000), "trans": (-5400, 0),
         "turn": ("0", "4800", "4500")},
        {"tag": "rect", "pos": (2000, 1000), "sz": (12800, 9000), "curSz": (12800, 9000), "trans": (0, 0),
         "turn": ("0", "6400", "4500")},
    ],
    "stretched2": [  # ungroupstretch2, 9000x12000
        {"tag": "ellipse", "pos": (7400, 1000), "sz": (3600, 12000), "curSz": (3600, 12000), "trans": (3600, 0),
         "turn": ("0", "1800", "6000")},
        {"tag": "rect", "pos": (2000, 1000), "sz": (4800, 12000), "curSz": (4800, 12000), "trans": (0, 0),
         "turn": ("0", "2400", "6000")},
    ],
    "turned30": [  # ungroupturned2: ellipse 9549/485 on the paragraph at 1600, group at (1755, -2415)
        {"tag": "rect", "pos": (1755, -2415), "sz": (9428, 8330), "curSz": (0, 0), "trans": (245, 3415),
         "turn": ("30", "4714", "4165")},
        {"tag": "ellipse", "pos": (9549, 1600 + 485), "sz": (7696, 7330), "curSz": (0, 0),
         "trans": (1451, -1085), "turn": ("30", "3848", "3665")},
    ],
    "turned45": [  # ungroupturned45b: rect 2429/-3571 = group's place, ellipse 8793/1193 on the paragraph at 1600
        {"tag": "rect", "pos": (2429, -3571), "sz": (9192, 9192), "curSz": (0, 0), "trans": (-429, 4571),
         "turn": ("45", "4596", "4596")},
        {"tag": "ellipse", "pos": (8793, 1600 + 1193), "sz": (7778, 7778),
         "curSz": (0, 0), "trans": (2207, -1793), "turn": ("45", "3889", "3889")},
    ],
    "turned90": [  # ungroupturned90: ellipse 7000/200 on the paragraph at 4800, group at (7000, -4000)
        {"tag": "rect", "pos": (7000, -4000), "sz": (5000, 8000), "curSz": (0, 0), "trans": (-5000, 5000),
         "turn": ("90", "2500", "4000")},
        {"tag": "ellipse", "pos": (7000, 4800 + 200), "sz": (5000, 6000), "curSz": (0, 0), "trans": (4000, -4000),
         "turn": ("90", "2500", "3000")},
    ],
}


@pytest.mark.parametrize("case", sorted(UNGROUPED))
def test_a_group_is_ungrouped_as_hancom_ungroups_it(case) -> None:
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    paragraph = group.paragraph
    if case == "stretched":
        group.resize(24000, 9000)
    elif case == "stretched2":
        group.resize(9000, 12000)
    elif case == "turned30":
        group.rotation = 30
    elif case == "turned90":
        group.rotation = 90
    elif case == "turned45":
        group.rotation = 45

    freed = group.ungroup()

    by_tag = {item["tag"]: item for item in UNGROUPED[case]}
    assert [shape.element.tag.rsplit("}", 1)[-1] for shape in freed] == ["ellipse", "rect"]  # the last member first
    for shape in freed:
        assert _freed(shape) == by_tag[_freed(shape)["tag"]]
        assert shape.paragraph.element is paragraph.element
        assert shape.element.get("groupLevel") == "0" and shape.element.get("textWrap") == "SQUARE"
    assert [o.element.tag.rsplit("}", 1)[-1] for o in paragraph.objects] == ["ellipse", "rect"]
    _reopen(doc)


def test_what_is_not_ungrouped_is_refused_before_anything_changes() -> None:
    from hwpx.oxml.container import ContainerMember

    doc = HwpxDocument.new()
    inline = doc.shapes.add_container([ContainerMember.rect(0, 0, 100, 100), ContainerMember.rect(200, 0, 100, 100)],
                                      paragraph=doc.add_paragraph(""))
    both_ways = doc.shapes.add_container([ContainerMember.rect(0, 0, 100, 100), ContainerMember.rect(200, 0, 100, 100)],
                                         treat_as_char=False, paragraph=doc.add_paragraph(""))
    both_ways.flip_horizontal = True
    both_ways.flip_vertical = True
    rectangle = doc.add_paragraph("").add_rectangle(100, 100)
    before = doc.to_bytes()
    for shape, says in ((inline, "character"), (both_ways, "both ways"), (rectangle, "not a group")):
        with pytest.raises(HwpxValueError) as excinfo:
            shape.ungroup()
        assert excinfo.value.code == "shape-ungroup-unsupported" and says in excinfo.value.context["reason"]
    assert doc.to_bytes() == before


def test_removing_a_groups_only_member_removes_the_group() -> None:
    from hwpx.oxml.container import ContainerMember

    doc = HwpxDocument.new()
    group = doc.shapes.add_container(
        [ContainerMember.rect(0, 0, 100, 100),
         ContainerMember.group(200, 0, [ContainerMember.rect(0, 0, 50, 50)])],
        treat_as_char=False, paragraph=doc.add_paragraph(""))
    inner = group.members[1]
    only = inner.members[0]

    only.remove()

    assert [m.shape_type for m in group.members] == ["rect"]
    _reopen(doc)


# -- copying into another document (o08 xpic/xeq/xchart/xconn, o11 xpic2/xchart2; xbox2 refused) --------


def test_an_object_copied_into_another_document_takes_its_image_and_chart_along() -> None:
    chart = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        '<c:chart><c:plotArea><c:layout/><c:pieChart><c:varyColors val="1"/></c:pieChart></c:plotArea></c:chart>'
        '</c:chartSpace>'
    )
    source, target = HwpxDocument.new(), HwpxDocument.new()
    picture = source.add_paragraph("").add_picture(str(source.media.add_image(PNG, "png")), width=3000, height=3000)
    source_chart = source.shapes.add_chart(chart, paragraph=source.add_paragraph(""))
    target.add_paragraph("").add_picture(str(target.media.add_image(PNG, "png")), width=3000, height=3000)
    target.shapes.add_chart(chart, paragraph=target.add_paragraph(""))
    place = target.add_paragraph("붙일 자리: ")

    copied = picture.copy_to(place)
    copied_chart = source_chart.copy_to(place)

    assert copied.paragraph.element is place.element
    reference = next(n.get("binaryItemIDRef") for n in copied.element.iter() if n.get("binaryItemIDRef"))
    assert reference not in {next(n.get("binaryItemIDRef") for n in picture.element.iter() if n.get("binaryItemIDRef"))}
    assert copied_chart.element.get("chartIDRef") == "Chart/chart2.xml"
    again = _reopen(target)
    assert len(again.media.images) == 2
    assert len(source.paragraphs[0].objects) == 1  # the original stays


def test_an_object_moved_into_another_document_leaves_the_first() -> None:
    source, target = HwpxDocument.new(), HwpxDocument.new()
    equation = source.add_paragraph("").add_equation("x^2")
    equation.move_to(target.add_paragraph(""))
    assert source.shapes.equations == ()
    assert [e.script for e in target.shapes.equations] == ["x^2"]
    assert equation.paragraph.section is target.sections[0]
    _reopen(source), _reopen(target)


def test_a_connector_is_not_copied_into_another_document() -> None:
    # Pasted alone into another document a connector lets go of its shapes, and Hancom 2024 draws it nowhere
    # (xconn's page image, and the engine's copy opened in Hancom: objlim-xdoc).
    source, target = HwpxDocument.new(), HwpxDocument.new()
    p = source.add_paragraph("")
    a = p.add_rectangle(5000, 4000, treat_as_char=False)
    b = p.add_rectangle(5000, 4000, treat_as_char=False)
    b.set_position(horizontal_offset=14000)
    connector = p.add_connector(a, b)
    place = target.add_paragraph("")
    before = target.to_bytes()

    with pytest.raises(HwpxValueError) as excinfo:
        connector.copy_to(place)
    assert excinfo.value.code == "shape-copy-document-unsupported"
    assert target.to_bytes() == before


def test_a_text_box_is_not_copied_into_another_document() -> None:
    source, target = HwpxDocument.new(), HwpxDocument.new()
    box = source.add_paragraph("").add_rectangle(9000, 3000)
    box.set_draw_text("글상자")
    with pytest.raises(HwpxValueError) as excinfo:
        box.copy_to(target.add_paragraph(""))
    assert excinfo.value.code == "shape-copy-document-unsupported"


def test_an_equation_or_a_chart_is_not_turned_because_hancom_does_not_turn_one() -> None:
    doc = HwpxDocument.new()
    equation = doc.add_paragraph("").add_equation("x")
    with pytest.raises(HwpxValueError) as excinfo:
        equation.rotation = 30
    assert excinfo.value.code == "shape-rotation-unsupported"
    assert "Hancom does not turn" in excinfo.value.context["reason"]


def test_a_stretched_and_turned_group_is_ungrouped_as_hancom_does() -> None:
    # ungroupturned45: Hancom's dialog stretched the group to 7200x7200 and turned it 45 degrees, then
    # ungrouped it. Its boxes came out a unit apart (7128x7127, 7807x7806): within 1 here.
    doc = HwpxDocument.new()
    group = _o03_group(doc)
    group.resize(7200, 7200)
    group.rotation = 45

    ellipse, rect = group.ungroup()

    for shape, size, cur, trans, centre in ((ellipse, (7128, 7127), (2880, 7200), (7072, 1516), (3564, 3563)),
                                            (rect, (7807, 7806), (3840, 7200), (1127, 4571), (3903, 3903))):
        got = _freed(shape)
        assert all(abs(a - b) <= 1 for a, b in zip(got["sz"], size))
        assert got["curSz"] == cur and got["trans"] == trans
        assert all(abs(int(a) - b) <= 1 for a, b in zip(got["turn"][1:], centre)) and got["turn"][0] == "45"
    assert _freed(ellipse)["pos"][0] - _freed(rect)["pos"][0] == 3928 - 873


def test_a_group_turned_and_then_stretched_is_not_ungrouped() -> None:
    doc = HwpxDocument.new()
    group = _stretched_by_hancom(doc)
    with pytest.raises(HwpxValueError) as excinfo:
        group.ungroup()
    assert excinfo.value.code == "shape-ungroup-unsupported" and "skewed" in excinfo.value.context["reason"]
