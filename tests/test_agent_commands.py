from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.agent import AGENT_BATCH_SCHEMA, HwpxAgentDocument, apply_document_commands
from hwpx.oxml.namespaces import HP
from hwpx.quality import SavePipeline
from hwpx.visual import NullOracle


def _revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(path: Path, *, merged: bool = False) -> None:
    with HwpxDocument.new() as document:
        first = document.sections[0].paragraphs[0]
        first.element.set("id", "101")
        first.text = "첫 문단"
        second = document.add_paragraph("둘째 문단")
        second.element.set("id", "102")
        third = document.add_paragraph("셋째 문단")
        third.element.set("id", "103")
        shape = second.add_rectangle(width=7200, height=3600, fill_color="#FFFFFF")
        shape.element.set("id", "401")
        shape.element.set("instid", "401")
        second.add_footnote("각주 원문").element.set("instId", "501")
        second.add_endnote("미주 원문").element.set("instId", "502")
        image_data = (
            Path(__file__).parent
            / "fixtures/fuzz_regressions/visual_review_seed_000000_000999_screenshots/seed-000003-710dbd610d8d.png"
        ).read_bytes()
        image_ref = document.add_image(image_data, "png")
        picture = second.add_picture(image_ref, width=7200, height=3600)
        picture.element.set("id", "402")
        picture.element.set("instid", "402")
        table = second.add_table(2, 2)
        table.element.set("id", "201")
        table.rows[0].cells[0].text = "A"
        table.rows[0].cells[1].text = "B"
        table.rows[1].cells[0].text = "C"
        table.rows[1].cells[1].text = "D"
        if merged:
            table.rows[0].cells[0].set_span(2, 1)
        document.sections[0].add_memo("검토 메모", memo_id="301")

        field_run = second.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        control = field_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
        begin = control.makeelement(
            f"{HP}fieldBegin",
            {"id": "601", "fieldName": "담당자", "type": "FORM", "editable": "true"},
        )
        control.append(begin)
        field_run.append(control)
        second.element.append(field_run)
        end_run = second.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        end_control = end_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
        end_control.append(
            end_control.makeelement(
                f"{HP}fieldEnd", {"beginIDRef": "601", "fieldid": "601"}
            )
        )
        end_run.append(end_control)
        second.element.append(end_run)
        second.section.mark_dirty()
        document.save_to_path(path)


def _batch(
    source: Path,
    output: Path,
    commands: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    expected_revision: str | None = None,
    idempotency_key: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": str(source)},
        "output": {"filename": str(output), "overwrite": overwrite},
        "commands": commands,
        "expectedRevision": expected_revision if expected_revision is not None else _revision(source),
        "idempotencyKey": idempotency_key,
        "dryRun": dry_run,
        "quality": "transparent",
        "verificationRequirements": [
            "package",
            "reopen",
            "openSafety",
            "semanticDiff",
            "bytePreservation",
        ],
    }


def _record(agent: HwpxAgentDocument, kind: str, identity: str):
    return next(
        record
        for record in agent.records
        if record.kind == kind and record.attributes.get("id") == identity
    )


def test_set_compiles_allowlisted_properties_and_verifies_once(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
        cell = next(record for record in agent.records if record.kind == "cell")
        field = _record(agent, "form-field", "601")
        shape = _record(agent, "shape", "401")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "p",
                    "op": "set",
                    "path": paragraph.path,
                    "properties": {
                        "text": "수정 문단",
                        "alignment": "CENTER",
                        "keepWithNext": True,
                    },
                },
                {
                    "commandId": "c",
                    "op": "set",
                    "path": cell.path,
                    "properties": {
                        "text": "수정 셀",
                        "verticalAlignment": "BOTTOM",
                        "backgroundColor": "#AABBCC",
                    },
                },
                {
                    "commandId": "f",
                    "op": "set",
                    "path": field.path,
                    "properties": {"value": "홍길동", "readOnly": True},
                },
                {
                    "commandId": "s",
                    "op": "set",
                    "path": shape.path,
                    "properties": {"altText": "흰색 사각형"},
                },
            ],
        )
    )

    assert result.ok, result.to_dict()
    assert result.rolled_back is False
    assert output.exists()
    assert _revision(output) == result.document_revision
    assert result.verification_report["savePipeline"]["ok"] is True
    assert result.verification_report["openSafety"]["ok"] is True
    assert validate_editor_open_safety(output).ok
    with HwpxAgentDocument.open(output) as agent:
        assert _record(agent, "paragraph", "101").summary["text"] == "수정 문단"
        assert next(record for record in agent.records if record.kind == "cell").summary["text"] == "수정 셀"
        assert _record(agent, "form-field", "601").summary["value"] == "홍길동"
        assert _record(agent, "form-field", "601").summary["readOnly"] is True
        assert _record(agent, "shape", "401").summary["altText"] == "흰색 사각형"


