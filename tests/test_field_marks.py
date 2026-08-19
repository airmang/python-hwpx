# SPDX-License-Identifier: Apache-2.0
"""날짜/시간 필드·교정 부호 표시 필드·파일 이름 필드·메일머지 표시 필드
-- cycle 6.13 트레인㊻(GUI 프로브 1·3)+6.14 트레인㊽b(PATH, 실 코퍼스
계약 재사용)+메일머지 표시(GUI 프로브 gold).

계약 출처: 날짜/교정 부호는 팀장이 실한컴 macOS GUI로 직접 실행한
프로브(합성 gold, 벤더드 코퍼스 아님 -- 사설 스크래치 경로에만 존재,
이 픽스처는 그 원문에서 확인한 정확한 속성/파라미터 값을 재현한다).
파일 이름은 이미 확보돼 있던 벤더드 코퍼스 표본(``markdown_export/
99_all_in_one_stress.hwpx``)에서 그대로 가져왔다 -- GUI 프로브 불필요.
메일머지 표시는 팀장 실한컴 gold(``tests/fixtures/gui_probes/
mailmerge_display_fields.hwpx``)가 픽스처로 편입돼 있어 바이트 대조한다.
``add_hyperlink``의 3-run 격리와 달리, 네 필드 다 **단일 run 안에
ctrl/t가 나란히** 산다(모듈 독스트링 참조).
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.namespaces import HP_NS as _HP_NS

_FIXTURES = Path(__file__).parent / "fixtures" / "gui_probes"


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


def test_add_date_field_end_repeats_the_begin_fieldid() -> None:
    """실측 gold: ``hp:fieldEnd``는 ``beginIDRef``(→fieldBegin의 ``id``)
    말고도 ``fieldid``(→fieldBegin의 ``fieldid``, 같은 값)를 반복해서
    갖는다 -- 처음 구현에서 빠졌던 속성, PATH 필드 추가 중 gold와 직접
    바이트 대조하다 발견."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    result = paragraph.add_date_field("2026년 8월 11일")

    ns = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    field_begin = result.element.find(f".//{ns}fieldBegin")
    field_end = result.element.getparent().find(f"{ns}ctrl/{ns}fieldEnd")
    assert field_begin is not None and field_end is not None
    assert field_end.get("beginIDRef") == field_begin.get("id")
    assert field_end.get("fieldid") == field_begin.get("fieldid")


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


def test_add_path_field_matches_the_real_corpus_contract() -> None:
    """실 코퍼스(markdown_export/99_all_in_one_stress.hwpx)의 hp:fieldBegin
    type="PATH" 그대로 -- GUI 프로브 없이 트레인㊺가 이미 확보한 계약."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_path_field("99_all_in_one_stress.hwpx")

    xml = _section_xml(document)
    assert 'type="PATH"' in xml
    assert 'name="Prop">8<' in xml  # DATE와 같은 값 -- 교정 부호의 Prop=0과 대조
    assert 'name="Command">$F<' in xml
    assert 'name="Format">$F<' in xml
    assert "<hp:t>99_all_in_one_stress.hwpx</hp:t>" in xml
    assert 'dirty="0"' in xml


def test_add_path_field_rejects_unsupported_format() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    with pytest.raises(HwpxValueError) as excinfo:
        paragraph.add_path_field("x", path_format="full_path")
    assert excinfo.value.code == "field-path-format-unsupported"
    assert excinfo.value.context["requested"] == "full_path"
    assert excinfo.value.context["supported"] == ["filename"]


def test_add_path_field_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_path_field("99_all_in_one_stress.hwpx")

    reopened = HwpxDocument.open(document.to_bytes())

    xml = _section_xml(reopened)
    assert 'type="PATH"' in xml
    assert "<hp:t>99_all_in_one_stress.hwpx</hp:t>" in xml


def test_add_path_field_packs_begin_text_end_into_a_single_run() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    result = paragraph.add_path_field("99_all_in_one_stress.hwpx")

    run = result.element.getparent()
    children = [child.tag for child in run]
    assert children == [
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}ctrl",
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}t",
        "{http://www.hancom.co.kr/hwpml/2011/paragraph}ctrl",
    ]


def _mail_merge_field_xml(xml: str, command: str) -> str:
    """*xml*에서 *command* 필드의 ``ctrl(begin)``~끝 빈 ``hp:t``까지를 잘라
    오되, 문서마다 달라지는 id 세 개는 지운다(구조·속성·순서만 대조)."""

    start = xml.index("<hp:ctrl><hp:fieldBegin", xml.index(f'name="Command">{command}<') - 600)
    end = xml.index("<hp:t/>", start) + len("<hp:t/>")
    return re.sub(r'(?<= )(id|fieldid|beginIDRef)="\d+"', r"\1=…", xml[start:end])


def _gold_mail_merge_field_xml(command: str) -> str:
    with zipfile.ZipFile(_FIXTURES / "mailmerge_display_fields.hwpx") as archive:
        return _mail_merge_field_xml(
            archive.read("Contents/section0.xml").decode("utf-8"), command
        )


def test_add_mail_merge_field_matches_the_real_gold_contract() -> None:
    """실측 gold("도구 > 메일 머지 > 메일 머지 표시 달기") 그대로 --
    파라미터 5개의 이름·타입·순서, 끝에 붙는 빈 ``hp:t``까지."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("Name: ")

    paragraph.add_mail_merge_field("name")

    emitted = _section_xml(document)
    assert _mail_merge_field_xml(emitted, "name") == _gold_mail_merge_field_xml("name")


