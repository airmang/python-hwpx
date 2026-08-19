# SPDX-License-Identifier: Apache-2.0
"""``hp:indexmark`` 저작(``add_index_mark``) -- "색인 표시".

계약 출처: 팀장의 실한컴(HWP 13.0.0.3901) GUI 프로브 gold 2건
(``tests/fixtures/gui_probes/index_mark_{first_only,two_keys}.hwpx``).
타겟팅은 ``add_title_mark``와 같은 "호출자가 대상 문단을 직접 지정"이나,
배치는 다르다 -- titleMark는 ``hp:t`` **안**에, indexmark는 같은 run 안의
``hp:ctrl`` 형제로 텍스트 **앞**에 선다.

스키마(``ParaList XML schema.xml:209-216``)는 ``firstKey``/``secondKey``를
둘 다 필수 시퀀스로 선언하지만 실물은 1단계 색인에서 ``secondKey``를
아예 생략한다 -- 아래 첫 두 테스트가 그 차이를 gold와 직접 대조한다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxStateError, HwpxValueError

_FIXTURES = Path(__file__).parent / "fixtures" / "gui_probes"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _gold_index_mark_xml(fixture_name: str) -> str:
    """gold의 ``hp:ctrl``(indexmark를 감싼 것)만 잘라 온다."""

    with zipfile.ZipFile(_FIXTURES / fixture_name) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    start = xml.index("<hp:ctrl><hp:indexmark>")
    return xml[start : xml.index("</hp:ctrl>", start) + len("</hp:ctrl>")]


def test_add_index_mark_first_key_only_matches_the_gold_verbatim() -> None:
    """실측(``index_mark_first_only.hwpx``): 1단계 키만 주면 ``secondKey``를
    방출하지 않는다 -- 스키마는 필수라고 선언하지만 실물이 생략한다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("apple item paragraph.")

    paragraph.add_index_mark("apple")

    xml = _section_xml(document)
    assert _gold_index_mark_xml("index_mark_first_only.hwpx") in xml
    assert "secondKey" not in xml


def test_add_index_mark_two_keys_matches_the_gold_verbatim() -> None:
    """실측(``index_mark_two_keys.hwpx``): 2단계 키는 ``firstKey`` 뒤
    형제로 붙는다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("banana item paragraph.")

    paragraph.add_index_mark("fruit", second="banana")

    assert _gold_index_mark_xml("index_mark_two_keys.hwpx") in _section_xml(document)


def test_add_index_mark_sits_in_the_text_run_ahead_of_the_text() -> None:
    """gold 배치 계약: 새 run을 만들지 않고 텍스트 run 안으로 들어가며,
    ``hp:ctrl``이 ``hp:t`` 앞에 온다(``add_title_mark``가 ``hp:t`` 안으로
    들어가는 것과 대조)."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("apple item paragraph.")

    result = paragraph.add_index_mark("apple")

    run = result.element.getparent()
    assert [child.tag for child in run] == [f"{_HP}ctrl", f"{_HP}t"]
    assert len(paragraph.element.findall(f"{_HP}run")) == 1


def test_add_index_mark_targets_whichever_paragraph_is_given() -> None:
    """``add_title_mark``와 같은 타겟팅 계약 -- 항상 첫 문단이 아니다."""

    document = HwpxDocument.new()
    document.add_paragraph("apple item paragraph.")
    second = document.add_paragraph("banana item paragraph.")

    second.add_index_mark("banana")

    xml = _section_xml(document)
    assert (
        "<hp:ctrl><hp:indexmark><hp:firstKey>banana</hp:firstKey></hp:indexmark></hp:ctrl>"
        "<hp:t>banana item paragraph.</hp:t>"
    ) in xml
    assert "<hp:t>apple item paragraph.</hp:t>" in xml  # 대상 오귀속 없음


@pytest.mark.parametrize(
    ("kwargs", "key_label"),
    [({"first": ""}, "first"), ({"first": "fruit", "second": ""}, "second")],
)
def test_add_index_mark_rejects_empty_keys(kwargs: dict[str, str], key_label: str) -> None:
    """빈 문자열은 생략과 다른 XML을 만든다(``<hp:secondKey/>`` vs 요소
    자체 없음) -- 어느 쪽을 뜻하는지 추측하지 않고 거부한다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("apple item paragraph.")

    with pytest.raises(HwpxValueError) as excinfo:
        paragraph.add_index_mark(**kwargs)
    assert excinfo.value.code == "paragraph-index-mark-empty-key"
    assert excinfo.value.context["key"] == key_label


def test_add_index_mark_rejects_a_paragraph_with_no_text_run() -> None:
    document = HwpxDocument.new()
    paragraph = document._root.sections[0].add_paragraph("", include_run=False)

    with pytest.raises(HwpxStateError) as excinfo:
        paragraph.add_index_mark("apple")
    assert excinfo.value.code == "paragraph-index-mark-no-text-run"


def test_add_index_mark_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("banana item paragraph.")
    paragraph.add_index_mark("fruit", second="banana")

    reopened = HwpxDocument.open(document.to_bytes())

    assert _gold_index_mark_xml("index_mark_two_keys.hwpx") in _section_xml(reopened)


@pytest.mark.parametrize(
    ("fixture_name", "expected_keys"),
    [
        ("index_mark_first_only.hwpx", ["apple"]),
        ("index_mark_two_keys.hwpx", ["fruit", "banana"]),
    ],
)
def test_real_gold_fixtures_open_and_round_trip_the_indexmark_verbatim(
    fixture_name: str, expected_keys: list[str]
) -> None:
    """실한컴 gold를 이 라이브러리로 열어 저장해도 indexmark가 무손실로
    보존된다(전용 읽기 모델은 없음 -- GenericElement 불투명 보존 경로)."""

    document = HwpxDocument.open(_FIXTURES / fixture_name)
    try:
        xml = _section_xml(document)
    finally:
        document.close()

    assert _gold_index_mark_xml(fixture_name) in xml
    marks = [key for key in expected_keys if f">{key}<" in xml]
    assert marks == expected_keys
