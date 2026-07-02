# SPDX-License-Identifier: Apache-2.0
"""M9-full P3 — authoring-quality corpus aggregator (specs/010, authoring axis).

Reconstructs the deterministic plan for every AUTHORED record in the frozen v1
open-rate corpus (``scripts/generate_openrate_corpus.py::authored_plans()``,
aligned to the manifest by record id + seed), runs the oracle-free structural
quality inspectors over the FROZEN bytes, and aggregates an honest per-type
report:

* ``inspect_document_authoring_quality(path, plan=...)`` — quality gates, gaps,
  ``korean_proofing_status`` (recorded verbatim; expected ``unverified`` —
  NEVER coerced),
* for 공문-typed docs additionally ``inspect_official_document_style(path,
  document_type='공문')`` — the hard-gate ``structure_pass`` + per-rule
  violations.

CRITICAL HONESTY RULE (spec 010 FR-006 + inventory risk): the 40 authored v1
docs were generated with their quality reports DISCARDED. This script is a
POST-HOC measurement of the frozen bytes — whatever pass rate comes out is the
number we publish. There is deliberately NO fail-exit on a low pass rate (a low
number is publishable truth, printed prominently); regenerate-until-green is
forbidden.

Report discipline (mirrors ``scripts/corpus_open_rate.py``):

* rule-of-three 95% lower bound accompanies every rate — 100% is never printed
  as a bare headline,
* denominators are explicit: ``judged`` (inspector produced a verdict) with
  ``coverage = judged / produced``; missing files / inspector crashes are
  listed, never silently dropped,
* opens-clean for these same files is ALREADY PUBLISHED in the workspace
  ``docs/openrate/report.json`` — cross-referenced in the metric note, not
  re-claimed here,
* ``generatedAt`` stays ``null`` (root stamps it; no wall clock here).

Exit codes: 0 = report written (regardless of pass rate — see honesty rule);
3 = fail-closed, ZERO authored records matched (empty measurement must not
masquerade as a benign publish); 2 = argparse usage errors (missing manifest).

Usage::

    .venv/bin/python scripts/corpus_authoring_quality.py \
        --corpus-root work/openrate-corpus \
        --manifest work/openrate-corpus/manifest.json \
        --out work/m9-prelim/authoring-quality.v1.json

Optionally ``--v2-manifest work/openrate-corpus-v2/manifest.json`` folds in the
v2 authored strata (``authored-toc`` / ``reading-runformat``). Those are built
directly (no document plan), so they are inspected with ``plan=None`` and no
공문 lint.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

# Make ``import hwpx`` work when run straight from a checkout (scripts/ sibling
# of src/), without requiring an install. Harmless if hwpx is already importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_SCRIPTS = Path(__file__).resolve().parent

# The workspace-level published open-rate report these same files appear in.
OPENRATE_REPORT_POINTER = "docs/openrate/report.json (workspace root: hwpx/docs/openrate/report.json)"

V2_AUTHORED_STRATA = ("authored-toc", "reading-runformat")

# A quality inspector maps (path, plan|None) -> the report dict of
# hwpx.authoring.inspect_document_authoring_quality. A gongmun lint maps a path
# -> the report dict of hwpx.tools.official_lint.inspect_official_document_style.
QualityInspector = Callable[[str, Mapping[str, Any] | None], dict[str, Any]]
GongmunLint = Callable[[str], dict[str, Any]]


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Pure alignment helpers (no hwpx import, no I/O beyond Path.exists) — these
# are what the unit tests pin.
# --------------------------------------------------------------------------- #

_AUTHORED_ID_RE = re.compile(r"^authored-([a-z]+)-\d+$")


def authored_type_from_seed(seed: Any) -> str | None:
    """``authored:gongmun:00`` -> ``gongmun`` (None when not an authored seed)."""

    parts = str(seed or "").split(":")
    if len(parts) >= 2 and parts[0] == "authored":
        return parts[1] or None
    return None


def authored_type_from_id(rec_id: Any) -> str | None:
    """``authored-gongmun-00`` -> ``gongmun`` (fallback when the seed is absent)."""

    match = _AUTHORED_ID_RE.match(str(rec_id or ""))
    return match.group(1) if match else None


def resolve_record_path(
    record: Mapping[str, Any], corpus_root: Path, subdir: str
) -> Path | None:
    """Resolve a manifest ``output_path`` against a possibly-relocated corpus.

    Preference: the recorded absolute path if it exists, else
    ``corpus_root/<subdir>/<basename>`` (the generator's layout). Returns the
    best candidate even if missing — the caller records missing_file honestly.
    """

    out = record.get("output_path")
    if not out:
        return None
    recorded = Path(str(out))
    if recorded.exists():
        return recorded
    return corpus_root / subdir / recorded.name


def match_records(
    manifest: Mapping[str, Any],
    plans_by_id: Mapping[str, tuple[str, Mapping[str, Any]]],
    *,
    corpus_root: Path,
    v2_manifest: Mapping[str, Any] | None = None,
    v2_corpus_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Align manifest authored records to regenerated plans.

    v1: records with ``bucket == "authored"``, matched to ``authored_plans()``
    output by record id; the manifest seed must equal the plan seed or the plan
    is NOT used (seed_mismatch — the generator drifted since the freeze; using
    a drifted plan would silently measure the wrong thing).

    v2 (optional): records whose ``stratum`` is an authored stratum
    (``authored-toc`` / ``reading-runformat``); no plan exists by design.

    Returns (entries, alignment) where alignment lists every anomaly.
    """

    entries: list[dict[str, Any]] = []
    seed_mismatches: list[dict[str, Any]] = []
    plan_unmatched: list[str] = []

    for rec in manifest.get("records") or manifest.get("items") or []:
        if str(rec.get("bucket", "")) != "authored":
            continue
        rec_id = str(rec.get("id", ""))
        seed = rec.get("seed")
        doc_type = authored_type_from_seed(seed) or authored_type_from_id(rec_id) or "unknown"
        plan: Mapping[str, Any] | None = None
        mismatch = False
        if rec_id in plans_by_id:
            plan_seed, candidate = plans_by_id[rec_id]
            if seed is not None and str(seed) != str(plan_seed):
                mismatch = True
                seed_mismatches.append(
                    {"id": rec_id, "manifest_seed": seed, "plan_seed": plan_seed}
                )
            else:
                plan = candidate
        else:
            plan_unmatched.append(rec_id)
        entries.append(
            {
                "id": rec_id,
                "source": "v1",
                "type": doc_type,
                "record": rec,
                "plan": plan,
                "seed_mismatch": mismatch,
                "path": resolve_record_path(rec, corpus_root, "authored"),
            }
        )

    if v2_manifest is not None:
        v2_root = v2_corpus_root or corpus_root
        for rec in v2_manifest.get("records") or v2_manifest.get("items") or []:
            stratum = str(rec.get("stratum") or rec.get("bucket") or "")
            if stratum not in V2_AUTHORED_STRATA:
                continue
            rec_id = str(rec.get("id", ""))
            entries.append(
                {
                    "id": rec_id,
                    "source": "v2",
                    "type": stratum,
                    "record": rec,
                    "plan": None,  # built directly, no document plan by design
                    "seed_mismatch": False,
                    "path": resolve_record_path(rec, v2_root, stratum),
                }
            )

    alignment = {
        "matched": len(entries),
        "with_plan": sum(1 for e in entries if e["plan"] is not None),
        "seed_mismatches": seed_mismatches,
        "plan_unmatched": plan_unmatched,
    }
    return entries, alignment


# --------------------------------------------------------------------------- #
# Evaluation (inspector calls are injected — unit tests use fakes)
# --------------------------------------------------------------------------- #

def evaluate_entries(
    entries: Iterable[Mapping[str, Any]],
    *,
    quality_inspector: QualityInspector,
    gongmun_lint: GongmunLint,
    verify_sha: bool = True,
) -> list[dict[str, Any]]:
    """Run the inspectors over matched entries -> flat per-file result rows.

    Never raises on a bad file: inspector crashes become ``inspect_error`` rows
    (listed failures), missing files become ``missing_file`` rows. Nothing is
    silently dropped from the denominators.
    """

    results: list[dict[str, Any]] = []
    for entry in entries:
        rec = entry["record"]
        row: dict[str, Any] = {
            "id": entry["id"],
            "source": entry["source"],
            "type": entry["type"],
            "path": str(entry["path"]) if entry["path"] else None,
            "plan_used": entry["plan"] is not None,
            "seed_mismatch": bool(entry.get("seed_mismatch")),
            "status": None,
            "sha_ok": None,
            "quality_pass": None,
            "gaps": [],
            "korean_proofing_status": None,
            "structure_pass": None,
            "lint_violations": [],
            "gongmun_embedded_structure_pass": None,
            "error": None,
        }
        if not rec.get("produced", False):
            row["status"] = "withheld"
            row["error"] = rec.get("withheld_reason") or "composer withheld (produced=false)"
            results.append(row)
            continue
        path = entry["path"]
        if path is None or not Path(path).exists():
            row["status"] = "missing_file"
            row["error"] = f"produced file not found: {path}"
            results.append(row)
            continue
        if verify_sha and rec.get("output_sha256"):
            try:
                row["sha_ok"] = sha256_file(Path(path)) == rec["output_sha256"]
            except OSError as exc:
                row["sha_ok"] = False
                row["error"] = f"sha256 read failed: {exc}"
        try:
            report = quality_inspector(str(path), entry["plan"])
        except Exception as exc:  # a file our own library cannot inspect is a listed failure
            row["status"] = "inspect_error"
            row["error"] = f"{type(exc).__name__}: {exc}"[:400]
            results.append(row)
            continue
        row["status"] = "judged"
        row["quality_pass"] = bool(report.get("pass", False))
        row["gaps"] = [str(g) for g in (report.get("gaps") or [])]
        # recorded verbatim — expected 'unverified'; NEVER coerced (FR-006 honesty)
        row["korean_proofing_status"] = report.get("korean_proofing_status")
        embedded = report.get("gongmun_structure")
        if isinstance(embedded, Mapping):
            row["gongmun_embedded_structure_pass"] = bool(embedded.get("structure_pass", False))
        if entry["type"] == "gongmun":
            try:
                lint = gongmun_lint(str(path))
                row["structure_pass"] = bool(lint.get("structure_pass", False))
                row["lint_violations"] = [
                    {
                        "rule": str(v.get("rule")),
                        "severity": str(v.get("severity")),
                        "paragraph_index": v.get("paragraph_index"),
                        "message": str(v.get("message", "")),
                    }
                    for v in (lint.get("violations") or [])
                ]
            except Exception as exc:
                # structure verdict unavailable — honest None, listed as an error
                row["error"] = f"gongmun lint failed: {type(exc).__name__}: {exc}"[:400]
        results.append(row)
    return results


# --------------------------------------------------------------------------- #
# Pure aggregation (unit-tested math)
# --------------------------------------------------------------------------- #

def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def _aggregate_cell(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [r for r in rows if r["status"] == "judged"]
    withheld = [r for r in rows if r["status"] == "withheld"]
    produced_n = len(rows) - len(withheld)
    quality_passes = sum(1 for r in judged if r["quality_pass"])
    gap_hist: Counter[str] = Counter()
    for r in judged:
        gap_hist.update(r["gaps"])
    proofing: Counter[str] = Counter(
        str(r["korean_proofing_status"]) for r in judged if r["korean_proofing_status"] is not None
    )
    cell: dict[str, Any] = {
        "records": len(rows),
        "withheld": len(withheld),
        "produced": produced_n,
        "judged": len(judged),
        "missing_file": sum(1 for r in rows if r["status"] == "missing_file"),
        "inspect_error": sum(1 for r in rows if r["status"] == "inspect_error"),
        "sha_mismatch": sum(1 for r in rows if r["sha_ok"] is False),
        "coverage": _rate(len(judged), produced_n),
        "quality": {
            "pass": quality_passes,
            "fail": len(judged) - quality_passes,
            "rate": _rate(quality_passes, len(judged)),
            "rate_lower_bound": rule_of_three_lower_bound(
                len(judged) - quality_passes, len(judged)
            ),
            "rate_interval": rule_of_three_text(len(judged) - quality_passes, len(judged)),
        },
        "gap_histogram": dict(sorted(gap_hist.items())),
        "proofing_status": dict(sorted(proofing.items())),
    }

    # structure_pass (the 공문 hard-gate) only over rows that carry a verdict.
    structure_rows = [r for r in judged if r["structure_pass"] is not None]
    if structure_rows:
        s_pass = sum(1 for r in structure_rows if r["structure_pass"])
        lint_hist: Counter[str] = Counter()
        for r in structure_rows:
            lint_hist.update(
                f"{v['rule']}:{v['severity']}" for v in r["lint_violations"]
            )
        embedded_disagree = [
            r["id"]
            for r in structure_rows
            if r["gongmun_embedded_structure_pass"] is not None
            and r["gongmun_embedded_structure_pass"] != r["structure_pass"]
        ]
        cell["structure"] = {
            "judged": len(structure_rows),
            "pass": s_pass,
            "fail": len(structure_rows) - s_pass,
            "rate": _rate(s_pass, len(structure_rows)),
            "rate_lower_bound": rule_of_three_lower_bound(
                len(structure_rows) - s_pass, len(structure_rows)
            ),
            "rate_interval": rule_of_three_text(
                len(structure_rows) - s_pass, len(structure_rows)
            ),
            "lint_violation_histogram": dict(sorted(lint_hist.items())),
            "embedded_gate_disagreements": embedded_disagree,
        }
    else:
        cell["structure"] = None

    failures = []
    for r in rows:
        reason = None
        if r["status"] in ("withheld", "missing_file", "inspect_error"):
            reason = r["error"] or r["status"]
        elif r["status"] == "judged" and (
            not r["quality_pass"] or r["structure_pass"] is False
        ):
            parts = []
            if not r["quality_pass"]:
                parts.append("quality gaps: " + "; ".join(r["gaps"] or ["(none listed)"]))
            if r["structure_pass"] is False:
                errs = [
                    f"{v['rule']}({v['message']})"
                    for v in r["lint_violations"]
                    if v["severity"] == "error"
                ]
                parts.append("공문 structure hard-gate FAILED: " + "; ".join(errs or ["?"]))
            reason = " | ".join(parts)
        if reason is not None:
            failures.append(
                {"id": r["id"], "path": r["path"], "reason": reason, "gaps": r["gaps"]}
            )
    cell["failures"] = failures
    return cell


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-type aggregation + honest totals. Pure (no I/O, no clock)."""

    by_type: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for row in results:
        by_type.setdefault(str(row["type"]), []).append(row)
    types = OrderedDict(
        (name, _aggregate_cell(rows)) for name, rows in sorted(by_type.items())
    )
    totals = _aggregate_cell(results)
    return {"types": types, "totals": totals}


def build_report(
    results: list[dict[str, Any]],
    alignment: Mapping[str, Any],
    *,
    sources: Mapping[str, Any],
    tool_versions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the full report dict (pure; no I/O, no clock)."""

    agg = aggregate(results)
    failures: list[dict[str, Any]] = []
    for name, cell in agg["types"].items():
        for f in cell["failures"]:
            failures.append({"type": name, **f})
    return {
        "schemaVersion": 1,
        "generatedAt": None,  # root stamps; never datetime.now (constitution V)
        "feature": "010-corpus-publication",
        "axis": "authoring",
        "metric": {
            "headline": "authoring quality over the FROZEN authored corpus: "
            "quality_pass rate (structural gates + gaps) per document type, plus the "
            "공문 hard-gate structure_pass rate (ERROR-severity spine checks)",
            "judge": "oracle-free structural inspectors "
            "(inspect_document_authoring_quality + inspect_official_document_style); "
            "no Hancom render claim is made here",
            "honestyRule": "FR-006: the v1 authored docs were generated with quality "
            "reports DISCARDED; this is a post-hoc measurement of the frozen bytes. "
            "The rate that comes out is the rate that gets published — NO "
            "regenerate-until-green. A low number is publishable truth.",
            "opensCleanCrossReference": "opens-clean/parsed for these same files is "
            f"ALREADY PUBLISHED in {OPENRATE_REPORT_POINTER}; cross-referenced here, "
            "NOT re-claimed and NOT re-measured.",
            "renderSampleNote": "render_checked for authored files is supplied by the "
            "box/Mac render leg (P2/OD-4), not by this aggregator — never fabricated here.",
            "proofingNote": "korean_proofing_status is recorded verbatim (expected "
            "'unverified' — no free offline Korean proofing oracle exists; never coerced).",
            "intervalRule": "rule of three: k=0 -> >= 1 - 3/N (95% CI); 100% is never "
            "printed as a bare headline",
            "denominatorRule": "rates are over JUDGED files (inspector returned a "
            "verdict); coverage = judged / produced; withheld / missing / inspect_error "
            "are listed and counted, never silently dropped",
        },
        "sources": dict(sources),
        "alignment": dict(alignment),
        "types": agg["types"],
        "totals": agg["totals"],
        "failures": failures,
        "per_file": results,
        "tool_versions": dict(tool_versions or {}),
    }


# --------------------------------------------------------------------------- #
# Real inspector wiring + CLI
# --------------------------------------------------------------------------- #

def _real_inspectors() -> tuple[QualityInspector, GongmunLint]:
    from hwpx.authoring import inspect_document_authoring_quality
    from hwpx.tools.official_lint import inspect_official_document_style

    def quality(path: str, plan: Mapping[str, Any] | None) -> dict[str, Any]:
        return inspect_document_authoring_quality(path, plan=plan)

    def lint(path: str) -> dict[str, Any]:
        return inspect_official_document_style(Path(path), document_type="공문")

    return quality, lint


def _load_authored_plans() -> dict[str, tuple[str, Mapping[str, Any]]]:
    """Deterministic v1 plan regeneration — READ-ONLY import of the generator."""

    gen = _load_sibling("generate_openrate_corpus")
    return {rec_id: (seed, plan) for rec_id, seed, plan in gen.authored_plans()}


def _collect_tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    try:
        from importlib.metadata import version

        versions["python-hwpx"] = version("python-hwpx")
    except Exception:
        versions["python-hwpx"] = None
    versions["python"] = sys.version.split()[0]
    return versions


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _fmt_rate(rate: float | None, lb: float | None) -> str:
    if rate is None:
        return "N/A"
    lb_txt = f" (95% lower bound >= {lb * 100:.1f}%)" if lb is not None else ""
    return f"{rate * 100:.1f}%{lb_txt}"


def _print_summary(report: dict[str, Any]) -> None:
    print("=" * 74)
    print("AUTHORING QUALITY — frozen authored corpus (specs/010 P3, oracle-free)")
    print("=" * 74)
    for name, cell in report["types"].items():
        q = cell["quality"]
        line = (
            f"{name:<20} judged {cell['judged']}/{cell['produced']}"
            f"  quality_pass {q['pass']}/{cell['judged']}"
            f" = {_fmt_rate(q['rate'], q['rate_lower_bound'])}"
        )
        s = cell.get("structure")
        if s:
            line += (
                f"  |  공문 structure_pass {s['pass']}/{s['judged']}"
                f" = {_fmt_rate(s['rate'], s['rate_lower_bound'])}"
            )
        print(line)
        for gap, n in cell["gap_histogram"].items():
            print(f"    gap x{n}: {gap}")
        if s and s["lint_violation_histogram"]:
            for rule, n in s["lint_violation_histogram"].items():
                print(f"    lint x{n}: {rule}")
    t = report["totals"]
    print("-" * 74)
    print(
        f"{'TOTAL':<20} judged {t['judged']}/{t['produced']}"
        f"  quality_pass {t['quality']['pass']}/{t['judged']}"
        f" = {_fmt_rate(t['quality']['rate'], t['quality']['rate_lower_bound'])}"
    )
    print(f"proofing status distribution: {t['proofing_status']}")
    if report["failures"]:
        print("-" * 74)
        print(f"FAILURES ({len(report['failures'])}) — publishable truth, listed per file:")
        for f in report["failures"]:
            print(f"  [{f['type']}] {f['id']}: {f['reason']}")
    print("-" * 74)
    print("NOTE: opens-clean for these same files is already published in")
    print(f"      {OPENRATE_REPORT_POINTER} — cross-referenced, not re-claimed.")
    print("HONESTY (FR-006): v1 quality reports were discarded at generation time;")
    print("      the numbers above are the post-hoc truth of the frozen bytes.")
    print("      NO regenerate-until-green. A low rate is published as-is.")
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus_authoring_quality",
        description="Aggregate authoring-quality (gates + 공문 hard-gate) over the "
        "frozen authored corpus into an honest per-type report.",
    )
    parser.add_argument(
        "--corpus-root",
        default="work/openrate-corpus",
        help="frozen v1 corpus root (relocation fallback for manifest paths)",
    )
    parser.add_argument(
        "--manifest",
        default="work/openrate-corpus/manifest.json",
        help="frozen v1 corpus manifest (default: work/openrate-corpus/manifest.json)",
    )
    parser.add_argument(
        "--v2-manifest",
        default=None,
        help="optional v2 manifest — folds in the authored-toc / reading-runformat "
        "strata (inspected plan-less; no 공문 lint)",
    )
    parser.add_argument(
        "--v2-corpus-root",
        default=None,
        help="v2 corpus root (default: the v2 manifest's parent directory)",
    )
    parser.add_argument(
        "--out",
        default="work/m9-prelim/authoring-quality.json",
        help="output report path (default: work/m9-prelim/authoring-quality.json)",
    )
    parser.add_argument(
        "--no-sha-check",
        action="store_true",
        help="skip the frozen-corpus sha256 drift check (faster; drift stays unflagged)",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    if not Path(args.manifest).exists():
        parser.error(f"manifest not found: {args.manifest}")
    manifest = _load_json(args.manifest)
    v2_manifest = None
    v2_root = None
    if args.v2_manifest:
        if not Path(args.v2_manifest).exists():
            parser.error(f"v2 manifest not found: {args.v2_manifest}")
        v2_manifest = _load_json(args.v2_manifest)
        v2_root = Path(args.v2_corpus_root or Path(args.v2_manifest).parent)

    plans_by_id = _load_authored_plans()
    entries, alignment = match_records(
        manifest,
        plans_by_id,
        corpus_root=Path(args.corpus_root),
        v2_manifest=v2_manifest,
        v2_corpus_root=v2_root,
    )

    quality_inspector, gongmun_lint = _real_inspectors()
    results = evaluate_entries(
        entries,
        quality_inspector=quality_inspector,
        gongmun_lint=gongmun_lint,
        verify_sha=not args.no_sha_check,
    )
    report = build_report(
        results,
        alignment,
        sources={
            "v1_manifest": args.manifest,
            "v1_corpus_root": args.corpus_root,
            "v2_manifest": args.v2_manifest,
        },
        tool_versions=_collect_tool_versions(),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Fail-closed: an EMPTY measurement must not look like a benign publish.
    if alignment["matched"] == 0:
        sys.stderr.write(
            f"FAIL-CLOSED: 0 authored records matched in {args.manifest}"
            + (f" + {args.v2_manifest}" if args.v2_manifest else "")
            + f". Wrote {out_path} for inspection but refusing exit 0.\n"
        )
        return 3

    _print_summary(report)
    # Deliberately NO exit-2 gate on a low pass rate (FR-006): the number above
    # is the number we publish, however low.
    print(f"wrote {out_path} (matched={alignment['matched']}, judged={report['totals']['judged']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
