# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools.id_integrity import check_id_integrity


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _first_element_with_attr(document: HwpxDocument, attr: str):
    for section in document.oxml.sections:
        for element in section.element.iter():
            if attr in element.attrib:
                return element
    for header in document.oxml.headers:
        for element in header.element.iter():
            if attr in element.attrib:
                return element
    raise AssertionError(f"fixture has no {attr}")


def test_clean_document_passes(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    path = tmp_path / "clean.hwpx"
    doc.save_to_path(path)

    report = check_id_integrity(HwpxDocument.open(path))

    assert report.ok is True
    assert report.dangling == []


def test_dangling_idref_detected(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    path = tmp_path / "dangling.hwpx"
    doc.save_to_path(path)
    broken = HwpxDocument.open(path)
    run = _first_element_with_attr(broken, "charPrIDRef")
    run.set("charPrIDRef", "999999")

    report = check_id_integrity(broken)

    assert report.ok is False
    assert any(
        item.attr == "charPrIDRef"
        and item.value == "999999"
        and item.table == "char_properties"
        for item in report.dangling
    )


@pytest.mark.parametrize(
    "name",
    [
        "reader_writer__SimplePicture.hwpx",
        "reader_writer__SimpleTable.hwpx",
        "reader_writer__HeaderFooter.hwpx",
    ],
)
def test_representative_corpus_documents_pass(name: str) -> None:
    report = check_id_integrity(HwpxDocument.open(CORPUS / name))

    assert report.ok is True
    assert report.dangling == []
