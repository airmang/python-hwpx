from __future__ import annotations

import io
from zipfile import ZipFile

from hwpx.document import HwpxDocument
from hwpx.oxml.parser import parse_section_xml
from hwpx.tools.exporter import export_html, export_markdown, export_text
from hwpx.tools.text_extractor import TextExtractor


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"


def test_run_model_preserves_hp_tab_in_content_order() -> None:
    xml = (
        "<hs:sec xmlns:hs='"
        f"{_HS_NS}' xmlns:hp='{_HP_NS}'>"
        "<hp:p><hp:run><hp:t>left</hp:t><hp:tab/><hp:t>right</hp:t></hp:run></hp:p>"
        "</hs:sec>"
    )

    section = parse_section_xml(xml)
    run = section.paragraphs[0].runs[0]

    assert [type(child).__name__ for child in run.content] == ["TextSpan", "Tab", "TextSpan"]
    assert len(run.tabs) == 1


def test_exporters_and_extractor_render_hp_tab_text() -> None:
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<hs:sec xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'"
        " xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>"
        "  <hp:p><hp:run><hp:t>left</hp:t><hp:tab/><hp:t>right</hp:t></hp:run></hp:p>"
        "  <hp:p><hp:run><hp:t>ctrl</hp:t><hp:ctrl id='tab'/><hp:t>path</hp:t></hp:run></hp:p>"
        "</hs:sec>"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)
    payload = buffer.getvalue()

    assert export_text(payload) == "left\tright\nctrl\tpath"
    assert "<p>left\tright</p>" in export_html(payload, full_document=False)
    assert "left\tright" in export_markdown(payload)

    with TextExtractor(io.BytesIO(payload)) as extractor:
        paragraphs = list(extractor.iter_document_paragraphs(include_nested=False))
    assert paragraphs[0].text() == "left\tright"
    assert paragraphs[1].text() == "ctrl\tpath"


def test_document_paragraph_roundtrip_preserves_tab_semantics() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("left\tright")

    assert paragraph.text == "left\tright"

    saved = doc.to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(saved))
    assert reopened.sections[0].paragraphs[-1].text == "left\tright"
    assert reopened.export_text().endswith("left\tright")
