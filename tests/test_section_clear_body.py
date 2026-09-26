# SPDX-License-Identifier: Apache-2.0
"""``Section.clear_body()``.

Blanking a document down to a template keeps the page setup (``hp:secPr``)
and section controls (``hp:ctrl``) of the first run and removes the rest of
the body. The success path must write exactly the bytes that the hand-rolled
tree edit callers used before this primitive existed, so the byte tests below
replay that edit on one copy and ``clear_body()`` on another.
"""

from __future__ import annotations

import copy
import io
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import ClearBodyReport
from hwpx.oxml.body import INLINE_OBJECT_NAMES
from hwpx.oxml.namespaces import HP, tag_local_name

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


# --------------------------------------------------------------------------
# Test-local replay of the pre-primitive tree edit (raw elements only)


def _content_tags_in(run: etree._Element) -> list[str]:
    tags: list[str] = []
    forbidden = INLINE_OBJECT_NAMES | {"tbl"}
    for node in run.iter():
        if node is run:
            continue
        name = tag_local_name(node.tag)
        if name == "t":
            if not (node.text or "").strip():
                continue
        elif name not in forbidden:
            continue
        tag = f"hp:{name}"
        if tag not in tags:
            tags.append(tag)
    return tags


def _replay_manual_blank(section) -> dict[str, int]:
    first = section.paragraphs[0]
    later_runs = first.runs[1:]
    for run in later_runs:
        run.remove()
    first_run = first.element.find(f"{HP}run")
    kept = {f"{HP}secPr", f"{HP}ctrl"}
    stripped = 0
    for child in list(first_run):
        if child.tag not in kept:
            first_run.remove(child)
            stripped += 1
    if _content_tags_in(first_run):
        raise AssertionError("fixture holds control content; the replay would refuse it")
    for cache in first.element.findall(f"{HP}linesegarray"):
        first.element.remove(cache)
    later_paragraphs = section.paragraphs[1:]
    for paragraph in later_paragraphs:
        paragraph.remove()
    section.mark_dirty()
    return {
        "removed_paragraphs": len(later_paragraphs),
        "removed_runs": len(later_runs),
        "stripped_run_children": stripped,
    }


# --------------------------------------------------------------------------
# Fixtures


def _generated_source() -> bytes:
    """Many paragraphs, tables, a picture, and text beside secPr/ctrl."""

    document = HwpxDocument.new()
    first = document.sections[0].paragraphs[0]
    first.text = "첫 문단 본문"
    first.add_table(2, 2)
    item = document.media.add_image(_PNG, "png")
    picture = first.add_picture(str(item))
    first.add_table(1, 3)
    document.add_paragraph("둘째 문단")
    document.add_table(3, 2)
    document.add_paragraph("셋째 문단")
    document.add_picture(_PNG, "png")
    document.add_paragraph("넷째 문단")

    # Move a table and the picture into the first run itself, next to
    # secPr/ctrl/t, so the whitelist strip has objects to remove.
    first_run = first.runs[0].element
    later_run = first.runs[1].element
    table = later_run.find(f"{HP}tbl")
    first_run.append(copy.deepcopy(table))
    first_run.append(copy.deepcopy(picture.element))
    document.sections[0].mark_dirty()
    return document.to_bytes()


_REAL_FIXTURES = (
    # 38 paragraphs, two runs in the first paragraph, several sections.
    "m3_gongmun_gold/mfds_admin_notice.hwpx",
    # secPr, ctrl, tbl and t all in the first run.
    "hwpxlib_corpus/error__20241104__mot.hwpx",
    # 101 paragraphs, layout caches on the first paragraph.
    "exam/A_form.hwpx",
)


def _sources() -> list[tuple[str, bytes]]:
    sources = [("generated", _generated_source())]
    for name in _REAL_FIXTURES:
        sources.append((name, (FIXTURES / name).read_bytes()))
    return sources


def _open(data: bytes) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(data))


# --------------------------------------------------------------------------
# Byte preservation against the manual edit


@pytest.mark.parametrize("name,data", _sources(), ids=[name for name, _ in _sources()])
def test_clear_body_writes_the_same_bytes_as_the_manual_edit(name: str, data: bytes) -> None:
    replayed = _open(data)
    cleared = _open(data)

    expected = _replay_manual_blank(replayed.sections[0])
    report = cleared.sections[0].clear_body()

    assert cleared.to_bytes() == replayed.to_bytes()
    assert isinstance(report, ClearBodyReport)
    assert report.removed_paragraphs == expected["removed_paragraphs"]
    assert report.removed_runs == expected["removed_runs"]
    assert report.stripped_run_children == expected["stripped_run_children"]
    assert report.control_content == ()
    assert report.stripped_controls == 0


