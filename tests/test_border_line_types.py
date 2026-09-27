# SPDX-License-Identifier: Apache-2.0
"""Border types are written the way Hancom spells them.

Hancom draws a border whose ``type`` it does not know as no border at all. Its 3D lines are
``THICK3D``, ``THICKREV3D``, ``3D`` and ``REV3D``; the longer names this library took before
(``THICK_3D``, ``THICK_3D_REVERSE_LIGHTING``, ``SLIM_3D``, ``SLIM_3D_REVERSE_LIGHTING``) are
written as those. ``fixtures/hancom_saved/border_3d.hwpx`` is a table Hancom made and saved
(author, version and dates removed) with its four 3D cell borders, each cell holding the name of
its border.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _border_types(document: HwpxDocument, fill_id: str, sides: str = "left|right|top|bottom") -> set[str]:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
    block = re.search(rf'<hh:borderFill id="{fill_id}".*?</hh:borderFill>', header, re.S)
    assert block is not None
    return set(re.findall(rf'<hh:(?:{sides})Border type="([^"]*)"', block.group(0)))


@pytest.mark.parametrize(
    ("border_type", "written"),
    [("THICK_3D", "THICK3D"), ("THICK_3D_REVERSE_LIGHTING", "THICKREV3D"), ("SLIM_3D", "3D"),
     ("SLIM_3D_REVERSE_LIGHTING", "REV3D"), ("slim_3d", "3D")],
)
def test_an_old_3d_name_is_written_as_hancom_spells_it(border_type: str, written: str) -> None:
    document = HwpxDocument.new()
    fill_id = document.styles.ensure_border_fill(border_type=border_type)
    assert _border_types(document, fill_id) == {written}


@pytest.mark.parametrize("border_type", ["THICK3D", "THICKREV3D", "3D", "REV3D", "WAVE", "DOUBLEWAVE", "LONG_DASH"])
def test_a_hancom_spelling_is_written_as_given(border_type: str) -> None:
    document = HwpxDocument.new()
    fill_id = document.styles.ensure_border_fill(border_type=border_type)
    assert _border_types(document, fill_id) == {border_type}


@pytest.mark.parametrize("border_type", ["DOUBLE_WAVE", "THICK_3D_REVERS", "XYZ"])
def test_a_spelling_hancom_does_not_know_is_refused(border_type: str) -> None:
    document = HwpxDocument.new()
    with pytest.raises(ValueError, match="unsupported border_type"):
        document.styles.ensure_border_fill(border_type=border_type)


def test_the_3d_names_are_the_ones_hancom_saves() -> None:
    hancom = HwpxDocument.open(FIXTURES / "border_3d.hwpx")
    table = next(table for paragraph in hancom.paragraphs for table in paragraph.tables)
    cells = [cell for row in table.rows for cell in row.cells]
    # Hancom gives a cell's right border the type it then sets on the cell to its right, so each
    # cell is read by its own left, top and bottom borders.
    saved = [_border_types(hancom, cell.element.get("borderFillIDRef"), "left|top|bottom") for cell in cells]
    assert [cell.text for cell in cells] == ["THICK3D", "THICKREV3D", "3D", "REV3D"]
    assert saved == [{"THICK3D"}, {"THICKREV3D"}, {"3D"}, {"REV3D"}]

    document = HwpxDocument.new()
    old_names = ("THICK_3D", "THICK_3D_REVERSE_LIGHTING", "SLIM_3D", "SLIM_3D_REVERSE_LIGHTING")
    written = [_border_types(document, document.styles.ensure_border_fill(border_type=name)) for name in old_names]

    assert written == saved
