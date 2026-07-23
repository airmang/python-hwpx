# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x compliance/quality/utility copies."""
from __future__ import annotations

import dataclasses
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
from hwpx import tools

official_lint = importlib.import_module("hwpx.tools.official_lint")
pii = importlib.import_module("hwpx.tools.pii")
page_guard = importlib.import_module("hwpx.tools.page_guard")
table_compute = importlib.import_module("hwpx.tools.table_compute")

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "policy_runtime_4x_freeze.json").read_text(
        encoding="utf-8"
    )
)
MODULES = (official_lint, pii, page_guard, table_compute)


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
    return [
        ROOT / "src" / "hwpx" / "tools" / "official_lint.py",
        ROOT / "src" / "hwpx" / "tools" / "pii.py",
        ROOT / "src" / "hwpx" / "tools" / "page_guard.py",
        ROOT / "src" / "hwpx" / "tools" / "table_compute.py",
    ]


def _qualified_api() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in MODULES:
        for name in module.__all__:
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


def _reexported_api(module: Any) -> list[dict[str, Any]]:
    prefixes = tuple(item.__name__ for item in MODULES)
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
    reference = page_guard.DocumentMetrics(
        section_count=1,
        paragraph_count=2,
        page_break_count=0,
        column_break_count=0,
        table_count=0,
        shape_count=0,
        control_count=0,
        table_shapes=[],
        shape_types=[],
        control_types=[],
        text_char_total=8,
        text_char_total_nospace=7,
        paragraph_text_lengths=[4, 4],
    )
    output = dataclasses.replace(
        reference,
        paragraph_count=3,
        text_char_total=13,
        text_char_total_nospace=12,
        paragraph_text_lengths=[4, 9],
    )
    text = "성명: 홍길동 / 010-1234-5678 / hong@example.com"
    table = {
        "type": "table",
        "columns": [
            {"key": "team", "label": "팀"},
            {"key": "amount", "label": "금액"},
        ],
        "rows": [
            {"team": "A", "amount": "1,000원"},
            {"team": "A", "amount": "2,000원"},
        ],
    }
    return {
        "official": official_lint.inspect_official_document_style(
            [
                "1. 추진 목적",
                "  가. 세부 내용",
                "일시: 2026. 7. 24.",
                "붙임  1. 자료 1부.  끝.",
            ],
            document_type="gongmun",
        ),
        "piiSpans": pii.detect_pii(text),
        "piiMasked": pii.mask_pii(text),
        "minimized": pii.minimize_fields(
            {"name": "홍길동", "empty": "", "score": 0},
            ["score", "empty", "name"],
            drop_empty=True,
        ),
        "deidentified": pii.deidentify("홍길동", salt="s100"),
        "pageComparison": page_guard.compare_metrics(reference, output),
        "tableCompute": table_compute.table_compute(
            table,
            value_columns=["amount"],
            operations=["subtotal", "sum"],
            group_by="team",
            label_column="team",
        ),
    }


def test_policy_source_files_are_exactly_frozen_for_core_4x() -> None:
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

    assert len(rows) == FREEZE["pythonFileCount"] == 4
    assert sum(int(row["loc"]) for row in rows) == FREEZE["loc"] == 1622
    assert _sha256(_canonical(rows)) == FREEZE[
        "canonicalFileManifestSha256"
    ]


def test_policy_public_imports_and_signatures_remain_exact() -> None:
    qualified = _qualified_api()
    top_level = _reexported_api(hwpx)
    tools_level = _reexported_api(tools)

    assert len(qualified) == FREEZE["qualifiedExportCount"] == 20
    assert _sha256(_canonical(qualified)) == FREEZE[
        "qualifiedSnapshotSha256"
    ]
    assert len(top_level) == FREEZE["topLevelExportCount"] == 2
    assert _sha256(_canonical(top_level)) == FREEZE[
        "topLevelSnapshotSha256"
    ]
    assert len(tools_level) == FREEZE["toolsExportCount"] == 5
    assert _sha256(_canonical(tools_level)) == FREEZE[
        "toolsSnapshotSha256"
    ]


def test_policy_deterministic_payloads_remain_exact() -> None:
    assert _sha256(_canonical(_deterministic_payloads())) == FREEZE[
        "deterministicPayloadsSha256"
    ]


def test_core_metadata_keeps_page_guard_cli_and_has_no_mcp_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["scripts"]["hwpx-page-guard"] == FREEZE[
        "pageGuardEntryPoint"
    ]
    assert not any(
        str(dependency).lower().startswith("hwpx-mcp-server")
        for dependency in project["dependencies"]
    )
