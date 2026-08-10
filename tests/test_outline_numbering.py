# SPDX-License-Identifier: Apache-2.0
"""개요 3종(번호 모양·적용/해제·수준 증감) -- cycle 6.13 트레인㊻.

편집기 메뉴 표면 역매핑(트레인㊷)이 [부분 대응]으로 분류한 이유:
``hh:heading type="OUTLINE"``이 목록 서식(bullet/number)과 **같은**
``hh:numbering``/``hh:paraHead`` id-space를 쓰는데(``bind_outline_level``,
``_document/headings.py``), v14의 ``authored-listformat`` 배치는
``kind="bullet"``/``"number"``만 회전시켰을 뿐 ``"outline"`` 자체는
독립적으로 실증되지 않았다.

실측: 개요 적용/해제(``apply_paragraph_format(outline_level=)``)와 수준
증감(같은 API 재호출)은 코드가 **이미** 완비돼 있었다 -- 이 트레인이
새로 연 건 번호 *모양*(개요 numbering 정의 자체의 numFormat/start
커스터마이즈) 하나뿐이다. ``ensure_numbering``에 ``"outline"`` 분기를
추가했고, ``apply_list_format``의 나머지 파이프라인은 kind-무관이라
그대로 재사용된다(신규 오케스트레이션 코드 없음).

실코퍼스 67파일 전수: `hh:heading type="OUTLINE"` 451건 전부
``idRef="0"``(스켈레톤 고정 개요 스타일) -- 커스텀 idRef 조합은 실증
밖이라 v17 배치 대기(Create(experimental)).
"""
from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument


def test_apply_list_format_outline_creates_a_custom_numbering_definition() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 번째 개요 제목")

    result = document.styles.apply_list_format(
        paragraph_index=0, kind="outline", level=1, number_format="DIGIT", start=5,
    )

    assert result.kind == "outline"
    paragraph = document.sections[0].paragraphs[0]
    heading = document.oxml.paragraph_property(paragraph.para_pr_id_ref).heading
    assert heading is not None
    assert heading.type == "OUTLINE"
    # a genuinely custom numbering id, not the skeleton's fixed "0".
    assert str(heading.id_ref) != "0"


def test_apply_list_format_outline_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("제목")
    document.styles.apply_list_format(
        paragraph_index=0, kind="outline", level=1, number_format="HANGUL",
    )
    before = document.oxml.paragraph_property(
        document.sections[0].paragraphs[0].para_pr_id_ref
    ).heading

    reopened = HwpxDocument.open(document.to_bytes())
    after = reopened.oxml.paragraph_property(
        reopened.sections[0].paragraphs[0].para_pr_id_ref
    ).heading

    assert before is not None and after is not None
    assert (after.type, after.id_ref, after.level) == (before.type, before.id_ref, before.level)


def test_ensure_numbering_rejects_unknown_kind_naming_all_three_valid_ones() -> None:
    document = HwpxDocument.new()
    with pytest.raises(ValueError, match="bullet.*number.*outline"):
        document.styles.ensure_numbering(kind="bogus")


def test_ensure_numbering_bullet_and_number_still_work_after_outline_addition() -> None:
    document = HwpxDocument.new()
    bullet_refs = document.styles.ensure_numbering(kind="bullet", levels=[{"char": "◆"}])
    number_refs = document.styles.ensure_numbering(kind="number", levels=[{"format": "DIGIT"}])
    assert bullet_refs and number_refs


# --------------------------------------------------------------------------
# 개요 적용/해제 · 한 수준 증가/감소 -- 이미 있던 API의 재확인(코드 변경 없음,
# apply_list_format(kind="outline")과 같은 hh:numbering id-space를 공유한다
# 는 사실만 새로 확인됐다).


def test_add_heading_applies_an_outline_level() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_heading("제목", level=2)

    heading = document.oxml.paragraph_property(paragraph.para_pr_id_ref).heading
    assert heading is not None
    assert heading.type == "OUTLINE"
    assert str(heading.level) == "1"


def test_apply_paragraph_format_increases_and_decreases_outline_level() -> None:
    document = HwpxDocument.new()
    document.add_heading("제목", level=2)

    document.styles.apply_paragraph_format(paragraph_index=0, outline_level=3)
    increased = document.oxml.paragraph_property(
        document.sections[0].paragraphs[0].para_pr_id_ref
    ).heading
    assert increased is not None and str(increased.level) == "2"

    document.styles.apply_paragraph_format(paragraph_index=0, outline_level=1)
    decreased = document.oxml.paragraph_property(
        document.sections[0].paragraphs[0].para_pr_id_ref
    ).heading
    assert decreased is not None and str(decreased.level) == "0"


def test_apply_paragraph_format_outline_level_zero_removes_the_heading() -> None:
    document = HwpxDocument.new()
    document.add_heading("제목", level=1)

    document.styles.apply_paragraph_format(paragraph_index=0, outline_level=0)

    heading = document.oxml.paragraph_property(
        document.sections[0].paragraphs[0].para_pr_id_ref
    ).heading
    assert heading is not None and heading.type == "NONE"
