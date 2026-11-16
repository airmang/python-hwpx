"""Where a floating object is after it is turned, turned again, turned back, resized and turned, and ungrouped --
python-hwpx's ``hp:pos`` compared with what Hancom 2024 saved after doing the same (rotate9, ``want-float1``).

``tests/fixtures/hancom_saved/float_*.hwpx`` (see its README): one-object documents python-hwpx made -- a 12000 x 6000
picture, a 12000 x 6000 rectangle and a group of a rectangle and a text box, floating from a paragraph and column
(left and top, 3000 across and 2000 down), from the paper (left and top, 20000 and 30000) or centred (across in its
column, down on the paper) -- changed by Hangul 2024 through its public automation in the order the names say
(``30``/``45``/``90``/``60``/``0`` its object dialog's angle, ``s`` the object properties' width and height, ``f``
its flip command, ``u`` its ungroup command), then saved.

Hangul moves the object in its frame so the centre it turns about stays where it was on the page: placed from the
left (top), its offset gains the old centre less the new one; centred, the old centre's distance from the middle of
its box less the new one's. A flip and a resize leave the offset. Hangul also hangs the object on the paragraph at the
height it starts then; python-hwpx keeps it on its paragraph, which draws it in the same spot, so Hangul's down offset
is carried to python-hwpx's paragraph (tests/hancom_place.py) with the heights of Hangul's layout of the document
flipped (a flip moves nothing).

Left out of the comparison: ids, ``curSz``, line layout caches, ``hp:shapeComment`` (Hangul's ungroup writes its
default descriptions), ``zOrder`` (ungrouping: tests/test_objects_as_hancom_does.py), the image's measured size and
its item name; numbers within 0.01.
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.container import ContainerMember
from tests.hancom_place import carry_down_offset, paragraph_heights, paragraph_index

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"


def _png(width: int, height: int) -> bytes:
    rows = b""
    for y in range(height):
        row = b"\x00"
        for x in range(width):
            colour = (200, 30, 30) if x < width // 2 else (30, 30, 200)
            row += bytes(c // 2 if y < height // 4 else c for c in colour)
        rows += row

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


KINDS = {
    "p": lambda doc, p: p.add_picture(doc.media.add_image(_png(40, 20), "png"), width=12000, height=6000),
    "r": lambda doc, p: doc.shapes.add_rectangle(12000, 6000, paragraph=p),
    "g": lambda doc, p: p.add_container([ContainerMember.rect(0, 0, 6000, 6000),
                                         ContainerMember.text_box(7000, 0, 9000, 5000, "묶음 안 글상자")],
                                        treat_as_char=False),
}
FRAMES = {
    "para": {"vertical_relative_to": "PARA", "horizontal_relative_to": "COLUMN", "vertical_alignment": "TOP",
            "horizontal_alignment": "LEFT", "vertical_offset": 2000, "horizontal_offset": 3000},
    "paper": {"vertical_relative_to": "PAPER", "horizontal_relative_to": "PAPER", "vertical_alignment": "TOP",
            "horizontal_alignment": "LEFT", "vertical_offset": 30000, "horizontal_offset": 20000},
    "center": {"vertical_relative_to": "PAPER", "horizontal_relative_to": "COLUMN", "vertical_alignment": "CENTER",
            "horizontal_alignment": "CENTER", "vertical_offset": 0, "horizontal_offset": 0},
}
#: (fixture, kind, frame, steps)
CASES = [
    ("float_p_para_30", "p", "para", ["r30"]),
    ("float_p_paper_s_30", "p", "paper", ["s18000x6000", "r30"]),
    ("float_p_center_30_60", "p", "center", ["r30", "r60"]),
    ("float_r_para_30_0", "r", "para", ["r30", "r0"]),
    ("float_r_center_90", "r", "center", ["r90"]),
    ("float_g_para_45", "g", "para", ["r45"]),
    ("float_g_paper_30_60", "g", "paper", ["r30", "r60"]),
    ("float_g_paper_30_0", "g", "paper", ["r30", "r0"]),
    ("float_g_center_s_30", "g", "center", ["s24000x6000", "r30"]),
    ("float_g_center_30_60", "g", "center", ["r30", "r60"]),
    ("float_g_para_30_u", "g", "para", ["r30", "u"]),
    ("float_g_center_30_u", "g", "center", ["r30", "u"]),
]


def _signed(value: str) -> int:
    number = int(value) & 0xFFFFFFFF
    return number - (1 << 32) if number >= 1 << 31 else number


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray", "shapeComment", "imgDim", "imgClip"}:
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid", "zOrder", "binaryItemIDRef"}}
    if name == "pos":
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


def _objects(doc: HwpxDocument) -> list:
    return [obj for paragraph in doc.paragraphs for obj in paragraph.objects]


def _made(kind: str, frame: str, steps: list[str]):
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    obj = KINDS[kind](doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, **FRAMES[frame])
    doc.add_paragraph("1번")
    doc.add_paragraph("2번")
    for step in steps:
        if step == "u":
            obj.ungroup()
        elif step.startswith("r"):
            obj.rotation = int(step[1:])
        elif step == "f":
            obj.flip_horizontal = not obj.flip_horizontal
        else:
            obj.resize(*(int(value) for value in step[1:].split("x")))
    return doc


@pytest.mark.parametrize(("fixture", "kind", "frame", "steps"), CASES, ids=[case[0] for case in CASES])
def test_a_floating_object_is_where_hancom_puts_it(fixture: str, kind: str, frame: str, steps: list) -> None:
    doc = _made(kind, frame, steps)
    ours = _objects(doc)
    saved = HwpxDocument.open(HANCOM / f"{fixture}.hwpx")
    left = _objects(saved)
    assert len(left) == len(ours)
    heights = paragraph_heights(HwpxDocument.open(HANCOM / f"float_{kind}_para_f.hwpx"))
    for mine in ours:  # Hangul hangs freed shapes on other paragraphs: paired by kind and box
        hancom = next(o for o in left if o.element.tag == mine.element.tag
                      and (o.box_width, o.box_height) == (mine.box_width, mine.box_height))
        left.remove(hancom)
        carry_down_offset(hancom.element, paragraph_index(saved, hancom), paragraph_index(doc, mine), heights)
        assert _same(_normalized(mine.element), _normalized(hancom.element))
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues


@pytest.mark.parametrize("frame", list(FRAMES))
@pytest.mark.parametrize("kind", list(KINDS))
def test_turning_back_to_0_puts_a_floating_object_back(kind: str, frame: str) -> None:
    doc = _made(kind, frame, [])
    obj = _objects(doc)[0]
    before = dict(obj.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}pos").attrib)
    for angle in (30, 45, 90, 60, 0):
        obj.rotation = angle
    assert dict(obj.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}pos").attrib) == before


@pytest.mark.parametrize("frame", list(FRAMES))
@pytest.mark.parametrize("kind", list(KINDS))
def test_resizing_a_turned_floating_object_to_its_own_size_changes_nothing(kind: str, frame: str) -> None:
    doc = _made(kind, frame, ["r30"])
    before = doc.to_bytes()
    obj = _objects(doc)[0]
    obj.resize(obj.width, obj.height)
    assert doc.to_bytes() == before


def test_a_turned_object_set_as_a_character_keeps_its_place() -> None:
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(12000, 6000)
    box.set_position(treat_as_char=True)
    before = dict(box.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}pos").attrib)
    box.rotation = 30
    assert dict(box.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}pos").attrib) == before


def test_ungrouped_members_take_the_groups_place_in_the_drawing_order_as_hancom_gives_them() -> None:
    # ``float_z_u``: a group (zOrder 1) between a rectangle under it (0) and one over it (2), each on a paragraph of
    # its own, all three floating from the paper and overlapping; Hangul's ungroup gave the group's first member 1,
    # its last 2 and the rectangle over it 3.
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    group = doc.add_paragraph("묶음 문단").add_container(
        [ContainerMember.rect(0, 0, 6000, 6000), ContainerMember.ellipse(4000, 2000, 6000, 6000)], treat_as_char=False)
    below = doc.shapes.add_rectangle(14000, 9000, paragraph=doc.add_paragraph("아래"), fill_color="#C0C0FF")
    above = doc.shapes.add_rectangle(5000, 5000, paragraph=doc.add_paragraph("위"), fill_color="#FFC0C0")
    for obj, order, x, y in ((group, 1, 22000, 31000), (below, 0, 20000, 30000), (above, 2, 26000, 33000)):
        obj.set_position(treat_as_char=False, vertical_relative_to="PAPER", horizontal_relative_to="PAPER",
                         vertical_offset=y, horizontal_offset=x)
        obj.element.set("zOrder", str(order))
    group.ungroup()

    def orders(document: HwpxDocument) -> list[tuple[str, int, int, str]]:
        return sorted((o.element.tag.rsplit("}", 1)[-1], o.box_width, o.box_height, o.element.get("zOrder"))
                      for o in _objects(document))

    assert orders(doc) == orders(HwpxDocument.open(HANCOM / "float_z_u.hwpx"))
    assert sorted(int(o.element.get("zOrder")) for o in _objects(doc)) == [0, 1, 2, 3]
