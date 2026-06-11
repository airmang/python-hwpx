# SPDX-License-Identifier: Apache-2.0
"""CLI for seeded HWPX fuzz convergence runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import canonical_json_bytes, operation_catalog
from .runner import load_scenario, run_scenario, run_seed_range


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run seeded HWPX fuzz scenarios")
    subparsers = parser.add_subparsers(dest="command")

    catalog_parser = subparsers.add_parser("catalog", help="print the operation catalog")
    catalog_parser.set_defaults(command="catalog")

    replay_parser = subparsers.add_parser("replay", help="replay one scenario JSON")
    replay_parser.add_argument("scenario", help="scenario JSON path")
    replay_parser.add_argument("--output", required=True, help="output .hwpx path")
    replay_parser.add_argument("--result", help="write result JSON")

    run_parser = subparsers.add_parser("run", help="run a seed range")
    run_parser.add_argument("--start", type=int, default=0, help="first seed")
    run_parser.add_argument("--count", type=int, default=1000, help="number of seeds")
    run_parser.add_argument("--out-dir", required=True, help="directory for generated scenarios and HWPX files")
    run_parser.add_argument("--report", required=True, help="report JSON path")
    run_parser.add_argument("--max-operations", type=int, default=16)
    run_parser.add_argument("--regression-dir", help="directory for fossilized failure fixtures")
    run_parser.add_argument("--write-regressions", action="store_true", help="write minimized failure fixtures")
    run_parser.add_argument("--sample-count", type=int, default=20)
    run_parser.add_argument("--sample-dir", help="copy selected visual review samples here")

    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["run", *argv]
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "catalog":
        print(json.dumps([spec.to_dict() for spec in operation_catalog()], indent=2, sort_keys=True))
        return 0

    if args.command == "replay":
        result = run_scenario(load_scenario(args.scenario), args.output)
        payload = result.to_dict()
        if args.result:
            Path(args.result).write_bytes(canonical_json_bytes(payload) + b"\n")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if result.ok else 1

    report = run_seed_range(
        start=args.start,
        count=args.count,
        output_dir=args.out_dir,
        report_path=args.report,
        regression_dir=args.regression_dir,
        max_operations=args.max_operations,
        write_regressions=args.write_regressions,
        sample_count=args.sample_count,
        sample_dir=args.sample_dir,
    )
    print(
        "[OK] seeds "
        f"{args.start}-{args.start + args.count - 1}: "
        f"ok={report['okCount']} failures={report['failureCount']} "
        f"report={args.report}"
    )
    return 0 if report["failureCount"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
