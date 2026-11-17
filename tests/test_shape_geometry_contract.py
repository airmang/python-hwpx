"""Anchor generated drawing shapes to real Hancom output.

The corpus fixtures under ``fixtures/hwpxlib_corpus`` are Hancom's own output,
so they are the contract for what this package emits.  These tests compare
**fully qualified** tags: an earlier suite compared local names, which let
``hp:pt0`` pass as ``pt0`` for a file Hancom refused to open.
"""

from __future__ import annotations

from pathlib import Path
import warnings
import xml.etree.ElementTree as ET
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.document import (
    _create_ellipse_element,
    _create_line_element,
    _create_rectangle_element,
)


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

# Present in the gold files but optional: a caption, the text inside a shape,
# and the author's comment are not part of the geometry contract.
_GOLD_ONLY_CHILDREN = frozenset({"drawText", "caption", "shapeComment"})


def _gold_shape(fixture: str, tag: str) -> ET.Element:
    with zipfile.ZipFile(CORPUS / fixture) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = ET.fromstring(archive.read(name))
    element = root.find(f".//{tag}")
    assert element is not None, f"{fixture} contains no {tag}"
    return element


def _contract_children(element: ET.Element) -> list[str]:
    return [
        child.tag
        for child in element
        if child.tag.split("}")[-1] not in _GOLD_ONLY_CHILDREN
    ]


def _paragraph():
    return HwpxDocument.new().add_paragraph("")


# =========================================================================
# Child sequence, anchored to real Hancom output
# =========================================================================


@pytest.mark.parametrize(
    "fixture, tag, build",
    [
        # Each shape is generated at the gold file's own size so the two child
        # sequences are directly comparable.
        (
            "reader_writer__SimpleLine.hwpx",
            f"{HP}line",
            lambda: _create_line_element(0, 0, 22478, 8447, ids=None),
        ),
        (
            "reader_writer__SimpleRectangle.hwpx",
            f"{HP}rect",
            lambda: _create_rectangle_element(20925, 14175, fill_color="#86AFDC", ids=None),
        ),
        (
            "reader_writer__SimpleEllipse.hwpx",
            f"{HP}ellipse",
            lambda: _create_ellipse_element(27950, 15150, fill_color="#4B87CB", ids=None),
        ),
    ],
)
def test_generated_shape_matches_gold_child_sequence(fixture, tag, build) -> None:
    assert _contract_children(build()) == _contract_children(_gold_shape(fixture, tag))


@pytest.mark.parametrize(
    "build, expected",
    [
        (
            lambda: _create_line_element(0, 0, 14400, 7200, ids=None),
            [f"{HC}startPt", f"{HC}endPt"],
        ),
        (
            lambda: _create_rectangle_element(14400, 7200, ids=None),
            [f"{HC}pt0", f"{HC}pt1", f"{HC}pt2", f"{HC}pt3"],
        ),
        (
            lambda: _create_ellipse_element(14400, 7200, ids=None),
            [f"{HC}center", f"{HC}ax1", f"{HC}ax2"],
        ),
    ],
)
def test_geometry_children_use_the_core_namespace(build, expected) -> None:
    """Hancom rejects the whole document when geometry lands in ``hp:``."""

    tags = [child.tag for child in build()]
    for tag in expected:
        assert tag in tags, f"{tag} missing; geometry namespace regressed"


@pytest.mark.parametrize(
    "build", [
        lambda: _create_rectangle_element(14400, 7200, fill_color="#CCE5FF", ids=None),
        lambda: _create_ellipse_element(10000, 6000, fill_color="#FFD9CC", ids=None),
    ],
)
def test_fill_brush_uses_the_core_namespace(build) -> None:
    """An ``hp:fillBrush`` parses but renders unfilled — the colour is lost."""

    element = build()
    assert element.find(f"{HP}fillBrush") is None
    brush = element.find(f"{HC}fillBrush/{HC}winBrush")
    assert brush is not None
    assert brush.get("faceColor") in {"#CCE5FF", "#FFD9CC"}


