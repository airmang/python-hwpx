#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Enforce the python-hwpx ownership ledger and no-new-drift ratchet."""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

FORBIDDEN_IMPORTS = ("hwpx_mcp_server", "hwpx_skill")
DEBT_DISPOSITIONS = ("mcp-migrate", "split")


def _python_files(root: Path, source_root: str) -> list[Path]:
    return sorted((root / source_root).rglob("*.py"))


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _baseline_files(root: Path, commit: str, source_root: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", source_root],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        line
        for line in result.stdout.splitlines()
        if line.endswith(".py")
    }


def _classification(
    path: str,
    ledger: dict[str, Any],
) -> tuple[str | None, str | None]:
    for exception in ledger.get("exceptions", []):
        if exception["path"] == path:
            return exception["disposition"], "exception"
    for rule in ledger["rules"]:
        if fnmatch.fnmatchcase(path, rule["glob"]):
            return rule["disposition"], rule["glob"]
    return None, None


def _reverse_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [f"could not inspect imports: {exc}"]
    found: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORTS):
                found.append(name)
    return found


def evaluate(
    root: Path,
    ledger: dict[str, Any],
    *,
    baseline_files: set[str] | None = None,
) -> dict[str, Any]:
    source_root = ledger["baseline"]["sourceRoot"]
    baseline_files = baseline_files if baseline_files is not None else _baseline_files(
        root,
        ledger["baseline"]["commit"],
        source_root,
    )
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0})
    violations: list[str] = []
    classified: dict[str, str] = {}

    for file_path in _python_files(root, source_root):
        relative = _relative(root, file_path)
        disposition, matched_by = _classification(relative, ledger)
        if disposition is None:
            violations.append(f"unclassified core module: {relative}")
            continue
        classified[relative] = disposition
        totals[disposition]["files"] += 1
        totals[disposition]["loc"] += len(file_path.read_text(encoding="utf-8").splitlines())

        if relative not in baseline_files and matched_by != "exception":
            violations.append(
                f"new module lacks explicit ownership exception: {relative} "
                f"(fell through {matched_by})"
            )
        for imported in _reverse_imports(file_path):
            violations.append(f"core reverse dependency: {relative} imports {imported}")

    baseline_counts = ledger["baseline"]["dispositionCounts"]
    for disposition in DEBT_DISPOSITIONS:
        current = totals[disposition]
        baseline = baseline_counts[disposition]
        if current["files"] > baseline["files"]:
            violations.append(
                f"{disposition} file debt grew: {current['files']} > {baseline['files']}"
            )
        if current["loc"] > baseline["loc"]:
            violations.append(
                f"{disposition} LOC debt grew: {current['loc']} > {baseline['loc']}"
            )

    return {
        "ok": not violations,
        "baselineCommit": ledger["baseline"]["commit"],
        "classifiedFiles": len(classified),
        "totals": dict(sorted(totals.items())),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/architecture/module-ownership.json"),
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    ledger_path = args.ledger if args.ledger.is_absolute() else root / args.ledger
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    report = evaluate(root, ledger)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
