# SPDX-License-Identifier: Apache-2.0
"""`section_index=` 별칭은 7.0부터 경고를 내고 8.0에서 사라진다.

6.x 문서는 "7.0에서 제거"라고 적었지만 6.x 동안 경고를 한 번도 내지 않았다.
경고 없이 바로 지우면 문서를 따라 쓴 사용자만 깨지므로, 7.0은 경고를 내기
시작하고 제거는 한 major 미룬다.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx._document._resolve import SECTION_INDEX_REMOVED_IN


def _section_index_warnings(record: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [
        item
        for item in record
        if issubclass(item.category, DeprecationWarning) and "section_index=" in str(item.message)
    ]


def test_removal_major_is_8_0() -> None:
    assert SECTION_INDEX_REMOVED_IN == "8.0"


@pytest.mark.parametrize(
    "call",
    [
        lambda doc: doc.add_paragraph("본문", section_index=0),
        lambda doc: doc.page.set_header(text="머리말", section_index=0),
        lambda doc: doc.notes.add_memo("메모", section_index=0),
        lambda doc: doc.shapes.add_rectangle(7200, 3600, section_index=0),
    ],
    ids=["add_paragraph", "page.set_header", "notes.add_memo", "shapes.add_rectangle"],
)
def test_section_index_warns_and_still_works(call) -> None:
    document = HwpxDocument.new()
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        result = call(document)
    assert result is not None
    found = _section_index_warnings(record)
    assert found, "section_index= 는 DeprecationWarning 을 내야 한다"
    message = str(found[0].message)
    assert "8.0" in message
    assert "section=" in message
    # 경고는 라이브러리 안쪽이 아니라 호출한 이 파일의 줄을 가리킨다.
    assert Path(found[0].filename).resolve() == Path(__file__).resolve()


def test_section_keyword_does_not_warn() -> None:
    document = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        document.add_paragraph("본문", section=0)
        document.page.set_header(text="머리말", section=0)
        document.notes.add_memo("메모", section=document.sections[0])
        document.add_paragraph("마지막 구역에")
        document.page.setup(paper_size="A4")


def test_fields_fill_does_not_warn_on_its_own() -> None:
    # 라이브러리 안에서 섹션 번호를 넘기는 경로가 사용자에게 경고를 떠넘기지 않는다.
    document = HwpxDocument.new()
    document.add_paragraph("이름: ")
    document.fields.add("name", prompt="이름")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        document.fields.fill("홍길동", name="name")
        document.fields.all
