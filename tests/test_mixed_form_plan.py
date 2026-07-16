from __future__ import annotations

import ast
import hashlib
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.agent import (
    AGENT_BATCH_SCHEMA,
    MIXED_FORM_COMPILED_PLAN_SCHEMA,
    MIXED_FORM_PLAN_SCHEMA,
    AgentContractError,
    HwpxAgentDocument,
    apply_mixed_form_fill,
    apply_mixed_form_plan,
    mixed_form_json_schemas,
    plan_mixed_form_fill,
    validate_mixed_form_plan,
    validate_mixed_form_request,
)
from hwpx.oxml.namespaces import HP


def _append(parent: Any, tag: str, attrs: dict[str, str] | None = None) -> Any:
    child = parent.makeelement(tag, attrs or {})
    parent.append(child)
    return child


def _add_native_project_field(document: HwpxDocument) -> None:
    paragraph = document.add_paragraph("사업명: ")
    paragraph.element.set("id", "240020")
    begin_run = _append(paragraph.element, f"{HP}run", {"charPrIDRef": "0"})
    control = _append(begin_run, f"{HP}ctrl", {"type": "FORM", "id": "ctrl-240021"})
    field_begin = _append(
        control,
        f"{HP}fieldBegin",
        {
            "id": "240021",
            "fieldid": "240021",
            "type": "ClickHere",
            "name": "사업명",
            "prompt": "사업명",
            "editable": "true",
        },
    )
    parameters = _append(field_begin, f"{HP}parameters", {"count": "2"})
    _append(parameters, f"{HP}stringParam", {"name": "FieldName"}).text = "사업명"
    _append(parameters, f"{HP}stringParam", {"name": "Instruction"}).text = "사업명"
    value_run = _append(paragraph.element, f"{HP}run", {"charPrIDRef": "0"})
    _append(value_run, f"{HP}t").text = "여기를 누르세요"
    end_run = _append(paragraph.element, f"{HP}run", {"charPrIDRef": "0"})
    end_control = _append(end_run, f"{HP}ctrl")
    _append(
        end_control,
        f"{HP}fieldEnd",
        {"beginIDRef": "240021", "fieldid": "240021"},
    )
    paragraph.section.mark_dirty()


def build_s079_korean_mixed_form_fixture(
    path: Path,
    *,
    split_body_anchor: bool = False,
    duplicate_body_anchor: bool = False,
    duplicate_native_field: bool = False,
    duplicate_label: bool = False,
    include_merged_probe: bool = False,
) -> None:
    """Build the synthetic, one-page Korean form frozen by Feature 024 P1."""

    with HwpxDocument.new() as document:
        title = document.sections[0].paragraphs[0]
        title.element.set("id", "240010")
        title.text = "S-079 혼합 양식 기준 문서"
        _add_native_project_field(document)
        if duplicate_native_field:
            _add_native_project_field(document)

        table_paragraph = document.add_paragraph("담당 부서")
        table_paragraph.element.set("id", "240030")
        table = table_paragraph.add_table(2, 2)
        table.element.set("id", "240031")
        table.rows[0].cells[0].text = "담당 부서" if duplicate_label else "사업명"
        table.rows[0].cells[1].text = ""
        table.rows[1].cells[0].text = "담당 부서"
        table.rows[1].cells[1].text = ""

        body = document.add_paragraph("", include_run=False)
        body.element.set("id", "240040")
        if split_body_anchor:
            body.add_run("담당자: {{담")
            body.add_run("당자}}")
        else:
            body.add_run("담당자: {{담당자}}")
        if duplicate_body_anchor:
            document.add_paragraph("비상 담당자: {{담당자}}")

        purpose = document.add_paragraph("행사 목적: 여기를 입력하세요")
        purpose.element.set("id", "240050")

        if include_merged_probe:
            merged_paragraph = document.add_paragraph("병합 대상")
            merged_table = merged_paragraph.add_table(2, 2)
            merged_table.rows[0].cells[0].text = "구분"
            merged_table.rows[0].cells[1].text = "병합값"
            merged_table.rows[1].cells[0].text = ""
            merged_table.rows[1].cells[1].text = ""
            merged_table.merge_cells("A2:B2")

        document.save_to_path(path)