def test_add_mail_merge_field_keeps_the_official_typo_parameter_name() -> None:
    """``Fiexde``는 실물·한컴 공식 문서 공통의 오타 철자다 -- 고쳐 쓰면
    실한컴이 파라미터를 못 찾는다(``trackchageConfig``·``NOMAL`` 전례)."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_mail_merge_field("name")

    xml = _section_xml(document)
    assert '<hp:booleanParam name="Fiexde">1</hp:booleanParam>' in xml
    assert "Fixed" not in xml


def test_add_mail_merge_field_omits_the_meta_tag_attribute() -> None:
    """MAILMERGE gold에는 ``metaTag``가 없다 -- DATE/교정 부호/PATH gold는
    셋 다 ``metaTag=""``를 달고 있는 것과 대조."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    result = paragraph.add_mail_merge_field("name")

    field_begin = result.element.find(f"{{{_HP_NS}}}fieldBegin")
    assert field_begin is not None
    assert "metaTag" not in field_begin.attrib
    assert field_begin.get("type") == "MAILMERGE"


def test_add_mail_merge_field_caches_the_placeholder_the_batch_merger_reads() -> None:
    """캐시 텍스트 기본값은 ``{{이름}}`` -- ``hwpx.tools.mail_merge``가
    치환 대상으로 인식하는 문법이라, 이 필드로 저작한 템플릿이 그 배치
    생성기에 그대로 물린다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_mail_merge_field("address")

    assert "<hp:t>{{address}}</hp:t>" in _section_xml(document)


def test_add_mail_merge_field_accepts_an_explicit_cached_text() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    paragraph.add_mail_merge_field("name", cached_text="홍길동")

    xml = _section_xml(document)
    assert "<hp:t>홍길동</hp:t>" in xml
    assert 'name="Command">name<' in xml  # 캐시 텍스트는 필드 이름을 안 건드린다


def test_add_mail_merge_field_rejects_an_empty_name() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)

    with pytest.raises(HwpxValueError) as excinfo:
        paragraph.add_mail_merge_field("")
    assert excinfo.value.code == "field-mail-merge-empty-name"


def test_add_mail_merge_field_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("", include_run=False)
    paragraph.add_mail_merge_field("name")

    reopened = HwpxDocument.open(document.to_bytes())

    xml = _section_xml(reopened)
    assert 'type="MAILMERGE"' in xml
    assert '<hp:stringParam name="FieldType">USER_DEFINE</hp:stringParam>' in xml
    assert "<hp:t>{{name}}</hp:t>" in xml


def test_real_gold_mail_merge_fixture_round_trips_verbatim() -> None:
    """실한컴 gold를 열어 저장해도 두 필드가 무손실로 보존된다."""

    document = HwpxDocument.open(_FIXTURES / "mailmerge_display_fields.hwpx")
    try:
        xml = _section_xml(document)
    finally:
        document.close()

    for command in ("name", "address"):
        assert _mail_merge_field_xml(xml, command) == _gold_mail_merge_field_xml(command)