def test_add_alias_and_remove_are_sequential_but_commit_atomically(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        section = next(record for record in agent.records if record.kind == "section")
        removable = _record(agent, "paragraph", "103")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "newp",
                    "op": "add",
                    "parent": section.path,
                    "kind": "paragraph",
                    "properties": {"text": "새 문단", "alignment": "RIGHT"},
                    "position": {"mode": "prepend"},
                },
                {
                    "commandId": "newrun",
                    "op": "add",
                    "parent": "$newp.path",
                    "kind": "run",
                    "properties": {"text": " 추가", "bold": True},
                },
                {"commandId": "drop", "op": "remove", "path": removable.path},
            ],
        )
    )

    assert result.ok, result.to_dict()
    assert result.command_results[1]["parentPath"] == result.command_results[0]["path"]
    with HwpxAgentDocument.open(output) as agent:
        texts = [record.summary["text"] for record in agent.records if record.kind == "paragraph"]
        assert texts[0] == "새 문단 추가"
        assert "셋째 문단" not in texts


def test_move_preserves_identity_and_copy_refreshes_nested_identities(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        section = next(record for record in agent.records if record.kind == "section")
        first = _record(agent, "paragraph", "101")
        second = _record(agent, "paragraph", "102")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "move",
                    "op": "move",
                    "path": second.path,
                    "parent": section.path,
                    "position": {"mode": "before", "path": first.path},
                },
                {
                    "commandId": "copy",
                    "op": "copy",
                    "path": "$move.path",
                    "parent": section.path,
                    "position": {"mode": "append"},
                },
            ],
        )
    )

    assert result.ok, result.to_dict()
    assert 'paragraph[@id="102"]' in result.command_results[0]["path"]
    identity_map = result.command_results[1]["generatedIdentities"]
    assert {item["kind"] for item in identity_map} >= {"paragraph", "table", "shape", "form-field"}
    object_pairs: dict[tuple[str, str], set[str]] = {}
    for item in identity_map:
        object_pairs.setdefault((item["kind"], item["old"]), set()).add(item["new"])
    assert all(len(values) == 1 for values in object_pairs.values())
    with HwpxAgentDocument.open(output) as agent:
        paragraph_ids = [
            record.attributes["id"]
            for record in agent.records
            if record.kind == "paragraph" and record.attributes["id"]
        ]
        assert len(paragraph_ids) == len(set(paragraph_ids))
        assert len([record for record in agent.records if record.kind == "table"]) == 2
    with HwpxDocument.open(output) as document:
        begins = {
            node.get("id")
            for section in document.sections
            for node in section.element.iter()
            if node.tag.endswith("}fieldBegin")
        }
        end_refs = {
            node.get("beginIDRef")
            for section in document.sections
            for node in section.element.iter()
            if node.tag.endswith("}fieldEnd")
        }
        assert None not in begins
        assert end_refs <= begins


def test_repeated_copy_uses_fresh_identities(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        section = next(record for record in agent.records if record.kind == "section")
        source_paragraph = _record(agent, "paragraph", "102")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "copy1",
                    "op": "copy",
                    "path": source_paragraph.path,
                    "parent": section.path,
                },
                {
                    "commandId": "copy2",
                    "op": "copy",
                    "path": source_paragraph.path,
                    "parent": section.path,
                },
            ],
        )
    )
    assert result.ok, result.to_dict()
    first_ids = {item["new"] for item in result.command_results[0]["generatedIdentities"]}
    second_ids = {item["new"] for item in result.command_results[1]["generatedIdentities"]}
    assert first_ids.isdisjoint(second_ids)


