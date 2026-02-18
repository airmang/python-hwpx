from __future__ import annotations

from typing import cast
import xml.etree.ElementTree as ET

import pytest

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlDocument, HwpxOxmlHeader, HwpxOxmlSection, RunStyle
from hwpx.opc.package import HwpxPackage


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"
HH = f"{{{HH_NS}}}"


def _build_header() -> HwpxOxmlHeader:
    element = ET.Element(f"{HH}head")
    ref_list = ET.SubElement(element, f"{HH}refList")
    char_props = ET.SubElement(ref_list, f"{HH}charProperties", {"itemCnt": "1"})
    char_pr = ET.SubElement(
        char_props,
        f"{HH}charPr",
        {
            "id": "10",
            "textColor": "#FF0000",
            "shadeColor": "none",
            "useFontSpace": "0",
            "useKerning": "0",
            "symMark": "NONE",
            "borderFillIDRef": "0",
        },
    )
    ET.SubElement(char_pr, f"{HH}underline", {"type": "SOLID", "color": "#FF0000"})
    memo_props = ET.SubElement(ref_list, f"{HH}memoProperties", {"itemCnt": "1"})
    ET.SubElement(
        memo_props,
        f"{HH}memoPr",
        {
            "id": "5",
            "width": "12000",
            "lineColor": "#123456",
            "fillColor": "#eeeeee",
        },
    )
    return HwpxOxmlHeader("header.xml", element)


def _build_section() -> HwpxOxmlSection:
    element = ET.Element(f"{HS}sec")
    paragraph = ET.SubElement(
        element,
        f"{HP}p",
        {"paraPrIDRef": "0", "styleIDRef": "0"},
    )
    run = ET.SubElement(paragraph, f"{HP}run", {"charPrIDRef": "10"})
    ET.SubElement(run, f"{HP}t").text = "Hello memo world"

    memo_group = ET.SubElement(element, f"{HP}memogroup")
    memo = ET.SubElement(memo_group, f"{HP}memo", {"id": "memo0", "memoShapeIDRef": "5"})
    para_list = ET.SubElement(memo, f"{HP}paraList")
    memo_paragraph = ET.SubElement(
        para_list,
        f"{HP}p",
        {"paraPrIDRef": "0", "styleIDRef": "0"},
    )
    memo_run = ET.SubElement(memo_paragraph, f"{HP}run", {"charPrIDRef": "10"})
    ET.SubElement(memo_run, f"{HP}t").text = "Initial memo"
    return HwpxOxmlSection("section0.xml", element)


def _build_document() -> tuple[HwpxDocument, HwpxOxmlSection, HwpxOxmlHeader]:
    header = _build_header()
    section = _build_section()
    manifest = ET.Element("manifest")
    root = HwpxOxmlDocument(manifest, [section], [header])
    document = HwpxDocument(cast(HwpxPackage, object()), root)
    section.reset_dirty()
    return document, section, header


def test_section_memo_parsing_exposes_text_and_shape() -> None:
    document, section, header = _build_document()

    memos = section.memos
    assert len(memos) == 1
    memo = memos[0]
    assert memo.text == "Initial memo"
    assert memo.memo_shape_id_ref == "5"

    shapes = document.memo_shapes
    assert "5" in shapes
    assert shapes["5"].fill_color == "#eeeeee"
    assert document.memo_shape(5) == shapes["5"]


def test_document_add_edit_and_remove_memos() -> None:
    document, section, _ = _build_document()

    new_memo = document.add_memo("Another memo", memo_shape_id_ref="5")
    assert any(memo.id == new_memo.id for memo in section.memos)
    assert new_memo.text == "Another memo"

    new_memo.text = "Edited memo"
    assert any(memo.text == "Edited memo" for memo in section.memos)

    document.remove_memo(new_memo)
    assert all(memo.id != new_memo.id for memo in section.memos)

    # Removing the remaining memo should clean up the memo group element entirely.
    document.remove_memo(section.memos[0])
    assert section.element.find(f"{HP}memogroup") is None


def test_find_runs_by_style_and_replace_text_marks_section_dirty() -> None:
    document, section, _ = _build_document()

    runs = document.find_runs_by_style(text_color="#FF0000")
    assert len(runs) == 1
    run = runs[0]
    assert run.text == "Hello memo world"

    section.reset_dirty()
    replaced = document.replace_text_in_runs("memo", "note", text_color="#FF0000")
    assert replaced == 1
    assert run.text == "Hello note world"
    assert section.dirty is True


def test_replace_text_in_runs_respects_limit() -> None:
    document, section, _ = _build_document()
    run = section.paragraphs[0].runs[0]
    run.text = "red red red"
    section.reset_dirty()

    replaced = document.replace_text_in_runs(
        "red",
        "blue",
        text_color="#FF0000",
        limit=2,
    )
    assert replaced == 2
    assert run.text == "blue blue red"


def test_char_property_lookup_returns_style() -> None:
    document, _, _ = _build_document()

    style = document.char_property("10")
    assert isinstance(style, RunStyle)
    assert style.text_color() == "#FF0000"
    assert style.underline_type() == "SOLID"


def test_replace_text_requires_non_empty_search() -> None:
    document, _, _ = _build_document()

    with pytest.raises(ValueError):
        document.replace_text_in_runs("", "ignored")


