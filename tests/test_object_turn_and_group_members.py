"""Turning a stretched object, resizing a turned one, and taking one member out of a group with the groups fitted
to what is left -- each the way Hancom-saved documents hold it."""

from __future__ import annotations

import math
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.model import Shape
from hwpx.oxml.container import ContainerMember
from hwpx.oxml.namespaces import HP

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


def _matrices(element) -> list[list[float]]:
    return [[float(m.get(k)) for k in ("e1", "e2", "e3", "e4", "e5", "e6")]
            for m in element.find(f"{HP}renderingInfo")]


def _apply(m: list[float], p: tuple[float, float]) -> tuple[float, float]:
    return m[0] * p[0] + m[1] * p[1] + m[2], m[3] * p[0] + m[4] * p[1] + m[5]


def _drawn(matrices: list[list[float]], point: tuple[float, float]) -> tuple[float, float]:
    """Where a top-level object's matrices draw *point* of its own geometry: scaled, turned, then moved."""

    trans, scale, rot = matrices
    return _apply(trans, _apply(rot, _apply(scale, point)))


# -- turning stretched objects ------------------------------------------------------------------------------

#: The public ``ta-pic-001-r.hwp`` (rhwp samples, saved by Hancom): a 49380 x 45840 picture drawn at
#: 13668 x 12686 and turned 34 degrees. Its box, centre and matrices as Hancom wrote them.
HANCOM_TURNED_PICTURE = {
    "size": (49380, 45840), "drawn": (13668, 12686), "angle": 34, "sz": (18425, 18160), "center": (9212, 9080),
    "matrices": [[1, 0, 730, 0, 1, 3694], [0.276792, 0, 0, 0, 0.276745, 0],
                 [0.829038, -0.559193, 6364.204761, 0.559193, 0.829038, -3694.39055]],
}


def test_a_stretched_picture_turns_as_hancom_turned_one() -> None:
    case = HANCOM_TURNED_PICTURE
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png", width=case["size"][0], height=case["size"][1])
    picture.resize(*case["drawn"])
    picture.set_rotation(case["angle"])
    element = picture.element
    size, info = element.find(f"{HP}sz"), element.find(f"{HP}rotationInfo")
    assert abs(int(size.get("width")) - case["sz"][0]) <= 1 and abs(int(size.get("height")) - case["sz"][1]) <= 1
    assert abs(int(info.get("centerX")) - case["center"][0]) <= 1
    assert abs(int(info.get("centerY")) - case["center"][1]) <= 1
    ours = _matrices(element)
    width, height = case["size"]
    for corner in ((0, 0), (width, 0), (width, height), (0, height), (width / 2, height / 3)):
        drawn, hancom = _drawn(ours, corner), _drawn(case["matrices"], corner)
        assert math.dist(drawn, hancom) < 1.5, (corner, drawn, hancom)
    again = _reopen(doc)
    assert again.media.pictures[0].rotation == 34


@pytest.mark.parametrize("angle", [30, 90, 135, 270])
def test_a_resized_shape_turns_and_fills_its_box(angle: int) -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png", width=8000, height=3000)
    picture.resize(width=4000, height=3000)  # drawn narrower than its own size: scaMatrix 0.5 x 1
    picture.set_rotation(angle)
    matrices = _matrices(picture.element)
    size = picture.element.find(f"{HP}sz")
    corners = [_drawn(matrices, c) for c in ((0, 0), (8000, 0), (8000, 3000), (0, 3000))]
    xs, ys = [x for x, _ in corners], [y for _, y in corners]
    assert abs(min(xs)) < 1.5 and abs(max(xs) - int(size.get("width"))) < 1.5
    assert abs(min(ys)) < 1.5 and abs(max(ys) - int(size.get("height"))) < 1.5
    edge = math.dist(corners[0], corners[1])
    assert abs(edge - 4000) < 1.5  # drawn 4000 wide, turned: a rectangle, not a stretched parallelogram


def test_a_turned_picture_resizes_and_crops_as_drawn() -> None:
    doc = HwpxDocument.new()
    turned = doc.add_picture(PNG, "png", width=6000, height=3000)
    turned.set_rotation(45)
    turned.resize(width=3000)
    assert turned.rotation == 45
    turned.set_rotation(0)
    assert (turned.width, turned.height) == (3000, 1500)
    cropped = doc.add_picture(PNG, "png", width=6000, height=3000)
    cropped.set_rotation(90)
    cropped.set_crop((0, 0, 3000, 0))
    assert (cropped.width, cropped.height) == (3000, 3000)  # turned 90 degrees: its box is its size turned
    cropped.set_rotation(0)
    assert (cropped.width, cropped.height) == (3000, 3000)
    _reopen(doc)


def test_a_flipped_object_and_a_group_still_refuse_to_turn() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = doc.sections[0].paragraphs[0].objects[0]
    for call in (lambda: group.set_rotation(30), lambda: group.members[1].set_rotation(30)):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code in {"shape-rotation-unsupported", "shape-group-member-unsupported"}


# -- taking a member out of a group --------------------------------------------------------------------------


def _group(doc: HwpxDocument) -> Shape:
    group = doc.sections[0].paragraphs[0].objects[0]
    assert isinstance(group, Shape) and group.shape_type == "container"
    return group


def _attrs(group: Shape, name: str) -> tuple[str | None, str | None]:
    node = group.element.find(f"{HP}{name}")
    return node.get("width"), node.get("height")


