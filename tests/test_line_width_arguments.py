# SPDX-License-Identifier: Apache-2.0
"""Border and column-line widths are written as one of Hancom's line widths.

Hancom keeps a width only when it is one of the ``hc:LineWidth`` strings (``0.1 mm`` …
``5.0 mm``) exactly; ``1 mm``, ``2 mm`` or ``0.12mm`` are drawn as ``0.1 mm``. A width a caller
gives in mm (``border_width_mm=``, ``separator_width_mm=``, ``sides={...: {"width_mm": ...}}``)
must be on that list: 7.0 refuses any other before the document changes rather than writing the
nearest listed width (the engine does not change a value it was told to write). Widths read from
a document still go through ``normalize_line_width`` (nearest listed width).
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.utils import LINE_WIDTHS, LINE_WIDTHS_MM, line_width_text, normalize_line_width


@pytest.mark.parametrize(
    ("value", "written"),
    [("1 mm", "1.0 mm"), ("1mm", "1.0 mm"), (1, "1.0 mm"), (0.5, "0.5 mm"), ("0.12MM", "0.12 mm"), (" 2 mm ", "2.0 mm"),
     ("0.4", "0.4 mm")],
)
def test_a_width_on_the_list_is_written_the_way_hancom_writes_it(value: object, written: str) -> None:
    assert normalize_line_width(value) == written  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "written"),
    [("0.13 mm", "0.12 mm"), ("0.45 mm", "0.5 mm"), ("0.35", "0.4 mm"), (2.5, "3.0 mm"), ("0.8 mm", "0.7 mm"),
     ("0.05mm", "0.1 mm"), ("6 mm", "5.0 mm"), ("40", "5.0 mm")],
)
def test_a_width_off_the_list_is_written_as_the_nearest_listed_width(value: object, written: str) -> None:
    # halfway between two widths (0.45, 0.35, 2.5) takes the thicker one
    assert normalize_line_width(value) == written  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["thick", "", "1 cm", "3 pt", "0", "-1 mm", "nan", "inf"])
def test_a_value_that_is_not_a_width_is_refused(value: str) -> None:
    with pytest.raises(HwpxValueError) as caught:
        normalize_line_width(value)
    assert caught.value.code == "style-line-width-invalid"


def test_every_listed_width_is_its_own_spelling() -> None:
    assert [normalize_line_width(width) for width in LINE_WIDTHS] == list(LINE_WIDTHS)


def _header_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/header.xml").decode("utf-8")


def test_a_border_fill_width_is_written_from_the_list() -> None:
    document = HwpxDocument.new()
    fill_id = document.styles.ensure_border_fill(border_width_mm=1.0)

    block = re.search(rf'<hh:borderFill id="{fill_id}".*?</hh:borderFill>', _header_xml(document), re.S)

    assert block is not None
    assert set(re.findall(r'<hh:(?:left|right|top|bottom)Border [^>]*width="([^"]*)"', block.group(0))) == {"1.0 mm"}


@pytest.mark.parametrize("value", LINE_WIDTHS_MM)
def test_a_listed_width_in_mm_is_written_as_hancom_spells_it(value: float) -> None:
    assert line_width_text(value) == LINE_WIDTHS[LINE_WIDTHS_MM.index(value)]


def test_a_whole_number_of_mm_is_the_listed_width() -> None:
    assert (line_width_text(1), line_width_text(5)) == ("1.0 mm", "5.0 mm")


@pytest.mark.parametrize("value", [0.45, 0.13, 0.8, 6, 0, -0.12, 0.1 + 0.2, float("nan"), "0.4 mm", "0.4", None, True])
def test_a_width_off_the_list_is_refused_with_the_widths_it_takes(value: object) -> None:
    with pytest.raises(HwpxValueError) as caught:
        line_width_text(value, argument="border_width_mm")
    assert caught.value.code == "style-line-width-invalid"
    assert caught.value.context["allowed"] == list(LINE_WIDTHS_MM)
    assert "0.12" in caught.value.suggestion and "5" in caught.value.suggestion


def test_a_border_fill_width_off_the_list_is_refused_before_the_header_changes() -> None:
    document = HwpxDocument.new()
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as caught:
        document.styles.ensure_border_fill(border_width_mm=0.45)
    assert caught.value.code == "style-line-width-invalid"
    with pytest.raises(HwpxValueError) as caught:
        document.styles.ensure_border_fill(sides={"top": {"width_mm": 0.45}})
    assert caught.value.code == "style-line-width-invalid"
    assert document.to_bytes() == before


def test_a_side_width_is_a_number_of_mm_and_the_6x_string_key_is_named() -> None:
    document = HwpxDocument.new()
    fill_id = document.styles.ensure_border_fill(sides={"top": {"width_mm": 0.4}})
    block = re.search(rf'<hh:borderFill id="{fill_id}".*?</hh:borderFill>', _header_xml(document), re.S)
    assert block is not None and re.search(r'<hh:topBorder [^>]*width="0.4 mm"', block.group(0))
    with pytest.raises(HwpxValueError, match="width_mm") as caught:
        document.styles.ensure_border_fill(sides={"top": {"width": "0.4 mm"}})
    assert caught.value.code == "style-border-side-invalid"


def test_a_paragraph_border_width_goes_through_the_same_check() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("테두리 문단")
    index = len(document.paragraphs) - 1
    before = document.to_bytes()
    with pytest.raises(HwpxValueError, match="width_mm") as caught:
        document.styles.apply_paragraph_format(paragraph=index, border={"width": "3 pt"})
    assert caught.value.code == "paragraph-border-invalid"
    for call in (
        lambda: document.styles.apply_paragraph_format(paragraph=index, border={"width_mm": 0.35}),
        lambda: document.styles.apply_paragraph_format(paragraph=index, bottom_border=True, border_width_mm="1 cm"),
        lambda: document.styles.apply_paragraph_format(paragraph=index, bottom_border=True, border_width_mm=0),
    ):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == "style-line-width-invalid"
    assert document.to_bytes() == before
    document.styles.apply_paragraph_format(paragraph=index, border={"width_mm": 0.4, "sides": ("top",)})
    assert 'width="0.4 mm"' in _header_xml(document)


def test_a_column_separator_width_is_written_from_the_list() -> None:
    document = HwpxDocument.new()
    document.page.set_columns(2, separator_type="SOLID", separator_width_mm=0.5)
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert re.search(r'<hp:colLine [^>]*width="0.5 mm"', section)

    for value in ("thick", 0.45):
        with pytest.raises(HwpxValueError) as caught:
            document.page.set_columns(2, separator_type="SOLID", separator_width_mm=value)
        assert caught.value.code == "style-line-width-invalid"


def test_a_table_border_and_a_note_line_take_only_listed_widths() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    with pytest.raises(HwpxValueError) as caught:
        table.set_borders(border_width_mm=0.45)
    assert caught.value.code == "style-line-width-invalid"
    table.set_borders(border_width_mm=0.4)
    with pytest.raises(HwpxValueError) as caught:
        document.page.set_footnote_shape(separator_width_mm=0.33)
    assert caught.value.code == "style-line-width-invalid"
    document.page.set_footnote_shape(separator_width_mm=0.3)
