# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the committed P3 PII zero-leak corpus sweep
(specs/010-corpus-publication, scripts/corpus_pii_leak_sweep.py).

Synthetic-only fixtures (no real persons). The MCP scanner functions are
unit-tested against FAKE surface payloads so this suite never requires
hwpx_mcp_server; one integration test exercises the real in-process MCP leg
and is skipped where hwpx_mcp_server is not importable (it runs when the
sweep is executed from the hwpx-mcp-server venv).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

# Load scripts/corpus_pii_leak_sweep.py as a module (scripts/ is not a package).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_pii_leak_sweep", _SCRIPTS / "corpus_pii_leak_sweep.py"
)
assert _spec and _spec.loader
sweep_mod = importlib.util.module_from_spec(_spec)
sys.modules["corpus_pii_leak_sweep"] = sweep_mod
_spec.loader.exec_module(sweep_mod)

try:  # the MCP surface is optional in this venv — integration test skips without it
    import hwpx_mcp_server.server  # noqa: F401

    _HAS_MCP_SERVER = True
except Exception:
    _HAS_MCP_SERVER = False


# ---------------------------------------------------------------------------------
# synthetic probes (machine-checkable set; card is Luhn-valid so masking engages)
# ---------------------------------------------------------------------------------
PROBES = {
    "rrn": "900101-2345678",
    "phone": "010-1234-5678",
    "email": "hong@example.com",
    "card": "4111-1111-1111-1111",
}
MASKED = sweep_mod.expected_masked_forms(PROBES)


def _write_doc(path: Path, lines: list[str]) -> Path:
    doc = HwpxDocument.new()
    for line in lines:
        doc.add_paragraph(line)
    doc.save_to_path(path)
    doc.close()
    return path


def _masked_doc(path: Path) -> Path:
    return _write_doc(
        path,
        [
            "개인정보 확인서 (합성)",
            f"주민등록번호: {MASKED['rrn']}",
            f"연락처: {MASKED['phone']}",
            f"이메일: {MASKED['email']}",
            f"카드번호: {MASKED['card']}",
        ],
    )


def _manifest(path: Path, records: list[dict]) -> Path:
    payload = {"schemaVersion": "hwpx.openrate.frozen-manifest.v2", "records": records}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _record(rec_id: str, doc_path: Path | None, *, produced: bool = True, probes=PROBES) -> dict:
    rec: dict = {
        "id": rec_id,
        "stratum": "pii-merge",
        "produced": produced,
        "output_path": str(doc_path) if doc_path else None,
    }
    if probes is not None:
        rec["pii_probe_values"] = dict(probes)
    return rec


def _forced_skip_loader():
    return None, "forced-skip (unit test)"


