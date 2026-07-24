# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x evalplan compatibility copy."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from hwpx import evalplan_fill

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "evalplan_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _signature(value: Any) -> str:
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return "<uninspectable>"


def _ordered_api() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in evalplan_fill.__all__:
        value = getattr(evalplan_fill, name)
        rows.append(
            {
                "name": name,
                "kind": type(value).__name__,
                "origin": getattr(value, "__module__", None),
                "signature": _signature(value),
            }
        )
    return rows


def _default(field: dataclasses.Field[Any]) -> str:
    if field.default is not dataclasses.MISSING:
        return repr(field.default)
    if field.default_factory is not dataclasses.MISSING:
        name = getattr(
            field.default_factory,
            "__name__",
            type(field.default_factory).__name__,
        )
        return f"<factory:{name}>"
    return "<required>"


def _dataclass_api() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cls in (
        evalplan_fill.RubricItem,
        evalplan_fill.RubricSubArea,
        evalplan_fill.Rubric,
        evalplan_fill.EvalPlanContent,
    ):
        rows.append(
            {
                "name": cls.__name__,
                "fields": [
                    {
                        "name": field.name,
                        "type": str(field.type),
                        "default": _default(field),
                    }
                    for field in dataclasses.fields(cls)
                ],
            }
        )
    return rows


def test_evalplan_source_is_exactly_frozen_for_core_4x() -> None:
    path = ROOT / "src" / "hwpx" / "evalplan_fill.py"
    data = path.read_bytes()
    rows = [
        {
            "path": "src/hwpx/evalplan_fill.py",
            "loc": len(data.splitlines()),
            "sha256": _sha256(data),
        }
    ]

    assert FREEZE["pythonFileCount"] == 1
    assert rows[0]["loc"] == FREEZE["loc"] == 2727
    assert rows[0]["sha256"] == FREEZE["sourceSha256"]
    assert _sha256(_canonical(rows)) == FREEZE["canonicalFileManifestSha256"]


def test_evalplan_public_imports_and_models_remain_exact() -> None:
    ordered = _ordered_api()
    models = _dataclass_api()

    assert len(ordered) == FREEZE["orderedExportCount"] == 14
    assert _sha256(_canonical(ordered)) == FREEZE["orderedExportSnapshotSha256"]
    assert len(models) == FREEZE["dataclassCount"] == 4
    assert _sha256(_canonical(models)) == FREEZE["dataclassSnapshotSha256"]


def test_core_has_no_mcp_or_skill_reverse_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert not any(
        str(dependency).lower().startswith(("hwpx-mcp-server", "hwpx-skill"))
        for dependency in project["dependencies"]
    )

    forbidden = ("hwpx_mcp_server", "hwpx_skill")
    violations: list[str] = []
    for path in sorted((ROOT / "src" / "hwpx").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(forbidden):
                    violations.append(
                        f"{path.relative_to(ROOT).as_posix()} -> {name}"
                    )

    assert violations == []
