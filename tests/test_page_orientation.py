# SPDX-License-Identifier: Apache-2.0
"""Page orientation is written the way Hancom writes it.

``hp:pagePr@landscape`` is ``WIDELY`` for a portrait page and ``NARROWLY`` for
a landscape page. Both keep the paper's portrait width and height; Hancom
turns a ``NARROWLY`` page when it draws it, and reads a missing or unknown
value as ``NARROWLY``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.layout_preview import render_layout_preview
from hwpx.tools.template_analyzer import analyze_template

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
A4 = (59528, 84189)


def _page_pr(document: HwpxDocument):
    page_pr = document.sections[0].element.find(f".//{HP}pagePr")
    assert page_pr is not None
    return page_pr


def _stored(document: HwpxDocument) -> tuple[str | None, int, int]:
    page_pr = _page_pr(document)
    return page_pr.get("landscape"), int(page_pr.get("width")), int(page_pr.get("height"))


@pytest.mark.parametrize(
    ("orientation", "expected"),
    [
        ("PORTRAIT", "WIDELY"),
        ("portrait", "WIDELY"),
        ("NARROW", "WIDELY"),
        ("WIDELY", "WIDELY"),
        ("LANDSCAPE", "NARROWLY"),
        ("landscape", "NARROWLY"),
        ("WIDE", "NARROWLY"),
        ("NARROWLY", "NARROWLY"),
    ],
)
def test_setup_writes_hancom_orientation_with_the_portrait_size(orientation: str, expected: str) -> None:
    document = HwpxDocument.new()
    result = document.page.setup(paper_size="A4", orientation=orientation)

    assert _stored(document) == (expected, *A4)
    assert result.page_size.orientation == expected
    drawn = (result.page_size.width_mm, result.page_size.height_mm)
    assert drawn == ((297.0, 210.0) if expected == "NARROWLY" else (210.0, 297.0))


def test_landscape_keeps_the_portrait_size_whatever_order_the_size_comes_in() -> None:
    document = HwpxDocument.new()
    document.page.setup(width_mm=297, height_mm=210, orientation="LANDSCAPE")

    assert _stored(document) == ("NARROWLY", *A4)


def test_orientation_alone_turns_the_page_without_changing_the_paper() -> None:
    document = HwpxDocument.new()
    _, width, height = _stored(document)

    document.page.setup(orientation="LANDSCAPE")

    assert _stored(document) == ("NARROWLY", width, height)
    size = document.sections[0].properties.page_size
    assert (size.drawn_width, size.drawn_height) == (height, width)


def test_a_page_stored_wider_than_tall_is_written_back_with_the_portrait_size() -> None:
    document = HwpxDocument.new()
    page_pr = _page_pr(document)
    page_pr.set("width", str(A4[1]))
    page_pr.set("height", str(A4[0]))

    document.page.setup(orientation="PORTRAIT")

    assert _stored(document) == ("WIDELY", *A4)


def test_an_orientation_read_back_keeps_the_page() -> None:
    document = HwpxDocument.new()
    document.page.setup(paper_size="A4", orientation="LANDSCAPE")

    orientation = document.sections[0].properties.page_size.orientation
    document.page.setup(paper_size="A4", orientation=orientation)

    assert _stored(document) == ("NARROWLY", *A4)


def test_every_page_size_setter_writes_hancom_orientation() -> None:
    document = HwpxDocument.new()

    document.sections[0].properties.set_page_size(width=A4[1], height=A4[0], orientation="LANDSCAPE")
    assert _stored(document) == ("NARROWLY", *A4)

    document.page.set_size(width=A4[1], height=A4[0], orientation="portrait")
    assert _stored(document) == ("WIDELY", *A4)


def test_an_unknown_orientation_is_rejected() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as caught:
        document.page.set_size(orientation="SIDEWAYS")

    assert caught.value.code == "page-orientation-unsupported"


@pytest.mark.parametrize(
    ("landscape", "drawn"),
    [("WIDELY", A4), ("NARROWLY", A4[::-1]), (None, A4[::-1]), ("PORTRAIT", A4[::-1])],
)
def test_the_drawn_size_follows_the_landscape_value(landscape: str | None, drawn: tuple[int, int]) -> None:
    document = HwpxDocument.new()
    page_pr = _page_pr(document)
    page_pr.set("width", str(A4[0]))
    page_pr.set("height", str(A4[1]))
    if landscape is None:
        page_pr.attrib.pop("landscape", None)
    else:
        page_pr.set("landscape", landscape)

    size = document.sections[0].properties.page_size

    assert (size.drawn_width, size.drawn_height) == drawn
    if landscape is None:
        assert size.orientation == "NARROWLY"


def test_a_landscape_page_gives_tables_headers_and_tools_the_landscape_width(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.page.setup(paper_size="A4", orientation="LANDSCAPE", margin_left_mm=20, margin_right_mm=20)
    document.set_header_text("머리말")
    table = document.add_table(1, 2)
    properties = document.sections[0].properties
    margins = properties.page_margins
    body_width = A4[1] - margins.left - margins.right - margins.gutter

    assert int(table.element.find(f"{HP}sz").get("width")) == body_width
    header_sublist = document.sections[0].element.find(f".//{HP}header/{HP}subList")
    assert header_sublist is not None
    assert int(header_sublist.get("textWidth")) == A4[1] - margins.left - margins.right

    path = tmp_path / "landscape.hwpx"
    document.save_to_path(path)
    layout = analyze_template(path).section_layouts[0]
    assert (layout.page_width, layout.page_height) == (A4[1], A4[0])
    assert layout.computed_body_width == body_width
    page = render_layout_preview(path).pages[0]
    assert page.width_mm > page.height_mm