def test_the_generated_fixture_exercises_every_removal_step() -> None:
    document = _open(_generated_source())
    section = document.sections[0]
    first_run_names = [tag_local_name(child.tag) for child in section.paragraphs[0].runs[0].element]
    assert {"secPr", "ctrl", "t", "tbl", "pic"} <= set(first_run_names)

    report = section.clear_body()

    assert report.removed_paragraphs >= 4
    assert report.removed_runs >= 2
    assert report.stripped_run_children == 3  # t, tbl, pic
    (paragraph,) = section.paragraphs
    (run,) = paragraph.runs
    assert [tag_local_name(child.tag) for child in run.element] == ["secPr", "ctrl"]
    assert paragraph.element.find(f"{HP}linesegarray") is None
    assert section.dirty


@pytest.mark.parametrize("name,data", _sources(), ids=[name for name, _ in _sources()])
def test_a_cleared_section_saves_reopens_and_validates(name: str, data: bytes) -> None:
    document = _open(data)
    section_properties = etree.tostring(document.sections[0].element.find(f".//{HP}secPr"))
    document.sections[0].clear_body()

    reopened = _open(document.to_bytes())

    assert reopened.validate().ok
    (paragraph,) = reopened.sections[0].paragraphs
    assert paragraph.text == ""
    assert etree.tostring(reopened.sections[0].element.find(f".//{HP}secPr")) == section_properties


def test_clear_body_leaves_other_section_children_and_attributes_alone() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    section = document.sections[0]
    section.add_memo("메모")
    attributes_before = dict(section.element.attrib)
    first_attributes_before = dict(section.paragraphs[0].element.attrib)

    section.clear_body()

    assert dict(section.element.attrib) == attributes_before
    assert dict(section.paragraphs[0].element.attrib) == first_attributes_before
    assert section.element.find(f"{HP}memogroup") is not None


def test_clear_body_report_to_dict_is_camel_case() -> None:
    report = ClearBodyReport(
        removed_paragraphs=3,
        removed_runs=1,
        stripped_run_children=2,
        control_content=("hp:t",),
        stripped_controls=1,
    )
    assert report.to_dict() == {
        "removedParagraphs": 3,
        "removedRuns": 1,
        "strippedRunChildren": 2,
        "controlContent": ["hp:t"],
        "strippedControls": 1,
    }


# --------------------------------------------------------------------------
# Control content: raise / keep / strip


def _with_header_text() -> bytes:
    document = HwpxDocument.new()
    document.page.set_header(text="머리말 글")
    document.add_paragraph("본문")
    first_run = document.sections[0].paragraphs[0].runs[0].element
    names = [tag_local_name(child.tag) for child in first_run]
    assert names.count("ctrl") == 2, names  # colPr ctrl + header ctrl
    return document.to_bytes()


def test_control_content_raises_by_default_and_changes_nothing() -> None:
    data = _with_header_text()
    document = _open(data)
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        document.sections[0].clear_body()

    assert caught.value.code == "section-clear-control-content"
    assert caught.value.context["tags"] == ["hp:t"]
    assert isinstance(caught.value, ValueError)
    assert document.to_bytes() == before
    assert not document.sections[0].dirty


def test_control_content_can_be_kept_and_reported() -> None:
    document = _open(_with_header_text())
    section = document.sections[0]

    report = section.clear_body(on_control_content="keep")

    assert report.control_content == ("hp:t",)
    assert report.stripped_controls == 0
    names = [tag_local_name(child.tag) for child in section.paragraphs[0].runs[0].element]
    assert names == ["secPr", "ctrl", "ctrl"]
    assert "머리말 글" in etree.tostring(section.element, encoding="unicode")


def test_control_content_can_be_stripped() -> None:
    document = _open(_with_header_text())
    section = document.sections[0]

    report = section.clear_body(on_control_content="strip")

    assert report.control_content == ("hp:t",)
    assert report.stripped_controls == 1
    names = [tag_local_name(child.tag) for child in section.paragraphs[0].runs[0].element]
    assert names == ["secPr", "ctrl"]
    (control,) = section.paragraphs[0].runs[0].element.findall(f"{HP}ctrl")
    assert "머리말 글" not in etree.tostring(control, encoding="unicode")
    assert _open(document.to_bytes()).validate().ok


