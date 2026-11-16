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
from hwpx.oxml.namespaces import HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
TEXT_BOX, GROUP, NESTED = "1720249014", "768560093", "2104287188"

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
]


def _objects(doc: HwpxDocument) -> list:
    return [obj for paragraph in doc.paragraphs for obj in paragraph.objects]


def _by_instid(doc: HwpxDocument, instid: str):
    return next(obj for obj in _objects(doc) if obj.element.get("instid") == instid)


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray"} or (name == "shapeComment" and not (element.text or "").strip()):
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid"} and not (name == "pos" and key in {"horzOffset", "vertOffset"})}
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
    assert (target.flip_horizontal, target.flip_vertical, target.rotation) == (False, False, 0)
    for name, value in steps:
        setattr(target, name, value)
    theirs = _by_instid(HwpxDocument.open(HANCOM / f"{hancom}.hwpx"), instid)
    assert (theirs.flip_horizontal, theirs.flip_vertical, theirs.rotation) == \
        (target.flip_horizontal, target.flip_vertical, target.rotation)
    assert _same(_normalized(target.element), _normalized(theirs.element))
    again = _by_instid(_reopen(doc), instid)
    assert (again.flip_horizontal, again.flip_vertical, again.rotation) == \
        (target.flip_horizontal, target.flip_vertical, target.rotation)


@pytest.mark.parametrize(("hancom", "instid", "steps", "untouched"), CASES, ids=[case[0] for case in CASES])
def test_hancoms_flip_and_turn_go_back(hancom: str, instid: str, steps: list, untouched: str) -> None:
    doc = HwpxDocument.open(HANCOM / f"{hancom}.hwpx")
    target = _by_instid(doc, instid)
    target.rotation = 0
    target.flip_horizontal = False
    target.flip_vertical = False
    original = _by_instid(HwpxDocument.open(HANCOM / f"{untouched}.hwpx"), instid)
    assert _same(_normalized(target.element), _normalized(original.element))


def test_a_flipped_group_keeps_its_members_unflipped_marked_as_hancom_marks_them() -> None:
    doc = HwpxDocument.open(HANCOM / "flip_text_box_left_right.hwpx")
    group = _by_instid(doc, GROUP)
    group.flip_horizontal = True
    assert [(m.flip_horizontal, m.rotation) for m in group.members] == [(False, 180), (False, 180)]
    group.flip_horizontal = False
    group.flip_vertical = True
    assert [(m.flip_vertical, m.rotation) for m in group.members] == [(False, 0), (False, 0)]


def test_what_hancom_was_not_seen_doing_is_refused() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    turned = paragraph.add_rectangle(8000, 4000)
    turned.rotation = 30
    flipped = paragraph.add_rectangle(8000, 4000)
    flipped.flip_horizontal = True
    resized_group = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                         ContainerMember.rect(5000, 0, 4000, 2000)])
    resized_group.resize(18000, 4000)
    nested = doc.add_paragraph("").add_container([
        ContainerMember.rect(0, 0, 3000, 3000),
        ContainerMember.group(4000, 0, [ContainerMember.rect(0, 0, 2000, 2000), ContainerMember.rect(3000, 0, 2000, 2000)]),
    ])
    line = doc.add_paragraph("").add_line(0, 0, 8000, 2000)
    ellipse = doc.add_paragraph("").add_ellipse(6000, 3000)
    for call, code, says in (
        (lambda: setattr(turned, "flip_horizontal", True), "shape-flip-unsupported", "turn it back to 0"),
        (lambda: setattr(flipped, "flip_vertical", True), "shape-flip-unsupported", "both"),
        (lambda: flipped.resize(4000, 2000), "shape-flip-unsupported", "flip it back first"),
        (lambda: setattr(resized_group, "flip_horizontal", True), "shape-rotation-unsupported", "resized"),
        (lambda: setattr(nested, "flip_horizontal", True), "shape-rotation-unsupported", "holds a group"),
        (lambda: setattr(nested.members[0], "flip_horizontal", True), "shape-group-member-unsupported", "group"),
        (lambda: setattr(line, "flip_horizontal", True), "shape-flip-unsupported", "line"),
        (lambda: setattr(ellipse, "flip_vertical", True), "shape-flip-unsupported", "ellipse"),
        (lambda: setattr(flipped, "flip_horizontal", 1), "shape-flip-value", "True or False"),
    ):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == code and says in str(caught.value), (code, str(caught.value))
    assert (flipped.flip_horizontal, flipped.flip_vertical, turned.rotation) == (True, False, 30)
    _reopen(doc)