# =========================================================================
# Line bounding box
# =========================================================================


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ((0, 0), (14400, 0), (14400, 0)),        # horizontal
        ((0, 0), (0, 7200), (0, 7200)),          # vertical
        ((0, 0), (14400, 7200), (14400, 7200)),  # diagonal, down-right
        ((0, 7200), (14400, 0), (14400, 7200)),  # diagonal, up-right
    ],
)
def test_line_size_is_the_bounding_box_of_its_endpoints(start, end, expected) -> None:
    """Gold ``SimpleLine`` has endPt (22478, 8447) with orgSz 22478x8447, and
    gold ``SimpleConnectLine`` runs (0, 5900) → (9000, 0) with orgSz 9000x5900:
    Hancom stores the box the endpoints span, not the segment length.
    orgSz/curSz keep at least 1 on each side, as Hancom writes a horizontal
    line; sz keeps the span itself.
    """

    element = _create_line_element(start[0], start[1], end[0], end[1], ids=None)

    for tag in ("orgSz", "curSz", "sz"):
        box = element.find(f"{HP}{tag}")
        assert box is not None
        floor = 0 if tag == "sz" else 1
        assert (int(box.get("width", "")), int(box.get("height", ""))) == (
            max(expected[0], floor), max(expected[1], floor),
        )

    start_pt = element.find(f"{HC}startPt")
    end_pt = element.find(f"{HC}endPt")
    assert start_pt is not None and end_pt is not None
    assert (start_pt.get("x"), start_pt.get("y")) == (str(start[0]), str(start[1]))
    assert (end_pt.get("x"), end_pt.get("y")) == (str(end[0]), str(end[1]))


@pytest.mark.parametrize("end", [(14400, 0), (0, 7200)])
def test_a_straight_line_keeps_a_box_of_at_least_one(end) -> None:
    """A horizontal or vertical line with a 0 side in orgSz is not drawn."""

    element = _create_line_element(0, 0, *end, ids=None)

    for tag in ("orgSz", "curSz"):
        box = element.find(f"{HP}{tag}")
        assert box is not None
        assert min(int(box.get("width", "")), int(box.get("height", ""))) == 1


def test_resizing_a_flat_line_keeps_its_original_box() -> None:
    # Hancom 2024 resizes a horizontal line through its scaMatrix: orgSz 14400x1 stays (objlim psizeline2).
    shape = _paragraph().add_line(0, 0, 14400, 0)

    shape.resize(28800, 0)

    org = shape.element.find(f"{HP}orgSz")
    sz = shape.element.find(f"{HP}sz")
    end_pt = shape.element.find(f"{HC}endPt")
    assert org is not None and sz is not None and end_pt is not None
    assert (org.get("width"), org.get("height")) == ("14400", "1")
    assert (sz.get("width"), sz.get("height")) == ("28800", "0")
    assert (end_pt.get("x"), end_pt.get("y")) == ("14400", "0")


def test_diagonal_line_is_not_sized_by_its_hypotenuse() -> None:
    """The old sizing wrote 16099x0 for a line whose own endPt said 14400x7200."""

    box = _create_line_element(0, 0, 14400, 7200, ids=None).find(f"{HP}orgSz")
    assert box is not None
    assert box.get("width") != "16099"
    assert box.get("height") != "0"


# =========================================================================
# resize() as Hancom 2024 resizes a drawing object: geometry and orgSz stay, scaMatrix draws it
# (objlim evidence psizerect, psizerect2, psizerect3, psizeline, psizeline2)
# =========================================================================


def _resized(shape) -> dict[str, tuple[str | None, ...]]:
    element = shape.element

    def box(tag: str) -> tuple[str | None, str | None]:
        child = element.find(f"{HP}{tag}")
        assert child is not None
        return child.get("width"), child.get("height")

    scale = element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    turn = element.find(f"{HP}rotationInfo")
    assert scale is not None and turn is not None
    return {"sz": box("sz"), "curSz": box("curSz"), "orgSz": box("orgSz"),
            "scale": (scale.get("e1"), scale.get("e5")), "centre": (turn.get("centerX"), turn.get("centerY"))}


