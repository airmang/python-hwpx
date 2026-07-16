# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.agent import (
    AGENT_BATCH_SCHEMA,
    MIXED_FORM_COMPILED_PLAN_SCHEMA,
    MIXED_FORM_LOCATOR_KINDS,
    MIXED_FORM_PLAN_SCHEMA,
    MIXED_FORM_REQUEST_SCHEMA,
    AgentContractError,
    HwpxAgentDocument,
    apply_mixed_form_fill,
    apply_mixed_form_plan,
    mixed_form_json_schemas,
    plan_mixed_form_fill,
    validate_mixed_form_plan,
    validate_mixed_form_request,
)
from hwpx.agent import form_plan as mixed_form_module
from hwpx.agent.catalog import agent_json_schemas
from hwpx.oxml.namespaces import HP
from hwpx.quality import SavePipeline
from hwpx.visual import NullOracle


def _append_native_field(
    paragraph: Any,
    *,
    field_id: str,
    name: str,
    value: str,
) -> None:
    begin_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    begin_control = begin_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
    begin_control.append(
        begin_control.makeelement(
            f"{HP}fieldBegin",
            {
                "id": field_id,
                "fieldName": name,
                "type": "FORM",
                "editable": "true",
            },
        )
    )
    begin_run.append(begin_control)
    paragraph.element.append(begin_run)

    value_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    text = value_run.makeelement(f"{HP}t", {})
    text.text = value
    value_run.append(text)
    paragraph.element.append(value_run)

    end_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    end_control = end_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
    end_control.append(
        end_control.makeelement(
            f"{HP}fieldEnd",
            {"beginIDRef": field_id, "fieldid": field_id},
        )
    )
    end_run.append(end_control)
    paragraph.element.append(end_run)
    paragraph.section.mark_dirty()


def _write_mixed_form_fixture(
    path: Path,
    *,
    duplicate_body_anchor: bool = False,
    split_body_anchor: bool = False,
    duplicate_field_name: bool = False,
    duplicate_table_anchor: bool = False,
) -> None:
    """Build a one-page Korean form exercising all four public locators."""

    with HwpxDocument.new() as document:
        title = document.sections[0].paragraphs[0]
        title.element.set("id", "1001")
        title.text = "2026학년도 동아리 활동 신청서"

        heading = document.add_paragraph("1. 신청 정보")
        heading.element.set("id", "1002")
        table = heading.add_table(3, 2)
        table.element.set("id", "2001")
        table.rows[0].cells[0].text = "구분"
        table.rows[0].cells[1].text = "미입력"
        table.rows[1].cells[0].text = "동아리명"
        table.rows[2].cells[0].text = "활동 장소"
        table.rows[2].cells[1].text = "미정"
        # The label at logical (1, 0) points right into a cell physically
        # anchored at (0, 1), proving merge-aware physical normalization.
        table.merge_cells(0, 1, 1, 1)

        if duplicate_table_anchor:
            duplicate_heading = document.add_paragraph("2. 신청 정보")
            duplicate_heading.element.set("id", "1006")
            duplicate = duplicate_heading.add_table(2, 2)
            duplicate.element.set("id", "2002")
            duplicate.rows[0].cells[0].text = "구분"
            duplicate.rows[0].cells[1].text = "내용"
            duplicate.rows[1].cells[0].text = "동아리명"
            duplicate.rows[1].cells[1].text = "미입력"

        if split_body_anchor:
            purpose = document.add_paragraph("신청 목적: {{신청")
            purpose.add_run("목적}}")
        else:
            purpose = document.add_paragraph("신청 목적: {{신청목적}}")
        purpose.element.set("id", "1003")
        if duplicate_body_anchor:
            duplicate_purpose = document.add_paragraph("추가 목적: {{신청목적}}")
            duplicate_purpose.element.set("id", "1007")

        teacher = document.add_paragraph("담당 교사: 미정")
        teacher.element.set("id", "1004")

        representative = document.add_paragraph("대표 학생: ")
        representative.element.set("id", "1005")
        _append_native_field(
            representative,
            field_id="3001",
            name="대표학생",
            value="미입력",
        )
        if duplicate_field_name:
            second_representative = document.add_paragraph("부대표 학생: ")
            second_representative.element.set("id", "1008")
            _append_native_field(
                second_representative,
                field_id="3002",
                name="대표학생",
                value="미입력",
            )
        document.save_to_path(path)


def _canonical_teacher_path(source: Path) -> str:
    with HwpxAgentDocument.open(source) as agent:
        return next(
            record.path
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") == "1004"
        )


