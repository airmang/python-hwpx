# SPDX-License-Identifier: Apache-2.0
"""hwpx.plan — 계획 검증·원자 실행 계약 테스트 (specs/059 §2~§5).

핵심 수락 기준: 중간 step 고의 실패 시 output·source가 **바이트 비교**로
무변경임을 증명한다(§4 원자성 계약 문장).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.plan import (
    EDIT_PLAN_SCHEMA,
    PLAN_OPS,
    EditPlan,
    PlanValidationError,
    apply_edit_plan,
    edit_plan_json_schema,
    validate_edit_plan,
)


@pytest.fixture(scope="module")
def base_doc(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """문단 2개 + 2×2 표 하나를 가진 실제 저작 문서."""

    path = tmp_path_factory.mktemp("plan-base") / "base.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("원본 첫 문단입니다.")
    doc.add_paragraph("두 번째 문단은 그대로 둡니다.")
    doc.add_table(2, 2)
    doc.save_to_path(path)
    doc.close()
    return path


def _plan(source: Path, output: Path, steps: list[dict], **extra) -> dict:
    return {
        "schemaVersion": EDIT_PLAN_SCHEMA,
        "source": str(source),
        "output": str(output),
        "steps": steps,
        **extra,
    }


def _section_bytes(path: Path) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return b"".join(
            zf.read(n) for n in sorted(zf.namelist()) if n.endswith("section0.xml")
        )


# ---------------------------------------------------------------- validation

def _expect_invalid(plan_dict: dict, *, fragment: str) -> PlanValidationError:
    with pytest.raises(PlanValidationError) as excinfo:
        validate_edit_plan(plan_dict)
    err = excinfo.value
    assert err.code == "plan-invalid"
    assert fragment in err.message
    return err


def test_validate_rejects_unknown_fields_and_ops(base_doc: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.hwpx"
    good_step = {"id": "s1", "op": "strip_trailing_table_captions", "args": {}}

    _expect_invalid(
        {**_plan(base_doc, out, [good_step]), "mode": "patch"}, fragment="미지 필드"
    )
    _expect_invalid(
        _plan(base_doc, out, [{**good_step, "when": "always"}]), fragment="미지 필드"
    )
    _expect_invalid(
        _plan(base_doc, out, [{"id": "s1", "op": "explode", "args": {}}]),
        fragment="미지 op",
    )
    _expect_invalid(
        _plan(base_doc, out, [{"id": "s1", "op": "fill_cells", "args": {"cellz": []}}]),
        fragment="받지 않는 인자",
    )
    _expect_invalid(
        _plan(base_doc, out, [{"id": "s1", "op": "fill_cells", "args": {}}]),
        fragment="필수 인자",
    )
    _expect_invalid(
        _plan(
            base_doc,
            out,
            [{"id": "s1", "op": "fill_cells", "args": {"cells": [], "why": 1}}],
        ),
        fragment="받지 않는 인자",
    )
    _expect_invalid(_plan(base_doc, out, [good_step, dict(good_step)]), fragment="중복")
    _expect_invalid(_plan(base_doc, out, []), fragment="steps")
    _expect_invalid(
        {**_plan(base_doc, out, [good_step]), "schemaVersion": "hwpx.edit-plan/v9"},
        fragment="schemaVersion",
    )


def test_validate_checks_paths_without_reading_documents(tmp_path: Path) -> None:
    step = {"id": "s1", "op": "strip_trailing_table_captions", "args": {}}
    _expect_invalid(
        _plan(tmp_path / "missing.hwpx", tmp_path / "out.hwpx", [step]),
        fragment="source가 존재하지",
    )
    src = tmp_path / "present.hwpx"
    src.write_bytes(b"not even a zip")  # 검증은 stat뿐 — 내용을 읽지 않는다
    validation = validate_edit_plan(
        _plan(src, tmp_path / "out.hwpx", [step])
    )
    assert validation.plan.steps[0].op == "strip_trailing_table_captions"
    _expect_invalid(
        _plan(src, tmp_path / "no-such-dir" / "out.hwpx", [step]),
        fragment="부모 디렉터리",
    )


def test_delete_table_order_lint(base_doc: Path, tmp_path: Path) -> None:
    plan = _plan(
        base_doc,
        tmp_path / "out.hwpx",
        [
            {
                "id": "s1",
                "op": "apply_table_ops",
                "args": {
                    "ops": [
                        {"op": "delete_table", "table_index": 0},
                        {"op": "delete_table", "table_index": 2},
                    ]
                },
            }
        ],
    )
    validation = validate_edit_plan(plan)
    assert [l["code"] for l in validation.lints] == ["delete-table-order"]


# ---------------------------------------------------------------- execution

def test_happy_path_executes_and_reports_measured_aggregate(
    base_doc: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.hwpx"
    journal = tmp_path / "plan.journal.jsonl"
    plan = _plan(
        base_doc,
        out,
        [
            {
                "id": "edit-text",
                "op": "apply_body_ops",
                "args": {
                    "ops": [
                        {"op": "replace_text", "find": "원본 첫", "replace": "계획 실행", "count": 1}
                    ]
                },
            },
            {
                "id": "fill-table",
                "op": "fill_cells",
                "args": {"cells": [{"table_index": 0, "row": 0, "col": 0, "text": "채움값"}]},
            },
        ],
        journalPath=str(journal),
    )

    report = apply_edit_plan(plan)

    assert report.ok and report.executed and not report.dry_run
    assert report.failed_step_id is None
    assert report.output_path == str(out)
    assert [s.status for s in report.steps] == ["applied", "applied"]
    # step 리포트는 입력 바이트를 스레딩해 실측된다(범위 존재).
    for step in report.steps:
        assert step.report is not None
        assert all(part.ranges for part in step.report.changed_parts)
    # 집계는 원본→최종 실측: 변경 part가 있고 검증 3값이 passed다.
    agg = report.aggregate
    assert agg is not None and agg.ok and agg.changed_parts
    assert agg.verification.package == "passed"
    assert agg.verification.reopen == "passed"
    assert agg.verification.visual == "not_performed"
    assert report.preservation_floor == "patch"
    # 산출물에 두 편집이 실재한다.
    section = _section_bytes(out)
    assert "계획 실행".encode() in section
    assert "채움값".encode() in section
    # 저널: plan-start / step×2 / plan-end 이벤트가 JSONL로 남는다.
    events = [json.loads(line)["event"] for line in journal.read_text().splitlines()]
    assert events == ["plan-start", "step", "step", "plan-end"]


def test_dry_run_touches_no_files(base_doc: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.hwpx"
    before = base_doc.read_bytes()
    plan = _plan(
        base_doc,
        out,
        [
            {
                "id": "edit-text",
                "op": "apply_body_ops",
                "args": {"ops": [{"op": "replace_text", "find": "두 번째", "replace": "둘째", "count": 1}]},
            }
        ],
    )
    report = apply_edit_plan(plan, dry_run=True)
    assert report.ok and not report.executed and report.dry_run
    assert [s.status for s in report.steps] == ["would_apply"]
    assert report.aggregate is not None and report.aggregate.changed_parts
    assert not out.exists()
    assert base_doc.read_bytes() == before


def test_mid_step_failure_leaves_output_and_source_byte_identical(
    base_doc: Path, tmp_path: Path
) -> None:
    """수락 기준(§4): 중간 op 고의 실패 → 대상 파일 무변경 바이트 증명."""

    out = tmp_path / "out.hwpx"
    before = base_doc.read_bytes()
    plan = _plan(
        base_doc,
        out,
        [
            {
                "id": "s1",
                "op": "apply_body_ops",
                "args": {"ops": [{"op": "replace_text", "find": "원본", "replace": "변경", "count": 1}]},
            },
            {
                "id": "s2",
                "op": "fill_cells",
                "args": {"cells": [{"table_index": 99, "row": 0, "col": 0, "text": "실패"}]},
            },
        ],
    )
    report = apply_edit_plan(plan)
    assert not report.ok and not report.executed
    assert report.failed_step_id == "s2"
    assert report.steps[0].status == "applied" and report.steps[1].status == "failed"
    assert report.steps[1].error is not None
    assert report.aggregate is None
    assert not out.exists()
    assert base_doc.read_bytes() == before


def test_in_place_failure_keeps_source_bytes(base_doc: Path, tmp_path: Path) -> None:
    src = tmp_path / "inplace.hwpx"
    src.write_bytes(base_doc.read_bytes())
    before = src.read_bytes()
    plan = _plan(
        src,
        src,
        [
            {
                "id": "s1",
                "op": "fill_cells",
                "args": {"cells": [{"table_index": 99, "row": 0, "col": 0, "text": "실패"}]},
            }
        ],
    )
    report = apply_edit_plan(plan)
    assert not report.ok and not report.executed
    assert src.read_bytes() == before


def test_in_place_success_replaces_atomically(base_doc: Path, tmp_path: Path) -> None:
    src = tmp_path / "inplace.hwpx"
    src.write_bytes(base_doc.read_bytes())
    plan = _plan(
        src,
        src,
        [
            {
                "id": "s1",
                "op": "apply_body_ops",
                "args": {"ops": [{"op": "replace_text", "find": "원본", "replace": "제자리", "count": 1}]},
            }
        ],
    )
    report = apply_edit_plan(plan)
    assert report.ok and report.executed
    assert any(l["code"] == "in-place-output" for l in report.lints)
    assert "제자리".encode() in _section_bytes(src)
    assert not list(tmp_path.glob("*.hwpx.tmp"))  # 임시 파일 잔존 없음


def test_failed_run_journal_still_written(base_doc: Path, tmp_path: Path) -> None:
    journal = tmp_path / "fail.journal.jsonl"
    plan = _plan(
        base_doc,
        tmp_path / "out.hwpx",
        [
            {
                "id": "s1",
                "op": "fill_cells",
                "args": {"cells": [{"table_index": 99, "row": 0, "col": 0, "text": "x"}]},
            }
        ],
        journalPath=str(journal),
    )
    report = apply_edit_plan(plan)
    assert not report.ok
    events = [json.loads(line)["event"] for line in journal.read_text().splitlines()]
    assert events == ["plan-start", "step", "plan-end"]
    assert json.loads(journal.read_text().splitlines()[1])["status"] == "failed"


def test_report_projection_and_roundtrip(base_doc: Path, tmp_path: Path) -> None:
    plan_dict = _plan(
        base_doc,
        tmp_path / "out.hwpx",
        [{"id": "s1", "op": "strip_trailing_table_captions", "args": {}}],
    )
    loaded = EditPlan.from_dict(plan_dict)
    assert EditPlan.from_dict(loaded.to_dict()) == loaded

    report = apply_edit_plan(loaded, dry_run=True)
    assert report.as_mutation_report() is report.aggregate
    payload = report.to_dict()
    assert payload["schemaVersion"] == "hwpx.plan-report/v1"
    assert payload["aggregate"]["schemaVersion"] == "hwpx.mutation-report/v1"

    # 실패 리포트의 사영은 정직 degraded(변경 없음·not_performed)다.
    failing = apply_edit_plan(
        _plan(
            base_doc,
            tmp_path / "out2.hwpx",
            [
                {
                    "id": "s1",
                    "op": "fill_cells",
                    "args": {"cells": [{"table_index": 99, "row": 0, "col": 0, "text": "x"}]},
                }
            ],
        )
    )
    degraded = failing.as_mutation_report()
    assert degraded.changed_parts == ()
    assert degraded.verification.package == "not_performed"


def test_schema_enum_matches_op_registry() -> None:
    schema = edit_plan_json_schema()
    enum = schema["properties"]["steps"]["items"]["properties"]["op"]["enum"]
    assert enum == sorted(PLAN_OPS)
