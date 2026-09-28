# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.shapes`."""

from __future__ import annotations

import re
import warnings
import zipfile
from pathlib import Path

import pytest

from hwpx import model
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.oxml import ContainerMember

CHART = b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'
MEMBERS = {
    "add_line": ((), model.Shape),
    "add_rectangle": ((), model.Shape),
    "add_ellipse": ((), model.Shape),
    "add_polygon": (([(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)],), model.Shape),
    "add_arc": ((), model.Shape),
    "add_chart": ((CHART,), model.InlineObject),
    "add_equation": (("x=1",), model.InlineObject),
    "add_raw": (("rect",), model.InlineObject),
    "add_control": ((), model.InlineObject),
}


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


@pytest.mark.parametrize("name", sorted(MEMBERS))
def test_every_shape_verb_delegates_and_returns_a_model_type(
    name: str, document: HwpxDocument
) -> None:
    args, expected = MEMBERS[name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # 탈출구는 스스로 위험을 경고한다
        created = getattr(document.shapes, name)(*args, section=0)
    assert isinstance(created, expected)


@pytest.mark.parametrize("name", sorted(MEMBERS))
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_bad_sections_are_typed_errors(name, kwargs, code, document) -> None:
    args, _ = MEMBERS[name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(HwpxError) as excinfo:
            getattr(document.shapes, name)(*args, **kwargs)
    assert excinfo.value.code == code


def test_add_raw_is_named_for_what_it_is(document: HwpxDocument) -> None:
    """탈출구는 이름이 탈출구임을 말해야 한다 — 5.x 는 ``add_shape`` 였다."""

    assert hasattr(document.shapes, "add_raw")
    with pytest.warns(UserWarning) as record:
        document.shapes.add_raw("rect", section=0)
    assert "Hancom refuses to open" in str(record[0].message)


def test_the_moved_root_names_still_answer(document: HwpxDocument) -> None:
    for name, args in [("add_line", ()), ("add_rectangle", ()), ("add_chart", (CHART,))]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with pytest.warns(DeprecationWarning):
                getattr(document, name)(*args, section_index=0)


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
# A 1x1 PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
HWPXLIB = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


@pytest.mark.parametrize(
    "name",
    [
        "reader_writer__SimpleArc.hwpx",
        "reader_writer__SimpleCurve.hwpx",
        "reader_writer__SimpleLine.hwpx",
        "reader_writer__SimplePolygon.hwpx",
        "reader_writer__SimpleRectangle.hwpx",
    ],
)
def test_shapes_drawn_in_hancom_have_a_33_line(name: str) -> None:
    # One shape drawn and saved in Hancom per file: its line is Hancom's
    # default, 0.12 mm (33 HWPUNIT).
    with zipfile.ZipFile(HWPXLIB / name) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert set(re.findall(r'<hp:lineShape\b[^>]*\bwidth="(\d+)"', section)) == {"33"}


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("add_line", ()),
        ("add_rectangle", ()),
        ("add_ellipse", ()),
        ("add_arc", ()),
        ("add_polygon", ([(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)],)),
    ],
)
def test_a_new_shape_draws_hancoms_default_line(name: str, args: tuple, document: HwpxDocument) -> None:
    shape = getattr(document.shapes, name)(*args)
    [line] = shape.element.iter(f"{HP}lineShape")
    assert line.get("width") == "33"


_SHAPE_TAGS = ("rect", "ellipse", "line", "arc", "polygon", "curve", "connectLine", "container")


@pytest.mark.parametrize(
    "name",
    [
        "reader_writer__SimpleArc.hwpx",
        "reader_writer__SimpleContainer.hwpx",
        "reader_writer__SimpleCurve.hwpx",
        "reader_writer__SimpleEllipse.hwpx",
        "reader_writer__SimpleLine.hwpx",
        "reader_writer__SimplePolygon.hwpx",
        "reader_writer__SimpleRectangle.hwpx",
    ],
)
def test_shapes_drawn_in_hancom_say_how_text_goes_around_them(name: str) -> None:
    # Every shape Hancom saves carries textWrap and textFlow; a group's members
    # are TOP_AND_BOTTOM. Every brush carries alpha.
    with zipfile.ZipFile(HWPXLIB / name) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    shapes = re.findall(rf"<hp:(?:{'|'.join(_SHAPE_TAGS)})\b[^>]*>", section)
    assert shapes
    for shape in shapes:
        assert re.search(r'\btextWrap="[A-Z_]+"', shape) and 'textFlow="BOTH_SIDES"' in shape, shape
        if 'groupLevel="1"' in shape:
            assert 'textWrap="TOP_AND_BOTTOM"' in shape, shape
    assert all("alpha=" in brush for brush in re.findall(r"<hc:winBrush\b[^>]*>", section))


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("add_line", ()),
        ("add_rectangle", ()),
        ("add_ellipse", ()),
        ("add_arc", ()),
        ("add_polygon", ([(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)],)),
    ],
)
def test_a_new_shape_says_how_text_goes_around_it(name: str, args: tuple, document: HwpxDocument) -> None:
    shape = getattr(document.shapes, name)(*args)
    assert (shape.element.get("textWrap"), shape.element.get("textFlow")) == ("SQUARE", "BOTH_SIDES")


def test_a_group_member_lets_the_group_place_it(document: HwpxDocument) -> None:
    group = document.shapes.add_container(
        [ContainerMember.rect(0, 0, 1000, 1000), ContainerMember.ellipse(1000, 0, 1000, 1000)]
    )
    members = [child for child in group.element if child.get("groupLevel") == "1"]
    assert len(members) == 2
    assert {member.get("textWrap") for member in members} == {"TOP_AND_BOTTOM"}
    assert (group.element.get("textWrap"), group.element.get("textFlow")) == ("SQUARE", "BOTH_SIDES")


def test_a_picture_keeps_the_text_wrap_it_was_given(document: HwpxDocument) -> None:
    # A seal stamped in front of the text must not push the text aside.
    paragraph = document.add_paragraph("")
    item = document.media.add_image(_PNG, "png")
    placed = paragraph.add_picture(str(item), treat_as_char=False, text_wrap="IN_FRONT_OF_TEXT")
    plain = paragraph.add_picture(str(item))

    assert (placed.element.get("textWrap"), placed.element.get("textFlow")) == ("IN_FRONT_OF_TEXT", "BOTH_SIDES")
    assert plain.element.get("textWrap") == "SQUARE"


def test_a_filled_shape_writes_its_brush_as_hancom_does(document: HwpxDocument) -> None:
    shape = document.shapes.add_rectangle(fill_color="#F1CB7E")
    [brush] = shape.element.iter(f"{HC}winBrush")
    assert brush.attrib == {"faceColor": "#F1CB7E", "hatchColor": "#FFFFFF", "alpha": "0"}
