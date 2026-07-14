# SPDX-License-Identifier: Apache-2.0
"""Strict public contracts for typed HWPX blueprint dump and replay."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..model import (
    AGENT_CATALOG_SCHEMA,
    NODE_KINDS,
    REVISION_PATTERN,
    AgentContractError,
    AgentError,
)

BLUEPRINT_SCHEMA = "hwpx.agent-blueprint/v1"
BLUEPRINT_REPLAY_SCHEMA = "hwpx.agent-blueprint-replay/v1"
BLUEPRINT_REPLAY_RESULT_SCHEMA = "hwpx.agent-blueprint-replay-result/v1"
BLUEPRINT_CATALOG_SCHEMA = "hwpx.agent-blueprint-catalog/v1"

BLUEPRINT_MODES = ("source-bound", "portable")
FIDELITY_LEVELS = ("exact", "mapped", "degraded", "unsupported")

MAX_BLUEPRINT_NODES = 10_000
MAX_BLUEPRINT_DEPTH = 32
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ASSETS = 128
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 64 * 1024 * 1024
MAX_DEPENDENCIES = 4_096
MAX_REFERENCES = 50_000
MAX_BLUEPRINT_TEXT = 16_384
MAX_BLUEPRINT_JSON_DEPTH = 32

BLUEPRINT_ID_PATTERN = re.compile(r"^n[0-9]{6}$")
DEPENDENCY_KEY_PATTERN = re.compile(r"^(style|char|numbering|resource):[a-f0-9]{64}$")
SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
ASSET_PATH_PATTERN = re.compile(r"^assets/[a-f0-9]{64}\.[a-z0-9]{1,12}$")

_FORBIDDEN_KEYS = frozenset(
    {
        "xml",
        "raw",
        "rawxml",
        "xpath",
        "namespace",
        "namespaceuri",
        "packagepath",
        "partpath",
        "nativeobject",
        "lxml",
        "absolutepath",
        "privatecoordinate",
        "executable",
        "script",
    }
)

_MANIFEST_KEYS = frozenset(
    {
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
    }
)


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentContractError("invalid_syntax", f"{name} must be an object", target=name)
    return dict(value)


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AgentContractError("invalid_syntax", f"{name} must be an array", target=name)
    return list(value)


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
    name: str,
) -> None:
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise AgentContractError(
            "invalid_syntax",
            f"{name} fields mismatch (missing={sorted(missing)}, extra={sorted(extra)})",
            target=name,
        )


def _validate_public_json(value: object, *, name: str, depth: int = 0) -> None:
    if depth > MAX_BLUEPRINT_JSON_DEPTH:
        raise AgentContractError("resource_limit", f"{name} exceeds JSON depth", target=name)
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > MAX_BLUEPRINT_TEXT:
            raise AgentContractError("resource_limit", f"{name} string is too long", target=name)
        if value.startswith("/") and name.endswith(("source.label", "sourceHint.nativeId")):
            raise AgentContractError(
                "verification_failed", f"{name} must not contain an absolute path", target=name
            )
        return
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = re.sub(r"[^a-z]", "", key.casefold())
            if normalized in _FORBIDDEN_KEYS:
                raise AgentContractError(
                    "unknown_property", f"{name} contains forbidden field {key!r}", target=f"{name}.{key}"
                )
            _validate_public_json(child, name=f"{name}.{key}", depth=depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for index, child in enumerate(value):
            _validate_public_json(child, name=f"{name}[{index}]", depth=depth + 1)
        return
    raise AgentContractError("invalid_syntax", f"{name} is not JSON-serializable", target=name)


def blueprint_limits() -> dict[str, int]:
    return {
        "maxNodes": MAX_BLUEPRINT_NODES,
        "maxDepth": MAX_BLUEPRINT_DEPTH,
        "maxManifestBytes": MAX_MANIFEST_BYTES,
        "maxAssets": MAX_ASSETS,
        "maxAssetBytes": MAX_ASSET_BYTES,
        "maxTotalAssetBytes": MAX_TOTAL_ASSET_BYTES,
        "maxDependencies": MAX_DEPENDENCIES,
        "maxReferences": MAX_REFERENCES,
    }


def canonical_manifest_bytes(value: Mapping[str, Any], *, include_hash: bool = False) -> bytes:
    payload = dict(value)
    if not include_hash:
        payload["blueprintHash"] = None
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentContractError(
            "invalid_syntax", "blueprint manifest is not canonical JSON", target="blueprint"
        ) from exc
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise AgentContractError(
            "resource_limit", "blueprint manifest exceeds byte limit", target="blueprint"
        )
    return encoded


def blueprint_hash(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_manifest_bytes(value)).hexdigest()


def with_blueprint_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["blueprintHash"] = blueprint_hash(result)
    return result


def _validate_dependency_record(value: object, *, name: str, kind: str) -> dict[str, Any]:
    record = _object(value, name)
    required = {"key", "signature", "properties"}
    optional = {"name", "kind"}
    _exact_keys(record, required=required, optional=optional, name=name)
    key = str(record["key"])
    expected_prefix = "numbering" if kind == "numbering" else kind
    if not DEPENDENCY_KEY_PATTERN.fullmatch(key) or not key.startswith(expected_prefix + ":"):
        raise AgentContractError("invalid_syntax", f"{name}.key is invalid", target=f"{name}.key")
    if not SHA256_PATTERN.fullmatch(str(record["signature"])):
        raise AgentContractError(
            "invalid_syntax", f"{name}.signature must be sha256", target=f"{name}.signature"
        )
    _validate_public_json(record["properties"], name=f"{name}.properties")
    return record


def _validate_resource(value: object, *, name: str) -> dict[str, Any]:
    record = _object(value, name)
    _exact_keys(
        record,
        required={"key", "sha256", "mediaType", "size", "assetPath"},
        optional={"name"},
        name=name,
    )
    key = str(record["key"])
    digest = str(record["sha256"])
    if not DEPENDENCY_KEY_PATTERN.fullmatch(key) or not key.startswith("resource:"):
        raise AgentContractError("invalid_syntax", f"{name}.key is invalid", target=f"{name}.key")
    if not SHA256_PATTERN.fullmatch(digest):
        raise AgentContractError("invalid_syntax", f"{name}.sha256 is invalid", target=f"{name}.sha256")
    size = record["size"]
    if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_ASSET_BYTES:
        raise AgentContractError("resource_limit", f"{name}.size is invalid", target=f"{name}.size")
    asset_path = str(record["assetPath"])
    if not ASSET_PATH_PATTERN.fullmatch(asset_path):
        raise AgentContractError(
            "verification_failed", f"{name}.assetPath is unsafe", target=f"{name}.assetPath"
        )
    if asset_path.split("/", 1)[1].split(".", 1)[0] != digest.removeprefix("sha256:"):
        raise AgentContractError(
            "verification_failed", f"{name}.assetPath does not match sha256", target=f"{name}.assetPath"
        )
    media_type = str(record["mediaType"])
    if not media_type.startswith("image/"):
        raise AgentContractError(
            "unsupported_content", f"{name}.mediaType is not allow-listed", target=f"{name}.mediaType"
        )
    return record


def validate_blueprint_manifest(value: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    """Validate and detach one strict ``hwpx.agent-blueprint/v1`` manifest."""

    manifest = _object(value, "blueprint")
    _exact_keys(manifest, required=_MANIFEST_KEYS, name="blueprint")
    if manifest["schemaVersion"] != BLUEPRINT_SCHEMA:
        raise AgentContractError("invalid_syntax", "unsupported blueprint schema", target="schemaVersion")
    if manifest["catalogVersion"] != AGENT_CATALOG_SCHEMA:
        raise AgentContractError("verification_failed", "agent catalog version skew", target="catalogVersion")
    if not SHA256_PATTERN.fullmatch(str(manifest["catalogHash"])):
        raise AgentContractError("invalid_syntax", "catalogHash must be sha256", target="catalogHash")
    mode = str(manifest["mode"])
    if mode not in BLUEPRINT_MODES:
        raise AgentContractError("invalid_syntax", "unsupported blueprint mode", target="mode")

    source = _object(manifest["source"], "source")
    _exact_keys(source, required={"revision", "label"}, name="source")
    if not REVISION_PATTERN.fullmatch(str(source["revision"])):
        raise AgentContractError("invalid_syntax", "source.revision must be sha256", target="source.revision")
    _validate_public_json(source, name="source")

    root = _object(manifest["root"], "root")
    _exact_keys(
        root,
        required={"blueprintId", "kind", "sourcePath", "sourceStability"},
        name="root",
    )
    if not BLUEPRINT_ID_PATTERN.fullmatch(str(root["blueprintId"])):
        raise AgentContractError("invalid_syntax", "root blueprintId is invalid", target="root.blueprintId")
    if root["kind"] not in NODE_KINDS:
        raise AgentContractError("unknown_kind", "root kind is unknown", target="root.kind")
    if not str(root["sourcePath"]).startswith("/"):
        raise AgentContractError("invalid_syntax", "root sourcePath must be semantic", target="root.sourcePath")

    nodes = _list(manifest["nodes"], "nodes")
    if not nodes or len(nodes) > MAX_BLUEPRINT_NODES:
        raise AgentContractError("resource_limit", "node count is outside limits", target="nodes")
    node_ids: set[str] = set()
    detached_nodes: list[dict[str, Any]] = []
    for index, item in enumerate(nodes):
        name = f"nodes[{index}]"
        node = _object(item, name)
        _exact_keys(
            node,
            required={
                "blueprintId",
                "kind",
                "properties",
                "children",
                "styleRefs",
                "numberingRefs",
                "resourceRefs",
                "references",
                "sourceHint",
                "support",
            },
            name=name,
        )
        node_id = str(node["blueprintId"])
        if not BLUEPRINT_ID_PATTERN.fullmatch(node_id) or node_id in node_ids:
            raise AgentContractError("invariant_violation", f"{name}.blueprintId is invalid or duplicate", target=name)
        node_ids.add(node_id)
        if node["kind"] not in NODE_KINDS:
            raise AgentContractError("unknown_kind", f"{name}.kind is unknown", target=f"{name}.kind")
        for field_name in ("children", "styleRefs", "numberingRefs", "resourceRefs", "references"):
            node[field_name] = [str(item) for item in _list(node[field_name], f"{name}.{field_name}")]
        support = _object(node["support"], f"{name}.support")
        _exact_keys(support, required={"replayable", "fidelity"}, name=f"{name}.support")
        if support["fidelity"] not in FIDELITY_LEVELS:
            raise AgentContractError("invalid_syntax", f"{name}.support fidelity is invalid", target=name)
        _validate_public_json(node["properties"], name=f"{name}.properties")
        _validate_public_json(node["sourceHint"], name=f"{name}.sourceHint")
        detached_nodes.append(node)

    if str(root["blueprintId"]) not in node_ids:
        raise AgentContractError("invariant_violation", "root does not reference a node", target="root")
    for index, node in enumerate(detached_nodes):
        for child in node["children"]:
            if child not in node_ids:
                raise AgentContractError(
                    "invariant_violation", "node child reference is missing", target=f"nodes[{index}].children"
                )

    styles = _list(manifest["styles"], "styles")
    numbering = _list(manifest["numbering"], "numbering")
    resources = _list(manifest["resources"], "resources")
    if len(styles) + len(numbering) > MAX_DEPENDENCIES:
        raise AgentContractError("resource_limit", "dependency count exceeds limit", target="styles")
    if len(resources) > MAX_ASSETS:
        raise AgentContractError("resource_limit", "resource count exceeds limit", target="resources")
    detached_styles = [
        _validate_dependency_record(item, name=f"styles[{index}]", kind=str(_object(item, "style").get("kind", "style")))
        for index, item in enumerate(styles)
    ]
    detached_numbering = [
        _validate_dependency_record(item, name=f"numbering[{index}]", kind="numbering")
        for index, item in enumerate(numbering)
    ]
    detached_resources = [
        _validate_resource(item, name=f"resources[{index}]") for index, item in enumerate(resources)
    ]
    if sum(int(item["size"]) for item in detached_resources) > MAX_TOTAL_ASSET_BYTES:
        raise AgentContractError("resource_limit", "total asset bytes exceed limit", target="resources")

    references = _list(manifest["references"], "references")
    if len(references) > MAX_REFERENCES:
        raise AgentContractError("resource_limit", "reference count exceeds limit", target="references")
    for index, item in enumerate(references):
        record = _object(item, f"references[{index}]")
        _exact_keys(record, required={"from", "field", "to", "required"}, name=f"references[{index}]")
        if str(record["from"]) not in node_ids:
            raise AgentContractError("invariant_violation", "reference source is missing", target=f"references[{index}]")

    unsupported = _list(manifest["unsupported"], "unsupported")
    for index, item in enumerate(unsupported):
        record = _object(item, f"unsupported[{index}]")
        _exact_keys(record, required={"path", "kind", "reason"}, name=f"unsupported[{index}]")

    capabilities = _object(manifest["capabilities"], "capabilities")
    _exact_keys(capabilities, required={"dump", "replay", "kinds"}, name="capabilities")
    limits = _object(manifest["limits"], "limits")
    if limits != blueprint_limits():
        raise AgentContractError("verification_failed", "blueprint limits do not match v1", target="limits")
    fidelity = _object(manifest["fidelity"], "fidelity")
    _exact_keys(fidelity, required={"replayable", "ceiling", "reasons"}, name="fidelity")
    if fidelity["ceiling"] not in FIDELITY_LEVELS:
        raise AgentContractError("invalid_syntax", "fidelity ceiling is invalid", target="fidelity.ceiling")

    _validate_public_json(manifest, name="blueprint")
    declared_hash = manifest["blueprintHash"]
    if not SHA256_PATTERN.fullmatch(str(declared_hash)):
        raise AgentContractError("invalid_syntax", "blueprintHash must be sha256", target="blueprintHash")
    if verify_hash and declared_hash != blueprint_hash(manifest):
        raise AgentContractError("verification_failed", "blueprintHash mismatch", target="blueprintHash")
    canonical_manifest_bytes(manifest, include_hash=True)
    return {
        **manifest,
        "nodes": detached_nodes,
        "styles": detached_styles,
        "numbering": detached_numbering,
        "resources": detached_resources,
        "references": [dict(item) for item in references],
        "unsupported": [dict(item) for item in unsupported],
    }


def validate_replay_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _object(value, "replay")
    _exact_keys(
        request,
        required={
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
        },
        name="replay",
    )
    if request["schemaVersion"] != BLUEPRINT_REPLAY_SCHEMA:
        raise AgentContractError("invalid_syntax", "unsupported replay schema", target="schemaVersion")
    if request["mode"] not in BLUEPRINT_MODES:
        raise AgentContractError("invalid_syntax", "unsupported replay mode", target="mode")
    bundle = _object(request["bundle"], "bundle")
    _exact_keys(bundle, required={"filename", "blueprintHash"}, name="bundle")
    if not SHA256_PATTERN.fullmatch(str(bundle["blueprintHash"])):
        raise AgentContractError("invalid_syntax", "bundle blueprintHash is invalid", target="bundle.blueprintHash")
    target = _object(request["target"], "target")
    _exact_keys(target, required={"input", "output", "overwrite"}, name="target")
    if not isinstance(target["overwrite"], bool):
        raise AgentContractError("invalid_syntax", "target.overwrite must be boolean", target="target.overwrite")
    if not str(request["targetParent"]).startswith("/"):
        raise AgentContractError("invalid_syntax", "targetParent must be semantic", target="targetParent")
    position = _object(request["position"], "position")
    if position.get("mode") not in {"append", "prepend", "index", "before", "after"}:
        raise AgentContractError("invalid_syntax", "position mode is invalid", target="position.mode")
    policy = _object(request["mappingPolicy"], "mappingPolicy")
    _exact_keys(policy, required={"strict"}, name="mappingPolicy")
    if not isinstance(policy["strict"], bool):
        raise AgentContractError("invalid_syntax", "mappingPolicy.strict must be boolean", target="mappingPolicy.strict")
    expected = request["expectedRevision"]
    if expected is not None and not REVISION_PATTERN.fullmatch(str(expected)):
        raise AgentContractError("invalid_syntax", "expectedRevision must be sha256", target="expectedRevision")
    if request["idempotencyKey"] is not None and not str(request["idempotencyKey"]).strip():
        raise AgentContractError("invalid_syntax", "idempotencyKey cannot be empty", target="idempotencyKey")
    if not isinstance(request["dryRun"], bool):
        raise AgentContractError("invalid_syntax", "dryRun must be boolean", target="dryRun")
    requirements = [str(item) for item in _list(request["verificationRequirements"], "verificationRequirements")]
    _validate_public_json(request, name="replay")
    return {**request, "bundle": bundle, "target": target, "position": position, "mappingPolicy": policy, "verificationRequirements": requirements}


@dataclass(frozen=True, slots=True)
class BlueprintReplayResult:
    ok: bool
    rolled_back: bool
    dry_run: bool
    input_revision: str
    document_revision: str
    output_filename: str
    blueprint_hash: str
    root_path: str | None = None
    node_map: Mapping[str, str] = field(default_factory=dict)
    dependency_maps: Mapping[str, Any] = field(default_factory=dict)
    fidelity: Mapping[str, Any] = field(default_factory=dict)
    semantic_diff: Mapping[str, Any] = field(default_factory=dict)
    verification_report: Mapping[str, Any] = field(default_factory=dict)
    error: AgentError | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": BLUEPRINT_REPLAY_RESULT_SCHEMA,
            "ok": self.ok,
            "rolledBack": self.rolled_back,
            "dryRun": self.dry_run,
            "inputRevision": self.input_revision,
            "documentRevision": self.document_revision,
            "outputFilename": self.output_filename,
            "blueprintHash": self.blueprint_hash,
            "rootPath": self.root_path,
            "nodeMap": dict(self.node_map),
            "dependencyMaps": dict(self.dependency_maps),
            "fidelity": dict(self.fidelity),
            "semanticDiff": dict(self.semantic_diff),
            "verificationReport": dict(self.verification_report),
            "error": self.error.to_dict() if self.error is not None else None,
        }


__all__ = [
    "ASSET_PATH_PATTERN",
    "BLUEPRINT_CATALOG_SCHEMA",
    "BLUEPRINT_ID_PATTERN",
    "BLUEPRINT_MODES",
    "BLUEPRINT_REPLAY_RESULT_SCHEMA",
    "BLUEPRINT_REPLAY_SCHEMA",
    "BLUEPRINT_SCHEMA",
    "BlueprintReplayResult",
    "FIDELITY_LEVELS",
    "MAX_ASSETS",
    "MAX_ASSET_BYTES",
    "MAX_BLUEPRINT_DEPTH",
    "MAX_BLUEPRINT_NODES",
    "MAX_DEPENDENCIES",
    "MAX_MANIFEST_BYTES",
    "MAX_REFERENCES",
    "MAX_TOTAL_ASSET_BYTES",
    "blueprint_hash",
    "blueprint_limits",
    "canonical_manifest_bytes",
    "validate_blueprint_manifest",
    "validate_replay_request",
    "with_blueprint_hash",
]
