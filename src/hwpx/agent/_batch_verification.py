# SPDX-License-Identifier: Apache-2.0
"""Verification/orchestration primitives for :func:`hwpx.agent.commands.apply_document_commands`.

Split out of ``commands.py`` (S-088 P3, agent/commands.py:apply_document_commands
complexity decomposition) to keep that module under its enforced line-count
ratchet.  Everything here is self-contained -- it depends only on
``hwpx.agent.model``/``hwpx.agent.document`` and absolute ``hwpx`` imports, never
on ``commands.py`` itself, so ``commands.py`` can import from this module
without creating an import cycle.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.mutation_report import member_diff_bytes
from hwpx.quality import QualityPolicy, SavePipeline
from hwpx.tools.package_validator import validate_editor_open_safety

from .document import HwpxAgentDocument
from .model import AgentBatchResult, AgentContractError, AgentError

_EMPTY_REVISION = "sha256:" + hashlib.sha256(b"").hexdigest()

IdempotencyStore = MutableMapping[str, Any]
FaultInjector = Callable[[str, int | None], None]
DomainVerifier = Callable[[bytes, Mapping[str, Any]], Mapping[str, Any]]


def _revision(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _error_from_exception(exc: BaseException, *, target: str | None = None) -> AgentError:
    if isinstance(exc, AgentContractError):
        code = exc.code
        message = str(exc)
        target = exc.target or target
    elif isinstance(exc, (KeyError, IndexError, TypeError, ValueError)):
        code = "invariant_violation"
        message = str(exc) or type(exc).__name__
    else:
        code = "verification_failed"
        message = f"{type(exc).__name__}: {exc}"
    recoverability = "retryable" if code in {"stale_revision", "idempotency_conflict"} else "terminal"
    if code in {"ambiguous_target", "volatile_target", "unsupported_content"}:
        recoverability = "needs-review"
    suggestions = {
        "stale_revision": "Read the document again and retry with its current revision.",
        "ambiguous_target": "Resolve a unique canonical path before mutation.",
        "volatile_target": "Refresh the positional path from the current document revision.",
        "unknown_property": "Use the node capability catalog to choose an editable property.",
        "incompatible_parent": "Choose a compatible semantic parent and position.",
        "verification_failed": "Inspect verificationReport and do not publish the candidate.",
    }
    return AgentError(
        code=code,
        message=message[:4096],
        target=target,
        recoverability=recoverability,
        suggestion=suggestions.get(code),
    )


def _failure_result(
    *,
    exc: BaseException,
    batch: Mapping[str, Any] | None,
    input_revision: str = _EMPTY_REVISION,
    command_results: list[Mapping[str, Any]] | None = None,
    verification: Mapping[str, Any] | None = None,
) -> AgentBatchResult:
    raw = batch or {}
    output = raw.get("output") if isinstance(raw, Mapping) else None
    output_filename = ""
    if isinstance(output, Mapping):
        output_filename = str(output.get("filename") or "")
    return AgentBatchResult(
        ok=False,
        rolled_back=True,
        dry_run=bool(raw.get("dryRun", False)),
        input_revision=input_revision,
        document_revision=input_revision,
        output_filename=output_filename,
        command_results=tuple(command_results or ()),
        verification_report=dict(verification or {}),
        error=_error_from_exception(exc),
    )


def _quality_policy(value: str | Mapping[str, Any] | None) -> QualityPolicy:
    if value is None or value == "transparent":
        return QualityPolicy.transparent()
    if value == "strict":
        return QualityPolicy.strict()
    if not isinstance(value, Mapping):  # already contract-validated
        raise AgentContractError("invalid_syntax", "quality is invalid", target="batch.quality")
    mode = value.get("mode", "transparent")
    policy = QualityPolicy.strict() if mode == "strict" else QualityPolicy.transparent()
    mapping = {
        "renderCheck": "render_check",
        "xsdMode": "xsd_mode",
        "overflowPolicy": "overflow_policy",
        "layoutLint": "layout_lint",
        "preserveUnmodifiedParts": "preserve_unmodified_parts",
        "requireReferenceIntegrity": "require_reference_integrity",
    }
    changes = {mapping[name]: setting for name, setting in value.items() if name in mapping}
    return policy.with_(**changes)


def _member_diff(before: bytes, after: bytes) -> dict[str, Any]:
    # Shared with the Safe Write Contract's MutationReport spine: one uncompressed
    # member comparison, one home for the diff shape (mutation_report.py).
    return member_diff_bytes(before, after)


def _verify_header_story_candidates(
    candidate_data: bytes,
    candidate_revision: str,
    expectations: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    if expectations:
        with HwpxDocument.open(candidate_data) as reopened:
            view = HwpxAgentDocument.from_document(
                reopened, revision=candidate_revision
            )
            for expectation in expectations.values():
                path = expectation["path"]
                binding = view._resolve_header_story(path)
                if (
                    binding.stable_id != expectation["stableId"]
                    or binding.page_type != expectation["pageType"]
                    or binding.text != expectation["text"]
                ):
                    raise AgentContractError(
                        "verification_failed",
                        "reopened header story does not match the committed binding",
                        target=path,
                    )
                receipts.append(
                    {
                        "commandId": expectation["commandId"],
                        "path": binding.path,
                        "stableId": binding.stable_id,
                        "pageType": binding.page_type,
                        "textMatched": True,
                    }
                )
    return {
        "schemaVersion": "hwpx.agent-story-preservation/v1",
        "ok": True,
        "storyCount": len(receipts),
        "stories": receipts,
    }


def _request_hash(batch: Mapping[str, Any]) -> str:
    payload = json.dumps(
        batch,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _revision(payload)


def _call_fault(injector: FaultInjector | None, stage: str, index: int | None = None) -> None:
    if injector is not None:
        injector(stage, index)


def _apply_commands_idempotency_lookup(
    verification: dict[str, Any],
    idempotency_store: IdempotencyStore | None,
    *,
    key: str | None,
    request_hash: str,
) -> AgentBatchResult | None:
    verification["idempotency"] = {
        "keyProvided": key is not None,
        "requestHash": request_hash,
        "replayed": False,
        "store": "caller-owned" if idempotency_store is not None else "none",
    }
    if key is not None and idempotency_store is not None and key in idempotency_store:
        cached = idempotency_store[key]
        if not isinstance(cached, Mapping) or cached.get("requestHash") != request_hash:
            raise AgentContractError(
                "idempotency_conflict",
                "idempotency key was used for a different request",
                target="batch.idempotencyKey",
            )
        prior = cached.get("result")
        if not isinstance(prior, AgentBatchResult):
            raise AgentContractError(
                "invariant_violation", "idempotency store contains an invalid result", target="batch.idempotencyKey"
            )
        replay_report = dict(prior.verification_report)
        replay_idempotency = dict(replay_report.get("idempotency", {}))
        replay_idempotency["replayed"] = True
        replay_report["idempotency"] = replay_idempotency
        return AgentBatchResult(
            ok=prior.ok,
            rolled_back=prior.rolled_back,
            dry_run=prior.dry_run,
            input_revision=prior.input_revision,
            document_revision=prior.document_revision,
            output_filename=prior.output_filename,
            command_results=prior.command_results,
            semantic_diff=prior.semantic_diff,
            verification_report=replay_report,
            error=prior.error,
        )
    return None


def _validate_apply_commands_input(
    normalized: Mapping[str, Any],
    verification: dict[str, Any],
    input_data: bytes,
    input_revision: str,
    output_path: Path,
) -> None:
    verification["revision"] = {
        "expected": normalized["expectedRevision"],
        "actual": input_revision,
        "matched": normalized["expectedRevision"] in {None, input_revision},
    }
    if normalized["expectedRevision"] not in {None, input_revision}:
        raise AgentContractError(
            "stale_revision", "expectedRevision does not match input bytes", target="batch.expectedRevision"
        )
    input_safety = validate_editor_open_safety(input_data)
    verification["inputOpenSafety"] = input_safety.to_dict()
    if not input_safety.ok:
        raise AgentContractError(
            "verification_failed",
            "input failed package/reopen/openSafety verification",
            target="batch.input.filename",
        )
    if output_path.exists() and not normalized["output"]["overwrite"] and not normalized["dryRun"]:
        raise AgentContractError(
            "invariant_violation", "output exists and overwrite is false", target="batch.output.filename"
        )


def _apply_commands_build_candidate_report(
    input_data: bytes,
    candidate_data: bytes,
    input_revision: str,
    semantic_changes: list[Mapping[str, Any]],
    identity_changes: list[Mapping[str, str]],
    story_expectations: Mapping[str, Mapping[str, str]],
    verification: dict[str, Any],
) -> tuple[str, dict[str, Any], Any, dict[str, Any]]:
    """Compute the candidate revision/semantic diff and write byte/package safety
    into ``verification``.

    Does not raise on unsafe candidates -- the original ordering runs domain
    verification before that check, so callers must still inspect the
    returned ``safety``/``byte_report``.
    """

    candidate_revision = _revision(candidate_data)
    if story_expectations:
        verification["storyPreservation"] = _verify_header_story_candidates(
            candidate_data,
            candidate_revision,
            story_expectations,
        )
    semantic_diff = {
        "schemaVersion": "hwpx.agent-semantic-diff/v1",
        "inputRevision": input_revision,
        "candidateRevision": candidate_revision,
        "changes": semantic_changes,
        "identityMap": identity_changes,
    }
    byte_report = _member_diff(input_data, candidate_data)
    safety = validate_editor_open_safety(candidate_data)
    safety_dict = safety.to_dict()
    verification.update(
        {
            "candidateRevision": candidate_revision,
            "package": safety_dict["validatePackage"],
            "reopen": safety_dict["reopen"],
            "openSafety": safety_dict,
            "semanticDiff": {"ok": True, "changeCount": len(semantic_changes)},
            "bytePreservation": byte_report,
        }
    )
    return candidate_revision, semantic_diff, safety, byte_report


def _apply_commands_domain_verification(
    candidate_data: bytes,
    normalized: Mapping[str, Any],
    requirements: set[str],
    domain_verifier: DomainVerifier | None,
    verification: dict[str, Any],
) -> None:
    if "domain" in requirements:
        if domain_verifier is None:
            verification["domain"] = {"ok": False, "error": "required verifier unavailable"}
            raise AgentContractError(
                "verification_failed", "required domain verifier is unavailable", target="domain"
            )
        domain_report = dict(domain_verifier(candidate_data, normalized))
        try:
            json.dumps(domain_report, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise AgentContractError(
                "verification_failed",
                "domain verifier returned a non-JSON report",
                target="domain",
            ) from exc
        verification["domain"] = domain_report
        if not domain_report.get("ok"):
            raise AgentContractError("verification_failed", "domain verification failed", target="domain")
    else:
        verification["domain"] = {"ok": None, "status": "not-requested"}


def _require_candidate_structural_safety(safety: Any, byte_report: Mapping[str, Any]) -> None:
    if not safety.ok or not byte_report.get("ok"):
        raise AgentContractError(
            "verification_failed", "candidate failed package/reopen/openSafety verification"
        )


def _apply_commands_run_save_pipeline(
    candidate_data: bytes,
    input_path: Path,
    output_path: Path,
    document: HwpxDocument,
    normalized: Mapping[str, Any],
    requirements: set[str],
    save_pipeline: SavePipeline | None,
    verification: dict[str, Any],
) -> Any:
    pipeline = save_pipeline or SavePipeline()
    quality_policy = _quality_policy(normalized["quality"])
    if "realHancom" in requirements:
        # Make the required oracle part of the atomic gate itself.  A
        # post-publication provenance check would be too late to roll
        # back an otherwise structurally valid file.
        quality_policy = quality_policy.with_(
            require_visual_complete=True,
            render_check="required",
        )
    quality_report = pipeline.run(
        candidate_data,
        output_path=None if normalized["dryRun"] else output_path,
        quality=quality_policy,
        before=input_path,
        reference_document=document,
        publish="never" if normalized["dryRun"] else "on_pass",
        source_label="agent.apply_document_commands",
    )
    verification["savePipeline"] = quality_report.to_dict()
    verification["realHancom"] = {
        "required": "realHancom" in requirements,
        "ok": quality_report.visual_complete,
        "status": quality_report.visual_complete_status,
        "renderChecked": quality_report.render_checked,
    }
    if "realHancom" in requirements and not quality_report.visual_complete:
        raise AgentContractError(
            "verification_failed",
            "required real-Hancom visual verification is unavailable or failed",
            target="realHancom",
        )
    if not quality_report.ok:
        raise AgentContractError(
            "verification_failed", "SavePipeline rejected the candidate", target="savePipeline"
        )
    return quality_report
