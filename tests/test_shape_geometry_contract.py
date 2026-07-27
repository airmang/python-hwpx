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
            lambda: _create_line_element(0, 0, 22478, 8447),
        ),
        (
            "reader_writer__SimpleRectangle.hwpx",
            f"{HP}rect",
            lambda: _create_rectangle_element(20925, 14175, fill_color="#86AFDC"),
        ),
        (
            "reader_writer__SimpleEllipse.hwpx",
            f"{HP}ellipse",
            lambda: _create_ellipse_element(27950, 15150, fill_color="#4B87CB"),
        ),
    ],
)
def test_generated_shape_matches_gold_child_sequence(fixture, tag, build) -> None:
    assert _contract_children(build()) == _contract_children(_gold_shape(fixture, tag))


@pytest.mark.parametrize(
    "build, expected",
    [
        (
            lambda: _create_line_element(0, 0, 14400, 7200),
            [f"{HC}startPt", f"{HC}endPt"],
        ),
        (
            lambda: _create_rectangle_element(14400, 7200),
            [f"{HC}pt0", f"{HC}pt1", f"{HC}pt2", f"{HC}pt3"],
        ),
        (
            lambda: _create_ellipse_element(14400, 7200),
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
        lambda: _create_rectangle_element(14400, 7200, fill_color="#CCE5FF"),
        lambda: _create_ellipse_element(10000, 6000, fill_color="#FFD9CC"),
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
    """

    element = _create_line_element(start[0], start[1], end[0], end[1])

    for tag in ("orgSz", "curSz", "sz"):
        box = element.find(f"{HP}{tag}")
        assert box is not None
        assert (int(box.get("width", "")), int(box.get("height", ""))) == expected

    start_pt = element.find(f"{HC}startPt")
    end_pt = element.find(f"{HC}endPt")
    assert start_pt is not None and end_pt is not None
    assert (start_pt.get("x"), start_pt.get("y")) == (str(start[0]), str(start[1]))
    assert (end_pt.get("x"), end_pt.get("y")) == (str(end[0]), str(end[1]))


def test_diagonal_line_is_not_sized_by_its_hypotenuse() -> None:
    """The old sizing wrote 16099x0 for a line whose own endPt said 14400x7200."""

    box = _create_line_element(0, 0, 14400, 7200).find(f"{HP}orgSz")
    assert box is not None
    assert box.get("width") != "16099"
    assert box.get("height") != "0"


# =========================================================================
# resize() must move the geometry Hancom draws
# =========================================================================


def test_resize_moves_rectangle_corners() -> None:
    shape = _paragraph().add_rectangle(7200, 3600)

    shape.resize(14400, 7200)

    corners = [
        (shape.element.find(f"{HC}pt{i}").get("x"),  # type: ignore[union-attr]
         shape.element.find(f"{HC}pt{i}").get("y"))  # type: ignore[union-attr]
        for i in range(4)
    ]
    assert corners == [
        ("0", "0"), ("14400", "0"), ("14400", "7200"), ("0", "7200"),
    ]


def test_resize_moves_ellipse_axes() -> None:
    shape = _paragraph().add_ellipse(7200, 3600)

    shape.resize(14400, 7200)

    def point(name: str) -> tuple[str | None, str | None]:
        child = shape.element.find(f"{HC}{name}")
        assert child is not None
        return child.get("x"), child.get("y")

    assert point("center") == ("7200", "3600")
    assert point("ax1") == ("14400", "3600")
    assert point("ax2") == ("7200", "7200")


def test_resize_moves_line_endpoint() -> None:
    shape = _paragraph().add_line(0, 0, 7200, 3600)

    shape.resize(14400, 7200)

    end_pt = shape.element.find(f"{HC}endPt")
    assert end_pt is not None
    assert (end_pt.get("x"), end_pt.get("y")) == ("14400", "7200")


@pytest.mark.parametrize(
    "kind, created, resized",
    [
        ("rect", (7200, 3600), (14400, 7200)),
        ("rect", (14400, 7200), (3600, 1800)),
        ("ellipse", (7200, 3600), (10000, 6000)),
    ],
)
def test_resize_lands_on_the_geometry_of_a_shape_created_at_that_size(
    kind, created, resized,
) -> None:
    """The point of the fix: a resized shape is drawn like a fresh one."""

    build = {
        "rect": _create_rectangle_element, "ellipse": _create_ellipse_element,
    }[kind]
    paragraph = _paragraph()
    shape = getattr(paragraph, f"add_{'rectangle' if kind == 'rect' else kind}")(
        *created,
    )

    shape.resize(*resized)

    def geometry(element: ET.Element) -> list[tuple[str, str | None, str | None]]:
        return [
            (child.tag, child.get("x"), child.get("y"))
            for child in element
            if child.tag.startswith(HC) and child.get("x") is not None
        ]

    assert geometry(shape.element) == geometry(build(*resized))


def test_resize_warns_when_an_axis_has_no_geometry_to_scale() -> None:
    """A flat line cannot gain height — say so instead of reporting a new size."""

    shape = _paragraph().add_line(0, 0, 14400, 0)

    with pytest.warns(UserWarning, match="height"):
        shape.resize(28800, 7200)

    end_pt = shape.element.find(f"{HC}endPt")
    assert end_pt is not None
    assert (end_pt.get("x"), end_pt.get("y")) == ("28800", "0")


def test_resize_resets_the_scale_matrix() -> None:
    """Hancom draws geometry × scaMatrix; a stale scale would undo the resize."""

    shape = _paragraph().add_rectangle(7200, 3600)
    matrix = shape.element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    assert matrix is not None
    matrix.set("e1", "0.5")
    matrix.set("e5", "2.0")

    shape.resize(14400, 7200)

    assert (matrix.get("e1"), matrix.get("e5")) == ("1", "1")


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
        HwpxDocument.new().add_shape("rect")


def test_document_facade_add_control_warns() -> None:
    with pytest.warns(UserWarning, match="no control child"):
        HwpxDocument.new().add_control(control_type="LINE")


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
