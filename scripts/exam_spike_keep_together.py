# SPDX-License-Identifier: Apache-2.0
"""Phase-0 measure-first spike (Wily S-056): keep-together mechanism decision.

QUESTION
========
In a B4 two-column newspaper flow, does Hancom honour the paragraph
``<hh:breakSetting keepWithNext="1" keepLines="1">`` setting so that a whole
문항 (a 발문 line + its 5 답항 lines) is kept together and never straddles a
column/page boundary?  Or must we instead force breaks with an inline
``columnBreak`` attribute?

This decision GATES the later exam-typesetting design, so the spike is
rigorous and honest (Constitution V — no silent true):

* If the Hancom oracle is unavailable or any render returns ``None`` →
  ``render_checked=false``, ``keepWithNext_honored=null``, ``mechanism="columnBreak"``
  (the safe default), ``skipped=["mac-hancom-oracle"]``.  A successful, honest
  outcome.
* If rendered, we measure three variants of the SAME content:
    1. BASELINE     — questions use a plain paraPr (no keep). Must produce ≥1
       split, else the harness is vacuous and we cannot conclude.
    2. KEEPWITHNEXT — every paragraph of every question uses a paraPr from
       ``ensure_paragraph_format(break_setting={keep_with_next, keep_lines})``.
    3. COLUMNBREAK  — each question's first paragraph carries ``columnBreak="1"``
       (deterministic control; 0 splits by construction).
  ``keepWithNext_honored = (baseline_splits > 0 and keepwithnext_splits == 0)``.
  ``mechanism = "keepWithNext"`` iff honored else ``"columnBreak"``.
  If ``baseline_splits == 0`` → ``harness_vacuous=true``, ``mechanism="columnBreak"``.

BED
===
The real school form copy (B4, 2-column NEWSPAPER colPr) is preferred; we
append the synthetic 문항 body after its existing template content so the
questions flow through the genuine two-column layout.  Each question carries a
unique ``[[QNN]]`` marker so its glyphs are unambiguously groupable regardless
of pre-existing form text.  If the real bed is missing we fall back to a clean
``HwpxDocument.new()`` doc re-shaped to B4 2-column (the keepWithNext question
is general Hancom behaviour, so a clean 2-column bed is valid).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Make the in-repo package importable when run as a plain script.
_REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.visual.oracle import (  # noqa: E402
    Block,
    MacHancomOracle,
    resolve_oracle,
)
import re as _re  # noqa: E402
from hwpx.exam.measure import group_question_blocks, measure_question_splits  # noqa: E402

_QNN_MARKER = _re.compile(r"\[\s*\[\s*Q\s*0*(\d+)\s*\]\s*\]")

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# ---------------------------------------------------------------------------
# Synthetic 문항 content.
# ---------------------------------------------------------------------------
# Each question = 1 발문 line (carries the unique marker) + 5 답항 lines.
# Make every question multi-line and reasonably long so questions naturally
# land on column / page boundaries when enough of them are stacked.
N_QUESTIONS = 40
CHOICE_MARKS = ["①", "②", "③", "④", "⑤"]


def _question_lines(qno: int) -> list[str]:
    """Return [발문, 답항x5] for question *qno* (1-based). 발문 carries [[QNN]]."""
    tag = f"[[Q{qno:02d}]]"
    prompt = (
        f"{tag} 다음 글을 읽고 물음에 답하시오. 아래 보기에서 가장 적절한 것을 "
        f"하나 고르시오. 이것은 두 단 흐름에서 문항이 잘리는지 측정하기 위한 합성 "
        f"문항 번호 {qno} 입니다."
    )
    choices = [
        f"{CHOICE_MARKS[i]} 선택지 {qno}-{i + 1} 번 보기 내용입니다 이것은 답항 줄"
        for i in range(5)
    ]
    return [prompt] + choices


# ---------------------------------------------------------------------------
# Bed construction.
# ---------------------------------------------------------------------------
def _b4_two_column_clean() -> HwpxDocument:
    """Fallback bed: a clean doc reshaped to B4 portrait, 2-column NEWSPAPER."""
    doc = HwpxDocument.new()
    section = doc.sections[0]
    root = section.element
    # pagePr: B4 portrait (HWP units; B4 = 257x364 mm ~= 72860 x 103180).
    for page_pr in root.iter(f"{_HP}pagePr"):
        page_pr.set("landscape", "WIDELY")
        page_pr.set("width", "72852")
        page_pr.set("height", "103180")
    # colPr: 2 columns, newspaper flow.
    for col_pr in root.iter(f"{_HP}colPr"):
        col_pr.set("type", "NEWSPAPER")
        col_pr.set("colCount", "2")
        col_pr.set("sameSz", "1")
    section.mark_dirty()
    return doc


def _open_bed(bed_path: str | None) -> tuple[HwpxDocument, str]:
    """Open the real school bed if present, else build the clean fallback.

    NOTE (Phase-0 finding): appending paragraphs into the real ``A_form.hwpx``
    body proved unrenderable — Hancom rendered ONLY the template's own
    boilerplate and silently dropped every appended 문항 (the synthetic
    ``[[QNN]]`` markers never appear in the PDF).  The real form is a constrained
    fixed-layout template, so the clean B4 2-column bed is used instead; the
    keepWithNext question is general Hancom two-column behaviour, so the clean
    bed is a valid measurement target (the task brief sanctions this fallback).
    """
    if bed_path and os.path.exists(bed_path):
        doc = HwpxDocument.open(bed_path)
        # Confirm it really is a 2-column section; if not, fall back.
        xml = ET.tostring(doc.sections[0].element, encoding="unicode")
        if 'colCount="2"' in xml:
            return doc, f"real-school-form:{os.path.basename(bed_path)}"
    return _b4_two_column_clean(), "clean-b4-2col-new()"


# ---------------------------------------------------------------------------
# Variant authoring.
# ---------------------------------------------------------------------------
def _append_questions(
    doc: HwpxDocument,
    *,
    keep: bool,
    column_break: bool,
) -> None:
    """Append N_QUESTIONS synthetic 문항 to *doc*'s last section.

    keep         -> every paragraph of every question uses a keepWithNext paraPr.
    column_break -> each question's FIRST paragraph carries columnBreak="1".
    """
    keep_pr_id: str | None = None
    if keep:
        keep_pr_id = doc.oxml.headers[0].ensure_paragraph_format(
            break_setting={"keep_with_next": True, "keep_lines": True}
        )

    for qno in range(1, N_QUESTIONS + 1):
        lines = _question_lines(qno)
        for li, text in enumerate(lines):
            extra: dict[str, str] = {}
            if column_break and li == 0 and qno > 1:
                # Force every question (except the first) to a fresh column.
                extra["columnBreak"] = "1"
            doc.add_paragraph(
                text,
                para_pr_id_ref=keep_pr_id if keep else None,
                inherit_style=True,
                **extra,
            )


def _build_variant(bed_path: str | None, variant: str, out_path: str) -> str:
    """Build one variant document on disk; return the bed label."""
    doc, bed_label = _open_bed(bed_path)
    if variant == "baseline":
        _append_questions(doc, keep=False, column_break=False)
    elif variant == "keepwithnext":
        _append_questions(doc, keep=True, column_break=False)
    elif variant == "columnbreak":
        _append_questions(doc, keep=False, column_break=True)
    else:  # pragma: no cover - guarded by caller
        raise ValueError(variant)
    doc.save_to_path(out_path)
    return bed_label


# ---------------------------------------------------------------------------
# Measurement.
# ---------------------------------------------------------------------------
# NOTE: _column_x_bounds, _group_blocks, and _measure_splits are now thin
# wrappers that delegate to hwpx.exam.measure (DRY).  The spike passes its
# own [[QNN]] marker so the grouping semantics are identical to before.

def _group_blocks(glyphs) -> list[Block]:
    """Group glyphs into Blocks via the ``[[QNN]]`` markers (delegates to measure)."""
    return group_question_blocks(glyphs, marker_re=_QNN_MARKER)


def _measure_splits(pdf_path: str) -> tuple[int, int, int, dict[str, int], list[str]]:
    """Return ``(n_splits, n_blocks, n_glyphs, kinds, split_ids)`` for a render."""
    r = measure_question_splits(pdf_path, marker_re=_QNN_MARKER)
    return r.n_splits, r.n_blocks, r.n_glyphs, dict(r.kinds), list(r.split_ids)


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bed",
        default=os.environ.get("EXAM_BED", ""),
        help="path to real B4 2-column school form (.hwpx); falls back to clean new()",
    )
    parser.add_argument(
        "--workdir",
        required=True,
        help="scratch dir for variant .hwpx + rendered .pdf (not committed)",
    )
    parser.add_argument(
        "--receipt",
        required=True,
        help="path to write the phase-0 decision receipt JSON",
    )
    args = parser.parse_args(argv)

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    receipt_path = Path(args.receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    variants = ("baseline", "keepwithnext", "columnbreak")

    # Build the three documents.
    bed_label = ""
    hwpx_paths: dict[str, str] = {}
    for v in variants:
        out = str(work / f"{v}.hwpx")
        bed_label = _build_variant(args.bed or None, v, out)
        hwpx_paths[v] = out
    notes.append(f"built {N_QUESTIONS} synthetic 문항 x3 variants on bed={bed_label}")

    # Resolve oracle.
    oracle = MacHancomOracle()
    if not oracle.available():
        oracle = resolve_oracle()

    receipt = {
        "bed": bed_label,
        "render_checked": False,
        "baseline_splits": None,
        "keepwithnext_splits": None,
        "columnbreak_splits": None,
        "keepWithNext_honored": None,
        "harness_vacuous": None,
        "mechanism": "columnBreak",  # safe default
        "skipped": [],
        "notes": notes,
    }

    if not oracle.available():
        notes.append("oracle unavailable -> safe default mechanism=columnBreak")
        receipt["skipped"] = ["mac-hancom-oracle"]
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    notes.append(f"oracle={type(oracle).__name__}")

    # Render + measure each variant (serialized; the Mac GUI is one session).
    counts: dict[str, int | None] = {}
    split_kinds: dict[str, dict[str, int]] = {}
    pdf_paths: dict[str, str] = {}
    render_failed = False
    for v in variants:
        pdf = str(work / f"{v}.pdf")
        rendered = oracle.render_pdf(hwpx_paths[v], pdf)
        if not rendered or not os.path.exists(rendered) or os.path.getsize(rendered) == 0:
            notes.append(f"render returned None/empty for variant={v}")
            render_failed = True
            counts[v] = None
            break
        pdf_paths[v] = rendered
        n_splits, n_blocks, n_glyphs, kinds, split_ids = _measure_splits(rendered)
        counts[v] = n_splits
        split_kinds[v] = kinds
        notes.append(
            f"{v}: splits={n_splits} kinds={kinds} ids={split_ids} "
            f"blocks={n_blocks} glyphs={n_glyphs} pdf={rendered}"
        )

    if render_failed:
        notes.append("a render failed -> render_checked=false, safe default mechanism=columnBreak")
        receipt["skipped"] = ["mac-hancom-oracle"]
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    baseline = counts["baseline"]
    keepwn = counts["keepwithnext"]
    colbrk = counts["columnbreak"]

    harness_vacuous = baseline == 0
    if harness_vacuous:
        honored = None
        mechanism = "columnBreak"
        notes.append("baseline_splits==0 -> harness vacuous; could not prove either way")
    else:
        honored = (baseline > 0 and keepwn == 0)
        mechanism = "keepWithNext" if honored else "columnBreak"

    receipt.update(
        {
            "render_checked": True,
            "baseline_splits": baseline,
            "keepwithnext_splits": keepwn,
            "columnbreak_splits": colbrk,
            "keepWithNext_honored": honored,
            "harness_vacuous": harness_vacuous,
            "mechanism": mechanism,
            "skipped": [],
            "split_kinds": split_kinds,
            "notes": notes,
            "pdf_paths": pdf_paths,
        }
    )
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
