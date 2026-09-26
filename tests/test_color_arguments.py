# SPDX-License-Identifier: Apache-2.0
"""Colour arguments are written as the ``#RRGGBB`` Hancom writes, or refused.

Hancom reads a colour attribute as one hexadecimal number and does not reject the rest:
``#ABC`` shows as ``#000ABC`` (not CSS's ``#AABBCC``), ``red`` as black and ``#12345`` as
``#012345``. A value that is not six hexadecimal digits is refused before it is written.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.body_patch import apply_body_ops
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.color import normalize_color

NOT_RRGGBB = ["#ABC", "red", "#RED", "#12345", "#1234567", "#FF123456", "#GGGGGG", "#12 345"]


def test_a_refused_colour_leaves_the_header_as_it_was() -> None:
    doc = HwpxDocument.new()
    doc.page.set_header(text="기존 머리말")

    with pytest.raises(HwpxValueError):
        doc.page.set_header(content=[{"children": [{"type": "run", "text": "새 머리말", "color": "#abc"}]}])

    assert doc.oxml.sections[0].properties.get_header().text == "기존 머리말"
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert section.count("기존 머리말") == 2 and "새 머리말" not in section


def test_a_header_refused_later_in_its_content_is_put_back() -> None:
    doc = HwpxDocument.new()
    header = doc.page.set_header(text="기존 머리말")

    with pytest.raises(ValueError):
        header.set_content([{"children": [{"type": "run", "text": "앞"}, {"type": "unknown"}]}])

    assert header.text == "기존 머리말"


def test_a_refused_column_line_leaves_the_columns_as_they_were() -> None:
    doc = HwpxDocument.new()
    props = doc.oxml.sections[0].properties
    props.set_columns(2, separator_type="DOT", separator_width="0.5 mm", separator_color="#FF0000")
    col_pr = next(doc.oxml.sections[0].element.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}colPr"))
    before = (dict(col_pr.attrib), [dict(child.attrib) for child in col_pr])

    for bad in ({"separator_width": "0.13 mm"}, {"separator_color": "#abc"}):
        with pytest.raises(HwpxValueError):
            props.set_columns(3, **bad)

    assert (dict(col_pr.attrib), [dict(child.attrib) for child in col_pr]) == before


@pytest.mark.parametrize("value", NOT_RRGGBB)
def test_a_value_that_is_not_rrggbb_is_refused(value: str) -> None:
    with pytest.raises(HwpxValueError) as caught:
        normalize_color(value)
    assert caught.value.code == "style-color-invalid"


@pytest.mark.parametrize(
    ("value", "written"),
    [("#1a2b3c", "#1A2B3C"), ("1A2B3C", "#1A2B3C"), (" #00ff00 ", "#00FF00"), ("NONE", "none"), ("", None), (None, None)],
)
def test_rrggbb_is_taken_with_or_without_the_hash_in_either_case(value: str | None, written: str | None) -> None:
    assert normalize_color(value) == written


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _char_color(document: HwpxDocument, char_pr_id: str) -> str | None:
    for header in document.parts.headers:
        for element in header._char_properties_element():
            if element.get("id") == str(char_pr_id):
                return element.get("textColor")
    return None


@pytest.mark.parametrize("argument", ["color", "highlight", "underline_color", "shadow"])
def test_run_colours_are_checked(argument: str) -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_run(**{argument: "#ABC"})


def test_a_run_colour_is_written_in_upper_case_with_its_hash() -> None:
    document = HwpxDocument.new()
    char_pr_id = document.styles.ensure_run(color="1a2b3c")
    assert _char_color(document, char_pr_id) == "#1A2B3C"


def test_cell_border_fill_and_memo_colours_are_checked() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        table.set_cell_shading(0, 0, "red")
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_border_fill(fill_color="#12345")
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_border_fill(border_color="#GGGGGG")
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_memo_shape(fill_color="#ABC")


def test_gradient_colours_are_checked_and_written_in_upper_case() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_border_fill(fill_gradient={"colors": ["#ABC", "#FFFFFF"]})
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.styles.ensure_border_fill(fill_gradient={"colors": ["none", "#FFFFFF"]})

    document.styles.ensure_border_fill(fill_gradient={"colors": ["#ff0000", "0000ff"]})
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
    assert re.findall(r'<hc:color value="([^"]*)"', header) == ["#FF0000", "#0000FF"]


def test_shape_colours_are_checked_and_written_in_upper_case() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.shapes.add_rectangle(line_color="red")
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.shapes.add_rectangle(fill_color="#12345")

    document.shapes.add_rectangle(line_color="#00ff00", fill_color="#0000ff")
    xml = _section_xml(document)
    assert re.search(r'<hp:lineShape\b[^>]*\bcolor="#00FF00"', xml)
    assert 'faceColor="#0000FF"' in xml


def test_a_column_separator_colour_is_checked() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="not #RRGGBB"):
        document.page.set_columns(2, separator_type="SOLID", separator_color="#ABC")


def test_body_patch_refuses_a_restyle_colour_that_is_not_rrggbb() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("바꿀 글")

    result = apply_body_ops(document.to_bytes(), [{"op": "restyle_text", "find": "바꿀 글", "text_color": "red"}])

    assert [entry["status"] for entry in result.skipped] == ["refused: colour 'red' is not #RRGGBB"]
