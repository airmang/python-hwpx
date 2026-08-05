# SPDX-License-Identifier: Apache-2.0
"""Aggregate the v3 box run into the published measurement artifacts.

Inputs (fetched from the Windows box after ``run_v3.ps1`` completes):

* ``work/openrate-corpus-v5/manifest.json``       — what was generated, by what
* ``work/openrate-corpus-v5/verdicts_v5.jsonl``   — per-file Hancom open verdicts
* ``work/openrate-corpus-v5/render_verdicts_v5.jsonl`` — per-file PDF render verdicts
* ``work/openrate-corpus-v5/hancom_build.json``   — which Hancom judged the run,
  recorded by the run itself from the COM server binary, never hand-written

Outputs (both published, both carrying full provenance):

* ``docs/openrate/report-v5.json``    — per-stratum figures with the rule-of-three
  bound; ``hancom_build`` and ``tool_versions`` are REQUIRED fields here —
  an aggregation without them refuses to publish.
* ``docs/openrate/verdicts_v5.jsonl`` — the raw receipts re-issued with a
  ``bucket`` field per row, so a third party can reproduce every denominator
  split with ``jq`` alone. (The v2 receipts lacked this, which made the
  documented 476/506 split irreproducible from the raw file.)

Negative controls are judged first, in effect: if any control opened clean the
whole report is marked ``harness_valid: false`` and the headline figures are
withheld — a suppressed-modal default of auto-repair would otherwise count
broken files as opened.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PYTHON_HWPX = Path(__file__).resolve().parent.parent
V3_DIR = PYTHON_HWPX / "work" / "openrate-corpus-v5"
OUT_DIR = PYTHON_HWPX / "docs" / "openrate"

NEGATIVE_CONTROL_BASENAMES = {
    "corrupt_section.hwpx",
    "corrupt_header.hwpx",
    "missing_section.hwpx",
}


def rule_of_three_lower_bound(failures: int, n: int) -> float | None:
    if n <= 0:
        return None
    if failures <= 0:
        return round(max(0.0, 1.0 - 3.0 / n), 4)
    return round(max(0.0, (n - failures) / n - 3.0 / n), 4)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> int:
    manifest = json.loads((V3_DIR / "manifest.json").read_text(encoding="utf-8"))
    verdicts = _read_jsonl(V3_DIR / "verdicts_v5.jsonl")
    renders = _read_jsonl(V3_DIR / "render_verdicts_v5.jsonl")
    hancom = json.loads((V3_DIR / "hancom_build.json").read_text(encoding="utf-8-sig"))

    tool_versions = manifest.get("toolVersions") or {}
    if not tool_versions.get("python-hwpx") or not hancom.get("hancomFileVersion"):
        print(
            "REFUSING to publish: tool_versions and hancom_build are required "
            "provenance — a measurement that cannot say what produced it or "
            "what judged it is the defect this script exists to end.",
            file=sys.stderr,
        )
        return 2

    by_id = {item["id"]: item for item in manifest["items"]}

    def bucket_of(source_path: str) -> str:
        basename = source_path.replace("\\", "/").rsplit("/", 1)[-1]
        if basename in NEGATIVE_CONTROL_BASENAMES:
            return "negative-control"
        stem = basename.removesuffix(".hwpx")
        item = by_id.get(stem)
        return item["bucket"] if item else "UNKNOWN"

    # ---- negative controls validate the harness before anything is counted
    control_rows = [v for v in verdicts if bucket_of(v["sourcePath"]) == "negative-control"]
    controls_broken = [v for v in control_rows if v.get("opened")]
    harness_valid = len(control_rows) == len(NEGATIVE_CONTROL_BASENAMES) and not controls_broken

    # keep retried-verdict-wins semantics: later row for the same basename wins
    latest: dict[str, dict[str, Any]] = {}
    for row in verdicts:
        basename = row["sourcePath"].replace("\\", "/").rsplit("/", 1)[-1]
        latest[basename] = row

    # The render JSONL's first row is a _meta header carrying the box's own
    # record of which Hancom rendered — cross-check it against hancom_build.json
    # so the two provenance channels cannot silently disagree.
    render_meta = next((row for row in renders if "_meta" in row), None)
    if render_meta is not None:
        normalized = str(render_meta.get("hancomBuild", "")).replace(", ", ".")
        if normalized and normalized != hancom.get("hancomFileVersion"):
            print(
                f"REFUSING to publish: render batch says Hancom {normalized!r} "
                f"but hancom_build.json says {hancom.get('hancomFileVersion')!r}",
                file=sys.stderr,
            )
            return 2

    # render_checked (the honest third tier) = the box SaveAs succeeded with
    # nonzero bytes AND the offline fitz check opened the PDF. Either half
    # alone is not a render verification.
    fitz_path = V3_DIR / "fitz_check_v5.json"
    fitz_results: dict[str, Any] = (
        json.loads(fitz_path.read_text(encoding="utf-8")) if fitz_path.exists() else {}
    )
    render_by_id = {}
    for row in renders:
        if "_meta" in row:
            continue
        source_id = row.get("sourceId") or row.get("id")
        saved = bool(row.get("saved")) and (row.get("pdfBytes") or 0) > 0
        fitz_ok = bool(fitz_results.get(source_id, {}).get("fitzOk"))
        render_by_id[source_id] = {
            "checked": saved and fitz_ok,
            "unverified": saved and not fitz_results,  # PDF exists, fitz not run
        }

    strata: dict[str, dict[str, Any]] = {}
    unknown_rows: list[str] = []
    receipt_rows: list[dict[str, Any]] = []
    for basename, row in sorted(latest.items()):
        bucket = bucket_of(row["sourcePath"])
        receipt_rows.append({"bucket": bucket, **row})
        if bucket == "negative-control":
            continue
        if bucket == "UNKNOWN":
            unknown_rows.append(basename)
            continue
        slot = strata.setdefault(bucket, {
            "requested": manifest["counts"][bucket]["requested"],
            "produced": manifest["counts"][bucket]["produced"],
            "judged": 0, "opened": 0, "parsed": 0,
            "render_checked": 0, "render_failed": 0, "render_unavailable": 0,
        })
        slot["judged"] += 1
        if row.get("opened"):
            slot["opened"] += 1
            if (row.get("textLength") or 0) > 0:
                slot["parsed"] += 1
        stem = basename.removesuffix(".hwpx")
        render = render_by_id.get(stem)
        if render is None or render["unverified"]:
            slot["render_unavailable"] += 1
        elif render["checked"]:
            slot["render_checked"] += 1
        else:
            slot["render_failed"] += 1

    for slot in strata.values():
        failures = slot["judged"] - slot["opened"]
        slot["open_rate"] = round(slot["opened"] / slot["judged"], 4) if slot["judged"] else None
        slot["open_rate_lower_bound"] = rule_of_three_lower_bound(failures, slot["judged"])

    totals = {
        "requested": sum(s["requested"] for s in strata.values()),
        "produced": sum(s["produced"] for s in strata.values()),
        "judged": sum(s["judged"] for s in strata.values()),
        "opened": sum(s["opened"] for s in strata.values()),
        "parsed": sum(s["parsed"] for s in strata.values()),
        "render_checked": sum(s["render_checked"] for s in strata.values()),
        "render_failed": sum(s["render_failed"] for s in strata.values()),
    }
    total_failures = totals["judged"] - totals["opened"]
    totals["open_rate"] = round(totals["opened"] / totals["judged"], 4) if totals["judged"] else None
    totals["open_rate_lower_bound"] = rule_of_three_lower_bound(total_failures, totals["judged"])

    report = {
        "schemaVersion": "hwpx.openrate.report/v5",
        "scopeNote": manifest["scopeNote"],
        "harness_valid": harness_valid,
        "negative_controls": {
            "expected": sorted(NEGATIVE_CONTROL_BASENAMES),
            "judged": len(control_rows),
            "wrongly_opened": [v["sourcePath"] for v in controls_broken],
        },
        "tool_versions": tool_versions,
        "hancom_build": hancom.get("hancomFileVersion"),
        "hancom_exe_path": hancom.get("hancomExePath"),
        "box_os": hancom.get("osVersion"),
        "measured_at": hancom.get("measuredAt"),
        "generator_manifest_schema": manifest["schemaVersion"],
        "strata": {name: strata[name] for name in sorted(strata)},
        "totals": totals if harness_valid else None,
        "unknown_rows": unknown_rows,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "report-v5.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipts_path = OUT_DIR / "verdicts_v5.jsonl"
    receipts_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in receipt_rows) + "\n",
        encoding="utf-8",
    )

    print(f"harness_valid : {harness_valid}")
    if not harness_valid:
        print(f"  wrongly opened controls: {[v['sourcePath'] for v in controls_broken]}")
    print(f"hancom_build  : {report['hancom_build']}")
    print(f"tool_versions : {tool_versions}")
    for name in sorted(strata):
        s = strata[name]
        print(f"  {name:20s} opened {s['opened']:3d}/{s['judged']:3d}"
              f"  parsed {s['parsed']:3d}"
              f"  render {s['render_checked']:3d}ok/{s['render_failed']}fail/{s['render_unavailable']}n.a."
              f"  (lb {s['open_rate_lower_bound']})")
    if totals["judged"]:
        print(f"  {'TOTAL':20s} opened {totals['opened']}/{totals['judged']}"
              f"  (lb {totals['open_rate_lower_bound']})")
    if unknown_rows:
        print(f"  UNKNOWN rows: {unknown_rows}")
    print(f"report   : {report_path}")
    print(f"receipts : {receipts_path}")
    return 0 if harness_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
