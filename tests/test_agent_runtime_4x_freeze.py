# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x agent compatibility copy."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

import hwpx.agent as agent
from hwpx.agent.cli import main

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "agent_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_agent_source_tree_is_exactly_frozen_for_core_4x() -> None:
    rows: list[dict[str, str | int]] = []
    for path in sorted((ROOT / "src" / "hwpx" / "agent").rglob("*.py")):
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "loc": len(data.splitlines()),
                "sha256": _sha256(data),
            }
        )
    canonical = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert len(rows) == FREEZE["pythonFileCount"] == 19
    assert sum(int(row["loc"]) for row in rows) == FREEZE["loc"] == 10008
    assert _sha256(canonical) == FREEZE["canonicalFileManifestSha256"]


def test_agent_exports_and_cli_remain_exact() -> None:
    ordered_exports = ("\n".join(agent.__all__) + "\n").encode("utf-8")
    assert len(agent.__all__) == FREEZE["rootExportCount"] == 62
    assert _sha256(ordered_exports) == FREEZE["rootOrderedExportsSha256"]

    stdout = io.StringIO()
    stderr = io.StringIO()
    assert main(["--help"], stdout=stdout, stderr=stderr) == 0
    assert stderr.getvalue() == ""
    assert _sha256(stdout.getvalue().encode("utf-8")) == FREEZE[
        "cliTopLevelHelpSha256"
    ]


def test_core_metadata_keeps_cli_and_has_no_mcp_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["scripts"]["hwpx"] == FREEZE["consoleEntryPoint"]
    assert not any(
        str(dependency).lower().startswith("hwpx-mcp-server")
        for dependency in project["dependencies"]
    )
