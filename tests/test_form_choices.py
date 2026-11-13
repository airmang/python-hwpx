# SPDX-License-Identifier: Apache-2.0
"""Choices typed as check marks: listing the groups and checking options."""
from __future__ import annotations

import io

from hwpx import HwpxDocument


def _form() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("○ 추진 배경")
    doc.add_paragraph("□ 세부 계획은 붙임과 같다")
    doc.add_paragraph("참석 여부: □ 예  □ 아니오")
    table = doc.add_table(4, 2)
    rows = [
        ("성  별", "☐ 남   ☑ 여"),
        ("신청 구분", "○ 신규, ● 변경, ○ 해지"),
        ("동의", "□   □"),
        ("비고", "해당 없음"),
    ]
    for row, (label, value) in zip(table.rows, rows):
        row.cells[0].paragraphs[0].text = label
        row.cells[1].paragraphs[0].text = value
    return doc


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    return HwpxDocument.open(buffer.getvalue())


def test_a_single_leading_mark_is_a_bullet_not_a_choice() -> None:
    listed = _form().fields.choices()
    assert listed["count"] == 4
    assert [group["path"] for group in listed["choices"]] == ["참석 여부", "성 별", "신청 구분", "동의"]


def test_a_group_lists_its_options_and_where_it_is() -> None:
    groups = {group["path"]: group for group in _form().fields.choices()["choices"]}
    assert "paragraph_index" in groups["참석 여부"]
    assert (groups["성 별"]["table_index"], groups["성 별"]["row"], groups["성 별"]["col"]) == (0, 0, 1)
    assert groups["성 별"]["options"] == [
        {"position": 1, "text": "남", "checked": False, "mark": "☐"},
        {"position": 2, "text": "여", "checked": True, "mark": "☑"},
    ]
    assert [option["text"] for option in groups["신청 구분"]["options"]] == ["신규", "변경", "해지"]
    assert [option["text"] for option in groups["동의"]["options"]] == ["", ""]


def test_choosing_checks_the_option_and_unchecks_the_others() -> None:
    doc = _form()
    result = doc.fields.choose({"참석여부": "예", "성별": "남", "신청 구분": ["신규", 3], "동의": 2})
    assert result["failed"] == []
    assert [entry["changed"] for entry in result["applied"]] == [1, 2, 3, 1]
    text = _reopened(doc).text.plain()
    assert "참석 여부: ■ 예  □ 아니오" in text
    assert "☑ 남   ☐ 여" in text  # the group's own marks
    assert "● 신규, ○ 변경, ● 해지" in text
    assert "□   ■" in text
    assert "○ 추진 배경" in text and "□ 세부 계획은 붙임과 같다" in text


def test_an_empty_list_clears_the_group_and_a_repeat_changes_nothing() -> None:
    doc = _form()
    assert doc.fields.choose({"성별": []})["applied"][0]["changed"] == 1
    assert "☐ 남   ☐ 여" in doc.text.plain()
    assert doc.fields.choose({"성별": []})["applied"][0]["changed"] == 0


def test_what_cannot_be_told_apart_is_left_alone() -> None:
    doc = _form()
    before = doc.text.plain()
    result = doc.fields.choose({"없는 묶음": "예", "성별": "중", "동의": 3, "신청 구분": 1.5, "#9": 1})
    assert result["applied"] == []
    reasons = {entry["path"]: entry for entry in result["failed"]}
    assert reasons["없는 묶음"]["reason"] == "choice group not found"
    assert reasons["없는 묶음"]["candidates"] == ["참석 여부", "성 별", "신청 구분", "동의"]
    assert reasons["성별"] == {"path": "성별", "reason": "option not found", "options": ["남", "여"]}
    assert reasons["동의"]["reason"] == "option position out of range: 3 of 2"
    assert "selection must be" in reasons["신청 구분"]["reason"]
    assert reasons["#9"]["reason"] == "no choice group #9 (there are 4)"
    assert doc.text.plain() == before


def test_groups_with_one_label_are_numbered_and_unnamed_ones_go_by_position() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("□ 가  □ 나")
    doc.add_paragraph("선택: □ 가  □ 나")
    doc.add_paragraph("선택: □ 다  □ 라")
    paths = [group["path"] for group in doc.fields.choices()["choices"]]
    assert paths == ["#1", "선택[1]", "선택[2]"]

    ambiguous = doc.fields.choose({"선택": "가"})
    assert ambiguous["failed"] == [
        {"path": "선택", "reason": "ambiguous label", "candidates": ["선택[1]", "선택[2]"]}
    ]
    assert doc.fields.choose({"#1": "나", "선택[2]": "다"})["failed_count"] == 0
    assert doc.text.plain().splitlines()[-3:] == ["□ 가  ■ 나", "선택: □ 가  □ 나", "선택: ■ 다  □ 라"]


def test_the_checked_mark_follows_the_documents_habit() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("가: □ 하나  ▣ 둘")
    doc.add_paragraph("나: □ 셋  □ 넷")
    doc.fields.choose({"나": "셋"})
    assert "나: ▣ 셋  □ 넷" in doc.text.plain()


def test_a_label_can_sit_on_the_line_above_or_in_the_cell_above() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    table.rows[0].cells[0].paragraphs[0].text = "수령 방법"
    table.rows[1].cells[0].paragraphs[0].text = "□ 방문  □ 우편"
    cell = table.rows[0].cells[1]
    cell.paragraphs[0].text = "결제 수단"
    cell.add_paragraph("□ 카드  □ 현금")
    paths = [group["path"] for group in doc.fields.choices()["choices"]]
    assert paths == ["결제 수단", "수령 방법"]


def test_marks_split_over_runs_are_still_one_group() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("구분: □ 갑")
    paragraph.add_run("  □ 을", bold=True)
    doc.fields.choose({"구분": "을"})
    assert _reopened(doc).text.plain().endswith("구분: □ 갑  ■ 을")
    assert len(list(paragraph.runs)) == 2
