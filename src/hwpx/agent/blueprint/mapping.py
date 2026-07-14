# SPDX-License-Identifier: Apache-2.0
"""Deterministic preflight and dependency mapping for blueprint replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from hwpx.document import HwpxDocument

from ..document import HwpxAgentDocument, NodeRecord
from ..model import AgentContractError
from .dump import _dependency, _numbering_properties, _style_dependency
from .native import create_character_format, create_numbering, create_paragraph_style

_CHILDREN: dict[str, frozenset[str]] = {
    "document": frozenset({"section"}),
    "section": frozenset({"paragraph", "memo"}),
    "paragraph": frozenset(
        {"run", "table", "picture", "shape", "footnote", "endnote", "form-field"}
    ),
    "table": frozenset({"row"}),
    "row": frozenset({"cell"}),
    "cell": frozenset({"paragraph"}),
    "run": frozenset(),
    "picture": frozenset(),
    "shape": frozenset(),
    "footnote": frozenset(),
    "endnote": frozenset(),
    "form-field": frozenset(),
    "memo": frozenset(),
}

_ROOT_PARENT = {
    "document": "document",
    "section": "document",
    "paragraph": "section",
    "run": "paragraph",
    "table": "paragraph",
    "picture": "paragraph",
    "shape": "paragraph",
    "footnote": "paragraph",
    "endnote": "paragraph",
    "form-field": "paragraph",
    "memo": "section",
    "row": "table",
}


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    mode: str
    root_id: str
    root_kind: str
    target_parent: str
    dependency_decisions: tuple[dict[str, Any], ...]
    node_fidelity: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rootId": self.root_id,
            "rootKind": self.root_kind,
            "targetParent": self.target_parent,
            "dependencyDecisions": [dict(item) for item in self.dependency_decisions],
            "nodeFidelity": [dict(item) for item in self.node_fidelity],
        }


def _stable_identity(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _target_dependency_indexes(
    document: HwpxDocument, view: HwpxAgentDocument
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    styles: dict[str, list[dict[str, Any]]] = {}
    numbering: dict[str, list[dict[str, Any]]] = {}
    resources: dict[str, list[dict[str, Any]]] = {}
    for record in view.records:
        dependency = _style_dependency(view, record)
        if dependency is not None:
            if record.kind == "paragraph":
                identity = {
                    "styleIDRef": str(record.native.element.get("styleIDRef") or "0"),
                    "paraPrIDRef": str(record.native.element.get("paraPrIDRef") or "0"),
                    "name": str(record.summary.get("style") or ""),
                }
            else:
                identity = {"charPrIDRef": str(record.native.char_pr_id_ref or "0")}
            styles.setdefault(str(dependency["signature"]), []).append(identity)
        properties = _numbering_properties(view, record)
        if properties is not None:
            dependency = _dependency("numbering", properties, name=str(properties["type"]))
            numbering.setdefault(str(dependency["signature"]), []).append(
                {"paraPrIDRef": str(record.native.element.get("paraPrIDRef") or "0")}
            )
    for item in document._package._manifest_items():  # type: ignore[attr-defined]
        media_type = str(item.get("media-type") or "").casefold()
        item_id = str(item.get("id") or "")
        package_name = str(item.get("href") or "")
        if not item_id or not package_name or not media_type.startswith("image/"):
            continue
        try:
            payload = document._package.read(package_name)  # type: ignore[attr-defined]
        except Exception:
            continue
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        resources.setdefault(digest, []).append(
            {"binaryItemIDRef": item_id, "mediaType": media_type}
        )
    for index in (styles, numbering, resources):
        for signature in index:
            index[signature] = sorted(index[signature], key=_stable_identity)
    return styles, numbering, resources


def _preflight_graph(
    manifest: dict[str, Any], target_parent: NodeRecord, mode: str
) -> tuple[str, str]:
    if manifest["mode"] != mode:
        raise AgentContractError("verification_failed", "replay mode does not match bundle mode", target="mode")
    if manifest["unsupported"] or not manifest["fidelity"]["replayable"]:
        raise AgentContractError("unsupported_content", "blueprint is inspection-only", target="bundle")
    nodes = {str(node["blueprintId"]): node for node in manifest["nodes"]}
    root_id = str(manifest["root"]["blueprintId"])
    root_kind = str(nodes[root_id]["kind"])
    expected_parent = _ROOT_PARENT.get(root_kind)
    if expected_parent is None or target_parent.kind != expected_parent:
        raise AgentContractError(
            "incompatible_parent",
            f"{root_kind} replay requires a {expected_parent} parent, not {target_parent.kind}",
            target=target_parent.path,
        )
    if root_kind in {"cell", "form-field"}:
        raise AgentContractError("unsupported_content", f"standalone {root_kind} replay is unavailable")
    parents: dict[str, str] = {}
    for node_id, node in nodes.items():
        allowed = _CHILDREN[str(node["kind"])]
        for child_id in node["children"]:
            child_kind = str(nodes[str(child_id)]["kind"])
            if child_kind not in allowed:
                raise AgentContractError(
                    "incompatible_parent",
                    f"{child_kind} is not a valid {node['kind']} child",
                    target=str(child_id),
                )
            parents[str(child_id)] = node_id
    references = {
        (str(item["from"]), str(item["field"])): str(item["to"])
        for item in manifest["references"]
    }
    for node_id, node in nodes.items():
        kind = str(node["kind"])
        host_id = references.get((node_id, "hostRun"))
        if host_id is not None:
            if nodes[host_id]["kind"] != "run" or parents.get(host_id) != parents.get(node_id):
                raise AgentContractError("invariant_violation", "hostRun must be a sibling run", target=node_id)
        if kind == "form-field":
            end_id = references.get((node_id, "endRun"))
            if host_id is None or end_id is None or nodes[end_id]["kind"] != "run":
                raise AgentContractError("invariant_violation", "form field run references are incomplete", target=node_id)
            if parents.get(end_id) != parents.get(node_id):
                raise AgentContractError("invariant_violation", "form field endRun is not a sibling", target=node_id)
        if kind == "shape" and str(node["properties"].get("shapeType")) not in {"rect", "ellipse"}:
            raise AgentContractError("unsupported_content", "shape type is not replayable", target=node_id)
    return root_id, root_kind


def plan_replay(
    document: HwpxDocument,
    view: HwpxAgentDocument,
    manifest: dict[str, Any],
    target_parent: NodeRecord,
    *,
    mode: str,
) -> ReplayPlan:
    """Produce a complete no-mutation mapping plan."""

    root_id, root_kind = _preflight_graph(manifest, target_parent, mode)
    target_styles, target_numbering, target_resources = _target_dependency_indexes(document, view)
    decisions: list[dict[str, Any]] = []
    for dependency in manifest["styles"]:
        source_key = str(dependency["key"])
        signature = str(dependency["signature"])
        candidates = target_styles.get(signature, [])
        if candidates:
            decisions.append(
                {
                    "sourceKey": source_key,
                    "family": str(dependency.get("kind") or "style"),
                    "action": "reuse",
                    "fidelity": "exact",
                    "identity": candidates[0],
                    "properties": dict(dependency["properties"]),
                }
            )
        elif mode == "source-bound":
            raise AgentContractError("not_found", "source-bound style fingerprint is missing", target=source_key)
        else:
            decisions.append(
                {
                    "sourceKey": source_key,
                    "family": str(dependency.get("kind") or "style"),
                    "action": "create",
                    "fidelity": "mapped",
                    "identity": None,
                    "properties": dict(dependency["properties"]),
                }
            )
    for dependency in manifest["numbering"]:
        source_key = str(dependency["key"])
        candidates = target_numbering.get(str(dependency["signature"]), [])
        if candidates:
            action, fidelity, identity = "reuse", "exact", candidates[0]
        elif mode == "source-bound":
            raise AgentContractError("not_found", "source-bound numbering fingerprint is missing", target=source_key)
        else:
            action, fidelity, identity = "create", "mapped", None
        decisions.append(
            {
                "sourceKey": source_key,
                "family": "numbering",
                "action": action,
                "fidelity": fidelity,
                "identity": identity,
                "properties": dict(dependency["properties"]),
            }
        )
    for resource in manifest["resources"]:
        source_key = str(resource["key"])
        candidates = [
            item
            for item in target_resources.get(str(resource["sha256"]), [])
            if item["mediaType"] == resource["mediaType"]
        ]
        if candidates:
            action, fidelity, identity = "reuse", "exact", candidates[0]
        elif mode == "source-bound":
            raise AgentContractError("not_found", "source-bound resource fingerprint is missing", target=source_key)
        else:
            action, fidelity, identity = "create", "mapped", None
        decisions.append(
            {
                "sourceKey": source_key,
                "family": "resource",
                "action": action,
                "fidelity": fidelity,
                "identity": identity,
                "properties": dict(resource),
            }
        )
    decisions.sort(key=lambda item: (str(item["family"]), str(item["sourceKey"])))
    node_fidelity = tuple(
        {
            "blueprintId": str(node["blueprintId"]),
            "kind": str(node["kind"]),
            "fidelity": "exact" if mode == "source-bound" else "mapped",
        }
        for node in manifest["nodes"]
    )
    return ReplayPlan(
        mode=mode,
        root_id=root_id,
        root_kind=root_kind,
        target_parent=target_parent.path,
        dependency_decisions=tuple(decisions),
        node_fidelity=node_fidelity,
    )


def materialize_dependencies(
    document: HwpxDocument,
    plan: ReplayPlan,
    assets: dict[str, bytes],
) -> dict[str, dict[str, Any]]:
    """Execute the already-complete dependency portion of a replay plan."""

    targets: dict[str, dict[str, Any]] = {}
    for raw in plan.dependency_decisions:
        item = dict(raw)
        if item["action"] == "create":
            family = str(item["family"])
            properties = dict(item["properties"])
            if family == "style":
                item["identity"] = create_paragraph_style(
                    document, properties, source_key=str(item["sourceKey"])
                )
            elif family == "char":
                item["identity"] = {
                    "charPrIDRef": create_character_format(document, properties)
                }
            elif family == "numbering":
                item["identity"] = {
                    "paraPrIDRef": create_numbering(document, properties)
                }
            elif family == "resource":
                asset_path = str(properties["assetPath"])
                suffix = asset_path.rsplit(".", 1)[-1]
                item["identity"] = {
                    "binaryItemIDRef": document.add_image(assets[asset_path], suffix),
                    "mediaType": properties["mediaType"],
                }
            else:  # pragma: no cover - validated dependency family exhaustiveness
                raise AgentContractError("invariant_violation", f"unknown dependency family: {family}")
        targets[str(item["sourceKey"])] = item
    return targets


__all__ = ["ReplayPlan", "materialize_dependencies", "plan_replay"]