@pytest.mark.parametrize(("name", "factors"), [
    ("group_in_a_group.hwpx", (1, 1)),
    ("group_in_a_group_resized_in_width.hwpx", (2, 1)),
    ("group_in_a_group_resized_twice.hwpx", (2, 2)),
])
def test_a_member_of_a_group_in_a_hancom_group_leaves_and_the_groups_fit(name: str, factors) -> None:
    doc = HwpxDocument.open(HANCOM / name)
    before = _parts(doc.to_bytes())
    group = _group(doc)
    position = group.element.find(f"{HP}pos")
    left, top = int(position.get("horzOffset")), int(position.get("vertOffset"))
    inner = next(m for m in group.members if isinstance(m, Shape) and m.shape_type == "container")
    paragraph = group.paragraph.element
    inner.members[0].remove()  # the picture at the inner group's top left: both groups shrink
    # What is left: the other picture (8650, 300)-(17372, 3250) and the line (3050, 1575)-(13250, 1775).
    assert _attrs(group, "orgSz") == ("14322", "2950")
    assert _attrs(group, "sz") == (str(14322 * factors[0]), str(2950 * factors[1]))
    assert (int(position.get("horzOffset")), int(position.get("vertOffset"))) == (
        left + 3050 * factors[0], top + 300 * factors[1])
    offsets = [(m.element.find(f"{HP}offset").get("x"), m.element.find(f"{HP}offset").get("y")) for m in group.members]
    assert offsets == [("5600", "0"), ("0", "1275")]
    assert _attrs(inner, "orgSz") == ("8722", "2950")
    assert len(inner.members) == 1
    assert paragraph.find(f"{HP}linesegarray") is None
    after = _parts(_reopen(doc).to_bytes())
    changed = {part for part in before if before[part] != after.get(part)}
    assert changed <= {"Contents/section0.xml", "Contents/content.hpf", "Contents/header.xml"} | {
        part for part in before if part.startswith("BinData/")}


def test_a_member_that_does_not_reach_the_edge_leaves_the_group_as_it_is() -> None:
    doc = HwpxDocument.new()
    group = doc.add_paragraph("").add_container([
        ContainerMember.rect(0, 0, 4000, 2000),
        ContainerMember.ellipse(1000, 500, 1000, 1000),
        ContainerMember.rect(5000, 1000, 3000, 3000),
    ])
    sizes = _attrs(group, "orgSz")
    group.members[1].remove()
    assert _attrs(group, "orgSz") == sizes and len(group.members) == 2
    group.members[0].remove()  # the one at the top left: the rest moves to the origin
    assert _attrs(group, "orgSz") == ("3000", "3000")
    assert group.members[0].element.find(f"{HP}offset").get("x") == "0"
    _reopen(doc)


def test_a_group_made_with_a_group_inside_is_valid_and_its_inner_member_leaves() -> None:
    doc = HwpxDocument.new()
    inner = ContainerMember.group(0, 0, [ContainerMember.rect(0, 0, 5000, 2500),
                                         ContainerMember.ellipse(5500, 500, 3000, 1500)])
    group = doc.add_paragraph("").add_container([inner, ContainerMember.rect(1000, 3000, 9000, 1200)],
                                                treat_as_char=False)
    assert not any(node.get("_treatAsChar") is not None for node in group.element.iter())  # no builder marker left
    group.members[0].members[0].remove()  # the rectangle at the top left of both groups
    inner_group = group.members[0]
    assert inner_group.element.find(f"{HP}offset").attrib == {"x": "4500", "y": "0"}
    assert _attrs(inner_group, "orgSz") == ("3000", "1500")
    # What is left: the ellipse (5500, 500)-(8500, 2000) and the band (1000, 3000)-(10000, 4200).
    assert _attrs(group, "orgSz") == ("9000", "3700")
    assert group.members[1].element.find(f"{HP}offset").attrib == {"x": "0", "y": "2500"}
    position = group.element.find(f"{HP}pos")
    assert (int(position.get("horzOffset")), int(position.get("vertOffset"))) == (1000, 500)
    _reopen(doc)


def test_the_last_member_and_a_turned_group_refuse() -> None:
    doc = HwpxDocument.new()
    group = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                  ContainerMember.rect(5000, 0, 2000, 2000)])
    group.members[0].remove()
    with pytest.raises(HwpxValueError) as caught:
        group.members[0].remove()
    assert caught.value.code == "shape-group-member-unsupported"
    assert "only member" in caught.value.context["reason"]
    turned = doc.add_paragraph("").add_container([ContainerMember.rect(0, 0, 4000, 2000),
                                                   ContainerMember.rect(5000, 0, 2000, 2000)])
    turned.element.find(f"{HP}rotationInfo").set("angle", "30")
    with pytest.raises(HwpxValueError) as caught:
        turned.members[0].remove()
    assert caught.value.code == "shape-group-member-unsupported"
    assert len(turned.members) == 2


def test_a_removed_member_takes_its_image_and_lets_connectors_go() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = _group(doc)
    inner = group.members[0]
    picture = inner.members[0]
    item = picture.item_id
    assert [p.item_id for p in doc.media.pictures].count(item) == 1
    picture.remove()
    assert item not in {str(i) for i in doc.media.images}
    _reopen(doc)


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}
