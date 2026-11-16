"""A floating object turned so it starts above its paragraph, built by python-hwpx and turned by python-hwpx alone,
compared with what Hancom 2024 saved after turning the same document (rotate12, ``want-unseen``).

``tests/fixtures/hancom_saved/turned_*.hwpx`` (see its README): an object measured from the paragraph under a label
(down 2000, across 3000 from the column; a picture in a table cell 2000 / 1000 from its paragraph), turned 30 degrees
by Hangul's object dialog. The matrices, box, angle and across offset are the turn and must be Hangul's. Where Hangul
hangs the object and its down offset there are Hangul's page layout: one turned above its paragraph it hangs on the
paragraph at that height (a curve at -272 on the label, a group at 2285, a triangle at 2745, an arrow line at -2900).
python-hwpx lays out no pages and keeps the paragraph, moving the offset so the centre it turns about stays (it may go
negative; turned back to 0 it is where it began). Hangul measures that down offset from the line the object's control
is on, not the paragraph's first line (rotate12 check17 ``wsq``), so a paragraph cannot be chosen from saved line
caches either. Objects Hangul leaves on their paragraph (an arc at 536, a picture in a cell's only paragraph at -1598)
are compared down to their place.

Around a changed floating object python-hwpx drops only its own paragraph's line cache; the paragraphs text went
around it keep theirs, and Hangul lays them out again (rotate12 check17, 2026-11-17: 19 changes to SQUARE and
TOP_AND_BOTTOM pictures drew pixel for pixel the same as with every cache of the section dropped).

Left out of the comparison: ids, ``zOrder``, ``curSz``, line layout caches and the picture's image size (Hangul
measures the image again); numbers within 0.01.
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.container import ContainerMember

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FLOAT = {"vertical_relative_to": "PARA", "horizontal_relative_to": "COLUMN", "vertical_alignment": "TOP",
         "horizontal_alignment": "LEFT", "vertical_offset": 2000, "horizontal_offset": 3000}


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


SHAPES = {
    "fy": ("다각형(삼각형 0,0 / 40,0 / 10,20 mm, 채움)",
           lambda doc, p: doc.shapes.add_polygon([(0, 0), (40, 0), (10, 20)], paragraph=p, fill_color="#C0E0FF")),
    "fa": ("호 8000x8000", lambda doc, p: doc.shapes.add_arc(8000, 8000, paragraph=p)),
    "fc": ("곡선(0,0 / 30,20 / 60,0 mm)", lambda doc, p: doc.shapes.add_curve([(0, 0), (30, 20), (60, 0)], paragraph=p)),
    "fn": ("묶음 안 묶음(사각형 5000 + [사각형 3000 + 타원 3000])",
           lambda doc, p: p.add_container([ContainerMember.rect(0, 0, 5000, 5000),
                                           ContainerMember.group(6000, 0, [ContainerMember.rect(0, 0, 3000, 3000),
                                                                           ContainerMember.ellipse(4000, 1000, 3000,
                                                                                                   3000)])],
                                          treat_as_char=False)),
}


def _floating(kind: str):
    title, make = SHAPES[kind]
    doc = HwpxDocument.new()
    doc.add_paragraph(f"떠 있는 개체 하나: {title}, 문단·단 기준 왼쪽·위 3000·2000")
    obj = make(doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, **FLOAT)
    doc.add_paragraph("1번")
    doc.add_paragraph("2번")
    return doc, obj


def _arrow_line():
    doc = HwpxDocument.new()
    doc.add_paragraph("개체 하나: 수평선 12000, 끝(오른쪽)에 화살표")
    line = doc.shapes.add_line(0, 0, 12000, 0, paragraph=doc.add_paragraph("0번"))
    shape = line.element.find(f"{_HP}lineShape")
    shape.set("tailStyle", "ARROW")
    shape.set("tailSz", "MEDIUM_MEDIUM")
    line.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    return doc, line


def _cell_picture():
    doc = HwpxDocument.new()
    doc.add_paragraph("표 칸 안의 떠 있는 그림 12000x6000(칸 문단 기준, 왼쪽·위 2000·1000)")
    cell = doc.add_paragraph("").add_table(1, 1, width=30000, height=15000).cell(0, 0).paragraphs[0]
    picture = cell.add_picture(doc.media.add_image(_png(40, 20), "png"), width=12000, height=6000)
    picture.set_position(treat_as_char=False, vertical_relative_to="PARA", horizontal_relative_to="COLUMN",
                         vertical_offset=1000, horizontal_offset=2000)
    doc.add_paragraph("끝 문단")
    return doc, picture


def _signed(value: str) -> int:
    number = int(value) & 0xFFFFFFFF
    return number - (1 << 32) if number >= 1 << 31 else number


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray", "shapeComment", "imgDim", "imgClip"}:  # Hangul measures an image again
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


def _where(doc: HwpxDocument) -> list[tuple[int, str]]:
    """Each top-level object's paragraph index and kind, in order."""

    return [(index, str(obj.element.tag).rsplit("}", 1)[-1]) for index, paragraph in enumerate(doc.paragraphs)
            for obj in paragraph.objects]


