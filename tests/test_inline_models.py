from __future__ import annotations

import xml.etree.ElementTree as ET

from hwpx.oxml import HwpxOxmlSection
from hwpx.oxml.body import TrackChangeMark
from hwpx.oxml.parser import parse_section_xml


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"


def _sample_section_xml() -> str:
    return (
        "<hs:sec xmlns:hs='"
        f"{_HS_NS}' xmlns:hp='{_HP_NS}'>"
        "<hp:p id='1' paraPrIDRef='1' styleIDRef='2'>"
        "<hp:run charPrIDRef='0'>"
        "<hp:ctrl type='FORM' id='ctrl1'>"
        "<hp:fieldBegin id='7' type='DATE'/>"
        "</hp:ctrl>"
        "<hp:t charStyleIDRef='3'>Prefix"
        "<hp:insertBegin TcId='7' Id='3'/>"
        "Middle"
        "<hp:insertEnd TcId='7' paraend='false'/>"
        "Suffix"
        "</hp:t>"
        "<hp:tbl width='2400'>"
        "<hp:tr><hp:tc><hp:cellAddr rowAddr='1' colAddr='1'/></hp:tc></hp:tr>"
        "</hp:tbl>"
        "<hp:line shapeID='ln1' linewidth='2'/>"
        "</hp:run>"
        "</hp:p>"
        "</hs:sec>"
    )


def test_run_model_contains_typed_children() -> None:
    section = parse_section_xml(_sample_section_xml())
    paragraph = section.paragraphs[0]
    run = paragraph.runs[0]

    control = run.controls[0]
    assert control.control_type == "FORM"
    assert control.attributes["id"] == "ctrl1"
    assert control.children and control.children[0].name == "fieldBegin"

    span = run.text_spans[0]
    assert span.leading_text == "Prefix"
    marks = [mark for mark in span.marks if isinstance(mark.element, TrackChangeMark)]
    assert marks and marks[0].element.tc_id == 7
    assert marks[0].element.is_begin is True
    assert marks[0].trailing_text == "Middle"

    table = run.tables[0]
    assert table.attributes["width"] == "2400"
    assert table.children and table.children[0].name == "tr"

    inline = run.inline_objects[0]
    assert inline.name == "line"
    assert inline.attributes["shapeID"] == "ln1"

    child_types = [type(child).__name__ for child in run.content]
    assert child_types == ["Control", "TextSpan", "Table", "InlineObject"]


def test_run_and_paragraph_round_trip_after_mutation() -> None:
    section_element = ET.fromstring(_sample_section_xml())
    section = HwpxOxmlSection("section0.xml", section_element)
    paragraph = section.paragraphs[0]
    run = paragraph.runs[0]

    run_model = run.to_model()
    run_model.char_pr_id_ref = 5
    run_model.controls[0].control_type = "PAGE_NUMBER"
    run_model.controls[0].attributes["id"] = "ctrl2"
    run_model.tables[0].attributes["width"] = "3600"
    run_model.inline_objects[0].attributes["linewidth"] = "3"

    span = run_model.text_spans[0]
    span.leading_text = "Intro"
    track_marks = [mark for mark in span.marks if isinstance(mark.element, TrackChangeMark)]
    assert track_marks  # sanity guard
    track_marks[0].element.tc_id = 13
    span.marks[0].trailing_text = "Body"
    span.marks[1].trailing_text = "Outro"

    run.apply_model(run_model)
    updated_model = run.to_model()

    assert updated_model.char_pr_id_ref == 5
    assert updated_model.controls[0].control_type == "PAGE_NUMBER"
    assert updated_model.controls[0].attributes["id"] == "ctrl2"
    assert updated_model.tables[0].attributes["width"] == "3600"
    assert updated_model.inline_objects[0].attributes["linewidth"] == "3"

    updated_span = updated_model.text_spans[0]
    assert updated_span.leading_text == "Intro"
    updated_marks = [mark for mark in updated_span.marks if isinstance(mark.element, TrackChangeMark)]
    assert updated_marks and updated_marks[0].element.tc_id == 13
    assert updated_span.marks[0].trailing_text == "Body"
    assert updated_span.marks[1].trailing_text == "Outro"

    paragraph_model = paragraph.to_model()
    paragraph_model.para_pr_id_ref = 9
    paragraph_model.runs[0].controls[0].attributes["name"] = "renamed"

    paragraph.apply_model(paragraph_model)
    roundtrip = paragraph.to_model()

    assert roundtrip.para_pr_id_ref == 9
    assert roundtrip.runs[0].controls[0].attributes["name"] == "renamed"
