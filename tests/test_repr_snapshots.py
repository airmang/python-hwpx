from __future__ import annotations

from typing import cast
import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument
from hwpx.oxml.document import HwpxOxmlDocument, HwpxOxmlSection
from hwpx.opc.package import HwpxPackage

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"


def _make_section_with_table() -> HwpxOxmlSection:
    section_element = ET.Element(f"{HS}sec")
    paragraph = ET.SubElement(section_element, f"{HP}p")
    run = ET.SubElement(paragraph, f"{HP}run", {"charPrIDRef": "1"})
    text = ET.SubElement(run, f"{HP}t")
    text.text = "x" * 10_000

    table = ET.SubElement(
        run,
        f"{HP}tbl",
        {
            "rowCnt": "2",
            "colCnt": "3",
            "borderFillIDRef": "1",
        },
    )
    for row_index in range(2):
        row = ET.SubElement(table, f"{HP}tr")
        for col_index in range(3):
            cell = ET.SubElement(row, f"{HP}tc")
            ET.SubElement(cell, f"{HP}cellAddr", {"rowAddr": str(row_index), "colAddr": str(col_index)})
            ET.SubElement(cell, f"{HP}cellSpan", {"rowSpan": "1", "colSpan": "1"})

    return HwpxOxmlSection("section0.xml", section_element)


def test_repr_snapshot_for_main_types() -> None:
    section = _make_section_with_table()
    paragraph = section.paragraphs[0]
    table = paragraph.tables[0]

    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    assert repr(document) == (
        "HwpxDocument(sections=1, paragraphs=1, headers=0, master_pages=0, histories=0, closed=False)"
    )
    assert repr(section) == "HwpxOxmlSection(part_name='section0.xml', paragraphs=1, memos=0)"
    assert repr(paragraph) == "HwpxOxmlParagraph(runs=1, tables=1, text_length=10000)"
    assert repr(table) == "HwpxOxmlTable(rows=2, cols=3, physical_rows=2)"


def test_repr_document_closed_state_snapshot() -> None:
    section = _make_section_with_table()
    root = HwpxOxmlDocument(ET.Element("manifest"), [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    document.close()

    assert repr(document) == (
        "HwpxDocument(sections=1, paragraphs=1, headers=0, master_pages=0, histories=0, closed=True)"
    )
