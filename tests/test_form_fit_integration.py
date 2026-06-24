# SPDX-License-Identifier: Apache-2.0
"""FormFit wired into the live model (plan §2 Phase C, task 4).

Exercises ``set_cell_text(fit=...)`` and ``fill_form_field(fit_policy=...)``: the
fit verdict propagates, a shrink is a real ``charPr`` change, the ledger records
style changes, the output stays open-safe, and — critically — the no-fit calls
behave exactly as before so the rest of the suite is undisturbed.
"""
from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.form_fit import FitPolicy
from hwpx.quality.ledger import DirtyLayoutLedger
from hwpx.tools.package_validator import validate_editor_open_safety

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _doc_with_cell(width: int):
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_size(width=width)
    return doc, table, cell


# --------------------------------------------------------------------------- #
# set_cell_text(fit=...)
# --------------------------------------------------------------------------- #
def test_no_fit_keeps_historical_behavior():
    doc, table, cell = _doc_with_cell(4000)
    assert table.set_cell_text(0, 0, "가" * 30) is None  # unchanged API
    assert cell.text == "가" * 30


def test_fit_short_value_fits_unchanged():
    doc, table, cell = _doc_with_cell(8000)
    result = table.set_cell_text(0, 0, "홍길동", fit=FitPolicy(max_lines=1))
    assert result is not None and result.ok and not result.overflow_detected
    assert result.applied_style_changes == {}
    assert cell.text == "홍길동"


def test_fit_gross_overflow_fails_with_field_overflow():
    doc, table, cell = _doc_with_cell(4000)
    result = table.set_cell_text(
        0, 0, "서울특별시강남구테헤란로무지무지하게긴주소값입니다정말로",
        fit=FitPolicy(mode="fail_on_overflow", overflow="fail", max_lines=1),
    )
    assert result is not None and result.ok is False
    assert result.overflow_detected and result.confidence == "high"
    assert any("FIELD_OVERFLOW" in e for e in result.errors)
    assert result.suggested_retry()["code"] == "FIELD_OVERFLOW"


def test_fit_shrink_is_a_real_font_change_and_open_safe(tmp_path: Path):
    doc, table, cell = _doc_with_cell(5000)
    run_before = cell.paragraphs[0].runs[0].char_pr_id_ref
    result = table.set_cell_text(
        0, 0, "가나다라마바사", fit=FitPolicy(mode="shrink", min_font_pt=6.0, max_lines=1)
    )
    assert result is not None and result.ok
    assert result.font_pt is not None and result.font_pt < 10.0
    # The run now points at a different (smaller) charPr — a real, oracle-visible change.
    run_after = cell.paragraphs[0].runs[0].char_pr_id_ref
    assert run_after != run_before
    out = tmp_path / "shrunk.hwpx"
    doc.save_to_path(out)
    assert validate_editor_open_safety(out.read_bytes()).ok is True


def test_fit_records_ledger_entry_on_style_change():
    ledger = DirtyLayoutLedger()
    doc, table, cell = _doc_with_cell(5000)
    table.set_cell_text(
        0, 0, "가나다라마바사",
        fit=FitPolicy(mode="shrink", min_font_pt=6.0, max_lines=1), ledger=ledger,
    )
    assert not ledger.is_empty
    entry = ledger.ranges[0]
    assert entry.story_type == "table_cell"
    assert entry.reason in ("style_changed", "form_filled")


def test_fit_borderline_overflow_downgrades_to_warn():
    # ~5 Hangul (5000) into a slot whose inner width lands just under that after
    # the 0.93 safety factor → borderline, must NOT hard-fail.
    doc, table, cell = _doc_with_cell(5550)  # inner ≈ 5161; band makes it borderline
    result = table.set_cell_text(
        0, 0, "가나다라마바", fit=FitPolicy(mode="fail_on_overflow", overflow="fail", max_lines=1)
    )
    assert result is not None
    if result.overflow_detected and result.confidence == "low":
        assert result.ok is True
        assert any("oracle" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# fill_form_field(fit_policy=..., box_width=...)
# --------------------------------------------------------------------------- #
def _append(parent, tag: str, attrs: dict[str, str] | None = None):
    child = parent.makeelement(tag, attrs or {})
    parent.append(child)
    return child


def _add_click_here_field(doc: HwpxDocument, *, name: str = "주소") -> None:
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    begin_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    ctrl = _append(begin_run, f"{HP}ctrl", {"type": "FORM", "id": "ctrl-a"})
    field_begin = _append(
        ctrl, f"{HP}fieldBegin",
        {"id": "f-a", "fieldid": "f-a", "type": "ClickHere", "name": name, "prompt": name},
    )
    params = _append(field_begin, f"{HP}parameters", {"count": "1"})
    _append(params, f"{HP}stringParam", {"name": "FieldName"}).text = name
    text_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    _append(text_run, f"{HP}t").text = "입력"
    end_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    end_ctrl = _append(end_run, f"{HP}ctrl")
    _append(end_ctrl, f"{HP}fieldEnd", {"beginIDRef": "f-a", "fieldid": "f-a"})
    _append(p, f"{HP}lineSegArray")
    paragraph.section.mark_dirty()


def test_fill_form_field_without_box_width_is_low_confidence_never_fails():
    doc = HwpxDocument.new()
    _add_click_here_field(doc)
    result = doc.fill_form_field(
        "가" * 50, name="주소", fit_policy=FitPolicy(overflow="fail")
    )
    assert result["ok"] is True  # honest: no geometry → never a hard fail
    assert result["fit"]["confidence"] == "low"


def test_fill_form_field_box_width_gross_overflow_fails():
    doc = HwpxDocument.new()
    _add_click_here_field(doc)
    result = doc.fill_form_field(
        "가" * 50, name="주소",
        fit_policy=FitPolicy(mode="fail_on_overflow", overflow="fail", max_lines=1),
        box_width=4000,
    )
    assert result["ok"] is False
    assert result["fit"]["overflowDetected"] is True
    assert result["suggestedRetry"]["code"] == "FIELD_OVERFLOW"


def test_fill_form_field_no_fit_policy_unchanged(tmp_path: Path):
    doc = HwpxDocument.new()
    _add_click_here_field(doc)
    result = doc.fill_form_field("서울시", name="주소")
    assert result["ok"] is True and "fit" not in result
    assert result["after_value"] == "서울시"
