"""Flipping a text box and a whole group (``flip_horizontal``/``flip_vertical``), turning a flipped one, and
turning a group inside a resized group -- compared with what Hancom 2024 saved after doing the same.

``tests/fixtures/hancom_saved/flip_*.hwpx`` and ``turn_group_in_resized_group_by_30.hwpx`` (see its README) were
made by python-hwpx -- a text box (instid 1720249014), a group of a rectangle and a text box (768560093) and a group
holding a group resized to 1.5 times (2104287188) -- and changed by Hangul 2024 through its public automation
(``ShapeObjHorzFlip``/``ShapeObjVertFlip``, then its object dialog's angle), then saved. In each file the other
objects are as Hangul saves them untouched, so each object is found unchanged in another file.
``turn_flipped_rect_by_30.hwpx`` holds a rectangle (67647593) Hangul flipped left-right and turned 30 degrees.

Left out of the comparison, as in test_turn_text_shapes_and_groups.py: ids, ``hp:pos`` offsets, ``curSz``, line
layout caches and an empty ``hp:shapeComment``. Numbers are compared within 0.01: turned back to 0, Hangul leaves
noise in a flipped object's matrix (-1.000001, 14400.004456).
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
TEXT_BOX, GROUP, NESTED = "1720249014", "768560093", "2104287188"
TURNED_BOX, TURNED_GROUP, ELLIPSE, POLYGON, LINE = "1570112883", "1425950003", "741191633", "1881274590", "1207765247"
PICTURE, TURNED_PICTURE = "1799081593", "1011038855"
G_TURNED, G_PLAIN, P_PLAIN = "1976520070", "1339080812", "967822942"
ARC, CURVE, G4, NESTED4 = "1772920078", "1177849096", "1887347079", "1260677313"

#: (file Hangul wrote, instid, what was done in order, a file holding the object untouched)
CASES = [
    ("flip_text_box_left_right", TEXT_BOX, [("flip_horizontal", True)], "flip_group_left_right"),
    ("flip_text_box_left_right_by_45", TEXT_BOX, [("flip_horizontal", True), ("rotation", 45)],
     "flip_group_left_right"),
    ("flip_text_box_left_right_by_45_back", TEXT_BOX,
     [("flip_horizontal", True), ("rotation", 45), ("rotation", 0)], "flip_group_left_right"),
    ("flip_text_box_up_down_by_45", TEXT_BOX, [("flip_vertical", True), ("rotation", 45)], "flip_group_left_right"),
    ("flip_group_left_right", GROUP, [("flip_horizontal", True)], "flip_text_box_left_right"),
    ("flip_group_left_right_by_30", GROUP, [("flip_horizontal", True), ("rotation", 30)],
     "flip_text_box_left_right"),
    ("flip_group_up_down_by_30", GROUP, [("flip_vertical", True), ("rotation", 30)], "flip_text_box_left_right"),
    ("turn_group_in_resized_group_by_30", NESTED, [("rotation", 30)], "flip_text_box_left_right"),
    ("turn_flipped_rect_by_30", "67647593", [("flip_horizontal", True), ("rotation", 30)],
     "turn_resized_group_by_30"),
    # ``flip_turned_*``, ``flip_ellipse_*``, ``flip_polygon_*``, ``flip_line_*``: a text box and a group turned 30
    # degrees (by python-hwpx), an ellipse, a polygon and a line, flipped (and turned) by Hangul. A turned object
    # flipped is written turned the other way (30 -> 330) and flipped.
    ("flip_turned_text_box_left_right", TURNED_BOX, [("flip_horizontal", True)], "flip_ellipse_left_right_by_30"),
    ("flip_turned_text_box_up_down", TURNED_BOX, [("flip_vertical", True)], "flip_ellipse_left_right_by_30"),
    ("flip_turned_text_box_both_ways", TURNED_BOX, [("flip_horizontal", True), ("flip_vertical", True)],
     "flip_ellipse_left_right_by_30"),
    ("flip_turned_group_left_right", TURNED_GROUP, [("flip_horizontal", True)], "flip_ellipse_left_right_by_30"),
    ("flip_ellipse_left_right_by_30", ELLIPSE, [("flip_horizontal", True), ("rotation", 30)],
     "flip_turned_text_box_left_right"),
    ("flip_polygon_left_right_by_30", POLYGON, [("flip_horizontal", True), ("rotation", 30)],
     "flip_turned_text_box_left_right"),
    ("flip_line_left_right_by_30", LINE, [("flip_horizontal", True), ("rotation", 30)],
     "flip_turned_text_box_left_right"),
    ("flip_line_up_down", LINE, [("flip_vertical", True)], "flip_turned_text_box_left_right"),
    # ``flip_*picture*``: a 12000 x 6000 picture and one turned 30 degrees (by python-hwpx), flipped (turned, resized
    # through the object's properties to 6000 x 6000) by Hangul. A flipped picture resized keeps its mirror about the
    # middle of its own size and moves by what it lost (scaMatrix 0.5, e3 6000).
    ("flip_picture_left_right", PICTURE, [("flip_horizontal", True)], "flip_turned_picture_left_right"),
    ("flip_picture_left_right_by_30", PICTURE, [("flip_horizontal", True), ("rotation", 30)],
     "flip_turned_picture_left_right"),
    ("flip_picture_both_ways", PICTURE, [("flip_horizontal", True), ("flip_vertical", True)],
     "flip_turned_picture_left_right"),
    ("flip_turned_picture_left_right", TURNED_PICTURE, [("flip_horizontal", True)], "flip_picture_left_right"),
    ("flip_picture_left_right_resized", PICTURE, [("flip_horizontal", True), ("size", (6000, 6000))],
     "flip_turned_picture_left_right"),
    # rotate6 (``want-flip3``): a group turned 30 degrees and one not, a picture and one turned 30 degrees, flipped,
    # resized and turned by Hangul in the orders the names say. Hangul flips a group in place (a turned one keeps
    # its move and box) and turns a flipped picture resized after its flip about where it holds its middle.
    ("flip_turned_group_up_down", G_TURNED, [("flip_vertical", True)], "flip_group_both_ways"),
    ("flip_group_both_ways", G_PLAIN, [("flip_horizontal", True), ("flip_vertical", True)],
     "flip_turned_group_up_down"),
    # resized by python-hwpx, then flipped: the flip mirrors about the middle of the size the group is drawn at,
    # whatever centre the resize left (python-hwpx's and Hangul's resize both leave the old one)
    ("flip_resized_group_left_right", G_PLAIN, [("size", (18000, 9000)), ("flip_horizontal", True)],
     "flip_turned_group_up_down"),
    ("flip_group_left_right_resized", G_PLAIN, [("flip_horizontal", True), ("size", (18000, 9000))],
     "flip_turned_group_up_down"),
    ("flip_resized_picture_left_right", P_PLAIN, [("size", (6000, 6000)), ("flip_horizontal", True)],
     "flip_group_both_ways"),
    ("flip_picture_left_right_resized_by_30", P_PLAIN,
     [("flip_horizontal", True), ("size", (6000, 6000)), ("rotation", 30)], "flip_group_both_ways"),
    ("flip_picture_up_down_resized", P_PLAIN, [("flip_vertical", True), ("size", (6000, 9000))],
     "flip_group_both_ways"),
    # rotate6 (``want-flip4``): an arc, a curve, a group, a group holding a group. An arc and a curve flip as the
    # other shapes (an odd-sized one turns about the whole-unit centre it holds); a group flipped up-down and
    # resized moves every scaMatrix by what it gained (e6) and puts its members' centres at their drawn middles; a
    # group holding a group flips with the group inside marked as its members are.
    ("flip_arc_up_down", ARC, [("flip_vertical", True)], "flip_curve_left_right_by_30"),
    ("flip_arc_left_right_by_30", ARC, [("flip_horizontal", True), ("rotation", 30)], "flip_curve_left_right_by_30"),
    ("flip_curve_left_right_by_30", CURVE, [("flip_horizontal", True), ("rotation", 30)], "flip_arc_up_down"),
    ("flip_group_up_down_resized", G4, [("flip_vertical", True), ("size", (18000, 9000))], "flip_arc_up_down"),
    ("flip_group_in_group_left_right", NESTED4, [("flip_horizontal", True)], "flip_arc_up_down"),
]


def _set(obj, name: str, value) -> None:
    if name == "size":
        obj.resize(*value)
    else:
        setattr(obj, name, value)


def _get(obj, name: str):
    return (obj.width, obj.height) if name == "size" else getattr(obj, name)


def _objects(doc: HwpxDocument) -> list:
    return [obj for paragraph in doc.paragraphs for obj in paragraph.objects]


def _by_instid(doc: HwpxDocument, instid: str):
    return next(obj for obj in _objects(doc) if obj.element.get("instid") == instid)


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    # imgDim/imgClip: Hangul measures again the image of a picture it changed (40 x 20 px: 3000 x 1500), not a flip
    if name in {"curSz", "linesegarray", "imgDim", "imgClip"} or (
            name == "shapeComment" and not (element.text or "").strip()):
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid", "binaryItemIDRef"}  # Hangul renames the items it saves
                  and not (name == "pos" and key in {"horzOffset", "vertOffset"})}
    here = f"{path}/{name}"
    lines = [f"{here} {sorted(attributes.items())} {(element.text or '').strip()!r}"]
    for child in element:
        lines += _normalized(child, here)
    return lines


def _same(ours: list[str], theirs: list[str], tolerance: float = 0.01) -> bool:
    if len(ours) != len(theirs):
        return False
    number = re.compile(r"'(-?\d+(?:\.\d+)?)'")
    for a, b in zip(ours, theirs):
        if number.sub("#", a) != number.sub("#", b):
            return False
        if any(abs(float(x) - float(y)) > tolerance for x, y in zip(number.findall(a), number.findall(b))):
            return False
    return True


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


@pytest.mark.parametrize(("hancom", "instid", "steps", "untouched"), CASES, ids=[case[0] for case in CASES])
def test_flipping_and_turning_write_what_hancom_wrote(hancom: str, instid: str, steps: list, untouched: str) -> None:
    doc = HwpxDocument.open(HANCOM / f"{untouched}.hwpx")
    target = _by_instid(doc, instid)
    assert (target.flip_horizontal, target.flip_vertical) == (False, False)
    for name, value in steps:
        _set(target, name, value)
    theirs = _by_instid(HwpxDocument.open(HANCOM / f"{hancom}.hwpx"), instid)
    assert (theirs.flip_horizontal, theirs.flip_vertical, theirs.rotation) == \
        (target.flip_horizontal, target.flip_vertical, target.rotation)
    assert _same(_normalized(target.element), _normalized(theirs.element))
    again = _by_instid(_reopen(doc), instid)
    assert (again.flip_horizontal, again.flip_vertical, again.rotation) == \
        (target.flip_horizontal, target.flip_vertical, target.rotation)


@pytest.mark.parametrize(("hancom", "instid", "steps", "untouched"), CASES, ids=[case[0] for case in CASES])
def test_hancoms_flip_and_turn_go_back(hancom: str, instid: str, steps: list, untouched: str) -> None:
    original = _by_instid(HwpxDocument.open(HANCOM / f"{untouched}.hwpx"), instid)
    before = []  # each step's value before it, replayed on the untouched object
    replay = _by_instid(HwpxDocument.open(HANCOM / f"{untouched}.hwpx"), instid)
    for name, value in steps:
        before.append(_get(replay, name))
        _set(replay, name, value)
    doc = HwpxDocument.open(HANCOM / f"{hancom}.hwpx")
    target = _by_instid(doc, instid)
    for (name, _), value in reversed(list(zip(steps, before))):  # undone in the other order
        _set(target, name, value)
    ours, theirs = _normalized(target.element), _normalized(original.element)
    if target.element.tag.endswith("}container") and [n for n, _ in steps] == ["size", "flip_horizontal"]:
        # the flip moved the centres to the middles drawn at 18000 x 9000; resizing back leaves centres, as
        # Hangul's resize does, so only they differ from the group before
        ours, theirs = (re.sub(r"\('center[XY]', '\d+'\), ", "", line) for line in ours), \
            (re.sub(r"\('center[XY]', '\d+'\), ", "", line) for line in theirs)
        ours, theirs = list(ours), list(theirs)
    assert _same(ours, theirs)


def test_a_flipped_group_keeps_its_members_unflipped_marked_as_hancom_marks_them() -> None:
    doc = HwpxDocument.open(HANCOM / "flip_text_box_left_right.hwpx")
    group = _by_instid(doc, GROUP)
    group.flip_horizontal = True
    assert [(m.flip_horizontal, m.rotation) for m in group.members] == [(False, 180), (False, 180)]
    group.flip_horizontal = False
    group.flip_vertical = True
    assert [(m.flip_vertical, m.rotation) for m in group.members] == [(False, 0), (False, 0)]


def test_a_turned_object_flipped_turns_the_other_way() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(8000, 4000)
    box.rotation = 30
    box.flip_horizontal = True
    assert (box.rotation, box.flip_horizontal) == (330, True)
    box.flip_vertical = True  # both ways: turned back to 30, mirrored both ways (a half turn)
    assert (box.rotation, box.flip_horizontal, box.flip_vertical) == (30, True, True)
    box.flip_horizontal = False
    box.flip_vertical = False
    assert (box.rotation, box.flip_horizontal, box.flip_vertical) == (30, False, False)
    _reopen(doc)


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)


def test_what_hancom_was_not_seen_doing_is_refused() -> None:
    doc = HwpxDocument.new()
    flipped = doc.add_paragraph("").add_rectangle(8000, 4000)
    flipped.flip_horizontal = True
    group = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                 ContainerMember.rect(5000, 0, 4000, 2000)])
    group.flip_vertical = True
    both_ways_group = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                           ContainerMember.rect(5000, 0, 4000, 2000)])
    both_ways_group.flip_horizontal = True
    both_ways_group.flip_vertical = True
    turned_group =doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                        ContainerMember.rect(5000, 0, 4000, 2000)])
    turned_group.rotation = 30
    resized_group = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                         ContainerMember.rect(5000, 0, 4000, 2000)])
    resized_group.resize(18000, 4000)
    resized_group.rotation = 30
    nested = doc.add_paragraph("").add_container([
        ContainerMember.rect(0, 0, 3000, 3000),
        ContainerMember.group(4000, 0, [ContainerMember.rect(0, 0, 2000, 2000), ContainerMember.rect(3000, 0, 2000, 2000)]),
    ])
    picture = doc.add_picture(PNG, "png", width=6000, height=3000)
    picture.flip_horizontal = True
    turned_picture = doc.add_picture(PNG, "png", width=6000, height=3000)
    turned_picture.flip_horizontal = True
    turned_picture.rotation = 30
    resized_rect = doc.add_paragraph("").add_rectangle(8000, 4000)
    resized_rect.element.find(f"{HP}renderingInfo/{HC}scaMatrix").set("e1", "0.5")  # drawn at half its width
    resized_rect.element.find(f"{HP}curSz").set("width", "4000")
    turned_picture.resize(3000, 1500)  # rotate7: its box stretched along the page (p-f-30-S)
    both_ways_group.resize(18000, 4000)  # rotate7 g-fv-S
    nested.flip_vertical = True  # rotate7 n-v
    nested.flip_vertical = False
    for call, code, says in (
        (lambda: setattr(picture, "crop", (0, 0, 1000, 0)), "shape-flip-unsupported", "flip it back first"),
        (lambda: flipped.resize(4000, 2000), "shape-flip-unsupported", "flip it back first"),
        (lambda: setattr(resized_rect, "flip_horizontal", True), "shape-flip-unsupported", "resized"),
        (lambda: setattr(resized_group, "flip_horizontal", True), "shape-rotation-unsupported", "resized, turned"),
        (lambda: setattr(turned_picture, "rotation", 0), "shape-rotation-unsupported", "more than scale"),
        (lambda: setattr(nested.members[0], "flip_horizontal", True), "shape-group-member-unsupported", "group"),
        (lambda: setattr(flipped, "flip_horizontal", 1), "shape-flip-value", "True or False"),
    ):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == code and says in str(caught.value), (code, str(caught.value))
    assert (flipped.flip_horizontal, flipped.flip_vertical, turned_group.rotation) == (True, False, 30)
    _reopen(doc)
