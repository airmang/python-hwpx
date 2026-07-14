# SPDX-License-Identifier: Apache-2.0
"""Typed, deterministic document/subtree blueprint projection."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..catalog import catalog_hash
from ..document import HwpxAgentDocument, NodeRecord
from ..model import AGENT_CATALOG_SCHEMA, NODE_KINDS, AgentContractError
from .bundle import (
    ALLOWED_MEDIA_TYPES,
    BlueprintBundle,
    build_blueprint_bundle,
    read_blueprint_bundle,
    write_blueprint_bundle,
)
from .model import (
    BLUEPRINT_MODES,
    BLUEPRINT_SCHEMA,
    MAX_BLUEPRINT_DEPTH,
    MAX_BLUEPRINT_NODES,
    blueprint_limits,
    validate_blueprint_manifest,
    with_blueprint_hash,
)


@dataclass(frozen=True, slots=True)
class BlueprintDumpResult:
    """One dump receipt plus the validated in-memory artifact."""

    manifest: Mapping[str, Any]
    assets: Mapping[str, bytes]
    bundle_bytes: bytes
    bundle_sha256: str
    output_filename: str | None

    def to_dict(self, *, include_manifest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": True,
            "schemaVersion": self.manifest["schemaVersion"],
            "blueprintHash": self.manifest["blueprintHash"],
            "bundleSha256": self.bundle_sha256,
            "bundleBytes": len(self.bundle_bytes),
            "outputFilename": self.output_filename,
            "mode": self.manifest["mode"],
            "root": dict(self.manifest["root"]),
            "nodeCount": len(self.manifest["nodes"]),
            "dependencyCount": (
                len(self.manifest["styles"])
                + len(self.manifest["numbering"])
                + len(self.manifest["resources"])
            ),
            "assetCount": len(self.assets),
            "unsupported": list(self.manifest["unsupported"]),
            "fidelity": dict(self.manifest["fidelity"]),
        }
        if include_manifest:
            result["manifest"] = dict(self.manifest)
        return result


def _local_name(element: Any) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dependency(kind: str, properties: Mapping[str, Any], *, name: str | None = None) -> dict[str, Any]:
    detached = dict(properties)
    digest = _canonical_digest(detached)
    result: dict[str, Any] = {
        "key": f"{kind}:{digest}",
        "kind": kind,
        "signature": f"sha256:{digest}",
        "properties": detached,
    }
    if name:
        result["name"] = str(name)[:512]
    return result


def _semantic_generic(value: Any) -> dict[str, Any]:
    """Convert a parsed definition to typed semantics without tags or native IDs."""

    attributes = {
        str(key): str(item)
        for key, item in sorted(getattr(value, "attributes", {}).items())
        if "id" not in str(key).casefold() and "ref" not in str(key).casefold()
    }
    result: dict[str, Any] = {"kind": str(getattr(value, "name", "definition"))}
    if attributes:
        result["properties"] = attributes
    text = getattr(value, "text", None)
    if text:
        result["text"] = str(text)[:16_384]
    children = [_semantic_generic(child) for child in getattr(value, "children", [])]
    if children:
        result["children"] = children
    return result


def _numbering_properties(agent: HwpxAgentDocument, record: NodeRecord) -> dict[str, Any] | None:
    if record.kind != "paragraph":
        return None
    paragraph = record.native
    para_pr = agent.document.paragraph_property(paragraph.element.get("paraPrIDRef"))
    heading = para_pr.heading if para_pr is not None else None
    if heading is None or not heading.type or str(heading.type).upper() == "NONE":
        return None
    properties: dict[str, Any] = {
        "type": str(heading.type),
        "level": heading.level,
    }
    ref = heading.id_ref
    if ref is not None and agent.document._root.headers:  # type: ignore[attr-defined]
        model = agent.document._root.headers[0].to_model()  # type: ignore[attr-defined]
        ref_list = model.ref_list
        definitions = []
        if str(heading.type).upper() == "BULLET" and ref_list and ref_list.bullets:
            definitions = list(ref_list.bullets.bullets)
        elif ref_list and ref_list.numberings:
            definitions = list(ref_list.numberings.numberings)
        for definition in definitions:
            raw_id = getattr(definition, "attributes", {}).get("id")
            if raw_id is not None and str(raw_id) == str(ref):
                properties["definition"] = _semantic_generic(definition)
                break
    return properties


def _style_dependency(agent: HwpxAgentDocument, record: NodeRecord) -> dict[str, Any] | None:
    if record.kind == "paragraph":
        paragraph = record.native
        style = agent.document.style(paragraph.element.get("styleIDRef"))
        properties = {
            "category": "paragraph",
            "name": record.summary.get("style"),
            "type": getattr(style, "type", None),
            "englishName": getattr(style, "eng_name", None),
            "lockForm": getattr(style, "lock_form", None),
            "alignment": record.summary.get("alignment"),
            "breakBefore": record.summary.get("breakBefore"),
            "keepWithNext": record.summary.get("keepWithNext"),
            "lineSpacingPercent": record.summary.get("lineSpacingPercent"),
        }
        return _dependency("style", properties, name=str(record.summary.get("style") or "paragraph"))
    if record.kind == "run":
        properties = {"category": "character"}
        properties.update({key: value for key, value in record.summary.items() if key != "text"})
        return _dependency("char", properties, name="character-format")
    return None


def _manifest_image_item(agent: HwpxAgentDocument, item_id: str) -> tuple[str, str] | None:
    matches: list[tuple[str, str]] = []
    for item in agent.document._package._manifest_items():  # type: ignore[attr-defined]
        if str(item.get("id") or "") == item_id:
            matches.append((str(item.get("href") or ""), str(item.get("media-type") or "")))
    if len(matches) > 1:
        raise AgentContractError(
            "invariant_violation", "picture resource identity is duplicated", target=item_id
        )
    return matches[0] if matches else None


def _picture_resource(
    agent: HwpxAgentDocument, record: NodeRecord
) -> tuple[dict[str, Any], bytes] | None:
    if record.kind != "picture":
        return None
    image = next((child for child in record.native.iter() if _local_name(child) == "img"), None)
    item_id = str(image.get("binaryItemIDRef") or "") if image is not None else ""
    if not item_id:
        return None
    manifest_item = _manifest_image_item(agent, item_id)
    if manifest_item is None:
        return None
    package_name, media_type = manifest_item
    media_type = media_type.casefold()
    if media_type not in ALLOWED_MEDIA_TYPES:
        return None
    suffix = Path(package_name).suffix.casefold().lstrip(".")
    if suffix not in ALLOWED_MEDIA_TYPES[media_type]:
        return None
    payload = agent.document._package.read(package_name)  # type: ignore[attr-defined]
    digest = hashlib.sha256(payload).hexdigest()
    resource = {
        "key": f"resource:{digest}",
        "sha256": f"sha256:{digest}",
        "mediaType": media_type,
        "size": len(payload),
        "assetPath": f"assets/{digest}.{suffix}",
        "name": str(record.summary.get("name") or "image")[:512],
    }
    return resource, payload


def _ordered_subtree(
    agent: HwpxAgentDocument, root: NodeRecord
) -> list[tuple[NodeRecord, int]]:
    by_path = {record.path: record for record in agent.records}
    ordered: list[tuple[NodeRecord, int]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(record: NodeRecord, depth: int) -> None:
        if depth > MAX_BLUEPRINT_DEPTH:
            raise AgentContractError("resource_limit", "blueprint subtree exceeds depth limit", target=record.path)
        if record.path in visiting:
            raise AgentContractError("invariant_violation", "semantic projection contains a cycle", target=record.path)
        if record.path in visited:
            raise AgentContractError(
                "invariant_violation", "semantic projection contains multiple parents", target=record.path
            )
        visiting.add(record.path)
        visited.add(record.path)
        ordered.append((record, depth))
        if len(ordered) > MAX_BLUEPRINT_NODES:
            raise AgentContractError("resource_limit", "blueprint subtree exceeds node limit", target=record.path)
        for child_path in record.child_paths:
            child = by_path.get(child_path)
            if child is None:
                raise AgentContractError("invariant_violation", "semantic child binding is missing", target=child_path)
            visit(child, depth + 1)
        visiting.remove(record.path)

    visit(root, 0)
    return ordered


def _make_manifest(
    agent: HwpxAgentDocument,
    *,
    root_path: str,
    source_label: str,
    mode: str,
    include_assets: bool,
    require_replayable: bool,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    if mode not in BLUEPRINT_MODES:
        raise AgentContractError("invalid_syntax", "unsupported blueprint mode", target="mode")
    root_record = agent.resolve_record(root_path, expected_revision=agent.revision)
    ordered = _ordered_subtree(agent, root_record)
    logical_ids = {record.path: f"n{index:06d}" for index, (record, _) in enumerate(ordered, start=1)}
    styles: dict[str, dict[str, Any]] = {}
    numbering: dict[str, dict[str, Any]] = {}
    resources: dict[str, dict[str, Any]] = {}
    assets: dict[str, bytes] = {}
    unsupported: list[dict[str, str]] = []
    nodes: list[dict[str, Any]] = []

    for record, _depth in ordered:
        style_refs: list[str] = []
        numbering_refs: list[str] = []
        resource_refs: list[str] = []
        dependency = _style_dependency(agent, record)
        if dependency is not None:
            styles.setdefault(str(dependency["key"]), dependency)
            style_refs.append(str(dependency["key"]))
        numbering_properties = _numbering_properties(agent, record)
        if numbering_properties is not None:
            definition = _dependency("numbering", numbering_properties, name=str(numbering_properties["type"]))
            numbering.setdefault(str(definition["key"]), definition)
            numbering_refs.append(str(definition["key"]))

        node_unsupported: list[str] = []
        for kind, count in sorted(record.unsupported_child_kinds.items()):
            reason = f"unprojected semantic child ({count})"
            unsupported.append({"path": record.path, "kind": str(kind), "reason": reason})
            node_unsupported.append(reason)

        if record.kind == "picture":
            extracted = _picture_resource(agent, record) if include_assets else None
            if extracted is None:
                reason = "picture resource is missing, disabled, or not allow-listed"
                unsupported.append({"path": record.path, "kind": "resource", "reason": reason})
                node_unsupported.append(reason)
            else:
                resource, payload = extracted
                resources.setdefault(str(resource["key"]), resource)
                assets.setdefault(str(resource["assetPath"]), payload)
                resource_refs.append(str(resource["key"]))

        replayable = not node_unsupported
        native_id = record.attributes.get("id") or record.stable_id
        node = {
            "blueprintId": logical_ids[record.path],
            "kind": record.kind,
            "properties": dict(record.summary),
            "children": [logical_ids[path] for path in record.child_paths],
            "styleRefs": sorted(style_refs),
            "numberingRefs": sorted(numbering_refs),
            "resourceRefs": sorted(resource_refs),
            "references": [],
            "sourceHint": {"nativeId": native_id, "path": record.path},
            "support": {
                "replayable": replayable,
                "fidelity": "exact" if replayable else "unsupported",
            },
        }
        nodes.append(node)

    all_replayable = not unsupported and all(node["support"]["replayable"] for node in nodes)
    if require_replayable and not all_replayable:
        first = unsupported[0] if unsupported else {"path": root_record.path, "reason": "not replayable"}
        raise AgentContractError(
            "unsupported_content",
            f"strict blueprint dump is not replayable: {first['reason']}",
            target=str(first["path"]),
        )

    kind_order = {kind: index for index, kind in enumerate(NODE_KINDS)}
    manifest: dict[str, Any] = {
        "schemaVersion": BLUEPRINT_SCHEMA,
        "catalogVersion": AGENT_CATALOG_SCHEMA,
        "catalogHash": catalog_hash(),
        "source": {"revision": agent.revision, "label": source_label[:512]},
        "mode": mode,
        "root": {
            "blueprintId": logical_ids[root_record.path],
            "kind": root_record.kind,
            "sourcePath": root_record.path,
            "sourceStability": root_record.stability,
        },
        "nodes": nodes,
        "styles": [styles[key] for key in sorted(styles)],
        "numbering": [numbering[key] for key in sorted(numbering)],
        "resources": [resources[key] for key in sorted(resources)],
        "references": [],
        "unsupported": unsupported,
        "capabilities": {
            "dump": True,
            "replay": all_replayable,
            "kinds": sorted({node["kind"] for node in nodes}, key=lambda kind: kind_order[kind]),
        },
        "limits": blueprint_limits(),
        "fidelity": {
            "replayable": all_replayable,
            "ceiling": "exact" if all_replayable else "unsupported",
            "reasons": [item["reason"] for item in unsupported],
        },
        "blueprintHash": None,
    }
    return validate_blueprint_manifest(with_blueprint_hash(manifest)), assets


def dump_document_blueprint(
    source: str | os.PathLike[str] | bytes,
    *,
    path: str = "/",
    mode: str = "portable",
    expected_revision: str | None = None,
    output: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
    include_assets: bool = True,
    require_replayable: bool = True,
) -> BlueprintDumpResult:
    """Dump one revision-bound semantic subtree to a validated typed bundle."""

    source_label = "memory.hwpx" if isinstance(source, bytes) else Path(source).name
    with HwpxAgentDocument.open(source) as agent:
        if expected_revision is not None and expected_revision != agent.revision:
            raise AgentContractError(
                "stale_revision", "document revision does not match", target=path
            )
        manifest, assets = _make_manifest(
            agent,
            root_path=path,
            source_label=source_label,
            mode=mode,
            include_assets=include_assets,
            require_replayable=require_replayable,
        )
    if output is None:
        bundle_bytes = build_blueprint_bundle(manifest, assets)
        bundle = read_blueprint_bundle(bundle_bytes)
        output_filename = None
    else:
        bundle = write_blueprint_bundle(output, manifest, assets, overwrite=overwrite)
        bundle_bytes = Path(output).read_bytes()
        output_filename = str(output)
    return BlueprintDumpResult(
        manifest=bundle.manifest,
        assets=bundle.assets,
        bundle_bytes=bundle_bytes,
        bundle_sha256=bundle.bundle_sha256,
        output_filename=output_filename,
    )


__all__ = ["BlueprintDumpResult", "dump_document_blueprint"]
