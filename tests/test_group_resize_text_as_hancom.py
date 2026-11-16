"""A group resized (unturned) -- its members' text laid out across the width they are drawn at -- compared with what
Hancom 2024 saved after resizing the same group through its object properties (rotate10, ``want-grpsize``).

``tests/fixtures/hancom_saved/grpsize_*.hwpx`` (see its README): one-group documents python-hwpx made -- a rectangle
and an ellipse (``p``) or a rectangle and a text box (``t``), set as a character (``c``), floating from a paragraph
and column (``f``) or centred (``m``) -- resized by Hangul to 24000 x 6000 (``s1``) or 16000 x 16000 (``s2``),
``_r``: then saved, opened again and saved again.

Hangul lays a member's text out across the width it is drawn at (``drawText/@lastWidth`` its ``orgSz`` width times
its scale across: 13500 at 1.5, 9000 at 1), whatever the group's place and after saving again. The members' rotation
centres it writes follow no one rule: kept or moved to the middles drawn at, in the same document differently
before and after saving it again (``tc_s1`` 4500/2500, ``tc_s1_r`` 6750/2500), on one axis but not the other. They
draw nothing while the members are unturned (a member turns only with its group, which writes them again), so
python-hwpx keeps them and they are left out of the comparison, with ids, ``curSz``, line layout caches and an empty
``hp:shapeComment``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.container import ContainerMember

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
MEMBERS = {
    "p": lambda: [ContainerMember.rect(0, 0, 6000, 6000), ContainerMember.ellipse(7000, 500, 9000, 5000)],
    "t": lambda: [ContainerMember.rect(0, 0, 6000, 6000),
                  ContainerMember.text_box(7000, 0, 9000, 5000, "묶음 안 글상자")],
}
PLACES = {
    "c": None,
    "f": {"vertical_relative_to": "PARA", "horizontal_relative_to": "COLUMN", "vertical_alignment": "TOP",
          "horizontal_alignment": "LEFT", "vertical_offset": 2000, "horizontal_offset": 3000},
    "m": {"vertical_relative_to": "PAPER", "horizontal_relative_to": "COLUMN", "vertical_alignment": "CENTER",
          "horizontal_alignment": "CENTER", "vertical_offset": 0, "horizontal_offset": 0},
}
SIZES = {"s1": (24000, 6000), "s2": (16000, 16000)}
CASES = ["grpsize_pc_s1", "grpsize_pc_s2", "grpsize_tc_s1", "grpsize_tc_s1_r", "grpsize_tf_s1", "grpsize_tf_s2",
         "grpsize_tm_s1"]


def _made(members: str, place: str):
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    keywords = PLACES[place]
    group = doc.add_paragraph("0번").add_container(MEMBERS[members](), treat_as_char=keywords is None)
    if keywords is None:
        group.set_position(treat_as_char=True)
    else:
        group.set_position(treat_as_char=False, **keywords)
    doc.add_paragraph("1번")
    return doc, group


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray"} or (name == "shapeComment" and not (element.text or "").strip()):
        return []
    attributes = {key: value for key, value in element.attrib.items() if key not in {"id", "instid"}}
    if name == "rotationInfo" and path.count("/") > 1:  # a member's centre: see the module's docstring
        attributes = {key: value for key, value in attributes.items() if key not in {"centerX", "centerY"}}
    here = f"{path}/{name}"
    lines = [f"{here} {sorted(attributes.items())} {(element.text or '').strip()!r}"]
    for child in element:
        lines += _normalized(child, here)
    return lines


def _same(ours: list[str], theirs: list[str], tolerance: float = 0.01) -> bool:
    ours, theirs = sorted(ours), sorted(theirs)
    if len(ours) != len(theirs):
        return False
    number = re.compile(r"'(-?\d+(?:\.\d+)?)'")
    for a, b in zip(ours, theirs):
        if number.sub("#", a) != number.sub("#", b):
            return False
        if any(abs(float(x) - float(y)) > tolerance for x, y in zip(number.findall(a), number.findall(b))):
            return False
    return True


def _only(doc: HwpxDocument):
    objects = [obj for paragraph in doc.paragraphs for obj in paragraph.objects]
    assert len(objects) == 1
    return objects[0]


@pytest.mark.parametrize("fixture", CASES)
def test_a_resized_group_lays_its_text_out_as_hancom_does(fixture: str) -> None:
    key = fixture.split("_")[1]
    doc, group = _made(key[0], key[1])
    group.resize(*SIZES[fixture.split("_")[2]])
    hancom = _only(HwpxDocument.open(HANCOM / f"{fixture}.hwpx"))
    assert _same(_normalized(group.element), _normalized(hancom.element))
    widths = [m.find(f"{HP}drawText").get("lastWidth") for m in group.element if m.find(f"{HP}drawText") is not None]
    assert widths == [m.find(f"{HP}drawText").get("lastWidth") for m in hancom.element
                      if m.find(f"{HP}drawText") is not None]
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues


def test_members_centres_draw_nothing_a_turn_writes_them_again() -> None:
    _kept_doc, kept = _made("t", "f")
    _moved_doc, moved = _made("t", "f")
    for group in (kept, moved):
        group.resize(24000, 6000)
    for member in moved.element:  # Hangul's other form: the centres at the middles drawn at
        info, own = member.find(f"{HP}rotationInfo"), member.find(f"{HP}orgSz")
        if info is not None and own is not None:
            info.set("centerX", str(int(own.get("width")) * 3 // 4))
    kept.rotation = 30
    moved.rotation = 30
    assert _normalized(kept.element) == _normalized(moved.element)
    assert [m.find(f"{HP}rotationInfo").attrib for m in kept.element if m.find(f"{HP}rotationInfo") is not None] == \
        [m.find(f"{HP}rotationInfo").attrib for m in moved.element if m.find(f"{HP}rotationInfo") is not None]


def test_a_text_box_resized_lays_its_text_out_across_its_new_width() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(9000, 5000)
    box.set_draw_text("글상자 글")
    box.resize(13500, 5000)
    assert box.element.find(f"{HP}drawText").get("lastWidth") == "13500"
    box.rotation = 30
    box.rotation = 0
    assert box.element.find(f"{HP}drawText").get("lastWidth") == "13500"


@pytest.mark.parametrize("steps", [["f"], ["v"], ["f", "v"], ["r30"]])
def test_a_flipped_or_turned_group_resized_lays_its_text_out_across_the_width_drawn(steps: list) -> None:
    _doc, group = _made("t", "f")
    for step in steps:
        if step == "f":
            group.flip_horizontal = True
        elif step == "v":
            group.flip_vertical = True
        else:
            group.rotation = int(step[1:])
    group.resize(24000, 6000)
    text_box = next(m for m in group.element if m.find(f"{HP}drawText") is not None)
    expected = "13500" if not group.rotation else None  # turned: the width of its turned box
    if expected is not None:
        assert text_box.find(f"{HP}drawText").get("lastWidth") == expected
    else:
        group.rotation = 0
        assert next(m for m in group.element if m.find(f"{HP}drawText") is not None) \
            .find(f"{HP}drawText").get("lastWidth") == "13500"
