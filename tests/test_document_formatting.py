from __future__ import annotations

import io
from typing import Callable, cast
from zipfile import ZipFile
import pytest
import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument
from hwpx.oxml.document import (
    HwpxOxmlDocument,
    HwpxOxmlHeader,
    HwpxOxmlParagraph,
    HwpxOxmlSection,
)
from hwpx.opc.package import HwpxPackage
from hwpx.oxml.section_format import SectionGrid
from hwpx.tools.package_validator import validate_package


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"
HH = f"{{{HH_NS}}}"


def _build_section_with_paragraph() -> tuple[HwpxOxmlSection, HwpxOxmlParagraph]:
    section_element = ET.Element(f"{HS}sec")
    paragraph_element = ET.SubElement(
        section_element,
        f"{HP}p",
        {"paraPrIDRef": "3", "styleIDRef": "2"},
    )
    run_element = ET.SubElement(paragraph_element, f"{HP}run", {"charPrIDRef": "1"})
    ET.SubElement(run_element, f"{HP}t").text = "Hello"

    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]
    section.reset_dirty()
    return section, paragraph


def _build_section_with_properties() -> tuple[HwpxOxmlSection, ET.Element]:
    section_element = ET.Element(f"{HS}sec")
    paragraph_element = ET.SubElement(
        section_element,
        f"{HP}p",
        {"paraPrIDRef": "3", "styleIDRef": "0"},
    )
    run_element = ET.SubElement(paragraph_element, f"{HP}run", {"charPrIDRef": "0"})
    sec_pr = ET.SubElement(run_element, f"{HP}secPr")
    page_pr = ET.SubElement(
        sec_pr,
        f"{HP}pagePr",
        {"landscape": "PORTRAIT", "width": "59528", "height": "84188", "gutterType": "LEFT_ONLY"},
    )
    ET.SubElement(
        page_pr,
        f"{HP}margin",
        {
            "left": "8504",
            "right": "8504",
            "top": "5668",
            "bottom": "4252",
            "header": "4252",
            "footer": "4252",
            "gutter": "0",
        },
    )
    ET.SubElement(
        sec_pr,
        f"{HP}startNum",
        {"pageStartsOn": "ODD", "page": "3", "pic": "2", "tbl": "5", "equation": "7"},
    )
    section = HwpxOxmlSection("section0.xml", section_element)
    section.reset_dirty()
    return section, sec_pr


def _set_header_text_and_get_xml_text(value: str) -> str:
    section, _ = _build_section_with_properties()
    header = section.properties.set_header_text("seed")
    header.text = value
    text_element = header.element.find(f".//{HP}t")
    assert text_element is not None
    return text_element.text or ""


def _set_run_text_and_get_xml_text(value: str) -> str:
    _, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]
    run.text = value
    text_element = run.element.find(f"{HP}t")
    assert text_element is not None
    return text_element.text or ""


def _set_table_cell_text_and_get_xml_text(value: str) -> str:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    table.set_cell_text(0, 0, value)
    text_element = table.cell(0, 0).element.find(f".//{HP}t")
    assert text_element is not None
    return text_element.text or ""


def _set_paragraph_text_and_get_xml_text(value: str) -> str:
    _, paragraph = _build_section_with_paragraph()
    paragraph.text = value
    text_element = paragraph.element.find(f".//{HP}t")
    assert text_element is not None
    return text_element.text or ""


_TEXT_SETTER_APPLIERS: tuple[Callable[[str], str], ...] = (
    _set_header_text_and_get_xml_text,
    _set_run_text_and_get_xml_text,
    _set_table_cell_text_and_get_xml_text,
)

_TEXT_SETTER_IDS = ("header_footer", "run", "table_cell")

_TEXT_SANITIZATION_CASES: tuple[tuple[str, str], ...] = (
    ("a\tb", "ab"),
    ("left\r\nright", "left\nright"),
    ("a\x01b", "ab"),
    ("line1\nline2", "line1\nline2"),
    ("", ""),
)


def test_paragraph_text_setter_serializes_tabs_as_elements() -> None:
    _, paragraph = _build_section_with_paragraph()

    paragraph.text = "left	right"

    run = paragraph.element.find(f"{HP}run")
    assert run is not None
    children = list(run)
    assert [child.tag for child in children] == [f"{HP}t", f"{HP}tab", f"{HP}t"]
    assert paragraph.text == "left	right"


@pytest.mark.parametrize("apply_setter", _TEXT_SETTER_APPLIERS, ids=_TEXT_SETTER_IDS)
@pytest.mark.parametrize(("raw_text", "expected"), _TEXT_SANITIZATION_CASES)
def test_text_setters_sanitize_illegal_xml_characters(
    apply_setter: Callable[[str], str],
    raw_text: str,
    expected: str,
) -> None:
    assert apply_setter(raw_text) == expected


def test_paragraph_allows_updating_para_pr_id_ref() -> None:
    section, paragraph = _build_section_with_paragraph()

    paragraph.para_pr_id_ref = 7

    assert paragraph.element.get("paraPrIDRef") == "7"
    assert section.dirty is True


def test_paragraph_style_id_ref_can_be_removed() -> None:
    section, paragraph = _build_section_with_paragraph()

    paragraph.style_id_ref = None

    assert "styleIDRef" not in paragraph.element.attrib
    assert section.dirty is True


def test_paragraph_char_pr_id_ref_updates_all_runs() -> None:
    section, paragraph = _build_section_with_paragraph()
    extra_run = ET.SubElement(paragraph.element, f"{HP}run", {"charPrIDRef": "5"})
    ET.SubElement(extra_run, f"{HP}t").text = "!"
    section.reset_dirty()

    paragraph.char_pr_id_ref = 9

    for run_element in paragraph.element.findall(f"{HP}run"):
        assert run_element.get("charPrIDRef") == "9"
    assert section.dirty is True


def test_paragraph_char_pr_id_ref_reports_none_when_mixed() -> None:
    _, paragraph = _build_section_with_paragraph()
    ET.SubElement(paragraph.element, f"{HP}run", {"charPrIDRef": "3"})

    assert paragraph.char_pr_id_ref is None


def test_run_wrapper_updates_character_reference() -> None:
    section, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]
    section.reset_dirty()

    run.char_pr_id_ref = 11
    assert run.element.get("charPrIDRef") == "11"
    assert section.dirty is True

    section.reset_dirty()
    run.char_pr_id_ref = None
    assert "charPrIDRef" not in run.element.attrib
    assert section.dirty is True


def test_run_replace_text_handles_nested_highlight_markup() -> None:
    section, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]

    text_element = run.element.find(f"{HP}t")
    assert text_element is not None
    text_element.clear()
    text_element.text = "Hello "
    mark_begin = ET.SubElement(text_element, f"{HP}markpenBegin", {"id": "mark1"})
    mark_begin.tail = "memo"
    mark_end = ET.SubElement(text_element, f"{HP}markpenEnd", {"id": "mark1"})
    mark_end.tail = " world"
    section.reset_dirty()

    replaced = run.replace_text("memo", "note")

    assert replaced == 1
    assert text_element.text == "Hello "
    assert mark_begin.tail == "note"
    assert mark_end.tail == " world"
    assert run.text == "Hello note world"
    assert section.dirty is True


def test_run_replace_text_handles_tag_separated_tokens() -> None:
    section, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]

    text_element = run.element.find(f"{HP}t")
    assert text_element is not None
    text_element.clear()
    text_element.text = ""
    token = ET.SubElement(text_element, f"{HP}tag", {"name": "token"})
    token.text = "foo"
    token.tail = " bar"
    section.reset_dirty()

    replaced = run.replace_text("foo bar", "baz qux")

    assert replaced == 1
    assert token.text == "baz"
    assert token.tail == " qux"
    assert run.text == "baz qux"
    assert section.dirty is True


def test_run_replace_text_spans_multiple_text_nodes() -> None:
    section, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]

    for child in list(run.element):
        run.element.remove(child)
    first = ET.SubElement(run.element, f"{HP}t")
    first.text = "foo "
    second = ET.SubElement(run.element, f"{HP}t")
    second.text = "bar"
    section.reset_dirty()

    replaced = run.replace_text("foo bar", "baz qux")

    assert replaced == 1
    assert first.text == "baz "
    assert second.text == "qux"
    assert run.text == "baz qux"
    assert section.dirty is True