def _public_plan(
    source: Path,
    output: Path,
    *,
    operations: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
    idempotency_key: str | None = "mixed-form-test",
) -> dict[str, Any]:
    if operations is None:
        operations = [
            {
                "operationId": "native",
                "target": {"kind": "nativeField", "name": "대표학생"},
                "value": "홍길동",
            },
            {
                "operationId": "label",
                "target": {
                    "kind": "labelCell",
                    "sectionPath": "/section[1]",
                    "tableAnchor": "신청 정보",
                    "cellAnchor": {"label": "동아리명", "direction": "right"},
                },
                "value": "인공지능 연구회",
            },
            {
                "operationId": "path",
                "target": {
                    "kind": "canonicalPath",
                    "path": _canonical_teacher_path(source),
                },
                "value": "담당 교사: 김교사",
            },
            {
                "operationId": "body",
                "target": {
                    "kind": "bodyAnchor",
                    "sectionPath": "/section[1]",
                    "anchor": "{{신청목적}}",
                    "expectedCount": 1,
                },
                "value": "교내 문제 해결",
            },
        ]
    return {
        "schemaVersion": MIXED_FORM_PLAN_SCHEMA,
        "source": str(source),
        "output": str(output),
        "expectedRevision": None,
        "idempotencyKey": idempotency_key,
        "dryRun": dry_run,
        "overwrite": True,
        "quality": "transparent",
        "verificationRequirements": [
            "package",
            "reopen",
            "openSafety",
            "semanticDiff",
            "bytePreservation",
        ],
        "operations": operations,
    }


def _single_operation_plan(
    source: Path,
    output: Path,
    target: dict[str, Any],
    *,
    value: str = "채움값",
) -> dict[str, Any]:
    return _public_plan(
        source,
        output,
        operations=[{"operationId": "only", "target": target, "value": value}],
        idempotency_key=None,
    )


