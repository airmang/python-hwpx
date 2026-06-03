from hwpx.tools.table_cleanup import (
    add_reverse_sum,
    add_sequence_column,
    normalize_cell_text,
    normalize_table_rows,
)


def test_normalize_cell_text_strips_edges_and_collapses_internal_newlines() -> None:
    assert normalize_cell_text("  금액\n  합계\r\n  원  ") == "금액 합계 원"
    assert normalize_cell_text(" \n\t ") == ""
    assert normalize_cell_text(None) == ""


def test_normalize_table_rows_preserves_shape_and_does_not_mutate_input() -> None:
    rows = [
        ["  이름  ", "  첫째\n둘째  "],
        ["", "  값\t유지  ", "  초과  "],
    ]

    normalized = normalize_table_rows(rows)

    assert normalized == [["이름", "첫째 둘째"], ["", "값\t유지", "초과"]]
    assert rows[0][0] == "  이름  "


def test_add_sequence_column_handles_empty_and_irregular_rows() -> None:
    assert add_sequence_column([]) == []
    assert add_sequence_column([["이름"], [], ["값", "비고"]]) == [
        ["1", "이름"],
        ["2"],
        ["3", "값", "비고"],
    ]


def test_add_reverse_sum_appends_numeric_sum_and_ignores_non_numeric_cells() -> None:
    rows = [
        ["항목", "10", " 20 "],
        ["비숫자", "x", "3.5"],
        ["빈값", "", None],
        ["콤마", "1,000", "-20"],
    ]

    assert add_reverse_sum(rows) == [
        ["항목", "10", " 20 ", "30"],
        ["비숫자", "x", "3.5", "3.5"],
        ["빈값", "", None, "0"],
        ["콤마", "1,000", "-20", "980"],
    ]
