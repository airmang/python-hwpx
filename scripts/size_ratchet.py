#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Make core growth visible: Python line counts and ``import hwpx`` breadth.

Core went from about 36k lines (5.0.1) to 72k (6.6.0) in two months and
nothing in review showed it. Two records keep it in view without making
every pull request fight over one file:

- ``docs/size-history.json``: one entry per release (``--record``) with
  the physical lines of every ``.py`` file under ``src/hwpx``, the same per
  top-level subpackage (``"."`` collects top-level modules such as
  ``document.py``), how many ``hwpx`` / ``hwpx.*`` modules a bare
  ``import hwpx`` loads, and that import's time. Lines are a release-notes
  fact, not a pull-request gate.
- ``tests/data/import_breadth.json``: an upper bound on that module count.
  ``tests/test_size_ratchet.py`` fails when ``import hwpx`` loads more
  modules than the bound, and only hints when it loads fewer.

The module count is measured in a fresh ``python -I`` interpreter with only
the measured tree's ``src`` on the path, so neither the environment nor an
installed copy of hwpx decides what gets imported.

    python scripts/size_ratchet.py                       # working tree vs last release
    python scripts/size_ratchet.py --record 6.8.0        # append the working tree
    python scripts/size_ratchet.py --record 6.0.0 --ref v6.0.0   # measure a git ref
    python scripts/size_ratchet.py --lower-bound         # tighten the module bound
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
HISTORY = ROOT / "docs" / "size-history.json"
BREADTH = ROOT / "tests" / "data" / "import_breadth.json"
HISTORY_SCHEMA = "python-hwpx.size-history/v1"
BREADTH_SCHEMA = "python-hwpx.import-breadth/v1"
ENTRY_KEYS = frozenset(
    {"version", "commit", "totalLines", "packages", "importedModules", "importMs"}
)

_IMPORT_PROBE = """
import sys, time
sys.path.insert(0, {src!r})
start = time.perf_counter()
import hwpx
elapsed = time.perf_counter() - start
loaded = sorted(name for name in sys.modules if name == "hwpx" or name.startswith("hwpx."))
assert all(
    getattr(sys.modules[name], "__file__", None) is None
    or sys.modules[name].__file__.startswith({src!r})
    for name in loaded
), "hwpx was imported from outside the measured tree"
print(len(loaded))
print(elapsed)
"""


def line_counts(package: pathlib.Path) -> tuple[int, dict[str, int]]:
    packages: Counter[str] = Counter()
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package)
        if "__pycache__" in relative.parts:
            continue
        with path.open("rb") as handle:
            lines = sum(1 for _ in handle)
        packages[relative.parts[0] if len(relative.parts) > 1 else "."] += lines
    return sum(packages.values()), dict(sorted(packages.items()))


def import_probe(src: pathlib.Path = SRC, runs: int = 1) -> tuple[int, float]:
    """(hwpx modules loaded, median import seconds over *runs* fresh interpreters)."""

    counts: set[int] = set()
    times: list[float] = []
    for _ in range(runs):
        result = subprocess.run(
            [sys.executable, "-I", "-c", _IMPORT_PROBE.format(src=str(src))],
            capture_output=True,
            text=True,
            check=True,
        )
        count, elapsed = result.stdout.split()
        counts.add(int(count))
        times.append(float(elapsed))
    if len(counts) != 1:  # pragma: no cover - would mean the probe is not deterministic
        raise RuntimeError(f"import hwpx loaded a different module count per run: {counts}")
    return counts.pop(), statistics.median(times)


def measure(src: pathlib.Path = SRC, runs: int = 3) -> dict[str, Any]:
    total, packages = line_counts(src / "hwpx")
    modules, elapsed = import_probe(src, runs)
    return {
        "totalLines": total,
        "packages": packages,
        "importedModules": modules,
        "importMs": round(elapsed * 1000),
    }


