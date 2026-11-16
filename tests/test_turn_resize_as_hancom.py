"""A turned (and flipped) object resized, a resized object flipped, a group holding a group flipped and a corner arc
flipped -- each built by python-hwpx from scratch and changed by python-hwpx alone, compared with what Hancom 2024
saved after doing the same to the same document.

``tests/fixtures/hancom_saved/one_*.hwpx`` (see its README): one-object documents python-hwpx made (a group of a
6000 x 6000 rectangle and a 9000 x 5000 text box, a 12000 x 6000 picture, a 12000 x 6000 text box, a group holding a
group, an arc at its top-left and at its bottom-right corner, a curve), changed by Hangul 2024 through its public
automation in the order the names say (``f``/``v`` its flip commands, ``30`` its object dialog's angle, ``s`` the
object properties' width and height: for a turned object the box around it), then saved. Hangul resizes a turned
object's box along the page: ``scaMatrix`` = L^-1 D L moved by L^-1 (D - I) t, its turn and move kept. Two plans of
the batch are left out: Hangul read a turned object's properties as another size just before resizing it (its log
shows 9835 x 8796 and 9836 x 9836), and the saved results follow no one rule with the others.

Left out of the comparison as in test_flip_shapes_and_groups.py: ids, ``hp:pos`` offsets, ``curSz`` (Hangul writes 0
on an axis left alone), line layout caches, an empty ``hp:shapeComment``, the image's measured size and its item
name; numbers within 0.01.
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


def _group(doc, paragraph):
    return paragraph.add_container([ContainerMember.rect(0, 0, 6000, 6000),
                                    ContainerMember.text_box(7000, 0, 9000, 5000, "묶음 안 글상자")],
                                   treat_as_char=False)


def _picture(doc, paragraph):
    return paragraph.add_picture(doc.media.add_image(_png(40, 20), "png"), width=12000, height=6000)


def _text_box(doc, paragraph):
    box = paragraph.add_rectangle(12000, 6000)
    box.set_draw_text("가나다 ABC 글상자")
    return box


def _nested(doc, paragraph):
    return paragraph.add_container([
        ContainerMember.rect(0, 0, 5000, 5000),
        ContainerMember.group(6000, 0, [ContainerMember.rect(0, 0, 3000, 3000),
                                        ContainerMember.ellipse(4000, 1000, 3000, 3000)])], treat_as_char=False)


SOURCES = {
    "g": _group, "p": _picture, "r": _text_box, "n": _nested,
    "ac": lambda doc, p: doc.shapes.add_arc(8000, 8000, corner="BOTTOM_RIGHT", paragraph=p),
    "a": lambda doc, p: doc.shapes.add_arc(8000, 8000, paragraph=p),
    "c": lambda doc, p: doc.shapes.add_curve([(0, 0), (30, 20), (60, 0)], paragraph=p),
}
#: (fixture, source, steps): f/v toggle a flip as Hangul's commands do, rN turns, sWxH resizes.
CASES = [
    ("one_g_f_30_s1", "g", ["f", "r30", "s24000x6000"]),
    ("one_g_30_f_s2", "g", ["r30", "f", "s16000x16000"]),
    ("one_g_v_30_s1", "g", ["v", "r30", "s24000x6000"]),
    ("one_g_fv_s1", "g", ["f", "v", "s24000x6000"]),
    ("one_p_f_30_s2", "p", ["f", "r30", "s12000x12000"]),
    ("one_p_30_f_s1", "p", ["r30", "f", "s18000x6000"]),
    ("one_p_30_s1", "p", ["r30", "s18000x6000"]),
    ("one_r_30_s1", "r", ["r30", "s18000x6000"]),
    ("one_r_f_30_s1", "r", ["f", "r30", "s18000x6000"]),
    ("one_n_v", "n", ["v"]),
    ("one_n_30_f", "n", ["r30", "f"]),
    ("one_n_s1_f", "n", ["s19500x5000", "f"]),
    ("one_ac_f", "ac", ["f"]),
    ("one_a_s_f", "a", ["s12000x8000", "f"]),
    ("one_c_s_f", "c", ["s24000x5669", "f"]),
]


def _only_object(doc: HwpxDocument):
    objects = [obj for paragraph in doc.paragraphs for obj in paragraph.objects]
    assert len(objects) == 1
    return objects[0]


def _normalized(element, path: str = "") -> list[str]:
    name = str(element.tag).rsplit("}", 1)[-1]
    if name in {"curSz", "linesegarray", "imgDim", "imgClip"} or (
            name == "shapeComment" and not (element.text or "").strip()):
        return []
    attributes = {key: ("0" if value == "-0" else value) for key, value in element.attrib.items()
                  if key not in {"id", "instid", "binaryItemIDRef"}
                  and not (name == "pos" and key in {"horzOffset", "vertOffset"})}
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
    else:
        obj.resize(*(int(value) for value in step[1:].split("x")))


@pytest.mark.parametrize(("fixture", "source", "steps"), CASES, ids=[case[0] for case in CASES])
def test_python_hwpx_from_scratch_writes_what_hancom_saved(fixture: str, source: str, steps: list) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    obj = SOURCES[source](doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    for step in steps:
        _do(obj, step)
    hancom = _only_object(HwpxDocument.open(HANCOM / f"{fixture}.hwpx"))
    assert (obj.rotation, obj.flip_horizontal, obj.flip_vertical) == \
        (hancom.rotation, hancom.flip_horizontal, hancom.flip_vertical)
    assert _same(_normalized(obj.element), _normalized(hancom.element))
    again = _only_object(HwpxDocument.open(doc.to_bytes()))
    assert (again.rotation, again.flip_horizontal, again.flip_vertical) == \
        (obj.rotation, obj.flip_horizontal, obj.flip_vertical)