def test_table_and_row_add_move_copy_remove_matrix(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        first = _record(agent, "paragraph", "101")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "table",
                    "op": "add",
                    "parent": first.path,
                    "kind": "table",
                    "properties": {
                        "rowCount": 1,
                        "columnCount": 2,
                        "widthMm": 80,
                        "caption": "추가 표",
                        "alignment": "CENTER",
                    },
                },
                {
                    "commandId": "row",
                    "op": "add",
                    "parent": "$table.path",
                    "kind": "row",
                    "properties": {"cellCount": 2, "heightMm": 12},
                },
                {
                    "commandId": "rowcopy",
                    "op": "copy",
                    "path": "$row.path",
                    "parent": "$table.path",
                    "position": {"mode": "prepend"},
                },
                {"commandId": "drop", "op": "remove", "path": "$row.path"},
            ],
        )
    )

    assert result.ok, result.to_dict()
    with HwpxAgentDocument.open(output) as agent:
        table = agent.resolve_record(result.command_results[0]["path"])
        assert table.summary["rowCount"] == 2
        assert table.summary["caption"] == "추가 표"
        assert table.summary["alignment"] == "CENTER"


def test_dry_run_returns_candidate_diff_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    before = source.read_bytes()
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "p",
                    "op": "set",
                    "path": paragraph.path,
                    "properties": {"text": "미리보기"},
                }
            ],
            dry_run=True,
        )
    )
    assert result.ok, result.to_dict()
    assert result.dry_run is True
    assert result.document_revision != result.input_revision
    assert result.semantic_diff["changes"][0]["changedProperties"]["text"]["after"] == "미리보기"
    assert source.read_bytes() == before
    assert not output.exists()


@pytest.mark.parametrize("fault_index", [0, 1, 2])
def test_fault_at_each_command_index_rolls_back_output(tmp_path: Path, fault_index: int) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paths = [
            record.path
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") in {"101", "102", "103"}
        ]
    commands = [
        {
            "commandId": f"p{index}",
            "op": "set",
            "path": path,
            "properties": {"text": f"수정 {index}"},
        }
        for index, path in enumerate(paths)
    ]

    def inject(stage: str, index: int | None) -> None:
        if stage == "after_command" and index == fault_index:
            raise RuntimeError("injected failure")

    result = apply_document_commands(_batch(source, output, commands), fault_injector=inject)
    assert not result.ok
    assert result.rolled_back
    assert result.error is not None and result.error.code == "verification_failed"
    assert not output.exists()


def test_unknown_property_and_stale_revision_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    invalid = _batch(
        source,
        output,
        [
            {
                "commandId": "bad",
                "op": "set",
                "path": paragraph.path,
                "properties": {"xml": "<hp:p/>"},
            }
        ],
    )
    result = apply_document_commands(invalid)
    assert not result.ok and result.error is not None
    assert result.error.code == "unknown_property"
    assert not output.exists()

    stale = _batch(
        source,
        output,
        [
            {
                "commandId": "p",
                "op": "set",
                "path": paragraph.path,
                "properties": {"text": "수정"},
            }
        ],
        expected_revision="sha256:" + "0" * 64,
    )
    stale_result = apply_document_commands(stale)
    assert not stale_result.ok and stale_result.error is not None
    assert stale_result.error.code == "stale_revision"
    assert not output.exists()


def test_idempotent_retry_and_conflict(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    request = _batch(
        source,
        output,
        [
            {
                "commandId": "p",
                "op": "set",
                "path": paragraph.path,
                "properties": {"text": "한 번만"},
            }
        ],
        idempotency_key="same-key",
    )
    store: dict[str, Any] = {}
    first = apply_document_commands(request, idempotency_store=store)
    replay = apply_document_commands(request, idempotency_store=store)
    assert first.ok and replay.ok
    assert replay.verification_report["idempotency"]["replayed"] is True
    assert replay.document_revision == first.document_revision

    conflict_request = dict(request)
    conflict_request["dryRun"] = True
    conflict = apply_document_commands(conflict_request, idempotency_store=store)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.code == "idempotency_conflict"


def test_vertical_merge_row_structure_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source, merged=True)
    with HwpxAgentDocument.open(source) as agent:
        row = next(record for record in agent.records if record.kind == "row")
    result = apply_document_commands(
        _batch(source, output, [{"commandId": "drop", "op": "remove", "path": row.path}])
    )
    assert not result.ok and result.error is not None
    assert result.error.code == "unsupported_content"
    assert not output.exists()


