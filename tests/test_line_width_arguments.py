# SPDX-License-Identifier: Apache-2.0
"""Border and column-line widths are written as one of Hancom's line widths, or refused.

Hancom keeps a width only when it is one of the ``hc:LineWidth`` strings (``0.1 mm`` …
``5.0 mm``) exactly; ``1 mm``, ``2 mm`` or ``0.12mm`` are drawn as ``0.1 mm``.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.utils import LINE_WIDTHS, normalize_line_width


@pytest.mark.parametrize(
    ("value", "written"),
    [("1 mm", "1.0 mm"), ("1mm", "1.0 mm"), (1, "1.0 mm"), (0.5, "0.5 mm"), ("0.12MM", "0.12 mm"), (" 2 mm ", "2.0 mm"),
     ("0.4", "0.4 mm")],
)
def test_a_width_on_the_list_is_written_the_way_hancom_writes_it(value: object, written: str) -> None:
    assert normalize_line_width(value) == written  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["0.13 mm", "6 mm", "40", "thick", "", "1 cm"])
def test_a_width_off_the_list_is_refused(value: str) -> None:
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
    fill_id = document.styles.ensure_border_fill(border_width="1 mm")

    block = re.search(rf'<hh:borderFill id="{fill_id}".*?</hh:borderFill>', _header_xml(document), re.S)

    assert block is not None
    assert set(re.findall(r'<hh:(?:left|right|top|bottom)Border [^>]*width="([^"]*)"', block.group(0))) == {"1.0 mm"}


def test_a_border_fill_width_off_the_list_is_refused() -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="not one of Hancom's line widths"):
        document.styles.ensure_border_fill(border_width="0.13 mm")


def test_a_paragraph_border_width_goes_through_the_same_check() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("테두리 문단")
    index = len(document.paragraphs) - 1
    with pytest.raises(HwpxValueError, match="not one of Hancom's line widths"):
        document.styles.apply_paragraph_format(paragraph_index=index, border={"width": "3 pt"})
    with pytest.raises(HwpxValueError, match="not one of Hancom's line widths"):
        document.styles.apply_paragraph_format(paragraph_index=index, bottom_border=True, border_width="1 cm")


def test_a_column_separator_width_is_written_from_the_list() -> None:
    document = HwpxDocument.new()
    document.page.set_columns(2, separator_type="SOLID", separator_width="0.5mm")
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert re.search(r'<hp:colLine [^>]*width="0.5 mm"', section)

    with pytest.raises(HwpxValueError, match="not one of Hancom's line widths"):
        document.page.set_columns(2, separator_type="SOLID", separator_width="thick")
