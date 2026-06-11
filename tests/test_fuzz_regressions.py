# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx.tools.fuzz.runner import run_scenario

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fuzz_regressions"
SCENARIOS = sorted(FIXTURE_DIR.glob("*.scenario.json"))


def _fixture_id(path: Path) -> str:
    return path.name.removesuffix(".scenario.json")


def test_fuzz_regression_fixture_directory_is_not_empty() -> None:
    assert SCENARIOS, "fuzz_regressions must contain at least one replay fixture"


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=_fixture_id)
def test_fuzz_regression_scenarios_replay_cleanly(
    scenario_path: Path,
    tmp_path: Path,
) -> None:
    fixture_id = _fixture_id(scenario_path)
    meta_path = FIXTURE_DIR / f"{fixture_id}.meta.json"
    snapshot_path = FIXTURE_DIR / f"{fixture_id}.hwpx"
    assert meta_path.exists(), f"missing fuzz regression metadata for {fixture_id}"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["schemaVersion"] == "hwpx.fuzz.regression-meta.v1"
    assert meta["classification"] in {"baseline_pass", "F0", "F1", "F2", "F3", "O1"}
    if meta["classification"] != "baseline_pass":
        assert meta.get("resolved") is True, f"unresolved fuzz fixture: {fixture_id}"
    assert snapshot_path.exists(), f"missing fuzz regression HWPX snapshot for {fixture_id}"

    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    result = run_scenario(scenario, tmp_path / f"{fixture_id}.hwpx")

    assert result.ok, result.to_dict()
    assert result.oracle_report["o1"]["ok"] is True
    assert result.oracle_report["o2"]["ok"] is True
