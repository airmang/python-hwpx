from __future__ import annotations

from typing import cast
import pytest
import xml.etree.ElementTree as ET

from hwpx.document import HwpxDocument
from hwpx.oxml.document import (
    HwpxOxmlDocument,
    HwpxOxmlHeader,
    HwpxOxmlParagraph,
    HwpxOxmlSection,
)
from hwpx.package import HwpxPackage


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


def test_table_merge_cells_updates_spans_and_structure() -> None:
    section_element = ET.Element(f"{HS}sec")
    section = HwpxOxmlSection("section0.xml", section_element)
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [])
    document = HwpxDocument(cast(HwpxPackage, object()), root)

    table = document.add_table(3, 3, section=section)
    initial_width = table.cell(0, 0).width
    initial_height = table.cell(0, 0).height
    section.reset_dirty()

    merged = table.merge_cells(0, 0, 1, 1)

    assert merged.span == (2, 2)
    assert merged.width >= initial_width
    assert merged.height >= initial_height
    assert table.cell(0, 1).element is merged.element
    assert table.cell(1, 0).element is merged.element
    assert len(table.rows[0].cells) == 2
    assert len(table.rows[1].cells) == 1
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


def test_paragraph_add_shape_and_control_updates_attributes() -> None:
    section, paragraph = _build_section_with_paragraph()

    shape = paragraph.add_shape("rect", {"width": "8000"})
    assert shape.get_attribute("width") == "8000"
    section.reset_dirty()
    shape.set_attribute("width", "9000")
    assert shape.get_attribute("width") == "9000"
    assert section.dirty is True

    section.reset_dirty()
    control = paragraph.add_control({"id": "ctrl1"}, control_type="LINE")
    assert control.get_attribute("type") == "LINE"
    section.reset_dirty()
    control.set_attribute("id", "ctrl2")
    assert control.get_attribute("id") == "ctrl2"
    control.set_attribute("id", None)
    assert control.get_attribute("id") is None
    assert section.dirty is True
