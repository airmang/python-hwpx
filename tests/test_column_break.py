# SPDX-License-Identifier: Apache-2.0
"""단 나누기(columnBreak) 저작 -- ``hp:p``의 자기 속성 (cycle 6.12 트레인㊸ 갭④).

``columnBreak``/``pageBreak``는 ``hh:breakSetting``(paraPr 공유 스타일 속성,
``page_break_before``가 다루는 그것)와 별개인 문단 인스턴스 속성이다 --
스키마(``ParaList XML schema.xml:679-680``)가 둘을 자매 속성으로 선언한다.
실코퍼스 67파일 전수(14266개 문단): ``pageBreak="1"`` 73건 실사용(어휘 자체가
"0"/"1" 리터럴, "true"/"false" 0건) 대비 ``columnBreak="1"``은 0건 -- 그래도
같은 요소·같은 리터럴 규약이라 구조적 추측 위험은 없다(text_direction과
같은 논리: 미확인인 건 렌더링뿐).
"""
from __future__ import annotations

import io

import pytest

from hwpx.document import HwpxDocument


def test_column_break_defaults_to_false() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("문단")
    paragraph = document.sections[0].paragraphs[-1]
    assert paragraph.column_break is False
    assert paragraph.element.get("columnBreak") == "0"


def test_column_break_property_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("문단")
    paragraph = document.sections[0].paragraphs[-1]

    paragraph.column_break = True
    assert paragraph.element.get("columnBreak") == "1"
    assert document.sections[0].dirty is True

    reopened = HwpxDocument.open(io.BytesIO(document.to_bytes()))
    assert reopened.sections[0].paragraphs[-1].column_break is True


def test_column_break_can_be_cleared() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("문단")
    paragraph = document.sections[0].paragraphs[-1]
    paragraph.column_break = True

    paragraph.column_break = False

    assert paragraph.column_break is False
    assert paragraph.element.get("columnBreak") == "0"


def test_apply_paragraph_format_sets_column_break_without_touching_para_pr() -> None:
    """column_break은 hp:p 자신의 속성이라 paraPrIDRef를 바꾸지 않아야 한다."""

    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    document.add_paragraph("둘째 문단")
    target = document.sections[0].paragraphs[1]
    before_para_pr = target.para_pr_id_ref

    result = document.styles.apply_paragraph_format(paragraph_index=1, column_break=True)

    assert result.formatted == 1
    assert target.column_break is True
    assert target.para_pr_id_ref == before_para_pr


def test_apply_paragraph_format_combines_column_break_with_paragraph_style() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("문단")

    document.styles.apply_paragraph_format(
        paragraph_index=0, column_break=True, page_break_before=True,
    )

    paragraph = document.sections[0].paragraphs[0]
    assert paragraph.column_break is True
    # page_break_before still goes through the paraPr/breakSetting path.
    from hwpx.oxml.namespaces import HH

    header = document.oxml.headers[0]
    break_setting = header.element.find(
        f".//{HH}paraPr[@id='{paragraph.para_pr_id_ref}']/{HH}breakSetting"
    )
    assert break_setting is not None
    assert break_setting.get("pageBreakBefore") == "1"


def test_apply_paragraph_format_column_break_alone_satisfies_the_empty_options_guard() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("문단")
    # Would raise paragraph-format-empty if column_break weren't recognized
    # as a real option by the guard.
    document.styles.apply_paragraph_format(paragraph_index=0, column_break=True)
    assert document.sections[0].paragraphs[0].column_break is True


def test_legacy_root_facade_does_not_accept_column_break() -> None:
    """The deprecated `doc.set_paragraph_format` shim is frozen at 5.x parity
    on purpose -- new post-6.0 options land only on the namespace path
    (`doc.styles.apply_paragraph_format`), matching how drop cap and the
    other train-48 gaps were kept out of `_legacy.py`."""

    document = HwpxDocument.new()
    document.add_paragraph("문단")
    with pytest.raises(TypeError):
        document.set_paragraph_format(paragraph_index=0, column_break=True)