def test_required_domain_and_real_hancom_fail_honestly_when_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    request = _batch(
        source,
        output,
        [
            {
                "commandId": "p",
                "op": "set",
                "path": paragraph.path,
                "properties": {"text": "수정"},
            }
        ],
    )
    request["verificationRequirements"] = ["domain"]
    result = apply_document_commands(request)
    assert not result.ok and result.error is not None
    assert result.error.code == "verification_failed"
    assert not output.exists()


def test_complete_set_property_matrix_on_supported_node_kinds(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
        run = next(record for record in agent.records if record.parent_path == paragraph.path and record.kind == "run")
        table = _record(agent, "table", "201")
        row = next(record for record in agent.records if record.parent_path == table.path and record.kind == "row")
        cell = next(record for record in agent.records if record.parent_path == row.path and record.kind == "cell")
        field = _record(agent, "form-field", "601")
        picture = _record(agent, "picture", "402")
        memo = _record(agent, "memo", "301")
        footnote = _record(agent, "footnote", "501")
        endnote = _record(agent, "endnote", "502")
        shape = _record(agent, "shape", "401")
        style = str(paragraph.summary["style"])

    commands = [
        {
            "commandId": "paragraph",
            "op": "set",
            "path": paragraph.path,
            "properties": {
                "text": "속성 전체",
                "style": style,
                "alignment": "LEFT",
                "breakBefore": True,
                "keepWithNext": True,
                "lineSpacingPercent": 170,
            },
        },
        {
            "commandId": "run",
            "op": "set",
            "path": run.path,
            "properties": {
                "text": "실행 속성",
                "bold": True,
                "italic": True,
                "underline": True,
                "fontName": "함초롬돋움",
                "fontSizePt": 12,
                "color": "#123456",
            },
        },
        {
            "commandId": "table",
            "op": "set",
            "path": table.path,
            "properties": {"caption": "표 설명", "alignment": "RIGHT"},
        },
        {"commandId": "row", "op": "set", "path": row.path, "properties": {"heightMm": 15}},
        {
            "commandId": "cell",
            "op": "set",
            "path": cell.path,
            "properties": {
                "text": "셀 전체",
                "verticalAlignment": "CENTER",
                "backgroundColor": "#DDEEFF",
            },
        },
        {
            "commandId": "field",
            "op": "set",
            "path": field.path,
            "properties": {"value": "필드 전체", "readOnly": False},
        },
        {"commandId": "picture", "op": "set", "path": picture.path, "properties": {"altText": "그림 설명"}},
        {"commandId": "memo", "op": "set", "path": memo.path, "properties": {"text": "메모 수정"}},
        {"commandId": "foot", "op": "set", "path": footnote.path, "properties": {"text": "각주 수정"}},
        {"commandId": "end", "op": "set", "path": endnote.path, "properties": {"text": "미주 수정"}},
        {"commandId": "shape", "op": "set", "path": shape.path, "properties": {"altText": "도형 설명"}},
    ]
    result = apply_document_commands(_batch(source, output, commands))
    assert result.ok, result.to_dict()
    assert len(result.command_results) == len(commands)
    with HwpxAgentDocument.open(output) as agent:
        assert _record(agent, "paragraph", "101").summary["breakBefore"] is True
        assert _record(agent, "table", "201").summary["caption"] == "표 설명"
        assert _record(agent, "picture", "402").summary["altText"] == "그림 설명"
        assert _record(agent, "memo", "301").summary["text"] == "메모 수정"
        assert _record(agent, "footnote", "501").summary["text"] == "각주 수정"
        assert _record(agent, "endnote", "502").summary["text"] == "미주 수정"


@pytest.mark.parametrize("kind", ["run", "table", "picture", "memo", "footnote", "endnote", "shape"])
def test_remove_positive_matrix_for_every_supported_kind(tmp_path: Path, kind: str) -> None:
    source = tmp_path / f"{kind}-input.hwpx"
    output = tmp_path / f"{kind}-output.hwpx"
    _write_fixture(source)
    identities = {
        "table": "201",
        "picture": "402",
        "memo": "301",
        "footnote": "501",
        "endnote": "502",
        "shape": "401",
    }
    with HwpxAgentDocument.open(source) as agent:
        if kind == "run":
            paragraph = _record(agent, "paragraph", "101")
            target = next(
                record
                for record in agent.records
                if record.parent_path == paragraph.path and record.kind == "run"
            )
        else:
            target = _record(agent, kind, identities[kind])
    result = apply_document_commands(
        _batch(
            source,
            output,
            [{"commandId": "remove", "op": "remove", "path": target.path}],
            dry_run=True,
        )
    )
    assert result.ok, result.to_dict()
    assert result.semantic_diff["changes"][0]["afterPath"] is None
    assert not output.exists()


def test_move_table_picture_shape_and_row_preserves_native_ids(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        destination = _record(agent, "paragraph", "101")
        table = _record(agent, "table", "201")
        picture = _record(agent, "picture", "402")
        shape = _record(agent, "shape", "401")
        row = next(record for record in agent.records if record.parent_path == table.path and record.kind == "row")
    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "row",
                    "op": "move",
                    "path": row.path,
                    "parent": table.path,
                    "position": {"mode": "append"},
                },
                {"commandId": "table", "op": "move", "path": table.path, "parent": destination.path},
                {"commandId": "picture", "op": "move", "path": picture.path, "parent": destination.path},
                {"commandId": "shape", "op": "move", "path": shape.path, "parent": destination.path},
            ],
        )
    )
    assert result.ok, result.to_dict()
    assert 'table[@id="201"]' in result.command_results[1]["path"]
    assert 'picture[@id="402"]' in result.command_results[2]["path"]
    assert 'shape[@id="401"]' in result.command_results[3]["path"]


