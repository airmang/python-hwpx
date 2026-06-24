# SPDX-License-Identifier: Apache-2.0
"""Conformance runner + ``hwpx-conformance`` CLI (plan §2 Phase G).

``run_conformance`` walks a :class:`~hwpx.conformance.corpus.ConformanceCorpus`,
evaluates each case across the four badge tiers, and aggregates a
:class:`~hwpx.conformance.report.ConformanceReport`. Two run tiers, matching the
§0.0 oracle boundary:

* ``structural`` — Open-Safe / Semantic-Safe / Form-Safe(measurement). No Hancom,
  no imaging stack; runs in any CI. VisualComplete is recorded ``unverified``.
* ``oracle`` — additionally renders every doc through a reachable Hancom backend
  and judges VisualComplete. Dev / spot-check (Mac) or CI-at-scale (Windows COM).

Each tier evaluator reuses the engine that already ships: open-safety from
``tools.package_validator``, text from ``tools.text_extractor``, fit from
``form_fit.measure``, render from ``visual.oracle`` — the conformance layer only
*scores a population*, it does not re-implement any check.

CLI::

    hwpx-conformance run [--corpus corpus.json] [--tier structural|oracle]
                         [--out report/] [--check golden.json] [--update-golden golden.json]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .badges import BadgeThresholds, evaluate_badges
from .corpus import BADGE_TIERS, ConformanceCase, ConformanceCorpus
from .report import CaseResult, ConformanceReport, RunTier, TierVerdict, diff_golden


# --------------------------------------------------------------------------- #
# Tier evaluators (each returns one TierVerdict; "skip" when not applicable).
# --------------------------------------------------------------------------- #
def _eval_open_safe(data: bytes, case: ConformanceCase) -> TierVerdict:
    from hwpx.tools.package_validator import validate_editor_open_safety

    report = validate_editor_open_safety(data)
    if not case.expect_open_safe:
        # A negative case: the doc is *expected* to be open-unsafe; passing means
        # the validator agrees it is unsafe (a guard against the validator going
        # blind). Such cases stay out of the public corpus but are supported.
        status = "pass" if not report.ok else "fail"
        return TierVerdict("open_safe", status, f"expected unsafe; ok={report.ok}")
    status = "pass" if report.ok else "fail"
    return TierVerdict("open_safe", status, report.summary)


def _eval_semantic(data: bytes, case: ConformanceCase) -> TierVerdict:
    if not case.must_contain and not case.must_not_contain:
        return TierVerdict("semantic_safe", "skip", "no assertions")

    from hwpx.tools.text_extractor import TextExtractor

    with TextExtractor(io.BytesIO(data)) as extractor:
        text = extractor.extract_text()
    missing = [needle for needle in case.must_contain if needle not in text]
    forbidden = [needle for needle in case.must_not_contain if needle in text]
    ok = not missing and not forbidden
    detail_parts = []
    if missing:
        detail_parts.append("missing: " + ", ".join(missing))
    if forbidden:
        detail_parts.append("forbidden present: " + ", ".join(forbidden))
    return TierVerdict(
        "semantic_safe",
        "pass" if ok else "fail",
        "; ".join(detail_parts) or "all assertions held",
        metrics={"missing": missing, "forbidden": forbidden},
    )


def _eval_form_safe(data: bytes, case: ConformanceCase) -> TierVerdict:
    if not case.required_fields and not case.form_slots:
        return TierVerdict("form_safe", "skip", "no form expectations")

    from hwpx.document import HwpxDocument
    from hwpx.form_fit import measure, resolve_slot_metrics

    overflow = 0
    low_confidence = 0
    checked = 0
    missing_required: list[str] = []
    notes: list[str] = []

    document = HwpxDocument.open(io.BytesIO(data))
    try:
        if case.required_fields:
            by_name = {
                str(f.get("name") or f.get("field_id") or ""): f
                for f in document.list_form_fields()
            }
            for name in case.required_fields:
                field = by_name.get(name)
                if field is None or not str(field.get("current_value", "")).strip():
                    missing_required.append(name)

        if case.form_slots:
            tables = [t for para in document.paragraphs for t in para.tables]
            for slot in case.form_slots:
                if slot.table >= len(tables):
                    notes.append(f"slot table {slot.table} out of range")
                    overflow += 1  # an unresolvable declared slot is a hard miss
                    checked += 1
                    continue
                cell = tables[slot.table].cell(slot.row, slot.col)
                value = slot.value if slot.value is not None else cell.text
                metrics = resolve_slot_metrics(
                    cell, document, max_lines=slot.max_lines
                )
                measurement = measure(value, metrics)
                checked += 1
                if measurement.overflow:
                    # Honour the FormFit honesty contract (plan §2 C): only a
                    # high-confidence overflow is a real miss; a borderline one
                    # defers to the oracle and is a warning, not a fail.
                    if measurement.confidence == "high":
                        overflow += 1
                    else:
                        low_confidence += 1
                        notes.append(
                            f"slot {slot.label or (slot.row, slot.col)}: "
                            "borderline overflow (oracle should confirm)"
                        )
    finally:
        document.close()

    ok = not missing_required and overflow == 0
    detail_parts = []
    if missing_required:
        detail_parts.append("required missing: " + ", ".join(missing_required))
    if overflow:
        detail_parts.append(f"{overflow} slot(s) overflow")
    detail_parts.extend(notes)
    return TierVerdict(
        "form_safe",
        "pass" if ok else "fail",
        "; ".join(detail_parts) or f"{checked} slot(s) fit",
        metrics={
            "checked": checked,
            "overflow_count": overflow,
            "low_confidence": low_confidence,
            "missing_required": missing_required,
        },
    )


def _eval_visual(
    corpus: ConformanceCorpus, case: ConformanceCase, oracle: Any | None
) -> TierVerdict:
    if oracle is None or not oracle.available():
        return TierVerdict(
            "visual_complete", "unverified", "no Hancom oracle reachable"
        )

    from hwpx.visual.oracle import visual_check

    after = corpus.path_for(case)
    before = corpus.root / case.before if case.before else None
    edit_mask = case.build_edit_mask()

    with tempfile.TemporaryDirectory(prefix="hwpx-conformance-") as work:
        report = visual_check(
            str(before) if before is not None else None,
            str(after),
            oracle=oracle,
            edit_mask=edit_mask,
            work_dir=work,
        )
    if not report.render_checked:
        return TierVerdict(
            "visual_complete",
            "unverified",
            "; ".join(report.warnings) or "render not checked",
        )

    flags = [
        label
        for label, flag in (
            ("overlap", report.overlap_detected),
            ("overflow", report.overflow_detected),
            ("out-of-mask change", report.unexpected_diff_outside_mask),
            ("table-break", report.table_break_detected),
            ("page-count change", report.page_count_changed),
        )
        if flag
    ]
    defect = not report.ok

    if case.expect_visual_defect:
        # Positive control: the gate must *catch* the planted defect.
        status = "pass" if defect else "fail"
        detail = (
            "defect correctly caught (" + "; ".join(flags) + ")"
            if defect
            else "EXPECTED a visual defect but the oracle saw none"
        )
        return TierVerdict(
            "visual_complete", status, detail, metrics={"checked": 1, "expected_defect": True}
        )

    status = "pass" if not defect else "fail"
    if before is None:
        # Conservative single-render pass: confirms faithful rasterisation +
        # stable pagination only; overlap/overflow need a before baseline.
        detail = "; ".join(flags) or "single-render faithful (no before/mask diff)"
    else:
        detail = "; ".join(flags) or "before/after diff clean (oracle-verified)"
    return TierVerdict(
        "visual_complete",
        status,
        detail,
        metrics={
            "overflow_count": 1 if report.overflow_detected else 0,
            "checked": 1,
            "diffed": before is not None,
        },
    )


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def evaluate_case(
    corpus: ConformanceCorpus,
    case: ConformanceCase,
    *,
    tier: RunTier,
    oracle: Any | None,
) -> CaseResult:
    """Evaluate one case across the four tiers."""

    path = corpus.path_for(case)
    data = path.read_bytes()

    verdicts: dict[str, TierVerdict] = {}
    verdicts["open_safe"] = _eval_open_safe(data, case)
    verdicts["semantic_safe"] = _eval_semantic(data, case)
    verdicts["form_safe"] = _eval_form_safe(data, case)
    if tier == "oracle":
        verdicts["visual_complete"] = _eval_visual(corpus, case, oracle)
    else:
        verdicts["visual_complete"] = TierVerdict(
            "visual_complete", "unverified", "structural tier (no render)"
        )

    return CaseResult(
        case_id=case.id,
        visibility=case.visibility,
        verdicts={t: verdicts[t] for t in BADGE_TIERS},
    )


def run_conformance(
    corpus: ConformanceCorpus,
    *,
    tier: RunTier = "structural",
    oracle: Any | None = None,
    thresholds: BadgeThresholds | None = None,
) -> ConformanceReport:
    """Evaluate *corpus* and aggregate badge verdicts.

    For ``tier="oracle"`` with no explicit *oracle*, the best reachable Hancom
    backend is resolved; if none is reachable VisualComplete stays ``unverified``
    and the run degrades to structural assurance with a warning (it never raises).
    """

    if tier == "oracle" and oracle is None:
        from hwpx.visual.oracle import resolve_oracle

        oracle = resolve_oracle()

    results = [
        evaluate_case(corpus, case, tier=tier, oracle=oracle)
        for case in corpus.cases
    ]
    badges = evaluate_badges(results, thresholds)
    render_checked = any(
        result.verdicts["visual_complete"].status in ("pass", "fail")
        for result in results
    )
    return ConformanceReport(
        tier=tier,
        render_checked=render_checked,
        cases=results,
        badges=badges,
        corpus_name=corpus.name,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hwpx-conformance",
        description="Score an HWPX corpus into VisualComplete badge tiers (plan §2 G).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the conformance suite over a corpus")
    run.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="path to a corpus.json manifest (default: the bundled public corpus)",
    )
    run.add_argument(
        "--tier",
        choices=("structural", "oracle"),
        default="structural",
        help="structural (no Hancom) or oracle (render via Hancom)",
    )
    run.add_argument("--out", type=Path, default=None, help="write report.json + report.md here")
    run.add_argument(
        "--check",
        type=Path,
        default=None,
        help="compare against a golden baseline; non-zero exit on regression",
    )
    run.add_argument(
        "--update-golden",
        type=Path,
        default=None,
        help="write the golden baseline for this run",
    )
    run.add_argument("--json", action="store_true", help="print the full report as JSON")
    return parser


def _load_corpus(path: Path | None) -> ConformanceCorpus:
    if path is None:
        return ConformanceCorpus.bundled()
    return ConformanceCorpus.load(path)


def _run_command(args: argparse.Namespace) -> int:
    corpus = _load_corpus(args.corpus)
    report = run_conformance(corpus, tier=args.tier)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(report.to_markdown())

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "report.json").write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.out / "report.md").write_text(report.to_markdown(), encoding="utf-8")

    if args.update_golden is not None:
        args.update_golden.parent.mkdir(parents=True, exist_ok=True)
        args.update_golden.write_text(
            json.dumps(report.golden_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        sys.stderr.write(f"golden written to {args.update_golden}\n")

    exit_code = 0 if report.ok else 1
    if args.check is not None:
        golden = json.loads(Path(args.check).read_text(encoding="utf-8"))
        regressions = diff_golden(golden, report)
        if regressions:
            sys.stderr.write("CONFORMANCE REGRESSION:\n")
            for line in regressions:
                sys.stderr.write(f"  - {line}\n")
            exit_code = 1
        else:
            sys.stderr.write("no regression against golden\n")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_command(args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["run_conformance", "evaluate_case", "main"]
