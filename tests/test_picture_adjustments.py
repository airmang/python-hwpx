"""A new picture's image adjustments (brightness, contrast, effect, transparency) and border, as Hancom keeps
and draws them."""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)

#: The arguments the fixture's picture was made with, before Hancom opened and saved it again.
FIXTURE_ARGS = {"brightness": 20, "contrast": -30, "effect": "GRAY_SCALE", "alpha": 64, "line_color": "#000000",
                "line_width": 141}


def _hancom_picture() -> etree._Element:
    with zipfile.ZipFile(FIXTURES / "picture_adjusted_and_bordered.hwpx") as package:
        root = etree.fromstring(package.read("Contents/section0.xml"))
    picture = root.find(f".//{HP}pic")
    assert picture is not None
    return picture


def test_a_new_picture_is_unadjusted_and_borderless_by_default() -> None:
    picture = HwpxDocument.new().add_picture(PNG_1X1, "png", width=20000, height=10000).element

    image = picture.find(f"{HC}img")
    assert (image.get("bright"), image.get("contrast"), image.get("effect"), image.get("alpha")) == (
        "0", "0", "REAL_PIC", "0")
    assert picture.find(f"{HP}lineShape") is None


def test_the_adjustments_and_border_are_written_as_hancom_keeps_them() -> None:
    picture = HwpxDocument.new().add_picture(PNG_1X1, "png", width=20000, height=10000, **FIXTURE_ARGS).element
    hancom = _hancom_picture()

    for name in ("bright", "contrast", "effect", "alpha"):
        assert picture.find(f"{HC}img").get(name) == hancom.find(f"{HC}img").get(name)
    border, kept = picture.find(f"{HP}lineShape"), hancom.find(f"{HP}lineShape")
    for name in ("color", "width", "style"):
        assert border.get(name) == kept.get(name)
    # right before the image's rectangle, as the schema orders a picture's children and Hancom's pictures have it
    children = [etree.QName(child).localname for child in picture]
    assert children[children.index("imgRect") - 1] == "lineShape"


def test_a_paragraph_takes_the_same_arguments_and_the_effect_in_any_case() -> None:
    document = HwpxDocument.new()
    item = document.media.add_image(PNG_1X1, "png")
    picture = document.add_paragraph("").add_picture(str(item), effect="black_white", alpha=255,
                                                     line_color="ff0000").element

    assert picture.find(f"{HC}img").get("effect") == "BLACK_WHITE"
    assert picture.find(f"{HC}img").get("alpha") == "255"
    assert (picture.find(f"{HP}lineShape").get("color"), picture.find(f"{HP}lineShape").get("width")) == (
        "#FF0000", "33")


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"brightness": 101}, "shape-picture-image-value"),  # drawn as at 100
        ({"brightness": -101}, "shape-picture-image-value"),
        ({"contrast": 101}, "shape-picture-image-value"),  # drawn with its colours turned over
        ({"contrast": -101}, "shape-picture-image-value"),  # drawn grey
        ({"alpha": 256}, "shape-picture-image-value"),  # saved as 0
        ({"alpha": -1}, "shape-picture-image-value"),
        ({"brightness": True}, "shape-picture-image-value"),
        ({"contrast": 1.5}, "shape-picture-image-value"),
        ({"effect": "PATTERN8x8"}, "shape-picture-image-value"),  # saved as REAL_PIC
        ({"line_color": "#000000", "line_width": -1}, "shape-picture-border-value"),
        ({"line_color": "#000000", "line_width": "33"}, "shape-picture-border-value"),
        ({"line_width": -1}, "shape-picture-border-value"),  # without a colour too: not dropped quietly
        ({"line_color": "red"}, "style-color-invalid"),
    ],
)
def test_a_value_hancom_does_not_draw_is_refused_before_anything_is_added(arguments, code) -> None:
    document = HwpxDocument.new()
    paragraphs, images = len(document.paragraphs), len(document.media.images)

    with pytest.raises(HwpxValueError) as caught:
        document.add_picture(PNG_1X1, "png", **arguments)

    assert caught.value.code == code
    assert (len(document.paragraphs), len(document.media.images)) == (paragraphs, images)


