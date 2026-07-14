# SPDX-License-Identifier: Apache-2.0
"""Single-source catalog and help generation for the agent document facade."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .model import (
    AGENT_CATALOG_SCHEMA,
    AgentContractError,
    NODE_KINDS,
    NODE_PROPERTY_CATALOG_V1,
    agent_contract_manifest,
)


def agent_catalog() -> dict[str, Any]:
    """Return a detached deterministic catalog shared by nodes, CLI, and MCP."""

    manifest = agent_contract_manifest()
    manifest["commands"] = {
        "set": {"required": ["commandId", "op", "path", "properties"]},
        "add": {
            "required": ["commandId", "op", "parent", "kind", "properties"],
            "optional": ["position"],
        },
        "remove": {"required": ["commandId", "op", "path"]},
        "move": {
            "required": ["commandId", "op", "path", "parent"],
            "optional": ["position"],
        },
        "copy": {
            "required": ["commandId", "op", "path", "parent"],
            "optional": ["position"],
        },
    }
    manifest["query"] = {
        "examples": [
            'paragraph[style="개요 1"]:contains("평가")',
            'section > paragraph[type="normal"]',
            'table[id="123"] > row > cell',
        ],
        "limitRequired": True,
        "normalization": "Unicode NFKC + whitespace collapse + casefold",
    }
    return deepcopy(manifest)


def catalog_hash() -> str:
    payload = json.dumps(agent_catalog(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def agent_json_schemas() -> dict[str, Any]:
    """Generate public JSON Schema fragments from the frozen catalog."""

    catalog = agent_catalog()
    command_variants: list[dict[str, Any]] = []
    for operation, shape in catalog["commands"].items():
        properties: dict[str, Any] = {
            "commandId": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,31}$"},
            "op": {"const": operation},
            "path": {"type": "string"},
            "parent": {"type": "string"},
            "kind": {"enum": [kind for kind in NODE_KINDS if kind not in {"document", "unsupported"}]},
            "properties": {"type": "object", "minProperties": 1, "maxProperties": 32},
            "position": {"type": "object"},
        }
        allowed = set(shape["required"]) | set(shape.get("optional", []))
        command_variants.append(
            {
                "type": "object",
                "required": list(shape["required"]),
                "additionalProperties": False,
                "properties": {key: value for key, value in properties.items() if key in allowed},
            }
        )
    return {
        "node": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "HwpxAgentNode v1",
            "type": "object",
            "required": [
                "schemaVersion",
                "kind",
                "path",
                "stableId",
                "stability",
                "summary",
                "childCount",
                "children",
                "coverage",
                "revision",
            ],
            "properties": {
                "schemaVersion": {"const": catalog["schemas"]["node"]},
                "kind": {"enum": list(NODE_KINDS)},
                "path": {"type": "string"},
                "stableId": {"type": ["string", "null"]},
                "stability": {"enum": catalog["path"]["stabilityLevels"]},
                "summary": {"type": "object"},
                "childCount": {"type": "integer", "minimum": 0},
                "children": {"type": "array"},
                "coverage": {"type": "object"},
                "revision": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
            },
        },
        "command": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "HwpxAgentCommand v1",
            "oneOf": command_variants,
        },
        "queryInput": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["selector", "limit"],
            "additionalProperties": False,
            "properties": {
                "selector": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": catalog["limits"]["maxSelectorChars"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": catalog["limits"]["maxQueryResults"]},
            },
        },
    }


def node_help(kind: str) -> dict[str, Any]:
    if kind not in NODE_KINDS:
        raise AgentContractError("unknown_kind", f"unknown node kind: {kind}", target="kind")
    entry = NODE_PROPERTY_CATALOG_V1[kind]
    return {
        "schemaVersion": AGENT_CATALOG_SCHEMA,
        "kind": kind,
        "readableProperties": list(entry["readable"]),
        "editableProperties": list(entry["editable"]),
        "operations": list(entry["operations"]),
    }


def human_help(kind: str | None = None) -> str:
    """Render compact human help from the same catalog used for JSON schemas."""

    kinds = [kind] if kind is not None else list(NODE_KINDS)
    lines = ["HWPX agent document interface v1", ""]
    for candidate in kinds:
        info = node_help(candidate)
        readable = ", ".join(info["readableProperties"]) or "-"
        editable = ", ".join(info["editableProperties"]) or "-"
        operations = ", ".join(info["operations"]) or "-"
        lines.extend(
            [
                candidate,
                f"  readable: {readable}",
                f"  editable: {editable}",
                f"  operations: {operations}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["agent_catalog", "agent_json_schemas", "catalog_hash", "human_help", "node_help"]