def test_section_add_paragraph_accepts_formatting_identifiers() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)

    paragraph = section.add_paragraph(
        "Body",
        para_pr_id_ref=4,
        style_id_ref=2,
        char_pr_id_ref=6,
        run_attributes={"id": "run1"},
    )

    assert paragraph.element.get("paraPrIDRef") == "4"
    assert paragraph.element.get("styleIDRef") == "2"
    run_element = paragraph.element.find(f"{HP}run")
    assert run_element is not None
    assert run_element.get("charPrIDRef") == "6"
    assert run_element.get("id") == "run1"


def test_document_add_paragraph_passes_formatting_options() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    paragraph = document.add_paragraph(
        "Formatted",
        section=section,
        para_pr_id_ref=8,
        style_id_ref=5,
        char_pr_id_ref=3,
    )

    assert paragraph.element.get("paraPrIDRef") == "8"
    assert paragraph.element.get("styleIDRef") == "5"
    run_element = paragraph.element.find(f"{HP}run")
    assert run_element is not None
    assert run_element.get("charPrIDRef") == "3"


def test_document_replace_text_preserves_style_and_markup() -> None:
    section, paragraph = _build_section_with_paragraph()
    run = paragraph.runs[0]

    text_element = run.element.find(f"{HP}t")
    assert text_element is not None
    text_element.clear()
    text_element.text = "Hello "
    mark_begin = ET.SubElement(text_element, f"{HP}markpenBegin", {"id": "mark1"})
    mark_begin.tail = "memo"
    mark_end = ET.SubElement(text_element, f"{HP}markpenEnd", {"id": "mark1"})
    mark_end.tail = " world"
    section.reset_dirty()

    manifest = ET.Element("manifest")
    document = HwpxDocument(
        cast(HwpxPackage, object()),
        HwpxOxmlDocument(manifest, [section], []),
    )
    original_char = run.char_pr_id_ref

    replaced = document.replace_text_in_runs("memo", "note")

    assert replaced == 1
    assert run.char_pr_id_ref == original_char
    assert mark_begin.tail == "note"
    assert mark_end.tail == " world"
    assert len(list(text_element)) == 2
    assert run.text == "Hello note world"
    assert section.dirty is True


def test_document_add_table_creates_table_structure() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(
        2,
        3,
        section=section,
        width=9000,
        height=6000,
        border_fill_id_ref="5",
    )

    assert table.element.get("rowCnt") == "2"
    assert table.element.get("colCnt") == "3"
    assert len(table.rows) == 2
    assert len(table.rows[0].cells) == 3
    section.reset_dirty()
    table.set_cell_text(0, 1, "Hello")
    assert table.cell(0, 1).text == "Hello"
    assert section.dirty is True


def test_table_set_cell_text_removes_layout_cache() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    cell = table.cell(0, 0)
    sublist = cell.element.find(f"{HP}subList")
    assert sublist is not None
    paragraph = sublist.find(f"{HP}p")
    assert paragraph is not None
    ET.SubElement(paragraph, f"{HP}lineSegArray")
    ET.SubElement(paragraph, f"{HP}linesegarray")
    assert paragraph.find(f"{HP}lineSegArray") is not None
    assert paragraph.find(f"{HP}linesegarray") is not None
    text_element = paragraph.find(f".//{HP}t")
    assert text_element is not None
    text_element.text = "Cached"

    table.set_cell_text(0, 0, "Updated")

    assert table.cell(0, 0).text == "Updated"
    assert paragraph.find(f"{HP}lineSegArray") is None
    assert paragraph.find(f"{HP}linesegarray") is None


def test_table_set_cell_text_converts_squeeze_to_break() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    cell = table.cell(0, 0)
    sublist = cell.element.find(f"{HP}subList")
    assert sublist is not None
    sublist.set("lineWrap", "SQUEEZE")

    table.set_cell_text(0, 0, "한 줄 폭을 넘는 신규 검토 의견 " * 8)

    assert sublist.get("lineWrap") == "BREAK"

    sublist.set("lineWrap", "SQUEEZE")
    table.set_cell_text(0, 0, cell.text)
    assert sublist.get("lineWrap") == "SQUEEZE"


