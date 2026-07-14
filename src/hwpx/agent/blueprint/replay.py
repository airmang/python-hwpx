# SPDX-License-Identifier: Apache-2.0
"""Atomic typed blueprint replay orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.quality import SavePipeline
from hwpx.tools.package_validator import validate_editor_open_safety

from ..catalog import catalog_hash
from ..commands import _error_from_exception, _member_diff, _quality_policy, _record_for_native, _revision
from ..document import HwpxAgentDocument
from ..model import AgentContractError
from .bundle import read_blueprint_bundle
from .dump import dump_document_blueprint
from .mapping import materialize_dependencies, plan_replay
from .model import BlueprintReplayResult, validate_replay_request
from .native import CreatedBinding, TypedNativeBridge

IdempotencyStore = MutableMapping[str, Any]
FaultInjector = Callable[[str, int | None], None]
DomainVerifier = Callable[[bytes, Mapping[str, Any]], Mapping[str, Any]]
_EMPTY_REVISION = "sha256:" + hashlib.sha256(b"").hexdigest()


def _call(injector: FaultInjector | None, stage: str, index: int | None = None) -> None:
    if injector is not None:
        injector(stage, index)


def _request_hash(request: Mapping[str, Any]) -> str:
    payload = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _revision(payload)


def _output_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": None}
    if not path.is_file():
        return {"exists": True, "sha256": None}
    return {"exists": True, "sha256": _revision(path.read_bytes())}


def _node_map(view: HwpxAgentDocument, bindings: Mapping[str, CreatedBinding]) -> dict[str, str]:
    result: dict[str, str] = {}
    for blueprint_id, binding in bindings.items():
        if binding.kind == "form-field":
            record = next(
                (
                    candidate
                    for candidate in view.records
                    if candidate.kind == "form-field" and candidate.attributes.get("id") == binding.native_id
                ),
                None,
            )
            if record is None:
                raise AgentContractError("not_found", "replayed form field was not projected", target=blueprint_id)
        else:
            record = _record_for_native(view, binding.native)
        result[blueprint_id] = record.path
    return result


def _semantic_nodes(
    manifest: Mapping[str, Any], dependency_targets: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for node in manifest["nodes"]:
        properties = dict(node["properties"])
        if dependency_targets and node["kind"] == "paragraph" and node["styleRefs"]:
            mapped = dependency_targets.get(str(node["styleRefs"][0]))
            identity = mapped.get("identity") if mapped else None
            if isinstance(identity, Mapping) and identity.get("name"):
                properties["style"] = identity["name"]
        normalized.append(
            {
                "blueprintId": str(node["blueprintId"]),
                "kind": str(node["kind"]),
                "properties": properties,
                "children": list(node["children"]),
                "references": list(node["references"]),
            }
        )
    return normalized


def _semantic_equivalence(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    dependency_targets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_nodes = _semantic_nodes(source, dependency_targets)
    candidate_nodes = _semantic_nodes(candidate)
    equivalent = source_nodes == candidate_nodes
    return {
        "ok": equivalent,
        "sourceNodeCount": len(source_nodes),
        "candidateNodeCount": len(candidate_nodes),
        "kindSequenceMatched": [item["kind"] for item in source_nodes]
        == [item["kind"] for item in candidate_nodes],
        "propertiesMatched": equivalent,
    }


def _dependency_receipt(targets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        key: {
            "family": item["family"],
            "action": item["action"],
            "fidelity": item["fidelity"],
            "identity": dict(item["identity"]),
        }
        for key, item in sorted(targets.items())
    }


def _fidelity_receipt(plan: Any, targets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    dependencies = {
        key: str(item["fidelity"]) for key, item in sorted(targets.items())
    }
    nodes = {
        str(item["blueprintId"]): str(item["fidelity"]) for item in plan.node_fidelity
    }
    levels = set(dependencies.values()) | set(nodes.values())
    strict_ok = levels <= {"exact", "mapped"}
    return {
        "strict": True,
        "ok": strict_ok,
        "ceiling": "exact" if levels <= {"exact"} else "mapped",
        "nodes": nodes,
        "dependencies": dependencies,
        "degraded": [],
        "unsupported": [],
    }


def _replayed_result(prior: BlueprintReplayResult) -> BlueprintReplayResult:
    verification = dict(prior.verification_report)
    idempotency = dict(verification.get("idempotency", {}))
    idempotency["replayed"] = True
    verification["idempotency"] = idempotency
    return BlueprintReplayResult(
        ok=prior.ok,
        rolled_back=prior.rolled_back,
        dry_run=prior.dry_run,
        input_revision=prior.input_revision,
        document_revision=prior.document_revision,
        output_filename=prior.output_filename,
        blueprint_hash=prior.blueprint_hash,
        root_path=prior.root_path,
        node_map=prior.node_map,
        dependency_maps=prior.dependency_maps,
        fidelity=prior.fidelity,
        semantic_diff=prior.semantic_diff,
        verification_report=verification,
        error=prior.error,
    )


def replay_document_blueprint(
    request: Mapping[str, Any],
    *,
    idempotency_store: IdempotencyStore | None = None,
    fault_injector: FaultInjector | None = None,
    domain_verifier: DomainVerifier | None = None,
    save_pipeline: SavePipeline | None = None,
) -> BlueprintReplayResult:
    """Validate, map, construct, verify, and atomically commit one blueprint."""

    normalized: dict[str, Any] | None = None
    verification: dict[str, Any] = {}
    input_revision = _EMPTY_REVISION
    blueprint_hash = "sha256:" + "0" * 64
    output_filename = ""
    output_path: Path | None = None
    output_before: dict[str, Any] | None = None
    temp_path: Path | None = None
    try:
        normalized = validate_replay_request(request)
        output_filename = str(normalized["target"]["output"])
        _call(fault_injector, "before_bundle_validation")
        bundle = read_blueprint_bundle(str(normalized["bundle"]["filename"]))
        manifest = dict(bundle.manifest)
        blueprint_hash = str(manifest["blueprintHash"])
        if blueprint_hash != normalized["bundle"]["blueprintHash"]:
            raise AgentContractError("verification_failed", "request blueprintHash does not match bundle", target="bundle")
        if manifest["catalogHash"] != catalog_hash():
            raise AgentContractError("verification_failed", "blueprint catalog hash does not match runtime", target="catalogHash")
        _call(fault_injector, "after_bundle_validation")
        verification["bundle"] = {
            "validatedBeforeTargetAccess": True,
            "blueprintHash": blueprint_hash,
            "bundleSha256": bundle.bundle_sha256,
            "bytes": bundle.size,
        }

        request_hash = _request_hash(normalized)
        key = normalized["idempotencyKey"]
        verification["idempotency"] = {
            "keyProvided": key is not None,
            "requestHash": request_hash,
            "replayed": False,
            "store": "caller-owned" if idempotency_store is not None else "none",
        }
        if key is not None and idempotency_store is not None and key in idempotency_store:
            cached = idempotency_store[key]
            if not isinstance(cached, Mapping) or cached.get("requestHash") != request_hash:
                raise AgentContractError("idempotency_conflict", "idempotency key was used for a different replay")
            prior = cached.get("result")
            if not isinstance(prior, BlueprintReplayResult):
                raise AgentContractError("invariant_violation", "idempotency store contains an invalid replay result")
            return _replayed_result(prior)

        _call(fault_injector, "before_target_read")
        input_path = Path(str(normalized["target"]["input"]))
        output_path = Path(output_filename)
        input_data = input_path.read_bytes()
        output_before = _output_fingerprint(output_path)
        if output_before["exists"] and not normalized["target"]["overwrite"] and not normalized["dryRun"]:
            raise AgentContractError("identity_collision", "replay output already exists", target="target.output")
        if not output_path.parent.exists():
            raise AgentContractError("not_found", "replay output parent does not exist", target="target.output")
        input_revision = _revision(input_data)
        _call(fault_injector, "after_target_read")
        expected_revision = normalized["expectedRevision"]
        verification["revision"] = {
            "expected": expected_revision,
            "actual": input_revision,
            "matched": expected_revision in {None, input_revision},
        }
        if expected_revision not in {None, input_revision}:
            raise AgentContractError("stale_revision", "expectedRevision does not match target input")
        input_safety = validate_editor_open_safety(input_data)
        verification["inputOpenSafety"] = input_safety.to_dict()
        if not input_safety.ok:
            raise AgentContractError("verification_failed", "target input failed editor-open safety")
        _call(fault_injector, "after_target_validation")

        with HwpxDocument.open(input_data) as document:
            view = HwpxAgentDocument.from_document(document, revision=input_revision)
            parent = view.resolve_record(
                str(normalized["targetParent"]),
                expected_revision=input_revision,
                require_stable=expected_revision is None,
            )
            _call(fault_injector, "before_plan")
            plan = plan_replay(
                document,
                view,
                manifest,
                parent,
                mode=str(normalized["mode"]),
            )
            verification["plan"] = plan.to_dict()
            _call(fault_injector, "after_plan")

            _call(fault_injector, "before_dependencies")
            dependency_targets = materialize_dependencies(document, plan, dict(bundle.assets))
            _call(fault_injector, "after_dependencies")
            dependency_maps = _dependency_receipt(dependency_targets)
            fidelity = _fidelity_receipt(plan, dependency_targets)
            if normalized["mappingPolicy"]["strict"] and not fidelity["ok"]:
                raise AgentContractError("unsupported_content", "strict replay fidelity failed")

            _call(fault_injector, "before_nodes")
            bridge = TypedNativeBridge(document, manifest, dependency_targets)
            bindings = bridge.create_root(parent, dict(normalized["position"]), view)
            _call(fault_injector, "after_nodes")
            fresh_view = HwpxAgentDocument.from_document(document, revision=input_revision)
            node_map = _node_map(fresh_view, bindings)
            root_path = node_map[plan.root_id]

            _call(fault_injector, "before_serialize")
            candidate_data = document.to_bytes()
            candidate_revision = _revision(candidate_data)
            _call(fault_injector, "after_serialize")
            candidate_safety = validate_editor_open_safety(candidate_data)
            safety_dict = candidate_safety.to_dict()
            byte_report = _member_diff(input_data, candidate_data)
            if not candidate_safety.ok or not byte_report.get("ok"):
                raise AgentContractError("verification_failed", "candidate failed structural verification")
            with HwpxAgentDocument.open(candidate_data) as reopened:
                for blueprint_id, target_path in node_map.items():
                    reopened.resolve_record(target_path)
            if plan.root_kind == "document":
                semantic_diff = {
                    "ok": True,
                    "scope": "document-root-children",
                    "sourceNodeCount": len(manifest["nodes"]),
                    "candidateNodeCount": len(node_map),
                    "kindSequenceMatched": True,
                    "propertiesMatched": None,
                }
            else:
                candidate_dump = dump_document_blueprint(
                    candidate_data,
                    path=root_path,
                    mode=str(normalized["mode"]),
                    require_replayable=True,
                )
                semantic_diff = _semantic_equivalence(
                    manifest, candidate_dump.manifest, dependency_targets
                )
                if not semantic_diff["ok"]:
                    raise AgentContractError("verification_failed", "replayed semantic graph differs from blueprint")
            verification.update(
                {
                    "candidateRevision": candidate_revision,
                    "package": safety_dict["validatePackage"],
                    "reopen": safety_dict["reopen"],
                    "openSafety": safety_dict,
                    "bytePreservation": byte_report,
                    "semanticDiff": semantic_diff,
                    "dependencyMaps": dependency_maps,
                    "nodeMap": node_map,
                    "fidelity": fidelity,
                }
            )
            _call(fault_injector, "after_candidate_verification")

            requirements = set(normalized["verificationRequirements"])
            if "domain" in requirements:
                if domain_verifier is None:
                    raise AgentContractError("verification_failed", "required domain verifier is unavailable", target="domain")
                domain_report = dict(domain_verifier(candidate_data, normalized))
                json.dumps(domain_report, ensure_ascii=False, sort_keys=True)
                verification["domain"] = domain_report
                if not domain_report.get("ok"):
                    raise AgentContractError("verification_failed", "domain verification failed", target="domain")
            else:
                verification["domain"] = {"ok": None, "status": "not-requested"}

            _call(fault_injector, "before_save_pipeline")
            pipeline = save_pipeline or SavePipeline()
            quality = _quality_policy(normalized["quality"]).with_(require_reference_integrity=True)
            if "realHancom" in requirements:
                quality = quality.with_(require_visual_complete=True, render_check="required")
            if normalized["dryRun"]:
                quality_report = pipeline.run(
                    candidate_data,
                    output_path=None,
                    quality=quality,
                    before=input_path,
                    reference_document=document,
                    publish="never",
                    source_label="agent.replay_document_blueprint",
                )
            else:
                descriptor, temp_name = tempfile.mkstemp(
                    prefix=f".{output_path.name}.", suffix=".hwpx", dir=output_path.parent
                )
                os.close(descriptor)
                os.unlink(temp_name)
                temp_path = Path(temp_name)
                quality_report = pipeline.run(
                    candidate_data,
                    output_path=temp_path,
                    quality=quality,
                    before=input_path,
                    reference_document=document,
                    publish="on_pass",
                    source_label="agent.replay_document_blueprint",
                )
            _call(fault_injector, "after_save_pipeline")
            save_report = quality_report.to_dict()
            save_report["outputPath"] = None if normalized["dryRun"] else output_filename
            save_report["debugPath"] = None
            verification["savePipeline"] = save_report
            verification["realHancom"] = {
                "required": "realHancom" in requirements,
                "ok": quality_report.visual_complete,
                "status": quality_report.visual_complete_status,
                "renderChecked": quality_report.render_checked,
            }
            if not quality_report.ok:
                raise AgentContractError("verification_failed", "SavePipeline rejected replay candidate")
            if "realHancom" in requirements and not quality_report.visual_complete:
                raise AgentContractError("verification_failed", "required real-Hancom verification is unavailable")
            if not normalized["dryRun"]:
                if temp_path is None or not temp_path.exists():
                    raise AgentContractError("verification_failed", "SavePipeline did not materialize candidate")
                _call(fault_injector, "before_commit")
                if normalized["target"]["overwrite"]:
                    os.replace(temp_path, output_path)
                else:
                    try:
                        os.link(temp_path, output_path)
                    except FileExistsError as exc:
                        raise AgentContractError("identity_collision", "replay output appeared before commit") from exc
                    os.unlink(temp_path)
                temp_path = None
                verification["commit"] = {"ok": True, "atomic": True, "savedOnce": True}
            else:
                verification["commit"] = {"ok": True, "atomic": True, "savedOnce": False, "dryRun": True}

        result = BlueprintReplayResult(
            ok=True,
            rolled_back=False,
            dry_run=bool(normalized["dryRun"]),
            input_revision=input_revision,
            document_revision=candidate_revision,
            output_filename=output_filename,
            blueprint_hash=blueprint_hash,
            root_path=root_path,
            node_map=node_map,
            dependency_maps=dependency_maps,
            fidelity=fidelity,
            semantic_diff=semantic_diff,
            verification_report=verification,
        )
        if key is not None and idempotency_store is not None:
            idempotency_store[key] = {"requestHash": request_hash, "result": result}
        return result
    except BaseException as exc:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
        if output_path is not None and output_before is not None:
            verification["rollback"] = {
                "ok": _output_fingerprint(output_path) == output_before,
                "outputBefore": output_before,
                "outputAfter": _output_fingerprint(output_path),
            }
        return BlueprintReplayResult(
            ok=False,
            rolled_back=True,
            dry_run=bool((normalized or request).get("dryRun", False)),
            input_revision=input_revision,
            document_revision=input_revision,
            output_filename=output_filename,
            blueprint_hash=blueprint_hash,
            verification_report=verification,
            error=_error_from_exception(exc),
        )


__all__ = [
    "DomainVerifier",
    "FaultInjector",
    "IdempotencyStore",
    "replay_document_blueprint",
]
