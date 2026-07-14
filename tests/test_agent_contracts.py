# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json

import pytest

from hwpx.agent.model import (
    AGENT_BATCH_SCHEMA,
    AGENT_NODE_SCHEMA,
    AgentBatchResult,
    AgentContractError,
    AgentError,
    AgentNode,
    NODE_PROPERTY_CATALOG_V1,
    agent_contract_manifest,
    validate_agent_batch,
    validate_agent_command,
)

REVISION = "sha256:" + "a" * 64


def _node(kind: str = "paragraph", **changes: object) -> AgentNode:
    catalog = NODE_PROPERTY_CATALOG_V1[kind]
    values: dict[str, object] = {
        "kind": kind,
        "path": '/section[1]/paragraph[@id="173821"]',
        "stable_id": "paragraph:173821",
        "stability": "native",
        "summary": {"text": "평가 방법", "style": "개요 1"},
        "child_count": 0,
        "readable_properties": catalog["readable"],
        "editable_properties": catalog["editable"],
        "operations": catalog["operations"],
        "revision": REVISION,
    }
    values.update(changes)
    return AgentNode(**values)  # type: ignore[arg-type]


def _batch(commands: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": "input.hwpx"},
        "output": {"filename": "output.hwpx", "overwrite": False},
        "commands": commands,
        "expectedRevision": REVISION,
        "idempotencyKey": "agent-contract-test-1",
        "dryRun": True,
        "quality": "transparent",
        "verificationRequirements": ["package", "reopen", "openSafety", "semanticDiff"],
    }


def test_agent_node_golden_shape_is_bounded_and_explicit() -> None:
    node = _node()
    assert node.to_dict() == {
        "schemaVersion": AGENT_NODE_SCHEMA,
        "kind": "paragraph",
        "path": '/section[1]/paragraph[@id="173821"]',
        "stableId": "paragraph:173821",
        "stability": "native",
        "volatilePath": False,
        "summary": {"text": "평가 방법", "style": "개요 1"},
        "childCount": 0,
        "children": [],
        "coverage": {
            "supportedChildren": 0,
            "unsupportedChildren": 0,
            "truncatedChildren": 0,
        },
        "readableProperties": list(NODE_PROPERTY_CATALOG_V1["paragraph"]["readable"]),
        "editableProperties": list(NODE_PROPERTY_CATALOG_V1["paragraph"]["editable"]),
        "operations": ["set", "add", "remove", "move", "copy"],
        "revision": REVISION,
    }


def test_positional_node_is_honestly_volatile() -> None:
    run = _node(
        "run",
        path='/section[1]/paragraph[@id="173821"]/run[1]',
        stable_id=None,
        stability="positional",
        summary={"text": "평가"},
    )
    assert run.to_dict()["volatilePath"] is True
    with pytest.raises(AgentContractError, match="cannot claim stableId"):
        _node("run", stable_id="run:1", stability="positional")


def test_node_child_coverage_is_exact_and_path_cannot_be_command_alias() -> None:
    with pytest.raises(AgentContractError, match="coverage must equal"):
        _node(child_count=2, truncated_child_count=1)
    with pytest.raises(AgentContractError, match="canonical path"):
        _node(path="$copy-source.path")


@pytest.mark.parametrize(
    "command",
    [
        {
            "commandId": "set-title",
            "op": "set",
            "path": '/section[1]/paragraph[@id="173821"]',
            "properties": {"text": "수정된 평가 방법", "style": "개요 2"},
        },
        {
            "commandId": "add-row",
            "op": "add",
            "parent": '/section[1]/paragraph[@id="173821"]/table[@id="91"]',
            "kind": "row",
            "properties": {"cells": ["항목", "값"]},
            "position": {"mode": "index", "index": 2},
        },
        {"commandId": "remove-placeholder", "op": "remove", "path": "/section[1]/paragraph[8]"},
        {
            "commandId": "move-table",
            "op": "move",
            "path": '/section[1]/paragraph[@id="173821"]/table[@id="91"]',
            "parent": "/section[1]",
            "position": {"mode": "before", "path": '/section[1]/paragraph[@id="442"]'},
        },
        {
            "commandId": "copy-table",
            "op": "copy",
            "path": '$move-table.path',
            "parent": "/section[1]",
            "position": {"mode": "after", "path": '/section[1]/paragraph[@id="442"]'},
        },
    ],
)
def test_command_union_accepts_only_frozen_shapes(command: dict[str, object]) -> None:
    normalized = validate_agent_command(command)
    assert normalized["commandId"] == command["commandId"]
    assert normalized["op"] == command["op"]


