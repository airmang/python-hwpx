# SPDX-License-Identifier: Apache-2.0
"""메모를 문단 전체가 아니라 글자 범위에 건다(doc.notes.add_memo(..., match=))."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _texts_between(paragraph) -> str:
    inside, parts = False, []
    for run in paragraph.element.findall(f"{HP}run"):
        for child in run:
            if child.find(f"{HP}fieldBegin") is not None:
                inside = True
            elif child.find(f"{HP}fieldEnd") is not None:
                inside = False
            elif inside and child.tag == f"{HP}t":
                parts.append("".join(child.itertext()))
    return "".join(parts)


def test_memo_on_some_characters_of_a_paragraph() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("검토가 필요한 문장입니다.")
    memo = doc.notes.add_memo("이 낱말을 고칠 것", anchor=paragraph, match="필요한")
    assert paragraph.text == "검토가 필요한 문장입니다."
    assert _texts_between(paragraph) == "필요한"
    assert memo.paragraph.element is paragraph.element
    assert paragraph.element.find(f"{HP}linesegarray") is None
    again = HwpxDocument.open(doc.to_bytes())
    assert not [i for i in again.validate().issues if i.severity == "error"]
    assert again.paragraphs[-1].text == "검토가 필요한 문장입니다."
    assert [m.text for m in again.notes.memos] == ["이 낱말을 고칠 것"]


def test_memo_attached_to_a_range_after_tabs() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가\t나다\t라")
    memo = doc.notes.add_memo("메모")
    doc.notes.attach(paragraph, memo, match="나다")
    assert _texts_between(paragraph) == "나다"
    assert paragraph.text == "가\t나다\t라"


def test_memo_range_must_be_in_the_paragraph() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가나다")
    with pytest.raises(HwpxValueError) as excinfo:
        doc.notes.add_memo("메모", anchor=paragraph, match="없는 글")
    assert excinfo.value.code == "note-match-not-found"
    assert doc.notes.memos == []  # 걸지 못한 메모는 남기지 않는다
