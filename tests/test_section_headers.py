"""Regression coverage for section header/footer apply/link handling."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from typing import cast

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlDocument, HwpxOxmlSection
from hwpx.opc.package import HwpxPackage


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"
FUZZ_BASELINE = Path(__file__).parent / "fixtures/fuzz_regressions/seed-000000-baseline.hwpx"


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


def _mirrored_stories(
    section: HwpxOxmlSection, kind: str, native_id: str
) -> list[ET.Element]:
    return [
        story
        for story in section.element.findall(f".//{HP}ctrl/{HP}{kind}")
        if story.get("id") == native_id
    ]


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


def test_header_footer_helpers_work_on_real_hwpx_document() -> None:
    document = HwpxDocument.new()

    document.set_header_text("Header {{HDR1}}")
    document.set_footer_text("Footer {{FTR1}}")

    reopened = HwpxDocument.open(document.to_bytes())

    header = reopened.sections[0].properties.get_header()
    footer = reopened.sections[0].properties.get_footer()

    assert header is not None
    assert footer is not None
    assert header.text == "Header {{HDR1}}"
    assert footer.text == "Footer {{FTR1}}"


def test_preserving_header_text_adds_only_missing_target_mirror() -> None:
    document = HwpxDocument.open(FUZZ_BASELINE)
    section = document.sections[0]
    target = section.properties.get_header("BOTH")
    unrelated = section.properties.get_header("EVEN")
    assert target is not None and target.id is not None
    assert unrelated is not None and unrelated.id is not None
    assert _mirrored_stories(section, "header", target.id) == []

    target_paragraph = target.element.find(f"{HP}subList/{HP}p")
    target_run = target.element.find(f"{HP}subList/{HP}p/{HP}run")
    unrelated_logical_before = ET.tostring(unrelated.element)
    unrelated_mirror_before = ET.tostring(
        _mirrored_stories(section, "header", unrelated.id)[0]
    )

    section.reset_dirty()
    target.set_simple_text_preserving("S-080 preserved header")

    mirrors = _mirrored_stories(section, "header", target.id)
    assert len(mirrors) == 1
    assert target.text == "S-080 preserved header"
    assert "".join(mirrors[0].itertext()) == "S-080 preserved header"
    assert target.element.find(f"{HP}subList/{HP}p") is target_paragraph
    assert target.element.find(f"{HP}subList/{HP}p/{HP}run") is target_run
    assert ET.tostring(unrelated.element) == unrelated_logical_before
    assert ET.tostring(_mirrored_stories(section, "header", unrelated.id)[0]) == (
        unrelated_mirror_before
    )
    assert section.dirty is True


def test_preserving_header_text_updates_existing_mirror_in_place() -> None:
    document = HwpxDocument.open(FUZZ_BASELINE)
    section = document.sections[0]
    target = section.properties.get_header("BOTH")
    assert target is not None and target.id is not None
    target.set_simple_text_preserving("first value")
    mirror = _mirrored_stories(section, "header", target.id)[0]
    mirror_paragraph = mirror.find(f"{HP}subList/{HP}p")
    mirror_run = mirror.find(f"{HP}subList/{HP}p/{HP}run")

    target.set_simple_text_preserving("second value")

    mirrors = _mirrored_stories(section, "header", target.id)
    assert mirrors == [mirror]
    assert mirrors[0].find(f"{HP}subList/{HP}p") is mirror_paragraph
    assert mirrors[0].find(f"{HP}subList/{HP}p/{HP}run") is mirror_run
    assert target.text == "second value"
    assert "".join(mirror.itertext()) == "second value"


@pytest.mark.parametrize("invalid_text", ["tab\ttext", "line\nbreak", "bad\x01text"])
def test_preserving_header_text_rejects_structural_text_without_mutation(
    invalid_text: str,
) -> None:
    document = HwpxDocument.open(FUZZ_BASELINE)
    section = document.sections[0]
    target = section.properties.get_header("BOTH")
    assert target is not None
    before = ET.tostring(section.element)
    section.reset_dirty()

    with pytest.raises(ValueError):
        target.set_simple_text_preserving(invalid_text)

    assert ET.tostring(section.element) == before
    assert section.dirty is False


def test_preserving_header_text_rejects_rich_story_without_mutation() -> None:
    document = HwpxDocument.open(FUZZ_BASELINE)
    section = document.sections[0]
    target = section.properties.get_header("BOTH")
    assert target is not None
    paragraph = target.element.find(f"{HP}subList/{HP}p")
    assert paragraph is not None
    paragraph.append(paragraph.makeelement(f"{HP}run", {"charPrIDRef": "0"}))
    before = ET.tostring(section.element)
    section.reset_dirty()

    with pytest.raises(ValueError, match="rich or control-bearing"):
        target.set_simple_text_preserving("must fail")

    assert ET.tostring(section.element) == before
    assert section.dirty is False


def test_preserving_header_text_rejects_duplicate_mirror_without_mutation() -> None:
    document = HwpxDocument.open(FUZZ_BASELINE)
    section = document.sections[0]
    target = section.properties.get_header("BOTH")
    assert target is not None and target.id is not None
    target.set_simple_text_preserving("mirrored")
    mirror = _mirrored_stories(section, "header", target.id)[0]
    original_control = next(
        control
        for control in section.element.findall(f".//{HP}ctrl")
        if mirror in list(control)
    )
    duplicate_control = deepcopy(original_control)
    original_run = next(
        run
        for run in section.element.findall(f".//{HP}run")
        if original_control in list(run)
    )
    original_run.append(duplicate_control)
    before = ET.tostring(section.element)
    section.reset_dirty()

    with pytest.raises(ValueError, match="ambiguous"):
        target.set_simple_text_preserving("must fail")

    assert ET.tostring(section.element) == before
    assert section.dirty is False
