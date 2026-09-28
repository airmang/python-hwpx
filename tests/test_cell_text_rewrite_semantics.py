# SPDX-License-Identifier: Apache-2.0
"""What a cell text write keeps and rebuilds, and how far a paragraph charPr write reaches.

Each test pins one sentence of ``docs/mutation-semantics.md``.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def _cell_with_three_paragraphs_and_a_nested_table():
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.text = "첫째"
    cell.add_paragraph("둘째", para_pr_id_ref=3, style_id_ref=2, char_pr_id_ref=4)
    cell.add_table(1, 1).cell(0, 0).text = "안쪽"
    return doc, table, cell


def _cell_with_a_blank_line_between_text_and_a_nested_table():
    doc, table, cell = _cell_with_three_paragraphs_and_a_nested_table()
    blank = cell.add_paragraph("", para_pr_id_ref=5, char_pr_id_ref=6).element
    host = cell.paragraphs[2].element
    host.getparent().remove(blank)
    host.addprevious(blank)
    return doc, table, cell


def test_set_cell_text_writes_the_first_text_and_drops_paragraphs_it_emptied() -> None:
    _, table, cell = _cell_with_a_blank_line_between_text_and_a_nested_table()
    before = cell.paragraphs
    kept_ids = [before[0].element.get("id"), before[2].element.get("id"), before[3].element.get("id")]
    cache = before[2].element.makeelement(f"{HP}linesegarray", {})
    before[2].element.append(cache)

    table.set_cell_text(0, 0, "새 글")

    # "둘째" was emptied and held nothing else, so its paragraph goes; the blank
    # line that was already empty and the paragraph holding the nested table stay.
    assert [(p.text, len(p.tables)) for p in cell.paragraphs] == [
        ("새 글", 0),
        ("", 0),
        ("", 1),
    ]
    assert [p.element.get("id") for p in cell.paragraphs] == kept_ids
    assert cell.paragraphs[1].element.get("paraPrIDRef") == "5"
    assert cell.paragraphs[1].runs[0].char_pr_id_ref == "6"
    assert cell.paragraphs[1].element.find(f"{HP}linesegarray") is None
    # The nested table keeps its text: only the cell's own paragraphs take the value.
    assert cell.tables[0].cell(0, 0).text == "안쪽"
    assert len(cell.tables[0].cell(0, 0).paragraphs) == 1


def test_set_cell_text_without_preserve_format_resets_only_the_written_run() -> None:
    _, table, cell = _cell_with_a_blank_line_between_text_and_a_nested_table()
    cell.paragraphs[0].runs[0].element.set("charPrIDRef", "7")

    table.set_cell_text(0, 0, "새 글", preserve_format=False)

    assert cell.paragraphs[0].runs[0].char_pr_id_ref == "0"
    assert cell.paragraphs[1].runs[0].char_pr_id_ref == "6"


def test_split_paragraphs_rebuilds_one_paragraph_per_line() -> None:
    _, table, cell = _cell_with_three_paragraphs_and_a_nested_table()
    old_ids = [p.element.get("id") for p in cell.paragraphs]

    table.set_cell_text(0, 0, "가\n나", split_paragraphs=True)

    paragraphs = cell.paragraphs
    assert [p.text for p in paragraphs] == ["가", "나"]
    assert cell.tables == []  # the paragraph that held the nested table is gone
    # Line i takes paraPrIDRef and its run's charPrIDRef from old paragraph i.
    assert paragraphs[1].element.get("paraPrIDRef") == "3"
    assert paragraphs[1].element.get("styleIDRef") == "2"
    assert [p.runs[0].char_pr_id_ref for p in paragraphs] == ["0", "4"]
    assert [len(p.runs) for p in paragraphs] == [1, 1]
    assert not {p.element.get("id") for p in paragraphs} & set(old_ids)


def test_paragraph_char_pr_id_ref_applies_to_every_run_of_that_paragraph() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가")
    paragraph.add_run("나", char_pr_id_ref=3)
    paragraph.add_run("다", char_pr_id_ref=4)
    assert paragraph.char_pr_id_ref is None  # mixed

    paragraph.char_pr_id_ref = 5

    assert [run.char_pr_id_ref for run in paragraph.runs] == ["5", "5", "5"]
    assert paragraph.char_pr_id_ref == "5"


def test_paragraph_char_pr_id_ref_leaves_runs_of_a_nested_table_alone() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1).cell(0, 0)
    host = cell.paragraphs[0]
    inner = host.add_table(1, 1).cell(0, 0)
    inner.text = "안쪽"

    host.char_pr_id_ref = 5

    assert {run.char_pr_id_ref for run in host.runs} == {"5"}
    assert inner.paragraphs[0].runs[0].char_pr_id_ref == "0"


def test_paragraph_char_pr_id_ref_makes_a_run_when_there_is_none_and_none_clears_it() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    for run in paragraph.runs:
        paragraph.element.remove(run.element)

    paragraph.char_pr_id_ref = 6
    assert [run.char_pr_id_ref for run in paragraph.runs] == ["6"]

    paragraph.char_pr_id_ref = None
    assert [run.char_pr_id_ref for run in paragraph.runs] == [None]
