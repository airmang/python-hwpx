# SPDX-License-Identifier: Apache-2.0
"""계획 실행기 — 인메모리 체이닝, 실패 시 무접촉, 성공 시 단 1회 원자 쓰기.

원자성 계약: output은 전 step 성공 + 최종 open-safety 검증 통과
후 단 한 번의 ``os.replace``로만 쓰인다. 그 전 어떤 실패에서도 output과 source는
바이트 불변이다(지정된 journalPath 제외 — 저널은 실패 시에도 진단용으로 남는
유일한 쓰기 표면이며, 문서 파일이 아니다).

각 step은 기존 op를 ``output_path=None``으로 호출한다 — 바이트-스플라이스
계열의 ``publish="always"`` 함정(게이트 실패·전 op 스킵이어도 파일을 쓰는 동작,
patch.py) 때문에 쓰기는 실행기가 소유한다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .. import body_patch, patch, table_patch
from ..mutation_report import MutationReport, project_byte_splice
from ..tools.package_validator import validate_editor_open_safety
from ..quality.save_pipeline import write_bytes_atomically
from ._model import EditPlan, PlanReport, StepRecord
from ._validate import validate_edit_plan

# 각 op를 (입력 바이트, args) -> 결과객체로 부르는 어댑터. output_path는 절대
# 전달하지 않는다(모듈 docstring). 키 집합은 PLAN_OPS와 정확히 일치해야 하며
# 드리프트 가드 테스트가 이를 강제한다.
_DISPATCH: dict[str, Callable[[bytes, Mapping[str, Any]], Any]] = {
    "paragraph_patch": lambda data, args: patch.paragraph_patch(
        data, args["patches"]
    ),
    "fill_cells": lambda data, args: table_patch.fill_cells(
        data,
        args["cells"],
        fit_max_lines=args.get("fit_max_lines"),
        min_font_pt=float(args.get("min_font_pt", 8.0)),
    ),
    "apply_table_ops": lambda data, args: table_patch.apply_table_ops(
        data, args["ops"]
    ),
    "apply_body_ops": lambda data, args: body_patch.apply_body_ops(
        data, args["ops"]
    ),
    "recolor_runs_by_color": lambda data, args: body_patch.recolor_runs_by_color(
        data, args["from_hexes"], args["to_color"]
    ),
    "strip_runs_by_color": lambda data, args: body_patch.strip_runs_by_color(
        data, args["hex_colors"]
    ),
    "strip_trailing_table_captions": lambda data, args: (
        table_patch.strip_trailing_table_captions(data)
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _result_detail(result: Any) -> dict[str, Any]:
    """결과객체의 진단 요약 — 전체 to_dict()는 무겁고(data 포함 아님이지만
    applied 전문 등), 저널·리포트에는 판정 근거만 싣는다."""

    detail: dict[str, Any] = {
        "ok": bool(result.ok),
        "changedParts": list(result.changed_parts),
        "byteIdentical": bool(result.byte_identical),
    }
    applied = getattr(result, "applied", None)
    if applied is not None:
        detail["appliedCount"] = len(applied)
    skipped = getattr(result, "skipped", ())
    detail["skipped"] = [
        item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in skipped
    ]
    transcript = getattr(result, "transcript", ())
    if transcript:
        detail["transcript"] = [dict(t) for t in transcript]
    open_safety = getattr(result, "open_safety", None)
    if isinstance(open_safety, Mapping):
        detail["openSafetyOk"] = open_safety.get("ok")
        summary = open_safety.get("summary")
        if summary:
            detail["openSafetySummary"] = summary
    return detail


class _Journal:
    """JSONL 저널 — journalPath 지정 시에만 디스크에 남는다."""

    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self.entries: list[dict[str, Any]] = []

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def apply_edit_plan(
    plan: EditPlan | Mapping[str, Any] | str | Path,
    *,
    dry_run: bool = False,
    journal_path: str | Path | None = None,
) -> PlanReport:
    """편집 계획을 검증하고 실행한다. 반환은 ``hwpx.plan-report/v1``.

    실행 실패는 예외가 아니라 ``ok=False`` 리포트로 돌아온다(실패 step의
    ``error``·``failedStepId``에 지점이 실린다) — 그때 어떤 문서 파일도 쓰이지
    않았다. 계획 자체가 무자격이면 :class:`~hwpx.plan.PlanValidationError`가
    파일 접촉 전에 던져진다.

    ``dry_run=True``는 동일한 체이닝을 전부 실행하되(검증·거부 실동작) 최종
    쓰기만 생략한다 — per-step "미리보기 전용" 경로가 따로 없으므로 미리보기와
    실제 실행의 결과가 정의상 동일하다.
    """

    validation = validate_edit_plan(plan)
    loaded = validation.plan
    effective_journal = (
        str(journal_path) if journal_path is not None else loaded.journal_path
    )
    journal = _Journal(effective_journal)

    source_path = Path(loaded.source)
    original = source_path.read_bytes()
    journal.append(
        {
            "event": "plan-start",
            "at": _now(),
            "source": str(source_path),
            "output": loaded.output,
            "dryRun": dry_run,
            "sourceSha256": _sha256(original),
            "stepCount": len(loaded.steps),
        }
    )

    records: list[StepRecord] = []
    current = original
    changed_union: set[str] = set()
    failed_step_id: str | None = None

    for step in loaded.steps:
        started = _now()
        input_sha = _sha256(current)
        try:
            result = _DISPATCH[step.op](current, step.args)
        except Exception as exc:  # 실행 실패 = 무접촉 중단 (fail-closed)
            error: dict[str, Any] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            to_dict = getattr(exc, "to_dict", None)
            if callable(to_dict):
                error["structured"] = to_dict()
            record = StepRecord(
                step_id=step.id,
                op=step.op,
                status="failed",
                started_at=started,
                finished_at=_now(),
                input_sha256=input_sha,
                output_sha256=None,
                report=None,
                detail={},
                error=error,
            )
            records.append(record)
            journal.append({"event": "step", "at": record.finished_at, **record.to_dict()})
            failed_step_id = step.id
            break

        detail = _result_detail(result)
        report = result.as_mutation_report(source=current)
        if not result.ok:
            record = StepRecord(
                step_id=step.id,
                op=step.op,
                status="failed",
                started_at=started,
                finished_at=_now(),
                input_sha256=input_sha,
                output_sha256=None,
                report=report,
                detail=detail,
                error={
                    "type": "StepRefused",
                    "message": (
                        "op이 스킵/불안전을 보고해 계획을 중단합니다 "
                        "(all-or-nothing — 부분 적용 없음)."
                    ),
                },
            )
            records.append(record)
            journal.append({"event": "step", "at": record.finished_at, **record.to_dict()})
            failed_step_id = step.id
            break

        current = result.data
        changed_union.update(result.changed_parts)
        record = StepRecord(
            step_id=step.id,
            op=step.op,
            status="would_apply" if dry_run else "applied",
            started_at=started,
            finished_at=_now(),
            input_sha256=input_sha,
            output_sha256=_sha256(current),
            report=report,
            detail=detail,
        )
        records.append(record)
        journal.append({"event": "step", "at": record.finished_at, **record.to_dict()})

    aggregate: MutationReport | None = None
    executed = False
    output_path: str | None = None

    if failed_step_id is None:
        final_safety = validate_editor_open_safety(current).to_dict()
        aggregate = project_byte_splice(
            data=current,
            changed_part_names=tuple(sorted(changed_union)),
            byte_identical=current == original,
            open_safety=final_safety,
            source=original,
        )
        if not bool(final_safety.get("ok")):
            # 실패 step은 없지만 최종 산출물이 open-safety를 통과하지 못했다 —
            # aggregate.verification이 failed를 실어 ok=False가 되고, 쓰기는
            # 일어나지 않는다. step에 누명을 씌우지 않는다.
            journal.append(
                {
                    "event": "final-verification-failed",
                    "at": _now(),
                    "openSafety": {
                        "ok": final_safety.get("ok"),
                        "summary": final_safety.get("summary"),
                    },
                }
            )
        elif not dry_run:
            write_bytes_atomically(loaded.output, current)
            executed = True
            output_path = loaded.output

    journal.append(
        {
            "event": "plan-end",
            "at": _now(),
            "executed": executed,
            "dryRun": dry_run,
            "failedStepId": failed_step_id,
            "finalVerificationOk": (
                bool(aggregate.ok) if aggregate is not None else None
            ),
            "finalSha256": _sha256(current) if failed_step_id is None else None,
        }
    )

    return PlanReport(
        plan=loaded,
        executed=executed,
        dry_run=dry_run,
        steps=tuple(records),
        aggregate=aggregate,
        lints=validation.lints,
        failed_step_id=failed_step_id,
        output_path=output_path,
        journal_path=effective_journal,
    )
