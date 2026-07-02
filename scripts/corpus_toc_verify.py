# SPDX-License-Identifier: Apache-2.0
"""010-corpus-publication P3 — authored-toc TOC structural corpus driver.

Consumes the corpus-v2 manifest (``work/openrate-corpus-v2/manifest.json``),
selects every record in the ``authored-toc`` stratum, and verifies the native
TABLEOFCONTENTS contract over two legs:

* Mode 1 (default) — ORACLE-FREE structural verification, FULL stratum:
  ``hwpx.tools.toc_fidelity.structural_report`` per doc (field present, entry
  model sane, anchors resolve, internally consistent) plus the manifest's
  recorded ``toc_entry_count`` cross-check and the ``dirty`` flag read verbatim
  (informational only — dirty is the open-time recompute trigger, NOT a
  reliable staleness marker; M7 measured semantics).
* Mode 2 (``--renumber-sample N``) — OPT-IN Mac Hancom refresh->render
  renumber sample: the first N produced docs (deterministic manifest order)
  are COPIED to a scratch workdir (the frozen corpus is never touched), then
  per copy: ``MacHancomOracle.refresh_document`` (its own Hancom session —
  open-time dirty regeneration + save), then ``render_pdf`` as a SEPARATE
  session/call (M7 crash contract: exporting a PDF from the regenerating
  session crashes this Hancom build), then
  ``toc_fidelity.toc_verify(pdf_path=...)`` -> per-doc verified/stale verdict.

Honesty rules baked in:
* S-060 discipline: the live Hancom oracle is NEVER resolved by default or
  from tests — ``--renumber-sample`` is the only path that touches it. When
  the oracle is unavailable every sampled doc is ``unverified``, never a pass,
  and the run exits 4 (a requested sample with zero render-checked verdicts
  must not look like a benign publish).
* Post-hoc measurement of the frozen bytes: the rate that comes out is the
  rate that gets published — NO regenerate-until-green; a low number is
  publishable truth (mirrors scripts/corpus_authoring_quality.py, FR-006).
* rule-of-three 95% lower bound accompanies every rate; denominators are
  explicit; withheld / missing_file / parse_error are listed and counted,
  never silently dropped. ``generatedAt`` stays ``null`` (root stamps it).

Exit codes: 0 = report written (regardless of pass rate — honesty rule);
3 = fail-closed, ZERO authored-toc records matched; 4 = renumber sample was
requested but ZERO docs reached a render-checked verdict (oracle unavailable
or every refresh/render failed — unverified never masquerades as done).

Usage (structural leg only — corpus-scale, no oracle)::

    .venv/bin/python scripts/corpus_toc_verify.py \
        --manifest work/openrate-corpus-v2/manifest.json \
        --out work/m9-prelim/toc-verify.json

Usage (plus the opt-in Mac renumber sample — macOS + Hancom GUI session)::

    .venv/bin/python scripts/corpus_toc_verify.py --renumber-sample 3
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

# Make ``import hwpx`` work when run straight from a checkout (scripts/ sibling
# of src/), without requiring an install. Harmless if hwpx is already importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hwpx.document import HwpxDocument
from hwpx.tools import toc_fidelity as tf

_SCRIPTS = Path(__file__).resolve().parent
PYTHON_HWPX = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PYTHON_HWPX / "work" / "openrate-corpus-v2" / "manifest.json"

REPORT_SCHEMA = "hwpx.corpus.toc-verify.v1"
TOC_STRATUM = "authored-toc"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

EXIT_OK = 0
EXIT_NO_RECORDS = 3
EXIT_SAMPLE_UNVERIFIED = 4


def _load_sibling(name: str):
    """Load a sibling scripts/ module by file path (scripts/ is not a package)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load scripts/{name}.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def rule_of_three_lower_bound(failures: int, n: int) -> float | None:
    """Delegates to corpus_open_rate (single definition of the published bound)."""
    return _load_sibling("corpus_open_rate").rule_of_three_lower_bound(failures, n)


def rule_of_three_text(failures: int, n: int) -> str:
    return _load_sibling("corpus_open_rate").rule_of_three_text(failures, n)


