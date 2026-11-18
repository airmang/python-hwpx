# SPDX-License-Identifier: Apache-2.0
"""Callable-level document-operation ownership and the released compatibility surface.

The freeze began as the 4.x surface of three modules. 7.0 moved the reference
consistency lint and mail merge to python-hwpx-automation, so the frozen surface is
now the document diff and the redline structure (``movedIn7_0`` in the freeze lists
what left).
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import hwpx
from hwpx import HwpxDocument, tools
from hwpx.tools.doc_diff import doc_diff
from hwpx.tools.redline import author_demo_redline, inspect_redline_structure

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (
        ROOT / "tests" / "data" / "document_ops_runtime_4x_freeze.json"
    ).read_text(encoding="utf-8")
)
MODULES = {
    name: importlib.import_module(name)
    for name in (
        "hwpx.tools.doc_diff",
        "hwpx.tools.redline",
    )
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _signature(value: Any) -> str | None:
    if not callable(value):
        return None
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return "<uninspectable>"


def _qualified_compatibility_projection() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expected in FREEZE["qualifiedExports"]:
        value = getattr(MODULES[expected["module"]], expected["name"])
        rows.append(
            {
                "module": expected["module"],
                "name": expected["name"],
                "kind": type(value).__name__,
                "origin": getattr(value, "__module__", None),
                "signature": _signature(value),
                "value": None if callable(value) else value,
            }
        )
    return rows


def _reexported_projection(module: Any) -> list[dict[str, Any]]:
    prefixes = tuple(MODULES)
    rows: list[dict[str, Any]] = []
    for name in module.__all__:
        value = getattr(module, name)
        origin = getattr(value, "__module__", "") or ""
        if not any(
            origin == prefix or origin.startswith(f"{prefix}.")
            for prefix in prefixes
        ):
            continue
        rows.append(
            {
                "name": name,
                "origin": origin,
                "kind": type(value).__name__,
                "signature": _signature(value),
            }
        )
    return rows


def _deterministic_payloads() -> dict[str, Any]:
    return {
        "diff": doc_diff(["a", "b"], ["a", "c", "d"]),
    }


def test_released_document_ops_4x_surface_is_exact() -> None:
    qualified = _qualified_compatibility_projection()
    top_level = _reexported_projection(hwpx)
    tools_level = _reexported_projection(tools)

    assert len(qualified) == FREEZE["qualifiedExportCount"] == 6
    assert _sha256(_canonical(qualified)) == FREEZE["qualifiedSnapshotSha256"]
    assert len(top_level) == FREEZE["topLevelExportCount"] == 2
    assert _sha256(_canonical(top_level)) == FREEZE["topLevelSnapshotSha256"]
    assert len(tools_level) == FREEZE["toolsExportCount"] == 2
    assert _sha256(_canonical(tools_level)) == FREEZE["toolsSnapshotSha256"]
    assert _sha256(_canonical(_deterministic_payloads())) == FREEZE[
        "deterministicPayloadsSha256"
    ]


def test_redline_structure_is_renderer_neutral(tmp_path: Path) -> None:
    after = tmp_path / "after.hwpx"
    document = HwpxDocument.new()
    try:
        document.add_paragraph("baseline")
        author_demo_redline(document)
        document.save(after)
    finally:
        document.close()

    report = inspect_redline_structure(after)

    assert report["changeCount"] == 2
    assert report["marksLinked"] is True
    assert report["displayEnabled"] is True
    assert report["opensClean"] is True


def test_neutral_redline_import_does_not_activate_visual_runtime() -> None:
    script = """
import json
import sys
from hwpx.tools.redline import inspect_redline_structure
print(json.dumps({
    "callable": callable(inspect_redline_structure),
    # The old assertion watched hwpx.visual.oracle, which 5.0 removed — it would
    # now pass by watching nothing. The boundary that still exists is the
    # companion package, so watch that.
    "visual": any(name.startswith("hwpx_automation.office.rendering") for name in sys.modules),
    "mcp": any(name.startswith("hwpx_automation") for name in sys.modules),
}))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    )

    assert json.loads(process.stdout) == {
        "callable": True,
        "visual": False,
        "mcp": False,
    }
