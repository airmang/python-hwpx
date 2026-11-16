"""Turning a shape holding text and a whole group, compared with what Hancom 2024 saved after turning them.

``tests/fixtures/hancom_saved/turn_*.hwpx`` (see its README) were made by python-hwpx and turned by Hangul 2024
through its public automation (the object selected, then its turn-by-90-degrees command or its object dialog with
an angle of 30), then saved by Hangul. Two files: a rectangle (0) and a rectangle holding text (1); three objects:
a group of a rectangle and an ellipse (0), a group of a rectangle and a text box (1) and an ellipse holding text
(2). In each file one object is turned and the others are as Hangul saves them unturned, so every object turned
in one file is found unturned in another. Hangul's dialog also drew the ellipse turned by 30 degrees at
7200 x 7200 (its scaMatrix 0.6 x 1.028571, ``curSz`` 7200 x 7199).

What Hangul's turn changes that python-hwpx does not, and is left out of the comparison: ``hp:pos`` offsets (its
commands move the object so its middle stays on the page; ``rotation`` keeps the box's top left corner),
``curSz`` (Hangul saves 0 x 0 for an unstretched object), the text's line layout caches (Hangul lays the text out
again; python-hwpx drops them for Hangul to do so), ids and an empty ``hp:shapeComment``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.container import ContainerMember
from hwpx.oxml.namespaces import HC, HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"

#: (file Hangul turned the object in, object index, angle, a file holding the same object unturned)
TURNED = [
    ("turn_rect_by_90", 0, 90, "turn_text_box_by_90"),
    ("turn_rect_by_30", 0, 30, "turn_text_box_by_30"),
    ("turn_text_box_by_90", 1, 90, "turn_rect_by_90"),
    ("turn_text_box_by_30", 1, 30, "turn_rect_by_30"),
    ("turn_group_by_90", 0, 90, "turn_group_with_text_box_by_90"),
    ("turn_group_by_30", 0, 30, "turn_group_with_text_box_by_30"),
    ("turn_group_with_text_box_by_90", 1, 90, "turn_group_by_90"),
    ("turn_group_with_text_box_by_30", 1, 30, "turn_group_by_30"),
    ("turn_text_ellipse_by_90", 2, 90, "turn_group_by_90"),
]


def _objects(doc: HwpxDocument) -> list:
    return [obj for paragraph in doc.paragraphs for obj in paragraph.objects]


def _local(node) -> str:
    return str(node.tag).rsplit("}", 1)[-1]


def _normalized(element, path: str = "", *, members_centres: bool = True) -> list[str]:
    """*element* as lines to compare. ``members_centres=False`` leaves out the ``rotationInfo`` centres of a
    group's members: Hangul's turn-by-90-degrees command leaves them, its object dialog (which ``rotation``
    follows, ``turn_shapes_group_resized_by_90``) sets them to the middle of each member's turned box."""

    name = _local(element)
    if name in {"curSz", "linesegarray"} or (name == "shapeComment" and not (element.text or "").strip()):
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid"} and not (name == "pos" and key in {"horzOffset", "vertOffset"})}
    if not members_centres and name in {"rotationInfo", "drawText"} and path.count("/") > 1:
        attributes = {key: value for key, value in attributes.items()
                      if key not in {"centerX", "centerY", "lastWidth"}}
    here = f"{path}/{name}"
    lines = [f"{here} {sorted(attributes.items())} {(element.text or '').strip()!r}"]
    for child in element:
        lines += _normalized(child, here, members_centres=members_centres)
    return lines


def _numbers_close(ours: list[str], theirs: list[str], tolerance: float) -> bool:
    """The same lines, numbers within *tolerance*: Hangul writes a turn's rotMatrix moves a few thousandths
    apart when it turns an object turned already (4654.416946 for 4654.4148 from its six-decimal cosine)."""

    if len(ours) != len(theirs):
        return False
    number = re.compile(r"'(-?\d+(?:\.\d+)?)'")
    for a, b in zip(ours, theirs):
        if number.sub("#", a) != number.sub("#", b):
            return False
        if any(abs(float(x) - float(y)) > tolerance for x, y in zip(number.findall(a), number.findall(b))):
            return False
    return True


def _by_instid(doc: HwpxDocument, instid: str):
    """The object with *instid*: Hangul may anchor a turned object in another paragraph."""

    return next(obj for obj in _objects(doc) if obj.element.get("instid") == instid)


