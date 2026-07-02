# SPDX-License-Identifier: Apache-2.0
"""Byte-identity corpus driver (specs/010-corpus-publication, P3 axis).

Metric row (specs/010 spec.md): "byte-identity | untouched part(content)
byte-identical 100% — PATCH-PATH ONLY | oracle-free (zip part diff) |
applied>0 docs only, zip_method split, full-save path explicitly out-of-claim".

Per corpus document this driver:

1. loads the source ``.hwpx`` bytes;
2. applies ONE deterministic ``hwpx.patch.paragraph_patch`` text edit (the
   replacement text is derived from the doc basename — no randomness), retrying
   across section parts / paragraph indexes until ``applied`` is non-empty;
3. if no paragraph is patchable the doc is classified ``not_applicable`` and is
   EXCLUDED from the denominator but listed separately (metric-vacuity guard:
   the 100% claim is never propped up by docs that were never patched);
4. for each applied doc, compares source vs patched bytes at the zip
   part-content level via ``hwpx.tools.idempotence.check_idempotent_pair`` and
   asserts the untouched-part invariant::

       untouched_ok = set(observed changed_parts) ⊆ set(result.changed_parts)
                      AND added_parts == () AND removed_parts == ()

Honesty constraints (mirrors scripts/corpus_open_rate.py):

* CLAIM SCOPE: part-content granularity; the full-save path is explicitly
  out-of-claim (python-hwpx assigns random hp:p element ids at save time, so a
  rebuild is never byte-reproducible — see the frozen-manifest determinism note).
* Denominator = APPLIED docs only (``applied > 0``); noop/skipped patches never
  count toward the claim. ``not_applicable`` docs are listed with reasons.
* 100% is never printed bare: the rule-of-three 95% lower bound accompanies the
  headline rate.
* ``zip_method`` distribution (``partial-local-record-copy`` vs
  ``zipfile-rewrite-fallback``) is published alongside — the two write paths are
  different code and must not be silently pooled.
* Fail-closed: exit 2 if ANY applied doc has an untouched part changed (the
  100% claim breaks — a REAL bug, printed loudly); exit 3 if applied == 0
  (vacuous run must not masquerade as a pass).
* ``generatedAt`` is left ``null`` — root stamps it; this script never calls
  ``datetime.now`` (deterministic, golden-friendly).
"""
from __future__ import annotations

import argparse
import glob as _glob
import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from typing import Any

# Make ``import hwpx`` work when run straight from a checkout (scripts/ sibling
# of src/), without requiring an install. Harmless if hwpx is already importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hwpx.patch import (  # noqa: E402
    BytePreservingPatchResult,
    ParagraphTextPatch,
    paragraph_patch,
)

# Same-repo private-helper reuse (script, not library surface): the paragraph
# enumeration MUST match the patcher's own span regex or the retry loop would
# probe indexes the patcher cannot see.
from hwpx.patch import _paragraph_spans, _TEXT_RE  # noqa: E402
from hwpx.tools.idempotence import check_idempotent_pair  # noqa: E402

# Interval helpers: shared with the open-rate driver so both reports print the
# same bound. Import from the sibling script when possible; otherwise duplicate
# verbatim (attributed) so the script stays standalone.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
try:
    from corpus_open_rate import rule_of_three_lower_bound, rule_of_three_text
except Exception:  # pragma: no cover - fallback when scripts/ is not importable
    # Duplicated from scripts/corpus_open_rate.py (keep in sync).
    def rule_of_three_lower_bound(failures: int, n: int) -> float | None:
        if n <= 0:
            return None
        if failures <= 0:
            return max(0.0, 1.0 - 3.0 / n)
        observed = (n - failures) / n
        return max(0.0, observed - 3.0 / n)

    def rule_of_three_text(failures: int, n: int) -> str:
        lb = rule_of_three_lower_bound(failures, n)
        if lb is None:
            return f"{failures}/{n} -> N/A (no trials)"
        return f"{failures}/{n} -> >= {lb * 100:.1f}% (95% CI, rule of three: 1 - 3/N)"


