# SPDX-License-Identifier: Apache-2.0
"""edit-plan / plan-report JSON Schema 라이브 빌드.

스키마는 코드에서 생성한다(파일 박제 아님) — op enum이 :data:`PLAN_OPS`에서
직접 나오므로 어휘 드리프트가 구조적으로 불가능하다. 중첩 op 어휘
(``apply_table_ops``의 12종 등)는 소유 op의 실행-시 검증이 진실 원천이라
스키마는 배열-of-객체까지만 말한다(정직 — 여기서 흉내 내지 않는다).
"""

from __future__ import annotations

from typing import Any

from ._model import EDIT_PLAN_SCHEMA, PLAN_REPORT_SCHEMA
from ._validate import PLAN_OPS

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def edit_plan_json_schema() -> dict[str, Any]:
    """``hwpx.edit-plan/v1``의 JSON Schema."""

    return {
        "$schema": _DRAFT,
        "$id": "https://airmang.github.io/python-hwpx/schemas/edit-plan-v1.json",
        "title": EDIT_PLAN_SCHEMA,
        "type": "object",
        "additionalProperties": False,
        "required": ["schemaVersion", "source", "output", "steps"],
        "properties": {
            "schemaVersion": {"const": EDIT_PLAN_SCHEMA},
            "source": {"type": "string", "minLength": 1},
            "output": {"type": "string", "minLength": 1},
            "journalPath": {"type": "string", "minLength": 1},
            "steps": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "op"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "op": {"enum": sorted(PLAN_OPS)},
                        "args": {"type": "object"},
                    },
                },
            },
        },
    }


def plan_report_json_schema() -> dict[str, Any]:
    """``hwpx.plan-report/v1``의 JSON Schema (판정 소비용 상위 형태)."""

    verification_value = {"enum": ["passed", "failed", "not_performed"]}
    return {
        "$schema": _DRAFT,
        "$id": "https://airmang.github.io/python-hwpx/schemas/plan-report-v1.json",
        "title": PLAN_REPORT_SCHEMA,
        "type": "object",
        "required": [
            "schemaVersion",
            "ok",
            "executed",
            "dryRun",
            "plan",
            "steps",
            "aggregate",
        ],
        "properties": {
            "schemaVersion": {"const": PLAN_REPORT_SCHEMA},
            "ok": {"type": "boolean"},
            "executed": {"type": "boolean"},
            "dryRun": {"type": "boolean"},
            "plan": edit_plan_json_schema(),
            "preservationFloor": {"enum": ["patch", None]},
            "failedStepId": {"type": ["string", "null"]},
            "outputPath": {"type": ["string", "null"]},
            "journalPath": {"type": ["string", "null"]},
            "lints": {"type": "array", "items": {"type": "object"}},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "stepId",
                        "op",
                        "status",
                        "inputSha256",
                        "report",
                    ],
                    "properties": {
                        "stepId": {"type": "string"},
                        "op": {"enum": sorted(PLAN_OPS)},
                        "status": {"enum": ["applied", "would_apply", "failed"]},
                        "startedAt": {"type": "string"},
                        "finishedAt": {"type": "string"},
                        "inputSha256": {"type": "string"},
                        "outputSha256": {"type": ["string", "null"]},
                        "report": {"type": ["object", "null"]},
                        "detail": {"type": "object"},
                        "error": {"type": ["object", "null"]},
                    },
                },
            },
            "aggregate": {
                "type": ["object", "null"],
                "description": (
                    "원본→최종 바이트의 hwpx.mutation-report/v1 실측 사영. "
                    "실패 시 null."
                ),
                "properties": {
                    "schemaVersion": {"const": "hwpx.mutation-report/v1"},
                    "verification": {
                        "type": "object",
                        "properties": {
                            "package": verification_value,
                            "openSafety": verification_value,
                            "reopen": verification_value,
                            "visual": verification_value,
                        },
                    },
                },
            },
        },
    }