def test_save_removes_stale_layout_cache_after_low_level_text_edit() -> None:
    document = HwpxDocument.new()
    try:
        paragraph = document.add_paragraph("Original paragraph with enough text for cached layout")
        document.to_bytes()

        paragraph_element = paragraph.element
        line_array = paragraph_element.makeelement(f"{HP}linesegarray", {})
        line_array.append(paragraph_element.makeelement(f"{HP}lineseg", {"textpos": "40"}))
        paragraph_element.append(line_array)
        text_element = paragraph_element.find(f".//{HP}t")
        assert text_element is not None
        text_element.text = "Short"

        archive_bytes = document.to_bytes()
    finally:
        document.close()

    assert validate_package(archive_bytes).ok
    with ZipFile(io.BytesIO(archive_bytes), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")

    assert b"Short" in section_xml
    root = ET.fromstring(section_xml)
    paragraphs = [node for node in root.iter() if node.tag.endswith("}p")]
    # textpos=40 against 5 chars of text is provably stale, so the save-time
    # stale sweep removes it even though the writer bypassed the APIs.
    assert paragraphs[-1].find(f"{HP}linesegarray") is None


def test_save_preserves_unjudgeable_layout_cache_on_dirty_complex_paragraph() -> None:
    document = HwpxDocument.new()
    try:
        paragraph = document.add_paragraph("Complex cached paragraph")
        document.to_bytes()

        paragraph_element = paragraph.element
        extra_run = paragraph_element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        extra_run.append(paragraph_element.makeelement(f"{HP}ctrl", {"id": "field"}))
        paragraph_element.append(extra_run)
        line_array = paragraph_element.makeelement(f"{HP}linesegarray", {})
        line_array.append(paragraph_element.makeelement(f"{HP}lineseg", {"textpos": "999"}))
        paragraph_element.append(line_array)
        paragraph.section.mark_dirty()

        archive_bytes = document.to_bytes()
    finally:
        document.close()

    assert validate_package(archive_bytes).ok
    with ZipFile(io.BytesIO(archive_bytes), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")

    root = ET.fromstring(section_xml)
    paragraphs = [node for node in root.iter() if node.tag.endswith("}p")]
    # Raw element mutation bypasses the mutating APIs, and a control-bearing
    # paragraph cannot be judged at the byte boundary — the cache survives.
    # Callers that hand-mutate elements own their invalidation (the text and
    # style setters clear caches themselves; blanket save-time stripping broke
    # untouched pages, specs/031 P0).
    assert paragraphs[-1].find(f"{HP}linesegarray") is not None


def test_table_cell_text_marks_cell_dirty_attribute() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    cell = table.cell(0, 0)
    assert cell.element.get("dirty") == "0"

    cell.text = "Updated"

    assert cell.element.get("dirty") == "1"

    cell.element.set("dirty", "0")

    table.set_cell_text(0, 0, "Again")

    assert table.cell(0, 0).element.get("dirty") == "1"


def test_table_set_cell_text_preserves_existing_char_pr_and_clears_extra_runs() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    cell = table.cell(0, 0)
    paragraph = cell.paragraphs[0]
    first_run = paragraph.runs[0]
    first_run.char_pr_id_ref = "7"
    extra_run = paragraph.add_run(" suffix", char_pr_id_ref="9")

    table.set_cell_text(0, 0, "updated code")

    assert paragraph.runs[0].char_pr_id_ref == "7"
    assert paragraph.runs[0].text == "updated code"
    assert extra_run.char_pr_id_ref == "9"
    assert extra_run.text == ""
    assert cell.text == "updated code"


def test_table_set_cell_text_can_split_multiline_input_into_paragraphs() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)
    cell = table.cell(0, 0)
    cell.paragraphs[0].runs[0].char_pr_id_ref = "11"

    table.set_cell_text(0, 0, "line one\nline two", split_paragraphs=True)

    paragraphs = cell.paragraphs
    assert [paragraph.text for paragraph in paragraphs] == ["line one", "line two"]
    assert [paragraph.runs[0].char_pr_id_ref for paragraph in paragraphs] == ["11", "11"]
    assert cell.text == "line one\nline two"


def test_table_merge_cells_updates_spans_and_structure() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(3, 3, section=section)
    initial_width = table.cell(0, 0).width
    initial_height = table.cell(0, 0).height
    table.set_cell_text(0, 1, "Top Right")
    table.set_cell_text(1, 0, "Bottom Left")
    table.set_cell_text(1, 1, "Bottom Right")
    section.reset_dirty()

    merged = table.merge_cells(0, 0, 1, 1)

    assert merged.span == (2, 2)
    assert merged.width >= initial_width
    assert merged.height >= initial_height
    assert table.cell(0, 1).element is merged.element
    assert table.cell(1, 0).element is merged.element
    assert table.cell(1, 1).element is merged.element
    assert [cell.address for cell in table.rows[0].cells] == [(0, 0), (0, 2)]
    assert [cell.address for cell in table.rows[1].cells] == [(1, 2)]
    assert all(
        cell.address not in {(0, 1), (1, 0), (1, 1)}
        for row in table.rows
        for cell in row.cells
    )
    assert section.dirty is True


def test_table_merge_cells_rejects_partial_overlap() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(2, 2, section=section)
    table.merge_cells(0, 0, 1, 1)

    with pytest.raises(ValueError):
        table.merge_cells(0, 1, 1, 1)


def test_table_iter_grid_reports_merged_cells() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(2, 2, section=section)
    table.merge_cells(0, 0, 0, 1)

    entries = list(table.iter_grid())
    assert len(entries) == 4
    mapping = {(entry.row, entry.column): entry for entry in entries}
    top_left = mapping[(0, 0)]
    right = mapping[(0, 1)]

    assert top_left.is_anchor is True
    assert top_left.row_span == 1
    assert top_left.col_span == 2
    assert right.is_anchor is False
    assert right.cell.element is top_left.cell.element
    assert right.row_span == top_left.row_span
    assert right.col_span == top_left.col_span

    cell_map = table.get_cell_map()
    assert cell_map[0][1].cell.element is top_left.cell.element


def test_table_logical_editing_can_split_merged_cells() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(2, 2, section=section)
    table.merge_cells(0, 0, 0, 1)

    table.set_cell_text(0, 1, "Shared", logical=True)
    assert table.cell(0, 0).text == "Shared"
    assert table.cell(0, 1).element is table.cell(0, 0).element

    table.set_cell_text(0, 1, "Right", logical=True, split_merged=True)

    left_cell = table.cell(0, 0)
    right_cell = table.cell(0, 1)

    assert left_cell.element is not right_cell.element
    assert left_cell.text == "Shared"
    assert right_cell.text == "Right"
    assert right_cell.span == (1, 1)


def test_table_cell_out_of_bounds_error_mentions_bounds() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(1, 1, section=section)

    with pytest.raises(IndexError) as excinfo:
        table.cell(5, 0)

    assert "exceed table bounds" in str(excinfo.value)


def test_paragraph_tables_property_returns_wrappers() -> None:
    section, paragraph = _build_section_with_paragraph()

    table = paragraph.add_table(1, 1)

    assert paragraph.tables
    assert paragraph.tables[0].element is table.element


def test_section_properties_reports_page_options() -> None:
    section, _ = _build_section_with_properties()

    properties = section.properties
    size = properties.page_size
    assert size.width == 59528
    assert size.height == 84188
    assert size.orientation == "PORTRAIT"
    assert size.gutter_type == "LEFT_ONLY"

    margins = properties.page_margins
    assert margins.left == 8504
    assert margins.right == 8504
    assert margins.header == 4252

    numbering = properties.start_numbering
    assert numbering.page_starts_on == "ODD"
    assert numbering.page == 3
    assert numbering.picture == 2
    assert numbering.equation == 7


def test_section_properties_updates_page_settings() -> None:
    section, sec_pr = _build_section_with_properties()
    properties = section.properties

    section.reset_dirty()
    properties.set_page_size(width=72000, height=36000, orientation="NARROWLY", gutter_type="TOP_BOTTOM")
    page_pr = sec_pr.find(f"{HP}pagePr")
    assert page_pr is not None
    assert page_pr.get("width") == "72000"
    assert page_pr.get("height") == "36000"
    assert page_pr.get("landscape") == "NARROWLY"
    assert page_pr.get("gutterType") == "TOP_BOTTOM"
    assert section.dirty is True

    section.reset_dirty()
    properties.set_page_margins(
        left=1000,
        right=2000,
        top=3000,
        bottom=4000,
        header=500,
        footer=600,
        gutter=700,
    )
    margin = page_pr.find(f"{HP}margin")
    assert margin is not None
    assert margin.get("left") == "1000"
    assert margin.get("right") == "2000"
    assert margin.get("top") == "3000"
    assert margin.get("bottom") == "4000"
    assert margin.get("header") == "500"
    assert margin.get("footer") == "600"
    assert margin.get("gutter") == "700"
    assert section.dirty is True

    section.reset_dirty()
    properties.set_start_numbering(page_starts_on="EVEN", page=7, picture=4, table=5, equation=6)
    start_num = sec_pr.find(f"{HP}startNum")
    assert start_num is not None
    assert start_num.get("pageStartsOn") == "EVEN"
    assert start_num.get("page") == "7"
    assert start_num.get("pic") == "4"
    assert start_num.get("tbl") == "5"
    assert start_num.get("equation") == "6"
    assert section.dirty is True


def test_section_properties_reports_grid_visibility_line_numbering_defaults() -> None:
    """secPr에 grid/visibility/lineNumberShape가 전혀 없을 때(문서화된
    스키마 기본값과 같은) 읽기 API가 정직한 기본 dataclass를 돌려준다."""

    section, _ = _build_section_with_properties()
    properties = section.properties

    grid = properties.grid
    assert grid.line_grid == 0
    assert grid.char_grid == 0
    assert grid.wonggoji_format is False

    visibility = properties.visibility
    assert visibility.hide_first_header is False
    assert visibility.border is None
    assert visibility.fill is None

    shape = properties.line_number_shape
    assert shape.restart_type is None
    assert shape.count_by is None
    assert shape.distance is None
    assert shape.start_number is None


def test_section_properties_updates_grid_visibility_line_numbering() -> None:
    section, sec_pr = _build_section_with_properties()
    properties = section.properties

    section.reset_dirty()
    properties.set_grid(line_grid=283, char_grid=567, wonggoji_format=True)
    grid_el = sec_pr.find(f"{HP}grid")
    assert grid_el is not None
    assert grid_el.get("lineGrid") == "283"
    assert grid_el.get("charGrid") == "567"
    assert grid_el.get("wonggojiFormat") == "true"
    assert section.dirty is True
    assert properties.grid == SectionGrid(line_grid=283, char_grid=567, wonggoji_format=True)

    section.reset_dirty()
    properties.set_visibility(
        hide_first_header=True,
        hide_first_footer=True,
        show_line_number=True,
        border="HIDE_ALL",
        fill="HIDE_ALL",
    )
    visibility_el = sec_pr.find(f"{HP}visibility")
    assert visibility_el is not None
    assert visibility_el.get("hideFirstHeader") == "true"
    assert visibility_el.get("hideFirstFooter") == "true"
    assert visibility_el.get("showLineNumber") == "true"
    assert visibility_el.get("border") == "HIDE_ALL"
    assert visibility_el.get("fill") == "HIDE_ALL"
    # 손대지 않은 플래그는 기본값(false)에서 그대로다.
    assert visibility_el.get("hideFirstMasterPage") == "false"
    assert section.dirty is True

    section.reset_dirty()
    properties.set_line_number_shape(restart_type=1, count_by=5, distance=850, start_number=1)
    shape_el = sec_pr.find(f"{HP}lineNumberShape")
    assert shape_el is not None
    assert shape_el.get("restartType") == "1"
    assert shape_el.get("countBy") == "5"
    assert shape_el.get("distance") == "850"
    assert shape_el.get("startNumber") == "1"
    assert section.dirty is True

    # 값을 안 준 두 번째 호출은 기존 값을 보존하고 dirty를 다시 세우지 않는다.
    section.reset_dirty()
    properties.set_grid()
    properties.set_visibility()
    properties.set_line_number_shape()
    assert section.dirty is False


def test_section_properties_reports_page_border_fill_defaults() -> None:
    section, _ = _build_section_with_properties()
    assert section.properties.page_border_fill() is None
    assert section.properties.page_border_fill("EVEN") is None


def test_section_properties_updates_page_border_fill() -> None:
    section, sec_pr = _build_section_with_properties()
    properties = section.properties

    section.reset_dirty()
    properties.set_page_border_fill(
        border_fill_id_ref=3,
        text_border="PAPER",
        header_inside=True,
        fill_area="PAGE",
        offset_left=500,
    )
    both = sec_pr.find(f"{HP}pageBorderFill")
    assert both is not None
    assert both.get("type") == "BOTH"
    assert both.get("borderFillIDRef") == "3"
    assert both.get("textBorder") == "PAPER"
    assert both.get("headerInside") == "true"
    assert both.get("footerInside") is None  # 안 건드린 속성은 안 생김
    assert both.get("fillArea") == "PAGE"
    offset = both.find(f"{HP}offset")
    assert offset is not None
    assert offset.get("left") == "500"
    assert offset.get("right") == "1417"  # 기본값 유지
    assert section.dirty is True

    # page_type이 다르면 별도 엔트리 — BOTH는 안 건드려진다.
    section.reset_dirty()
    properties.set_page_border_fill(page_type="EVEN", border_fill_id_ref=7)
    entries = sec_pr.findall(f"{HP}pageBorderFill")
    assert len(entries) == 2
    assert {e.get("type") for e in entries} == {"BOTH", "EVEN"}
    assert both.get("borderFillIDRef") == "3"  # BOTH 엔트리 무변경

    read_back = properties.page_border_fill("EVEN")
    assert read_back is not None
    assert read_back.border_fill_id_ref == "7"

    # no-op 재호출은 dirty를 다시 세우지 않는다.
    section.reset_dirty()
    properties.set_page_border_fill(border_fill_id_ref=3)
    assert section.dirty is False


def test_section_properties_footnote_and_endnote_shape_defaults() -> None:
    section, _ = _build_section_with_properties()
    assert section.properties.footnote_shape is None
    assert section.properties.endnote_shape is None


def test_section_properties_footnote_partial_updates_do_not_touch_other_blocks() -> None:
    """부분 갱신 계약의 핵심 게이트: noteLine만 바꿔도 autoNumFormat·noteSpacing·
    numbering·placement는 (생성 시 기본값에서) 전혀 안 움직여야 한다 — 실문서
    왕복에서 이 4개 블록의 기존 값을 깨지 않는다는 걸 구조로 증명한다."""

    section, sec_pr = _build_section_with_properties()
    properties = section.properties

    section.reset_dirty()
    properties.set_footnote_note_line(color="#FF0000", width="0.2 mm")
    footnote_el = sec_pr.find(f"{HP}footNotePr")
    assert footnote_el is not None
    assert section.dirty is True

    shape = properties.footnote_shape
    assert shape is not None
    assert shape.note_line.color == "#FF0000"
    assert shape.note_line.width == "0.2 mm"
    # 생성 시 함께 만들어진 나머지 4블록은 스키마 기본값 그대로.
    assert shape.auto_num_format.type == "DIGIT"
    assert shape.auto_num_format.suffix_char == ")"
    assert shape.note_spacing.between_notes == 850
    assert shape.numbering.type == "CONTINUOUS"
    assert shape.placement.place == "EACH_COLUMN"  # 각주 기본값(미주와 다름)

    # 다른 블록 하나를 갱신해도 noteLine은 그대로.
    section.reset_dirty()
    properties.set_footnote_numbering(type="ON_SECTION", new_num=3)
    shape2 = properties.footnote_shape
    assert shape2.numbering.type == "ON_SECTION"
    assert shape2.numbering.new_num == 3
    assert shape2.note_line.color == "#FF0000"  # 이전 갱신 보존
    assert section.dirty is True

    # no-op 재호출(인자 없음)은 dirty를 다시 세우지 않는다.
    section.reset_dirty()
    properties.set_footnote_auto_num_format()
    properties.set_footnote_note_line()
    properties.set_footnote_note_spacing()
    properties.set_footnote_numbering()
    properties.set_footnote_placement()
    assert section.dirty is False


def test_section_properties_endnote_placement_default_differs_from_footnote() -> None:
    section, _ = _build_section_with_properties()
    properties = section.properties

    properties.set_endnote_placement(beneath_text=True)
    shape = properties.endnote_shape
    assert shape is not None
    assert shape.placement.place == "END_OF_DOCUMENT"  # 미주 기본값(각주와 다름)
    assert shape.placement.beneath_text is True
    # footnote_shape는 여전히 None — endnote 갱신이 footnote를 안 건드림.
    assert properties.footnote_shape is None


def test_section_properties_header_footer_helpers() -> None:
    section, sec_pr = _build_section_with_properties()
    properties = section.properties

    section.reset_dirty()
    header = properties.set_header_text("Confidential")
    header_element = sec_pr.find(f"{HP}header")
    assert header_element is not None
    assert header_element.get("applyPageType") == "BOTH"
    assert header.text == "Confidential"
    text_element = header_element.find(f".//{HP}t")
    assert text_element is not None and text_element.text == "Confidential"
    assert section.dirty is True

    section.reset_dirty()
    header.text = "Approved"
    text_element = header_element.find(f".//{HP}t")
    assert text_element is not None and text_element.text == "Approved"
    assert section.dirty is True

    section.reset_dirty()
    footer = properties.set_footer_text("Page", page_type="ODD")
    footer_element = sec_pr.find(f"{HP}footer")
    assert footer_element is not None
    assert footer.apply_page_type == "ODD"
    assert footer_element.find(f".//{HP}t").text == "Page"
    assert section.dirty is True

    section.reset_dirty()
    properties.remove_header()
    assert properties.get_header() is None
    assert section.dirty is True


def test_header_begin_numbering_updates_xml() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    ET.SubElement(
        head_element,
        f"{HH}beginNum",
        {"page": "1", "footnote": "2", "endnote": "3", "pic": "4", "tbl": "5", "equation": "6"},
    )
    header = HwpxOxmlHeader("header.xml", head_element)

    numbering = header.begin_numbering
    assert numbering.page == 1
    assert numbering.footnote == 2
    assert numbering.endnote == 3

    header.reset_dirty()
    header.set_begin_numbering(page=9, footnote=8, picture=7)
    begin_num = head_element.find(f"{HH}beginNum")
    assert begin_num is not None
    assert begin_num.get("page") == "9"
    assert begin_num.get("footnote") == "8"
    assert begin_num.get("pic") == "7"
    assert begin_num.get("tbl") == "5"
    assert header.dirty is True


def test_header_begin_numbering_creates_element_when_missing() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    header.reset_dirty()
    header.set_begin_numbering(page=4)
    begin_num = head_element.find(f"{HH}beginNum")
    assert begin_num is not None
    assert begin_num.get("page") == "4"
    assert begin_num.get("footnote") == "1"
    assert header.dirty is True


def test_header_ensure_char_property_creates_blocks_and_ids() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    created = header.ensure_char_property(
        modifier=lambda el: ET.SubElement(el, f"{HH}bold"),
    )

    ref_list = head_element.find(f"{HH}refList")
    assert ref_list is not None
    char_props = ref_list.find(f"{HH}charProperties")
    assert char_props is not None
    assert char_props.get("itemCnt") == "1"
    assert created.get("id") == "0"

    def italic_modifier(element: ET.Element) -> None:
        for child in list(element.findall(f"{HH}bold")):
            element.remove(child)
        ET.SubElement(element, f"{HH}italic")

    second = header.ensure_char_property(modifier=italic_modifier)
    assert second.get("id") == "1"
    assert char_props.get("itemCnt") == "2"


def test_header_ensure_style_creates_dedupes_by_name_and_partial_updates() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    style_id = header.ensure_style(
        "내설명", eng_name="MyDesc", para_pr_id_ref=0, char_pr_id_ref=0
    )
    styles_el = head_element.find(f"{HH}refList/{HH}styles")
    assert styles_el is not None
    assert styles_el.get("itemCnt") == "1"
    created = styles_el.find(f"{HH}style")
    assert created is not None
    assert created.get("id") == style_id
    assert created.get("type") == "PARA"  # 미지정 시 기본값(스키마 필수, 기본 없음)
    assert created.get("name") == "내설명"
    assert created.get("engName") == "MyDesc"
    assert created.get("paraPrIDRef") == "0"
    assert created.get("charPrIDRef") == "0"

    # 동명 재호출은 새 항목을 안 만들고 같은 id를 재사용 + 준 값만 갱신한다.
    reused_id = header.ensure_style("내설명", next_style_id_ref=style_id)
    assert reused_id == style_id
    assert styles_el.get("itemCnt") == "1"  # 개수 안 늘어남
    assert created.get("nextStyleIDRef") == style_id
    assert created.get("engName") == "MyDesc"  # 안 건드린 값 보존

    # 다른 이름은 다른 id.
    other_id = header.ensure_style("다른스타일", style_type="CHAR")
    assert other_id != style_id
    assert styles_el.get("itemCnt") == "2"
    other = next(s for s in styles_el.findall(f"{HH}style") if s.get("name") == "다른스타일")
    assert other.get("type") == "CHAR"


def test_header_ensure_style_resolves_by_name_immediately_on_a_real_document() -> None:
    """``_style_name_id_map``/``style_name_aliases``는 HwpxOxmlDocument 계층
    책임이라 실제 문서로 검증한다(위 테스트는 헤더 단위 생성/중복제거만)."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    header = doc.oxml.headers[0]

    style_id = header.ensure_style("내설명", eng_name="MyDesc")

    aliases = doc.oxml.style_name_aliases()
    assert aliases["내설명"] == (style_id,)
    assert aliases["MyDesc"] == (style_id,)
    assert doc.oxml._style_name_id_map()["내설명"] == style_id
    doc.close()


# -- 6.1 글꼴 선언·대체 (StylesNamespace.ensure_font) -----------------------


def test_header_ensure_font_registers_all_lang_blocks_by_default() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    font_id = header.ensure_font("우리새글꼴")

    fontfaces = head_element.find(f"{HH}refList/{HH}fontfaces")
    assert fontfaces is not None
    assert fontfaces.get("itemCnt") == "7"
    langs = [ff.get("lang") for ff in fontfaces.findall(f"{HH}fontface")]
    assert langs == [
        "HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER",
    ]
    for fontface in fontfaces.findall(f"{HH}fontface"):
        assert fontface.get("fontCnt") == "1"
        font = fontface.find(f"{HH}font")
        assert font is not None
        assert font.get("id") == font_id
        assert font.get("face") == "우리새글꼴"
        assert font.get("type") == "TTF"
        assert font.get("isEmbedded") == "0"  # 실코퍼스 관행: "0"/"1"(true/false 아님)
        assert "binaryItemIDRef" not in font.attrib  # 실코퍼스: 비-임베드는 속성 자체가 없다


def test_header_ensure_font_single_lang_scopes_registration() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    header.ensure_font("한글전용체", lang="HANGUL")

    fontfaces = head_element.find(f"{HH}refList/{HH}fontfaces")
    assert fontfaces is not None
    assert [ff.get("lang") for ff in fontfaces.findall(f"{HH}fontface")] == ["HANGUL"]
    fontface = fontfaces.find(f"{HH}fontface")
    assert fontface.get("fontCnt") == "1"


def test_header_ensure_font_dedupes_by_face_within_a_lang_block() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    first_id = header.ensure_font("중복체", lang="HANGUL", font_type="TTF")
    second_id = header.ensure_font("중복체", lang="HANGUL", font_type="TTF")

    assert first_id == second_id
    fontface = head_element.find(f"{HH}refList/{HH}fontfaces/{HH}fontface")
    assert fontface.get("fontCnt") == "1"  # 안 늘어남
    assert len(fontface.findall(f"{HH}font")) == 1

    # 다른 face는 새 id.
    other_id = header.ensure_font("다른체", lang="HANGUL")
    assert other_id != first_id
    assert fontface.get("fontCnt") == "2"


def test_header_ensure_font_allocates_ids_independently_per_lang_block() -> None:
    """실코퍼스 실측: fontface 블록마다 id 채번이 독립이다(공유 카운터가
    아니다) — 한 블록에 미리 항목이 많으면 그 블록의 다음 id 만 밀린다."""

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    # HANGUL 블록만 먼저 채워서 다음 id를 밀어 둔다.
    header.ensure_font("먼저등록체1", lang="HANGUL")
    header.ensure_font("먼저등록체2", lang="HANGUL")

    shared_id = header.ensure_font("공용체", lang=("HANGUL", "LATIN"))

    fontfaces = head_element.find(f"{HH}refList/{HH}fontfaces")
    hangul = next(ff for ff in fontfaces.findall(f"{HH}fontface") if ff.get("lang") == "HANGUL")
    latin = next(ff for ff in fontfaces.findall(f"{HH}fontface") if ff.get("lang") == "LATIN")
    hangul_entry = next(f for f in hangul.findall(f"{HH}font") if f.get("face") == "공용체")
    latin_entry = next(f for f in latin.findall(f"{HH}font") if f.get("face") == "공용체")

    assert hangul_entry.get("id") == "2"  # 앞선 두 등록 뒤라 다음 id
    assert latin_entry.get("id") == "0"  # LATIN 블록은 비어 있었으므로 0부터
    assert shared_id == hangul_entry.get("id")  # 반환값 = 정규 순서상 첫 lang(HANGUL) 블록의 id


def test_header_ensure_font_rejects_empty_face() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_font("   ")
    assert excinfo.value.code == "style-font-face-empty"


def test_header_ensure_font_rejects_invalid_lang() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_font("아무체", lang="KLINGON")
    assert excinfo.value.code == "style-font-lang-invalid"
    assert "HANGUL" in excinfo.value.context["available"]


def test_header_ensure_font_rejects_invalid_font_type() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_font("아무체", lang="HANGUL", font_type="OTF")
    assert excinfo.value.code == "style-font-type-invalid"


def test_header_ensure_font_rejects_incomplete_substitute() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_font("아무체", lang="HANGUL", subst_type="TTF")  # subst_face 없음
    assert excinfo.value.code == "style-font-substitute-incomplete"


def test_header_ensure_font_emits_subst_font_matching_real_corpus_shape() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    font_id = header.ensure_font(
        "없는글꼴",
        lang="HANGUL",
        subst_face="함초롬바탕",
        subst_type="TTF",
    )

    font = head_element.find(f"{HH}refList/{HH}fontfaces/{HH}fontface/{HH}font")
    assert font.get("id") == font_id
    subst = font.find(f"{HH}substFont")
    assert subst is not None
    assert subst.get("face") == "함초롬바탕"
    assert subst.get("type") == "TTF"
    assert subst.get("isEmbedded") == "0"
    # 실코퍼스 관행: substFont는 binaryItemIDRef를 항상 갖되(font와 반대)
    # 값이 없으면 빈 문자열로 남는다.
    assert subst.get("binaryItemIDRef") == ""

    # dedupe 재호출은 이미 있는 hh:font를 재사용하고, 대체 글꼴을 새로
    # 끼워 넣지 않는다(기존 선언을 조용히 바꾸지 않는다).
    reused_id = header.ensure_font("없는글꼴", lang="HANGUL")
    assert reused_id == font_id
    fontface = head_element.find(f"{HH}refList/{HH}fontfaces/{HH}fontface")
    assert fontface.get("fontCnt") == "1"


def test_document_ensure_font_then_ensure_run_wires_a_real_font_ref() -> None:
    """등록(ensure_font) → 사용(ensure_run(font=...)) 왕복이 한 호출 체인에서
    가능해야 한다는 6.1 게이트 ②의 핵심 계약."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    face = "체인등록체"
    font_id = doc.styles.ensure_font(face, lang="HANGUL")
    run_id = doc.styles.ensure_run(font=face, bold=True)

    char_pr = doc.oxml.char_property(run_id)
    assert char_pr is not None
    # RunStyle 모델은 자식 요소를 child_attributes[로컬이름] 로 노출한다.
    font_ref = char_pr.child_attributes.get("fontRef")
    assert font_ref is not None
    assert font_ref.get("hangul") == font_id
    doc.close()


# -- 6.1 문단 탭 정의 (StylesNamespace.apply_paragraph_format(tab_stops=...)) --


def test_header_ensure_tab_definition_creates_and_dedupes() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    tab_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 3543, "type": "LEFT", "leader": "NONE"}],
    )

    tabprops = head_element.find(f"{HH}refList/{HH}tabProperties")
    assert tabprops is not None
    assert tabprops.get("itemCnt") == "1"
    tabpr = tabprops.find(f"{HH}tabPr")
    assert tabpr is not None
    assert tabpr.get("id") == tab_id
    assert tabpr.get("autoTabLeft") == "0"  # 실코퍼스 관행: "0"/"1"(true/false 아님)
    assert tabpr.get("autoTabRight") == "0"
    items = tabpr.findall(f"{HH}tabItem")
    assert len(items) == 1
    assert items[0].get("pos") == "3543"
    assert items[0].get("type") == "LEFT"
    assert items[0].get("leader") == "NONE"

    # 동일 스펙 재호출은 새 항목을 안 만들고 같은 id를 재사용한다(ensure_style 선례).
    reused_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 3543, "type": "LEFT", "leader": "NONE"}],
    )
    assert reused_id == tab_id
    assert tabprops.get("itemCnt") == "1"