def _member_payloads(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        return {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if not info.is_dir()
        }


def _rehash_compiled_plan(payload: dict[str, Any]) -> None:
    material = copy.deepcopy(payload)
    material["planHash"] = None
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["planHash"] = "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_three_schema_roles_are_strict_shared_and_exam_free() -> None:
    schemas = mixed_form_json_schemas()
    assert set(schemas) == {"plan", "internalRequest", "compiledPlan"}
    assert schemas["plan"]["properties"]["schemaVersion"] == {
        "const": MIXED_FORM_PLAN_SCHEMA
    }
    assert schemas["internalRequest"]["properties"]["schemaVersion"] == {
        "const": MIXED_FORM_REQUEST_SCHEMA
    }
    assert schemas["compiledPlan"]["properties"]["schemaVersion"] == {
        "const": MIXED_FORM_COMPILED_PLAN_SCHEMA
    }

    shared_batch = agent_json_schemas()["batch"]
    embedded_batch = schemas["compiledPlan"]["properties"]["batch"]
    assert embedded_batch["additionalProperties"] is False
    assert embedded_batch["properties"]["commands"]["items"] == shared_batch["properties"][
        "commands"
    ]["items"]
    assert schemas["plan"]["properties"]["quality"] == shared_batch["properties"][
        "quality"
    ]
    assert schemas["internalRequest"]["properties"]["quality"] == shared_batch[
        "properties"
    ]["quality"]
    assert set(MIXED_FORM_LOCATOR_KINDS) == {
        "nativeField",
        "labelCell",
        "canonicalPath",
        "bodyAnchor",
    }
    assert "exam" not in json.dumps(schemas, ensure_ascii=False).casefold()


def test_public_plan_rejects_missing_unknown_and_non_exact_targets(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _write_mixed_form_fixture(source)
    request = _public_plan(source, tmp_path / "output.hwpx")

    unknown = copy.deepcopy(request)
    unknown["unexpected"] = True
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(unknown)
    assert exc.value.code == "invalid_syntax"

    missing = copy.deepcopy(request)
    del missing["operations"][0]["value"]
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(missing)
    assert exc.value.code == "invalid_syntax"

    extra_target = copy.deepcopy(request)
    extra_target["operations"][0]["target"]["index"] = 0
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(extra_target)
    assert exc.value.code == "invalid_syntax"

    wrong_expected_count = copy.deepcopy(request)
    wrong_expected_count["operations"][3]["target"]["expectedCount"] = 2
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(wrong_expected_count)
    assert exc.value.code == "invalid_syntax"

    bad_quality = copy.deepcopy(request)
    bad_quality["quality"] = {"renderCheck": "sometimes"}
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(bad_quality)
    assert exc.value.code == "invalid_syntax"


def test_plan_resolves_all_four_targets_to_one_revision_bound_batch(tmp_path: Path) -> None:
    source = tmp_path / "mixed-anchor-input.hwpx"
    output = tmp_path / "mixed-anchor-output.hwpx"
    _write_mixed_form_fixture(source)
    public_plan = _public_plan(source, output)

    internal = validate_mixed_form_request(public_plan)
    assert internal["schemaVersion"] == MIXED_FORM_REQUEST_SCHEMA
    assert all("locator" in operation for operation in internal["operations"])
    compiled = plan_mixed_form_fill(public_plan)
    payload = compiled.to_dict()

    assert payload["schemaVersion"] == MIXED_FORM_COMPILED_PLAN_SCHEMA
    assert payload["inputRevision"] == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    assert payload["requestHash"].startswith("sha256:")
    assert payload["planHash"].startswith("sha256:")
    assert payload["batch"]["schemaVersion"] == AGENT_BATCH_SCHEMA
    assert payload["batch"]["expectedRevision"] == payload["inputRevision"]
    assert len(payload["batch"]["commands"]) == 4
    assert all("schemaVersion" not in command for command in payload["batch"]["commands"])
    assert [item["locatorKind"] for item in payload["resolutions"]] == [
        "nativeField",
        "labelCell",
        "canonicalPath",
        "bodyAnchor",
    ]
    label = payload["resolutions"][1]
    assert (label["logicalRow"], label["logicalColumn"]) == (1, 1)
    assert (label["physicalRow"], label["physicalColumn"]) == (0, 1)
    assert payload["resolutions"][3]["nodeKind"] == "run"
    assert validate_mixed_form_plan(payload).to_dict() == payload


def test_apply_uses_one_executor_preserves_members_and_reopens(tmp_path: Path) -> None:
    source = tmp_path / "mixed-anchor-input.hwpx"
    output = tmp_path / "mixed-anchor-output.hwpx"
    _write_mixed_form_fixture(source)

    class CountingPipeline(SavePipeline):
        def __init__(self) -> None:
            super().__init__(oracle=NullOracle())
            self.calls = 0

        def run(self, *args: Any, **kwargs: Any):
            self.calls += 1
            return super().run(*args, **kwargs)

    pipeline = CountingPipeline()
    result = apply_mixed_form_fill(_public_plan(source, output), save_pipeline=pipeline)
    assert result.ok, result.to_dict()
    assert result.rolled_back is False
    assert pipeline.calls == 1
    assert output.exists()
    assert validate_editor_open_safety(output).ok
    byte_report = result.verification_report["bytePreservation"]
    assert byte_report["ok"] is True
    assert byte_report["changedMembers"] == ["Contents/section0.xml"]
    assert byte_report["unchangedMemberCount"] > 0

    before = _member_payloads(source)
    after = _member_payloads(output)
    assert set(before) == set(after)
    assert all(
        before[name] == after[name]
        for name in before
        if name != "Contents/section0.xml"
    )

    with HwpxAgentDocument.open(output) as agent:
        field = next(record for record in agent.records if record.kind == "form-field")
        teacher = next(
            record
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") == "1004"
        )
        purpose = next(
            record
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") == "1003"
        )
        merged_cell = next(
            record
            for record in agent.records
            if record.kind == "cell"
            and record.summary.get("row") == 1
            and record.summary.get("column") == 2
        )
        assert field.summary["value"] == "홍길동"
        assert merged_cell.summary["text"] == "인공지능 연구회"
        assert merged_cell.summary["rowSpan"] == 2
        assert teacher.summary["text"] == "담당 교사: 김교사"
        assert purpose.summary["text"] == "신청 목적: 교내 문제 해결"


def test_dry_run_rollback_and_idempotent_replay(tmp_path: Path) -> None:
    source = tmp_path / "mixed-anchor-input.hwpx"
    _write_mixed_form_fixture(source)

    dry_output = tmp_path / "dry-output.hwpx"
    dry_plan = plan_mixed_form_fill(_public_plan(source, dry_output, dry_run=True))
    dry_result = apply_mixed_form_plan(dry_plan)
    assert dry_result.ok and dry_result.dry_run
    assert not dry_output.exists()

    rollback_output = tmp_path / "rollback-output.hwpx"
    rollback_output.write_bytes(b"existing destination")
    rollback_plan = plan_mixed_form_fill(_public_plan(source, rollback_output))

    def fail_third(stage: str, index: int | None) -> None:
        if stage == "before_command" and index == 2:
            raise RuntimeError("injected mixed-form failure")

    failed = apply_mixed_form_plan(rollback_plan, fault_injector=fail_third)
    assert not failed.ok and failed.rolled_back
    assert rollback_output.read_bytes() == b"existing destination"

    replay_output = tmp_path / "replay-output.hwpx"
    replay_plan = plan_mixed_form_fill(
        _public_plan(source, replay_output, idempotency_key="mixed-replay")
    )
    store: dict[str, Any] = {}
    first = apply_mixed_form_plan(replay_plan, idempotency_store=store)
    first_bytes = replay_output.read_bytes()
    replay = apply_mixed_form_plan(replay_plan, idempotency_store=store)
    assert first.ok and replay.ok
    assert replay.verification_report["idempotency"]["replayed"] is True
    assert replay_output.read_bytes() == first_bytes


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "nativeField", "name": "없는필드"},
        {
            "kind": "labelCell",
            "sectionPath": "/section[1]",
            "tableAnchor": "없는표제",
            "cellAnchor": {"label": "동아리명", "direction": "right"},
        },
        {
            "kind": "bodyAnchor",
            "sectionPath": "/section[1]",
            "anchor": "{{없는본문}}",
            "expectedCount": 1,
        },
        {"kind": "canonicalPath", "path": "/section[1]/paragraph[999]"},
    ],
)
def test_zero_candidate_locators_fail_closed(tmp_path: Path, target: dict[str, Any]) -> None:
    source = tmp_path / "input.hwpx"
    _write_mixed_form_fixture(source)
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(_single_operation_plan(source, tmp_path / "out.hwpx", target))
    assert exc.value.code == "not_found"