#: (file Hangul's object dialog turned the object in, the object's instid, the angle given, a file holding the
#: same object unturned or turned otherwise, a size Hangul's dialog also drew it at). ``turn_shapes_*``: a text
#: box, a group of a rectangle and a text box, a group of a rectangle, a line and a polygon; ``turn_resized_*`` /
#: ``turn_group_in_*``: a group resized to 1.5 times and a group holding a group; ``turn_again_*``: a text box and
#: a group turned 30 degrees (by python-hwpx, read by Hangul's dialog as 30), turned to 45.
DIALOG = [
    ("turn_shapes_text_box_by_330", "1489198821", -30, "turn_shapes_group_with_text_box_by_45", None),
    ("turn_shapes_group_with_text_box_by_45", "944689471", 45, "turn_shapes_text_box_by_330", None),
    ("turn_shapes_group_resized_by_90", "944689471", 90, "turn_shapes_text_box_by_330", (7200, 7200)),
    ("turn_shapes_group_with_line_by_270", "1810697293", 270, "turn_shapes_text_box_by_330", None),
    ("turn_resized_group_by_30", "252925443", 30, "turn_group_in_group_by_30", None),
    ("turn_group_in_group_by_30", "1425497838", 30, "turn_resized_group_by_30", None),
    ("turn_again_text_box_by_45", "1118188575", 45, "turn_again_group_by_45", None),
    ("turn_again_group_by_45", "2002383626", 45, "turn_again_text_box_by_45", None),
]


@pytest.mark.parametrize(("turned", "instid", "angle", "source", "drawn"), DIALOG, ids=[case[0] for case in DIALOG])
def test_turning_writes_what_hancoms_dialog_wrote(turned: str, instid: str, angle: int, source: str,
                                                   drawn: tuple[int, int] | None) -> None:
    doc = HwpxDocument.open(HANCOM / f"{source}.hwpx")
    target = _by_instid(doc, instid)
    if drawn is not None:  # Hangul's dialog also drew the group at this size: resize writes Hangul's resized group
        target.resize(*drawn)
    target.rotation = angle
    hancom = _by_instid(HwpxDocument.open(HANCOM / f"{turned}.hwpx"), instid)
    assert hancom.rotation == angle % 360 == target.rotation
    ours, theirs = _normalized(target.element), _normalized(hancom.element)
    assert ours == theirs if "again" not in turned else _numbers_close(ours, theirs, 0.01)
    again = _reopen(doc)
    assert _by_instid(again, instid).rotation == angle % 360


@pytest.mark.parametrize(("turned", "instid", "angle", "source", "drawn"), DIALOG, ids=[case[0] for case in DIALOG])
def test_hancoms_dialog_turn_turns_back(turned: str, instid: str, angle: int, source: str,
                                        drawn: tuple[int, int] | None) -> None:
    doc = HwpxDocument.open(HANCOM / f"{turned}.hwpx")
    target = _by_instid(doc, instid)
    target.rotation = 0
    original = _by_instid(HwpxDocument.open(HANCOM / f"{source}.hwpx"), instid)
    original.rotation = 0  # a turned-again source is the object turned 30 degrees: back to 0 too
    if drawn is not None:
        # resize keeps the members' centres and text widths; a turn back writes them as drawn, as Hangul saves a
        # resized group's members (turn_group_in_group_by_30 holds one: drawn 9000 wide, centre 4500)
        original.resize(*drawn)
    assert _normalized(target.element, members_centres=drawn is None) == \
        _normalized(original.element, members_centres=drawn is None)


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


@pytest.mark.parametrize(("turned", "index", "angle", "unturned"), TURNED, ids=[case[0] for case in TURNED])
def test_turning_writes_what_hancom_wrote(turned: str, index: int, angle: int, unturned: str) -> None:
    doc = HwpxDocument.open(HANCOM / f"{unturned}.hwpx")
    target = _objects(doc)[index]
    assert target.rotation == 0
    target.rotation = angle
    hancom = _objects(HwpxDocument.open(HANCOM / f"{turned}.hwpx"))[index]
    command = turned.startswith("turn_group") and turned.endswith("_by_90")  # Hangul's turn-by-90 command
    assert _normalized(target.element, members_centres=not command) == \
        _normalized(hancom.element, members_centres=not command)
    again = _reopen(doc)
    assert _objects(again)[index].rotation == angle


@pytest.mark.parametrize(("turned", "index", "angle", "unturned"), TURNED, ids=[case[0] for case in TURNED])
def test_hancoms_turn_reads_and_turns_back(turned: str, index: int, angle: int, unturned: str) -> None:
    doc = HwpxDocument.open(HANCOM / f"{turned}.hwpx")
    objects = _objects(doc)
    assert [obj.rotation for obj in objects] == [angle if i == index else 0 for i in range(len(objects))]
    target = objects[index]
    for member in getattr(target, "members", ()):  # a turned group's members keep angle 0
        assert member.rotation == 0
    target.rotation = 0
    original = _objects(HwpxDocument.open(HANCOM / f"{unturned}.hwpx"))[index]
    assert _normalized(target.element) == _normalized(original.element)


