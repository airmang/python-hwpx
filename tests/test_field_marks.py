# SPDX-License-Identifier: Apache-2.0
"""날짜/시간 필드·교정 부호 표시 필드 -- cycle 6.13 트레인㊻, GUI 프로브 1·3.

계약 출처: 팀장이 실한컴 macOS GUI로 직접 실행한 프로브(합성 gold,
벤더드 코퍼스 아님 -- 사설 스크래치 경로에만 존재, 이 픽스처는 그
원문에서 확인한 정확한 속성/파라미터 값을 재현한다). ``add_hyperlink``의
3-run 격리와 달리, 두 필드 다 **단일 run 안에 ctrl/t가 나란히** 산다
(모듈 독스트링 참조).
"""
from __future__ import annotations

import io
import zipfile

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def test_add_date_field_matches_the_real_gold_contract() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_date_field("2026년 8월 11일")

    xml = _section_xml(document)
    assert 'type="DATE"' in xml
    assert 'name="Prop">8<' in xml
    assert 'name="Command">:1년 2월 3일<' in xml  # 실측 미리보기 문자열, 포맷코드 아님
    assert 'name="DateNation">KOR<' in xml
    assert 'name="DateFormat">YYYY년 M월 D일<' in xml
    assert "<hp:t>2026년 8월 11일</hp:t>" in xml
    assert 'dirty="0"' in xml  # TOC와 달리 재계산 트리거 아님(실측)


def test_add_date_field_id_and_fieldid_are_independent_random_values() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    result = paragraph.add_date_field("2026년 8월 11일")

    field_begin = result.element.find(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}fieldBegin")
    assert field_begin is not None
    assert field_begin.get("id") != field_begin.get("fieldid")


def test_add_date_field_rejects_unsupported_format() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    with pytest.raises(HwpxValueError) as excinfo:
        paragraph.add_date_field("x", date_format="MM/DD/YYYY")
    assert excinfo.value.code == "field-date-format-unsupported"
    assert excinfo.value.context["requested"] == "MM/DD/YYYY"


def test_add_date_field_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_date_field("2026년 8월 11일")

    reopened = HwpxDocument.open(document.to_bytes())

    xml = _section_xml(reopened)
    assert 'type="DATE"' in xml
    assert "<hp:t>2026년 8월 11일</hp:t>" in xml


def test_add_proofreading_mark_matches_the_real_gold_contract() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_proofreading_mark("space")

    xml = _section_xml(document)
    assert 'type="PROOFREADING_MARKS_SIGN"' in xml  # 스키마는 PROOFREADING_MARKS라고 선언(DEV-043)
    assert 'name="Prop">0<' in xml
    assert 'name="Command">$RevisionSign;1;<' in xml


def test_add_proofreading_mark_rejects_unconfirmed_marks() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    with pytest.raises(HwpxValueError) as excinfo:
        paragraph.add_proofreading_mark("insertion_sign")
    assert excinfo.value.code == "field-proofreading-mark-unsupported"
    assert excinfo.value.context["requested"] == "insertion_sign"
    assert excinfo.value.context["supported"] == ["space"]


def test_add_proofreading_mark_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_proofreading_mark("space")

    reopened = HwpxDocument.open(document.to_bytes())

    xml = _section_xml(reopened)
    assert 'type="PROOFREADING_MARKS_SIGN"' in xml
    assert "RevisionSign;1;" in xml


def test_both_fields_pack_their_own_begin_text_end_into_a_single_run() -> None:
    """하이퍼링크의 3-run 격리와 달리, 실측 gold는 ctrl/t를 한 run 안에
    나란히 담는다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    date_result = paragraph.add_date_field("2026년 8월 11일")

    run = date_result.element.getparent()
    children = [child.tag for child in run]
    assert children == [
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}ctrl",
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}t",
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}ctrl",
    ]
