#!/usr/bin/env python3
"""Validate an S-068 100-document queue measurement report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_CONTRACT_HASH = "5bb221d90c5cd138fa7561ae09eea41a25154fdd2f9f54cf2011c49d6dfab442"


def validate(report: dict) -> list[str]:
    failures = []
    checks = {
        "schemaVersion": report.get("schemaVersion") == "hwpx.render-measurement.v1",
        "corpusContractHash": report.get("corpusContractHash") == EXPECTED_CONTRACT_HASH,
        "documents": report.get("documents") == 100,
        "lostJobs": report.get("lostJobs") == 0,
        "duplicateTerminalReceipts": report.get("duplicateTerminalReceipts") == 0,
        "terminalAccountingRate": report.get("terminalAccountingRate") == 1.0,
        "exactAccounting": report.get("exactAccounting") is True,
        "latencySeconds": set((report.get("latencySeconds") or {}).keys()) == {"p50", "p95", "p99"},
    }
    for key, ok in checks.items():
        if not ok:
            failures.append(key)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    failures = validate(report)
    print(json.dumps({"ok": not failures, "failures": failures}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
