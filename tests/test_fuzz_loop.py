# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json

from hwpx.tools.fuzz import (
    FuzzRunResult,
    SCENARIO_SCHEMA_VERSION,
    canonical_json_bytes,
    generate_scenario,
    operation_catalog,
    run_scenario,
    run_seed_range,
    scenario_digest,
)
from hwpx.tools.fuzz.minimize import minimize_scenario
from hwpx.tools.fuzz.runner import fossilize_failure


def test_seeded_scenario_generation_is_deterministic() -> None:
    first = generate_scenario(42)
    second = generate_scenario(42)
    other = generate_scenario(43)

    assert first == second
    assert first != other
    assert first["schemaVersion"] == SCENARIO_SCHEMA_VERSION
    assert first["scenarioDigest"] == scenario_digest(first)
    assert {spec.name for spec in operation_catalog()} >= {
        "build_document",
        "add_paragraph",
        "add_table",
        "set_table_cell_text",
        "merge_table_cells",
        "replace_text",
    }


def test_same_seed_replay_writes_identical_open_safe_hwpx(tmp_path) -> None:
    scenario = generate_scenario(7)
    first_path = tmp_path / "first.hwpx"
    second_path = tmp_path / "second.hwpx"

    first = run_scenario(scenario, first_path)
    second = run_scenario(generate_scenario(7), second_path)

    assert first.ok, first.to_dict()
    assert second.ok, second.to_dict()
    assert first_path.read_bytes() == second_path.read_bytes()
    assert hashlib.sha256(first_path.read_bytes()).hexdigest() == hashlib.sha256(
        second_path.read_bytes()
    ).hexdigest()
    assert first.oracle_report["o1"]["openSafety"]["ok"] is True
    assert first.oracle_report["o2"]["roundtrip"]["ok"] is True


def test_seed_range_runner_reports_every_failure_explicitly(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    sample_dir = tmp_path / "samples"

    report = run_seed_range(
        start=0,
        count=12,
        output_dir=tmp_path / "out",
        report_path=report_path,
        sample_dir=sample_dir,
        sample_count=4,
    )

    assert report["schemaVersion"] == "hwpx.fuzz.report.v1"
    assert report["seedStart"] == 0
    assert report["seedCount"] == 12
    assert report["okCount"] + report["failureCount"] == 12
    assert report["failureCount"] == 0, report["failures"]
    assert len(report["visualReviewSamples"]) == 4
    assert all((sample_dir / path.name).exists() for path in sample_dir.glob("*.hwpx"))

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["failureCount"] == report["failureCount"]


def test_minimizer_and_fossilizer_write_regression_triplet(tmp_path) -> None:
    scenario = generate_scenario(2)
    scenario["operations"].append({"op": "add_paragraph", "text": "trigger_failure"})

    minimized = minimize_scenario(
        scenario,
        lambda candidate: any(
            op.get("text") == "trigger_failure"
            for op in candidate.get("operations") or ()
        ),
    )

    assert any(op.get("text") == "trigger_failure" for op in minimized["operations"])
    assert len(minimized["operations"]) < len(scenario["operations"])

    snapshot = tmp_path / "failed.hwpx"
    snapshot.write_bytes(b"snapshot")
    result = FuzzRunResult(
        seed=2,
        scenario_digest=scenario_digest(minimized),
        output_path=snapshot,
        ok=False,
        classification="F3",
        oracle_report={"o1": {"ok": True}, "o2": {"ok": False}},
        scenario=minimized,
    )

    paths = fossilize_failure(result, tmp_path / "regressions", resolved=True)

    assert paths["scenario"].exists()
    assert paths["snapshot"].exists()
    assert paths["meta"].exists()
    meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    assert meta["classification"] == "F3"
    assert meta["resolved"] is True
    assert paths["scenario"].read_bytes() == canonical_json_bytes(minimized) + b"\n"