def test_copy_run_memo_notes_picture_and_shape_matrix(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        destination = _record(agent, "paragraph", "101")
        section = next(record for record in agent.records if record.kind == "section")
        source_paragraph = _record(agent, "paragraph", "102")
        run = next(
            record
            for record in agent.records
            if record.parent_path == source_paragraph.path and record.kind == "run"
        )
        memo = _record(agent, "memo", "301")
        footnote = _record(agent, "footnote", "501")
        endnote = _record(agent, "endnote", "502")
        picture = _record(agent, "picture", "402")
        shape = _record(agent, "shape", "401")
    commands = [
        {"commandId": "run", "op": "copy", "path": run.path, "parent": destination.path},
        {"commandId": "memo", "op": "copy", "path": memo.path, "parent": section.path},
        {"commandId": "foot", "op": "copy", "path": footnote.path, "parent": destination.path},
        {"commandId": "end", "op": "copy", "path": endnote.path, "parent": destination.path},
        {"commandId": "picture", "op": "copy", "path": picture.path, "parent": destination.path},
        {"commandId": "shape", "op": "copy", "path": shape.path, "parent": destination.path},
    ]
    result = apply_document_commands(_batch(source, output, commands))
    assert result.ok, result.to_dict()
    assert all(command["ok"] for command in result.command_results)
    assert result.verification_report["bytePreservation"]["addedMembers"] == []
    with HwpxAgentDocument.open(output) as agent:
        assert len([record for record in agent.records if record.kind == "memo"]) == 2
        assert len([record for record in agent.records if record.kind == "picture"]) == 2
        assert len([record for record in agent.records if record.kind == "shape"]) == 2


def test_copy_paragraph_preserves_merged_subtree_but_refreshes_ids(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source, merged=True)
    with HwpxAgentDocument.open(source) as agent:
        section = next(record for record in agent.records if record.kind == "section")
        paragraph = _record(agent, "paragraph", "102")
    result = apply_document_commands(
        _batch(
            source,
            output,
            [{"commandId": "copy", "op": "copy", "path": paragraph.path, "parent": section.path}],
        )
    )
    assert result.ok, result.to_dict()
    assert result.command_results[0]["generatedIdentities"]
    with HwpxAgentDocument.open(output) as agent:
        tables = [record for record in agent.records if record.kind == "table"]
        assert len(tables) == 2
        merged_cells = [
            record
            for record in agent.records
            if record.kind == "cell" and record.summary.get("rowSpan") == 2
        ]
        assert len(merged_cells) == 2


@pytest.mark.parametrize(
    ("path_kind", "operation"),
    [
        ("cell", "remove"),
        ("form-field", "copy"),
        ("run", "move"),
        ("memo", "move"),
    ],
)
def test_unsupported_operation_matrix_fails_before_output(
    tmp_path: Path, path_kind: str, operation: str
) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        target = next(record for record in agent.records if record.kind == path_kind)
        section = next(record for record in agent.records if record.kind == "section")
    command: dict[str, Any] = {"commandId": "bad", "op": operation, "path": target.path}
    if operation in {"move", "copy"}:
        command["parent"] = section.path
    result = apply_document_commands(_batch(source, output, [command]))
    assert not result.ok and result.error is not None
    assert result.error.code == "unsupported_operation"
    assert not output.exists()


def test_byte_preservation_receipt_and_corrupt_input_failure(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    command = {
        "commandId": "set",
        "op": "set",
        "path": paragraph.path,
        "properties": {"text": "바이트 영수증"},
    }
    result = apply_document_commands(_batch(source, output, [command]))
    assert result.ok, result.to_dict()
    byte_report = result.verification_report["bytePreservation"]
    assert byte_report["ok"] is True
    assert byte_report["unchangedMemberCount"] > 0
    assert "Contents/section0.xml" in byte_report["changedMembers"]

    corrupt = tmp_path / "corrupt.hwpx"
    corrupt.write_bytes(b"not-a-zip")
    corrupt_output = tmp_path / "corrupt-output.hwpx"
    bad = _batch(corrupt, corrupt_output, [command], expected_revision=_revision(corrupt))
    failed = apply_document_commands(bad)
    assert not failed.ok and failed.error is not None
    assert failed.error.code == "verification_failed"
    assert not corrupt_output.exists()


def test_same_path_idempotency_replay_precedes_stale_revision(tmp_path: Path) -> None:
    source = tmp_path / "in-place.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    request = _batch(
        source,
        source,
        [
            {
                "commandId": "set",
                "op": "set",
                "path": paragraph.path,
                "properties": {"text": "인플레이스 한 번"},
            }
        ],
        idempotency_key="in-place-key",
    )
    store: dict[str, Any] = {}
    first = apply_document_commands(request, idempotency_store=store)
    after_first = source.read_bytes()
    replay = apply_document_commands(request, idempotency_store=store)
    assert first.ok and replay.ok
    assert replay.verification_report["idempotency"]["replayed"] is True
    assert source.read_bytes() == after_first


def test_add_section_alias_and_page_geometry(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "section",
                    "op": "add",
                    "parent": "/",
                    "kind": "section",
                    "properties": {"pageWidthMm": 210, "pageHeightMm": 297},
                },
                {
                    "commandId": "paragraph",
                    "op": "add",
                    "parent": "$section.path",
                    "kind": "paragraph",
                    "properties": {"text": "새 섹션 문단"},
                },
            ],
        )
    )
    assert result.ok, result.to_dict()
    with HwpxAgentDocument.open(output) as agent:
        sections = [record for record in agent.records if record.kind == "section"]
        assert len(sections) == 2
        assert sections[-1].summary["pageWidthMm"] == pytest.approx(210, abs=0.01)
        assert sections[-1].summary["pageHeightMm"] == pytest.approx(297, abs=0.01)
        assert any(
            record.kind == "paragraph" and record.summary["text"] == "새 섹션 문단"
            for record in agent.records
        )