def _turned_as_hangul_turned_it(ours, theirs, *, place: bool) -> None:
    """The turn as Hangul wrote it; its down offset only when Hangul kept the paragraph (*place*)."""

    if not place:
        theirs.find(f"{_HP}pos").set("vertOffset", ours.find(f"{_HP}pos").get("vertOffset"))
    assert _same(_normalized(ours), _normalized(theirs))


#: (fixture, kind, where Hangul put it, whether Hangul kept its paragraph)
CASES = [
    ("turned_fc_30", "fc", "Hangul: on the label at -272", False),
    ("turned_fn_30", "fn", "Hangul: on the label (two lines) at 2285", False),
    ("turned_fy_30", "fy", "Hangul: on the label (two lines) at 2745", False),
    ("turned_fa_30", "fa", "Hangul: where it was, at 536", True),
]


@pytest.mark.parametrize(("fixture", "kind", "where", "kept"), CASES, ids=[case[0] for case in CASES])
def test_a_turned_floating_shape_turns_as_hancom_turns_it(fixture: str, kind: str, where: str, kept: bool) -> None:
    doc, obj = _floating(kind)
    before = (obj.position.horizontal_offset, obj.position.vertical_offset)
    obj.rotation = 30
    saved = HwpxDocument.open(HANCOM / f"{fixture}.hwpx")
    assert _where(doc) == [(1, _where(saved)[0][1])], where  # python-hwpx keeps the paragraph
    assert (_where(saved)[0][0] == 1) == kept, where
    theirs = next(o for p in saved.paragraphs for o in p.objects)
    _turned_as_hangul_turned_it(obj.element, theirs.element, place=kept)
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues
    obj.rotation = 0
    assert (obj.position.horizontal_offset, obj.position.vertical_offset) == before


def test_a_resized_arrow_line_turned_above_its_paragraph_turns_as_hancom_turns_it() -> None:
    doc, line = _arrow_line()
    line.resize(18000, 0)
    line.rotation = 30
    saved = HwpxDocument.open(HANCOM / "turned_ha_s1_30.hwpx")
    assert _where(doc) == [(1, "line")] and _where(saved) == [(0, "line")]  # Hangul: on the label at -2900
    theirs = next(o for p in saved.paragraphs for o in p.objects)
    _turned_as_hangul_turned_it(line.element, theirs.element, place=False)
    assert line.position.vertical_offset == -4500  # the centre stays: 9000 high, 18000 wide at 30 degrees


def test_a_picture_in_a_cells_only_paragraph_turns_as_hancom_turns_it() -> None:
    doc, picture = _cell_picture()
    picture.rotation = 30
    saved = HwpxDocument.open(HANCOM / "turned_cell_p_30.hwpx")
    theirs = saved.paragraphs[1].tables[0].cell(0, 0).paragraphs[0].objects[0]
    _turned_as_hangul_turned_it(picture.element, theirs.element, place=True)  # -1598 in both
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues
