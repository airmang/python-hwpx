# SPDX-License-Identifier: Apache-2.0
"""Emit the EXACT ordered file list for the .161 box open-rate run (specs/007, S1).

The runbook previously globbed C:\\openrate\\corpus recursively, which also opened
the two mail-merge SOURCE TEMPLATES (mail-merge/_templates/) that are NOT in the
frozen manifest — wasting babysit clears and mislabelling the population. This
helper reads the frozen manifest + negatives.json and writes the precise list of
box paths to open, so the population equals exactly {100 produced} ∪ {7 negatives}
and nothing else. Any stray file in the tree is simply never listed.

Ordering: NEGATIVES FIRST (the spike gate — a must_refuse leak surfaces in ~7
opens, before the operator commits to the full 100-file sitting), then produced.

The box then runs:
    $files = Get-Content C:\\openrate\\box_run.filelist
    C:\\openrate\\hancom_open_rate.ps1 -Path $files -OutJsonl C:\\openrate\\verdicts.jsonl -ProbeRepairMode

corpus v2 (specs/010): pass ``--combined`` with the combined v1+v2 manifest
(records carry ``box_rel``; the box mirrors ``{v1/**, v2/**, shipped/**}``).
Without the flag, behavior is byte-identical to the frozen v1 run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # python-hwpx/
CORPUS = ROOT / "work" / "openrate-corpus"


def _relpath_under_corpus(abs_path: str) -> str:
    """Path relative to the corpus root (the box mirrors this tree)."""
    p = Path(abs_path).resolve()
    try:
        return p.relative_to(CORPUS.resolve()).as_posix()
    except ValueError:
        # Not under the corpus tree (shouldn't happen for a frozen corpus): fall
        # back to the basename so it still lands under the mirrored root.
        return p.name


def _to_box_path(rel: str, box_root: str) -> str:
    sep = "\\" if "\\" in box_root or ":" in box_root else "/"
    rel = rel.replace("/", sep)
    return box_root.rstrip("/\\") + sep + rel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="openrate_box_filelist", description=__doc__)
    ap.add_argument("--manifest", default=str(CORPUS / "manifest.json"))
    ap.add_argument("--negatives-manifest", default=str(CORPUS / "_negatives" / "negatives.json"))
    ap.add_argument("--box-root", default="C:\\openrate\\corpus",
                    help="the box path that the corpus tree is rsync'd to")
    ap.add_argument("--out", default=str(CORPUS / "box_run.filelist"))
    ap.add_argument("--combined", action="store_true",
                    help="the manifest is a combined v1+v2 manifest "
                         "(hwpx.openrate.combined-manifest.v1) whose records carry "
                         "box_rel; the box mirrors the {v1/**, v2/**, shipped/**} "
                         "layout, so negatives (which live in the v1 tree) are "
                         "prefixed v1/. Default (off) keeps v1 behavior byte-identical.")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    negatives = json.loads(Path(args.negatives_manifest).read_text(encoding="utf-8"))

    lines: list[str] = []

    # Negatives FIRST (spike gate). Ordered must_refuse before expected_refuse.
    neg_records = list(negatives.get("negatives", []))
    neg_records.sort(key=lambda r: 0 if r.get("tier") == "must_refuse" else 1)
    hard = sum(1 for r in neg_records if r.get("tier") == "must_refuse")
    soft = len(neg_records) - hard
    for r in neg_records:
        rel = _relpath_under_corpus(str(r["path"]))
        if args.combined:
            rel = "v1/" + rel  # negatives live inside the mirrored v1 tree
        lines.append(_to_box_path(rel, args.box_root))

    # Produced files (frozen manifest population).
    # produced default MUST match corpus_open_rate.py (output_path-based), so the
    # box population and the aggregator population can never diverge.
    produced = [
        r for r in (manifest.get("records") or manifest.get("items") or [])
        if r.get("output_path") and bool(r.get("produced", r.get("output_path") is not None))
    ]
    for r in produced:
        if args.combined:
            rel = r.get("box_rel")
            if not rel:  # fail closed: a combined record without box_rel would
                # silently drop a population member from the box run.
                sys.stderr.write(
                    f"ERROR: combined manifest record {r.get('id')!r} has no box_rel "
                    "— regenerate the combined manifest (merge_manifests).\n"
                )
                return 1
        else:
            rel = _relpath_under_corpus(str(r["output_path"]))
        lines.append(_to_box_path(rel, args.box_root))

    out = Path(args.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total = len(lines)
    print(f"wrote {out}")
    print(f"  negatives : {len(neg_records)} ({hard} must_refuse + {soft} expected_refuse) — opened FIRST")
    print(f"  produced  : {len(produced)}")
    print(f"  TOTAL     : {total}  <-- operator tripwire: the box must open exactly this many files")
    # Guard: the manifest declares produced_total; the emitted count must match it.
    declared = manifest.get("produced_total")
    if declared is not None and declared != len(produced):
        sys.stderr.write(
            f"WARNING: manifest.produced_total={declared} but {len(produced)} produced records "
            "were listed — corpus/manifest drift.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
