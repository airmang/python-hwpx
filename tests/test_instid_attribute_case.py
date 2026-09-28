# SPDX-License-Identifier: Apache-2.0
"""인스턴스 ID 속성명의 대소문자.

개체(그림·도형·표 등, ``AbstractShapeObjectType``)의 속성명은 소문자 ``instid``이고,
각주·미주(``NoteType``)는 ``instId``다. 스키마가 그렇게 선언하고, 한/글이 저장한
각주·미주도 ``instId``다. 6.6 이하 python-hwpx는 각주·미주에도 ``instid``를 썼다.
계약: 각주·미주는 ``instId``로 쓰고, 읽기는 ``instId`` 먼저, ``instid``는 옛 산출물
폴백. 문단 복제는 어느 철자든 값만 재발급하고 속성명은 그대로 둔다.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.oxml._document_primitives import _clone_paragraph_element
from hwpx.oxml.memo import HwpxOxmlNote
from hwpx.tools.markdown_export import export_markdown

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _note_elements(document: HwpxDocument, tag: str = "footNote"):
    for paragraph in document.paragraphs:
        for element in paragraph.element.iter():
            if element.tag == f"{HP}{tag}":
                yield element


def test_note_authoring_writes_inst_id_as_the_schema_and_hancom_do() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")
    paragraph.add_endnote("미주 본문")

    for tag in ("footNote", "endNote"):
        notes = list(_note_elements(document, tag))
        assert notes, f"{tag}가 저작되지 않았다"
        for note in notes:
            assert note.get("instId"), f"{tag}에 instId가 없다"
            assert note.get("instid") is None, f"{tag}에 개체 철자 instid를 썼다"

    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        section = archive.read("Contents/section0.xml")
    assert section.count(b'instId="') == 2 and b"instid=" not in section


def test_note_inst_id_survives_an_hwp_save() -> None:
    # The HWP writer takes a note's instance id from instId; a lowercase instid became 0.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")
    authored = next(iter(_note_elements(document))).get("instId")

    reopened = HwpxDocument.open(document.to_bytes(format="hwp"))
    [note] = reopened.sections[0].element.iter(f"{HP}footNote")
    assert note.get("instId") == authored


def test_hancom_writes_a_note_inst_id_as_inst_id() -> None:
    # Hancom saved a document python-hwpx wrote with a lowercase instid on its
    # footnote and endnote: it dropped instid and wrote instId.
    data = (Path(__file__).parent / "fixtures" / "hancom_saved" / "notes_inst_id.hwpx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        section = archive.read("Contents/section0.xml")
    notes = re.findall(rb"<hp:(?:footNote|endNote)\b[^>]*>", section)
    assert len(notes) == 2
    assert all(b'instId="' in note and b"instid=" not in note for note in notes)

    document = HwpxDocument.open(data)
    [footnote] = document.sections[0].element.iter(f"{HP}footNote")
    assert HwpxOxmlNote(footnote, document.paragraphs[0]).inst_id == footnote.get("instId")


def test_clone_reissues_the_note_inst_id() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")
    original = next(iter(_note_elements(document))).get("instId")
    assert original

    cloned = _clone_paragraph_element(paragraph.element)
    cloned_note = next(el for el in cloned.iter() if el.tag == f"{HP}footNote")
    assert cloned_note.get("instId"), "복제본에서 instId가 사라졌다"
    assert cloned_note.get("instId") != original, "복제본 instId가 재발급되지 않았다 (중복 인스턴스 ID)"


def test_clone_reissues_an_old_lowercase_note_value_but_keeps_its_name() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    paragraph.element.append(run)
    old = run.makeelement(f"{HP}footNote", {"instid": "9999"})
    run.append(old)

    cloned = _clone_paragraph_element(paragraph.element)
    cloned_note = next(el for el in cloned.iter() if el.tag == f"{HP}footNote")
    assert cloned_note.get("instid") not in (None, "9999"), "옛 산출물의 instid도 값 재발급 대상"
    assert cloned_note.get("instId") is None, "속성명은 그대로 둔다"


def test_note_reader_prefers_inst_id_with_the_old_lowercase_fallback() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    element = paragraph.element.makeelement(f"{HP}footNote", {"instId": "11"})
    assert HwpxOxmlNote(element, paragraph).inst_id == "11"

    old = paragraph.element.makeelement(f"{HP}footNote", {"instid": "22"})
    assert HwpxOxmlNote(old, paragraph).inst_id == "22"

    both = paragraph.element.makeelement(f"{HP}footNote", {"instId": "11", "instid": "22"})
    assert HwpxOxmlNote(both, paragraph).inst_id == "11"


def test_markdown_note_marker_carries_the_authored_inst_id() -> None:
    """저작(쓰기)과 export(읽기)가 같은 속성명으로 만나야 마커에 ID가 실린다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")

    markdown = export_markdown(HwpxDocument.open(document.to_bytes()))
    match = re.search(r"\[\^fn(\d+)\]", markdown)
    assert match, f"각주 마커에 instId가 비었다: {markdown!r}"
