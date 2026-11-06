# SPDX-License-Identifier: Apache-2.0
"""doc.text.blocks / outline / apply_changes — id-addressed text for small models."""

from __future__ import annotations

import io
import json

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP


def _sample() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("제목 문단")
    doc.add_paragraph("")
    table = doc.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            table.set_cell_text(row, col, f"칸{row}{col}")
    table.merge_cells(1, 0, 2, 0)
    inner = table.cell(0, 1).add_table(1, 2)
    inner.set_cell_text(0, 0, "안쪽")
    doc.add_paragraph("끝\t문단")
    return doc


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(doc.to_bytes()))


def _by_text(doc: HwpxDocument, text: str):
    return next(block for block in doc.text.blocks() if block.text == text)


# --------------------------------------------------------------------------- blocks


def test_blocks_walk_body_cells_and_nested_tables_in_document_order() -> None:
    blocks = list(_sample().text.blocks())
    texts = [block.text for block in blocks if block.text]
    assert texts == ["제목 문단", "칸00", "칸01", "안쪽", "칸02", "칸10", "칸20", "칸11", "칸12", "칸21", "칸22", "끝\t문단"]

    title = next(block for block in blocks if block.text == "제목 문단")
    assert (title.id, title.location, title.in_table) == ("s0p1", "본문 2문단", False)

    cell = next(block for block in blocks if block.text == "칸22")
    assert (cell.id, cell.location, cell.in_table) == ("s0p3t0r2c2q0", "표1 3행 3열", True)

    nested = next(block for block in blocks if block.text == "안쪽")
    assert nested.id == "s0p3t0r0c1q1t0r0c0q0"
    assert nested.location == "표1 1행 2열 안 표1 1행 1열"


def test_a_merged_cell_appears_once_at_its_anchor() -> None:
    blocks = list(_sample().text.blocks())
    merged = [block for block in blocks if block.id.startswith("s0p3t0r1c0") or block.id.startswith("s0p3t0r2c0")]
    # The merge moved the covered cell's paragraph into the anchor; no r2c0 block exists.
    assert [block.id for block in merged] == ["s0p3t0r1c0q0", "s0p3t0r1c0q1"]
    assert [block.text for block in merged] == ["칸10", "칸20"]


def test_ids_are_unique_and_survive_save_and_reopen() -> None:
    doc = _sample()
    before = {block.id: block.text for block in doc.text.blocks()}
    assert len(before) == len(list(doc.text.blocks()))
    after = {block.id: block.text for block in _reopen(doc).text.blocks()}
    assert after == before


def test_a_table_without_cell_addresses_gets_physical_ids() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    for row in range(2):
        for col in range(2):
            table.set_cell_text(row, col, f"{row}{col}")
    for tc in table.element.iter(f"{HP}tc"):
        for addr in tc.findall(f"{HP}cellAddr"):
            tc.remove(addr)
    blocks = [block for block in doc.text.blocks() if block.in_table]
    prefix = blocks[0].id.split("t0")[0]
    assert [block.id for block in blocks] == [f"{prefix}t0r{row}c{col}q0" for row in range(2) for col in range(2)]
    assert [block.text for block in blocks] == ["00", "01", "10", "11"]


# --------------------------------------------------------------------------- outline


def test_outline_lists_only_non_empty_blocks_with_clean_text() -> None:
    items = _sample().text.outline()
    assert items.complete is True and items.next_after is None
    assert items.total == len(items) == 12
    assert items[0] == {"id": "s0p1", "where": "본문 2문단", "text": "제목 문단"}
    assert items[-1]["text"] == "끝 문단"  # the tab became a space
    # A plain list for JSON: the paging attributes stay out of the payload.
    assert json.loads(json.dumps(items, ensure_ascii=False))[0]["id"] == "s0p1"


def test_outline_truncates_a_long_block_and_marks_it() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("가" * 500)
    (item,) = doc.text.outline(max_block_chars=50)
    assert item["truncated"] is True
    assert len(item["text"]) == 50 and item["text"].endswith("…")


def test_outline_pages_through_the_document_within_the_budget() -> None:
    doc = _sample()
    full = [item["id"] for item in doc.text.outline()]
    collected: list[str] = []
    after = None
    for _ in range(20):
        page = doc.text.outline(max_chars=40, after=after)
        assert page, "a page always holds one item"
        cost = sum(len(i["id"]) + len(i["where"]) + len(i["text"]) for i in page)
        assert cost <= 40 or len(page) == 1  # a lone item may exceed the budget
        collected += [item["id"] for item in page]
        if page.complete:
            break
        after = page.next_after
    assert collected == full


