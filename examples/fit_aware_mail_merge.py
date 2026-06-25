#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Fit-aware batch fill with per-record isolation (M2 / FR-004).

Builds a one-cell 안내 template whose ``{{contact}}`` lives in a narrow table cell,
then mail-merges a 3-row roster through it with a ``FitPolicy``. The value that would
overflow its cell and the row missing a required field are isolated into
``needsReview`` / (with ``strict``) ``skipped`` — the clean row is untouched. No
Hancom oracle is needed: slots are measured once from the template with the
advance model (``template-once-measure``).

Run:  python examples/fit_aware_mail_merge.py
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hwpx.document import HwpxDocument
from hwpx.form_fit import FitPolicy
from hwpx.tools.mail_merge import mail_merge


def build_template(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("수신자 안내 — {{title}}")
    table = doc.add_paragraph("").add_table(1, 2)
    table.cell(0, 0).set_text("연락처")
    cell = table.cell(0, 1)
    cell.set_size(width=3500)          # a deliberately narrow (~3 CJK) cell
    cell.set_text("{{contact}}")
    doc.save_to_path(path)


def main() -> None:
    roster = [
        {"title": "협조", "contact": "총무과"},                       # fits
        {"title": "협조", "contact": "행정안전부 자료관리과 정보화담당관실 통계조사팀"},  # overflows
        {"title": "협조", "contact": ""},                              # missing required
    ]
    with TemporaryDirectory() as tmp:
        template = Path(tmp) / "template.hwpx"
        build_template(template)
        report = mail_merge(
            template, roster,
            output_dir=Path(tmp) / "out",
            fit_policy=FitPolicy.keep(),   # detect + isolate overflow; never truncate
            strict=False,
        )

        print(f"rows={report['rowCount']} created={report['createdCount']} "
              f"fitAware={report['fitAware']} measuredSlots={report['measuredSlots']}")
        for r in report["needsReview"]:
            print(f"  needsReview row {r['rowIndex']}: reasons={r['reasons']}")
        for r in report["skipped"]:
            print(f"  skipped   row {r['rowIndex']}: reasons={r['reasons']}")
        clean = [r["rowIndex"] for r in report["rows"]
                 if r["created"] and not r["reasons"]]
        print(f"  clean rows (no review needed): {clean}")


if __name__ == "__main__":
    main()
