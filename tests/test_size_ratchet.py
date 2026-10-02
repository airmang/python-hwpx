# SPDX-License-Identifier: Apache-2.0
"""Core size history is well-formed, and ``import hwpx`` stays under its bound.

Line counts are recorded per release in ``docs/size-history.json`` during
release prep (``python scripts/size_ratchet.py --record <version>``); they are
not a pull-request gate, because parallel branches would conflict on any exact
lock. The number of hwpx modules ``import hwpx`` loads is an upper-bound
ratchet in ``tests/data/import_breadth.json``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import warnings
from pathlib import Path

import size_ratchet  # scripts/ is on the pytest pythonpath

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "docs" / "size-history.json"
BREADTH = ROOT / "tests" / "data" / "import_breadth.json"


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_size_history_is_well_formed() -> None:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))

    found = size_ratchet.history_problems(history, _project_version())

    assert found == [], "\n".join(found)


def test_history_checks_can_fail() -> None:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    newest = history["releases"][-1]
    ahead = json.loads(json.dumps(history))
    ahead["releases"].append({**newest, "version": "99.0.0"})
    shuffled = json.loads(json.dumps(history))
    shuffled["releases"].reverse()
    broken = json.loads(json.dumps(history))
    broken["releases"][0]["totalLines"] += 1
    del broken["releases"][1]["importMs"]

    assert size_ratchet.history_problems(ahead, _project_version()) == [
        f"newest recorded release 99.0.0 is newer than pyproject version {_project_version()}"
    ]
    assert size_ratchet.history_problems(shuffled, _project_version()) == [
        "releases are not in strictly increasing version order"
    ]
    assert len(size_ratchet.history_problems(broken, _project_version())) == 2


def test_import_breadth_stays_under_the_bound() -> None:
    bound = json.loads(BREADTH.read_text(encoding="utf-8"))
    assert bound["schemaVersion"] == size_ratchet.BREADTH_SCHEMA
    live, _elapsed = size_ratchet.import_probe()

    ok, message = size_ratchet.breadth_message(live, bound["maxImportedModules"])

    assert ok, message
    if live < bound["maxImportedModules"]:
        warnings.warn(message, UserWarning, stacklevel=1)


def test_breadth_ratchet_fails_only_upward() -> None:
    above, above_message = size_ratchet.breadth_message(118, 117)
    below, below_message = size_ratchet.breadth_message(100, 117)
    equal, _ = size_ratchet.breadth_message(117, 117)

    assert not above and "above the bound of 117" in above_message
    assert below and "--lower-bound" in below_message
    assert equal


def test_import_probe_is_deterministic() -> None:
    first, _ = size_ratchet.import_probe()
    second, _ = size_ratchet.import_probe()

    assert first == second > 1


def test_cli_prints_the_delta_against_the_last_release() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "size_ratchet.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    newest = json.loads(HISTORY.read_text(encoding="utf-8"))["releases"][-1]["version"]
    assert f"working tree vs {newest}" in result.stdout
    assert "not gated" in result.stdout