def _revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _plan_request(
    source: Path,
    output: Path,
    *,
    dry_run: bool = False,
    idempotency_key: str | None = "s079-mixed-anchor-reference-v1",
) -> dict[str, Any]:
    return {
        "schemaVersion": MIXED_FORM_PLAN_SCHEMA,
        "source": str(source),
        "output": str(output),
        "expectedRevision": _revision(source),
        "idempotencyKey": idempotency_key,
        "dryRun": dry_run,
        "overwrite": True,
        "quality": "transparent",
        "verificationRequirements": [
            "package",
            "reopen",
            "bytePreservation",
            "openSafety",
        ],
        "operations": [
            {
                "operationId": "native-project-name",
                "target": {"kind": "nativeField", "fieldId": "240021"},
                "value": "AI 수업 나눔의 날",
            },
            {
                "operationId": "label-department",
                "target": {
                    "kind": "labelCell",
                    "sectionPath": "/section[1]",
                    "tableAnchor": "담당 부서",
                    "cellAnchor": {"label": "담당 부서", "direction": "right"},
                },
                "value": "교육연구부",
            },
            {
                "operationId": "canonical-purpose",
                "target": {
                    "kind": "canonicalPath",
                    "path": '/section[1]/paragraph[@id="240050"]',
                },
                "value": "행사 목적: 교내 AI 활용 사례 공유",
            },
            {
                "operationId": "body-owner",
                "target": {
                    "kind": "bodyAnchor",
                    "sectionPath": "/section[1]",
                    "anchor": "{{담당자}}",
                    "expectedCount": 1,
                },
                "value": "김서현",
            },
        ],
    }


def _operation_only(request: dict[str, Any], operation_id: str) -> dict[str, Any]:
    selected = deepcopy(request)
    selected["operations"] = [
        operation
        for operation in selected["operations"]
        if operation["operationId"] == operation_id
    ]
    return selected


def test_p1_frozen_plan_compiles_four_locators_before_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    build_s079_korean_mixed_form_fixture(source)
    source_before = source.read_bytes()

    plan = plan_mixed_form_fill(_plan_request(source, output, dry_run=True))

    assert source.read_bytes() == source_before
    assert not output.exists()
    assert plan.to_dict()["schemaVersion"] == MIXED_FORM_COMPILED_PLAN_SCHEMA
    assert plan.input_revision == _revision(source)
    assert [item.locator_kind for item in plan.resolutions] == [
        "nativeField",
        "labelCell",
        "canonicalPath",
        "bodyAnchor",
    ]
    assert plan.batch["schemaVersion"] == AGENT_BATCH_SCHEMA
    assert plan.batch["expectedRevision"] == plan.input_revision
    assert len({item.path for item in plan.resolutions}) == 4
    assert [command["op"] for command in plan.batch["commands"]] == ["set"] * 4
    assert validate_mixed_form_plan(plan).plan_hash == plan.plan_hash


