"""Regression coverage for section header/footer apply/link handling."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from typing import cast

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlDocument, HwpxOxmlSection
from hwpx.opc.package import HwpxPackage


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"


def _build_section_with_sec_pr() -> tuple[HwpxOxmlSection, ET.Element]:
    section_element = ET.Element(f"{HS}sec")
    paragraph_element = ET.SubElement(
        section_element,
        f"{HP}p",
        {"paraPrIDRef": "0", "styleIDRef": "0"},
    )
    run_element = ET.SubElement(paragraph_element, f"{HP}run", {"charPrIDRef": "0"})
    sec_pr = ET.SubElement(run_element, f"{HP}secPr")
    section = HwpxOxmlSection("section0.xml", section_element)
    section.reset_dirty()
    return section, sec_pr


def _apply_reference(apply_element: ET.Element, *candidates: str) -> str | None:
    for name in candidates:
        value = apply_element.get(name)
        if value:
            return value
    return None


def test_set_header_text_creates_header_apply() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    properties = section.properties

    header = properties.set_header_text("Confidential", page_type="BOTH")

    header_element = sec_pr.find(f"{HP}header")
    header_apply = sec_pr.find(f"{HP}headerApply")

    assert header_element is not None
    assert header_apply is not None
    assert header_apply.get("applyPageType") == "BOTH"
    assert _apply_reference(header_apply, "idRef", "headerIDRef", "headerRef") == header.id


def test_set_footer_text_creates_footer_apply() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    properties = section.properties

    footer = properties.set_footer_text("Page", page_type="ODD")

    footer_element = sec_pr.find(f"{HP}footer")
    footer_apply = sec_pr.find(f"{HP}footerApply")

    assert footer_element is not None
    assert footer.apply_page_type == "ODD"
    assert footer_apply is not None
    assert footer_apply.get("applyPageType") == "ODD"
    assert _apply_reference(footer_apply, "idRef", "footerIDRef", "footerRef") == footer.id


def test_header_wrapper_updates_apply_attributes() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    properties = section.properties
    wrapper = properties.set_header_text("Initial", page_type="BOTH")

    header_apply = sec_pr.find(f"{HP}headerApply")
    assert header_apply is not None

    section.reset_dirty()
    wrapper.apply_page_type = "EVEN"
    assert header_apply.get("applyPageType") == "EVEN"
    assert section.dirty is True

    section.reset_dirty()
    wrapper.id = "777"
    assert header_apply.get("idRef") == "777"
    assert wrapper.id == "777"
    assert section.dirty is True


def test_remove_header_removes_header_apply() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    properties = section.properties
    properties.set_header_text("To be removed", page_type="BOTH")
    section.reset_dirty()

    properties.remove_header(page_type="BOTH")

    assert sec_pr.find(f"{HP}header") is None
    assert sec_pr.find(f"{HP}headerApply") is None
    assert section.dirty is True


def test_existing_header_apply_attribute_is_preserved() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    header_element = ET.SubElement(
        sec_pr,
        f"{HP}header",
        {"id": "55", "applyPageType": "BOTH"},
    )
    ET.SubElement(header_element, f"{HP}subList")
    header_apply = ET.SubElement(
        sec_pr,
        f"{HP}headerApply",
        {"applyPageType": "BOTH", "headerIDRef": "999"},
    )

    section.reset_dirty()
    wrapper = section.properties.get_header()
    assert wrapper is not None

    section.reset_dirty()
    wrapper.id = "101"
    assert header_element.get("id") == "101"
    assert header_apply.get("headerIDRef") == "101"
    assert "idRef" not in header_apply.attrib
    assert section.dirty is True


def test_document_helpers_manage_header_apply_nodes() -> None:
    section, sec_pr = _build_section_with_sec_pr()
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    document.set_header_text("Doc Header", section=section)
    header_apply = sec_pr.find(f"{HP}headerApply")
    assert header_apply is not None

    document.remove_header(section=section)
    assert sec_pr.find(f"{HP}headerApply") is None
