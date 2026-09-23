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


def _control_page_types(section: HwpxOxmlSection, kind: str) -> list[str]:
    return sorted(
        story.get("applyPageType", "BOTH")
        for story in section.element.findall(f".//{HP}ctrl/{HP}{kind}")
    )


def _control_text(section: HwpxOxmlSection, kind: str, page_type: str) -> str:
    (story,) = [
        story
        for story in section.element.findall(f".//{HP}ctrl/{HP}{kind}")
        if story.get("applyPageType", "BOTH") == page_type
    ]
    return "".join(t.text or "" for t in story.iter(f"{HP}t"))


def test_footers_of_different_page_types_each_keep_a_hancom_control() -> None:
    # Hancom reads stories from hp:ctrl only and drops the hp:secPr copies on
    # save. Syncing the BOTH footer used to delete the ODD footer's control, so
    # the ODD text vanished in Hancom.
    section, _ = _build_section_with_sec_pr()
    properties = section.properties

    properties.set_footer_text("odd pages", page_type="ODD")
    properties.set_footer_text("every page", page_type="BOTH")

    assert _control_page_types(section, "footer") == ["BOTH", "ODD"]
    assert _control_text(section, "footer", "ODD") == "odd pages"


def _control_order(section: HwpxOxmlSection, kind: str) -> list[str]:
    return [
        story.get("applyPageType", "BOTH")
        for story in section.element.findall(f".//{HP}ctrl/{HP}{kind}")
    ]


@pytest.mark.parametrize("first", ["BOTH", "ODD"])
def test_page_specific_story_follows_the_both_story_whatever_the_call_order(first: str) -> None:
    # On each page Hancom draws the last applicable control in document order
    # -- with BOTH after ODD the ODD footer never showed. BOTH must come first
    # so ODD/EVEN override it on their pages.
    section, _ = _build_section_with_sec_pr()
    properties = section.properties
    second = "ODD" if first == "BOTH" else "BOTH"

    properties.set_footer_text(f"{first} text", page_type=first)
    properties.set_footer_text(f"{second} text", page_type=second)
    properties.set_footer_text("even text", page_type="EVEN")

    order = _control_order(section, "footer")
    assert order[0] == "BOTH"
    assert sorted(order[1:]) == ["EVEN", "ODD"]


def test_resetting_a_page_type_replaces_only_its_own_control() -> None:
    section, _ = _build_section_with_sec_pr()
    properties = section.properties

    properties.set_header_text("odd", page_type="ODD")
    properties.set_header_text("even", page_type="EVEN")
    properties.set_header_text("odd again", page_type="ODD")

    assert _control_page_types(section, "header") == ["EVEN", "ODD"]
    assert _control_text(section, "header", "ODD") == "odd again"


def test_removing_one_page_type_keeps_the_other_controls() -> None:
    section, _ = _build_section_with_sec_pr()
    properties = section.properties
    properties.set_header_text("odd", page_type="ODD")
    properties.set_header_text("even", page_type="EVEN")

    properties.remove_header(page_type="EVEN")

    assert _control_page_types(section, "header") == ["ODD"]


def test_page_number_footer_keeps_an_existing_footer_of_another_page_type() -> None:
    # The corpus case end to end: set_footer(ODD) then set_page_number (BOTH).
    document = HwpxDocument.new()
    document.page.set_footer(text="담당부서 배포", page_type="ODD")
    document.page.set_page_number(position="BOTTOM_CENTER", prefix="- ", suffix=" -")

    reopened = HwpxDocument.open(document.to_bytes())
    section = reopened.sections[0]

    assert _control_order(section, "footer") == ["BOTH", "ODD"]
    assert _control_text(section, "footer", "ODD") == "담당부서 배포"


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
    target.set_simple_text_preserving("preserved header text")

    mirrors = _mirrored_stories(section, "header", target.id)
    assert len(mirrors) == 1
    assert target.text == "preserved header text"
    assert "".join(mirrors[0].itertext()) == "preserved header text"
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