def test_multiple_candidate_locators_fail_closed(tmp_path: Path) -> None:
    duplicate_field = tmp_path / "duplicate-field.hwpx"
    _write_mixed_form_fixture(duplicate_field, duplicate_field_name=True)
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(
            _single_operation_plan(
                duplicate_field,
                tmp_path / "field-out.hwpx",
                {"kind": "nativeField", "name": "대표학생"},
            )
        )
    assert exc.value.code == "ambiguous_target"

    duplicate_body = tmp_path / "duplicate-body.hwpx"
    _write_mixed_form_fixture(duplicate_body, duplicate_body_anchor=True)
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(
            _single_operation_plan(
                duplicate_body,
                tmp_path / "body-out.hwpx",
                {
                    "kind": "bodyAnchor",
                    "sectionPath": "/section[1]",
                    "anchor": "{{신청목적}}",
                    "expectedCount": 1,
                },
            )
        )
    assert exc.value.code == "ambiguous_target"

    duplicate_table = tmp_path / "duplicate-table.hwpx"
    _write_mixed_form_fixture(duplicate_table, duplicate_table_anchor=True)
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(
            _single_operation_plan(
                duplicate_table,
                tmp_path / "table-out.hwpx",
                {
                    "kind": "labelCell",
                    "sectionPath": "/section[1]",
                    "tableAnchor": "신청 정보",
                    "cellAnchor": {"label": "동아리명", "direction": "right"},
                },
            )
        )
    assert exc.value.code == "ambiguous_target"


def test_body_anchor_crossing_runs_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "split-body-anchor.hwpx"
    _write_mixed_form_fixture(source, split_body_anchor=True)
    request = _single_operation_plan(
        source,
        tmp_path / "out.hwpx",
        {
            "kind": "bodyAnchor",
            "sectionPath": "/section[1]",
            "anchor": "{{신청목적}}",
            "expectedCount": 1,
        },
    )
    with pytest.raises(AgentContractError) as exc:
        plan_mixed_form_fill(request)
    assert exc.value.code == "unsupported_content"
    assert "run boundaries" in str(exc.value)


def test_compiled_plan_hash_rejects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _write_mixed_form_fixture(source)
    compiled = plan_mixed_form_fill(_public_plan(source, tmp_path / "out.hwpx")).to_dict()
    compiled["batch"]["commands"][0]["properties"]["value"] = "변조"
    with pytest.raises(AgentContractError) as exc:
        validate_mixed_form_plan(compiled)
    assert exc.value.code == "verification_failed"

    extra = plan_mixed_form_fill(_public_plan(source, tmp_path / "out2.hwpx")).to_dict()
    extra["unexpected"] = True
    with pytest.raises(AgentContractError) as exc:
        validate_mixed_form_plan(extra)
    assert exc.value.code == "invalid_syntax"


