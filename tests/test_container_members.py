# SPDX-License-Identifier: Apache-2.0
"""Group members beyond rectangles, ellipses and polygons: lines, text boxes, pictures and groups in groups.

Hancom's groups (1,628 in the real corpus, 4,473 members): every member drops the ``sz``/``pos``/
``outMargin``/``shapeComment`` tail, has ``id="0"``, ``zOrder="0"``, ``numberingType="NONE"`` and
``textWrap="TOP_AND_BOTTOM"``, and its ``groupLevel`` is its depth (1, 2, 3 ...). A group in a group is such
a member with its own envelope and members; only the outermost group has the tail and
``numberingType="PICTURE"``. Pictures (1,277 members) keep ``img``/``imgRect``/``imgClip``/``inMargin``/
``imgDim``/``effects``; text boxes (1,658 rectangle members) keep ``drawText`` before the corner points.
"""

from __future__ import annotations

import struct
import zipfile
import zlib
import io
import xml.etree.ElementTree as ET

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml import ContainerMember

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
_TAIL = ("sz", "pos", "outMargin", "shapeComment")


def _png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\0" + b"\xc8\x3c\x3c" * 4 for _ in range(3))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 3, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _saved_group(doc: HwpxDocument) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        root = ET.fromstring(archive.read("Contents/section0.xml"))
    group = root.find(f".//{HP}container")
    assert group is not None
    return group


def _local(element: ET.Element) -> str:
    return element.tag.split("}")[-1]


def _members(group: ET.Element) -> list[ET.Element]:
    return [child for child in group if _local(child) in {"rect", "ellipse", "polygon", "line", "pic", "container"}]


def test_a_line_member_keeps_its_ends_relative_to_its_top_left() -> None:
    doc = HwpxDocument.new()
    doc.shapes.add_container([ContainerMember.rect(0, 0, 6000, 4000), ContainerMember.line(12000, 3000, 6000, 1000)])

    line = _members(_saved_group(doc))[1]

    assert _local(line) == "line"
    assert (line.find(f"{HP}offset").get("x"), line.find(f"{HP}offset").get("y")) == ("6000", "1000")
    assert (line.find(f"{HC}startPt").get("x"), line.find(f"{HC}startPt").get("y")) == ("6000", "2000")
    assert (line.find(f"{HC}endPt").get("x"), line.find(f"{HC}endPt").get("y")) == ("0", "0")
    assert (line.find(f"{HP}orgSz").get("width"), line.find(f"{HP}orgSz").get("height")) == ("6000", "2000")


def test_text_box_members_get_their_text_with_paragraph_ids_unused_in_the_section() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("before")
    doc.shapes.add_container([
        ContainerMember.text_box(0, 0, 12000, 3000, "first"),
        ContainerMember.text_box(0, 4000, 9000, 3000, "second", vert_align="TOP", margin={"left": 0}),
    ])

    group = _saved_group(doc)
    boxes = _members(group)
    texts = ["".join(t.text or "" for t in box.iter(f"{HP}t")) for box in boxes]
    assert texts == ["first", "second"]
    children = [_local(child) for child in boxes[0]]
    assert children.index("drawText") < children.index("pt0")
    assert [box.find(f"{HP}drawText").get("lastWidth") for box in boxes] == ["12000", "9000"]
    assert boxes[1].find(f".//{HP}subList").get("vertAlign") == "TOP"
    assert boxes[1].find(f".//{HP}textMargin").get("left") == "0"
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        root = ET.fromstring(archive.read("Contents/section0.xml"))
    ids = [p.get("id") for p in root.iter(f"{HP}p")]
    assert len(ids) == len(set(ids))


def test_a_bad_text_alignment_is_refused_before_the_document_changes() -> None:
    doc = HwpxDocument.new()
    before = doc.to_bytes()

    with pytest.raises(HwpxValueError):
        ContainerMember.text_box(0, 0, 1000, 1000, "x", vert_align="MIDDLE")

    assert doc.to_bytes() == before


def test_a_picture_member_shows_the_image_it_was_given() -> None:
    doc = HwpxDocument.new()
    image = doc.media.add_image(_png(), "png")
    doc.shapes.add_container([ContainerMember.picture(0, 0, 8000, 6000, image), ContainerMember.rect(9000, 0, 3000, 3000)])

    picture = _members(_saved_group(doc))[0]

    assert _local(picture) == "pic"
    assert picture.find(f"{HC}img").get("binaryItemIDRef") == str(image)
    for name in ("imgRect", "imgClip", "inMargin", "imgDim", "effects"):
        assert picture.find(f"{HP}{name}") is not None, name
    assert all(picture.find(f"{HP}{name}") is None for name in _TAIL)


