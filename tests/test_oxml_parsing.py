from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from lxml import etree

from hwpx.oxml import (
    BeginNum,
    Bullet,
    Header,
    HwpxOxmlDocument,
    HwpxOxmlHeader,
    MemoShape,
    Paragraph,
    ParagraphProperty,
    Run,
    Section,
    Style,
    TextSpan,
    TrackChange,
    TrackChangeAuthor,
    element_to_model,
    load_schema,
    parse_header_xml,
    parse_section_xml,
)

SAMPLE_FILE = Path("hwpx-java-library/testFile/reader_writer/SimpleLine.hwpx")


def _read_zip_entry(path: Path, entry: str) -> bytes:
    if not path.exists():
        pytest.skip("Sample HWPX package not available")
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


def test_parse_header_full_reference_lists() -> None:
    fixture = Path("tests/fixtures/header_with_full_refs.xml")
    header = parse_header_xml(fixture.read_bytes())

    assert isinstance(header, Header)
    ref_list = header.ref_list
    assert ref_list is not None

    bullet_list = ref_list.bullets
    assert bullet_list is not None
    assert bullet_list.item_cnt == 2
    assert len(bullet_list.bullets) == 2

    first_bullet, second_bullet = bullet_list.bullets
    assert isinstance(first_bullet, Bullet)
    assert first_bullet.id == 0
    assert first_bullet.raw_id == "0"
    assert first_bullet.char == "●"
    assert first_bullet.checked_char == "○"
    assert first_bullet.use_image is False
    assert first_bullet.para_head.level == 1
    assert first_bullet.para_head.text == "^1."
    assert first_bullet.para_head.align == "LEFT"
    assert header.bullet(0) is first_bullet
    assert header.bullet("0") is first_bullet

    assert isinstance(second_bullet, Bullet)
    assert second_bullet.id == 2
    assert second_bullet.raw_id == "02"
    assert second_bullet.use_image is True
    assert second_bullet.image is not None
    assert second_bullet.image.attributes["binaryItemIDRef"] == "100"
    assert second_bullet.para_head.text == "prefix"
    assert second_bullet.para_head.text_offset_type == "HWPUNIT"
    assert header.bullet(2) is second_bullet
    assert header.bullet("02") is second_bullet

    para_properties = ref_list.para_properties
    assert para_properties is not None
    assert para_properties.item_cnt == 2
    assert len(para_properties.properties) == 2

    first_prop, second_prop = para_properties.properties
    assert isinstance(first_prop, ParagraphProperty)
    assert first_prop.id == 1
    assert first_prop.tab_pr_id_ref == 10
    assert first_prop.condense == 5
    assert first_prop.font_line_height is True
    assert first_prop.snap_to_grid is False
    assert first_prop.suppress_line_numbers is True
    assert first_prop.checked is True
    assert first_prop.align is not None and first_prop.align.horizontal == "JUSTIFY"
    assert first_prop.heading is not None and first_prop.heading.id_ref == 0
    assert first_prop.break_setting is not None
    assert first_prop.break_setting.break_latin_word == "KEEP_WORD"
    assert first_prop.margin is not None and first_prop.margin.left == "10mm"
    assert first_prop.line_spacing is not None and first_prop.line_spacing.value == 160
    assert first_prop.border is not None and first_prop.border.border_fill_id_ref == 7
    assert first_prop.auto_spacing is not None and first_prop.auto_spacing.e_asian_eng is True
    assert header.paragraph_property(1) is first_prop
    assert header.paragraph_property("1") is first_prop

    assert isinstance(second_prop, ParagraphProperty)
    assert second_prop.id == 7
    assert second_prop.raw_id == "07"
    assert second_prop.align is not None and second_prop.align.horizontal == "LEFT"
    assert second_prop.margin is not None and second_prop.margin.intent == "-10mm"
    assert header.paragraph_property(7) is second_prop
    assert header.paragraph_property("07") is second_prop

    styles = ref_list.styles
    assert styles is not None
    assert styles.item_cnt == 2
    assert len(styles.styles) == 2

    normal_style, emphasis_style = styles.styles
    assert isinstance(normal_style, Style)
    assert normal_style.id == 0
    assert normal_style.type == "PARA"
    assert normal_style.name == "Normal"
    assert normal_style.para_pr_id_ref == 1
    assert normal_style.char_pr_id_ref == 0
    assert normal_style.lock_form is True
    assert header.style("0") is normal_style
    assert header.style(0) is normal_style

    assert isinstance(emphasis_style, Style)
    assert emphasis_style.id == 3
    assert emphasis_style.raw_id == "03"
    assert emphasis_style.name == "Emphasis"
    assert emphasis_style.eng_name == "Emphasis"
    assert emphasis_style.char_pr_id_ref == 2
    assert header.style("03") is emphasis_style
    assert header.style(3) is emphasis_style

    memo_props = ref_list.memo_properties
    assert memo_props is not None
    assert memo_props.item_cnt == 1
    assert len(memo_props.memo_shapes) == 1
    assert memo_props.memo_shapes[0].id == 9

    track_changes = ref_list.track_changes
    assert track_changes is not None
    assert track_changes.item_cnt == 2
    assert len(track_changes.changes) == 2

    change_insert, change_delete = track_changes.changes
    assert isinstance(change_insert, TrackChange)
    assert change_insert.id == 1
    assert change_insert.change_type == "INSERT"
    assert change_insert.author_id == 5
    assert change_insert.char_shape_id == 10
    assert change_insert.hide is False
    assert header.track_change(1) is change_insert
    assert header.track_change("1") is change_insert

    assert isinstance(change_delete, TrackChange)
    assert change_delete.id == 5
    assert change_delete.raw_id == "05"
    assert change_delete.change_type == "DELETE"
    assert change_delete.hide is True
    assert header.track_change(5) is change_delete
    assert header.track_change("05") is change_delete

    authors = ref_list.track_change_authors
    assert authors is not None
    assert authors.item_cnt == 1
    assert len(authors.authors) == 1

    author = authors.authors[0]
    assert isinstance(author, TrackChangeAuthor)
    assert author.id == 5
    assert author.raw_id == "5"
    assert author.name == "Alice"
    assert author.mark is True
    assert author.color == "#FF0000"
    assert header.track_change_author(5) is author
    assert header.track_change_author("5") is author


