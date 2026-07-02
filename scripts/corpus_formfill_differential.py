# SPDX-License-Identifier: Apache-2.0
"""Form-fill differential corpus driver (M9-full P3, specs/010 FR-004).

Drives the shipped form-fill differential DECISION (new-overflow / layout-stable
/ new-overlap, ``hwpx.form_fit.wordbox``) over the frozen corpus manifest's
form-fit records, **entirely offline** against pre-rendered Hancom PDFs:

* the blank forms were rendered once on the Mac oracle (P0 spike-3; the receipt
  ``specs/010-corpus-publication/evidence/clip_detectability.json`` predicts
  ~24/27 blanks clip-detectable, 3 prose docs without tables);
* the filled outputs come from the P2 render leg (``--filled-pdf-dir``); a
  filled file with no PDF yet is an honest ``unverified: no_render`` — never a
  silent pass or fail.

Design choice (why NOT ``verify_form_fill_differential`` per pair): the shipped
verdict function renders **and re-extracts** the blank geometry on every call
(``render_form_layout`` twice). The corpus pairs many fills onto one blank
(v1: 20 pairs / 7 blanks; v2 ~3 fills per blank), and the spec requires the
blank render/extraction to be paid ONCE per unique blank. So this driver
composes the *same* verdict from the pure offline pieces the shipped function
is built from — ``extract_glyph_boxes`` + ``extract_cell_clips`` +
``extract_layout_signature`` once per PDF (blank geometry cached), then
``diff_layout`` / ``diff_overflow`` / ``diff_overlaps`` per pair — mirroring
``verify_form_fill_differential``'s decision tail verbatim. The shipped hot
path is NOT modified; parity is pinned by a test that runs the shipped function
through :class:`PrerenderedOracle` and asserts an identical verdict.

:class:`PrerenderedOracle` is the reusable FR-004 shim for the drivers that
*do* go through the ``oracle=`` injection seam (``visual_check`` /
``verify_redline``): ``available() == True`` and ``render_pdf`` serves a
pre-rendered PDF by source basename, returning ``None`` for unmapped sources
(the ``MacHancomOracle`` degrade contract) so ``verify_*`` degrades to an
honest ``unverified``, never a fabricated render.

Honesty tiers (constitution V/VI/IX; spec metric row "form-fill"):

* ``verified``   — both PDFs found and parsed; the three differential signals
  were decided by geometry.
* ``unverified`` — no filled PDF (``no_render``), no blank PDF
  (``no_blank_render``), or an unreadable/0-page PDF
  (``render_failure`` / ``blank_render_failure``). Reported with explicit
  counts + reasons; NEVER folded into pass or fail.
* ``clip_undetectable`` — the render parsed but ``find_tables`` found no cell
  clips (detected LIVE via ``extract_cell_clips() == []``, matching the P0
  spike): the overflow signal is honestly not-evaluated
  (``overflowChecked=false``) while layout + overlap are still decided. Such
  pairs are excluded from the overflow and all-pass cells (they erode the
  published lower bound; they do not inflate it).

Rates are computed over VERIFIED pairs only; every all-pass cell carries a
rule-of-three 95% lower bound (``1 - 3/N``) so 100% is never printed.
Fail-closed: 0 verified pairs -> exit 3 (the report is still written for
inspection). ``generatedAt`` is left ``null`` — root stamps it; this script
never calls ``datetime.now``.

Usage::

    .venv/bin/python scripts/corpus_formfill_differential.py \
        --manifest work/openrate-corpus/manifest.json \
        --corpus-root work/openrate-corpus \
        --blank-pdf-dir /path/to/mac_blank_pdf \
        --filled-pdf-dir /path/to/mac_filled_pdf \
        --out docs/formfill/report.json

PDF naming: the box/Mac render legs emit ``NNN_<source-stem>.pdf``; the leading
``NNN_`` batch index is stripped when binding PDFs to manifest records, and a
bare ``<source-stem>.pdf`` is accepted too.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Make ``import hwpx`` work when run straight from a checkout (scripts/ sibling
# of src/), without requiring an install. Harmless if hwpx is already importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hwpx.form_fit import wordbox as wb  # noqa: E402

# How many overflow/overlap incidents to embed per pair (counts stay exact; the
# examples are capped so a pathological pair cannot balloon the report).
_MAX_EXAMPLES = 10
# ``NNN_`` batch prefix on box/Mac-rendered PDFs (e.g. ``007_aikorea-...pdf``).
_BATCH_PREFIX = re.compile(r"^\d+_")


# --------------------------------------------------------------------------- #
# PrerenderedOracle shim (the FR-004 oracle-injection seam over frozen PDFs)
# --------------------------------------------------------------------------- #

class PrerenderedOracle:
    """Render-backend shim that serves pre-rendered PDFs by source basename.

    Drop-in for the ``oracle=`` seam of ``verify_form_fill_differential`` /
    ``visual_check`` / ``verify_redline`` (it implements the ``RenderBackend``
    duck type: ``available`` / ``render_pdf`` / ``render_many``). The map binds
    a source *basename* (e.g. ``"form_002.hwpx"``) to the PDF a real Hancom
    already produced for that exact source, so a corpus run replays faithful
    captures without touching Hancom.

    Degrade contract (matches :class:`hwpx.visual.oracle.MacHancomOracle`): an
    unmapped source — or a mapped PDF that is missing/empty on disk — returns
    ``None`` from :meth:`render_pdf`, which the ``verify_*`` render legs turn
    into ``OracleUnavailable`` -> an honest ``unverified`` verdict. It never
    raises on the fill path and never fabricates a render.
    """

    def __init__(self, pdf_by_basename: dict[str, str]) -> None:
        self._pdf_by_basename = dict(pdf_by_basename)

    def available(self) -> bool:
        return True

    def render_pdf(self, hwpx_path: str, out_pdf: str | None = None) -> str | None:
        pdf = self._pdf_by_basename.get(os.path.basename(str(hwpx_path)))
        if not pdf or not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
            return None  # unmapped/unusable -> the caller degrades honestly
        if out_pdf is None:
            return pdf
        out_pdf = os.path.abspath(out_pdf)
        if os.path.abspath(pdf) != out_pdf:
            shutil.copyfile(pdf, out_pdf)
        return out_pdf

    def render_many(self, pairs: list[tuple[str, str]]) -> dict[str, str | None]:
        result: dict[str, str | None] = {src: None for src, _ in pairs}
        for src, pdf in pairs:
            try:
                result[src] = self.render_pdf(src, pdf)
            except Exception:
                result[src] = None  # degrade, never crash (RenderBackend contract)
        return result


# --------------------------------------------------------------------------- #
# Offline geometry + the differential verdict (pure composition, blank cached)
# --------------------------------------------------------------------------- #

def _extract_geometry(
    pdf_path: str,
) -> tuple[list[wb.WordBox], list[wb.Rect], wb.LayoutSignature]:
    """(glyphs, clips, signature) for one pre-rendered PDF.

    The offline analogue of ``render_form_layout`` minus the render: same
    validations (missing/empty/0-page PDF -> ``OracleUnavailable``) so the
    driver's degrade reasons line up with the shipped verdict function's.
    """

    if not pdf_path or not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        raise wb.OracleUnavailable("render produced no PDF")
    glyphs = wb.extract_glyph_boxes(pdf_path)
    clips = wb.extract_cell_clips(pdf_path)
    signature = wb.extract_layout_signature(pdf_path)
    if signature.page_count == 0:  # a 0-page render is a failed render
        raise wb.OracleUnavailable("render produced an empty (0-page) PDF")
    return glyphs, clips, signature


def differential_verdict(
    blank_geometry: tuple[list[wb.WordBox], list[wb.Rect], wb.LayoutSignature],
    filled_geometry: tuple[list[wb.WordBox], list[wb.Rect], wb.LayoutSignature],
    *,
    tol: float = wb._OVERFLOW_TOL_PT,
    require_table_shapes: bool = True,
    area_eps: float = wb._OVERLAP_AREA_EPS_PT2,
    area_frac: float = wb._OVERLAP_AREA_FRAC,
) -> wb.FormFillVerdict:
    """The ``verify_form_fill_differential`` decision tail on pre-extracted geometry.

    Byte-for-byte the same verdict the shipped function builds after its two
    ``render_form_layout`` calls (parity is pinned by a test); factored out here
    so the blank geometry can be extracted once per unique blank and reused
    across every fill of that form.
    """

    blank_glyphs, blank_clips, blank_sig = blank_geometry
    filled_glyphs, clips, filled_sig = filled_geometry
    diff = wb.diff_layout(blank_sig, filled_sig, require_table_shapes=require_table_shapes)
    overflow = wb.diff_overflow(blank_glyphs, blank_clips, filled_glyphs, clips, tol=tol)
    new_overlaps = wb.diff_overlaps(
        blank_glyphs, filled_glyphs, area_eps=area_eps, area_frac=area_frac
    )
    note_bits: list[str] = []
    if not clips:
        note_bits.append("no table cells detected (overflow not evaluated)")
    if not diff.stable:
        note_bits.append("layout unstable: " + "; ".join(diff.reasons))
    if new_overlaps:
        note_bits.append(f"{len(new_overlaps)} new glyph overlap(s) introduced by fill")
    return wb.FormFillVerdict(
        render_checked=True,
        overflow_detected=bool(overflow),
        overflow_checked=bool(clips),
        overlap_detected=bool(new_overlaps),
        layout_stable=diff.stable,
        overflow=[
            {"box": wb._box_brief(b), "clip": r.label, "escapePt": round(r.overflow_of(b), 2)}
            for b, r in overflow
        ],
        overlap=[{"a": wb._box_brief(a), "b": wb._box_brief(b)} for a, b in new_overlaps],
        note="; ".join(note_bits),
    )


# --------------------------------------------------------------------------- #
# PDF binding (NNN_-prefixed render outputs -> manifest records)
# --------------------------------------------------------------------------- #

def build_pdf_map(dir_path: str | None) -> tuple[dict[str, str], list[str]]:
    """Map ``{source-stem -> pdf-path}`` for a directory of pre-rendered PDFs.

    Accepts both ``<stem>.pdf`` and the render legs' ``NNN_<stem>.pdf`` batch
    naming (the ``NNN_`` prefix is stripped for a second binding). A missing or
    unset directory yields an empty map — every dependent pair then degrades to
    an honest ``unverified`` (the filled leg MAY not have run yet). Ambiguous
    stems keep the first (sorted) file and are reported as warnings, never
    silently rebound.
    """

    mapping: dict[str, str] = {}
    warnings: list[str] = []
    if not dir_path or not os.path.isdir(dir_path):
        return mapping, warnings
    for entry in sorted(os.listdir(dir_path)):
        if not entry.lower().endswith(".pdf"):
            continue
        full = os.path.join(dir_path, entry)
        stem = entry[:-len(".pdf")]
        keys = [stem]
        stripped = _BATCH_PREFIX.sub("", stem, count=1)
        if stripped and stripped != stem:
            keys.append(stripped)
        for key in keys:
            if key in mapping and mapping[key] != full:
                warnings.append(
                    f"ambiguous pdf stem {key!r}: keeping {mapping[key]!r}, ignoring {full!r}"
                )
            else:
                mapping[key] = full
    return mapping, warnings


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(str(path)))[0]


def select_form_records(
    records: list[dict[str, Any]], bucket_prefix: str = "form-fit"
) -> list[dict[str, Any]]:
    """Form-fill records: bucket ``form-fit`` today, ``form-fit-wide`` in corpus v2."""

    return [r for r in records if str(r.get("bucket") or "").startswith(bucket_prefix)]


# --------------------------------------------------------------------------- #
# Per-pair evaluation (blank geometry cached once per unique blank)
# --------------------------------------------------------------------------- #

def evaluate_pairs(
    records: list[dict[str, Any]],
    *,
    blank_pdf_map: dict[str, str],
    filled_pdf_map: dict[str, str],
    tol: float = wb._OVERFLOW_TOL_PT,
    require_table_shapes: bool = True,
    area_eps: float = wb._OVERLAP_AREA_EPS_PT2,
    area_frac: float = wb._OVERLAP_AREA_FRAC,
) -> list[dict[str, Any]]:
    """Decide the differential for every form-fit record; one result dict each.

    The blank geometry is extracted ONCE per unique blank PDF and cached —
    including a cached *failure*, so an unreadable blank is not re-parsed for
    every fill that shares it.
    """

    blank_cache: dict[str, Any] = {}  # pdf path -> geometry tuple | OracleUnavailable

    def _blank_geometry(pdf_path: str) -> Any:
        if pdf_path not in blank_cache:
            try:
                blank_cache[pdf_path] = _extract_geometry(pdf_path)
            except wb.OracleUnavailable as exc:
                blank_cache[pdf_path] = exc
        return blank_cache[pdf_path]

    results: list[dict[str, Any]] = []
    for rec in records:
        input_path = rec.get("input_path")
        output_path = rec.get("output_path")
        base: dict[str, Any] = {
            "id": rec.get("id"),
            "bucket": rec.get("bucket"),
            "blank": os.path.basename(str(input_path)) if input_path else None,
            "filled": os.path.basename(str(output_path)) if output_path else None,
            "blankPdf": None,
            "filledPdf": None,
        }

        if not rec.get("produced", output_path is not None) or not output_path or not input_path:
            results.append(
                {
                    **base,
                    "status": "skipped",
                    "reasonKind": "not_produced",
                    "reason": rec.get("withheld_reason")
                    or "record not produced (or missing input/output path)",
                }
            )
            continue

        blank_pdf = blank_pdf_map.get(_stem(input_path))
        filled_pdf = filled_pdf_map.get(_stem(output_path))
        base["blankPdf"] = blank_pdf
        base["filledPdf"] = filled_pdf

        if blank_pdf is None:
            results.append(
                {
                    **base,
                    "status": "unverified",
                    "reasonKind": "no_blank_render",
                    "reason": f"no pre-rendered blank PDF for stem {_stem(input_path)!r}",
                }
            )
            continue
        if filled_pdf is None:
            results.append(
                {
                    **base,
                    "status": "unverified",
                    "reasonKind": "no_render",
                    "reason": f"no pre-rendered filled PDF for stem {_stem(output_path)!r}",
                }
            )
            continue

        blank_geometry = _blank_geometry(blank_pdf)
        if isinstance(blank_geometry, wb.OracleUnavailable):
            results.append(
                {
                    **base,
                    "status": "unverified",
                    "reasonKind": "blank_render_failure",
                    "reason": f"blank render unusable: {blank_geometry}",
                }
            )
            continue
        try:
            filled_geometry = _extract_geometry(filled_pdf)
        except wb.OracleUnavailable as exc:
            results.append(
                {
                    **base,
                    "status": "unverified",
                    "reasonKind": "render_failure",
                    "reason": f"filled render unusable: {exc}",
                }
            )
            continue

        verdict = differential_verdict(
            blank_geometry,
            filled_geometry,
            tol=tol,
            require_table_shapes=require_table_shapes,
            area_eps=area_eps,
            area_frac=area_frac,
        )
        blank_clip_detectable = bool(blank_geometry[1])  # live extract_cell_clips
        overflow_tier = (
            "checked"
            if (verdict.overflow_checked and blank_clip_detectable)
            else "clip_undetectable"
        )
        results.append(
            {
                **base,
                "status": "verified",
                "reasonKind": None,
                "reason": None,
                "ok": verdict.ok,
                "newOverflow": len(verdict.overflow),
                "layoutStable": verdict.layout_stable,
                "newOverlap": len(verdict.overlap),
                "overflowChecked": verdict.overflow_checked,
                "blankClipDetectable": blank_clip_detectable,
                "overflowTier": overflow_tier,
                "note": verdict.note,
                "overflowExamples": verdict.overflow[:_MAX_EXAMPLES],
                "overlapExamples": verdict.overlap[:_MAX_EXAMPLES],
            }
        )
    return results


# --------------------------------------------------------------------------- #
# Aggregation (pure; what the unit tests pin)
# --------------------------------------------------------------------------- #

def rule_of_three_lower_bound(passed: int, n: int) -> float | None:
    """95% lower bound on the pass rate for an ALL-PASS cell: ``1 - 3/n``.

    Only defined when every one of ``n > 0`` trials passed (the rule of three);
    ``None`` otherwise — a cell with observed failures publishes its observed
    rate, not a fabricated bound. 100% is never printed as the headline.
    """

    if n <= 0 or passed != n:
        return None
    return max(0.0, 1.0 - 3.0 / n)


def _cell(name: str, n: int, passed: int) -> dict[str, Any]:
    lb = rule_of_three_lower_bound(passed, n)
    return {
        "name": name,
        "n": n,
        "passed": passed,
        "rate": (round(passed / n, 4) if n > 0 else None),
        "allPass": bool(n > 0 and passed == n),
        "ruleOfThreeLowerBound": lb,
        "interval": (
            f"{passed}/{n} -> >= {lb * 100:.1f}% (95% CI, rule of three: 1 - 3/N)"
            if lb is not None
            else f"{passed}/{n}"
        ),
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals + metric cells over per-pair results (pure; no I/O).

    Pass rates are computed over VERIFIED pairs only. Unverified pairs are
    counted + broken down by reason, never folded into pass or fail. The
    overflow and all-pass cells additionally exclude the ``clip_undetectable``
    tier (overflow honestly not evaluated there), which is reported as its own
    bucket with its layout+overlap partial result.
    """

    verified = [r for r in results if r.get("status") == "verified"]
    unverified = [r for r in results if r.get("status") == "unverified"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    checked = [r for r in verified if r.get("overflowTier") == "checked"]
    clip_und = [r for r in verified if r.get("overflowTier") == "clip_undetectable"]

    def _layout_overlap_ok(r: dict[str, Any]) -> bool:
        return bool(r.get("layoutStable") is True and r.get("newOverlap") == 0)

    def _all_ok(r: dict[str, Any]) -> bool:
        return bool(r.get("newOverflow") == 0 and _layout_overlap_ok(r))

    cells = [
        _cell(
            "new_overflow_zero",
            len(checked),
            sum(1 for r in checked if r.get("newOverflow") == 0),
        ),
        _cell(
            "layout_stable",
            len(verified),
            sum(1 for r in verified if r.get("layoutStable") is True),
        ),
        _cell(
            "new_overlap_zero",
            len(verified),
            sum(1 for r in verified if r.get("newOverlap") == 0),
        ),
        _cell("all_pass", len(checked), sum(1 for r in checked if _all_ok(r))),
    ]
    all_pass_cell = cells[-1]

    reasons = Counter(str(r.get("reasonKind")) for r in unverified)
    totals: dict[str, Any] = {
        "records": len(results),
        "skippedNotProduced": len(skipped),
        "pairs": len(verified) + len(unverified),
        "verified": len(verified),
        "unverified": len(unverified),
        "unverifiedReasons": dict(sorted(reasons.items())),
        "clipUndetectable": len(clip_und),
        "clipUndetectableLayoutOverlapPass": sum(
            1 for r in clip_und if _layout_overlap_ok(r)
        ),
        "fullyVerified": len(checked),
        "passed": all_pass_cell["passed"],
        "failed": len(checked) - all_pass_cell["passed"],
        "passRate": all_pass_cell["rate"],
        "passRateLowerBound": all_pass_cell["ruleOfThreeLowerBound"],
        "passRateInterval": all_pass_cell["interval"],
    }
    return {"totals": totals, "cells": cells}


def build_report(
    results: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
    params: dict[str, Any] | None = None,
    tool_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the full ``report.json`` dict (pure; no I/O, no clock)."""

    agg = aggregate(results)
    failures = [
        {
            "id": r.get("id"),
            "filled": r.get("filled"),
            "newOverflow": r.get("newOverflow"),
            "layoutStable": r.get("layoutStable"),
            "newOverlap": r.get("newOverlap"),
            "note": r.get("note"),
        }
        for r in results
        if r.get("status") == "verified" and not r.get("ok")
    ]
    return {
        "schemaVersion": 1,
        "generatedAt": None,  # root stamps; never datetime.now (constitution V)
        "feature": "010-corpus-publication/form-fill",
        "metric": {
            "headline": "form-fill differential per pair: new-overflow 0 AND layout-stable "
            "AND new-overlap 0, decided offline (fitz) against real-Hancom pre-rendered "
            "blank+filled PDFs (blank geometry extracted once per unique blank)",
            "decision": "verify_form_fill_differential decision tail composed from "
            "diff_overflow / diff_layout / diff_overlaps on pre-extracted geometry "
            "(shipped hot path untouched; parity pinned by test)",
            "tiers": [
                "verified (both renders parsed; all three signals decided)",
                "clip_undetectable (no find_tables cells: overflow not evaluated; "
                "layout+overlap still decided; excluded from overflow/all-pass cells)",
                "unverified (no_render / no_blank_render / render_failure / "
                "blank_render_failure; never folded into pass or fail)",
            ],
            "denominatorRule": "rates over VERIFIED pairs only; overflow + all-pass "
            "cells over the clip-checked subset; unverified reported separately",
            "intervalRule": "rule of three on all-pass cells: >= 1 - 3/N (95% CI); "
            "100% is never printed",
        },
        "totals": agg["totals"],
        "cells": agg["cells"],
        "pairs": results,
        "failures": failures,
        "warnings": list(warnings or []),
        "params": dict(params or {}),
        "tool_versions": tool_versions or _collect_tool_versions(),
    }


def _collect_tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    try:
        from importlib.metadata import version

        versions["python-hwpx"] = version("python-hwpx")
    except Exception:
        versions["python-hwpx"] = None
    try:
        import fitz

        versions["pymupdf"] = getattr(fitz, "__version__", None) or getattr(
            fitz, "version", (None,)
        )[0]
    except Exception:
        versions["pymupdf"] = None
    versions["python"] = sys.version.split()[0]
    # Hancom build is render-leg-supplied; root stamps it. Left as a documented slot.
    versions["hancom_build"] = None
    return versions


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus_formfill_differential",
        description="Decide the form-fill differential (new-overflow/layout/new-overlap) "
        "over the frozen corpus, offline, against pre-rendered Hancom PDFs.",
    )
    parser.add_argument(
        "--manifest",
        default="work/openrate-corpus/manifest.json",
        help="frozen corpus manifest (default: work/openrate-corpus/manifest.json)",
    )
    parser.add_argument(
        "--corpus-root",
        default=None,
        help="root for resolving relative manifest paths (default: the manifest's directory)",
    )
    parser.add_argument(
        "--blank-pdf-dir",
        required=True,
        help="directory of pre-rendered BLANK-form PDFs (NNN_<stem>.pdf or <stem>.pdf)",
    )
    parser.add_argument(
        "--filled-pdf-dir",
        default=None,
        help="directory of pre-rendered FILLED-output PDFs; MAY be absent/empty — "
        "pairs without a filled PDF are honest unverified(no_render)",
    )
    parser.add_argument(
        "--bucket-prefix",
        default="form-fit",
        help="manifest bucket prefix to select (default: form-fit; matches form-fit-wide in v2)",
    )
    parser.add_argument(
        "--out",
        default="docs/formfill/report.json",
        help="output report.json path (default: docs/formfill/report.json)",
    )
    parser.add_argument(
        "--tol",
        type=float,
        default=wb._OVERFLOW_TOL_PT,
        help=f"overflow tolerance in pt (default: {wb._OVERFLOW_TOL_PT})",
    )
    parser.add_argument(
        "--table-shapes-advisory",
        action="store_true",
        help="judge layout stability by page count only (table shapes advisory) — "
        "the diff_layout calibration knob for a corpus where find_tables proves "
        "too content-sensitive; decided by measurement, not assumption",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    if not os.path.exists(args.manifest):
        parser.error(f"manifest not found: {args.manifest}")
    if not os.path.isdir(args.blank_pdf_dir):
        parser.error(f"blank PDF directory not found: {args.blank_pdf_dir}")

    with open(args.manifest, encoding="utf-8") as handle:
        manifest = json.load(handle)
    records = list(manifest.get("records") or manifest.get("items") or [])

    corpus_root = args.corpus_root or os.path.dirname(os.path.abspath(args.manifest))

    def _resolve(path: Any) -> Any:
        # Manifest v1 carries absolute paths; v2 may carry corpus-relative ones.
        if not path or os.path.isabs(str(path)):
            return path
        return os.path.join(corpus_root, str(path))

    form_records = []
    for rec in select_form_records(records, args.bucket_prefix):
        rec = dict(rec)
        rec["input_path"] = _resolve(rec.get("input_path"))
        rec["output_path"] = _resolve(rec.get("output_path"))
        form_records.append(rec)

    blank_map, blank_warnings = build_pdf_map(args.blank_pdf_dir)
    filled_map, filled_warnings = build_pdf_map(args.filled_pdf_dir)
    warnings = blank_warnings + filled_warnings
    if args.filled_pdf_dir and not os.path.isdir(args.filled_pdf_dir):
        warnings.append(
            f"filled PDF directory not found: {args.filled_pdf_dir} "
            "(all pairs degrade to unverified: no_render)"
        )

    results = evaluate_pairs(
        form_records,
        blank_pdf_map=blank_map,
        filled_pdf_map=filled_map,
        tol=args.tol,
        require_table_shapes=not args.table_shapes_advisory,
    )
    report = build_report(
        results,
        warnings=warnings,
        params={
            "manifest": args.manifest,
            "corpusRoot": corpus_root,
            "bucketPrefix": args.bucket_prefix,
            "blankPdfDir": args.blank_pdf_dir,
            "filledPdfDir": args.filled_pdf_dir,
            "tol": args.tol,
            "requireTableShapes": not args.table_shapes_advisory,
            "uniqueBlanks": len({r.get("blankPdf") for r in results if r.get("blankPdf")}),
        },
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for w in warnings:
        sys.stderr.write(w + "\n")

    totals = report["totals"]
    # Fail-closed: a run that verified NOTHING (no filled renders yet, wrong dirs,
    # fitz missing) must not masquerade as a benign exit-0 publish.
    if totals["verified"] == 0:
        sys.stderr.write(
            f"FAIL_CLOSED: 0 of {totals['pairs']} form-fill pairs verified "
            f"(unverified reasons: {totals['unverifiedReasons']}). Wrote {out_path} "
            "for inspection but refusing exit 0.\n"
        )
        return 3
    print(
        f"wrote {out_path} (verified={totals['verified']}, unverified={totals['unverified']}, "
        f"clipUndetectable={totals['clipUndetectable']}, passRate={totals['passRate']}, "
        f"lowerBound={totals['passRateLowerBound']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