def test_a_picture_member_needs_an_image() -> None:
    with pytest.raises(HwpxValueError, match="binary item"):
        ContainerMember.picture(0, 0, 1000, 1000, " ")


def test_groups_in_groups_take_their_depth_as_group_level() -> None:
    doc = HwpxDocument.new()
    image = doc.media.add_image(_png(), "png")
    doc.shapes.add_container([
        ContainerMember.group(1000, 1000, [
            ContainerMember.group(0, 0, [ContainerMember.rect(0, 0, 4000, 2000), ContainerMember.picture(4500, 0, 4000, 2000, image)]),
            ContainerMember.line(0, 2500, 8500, 2500),
        ]),
        ContainerMember.rect(9500, 1000, 3000, 3000),
    ])

    group = _saved_group(doc)
    assert (group.get("groupLevel"), group.get("numberingType")) == ("0", "PICTURE")
    assert all(group.find(f"{HP}{name}") is not None for name in _TAIL)
    inner, rect = _members(group)
    deeper, line = _members(inner)
    assert [m.get("groupLevel") for m in (inner, rect, deeper, line)] == ["1", "1", "2", "2"]
    assert [m.get("groupLevel") for m in _members(deeper)] == ["3", "3"]
    for member in (inner, rect, deeper, line, *_members(deeper)):
        assert (member.get("id"), member.get("zOrder"), member.get("numberingType"), member.get("textWrap")) == (
            "0", "0", "NONE", "TOP_AND_BOTTOM")
        assert all(member.find(f"{HP}{name}") is None for name in _TAIL)
    # the outer group spans its members; the inner group sits at its local corner
    assert (group.find(f"{HP}orgSz").get("width"), group.find(f"{HP}orgSz").get("height")) == ("11500", "3000")
    assert (inner.find(f"{HP}offset").get("x"), inner.find(f"{HP}offset").get("y")) == ("0", "0")
    assert (rect.find(f"{HP}offset").get("x"), rect.find(f"{HP}offset").get("y")) == ("8500", "0")
    assert (inner.find(f"{HP}orgSz").get("width"), inner.find(f"{HP}orgSz").get("height")) == ("8500", "2501")  # a level line is 1 high


def test_a_group_inside_needs_members() -> None:
    with pytest.raises(HwpxValueError, match="at least one member"):
        ContainerMember.group(0, 0, [])


def test_a_mixed_group_round_trips_and_passes_open_safety(tmp_path) -> None:
    doc = HwpxDocument.new()
    image = doc.media.add_image(_png(), "png")
    doc.shapes.add_container([
        ContainerMember.picture(0, 0, 8000, 6000, image),
        ContainerMember.text_box(8500, 0, 9000, 3000, "caption", fill_color="#DDEEFF"),
        ContainerMember.line(8500, 3500, 17500, 3500),
        ContainerMember.group(8500, 4000, [ContainerMember.ellipse(0, 0, 2000, 2000)]),
    ], treat_as_char=False)
    path = tmp_path / "mixed.hwpx"
    doc.save_to_path(path)

    reopened = HwpxDocument.open(path)

    group = _saved_group(reopened)
    assert [_local(m) for m in _members(group)] == ["pic", "rect", "line", "container"]
    assert "caption" in "".join(t.text or "" for t in group.iter(f"{HP}t"))


def test_the_members_of_a_group_inside_go_where_that_group_goes() -> None:
    # Hancom draws every shape of a group at its own transMatrix in the outermost group's space: a group
    # inside at (8500, 4000) keeps its members there too, a level deeper at (8500 + 500, 4000 + 1000).
    doc = HwpxDocument.new()
    doc.shapes.add_container([
        ContainerMember.rect(0, 0, 8000, 6000),
        ContainerMember.group(8500, 4000, [
            ContainerMember.ellipse(0, 0, 2000, 2000),
            ContainerMember.group(500, 1000, [ContainerMember.rect(0, 0, 1000, 1000), ContainerMember.rect(1500, 0, 1000, 1000)]),
        ]),
    ])

    def place(element: ET.Element) -> tuple[str, str, str, str]:
        offset, trans = element.find(f"{HP}offset"), element.find(f"{HP}renderingInfo/{HC}transMatrix")
        return offset.get("x"), offset.get("y"), trans.get("e3"), trans.get("e6")

    _, inner = _members(_saved_group(doc))
    ellipse, deeper = _members(inner)
    assert place(inner) == ("8500", "4000", "8500", "4000")
    assert place(ellipse) == ("8500", "4000", "8500", "4000")
    assert place(deeper) == ("9000", "5000", "9000", "5000")
    assert [place(m) for m in _members(deeper)] == [("9000", "5000", "9000", "5000"), ("10500", "5000", "10500", "5000")]