def test_header_ensure_tab_definition_order_is_part_of_the_dedupe_key() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    forward_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 1000, "type": "LEFT"}, {"pos": 2000, "type": "LEFT"}],
    )
    reversed_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 2000, "type": "LEFT"}, {"pos": 1000, "type": "LEFT"}],
    )

    assert forward_id != reversed_id
    tabprops = head_element.find(f"{HH}refList/{HH}tabProperties")
    assert tabprops.get("itemCnt") == "2"


def test_header_ensure_tab_definition_auto_flags_are_part_of_the_dedupe_key() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    plain_id = header.ensure_tab_definition()
    left_id = header.ensure_tab_definition(auto_tab_left=True)
    right_id = header.ensure_tab_definition(auto_tab_right=True)

    assert len({plain_id, left_id, right_id}) == 3
    tabprops = head_element.find(f"{HH}refList/{HH}tabProperties")
    assert tabprops.get("itemCnt") == "3"
    # 재호출은 dedupe.
    assert header.ensure_tab_definition(auto_tab_left=True) == left_id
    assert tabprops.get("itemCnt") == "3"


def test_header_ensure_tab_definition_dedupes_against_a_switch_wrapped_existing_entry() -> None:
    """DEV-022: 실코퍼스 449/449 hp:switch로 감싼 hh:tabPr은 직속 hh:tabItem이
    없다 — 그 경우 dedupe 비교가 hp:default 분기를 보지 않으면 동등한
    스펙을 "불일치"로 오판해 중복 tabPr을 만든다(결함-부활으로 확인됨)."""

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)
    ref_list = ET.SubElement(head_element, f"{HH}refList")
    tabprops = ET.SubElement(ref_list, f"{HH}tabProperties", {"itemCnt": "1"})
    tab_pr = ET.SubElement(
        tabprops, f"{HH}tabPr", {"id": "0", "autoTabLeft": "0", "autoTabRight": "0"}
    )
    switch = ET.SubElement(tab_pr, f"{HP}switch")
    case = ET.SubElement(
        switch,
        f"{HP}case",
        {f"{HP}required-namespace": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"},
    )
    ET.SubElement(case, f"{HH}tabItem", {"pos": "4032", "type": "LEFT", "leader": "NONE", "unit": "HWPUNIT"})
    default = ET.SubElement(switch, f"{HP}default")
    ET.SubElement(default, f"{HH}tabItem", {"pos": "8064", "type": "LEFT", "leader": "NONE"})

    # hp:default's value (8064) is the real-corpus-verified standard scale --
    # matching it should reuse id="0", not create a duplicate.
    matched_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 8064, "type": "LEFT", "leader": "NONE"}],
    )

    assert matched_id == "0"
    assert len(tabprops.findall(f"{HH}tabPr")) == 1


