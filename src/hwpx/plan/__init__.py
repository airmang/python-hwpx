# SPDX-License-Identifier: Apache-2.0
"""``hwpx.plan`` — 선언적 편집 계획 실행기 (experimental, 5.6.0 신규).

기존 바이트-스플라이스 편집 op 어휘(``paragraph_patch``·``fill_cells``·
``apply_table_ops``·``apply_body_ops``·색 run 일괄 op·꼬리 캡션 제거)를
계획 1파일(``hwpx.edit-plan/v1``)로 합성해 실행한다:

    정적 선검증(파일 무접촉) → 전 체인 인메모리 실행 → 최종 open-safety 검증
    → 단 1회 원자 쓰기

중간 어느 step이 실패해도 output·source는 바이트 불변이다(all-or-nothing).
결과는 ``hwpx.plan-report/v1`` — step별 ``hwpx.mutation-report/v1`` 사영과
원본→최종 실측 집계를 싣는다. 상세 계약:
``docs/safe-write-contract.md``.
"""

from __future__ import annotations

from ._execute import apply_edit_plan
from ._model import (
    EDIT_PLAN_SCHEMA,
    PLAN_REPORT_SCHEMA,
    EditPlan,
    PlanReport,
    PlanStep,
    PlanValidation,
    PlanValidationError,
    StepRecord,
)
from ._schema import edit_plan_json_schema, plan_report_json_schema
from ._validate import PLAN_OPS, OpSpec, validate_edit_plan

__all__ = [
    "EDIT_PLAN_SCHEMA",
    "PLAN_REPORT_SCHEMA",
    "PLAN_OPS",
    "OpSpec",
    "EditPlan",
    "PlanStep",
    "PlanValidation",
    "PlanValidationError",
    "StepRecord",
    "PlanReport",
    "validate_edit_plan",
    "apply_edit_plan",
    "edit_plan_json_schema",
    "plan_report_json_schema",
]