def measure_ref(ref: str, runs: int = 3) -> tuple[dict[str, Any], str]:
    """Measure *ref* from ``git archive`` into a temp dir — no worktree, no checkout."""

    commit = subprocess.run(
        ["git", "rev-parse", "--short", f"{ref}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory() as scratch:
        archive = pathlib.Path(scratch) / "src.tar"
        subprocess.run(
            ["git", "archive", "--format=tar", "-o", str(archive), commit, "src/hwpx"],
            cwd=ROOT, check=True,
        )
        with tarfile.open(archive) as tar:
            try:
                tar.extractall(scratch, filter="data")
            except TypeError:  # Python without extraction filters; our own archive
                tar.extractall(scratch)
        return measure(pathlib.Path(scratch) / "src", runs), commit


def head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def load_history(path: pathlib.Path = HISTORY) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": HISTORY_SCHEMA, "releases": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def history_problems(history: dict[str, Any], project_version: str) -> list[str]:
    """Shape of ``docs/size-history.json``; empty means well-formed."""

    found: list[str] = []
    if history.get("schemaVersion") != HISTORY_SCHEMA:
        found.append(f"schemaVersion is not {HISTORY_SCHEMA!r}")
    releases = history.get("releases") or []
    if not releases:
        found.append("no releases recorded")
    versions: list[tuple[int, ...]] = []
    for index, entry in enumerate(releases):
        if set(entry) != ENTRY_KEYS:
            found.append(f"releases[{index}] keys {sorted(entry)} != {sorted(ENTRY_KEYS)}")
            continue
        try:
            versions.append(version_key(entry["version"]))
        except ValueError:
            found.append(f"releases[{index}] version {entry['version']!r} is not N.N.N")
            continue
        if sum(entry["packages"].values()) != entry["totalLines"]:
            found.append(f"releases[{index}] packages do not add up to totalLines")
    if versions != sorted(versions) or len(set(versions)) != len(versions):
        found.append("releases are not in strictly increasing version order")
    if versions and versions[-1] > version_key(project_version):
        found.append(
            f"newest recorded release {releases[-1]['version']} is newer than "
            f"pyproject version {project_version}"
        )
    return found


def breadth_message(live: int, bound: int) -> tuple[bool, str]:
    """(ok, message) for the upper-bound module ratchet."""

    if live > bound:
        return False, (
            f"import hwpx now loads {live} hwpx modules, above the bound of {bound} in "
            "tests/data/import_breadth.json. Keep new modules out of the import path "
            "(import them lazily where they are used), or, if the growth is intended, "
            "raise the bound in the same change and say why in the pull request."
        )
    if live < bound:
        return True, (
            f"import hwpx loads {live} hwpx modules, below the bound of {bound}; "
            "run `python scripts/size_ratchet.py --lower-bound` to tighten it."
        )
    return True, f"import hwpx loads {live} hwpx modules (bound {bound})"


def _delta(after: int, before: int | None) -> str:
    if before is None:
        return "new"
    change = after - before
    percent = f" ({change / before:+.1%})" if before else ""
    return f"{change:+d}{percent}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", metavar="VERSION", help="append a release entry")
    parser.add_argument("--ref", help="with --record: measure this git ref instead of the working tree")
    parser.add_argument("--lower-bound", action="store_true", help="set the module bound to the live count")
    args = parser.parse_args(argv)

    if args.ref and not args.record:
        parser.error("--ref needs --record")

    if args.record:
        if args.ref:
            live, commit = measure_ref(args.ref)
        else:
            live, commit = measure(), head_commit()
        history = load_history()
        releases = [r for r in history["releases"] if r["version"] != args.record]
        releases.append({"version": args.record, "commit": commit, **live})
        releases.sort(key=lambda r: version_key(r["version"]))
        history["releases"] = releases
        write_json(HISTORY, history)
        print(
            f"recorded {args.record} ({commit}): {live['totalLines']} lines, "
            f"{live['importedModules']} modules, {live['importMs']} ms"
        )
        return 0

    live = measure()
    bound = json.loads(BREADTH.read_text(encoding="utf-8"))
    if args.lower_bound:
        bound["maxImportedModules"] = live["importedModules"]
        write_json(BREADTH, bound)
        print(f"module bound set to {live['importedModules']}")
        return 0

    releases = load_history()["releases"]
    if releases:
        last = releases[-1]
        print(f"working tree vs {last['version']} ({last['commit']}):")
        print(f"  total      {live['totalLines']:>7}  {_delta(live['totalLines'], last['totalLines'])}")
        for name, lines in live["packages"].items():
            print(f"  {name:<10} {lines:>7}  {_delta(lines, last['packages'].get(name))}")
        for name in sorted(set(last["packages"]) - set(live["packages"])):
            print(f"  {name:<10} {0:>7}  removed ({-last['packages'][name]:+d})")
        print(
            f"  modules    {live['importedModules']:>7}  "
            f"{_delta(live['importedModules'], last['importedModules'])}"
        )
    print(f"import hwpx: {live['importMs']} ms (median of 3, not gated)")
    ok, message = breadth_message(live["importedModules"], bound["maxImportedModules"])
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