def test_find_runs_by_style_can_filter_by_char_pr() -> None:
    document, section, _ = _build_document()
    run = section.paragraphs[0].runs[0]

    matches = document.find_runs_by_style(char_pr_id_ref="10")
    assert len(matches) == 1
    assert matches[0].element is run.element
    assert document.find_runs_by_style(char_pr_id_ref="99") == []


def test_attach_memo_field_inserts_control_runs() -> None:
    document, section, _ = _build_document()
    paragraph = section.paragraphs[0]

    memo = document.add_memo("Follow-up", memo_shape_id_ref="5", memo_id="release-1", char_pr_id_ref="10")

    field_id = document.attach_memo_field(
        paragraph,
        memo,
        field_id="field-01",
        author="QA",
        created="2024-12-02 09:00:00",
        number=3,
        char_pr_id_ref="10",
    )

    assert field_id == "field-01"
    runs = paragraph.element.findall(f"{HP}run")
    assert len(runs) >= 2

    field_begin = runs[0].find(f"{HP}ctrl/{HP}fieldBegin")
    assert field_begin is not None
    assert field_begin.get("id") == "field-01"

    parameters = field_begin.find(f"{HP}parameters")
    assert parameters is not None
    assert parameters.get("count") == "5"
    memo_shape_param = parameters.find(f"{HP}stringParam[@name='MemoShapeID']")
    assert memo_shape_param is not None
    assert memo_shape_param.text == memo.memo_shape_id_ref

    field_end = runs[-1].find(f"{HP}ctrl/{HP}fieldEnd")
    assert field_end is not None
    assert field_end.get("beginIDRef") == "field-01"


def test_add_memo_with_anchor_creates_paragraph_when_missing() -> None:
    document, section, _ = _build_document()

    memo, paragraph, field_id = document.add_memo_with_anchor(
        "Anchored memo",
        section=section,
        memo_shape_id_ref="5",
        memo_id="release-2",
        char_pr_id_ref="10",
        paragraph_text="Anchor target",
        field_id="field-02",
        anchor_char_pr_id_ref="10",
    )

    assert memo.text == "Anchored memo"
    assert paragraph.text.endswith("Anchor target")
    assert field_id == "field-02"

    runs = paragraph.element.findall(f"{HP}run")
    assert runs
    field_begin = runs[0].find(f"{HP}ctrl/{HP}fieldBegin")
    assert field_begin is not None
    assert field_begin.get("id") == "field-02"

    field_end = runs[-1].find(f"{HP}ctrl/{HP}fieldEnd")
    assert field_end is not None
    assert field_end.get("beginIDRef") == "field-02"


def test_document_ensure_run_style_creates_bold_entry() -> None:
    document, _, header = _build_document()

    char_props = header.element.find(f"{HH}refList/{HH}charProperties")
    assert char_props is not None
    initial_count = len(list(char_props.findall(f"{HH}charPr")))

    style_id = document.ensure_run_style(bold=True)
    assert style_id != "10"

    assert char_props.get("itemCnt") == str(initial_count + 1)
    created = char_props.find(f"{HH}charPr[@id='{style_id}']")
    assert created is not None
    assert created.find(f"{HH}bold") is not None
    underline = created.find(f"{HH}underline")
    assert underline is not None and underline.get("type") == "NONE"

    style = document.char_property(style_id)
    assert style is not None and "bold" in style.child_attributes

    assert document.ensure_run_style(bold=True) == style_id
    assert char_props.get("itemCnt") == str(initial_count + 1)


def test_paragraph_add_run_and_toggle_formatting() -> None:
    document, section, header = _build_document()
    paragraph = section.paragraphs[0]
    char_props = header.element.find(f"{HH}refList/{HH}charProperties")
    assert char_props is not None

    initial_count = len(list(char_props.findall(f"{HH}charPr")))
    run = paragraph.add_run("서식 적용", bold=True)

    assert run.text == "서식 적용"
    assert run.bold is True
    assert run.italic is False
    assert run.underline is False

    bold_id = run.char_pr_id_ref
    assert bold_id is not None
    bold_entry = char_props.find(f"{HH}charPr[@id='{bold_id}']")
    assert bold_entry is not None
    assert len(list(char_props.findall(f"{HH}charPr"))) == initial_count + 1

    run.italic = True
    assert run.bold is True
    assert run.italic is True
    italic_id = run.char_pr_id_ref
    assert italic_id is not None and italic_id != bold_id
    italic_entry = char_props.find(f"{HH}charPr[@id='{italic_id}']")
    assert italic_entry is not None
    assert italic_entry.find(f"{HH}bold") is not None
    assert italic_entry.find(f"{HH}italic") is not None

    run.underline = True
    assert run.underline is True
    underline_id = run.char_pr_id_ref
    underline_entry = char_props.find(f"{HH}charPr[@id='{underline_id}']")
    assert underline_entry is not None
    underline_node = underline_entry.find(f"{HH}underline")
    assert underline_node is not None and underline_node.get("type", "") != "NONE"

    total_styles = len(list(char_props.findall(f"{HH}charPr")))
    assert total_styles == initial_count + 3
    assert char_props.get("itemCnt") == str(total_styles)
