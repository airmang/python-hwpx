"""A floating object turned so it starts above its paragraph, built by python-hwpx and turned by python-hwpx alone,
compared with what Hancom 2024 saved after turning the same document (rotate12, ``want-unseen``).

``tests/fixtures/hancom_saved/turned_*.hwpx`` (see its README): an object measured from the paragraph under a label
(down 2000, across 3000 from the column; a picture in a table cell 2000 / 1000 from its paragraph), turned 30 degrees
by Hangul's object dialog. Hangul hangs one that then starts above its paragraph on the paragraph at that height --
the label (a curve at -272, a group at 2285, a triangle at 2745) -- or leaves it measured above the first paragraph of
its page or box (a picture in a cell's only paragraph at -1598, an arrow line at -2900). It has to: Hangul does not
draw an object above the top of the paragraph it is measured from where its offset says (kept in the page area it
starts at that top; one text goes around lands a line higher, rotate12 check15). python-hwpx hangs it the same way
when the paragraphs' line layout is known (here Hangul's: one line each, 1600 apart; the group's label two lines),
and compares where it is with Hangul's -- paragraph and offsets -- as it is written.

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
from tests.hancom_place import carry_down_offset, lay_out

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


def _floating(kind: str, tops: list[int] | None):
    title, make = SHAPES[kind]
    doc = HwpxDocument.new()
    doc.add_paragraph(f"떠 있는 개체 하나: {title}, 문단·단 기준 왼쪽·위 3000·2000")
    obj = make(doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, **FLOAT)
    doc.add_paragraph("1번")
    doc.add_paragraph("2번")
    if tops:
        lay_out(doc, tops)
    return doc, obj


def _arrow_line(tops: list[int] | None):
    doc = HwpxDocument.new()
    doc.add_paragraph("개체 하나: 수평선 12000, 끝(오른쪽)에 화살표")
    line = doc.shapes.add_line(0, 0, 12000, 0, paragraph=doc.add_paragraph("0번"))
    shape = line.element.find(f"{_HP}lineShape")
    shape.set("tailStyle", "ARROW")
    shape.set("tailSz", "MEDIUM_MEDIUM")
    line.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    if tops:
        lay_out(doc, tops)
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


#: (fixture, kind, Hangul's line tops of the label and the paragraphs under it, where Hangul put it)
CASES = [
    ("turned_fc_30", "fc", [0, 1600, 3200, 4800], "on the label at -272 (it starts above the page's first line)"),
    ("turned_fn_30", "fn", [0, 3200, 4800, 6400], "on the label (two lines) at 2285"),
    ("turned_fy_30", "fy", [0, 3200, 4800, 6400], "on the label (two lines) at 2745"),
    ("turned_fa_30", "fa", [0, 1600, 3200, 4800], "where it was, at 536 (not above its paragraph)"),
]


@pytest.mark.parametrize(("fixture", "kind", "tops", "where"), CASES, ids=[case[0] for case in CASES])
def test_a_turned_floating_shape_is_hung_where_hancom_hangs_it(fixture: str, kind: str, tops: list, where: str) -> None:
    doc, obj = _floating(kind, tops)
    obj.rotation = 30
    saved = HwpxDocument.open(HANCOM / f"{fixture}.hwpx")
    assert _where(doc) == _where(saved), where
    theirs = next(o for p in saved.paragraphs for o in p.objects)
    assert _same(_normalized(obj.element), _normalized(theirs.element)), where
    assert obj.paragraph.element is next(p.element for p in doc.paragraphs if obj.element in list(p.element.iter()))
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    assert _where(again) == _where(saved)


def test_a_resized_arrow_line_turned_above_the_first_paragraph_is_where_hancom_puts_it() -> None:
    doc, line = _arrow_line([0, 1600])
    line.resize(18000, 0)  # the resize drops its paragraph's line layout: the height above is no longer known
    line.rotation = 30
    saved = HwpxDocument.open(HANCOM / "turned_ha_s1_30.hwpx")
    assert _where(saved) == [(0, "line")] and _where(doc) == [(1, "line")]  # left on its paragraph, nothing guessed
    theirs = next(o for p in saved.paragraphs for o in p.objects)
    carry_down_offset(theirs.element, 0, 1, [1600])  # Hangul's -2900 on the label is -4500 on the paragraph below
    assert _same(_normalized(line.element), _normalized(theirs.element))


def test_without_a_line_layout_on_every_paragraph_in_between_it_is_not_hung() -> None:
    doc, obj = _floating("fn", [0, 3200, 4800, 6400])
    for child in [c for c in doc.paragraphs[0].element if str(c.tag).endswith("}linesegarray")]:
        doc.paragraphs[0].element.remove(child)  # the label changed: its layout gone
    obj.rotation = 30
    assert _where(doc) == [(1, "container")]
    assert obj.position.vertical_offset == -915


def test_a_picture_in_a_cells_only_paragraph_stays_on_it_measured_above_it() -> None:
    doc, picture = _cell_picture()
    picture.rotation = 30
    saved = HwpxDocument.open(HANCOM / "turned_cell_p_30.hwpx")
    theirs = saved.paragraphs[1].tables[0].cell(0, 0).paragraphs[0].objects[0]
    assert _same(_normalized(picture.element), _normalized(theirs.element))  # -1598
    assert not HwpxDocument.open(doc.to_bytes()).validate().issues


def test_without_a_line_layout_a_turned_shape_stays_on_its_paragraph() -> None:
    # the paragraphs' heights are not known (no hp:linesegarray): it is left measured from its own paragraph
    doc, obj = _floating("fc", None)
    obj.rotation = 30
    assert _where(doc) == [(1, "curve")]
    assert obj.position.vertical_offset == -1872
    obj.rotation = 0  # turned back where it began
    assert (obj.position.horizontal_offset, obj.position.vertical_offset) == (3000, 2000)


def test_a_turned_shape_hung_on_the_label_turns_back_to_where_it_began() -> None:
    doc, obj = _floating("fn", [0, 3200, 4800, 6400])
    obj.rotation = 30
    assert _where(doc) == [(0, "container")]
    obj.rotation = 0  # on the label now, measured from its top: where it began, 3200 + 2000 down
    assert _where(doc) == [(0, "container")]
    assert (obj.position.horizontal_offset, obj.position.vertical_offset) == (3000, 5200)
