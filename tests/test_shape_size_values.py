"""Shape, picture and equation sizes, rectangle ratios and equation base units Hancom does not keep are refused.

Hancom reads a negative size or corner ratio as 0 (and saves 0), so they are refused before anything is added:
no paragraph, run or image is left behind. ``tests/fixtures/hancom_saved/*_negative.hwpx`` are Hancom's saves of
a rectangle, a picture and an equation written 1 unit below 0 and of a rectangle with ratio -1.
"""

from __future__ import annotations

import base64
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)


def _saved(name: str, tag: str) -> etree._Element:
    """The first ``hp:<tag>`` object in the Hancom-saved fixture *name*."""

    with zipfile.ZipFile(FIXTURES / name) as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    return next(root.iter(f"{HP}{tag}"))


def _size(element: etree._Element, child: str = "sz") -> tuple[str | None, str | None]:
    node = element.find(f"{HP}{child}")
    return node.get("width"), node.get("height")


def _state(document: HwpxDocument) -> tuple[int, int, list[bytes]]:
    """What a refused object must leave as it was: the paragraphs, the stored images and every section's XML."""

    return (
        len(document.paragraphs),
        len(document.media.images),
        [etree.tostring(section.element) for section in document.sections],
    )


def test_hancom_reads_a_negative_size_or_corner_ratio_as_0() -> None:
    # Written as -1 by -1, Hancom saved 0 for the size, the original size and the rotation centre written from
    # it, and a picture's image size; a corner ratio of -1 it saved as 0.
    rectangle = _saved("shape_rect_size_negative.hwpx", "rect")
    assert {_size(rectangle, child) for child in ("sz", "orgSz")} == {("0", "0")}
    rotation = rectangle.find(f"{HP}rotationInfo")
    assert (rotation.get("centerX"), rotation.get("centerY")) == ("0", "0")

    assert _saved("shape_rect_ratio_negative.hwpx", "rect").get("ratio") == "0"

    picture = _saved("picture_size_negative.hwpx", "pic")
    assert {_size(picture, child) for child in ("sz", "orgSz")} == {("0", "0")}
    image = picture.find(f"{HP}imgDim")
    assert (image.get("dimwidth"), image.get("dimheight")) == ("0", "0")

    assert _size(_saved("equation_size_negative.hwpx", "equation")) == ("0", "0")


_SHAPES: dict[str, Callable[[HwpxDocument, object, object], object]] = {
    "rectangle": lambda document, width, height: document.shapes.add_rectangle(width=width, height=height),
    "ellipse": lambda document, width, height: document.shapes.add_ellipse(width=width, height=height),
    "arc": lambda document, width, height: document.shapes.add_arc(width=width, height=height),
    "equation": lambda document, width, height: document.shapes.add_equation("x + 1 over 2", size=(width, height)),
}


@pytest.mark.parametrize("kind", sorted(_SHAPES))
@pytest.mark.parametrize("width, height", [(-1, 7200), (7200, -1), (2**31, 7200), (7200.0, 7200), (True, 7200)])
def test_a_size_hancom_does_not_keep_is_refused_before_anything_is_added(
    kind: str, width: object, height: object
) -> None:
    document = HwpxDocument.new()
    before = _state(document)

    with pytest.raises(HwpxValueError) as caught:
        _SHAPES[kind](document, width, height)

    assert caught.value.code == "shape-size-value"
    assert _state(document) == before


@pytest.mark.parametrize(
    "size", [{"width": -1, "height": 7200}, {"width": 7200, "height": -1}, {"width": 2**31}, {"width_mm": -1.0}]
)
def test_a_picture_size_hancom_does_not_keep_is_refused_before_the_image_is_stored(size: dict[str, object]) -> None:
    document = HwpxDocument.new()
    before = _state(document)

    with pytest.raises(HwpxValueError) as caught:
        document.add_picture(PNG_1X1, "png", **size)  # type: ignore[arg-type]

    assert caught.value.code == "shape-size-value"
    assert _state(document) == before


@pytest.mark.parametrize("value", [True, False, -0.5, 14400.5, "14400"])
@pytest.mark.parametrize("dimension", ["width", "height"])
@pytest.mark.parametrize("direct", [False, True])
def test_picture_units_are_validated_without_coercion(value: object, dimension: str, direct: bool) -> None:
    document = HwpxDocument.new()
    paragraph = document.paragraphs[0]
    before = _state(document)
    sizes = {dimension: value}

    with pytest.raises(HwpxValueError) as caught:
        if direct:
            paragraph.add_picture("image1", **sizes)  # type: ignore[arg-type]
        else:
            document.add_picture(PNG_1X1, "png", **sizes)  # type: ignore[arg-type]

    assert caught.value.code == "shape-size-value"
    assert _state(document) == before


