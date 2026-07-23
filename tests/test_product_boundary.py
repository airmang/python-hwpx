# SPDX-License-Identifier: Apache-2.0
"""Positive and negative fixtures for the product-boundary ratchet."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_product_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_product_boundary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
boundary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boundary)


def _ledger() -> dict:
    return json.loads(
        (ROOT / "docs" / "architecture" / "module-ownership.json").read_text(
            encoding="utf-8"
        )
    )


def test_real_tree_satisfies_ownership_ratchet() -> None:
    report = boundary.evaluate(ROOT, _ledger())
    assert report["ok"], report["violations"]
    assert report["classifiedFiles"] >= 176


def test_new_application_module_fails_closed(tmp_path) -> None:
    source = tmp_path / "src" / "hwpx" / "agent"
    source.mkdir(parents=True)
    (source / "new_workflow.py").write_text("VALUE = 1\n", encoding="utf-8")

    report = boundary.evaluate(tmp_path, _ledger(), baseline_files=set())

    assert not report["ok"]
    assert any("new module lacks explicit ownership" in item for item in report["violations"])


def test_core_reverse_dependency_fails_closed(tmp_path) -> None:
    source = tmp_path / "src" / "hwpx"
    source.mkdir(parents=True)
    path = source / "document.py"
    path.write_text("import hwpx_mcp_server\n", encoding="utf-8")

    report = boundary.evaluate(
        tmp_path,
        _ledger(),
        baseline_files={"src/hwpx/document.py"},
    )

    assert not report["ok"]
    assert any("core reverse dependency" in item for item in report["violations"])


def test_unpublished_house_style_surface_is_absent_from_core() -> None:
    import hwpx

    assert importlib.util.find_spec("hwpx.house_style") is None
    assert "build_section_chip" not in hwpx.__all__
    assert not hasattr(hwpx, "build_section_chip")