def test_dry_run_and_real_run_have_same_candidate_semantics(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    dry_output = tmp_path / "dry.hwpx"
    real_output = tmp_path / "real.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    command = {
        "commandId": "set",
        "op": "set",
        "path": paragraph.path,
        "properties": {"text": "동일 후보"},
    }
    dry_result = apply_document_commands(
        _batch(source, dry_output, [command], dry_run=True)
    )
    real_result = apply_document_commands(_batch(source, real_output, [command]))
    assert dry_result.ok and real_result.ok
    assert dry_result.document_revision == real_result.document_revision
    assert dry_result.semantic_diff == real_result.semantic_diff
    assert not dry_output.exists()
    assert real_output.exists()


def test_late_static_error_is_rejected_before_first_command(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        first = _record(agent, "paragraph", "101")
        second = _record(agent, "paragraph", "102")
    entered: list[int] = []

    def inject(stage: str, index: int | None) -> None:
        if stage == "before_command" and index is not None:
            entered.append(index)

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "valid",
                    "op": "set",
                    "path": first.path,
                    "properties": {"text": "실행되면 안 됨"},
                },
                {
                    "commandId": "invalid",
                    "op": "set",
                    "path": second.path,
                    "properties": {"notInCatalog": "거부"},
                },
            ],
        ),
        fault_injector=inject,
    )
    assert not result.ok and result.error is not None
    assert result.error.code == "unknown_property"
    assert entered == []
    assert not output.exists()