def test_strip_never_touches_section_properties() -> None:
    # set_header() also writes a non-schema copy of the story into hp:secPr
    # (Hancom reads only the hp:ctrl one and drops the copy when it saves).
    # "strip" removes controls only, so that copy stays; the scan reported it.
    document = _open(_with_header_text())
    section = document.sections[0]
    section_properties = section.paragraphs[0].runs[0].element.find(f"{HP}secPr")
    before = etree.tostring(section_properties)

    section.clear_body(on_control_content="strip")

    assert etree.tostring(section.paragraphs[0].runs[0].element.find(f"{HP}secPr")) == before


def test_control_content_tags_come_in_first_seen_order_without_duplicates() -> None:
    document = HwpxDocument.new()
    first_run = document.sections[0].paragraphs[0].runs[0].element
    ctrl = etree.SubElement(first_run, f"{HP}ctrl")
    footer = etree.SubElement(ctrl, f"{HP}footer")
    sub_list = etree.SubElement(footer, f"{HP}subList")
    for text in ("가", "나"):
        paragraph = etree.SubElement(sub_list, f"{HP}p")
        run = etree.SubElement(paragraph, f"{HP}run")
        etree.SubElement(run, f"{HP}tbl")
        etree.SubElement(run, f"{HP}t").text = text
        etree.SubElement(run, f"{HP}rect")
    # Whitespace-only text is not content.
    etree.SubElement(etree.SubElement(ctrl, f"{HP}header"), f"{HP}t").text = "  "

    with pytest.raises(HwpxValueError) as caught:
        document.sections[0].clear_body()

    assert caught.value.context["tags"] == ["hp:tbl", "hp:t", "hp:rect"]


def test_the_real_header_footer_fixture_is_refused_and_can_be_stripped() -> None:
    data = (FIXTURES / "hwpxlib_corpus/reader_writer__HeaderFooter.hwpx").read_bytes()

    with pytest.raises(HwpxValueError) as caught:
        _open(data).sections[0].clear_body()
    assert caught.value.code == "section-clear-control-content"
    assert "hp:t" in caught.value.context["tags"]

    document = _open(data)
    report = document.sections[0].clear_body(on_control_content="strip")
    assert report.stripped_controls >= 1
    assert "hp:t" in report.control_content
    reopened = _open(document.to_bytes())
    assert reopened.validate().ok
    assert _content_tags_in(reopened.sections[0].paragraphs[0].runs[0].element) == []


# --------------------------------------------------------------------------
# Preconditions fail before any mutation


def test_an_unknown_mode_is_refused_before_anything_changes() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        document.sections[0].clear_body(on_control_content="report")

    assert caught.value.code == "section-clear-mode-invalid"
    assert document.to_bytes() == before


def test_a_first_run_without_section_properties_is_refused() -> None:
    data = (FIXTURES / "reader_robustness/irb_form_blank.hwpx").read_bytes()
    section = _open(data).sections[0]
    before = etree.tostring(section.element)

    with pytest.raises(HwpxValueError) as caught:
        section.clear_body()

    assert caught.value.code == "section-clear-no-section-properties"
    assert etree.tostring(section.element) == before
    assert not section.dirty


def test_section_properties_outside_the_first_run_are_refused() -> None:
    document = HwpxDocument.new()
    first = document.sections[0].paragraphs[0]
    first.element.insert(0, first.element.makeelement(f"{HP}run", {"charPrIDRef": "0"}))
    document.add_paragraph("본문")
    before = document.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        document.sections[0].clear_body()

    assert caught.value.code == "section-clear-no-section-properties"
    assert document.to_bytes() == before


def test_a_section_without_paragraphs_is_refused() -> None:
    document = HwpxDocument.new()
    section = document.sections[0]
    for paragraph in list(section.element):
        section.element.remove(paragraph)

    with pytest.raises(HwpxValueError) as caught:
        section.clear_body()

    assert caught.value.code == "section-clear-no-section-properties"


def test_clear_body_is_idempotent() -> None:
    document = _open(_generated_source())
    section = document.sections[0]
    section.clear_body()
    once = document.to_bytes()

    report = section.clear_body()

    assert report == ClearBodyReport(0, 0, 0, (), 0)
    assert document.to_bytes() == once
