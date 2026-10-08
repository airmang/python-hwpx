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
    # Hancom saves the border right after the image
    children = [etree.QName(child).localname for child in picture]
    assert children[children.index("img") + 1] == "lineShape"


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