def test_required_domain_verifier_can_pass_and_real_hancom_requirement_cannot_blur(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.hwpx"
    domain_output = tmp_path / "domain.hwpx"
    visual_output = tmp_path / "visual.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
    command = {
        "commandId": "set",
        "op": "set",
        "path": paragraph.path,
        "properties": {"text": "검증"},
    }
    domain_request = _batch(source, domain_output, [command])
    domain_request["verificationRequirements"] = ["domain"]
    domain = apply_document_commands(
        domain_request,
        domain_verifier=lambda data, request: {
            "ok": data.startswith(b"PK"),
            "schemaVersion": request["schemaVersion"],
        },
    )
    assert domain.ok, domain.to_dict()
    assert domain.verification_report["domain"]["ok"] is True

    visual_request = _batch(source, visual_output, [command])
    visual_request["verificationRequirements"] = ["realHancom"]
    visual = apply_document_commands(
        visual_request,
        save_pipeline=SavePipeline(oracle=NullOracle()),
    )
    assert not visual.ok and visual.error is not None
    assert visual.error.code == "verification_failed"
    assert not visual_output.exists()


@pytest.mark.parametrize(
    ("property_name", "value"),
    [
        ("bold", "true"),
        ("fontSizePt", "12"),
        ("color", "red"),
    ],
)
def test_lossy_property_coercions_fail_closed(
    tmp_path: Path, property_name: str, value: object
) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")
        run = next(
            record
            for record in agent.records
            if record.parent_path == paragraph.path and record.kind == "run"
        )
    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "bad",
                    "op": "set",
                    "path": run.path,
                    "properties": {property_name: value},
                }
            ],
        )
    )
    assert not result.ok and result.error is not None
    assert result.error.code == "invalid_syntax"
    assert not output.exists()


@pytest.mark.parametrize("seed", range(8))
def test_deterministic_generated_command_sequences(seed: int, tmp_path: Path) -> None:
    source = tmp_path / f"input-{seed}.hwpx"
    output = tmp_path / f"output-{seed}.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        section = next(record for record in agent.records if record.kind == "section")
        paragraph = _record(agent, "paragraph", "101")
        cell = next(record for record in agent.records if record.kind == "cell")
    positions = (
        {"mode": "append"},
        {"mode": "prepend"},
        {"mode": "index", "index": 2},
    )
    commands = [
        {
            "commandId": "add",
            "op": "add",
            "parent": section.path,
            "kind": "paragraph",
            "properties": {"text": f"생성 {seed}"},
            "position": positions[seed % len(positions)],
        },
        {
            "commandId": "run",
            "op": "add",
            "parent": "$add.path",
            "kind": "run",
            "properties": {"text": f"-{seed}", "bold": bool(seed % 2)},
        },
        {
            "commandId": "copy",
            "op": "copy",
            "path": paragraph.path,
            "parent": section.path,
            "position": {"mode": "append"},
        },
        {
            "commandId": "cell",
            "op": "set",
            "path": cell.path,
            "properties": {"text": f"셀 {seed}"},
        },
    ]
    result = apply_document_commands(
        _batch(source, output, commands, dry_run=bool(seed % 2))
    )
    assert result.ok, result.to_dict()
    assert len(result.command_results) == len(commands)
    assert result.verification_report["openSafety"]["ok"] is True


def test_batch_invokes_save_pipeline_exactly_once(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _write_fixture(source)
    with HwpxAgentDocument.open(source) as agent:
        paragraph = _record(agent, "paragraph", "101")

    class CountingPipeline(SavePipeline):
        def __init__(self) -> None:
            super().__init__(oracle=NullOracle())
            self.calls = 0

        def run(self, *args: Any, **kwargs: Any):
            self.calls += 1
            return super().run(*args, **kwargs)

    pipeline = CountingPipeline()
    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "one",
                    "op": "set",
                    "path": paragraph.path,
                    "properties": {"text": "한 번 저장"},
                }
            ],
        ),
        save_pipeline=pipeline,
    )
    assert result.ok, result.to_dict()
    assert pipeline.calls == 1