def test_evalplan_and_exam_remain_separate_from_mixed_contract() -> None:
    from hwpx.evalplan_fill import fill_evalplan

    tree = ast.parse(Path(mixed_form_module.__file__).read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any(name == "hwpx.exam" or name.startswith("hwpx.exam.") for name in imported_modules)
    assert "exam" not in MIXED_FORM_LOCATOR_KINDS
    assert "evalplan" not in MIXED_FORM_LOCATOR_KINDS
    assert fill_evalplan.__module__ == "hwpx.evalplan_fill"


@pytest.mark.parametrize("alias_kind", ["exact", "lexical", "symlink", "hardlink"])
def test_planning_rejects_every_source_output_alias(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    source = tmp_path / "source.hwpx"
    _write_mixed_form_fixture(source)
    source_before = source.read_bytes()

    if alias_kind == "exact":
        output = source
    elif alias_kind == "lexical":
        output = tmp_path / "not-created" / ".." / source.name
    else:
        output = tmp_path / f"{alias_kind}.hwpx"
        if alias_kind == "symlink":
            output.symlink_to(source)
        else:
            output.hardlink_to(source)

    with pytest.raises(AgentContractError) as caught:
        plan_mixed_form_fill(_public_plan(source, output))
    assert caught.value.code == "invariant_violation"
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_apply_rechecks_source_output_identity_after_planning(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    _write_mixed_form_fixture(source)
    plan = plan_mixed_form_fill(_public_plan(source, output))
    source_before = source.read_bytes()

    if alias_kind == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)

    with pytest.raises(AgentContractError) as caught:
        apply_mixed_form_plan(plan)
    assert caught.value.code == "invariant_violation"
    assert source.read_bytes() == source_before


def test_mixed_form_cell_label_requires_normalized_exact_equality(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    _write_mixed_form_fixture(source)
    target = {
        "kind": "labelCell",
        "sectionPath": "/section[1]",
        "tableAnchor": "신청 정보",
        "cellAnchor": {"label": "동아리", "direction": "right"},
    }

    with pytest.raises(AgentContractError) as caught:
        plan_mixed_form_fill(_single_operation_plan(source, tmp_path / "out.hwpx", target))
    assert caught.value.code == "not_found"


def test_public_request_hash_participates_in_idempotency_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    _write_mixed_form_fixture(source)

    by_name_request = _public_plan(source, output, idempotency_key="locator-identity")
    by_id_request = copy.deepcopy(by_name_request)
    by_id_request["operations"][0]["target"] = {
        "kind": "nativeField",
        "fieldId": "3001",
    }
    by_name = plan_mixed_form_fill(by_name_request)
    by_id = plan_mixed_form_fill(by_id_request)
    assert by_name.batch == by_id.batch
    assert by_name.request_hash != by_id.request_hash

    store: dict[str, Any] = {}
    first = apply_mixed_form_plan(by_name, idempotency_store=store)
    first_output = output.read_bytes()
    first_identity = store["locator-identity"]["requestHash"]
    conflict = apply_mixed_form_plan(by_id, idempotency_store=store)

    assert first.ok
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.code == "idempotency_conflict"
    assert conflict.verification_report["idempotency"]["replayed"] is False
    assert output.read_bytes() == first_output
    stored = store["locator-identity"]
    assert stored["identityScope"] == "hwpx.mixed-form-idempotency/v1"
    assert stored["mixedFormRequestHash"] == by_name.request_hash
    assert stored["batchRequestHash"] != stored["requestHash"]
    assert stored["requestHash"] == first_identity


@pytest.mark.parametrize(
    ("operation_id", "mutation"),
    [
        (
            "path",
            lambda resolution: resolution.update({"locatorKind": "nativeField"}),
        ),
        (
            "body",
            lambda resolution: resolution.update({"section": None}),
        ),
        (
            "label",
            lambda resolution: resolution.update({"physicalColumn": None}),
        ),
        (
            "path",
            lambda resolution: resolution.update({"nodeKind": "run"}),
        ),
    ],
    ids=[
        "native-field-must-be-form-field",
        "body-anchor-must-have-section",
        "label-cell-must-have-coordinates",
        "canonical-path-kind-must-match-node",
    ],
)
def test_compiled_plan_enforces_locator_node_path_invariants(
    tmp_path: Path,
    operation_id: str,
    mutation: Any,
) -> None:
    source = tmp_path / "source.hwpx"
    _write_mixed_form_fixture(source)
    payload = plan_mixed_form_fill(_public_plan(source, tmp_path / "out.hwpx")).to_dict()
    resolution = next(
        item for item in payload["resolutions"] if item["operationId"] == operation_id
    )
    mutation(resolution)
    _rehash_compiled_plan(payload)

    with pytest.raises(AgentContractError) as caught:
        validate_mixed_form_plan(payload)
    assert caught.value.code == "invariant_violation"