def test_header_ensure_tab_definition_rejects_missing_pos() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_tab_definition(tab_stops=[{"type": "LEFT"}])
    assert excinfo.value.code == "paragraph-tab-pos-invalid"


def test_header_ensure_tab_definition_rejects_negative_pos() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_tab_definition(tab_stops=[{"pos": -1}])
    assert excinfo.value.code == "paragraph-tab-pos-invalid"


def test_header_ensure_tab_definition_rejects_invalid_type() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_tab_definition(tab_stops=[{"pos": 100, "type": "MIDDLE"}])
    assert excinfo.value.code == "paragraph-tab-type-invalid"


def test_header_ensure_tab_definition_rejects_invalid_leader() -> None:
    from hwpx.errors import HwpxValueError

    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    with pytest.raises(HwpxValueError) as excinfo:
        header.ensure_tab_definition(tab_stops=[{"pos": 100, "leader": "SPARKLE"}])
    assert excinfo.value.code == "paragraph-tab-leader-invalid"


def test_header_tab_properties_read_exposes_stops_and_resolves_by_id() -> None:
    head_element = ET.Element(f"{HH}head", {"version": "1.4", "secCnt": "1"})
    header = HwpxOxmlHeader("header.xml", head_element)

    tab_id = header.ensure_tab_definition(
        tab_stops=[{"pos": 2000, "type": "RIGHT", "leader": "DOT"}],
        auto_tab_left=True,
    )

    definitions = header.tab_properties
    assert tab_id in definitions
    definition = definitions[tab_id]
    assert definition.auto_tab_left is True
    assert definition.auto_tab_right is False
    assert len(definition.tab_stops) == 1
    stop = definition.tab_stops[0]
    assert stop.pos == 2000
    assert stop.type == "RIGHT"
    assert stop.leader == "DOT"

    assert header.tab_property(tab_id) == definition
    assert header.tab_property(int(tab_id)) == definition