def test_batch_accepts_prior_alias_and_preserves_one_based_position() -> None:
    batch = _batch(
        [
            {
                "commandId": "copy-source",
                "op": "copy",
                "path": '/section[1]/paragraph[@id="173821"]',
                "parent": "/section[1]",
                "position": {"mode": "index", "index": 2},
            },
            {
                "commandId": "set-copy",
                "op": "set",
                "path": "$copy-source.path",
                "properties": {"text": "복사본"},
            },
        ]
    )
    normalized = validate_agent_batch(batch)
    assert normalized["commands"][0]["position"] == {"mode": "index", "index": 2}
    assert normalized["commands"][1]["path"] == "$copy-source.path"


def test_batch_rejects_forward_alias_duplicate_ids_and_zero_index() -> None:
    with pytest.raises(AgentContractError, match="earlier command"):
        validate_agent_batch(
            _batch(
                [
                    {"commandId": "first", "op": "set", "path": "$later.path", "properties": {"text": "x"}},
                    {"commandId": "later", "op": "remove", "path": "/section[1]/paragraph[1]"},
                ]
            )
        )
    with pytest.raises(AgentContractError, match="must be unique"):
        validate_agent_batch(
            _batch(
                [
                    {"commandId": "same", "op": "remove", "path": "/section[1]/paragraph[1]"},
                    {"commandId": "same", "op": "remove", "path": "/section[1]/paragraph[2]"},
                ]
            )
        )
    with pytest.raises(AgentContractError, match="one-based"):
        validate_agent_command(
            {
                "commandId": "bad-index",
                "op": "move",
                "path": "/section[1]/paragraph[1]",
                "parent": "/section[1]",
                "position": {"mode": "index", "index": 0},
            }
        )


@pytest.mark.parametrize("key", ["rawXml", "xpath", "namespaceUri", "packagePath"])
def test_contract_rejects_raw_xml_and_package_escape_hatches(key: str) -> None:
    with pytest.raises(AgentContractError) as exc:
        validate_agent_command(
            {
                "commandId": "raw-attempt",
                "op": "set",
                "path": "/section[1]/paragraph[1]",
                "properties": {key: "forbidden"},
            }
        )
    assert exc.value.code == "unknown_property"


def test_contract_manifest_is_deterministic_and_freezes_v1_surface() -> None:
    manifest = agent_contract_manifest()
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == "1a0f31dd9468be8d4ba619e7651dfd7845148d3b99f19d1e5fa5bd79934377fd"
    assert manifest["path"]["externalIndexBase"] == 1
    assert manifest["selector"]["xpath"] is False
    assert manifest["selector"]["rawXml"] is False
    assert set(manifest["operations"]) == {"set", "add", "remove", "move", "copy"}


def test_batch_result_and_error_golden_shape() -> None:
    result = AgentBatchResult(
        ok=False,
        rolled_back=True,
        dry_run=False,
        input_revision=REVISION,
        document_revision=REVISION,
        output_filename="output.hwpx",
        error=AgentError(
            code="ambiguous_target",
            message="selector matched two paragraphs",
            target="commands[0].path",
            recoverability="retryable",
            suggestion="query and choose one canonical path",
            valid_values=("/section[1]/paragraph[2]", "/section[1]/paragraph[5]"),
        ),
    ).to_dict()
    assert result["ok"] is False
    assert result["rolledBack"] is True
    assert result["error"]["schemaVersion"] == "hwpx.agent-error/v1"
    assert result["error"]["code"] == "ambiguous_target"
