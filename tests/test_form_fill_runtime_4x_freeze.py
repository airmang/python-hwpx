# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x form-fill compatibility copy."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

import hwpx

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "form_fill_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)
MODULE_NAMES = (
    "hwpx.fill_residue",
    "hwpx.form_fill",
    "hwpx.form_fit",
    "hwpx.form_fit.apply",
    "hwpx.form_fit.engine",
    "hwpx.form_fit.measure",
    "hwpx.form_fit.policy",
    "hwpx.form_fit.report",
    "hwpx.form_fit.seal",
    "hwpx.form_fit.wordbox",
    "hwpx.formfill_quality",
    "hwpx.guidance_scan",
    "hwpx.template_formfit",
)
MODULES = tuple(importlib.import_module(name) for name in MODULE_NAMES)


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


def _signature(value: Any) -> str | None:
    if not callable(value):
        return None
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return "<uninspectable>"


def _source_paths() -> list[Path]:
    paths = [
        ROOT / "src" / "hwpx" / "fill_residue.py",
        ROOT / "src" / "hwpx" / "form_fill.py",
        ROOT / "src" / "hwpx" / "formfill_quality.py",
        ROOT / "src" / "hwpx" / "guidance_scan.py",
        ROOT / "src" / "hwpx" / "template_formfit.py",
    ]
    paths.extend(sorted((ROOT / "src" / "hwpx" / "form_fit").glob("*.py")))
    return sorted(paths)


def _qualified_api() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in MODULES:
        names = list(getattr(module, "__all__", ()))
        if not names:
            names = sorted(
                name
                for name, value in vars(module).items()
                if not name.startswith("_")
                and getattr(value, "__module__", None) == module.__name__
            )
        for name in names:
            value = getattr(module, name)
            row: dict[str, Any] = {
                "module": module.__name__,
                "name": name,
                "kind": type(value).__name__,
                "origin": getattr(value, "__module__", None),
                "signature": _signature(value),
            }
            if not callable(value):
                row["value"] = value
            rows.append(row)
    return rows


def _top_level_api() -> list[dict[str, Any]]:
    prefixes = tuple(module.__name__ for module in MODULES)
    rows: list[dict[str, Any]] = []
    for name in hwpx.__all__:
        value = getattr(hwpx, name)
        origin = getattr(value, "__module__", "") or ""
        if not any(
            origin == prefix or origin.startswith(f"{prefix}.") for prefix in prefixes
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


def test_form_fill_source_tree_is_exactly_frozen_for_core_4x() -> None:
    rows: list[dict[str, str | int]] = []
    for path in _source_paths():
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "loc": len(data.splitlines()),
                "sha256": _sha256(data),
            }
        )

    assert len(rows) == FREEZE["pythonFileCount"] == 13
    assert sum(int(row["loc"]) for row in rows) == FREEZE["loc"] == 5745
    assert _sha256(_canonical(rows)) == FREEZE["canonicalFileManifestSha256"]


def test_form_fill_public_imports_and_signatures_remain_exact() -> None:
    qualified = _qualified_api()
    top_level = _top_level_api()

    assert len(qualified) == FREEZE["qualifiedExportCount"] == 103
    assert (
        _sha256(_canonical(qualified)) == FREEZE["verificationQualifiedSnapshotSha256"]
    )
    assert FREEZE["adoptionQualifiedSnapshotSha256"] == (
        "430290c5918600f822fdcbcf108236c1dbca34922a04670038ff3898baace3c8"
    )
    assert len(top_level) == FREEZE["topLevelExportCount"] == 0
    assert _sha256(_canonical(top_level)) == FREEZE["topLevelSnapshotSha256"]


def test_core_metadata_has_no_mcp_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert not any(
        str(dependency).lower().startswith("hwpx-mcp-server")
        for dependency in project["dependencies"]
    )