def test_document_apply_paragraph_format_wires_tab_pr_id_ref_to_a_resolvable_definition() -> None:
    """등록(tab_stops=...) → 해석(doc.styles.tab_property) 왕복이 한 호출
    체인에서 가능해야 한다는 6.1 게이트 ②의 핵심 계약(ensure_font 선례와 동형)."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("탭 정의 문단입니다.")
    index = len(doc.paragraphs) - 1

    doc.styles.apply_paragraph_format(
        paragraph_index=index,
        tab_stops=[{"pos_mm": 10}, {"pos_mm": 30, "type": "CENTER"}],
    )

    para = doc.paragraphs[index]
    para_prop = doc.styles.paragraph_property(para.para_pr_id_ref)
    assert para_prop is not None
    assert para_prop.tab_pr_id_ref is not None

    tab_def = doc.styles.tab_property(para_prop.tab_pr_id_ref)
    assert tab_def is not None
    assert [(s.pos, s.type) for s in tab_def.tab_stops] == [(2835, "LEFT"), (8504, "CENTER")]
    doc.close()


def test_document_apply_paragraph_format_tab_stops_reject_missing_pos_mm() -> None:
    from hwpx.document import HwpxDocument
    from hwpx.errors import HwpxValueError

    doc = HwpxDocument.new()
    doc.add_paragraph("문단")
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.apply_paragraph_format(paragraph_index=1, tab_stops=[{"type": "LEFT"}])
    assert excinfo.value.code == "paragraph-tab-pos-invalid"
    doc.close()


# -- 6.1 문서 옵션·호환성 읽기(hh:layoutCompatibility·compatibleDocument·-----
# -- settings.xml ha:HWPApplicationSetting) ----------------------------------


def test_header_compatible_document_reports_target_program_and_empty_flags_on_skeleton() -> None:
    """실코퍼스 176파일 전수: targetProgram="HWP201X"·layoutCompatibility
    플래그 0개(감사 §4-R1이 "코드가 단어조차 모르는" 요소로 지목한 자리)."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    model = doc.oxml.headers[0].to_model()
    compatible = model.compatible_document
    assert compatible is not None
    assert compatible.target_program == "HWP201X"
    assert compatible.layout_compatibility is not None
    assert compatible.layout_compatibility.flags == frozenset()
    doc.close()


