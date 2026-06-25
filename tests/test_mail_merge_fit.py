# SPDX-License-Identifier: Apache-2.0
"""Fit-aware batch fill with per-record isolation (M2 P4 / FR-004).

The shipped ``mail_merge`` inserts values raw. P4 adds a ``fit_policy``: each
placeholder's slot is measured **once** from the template (template-once-measure,
advance-model — no per-record oracle), then every record's value is fit against it.
A value that would overflow its slot, or a row missing a required field, is
**isolated** into ``needsReview[]`` / ``skipped[]`` with a reason — never silently
mangled, and never corrupting the rest of the batch.
"""
from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.form_fit import FitPolicy
from hwpx.tools.mail_merge import mail_merge

CLEAN = "홍길동"
OVERFLOW = "아주아주아주아주아주긴이름입니다정말로깁니다"  # >> a 3-CJK-wide cell


def _template(path: Path) -> None:
    """A form whose {{name}} sits in a narrow (~3 CJK) table cell."""
    doc = HwpxDocument.new()
    doc.add_paragraph("수신자 안내 — {{title}}")
    table = doc.add_paragraph("").add_table(1, 2)
    table.cell(0, 0).set_text("이름")
    value_cell = table.cell(0, 1)
    value_cell.set_size(width=3500)
    value_cell.set_text("{{name}}")
    doc.save_to_path(path)


def _roster():
    return [
        {"title": "협조", "name": CLEAN},      # fits
        {"title": "협조", "name": OVERFLOW},   # overflows the narrow cell
        {"title": "협조", "name": ""},          # missing required
    ]


def _by_index(items, idx):
    return next((it for it in items if it["rowIndex"] == idx), None)


def test_fit_aware_batch_isolates_overflow_into_needs_review(tmp_path):
    template = tmp_path / "template.hwpx"
    _template(template)
    report = mail_merge(
        template,
        _roster(),
        output_dir=tmp_path / "out",
        fit_policy=FitPolicy.keep(),
        strict=False,
    )

    # row 1 (clean) is created and NOT flagged
    assert 1 not in [r["rowIndex"] for r in report["needsReview"]]
    assert 1 not in [r["rowIndex"] for r in report["skipped"]]
    row1 = _by_index(report["rows"], 1)
    assert row1["created"] is True and Path(row1["filename"]).exists()

    # row 2 (overflow) lands in needsReview with an 'overflow' reason
    nr2 = _by_index(report["needsReview"], 2)
    assert nr2 is not None
    assert "overflow" in nr2["reasons"]

    # row 3 (missing required, non-strict) is flagged for review, not silently OK
    nr3 = _by_index(report["needsReview"], 3)
    assert nr3 is not None and "missing_required" in nr3["reasons"]

    # the batch is not corrupted: every row still produced a file
    assert report["createdCount"] == 3


def test_fit_aware_batch_strict_skips_missing_required(tmp_path):
    template = tmp_path / "template.hwpx"
    _template(template)
    report = mail_merge(
        template,
        _roster(),
        output_dir=tmp_path / "out_strict",
        fit_policy=FitPolicy.keep(),
        strict=True,
    )
    sk = _by_index(report["skipped"], 3)
    assert sk is not None and "missing_required" in sk["reasons"]
    row3 = _by_index(report["rows"], 3)
    assert row3["created"] is False  # not generated


def test_fit_measures_narrowest_cell_when_token_in_multiple(tmp_path):
    # the same {{x}} sits in a wide AND a narrow cell; template-once-measure must use
    # the *narrowest* slot so a value that fits the wide one but not the narrow one is
    # still flagged (conservative — if it fits the narrowest it fits all).
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(1, 2)
    wide = table.cell(0, 0)
    wide.set_size(width=40000)
    wide.set_text("{{x}}")
    narrow = table.cell(0, 1)
    narrow.set_size(width=3000)
    narrow.set_text("{{x}}")
    template = tmp_path / "multi.hwpx"
    doc.save_to_path(template)

    report = mail_merge(
        template,
        [{"x": "홍길동홍길동"}],  # fits 40000 but overflows ~3000
        output_dir=tmp_path / "out",
        fit_policy=FitPolicy.keep(),
    )
    assert report["needsReview"], "narrowest slot should have flagged the overflow"
    assert "overflow" in report["needsReview"][0]["reasons"]


def test_no_fit_policy_keeps_raw_behaviour_and_empty_isolation(tmp_path):
    template = tmp_path / "template.hwpx"
    _template(template)
    report = mail_merge(
        template,
        [{"title": "협조", "name": OVERFLOW}],
        output_dir=tmp_path / "out_raw",
        strict=False,
    )
    # without a fit_policy nothing is measured, so overflow is not flagged
    assert report["needsReview"] == []
    assert report["rows"][0]["created"] is True
