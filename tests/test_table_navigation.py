from __future__ import annotations


from hwpx import HwpxDocument


def _paragraph_index(document: HwpxDocument, target) -> int:
    for index, paragraph in enumerate(document.paragraphs):
        if paragraph.element is target.element:
            return index
    raise AssertionError("target paragraph was not found in document order")


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

    result = document.tables.map()
    first_entry = result["tables"][0]
    second_entry = result["tables"][1]

    assert first_entry["table_index"] == 0
    assert first_entry["paragraph_index"] == _paragraph_index(document, first.paragraph)
    assert first_entry["location"] == {
        "kind": "body_paragraph",
        "paragraph_index": first_entry["paragraph_index"],
    }
    assert first_entry["rows"] == 2
    assert first_entry["cols"] == 4
    assert first_entry["caption_text"] == ""
    assert first_entry["preceding_paragraph_text"] == "1. 기본 현황"
    assert first_entry["header_text"] == "1. 기본 현황"
    assert first_entry["first_row_preview"] == ["성명", "소속", "직위", "연락처"]
    assert first_entry["cells"][0]["location"] == {
        "kind": "table_cell",
        "table_index": 0,
        "row": 0,
        "col": 0,
    }
    assert first_entry["cells"][0]["paragraphs"][0]["location"] == {
        "kind": "table_cell_paragraph",
        "table_index": 0,
        "row": 0,
        "col": 0,
        "cell_paragraph_index": 0,
    }
    assert first_entry["is_empty"] is False

    assert second_entry["table_index"] == 1
    assert second_entry["paragraph_index"] == _paragraph_index(document, second.paragraph)
    assert second_entry["header_text"] == "2. 비고"
    assert second_entry["first_row_preview"] == ["항목", "값"]
    assert second_entry["is_empty"] is False


def test_get_table_map_marks_tables_with_only_empty_strings_as_empty() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("빈 표")
    table = document.add_table(2, 2)

    result = document.tables.map()
    entry = result["tables"][0]

    assert entry["table_index"] == 0
    assert entry["paragraph_index"] == _paragraph_index(document, table.paragraph)
    assert entry["rows"] == 2
    assert entry["cols"] == 2
    assert entry["header_text"] == "빈 표"
    assert entry["first_row_preview"] == ["", ""]
    assert entry["is_empty"] is True


def test_get_table_map_preserves_cell_paragraph_boundaries_in_preview() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("코드 표")
    table = document.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_text("line 1\nline 2", split_paragraphs=True)

    result = document.tables.map()
    entry = result["tables"][0]

    assert entry["first_row_preview"] == ["line 1\nline 2"]
    assert entry["cells"][0]["text"] == "line 1\nline 2"
    assert [item["text"] for item in entry["cells"][0]["paragraphs"]] == ["line 1", "line 2"]