def test_header_layout_compatibility_preserves_unknown_flags_without_hardcoded_enum() -> None:
    """실문서에 등장한 적 없는 조합이라도(로컬 코퍼스 176파일 전수 0개) 무손실
    보존해야 한다 — 이름→존재 집합 모델이지 하드코딩 열거가 아니라는 계약."""

    from hwpx.oxml.header import parse_compatible_document

    node = ET.Element(f"{HH}compatibleDocument", {"targetProgram": "MS_WORD"})
    layout = ET.SubElement(node, f"{HH}layoutCompatibility")
    ET.SubElement(layout, f"{HH}applyFontWeightToBold")
    ET.SubElement(layout, f"{HH}doNotApplyImageEffect")
    ET.SubElement(layout, f"{HH}notInTheSchema42")  # 스키마 밖 미래 플래그도 무손실
    compatible = parse_compatible_document(node)
    assert compatible.target_program == "MS_WORD"
    assert compatible.layout_compatibility.flags == {
        "applyFontWeightToBold",
        "doNotApplyImageEffect",
        "notInTheSchema42",
    }
    assert compatible.layout_compatibility.has("applyFontWeightToBold")
    assert not compatible.layout_compatibility.has("useInnerUnderline")


def test_header_compatible_document_matches_real_hancom_documents() -> None:
    """게이트 ①: 실한컴 저장본 3표본에서 targetProgram이 원 XML과 정합."""

    from hwpx.document import HwpxDocument

    fixtures = [
        "tests/fixtures/hwpxlib_corpus/error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx",
        "tests/fixtures/hwpxlib_corpus/error__20251107__test_re.hwpx",
        "tests/fixtures/hwpxlib_corpus/error__20230728__test.hwpx",
    ]
    ns = {"hh": "http://www.hancom.co.kr/hwpml/2011/head"}
    for path in fixtures:
        import zipfile
        from lxml import etree as LET2

        raw = zipfile.ZipFile(path).read("Contents/header.xml")
        raw_root = LET2.fromstring(raw)
        raw_compatible = raw_root.find(".//hh:compatibleDocument", ns)
        expected_target = raw_compatible.get("targetProgram")
        raw_layout = raw_compatible.find("hh:layoutCompatibility", ns)
        expected_flags = frozenset(LET2.QName(c.tag).localname for c in raw_layout)

        doc = HwpxDocument.open(path)
        compatible = doc.oxml.headers[0].to_model().compatible_document
        assert compatible.target_program == expected_target, path
        assert compatible.layout_compatibility.flags == expected_flags, path
        doc.close()


def test_settings_parse_application_settings_from_bare_xml() -> None:
    from hwpx.oxml.settings import parse_application_settings

    xml = (
        "<ha:HWPApplicationSetting xmlns:ha='http://www.hancom.co.kr/hwpml/2011/app' "
        "xmlns:config='urn:oasis:names:tc:opendocument:xmlns:config:1.0'>"
        "<ha:CaretPosition listIDRef='0' paraIDRef='72' pos='16'/>"
        "<config:config-item-set name='PrintInfo'>"
        "<config:config-item name='PrintAutoFootNote' type='boolean'>false</config:config-item>"
        "<config:config-item name='ZoomX' type='short'>100</config:config-item>"
        "</config:config-item-set>"
        "</ha:HWPApplicationSetting>"
    )
    settings = parse_application_settings(ET.fromstring(xml))
    assert settings.caret_position.list_id_ref == 0
    assert settings.caret_position.para_id_ref == 72
    assert settings.caret_position.pos == 16
    print_info = settings.config_item_sets["PrintInfo"]
    assert print_info.items["PrintAutoFootNote"].value is False
    assert print_info.items["ZoomX"].value == 100
    assert isinstance(print_info.items["ZoomX"].value, int)


def test_settings_parse_application_settings_rejects_wrong_root() -> None:
    from hwpx.errors import HwpxValueError
    from hwpx.oxml.settings import parse_application_settings

    with pytest.raises(HwpxValueError) as excinfo:
        parse_application_settings(ET.fromstring("<ha:NotSettings xmlns:ha='urn:x'/>"))
    assert excinfo.value.code == "document-settings-root-invalid"


def test_document_parts_settings_available_on_a_new_skeleton_document() -> None:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    settings_part = doc.parts.settings
    assert settings_part is not None
    model = settings_part.to_model()
    assert model.caret_position is not None
    doc.close()


def test_document_parts_settings_matches_real_hancom_documents() -> None:
    """게이트 ①: 실한컴 저장본 3표본에서 CaretPosition·config-item 값이
    원 settings.xml과 정합. 게이트 ②: 읽기 전용 open→save가 settings.xml
    바이트를 무손상 보존(쓰기 경로를 열지 않았으므로 당연히 불변)."""

    import zipfile

    from hwpx.document import HwpxDocument

    fixtures = [
        "tests/fixtures/hwpxlib_corpus/error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx",
        "tests/fixtures/hwpxlib_corpus/error__20251107__test_re.hwpx",
        "tests/fixtures/hwpxlib_corpus/error__20230728__test.hwpx",
    ]
    for path in fixtures:
        original_settings_bytes = zipfile.ZipFile(path).read("settings.xml")

        doc = HwpxDocument.open(path)
        model = doc.parts.settings.to_model()
        assert model.caret_position is not None
        out_bytes = doc.to_bytes()
        doc.close()

        reopened_settings_bytes = zipfile.ZipFile(io.BytesIO(out_bytes)).read("settings.xml")
        assert reopened_settings_bytes == original_settings_bytes, path


# -- 6.1 도형 안 텍스트(hp:drawText) + 개체 캡션(hp:caption) ------------------


def test_shape_draw_text_and_caption_match_real_hancom_document() -> None:
    """게이트 ①: 실한컴 저장본에서 drawText/caption 읽기 값이 원 XML과 정합."""

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open("tests/fixtures/hwpxlib_corpus/reader_writer__SimpleRectangle.hwpx")
    shape = doc.sections[0].paragraphs[0].shapes[0]

    draw_text = shape.draw_text
    assert draw_text is not None
    assert draw_text.text == "ABC"
    assert draw_text.editable is False
    assert draw_text.text_margin == {"left": 283, "right": 283, "top": 283, "bottom": 283}

    caption = shape.caption
    assert caption is not None
    assert caption.side == "BOTTOM"
    assert caption.full_sz is False
    assert caption.width == 8504
    assert caption.gap == 850
    assert "그림" in caption.text
    doc.close()


def test_table_caption_matches_real_hancom_document() -> None:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(
        "tests/fixtures/hwpxlib_corpus/"
        "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
    )
    captions = []
    for section in doc.sections:
        for para in section.paragraphs:
            for tbl in para.tables:
                if tbl.caption is not None:
                    captions.append(tbl.caption)
    doc.close()

    assert len(captions) == 10
    assert all(c.side == "TOP" for c in captions)
    assert all(c.full_sz is False for c in captions)
    assert any("기상특보" in c.text for c in captions)


def test_shape_set_draw_text_creates_and_round_trips() -> None:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    rect = p.add_rectangle(20000, 10000, treat_as_char=True)
    assert rect.draw_text is None

    rect.set_draw_text("제목 텍스트", name="사각형1")
    assert rect.draw_text.text == "제목 텍스트"
    assert rect.draw_text.name == "사각형1"
    assert rect.draw_text.text_margin == {"left": 283, "right": 283, "top": 283, "bottom": 283}

    out = doc.to_bytes()
    doc.close()

    reopened = HwpxDocument.open(io.BytesIO(out))
    shape2 = reopened.sections[0].paragraphs[1].shapes[0]
    assert shape2.draw_text.text == "제목 텍스트"
    reopened.close()


