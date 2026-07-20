# SPDX-License-Identifier: Apache-2.0
"""Document preview viewer + object-marker tests."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from hwpx.tools.document_viewer import FIDELITY_BADGE, render_document_viewer
from hwpx.tools.layout_preview import _ObjectCounter, _render_paragraph, render_layout_preview

EQUATION_FIXTURE = Path(__file__).parent / "fixtures" / "equation_preview" / "equation_p0.hwpx"
CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_STYLES = {"para": {}, "char": {}, "border": {}}


def _hp(tag: str) -> str:
    return f"{{{_HP}}}{tag}"


def _para_with(*children: ET.Element) -> ET.Element:
    paragraph = ET.Element(_hp("p"))
    run = ET.SubElement(paragraph, _hp("run"))
    for child in children:
        run.append(child)
    return paragraph


def _equation(script: str) -> ET.Element:
    equation = ET.Element(_hp("equation"))
    script_node = ET.SubElement(equation, _hp("script"))
    script_node.text = script
    return equation


# --- viewer chrome ---------------------------------------------------------


def test_viewer_has_top_bar_page_indicator_and_honest_badge() -> None:
    viewer = render_document_viewer(EQUATION_FIXTURE, title="수식 프리뷰")
    html = viewer.html
    assert "<title>수식 프리뷰</title>" in html
    assert "hwpx-viewer-bar" in html
    assert 'id="hwpx-viewer-page"' in html
    assert FIDELITY_BADGE in html
    # honest, non-truth framing (Constitution IX)
    assert "근사" in FIDELITY_BADGE and "MathML" in FIDELITY_BADGE


def test_viewer_has_intersection_observer_and_keyboard_nav() -> None:
    html = render_document_viewer(EQUATION_FIXTURE).html
    assert "IntersectionObserver" in html
    assert "keydown" in html
    for key in ("PageDown", "PageUp", "Home", "End"):
        assert key in html


def test_viewer_is_self_contained_no_external_resources() -> None:
    html = render_document_viewer(EQUATION_FIXTURE).html
    # No external stylesheet/script/resource loads.
    assert "<link" not in html
    assert "<script src" not in html
    assert not re.search(r'(?:src|href)\s*=\s*["\']https?:', html)
    assert "@import" not in html
    assert not re.search(r"url\(\s*https?:", html)
    # The only http(s) strings allowed are the non-fetching MathML/XML namespace.
    for url in re.findall(r"https?://[^\s\"'<>]+", html):
        assert "w3.org" in url, f"unexpected external URL: {url}"


def test_viewer_size_is_lightweight() -> None:
    viewer = render_document_viewer(EQUATION_FIXTURE)
    # Text HTML preview stays in the tens-of-KB range (no rasterization).
    assert viewer.as_dict()["byteSize"] < 200_000


# --- equations flow into the viewer ---------------------------------------


def test_viewer_renders_equations_as_mathml_when_available() -> None:
    pytest.importorskip("latex2mathml")
    html = render_document_viewer(EQUATION_FIXTURE).html
    assert html.count("<math") == 3


def test_equations_never_render_as_empty_paragraphs() -> None:
    # Regression: the OLD behavior dropped <hp:equation> to a blank &nbsp;
    # paragraph.  Each rendered <math> must live in a non-empty paragraph.
    html = render_layout_preview(EQUATION_FIXTURE, mode="long").html
    for match in re.finditer(r'<p class="([^"]*)"[^>]*>(.*?)</p>', html, re.S):
        classes, body = match.group(1), match.group(2)
        if "<math" in body:
            assert "hwpx-empty-paragraph" not in classes


# --- unit-level: markers and the empty-paragraph regression ---------------


def test_equation_only_paragraph_is_not_empty() -> None:
    html = _render_paragraph(_para_with(_equation("{alpha} over {beta}")), _STYLES, _ObjectCounter())
    assert "<math" in html or "hwpx-equation" in html
    assert "hwpx-empty-paragraph" not in html


def test_truly_empty_paragraph_still_marked_empty() -> None:
    # Legit blank lines are preserved as empty paragraphs.
    empty = ET.Element(_hp("p"))
    ET.SubElement(empty, _hp("run"))
    html = _render_paragraph(empty, _STYLES, _ObjectCounter())
    assert "hwpx-empty-paragraph" in html


def test_picture_marker_numbers_across_document() -> None:
    counter = _ObjectCounter()
    first = _render_paragraph(_para_with(ET.Element(_hp("pic"))), _STYLES, counter)
    second = _render_paragraph(_para_with(ET.Element(_hp("pic"))), _STYLES, counter)
    assert "⟦그림 1⟧" in first
    assert "⟦그림 2⟧" in second
    assert "hwpx-empty-paragraph" not in first


def test_shape_and_ole_markers() -> None:
    shape = _render_paragraph(_para_with(ET.Element(_hp("rect"))), _STYLES, _ObjectCounter())
    ole = _render_paragraph(_para_with(ET.Element(_hp("ole"))), _STYLES, _ObjectCounter())
    assert "⟦도형⟧" in shape
    assert "⟦개체⟧" in ole


def test_tables_still_render_as_tables_not_markers() -> None:
    html = render_layout_preview(CORPUS / "reader_writer__SimpleTable.hwpx").html
    assert '<table class="hwpx-table"' in html
