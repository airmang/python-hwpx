# SPDX-License-Identifier: Apache-2.0
"""Section columns are set on the section's own column definition.

Hancom lays out a section with the ``hp:colPr`` in the run that carries
``hp:secPr``. ``page.setup(columns=...)`` and ``page.set_columns()`` rewrite
that definition in place; ``page.set_columns(paragraph=...)`` starts new
columns at a paragraph.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.package_validator import validate_editor_open_safety

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _section_xml(document: HwpxDocument) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return etree.fromstring(archive.read("Contents/section0.xml"))


def _column_definitions(root: etree._Element) -> list[etree._Element]:
    return list(root.iter(f"{HP}colPr"))


def _section_column_definition(root: etree._Element) -> etree._Element:
    first_paragraph = root.find(f"{HP}p")
    assert first_paragraph is not None
    carrier = next(run for run in first_paragraph.findall(f"{HP}run") if run.find(f"{HP}secPr") is not None)
    col_pr = carrier.find(f"{HP}ctrl/{HP}colPr")
    assert col_pr is not None
    return col_pr


def _document_with_body() -> HwpxDocument:
    document = HwpxDocument.new()
    for index in range(3):
        document.add_paragraph(f"본문 {index}")
    return document


def test_setup_columns_rewrites_the_section_definition_in_place() -> None:
    document = _document_with_body()
    paragraphs = len(document.paragraphs)

    document.page.setup(columns=2, column_gap_mm=8)

    assert len(document.paragraphs) == paragraphs
    root = _section_xml(document)
    assert len(_column_definitions(root)) == 1
    col_pr = _section_column_definition(root)
    assert (col_pr.get("colCount"), col_pr.get("sameSz"), col_pr.get("sameGap")) == ("2", "1", "2268")
    assert (col_pr.get("type"), col_pr.get("layout")) == ("NEWSPAPER", "LEFT")


def test_set_columns_without_a_paragraph_sets_the_whole_section() -> None:
    document = _document_with_body()
    paragraphs = len(document.paragraphs)

    control = document.page.set_columns(3, same_gap=567, separator_type="SOLID")

    assert len(document.paragraphs) == paragraphs
    assert control.element.tag == f"{HP}ctrl"
    root = _section_xml(document)
    assert len(_column_definitions(root)) == 1
    col_pr = _section_column_definition(root)
    assert (col_pr.get("colCount"), col_pr.get("sameGap")) == ("3", "567")
    line = col_pr.find(f"{HP}colLine")
    assert line is not None
    assert (line.get("type"), line.get("width"), line.get("color")) == ("SOLID", "0.12 mm", "#000000")


def test_unequal_columns_write_their_sizes() -> None:
    document = _document_with_body()

    document.page.set_columns(2, same_size=False, column_widths=[(20000, 1000), (21520, 0)])

    col_pr = _section_column_definition(_section_xml(document))
    assert (col_pr.get("sameSz"), col_pr.get("sameGap")) == ("0", "0")
    sizes = [(size.get("width"), size.get("gap")) for size in col_pr.findall(f"{HP}colSz")]
    assert sizes == [("20000", "1000"), ("21520", "0")]


def test_setting_one_column_clears_the_previous_layout() -> None:
    document = _document_with_body()
    document.page.set_columns(2, separator_type="SOLID")

    document.page.setup(columns=1)

    col_pr = _section_column_definition(_section_xml(document))
    assert col_pr.get("colCount") == "1"
    assert col_pr.find(f"{HP}colLine") is None


def test_set_columns_at_a_paragraph_starts_new_columns_there() -> None:
    document = _document_with_body()
    paragraph = document.paragraphs[2]

    document.page.set_columns(2, paragraph=paragraph)

    root = _section_xml(document)
    assert _section_column_definition(root).get("colCount") == "1"
    counts = [col_pr.get("colCount") for col_pr in _column_definitions(root)]
    assert counts == ["1", "2"]
    started = paragraph.element.find(f"{HP}run/{HP}ctrl/{HP}colPr")
    assert started is not None
    # Hancom writes a column definition with an empty id and a 1/0 sameSz.
    assert (started.get("id"), started.get("sameSz")) == ("", "1")


def test_a_section_without_a_column_definition_gets_one_next_to_secpr() -> None:
    document = _document_with_body()
    section_properties = document.sections[0].properties.element
    carrier = next(
        run for run in document.sections[0].element.iter(f"{HP}run")
        if any(child is section_properties for child in run)
    )
    for ctrl in [ctrl for ctrl in carrier.findall(f"{HP}ctrl") if ctrl.find(f"{HP}colPr") is not None]:
        carrier.remove(ctrl)

    document.page.set_columns(2)

    children = list(carrier)
    position = children.index(section_properties)
    added = children[position + 1]
    assert added.tag == f"{HP}ctrl"
    assert added.find(f"{HP}colPr").get("colCount") == "2"


def test_columns_survive_a_save_and_stay_open_safe(tmp_path: Path) -> None:
    document = _document_with_body()
    document.page.setup(columns=2, column_gap_mm=8)
    path = tmp_path / "columns.hwpx"
    document.save_to_path(path)

    assert validate_editor_open_safety(path).ok
    reopened = HwpxDocument.open(path)
    col_pr = _section_column_definition(_section_xml(reopened))
    assert col_pr.get("colCount") == "2"


@pytest.mark.parametrize("count", [0, 256])
def test_an_out_of_range_column_count_is_rejected(count: int) -> None:
    document = _document_with_body()

    with pytest.raises(HwpxValueError) as caught:
        document.page.set_columns(count)

    assert caught.value.code == "page-columns-invalid"
