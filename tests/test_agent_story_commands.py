from __future__ import annotations

import copy
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.agent import AGENT_BATCH_SCHEMA, HwpxAgentDocument, apply_document_commands
from hwpx.agent.catalog import catalog_hash
from hwpx.agent.model import AgentContractError, agent_contract_manifest
from hwpx.agent.path import parse_path
from hwpx.agent.story import parse_header_story_path
from hwpx.oxml import HwpxOxmlDocument


_SEED = (
    Path(__file__).parent
    / "fixtures/fuzz_regressions/seed-000000-baseline.hwpx"
)
_BODY_BEFORE = "fuzz_s000000_replace_06_80202"
_CELL_BEFORE = "fuzz_s000000_builder_h0_00_53075"
_BOTH_BEFORE = "fuzz_s000000_header_01_40651"
_EVEN_BEFORE = "fuzz_s000000_header_09_71170"
_BOTH_PATH = '/section[1]/header[@page-type="BOTH"]'
_EVEN_PATH = '/section[1]/header[@page-type="EVEN"]'


def _revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_seed(path: Path) -> None:
    path.write_bytes(_SEED.read_bytes())


def _batch(
    source: Path,
    output: Path,
    commands: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    expected_revision: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": str(source)},
        "output": {"filename": str(output), "overwrite": True},
        "commands": commands,
        "expectedRevision": expected_revision or _revision(source),
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


def _body_and_cell_paths(source: Path) -> tuple[str, str]:
    with HwpxAgentDocument.open(source) as view:
        body = next(
            record
            for record in view.records
            if record.kind == "paragraph" and record.summary.get("text") == _BODY_BEFORE
        )
        cell = next(
            record
            for record in view.records
            if record.kind == "cell" and record.summary.get("text") == _CELL_BEFORE
        )
    return body.path, cell.path


def _local_name(element: Any) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _tree_snapshot(element: Any, *, ignore_text: bool = False) -> Any:
    local = _local_name(element)
    if local.lower() == "linesegarray":
        return None
    children = tuple(
        snapshot
        for child in element
        if (snapshot := _tree_snapshot(child, ignore_text=ignore_text)) is not None
    )
    text = None if ignore_text and local == "t" else element.text
    return (local, tuple(sorted(element.attrib.items())), text, children)


def _header_structure(header: Any) -> Any:
    return (
        _tree_snapshot(header.element, ignore_text=True),
        None
        if header.apply_element is None
        else _tree_snapshot(header.apply_element, ignore_text=True),
    )


def _header_mirrors(section: Any) -> dict[tuple[str | None, str], list[Any]]:
    mirrors: dict[tuple[str | None, str], list[Any]] = {}
    for element in section.element.iter():
        if _local_name(element) != "ctrl":
            continue
        for child in element:
            if _local_name(child) != "header":
                continue
            key = (child.get("id"), child.get("applyPageType", "BOTH"))
            mirrors.setdefault(key, []).append(_tree_snapshot(child))
    return mirrors


def _members(payload: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(payload)) as archive:
        return {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if not info.is_dir()
        }


def _three_story_commands(source: Path) -> list[dict[str, Any]]:
    body_path, cell_path = _body_and_cell_paths(source)
    return [
        {
            "commandId": "body",
            "op": "set",
            "path": body_path,
            "properties": {"text": "S-080 본문"},
        },
        {
            "commandId": "cell",
            "op": "set",
            "path": cell_path,
            "properties": {"text": "S-080 표 셀"},
        },
        {
            "commandId": "header",
            "op": "set",
            "path": _BOTH_PATH,
            "properties": {"text": "S-080 머리글"},
        },
    ]


def test_private_story_path_keeps_public_catalog_and_projection_frozen() -> None:
    manifest = json.dumps(
        agent_contract_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert catalog_hash() == (
        "sha256:e1991f8cf51f9aa5f63f2d70139f98b7d418d16c3b80519cc7bae64eee1dc5f5"
    )
    assert hashlib.sha256(manifest).hexdigest() == (
        "1a0f31dd9468be8d4ba619e7651dfd7845148d3b99f19d1e5fa5bd79934377fd"
    )

    with pytest.raises(AgentContractError) as id_error:
        parse_path('/section[1]/header[@id="943624428"]')
    assert id_error.value.code == "unknown_kind"
    with pytest.raises(AgentContractError):
        parse_path(_BOTH_PATH)

    assert parse_header_story_path(_BOTH_PATH).canonical == _BOTH_PATH
    assert (
        parse_header_story_path('/section[01]/header[@id="943624428"]').canonical
        == '/section[1]/header[@id="943624428"]'
    )
    with HwpxAgentDocument.open(_SEED) as view:
        assert all(record.kind != "header" for record in view.records)
        with pytest.raises(AgentContractError):
            view.get(_BOTH_PATH)


def test_body_table_header_batch_preserves_structure_and_even_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _copy_seed(source)
    source_data = source.read_bytes()
    with HwpxDocument.open(source_data) as document:
        section = document.sections[0]
        both = section.properties.get_header("BOTH")
        even = section.properties.get_header("EVEN")
        assert both is not None and even is not None
        both_id = both.id
        both_structure = _header_structure(both)
        even_structure = _header_structure(even)
        even_mirrors = _header_mirrors(section)
        assert (even.id, "EVEN") in even_mirrors

    serialize_calls = 0
    original_serialize = HwpxOxmlDocument.serialize

    def counted_serialize(document: HwpxOxmlDocument) -> dict[str, bytes]:
        nonlocal serialize_calls
        serialize_calls += 1
        return original_serialize(document)

    monkeypatch.setattr(HwpxOxmlDocument, "serialize", counted_serialize)
    result = apply_document_commands(
        _batch(source, output, _three_story_commands(source))
    )

    assert result.ok, result.to_dict()
    assert serialize_calls == 1
    assert result.rolled_back is False
    assert result.command_results[2]["path"] == _BOTH_PATH
    assert result.command_results[2]["stableId"] == f"header:{both_id}"
    assert result.command_results[2]["changedProperties"] == {
        "text": {"before": _BOTH_BEFORE, "after": "S-080 머리글"}
    }
    assert result.semantic_diff["changes"][2]["afterPath"] == _BOTH_PATH
    story_receipt = result.verification_report["storyPreservation"]
    assert story_receipt == {
        "schemaVersion": "hwpx.agent-story-preservation/v1",
        "ok": True,
        "storyCount": 1,
        "stories": [
            {
                "commandId": "header",
                "path": _BOTH_PATH,
                "stableId": f"header:{both_id}",
                "pageType": "BOTH",
                "textMatched": True,
            }
        ],
    }
    byte_report = result.verification_report["bytePreservation"]
    assert byte_report["changedMembers"] == ["Contents/section0.xml"]
    assert byte_report["addedMembers"] == []
    assert byte_report["removedMembers"] == []
    assert validate_editor_open_safety(output).ok

    source_members = _members(source_data)
    output_members = _members(output.read_bytes())
    assert set(source_members) == set(output_members)
    assert all(
        source_members[name] == output_members[name]
        for name in source_members
        if name != "Contents/section0.xml"
    )
    with HwpxDocument.open(output) as reopened:
        section = reopened.sections[0]
        both = section.properties.get_header("BOTH")
        even = section.properties.get_header("EVEN")
        assert both is not None and even is not None
        assert both.text == "S-080 머리글"
        assert both.id == both_id
        assert _header_structure(both) == both_structure
        assert even.text == _EVEN_BEFORE
        assert _header_structure(even) == even_structure
        assert _header_mirrors(section).get((even.id, "EVEN")) == even_mirrors[
            (even.id, "EVEN")
        ]
        assert section.paragraphs[1].text == "S-080 본문"
        assert section.paragraphs[3].tables[0].cell(0, 0).text == "S-080 표 셀"


def test_header_story_dry_run_matches_apply_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    dry_output = tmp_path / "dry.hwpx"
    real_output = tmp_path / "real.hwpx"
    _copy_seed(source)
    before = source.read_bytes()
    command = {
        "commandId": "header",
        "op": "set",
        "path": _BOTH_PATH,
        "properties": {"text": "동일 후보"},
    }

    dry_result = apply_document_commands(
        _batch(source, dry_output, [command], dry_run=True)
    )
    real_result = apply_document_commands(_batch(source, real_output, [command]))

    assert dry_result.ok and real_result.ok
    assert dry_result.document_revision == real_result.document_revision
    assert dry_result.semantic_diff == real_result.semantic_diff
    assert dry_result.command_results == real_result.command_results
    assert (
        dry_result.verification_report["storyPreservation"]
        == real_result.verification_report["storyPreservation"]
    )
    assert source.read_bytes() == before
    assert not dry_output.exists()
    assert real_output.exists()


def test_native_id_header_story_path_applies_and_remains_stable(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _copy_seed(source)
    with HwpxDocument.open(source) as document:
        header = document.sections[0].properties.get_header("BOTH")
        assert header is not None and header.id is not None
        header_id = header.id
    path = f'/section[1]/header[@id="{header_id}"]'

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "header",
                    "op": "set",
                    "path": path,
                    "properties": {"text": "ID 경로 수정"},
                }
            ],
        )
    )

    assert result.ok, result.to_dict()
    assert result.command_results[0]["path"] == path
    assert result.command_results[0]["stableId"] == f"header:{header_id}"
    assert result.verification_report["storyPreservation"]["stories"][0]["path"] == path
    with HwpxDocument.open(output) as reopened:
        updated = reopened.sections[0].properties.get_header("BOTH")
        assert updated is not None and updated.id == header_id
        assert updated.text == "ID 경로 수정"


