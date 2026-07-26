# SPDX-License-Identifier: Apache-2.0
"""Release ordering must protect the already-published 5.x application."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_legacy_release_cap.py"
LEGACY_STEP = "Require public 5.1.1 legacy cap before core 5"
LEGACY_COMMAND = (
    'python scripts/verify_legacy_release_cap.py '
    '--venv "${RUNNER_TEMP}/hwpx-phase0-legacy"'
)


def _verifier_module():
    spec = importlib.util.spec_from_file_location(
        "verify_legacy_release_cap",
        VERIFY_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_safety_failures(workflow: str) -> list[str]:
    failures: list[str] = []
    try:
        parsed = yaml.safe_load(workflow)
        jobs: dict[str, dict[str, Any]] = parsed["jobs"]
        legacy = jobs["legacy-cap"]
        prepublish = jobs["prepublish"]
        release = jobs["release"]
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        return [f"invalid release job structure: {exc}"]

    if prepublish.get("needs") != "legacy-cap":
        failures.append("prepublish must need legacy-cap")
    if release.get("needs") != "prepublish":
        failures.append("release must need prepublish")
    for job_name, job in (
        ("legacy-cap", legacy),
        ("prepublish", prepublish),
        ("release", release),
    ):
        if "if" in job:
            failures.append(f"{job_name} must not override dependency status")
        if job.get("continue-on-error", False):
            failures.append(f"{job_name} must not continue on error")
        for step in job.get("steps", []):
            if step.get("continue-on-error", False):
                failures.append(
                    f"{job_name} step must not continue on error: "
                    f"{step.get('name', step.get('uses', '<unnamed>'))}"
                )

    matching_steps = [
        step
        for step in legacy.get("steps", [])
        if step.get("name") == LEGACY_STEP
    ]
    if len(matching_steps) != 1:
        failures.append("legacy-cap must have exactly one named verifier step")
    elif matching_steps[0].get("run") != LEGACY_COMMAND:
        failures.append("legacy-cap verifier command must be exact")
    return failures


def test_public_legacy_cap_is_a_required_fail_closed_job() -> None:
    workflow = RELEASE.read_text(encoding="utf-8")
    assert _workflow_safety_failures(workflow) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda text: text.replace("needs: legacy-cap", "needs: []", 1),
            "prepublish must need legacy-cap",
        ),
        (
            lambda text: text.replace("needs: prepublish", "needs: []", 1),
            "release must need prepublish",
        ),
        (
            lambda text: text.replace(
                "  release:\n    needs:",
                "  release:\n    if: always()\n    needs:",
                1,
            ),
            "release must not override dependency status",
        ),
        (
            lambda text: text.replace(
                "      - name: Require public 5.1.1 legacy cap before core 5",
                "      - name: Require public 5.1.1 legacy cap before core 5\n"
                "        continue-on-error: true",
                1,
            ),
            "legacy-cap step must not continue on error",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: {LEGACY_COMMAND} || true",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: exit    0; {LEGACY_COMMAND}",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: if false; then {LEGACY_COMMAND}; fi",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
    ),
    ids=(
        "remove-legacy-needs",
        "remove-prepublish-needs",
        "release-always",
        "continue-on-error",
        "ignore-verifier-failure",
        "early-success-exit",
        "unreachable-verifier",
    ),
)
def test_release_workflow_mutations_are_rejected(
    mutate,
    expected: str,
) -> None:
    workflow = RELEASE.read_text(encoding="utf-8")

    failures = _workflow_safety_failures(mutate(workflow))

    assert any(expected in failure for failure in failures)


def _safe_requirements() -> list[str]:
    return [
        "python-hwpx>=4.2.0,<5",
        'python-hwpx[visual]<5,>=4.2.0; extra == "oracle"',
        'python-hwpx[visual]>=4.2.0,<5; extra == "vision"',
    ]


def test_exact_legacy_metadata_contract_accepts_only_safe_public_pair() -> None:
    verifier = _verifier_module()

    assert (
        verifier.validate_legacy_cap(
            core_version="4.2.0",
            legacy_version="5.1.1",
            requirements=_safe_requirements(),
        )
        == []
    )


@pytest.mark.parametrize(
    ("core_version", "legacy_version", "requirements", "expected"),
    (
        ("5.0.0", "5.1.1", _safe_requirements(), "python-hwpx version"),
        ("4.2.0", "5.1.0", _safe_requirements(), "hwpx-mcp-server version"),
        (
            "4.2.0",
            "5.1.1",
            [
                "python-hwpx>=4.2.0,<50",
                'python-hwpx[visual]>=4.2.0,<50; extra == "oracle"',
                'python-hwpx[visual]>=4.2.0,<50; extra == "vision"',
            ],
            "unsafe python-hwpx specifiers",
        ),
        (
            "4.2.0",
            "5.1.1",
            _safe_requirements()[:2],
            "expected 3 python-hwpx requirements",
        ),
    ),
    ids=("core5", "legacy510", "upper50", "missing-extra"),
)
def test_legacy_metadata_mutations_fail_closed(
    core_version: str,
    legacy_version: str,
    requirements: list[str],
    expected: str,
) -> None:
    verifier = _verifier_module()

    failures = verifier.validate_legacy_cap(
        core_version=core_version,
        legacy_version=legacy_version,
        requirements=requirements,
    )

    assert any(expected in failure for failure in failures)


def test_legacy_runner_executes_every_command_with_check_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _verifier_module()
    calls: list[tuple[tuple[str, ...], bool]] = []

    def record(command, *, check: bool):
        calls.append((tuple(command), check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", record)
    verifier.install_and_verify(tmp_path / "legacy-venv")

    assert len(calls) == 7
    assert all(check is True for _, check in calls)
    assert calls[0][0][-2:] == (
        str(tmp_path / "legacy-venv-wheelhouse"),
        str(ROOT),
    )
    assert calls[1][0][-2:] == (
        "python-hwpx==4.2.0",
        "hwpx-mcp-server==5.1.1",
    )
    install = calls[3][0]
    assert "--no-index" in install
    assert "--find-links" in install
    assert "python-hwpx==4.2.0" not in install
    assert install[-1] == "hwpx-mcp-server==5.1.1"
    assert calls[4][0][-3:] == ("-m", "pip", "check")
    assert calls[5][0][-1] == "--inspect-installed"
    assert calls[6][0][-1] == "--help"


@pytest.mark.parametrize("failed_command", range(7))
def test_legacy_runner_propagates_every_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failed_command: int,
) -> None:
    verifier = _verifier_module()
    call_index = 0

    def fail_one(command, *, check: bool):
        nonlocal call_index
        current = call_index
        call_index += 1
        if current == failed_command:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", fail_one)

    with pytest.raises(subprocess.CalledProcessError):
        verifier.install_and_verify(tmp_path / "legacy-venv")