def resolve_output_path(raw: str | None, corpus_root: Path) -> Path | None:
    """Delegates to corpus_pii_leak_sweep (single definition of v2 re-rooting)."""
    return _load_sibling("corpus_pii_leak_sweep").resolve_output_path(raw, corpus_root)


# ================================================================================
# manifest selection (pure, unit-tested)
# ================================================================================
def select_toc_records(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every record in the authored-toc stratum, manifest order preserved."""
    selected: list[dict[str, Any]] = []
    for rec in manifest.get("records", []):
        stratum = str(rec.get("stratum") or rec.get("bucket") or "")
        if stratum == TOC_STRATUM:
            selected.append(rec)
    return selected


# ================================================================================
# structural leg (oracle-free; follows what structural_report exposes)
# ================================================================================
def toc_dirty_flag(path: Path | str) -> str | None:
    """The TABLEOFCONTENTS ``dirty`` attribute, verbatim (informational only)."""
    doc = HwpxDocument.open(path)
    try:
        for section in doc.oxml.sections:
            for begin in section.element.iter(f"{_HP}fieldBegin"):
                if begin.get("type") == "TABLEOFCONTENTS":
                    return begin.get("dirty")
        return None
    finally:
        close = getattr(doc, "close", None)
        if callable(close):
            close()


def structural_checks(
    report: Mapping[str, Any], manifest_entry_count: Any
) -> dict[str, bool | None]:
    """Per-doc boolean checks derived from structural_report + the manifest.

    ``None`` means not-applicable (the manifest carried no toc_entry_count) —
    never counted as a pass or a fail.
    """
    entries = report.get("entries") or []
    checks: dict[str, bool | None] = {
        "field_present": bool(report.get("hasNativeToc")),
        "entries_nonempty": int(report.get("entryCount") or 0) > 0,
        "entries_sane": bool(entries)
        and all(
            str(e.get("title") or "").strip() and e.get("cachedPage") is not None
            for e in entries
        ),
        "targets_resolve": bool(report.get("targetsResolve")),
        "internally_consistent": bool(report.get("internally_consistent")),
    }
    if manifest_entry_count is None:
        checks["manifest_entry_count_match"] = None
    else:
        checks["manifest_entry_count_match"] = int(
            report.get("entryCount") or 0
        ) == int(manifest_entry_count)
    return checks


def structural_pass(checks: Mapping[str, bool | None]) -> bool:
    return all(value for value in checks.values() if value is not None)


def evaluate_structural(
    records: list[Mapping[str, Any]], corpus_root: Path
) -> list[dict[str, Any]]:
    """Run structural_report over every stratum record -> honest per-file rows.

    Never raises on a bad file: parse crashes become ``parse_error`` rows,
    missing files ``missing_file``, withheld records ``withheld`` — all listed,
    nothing silently dropped from the denominators.
    """
    rows: list[dict[str, Any]] = []
    for rec in records:
        row: dict[str, Any] = {
            "id": rec.get("id"),
            "stratum": str(rec.get("stratum") or rec.get("bucket") or ""),
            "path": None,
            "status": None,
            "structural_pass": None,
            "checks": None,
            "tocDirty": None,
            "entryCount": None,
            "crossrefCount": None,
            "unresolvedTargets": [],
            "internalConflicts": 0,
            "manifestEntryCount": rec.get("toc_entry_count"),
            "error": None,
        }
        if not rec.get("produced"):
            row["status"] = "withheld"
            row["error"] = rec.get("withheld_reason") or "composer withheld (produced=false)"
            rows.append(row)
            continue
        path = resolve_output_path(rec.get("output_path"), corpus_root)
        if path is None:
            row["status"] = "missing_file"
            row["error"] = f"produced file not found: {rec.get('output_path')}"
            rows.append(row)
            continue
        row["path"] = str(path)
        try:
            report = tf.structural_report(path)
            row["tocDirty"] = toc_dirty_flag(path)
        except Exception as exc:  # a file our own harness cannot parse is a listed failure
            row["status"] = "parse_error"
            row["error"] = f"{type(exc).__name__}: {exc}"[:400]
            rows.append(row)
            continue
        checks = structural_checks(report, rec.get("toc_entry_count"))
        row["status"] = "judged"
        row["checks"] = checks
        row["structural_pass"] = structural_pass(checks)
        row["entryCount"] = report.get("entryCount")
        row["crossrefCount"] = report.get("crossrefCount")
        row["unresolvedTargets"] = list(report.get("unresolvedTargets") or [])
        row["internalConflicts"] = len(report.get("internal_conflicts") or [])
        rows.append(row)
    return rows


# ================================================================================
# pure aggregation (unit-tested math)
# ================================================================================
def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def aggregate_structural(
    rows: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(totals, failures) over the per-file rows. Pure (no I/O, no clock)."""
    judged = [r for r in rows if r["status"] == "judged"]
    withheld = sum(1 for r in rows if r["status"] == "withheld")
    produced = len(rows) - withheld
    passes = sum(1 for r in judged if r["structural_pass"])
    fails = len(judged) - passes

    check_hist: Counter[str] = Counter()
    for r in judged:
        if not r["structural_pass"]:
            check_hist.update(
                name for name, ok in (r["checks"] or {}).items() if ok is False
            )

    totals = {
        "records": len(rows),
        "withheld": withheld,
        "produced": produced,
        "missing_file": sum(1 for r in rows if r["status"] == "missing_file"),
        "parse_error": sum(1 for r in rows if r["status"] == "parse_error"),
        "judged": len(judged),
        "coverage": _rate(len(judged), produced),
        "structural": {
            "pass": passes,
            "fail": fails,
            "rate": _rate(passes, len(judged)),
            "rate_lower_bound": rule_of_three_lower_bound(fails, len(judged)),
            "rate_interval": rule_of_three_text(fails, len(judged)),
            "all_pass": len(judged) > 0 and fails == 0,
            "check_failure_histogram": dict(sorted(check_hist.items())),
        },
    }

    failures: list[dict[str, Any]] = []
    for r in rows:
        reason = None
        if r["status"] in ("withheld", "missing_file", "parse_error"):
            reason = r["error"] or r["status"]
        elif r["status"] == "judged" and not r["structural_pass"]:
            failed = [name for name, ok in (r["checks"] or {}).items() if ok is False]
            reason = "structural checks failed: " + ", ".join(failed or ["?"])
        if reason is not None:
            failures.append({"id": r["id"], "path": r["path"], "reason": reason})
    return totals, failures


# ================================================================================
# renumber sample leg (OPT-IN; oracle injected — unit tests use fakes)
# ================================================================================
def _cached_pages(path: Path | str) -> list[int | None] | None:
    try:
        return [e.cached_page for e in tf.parse_toc_model(str(path)).entries]
    except Exception:
        return None


def run_renumber_sample(
    records: list[Mapping[str, Any]],
    corpus_root: Path,
    n: int,
    oracle: Any | None,
    workdir: Path,
) -> dict[str, Any]:
    """Refresh->render->toc_verify over the first N produced docs.

    Session separation is structural here: ``refresh_document`` and
    ``render_pdf`` are two independent oracle calls — each osascript run is its
    own Hancom open/close session (M7 crash contract). The frozen corpus file
    is never touched: refresh saves in place on a scratch COPY.

    Oracle unavailable (or missing) -> every sampled doc is ``unverified``,
    never a pass.
    """
    selected: list[tuple[Any, Path]] = []
    skipped: list[dict[str, Any]] = []
    for rec in records:
        if len(selected) >= n:
            break
        if not rec.get("produced"):
            skipped.append({"id": rec.get("id"), "reason": "withheld (produced=false)"})
            continue
        path = resolve_output_path(rec.get("output_path"), corpus_root)
        if path is None:
            skipped.append(
                {"id": rec.get("id"), "reason": f"file not found: {rec.get('output_path')}"}
            )
            continue
        selected.append((rec.get("id"), path))

    oracle_available = False
    if oracle is not None:
        try:
            oracle_available = bool(getattr(oracle, "available", lambda: False)())
        except Exception:
            oracle_available = False

    per_doc: list[dict[str, Any]] = []
    for rec_id, src in selected:
        row: dict[str, Any] = {
            "id": rec_id,
            "sourcePath": str(src),
            "workPath": None,
            "refreshed": None,
            "rendered": None,
            "pdf": None,
            "renderChecked": False,
            "verdict": "unverified",
            "reason": None,
            "tocRatio": None,
            "xrefRatio": None,
            "pagesBefore": None,
            "pagesAfter": None,
        }
        if not oracle_available:
            row["reason"] = "oracle unavailable — unverified, never a pass"
            per_doc.append(row)
            continue

        work = workdir / Path(src).name
        shutil.copyfile(src, work)  # frozen corpus stays untouched
        row["workPath"] = str(work)
        row["pagesBefore"] = _cached_pages(work)

        # Session 1: open-time dirty regeneration + save-in-place, then close.
        try:
            refreshed = bool(oracle.refresh_document(str(work)))
        except Exception as exc:
            refreshed = False
            row["reason"] = f"refresh raised: {type(exc).__name__}: {exc}"[:200]
        row["refreshed"] = refreshed
        if not refreshed:
            row["reason"] = row["reason"] or "Hancom refresh failed — unverified"
            per_doc.append(row)
            continue
        row["pagesAfter"] = _cached_pages(work)

        # Session 2 (SEPARATE call — M7 crash contract): render the refreshed copy.
        pdf_target = str(Path(work).with_suffix(".pdf"))
        try:
            pdf = oracle.render_pdf(str(work), pdf_target)
        except Exception as exc:
            pdf = None
            row["reason"] = f"render raised: {type(exc).__name__}: {exc}"[:200]
        row["rendered"] = bool(pdf)
        if not pdf:
            row["reason"] = row["reason"] or "Hancom render failed — unverified"
            per_doc.append(row)
            continue
        row["pdf"] = str(pdf)

        verify = tf.toc_verify(str(work), pdf_path=str(pdf))
        row["renderChecked"] = bool(verify.get("render_checked"))
        row["verdict"] = verify.get("verdict") or "unverified"
        row["tocRatio"] = verify.get("toc_correctness_ratio")
        row["xrefRatio"] = verify.get("crossref_correctness_ratio")
        if not row["renderChecked"]:
            row["reason"] = "PDF text layer unusable — degraded to unverified"
        per_doc.append(row)

    sampled = len(per_doc)
    verified = sum(1 for r in per_doc if r["verdict"] == "verified")
    stale = sum(1 for r in per_doc if r["verdict"] == "stale")
    unverified = sampled - verified - stale
    return {
        "requested": n,
        "selectionRule": "first N produced authored-toc records in manifest order (deterministic)",
        "skipped": skipped,
        "workdir": str(workdir),
        "oracle": {
            "backend": type(oracle).__name__ if oracle is not None else None,
            "available": oracle_available,
        },
        "sessionRule": "refresh_document and render_pdf run as SEPARATE Hancom "
        "sessions (M7 crash contract: exporting a PDF from the regenerating "
        "session crashes this Hancom build)",
        "sampled": sampled,
        "renderChecked": sum(1 for r in per_doc if r["renderChecked"]),
        "verified": verified,
        "stale": stale,
        "unverified": unverified,
        "verifiedRatio": _rate(verified, sampled),
        "verifiedInterval": rule_of_three_text(sampled - verified, sampled),
        "perDoc": per_doc,
    }


# ================================================================================
# report assembly + driver
# ================================================================================
def build_report(
    rows: list[dict[str, Any]],
    totals: dict[str, Any],
    failures: list[dict[str, Any]],
    *,
    sources: Mapping[str, Any],
    renumber_sample: dict[str, Any] | None,
    tool_versions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the full report dict (pure; no I/O, no clock)."""
    return {
        "schemaVersion": 1,
        "report": REPORT_SCHEMA,
        "generatedAt": None,  # root stamps; never datetime.now (constitution V)
        "feature": "010-corpus-publication",
        "axis": "toc",
        "metric": {
            "headline": "authored-toc stratum: oracle-free STRUCTURAL verification "
            "over the FULL stratum (native TABLEOFCONTENTS field present, entry "
            "model sane, anchors resolve, internally consistent, manifest entry-count "
            "match) + an OPT-IN Mac Hancom refresh->render renumber sample",
            "judge": "hwpx.tools.toc_fidelity.structural_report (oracle-free) for the "
            "full stratum; hwpx.tools.toc_fidelity.toc_verify against a real Hancom "
            "render for the renumber sample only — no render claim is ever made by "
            "the structural leg",
            "oracleRule": "S-060 discipline: the live Hancom oracle is NEVER resolved "
            "by default or from tests; --renumber-sample is the only path. Oracle "
            "unavailable -> every sampled doc is 'unverified', never a pass (exit 4 "
            "when zero docs reach a render-checked verdict)",
            "sessionRule": "M7 crash contract: refresh_document (open-time dirty "
            "regeneration + save) and render_pdf run as SEPARATE Hancom sessions — "
            "exporting a PDF from the regenerating session crashes this Hancom build",
            "dirtyNote": "tocDirty is recorded verbatim per doc but NOT gated: dirty "
            "is the open-time recompute trigger, not a reliable staleness marker "
            "(M7 measured semantics)",
            "honestyRule": "post-hoc measurement of the frozen bytes — the rate that "
            "comes out is the rate that gets published; NO regenerate-until-green; "
            "a low number is publishable truth",
            "intervalRule": "rule of three: k=0 -> >= 1 - 3/N (95% CI); 100% is never "
            "printed as a bare headline",
            "denominatorRule": "structural rate is over JUDGED files (structural_report "
            "returned a verdict); coverage = judged / produced; withheld / missing_file "
            "/ parse_error are listed and counted, never silently dropped. Renumber "
            "verifiedRatio is over SAMPLED docs — 'unverified' counts against the "
            "ratio, it never passes",
            "unverifiedBuckets": "structural leg: withheld | missing_file | parse_error; "
            "renumber leg: unverified (oracle unavailable / refresh failed / render "
            "failed / PDF text layer unusable)",
        },
        "sources": dict(sources),
        "totals": totals,
        "failures": failures,
        "per_file": rows,
        "renumberSample": renumber_sample,
        "tool_versions": dict(tool_versions or {}),
    }


def _collect_tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    try:
        from importlib.metadata import version

        versions["python-hwpx"] = version("python-hwpx")
    except Exception:
        versions["python-hwpx"] = None
    versions["python"] = sys.version.split()[0]
    return versions


def run(
    manifest_path: Path | str,
    corpus_root: Path | str | None = None,
    *,
    renumber_sample: int = 0,
    oracle: Any | None = None,
    renumber_workdir: Path | str | None = None,
) -> tuple[dict[str, Any], int]:
    """Full driver. Returns (report dict, exit code).

    ``oracle`` is only consulted when ``renumber_sample > 0`` — callers (and
    the CLI) never resolve a live backend otherwise.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(corpus_root) if corpus_root else manifest_path.resolve().parent

    records = select_toc_records(manifest)
    rows = evaluate_structural(records, root)
    totals, failures = aggregate_structural(rows)

    sample: dict[str, Any] | None = None
    if renumber_sample > 0:
        workdir = (
            Path(renumber_workdir)
            if renumber_workdir
            else Path(tempfile.mkdtemp(prefix="toc-renumber-"))
        )
        workdir.mkdir(parents=True, exist_ok=True)
        sample = run_renumber_sample(records, root, renumber_sample, oracle, workdir)

    report = build_report(
        rows,
        totals,
        failures,
        sources={
            "manifest": str(manifest_path),
            "manifestSchema": manifest.get("schemaVersion"),
            "corpusRoot": str(root),
            "stratum": TOC_STRATUM,
        },
        renumber_sample=sample,
        tool_versions=_collect_tool_versions(),
    )

    if not records:
        return report, EXIT_NO_RECORDS
    if sample is not None and sample["renderChecked"] == 0:
        return report, EXIT_SAMPLE_UNVERIFIED
    return report, EXIT_OK


# ================================================================================
# CLI
# ================================================================================
def _fmt_rate(rate: float | None, lb: float | None) -> str:
    if rate is None:
        return "N/A"
    lb_txt = f" (95% lower bound >= {lb * 100:.1f}%)" if lb is not None else ""
    return f"{rate * 100:.1f}%{lb_txt}"


def _print_summary(report: dict[str, Any], exit_code: int) -> None:
    t = report["totals"]
    s = t["structural"]
    print("=" * 74)
    print("TOC VERIFY — authored-toc stratum (specs/010 P3)")
    print("=" * 74)
    print(
        f"structural: judged {t['judged']}/{t['produced']} (records {t['records']}, "
        f"withheld {t['withheld']}, missing {t['missing_file']}, "
        f"parse_error {t['parse_error']})"
    )
    print(
        f"structural_pass {s['pass']}/{t['judged']} = "
        f"{_fmt_rate(s['rate'], s['rate_lower_bound'])}"
    )
    for check, count in s["check_failure_histogram"].items():
        print(f"    check-fail x{count}: {check}")
    if report["failures"]:
        print("-" * 74)
        print(f"FAILURES ({len(report['failures'])}) — publishable truth, listed per file:")
        for f in report["failures"]:
            print(f"  {f['id']}: {f['reason']}")
    sample = report.get("renumberSample")
    if sample is not None:
        print("-" * 74)
        print(
            f"renumber sample: sampled {sample['sampled']} "
            f"(requested {sample['requested']}, render-checked {sample['renderChecked']})"
        )
        print(
            f"  verified {sample['verified']} / stale {sample['stale']} / "
            f"unverified {sample['unverified']}  ->  verifiedRatio "
            f"{sample['verifiedRatio']}  [{sample['verifiedInterval']}]"
        )
        print(f"  oracle: {sample['oracle']}  workdir: {sample['workdir']}")
    print("-" * 74)
    print("HONESTY: post-hoc measurement of the frozen bytes; NO regenerate-until-")
    print("      green. dirty flag recorded verbatim, never gated (M7 semantics).")
    print(f"exit={exit_code}")
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus_toc_verify",
        description="TOC structural verification over the corpus-v2 authored-toc "
        "stratum (oracle-free), plus an OPT-IN Mac Hancom refresh->render renumber "
        "sample (session-separated).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"corpus-v2 manifest path (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=None,
        help="root for resolving/re-rooting record output paths (default: manifest dir)",
    )
    parser.add_argument(
        "--renumber-sample",
        type=int,
        default=0,
        metavar="N",
        help="OPT-IN: refresh->render->verify the first N produced docs via the live "
        "Mac Hancom oracle (default 0 = structural leg only; never triggered "
        "by default or from tests)",
    )
    parser.add_argument(
        "--renumber-workdir",
        type=Path,
        default=None,
        help="scratch dir for renumber-sample copies (default: a fresh temp dir; "
        "the frozen corpus is never touched either way)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PYTHON_HWPX / "work" / "m9-prelim" / "toc-verify.json",
        help="output report path (default: work/m9-prelim/toc-verify.json)",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return EXIT_NO_RECORDS

    oracle: Any | None = None
    if args.renumber_sample > 0:
        # The ONLY path that touches a live backend (S-060 discipline).
        from hwpx.visual.oracle import resolve_oracle

        oracle = resolve_oracle()

    report, exit_code = run(
        args.manifest,
        args.corpus_root,
        renumber_sample=args.renumber_sample,
        oracle=oracle,
        renumber_workdir=args.renumber_workdir,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if exit_code == EXIT_NO_RECORDS:
        sys.stderr.write(
            f"FAIL-CLOSED: 0 {TOC_STRATUM} records matched in {args.manifest}. "
            f"Wrote {args.out} for inspection but refusing exit 0.\n"
        )
        return exit_code

    _print_summary(report, exit_code)
    if exit_code == EXIT_SAMPLE_UNVERIFIED:
        sys.stderr.write(
            "RENUMBER SAMPLE UNVERIFIED: a sample was requested but zero docs "
            "reached a render-checked verdict — unverified never passes (exit 4).\n"
        )
    print(f"wrote {args.out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
