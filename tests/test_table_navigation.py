from __future__ import annotations

from hwpx import HwpxDocument


def _paragraph_index(document: HwpxDocument, target) -> int:
    for index, paragraph in enumerate(document.paragraphs):
        if paragraph.element is target.element:
            return index
    raise AssertionError("target paragraph was not found in document order")


def test_fill_by_path_handles_unique_labels_in_a_single_table() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("1. 기본 현황")
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "성명:"
    table.cell(1, 0).text = "소속"

    result = document.fill_by_path(
        {
            "성명 > right": "홍길동",
            "소속 > right": "플랫폼팀",
        }
    )

    assert result["applied_count"] == 2
    assert result["failed_count"] == 0
    assert table.cell(0, 1).text == "홍길동"
    assert table.cell(1, 1).text == "플랫폼팀"


def test_find_cell_by_label_normalizes_trailing_colons() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("기본 정보")
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "성명:"

    result = document.find_cell_by_label("성명")

    assert result["count"] == 1
    assert result["matches"][0]["table_index"] == 0
    assert result["matches"][0]["label_cell"] == {
        "row": 0,
        "col": 0,
        "text": "성명:",
    }
    assert result["matches"][0]["target_cell"] == {
        "row": 0,
        "col": 1,
        "text": "",
    }


def test_multiple_tables_with_the_same_label_return_all_matches_and_make_fill_ambiguous() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("1. 신청인")
    first = document.add_table(1, 2)
    first.cell(0, 0).text = "성명"

    document.add_paragraph("2. 보호자")
    second = document.add_table(1, 2)
    second.cell(0, 0).text = "성명"

    matches = document.find_cell_by_label("성명")
    fill_result = document.fill_by_path({"성명 > right": "홍길동"})

    assert matches["count"] == 2
    assert [match["table_index"] for match in matches["matches"]] == [0, 1]
    assert fill_result["applied_count"] == 0
    assert fill_result["failed_count"] == 1
    assert fill_result["failed"][0] == {
        "path": "성명 > right",
        "reason": "ambiguous label",
    }
    assert first.cell(0, 1).text == ""
    assert second.cell(0, 1).text == ""


def test_out_of_bounds_candidates_are_skipped_and_reported_for_batch_fill() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("경계 값")
    table = document.add_table(2, 2)
    table.cell(0, 1).text = "마지막열"
    table.cell(1, 0).text = "마지막행"

    right_matches = document.find_cell_by_label("마지막열", direction="right")
    down_matches = document.find_cell_by_label("마지막행", direction="down")
    fill_result = document.fill_by_path(
        {
            "마지막열 > right": "실패",
            "마지막행 > down": "실패",
        }
    )

    assert right_matches["count"] == 0
    assert down_matches["count"] == 0
    assert fill_result["applied_count"] == 0
    assert fill_result["failed_count"] == 2
    assert fill_result["failed"] == [
        {"path": "마지막열 > right", "reason": "navigation out of bounds"},
        {"path": "마지막행 > down", "reason": "navigation out of bounds"},
    ]


def test_fill_by_path_supports_multi_step_navigation() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("정산표")
    table = document.add_table(3, 2)
    table.cell(0, 0).text = "합계"

    result = document.fill_by_path({"합계 > down > right": "100"})

    assert result["applied"] == [
        {
            "path": "합계 > down > right",
            "table_index": 0,
            "row": 1,
            "col": 1,
            "value": "100",
        }
    ]
    assert result["failed"] == []
    assert table.cell(1, 1).text == "100"


def test_get_table_map_reports_stable_order_shape_and_header_text() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("1. 기본 현황")
    first = document.add_table(2, 4)
    first.cell(0, 0).text = "성명"
    first.cell(0, 1).text = "소속"
    first.cell(0, 2).text = "직위"
    first.cell(0, 3).text = "연락처"
    first.cell(1, 0).text = "홍길동"

    document.add_paragraph("2. 비고")
    second = document.add_table(1, 2)
    second.cell(0, 0).text = "항목"
    second.cell(0, 1).text = "값"

    result = document.get_table_map()

    assert result["tables"] == [
        {
            "table_index": 0,
            "paragraph_index": _paragraph_index(document, first.paragraph),
            "rows": 2,
            "cols": 4,
            "header_text": "1. 기본 현황",
            "first_row_preview": ["성명", "소속", "직위", "연락처"],
            "is_empty": False,
        },
        {
            "table_index": 1,
            "paragraph_index": _paragraph_index(document, second.paragraph),
            "rows": 1,
            "cols": 2,
            "header_text": "2. 비고",
            "first_row_preview": ["항목", "값"],
            "is_empty": False,
        },
    ]


def test_get_table_map_marks_tables_with_only_empty_strings_as_empty() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("빈 표")
    table = document.add_table(2, 2)

    result = document.get_table_map()

    assert result["tables"] == [
        {
            "table_index": 0,
            "paragraph_index": _paragraph_index(document, table.paragraph),
            "rows": 2,
            "cols": 2,
            "header_text": "빈 표",
            "first_row_preview": ["", ""],
            "is_empty": True,
        }
    ]
