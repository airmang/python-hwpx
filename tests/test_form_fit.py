# SPDX-License-Identifier: Apache-2.0
"""FormFit unit tests (plan §2 Phase C).

These pin the Hancom-calibrated measurement (Hangul = 1.0 em), the keep/wrap/
shrink/expand/truncate/fail ladder, and — most importantly — the *honesty
contract*: a hard ``overflow="fail"`` fires only on a high-confidence (gross)
overflow; a borderline overflow is downgraded to a warning for the render oracle.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.form_fit import (
    FitEngine,
    FitPolicy,
    SlotMetrics,
    estimate_lines,
    estimate_text_width,
    measure,
    to_form_report,
)
from hwpx.form_fit.measure import classify_char, resolve_slot_metrics


# --------------------------------------------------------------------------- #
# Measurement — calibrated against the real Hancom doc.
# --------------------------------------------------------------------------- #
def test_hangul_is_full_width_em():
    # 1pt = 100 HWPUNIT; a Hangul glyph advances exactly one em.
    assert estimate_text_width("가", 10.0) == pytest.approx(1000.0)
    assert estimate_text_width("홍길동", 10.0) == pytest.approx(3000.0)
    # 12pt → em 1200.
    assert estimate_text_width("가나", 12.0) == pytest.approx(2400.0)


def test_classify_char_buckets():
    assert classify_char("가") == "hangul"
    assert classify_char("A") == "upper"
    assert classify_char("a") == "lower"
    assert classify_char("7") == "digit"
    assert classify_char(" ") == "space"
    assert classify_char(",") == "punct"
    assert classify_char("，") == "wide"  # fullwidth comma


def test_latin_is_narrower_than_hangul():
    assert estimate_text_width("abcd", 10.0) < estimate_text_width("가나다라", 10.0)


def test_estimate_lines_wraps_like_hancom():
    # '수요조사 참여 여부' wrapped after '수요조사 ' at budget 4516 in the real doc.
    # 4 Hangul + space = 4320 fits; the 5th Hangul (참) pushes to a 2nd line.
    assert estimate_lines("수요조사 참여 여부", 4516, 10.0) >= 2
    # The same text in a wide-enough slot stays on one line.
    assert estimate_lines("수요조사 참여 여부", 12000, 10.0) == 1


def test_single_unbreakable_run_fills_lines():
    # Pure Hangul (breakable anywhere) of 10 glyphs in a 3-glyph-wide slot.
    assert estimate_lines("가나다라마바사아자차", 3000, 10.0) >= 3


# --------------------------------------------------------------------------- #
# Confidence — the honesty gate.
# --------------------------------------------------------------------------- #
def test_comfortable_fit_is_high_confidence():
    slot = SlotMetrics(available_width=5000, font_pt=10.0, max_lines=1)
    m = measure("홍길동", slot)  # 3000 << 5000
    assert m.fits and m.confidence == "high"


def test_gross_overflow_is_high_confidence():
    slot = SlotMetrics(available_width=5000, font_pt=10.0, max_lines=1)
    m = measure("가" * 20, slot)  # 20000 >> 5000
    assert m.overflow and m.confidence == "high"


def test_borderline_fit_is_low_confidence():
    # 5 Hangul (5000) in a slot only just wider (5200): within the error band.
    slot = SlotMetrics(available_width=5200, font_pt=10.0, max_lines=1)
    m = measure("가나다라마", slot)
    assert m.fits and m.confidence == "low"


def test_borderline_overflow_is_low_confidence():
    # 5 Hangul (5000) in a slot just under (4900): a borderline overflow.
    slot = SlotMetrics(available_width=4900, font_pt=10.0, max_lines=1)
    m = measure("가나다라마", slot)
    assert m.overflow and m.confidence == "low"


# --------------------------------------------------------------------------- #
# Engine ladder.
# --------------------------------------------------------------------------- #
def _slot(width: float = 5000, font_pt: float = 10.0, max_lines: int = 1) -> SlotMetrics:
    return SlotMetrics(available_width=width, font_pt=font_pt, max_lines=max_lines)


def test_keep_inserts_verbatim_even_when_overflowing():
    engine = FitEngine()
    result = engine.fit("가" * 20, _slot(), FitPolicy.keep())
    assert result.ok is True
    assert result.applied_value == "가" * 20
    assert result.overflow_detected is True
    assert result.applied_style_changes == {}


def test_short_value_fits_unchanged():
    engine = FitEngine()
    result = engine.fit("홍길동", _slot(), FitPolicy(mode="wrap_then_shrink"))
    assert result.ok and not result.overflow_detected
    assert result.applied_style_changes == {}
    assert result.font_pt == 10.0


def test_wrap_allows_multiple_lines():
    engine = FitEngine()
    policy = FitPolicy(mode="wrap", max_lines=3)
    result = engine.fit("수요조사 참여 여부", _slot(width=4516), policy)
    assert result.ok and result.lines is not None and result.lines >= 2
    assert result.lines <= 3


def test_shrink_reduces_font_and_records_a_real_change():
    engine = FitEngine()
    # 7 Hangul (7000 @10pt) in a 6000-wide single-line slot → shrink ~10pt→8pt.
    policy = FitPolicy(mode="shrink", min_font_pt=6.0)
    result = engine.fit("가나다라마바사", _slot(width=6000), policy)
    assert result.ok
    assert result.font_pt is not None and 6.0 <= result.font_pt < 10.0
    assert result.applied_style_changes.get("font_pt") == result.font_pt
    assert result.applied_style_changes.get("from_font_pt") == 10.0


def test_shrink_floor_overflows_when_even_min_font_cannot_fit():
    engine = FitEngine()
    # 10 Hangul can't fit one 6000-wide line even at 6pt → terminal overflow.
    policy = FitPolicy(mode="shrink", min_font_pt=6.0, overflow="fail")
    result = engine.fit("가나다라마바사아자차", _slot(width=6000), policy)
    assert result.ok is False and result.overflow_detected


def test_wrap_then_shrink_prefers_wrap_then_falls_back():
    engine = FitEngine()
    # Fits in 2 lines without shrinking → no font change.
    policy = FitPolicy(mode="wrap_then_shrink", max_lines=2)
    wrapped = engine.fit("가나다라마바사", _slot(width=4000, max_lines=2), policy)
    assert wrapped.ok and "font_pt" not in wrapped.applied_style_changes


def test_expand_row_accepts_tall_content():
    engine = FitEngine()
    policy = FitPolicy(mode="expand_row", allow_row_expand=True)
    result = engine.fit("가나다라마바사아자차", _slot(width=3000), policy)
    assert result.ok
    assert result.applied_style_changes.get("expand_row") is True


def test_truncate_with_report_cuts_to_fit():
    engine = FitEngine()
    policy = FitPolicy(mode="truncate_with_report")
    value = "가" * 30
    result = engine.fit(value, _slot(width=5000), policy)
    assert result.ok and result.truncated
    assert len(result.applied_value) < len(value)
    assert estimate_text_width(result.applied_value, 10.0) <= 5000


# --------------------------------------------------------------------------- #
# The headline acceptance: fail vs warn.
# --------------------------------------------------------------------------- #
def test_fail_on_gross_overflow_returns_not_ok():
    engine = FitEngine()
    policy = FitPolicy(mode="fail_on_overflow", overflow="fail")
    result = engine.fit("가" * 40, _slot(width=5000), policy)
    assert result.ok is False
    assert result.overflow_detected and result.confidence == "high"
    assert any("FIELD_OVERFLOW" in e for e in result.errors)
    retry = result.suggested_retry()
    assert retry is not None and retry["code"] == "FIELD_OVERFLOW"


def test_fail_downgrades_to_warn_on_borderline_overflow():
    # The honesty contract: a borderline overflow must NOT hard-fail; it warns and
    # defers to the render oracle, so we never assert a false precision.
    engine = FitEngine()
    policy = FitPolicy(mode="fail_on_overflow", overflow="fail")
    result = engine.fit("가나다라마", _slot(width=4900), policy)  # ~2% over
    assert result.ok is True
    assert result.overflow_detected is True
    assert result.confidence == "low"
    assert any("oracle" in w for w in result.warnings)


def test_warn_policy_never_fails():
    engine = FitEngine()
    policy = FitPolicy(mode="fail_on_overflow", overflow="warn")
    result = engine.fit("가" * 40, _slot(width=5000), policy)
    assert result.ok is True and result.overflow_detected is True


# --------------------------------------------------------------------------- #
# Vertical (row-height) budget.
# --------------------------------------------------------------------------- #
def _vslot(width=6000, font_pt=10.0, height=None, ratio=None, unavailable=False):
    return SlotMetrics(
        available_width=width,
        font_pt=font_pt,
        available_height=height,
        line_spacing_ratio=ratio,
        height_unavailable=unavailable,
    )


def test_line_height_and_budget_math():
    slot = _vslot(height=3300)  # default 160% pitch → 1600/line; tight 1.0 → 1000/line
    assert slot.line_height(10.0) == pytest.approx(1600.0)
    assert slot.height_lines(10.0) == 2          # floor(3300 / 1600)
    assert slot.height_lines_optimistic(10.0) == 3  # floor(3300 / 1000)


def test_budget_uses_declared_percent_line_spacing():
    slot = _vslot(height=3300, ratio=2.0)  # declared 200% → 2000/line
    assert slot.line_height(10.0) == pytest.approx(2000.0)
    assert slot.height_lines(10.0) == 2          # two lines take 2000 + 1000
    # Optimistic budget never uses a looser pitch than the tight floor.
    assert slot.height_lines_optimistic(10.0) == 3  # floor(3300 / 1000)


def test_budget_is_none_without_height_and_never_below_one():
    assert _vslot(height=None).height_lines(10.0) is None
    assert _vslot(height=None).height_lines_optimistic(10.0) is None
    # A cell shorter than one line still reports a 1-line budget (guaranteed floor).
    assert _vslot(height=500).height_lines(10.0) == 1


def test_no_height_budget_is_width_only_with_warning_when_unavailable():
    engine = FitEngine()
    warned = engine.fit("홍길동", _vslot(height=None, unavailable=True), FitPolicy())
    assert warned.ok and any("width-only" in w for w in warned.warnings)
    # A caller that never had a height (native field) must NOT get the warning.
    silent = engine.fit("홍길동", _vslot(height=None, unavailable=False), FitPolicy())
    assert silent.ok and not any("width-only" in w for w in silent.warnings)


def test_value_fits_within_ample_height_is_unchanged():
    engine = FitEngine()
    # 11 Hangul wrap to 2 lines in a 6000-wide slot; a 6000-tall cell budgets 3.
    result = engine.fit("가" * 11, _vslot(height=6000), FitPolicy(mode="wrap"))
    assert result.ok and not result.overflow_detected
    assert not any("row will grow" in w for w in result.warnings)


def test_a_value_the_row_cannot_hold_fails_by_default():
    engine = FitEngine()
    # 2 lines needed, 1-line height budget: the row would grow and shift the pages.
    result = engine.fit("가" * 11, _vslot(height=1600), FitPolicy(mode="wrap"))
    assert result.ok is False and result.overflow_detected
    assert any("FIELD_OVERFLOW" in e for e in result.errors)


def test_a_row_grows_only_when_the_policy_allows_it():
    engine = FitEngine()
    warned = engine.fit("가" * 11, _vslot(height=1600), FitPolicy(mode="wrap", overflow="warn"))
    assert warned.ok is True and warned.overflow_detected
    assert any("row will balloon" in w for w in warned.warnings)

    expanded = engine.fit("가" * 11, _vslot(height=1600), FitPolicy(mode="wrap", allow_row_expand=True))
    assert expanded.ok is True and expanded.errors == []


def test_gross_vertical_balloon_fails_closed_when_cannot_shrink():
    engine = FitEngine()
    # 4 lines in a 1-line budget = a gross balloon; wrap mode cannot shrink → fail.
    result = engine.fit(
        "가" * 20, _vslot(height=1600), FitPolicy(mode="wrap", overflow="fail")
    )
    assert result.ok is False and result.overflow_detected
    assert any("FIELD_OVERFLOW" in e for e in result.errors)


def test_gross_vertical_balloon_shrinks_into_the_row_when_allowed():
    engine = FitEngine()
    before = _vslot(height=1600)
    result = engine.fit("가" * 20, before, FitPolicy(mode="wrap_then_shrink", min_font_pt=6.0))
    assert result.ok is True and not result.overflow_detected
    assert result.font_pt is not None and result.font_pt < before.font_pt
    assert result.applied_style_changes.get("from_font_pt") == 10.0

    # No font down to 8 pt fits the row: shrinking part way no longer counts.
    refused = engine.fit("가" * 20, before, FitPolicy(mode="wrap_then_shrink", min_font_pt=8.0))
    assert refused.ok is False
    assert any("FIELD_OVERFLOW" in e for e in refused.errors)


def test_expand_row_bypasses_the_height_budget():
    engine = FitEngine()
    # A gross balloon is accepted (no fail) when row growth is opted into explicitly.
    result = engine.fit(
        "가" * 20,
        _vslot(height=1600),
        FitPolicy(mode="wrap_then_shrink", allow_row_expand=True),
    )
    assert result.ok is True
    assert not any("FIELD_OVERFLOW" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# Report adapter → the one VisualCompleteReport.
# --------------------------------------------------------------------------- #
def test_to_form_report_folds_results():
    engine = FitEngine()
    ok = engine.fit("홍길동", _slot(), FitPolicy(), field_id="name")
    bad = engine.fit(
        "가" * 40, _slot(width=5000),
        FitPolicy(mode="fail_on_overflow", overflow="fail"), field_id="addr",
    )
    report = to_form_report([ok, bad])
    assert report.ok is False
    assert len(report.fields) == 2
    assert report.fields[0]["fieldId"] == "name"
    assert any("FIELD_OVERFLOW" in e for e in report.errors)


def test_modest_vertical_overflow_shrinks_into_budget_when_possible():
    # Differential calibration round 2: the modest band is where pages
    # actually shift, so wrap_then_shrink must land INSIDE the height budget
    # instead of warning and letting the row grow.
    engine = FitEngine()
    # height=2400: 2 lines exceed the 1-line budget at 10pt (modest), but a
    # shrink to 7.5pt lands both lines fully inside the budget.
    before = _vslot(height=2400)
    result = engine.fit(
        "가" * 11, before, FitPolicy(mode="wrap_then_shrink", min_font_pt=6.0)
    )
    assert result.ok is True
    assert result.overflow_detected is False
    assert not any("row will grow" in w for w in result.warnings)
    assert result.font_pt is not None and result.font_pt < before.font_pt


def test_a_value_shrink_cannot_fit_in_the_row_fails():
    # height=1500 cannot hold two lines even at min font (two 6 pt lines take
    # 960 + 600): no false shrink claim, and no silent row growth.
    engine = FitEngine()
    result = engine.fit(
        "가" * 11, _vslot(height=1500), FitPolicy(mode="wrap_then_shrink", min_font_pt=6.0)
    )
    assert result.ok is False and result.overflow_detected
    assert any("FIELD_OVERFLOW" in e for e in result.errors)


def test_inline_control_width_narrows_slot_and_refuses_wrap() -> None:
    """A checkbox sharing the cell line consumes its declared
    width; a value that no longer fits must be a typed refusal, not a silent
    "fits" that grows the row and repaginates the form on real Hancom."""
    from hwpx.form_fit.measure import SlotMetrics

    slot = SlotMetrics(
        available_width=742.0,          # 7261 - 6519 checkbox, as measured
        font_pt=11.0,
        max_lines=1,
        available_height=1581.0,
        inline_object_width=6519.0,
        inline_object_count=1,
    )
    result = FitEngine().fit("김민준", slot, FitPolicy())
    assert not result.ok
    assert result.overflow_detected
    assert any("FIELD_OVERFLOW" in e for e in result.errors)
    assert any("inline control" in w for w in result.warnings)


def test_inline_object_width_measured_from_cell(tmp_path) -> None:
    from pathlib import Path

    from hwpx.document import HwpxDocument
    from hwpx.form_fit.measure import resolve_slot_metrics

    fixture = Path(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"
    doc = HwpxDocument.open(fixture)
    try:
        target = None
        for paragraph in doc.sections[0].paragraphs:
            for table in paragraph.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text = "".join(
                            getattr(p, "text", "") or ""
                            for p in getattr(cell, "paragraphs", [])
                        )
                        if text.strip() == "" and target is None:
                            target = cell
        assert target is not None
        slot = resolve_slot_metrics(target, doc, max_lines=1)
    finally:
        doc.close()
    assert slot.inline_object_count == 1
    assert slot.inline_object_width == 6519.0
    assert slot.available_width < 1000  # 7261 - 6519


def test_inline_control_consuming_whole_width_gets_named_refusal() -> None:
    from hwpx.form_fit.measure import SlotMetrics

    slot = SlotMetrics(
        available_width=0.0,
        font_pt=10.0,
        max_lines=1,
        inline_object_width=8000.0,
        inline_object_count=1,
    )
    result = FitEngine().fit("값", slot, FitPolicy())
    assert not result.ok and result.overflow_detected
    assert any("leave no usable width" in e for e in result.errors)


def test_a_cell_fit_that_fails_leaves_the_cell_as_it_was():
    from hwpx import HwpxDocument

    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.text = "원래 값"
    cell.element.find(f"{hp}cellSz").set("height", str(1600 + 1000 + 282))  # two 10 pt lines and the margins

    refused = table.set_cell_text(0, 0, "가" * 200, fit=FitPolicy(mode="wrap"))
    assert refused is not None and refused.ok is False
    assert cell.text == "원래 값"

    grown = table.set_cell_text(0, 0, "가" * 200, fit=FitPolicy(mode="wrap", allow_row_expand=True))
    assert grown is not None and grown.ok is True
    assert cell.text == "가" * 200


# --------------------------------------------------------------------------- #
# An auto-grow cell (stored height below one line) keeps the height of its row.
# --------------------------------------------------------------------------- #
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
_LONG = "두 줄로 넘치는 긴 값입니다 " * 5


def _drawn_end(cell) -> int:
    return max(
        int(line.get("vertpos")) + int(line.get("vertsize"))
        for line in cell.element.findall(f"{_HP}subList/{_HP}p/{_HP}linesegarray/{_HP}lineseg")
    )


def _auto_grow(name: str):
    from hwpx import HwpxDocument

    document = HwpxDocument.open((_HANCOM_SAVED / name).read_bytes())
    table = document.tables.all[0]
    return document, table, table.cell(0, 0)


def test_hancom_grows_an_auto_grow_cell_to_the_lines_it_draws():
    # Hancom saved a cell 500 high (below one 10 pt line) holding one line, and the same
    # cell after filling a longer value: the stored height stays, the row grows with the lines.
    _, _, saved = _auto_grow("auto_grow_cell_saved.hwpx")
    _, _, filled = _auto_grow("auto_grow_cell_filled.hwpx")

    assert (saved.element.find(f"{_HP}cellSz").get("height"), _drawn_end(saved)) == ("500", 1000)
    assert (filled.element.find(f"{_HP}cellSz").get("height"), _drawn_end(filled)) == ("500", 5800)


def test_an_auto_grow_cell_keeps_the_height_hancom_drew():
    document, table, cell = _auto_grow("auto_grow_cell_saved.hwpx")

    metrics = resolve_slot_metrics(cell, document)
    assert metrics.available_height is not None and metrics.height_lines() == 1

    refused = table.set_cell_text(0, 0, _LONG, fit=FitPolicy(mode="wrap"))
    assert refused is not None and refused.ok is False
    assert cell.text == "짧은 값"

    grown = table.set_cell_text(0, 0, _LONG, fit=FitPolicy(mode="wrap", allow_row_expand=True))
    assert grown is not None and grown.ok is True
    assert cell.text == _LONG


def test_an_auto_grow_cell_without_drawn_lines_holds_the_lines_of_its_text():
    from hwpx import HwpxDocument

    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "짧은 값"
    cell.element.find(f"{_HP}cellSz").set("height", "500")

    metrics = resolve_slot_metrics(cell, document)

    assert not metrics.height_unavailable
    assert metrics.available_height == 1000 and metrics.height_lines() == 1


_TWO_LINES = "두 줄에 들어가는 채울 값입니다"
_THREE_LINES = "세 줄로 넘치는 아주 긴 채울 값을 적어 넣습니다"


def _table_height(document) -> int:
    return int(document.tables.all[0].element.find(f"{_HP}sz").get("height"))


def test_hancom_draws_an_auto_grow_row_as_tall_as_its_tallest_cell():
    # Two cells stored 500 high: the first holds one line, the second two. Hancom
    # filled the first with a two-line value, then with a three-line one.
    saved, _, (first, second) = _auto_grow_row("auto_grow_row_saved.hwpx")
    two, _, (two_first, _) = _auto_grow_row("auto_grow_row_filled_two.hwpx")
    three, _, (three_first, _) = _auto_grow_row("auto_grow_row_filled_three.hwpx")

    assert (_drawn_end(first), _drawn_end(second), _table_height(saved)) == (1000, 2600, 2882)
    # Two lines in the first cell: the row stays as tall as the second cell.
    assert (_drawn_end(two_first), _table_height(two)) == (2600, 2882)
    # Three lines: the row grows.
    assert (_drawn_end(three_first), _table_height(three)) == (4200, 4482)


def _auto_grow_row(name: str):
    from hwpx import HwpxDocument

    document = HwpxDocument.open((_HANCOM_SAVED / name).read_bytes())
    table = document.tables.all[0]
    return document, table, (table.cell(0, 0), table.cell(0, 1))


def test_an_auto_grow_cell_holds_as_many_lines_as_its_row():
    document, table, (first, _) = _auto_grow_row("auto_grow_row_saved.hwpx")
    assert resolve_slot_metrics(first, document).height_lines() == 2

    kept = table.set_cell_text(0, 0, _TWO_LINES, fit=FitPolicy())
    assert kept is not None and kept.ok is True and kept.lines == 2
    assert not kept.applied_style_changes.get("font_pt")

    document, table, _ = _auto_grow_row("auto_grow_row_saved.hwpx")
    refused = table.set_cell_text(0, 0, _THREE_LINES, fit=FitPolicy())
    assert refused is not None and refused.ok is False
    assert any("FIELD_OVERFLOW" in error for error in refused.errors)


def test_hancom_draws_a_row_as_tall_as_lines_that_run_past_its_stored_height():
    # One cell stored 2000 high (room for one 10 pt line inside) holding two lines; then Hancom filled it
    # with another two-line value and with a three-line one.
    saved, _, (cell, _other) = _overflow_row("overflow_row_saved.hwpx")
    two, _, (two_cell, _) = _overflow_row("overflow_row_filled_two.hwpx")
    three, _, (three_cell, _) = _overflow_row("overflow_row_filled_three.hwpx")

    assert [c.element.find(f"{_HP}cellSz").get("height") for c in (cell, two_cell, three_cell)] == ["2000"] * 3
    assert (_drawn_end(cell), _table_height(saved)) == (2600, 2882)
    assert (_drawn_end(two_cell), _table_height(two)) == (2600, 2882)
    assert (_drawn_end(three_cell), _table_height(three)) == (4200, 4482)


def _overflow_row(name: str):
    from hwpx import HwpxDocument

    document = HwpxDocument.open((_HANCOM_SAVED / name).read_bytes())
    table = document.tables.all[0]
    return document, table, (table.cell(0, 0), None)


def test_a_row_whose_lines_run_past_its_stored_height_holds_them():
    document, table, (cell, _) = _overflow_row("overflow_row_saved.hwpx")
    assert resolve_slot_metrics(cell, document).height_lines() == 2

    kept = table.set_cell_text(0, 0, _TWO_LINES, fit=FitPolicy())
    assert kept is not None and kept.ok is True and kept.lines == 2
    assert not kept.applied_style_changes.get("font_pt")

    document, table, _ = _overflow_row("overflow_row_saved.hwpx")
    refused = table.set_cell_text(0, 0, _THREE_LINES, fit=FitPolicy())
    assert refused is not None and refused.ok is False


def test_an_auto_grow_row_without_drawn_lines_is_as_tall_as_its_measured_text():
    document, table, (first, _) = _auto_grow_row("auto_grow_row_saved.hwpx")
    for paragraph in table.element.iter(f"{_HP}p"):
        for cache in paragraph.findall(f"{_HP}linesegarray"):
            paragraph.remove(cache)

    # The second cell's text measures two lines, as Hancom laid it out.
    metrics = resolve_slot_metrics(first, document)
    assert metrics.available_height == 2600 and metrics.height_lines() == 2