# ---------------------------------------------------------------------------------
# engine leg
# ---------------------------------------------------------------------------------
def test_masked_output_passes_with_exit_0(tmp_path: Path) -> None:
    doc = _masked_doc(tmp_path / "masked.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("r1", doc)])

    report, code = sweep_mod.sweep(manifest, tmp_path, mcp_loader=_forced_skip_loader)

    assert code == sweep_mod.EXIT_OK
    assert report["zeroLeak"] is True
    totals = report["totals"]
    assert totals["records"] == 1
    assert totals["values_probed"] == len(PROBES)
    assert totals["leaks_engine"] == 0
    assert totals["masked_form_missing"] == 0
    # the MCP leg must be reported as skipped_env, never silently passed
    assert report["legs"]["mcp"]["status"] == "skipped_env"
    assert "skipped_env" in report["coverageNote"]
    assert report["records"][0]["mcp"]["status"] == "skipped_env"


def test_leaked_output_detected_on_engine_leg_exit_2(tmp_path: Path) -> None:
    leaked = _write_doc(
        tmp_path / "leaked.hwpx",
        [
            f"주민등록번호: {PROBES['rrn']}",  # RAW value deliberately written
            f"연락처: {MASKED['phone']}",
            f"이메일: {MASKED['email']}",
            f"카드번호: {MASKED['card']}",
        ],
    )
    manifest = _manifest(tmp_path / "manifest.json", [_record("leak1", leaked)])

    report, code = sweep_mod.sweep(manifest, tmp_path, mcp_loader=_forced_skip_loader)

    assert code == sweep_mod.EXIT_LEAK
    assert report["zeroLeak"] is False
    assert report["totals"]["leaks_engine"] >= 1
    engine_leaks = report["records"][0]["engine"]["leaks"]
    assert any(leak["type"] == "rrn" for leak in engine_leaks)
    # the report itself must NEVER echo the raw probe value (masked form only)
    blob = json.dumps(report, ensure_ascii=False)
    assert PROBES["rrn"] not in blob
    assert MASKED["rrn"] in blob


def test_masked_form_missing_is_flagged_but_not_a_leak(tmp_path: Path) -> None:
    # value silently DROPPED: neither raw nor masked form present
    dropped = _write_doc(tmp_path / "dropped.hwpx", ["개인정보 없음 문서"])
    manifest = _manifest(tmp_path / "manifest.json", [_record("drop1", dropped)])

    report, code = sweep_mod.sweep(manifest, tmp_path, mcp_loader=_forced_skip_loader)

    assert code == sweep_mod.EXIT_OK  # no raw value present -> not a leak
    assert report["zeroLeak"] is True
    assert report["totals"]["masked_form_missing"] == len(PROBES)
    flagged = report["records"][0]["engine"]["maskedFormMissing"]
    assert sorted(flagged) == sorted(PROBES)
    assert "masked-form-missing" in report["coverageNote"]


# ---------------------------------------------------------------------------------
# vacuous-measurement ban (exit 3)
# ---------------------------------------------------------------------------------
def test_manifest_without_pii_records_is_vacuous_exit_3(tmp_path: Path) -> None:
    doc = _masked_doc(tmp_path / "plain.hwpx")
    manifest = _manifest(
        tmp_path / "manifest.json", [_record("nopii", doc, probes=None)]
    )

    report, code = sweep_mod.sweep(manifest, tmp_path, mcp_loader=_forced_skip_loader)

    assert code == sweep_mod.EXIT_VACUOUS
    assert report["zeroLeak"] is False
    assert report["totals"]["records"] == 0
    assert "VACUOUS" in report["coverageNote"]


def test_all_files_missing_is_vacuous_exit_3(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path / "manifest.json",
        [_record("ghost", tmp_path / "does-not-exist.hwpx")],
    )

    report, code = sweep_mod.sweep(manifest, tmp_path, mcp_loader=_forced_skip_loader)

    assert code == sweep_mod.EXIT_VACUOUS
    assert report["zeroLeak"] is False
    assert report["totals"]["files_missing"] == 1
    assert report["records"][0]["status"] == "missing_file"


# ---------------------------------------------------------------------------------
# MCP scanner functions against FAKE surface payloads (no hwpx_mcp_server needed)
# ---------------------------------------------------------------------------------
def test_scan_mcp_payloads_clean_fake_surfaces_report_no_leak() -> None:
    payloads = {
        "get_document_text": {"text": f"주민 {MASKED['rrn']} 폰 {MASKED['phone']}"},
        "hwpx_to_markdown": {"markdown": f"# 문서\n{MASKED['email']}"},
        "hwpx_extract_json": {
            "doc": {"sections": [{"paragraphs": [f"카드 {MASKED['card']}"]}]}
        },
    }
    assert sweep_mod.scan_mcp_payloads(payloads, PROBES) == []


def test_scan_mcp_payloads_deep_scans_nested_json_for_raw_values() -> None:
    payloads = {
        "get_document_text": {"text": "clean"},
        "hwpx_to_markdown": {"markdown": "clean"},
        "hwpx_extract_json": {
            "doc": {
                "tables": [
                    {"rows": [{"cells": [{"text": f"주민등록번호 {PROBES['rrn']}"}]}]}
                ]
            }
        },
    }
    leaks = sweep_mod.scan_mcp_payloads(payloads, PROBES)
    assert len(leaks) == 1
    leak = leaks[0]
    assert leak["surface"] == "hwpx_extract_json"
    assert leak["type"] == "rrn"
    assert "tables" in leak["where"] and "cells" in leak["where"]
    # scanner output must carry the masked form, never the raw value
    assert leak["maskedValue"] == MASKED["rrn"]
    assert PROBES["rrn"] not in json.dumps(leaks)


def test_scan_mcp_payloads_flags_leak_in_markdown_surface() -> None:
    payloads = {"hwpx_to_markdown": {"markdown": f"연락처 {PROBES['phone']}"}}
    leaks = sweep_mod.scan_mcp_payloads(payloads, PROBES)
    assert [(l["surface"], l["type"]) for l in leaks] == [("hwpx_to_markdown", "phone")]


def test_missing_masked_forms_and_expected_forms_are_consistent() -> None:
    text = f"{MASKED['rrn']} / {MASKED['email']}"
    missing = sweep_mod.missing_masked_forms(text, PROBES)
    assert sorted(missing) == ["card", "phone"]
    # masked forms differ from raw values for the whole machine set
    for kind, masked in MASKED.items():
        assert masked != PROBES[kind]


def test_resolve_output_path_reroots_foreign_absolute_paths(tmp_path: Path) -> None:
    corpus_root = tmp_path / "openrate-corpus-v2"
    target = corpus_root / "pii-merge" / "merged" / "pii-01.hwpx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"stub")

    foreign = "/home/elsewhere/work/openrate-corpus-v2/pii-merge/merged/pii-01.hwpx"
    assert sweep_mod.resolve_output_path(foreign, corpus_root) == target
    # relative form also resolves; unresolvable returns None
    assert (
        sweep_mod.resolve_output_path("pii-merge/merged/pii-01.hwpx", corpus_root)
        == target
    )
    assert sweep_mod.resolve_output_path("nope/missing.hwpx", corpus_root) is None
    assert sweep_mod.resolve_output_path(None, corpus_root) is None


# ---------------------------------------------------------------------------------
# real MCP leg (integration; runs only where hwpx_mcp_server imports)
# ---------------------------------------------------------------------------------
@pytest.mark.skipif(
    not _HAS_MCP_SERVER,
    reason="hwpx_mcp_server not importable in this venv — MCP-leg integration "
    "runs from the hwpx-mcp-server venv",
)
def test_mcp_leg_integration_scans_three_surfaces(tmp_path: Path) -> None:
    doc = _masked_doc(tmp_path / "masked.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("mcp1", doc)])

    report, code = sweep_mod.sweep(manifest, tmp_path)  # default loader: real import

    assert code == sweep_mod.EXIT_OK
    assert report["legs"]["mcp"]["status"] == "scanned"
    rec = report["records"][0]
    assert rec["mcp"]["status"] == "scanned"
    assert sorted(rec["mcp"]["surfaces"]) == sorted(sweep_mod.MCP_SURFACES)
    assert rec["mcp"]["leaks"] == [] and rec["mcp"]["errors"] == []
