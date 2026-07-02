# SPDX-License-Identifier: Apache-2.0
"""010-corpus-publication P3 — committed PII zero-leak corpus sweep.

Consumes the corpus-v2 manifest (``work/openrate-corpus-v2/manifest.json``),
selects every record that carries ``pii_probe_values`` (raw synthetic
rrn/phone/email/card written by the pii-merge stratum generator), and runs the
proven M5 zero-leak algorithm (demo/M5-pii/build_demo.py) as a COMMITTED,
reproducible script over two legs:

* ENGINE leg — read the produced .hwpx bytes, extract text via the python-hwpx
  reading surface with NO masking (``hwpx.tools.exporter.export_text``: what is
  actually written in the document), then for every raw probe value assert
  ABSENCE (presence = leak) AND assert the expected masked form
  (``hwpx.tools.pii.mask_value``) IS present — masking actually engaged, the
  value was not merely dropped.
* MCP leg — drive the three shipped extract surfaces IN-PROCESS with their
  default ``mask=True`` (``get_document_text`` / ``hwpx_to_markdown`` /
  ``hwpx_extract_json``) and deep-scan every returned payload recursively for
  the same raw probe values. If ``hwpx_mcp_server`` is not importable from the
  running venv the leg degrades HONESTLY to ``skipped_env`` (never a pass) —
  run the sweep from the hwpx-mcp-server venv for full two-leg coverage.

Honesty rules baked in:
* The report JSON NEVER contains raw probe values — leak entries carry the
  type, the masked form, and a JSON-path ``where`` (the record id + manifest
  identify the raw value for debugging).
* ``get_document_text`` is called with an explicit huge ``max_chars`` and a
  truncated response is reported as a scan error (truncation could hide a
  leak) — never silently accepted.
* Vacuous-measurement ban (spec pii row): exit 3 when ZERO PII-bearing records
  were actually scanned; a 0-leak claim over nothing is not a claim.

Exit codes: 0 = scanned and zero leak · 2 = ANY leak (fail-closed) ·
3 = vacuous (no PII-bearing record scanned).

Usage (engine leg only, python-hwpx venv):

    .venv/bin/python scripts/corpus_pii_leak_sweep.py \
        --manifest work/openrate-corpus-v2/manifest.json \
        --report docs/pii/leak_sweep_report.json

Usage (both legs, hwpx-mcp-server venv — its editable python-hwpx is this repo):

    ../hwpx-mcp-server/.venv/bin/python scripts/corpus_pii_leak_sweep.py ...
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_text
from hwpx.tools.pii import DEFAULT_POLICY, mask_value

PYTHON_HWPX = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PYTHON_HWPX / "work" / "openrate-corpus-v2" / "manifest.json"

REPORT_SCHEMA = "hwpx.corpus.pii-leak-sweep.v1"
MCP_SURFACES = ("get_document_text", "hwpx_to_markdown", "hwpx_extract_json")
# get_document_text defaults to a 10k-char truncation (HWPX_MCP_MAX_CHARS) —
# a truncated scan could hide a leak, so we ask for effectively-everything and
# still fail the surface if the response reports truncated=True.
MCP_SCAN_MAX_CHARS = 100_000_000

EXIT_OK = 0
EXIT_LEAK = 2
EXIT_VACUOUS = 3


# ================================================================================
# manifest selection / path resolution (pure, unit-tested)
# ================================================================================
def select_pii_records(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Records carrying at least one non-empty raw probe value."""
    selected: list[dict[str, Any]] = []
    for rec in manifest.get("records", []):
        probes = rec.get("pii_probe_values")
        if isinstance(probes, Mapping) and any(
            str(value or "").strip() for value in probes.values()
        ):
            selected.append(rec)
    return selected


def record_probes(rec: Mapping[str, Any]) -> dict[str, str]:
    """Normalized {kind: raw value} map for one record (empty values dropped)."""
    probes = rec.get("pii_probe_values") or {}
    return {
        str(kind): str(value)
        for kind, value in probes.items()
        if str(value or "").strip()
    }


