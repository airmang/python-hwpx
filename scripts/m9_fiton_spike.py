#!/usr/bin/env python3
"""S-085 P0: refill the M9 form-fit pairs with the REAL fit policy.

The M9 corpus filled cells with ``FitPolicy.keep()`` (fit disabled), which is
what the published 49.2% differential measured. This spike refills the SAME
(base form, length) combos with the engine default
``FitPolicy(mode="wrap_then_shrink", overflow="fail")`` so the differential can
measure the engine's actual capability. Policy refusals (overflow="fail") are
recorded as ``refused_by_policy`` — for overflow-stress variants that is the
fail-closed SUCCESS mode, never hidden.

Outputs (never touches the frozen corpus):
  work/m9-fitspike/fills/<id>.hwpx
  work/m9-fitspike/spike_manifest.json   (differential-driver compatible)
  work/m9-fitspike/fill_receipt.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    LENGTH_SWEEP,
    _first_fillable_cell,
    form_fit_inputs,
    plan_form_fit_wide,
    v1_formfit_combos,
)
from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.form_fit import FitPolicy  # noqa: E402
from hwpx.form_fit.apply import fit_cell_text  # noqa: E402


def v1_formfit_plan(v1_manifest: dict[str, Any]) -> list[tuple[str, Path, str]]:
    """Reconstruct the v1 form-fit combos as (tag, input_path, length)."""
    plans: list[tuple[str, Path, str]] = []
    for rec in v1_manifest.get("records", []):
        if rec.get("bucket") != "form-fit" or not rec.get("produced"):
            continue
        seed = rec.get("seed", "")
        # seed = "formfit:{tag}:{length}" where tag contains one colon
        parts = seed.split(":")
        if len(parts) < 3 or parts[0] != "formfit":
            continue
        length = parts[-1]
        tag = ":".join(parts[1:-1])
        input_path = rec.get("input_path")
        if not input_path or length not in LENGTH_SWEEP:
            continue
        plans.append((tag, Path(input_path), length))
    return plans


def main() -> int:
    out_dir = ROOT / "work" / "m9-fitspike"
    fills = out_dir / "fills"
    fills.mkdir(parents=True, exist_ok=True)

    v1_manifest = json.loads(
        (ROOT / "work" / "openrate-corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    inputs = [(tag, p) for tag, p in form_fit_inputs() if p.exists()]
    wide = plan_form_fit_wide(inputs, v1_formfit_combos(v1_manifest))
    v1_plan = v1_formfit_plan(v1_manifest)

    combos: list[tuple[str, str, Path, str]] = []
    for tag, in_path, length in v1_plan:
        combos.append(("form-fit", tag, in_path, length))
    for tag, in_path, length in wide:
        combos.append(("form-fit-wide", tag, in_path, length))

    policy = FitPolicy()  # wrap_then_shrink, overflow="fail", min 8pt
    records: list[dict[str, Any]] = []
    filled = refused = errored = no_cell = 0
    for bucket, tag, in_path, length in combos:
        rec_id = f"fiton-{tag.replace(':', '_')}-{length}"
        out_path = fills / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        value = LENGTH_SWEEP[length]
        status = "filled"
        reason: str | None = None
        try:
            doc = HwpxDocument.open(in_path)
            cell = _first_fillable_cell(doc)
            if cell is None:
                status, reason = "no_fillable_cell", "no empty table cell"
                doc.close()
            else:
                try:
                    fit_cell_text(cell, value, policy, document=doc)
                    doc.save_to_path(out_path)
                finally:
                    doc.close()
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}".strip()[:300]
            if "overflow" in message.lower() or "fit" in message.lower():
                status, reason = "refused_by_policy", message
            else:
                status, reason = "error", message
        if status == "filled" and not out_path.exists():
            status, reason = "error", "no output written"
        if status == "filled":
            filled += 1
        elif status == "refused_by_policy":
            refused += 1
        elif status == "no_fillable_cell":
            no_cell += 1
        else:
            errored += 1
        records.append({
            "id": rec_id,
            "bucket": bucket,
            "stratum": bucket,
            "seed": f"fiton:{tag}:{length}",
            "requested": True,
            "produced": status == "filled",
            "withheld_reason": None if status == "filled" else f"{status}: {reason}",
            "output_path": str(out_path) if status == "filled" else None,
            "input_path": str(in_path),
            "value_length_class": length,
            "fit_policy": {"mode": policy.mode, "overflow": policy.overflow,
                            "min_font_pt": policy.min_font_pt},
            "fill_status": status,
            "fill_reason": reason,
        })
        print(f"[{bucket}] {rec_id}: {status}{' — ' + reason if reason else ''}")

    manifest = {
        "schemaVersion": "hwpx.fiton-spike-manifest.v1",
        "note": "S-085 P0 fit-on refill of the M9 form-fit combos; frozen corpus untouched",
        "policy": {"mode": policy.mode, "overflow": policy.overflow,
                    "min_font_pt": policy.min_font_pt},
        "records": records,
    }
    (out_dir / "spike_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    summary = {"combos": len(combos), "filled": filled,
               "refused_by_policy": refused, "no_fillable_cell": no_cell,
               "error": errored}
    (out_dir / "fill_receipt.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
