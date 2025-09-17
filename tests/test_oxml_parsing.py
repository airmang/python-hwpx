from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from lxml import etree

from hwpx.oxml import (
    BeginNum,
    Header,
    HwpxOxmlHeader,
    MemoShape,
    Paragraph,
    Run,
    Section,
    TextSpan,
    element_to_model,
    load_schema,
    parse_header_xml,
    parse_section_xml,
)

SAMPLE_FILE = Path("hwpx-java-library/testFile/reader_writer/SimpleLine.hwpx")


def _read_zip_entry(path: Path, entry: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        with archive.open(entry) as stream:
            return stream.read()


def test_parse_header_sample_document() -> None:
    header_xml = _read_zip_entry(SAMPLE_FILE, "Contents/header.xml")
    header = parse_header_xml(header_xml)

    assert isinstance(header, Header)
    assert header.version == "1.4"
    assert header.sec_cnt == 1
    assert header.begin_num is not None
    assert header.begin_num.page == 1
    assert header.doc_option is not None
    assert header.doc_option.link_info.page_inherit is False

    assert header.ref_list is not None
    assert header.ref_list.fontfaces is not None
    assert header.ref_list.fontfaces.item_cnt == len(header.ref_list.fontfaces.fontfaces)
    first_font = header.ref_list.fontfaces.fontfaces[0].fonts[0]
    assert first_font.face
    assert header.ref_list.char_properties is not None
    assert header.ref_list.char_properties.properties


def test_parse_section_sample_document() -> None:
    section_xml = _read_zip_entry(SAMPLE_FILE, "Contents/section0.xml")
    section = parse_section_xml(section_xml)

    assert isinstance(section, Section)
    assert section.paragraphs

    paragraph = section.paragraphs[0]
    assert isinstance(paragraph, Paragraph)
    assert paragraph.runs

    run = paragraph.runs[0]
    assert isinstance(run, Run)
    assert run.inline_objects
    assert run.inline_objects[0].name == "line"


def test_parse_section_with_text_marks() -> None:
    xml = (
        "<hs:sec xmlns:hs='http://www.owpml.org/owpml/2024/section' "
        "xmlns:hp='http://www.owpml.org/owpml/2024/paragraph'>"
        "<hp:p id='1' paraPrIDRef='1' styleIDRef='1'>"
        "<hp:run charPrIDRef='0'>"
        "<hp:t>Hello <hp:markpenBegin color='#FFFF00'/>World</hp:t>"
        "</hp:run>"
        "</hp:p>"
        "</hs:sec>"
    )

    section = parse_section_xml(xml)
    span = section.paragraphs[0].runs[0].text_spans[0]

    assert isinstance(span, TextSpan)
    assert span.text == "Hello World"
    assert span.marks and span.marks[0].name == "markpenBegin"


def test_element_factory_maps_begin_num() -> None:
    element = etree.fromstring(
        "<hh:beginNum xmlns:hh='http://www.owpml.org/owpml/2024/head' "
        "page='3' footnote='4' endnote='5' pic='6' tbl='7' equation='8'/>"
    )

    obj = element_to_model(element)
    assert isinstance(obj, BeginNum)
    assert obj.tbl == 7


def test_load_schema_core_file() -> None:
    schema_path = Path("DevDoc") / "OWPML SCHEMA" / "Core XML schema.xml"
    schema = load_schema(schema_path)
    assert schema is not None


def test_parse_header_memo_properties_fixture() -> None:
    fixture = Path("tests/fixtures/header_with_memo.xml")
    header = parse_header_xml(fixture.read_bytes())

    assert isinstance(header, Header)
    assert header.ref_list is not None
    assert "memoProperties" not in header.ref_list.other_collections

    memo_props = header.ref_list.memo_properties
    assert memo_props is not None
    assert memo_props.item_cnt == 2
    assert memo_props.attributes["custom"] == "yes"
    assert len(memo_props.memo_shapes) == 2

    first_shape, second_shape = memo_props.memo_shapes
    assert isinstance(first_shape, MemoShape)
    assert first_shape.width == 15591
    assert first_shape.line_width == "0.6mm"
    assert first_shape.memo_type == "NOMAL"
    assert first_shape.attributes["lineColor"] == "#B6D7AE"

    assert second_shape.active_color == "#778899"
    assert second_shape.attributes["data-extra"] == "true"

    assert memo_props.shape_by_id("0") == first_shape
    assert header.memo_shape(0) == first_shape
    assert header.memo_shape("7") == second_shape
    assert header.memo_shape(" 7 ") == second_shape
    assert header.memo_shape("missing") is None


def test_hwpx_oxml_header_exposes_memo_shapes() -> None:
    fixture = Path("tests/fixtures/header_with_memo.xml")
    element = ET.fromstring(fixture.read_text(encoding="utf-8"))
    header = HwpxOxmlHeader("header.xml", element)

    shapes = header.memo_shapes
    assert "0" in shapes and "7" in shapes

    zero_shape = shapes["0"]
    assert isinstance(zero_shape, MemoShape)
    assert zero_shape.fill_color == "#F0FFE9"
    assert header.memo_shape(0) == zero_shape

    shape_seven = header.memo_shape("7")
    assert shape_seven is not None
    assert shape_seven.line_type == "DOT"
    assert shape_seven.attributes["data-extra"] == "true"

    assert header.memo_shape("07") == shapes["7"]
    assert header.memo_shape(None) is None
    assert header.memo_shape("unknown") is None