def resolve_output_path(raw: str | None, corpus_root: Path) -> Path | None:
    """Resolve a manifest output_path against a possibly-relocated corpus root.

    Tries, in order: the recorded path as-is (absolute), the path joined to
    ``corpus_root`` (relative form), and — when the recorded path contains the
    corpus root's directory name — the tail re-rooted under ``corpus_root``
    (absolute paths from the generating machine). Returns None when no
    candidate exists on disk.
    """
    if not raw:
        return None
    recorded = Path(raw)
    candidates: list[Path] = []
    if recorded.is_absolute():
        candidates.append(recorded)
    else:
        candidates.append(corpus_root / recorded)
    parts = recorded.parts
    root_name = corpus_root.name
    if root_name in parts:
        idx = len(parts) - 1 - parts[::-1].index(root_name)
        tail = parts[idx + 1 :]
        if tail:
            candidates.append(corpus_root.joinpath(*tail))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


# ================================================================================
# scanning primitives (pure, unit-tested; leak entries NEVER carry raw values)
# ================================================================================
def _leak_entry(kind: str, raw_value: str, where: str) -> dict[str, str]:
    return {
        "type": kind,
        "maskedValue": mask_value(raw_value, kind, DEFAULT_POLICY),
        "where": where,
    }


def deep_scan(obj: Any, probes: Mapping[str, str], where: str = "$") -> list[dict[str, str]]:
    """Recursively scan any str/dict/list payload for raw probe substrings."""
    leaks: list[dict[str, str]] = []
    if isinstance(obj, str):
        for kind, raw_value in probes.items():
            if raw_value and raw_value in obj:
                leaks.append(_leak_entry(kind, raw_value, where))
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            leaks.extend(deep_scan(value, probes, f"{where}.{key}"))
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            leaks.extend(deep_scan(value, probes, f"{where}[{index}]"))
    return leaks


def scan_text_for_probes(text: str, probes: Mapping[str, str]) -> list[dict[str, str]]:
    return deep_scan(text, probes, where="$text")


def expected_masked_forms(probes: Mapping[str, str]) -> dict[str, str]:
    """{kind: masked form the shipped DEFAULT_POLICY must have written}."""
    return {
        kind: mask_value(raw_value, kind, DEFAULT_POLICY)
        for kind, raw_value in probes.items()
    }


def missing_masked_forms(text: str, probes: Mapping[str, str]) -> list[str]:
    """Probe kinds whose expected masked form is ABSENT from the extracted text.

    This is the build_demo.py masked-form presence check generalized: masking
    must have actually engaged (masked form present), not merely dropped the
    value. Kinds whose mask_value is a no-op are skipped (nothing checkable).
    """
    missing: list[str] = []
    for kind, masked in expected_masked_forms(probes).items():
        if masked == probes[kind]:
            continue  # mask did not transform — presence check would be meaningless
        if masked not in text:
            missing.append(kind)
    return missing


def scan_mcp_payloads(
    payloads: Mapping[str, Any], probes: Mapping[str, str]
) -> list[dict[str, str]]:
    """Deep-scan {surface: returned payload} maps; tags each leak with its surface."""
    leaks: list[dict[str, str]] = []
    for surface, payload in payloads.items():
        for leak in deep_scan(payload, probes):
            entry = dict(leak)
            entry["surface"] = surface
            leaks.append(entry)
    return leaks


# ================================================================================
# ENGINE leg — python-hwpx reading surface, unmasked raw read
# ================================================================================
def extract_engine_text(path: Path) -> str:
    """What is ACTUALLY written in the document (no masking on read)."""
    doc = HwpxDocument.open(path)
    try:
        return export_text(doc)
    finally:
        close = getattr(doc, "close", None)
        if callable(close):
            close()


