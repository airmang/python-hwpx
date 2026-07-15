from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx.agent.blueprint import (
    BLUEPRINT_REPLAY_SCHEMA,
    BLUEPRINT_SCHEMA,
    blueprint_catalog,
    blueprint_catalog_hash,
    blueprint_hash,
    blueprint_json_schemas,
    blueprint_limits,
    canonical_manifest_bytes,
    validate_blueprint_manifest,
    validate_replay_request,
    with_blueprint_hash,
)
from hwpx.agent.model import AGENT_CATALOG_SCHEMA, AgentContractError


def _digest(seed: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


def _manifest() -> dict:
    value = {
        "schemaVersion": BLUEPRINT_SCHEMA,
        "catalogVersion": AGENT_CATALOG_SCHEMA,
        "catalogHash": _digest("agent-catalog"),
        "source": {"revision": _digest("source"), "label": "public.hwpx"},
        "mode": "portable",
        "root": {
            "blueprintId": "n000001",
            "kind": "paragraph",
            "sourcePath": '/section[1]/paragraph[@id="1"]',
            "sourceStability": "native",
        },
        "nodes": [
            {
                "blueprintId": "n000001",
                "kind": "paragraph",
                "properties": {"text": "typed", "style": "본문"},
                "children": ["n000002"],
                "styleRefs": [_digest("style").replace("sha256", "style")],
                "numberingRefs": [],
                "resourceRefs": [],
                "references": [],
                "sourceHint": {"nativeId": "1", "path": "/section[1]/paragraph[1]"},
                "support": {"replayable": True, "fidelity": "exact"},
            },
            {
                "blueprintId": "n000002",
                "kind": "run",
                "properties": {"text": "typed", "bold": False},
                "children": [],
                "styleRefs": [],
                "numberingRefs": [],
                "resourceRefs": [],
                "references": [],
                "sourceHint": {"nativeId": None, "path": "/section[1]/paragraph[1]/run[1]"},
                "support": {"replayable": True, "fidelity": "exact"},
            },
        ],
        "styles": [
            {
                "key": _digest("style").replace("sha256", "style"),
                "kind": "style",
                "name": "본문",
                "signature": _digest("style"),
                "properties": {"type": "paragraph"},
            }
        ],
        "numbering": [],
        "resources": [],
        "references": [],
        "unsupported": [],
        "capabilities": {"dump": True, "replay": True, "kinds": ["paragraph", "run"]},
        "limits": blueprint_limits(),
        "fidelity": {"replayable": True, "ceiling": "exact", "reasons": []},
        "blueprintHash": None,
    }
    return with_blueprint_hash(value)


def test_catalog_and_json_schemas_are_deterministic() -> None:
    first = blueprint_catalog()
    second = blueprint_catalog()
    assert first == second
    assert blueprint_catalog_hash() == blueprint_catalog_hash()
    assert blueprint_json_schemas()["blueprint"]["properties"]["schemaVersion"]["const"] == BLUEPRINT_SCHEMA
    json.dumps(blueprint_json_schemas(), sort_keys=True)


def test_manifest_hash_and_validation_are_canonical() -> None:
    manifest = _manifest()
    assert manifest["blueprintHash"] == blueprint_hash(manifest)
    assert validate_blueprint_manifest(manifest) == validate_blueprint_manifest(dict(reversed(list(manifest.items()))))
    assert canonical_manifest_bytes(manifest) == canonical_manifest_bytes(dict(reversed(list(manifest.items()))))


@pytest.mark.parametrize("forbidden", ["xml", "rawXml", "packagePath", "nativeObject", "privateCoordinate"])
def test_manifest_forbids_raw_or_private_escape_fields(forbidden: str) -> None:
    manifest = _manifest()
    manifest["nodes"][0]["properties"][forbidden] = "no"
    manifest = with_blueprint_hash(manifest)
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(manifest)


def test_manifest_rejects_duplicate_or_missing_logical_ids() -> None:
    duplicate = _manifest()
    duplicate["nodes"][1]["blueprintId"] = "n000001"
    duplicate = with_blueprint_hash(duplicate)
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(duplicate)

    missing = _manifest()
    missing["nodes"][0]["children"] = ["n999999"]
    missing = with_blueprint_hash(missing)
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(missing)


def test_manifest_rejects_hash_mismatch_and_absolute_private_label() -> None:
    manifest = _manifest()
    manifest["blueprintHash"] = _digest("wrong")
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(manifest)
    manifest = _manifest()
    manifest["source"]["label"] = "/workspace/private/source.hwpx"
    manifest = with_blueprint_hash(manifest)
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(manifest)


def test_replay_request_contract_is_strict_and_revision_bound() -> None:
    request = {
        "schemaVersion": BLUEPRINT_REPLAY_SCHEMA,
        "bundle": {"filename": "block.hwpxbp", "blueprintHash": _manifest()["blueprintHash"]},
        "target": {"input": "target.hwpx", "output": "out.hwpx", "overwrite": False},
        "targetParent": "/section[1]",
        "position": {"mode": "append"},
        "mode": "portable",
        "mappingPolicy": {"strict": True},
        "expectedRevision": _digest("target"),
        "idempotencyKey": "bp-1",
        "dryRun": False,
        "quality": "transparent",
        "verificationRequirements": ["package", "reopen", "openSafety"],
    }
    assert validate_replay_request(request)["mode"] == "portable"
    request["unexpected"] = True
    with pytest.raises(AgentContractError):
        validate_replay_request(request)


def test_planning_limits_match_approved_ceiling() -> None:
    assert blueprint_limits() == {
        "maxNodes": 10_000,
        "maxDepth": 32,
        "maxManifestBytes": 16 * 1024 * 1024,
        "maxAssets": 128,
        "maxAssetBytes": 16 * 1024 * 1024,
        "maxTotalAssetBytes": 64 * 1024 * 1024,
        "maxDependencies": 4_096,
        "maxReferences": 50_000,
    }


def test_frozen_task_pack_and_threat_matrix_are_complete() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    task_pack = json.loads((fixtures / "agent_blueprint_tasks.json").read_text(encoding="utf-8"))
    tasks = task_pack["tasks"]
    assert len(tasks) == 20
    assert len({task["id"] for task in tasks}) == 20
    assert {task["terminal"] for task in tasks} >= {
        "success",
        "structured-refusal",
        "unverified",
        "oracle-clean",
    }
    threats = json.loads(
        (fixtures / "agent_blueprint_hostile_cases.json").read_text(encoding="utf-8")
    )["cases"]
    assert len(threats) >= 20
    assert len(set(threats)) == len(threats)