def test_outline_max_items_and_to_text() -> None:
    page = _sample().text.outline(max_items=2)
    assert len(page) == 2 and page.complete is False and page.total == 12
    assert page.to_text().splitlines() == [
        "[s0p1] 본문 2문단: 제목 문단",
        "[s0p3t0r0c0q0] 표1 1행 1열: 칸00",
        "… 10 more (after=s0p3t0r0c0q0)",
    ]


def test_outline_rejects_an_unknown_cursor_and_bad_budgets() -> None:
    doc = _sample()
    with pytest.raises(KeyError):
        doc.text.outline(after="s9p9")
    with pytest.raises(ValueError):
        doc.text.outline(max_chars=0)
    with pytest.raises(ValueError):
        doc.text.outline(max_items=0)


# --------------------------------------------------------------------------- apply_changes


def test_apply_changes_reports_each_id() -> None:
    doc = _sample()
    report = doc.text.apply_changes({"s0p1": "새 제목", "s0p3t0r0c0q0": "칸00", "s9p9": "없음"})
    assert report.changed == ["s0p1"]
    assert report.unchanged == ["s0p3t0r0c0q0"]
    assert report.unknown_ids == ["s9p9"]
    assert report.ok is False
    assert report.to_dict()["unknownIds"] == ["s9p9"]
    reopened = _reopen(doc)
    assert next(reopened.text.blocks()).text == "" and _by_text(reopened, "새 제목").id == "s0p1"


def test_apply_changes_keeps_runs_when_the_edit_stays_in_one_run() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("이름: ")
    paragraph.add_run("홍길동", bold=True)
    styles_before = [run.char_pr_id_ref for run in paragraph.runs]
    block_id = _by_text(doc, "이름: 홍길동").id

    report = doc.text.apply_changes({block_id: "이름: 김철수"})

    assert report.changed == [block_id] and report.rewritten == []
    assert [run.text for run in paragraph.runs] == ["이름: ", "김철수"]
    assert [run.char_pr_id_ref for run in paragraph.runs] == styles_before


def test_apply_changes_rewrites_an_edit_across_runs_and_says_so() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞 ")
    paragraph.add_run("굵게", bold=True)
    block_id = _by_text(doc, "앞 굵게").id

    report = doc.text.apply_changes({block_id: "완전히 다른 글"})

    assert report.rewritten == [block_id]
    assert paragraph.text == "완전히 다른 글"


def test_a_line_break_in_new_text_becomes_a_line_break_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("한 줄")
    block_id = _by_text(doc, "한 줄").id
    report = doc.text.apply_changes({block_id: "첫 줄\n둘째 줄"})
    assert report.rewritten == [block_id]
    assert paragraph.element.find(f".//{HP}lineBreak") is not None
    assert _by_text(_reopen(doc), "첫 줄\n둘째 줄").id == block_id


def test_apply_changes_warns_when_a_cell_would_grow() -> None:
    doc = _sample()
    target = _by_text(doc, "칸22").id
    report = doc.text.apply_changes({target: "아주 긴 문장입니다 " * 60})
    assert report.changed == [target]
    (entry,) = report.overflow
    assert entry["id"] == target and entry["where"] == "표1 3행 3열"
    assert entry["lines"] > entry["lineBudget"] >= entry["linesBefore"]
    assert report.ok is False


def test_a_short_cell_edit_does_not_warn_and_the_check_can_be_skipped() -> None:
    doc = _sample()
    target = _by_text(doc, "칸22").id
    assert doc.text.apply_changes({target: "짧게"}).overflow == []
    long_report = doc.text.apply_changes({target: "아주 긴 문장입니다 " * 60}, check_overflow=False)
    assert long_report.overflow == [] and long_report.ok is True


def test_an_empty_change_set_touches_nothing() -> None:
    doc = _sample()
    before = doc.to_bytes()
    report = doc.text.apply_changes({})
    assert report.to_dict() == {
        "ok": True, "changed": [], "unknownIds": [], "unchanged": [], "rewritten": [], "overflow": [], "warnings": [],
    }
    assert doc.to_bytes() == before
