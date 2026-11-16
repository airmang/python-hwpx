"""A turned (and flipped) object resized to its own size, a resized turned group flipped, a group holding a group
flipped and a corner arc flipped -- each built by python-hwpx from scratch and changed by python-hwpx alone, compared
with what Hancom 2024 saved after doing the same (or, for ``resize``, after resizing first) to the same document.

``tests/fixtures/hancom_saved/one_*.hwpx`` (see its README): one-object documents python-hwpx made (a group of a
6000 x 6000 rectangle and a 9000 x 5000 text box, a 12000 x 6000 picture, a 12000 x 6000 text box, a group holding a
group, an arc at its top-left and at its bottom-right corner, a curve), changed by Hangul 2024 through its public
automation in the order the names say (``f``/``v`` its flip commands, ``30`` its object dialog's angle, ``s`` the
object properties' width and height), then saved.

``resize`` takes an object's own size, turned or not: python-hwpx turning first and resizing after writes what Hangul
writes resizing first and turning after. Hangul's object properties take a turned object's box instead and stretch
the object along the page into a parallelogram (``one_p_30_s1``, ``one_r_30_s1``, ``one_g_f_30_s1``): python-hwpx
reads that form and keeps it, but does not resize, turn or flip it again.

Left out of the comparison as in test_flip_shapes_and_groups.py: ids, ``hp:pos`` offsets, ``curSz`` (Hangul writes 0
on an axis left alone), line layout caches, an empty ``hp:shapeComment``, the image's measured size and its item
name; numbers within 0.01.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
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
#: (fixture Hangul saved, source, python-hwpx's steps): f/v toggle a flip as Hangul's commands do, rN turns, sWxH
#: resizes. ``one_g_s1_30_f``/``one_g_s2_30_v`` were resized, turned and flipped by Hangul; python-hwpx gets there in
#: any order, ``resize`` taking the group's own size.
CASES = [
    ("one_g_s1_30_f", "g", ["s24000x6000", "r30", "f"]),
    ("one_g_s1_30_f", "g", ["r30", "s24000x6000", "f"]),
    ("one_g_s1_30_f", "g", ["r30", "f", "s24000x6000"]),
    ("one_g_s2_30_v", "g", ["s16000x16000", "r30", "v"]),
    ("one_g_s2_30_v", "g", ["r30", "s16000x16000", "v"]),
    ("one_g_s2_30_v", "g", ["r30", "v", "s16000x16000"]),
    ("one_g_fv_s1", "g", ["f", "v", "s24000x6000"]),
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


def _made(source: str, steps: list[str]):
    doc = HwpxDocument.new()
    doc.add_paragraph("원본")
    obj = SOURCES[source](doc, doc.add_paragraph("0번"))
    obj.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    for step in steps:
        _do(obj, step)
    return doc, obj


@pytest.mark.parametrize(("fixture", "source", "steps"), CASES, ids=[f"{c[0]}-{'-'.join(c[2])}" for c in CASES])
def test_python_hwpx_from_scratch_writes_what_hancom_saved(fixture: str, source: str, steps: list) -> None:
    doc, obj = _made(source, steps)
    hancom = _only_object(HwpxDocument.open(HANCOM / f"{fixture}.hwpx"))
    assert (obj.rotation, obj.flip_horizontal, obj.flip_vertical) == \
        (hancom.rotation, hancom.flip_horizontal, hancom.flip_vertical)
    assert _same(_normalized(obj.element), _normalized(hancom.element))
    again = _only_object(HwpxDocument.open(doc.to_bytes()))
    assert (again.rotation, again.flip_horizontal, again.flip_vertical) == \
        (obj.rotation, obj.flip_horizontal, obj.flip_vertical)


#: Turned (and flipped) first, resized after: the object resized first and turned (and flipped) after, its own size
#: the size given -- a turned rectangle, picture or group stays a rectangle turned, not a parallelogram.
SAME_AS_RESIZED_FIRST = [
    ("p", ["r30", "s18000x6000"], ["s18000x6000", "r30"]),
    ("p", ["r30", "s12000x12000"], ["s12000x12000", "r30"]),
    ("p", ["f", "r30", "s6000x6000"], ["f", "s6000x6000", "r30"]),
    ("p", ["r30", "f", "s18000x6000"], ["f", "s18000x6000", "r330"]),
    ("r", ["r30", "s18000x6000"], ["s18000x6000", "r30"]),
    ("g", ["r30", "s24000x6000"], ["s24000x6000", "r30"]),
    ("g", ["f", "r30", "s24000x6000"], ["s24000x6000", "r330", "f"]),
]


@pytest.mark.parametrize(("source", "turned_first", "resized_first"), SAME_AS_RESIZED_FIRST,
                         ids=["-".join([c[0], *c[1]]) for c in SAME_AS_RESIZED_FIRST])
def test_resize_takes_a_turned_objects_own_size(source: str, turned_first: list, resized_first: list) -> None:
    _, ours = _made(source, turned_first)
    _, theirs = _made(source, resized_first)
    assert (ours.rotation, ours.flip_horizontal, ours.flip_vertical) == \
        (theirs.rotation, theirs.flip_horizontal, theirs.flip_vertical)
    assert _same(_normalized(ours.element), _normalized(theirs.element))
    scale = ours.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}renderingInfo")[1]
    assert abs(float(scale.get("e2"))) < 1e-6 and abs(float(scale.get("e4"))) < 1e-6  # not skewed


def test_one_size_alone_keeps_a_turned_objects_own_aspect_ratio() -> None:
    _, picture = _made("p", ["r30"])
    picture.resize(6000)
    picture.rotation = 0
    assert (picture.width, picture.height) == (6000, 3000)


@pytest.mark.parametrize("fixture", ["one_p_30_s1", "one_r_30_s1", "one_g_f_30_s1"])
def test_an_object_hancom_stretched_along_the_page_is_read_and_kept_but_not_changed_again(fixture: str) -> None:
    path = HANCOM / f"{fixture}.hwpx"
    doc = HwpxDocument.open(path)
    obj = _only_object(doc)
    # Hangul's object properties resized the turned object's box (18000 x 6000, 24000 x 6000): its scaMatrix skews
    assert (obj.rotation, obj.width, obj.height) == ((30, 24000, 6000) if fixture == "one_g_f_30_s1" else
                                                     (30, 18000, 6000))
    assert obj.flip_horizontal is (fixture == "one_g_f_30_s1") and obj.flip_vertical is False
    saved = zipfile.ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/section0.xml")
    assert saved == zipfile.ZipFile(path).read("Contents/section0.xml")
    for change in (lambda: obj.resize(12000, 6000), lambda: setattr(obj, "rotation", 0),
                   lambda: setattr(obj, "flip_vertical", True)):
        with pytest.raises(HwpxValueError) as caught:
            change()
        assert caught.value.code in ("shape-rotation-unsupported", "shape-flip-unsupported")
    assert zipfile.ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/section0.xml") == saved