@pytest.mark.parametrize("fault_index", [0, 1, 2])
def test_fault_after_each_story_batch_command_preserves_existing_output(
    tmp_path: Path, fault_index: int
) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "existing-output.hwpx"
    _copy_seed(source)
    existing = b"pre-existing output must survive"
    output.write_bytes(existing)

    def inject(stage: str, index: int | None) -> None:
        if stage == "after_command" and index == fault_index:
            raise RuntimeError("injected story transaction failure")

    result = apply_document_commands(
        _batch(source, output, _three_story_commands(source)),
        fault_injector=inject,
    )

    assert not result.ok
    assert result.rolled_back
    assert result.error is not None and result.error.code == "verification_failed"
    assert output.read_bytes() == existing


def test_header_story_idempotency_stale_revision_and_alias_stability(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    stale_output = tmp_path / "stale.hwpx"
    _copy_seed(source)
    request = _batch(
        source,
        output,
        [
            {
                "commandId": "first",
                "op": "set",
                "path": _BOTH_PATH,
                "properties": {"text": "첫 수정"},
            },
            {
                "commandId": "second",
                "op": "set",
                "path": "$first.path",
                "properties": {"text": "최종 수정"},
            },
        ],
        idempotency_key="story-retry-key",
    )
    store: dict[str, Any] = {}

    first = apply_document_commands(request, idempotency_store=store)
    output_after_first = output.read_bytes()
    replay = apply_document_commands(request, idempotency_store=store)

    assert first.ok and replay.ok
    assert first.command_results[0]["path"] == _BOTH_PATH
    assert first.command_results[1]["path"] == _BOTH_PATH
    assert first.command_results[0]["stableId"] == first.command_results[1]["stableId"]
    assert replay.verification_report["idempotency"]["replayed"] is True
    assert output.read_bytes() == output_after_first
    with HwpxDocument.open(output) as reopened:
        header = reopened.sections[0].properties.get_header("BOTH")
        assert header is not None and header.text == "최종 수정"

    conflict_request = copy.deepcopy(request)
    conflict_request["dryRun"] = True
    conflict = apply_document_commands(conflict_request, idempotency_store=store)
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.code == "idempotency_conflict"

    stale = _batch(
        source,
        stale_output,
        [
            {
                "commandId": "header",
                "op": "set",
                "path": _BOTH_PATH,
                "properties": {"text": "적용 금지"},
            }
        ],
        expected_revision="sha256:" + "0" * 64,
    )
    stale_result = apply_document_commands(stale)
    assert not stale_result.ok and stale_result.error is not None
    assert stale_result.error.code == "stale_revision"
    assert not stale_output.exists()


def test_header_story_rejects_non_set_missing_ambiguous_and_rich_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.hwpx"
    _copy_seed(source)
    with HwpxDocument.open(source) as document:
        view = HwpxAgentDocument.from_document(document, revision=_revision(source))
        with pytest.raises(AgentContractError) as missing:
            view._resolve_header_story('/section[1]/header[@page-type="ODD"]')
        assert missing.value.code == "not_found"

        section = document.sections[0]
        both = section.properties.get_header("BOTH")
        assert both is not None and both.apply_element is not None
        duplicate = copy.deepcopy(both.element)
        duplicate.set("id", "duplicate-header-id")
        duplicate_apply = copy.deepcopy(both.apply_element)
        for name in ("idRef", "headerIDRef", "headerIdRef", "headerRef"):
            if name in duplicate_apply.attrib:
                duplicate_apply.set(name, "duplicate-header-id")
        section.properties.element.append(duplicate)
        section.properties.element.append(duplicate_apply)
        ambiguous_view = HwpxAgentDocument.from_document(
            document, revision=_revision(source)
        )
        with pytest.raises(AgentContractError) as ambiguous:
            ambiguous_view._resolve_header_story(_BOTH_PATH)
        assert ambiguous.value.code == "ambiguous_target"

    remove_output = tmp_path / "remove.hwpx"
    removed = apply_document_commands(
        _batch(
            source,
            remove_output,
            [{"commandId": "remove", "op": "remove", "path": _BOTH_PATH}],
        )
    )
    assert not removed.ok and removed.error is not None
    assert removed.error.code == "unsupported_operation"
    assert not remove_output.exists()

    property_output = tmp_path / "unknown-property.hwpx"
    invalid_property = apply_document_commands(
        _batch(
            source,
            property_output,
            [
                {
                    "commandId": "header",
                    "op": "set",
                    "path": _BOTH_PATH,
                    "properties": {"text": "수정 금지", "alignment": "CENTER"},
                }
            ],
        )
    )
    assert not invalid_property.ok and invalid_property.error is not None
    assert invalid_property.error.code == "unknown_property"
    assert not property_output.exists()

    rich_source = tmp_path / "rich.hwpx"
    rich_output = tmp_path / "rich-output.hwpx"
    with HwpxDocument.open(source) as document:
        header = document.sections[0].properties.get_header("BOTH")
        assert header is not None
        header.add_run("추가 서식 런", bold=True)
        rich_source.write_bytes(document.to_bytes())
    rich_result = apply_document_commands(
        _batch(
            rich_source,
            rich_output,
            [
                {
                    "commandId": "header",
                    "op": "set",
                    "path": _BOTH_PATH,
                    "properties": {"text": "평탄화 금지"},
                }
            ],
        )
    )
    assert not rich_result.ok and rich_result.error is not None
    assert rich_result.error.code == "unsupported_content"
    assert not rich_output.exists()

    mirror_source = tmp_path / "ambiguous-mirror.hwpx"
    mirror_output = tmp_path / "ambiguous-mirror-output.hwpx"
    with HwpxDocument.open(source) as document:
        section = document.sections[0]
        header = section.properties.get_header("BOTH")
        assert header is not None and header.id is not None
        header.set_simple_text_preserving("mirrored")
        target_control = next(
            control
            for run in section.element.iter()
            if _local_name(run) == "run"
            for control in run
            if _local_name(control) == "ctrl"
            if any(
                _local_name(story) == "header" and story.get("id") == header.id
                for story in control
            )
        )
        target_run = next(
            run
            for run in section.element.iter()
            if _local_name(run) == "run" and target_control in list(run)
        )
        target_run.append(copy.deepcopy(target_control))
        mirror_source.write_bytes(document.to_bytes())
    ambiguous_result = apply_document_commands(
        _batch(
            mirror_source,
            mirror_output,
            [
                {
                    "commandId": "header",
                    "op": "set",
                    "path": _BOTH_PATH,
                    "properties": {"text": "모호성 거부"},
                }
            ],
        )
    )
    assert not ambiguous_result.ok and ambiguous_result.error is not None
    assert ambiguous_result.error.code == "ambiguous_target"
    assert not mirror_output.exists()


def test_multisection_header_edit_preserves_other_section_and_story(
    tmp_path: Path,
) -> None:
    source = tmp_path / "multi.hwpx"
    output = tmp_path / "multi-output.hwpx"
    with HwpxDocument.new() as document:
        first = document.sections[0]
        first.paragraphs[0].text = "첫 섹션 본문"
        document.set_header_text("첫 섹션 머리글", section=first, page_type="BOTH")
        second = document.add_section()
        second.paragraphs[0].text = "둘째 섹션 본문"
        document.set_header_text("둘째 섹션 머리글", section=second, page_type="BOTH")
        source.write_bytes(document.to_bytes())
    before_members = _members(source.read_bytes())

    result = apply_document_commands(
        _batch(
            source,
            output,
            [
                {
                    "commandId": "header",
                    "op": "set",
                    "path": _BOTH_PATH,
                    "properties": {"text": "첫 섹션만 수정"},
                }
            ],
        )
    )

    assert result.ok, result.to_dict()
    assert result.verification_report["bytePreservation"]["changedMembers"] == [
        "Contents/section0.xml"
    ]
    after_members = _members(output.read_bytes())
    assert after_members["Contents/section1.xml"] == before_members["Contents/section1.xml"]
    with HwpxDocument.open(output) as reopened:
        first_header = reopened.sections[0].properties.get_header("BOTH")
        second_header = reopened.sections[1].properties.get_header("BOTH")
        assert first_header is not None and first_header.text == "첫 섹션만 수정"
        assert second_header is not None and second_header.text == "둘째 섹션 머리글"
        assert reopened.sections[1].paragraphs[0].text == "둘째 섹션 본문"
