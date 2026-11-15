# SPDX-License-Identifier: Apache-2.0
"""fields.choices() does not read prose marks as choice groups."""

from __future__ import annotations

from hwpx import HwpxDocument


def _labels(*lines: str) -> list[list[str]]:
    doc = HwpxDocument.new()
    for line in lines:
        doc.add_paragraph(line)
    return [[option["text"] for option in group["options"]] for group in doc.fields.choices()["choices"]]


def test_a_mark_alone_in_brackets_is_not_an_option() -> None:
    assert _labels("(예시) 200,000천원(○), 170,000천원(○), 136,000천원( ○ )") == []
    assert _labels("<예시> 오후 3시 20분(×) → 15:20(○), 오전 7시 9분(×) → 07:09(○)") == []


def test_marks_between_long_clauses_are_prose() -> None:
    line = (
        "a) ○ 성년이고 승낙능력이 있으며 ○ 법에 규정된 적출에 관한 정보를 받았고 적출에 승낙했으며 "
        "○ 의사가 판단할 때 기증자로서 적합하고 수술위험 이외의 위험이 발생하지 않는 경우"
    )
    assert _labels(line) == []


def test_real_choices_are_still_groups() -> None:
    assert _labels(
        "참석 여부: □ 예  □ 아니오",
        "평가 방법: ☐ 교사 관찰 및 기록 ☐ 자기평가 ☐ 동료평가",
        "□ 개인정보 수집·이용에 동의합니다  □ 동의하지 않습니다",
        "구분: ○ 신규 ( ) ○ 변경",
    ) == [
        ["예", "아니오"],
        ["교사 관찰 및 기록", "자기평가", "동료평가"],
        ["개인정보 수집·이용에 동의합니다", "동의하지 않습니다"],
        ["신규 ( )", "변경"],
    ]
