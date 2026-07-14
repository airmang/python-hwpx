from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.agent import HwpxAgentDocument
from hwpx.agent.model import AgentContractError
from hwpx.agent.blueprint import dump_document_blueprint, replay_document_blueprint
from hwpx.quality import SavePipeline
from hwpx.visual import NullOracle
from hwpx.oxml.namespaces import HP

PNG = (
    Path(__file__).parent
    / "fixtures/fuzz_regressions/visual_review_seed_000000_000999_screenshots/seed-000003-710dbd610d8d.png"
).read_bytes()


def _write_supported_fixture(path: Path, *, paragraph_id: str = "102") -> str:
    with HwpxDocument.new() as document:
        paragraph = document.sections[0].paragraphs[0]
        paragraph.element.set("id", paragraph_id)
        paragraph.text = "결재 요청 본문"
        paragraph.add_rectangle(width=7200, height=3600, fill_color="#FFFFFF")
        paragraph.add_footnote("승인 근거")
        image_ref = document.add_image(PNG, "png")
        paragraph.add_picture(image_ref, width=7200, height=3600)
        table = paragraph.add_table(2, 2)
        table.rows[0].cells[0].text = "항목 / 담당"
        table.rows[0].cells[1].text = "내용"
        table.rows[1].cells[1].text = "홍길동"
        table.merge_cells("A1:A2")
        begin_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        begin_ctrl = begin_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
        begin_ctrl.append(
            begin_ctrl.makeelement(
                f"{HP}fieldBegin",
                {
                    "id": "601",
                    "fieldid": "601",
                    "name": "담당자",
                    "prompt": "담당자",
                    "type": "CLICK_HERE",
                    "editable": "true",
                },
            )
        )
        begin = begin_ctrl[-1]
        parameters = begin.makeelement(f"{HP}parameters", {"count": "2"})
        name_param = parameters.makeelement(f"{HP}stringParam", {"name": "FieldName"})
        name_param.text = "담당자"
        prompt_param = parameters.makeelement(f"{HP}stringParam", {"name": "Instruction"})
        prompt_param.text = "담당자"
        parameters.extend((name_param, prompt_param))
        begin.append(parameters)
        begin_run.append(begin_ctrl)
        paragraph.element.append(begin_run)
        end_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        end_ctrl = end_run.makeelement(f"{HP}ctrl", {})
        end_ctrl.append(end_ctrl.makeelement(f"{HP}fieldEnd", {"beginIDRef": "601", "fieldid": "601"}))
        end_run.append(end_ctrl)
        paragraph.element.append(end_run)
        paragraph.section.mark_dirty()
        document.save_to_path(path)
    with HwpxAgentDocument.open(path) as agent:
        return next(
            record.path
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") == paragraph_id
        )


def _write_unsupported_fixture(path: Path) -> str:
    root = _write_supported_fixture(path)
    with HwpxDocument.open(path) as document:
        paragraph = document.sections[0].paragraphs[0]
        paragraph.runs[0].element.append(paragraph.runs[0].element.makeelement(f"{HP}mysteryObject", {}))
        paragraph.section.mark_dirty()
        document.save_to_path(path)
    return root


def _revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_target(path: Path, texts: tuple[str, ...] = ("TARGET",)) -> None:
    with HwpxDocument.new() as document:
        first = document.sections[0].paragraphs[0]
        first.text = texts[0]
        for text in texts[1:]:
            document.add_paragraph(text)
        document.save_to_path(path)


def _request(
    bundle: Path,
    blueprint_hash: str,
    target: Path,
    output: Path,
    *,
    mode: str = "portable",
    target_parent: str = "/section[1]",
    position: dict[str, Any] | None = None,
    expected_revision: str | None = None,
    idempotency_key: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    requirements: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "hwpx.agent-blueprint-replay/v1",
        "bundle": {"filename": str(bundle), "blueprintHash": blueprint_hash},
        "target": {"input": str(target), "output": str(output), "overwrite": overwrite},
        "targetParent": target_parent,
        "position": position or {"mode": "append"},
        "mode": mode,
        "mappingPolicy": {"strict": True},
        "expectedRevision": expected_revision if expected_revision is not None else _revision(target),
        "idempotencyKey": idempotency_key,
        "dryRun": dry_run,
        "quality": "transparent",
        "verificationRequirements": requirements or [
            "package",
            "reopen",
            "openSafety",
            "semanticDiff",
            "bytePreservation",
        ],
    }


def _portable_fixture(tmp_path: Path) -> tuple[Path, Path, str, Path]:
    source = tmp_path / "source.hwpx"
    bundle = tmp_path / "block.hwpxbp"
    target = tmp_path / "target.hwpx"
    root = _write_supported_fixture(source)
    dumped = dump_document_blueprint(source, path=root, mode="portable", output=bundle)
    _write_target(target)
    return bundle, target, str(dumped.manifest["blueprintHash"]), source


