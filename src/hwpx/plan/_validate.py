# SPDX-License-Identifier: Apache-2.0
"""계획 정적 선검증 — 파일을 읽지 않고 계획의 실행 자격을 판정한다.

op 어휘의 단일 진실 원천 :data:`PLAN_OPS`가 여기 있다. 실행 디스패치
(:mod:`hwpx.plan._execute`)와 JSON Schema(:mod:`hwpx.plan._schema`),
``hwpx.capabilities()``의 ``editPlanOps``가 전부 이 표를 참조한다 — 드리프트
가드 테스트가 3자 일치를 강제한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ._model import EditPlan, PlanValidation, PlanValidationError


@dataclass(frozen=True)
class OpSpec:
    """plan step이 지시할 수 있는 op 하나의 인자 계약.

    ``required``/``optional``은 step ``args``의 **바깥** 키만 다룬다 —
    ``apply_table_ops``의 내부 12종 op dict 같은 중첩 어휘는 해당 op 자신의
    실행-시 검증(fail-closed·transcript)이 소유하고, 여기서는 반복하지 않는다.
    """

    required: frozenset[str]
    optional: frozenset[str]

    @property
    def allowed(self) -> frozenset[str]:
        return self.required | self.optional


#: v1 op 어휘 — 이름은 core 함수명 그대로(새 동사 없음). 계약 v1.
PLAN_OPS: dict[str, OpSpec] = {
    "paragraph_patch": OpSpec(frozenset({"patches"}), frozenset()),
    "fill_cells": OpSpec(
        frozenset({"cells"}), frozenset({"fit_max_lines", "min_font_pt"})
    ),
    "apply_table_ops": OpSpec(frozenset({"ops"}), frozenset()),
    "apply_body_ops": OpSpec(frozenset({"ops"}), frozenset()),
    "recolor_runs_by_color": OpSpec(
        frozenset({"from_hexes", "to_color"}), frozenset()
    ),
    "strip_runs_by_color": OpSpec(frozenset({"hex_colors"}), frozenset()),
    "strip_trailing_table_captions": OpSpec(frozenset(), frozenset()),
}

_LIST_ARGS = {"patches", "cells", "ops", "from_hexes", "hex_colors"}


def _load_plan(plan: EditPlan | Mapping[str, Any] | str | Path) -> EditPlan:
    if isinstance(plan, EditPlan):
        return plan
    if isinstance(plan, Mapping):
        return EditPlan.from_dict(plan)
    if isinstance(plan, (str, Path)):
        path = Path(plan)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PlanValidationError(
                f"계획 파일을 읽을 수 없습니다: {path}",
                context={"path": str(path), "oserror": str(exc)},
            ) from exc
        except json.JSONDecodeError as exc:
            raise PlanValidationError(
                f"계획 파일이 유효한 JSON이 아닙니다: {path}",
                context={"path": str(path), "jsonError": str(exc)},
            ) from exc
        return EditPlan.from_dict(raw)
    raise PlanValidationError(
        "계획은 EditPlan, 객체(dict), 또는 JSON 파일 경로여야 합니다.",
        context={"got": type(plan).__name__},
    )


def _lint_delete_table_order(step_id: str, ops: Any) -> dict[str, Any] | None:
    """``delete_table``을 오름차순 인덱스로 늘어놓으면 후행 인덱스가 시프트되는
    함정(table_patch.py 문서화)을 경고한다 — 실행은 막지 않는다."""

    if not isinstance(ops, (list, tuple)):
        return None
    indices = [
        op.get("table_index", op.get("tableIndex"))
        for op in ops
        if isinstance(op, Mapping) and op.get("op") == "delete_table"
    ]
    numeric = [i for i in indices if isinstance(i, int)]
    if len(numeric) >= 2 and numeric != sorted(numeric, reverse=True):
        return {
            "stepId": step_id,
            "code": "delete-table-order",
            "message": (
                "delete_table 여러 건은 역순(table_index 내림차순)으로 배열해야 "
                "후행 인덱스 시프트를 피합니다."
            ),
        }
    return None


def validate_edit_plan(
    plan: EditPlan | Mapping[str, Any] | str | Path,
) -> PlanValidation:
    """계획을 정적으로 검증한다 — **어떤 문서 파일도 열지 않는다**.

    구조 결함(미지 필드·중복 id·미지 op·인자 키 위반·source 부재)은
    :class:`PlanValidationError`로 즉시 거부한다(fail-closed). 실행을 막지 않는
    권고 위반은 ``lints``로 돌려준다. source 확인은 존재 여부(stat)뿐이며 내용은
    읽지 않는다.
    """

    loaded = _load_plan(plan)
    lints: list[dict[str, Any]] = []

    for step in loaded.steps:
        spec = PLAN_OPS.get(step.op)
        if spec is None:
            raise PlanValidationError(
                f"미지 op '{step.op}'입니다.",
                context={"stepId": step.id, "op": step.op},
                suggestion=f"v1 op 어휘: {', '.join(sorted(PLAN_OPS))}",
            )
        keys = set(step.args)
        unknown = sorted(keys - spec.allowed)
        if unknown:
            raise PlanValidationError(
                f"op '{step.op}'가 받지 않는 인자: {', '.join(unknown)}",
                context={"stepId": step.id, "unknownArgs": unknown},
                suggestion=f"허용 인자: {', '.join(sorted(spec.allowed)) or '(없음)'}",
            )
        missing = sorted(spec.required - keys)
        if missing:
            raise PlanValidationError(
                f"op '{step.op}'의 필수 인자 누락: {', '.join(missing)}",
                context={"stepId": step.id, "missingArgs": missing},
            )
        for key in keys & _LIST_ARGS:
            value = step.args[key]
            if not isinstance(value, (list, tuple)) or not value:
                raise PlanValidationError(
                    f"인자 '{key}'는 비어 있지 않은 배열이어야 합니다.",
                    context={"stepId": step.id, "arg": key},
                )
        if step.op == "apply_table_ops":
            lint = _lint_delete_table_order(step.id, step.args.get("ops"))
            if lint:
                lints.append(lint)

    source = Path(loaded.source)
    if not source.is_file():
        raise PlanValidationError(
            f"source가 존재하지 않습니다: {source}",
            context={"source": str(source)},
        )
    output_parent = Path(loaded.output).parent
    if not output_parent.is_dir():
        raise PlanValidationError(
            f"output의 부모 디렉터리가 존재하지 않습니다: {output_parent}",
            context={"output": loaded.output},
            suggestion="원자 쓰기는 output과 같은 디렉터리에 임시 파일을 만듭니다.",
        )
    if Path(loaded.output).resolve() == source.resolve():
        lints.append(
            {
                "stepId": None,
                "code": "in-place-output",
                "message": "output이 source와 같아 in-place 편집입니다(원자 교체로 안전).",
            }
        )
    return PlanValidation(plan=loaded, lints=tuple(lints))
