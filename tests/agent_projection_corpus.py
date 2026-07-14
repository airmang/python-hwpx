#!/usr/bin/env python3
"""Deterministic corpus receipt generator for the agent read surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import statistics
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any

from hwpx.agent.document import HwpxAgentDocument


def _projection_payload(agent: HwpxAgentDocument) -> list[dict[str, Any]]:
    return [
        {
            "kind": record.kind,
            "path": record.path,
            "stableId": record.stable_id,
            "stability": record.stability,
            "summary": record.summary,
            "parentPath": record.parent_path,
            "childCount": len(record.child_paths) + record.unsupported_child_count,
            "unsupportedChildCount": record.unsupported_child_count,
        }
        for record in agent.records
    ]


def _payload_hash(agent: HwpxAgentDocument) -> str:
    encoded = json.dumps(
        _projection_payload(agent), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def run_corpus(fixtures: list[Path], *, trace_memory: bool = False) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    elapsed_values: list[float] = []
    traced_peaks: list[int] = []
    aggregate_kinds: Counter[str] = Counter()
    aggregate_unsupported: Counter[str] = Counter()
    aggregate_unsupported_kinds: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    for fixture in fixtures:
        try:
            if trace_memory:
                tracemalloc.start()
            started = time.perf_counter()
            with HwpxAgentDocument.open(fixture) as first:
                first_hash = _payload_hash(first)
                kind_counts = Counter(record.kind for record in first.records)
                unsupported_counts: Counter[str] = Counter()
                unsupported_kinds: Counter[str] = Counter()
                for record in first.records:
                    unsupported_counts[record.kind] += record.unsupported_child_count
                    unsupported_kinds.update(record.unsupported_child_kinds)
                queries = {
                    selector: first.query(selector, limit=100).to_dict()["count"]
                    for selector in (
                        "paragraph",
                        "table",
                        "form-field",
                        'paragraph:contains("평가")',
                    )
                }
                revision = first.revision
                node_count = len(first.records)
            elapsed = time.perf_counter() - started
            traced_peak: int | None = None
            if trace_memory:
                _current, traced_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            with HwpxAgentDocument.open(fixture) as second:
                second_hash = _payload_hash(second)
            if first_hash != second_hash:
                raise AssertionError("projection hash changed across reopen")
            entry = {
                "fixture": str(fixture),
                "revision": revision,
                "projectionHash": first_hash,
                "deterministicReopen": True,
                "nodeCount": node_count,
                "kindCounts": dict(sorted(kind_counts.items())),
                "unsupportedChildCounts": {
                    key: value for key, value in sorted(unsupported_counts.items()) if value
                },
                "unsupportedKinds": dict(sorted(unsupported_kinds.items())),
                "queries": queries,
                "elapsedSeconds": round(elapsed, 6),
                "tracedPeakBytes": traced_peak,
            }
            entries.append(entry)
            elapsed_values.append(elapsed)
            if traced_peak is not None:
                traced_peaks.append(traced_peak)
            aggregate_kinds.update(kind_counts)
            aggregate_unsupported.update(unsupported_counts)
            aggregate_unsupported_kinds.update(unsupported_kinds)
        except Exception as exc:  # corpus receipt must retain rejected inputs
            if trace_memory and tracemalloc.is_tracing():
                tracemalloc.stop()
            errors.append(
                {
                    "fixture": str(fixture),
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }
            )

    return {
        "schemaVersion": "hwpx.agent-projection-corpus/v1",
        "fixtureCount": len(fixtures),
        "projectedCount": len(entries),
        "rejectedCount": len(errors),
        "allProjectedDeterministic": all(entry["deterministicReopen"] for entry in entries),
        "coverage": {
            "nodeKinds": dict(sorted(aggregate_kinds.items())),
            "unsupportedChildrenByParentKind": {
                key: value for key, value in sorted(aggregate_unsupported.items()) if value
            },
            "unsupportedKinds": dict(sorted(aggregate_unsupported_kinds.items())),
        },
        "performance": {
            "elapsedP50Seconds": round(statistics.median(elapsed_values), 6) if elapsed_values else None,
            "elapsedP95Seconds": (
                round(_percentile(elapsed_values, 0.95) or 0.0, 6) if elapsed_values else None
            ),
            "maxTracedPeakBytes": max(traced_peaks) if traced_peaks else None,
            "processMaxRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "memoryNote": (
                "tracemalloc is per projection; max RSS uses macOS bytes"
                if trace_memory
                else "max RSS uses macOS bytes; tracemalloc disabled to avoid instrumentation distortion"
            ),
        },
        "entries": entries,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--tracemalloc", action="store_true")
    args = parser.parse_args()

    if args.manifest is not None:
        fixtures = [
            args.fixtures_root / line.strip()
            for line in args.manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ][: args.limit]
    else:
        fixtures = sorted(args.fixtures_root.rglob("*.hwpx"))[: args.limit]
    result = run_corpus(fixtures, trace_memory=args.tracemalloc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        key: result[key]
        for key in ("fixtureCount", "projectedCount", "rejectedCount", "performance")
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if result["projectedCount"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