def test_hwpx_oxml_header_reference_lookup_full_fixture() -> None:
    fixture = Path("tests/fixtures/header_with_full_refs.xml")
    element = ET.fromstring(fixture.read_text(encoding="utf-8"))
    header = HwpxOxmlHeader("header.xml", element)

    bullets = header.bullets
    assert bullets["0"].char == "●"
    assert bullets["02"].use_image is True
    assert "2" in bullets
    assert header.bullet("02").char == "※"
    assert header.bullet(2).para_head.level == 2

    para_props = header.paragraph_properties
    assert para_props["1"].align.horizontal == "JUSTIFY"
    assert para_props["7"].margin.intent == "-10mm"
    assert header.paragraph_property("07").margin.intent == "-10mm"

    styles = header.styles
    assert styles["0"].name == "Normal"
    assert styles["03"].eng_name == "Emphasis"
    assert header.style("03").char_pr_id_ref == 2

    changes = header.track_changes
    assert changes["1"].change_type == "INSERT"
    assert changes["05"].hide is True
    assert header.track_change("05").hide is True

    authors = header.track_change_authors
    assert authors["5"].name == "Alice"
    assert header.track_change_author(5).color == "#FF0000"


def test_hwpx_oxml_document_reference_helpers_merge_headers() -> None:
    fixture = Path("tests/fixtures/header_with_full_refs.xml")
    xml = fixture.read_text(encoding="utf-8")

    primary_element = ET.fromstring(xml)
    secondary_element = ET.fromstring(xml)
    hh = "{http://www.hancom.co.kr/hwpml/2011/head}"

    alternate_bullet = secondary_element.find(f"{hh}refList/{hh}bullets/{hh}bullet")
    assert alternate_bullet is not None
    alternate_bullet.set("id", "99")
    alternate_bullet.set("char", "◆")
    para_head = alternate_bullet.find(f"{hh}paraHead")
    if para_head is not None:
        para_head.text = "◆"

    primary_header = HwpxOxmlHeader("primary.xml", primary_element)
    secondary_header = HwpxOxmlHeader("secondary.xml", secondary_element)
    manifest = ET.Element("manifest")
    document = HwpxOxmlDocument(manifest, [], [primary_header, secondary_header])

    bullets = document.bullets
    assert bullets["0"].char == "●"
    assert bullets["02"].char == "※"
    assert bullets["99"].char == "◆"
    assert document.bullet("99").char == "◆"
    assert document.bullet(2).use_image is True

    para_props = document.paragraph_properties
    assert para_props["1"].align.horizontal == "JUSTIFY"
    assert para_props["7"].margin.intent == "-10mm"

    styles = document.styles
    assert styles["0"].name == "Normal"
    assert document.style("03").eng_name == "Emphasis"

    changes = document.track_changes
    assert changes["1"].author_id == 5
    assert document.track_change("05").hide is True

    authors = document.track_change_authors
    assert authors["5"].name == "Alice"
    assert document.track_change_author(5).mark is True
