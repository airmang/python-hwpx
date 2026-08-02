# SPDX-License-Identifier: Apache-2.0
"""``hwpx.edit-plan/v1`` / ``hwpx.plan-report/v1`` 데이터 모델.

계획(plan)은 기존 바이트-스플라이스 편집 op 어휘를 선언적으로 합성하는 JSON
1파일이다. 실행 의미론(정적 선검증 → 인메모리 체이닝 → 단 1회 원자 쓰기)은
:mod:`hwpx.plan._execute`가, op 어휘와 인자 검증은 :mod:`hwpx.plan._validate`가
소유한다. 여기는 형태와 직렬화만 있다.

모든 모델은 하우스 관례를 따른다: frozen dataclass, ``ok`` 프로퍼티, camelCase
``to_dict()``, 측정하지 않은 값은 조작 없이 ``None``/``not_performed``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import HwpxError
from ..mutation_report import MutationReport, project_byte_splice

EDIT_PLAN_SCHEMA = "hwpx.edit-plan/v1"
PLAN_REPORT_SCHEMA = "hwpx.plan-report/v1"

_ALLOWED_PLAN_KEYS = {"schemaVersion", "source", "output", "steps", "journalPath"}
_ALLOWED_STEP_KEYS = {"id", "op", "args"}


class PlanValidationError(HwpxError):
    """계획이 실행 자격을 얻지 못했다 — 어떤 파일도 읽거나 쓰기 전에 거부된다.

    미지 필드·중복 id·미지 op·인자 형상 위반 등 구조적 결함 전부가 이 예외로
    수렴한다(fail-closed, 무음 유실 금지). ``context``에 위반 지점이 실린다.
    """

    default_code = "plan-invalid"


def _require_str(value: Any, *, key: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(
            f"'{key}'는 비어 있지 않은 문자열이어야 합니다.",
            context={"key": key, "where": where, "got": repr(value)},
        )
    return value


@dataclass(frozen=True)
class PlanStep:
    """계획의 한 step — 기존 편집 op 하나를 이름 그대로 지시한다."""

    id: str
    op: str
    args: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "op": self.op, "args": dict(self.args)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, index: int) -> "PlanStep":
        if not isinstance(raw, Mapping):
            raise PlanValidationError(
                "step은 객체여야 합니다.",
                context={"stepIndex": index, "got": type(raw).__name__},
            )
        unknown = sorted(set(raw) - _ALLOWED_STEP_KEYS)
        if unknown:
            raise PlanValidationError(
                f"step에 미지 필드가 있습니다: {', '.join(unknown)}",
                context={"stepIndex": index, "unknownKeys": unknown},
                suggestion="허용 필드는 id·op·args뿐입니다.",
            )
        step_id = _require_str(raw.get("id"), key="id", where=f"steps[{index}]")
        op = _require_str(raw.get("op"), key="op", where=f"steps[{index}]")
        args = raw.get("args", {})
        if not isinstance(args, Mapping):
            raise PlanValidationError(
                "step 'args'는 객체여야 합니다.",
                context={"stepId": step_id, "got": type(args).__name__},
            )
        return cls(id=step_id, op=op, args=dict(args))


@dataclass(frozen=True)
class EditPlan:
    """선언적 편집 계획 — ``hwpx.edit-plan/v1``."""

    source: str
    output: str
    steps: tuple[PlanStep, ...]
    journal_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schemaVersion": EDIT_PLAN_SCHEMA,
            "source": self.source,
            "output": self.output,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.journal_path is not None:
            out["journalPath"] = self.journal_path
        return out

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EditPlan":
        if not isinstance(raw, Mapping):
            raise PlanValidationError(
                "계획은 객체여야 합니다.", context={"got": type(raw).__name__}
            )
        unknown = sorted(set(raw) - _ALLOWED_PLAN_KEYS)
        if unknown:
            raise PlanValidationError(
                f"계획에 미지 필드가 있습니다: {', '.join(unknown)}",
                context={"unknownKeys": unknown},
                suggestion=(
                    "허용 필드는 schemaVersion·source·output·steps·journalPath"
                    "뿐입니다. 오타나 미래 스키마 필드는 무음 유실 대신 거부됩니다."
                ),
            )
        schema = raw.get("schemaVersion")
        if schema != EDIT_PLAN_SCHEMA:
            raise PlanValidationError(
                f"schemaVersion이 '{EDIT_PLAN_SCHEMA}'가 아닙니다.",
                context={"got": schema},
            )
        source = _require_str(raw.get("source"), key="source", where="plan")
        output = _require_str(raw.get("output"), key="output", where="plan")
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, (list, tuple)) or not raw_steps:
            raise PlanValidationError(
                "steps는 비어 있지 않은 배열이어야 합니다.",
                context={"got": type(raw_steps).__name__},
            )
        steps = tuple(
            PlanStep.from_dict(item, index=i) for i, item in enumerate(raw_steps)
        )
        seen: set[str] = set()
        for step in steps:
            if step.id in seen:
                raise PlanValidationError(
                    f"step id '{step.id}'가 중복됩니다.",
                    context={"stepId": step.id},
                )
            seen.add(step.id)
        journal = raw.get("journalPath")
        if journal is not None:
            journal = _require_str(journal, key="journalPath", where="plan")
        return cls(source=source, output=output, steps=steps, journal_path=journal)


@dataclass(frozen=True)
class PlanValidation:
    """정적 선검증 결과 — 통과한 계획과 비치명 린트 목록.

    치명 결함은 :class:`PlanValidationError`로 이미 던져졌다. ``lints``는 실행을
    막지 않는 경고(예: ``delete_table`` 역순 위반 권고)다.
    """

    plan: EditPlan
    lints: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"plan": self.plan.to_dict(), "lints": [dict(l) for l in self.lints]}


@dataclass(frozen=True)
class StepRecord:
    """실행된(또는 실패한) step 하나의 기록."""

    step_id: str
    op: str
    status: str  # "applied" | "would_apply" | "failed"
    started_at: str
    finished_at: str
    input_sha256: str
    output_sha256: str | None
    report: MutationReport | None
    detail: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("applied", "would_apply") and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "op": self.op,
            "status": self.status,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "inputSha256": self.input_sha256,
            "outputSha256": self.output_sha256,
            "report": None if self.report is None else self.report.to_dict(),
            "detail": dict(self.detail),
            "error": None if self.error is None else dict(self.error),
        }


@dataclass(frozen=True)
class PlanReport:
    """계획 실행 집계 리포트 — ``hwpx.plan-report/v1``.

    ``aggregate``는 원본→최종 바이트의 **실측** ``hwpx.mutation-report/v1``
    사영이다(step 합성 밖의 변경은 ``unexpected``로 드러난다). 실패 시
    ``aggregate=None``이고 실패 지점은 ``failed_step_id``와 해당
    :class:`StepRecord`의 ``error``에 있다 — 그때 output·source는 바이트
    불변이다(쓰기 자체가 일어나지 않음).
    """

    plan: EditPlan
    executed: bool
    dry_run: bool
    steps: tuple[StepRecord, ...]
    aggregate: MutationReport | None
    lints: tuple[dict[str, Any], ...] = ()
    failed_step_id: str | None = None
    output_path: str | None = None
    journal_path: str | None = None
    schema_version: str = field(init=False, default=PLAN_REPORT_SCHEMA)

    @property
    def ok(self) -> bool:
        return (
            self.failed_step_id is None
            and self.aggregate is not None
            and self.aggregate.ok
            and all(step.ok for step in self.steps)
        )

    @property
    def preservation_floor(self) -> str | None:
        """v1 op 어휘는 전부 바이트-스플라이스라 성공 시 플로어는 ``patch``다.

        DOM 브리지(v1.1)가 들어오면 step 등급의 min으로 일반화된다.
        """

        return "patch" if self.aggregate is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "ok": self.ok,
            "executed": self.executed,
            "dryRun": self.dry_run,
            "plan": self.plan.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "aggregate": None if self.aggregate is None else self.aggregate.to_dict(),
            "preservationFloor": self.preservation_floor,
            "lints": [dict(l) for l in self.lints],
            "failedStepId": self.failed_step_id,
            "outputPath": self.output_path,
            "journalPath": self.journal_path,
        }

    def as_mutation_report(self) -> MutationReport:
        """집계를 단일 ``hwpx.mutation-report/v1``로 낮춘다(결과모델 통일 관례).

        실패로 ``aggregate``가 없으면 정직 degraded 사영을 돌려준다 —
        아무것도 쓰이지 않았으므로 변경 part 없음·검증 ``not_performed``.
        """

        if self.aggregate is not None:
            return self.aggregate
        return project_byte_splice(
            data=b"",
            changed_part_names=(),
            byte_identical=True,
            open_safety=None,
        )
