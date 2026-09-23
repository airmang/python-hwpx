# SPDX-License-Identifier: Apache-2.0
"""Text that follows an inline element inside ``hp:t`` is part of the paragraph.

Hancom writes tabs, line breaks and special spaces *inside* ``hp:t`` as mixed
content (``<hp:t>성<hp:fwSpace/>명<hp:tab/>홍길동</hp:t>``). Readers that took
only ``hp:t``'s own text returned "성" and lost the rest.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.tools.markdown_export import export_markdown
from hwpx.tools.text_extractor import TextExtractor

HANCOM_T = (
    '<hp:t>성<hp:fwSpace/>명<hp:tab width="4000" leader="0" type="1"/>홍길동<hp:lineBreak/>'
    '둘째 줄<hp:markpenBegin color="#FFFF00"/>강조<hp:markpenEnd/>끝<hp:nbSpace/>.</hp:t>'
)
EXPECTED = "성　명\t홍길동\n둘째 줄강조끝 ."


def _document_with(t_xml: str, *, in_table: bool = False) -> HwpxDocument:
    doc = HwpxDocument.new()
    if in_table:
        doc.add_table(1, 2).set_cell_text(0, 0, "PLACEHOLDER")
    else:
        doc.add_paragraph("PLACEHOLDER")
    source = io.BytesIO(doc.to_bytes())
    out = io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                data = data.decode("utf-8").replace("<hp:t>PLACEHOLDER</hp:t>", t_xml).encode("utf-8")
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return HwpxDocument.open(io.BytesIO(out.getvalue()))


def test_paragraph_text_keeps_text_after_inline_elements() -> None:
    doc = _document_with(HANCOM_T)
    assert doc.paragraphs[-1].text == EXPECTED


def test_an_element_child_with_its_own_text_keeps_that_text() -> None:
    # Children other than the character atoms (tab, lineBreak, spaces, hyphen)
    # contribute their own text, the way ``run.text`` always read them.
    doc = _document_with('<hp:t>앞<hp:tag name="token">가운데</hp:tag>뒤</hp:t>')
    assert doc.paragraphs[-1].text == "앞가운데뒤"
    assert doc.paragraphs[-1].runs[-1].text == "앞가운데뒤"


def test_run_text_reads_inline_elements_like_the_paragraph() -> None:
    doc = _document_with(HANCOM_T)
    run = doc.paragraphs[-1].runs[-1]
    assert run.text == EXPECTED


def test_plain_text_export_keeps_text_after_inline_elements() -> None:
    doc = _document_with(HANCOM_T)
    assert EXPECTED in doc.text.plain()


def test_plain_text_export_reads_table_cells_the_same_way() -> None:
    doc = _document_with(HANCOM_T, in_table=True)
    assert "홍길동" in doc.text.plain()
    assert "둘째 줄강조끝" in doc.text.plain()


def test_markdown_export_keeps_text_after_inline_elements() -> None:
    markdown = export_markdown(_document_with(HANCOM_T))
    for piece in ("명", "홍길동", "둘째 줄", "강조끝"):
        assert piece in markdown


@pytest.mark.parametrize("preserve_breaks, tab", [(True, "\t"), (False, " ")])
def test_text_extractor_reads_a_tab_inside_hp_t(preserve_breaks: bool, tab: str) -> None:
    doc = _document_with(HANCOM_T)
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive, TextExtractor(archive) as extractor:
        texts = [p.text(preserve_breaks=preserve_breaks) for p in extractor.iter_document_paragraphs()]
    assert any(f"명{tab}홍길동" in text for text in texts)


def test_a_spaced_form_label_is_found_by_its_letters() -> None:
    # Korean forms spread short labels with full-width spaces: "성<hp:fwSpace/>명".
    doc = _document_with('<hp:t>성<hp:fwSpace/>명</hp:t>', in_table=True)
    result = doc.tables.find_cell_by_label("성 명")
    assert result["count"] >= 1
