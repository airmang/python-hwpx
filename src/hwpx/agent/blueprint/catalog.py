# SPDX-License-Identifier: Apache-2.0
"""Shared blueprint capability, limit, schema, and help catalog."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..model import AGENT_CATALOG_SCHEMA, NODE_KINDS
from .model import (
    BLUEPRINT_CATALOG_SCHEMA,
    BLUEPRINT_MODES,
    BLUEPRINT_REPLAY_RESULT_SCHEMA,
    BLUEPRINT_REPLAY_SCHEMA,
    BLUEPRINT_SCHEMA,
    FIDELITY_LEVELS,
    blueprint_limits,
)


def blueprint_catalog() -> dict[str, Any]:
    return {
        "schemaVersion": BLUEPRINT_CATALOG_SCHEMA,
        "agentCatalogVersion": AGENT_CATALOG_SCHEMA,
        "schemas": {
            "blueprint": BLUEPRINT_SCHEMA,
            "replay": BLUEPRINT_REPLAY_SCHEMA,
            "replayResult": BLUEPRINT_REPLAY_RESULT_SCHEMA,
        },
        "modes": list(BLUEPRINT_MODES),
        "fidelity": list(FIDELITY_LEVELS),
        "kinds": [kind for kind in NODE_KINDS if kind != "unsupported"],
        "bundle": {
            "extension": ".hwpxbp",
            "manifest": "blueprint.json",
            "assetPattern": "assets/<sha256>.<safe-extension>",
            "allowedMediaPrefixes": ["image/"],
            "forbidden": ["xml", "script", "symlink", "nested-archive", "absolute-path", "parent-path"],
        },
        "limits": blueprint_limits(),
        "surfaces": {"cli": ["dump", "replay"], "mcpMaximumTools": 2},
    }


def blueprint_catalog_hash() -> str:
    encoded = json.dumps(
        blueprint_catalog(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def blueprint_json_schemas() -> dict[str, Any]:
    catalog = blueprint_catalog()
    return {
        "blueprint": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "HwpxBlueprint v1",
            "type": "object",
            "required": [
                "schemaVersion",
                "catalogVersion",
                "catalogHash",
                "source",
                "mode",
                "root",
                "nodes",
                "styles",
                "numbering",
                "resources",
                "references",
                "unsupported",
                "capabilities",
                "limits",
                "fidelity",
                "blueprintHash",
            ],
            "additionalProperties": False,
            "properties": {
                "schemaVersion": {"const": BLUEPRINT_SCHEMA},
                "catalogVersion": {"const": AGENT_CATALOG_SCHEMA},
                "catalogHash": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
                "mode": {"enum": list(BLUEPRINT_MODES)},
                "nodes": {"type": "array", "minItems": 1, "maxItems": catalog["limits"]["maxNodes"]},
                "resources": {"type": "array", "maxItems": catalog["limits"]["maxAssets"]},
                "blueprintHash": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
            },
        },
        "replay": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "HwpxBlueprintReplay v1",
            "type": "object",
            "required": [
                "schemaVersion",
                "bundle",
                "target",
                "targetParent",
                "position",
                "mode",
                "mappingPolicy",
                "expectedRevision",
                "idempotencyKey",
                "dryRun",
                "quality",
                "verificationRequirements",
            ],
            "additionalProperties": False,
            "properties": {
                "schemaVersion": {"const": BLUEPRINT_REPLAY_SCHEMA},
                "mode": {"enum": list(BLUEPRINT_MODES)},
                "targetParent": {"type": "string"},
                "dryRun": {"type": "boolean"},
            },
        },
    }


def blueprint_human_help() -> str:
    limits = blueprint_limits()
    return (
        "HWPX typed blueprint v1\n"
        "  dump: revision-bound document/subtree -> deterministic .hwpxbp\n"
        "  replay: source-bound|portable -> one atomic SavePipeline commit\n"
        "  fidelity: exact, mapped; strict replay rejects degraded/unsupported\n"
        f"  limits: nodes={limits['maxNodes']}, assets={limits['maxAssets']}, "
        f"manifest={limits['maxManifestBytes']} bytes\n"
        "  raw XML, package parts, resident sessions, watch, and OfficeCLI are unavailable\n"
    )


__all__ = [
    "blueprint_catalog",
    "blueprint_catalog_hash",
    "blueprint_human_help",
    "blueprint_json_schemas",
]