@pytest.mark.parametrize("ratio", [-1, 2**31, 12.5, True])
def test_a_corner_ratio_hancom_does_not_keep_is_refused_before_anything_is_added(ratio: object) -> None:
    document = HwpxDocument.new()
    before = _state(document)

    with pytest.raises(HwpxValueError) as caught:
        document.shapes.add_rectangle(width=14400, height=7200, ratio=ratio)  # type: ignore[arg-type]

    assert caught.value.code == "shape-rect-ratio-value"
    assert _state(document) == before


def test_the_smallest_and_largest_sizes_are_written_as_given() -> None:
    document = HwpxDocument.new()

    rectangle = document.shapes.add_rectangle(width=0, height=2**31 - 1, ratio=50)
    equation = document.shapes.add_equation("x + 1 over 2", size=(0, 2**31 - 1))

    assert _size(rectangle.element) == ("0", str(2**31 - 1))
    assert rectangle.element.get("ratio") == "50"
    assert _size(equation.element) == ("0", str(2**31 - 1))


@pytest.mark.parametrize("base_unit", [0, -1100, 2**31, 1100.0, True])
def test_an_equation_base_unit_outside_1_to_2_31_is_refused_before_anything_is_added(base_unit: object) -> None:
    document = HwpxDocument.new()
    before = _state(document)

    with pytest.raises(HwpxValueError) as caught:
        document.shapes.add_equation("x + 1 over 2", base_unit=base_unit)  # type: ignore[arg-type]

    assert caught.value.code == "shape-equation-base-unit-value"
    assert isinstance(caught.value, ValueError)  # what it raised before
    assert _state(document) == before


def test_an_equation_box_measured_past_31_bits_is_refused_and_a_given_box_keeps_the_largest_base_unit() -> None:
    # Hancom keeps base_unit 2**31 - 1 and lays the page out with the stored box. The box measured at it is past
    # 32 bits: Hancom saved 2**32 - 1 for it. With a box given, it kept both.
    measured = _saved("equation_base_unit_largest_measured.hwpx", "equation")
    assert measured.get("baseUnit") == "2147483647"
    assert _size(measured) == ("4294967295", "4294967295")
    given = _saved("equation_base_unit_largest_given_size.hwpx", "equation")
    assert given.get("baseUnit") == "2147483647"
    assert _size(given) == ("1342", "1089")

    document = HwpxDocument.new()
    before = _state(document)
    with pytest.raises(HwpxValueError) as caught:
        document.shapes.add_equation("x + 1 over 2", base_unit=2**31 - 1)
    assert caught.value.code == "shape-size-value"
    assert _state(document) == before

    equation = document.shapes.add_equation("(x)", base_unit=2**31 - 1, size=(1342, 1089))
    assert equation.element.get("baseUnit") == "2147483647"
    assert _size(equation.element) == ("1342", "1089")


def test_the_paragraph_writers_check_before_adding_a_run() -> None:
    document = HwpxDocument.new()
    paragraph = document.paragraphs[0]
    runs = len(paragraph.element.findall(f"{HP}run"))

    for add, code in (
        (lambda: paragraph.add_rectangle(width=-1, height=7200), "shape-size-value"),
        (lambda: paragraph.add_rectangle(width=-1, height=7200, original_size=(100, 100)), "shape-size-value"),
        (lambda: paragraph.add_rectangle(width=14400, height=7200, ratio=-1), "shape-rect-ratio-value"),
        (lambda: paragraph.add_picture("image1", width=-1, height=7200), "shape-size-value"),
        (lambda: paragraph.add_equation("x", size=(-1, 7200)), "shape-size-value"),
        (lambda: paragraph.add_equation("x", base_unit=0), "shape-equation-base-unit-value"),
    ):
        with pytest.raises(HwpxValueError) as caught:
            add()
        assert caught.value.code == code

    assert len(paragraph.element.findall(f"{HP}run")) == runs


def test_resizing_a_shape_to_a_negative_size_is_refused_and_leaves_it_as_it_was() -> None:
    document = HwpxDocument.new()
    shape = document.shapes.add_rectangle(width=14400, height=7200, treat_as_char=False)
    before = etree.tostring(shape.element)

    with pytest.raises(HwpxValueError) as caught:
        shape.resize(-1, 7200)

    assert caught.value.code == "shape-size-value"
    assert etree.tostring(shape.element) == before