def test_portable_replay_preserves_merged_table_form_note_shape_and_media(tmp_path: Path) -> None:
    bundle, target, blueprint_hash, _source = _portable_fixture(tmp_path)
    output = tmp_path / "output.hwpx"
    result = replay_document_blueprint(_request(bundle, blueprint_hash, target, output))

    assert result.ok is True
    assert result.rolled_back is False
    assert result.semantic_diff["ok"] is True
    assert result.fidelity["ok"] is True
    assert set(result.fidelity["nodes"].values()) == {"mapped"}
    assert validate_editor_open_safety(output).ok
    with HwpxAgentDocument.open(output) as agent:
        root = agent.resolve_record(str(result.root_path))
        kinds = {agent.resolve_record(path).kind for path in root.child_paths}
        table = next(record for record in agent.records if record.path.startswith(root.path) and record.kind == "table")
        field = next(record for record in agent.records if record.path.startswith(root.path) and record.kind == "form-field")
        picture = next(record for record in agent.records if record.path.startswith(root.path) and record.kind == "picture")
        first_cell = next(record for record in agent.records if record.path.startswith(table.path) and record.kind == "cell")
    assert {"table", "picture", "shape", "footnote", "form-field"} <= kinds
    assert first_cell.summary["rowSpan"] == 2
    assert field.summary["name"] == "담당자"
    assert picture.summary["widthMm"] == 25.4
    assert result.verification_report["commit"] == {"ok": True, "atomic": True, "savedOnce": True}
    with HwpxDocument.open(output) as document:
        control_runs = [
            run
            for section in document.sections
            for run in section.element.iter(f"{HP}run")
            if any(
                child.tag.rsplit("}", 1)[-1]
                in {"tbl", "pic", "rect", "footNote", "endNote", "ctrl"}
                for child in run
            )
        ]
        assert control_runs
        assert all(
            not any(
                child.tag.rsplit("}", 1)[-1] == "t"
                and not "".join(child.itertext())
                and not child.tail
                for child in run
            )
            for run in control_runs
        )


