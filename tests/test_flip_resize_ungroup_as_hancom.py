"""Basic shapes resized and flipped, flipped and resized (and turned after), groups flipped, resized and turned, a
resized turned flipped group turned again, a group holding a group flipped and resized, and flipped groups and a group
holding a group ungrouped -- each built by python-hwpx from scratch and changed by python-hwpx alone, compared with
what Hancom 2024 saved after doing the same to the same document (rotate8, ``want-flip6``).

``tests/fixtures/hancom_saved/one_*.hwpx`` (see its README): one-object documents python-hwpx made (a 12000 x 6000
rectangle and ellipse, a triangle 11339 x 5669, a diagonal line, a horizontal line, a group of a rectangle and a text
box, a group holding a group), changed by Hangul 2024 through its public automation in the order the names say (``f``
/``v`` its flip commands, ``s`` the object properties' width and height, ``30``/``60`` the object dialog's angle,
``u`` its ungroup command), then saved.

Left out of the comparison: ids (Hangul hangs ungrouped shapes on other paragraphs: their down offset is carried
to python-hwpx's paragraph, see tests/hancom_place.py), ``curSz``, line layout caches, ``hp:shapeComment`` (Hangul's ungroup writes its default
descriptions) and ``zOrder``; numbers within 0.01.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.container import ContainerMember
from tests.hancom_place import carry_down_offset, paragraph_heights, paragraph_index

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
GSO = {"rect", "ellipse", "polygon", "line", "container", "pic", "arc", "curve"}

SOURCES = {
    "q": lambda doc, p: doc.shapes.add_rectangle(12000, 6000, paragraph=p),
    "e": lambda doc, p: doc.shapes.add_ellipse(12000, 6000, paragraph=p),
    "y": lambda doc, p: doc.shapes.add_polygon([(0, 0), (40, 0), (10, 20)], paragraph=p),
    "l": lambda doc, p: doc.shapes.add_line(0, 0, 12000, 6000, paragraph=p),
    "h": lambda doc, p: doc.shapes.add_line(0, 0, 12000, 0, paragraph=p),
    "g": lambda doc, p: p.add_container([ContainerMember.rect(0, 0, 6000, 6000),
                                         ContainerMember.text_box(7000, 0, 9000, 5000, "묶음 안 글상자")],
                                        treat_as_char=False),
    "n": lambda doc, p: p.add_container([
        ContainerMember.rect(0, 0, 5000, 5000),
        ContainerMember.group(6000, 0, [ContainerMember.rect(0, 0, 3000, 3000),
                                        ContainerMember.ellipse(4000, 1000, 3000, 3000)])], treat_as_char=False),
}
#: (fixture Hangul saved, source, python-hwpx's steps): f/v toggle a flip, rN turns, sWxH resizes, u ungroups.
CASES = [
    ("one_q_f_s1_30", "q", ["f", "s18000x6000", "r30"]),
    ("one_e_s2_v", "e", ["s8000x12000", "v"]),
    ("one_y_s1_f_30", "y", ["s18000x6000", "f", "r30"]),
    ("one_y_f_s1", "y", ["f", "s18000x6000"]),
    ("one_l_s1_f_30", "l", ["s18000x6000", "f", "r30"]),
    ("one_h_s2_v", "h", ["s8000x3000", "v"]),
    ("one_n_v_s1", "n", ["v", "s19500x5000"]),
    ("one_g_f_s1_30", "g", ["f", "s24000x6000", "r30"]),
    ("one_g_s1_30_v_60", "g", ["s24000x6000", "r30", "v", "r60"]),
    ("one_g_s2_30_f_60", "g", ["s16000x16000", "r30", "f", "r60"]),
    ("one_g_v_u", "g", ["v", "u"]),
    ("one_g_30_f_u", "g", ["r30", "f", "u"]),
    ("one_n_u", "n", ["u"]),
]


def _objects(doc: HwpxDocument) -> list:
    return [obj for paragraph in doc.paragraphs for obj in paragraph.objects]


def _signed(value: str) -> int:
    number = int(value) & 0xFFFFFFFF
    return number - (1 << 32) if number >= 1 << 31 else number


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray", "shapeComment"}:
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid", "zOrder"}}
    if name == "pos":  # offsets as signed numbers: Hangul writes a negative one unsigned too
        attributes = {key: (str(_signed(value)) if key in {"horzOffset", "vertOffset"} else value)
                      for key, value in attributes.items()}
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


def _do(obj, step: str) -> None:
    if step in ("f", "v"):
        name = "flip_horizontal" if step == "f" else "flip_vertical"
        setattr(obj, name, not getattr(obj, name))
    elif step.startswith("r"):
        obj.rotation = int(step[1:])
    elif step == "u":
        obj.ungroup()
    else:
        obj.resize(*(int(value) for value in step[1:].split("x")))


def _made(source: str, steps: list[str]):
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    obj = SOURCES[source](doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    for step in steps:
        _do(obj, step)
    return doc, obj


@pytest.mark.parametrize(("fixture", "source", "steps"), CASES, ids=[case[0] for case in CASES])
def test_python_hwpx_from_scratch_writes_what_hancom_saved(fixture: str, source: str, steps: list) -> None:
    doc, _ = _made(source, steps)
    ours = _objects(doc)
    saved = HwpxDocument.open(HANCOM / f"{fixture}.hwpx")
    left = _objects(saved)
    theirs = []
    for mine in ours:  # Hangul hangs freed shapes on other paragraphs: paired by kind and box
        hancom = next(o for o in left if o.element.tag == mine.element.tag
                      and (o.box_width, o.box_height) == (mine.box_width, mine.box_height))
        left.remove(hancom)
        theirs.append(hancom)
    heights = paragraph_heights(saved, first_line_only=True)
    for mine, hancom in zip(ours, theirs):  # its offset carried to python-hwpx's paragraph
        carry_down_offset(hancom.element, paragraph_index(saved, hancom), paragraph_index(doc, mine), heights)
    assert len(ours) == len(theirs)
    for mine, hancom in zip(ours, theirs):
        assert (mine.rotation, mine.flip_horizontal, mine.flip_vertical) == \
            (hancom.rotation, hancom.flip_horizontal, hancom.flip_vertical)
        assert _same(_normalized(mine.element), _normalized(hancom.element))
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    assert [(o.rotation, o.flip_horizontal, o.flip_vertical) for o in _objects(again)] == \
        [(o.rotation, o.flip_horizontal, o.flip_vertical) for o in ours]


#: Every state rotate8 opens (and the shapes ungrouping frees): resizing to the own size changes nothing.
STATES = [(source, steps) for _, source, steps in CASES] + [
    (key, steps) for key in ("q", "e", "y", "l") for steps in (
        ["s18000x6000", "f"], ["s8000x12000", "v"], ["s18000x6000", "f", "r30"])] + [
    (key, steps) for key in ("q", "e", "y") for steps in (["f", "s18000x6000"], ["v", "s8000x12000", "r30"])] + [
    ("g", ["f", "s16000x16000", "r30"]), ("g", ["s24000x6000", "r30", "f", "r60"]), ("n", ["f", "s13000x13000"]),
    ("g", ["f", "u"]), ("g", ["r30", "v", "u"])]


@pytest.mark.parametrize(("source", "steps"), STATES, ids=["-".join([s, *steps]) for s, steps in STATES])
def test_resizing_to_the_own_width_and_height_changes_nothing(source: str, steps: list) -> None:
    doc, _ = _made(source, steps)
    before = doc.to_bytes()
    for obj in _objects(doc):
        obj.resize(obj.width, obj.height)
        obj.resize(obj.width)
    assert doc.to_bytes() == before


def test_a_resized_turned_flipped_group_turned_again_turns_back_and_flips_back() -> None:
    doc, group = _made("g", ["s24000x6000", "r30", "f"])
    flipped = doc.to_bytes()
    group.rotation = 60
    group.rotation = 330
    assert doc.to_bytes() == flipped
    group.flip_horizontal = False
    assert (group.rotation, group.flip_horizontal) == (30, False)
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues


def test_what_hancom_does_not_keep_is_still_refused() -> None:
    _, line = _made("l", ["f"])
    with pytest.raises(HwpxValueError) as caught:  # Hangul resizing a flipped line drops its mirror
        line.resize(18000, 6000)
    assert caught.value.code == "shape-flip-unsupported" and "unflipped" in str(caught.value)
    _, flat = _made("h", ["s18000x0"])
    with pytest.raises(HwpxValueError) as caught:  # drawn 0 high: Hangul writes its flip as a half turn
        flat.flip_horizontal = True
    assert caught.value.code == "shape-flip-unsupported"
    for steps in (["f", "v"], ["f", "s24000x6000"]):  # no Hancom-saved document shows these ungrouped
        _, group = _made("g", steps)
        with pytest.raises(HwpxValueError) as caught:
            group.ungroup()
        assert caught.value.code == "shape-ungroup-unsupported"
