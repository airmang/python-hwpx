# SPDX-License-Identifier: Apache-2.0
"""셀 높이/너비를 같게 -- cycle 6.13 트레인㊻ (편집기 메뉴 표면 역매핑
트레인㊷·㊺가 찾은 "부분 대응": `set_column_widths`/`set_row_heights`류는
이미 있었으나 "균등화" 전용 헬퍼가 없어 호출자가 매번 값을 직접 계산해야
했다). ``equalize_column_widths``는 균등 가중치로 기존
``set_column_widths``를 호출하는 것과 정확히 동치, ``equalize_row_heights``는
그 행 대응(같은 rowSpan/iter_grid 로직, 축만 다름) -- 둘 다 신규 XML
어휘가 전혀 없다.
"""
from __future__ import annotations

from hwpx.document import HwpxDocument


def test_equalize_column_widths_normalizes_uneven_widths() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=3, width=30000)
    table.set_column_widths([1, 5, 2])
    assert [table.cell(0, c).width for c in range(3)] != [10000, 10000, 10000]

    table.equalize_column_widths()

    widths = [table.cell(0, c).width for c in range(3)]
    assert widths == [10000, 10000, 10000]
    assert sum(widths) == 30000


def test_equalize_column_widths_is_equivalent_to_uniform_weights() -> None:
    document = HwpxDocument.new()
    a = document.add_table(rows=2, cols=4, width=28000)
    b = document.add_table(rows=2, cols=4, width=28000)

    a.equalize_column_widths()
    b.set_column_widths([1, 1, 1, 1])

    assert [a.cell(0, c).width for c in range(4)] == [b.cell(0, c).width for c in range(4)]


def test_equalize_column_widths_gives_a_merged_cell_the_sum_of_its_span() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=4, width=40000)
    table.merge_cells("A1:B1")

    table.equalize_column_widths()

    merged = table.cell(0, 0)
    assert merged.span == (1, 2)
    assert merged.width == table.cell(0, 2).width + table.cell(0, 3).width


def test_equalize_row_heights_normalizes_uneven_heights() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=3, cols=2, height=12000)
    # perturb one row's height directly (bypassing any equalizer) so the
    # starting point is genuinely uneven.
    table.cell(1, 0).set_size(height=9000)
    table.cell(1, 1).set_size(height=9000)

    table.equalize_row_heights()

    heights = [table.cell(r, 0).height for r in range(3)]
    assert heights == [4000, 4000, 4000]
    assert sum(heights) == 12000


def test_equalize_row_heights_gives_a_merged_cell_the_sum_of_its_span() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=4, cols=2, height=20000)
    table.merge_cells("A1:A2")

    table.equalize_row_heights()

    merged = table.cell(0, 0)
    assert merged.span == (2, 1)
    assert merged.height == table.cell(2, 0).height + table.cell(3, 0).height


def test_equalize_column_widths_and_row_heights_round_trip_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=3, width=30000, height=8000)
    table.set_column_widths([1, 5, 2])
    table.equalize_column_widths()
    table.equalize_row_heights()

    before_widths = [table.cell(0, c).width for c in range(3)]
    before_heights = [table.cell(r, 0).height for r in range(2)]

    reopened = HwpxDocument.open(document.to_bytes())
    reopened_table = reopened.tables.all[0]

    assert [reopened_table.cell(0, c).width for c in range(3)] == before_widths
    assert [reopened_table.cell(r, 0).height for r in range(2)] == before_heights
