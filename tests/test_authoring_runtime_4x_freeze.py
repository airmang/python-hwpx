# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x authoring compatibility copy."""
from __future__ import annotations

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

import hwpx
from hwpx import authoring, builder, design, presets
from hwpx.tools import advanced_generators, style_profile, template_analyzer


ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "authoring_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)
MODULES = (
    authoring,
    builder,
    design,
    presets,
    advanced_generators,
    style_profile,
    template_analyzer,
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


def _source_paths() -> list[Path]:
    paths = [
        ROOT / "src" / "hwpx" / "authoring.py",
        ROOT / "src" / "hwpx" / "tools" / "advanced_generators.py",
        ROOT / "src" / "hwpx" / "tools" / "style_profile.py",
        ROOT / "src" / "hwpx" / "tools" / "template_analyzer.py",
    ]
    for relative in (
        "src/hwpx/builder",
        "src/hwpx/design",
        "src/hwpx/presets",
    ):
        paths.extend(sorted((ROOT / relative).rglob("*.py")))
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
                and (
                    getattr(value, "__module__", None) == module.__name__
                    or (
                        name.isupper()
                        and isinstance(
                            value,
                            (str, int, float, bool, tuple, frozenset),
                        )
                    )
                )
            )
        for name in names:
            value = getattr(module, name)
            try:
                signature = (
                    str(inspect.signature(value)) if callable(value) else None
                )
            except (TypeError, ValueError):
                signature = "<uninspectable>"
            row: dict[str, Any] = {
                "module": module.__name__,
                "name": name,
                "kind": type(value).__name__,
                "origin": getattr(value, "__module__", None),
                "signature": signature,
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
            origin == prefix or origin.startswith(f"{prefix}.")
            for prefix in prefixes
        ):
            continue
        try:
            signature = (
                str(inspect.signature(value)) if callable(value) else None
            )
        except (TypeError, ValueError):
            signature = "<uninspectable>"
        rows.append(
            {
                "name": name,
                "origin": origin,
                "kind": type(value).__name__,
                "signature": signature,
            }
        )
    return rows


def _deterministic_payloads() -> dict[str, Any]:
    plan = {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "동결",
        "blocks": [{"type": "paragraph", "text": "본문"}],
    }
    profile = {
        "schemaVersion": "hwpx.style-profile.v1",
        "page": {
            "orientation": "LANDSCAPE",
            "widthMm": 297,
            "heightMm": 210,
            "marginsMm": {
                "left": 20,
                "right": 20,
                "top": 15,
                "bottom": 15,
            },
        },
        "body": {"font": "함초롬바탕", "sizePt": 11},
    }
    return {
        "documentPlanSchema": authoring.get_document_plan_schema(),
        "normalizedPlan": authoring.normalize_document_plan(plan).to_dict(),
        "validPlanReport": authoring.validate_document_plan(plan).to_dict(),
        "invalidPlanReport": authoring.validate_document_plan(
            {
                "schemaVersion": "hwpx.document_plan.v1",
                "blocks": [{}],
            }
        ).to_dict(),
        "imageGrid": advanced_generators.build_image_grid(
            ["a.png", "b.png"],
            columns=2,
            image_width_mm=50,
        ),
        "nameplates": advanced_generators.build_meeting_nameplates(
            ["가", "나"],
            size="150x70",
            columns=2,
        ),
        "organizationChart": advanced_generators.build_organization_chart(
            {"name": "대표", "children": [{"name": "팀"}]}
        ),
        "proposalSpec": dataclasses.asdict(
            presets.normalize_proposal_spec(
                {
                    "title": "제안",
                    "sections": [
                        {"title": "배경", "paragraphs": ["내용"]}
                    ],
                }
            )
        ),
        "styledPlan": style_profile.apply_style_profile_to_plan(
            plan,
            profile,
        ),
        "templateAgentSchema": (
            template_analyzer.template_analysis_agent_schema()
        ),
    }


def test_authoring_source_tree_is_exactly_frozen_for_core_4x() -> None:
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

    assert len(rows) == FREEZE["pythonFileCount"] == 16
    assert sum(int(row["loc"]) for row in rows) == FREEZE["loc"] == 7554
    assert _sha256(_canonical(rows)) == FREEZE[
        "canonicalFileManifestSha256"
    ]


def test_authoring_public_imports_and_signatures_remain_exact() -> None:
    qualified = _qualified_api()
    top_level = _top_level_api()
    versions = [
        {
            "module": module.__name__,
            "name": name,
            "value": value,
        }
        for module in MODULES
        for name, value in vars(module).items()
        if name.isupper()
        and isinstance(value, str)
        and ("version" in name.lower() or "/v" in value or ".v" in value)
    ]

    assert len(qualified) == FREEZE["qualifiedExportCount"] == 79
    assert _sha256(_canonical(qualified)) == FREEZE[
        "qualifiedSnapshotSha256"
    ]
    assert len(top_level) == FREEZE["topLevelExportCount"] == 22
    assert _sha256(_canonical(top_level)) == FREEZE[
        "topLevelSnapshotSha256"
    ]
    assert len(versions) == FREEZE["schemaVersionCount"] == 10
    assert _sha256(_canonical(versions)) == FREEZE[
        "schemaVersionsSha256"
    ]


def test_authoring_deterministic_payloads_remain_exact() -> None:
    assert _sha256(_canonical(_deterministic_payloads())) == FREEZE[
        "deterministicPayloadsSha256"
    ]


def test_core_metadata_keeps_public_cli_and_has_no_mcp_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["scripts"]["hwpx-analyze-template"] == FREEZE[
        "templateAnalyzerEntryPoint"
    ]
    assert not any(
        str(dependency).lower().startswith("hwpx-mcp-server")
        for dependency in project["dependencies"]
    )
