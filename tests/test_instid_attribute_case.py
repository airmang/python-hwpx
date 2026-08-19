# SPDX-License-Identifier: Apache-2.0
"""instid 속성명 대소문자 회귀 (#88).

OWPML 스키마·실한컴 산출물의 인스턴스 ID 속성명은 소문자 ``instid``다
(픽스처 전수 재집계 instid 744 / instId 0). 과거 코드가 4곳에서 카멜케이스
``instId``를 읽거나 써서: ① 문단 복제 재발급 분기가 사문화(중복 instid 복제),
② 각주/미주 저작이 스키마에 없는 속성명을 방출, ③ 리더가 실한컴 파일에서
항상 None을 봤다. 수리 계약: 쓰기는 ``instid``, 읽기는 ``instid`` 우선 +
과거 자사 산출물(``instId``) 폴백, 복제 재발급은 양쪽 속성명 모두 값 재발급
(속성명 자체는 보존 — 바이트 보수).
"""
from __future__ import annotations

import re

from hwpx import HwpxDocument
from hwpx.oxml._document_primitives import _clone_paragraph_element
from hwpx.oxml.memo import HwpxOxmlNote
from hwpx.tools.markdown_export import export_markdown

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _footnote_elements(document: HwpxDocument):
    for paragraph in document.paragraphs:
        for element in paragraph.element.iter():
            if element.tag == f"{HP}footNote":
                yield element


def test_footnote_authoring_emits_schema_case_instid() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")

    notes = list(_footnote_elements(document))
    assert notes, "각주가 저작되지 않았다"
    for note in notes:
        assert note.get("instid"), "스키마 정본 속성명 instid가 없다"
        assert note.get("instId") is None, "카멜케이스 instId를 다시 방출했다"

    data = document.to_bytes()
    assert b'instId="' not in data


def test_clone_reissues_schema_case_instid() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")
    source = paragraph.element
    original = next(iter(_footnote_elements(document))).get("instid")
    assert original

    cloned = _clone_paragraph_element(source)
    cloned_note = next(
        el for el in cloned.iter() if el.tag == f"{HP}footNote"
    )
    assert cloned_note.get("instid"), "복제본에서 instid가 사라졌다"
    assert cloned_note.get("instid") != original, "복제본 instid가 재발급되지 않았다 (중복 인스턴스 ID)"


def test_clone_reissues_legacy_camelcase_value_but_keeps_name() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    paragraph.element.append(run)
    legacy = run.makeelement(f"{HP}footNote", {"instId": "9999"})
    run.append(legacy)

    cloned = _clone_paragraph_element(paragraph.element)
    cloned_note = next(el for el in cloned.iter() if el.tag == f"{HP}footNote")
    assert cloned_note.get("instId") not in (None, "9999"), "과거 자사 산출물의 instId도 값 재발급 대상"
    assert cloned_note.get("instid") is None, "속성명은 보존한다 (바이트 보수)"


def test_note_reader_prefers_schema_case_with_legacy_fallback() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    element = paragraph.element.makeelement(f"{HP}footNote", {"instid": "11"})
    assert HwpxOxmlNote(element, paragraph).inst_id == "11"

    legacy = paragraph.element.makeelement(f"{HP}footNote", {"instId": "22"})
    assert HwpxOxmlNote(legacy, paragraph).inst_id == "22"

    both = paragraph.element.makeelement(
        f"{HP}footNote", {"instid": "11", "instId": "22"}
    )
    assert HwpxOxmlNote(both, paragraph).inst_id == "11"


def test_markdown_note_marker_carries_authored_instid() -> None:
    """저작(쓰기)과 export(읽기)가 같은 속성명으로 만나야 마커에 ID가 실린다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    paragraph.add_footnote("각주 본문")

    markdown = export_markdown(HwpxDocument.open(document.to_bytes()))
    match = re.search(r"\[\^fn(\d+)\]", markdown)
    assert match, f"각주 마커에 instid가 비었다: {markdown!r}"