def test_a_crop_cuts_the_sides_at_the_same_scale_as_hancom_keeps_it() -> None:
    # 20000 x 10000 with 5000 cut from the left and right and 2500 from the top and bottom: drawn 10000 x 5000,
    # the whole picture's size in hp:imgDim and the part kept in hp:imgClip
    picture = HwpxDocument.new().add_picture(PNG_1X1, "png", width=20000, height=10000,
                                             crop=(5000, 2500, 5000, 2500)).element
    with zipfile.ZipFile(FIXTURES / "picture_cropped.hwpx") as package:
        hancom = etree.fromstring(package.read("Contents/section0.xml")).find(f".//{HP}pic")

    for name in ("orgSz", "sz", "imgClip", "imgDim"):
        mine, kept = picture.find(f"{HP}{name}"), hancom.find(f"{HP}{name}")
        assert {key: mine.get(key) for key in kept.attrib if key in mine.attrib} == {
            key: kept.get(key) for key in kept.attrib if key in mine.attrib}, name
    assert (picture.find(f"{HP}sz").get("width"), picture.find(f"{HP}sz").get("height")) == ("10000", "5000")
    assert [(pt.get("x"), pt.get("y")) for pt in picture.find(f"{HP}imgRect")] == [
        ("0", "0"), ("10000", "0"), ("10000", "5000"), ("0", "5000")]


@pytest.mark.parametrize("crop", [(10000, 0, 10000, 0), (0, 5000, 0, 5000), (0, 0, 0), (-1, 0, 0, 0),
                                  (0, 0, 0, True), (0.5, 0, 0, 0), "abcd"])
def test_a_crop_that_is_not_four_cuts_leaving_some_picture_is_refused(crop) -> None:
    document = HwpxDocument.new()
    paragraphs, images = len(document.paragraphs), len(document.media.images)

    with pytest.raises(HwpxValueError) as caught:
        document.add_picture(PNG_1X1, "png", width=20000, height=10000, crop=crop)

    assert caught.value.code == "shape-picture-crop-value"
    assert (len(document.paragraphs), len(document.media.images)) == (paragraphs, images)


def test_a_shadow_and_a_glow_are_written_as_hancom_keeps_them() -> None:
    from hwpx.oxml import PictureGlow, PictureShadow

    picture = HwpxDocument.new().add_picture(
        PNG_1X1, "png", width=20000, height=10000,
        shadow=PictureShadow(direction=90, distance=800), glow=PictureGlow(radius=700)).element
    with zipfile.ZipFile(FIXTURES / "picture_shadow_and_glow.hwpx") as package:
        hancom = etree.fromstring(package.read("Contents/section0.xml")).find(f".//{HP}pic")

    def effects(element):
        return [(etree.QName(node).localname, dict(node.attrib)) for node in element.find(f"{HP}effects").iter()
                if node is not element.find(f"{HP}effects")]

    assert effects(picture) == effects(hancom)


def test_no_effect_by_default() -> None:
    picture = HwpxDocument.new().add_picture(PNG_1X1, "png").element

    assert len(picture.find(f"{HP}effects")) == 0


@pytest.mark.parametrize(
    "arguments",
    [
        {"shadow": "shadow"},
        {"glow": {"radius": 500}},
    ],
)
def test_an_effect_that_is_not_its_class_is_refused(arguments) -> None:
    with pytest.raises(HwpxValueError) as caught:
        HwpxDocument.new().add_picture(PNG_1X1, "png", **arguments)

    assert caught.value.code == "shape-picture-effect-value"


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        ("shadow", {"alpha": 1.5}),  # saved as 1
        ("shadow", {"alpha": -0.1}),  # saved as 0
        ("shadow", {"direction": 360}),  # saved as itself, drawn as 0
        ("shadow", {"direction": -90}),  # saved as 270
        ("shadow", {"blur": -1}),  # drawn as 0
        ("shadow", {"distance": -600}),
        ("shadow", {"color": "red"}),
        ("shadow", {"color": "#80FF0000"}),
        ("shadow", {"inside": 1}),
        ("glow", {"radius": 1.5}),
        ("glow", {"alpha": True}),
        ("glow", {"color": None}),
    ],
)
def test_a_shadow_or_glow_value_hancom_does_not_keep_is_refused_before_anything_is_added(kind, fields) -> None:
    from hwpx.oxml import PictureGlow, PictureShadow

    effect = PictureShadow(**fields) if kind == "shadow" else PictureGlow(**fields)
    document = HwpxDocument.new()
    paragraphs, images = len(document.paragraphs), len(document.media.images)

    with pytest.raises(HwpxValueError) as caught:
        document.add_picture(PNG_1X1, "png", **{kind: effect})

    assert caught.value.code == "shape-picture-effect-value"
    assert (len(document.paragraphs), len(document.media.images)) == (paragraphs, images)