def test_a_stretched_text_ellipse_turns_as_hancom_turned_it() -> None:
    hancom = _objects(HwpxDocument.open(HANCOM / "turn_text_ellipse_stretched_by_30.hwpx"))[2]
    assert hancom.rotation == 30
    doc = HwpxDocument.open(HANCOM / "turn_text_ellipse_by_90.hwpx")
    ellipse = _objects(doc)[2]
    ellipse.rotation = 0
    # drawn at 7200 x 7200 as Hangul's dialog drew it: orgSz and geometry kept, scaMatrix scales
    scale = ellipse.element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    scale.set("e1", "0.6")
    scale.set("e5", "1.028571")
    for name, (width, height) in (("curSz", ("7200", "7199")), ("sz", ("7200", "7200"))):
        ellipse.element.find(f"{HP}{name}").attrib.update({"width": width, "height": height})
    ellipse.rotation = 30
    assert _normalized(ellipse.element) == _normalized(hancom.element)
    draw_text = ellipse.element.find(f"{HP}drawText")
    assert draw_text.get("lastWidth") == "9836" == ellipse.element.find(f"{HP}sz").get("width")


def test_a_turned_text_box_lays_its_text_across_the_turned_box() -> None:
    doc = HwpxDocument.open(HANCOM / "turn_rect_by_30.hwpx")
    box = _objects(doc)[1]
    draw_text = box.element.find(f"{HP}drawText")
    assert draw_text.find(f".//{HP}linesegarray") is not None  # Hangul's layout at 14400 wide
    box.rotation = 30
    assert draw_text.get("lastWidth") == "16070"
    assert draw_text.find(f".//{HP}linesegarray") is None  # laid out again by Hangul at the new width
    box.rotation = 90
    assert draw_text.get("lastWidth") == "7200"
    _reopen(doc)


def test_a_new_text_box_and_group_turn_in_a_table_cell_as_a_character() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    box = cell_paragraph.add_rectangle(6000, 3000)
    box.set_draw_text("글상자")
    box.set_position(treat_as_char=True)
    group = cell_paragraph.add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                          ContainerMember.text_box(5000, 0, 4000, 2000, "묶음 글")])
    group.set_position(treat_as_char=True)
    holder = table.element
    while _local(holder) != "p":
        holder = holder.getparent()
    for obj, angle in ((box, 45), (group, 45)):
        holder.append(holder.makeelement(f"{HP}linesegarray", {}))
        obj.rotation = angle
        assert holder.find(f"{HP}linesegarray") is None  # the line holding the table is laid out again
    assert (box.rotation, group.rotation) == (45, 45)
    again = _reopen(doc)
    cell = again.tables[0].cell(0, 0)
    assert [obj.rotation for obj in cell.paragraphs[0].objects] == [45, 45]


def _group(doc: HwpxDocument):
    return doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 9000, 5000),
                                                ContainerMember.ellipse(10000, 1000, 5000, 5000)])


def test_what_is_not_shown_by_hancom_is_still_refused() -> None:
    doc = HwpxDocument.open(HANCOM / "turn_group_by_30.hwpx")
    turned = _objects(doc)[0]
    for call, code, says in (
        (lambda: setattr(turned.members[0], "rotation", 30), "shape-group-member-unsupported", "whole group"),
        (lambda: turned.resize(20000, 15000), "shape-rotation-unsupported", "turn it back to 0 first"),
        (lambda: setattr(turned, "rotation", 30.5), "shape-rotation-value", "whole degrees"),
    ):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == code and says in str(caught.value)
    fresh = HwpxDocument.new()
    both_ways = fresh.add_paragraph("").add_rectangle(8000, 4000)
    both_ways.element.find(f"{HP}flip").attrib.update({"horizontal": "1", "vertical": "1"})
    flipped_by_flag_only = _group(fresh)  # hp:flip set but no mirror in its matrices: not Hancom's form
    flipped_by_flag_only.element.find(f"{HP}flip").set("horizontal", "1")
    member_turned = _group(fresh)
    member_turned.element.find(f"{HP}rect/{HP}rotationInfo").set("angle", "30")
    for shape, reason in ((both_ways, "both ways"), (flipped_by_flag_only, "not a turn"),
                          (member_turned, "on its own")):
        before = [dict(node.attrib) for node in shape.element.iter()]
        with pytest.raises(HwpxValueError) as caught:
            shape.rotation = 45
        assert caught.value.code == "shape-rotation-unsupported" and reason in caught.value.context["reason"]
        assert [dict(node.attrib) for node in shape.element.iter()] == before  # refused before any change
    equation = fresh.shapes.add_equation("x")
    with pytest.raises(HwpxValueError) as caught:
        equation.rotation = 30
    assert caught.value.code == "shape-rotation-unsupported"


def test_angles_are_kept_as_hancom_keeps_them() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(14400, 7200)
    for given, kept in ((-30, 330), (390, 30), (720, 0), (-360, 0)):
        box.rotation = given
        assert box.rotation == kept
    group = _group(doc)
    group.rotation = -90
    assert group.rotation == 270


def test_a_group_turned_back_to_0_is_the_group_it_was() -> None:
    doc = HwpxDocument.new()
    group = _group(doc)
    before = _normalized(group.element)
    for angle in (15, 90, 180, 270, 359):
        group.rotation = angle
        assert group.rotation == angle
        group.rotation = 0
        assert _normalized(group.element) == before
    _reopen(doc)