def test_success_preserves_untouched_members_and_reopens(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    build_s079_korean_mixed_form_fixture(source)

    result = apply_mixed_form_fill(_plan_request(source, output))

    assert result.ok, result.to_dict()
    assert result.rolled_back is False
    assert result.verification_report["openSafety"]["ok"] is True
    assert result.verification_report["bytePreservation"]["ok"] is True
    assert validate_editor_open_safety(output).ok
    with HwpxDocument.open(output) as document:
        assert document.list_form_fields()[0]["current_value"] == "AI 수업 나눔의 날"
        matches = document.find_cell_by_label("담당 부서", direction="right")
        match = matches["matches"][0]
        assert match["target_cell"]["text"] == "교육연구부"
    with HwpxAgentDocument.open(output) as agent:
        purpose = agent.resolve_record('/section[1]/paragraph[@id="240050"]')
        owner = agent.resolve_record('/section[1]/paragraph[@id="240040"]')
        assert purpose.summary["text"] == "행사 목적: 교내 AI 활용 사례 공유"
        assert owner.summary["text"] == "담당자: 김서현"

    changed = set(result.verification_report["bytePreservation"]["changedMembers"])
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        common = set(before.namelist()) & set(after.namelist())
        assert "Contents/section0.xml" in changed
        assert all(before.read(name) == after.read(name) for name in common - changed)


def test_dry_run_and_injected_failure_publish_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    dry_output = tmp_path / "dry.hwpx"
    failed_output = tmp_path / "failed.hwpx"
    build_s079_korean_mixed_form_fixture(source)

    dry = apply_mixed_form_fill(_plan_request(source, dry_output, dry_run=True))
    assert dry.ok and dry.dry_run
    assert not dry_output.exists()

    prior = b"prior destination must survive"
    failed_output.write_bytes(prior)
    plan = plan_mixed_form_fill(_plan_request(source, failed_output))

    def fail_after_second(stage: str, index: int | None) -> None:
        if stage == "after_command" and index == 1:
            raise RuntimeError("injected mixed-form failure")

    failed = apply_mixed_form_plan(plan, fault_injector=fail_after_second)
    assert not failed.ok
    assert failed.rolled_back
    assert failed_output.read_bytes() == prior
    assert source.exists() and validate_editor_open_safety(source).ok


def test_idempotent_replay_and_same_key_conflict(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    build_s079_korean_mixed_form_fixture(source)
    store: dict[str, Any] = {}
    request = _plan_request(source, output)
    plan = plan_mixed_form_fill(request)

    first = apply_mixed_form_plan(plan, idempotency_store=store)
    replay = apply_mixed_form_plan(plan, idempotency_store=store)
    assert first.ok and replay.ok
    assert replay.document_revision == first.document_revision
    assert replay.verification_report["idempotency"]["replayed"] is True

    conflicting_request = deepcopy(request)
    conflicting_request["operations"][0]["value"] = "다른 사업명"
    conflict_plan = plan_mixed_form_fill(conflicting_request)
    conflict = apply_mixed_form_plan(conflict_plan, idempotency_store=store)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.code == "idempotency_conflict"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda request: request.update({"unknown": True}),
        lambda request: request["operations"][0]["target"].update({"raw": "forbidden"}),
        lambda request: request["operations"][3]["target"].pop("expectedCount"),
        lambda request: request["operations"][1]["target"].update(
            {"sectionPath": "/section[@id=\"1\"]"}
        ),
    ],
)
def test_public_plan_is_strict_and_fail_closed(tmp_path: Path, mutation: Any) -> None:
    source = tmp_path / "source.hwpx"
    build_s079_korean_mixed_form_fixture(source)
    request = _plan_request(source, tmp_path / "output.hwpx")
    mutation(request)

    with pytest.raises(AgentContractError):
        validate_mixed_form_request(request)

    schema = mixed_form_json_schemas()["plan"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["operations"]["items"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("fixture_options", "expected_code"),
    [
        ({"split_body_anchor": True}, "unsupported_content"),
        ({"duplicate_body_anchor": True}, "ambiguous_target"),
    ],
)
def test_body_anchor_zero_multiple_and_run_spanning_fail_closed(
    tmp_path: Path,
    fixture_options: dict[str, bool],
    expected_code: str,
) -> None:
    source = tmp_path / "source.hwpx"
    build_s079_korean_mixed_form_fixture(source, **fixture_options)
    request = _operation_only(
        _plan_request(source, tmp_path / "output.hwpx"),
        "body-owner",
    )

    with pytest.raises(AgentContractError) as caught:
        plan_mixed_form_fill(request)
    assert caught.value.code == expected_code

    missing = deepcopy(request)
    missing["operations"][0]["target"]["anchor"] = "{{없는값}}"
    with pytest.raises(AgentContractError) as absent:
        plan_mixed_form_fill(missing)
    assert absent.value.code == "not_found"


@pytest.mark.parametrize(
    ("fixture_options", "operation_id", "expected_code"),
    [
        ({"duplicate_native_field": True}, "native-project-name", "ambiguous_target"),
        ({"duplicate_label": True}, "label-department", "ambiguous_target"),
    ],
)
def test_native_and_label_locators_reject_multiple_matches(
    tmp_path: Path,
    fixture_options: dict[str, bool],
    operation_id: str,
    expected_code: str,
) -> None:
    source = tmp_path / "source.hwpx"
    build_s079_korean_mixed_form_fixture(source, **fixture_options)
    request = _operation_only(
        _plan_request(source, tmp_path / "output.hwpx"),
        operation_id,
    )

    with pytest.raises(AgentContractError) as caught:
        plan_mixed_form_fill(request)
    assert caught.value.code == expected_code


def test_revision_binding_rejects_stale_source(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    build_s079_korean_mixed_form_fixture(source)
    request = _plan_request(source, tmp_path / "output.hwpx")
    request["expectedRevision"] = "sha256:" + "0" * 64

    with pytest.raises(AgentContractError) as caught:
        plan_mixed_form_fill(request)
    assert caught.value.code == "stale_revision"


def test_label_cell_normalizes_merged_logical_coordinate(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    build_s079_korean_mixed_form_fixture(source, include_merged_probe=True)
    request = _operation_only(
        _plan_request(source, tmp_path / "output.hwpx", dry_run=True),
        "label-department",
    )
    request["operations"][0]["target"] = {
        "kind": "labelCell",
        "sectionPath": "/section[1]",
        "tableAnchor": "병합 대상",
        "cellAnchor": {"label": "병합값", "direction": "below"},
    }

    plan = plan_mixed_form_fill(request)
    resolution = plan.resolutions[0]
    assert (resolution.logical_row, resolution.logical_column) == (1, 1)
    assert (resolution.physical_row, resolution.physical_column) == (1, 0)
    assert resolution.path.endswith("/row[2]/cell[1]")


def test_evalplan_remains_available_and_exam_is_not_imported() -> None:
    import hwpx.agent.form_plan as form_plan
    import hwpx.evalplan_fill as evalplan_fill

    tree = ast.parse(Path(form_plan.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not any(name == "hwpx.exam" or name.startswith("hwpx.exam.") for name in imported)
    assert callable(evalplan_fill.parse_review_md)
    assert callable(evalplan_fill.fill_evalplan)