METRIC_NOTE = (
    "part-content granularity; full-save path out-of-claim (random hp:p ids)"
)

# Bound on paragraph_patch attempts per doc: every attempt (even a skip) runs
# the SavePipeline gate, so an all-unpatchable 500-paragraph doc must not cost
# 500 pipeline runs. Text-bearing paragraphs are probed first, so real corpora
# apply on the first or second attempt; a doc misclassified by the cap lands in
# not_applicable (listed, denominator-excluded) — conservative, never a false pass.
DEFAULT_MAX_ATTEMPTS = 8


# --------------------------------------------------------------------------- #
# Pure per-doc helpers (unit-testable; no CLI, no report I/O)
# --------------------------------------------------------------------------- #

def replacement_text_for(basename: str) -> str:
    """Deterministic single-line replacement text derived from the basename."""

    stem = PurePosixPath(basename).stem
    digest = hashlib.sha256(basename.encode("utf-8")).hexdigest()[:8]
    return f"BYTEID {stem} {digest}"


def _section_parts(source_bytes: bytes) -> list[tuple[str, bytes]]:
    """``[(part_name, xml_bytes)]`` for ``Contents/section*.xml``, in spine order."""

    import io
    import zipfile

    sections: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
        for name in archive.namelist():
            if name.startswith("Contents/section") and name.endswith(".xml"):
                sections.append((name, archive.read(name)))
    sections.sort(key=lambda item: item[0])
    return sections


def _candidate_indexes(section_xml: bytes) -> list[int]:
    """Paragraph indexes to try, text-bearing paragraphs first.

    Ordering only — every span stays a candidate so the retry loop degrades to
    exhaustive (up to the attempt cap) instead of silently narrowing.
    """

    spans = _paragraph_spans(section_xml)
    with_text = [s.index for s in spans if _TEXT_RE.search(s.payload)]
    without_text = [s.index for s in spans if not _TEXT_RE.search(s.payload)]
    return with_text + without_text


