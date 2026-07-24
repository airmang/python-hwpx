# SPDX-License-Identifier: Apache-2.0
"""Freeze the operational core 4.x exam compatibility copy."""

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

from hwpx import exam

ROOT = Path(__file__).resolve().parents[1]
FREEZE = json.loads(
    (ROOT / "tests" / "data" / "exam_runtime_4x_freeze.json").read_text(
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
    return [
        {
            "name": name,
            "kind": type(getattr(exam, name)).__name__,
            "origin": getattr(getattr(exam, name), "__module__", None),
            "signature": _signature(getattr(exam, name)),
        }
        for name in exam.__all__
    ]


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
    classes = [
        value
        for name in exam.__all__
        if dataclasses.is_dataclass(value := getattr(exam, name))
    ]
    return [
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
        for cls in classes
    ]


def test_exam_source_tree_is_exactly_frozen_for_core_4x() -> None:
    rows: list[dict[str, str | int]] = []
    for path in sorted((ROOT / "src" / "hwpx" / "exam").rglob("*.py")):
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "loc": len(data.splitlines()),
                "sha256": _sha256(data),
            }
        )

    assert len(rows) == FREEZE["pythonFileCount"] == 6
    assert sum(int(row["loc"]) for row in rows) == FREEZE["loc"] == 708
    assert _sha256(_canonical(rows)) == FREEZE["canonicalFileManifestSha256"]


def test_exam_public_api_and_ten_dataclasses_remain_exact() -> None:
    ordered = _ordered_api()
    models = _dataclass_api()

    assert len(ordered) == FREEZE["orderedExportCount"] == 20
    assert _sha256(_canonical(ordered)) == FREEZE["orderedExportSnapshotSha256"]
    assert len(models) == FREEZE["dataclassCount"] == 10
    assert _sha256(_canonical(models)) == FREEZE["dataclassSnapshotSha256"]


def test_exam_parser_lowering_and_error_projection_is_frozen() -> None:
    markdown = """# 동결 시험

## 1. (3점)
발문 [그림1]
① 가
② 나

## 2∼3. 세트
공통 지문
### 2.
둘째
① 다
### 3. (2점)
셋째
① 라
"""
    parsed = exam.parse_exam_markdown(markdown)
    normal = exam.ResolvedStyle("바탕글", "0", "0", "0")
    profile = exam.FormProfile(
        role_styles={
            "normal": normal,
            "number": exam.ResolvedStyle("번호", "1", "1", "1"),
            "choice1": exam.ResolvedStyle("답항", "2", "2", "2"),
        },
        admin_box_index=0,
        body_start=1,
        body_end=3,
        replaceable_indices=(1, 2, 3),
        structural_indices=(),
        ambiguous_indices=(),
    )
    lowered = exam.lower_exam(parsed, profile)

    assert dataclasses.asdict(parsed) == {
        "title": "동결 시험",
        "blocks": (
            {
                "number": "1",
                "stem": "발문 [그림1]",
                "choices": ("① 가", "② 나"),
                "points": "3",
                "placeholders": (
                    {"id": "그림1", "kind": "img", "raw_text": "[그림1]"},
                ),
            },
            {
                "passage": "공통 지문",
                "rng": "2∼3",
                "members": (
                    {
                        "number": "2",
                        "stem": "둘째",
                        "choices": ("① 다",),
                        "points": None,
                        "placeholders": (),
                    },
                    {
                        "number": "3",
                        "stem": "셋째",
                        "choices": ("① 라",),
                        "points": "2",
                        "placeholders": (),
                    },
                ),
            },
        ),
    }
    assert [dataclasses.asdict(spec) for spec in lowered] == [
        {
            "text": "1. 발문 [그림1]",
            "role": "number",
            "keep_with_next": True,
            "is_question_head": True,
            "question_number": "1",
        },
        {
            "text": "① 가",
            "role": "choice1",
            "keep_with_next": True,
            "is_question_head": False,
            "question_number": "1",
        },
        {
            "text": "② 나",
            "role": "choice1",
            "keep_with_next": False,
            "is_question_head": False,
            "question_number": "1",
        },
        {
            "text": "공통 지문",
            "role": "normal",
            "keep_with_next": True,
            "is_question_head": False,
            "question_number": None,
        },
        {
            "text": "2. 둘째",
            "role": "number",
            "keep_with_next": True,
            "is_question_head": True,
            "question_number": "2",
        },
        {
            "text": "① 다",
            "role": "choice1",
            "keep_with_next": False,
            "is_question_head": False,
            "question_number": "2",
        },
        {
            "text": "3. 셋째",
            "role": "number",
            "keep_with_next": True,
            "is_question_head": True,
            "question_number": "3",
        },
        {
            "text": "① 라",
            "role": "choice1",
            "keep_with_next": False,
            "is_question_head": False,
            "question_number": "3",
        },
    ]

    try:
        exam.parse_exam_markdown("헤더 없는 본문")
    except exam.ExamParseError as error:
        assert (
            str(error),
            error.line_no,
            error.text,
            error.reason,
        ) == (
            "line 1: content before any 문항 / 세트 header: '헤더 없는 본문'",
            1,
            "헤더 없는 본문",
            "content before any 문항 / 세트 header",
        )
    else:  # pragma: no cover - fail-loud guard
        raise AssertionError("invalid exam Markdown must fail loud")


def test_core_has_no_mcp_or_skill_reverse_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert not any(
        str(dependency).lower().startswith(("hwpx-mcp-server", "hwpx-skill"))
        for dependency in project["dependencies"]
    )

    violations: list[str] = []
    for path in sorted((ROOT / "src" / "hwpx").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imports: list[str] = []
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            violations.extend(
                f"{path.relative_to(ROOT).as_posix()} -> {name}"
                for name in imports
                if name.startswith(("hwpx_mcp_server", "hwpx_skill"))
            )

    assert violations == []
