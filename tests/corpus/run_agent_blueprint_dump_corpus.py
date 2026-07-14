#!/usr/bin/env python3
"""Measure deterministic inspection dumps over the frozen local HWPX corpus."""

from __future__ import annotations

import argparse
import json
import logging
import resource
import signal
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

from hwpx.agent.blueprint import dump_document_blueprint
from hwpx.agent.model import AgentContractError

logging.disable(logging.CRITICAL)


def _timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("corpus case exceeded 3 seconds")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile)))
    return round(ordered[index], 3)


def _select(root: Path) -> list[tuple[str, Path]]:
    candidates = sorted((root / "tests" / "fixtures").rglob("*.hwpx"))
    regular = candidates[:20]
    stress = sorted((path for path in candidates if path not in regular), key=lambda path: (-path.stat().st_size, str(path)))[:5]
    return [("regular", path) for path in regular] + [("stress", path) for path in stress]


def run(root: Path) -> dict[str, Any]:
    signal.signal(signal.SIGALRM, _timeout)
    rows: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    dependency_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    durations: list[float] = []
    peaks: list[int] = []

    for corpus, path in _select(root):
        relative = str(path.relative_to(root))
        started = time.perf_counter()
        signal.alarm(3)
        try:
            first = dump_document_blueprint(path, path="/", require_replayable=False)
            second = dump_document_blueprint(path, path="/", require_replayable=False)
            elapsed_ms = (time.perf_counter() - started) * 1000
            peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            row = {
                "corpus": corpus,
                "path": relative,
                "status": "dumped",
                "deterministic": first.bundle_bytes == second.bundle_bytes,
                "blueprintHash": first.manifest["blueprintHash"],
                "bundleSha256": first.bundle_sha256,
                "nodeCount": len(first.manifest["nodes"]),
                "assetCount": len(first.assets),
                "styleCount": len(first.manifest["styles"]),
                "numberingCount": len(first.manifest["numbering"]),
                "unsupportedCount": len(first.manifest["unsupported"]),
                "replayable": first.manifest["fidelity"]["replayable"],
                "durationMs": round(elapsed_ms, 3),
                "peakBytes": peak,
            }
            kind_counts.update(node["kind"] for node in first.manifest["nodes"])
            dependency_counts.update(
                {
                    "style": len(first.manifest["styles"]),
                    "numbering": len(first.manifest["numbering"]),
                    "resource": len(first.manifest["resources"]),
                }
            )
            durations.append(elapsed_ms)
            peaks.append(peak)
        except (AgentContractError, OSError, TimeoutError, ValueError) as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            code = exc.code if isinstance(exc, AgentContractError) else type(exc).__name__
            rejection_counts[code] += 1
            durations.append(elapsed_ms)
            peaks.append(peak)
            row = {
                "corpus": corpus,
                "path": relative,
                "status": "rejected",
                "reason": code,
                "durationMs": round(elapsed_ms, 3),
                "peakBytes": peak,
            }
        finally:
            signal.alarm(0)
        rows.append(row)

    dumped = [row for row in rows if row["status"] == "dumped"]
    return {
        "schemaVersion": "hwpx.agent-blueprint-dump-corpus/v1",
        "selection": {"regular": 20, "stress": 5, "rule": "path-sorted first 20 plus largest remaining 5"},
        "summary": {
            "attempted": len(rows),
            "dumped": len(dumped),
            "rejected": len(rows) - len(dumped),
            "deterministic": sum(bool(row.get("deterministic")) for row in dumped),
            "replayable": sum(bool(row.get("replayable")) for row in dumped),
            "p50DurationMs": round(statistics.median(durations), 3) if durations else 0.0,
            "p95DurationMs": _percentile(durations, 0.95),
            "peakBytes": max(peaks, default=0),
            "peakMetric": "ru_maxrss bytes on macOS",
        },
        "coverage": {
            "nodeKinds": dict(sorted(kind_counts.items())),
            "dependencies": dict(sorted(dependency_counts.items())),
            "rejections": dict(sorted(rejection_counts.items())),
        },
        "contractAmendments": [],
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