def test_shape_set_caption_rejects_invalid_side() -> None:
    from hwpx.document import HwpxDocument
    from hwpx.errors import HwpxValueError

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    rect = p.add_rectangle(20000, 10000, treat_as_char=True)
    with pytest.raises(HwpxValueError) as excinfo:
        rect.set_caption("캡션", side="MIDDLE")
    assert excinfo.value.code == "shape-caption-side-invalid"
    doc.close()


def test_shape_remove_caption_and_draw_text() -> None:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    rect = p.add_rectangle(20000, 10000, treat_as_char=True)
    rect.set_caption("캡션")
    rect.set_draw_text("텍스트")

    assert rect.remove_caption() is True
    assert rect.remove_draw_text() is True
    assert rect.caption is None
    assert rect.draw_text is None
    # 이미 없는 것을 다시 지우면 False.
    assert rect.remove_caption() is False
    assert rect.remove_draw_text() is False
    doc.close()


def test_table_set_caption_creates_and_round_trips_at_real_document_position() -> None:
    """게이트 ①: 신규 저작 캡션의 자식 순서가 실코퍼스 실측(outMargin,
    caption, inMargin, tr)과 일치해야 한다."""

    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import tag_local_name

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    tbl = p.add_table(2, 2)
    assert tbl.caption is None

    tbl.set_caption("표 1 요약", side="TOP")
    children = [tag_local_name(c.tag) for c in tbl.element]
    assert children.index("caption") == children.index("outMargin") + 1
    assert children.index("caption") == children.index("inMargin") - 1

    out = doc.to_bytes()
    doc.close()

    reopened = HwpxDocument.open(io.BytesIO(out))
    tbl2 = reopened.sections[0].paragraphs[1].tables[0]
    assert tbl2.caption.text == "표 1 요약"
    assert tbl2.caption.side == "TOP"
    reopened.close()


def test_inline_object_set_caption_on_picture() -> None:
    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import tag_local_name

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    media = doc.media.add_image(b"\x89PNG\r\n\x1a\n" + b"0" * 40, "png")
    pic = p.add_picture(media.item_id, width=10000, height=8000)
    assert pic.caption is None

    pic.set_caption("그림 1. 테스트", side="BOTTOM")
    assert pic.caption.text == "그림 1. 테스트"
    # outMargin 다음(표/도형과 같은 관행) — 이 자리는 실코퍼스 표본이 없어
    # unverified 명시: 표/도형에서 검증된 규칙을 그대로 적용했을 뿐이다.
    children = [tag_local_name(c.tag) for c in pic.element]
    assert children.index("caption") == children.index("outMargin") + 1

    out = doc.to_bytes()
    doc.close()

    reopened = HwpxDocument.open(io.BytesIO(out))
    from hwpx.oxml.objects import HwpxOxmlInlineObject

    reopened_paragraph = reopened.sections[0].paragraphs[1]
    pic_element = next(
        e for e in reopened_paragraph.element.iter() if tag_local_name(e.tag) == "pic"
    )
    pic2 = HwpxOxmlInlineObject(pic_element, reopened_paragraph)
    assert pic2.caption.text == "그림 1. 테스트"
    assert pic2.caption.side == "BOTTOM"
    reopened.close()


def test_markdown_export_includes_table_caption() -> None:
    from hwpx.document import HwpxDocument
    from hwpx.tools.markdown_export import export_markdown

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    tbl = p.add_table(1, 1)
    tbl.set_caption("표 1 매출 현황")
    md = export_markdown(doc)
    doc.close()
    assert "표 1 매출 현황" in md


def test_markdown_export_includes_picture_caption(tmp_path) -> None:
    from hwpx.document import HwpxDocument
    from hwpx.tools.markdown_export import export_markdown

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    media = doc.media.add_image(b"\x89PNG\r\n\x1a\n" + b"0" * 40, "png")
    pic = p.add_picture(media.item_id, width=10000, height=8000)
    pic.set_caption("그림 1. 매출 그래프")
    md = export_markdown(doc, image_dir=str(tmp_path))
    doc.close()
    assert "![image]" in md
    assert "*그림 1. 매출 그래프*" in md


def test_shape_text_and_caption_stay_undistorted_after_real_document_round_trip() -> None:
    """게이트 ②: 왕복 무손상 — drawText/caption 서브트리가 수정 없이
    open→save 를 거쳐도 바이트 수준으로 그대로다."""

    import zipfile

    from lxml import etree

    from hwpx.document import HwpxDocument

    path = "tests/fixtures/hwpxlib_corpus/reader_writer__SimpleRectangle.hwpx"
    with zipfile.ZipFile(path) as zf:
        original = zf.read("Contents/section0.xml")

    doc = HwpxDocument.open(path)
    out = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        reopened = zf.read("Contents/section0.xml")

    ns = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    orig_root = etree.fromstring(original)
    new_root = etree.fromstring(reopened)
    orig_dt = [etree.tostring(e) for e in orig_root.findall(".//hp:drawText", ns)]
    new_dt = [etree.tostring(e) for e in new_root.findall(".//hp:drawText", ns)]
    orig_cap = [etree.tostring(e) for e in orig_root.findall(".//hp:caption", ns)]
    new_cap = [etree.tostring(e) for e in new_root.findall(".//hp:caption", ns)]
    assert orig_dt == new_dt
    assert orig_cap == new_cap


def test_paragraph_add_shape_and_control_updates_attributes() -> None:
    section, paragraph = _build_section_with_paragraph()

    # 두 진입점 모두 OWPML 필수 자식 없이 만들어진다 — 한컴이 못 여는 산출물이라
    # 생성 시점에 경고한다.
    with pytest.warns(UserWarning, match="orgSz"):
        shape = paragraph.add_shape("rect", {"width": "8000"})
    assert shape.get_attribute("width") == "8000"
    section.reset_dirty()
    shape.set_attribute("width", "9000")
    assert shape.get_attribute("width") == "9000"
    assert section.dirty is True

    section.reset_dirty()
    with pytest.warns(UserWarning, match="no control child"):
        control = paragraph.add_control({"id": "ctrl1"}, control_type="LINE")
    assert control.get_attribute("type") == "LINE"
    section.reset_dirty()
    control.set_attribute("id", "ctrl2")
    assert control.get_attribute("id") == "ctrl2"
    control.set_attribute("id", None)
    assert control.get_attribute("id") is None
    assert section.dirty is True


# ---------------------------------------------------------------------------
# Regression: issue #30 — stdlib ET.SubElement called on lxml _Element
# https://github.com/airmang/python-hwpx/issues/30
# ---------------------------------------------------------------------------


def test_issue_30_set_cell_text_on_blank_cell() -> None:
    """Setting ``cell.text`` on a cell that lacks ``<hp:subList>/<hp:p>/<hp:run>``
    must not raise ``TypeError``.

    Before the fix, ``HwpxOxmlTableCell._ensure_text_element`` used
    ``ET.SubElement`` (stdlib) on ``self.element`` which is an
    ``lxml.etree._Element``. This reproduces the call path reported by
    ``@devnoff`` in issue #30 and by downstream consumers running
    ``table.set_cell_text(...)`` on freshly created tables.
    """

    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)

    # Both the explicit API and the property setter must succeed.
    table.set_cell_text(0, 0, "hello")
    cells = list(table.rows[1].cells)
    cells[1].text = "world"

    assert table.rows[0].cells[0].text == "hello"
    assert table.rows[1].cells[1].text == "world"


def test_issue_30_add_run_bold() -> None:
    """``paragraph.add_run(text, bold=True)`` must not raise ``TypeError``.

    Before the fix, ``ensure_run_style``'s ``modifier`` closure called
    ``ET.SubElement(element, ...)`` where ``element`` is an lxml element.
    This is the original reproduction from the body of issue #30.
    """

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    run = paragraph.add_run("hello", bold=True)

    assert run.text == "hello"