def patch_one_document(
    source_bytes: bytes,
    replacement: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[BytePreservingPatchResult | None, list[str], int]:
    """Apply ONE deterministic paragraph patch, retrying across indexes.

    Returns ``(result, skip_reasons, attempts)``; ``result`` is ``None`` when no
    attempt produced a non-empty ``applied`` (-> not_applicable upstream).
    """

    sections = _section_parts(source_bytes)
    reasons: list[str] = []
    if not sections:
        return None, ["no Contents/section*.xml part in package"], 0

    attempts = 0
    for section_path, section_xml in sections:
        indexes = _candidate_indexes(section_xml)
        if not indexes:
            reasons.append(f"{section_path}: no paragraph spans")
            continue
        for index in indexes:
            if attempts >= max_attempts:
                reasons.append(f"attempt cap reached ({max_attempts})")
                return None, reasons, attempts
            attempts += 1
            result = paragraph_patch(
                source_bytes,
                [ParagraphTextPatch(section_path, index, replacement)],
            )
            if result.applied and result.changed_parts:
                return result, reasons, attempts
            if result.skipped:
                reasons.append(f"{section_path}#{index}: {result.skipped[0].reason}")
            else:
                reasons.append(
                    f"{section_path}#{index}: noop (text already equals replacement)"
                )
    if not reasons:
        reasons.append("no paragraph accepted the patch")
    return None, reasons, attempts


def evaluate_untouched_parts(
    source_bytes: bytes, result: BytePreservingPatchResult
) -> dict[str, Any]:
    """The verdict core: untouched parts must be byte-identical.

    ``check_idempotent_pair`` diffs the two blobs at the part-content level;
    every observed change must be declared in ``result.changed_parts`` and no
    part may appear or vanish.
    """

    report = check_idempotent_pair(source_bytes, result.data)
    observed = set(report.changed_parts)
    declared = set(result.changed_parts)
    unexpected = sorted(observed - declared)
    untouched_ok = (
        not unexpected and not report.added_parts and not report.removed_parts
    )
    return {
        "untouched_ok": untouched_ok,
        "observed_changed_parts": sorted(observed),
        "declared_changed_parts": sorted(declared),
        "unexpected_changed_parts": unexpected,
        "added_parts": list(report.added_parts),
        "removed_parts": list(report.removed_parts),
    }


def process_document(
    path: Path,
    *,
    bucket: str = "?",
    doc_id: str | None = None,
    expected_sha256: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Full per-doc pipeline: load -> deterministic patch -> untouched verdict.

    Returns a row dict with ``status`` in {``applied``, ``not_applicable``}.
    """

    row: dict[str, Any] = {
        "id": doc_id or path.name,
        "bucket": bucket,
        "path": str(path),
    }
    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        row.update(status="not_applicable", reasons=[f"source file unreadable: {exc}"])
        return row

    if expected_sha256:
        actual = hashlib.sha256(source_bytes).hexdigest()
        row["source_sha256_ok"] = actual == expected_sha256
    else:
        row["source_sha256_ok"] = None

    replacement = replacement_text_for(path.name)
    row["replacement_text"] = replacement

    try:
        result, reasons, attempts = patch_one_document(
            source_bytes, replacement, max_attempts=max_attempts
        )
    except Exception as exc:  # a crash on real corpus bytes is a finding, not a pass
        row.update(
            status="not_applicable",
            reasons=[f"paragraph_patch raised {type(exc).__name__}: {exc}"],
        )
        return row
    row["attempts"] = attempts
    if result is None:
        row.update(status="not_applicable", reasons=reasons)
        return row

    verdict = evaluate_untouched_parts(source_bytes, result)
    row.update(
        status="applied",
        applied_count=len(result.applied),
        section_path=result.applied[0].section_path,
        paragraph_index=result.applied[0].paragraph_index,
        zip_method=result.zip_method,
        byte_identical=result.byte_identical,
        **verdict,
    )
    return row


# --------------------------------------------------------------------------- #
# Report assembly (pure; no I/O, no clock)
# --------------------------------------------------------------------------- #

def build_report(rows: list[dict[str, Any]], *, source: str = "?") -> dict[str, Any]:
    applied = [r for r in rows if r.get("status") == "applied"]
    not_applicable = [r for r in rows if r.get("status") == "not_applicable"]
    ok = [r for r in applied if r.get("untouched_ok")]
    violations = [r for r in applied if not r.get("untouched_ok")]

    zip_methods: "OrderedDict[str, int]" = OrderedDict()
    for r in applied:
        method = str(r.get("zip_method"))
        zip_methods[method] = zip_methods.get(method, 0) + 1

    buckets: "OrderedDict[str, dict[str, int]]" = OrderedDict()
    for r in rows:
        b = buckets.setdefault(
            str(r.get("bucket", "?")),
            {"applied": 0, "not_applicable": 0, "untouched_ok": 0, "violations": 0},
        )
        if r.get("status") == "applied":
            b["applied"] += 1
            if r.get("untouched_ok"):
                b["untouched_ok"] += 1
            else:
                b["violations"] += 1
        else:
            b["not_applicable"] += 1

    n = len(applied)
    failures = len(violations)
    sha_mismatches = [r["path"] for r in rows if r.get("source_sha256_ok") is False]

    return {
        "schemaVersion": 1,
        "generatedAt": None,  # root stamps; never datetime.now (constitution V)
        "feature": "010-corpus-publication",
        "axis": "byte-identity",
        "source": source,
        "metric": {
            "headline": "untouched-part byte-identity = untouched_ok / applied "
            "(every zip part NOT declared in changed_parts is byte-identical, "
            "no part added/removed)",
            "claimScope": "PATCH-PATH ONLY (hwpx.patch.paragraph_patch)",
            "granularityNote": METRIC_NOTE,
            "denominatorRule": "applied docs only (paragraph_patch applied>0); "
            "noop/skipped docs are not_applicable, excluded and listed separately "
            "(metric-vacuity guard)",
            "intervalRule": "rule of three: k=0 -> >= 1 - 3/N (95% CI); "
            "100% is never printed bare",
            "zipMethodNote": "partial-local-record-copy vs zipfile-rewrite-fallback "
            "are different write paths; the distribution is published, never pooled "
            "silently",
        },
        "totals": {
            "docs_considered": len(rows),
            "applied": n,
            "not_applicable": len(not_applicable),
            "untouched_ok": len(ok),
            "violations": failures,
            "untouched_ok_rate": _rate(len(ok), n),
            "untouched_ok_lower_bound": rule_of_three_lower_bound(failures, n),
            "untouched_ok_interval": rule_of_three_text(failures, n),
            "zip_method_distribution": dict(zip_methods),
            "byte_identical_true": sum(1 for r in applied if r.get("byte_identical")),
        },
        "strata": [
            {"bucket": name, **counts} for name, counts in buckets.items()
        ],
        "violations": violations,
        "not_applicable": [
            {"id": r.get("id"), "path": r.get("path"), "reasons": r.get("reasons", [])}
            for r in not_applicable
        ],
        "sha256_mismatches": sha_mismatches,
        "docs": rows,
        "tool_versions": _collect_tool_versions(),
    }


def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def _collect_tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    try:
        from importlib.metadata import version

        versions["python-hwpx"] = version("python-hwpx")
    except Exception:
        versions["python-hwpx"] = None
    versions["python"] = sys.version.split()[0]
    return versions


# --------------------------------------------------------------------------- #
# Input loading (manifest / glob) + CLI
# --------------------------------------------------------------------------- #

def _resolve_output_path(
    output_path: str, corpus_root: Path | None, bucket: str
) -> Path | None:
    p = Path(output_path)
    if p.is_file():
        return p
    if corpus_root is not None:
        for candidate in (
            corpus_root / output_path,
            corpus_root / bucket / p.name,
            corpus_root / p.name,
        ):
            if candidate.is_file():
                return candidate
    return None


def load_corpus_entries(
    manifest_path: Path, corpus_root: Path | None
) -> list[dict[str, Any]]:
    """Manifest records -> ``[{id, bucket, path, sha256, missing?, withheld?}]``.

    Accepts both the P1 reference schema (``items``) and the P2 frozen-manifest
    schema (``records``). Withheld records (produced=false / no output_path) are
    surfaced as not_applicable rows — never dropped silently.
    """

    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    records = list(manifest.get("records") or manifest.get("items") or [])
    entries: list[dict[str, Any]] = []
    for rec in records:
        bucket = str(rec.get("bucket", "?"))
        doc_id = str(rec.get("id") or rec.get("output_path") or "?")
        output_path = rec.get("output_path")
        produced = bool(rec.get("produced", output_path is not None))
        if not produced or output_path is None:
            entries.append(
                {
                    "id": doc_id,
                    "bucket": bucket,
                    "path": None,
                    "withheld": True,
                }
            )
            continue
        resolved = _resolve_output_path(str(output_path), corpus_root, bucket)
        entries.append(
            {
                "id": doc_id,
                "bucket": bucket,
                "path": resolved,
                "declared_path": str(output_path),
                "sha256": rec.get("output_sha256"),
                "missing": resolved is None,
            }
        )
    return entries


def run_corpus(
    entries: list[dict[str, Any]],
    *,
    source: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    progress: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        if entry.get("withheld"):
            rows.append(
                {
                    "id": entry["id"],
                    "bucket": entry["bucket"],
                    "path": None,
                    "status": "not_applicable",
                    "reasons": ["not produced (composer withheld)"],
                }
            )
            continue
        if entry.get("missing"):
            rows.append(
                {
                    "id": entry["id"],
                    "bucket": entry["bucket"],
                    "path": entry.get("declared_path"),
                    "status": "not_applicable",
                    "reasons": ["source file missing on disk (corpus drift?)"],
                }
            )
            continue
        if progress:
            sys.stderr.write(
                f"[{i + 1}/{len(entries)}] {entry['bucket']}/{Path(str(entry['path'])).name}\n"
            )
        rows.append(
            process_document(
                Path(str(entry["path"])),
                bucket=entry["bucket"],
                doc_id=entry["id"],
                expected_sha256=entry.get("sha256"),
                max_attempts=max_attempts,
            )
        )
    return build_report(rows, source=source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus_byte_patch_identity",
        description="Byte-identity corpus driver: one deterministic paragraph_patch "
        "per doc, untouched zip parts must stay byte-identical (patch path only).",
    )
    parser.add_argument(
        "--corpus-root",
        default=None,
        help="corpus root directory (used to resolve manifest-relative paths)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="frozen corpus manifest (v1 shape: records[]/items[]); defaults to "
        "<corpus-root>/manifest.json when --corpus-root is given",
    )
    parser.add_argument(
        "--glob",
        default=None,
        help="plain file glob alternative to a manifest, e.g. 'work/foo/*.hwpx'",
    )
    parser.add_argument(
        "--out",
        default="docs/byteidentity/report.json",
        help="output report.json path (default: docs/byteidentity/report.json)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"paragraph_patch attempts per doc before not_applicable "
        f"(default: {DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--progress", action="store_true", help="print per-file progress to stderr"
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    corpus_root = Path(args.corpus_root) if args.corpus_root else None

    if args.glob:
        paths = sorted(_glob.glob(args.glob))
        if not paths:
            parser.error(f"--glob matched no files: {args.glob}")
        entries = [
            {"id": Path(p).name, "bucket": "glob", "path": Path(p)} for p in paths
        ]
        source = f"glob:{args.glob}"
    else:
        manifest_path = (
            Path(args.manifest)
            if args.manifest
            else (corpus_root / "manifest.json" if corpus_root else None)
        )
        if manifest_path is None:
            parser.error("pass --manifest (or --corpus-root with a manifest.json), or --glob")
        if not manifest_path.is_file():
            parser.error(f"manifest not found: {manifest_path}")
        entries = load_corpus_entries(manifest_path, corpus_root)
        source = f"manifest:{manifest_path}"

    report = run_corpus(
        entries,
        source=source,
        max_attempts=args.max_attempts,
        progress=args.progress,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    totals = report["totals"]
    for path in report["sha256_mismatches"]:
        sys.stderr.write(f"WARNING: source sha256 mismatch (corpus drift?): {path}\n")

    # Fail-closed exits, most severe first.
    if totals["violations"] > 0:
        sys.stderr.write(
            "BYTE_IDENTITY_VIOLATION: untouched zip part(s) changed on the patch "
            "path — the 100% untouched-part claim is BROKEN. This is a real bug "
            "find, not a reporting artifact. Offending docs:\n"
        )
        for row in report["violations"]:
            sys.stderr.write(
                f"  {row['path']}: unexpected={row.get('unexpected_changed_parts')} "
                f"added={row.get('added_parts')} removed={row.get('removed_parts')}\n"
            )
        sys.stderr.write(f"wrote {out_path} for inspection; refusing exit 0\n")
        return 2
    if totals["applied"] == 0:
        sys.stderr.write(
            f"METRIC_VACUOUS: 0 of {totals['docs_considered']} docs accepted a "
            "paragraph patch (applied==0). The byte-identity claim has an empty "
            f"denominator and must not be published. Wrote {out_path} for "
            "inspection; refusing exit 0.\n"
        )
        return 3

    print(
        f"wrote {out_path} (applied={totals['applied']}, "
        f"not_applicable={totals['not_applicable']}, "
        f"untouched_ok={totals['untouched_ok']}, "
        f"rate={totals['untouched_ok_rate']}, "
        f"interval='{totals['untouched_ok_interval']}', "
        f"zip_methods={totals['zip_method_distribution']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
