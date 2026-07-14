from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.agent import AGENT_BATCH_SCHEMA, HwpxAgentDocument
from hwpx.agent.blueprint import read_blueprint_bundle
from hwpx.agent.cli import (
    EXIT_CONFLICT,
    EXIT_OK,
    EXIT_TARGET,
    EXIT_USAGE,
    EXIT_VERIFICATION,
    main,
)


def _fixture(path: Path) -> None:
    with HwpxDocument.new() as document:
        first = document.sections[0].paragraphs[0]
        first.element.set("id", "101")
        first.text = "평가 계획"
        second = document.add_paragraph("평가 방법")
        second.element.set("id", "102")
        table = second.add_table(1, 2)
        table.element.set("id", "201")
        table.rows[0].cells[0].text = "항목"
        table.rows[0].cells[1].text = "내용"
        document.save_to_path(path)


def _revision(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(argv: list[str], stdin_text: str = "") -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(
        argv,
        stdin=io.StringIO(stdin_text),
        stdout=stdout,
        stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


class _BinaryStdout:
    def __init__(self) -> None:
        self.buffer = self
        self.data = bytearray()

    def write(self, value: bytes | str) -> int:
        encoded = value.encode("utf-8") if isinstance(value, str) else value
        self.data.extend(encoded)
        return len(encoded)

    def flush(self) -> None:
        return None


def _path(source: Path, kind: str, identity: str) -> str:
    with HwpxAgentDocument.open(source) as agent:
        return next(
            record.path
            for record in agent.records
            if record.kind == kind and record.attributes.get("id") == identity
        )


def _batch(source: Path, output: Path, command: dict) -> dict:
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": str(source)},
        "output": {"filename": str(output), "overwrite": True},
        "commands": [command],
        "expectedRevision": _revision(source),
        "idempotencyKey": None,
        "dryRun": False,
        "quality": "transparent",
        "verificationRequirements": ["package", "reopen", "openSafety"],
    }


def test_help_human_and_json_come_from_shared_catalog() -> None:
    code, human, error = _run(["help", "paragraph"])
    assert code == EXIT_OK and error == ""
    assert "editable: text, style, alignment" in human
    code, payload, error = _run(["help", "paragraph", "--json"])
    assert code == EXIT_OK and error == ""
    parsed = json.loads(payload)
    assert parsed["nodeKinds"]["paragraph"]["operations"] == [
        "set",
        "add",
        "remove",
        "move",
        "copy",
    ]

    code, payload, error = _run(["help", "blueprint", "--json"])
    assert code == EXIT_OK and error == ""
    blueprint = json.loads(payload)
    assert blueprint["surfaces"] == {"cli": ["dump", "replay"], "mcpMaximumTools": 2}


def test_blueprint_dump_inspect_repack_and_binary_stdout_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    first = tmp_path / "first.hwpxbp"
    second = tmp_path / "second.hwpxbp"
    repacked = tmp_path / "repacked.hwpxbp"
    manifest_path = tmp_path / "manifest.json"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")

    for output in (first, second):
        code, payload, error = _run(
            [
                "dump",
                str(source),
                "--path",
                paragraph,
                "--output",
                str(output),
                "--expected-revision",
                _revision(source),
            ]
        )
        assert code == EXIT_OK and error == ""
        assert json.loads(payload)["outputFilename"] == str(output)
    assert first.read_bytes() == second.read_bytes()

    code, payload, error = _run(["dump", "--inspect", str(first)])
    assert code == EXIT_OK and error == ""
    inspected = json.loads(payload)
    manifest_path.write_text(json.dumps(inspected["manifest"], ensure_ascii=False), encoding="utf-8")
    code, payload, error = _run(
        [
            "dump",
            "--repack",
            str(first),
            "--manifest",
            str(manifest_path),
            "--output",
            str(repacked),
        ]
    )
    assert code == EXIT_OK and error == ""
    assert json.loads(payload)["blueprintHash"] == inspected["blueprintHash"]
    assert repacked.read_bytes() == first.read_bytes()

    binary = _BinaryStdout()
    stderr = io.StringIO()
    code = main(
        ["dump", str(source), "--path", paragraph, "--output", "-"],
        stdin=io.StringIO(),
        stdout=binary,  # type: ignore[arg-type]
        stderr=stderr,
    )
    assert code == EXIT_OK and stderr.getvalue() == ""
    assert read_blueprint_bundle(bytes(binary.data)).manifest["blueprintHash"] == inspected["blueprintHash"]


def test_blueprint_replay_reads_request_from_stdin_and_commits_atomically(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    bundle = tmp_path / "block.hwpxbp"
    target = tmp_path / "target.hwpx"
    output = tmp_path / "output.hwpx"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")
    code, payload, error = _run(
        ["dump", str(source), "--path", paragraph, "--output", str(bundle)]
    )
    assert code == EXIT_OK and error == ""
    blueprint_hash = json.loads(payload)["blueprintHash"]
    with HwpxDocument.new() as document:
        document.sections[0].paragraphs[0].text = "TARGET"
        document.save_to_path(target)
    request = {
        "schemaVersion": "hwpx.agent-blueprint-replay/v1",
        "bundle": {"filename": str(bundle), "blueprintHash": blueprint_hash},
        "target": {"input": str(target), "output": str(output), "overwrite": False},
        "targetParent": "/section[1]",
        "position": {"mode": "append"},
        "mode": "portable",
        "mappingPolicy": {"strict": True},
        "expectedRevision": _revision(target),
        "idempotencyKey": "cli-blueprint-1",
        "dryRun": False,
        "quality": "transparent",
        "verificationRequirements": [
            "package",
            "reopen",
            "openSafety",
            "semanticDiff",
            "bytePreservation",
        ],
    }
    code, payload, error = _run(["replay", "-"], json.dumps(request, ensure_ascii=False))
    assert code == EXIT_OK and error == ""
    result = json.loads(payload)
    assert result["ok"] is True
    assert result["verificationReport"]["savePipeline"]["ok"] is True
    assert result["verificationReport"]["openSafety"]["ok"] is True
    assert output.exists()


def test_view_get_query_json_and_human(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)
    paragraph_path = _path(source, "paragraph", "101")

    code, payload, error = _run(["view", str(source), "--depth", "2"])
    assert code == EXIT_OK and error == ""
    assert json.loads(payload)["kind"] == "document"

    code, human, error = _run(["get", str(source), paragraph_path, "--format", "human"])
    assert code == EXIT_OK and error == ""
    assert "paragraph" in human and "평가 계획" in human

    code, payload, error = _run(
        ["query", str(source), 'paragraph:contains("평가")', "--limit", "10"]
    )
    assert code == EXIT_OK and error == ""
    result = json.loads(payload)
    assert len(result["nodes"]) == 2
    assert result["truncated"] is False


def test_single_set_command_writes_verified_output(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _fixture(source)
    paragraph_path = _path(source, "paragraph", "101")
    code, payload, error = _run(
        [
            "set",
            str(source),
            str(output),
            paragraph_path,
            "--properties",
            '{"text":"CLI 수정","alignment":"CENTER"}',
            "--expected-revision",
            _revision(source),
        ]
    )
    assert code == EXIT_OK and error == ""
    result = json.loads(payload)
    assert result["ok"] is True
    assert result["verificationReport"]["savePipeline"]["ok"] is True
    with HwpxAgentDocument.open(output) as agent:
        assert agent.resolve_record(paragraph_path).summary["text"] == "CLI 수정"


def test_single_add_move_copy_remove_commands_are_available(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)
    section = "/section[1]"
    paragraph = _path(source, "paragraph", "101")
    commands = [
        [
            "add",
            str(source),
            str(tmp_path / "add.hwpx"),
            section,
            "paragraph",
            "--properties",
            '{"text":"추가"}',
            "--dry-run",
        ],
        [
            "move",
            str(source),
            str(tmp_path / "move.hwpx"),
            paragraph,
            section,
            "--dry-run",
        ],
        [
            "copy",
            str(source),
            str(tmp_path / "copy.hwpx"),
            paragraph,
            section,
            "--dry-run",
        ],
        [
            "remove",
            str(source),
            str(tmp_path / "remove.hwpx"),
            paragraph,
            "--dry-run",
        ],
    ]
    for argv in commands:
        code, payload, error = _run(argv)
        assert code == EXIT_OK, (argv, payload, error)
        assert json.loads(payload)["dryRun"] is True


def test_batch_json_file_and_stdin_are_replayable(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    replay = tmp_path / "replay.hwpx"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")
    request = _batch(
        source,
        output,
        {
            "commandId": "set",
            "op": "set",
            "path": paragraph,
            "properties": {"text": "JSON 파일"},
        },
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    code, payload, error = _run(["batch", str(request_path)])
    assert code == EXIT_OK and error == "" and json.loads(payload)["ok"] is True

    request["output"]["filename"] = str(replay)
    code, payload, error = _run(["batch", "-"], json.dumps(request, ensure_ascii=False))
    assert code == EXIT_OK and error == "" and json.loads(payload)["ok"] is True


def test_command_only_jsonl_combines_into_one_atomic_batch(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")
    lines = "\n".join(
        json.dumps(command, ensure_ascii=False)
        for command in [
            {
                "commandId": "set",
                "op": "set",
                "path": paragraph,
                "properties": {"text": "JSONL"},
            },
            {
                "commandId": "copy",
                "op": "copy",
                "path": paragraph,
                "parent": "/section[1]",
            },
        ]
    )
    code, payload, error = _run(
        [
            "batch",
            "-",
            "--jsonl-input",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        lines,
    )
    assert code == EXIT_OK and error == ""
    result = json.loads(payload)
    assert result["ok"] is True and len(result["commandResults"]) == 2


def test_jsonl_batch_stream_emits_one_result_per_line(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")
    requests = []
    for index in range(2):
        request = _batch(
            source,
            tmp_path / f"out-{index}.hwpx",
            {
                "commandId": "set",
                "op": "set",
                "path": paragraph,
                "properties": {"text": f"결과 {index}"},
            },
        )
        requests.append(json.dumps(request, ensure_ascii=False))
    code, payload, error = _run(
        ["batch", "-", "--jsonl-input", "--format", "jsonl"],
        "\n".join(requests),
    )
    assert code == EXIT_OK and error == ""
    assert len([json.loads(line) for line in payload.splitlines()]) == 2


def test_multiple_batch_requests_in_json_mode_emit_valid_array(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)
    paragraph = _path(source, "paragraph", "101")
    requests = [
        _batch(
            source,
            tmp_path / f"out-{index}.hwpx",
            {
                "commandId": "set",
                "op": "set",
                "path": paragraph,
                "properties": {"text": f"배열 {index}"},
            },
        )
        for index in range(2)
    ]
    code, payload, error = _run(["batch", "-"], json.dumps(requests, ensure_ascii=False))
    assert code == EXIT_OK and error == ""
    assert len(json.loads(payload)) == 2


def test_properties_can_be_loaded_from_at_file(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    output = tmp_path / "output.hwpx"
    props = tmp_path / "props.json"
    _fixture(source)
    props.write_text('{"text":"파일 속성"}', encoding="utf-8")
    code, payload, error = _run(
        [
            "set",
            str(source),
            str(output),
            _path(source, "paragraph", "101"),
            "--properties",
            f"@{props}",
        ]
    )
    assert code == EXIT_OK and error == "" and json.loads(payload)["ok"] is True


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_error"),
    [
        (["batch", "-"], EXIT_USAGE, "invalid_syntax"),
        (["help", "not-a-kind", "--json"], EXIT_USAGE, "invalid_syntax"),
    ],
)
def test_cli_usage_errors_are_structured(
    argv: list[str], expected_code: int, expected_error: str
) -> None:
    code, output, error = _run(argv, "not-json")
    assert code == expected_code and output == ""
    assert json.loads(error)["error"]["code"] == expected_error


def test_target_conflict_and_verification_exit_codes(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)

    code, output, error = _run(["get", str(source), "/section[99]"])
    assert code == EXIT_TARGET and output == ""
    assert json.loads(error)["error"]["code"] == "not_found"

    paragraph = _path(source, "paragraph", "101")
    code, payload, error = _run(
        [
            "set",
            str(source),
            str(tmp_path / "stale.hwpx"),
            paragraph,
            "--properties",
            '{"text":"stale"}',
            "--expected-revision",
            "sha256:" + "0" * 64,
        ]
    )
    assert code == EXIT_CONFLICT and error == ""
    assert json.loads(payload)["error"]["code"] == "stale_revision"

    existing = tmp_path / "exists.hwpx"
    existing.write_bytes(b"occupied")
    code, payload, error = _run(
        [
            "set",
            str(source),
            str(existing),
            paragraph,
            "--properties",
            '{"text":"blocked"}',
        ]
    )
    assert code == EXIT_VERIFICATION and error == ""
    assert json.loads(payload)["ok"] is False


def test_human_mutation_output_and_help_exit(tmp_path: Path) -> None:
    source = tmp_path / "input.hwpx"
    _fixture(source)
    code, output, error = _run(
        [
            "set",
            str(source),
            str(tmp_path / "dry.hwpx"),
            _path(source, "paragraph", "101"),
            "--properties",
            '{"text":"human"}',
            "--dry-run",
            "--format",
            "human",
        ]
    )
    assert code == EXIT_OK and error == ""
    assert output.startswith("DRY-RUN: 1 command(s)")

    code, output, error = _run(["view", "--help"])
    assert code == EXIT_OK
    assert "usage: hwpx view" in output
    assert error == ""


def test_pyproject_adds_hwpx_without_removing_legacy_scripts() -> None:
    text = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    for script in (
        'hwpx = "hwpx.agent.cli:main"',
        'hwpx-unpack = "hwpx.tools.archive_cli:unpack_main"',
        'hwpx-pack = "hwpx.tools.archive_cli:pack_main"',
        'hwpx-validate = "hwpx.tools.validator:main"',
        'hwpx-conformance = "hwpx.conformance.runner:main"',
    ):
        assert script in text
