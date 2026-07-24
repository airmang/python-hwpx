# SPDX-License-Identifier: Apache-2.0
"""Renderer-neutral core seam and frozen 4.x visual surface."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

from hwpx.visual.block_splits import Block, BlockSplit, detect_block_splits

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "visual_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)
POST_SPLIT = json.loads(
    (
        ROOT
        / "tests"
        / "data"
        / "visual_runtime_post_split_freeze.json"
    ).read_text(encoding="utf-8")
)
PUBLIC_MODULES = (
    "hwpx.visual",
    "hwpx.visual.detectors",
    "hwpx.visual.diff",
    "hwpx.visual.fixture_corpus",
    "hwpx.visual.hancom_worker",
    "hwpx.visual.oracle",
    "hwpx.visual.page_qa",
    "hwpx.visual.qa_contracts",
    "hwpx.visual.qa_metrics",
)


@dataclasses.dataclass
class _Glyph:
    page: int
    x0: float
    x1: float


def _public_projection() -> dict[str, list[dict[str, object]]]:
    projection: dict[str, list[dict[str, object]]] = {}
    for module_name in PUBLIC_MODULES:
        module = importlib.import_module(module_name)
        shaped: list[dict[str, object]] = []
        for name in getattr(module, "__all__", ()):
            value = getattr(module, name)
            row: dict[str, object] = {
                "name": name,
                "kind": (
                    "class"
                    if inspect.isclass(value)
                    else "callable"
                    if callable(value)
                    else type(value).__name__
                ),
            }
            if callable(value):
                try:
                    row["signature"] = str(inspect.signature(value))
                except (TypeError, ValueError):
                    row["signature"] = None
            if inspect.isclass(value) and dataclasses.is_dataclass(value):
                row["fields"] = [
                    {
                        "name": field.name,
                        "type": str(field.type),
                        "default": (
                            "MISSING"
                            if field.default is dataclasses.MISSING
                            else repr(field.default)
                        ),
                        "defaultFactory": (
                            "MISSING"
                            if field.default_factory is dataclasses.MISSING
                            else repr(field.default_factory)
                        ),
                    }
                    for field in dataclasses.fields(value)
                ]
            shaped.append(row)
        projection[module_name] = shaped
    return projection


def test_released_visual_public_surface_is_exact() -> None:
    visual = importlib.import_module("hwpx.visual")
    assert list(visual.__all__) == FREEZE["publicSurface"]["orderedAll"]
    canonical = json.dumps(
        _public_projection(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == (
        FREEZE["publicSurface"]["projectionSha256"]
    )


def test_block_split_contract_has_no_runtime_or_application_imports() -> None:
    path = ROOT / "src" / "hwpx" / "visual" / "block_splits.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(
        name == forbidden or name.startswith(f"{forbidden}.")
        for name in imported
        for forbidden in (
            "hwpx.form_fit",
            "hwpx_mcp_server",
            "subprocess",
            "importlib.resources",
        )
    )


def test_block_split_geometry_is_behavior_compatible() -> None:
    blocks = [
        Block("page", [_Glyph(0, 1, 2), _Glyph(1, 1, 2)]),
        Block("column", [_Glyph(0, 1, 2), _Glyph(0, 11, 12)]),
        Block("clean", [_Glyph(0, 1, 2), _Glyph(0, 2, 3)]),
    ]
    assert detect_block_splits(blocks, [(0, 5), (10, 15)], 100) == [
        BlockSplit("page", "page"),
        BlockSplit("column", "column"),
    ]


def test_post_split_contract_and_compatibility_sources_are_frozen() -> None:
    rows: list[dict[str, str | int]] = []
    for expected in POST_SPLIT["files"]:
        path = ROOT / expected["path"]
        payload = path.read_bytes()
        rows.append(
            {
                "path": expected["path"],
                "loc": len(payload.splitlines()),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    canonical = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert rows == POST_SPLIT["files"]
    assert len(rows) == POST_SPLIT["pythonFiles"] == 12
    assert sum(int(row["loc"]) for row in rows) == POST_SPLIT["loc"] == 2698
    assert hashlib.sha256(canonical).hexdigest() == POST_SPLIT[
        "manifestSha256"
    ]


def test_neutral_import_does_not_activate_application_runtime() -> None:
    script = """
import json
import sys
import hwpx.visual.block_splits
import hwpx.visual.detectors
import hwpx.visual.diff
import hwpx.visual.qa_contracts
application = [
    "hwpx.visual.fixture_corpus",
    "hwpx.visual.hancom_worker",
    "hwpx.visual.oracle",
    "hwpx.visual.page_qa",
    "hwpx.visual.qa_metrics",
]
print(json.dumps([name for name in application if name in sys.modules]))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(process.stdout) == []


def test_neutral_files_have_no_mcp_or_hancom_runtime_dependency() -> None:
    forbidden = (
        "hwpx_mcp_server",
        "hwpx.form_fit",
        "subprocess",
        "importlib.resources",
    )
    for relative in POST_SPLIT["neutralFiles"]:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(
            name == denied or name.startswith(f"{denied}.")
            for name in imported
            for denied in forbidden
        ), (relative, imported)