def test_source_bound_replay_reuses_exact_fingerprints(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    bundle = tmp_path / "bound.hwpxbp"
    output = tmp_path / "bound-output.hwpx"
    root = _write_supported_fixture(source)
    dumped = dump_document_blueprint(source, path=root, mode="source-bound", output=bundle)
    result = replay_document_blueprint(
        _request(bundle, str(dumped.manifest["blueprintHash"]), source, output, mode="source-bound")
    )
    assert result.ok is True
    assert result.fidelity["ceiling"] == "exact"
    assert {item["action"] for item in result.dependency_maps.values()} == {"reuse"}


def test_portable_style_conflict_and_numbering_allocate_mapped_records(tmp_path: Path) -> None:
    source = tmp_path / "list-source.hwpx"
    target = tmp_path / "target.hwpx"
    bundle = tmp_path / "list.hwpxbp"
    output = tmp_path / "list-output.hwpx"
    with HwpxDocument.new() as document:
        paragraph = document.sections[0].paragraphs[0]
        paragraph.text = "목록 항목"
        document.set_paragraph_format(paragraph_index=0, alignment="CENTER")
        document.set_list_format(paragraph_index=0, kind="bullet", level=1)
        document.save_to_path(source)
    with HwpxAgentDocument.open(source) as agent:
        root = next(record.path for record in agent.records if record.kind == "paragraph")
    dumped = dump_document_blueprint(source, path=root, output=bundle)
    _write_target(target)
    result = replay_document_blueprint(_request(bundle, str(dumped.manifest["blueprintHash"]), target, output))
    assert result.ok is True
    created = [item for item in result.dependency_maps.values() if item["action"] == "create"]
    assert {item["family"] for item in created} == {"style", "numbering"}
    style = next(item for item in created if item["family"] == "style")
    assert "__bp_" in style["identity"]["name"]


def test_dry_run_writes_nothing_and_caller_owned_idempotency_replays_once(tmp_path: Path) -> None:
    bundle, target, blueprint_hash, _source = _portable_fixture(tmp_path)
    dry_output = tmp_path / "dry.hwpx"
    dry = replay_document_blueprint(
        _request(bundle, blueprint_hash, target, dry_output, dry_run=True, idempotency_key="dry")
    )
    assert dry.ok is True
    assert dry.dry_run is True
    assert not dry_output.exists()
    assert dry.verification_report["commit"]["savedOnce"] is False

    output = tmp_path / "once.hwpx"
    store: dict[str, Any] = {}
    request = _request(bundle, blueprint_hash, target, output, idempotency_key="once")
    first = replay_document_blueprint(request, idempotency_store=store)
    first_bytes = output.read_bytes()
    second = replay_document_blueprint(request, idempotency_store=store)
    assert first.ok and second.ok
    assert output.read_bytes() == first_bytes
    assert second.verification_report["idempotency"]["replayed"] is True

    conflict_request = deepcopy(request)
    conflict_request["position"] = {"mode": "prepend"}
    conflict = replay_document_blueprint(conflict_request, idempotency_store=store)
    assert conflict.ok is False
    assert conflict.error is not None and conflict.error.code == "idempotency_conflict"


def test_before_position_and_document_root_children_are_supported(tmp_path: Path) -> None:
    source = tmp_path / "simple-source.hwpx"
    target = tmp_path / "target.hwpx"
    bundle = tmp_path / "simple.hwpxbp"
    output = tmp_path / "positioned.hwpx"
    with HwpxDocument.new() as document:
        document.sections[0].paragraphs[0].text = "INSERTED"
        document.save_to_path(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph_path = next(record.path for record in agent.records if record.kind == "paragraph")
    dumped = dump_document_blueprint(source, path=paragraph_path, output=bundle)
    _write_target(target, ("A", "B"))
    with HwpxAgentDocument.open(target) as agent:
        anchor = [record.path for record in agent.records if record.kind == "paragraph"][1]
    result = replay_document_blueprint(
        _request(
            bundle,
            str(dumped.manifest["blueprintHash"]),
            target,
            output,
            position={"mode": "before", "path": anchor},
        )
    )
    assert result.ok is True
    with HwpxDocument.open(output) as document:
        assert [paragraph.text for paragraph in document.sections[0].paragraphs] == ["A", "INSERTED", "B"]

    document_bundle = tmp_path / "document.hwpxbp"
    document_output = tmp_path / "document-output.hwpx"
    full = dump_document_blueprint(source, path="/", output=document_bundle)
    full_result = replay_document_blueprint(
        _request(
            document_bundle,
            str(full.manifest["blueprintHash"]),
            target,
            document_output,
            target_parent="/",
        )
    )
    assert full_result.ok is True
    assert full_result.semantic_diff["scope"] == "document-root-children"


def test_standalone_section_replay_ignores_source_index_at_append_destination(tmp_path: Path) -> None:
    source = tmp_path / "section-source.hwpx"
    target = tmp_path / "section-target.hwpx"
    bundle = tmp_path / "section.hwpxbp"
    output = tmp_path / "section-output.hwpx"
    with HwpxDocument.new() as document:
        document.sections[0].paragraphs[0].text = "APPENDED SECTION"
        document.save_to_path(source)
    with HwpxAgentDocument.open(source) as agent:
        section_path = next(record.path for record in agent.records if record.kind == "section")
    dumped = dump_document_blueprint(source, path=section_path, output=bundle)
    section_node = next(node for node in dumped.manifest["nodes"] if node["kind"] == "section")
    assert "index" not in section_node["properties"]

    _write_target(target)
    result = replay_document_blueprint(
        _request(
            bundle,
            str(dumped.manifest["blueprintHash"]),
            target,
            output,
            target_parent="/",
        )
    )

    assert result.ok is True
    assert result.root_path == "/section[2]"
    assert result.semantic_diff["ok"] is True
    with HwpxDocument.open(output) as document:
        assert len(document.sections) == 2
        assert document.sections[1].paragraphs[0].text == "APPENDED SECTION"


def test_standalone_row_replays_but_cell_dump_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "row-source.hwpx"
    target = tmp_path / "row-target.hwpx"
    bundle = tmp_path / "row.hwpxbp"
    output = tmp_path / "row-output.hwpx"
    with HwpxDocument.new() as document:
        source_table = document.sections[0].paragraphs[0].add_table(1, 2)
        source_table.rows[0].cells[0].text = "왼쪽"
        source_table.rows[0].cells[1].text = "오른쪽"
        document.save_to_path(source)
    with HwpxAgentDocument.open(source) as agent:
        row_path = next(record.path for record in agent.records if record.kind == "row")
        cell_path = next(record.path for record in agent.records if record.kind == "cell")
    dumped = dump_document_blueprint(source, path=row_path, output=bundle)
    with pytest.raises(AgentContractError) as cell_error:
        dump_document_blueprint(source, path=cell_path)
    assert cell_error.value.code == "unsupported_content"

    with HwpxDocument.new() as document:
        document.sections[0].paragraphs[0].add_table(1, 2)
        document.save_to_path(target)
    with HwpxAgentDocument.open(target) as agent:
        target_table = next(record.path for record in agent.records if record.kind == "table")
    result = replay_document_blueprint(
        _request(
            bundle,
            str(dumped.manifest["blueprintHash"]),
            target,
            output,
            target_parent=target_table,
        )
    )
    assert result.ok is True
    with HwpxDocument.open(output) as document:
        table = document.sections[0].paragraphs[0].tables[0]
        assert len(table.rows) == 2
        assert [cell.text for cell in table.rows[1].cells] == ["왼쪽", "오른쪽"]


@pytest.mark.parametrize(
    "fault_stage",
    [
        "before_bundle_validation",
        "after_bundle_validation",
        "before_target_read",
        "after_target_read",
        "after_target_validation",
        "before_plan",
        "after_plan",
        "before_dependencies",
        "after_dependencies",
        "before_nodes",
        "after_nodes",
        "before_serialize",
        "after_serialize",
        "after_candidate_verification",
        "before_save_pipeline",
        "after_save_pipeline",
        "before_commit",
    ],
)
def test_fault_injection_rolls_back_requested_output(tmp_path: Path, fault_stage: str) -> None:
    bundle, target, blueprint_hash, _source = _portable_fixture(tmp_path)
    output = tmp_path / f"fault-{fault_stage}.hwpx"
    sentinel = b"owner-output-sentinel"
    output.write_bytes(sentinel)

    def inject(stage: str, _index: int | None) -> None:
        if stage == fault_stage:
            raise RuntimeError(f"fault:{stage}")

    result = replay_document_blueprint(
        _request(bundle, blueprint_hash, target, output, overwrite=True),
        fault_injector=inject,
    )
    assert result.ok is False
    assert result.rolled_back is True
    assert output.read_bytes() == sentinel
    if "rollback" in result.verification_report:
        assert result.verification_report["rollback"]["ok"] is True


def test_failures_are_closed_before_or_without_output_mutation(tmp_path: Path) -> None:
    bundle, target, blueprint_hash, source = _portable_fixture(tmp_path)
    output = tmp_path / "failed.hwpx"

    stale_request = _request(bundle, blueprint_hash, target, output)
    stale_request["expectedRevision"] = "sha256:" + "0" * 64
    stale = replay_document_blueprint(stale_request)
    assert stale.ok is False and stale.error is not None and stale.error.code == "stale_revision"
    assert not output.exists()

    missing_target = tmp_path / "missing-target.hwpx"
    invalid_bundle = tmp_path / "invalid.hwpxbp"
    invalid_bundle.write_bytes(b"not a zip")
    invalid = replay_document_blueprint(
        _request(invalid_bundle, "sha256:" + "0" * 64, missing_target, output, expected_revision="sha256:" + "0" * 64)
    )
    assert invalid.ok is False
    assert invalid.error is not None and invalid.error.code == "invalid_syntax"
    assert invalid.verification_report.get("revision") is None

    bound_bundle = tmp_path / "bound.hwpxbp"
    with HwpxAgentDocument.open(source) as agent:
        root = next(record.path for record in agent.records if record.kind == "paragraph")
    bound = dump_document_blueprint(source, path=root, mode="source-bound", output=bound_bundle)
    missing_dependency = replay_document_blueprint(
        _request(
            bound_bundle,
            str(bound.manifest["blueprintHash"]),
            target,
            output,
            mode="source-bound",
        )
    )
    assert missing_dependency.ok is False
    assert missing_dependency.error is not None and missing_dependency.error.code == "not_found"
    assert not output.exists()

    unsupported_source = tmp_path / "unsupported.hwpx"
    unsupported_bundle = tmp_path / "unsupported.hwpxbp"
    unsupported_root = _write_unsupported_fixture(unsupported_source)
    inspection = dump_document_blueprint(
        unsupported_source,
        path=unsupported_root,
        require_replayable=False,
        output=unsupported_bundle,
    )
    refused = replay_document_blueprint(
        _request(unsupported_bundle, str(inspection.manifest["blueprintHash"]), target, output)
    )
    assert refused.ok is False
    assert refused.error is not None and refused.error.code == "unsupported_content"
    assert not output.exists()


def test_required_domain_and_real_hancom_are_atomic_gates(tmp_path: Path) -> None:
    bundle, target, blueprint_hash, _source = _portable_fixture(tmp_path)
    domain_output = tmp_path / "domain.hwpx"
    domain = replay_document_blueprint(
        _request(
            bundle,
            blueprint_hash,
            target,
            domain_output,
            requirements=["package", "reopen", "openSafety", "domain"],
        )
    )
    assert domain.ok is False
    assert domain.error is not None and domain.error.code == "verification_failed"
    assert not domain_output.exists()

    hancom_output = tmp_path / "hancom.hwpx"
    hancom = replay_document_blueprint(
        _request(
            bundle,
            blueprint_hash,
            target,
            hancom_output,
            requirements=["package", "reopen", "openSafety", "realHancom"],
        ),
        save_pipeline=SavePipeline(oracle=NullOracle()),
    )
    assert hancom.ok is False
    assert hancom.error is not None and hancom.error.code == "verification_failed"
    assert not hancom_output.exists()
