# SPDX-License-Identifier: Apache-2.0
"""바탕쪽(masterPage) 저작 -- cycle 6.13 트레인㊻, 갭#8(마지막).

읽기 모델(``oxml/master_page.py``, ``tests/test_part_hierarchy_read_
models.py``)은 이미 있었으나 쓰기 경로가 없었다 -- ``HwpxOxmlMasterPage``
자신의 독스트링이 "읽기 전용... 쓰기 경로는 열지 않는다"고 명시했다
(6.4 트레인⑮의 의도적 스코프 축소). 이 파일이 그 쓰기 경로를 검증한다.

유일한 실 예시(``error__20250808__...hwpx``)에서 확인된 계약: 파트
파일명·매니페스트 ``opf:item id``·``masterPage`` 루트 자신의 ``id``·절의
``hp:masterPage/@idRef`` 넷 다 같은 문자열("masterpage0")을 쓴다.
``hp:secPr``의 자식 시퀀스에서 ``hp:masterPage``는 맨 끝에 온다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

REPO = Path(__file__).resolve().parent.parent
MASTERPAGE_FIXTURE = (
    REPO
    / "tests"
    / "fixtures"
    / "hwpxlib_corpus"
    / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
)

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_OPF_NS = "http://www.idpf.org/2007/opf/"


def test_add_master_page_creates_a_part_and_registers_it_in_the_manifest() -> None:
    document = HwpxDocument.new()

    master_page_id = document.parts.add_master_page(text="회사명")

    assert master_page_id == "masterpage0"
    parts = document.parts.master_pages
    assert len(parts) == 1
    assert parts[0].part_name == "Contents/masterpage0.xml"

    model = parts[0].to_model()
    assert model.id == "masterpage0"
    assert model.paragraph_texts == ("회사명",)

    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        manifest = archive.read("Contents/content.hpf")
        assert b'id="masterpage0"' in manifest
        assert b'href="Contents/masterpage0.xml"' in manifest
        # master pages are not reading-order parts -- no spine itemref.
        assert b'idref="masterpage0"' not in manifest


def test_add_master_page_supports_multiple_paragraphs_and_type_flags() -> None:
    document = HwpxDocument.new()

    master_page_id = document.parts.add_master_page(
        paragraphs=["회사명", "기밀문서"],
        page_type="EVEN",
        page_number=3,
        page_duplicate=True,
        page_front=True,
    )

    model = document.parts.master_pages[0].to_model()
    assert master_page_id == "masterpage0"
    assert model.type == "EVEN"
    assert model.page_number == 3
    assert model.page_duplicate is True
    assert model.page_front is True
    assert model.paragraph_texts == ("회사명", "기밀문서")


def test_add_master_page_rejects_unsupported_type() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as excinfo:
        document.parts.add_master_page(page_type="BOGUS")
    assert excinfo.value.code == "master-page-type-unsupported"
    assert excinfo.value.context["requested"] == "BOGUS"


def test_add_master_page_twice_increments_the_part_index() -> None:
    document = HwpxDocument.new()

    first = document.parts.add_master_page(text="첫째")
    second = document.parts.add_master_page(text="둘째")

    assert (first, second) == ("masterpage0", "masterpage1")
    assert {mp.part_name for mp in document.parts.master_pages} == {
        "Contents/masterpage0.xml",
        "Contents/masterpage1.xml",
    }


def test_set_master_page_wires_the_section_reference() -> None:
    document = HwpxDocument.new()
    master_page_id = document.parts.add_master_page(text="회사명")

    assert document.page.master_page_refs(section=0) == ()

    document.page.set_master_page(master_page_id, section=0)

    assert document.page.master_page_refs(section=0) == ("masterpage0",)
    secpr = document._root.sections[0].element.find(f".//{_HP}secPr")
    assert secpr is not None
    assert secpr.get("masterPageCnt") == "1"
    # real sample: hp:masterPage is the last child of hp:secPr.
    assert [child.tag for child in secpr][-1] == f"{_HP}masterPage"


def test_set_master_page_is_idempotent() -> None:
    document = HwpxDocument.new()
    master_page_id = document.parts.add_master_page(text="회사명")

    document.page.set_master_page(master_page_id, section=0)
    document.page.set_master_page(master_page_id, section=0)

    assert document.page.master_page_refs(section=0) == ("masterpage0",)
    secpr = document._root.sections[0].element.find(f".//{_HP}secPr")
    assert secpr is not None and secpr.get("masterPageCnt") == "1"


def test_master_page_and_section_reference_round_trip_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    master_page_id = document.parts.add_master_page(
        paragraphs=["회사명", "기밀문서"], page_type="ODD",
    )
    document.page.set_master_page(master_page_id, section=0)

    reopened = HwpxDocument.open(document.to_bytes())

    assert len(reopened.parts.master_pages) == 1
    model = reopened.parts.master_pages[0].to_model()
    assert model.id == "masterpage0"
    assert model.type == "ODD"
    assert model.paragraph_texts == ("회사명", "기밀문서")
    assert reopened.page.master_page_refs(section=0) == ("masterpage0",)


def test_real_corpus_master_page_sample_still_parses_and_round_trips() -> None:
    """소스오브트루스 실 픽스처 자체가 여전히 정상 파싱·왕복되는지 -- 이
    트레인의 신규 쓰기 경로가 기존 읽기 경로를 건드리지 않았음을 재확인."""

    if not MASTERPAGE_FIXTURE.exists():
        pytest.skip(f"{MASTERPAGE_FIXTURE.name} not present in this checkout")

    document = HwpxDocument.open(str(MASTERPAGE_FIXTURE))
    try:
        parts = document.parts.master_pages
        assert len(parts) == 1
        model = parts[0].to_model()
        assert model.id == "masterpage0"

        for section in document.sections:
            secpr = section.element.find(f".//{_HP}secPr")
            if secpr is None:
                continue
            refs = [c.get("idRef") for c in secpr if c.tag == f"{_HP}masterPage"]
            if refs:
                assert refs == ["masterpage0"]
                assert secpr.get("masterPageCnt") == str(len(refs))
    finally:
        document.close()