def sweep_record_engine(path: Path, probes: Mapping[str, str]) -> dict[str, Any]:
    text = extract_engine_text(path)
    return {
        "leaks": scan_text_for_probes(text, probes),
        "maskedFormMissing": missing_masked_forms(text, probes),
    }


# ================================================================================
# MCP leg — the three shipped extract surfaces, in-process, mask default ON
# ================================================================================
def load_mcp_server() -> tuple[Any | None, str | None]:
    """(module, None) when hwpx_mcp_server imports; (None, reason) otherwise.

    The MCP server CLI sandboxes paths via HWPX_MCP_SANDBOX_ROOT; in-process
    sweep calls must not inherit a stray sandbox (mirrors the hwpx-mcp-server
    tests/conftest.py fixture), so the variable is cleared before import.
    """
    os.environ.pop("HWPX_MCP_SANDBOX_ROOT", None)
    try:
        import hwpx_mcp_server.server as server_mod  # noqa: PLC0415 (lazy by design)
    except Exception as exc:  # ImportError or any transitive dep failure
        return None, f"{type(exc).__name__}: {exc}"
    return server_mod, None


def sweep_record_mcp(
    server_mod: Any, path: Path, probes: Mapping[str, str]
) -> dict[str, Any]:
    """Drive the three extract surfaces for one record; deep-scan every payload."""
    payload_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    calls: dict[str, Callable[[], Any]] = {
        "get_document_text": lambda: server_mod.get_document_text(
            str(path), max_chars=MCP_SCAN_MAX_CHARS
        ),
        "hwpx_to_markdown": lambda: server_mod.hwpx_to_markdown(hwpx_base64=payload_b64),
        "hwpx_extract_json": lambda: server_mod.hwpx_extract_json(hwpx_base64=payload_b64),
    }
    leaks: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    scanned_surfaces: list[str] = []
    for surface, call in calls.items():
        try:
            payload = call()
        except Exception as exc:
            errors.append({"surface": surface, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if (
            surface == "get_document_text"
            and isinstance(payload, Mapping)
            and payload.get("truncated")
        ):
            errors.append(
                {
                    "surface": surface,
                    "error": "response truncated — leak scan over this surface is incomplete",
                }
            )
        leaks.extend(scan_mcp_payloads({surface: payload}, probes))
        scanned_surfaces.append(surface)
    status = "scanned" if scanned_surfaces else "error"
    return {
        "status": status,
        "surfaces": scanned_surfaces,
        "leaks": leaks,
        "errors": errors,
    }


# ================================================================================
# sweep driver
# ================================================================================
def sweep(
    manifest_path: Path | str,
    corpus_root: Path | str | None = None,
    *,
    mcp_loader: Callable[[], tuple[Any | None, str | None]] = load_mcp_server,
) -> tuple[dict[str, Any], int]:
    """Run the full sweep. Returns (report dict, exit code)."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(corpus_root) if corpus_root else manifest_path.resolve().parent

    selected = select_pii_records(manifest)
    server_mod, mcp_skip_reason = mcp_loader()

    totals = {
        "records": 0,
        "values_probed": 0,
        "leaks_engine": 0,
        "leaks_mcp": 0,
        "masked_form_missing": 0,
        "files_missing": 0,
        "not_produced": 0,
        "scan_errors": 0,
    }
    record_entries: list[dict[str, Any]] = []
    scanned_count = 0

    for rec in selected:
        probes = record_probes(rec)
        entry: dict[str, Any] = {
            "id": rec.get("id"),
            "stratum": rec.get("stratum") or rec.get("bucket"),
            "probeKinds": sorted(probes),
        }
        if not rec.get("produced"):
            entry["status"] = "not_produced"
            entry["note"] = rec.get("withheld_reason")
            totals["not_produced"] += 1
            record_entries.append(entry)
            continue
        path = resolve_output_path(rec.get("output_path"), root)
        if path is None:
            entry["status"] = "missing_file"
            entry["recordedPath"] = rec.get("output_path")
            totals["files_missing"] += 1
            record_entries.append(entry)
            continue
        entry["path"] = str(path)

        try:
            engine = sweep_record_engine(path, probes)
        except Exception as exc:
            entry["status"] = "error"
            entry["engine"] = {"error": f"{type(exc).__name__}: {exc}"}
            totals["scan_errors"] += 1
            record_entries.append(entry)
            continue
        entry["engine"] = engine
        totals["leaks_engine"] += len(engine["leaks"])
        totals["masked_form_missing"] += len(engine["maskedFormMissing"])

        if server_mod is None:
            entry["mcp"] = {"status": "skipped_env", "reason": mcp_skip_reason}
        else:
            mcp_result = sweep_record_mcp(server_mod, path, probes)
            entry["mcp"] = mcp_result
            totals["leaks_mcp"] += len(mcp_result["leaks"])
            totals["scan_errors"] += len(mcp_result["errors"])

        entry["status"] = "scanned"
        totals["records"] += 1
        totals["values_probed"] += len(probes)
        scanned_count += 1
        record_entries.append(entry)

    leak_total = totals["leaks_engine"] + totals["leaks_mcp"]
    zero_leak = scanned_count > 0 and leak_total == 0

    coverage_notes: list[str] = []
    if server_mod is None:
        coverage_notes.append(
            "MCP leg skipped_env (hwpx_mcp_server not importable from this venv: "
            f"{mcp_skip_reason}) — the three extract surfaces were NOT verified; "
            "rerun from the hwpx-mcp-server venv for full coverage"
        )
    if totals["files_missing"]:
        coverage_notes.append(
            f"{totals['files_missing']} record(s) had unresolvable output files — not scanned"
        )
    if totals["not_produced"]:
        coverage_notes.append(
            f"{totals['not_produced']} PII-bearing record(s) were withheld at generation "
            "(no bytes to scan)"
        )
    if totals["scan_errors"]:
        coverage_notes.append(
            f"{totals['scan_errors']} scan error(s) — affected legs/surfaces are unverified, not passed"
        )
    if totals["masked_form_missing"]:
        coverage_notes.append(
            f"{totals['masked_form_missing']} masked-form-missing flag(s): the raw value is absent "
            "but the expected masked form was not found (masking may not have engaged)"
        )
    if scanned_count == 0:
        coverage_notes.append(
            "VACUOUS: zero PII-bearing records scanned — no 0-leak claim can be made"
        )

    report = {
        "sweep": REPORT_SCHEMA,
        "manifest": str(manifest_path),
        "manifestSchema": manifest.get("schemaVersion"),
        "corpusRoot": str(root),
        "legs": {
            "engine": {
                "status": "scanned" if scanned_count else "no_records",
                "surface": "hwpx.tools.exporter.export_text (unmasked raw read)",
            },
            "mcp": {
                "status": "skipped_env" if server_mod is None else "scanned",
                "reason": mcp_skip_reason,
                "surfaces": list(MCP_SURFACES),
                "maskDefault": True,
            },
        },
        "totals": totals,
        "records": record_entries,
        "zeroLeak": zero_leak,
        "coverageNote": "; ".join(coverage_notes) or "full coverage: engine + MCP 3 surfaces",
    }

    if scanned_count == 0:
        return report, EXIT_VACUOUS
    if leak_total > 0:
        return report, EXIT_LEAK
    return report, EXIT_OK


# ================================================================================
# CLI
# ================================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
        "--report",
        type=Path,
        default=None,
        help="write the verdict JSON here (always also printed to stdout)",
    )
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return EXIT_VACUOUS

    report, exit_code = sweep(args.manifest, args.corpus_root)

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(
        f"[pii-leak-sweep] exit={exit_code} zeroLeak={report['zeroLeak']} "
        f"records={report['totals']['records']} values={report['totals']['values_probed']} "
        f"leaks_engine={report['totals']['leaks_engine']} leaks_mcp={report['totals']['leaks_mcp']} "
        f"masked_form_missing={report['totals']['masked_form_missing']}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
