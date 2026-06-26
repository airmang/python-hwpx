# python-hwpx/scripts/exam_profile_a_form.py
# SPDX-License-Identifier: Apache-2.0
"""Measure-first probe (S-056 Plan 2): characterize A_form's body region.

Prints, for section 0 of the school form, every paragraph's (index, style id,
style name, text head); then derives the replaceable body range vs the
관리박스 / structural / footer paragraphs and writes an evidence receipt.
No assumptions — the composer's body-region rule is grounded by THIS output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hwpx.document import HwpxDocument  # noqa: E402

# Style names the form uses for replaceable question/answer body content
# (recon, identical in A and B). Anything else in the body is structural.
REPLACEABLE_NAMES = {
    "바탕글", "문항자동번호넣기",
    "1행답항", "2행답항", "3행답항", "5행답항",
    "(보기)박스안내용", "박스안내용",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--form", default="tests/fixtures/exam/A_form.hwpx")
    ap.add_argument("--receipt", default="../specs/003-exam-typesetting/evidence/a-form-body-map.json")
    args = ap.parse_args(argv)

    doc = HwpxDocument.open(args.form)
    section = doc.sections[0]
    rows = []
    for idx, para in enumerate(section.paragraphs):
        sid = para.style_id_ref
        style = doc.style(sid) if sid is not None else None
        name = style.name if style else None
        rows.append(
            {
                "index": idx,
                "style_id": sid,
                "style_name": name,
                "text_head": (para.text or "")[:40],
            }
        )

    repl = [r["index"] for r in rows if r["style_name"] in REPLACEABLE_NAMES]
    body_start = min(repl) if repl else None
    body_end = max(repl) if repl else None
    structural = [
        r["index"]
        for r in rows
        if body_start is not None and body_start <= r["index"] <= body_end
        and r["style_name"] not in REPLACEABLE_NAMES
    ]
    receipt = {
        "form": args.form,
        "n_sections": len(doc.sections),
        "n_paragraphs_section0": len(rows),
        "admin_box_index": 0,
        "body_start": body_start,
        "body_end": body_end,
        "footer_indices": [r["index"] for r in rows if body_end is not None and r["index"] > body_end],
        "structural_indices_in_body": structural,
        "replaceable_style_names": sorted(REPLACEABLE_NAMES),
        "paragraphs": rows,
    }
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in receipt if k != "paragraphs"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
