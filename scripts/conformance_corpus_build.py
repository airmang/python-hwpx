# SPDX-License-Identifier: Apache-2.0
"""Build the bundled *public* conformance corpus (plan §2 Phase G).

One-off authoring step (re-runnable): emits a handful of small, dependency-light
``.hwpx`` documents — all python-hwpx outputs, so the structural tiers (Open /
Semantic / Form-measurement) run on them in any CI with no Hancom — plus the
``corpus.json`` manifest that declares each case's badge expectations.

The *private* oracle corpus (real Hancom-saved 신청서/공문, the only honest input
for the VisualComplete tier) is intentionally NOT built here: it stays out of the
repo and is pointed at via ``hwpx-conformance run --corpus <path> --tier oracle``.

Run::

    python scripts/conformance_corpus_build.py
"""
from __future__ import annotations

import json
from pathlib import Path

from hwpx import HwpxDocument

CORPUS_DIR = Path(__file__).resolve().parents[1] / "src" / "hwpx" / "conformance" / "corpus"


def _notice() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("2026학년도 학교 운영 계획 알림")
    doc.add_paragraph("학부모님께 다음과 같이 운영 계획을 안내합니다.")
    doc.add_paragraph("가정의 평안과 건강을 기원합니다.")
    return doc.to_bytes()


def _report_table() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("분기 실적 보고")
    table = doc.add_table(2, 3, width=42000)
    header = ["구분", "내용", "비고"]
    body = ["매출", "1억원", "달성"]
    for col, value in enumerate(header):
        table.cell(0, col).text = value
    for col, value in enumerate(body):
        table.cell(1, col).text = value
    return doc.to_bytes()


def _plain() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("회의 결과 요약")
    doc.add_paragraph("참석자 전원이 안건에 동의하였습니다.")
    return doc.to_bytes()


CASES = [
    {
        "builder": _notice,
        "filename": "notice.hwpx",
        "case": {
            "id": "public-notice",
            "path": "notice.hwpx",
            "mustContain": ["운영 계획", "안내"],
            "mustNotContain": ["{{"],
            "note": "official-notice style body; open + semantic tiers",
        },
    },
    {
        "builder": _report_table,
        "filename": "report_table.hwpx",
        "case": {
            "id": "public-report-table",
            "path": "report_table.hwpx",
            "mustContain": ["분기 실적", "매출"],
            "formSlots": [
                {"table": 0, "row": 1, "col": 1, "value": "1억원", "maxLines": 1, "label": "매출-값"},
                {"table": 0, "row": 1, "col": 0, "value": "매출", "maxLines": 1, "label": "구분-값"},
            ],
            "note": "table body; open + semantic + form-fit tiers",
        },
    },
    {
        "builder": _plain,
        "filename": "meeting_summary.hwpx",
        "case": {
            "id": "public-meeting-summary",
            "path": "meeting_summary.hwpx",
            "mustContain": ["회의 결과", "참석자"],
            "note": "plain body; open + semantic tiers",
        },
    },
]


def main() -> int:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "public",
        "cases": [entry["case"] for entry in CASES],
    }
    for entry in CASES:
        data = entry["builder"]()
        (CORPUS_DIR / entry["filename"]).write_bytes(data)
        print(f"wrote {entry['filename']} ({len(data)} bytes)")
    (CORPUS_DIR / "corpus.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote corpus.json ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
