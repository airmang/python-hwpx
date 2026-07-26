# SPDX-License-Identifier: Apache-2.0
"""Release ordering must protect the already-published 5.x application."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


def test_public_legacy_cap_is_observed_before_core_release_tests() -> None:
    workflow = RELEASE.read_text(encoding="utf-8")
    phase0_name = "- name: Require public 5.1.1 legacy cap before core 5"
    dependency_name = "- name: Install release test dependencies"
    phase0 = workflow.index(phase0_name)
    dependencies = workflow.index(dependency_name)
    assert phase0 < dependencies

    block = workflow[phase0:dependencies]
    assert '"python-hwpx==4.2.0"' in block
    assert '"hwpx-mcp-server==5.1.1"' in block
    assert '"python-hwpx==5.0.0"' not in block
    assert '"<5"' in block
    assert '">=4.2.0"' in block
    assert "len(requirements) == 3" in block
    assert "import hwpx_mcp_server" in block
    assert '"${PHASE0_VENV}/bin/hwpx-mcp-server" --help' in block