@pytest.mark.parametrize(
    "size, expected",
    [
        ((12000, 5000), {"sz": ("12000", "5000"), "curSz": ("12000", "0"), "scale": ("1.5", "1"),
                         "centre": ("6000", "2500")}),  # psizerect
        ((4000, 10000), {"sz": ("4000", "10000"), "curSz": ("4000", "10000"), "scale": ("0.5", "2"),
                         "centre": ("2000", "5000")}),  # psizerect2
    ],
)
def test_resize_draws_a_rectangle_through_its_scale_matrix(size, expected) -> None:
    shape = _paragraph().add_rectangle(8000, 5000)

    shape.resize(*size)

    assert _resized(shape) == {**expected, "orgSz": ("8000", "5000")}
    corners = [(shape.element.find(f"{HC}pt{i}").get("x"), shape.element.find(f"{HC}pt{i}").get("y"))  # type: ignore[union-attr]
               for i in range(4)]
    assert corners == [("0", "0"), ("8000", "0"), ("8000", "5000"), ("0", "5000")]


def test_resize_twice_scales_from_the_original_size() -> None:
    shape = _paragraph().add_rectangle(8000, 5000)

    shape.resize(12000, 5000)
    shape.resize(6000, 2500)  # psizerect3

    assert _resized(shape) == {"sz": ("6000", "2500"), "curSz": ("6000", "2500"), "orgSz": ("8000", "5000"),
                               "scale": ("0.75", "0.5"), "centre": ("3000", "1250")}


@pytest.mark.parametrize(
    "size, expected",
    [
        ((14400, 2000), {"sz": ("14400", "2000"), "curSz": ("0", "2000"), "scale": ("1", "2000"),
                         "centre": ("7200", "1000")}),  # psizeline
        ((7200, 3000), {"sz": ("7200", "3000"), "curSz": ("7200", "3000"), "scale": ("0.5", "3000"),
                        "centre": ("3600", "1500")}),  # psizeline2
    ],
)
def test_resize_gives_a_flat_line_a_height_through_its_scale_matrix(size, expected) -> None:
    shape = _paragraph().add_line(0, 0, 14400, 0)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        shape.resize(*size)

    assert _resized(shape) == {**expected, "orgSz": ("14400", "1")}


def test_resize_keeps_the_ellipse_geometry() -> None:
    shape = _paragraph().add_ellipse(7200, 3600)

    shape.resize(14400, 7200)

    def point(name: str) -> tuple[str | None, str | None]:
        child = shape.element.find(f"{HC}{name}")
        assert child is not None
        return child.get("x"), child.get("y")

    assert point("center") == ("3600", "1800")
    assert _resized(shape)["scale"] == ("2", "2")


# =========================================================================
# Generic add_shape / add_control
# =========================================================================


def test_generic_add_shape_warns_that_it_is_incomplete() -> None:
    with pytest.warns(UserWarning, match="orgSz"):
        _paragraph().add_shape("rect")


def test_generic_add_control_warns_that_it_is_empty() -> None:
    with pytest.warns(UserWarning, match="no control child"):
        _paragraph().add_control(control_type="LINE")


def test_document_facade_add_shape_warns() -> None:
    with pytest.warns(UserWarning, match="orgSz"):
        HwpxDocument.new().shapes.add_raw("rect")


def test_document_facade_add_control_warns() -> None:
    with pytest.warns(UserWarning, match="no control child"):
        HwpxDocument.new().shapes.add_control(control_type="LINE")


def test_dedicated_shape_helpers_do_not_warn() -> None:
    paragraph = _paragraph()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        paragraph.add_line(0, 0, 14400, 7200)
        paragraph.add_rectangle(14400, 7200, fill_color="#CCE5FF")
        paragraph.add_ellipse(10000, 6000, fill_color="#FFD9CC")

    assert [w for w in caught if issubclass(w.category, UserWarning)] == []


def test_dedicated_control_helpers_do_not_warn() -> None:
    paragraph = _paragraph()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        paragraph.add_column_definition(col_count=2)
        paragraph.add_bookmark("mark")

    assert [w for w in caught if issubclass(w.category, UserWarning)] == []
