# SPDX-License-Identifier: Apache-2.0
"""Strict mixed-anchor form-fill planning over the semantic agent facade.

The module deliberately owns *planning only*.  It resolves four public locator
types against one immutable document revision, compiles them to ordinary
``hwpx.agent-batch/v1`` ``set`` commands, and delegates execution to
``apply_document_commands``.  There is no second mutation or save engine here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hwpx.quality import SavePipeline
from hwpx.table_patch import ResolvedCellTarget, resolve_cell_target

from .catalog import agent_json_schemas
from .commands import (
    DomainVerifier,
    FaultInjector,
    IdempotencyStore,
    apply_document_commands,
)
from .document import HwpxAgentDocument, NodeRecord
from .model import (
    AGENT_BATCH_SCHEMA,
    COMMAND_ID_PATTERN,
    MAX_COMMANDS,
    MAX_TEXT_CHARS,
    REVISION_PATTERN,
    STABILITY_LEVELS,
    VERIFICATION_REQUIREMENTS,
    AgentBatchResult,
    AgentContractError,
    _validate_quality,
    validate_agent_batch,
)
from .path import parse_path

# Public input authored by a client/agent (``operations[].target``).
MIXED_FORM_PLAN_SCHEMA = "hwpx.mixed-form-plan/v1"
# Internal normalized form (``operations[].locator``); not an MCP wire promise.
MIXED_FORM_REQUEST_SCHEMA = "hwpx.mixed-form-request/v1"
# Revision-bound output containing the single ``hwpx.agent-batch/v1`` request.
MIXED_FORM_COMPILED_PLAN_SCHEMA = "hwpx.mixed-form-compiled-plan/v1"
MIXED_FORM_LOCATOR_KINDS = (
    "nativeField",
    "labelCell",
    "canonicalPath",
    "bodyAnchor",
)

_FILLABLE_NODE_KINDS = frozenset({"paragraph", "run", "cell", "form-field"})
_DIRECTIONS = frozenset({"right", "left", "below", "above"})
_MIXED_FORM_IDENTITY_SCOPE = "hwpx.mixed-form-idempotency/v1"
_COMPILED_PLAN_KEYS = frozenset(
    {
        "schemaVersion",
        "inputRevision",
        "requestHash",
        "resolutions",
        "batch",
        "planHash",
    }
)
_RESOLUTION_KEYS = frozenset(
    {
        "operationId",
        "locatorKind",
        "path",
        "nodeKind",
        "stability",
        "section",
        "tableIndex",
        "logicalRow",
        "logicalColumn",
        "physicalRow",
        "physicalColumn",
    }
)


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentContractError("invalid_syntax", f"{name} must be an object", target=name)
    return dict(value)


def _array(value: object, name: str) -> list[Any]:
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


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentContractError("invalid_syntax", f"{name} must be a non-empty string", target=name)
    if len(value) > MAX_TEXT_CHARS:
        raise AgentContractError("resource_limit", f"{name} is too long", target=name)
    return value


def _value_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AgentContractError("invalid_syntax", f"{name} must be a string", target=name)
    if len(value) > MAX_TEXT_CHARS:
        raise AgentContractError("resource_limit", f"{name} is too long", target=name)
    return value


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AgentContractError(
            "invalid_syntax", f"{name} must be a one-based integer", target=name
        )
    return value


def _nonnegative_integer_or_none(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentContractError(
            "invalid_syntax", f"{name} must be a non-negative integer or null", target=name
        )
    return value


def _section_index_from_path(value: object, name: str) -> int:
    section_path = _nonempty_string(value, name)
    parsed = parse_path(section_path)
    if (
        len(parsed.segments) != 1
        or parsed.segments[0].kind != "section"
        or parsed.segments[0].index is None
    ):
        raise AgentContractError(
            "invalid_syntax",
            f"{name} must be a positional section path such as /section[1]",
            target=name,
        )
    return parsed.segments[0].index


def _canonical_hash(value: Mapping[str, Any]) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentContractError(
            "invalid_syntax", "mixed-form contract is not canonical JSON", target="mixedForm"
        ) from exc
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _assert_distinct_source_output(source: str, output: str) -> None:
    """Fail closed when output can name the input document itself.

    The lexical/real-path comparison catches ``.``/``..`` and symlink aliases,
    while ``samefile`` additionally catches distinct hard-link names.  This is
    intentionally run both while planning and immediately before execution so
    an output created or replaced between those phases cannot overwrite input.
    """

    source_path = Path(source)
    output_path = Path(output)
    try:
        source_resolved = source_path.resolve(strict=False)
        output_resolved = output_path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise AgentContractError(
            "verification_failed",
            f"source/output identity could not be resolved safely: {exc}",
            target="output.filename",
        ) from exc
    if source_resolved == output_resolved:
        raise AgentContractError(
            "invariant_violation",
            "mixed-form output must not resolve to the input document",
            target="output.filename",
        )
    try:
        same_file = source_path.samefile(output_path)
    except FileNotFoundError:
        same_file = False
    except OSError as exc:
        raise AgentContractError(
            "verification_failed",
            f"source/output identity could not be checked safely: {exc}",
            target="output.filename",
        ) from exc
    if same_file:
        raise AgentContractError(
            "invariant_violation",
            "mixed-form output must not alias the input document",
            target="output.filename",
        )


class _MixedFormIdempotencyStore(MutableMapping[str, Any]):
    """Translate one mixed-form identity to the batch executor's store shape.

    ``apply_document_commands`` remains the sole executor and continues to see
    its own batch hash.  The caller-owned backing store, however, records a
    scoped composite hash, so two distinct public locator requests cannot
    replay merely because they compile to the same canonical batch.
    """

    def __init__(
        self,
        backing: IdempotencyStore,
        *,
        active_key: str,
        mixed_form_request_hash: str,
        batch_request_hash: str,
    ) -> None:
        self._backing = backing
        self._active_key = active_key
        self._mixed_form_request_hash = mixed_form_request_hash
        self._batch_request_hash = batch_request_hash
        self._composite_hash = _canonical_hash(
            {
                "scope": _MIXED_FORM_IDENTITY_SCOPE,
                "mixedFormRequestHash": mixed_form_request_hash,
                "batchRequestHash": batch_request_hash,
            }
        )

    def __getitem__(self, key: str) -> Any:
        cached = self._backing[key]
        if key != self._active_key or not isinstance(cached, Mapping):
            return cached
        if (
            cached.get("requestHash") == self._composite_hash
            and cached.get("identityScope") == _MIXED_FORM_IDENTITY_SCOPE
            and cached.get("mixedFormRequestHash") == self._mixed_form_request_hash
            and cached.get("batchRequestHash") == self._batch_request_hash
        ):
            executor_view = dict(cached)
            executor_view["requestHash"] = self._batch_request_hash
            return executor_view
        # A standard batch entry, another mixed-form request, or a malformed
        # entry must conflict inside the existing typed executor path.
        conflict_view = dict(cached)
        conflict_view["requestHash"] = None
        return conflict_view

    def __setitem__(self, key: str, value: Any) -> None:
        if key != self._active_key or not isinstance(value, Mapping):
            self._backing[key] = value
            return
        stored = dict(value)
        stored.update(
            {
                "requestHash": self._composite_hash,
                "identityScope": _MIXED_FORM_IDENTITY_SCOPE,
                "mixedFormRequestHash": self._mixed_form_request_hash,
                "batchRequestHash": self._batch_request_hash,
            }
        )
        self._backing[key] = stored

    def __delitem__(self, key: str) -> None:
        del self._backing[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._backing)

    def __len__(self) -> int:
        return len(self._backing)


def _batch_request_shape(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """Detach validator output into the request shape the executor accepts.

    ``validate_agent_command`` annotates normalized commands with their schema
    version, while an ``hwpx.agent-batch/v1`` request intentionally omits that
    derived field.  The executor validates requests again, so compiled plans
    must retain the request shape rather than feed normalized commands back
    through a non-idempotent validator.
    """

    batch = deepcopy(dict(normalized))
    for command in batch["commands"]:
        command.pop("schemaVersion", None)
    return batch


def _validate_locator(value: object, *, name: str) -> dict[str, Any]:
    locator = _object(value, name)
    kind = str(locator.get("kind", ""))
    if kind not in MIXED_FORM_LOCATOR_KINDS:
        raise AgentContractError(
            "unknown_kind", f"unsupported mixed-form locator: {kind!r}", target=f"{name}.kind"
        )

    if kind == "nativeField":
        _exact_keys(
            locator,
            required={"kind"},
            optional={"fieldId", "name"},
            name=name,
        )
        selectors = [key for key in ("fieldId", "name") if key in locator]
        if len(selectors) != 1:
            raise AgentContractError(
                "invalid_syntax",
                f"{name} requires exactly one of fieldId or name",
                target=name,
            )
        selector = selectors[0]
        return {"kind": kind, selector: _nonempty_string(locator[selector], f"{name}.{selector}")}

    if kind == "labelCell":
        _exact_keys(
            locator,
            required={"kind", "section", "cellAnchor"},
            optional={"tableAnchor", "tableIndex"},
            name=name,
        )
        table_selectors = [key for key in ("tableAnchor", "tableIndex") if key in locator]
        if len(table_selectors) != 1:
            raise AgentContractError(
                "invalid_syntax",
                f"{name} requires exactly one of tableAnchor or tableIndex",
                target=name,
            )
        anchor = _object(locator["cellAnchor"], f"{name}.cellAnchor")
        _exact_keys(
            anchor,
            required={"label"},
            optional={"direction"},
            name=f"{name}.cellAnchor",
        )
        direction = str(anchor.get("direction", "right")).lower()
        if direction not in _DIRECTIONS:
            raise AgentContractError(
                "invalid_syntax",
                f"{name}.cellAnchor.direction is unsupported",
                target=f"{name}.cellAnchor.direction",
            )
        normalized: dict[str, Any] = {
            "kind": kind,
            "section": _positive_integer(locator["section"], f"{name}.section"),
            "cellAnchor": {
                "label": _nonempty_string(anchor["label"], f"{name}.cellAnchor.label"),
                "direction": direction,
            },
        }
        table_selector = table_selectors[0]
        if table_selector == "tableAnchor":
            normalized[table_selector] = _nonempty_string(
                locator[table_selector], f"{name}.tableAnchor"
            )
        else:
            index = locator[table_selector]
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise AgentContractError(
                    "invalid_syntax",
                    f"{name}.tableIndex must be a zero-based integer",
                    target=f"{name}.tableIndex",
                )
            normalized[table_selector] = index
        return normalized

    if kind == "canonicalPath":
        _exact_keys(locator, required={"kind", "path"}, name=name)
        return {"kind": kind, "path": _nonempty_string(locator["path"], f"{name}.path")}

    _exact_keys(locator, required={"kind", "section", "anchor"}, name=name)
    return {
        "kind": kind,
        "section": _positive_integer(locator["section"], f"{name}.section"),
        "anchor": _nonempty_string(locator["anchor"], f"{name}.anchor"),
    }


def _validate_plan_target(value: object, *, name: str) -> dict[str, Any]:
    """Validate the public ``hwpx.mixed-form-plan/v1`` target vocabulary."""

    target = _object(value, name)
    kind = str(target.get("kind", ""))
    if kind not in MIXED_FORM_LOCATOR_KINDS:
        raise AgentContractError(
            "unknown_kind", f"unsupported mixed-form target: {kind!r}", target=f"{name}.kind"
        )

    if kind == "nativeField":
        _exact_keys(target, required={"kind"}, optional={"fieldId", "name"}, name=name)
        selectors = [key for key in ("fieldId", "name") if key in target]
        if len(selectors) != 1:
            raise AgentContractError(
                "invalid_syntax",
                f"{name} requires exactly one of fieldId or name",
                target=name,
            )
        selector = selectors[0]
        return {
            "kind": kind,
            selector: _nonempty_string(target[selector], f"{name}.{selector}"),
        }

    if kind == "labelCell":
        _exact_keys(
            target,
            required={"kind", "sectionPath", "cellAnchor"},
            optional={"tableAnchor", "tableIndex"},
            name=name,
        )
        table_selectors = [key for key in ("tableAnchor", "tableIndex") if key in target]
        if len(table_selectors) != 1:
            raise AgentContractError(
                "invalid_syntax",
                f"{name} requires exactly one of tableAnchor or tableIndex",
                target=name,
            )
        anchor = _object(target["cellAnchor"], f"{name}.cellAnchor")
        _exact_keys(
            anchor,
            required={"label", "direction"},
            name=f"{name}.cellAnchor",
        )
        direction = _nonempty_string(
            anchor["direction"], f"{name}.cellAnchor.direction"
        ).lower()
        if direction not in _DIRECTIONS:
            raise AgentContractError(
                "invalid_syntax",
                f"{name}.cellAnchor.direction is unsupported",
                target=f"{name}.cellAnchor.direction",
            )
        normalized: dict[str, Any] = {
            "kind": kind,
            "section": _section_index_from_path(target["sectionPath"], f"{name}.sectionPath"),
            "cellAnchor": {
                "label": _nonempty_string(anchor["label"], f"{name}.cellAnchor.label"),
                "direction": direction,
            },
        }
        table_selector = table_selectors[0]
        if table_selector == "tableAnchor":
            normalized[table_selector] = _nonempty_string(
                target[table_selector], f"{name}.tableAnchor"
            )
        else:
            table_index = target[table_selector]
            if isinstance(table_index, bool) or not isinstance(table_index, int) or table_index < 0:
                raise AgentContractError(
                    "invalid_syntax",
                    f"{name}.tableIndex must be a zero-based integer",
                    target=f"{name}.tableIndex",
                )
            normalized[table_selector] = table_index
        return normalized

    if kind == "canonicalPath":
        _exact_keys(target, required={"kind", "path"}, name=name)
        return {"kind": kind, "path": _nonempty_string(target["path"], f"{name}.path")}

    _exact_keys(
        target,
        required={"kind", "sectionPath", "anchor", "expectedCount"},
        name=name,
    )
    expected_count = target["expectedCount"]
    if isinstance(expected_count, bool) or expected_count != 1:
        raise AgentContractError(
            "invalid_syntax",
            f"{name}.expectedCount must be exactly 1",
            target=f"{name}.expectedCount",
        )
    return {
        "kind": kind,
        "section": _section_index_from_path(target["sectionPath"], f"{name}.sectionPath"),
        "anchor": _nonempty_string(target["anchor"], f"{name}.anchor"),
        "expectedCount": 1,
    }


def _validate_public_plan_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the P1-frozen public plan into the internal request shape."""

    required = {
        "schemaVersion",
        "source",
        "output",
        "expectedRevision",
        "idempotencyKey",
        "dryRun",
        "overwrite",
        "quality",
        "verificationRequirements",
        "operations",
    }
    _exact_keys(request, required=required, name="mixedFormPlan")
    source = _nonempty_string(request["source"], "mixedFormPlan.source")
    output = _nonempty_string(request["output"], "mixedFormPlan.output")
    if not isinstance(request["dryRun"], bool):
        raise AgentContractError(
            "invalid_syntax", "mixedFormPlan.dryRun must be boolean", target="mixedFormPlan.dryRun"
        )
    if not isinstance(request["overwrite"], bool):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormPlan.overwrite must be boolean",
            target="mixedFormPlan.overwrite",
        )

    expected_revision = request["expectedRevision"]
    if expected_revision is not None and (
        not isinstance(expected_revision, str)
        or REVISION_PATTERN.fullmatch(expected_revision) is None
    ):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormPlan.expectedRevision must be sha256 or null",
            target="mixedFormPlan.expectedRevision",
        )
    idempotency_key = request["idempotencyKey"]
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128
    ):
        raise AgentContractError(
            "resource_limit",
            "mixedFormPlan.idempotencyKey length is invalid",
            target="mixedFormPlan.idempotencyKey",
        )

    raw_operations = _array(request["operations"], "mixedFormPlan.operations")
    if not raw_operations or len(raw_operations) > MAX_COMMANDS:
        raise AgentContractError(
            "resource_limit",
            "mixedFormPlan.operations count is out of bounds",
            target="mixedFormPlan.operations",
        )
    operations: list[dict[str, Any]] = []
    operation_ids: list[str] = []
    for index, raw_operation in enumerate(raw_operations):
        name = f"mixedFormPlan.operations[{index}]"
        operation = _object(raw_operation, name)
        _exact_keys(operation, required={"operationId", "target", "value"}, name=name)
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not COMMAND_ID_PATTERN.fullmatch(operation_id):
            raise AgentContractError(
                "invalid_syntax", f"{name}.operationId is invalid", target=f"{name}.operationId"
            )
        operation_ids.append(operation_id)
        operations.append(
            {
                "operationId": operation_id,
                "locator": _validate_plan_target(operation["target"], name=f"{name}.target"),
                "value": _value_string(operation["value"], f"{name}.value"),
            }
        )
    if len(operation_ids) != len(set(operation_ids)):
        raise AgentContractError(
            "invariant_violation",
            "mixed-form operationId values must be unique",
            target="mixedFormPlan.operations",
        )

    requirements = _array(
        request["verificationRequirements"], "mixedFormPlan.verificationRequirements"
    )
    if any(not isinstance(item, str) for item in requirements):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormPlan.verificationRequirements items must be strings",
            target="mixedFormPlan.verificationRequirements",
        )
    unknown_requirements = sorted(set(requirements) - set(VERIFICATION_REQUIREMENTS))
    if unknown_requirements:
        raise AgentContractError(
            "invalid_syntax",
            f"unknown verification requirements: {unknown_requirements}",
            target="mixedFormPlan.verificationRequirements",
        )
    return {
        "schemaVersion": MIXED_FORM_REQUEST_SCHEMA,
        "input": {"filename": source},
        "output": {"filename": output, "overwrite": request["overwrite"]},
        "operations": operations,
        "expectedRevision": expected_revision,
        "idempotencyKey": idempotency_key,
        "dryRun": request["dryRun"],
        "quality": _validate_quality(request["quality"]),
        "verificationRequirements": list(dict.fromkeys(requirements)),
    }


def validate_mixed_form_request(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a public plan or internal envelope into the internal shape."""

    request = _object(value, "mixedFormRequest")
    schema_version = request.get("schemaVersion")
    if schema_version == MIXED_FORM_PLAN_SCHEMA:
        return _validate_public_plan_request(request)
    if schema_version != MIXED_FORM_REQUEST_SCHEMA:
        raise AgentContractError(
            "invalid_syntax", "unsupported mixed-form request schema", target="schemaVersion"
        )
    required = {
        "schemaVersion",
        "input",
        "output",
        "operations",
        "expectedRevision",
        "idempotencyKey",
        "dryRun",
        "quality",
        "verificationRequirements",
    }
    _exact_keys(request, required=required, name="mixedFormRequest")
    input_ref = _object(request["input"], "mixedFormRequest.input")
    _exact_keys(input_ref, required={"filename"}, name="mixedFormRequest.input")
    input_filename = _nonempty_string(
        input_ref["filename"], "mixedFormRequest.input.filename"
    )

    output_ref = _object(request["output"], "mixedFormRequest.output")
    _exact_keys(
        output_ref,
        required={"filename", "overwrite"},
        name="mixedFormRequest.output",
    )
    output_filename = _nonempty_string(
        output_ref["filename"], "mixedFormRequest.output.filename"
    )
    if not isinstance(output_ref["overwrite"], bool):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormRequest.output.overwrite must be boolean",
            target="mixedFormRequest.output.overwrite",
        )

    raw_operations = _array(request["operations"], "mixedFormRequest.operations")
    if not raw_operations or len(raw_operations) > MAX_COMMANDS:
        raise AgentContractError(
            "resource_limit",
            "mixedFormRequest.operations count is out of bounds",
            target="mixedFormRequest.operations",
        )
    operations: list[dict[str, Any]] = []
    operation_ids: list[str] = []
    for index, raw_operation in enumerate(raw_operations):
        name = f"mixedFormRequest.operations[{index}]"
        operation = _object(raw_operation, name)
        _exact_keys(operation, required={"operationId", "locator", "value"}, name=name)
        operation_id = str(operation.get("operationId", ""))
        if not COMMAND_ID_PATTERN.fullmatch(operation_id):
            raise AgentContractError(
                "invalid_syntax", f"{name}.operationId is invalid", target=f"{name}.operationId"
            )
        operation_ids.append(operation_id)
        operations.append(
            {
                "operationId": operation_id,
                "locator": _validate_locator(operation["locator"], name=f"{name}.locator"),
                "value": _value_string(operation["value"], f"{name}.value"),
            }
        )
    if len(operation_ids) != len(set(operation_ids)):
        raise AgentContractError(
            "invariant_violation",
            "mixed-form operationId values must be unique",
            target="mixedFormRequest.operations",
        )

    expected_revision = request["expectedRevision"]
    if expected_revision is not None and not REVISION_PATTERN.fullmatch(str(expected_revision)):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormRequest.expectedRevision must be sha256 or null",
            target="mixedFormRequest.expectedRevision",
        )
    idempotency_key = request["idempotencyKey"]
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128
    ):
        raise AgentContractError(
            "resource_limit",
            "mixedFormRequest.idempotencyKey length is invalid",
            target="mixedFormRequest.idempotencyKey",
        )
    if not isinstance(request["dryRun"], bool):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormRequest.dryRun must be boolean",
            target="mixedFormRequest.dryRun",
        )

    requirements = _array(
        request["verificationRequirements"],
        "mixedFormRequest.verificationRequirements",
    )
    if any(not isinstance(item, str) for item in requirements):
        raise AgentContractError(
            "invalid_syntax",
            "mixedFormRequest.verificationRequirements items must be strings",
            target="mixedFormRequest.verificationRequirements",
        )
    unknown_requirements = sorted(set(requirements) - set(VERIFICATION_REQUIREMENTS))
    if unknown_requirements:
        raise AgentContractError(
            "invalid_syntax",
            f"unknown verification requirements: {unknown_requirements}",
            target="mixedFormRequest.verificationRequirements",
        )

    return {
        "schemaVersion": MIXED_FORM_REQUEST_SCHEMA,
        "input": {"filename": input_filename},
        "output": {
            "filename": output_filename,
            "overwrite": output_ref["overwrite"],
        },
        "operations": operations,
        "expectedRevision": None if expected_revision is None else str(expected_revision),
        "idempotencyKey": idempotency_key,
        "dryRun": request["dryRun"],
        "quality": _validate_quality(request["quality"]),
        "verificationRequirements": list(dict.fromkeys(str(item) for item in requirements)),
    }


@dataclass(frozen=True, slots=True)
class MixedFormResolution:
    operation_id: str
    locator_kind: str
    path: str
    node_kind: str
    stability: str
    section: int | None = None
    table_index: int | None = None
    logical_row: int | None = None
    logical_column: int | None = None
    physical_row: int | None = None
    physical_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operationId": self.operation_id,
            "locatorKind": self.locator_kind,
            "path": self.path,
            "nodeKind": self.node_kind,
            "stability": self.stability,
            "section": self.section,
            "tableIndex": self.table_index,
            "logicalRow": self.logical_row,
            "logicalColumn": self.logical_column,
            "physicalRow": self.physical_row,
            "physicalColumn": self.physical_column,
        }


@dataclass(frozen=True, slots=True)
class MixedFormPlan:
    input_revision: str
    request_hash: str
    resolutions: tuple[MixedFormResolution, ...]
    batch: Mapping[str, Any]
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": MIXED_FORM_COMPILED_PLAN_SCHEMA,
            "inputRevision": self.input_revision,
            "requestHash": self.request_hash,
            "resolutions": [resolution.to_dict() for resolution in self.resolutions],
            "batch": deepcopy(dict(self.batch)),
            "planHash": self.plan_hash,
        }


def _section_record(agent: HwpxAgentDocument, section_index: int) -> NodeRecord:
    matches = [
        record
        for record in agent.records
        if record.kind == "section" and record.summary.get("index") == section_index
    ]
    if not matches:
        raise AgentContractError(
            "not_found", f"section {section_index} was not found", target=f"section[{section_index}]"
        )
    if len(matches) != 1:  # pragma: no cover - projection invariant
        raise AgentContractError(
            "invariant_violation",
            f"section {section_index} projected more than once",
            target=f"section[{section_index}]",
        )
    return matches[0]


def _native_field_record(agent: HwpxAgentDocument, locator: Mapping[str, Any]) -> NodeRecord:
    records = [record for record in agent.records if record.kind == "form-field"]
    if "fieldId" in locator:
        wanted = str(locator["fieldId"]).strip()
        matches = [
            record
            for record in records
            if wanted
            in {
                str(record.native.get("field_id") or ""),
                str(record.native.get("id") or ""),
                str(record.native.get("fieldid") or ""),
            }
        ]
        target = f"nativeField.fieldId={wanted!r}"
    else:
        wanted = str(locator["name"]).strip().casefold()
        matches = [
            record
            for record in records
            if wanted
            in {
                str(record.native.get("name") or "").strip().casefold(),
                str(record.native.get("prompt") or "").strip().casefold(),
                str(record.native.get("instruction") or "").strip().casefold(),
            }
        ]
        target = f"nativeField.name={locator['name']!r}"
    if not matches:
        raise AgentContractError("not_found", "native form field was not found", target=target)
    if len(matches) > 1:
        raise AgentContractError(
            "ambiguous_target",
            f"native form-field locator matched {len(matches)} fields",
            target=target,
        )
    return matches[0]


def _table_resolution_error(exc: ValueError, *, target: str) -> AgentContractError:
    message = str(exc)
    lowered = message.casefold()
    if "ambiguous" in lowered:
        code = "ambiguous_target"
    elif "invalid" in lowered:
        code = "unsupported_content"
    else:
        code = "not_found"
    return AgentContractError(code, message, target=target)


def _table_cell_record(
    agent: HwpxAgentDocument,
    section: NodeRecord,
    target: ResolvedCellTarget,
) -> NodeRecord:
    part_name = str(section.native.part_name)
    tables = [
        record
        for record in agent.records
        if record.kind == "table"
        and str(record.native.paragraph.section.part_name) == part_name
    ]
    if not 0 <= target.table_index < len(tables):
        raise AgentContractError(
            "invariant_violation",
            "byte table ordinal is absent from the semantic projection",
            target=f"table[{target.table_index}]",
        )
    table = tables[target.table_index]
    matches = [
        record
        for record in agent.records
        if record.kind == "cell"
        and record.native.table.element is table.native.element
        and tuple(record.native.address) == (target.row, target.col)
    ]
    if not matches:
        raise AgentContractError(
            "not_found",
            "resolved physical cell is absent from the semantic projection",
            target=table.path,
        )
    if len(matches) > 1:  # pragma: no cover - invalid projection invariant
        raise AgentContractError(
            "ambiguous_target",
            "resolved physical cell projected more than once",
            target=table.path,
        )
    return matches[0]


def _label_cell_record(
    agent: HwpxAgentDocument,
    source_bytes: bytes,
    locator: Mapping[str, Any],
) -> tuple[NodeRecord, ResolvedCellTarget]:
    section_index = int(locator["section"])
    section = _section_record(agent, section_index)
    byte_locator: dict[str, Any] = {
        "section_path": str(section.native.part_name),
        "cell_anchor": {
            "label": locator["cellAnchor"]["label"],
            "direction": locator["cellAnchor"]["direction"],
        },
    }
    if "tableAnchor" in locator:
        byte_locator["table_anchor"] = locator["tableAnchor"]
    else:
        byte_locator["table_index"] = locator["tableIndex"]
    try:
        resolved = resolve_cell_target(source_bytes, byte_locator)
    except ValueError as exc:
        raise _table_resolution_error(exc, target="labelCell") from exc
    return _table_cell_record(agent, section, resolved), resolved


def _local_name(element: Any) -> str:
    return str(getattr(element, "tag", "")).rsplit("}", 1)[-1]


def _body_anchor_record(
    agent: HwpxAgentDocument,
    locator: Mapping[str, Any],
) -> tuple[NodeRecord, str]:
    section_index = int(locator["section"])
    section = _section_record(agent, section_index)
    anchor = str(locator["anchor"])
    paragraphs = [
        record
        for record in agent.records
        if record.kind == "paragraph" and record.parent_path == section.path
    ]
    occurrences: list[tuple[NodeRecord, int]] = []
    for paragraph in paragraphs:
        count = str(paragraph.native.text).count(anchor)
        if count:
            occurrences.append((paragraph, count))
    total = sum(count for _paragraph, count in occurrences)
    if total == 0:
        raise AgentContractError(
            "not_found", "direct-body anchor was not found", target=f"bodyAnchor={anchor!r}"
        )
    if total != 1:
        raise AgentContractError(
            "ambiguous_target",
            f"direct-body anchor matched {total} times",
            target=f"bodyAnchor={anchor!r}",
        )
    paragraph = occurrences[0][0]
    runs = [
        record
        for record in agent.records
        if record.kind == "run" and record.parent_path == paragraph.path
    ]
    run_hits = [(record, str(record.native.text).count(anchor)) for record in runs]
    run_hits = [(record, count) for record, count in run_hits if count]
    if not run_hits:
        raise AgentContractError(
            "unsupported_content",
            "direct-body anchor crosses run boundaries",
            target=paragraph.path,
        )
    if sum(count for _record, count in run_hits) != 1:
        raise AgentContractError(
            "ambiguous_target",
            "direct-body anchor is ambiguous within its paragraph",
            target=paragraph.path,
        )
    run = run_hits[0][0]
    children = list(run.native.element)
    if not children or any(_local_name(child) != "t" or len(list(child)) for child in children):
        raise AgentContractError(
            "unsupported_content",
            "direct-body anchor run contains non-plain inline content",
            target=run.path,
        )
    return run, str(run.native.text).replace(anchor, str(locator.get("value", "")), 1)


def _compile_operation(
    agent: HwpxAgentDocument,
    source_bytes: bytes,
    operation: Mapping[str, Any],
) -> tuple[dict[str, Any], MixedFormResolution]:
    operation_id = str(operation["operationId"])
    locator = operation["locator"]
    locator_kind = str(locator["kind"])
    value = str(operation["value"])
    resolved_table: ResolvedCellTarget | None = None

    if locator_kind == "nativeField":
        record = _native_field_record(agent, locator)
        property_name = "value"
        compiled_value = value
    elif locator_kind == "labelCell":
        record, resolved_table = _label_cell_record(agent, source_bytes, locator)
        property_name = "text"
        compiled_value = value
    elif locator_kind == "canonicalPath":
        record = agent.resolve_record(str(locator["path"]), expected_revision=agent.revision)
        if record.kind not in _FILLABLE_NODE_KINDS:
            raise AgentContractError(
                "unsupported_operation",
                f"canonical path targets non-fillable kind {record.kind!r}",
                target=record.path,
            )
        property_name = "value" if record.kind == "form-field" else "text"
        compiled_value = value
    else:
        body_locator = dict(locator)
        body_locator["value"] = value
        record, compiled_value = _body_anchor_record(agent, body_locator)
        property_name = "text"

    command = {
        "commandId": operation_id,
        "op": "set",
        "path": record.path,
        "properties": {property_name: compiled_value},
    }
    section = int(locator["section"]) if "section" in locator else None
    resolution = MixedFormResolution(
        operation_id=operation_id,
        locator_kind=locator_kind,
        path=record.path,
        node_kind=record.kind,
        stability=record.stability,
        section=section,
        table_index=(resolved_table.table_index if resolved_table is not None else None),
        logical_row=(resolved_table.logical_row if resolved_table is not None else None),
        logical_column=(resolved_table.logical_col if resolved_table is not None else None),
        physical_row=(resolved_table.row if resolved_table is not None else None),
        physical_column=(resolved_table.col if resolved_table is not None else None),
    )
    return command, resolution


def plan_mixed_form_fill(request: Mapping[str, Any]) -> MixedFormPlan:
    """Resolve four target types and compile one revision-bound agent batch."""

    normalized = validate_mixed_form_request(request)
    input_path = Path(normalized["input"]["filename"])
    _assert_distinct_source_output(
        normalized["input"]["filename"],
        normalized["output"]["filename"],
    )
    try:
        source_bytes = input_path.read_bytes()
    except OSError as exc:
        raise AgentContractError(
            "not_found", f"mixed-form input could not be read: {exc}", target="input.filename"
        ) from exc

    actual_revision = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    expected_revision = normalized["expectedRevision"]
    if expected_revision not in {None, actual_revision}:
        raise AgentContractError(
            "stale_revision",
            "mixed-form expectedRevision does not match input bytes",
            target="expectedRevision",
        )

    commands: list[dict[str, Any]] = []
    resolutions: list[MixedFormResolution] = []
    try:
        with HwpxAgentDocument.open(source_bytes) as agent:
            for operation in normalized["operations"]:
                command, resolution = _compile_operation(agent, source_bytes, operation)
                commands.append(command)
                resolutions.append(resolution)
    except AgentContractError:
        raise
    except Exception as exc:
        raise AgentContractError(
            "verification_failed",
            f"mixed-form input could not be projected safely: {type(exc).__name__}: {exc}",
            target="input.filename",
        ) from exc

    resolved_paths = [resolution.path for resolution in resolutions]
    if len(resolved_paths) != len(set(resolved_paths)):
        raise AgentContractError(
            "identity_collision",
            "mixed-form operations resolve to the same canonical target",
            target="operations",
        )

    normalized_batch = validate_agent_batch(
        {
            "schemaVersion": AGENT_BATCH_SCHEMA,
            "input": deepcopy(normalized["input"]),
            "output": deepcopy(normalized["output"]),
            "commands": commands,
            # A compiled plan is always revision-bound, including when the
            # planning request deliberately supplied null.
            "expectedRevision": actual_revision,
            "idempotencyKey": normalized["idempotencyKey"],
            "dryRun": normalized["dryRun"],
            "quality": deepcopy(normalized["quality"]),
            "verificationRequirements": list(normalized["verificationRequirements"]),
        }
    )
    batch = _batch_request_shape(normalized_batch)
    request_hash = _canonical_hash(normalized)
    plan_payload: dict[str, Any] = {
        "schemaVersion": MIXED_FORM_COMPILED_PLAN_SCHEMA,
        "inputRevision": actual_revision,
        "requestHash": request_hash,
        "resolutions": [resolution.to_dict() for resolution in resolutions],
        "batch": deepcopy(batch),
        "planHash": None,
    }
    plan_hash = _canonical_hash(plan_payload)
    return MixedFormPlan(
        input_revision=actual_revision,
        request_hash=request_hash,
        resolutions=tuple(resolutions),
        batch=batch,
        plan_hash=plan_hash,
    )


def _validate_mixed_form_plan_digests(plan: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return (input_revision, request_hash, plan_hash) after schema/sha256 checks."""

    if plan["schemaVersion"] != MIXED_FORM_COMPILED_PLAN_SCHEMA:
        raise AgentContractError(
            "invalid_syntax", "unsupported mixed-form plan schema", target="schemaVersion"
        )
    input_revision = str(plan["inputRevision"])
    request_hash = str(plan["requestHash"])
    plan_hash = str(plan["planHash"])
    for name, digest in (
        ("inputRevision", input_revision),
        ("requestHash", request_hash),
        ("planHash", plan_hash),
    ):
        if not REVISION_PATTERN.fullmatch(digest):
            raise AgentContractError(
                "invalid_syntax", f"mixedFormPlan.{name} must be sha256", target=name
            )
    return input_revision, request_hash, plan_hash


def _parse_mixed_form_resolution_fields(
    name: str, resolution: Mapping[str, Any]
) -> tuple[str, str, str, int | None, int | None, int | None, int | None, int | None, int | None, str, Any]:
    """Extract + type/shape-validate one resolution's fields (no locator-kind cross-checks).

    Returns (locator_kind, node_kind, stability, section, table_index, logical_row,
    logical_column, physical_row, physical_column, path, parsed_path).
    """

    locator_kind = str(resolution["locatorKind"])
    node_kind = str(resolution["nodeKind"])
    stability = str(resolution["stability"])
    if locator_kind not in MIXED_FORM_LOCATOR_KINDS:
        raise AgentContractError("unknown_kind", "unknown plan locator kind", target=name)
    if node_kind not in _FILLABLE_NODE_KINDS:
        raise AgentContractError("unknown_kind", "plan targets a non-fillable kind", target=name)
    if stability not in STABILITY_LEVELS:
        raise AgentContractError("invalid_syntax", "unknown path stability", target=name)
    section = resolution["section"]
    if section is not None:
        section = _positive_integer(section, f"{name}.section")
    table_index = _nonnegative_integer_or_none(resolution["tableIndex"], f"{name}.tableIndex")
    logical_row = _nonnegative_integer_or_none(resolution["logicalRow"], f"{name}.logicalRow")
    logical_column = _nonnegative_integer_or_none(
        resolution["logicalColumn"], f"{name}.logicalColumn"
    )
    physical_row = _nonnegative_integer_or_none(
        resolution["physicalRow"], f"{name}.physicalRow"
    )
    physical_column = _nonnegative_integer_or_none(
        resolution["physicalColumn"], f"{name}.physicalColumn"
    )
    path = _nonempty_string(resolution["path"], f"{name}.path")
    parsed_path = parse_path(path)
    if parsed_path.canonical != path or not parsed_path.segments:
        raise AgentContractError(
            "invalid_syntax", "resolution path must be canonical and non-root", target=f"{name}.path"
        )
    path_kind = parsed_path.segments[-1].kind
    if node_kind != path_kind:
        raise AgentContractError(
            "invariant_violation",
            "resolution nodeKind does not match its canonical path kind",
            target=name,
        )
    return (
        locator_kind, node_kind, stability, section, table_index,
        logical_row, logical_column, physical_row, physical_column, path, parsed_path,
    )


def _check_label_cell_or_table_coordinates(
    name: str, locator_kind: str, node_kind: str, section: int | None, coordinates: tuple[Any, ...]
) -> None:
    if locator_kind == "labelCell":
        if section is None or any(item is None for item in coordinates) or node_kind != "cell":
            raise AgentContractError(
                "invariant_violation", "labelCell plan lacks a physical resolution", target=name
            )
    elif any(item is not None for item in coordinates):
        raise AgentContractError(
            "invariant_violation", "non-table plan carries table coordinates", target=name
        )


def _check_native_field_invariant(name: str, locator_kind: str, node_kind: str, section: int | None) -> None:
    if locator_kind == "nativeField" and (node_kind != "form-field" or section is not None):
        raise AgentContractError(
            "invariant_violation",
            "nativeField plan must resolve only to a form-field without section metadata",
            target=name,
        )


def _check_canonical_path_invariant(name: str, locator_kind: str, section: int | None) -> None:
    if locator_kind == "canonicalPath" and section is not None:
        raise AgentContractError(
            "invariant_violation",
            "canonicalPath plan must not carry locator section metadata",
            target=name,
        )


def _check_body_anchor_invariant(name: str, locator_kind: str, node_kind: str, section: int | None) -> None:
    if locator_kind == "bodyAnchor" and (node_kind != "run" or section is None):
        raise AgentContractError(
            "invariant_violation",
            "bodyAnchor plan must resolve to a run in its declared section",
            target=name,
        )


def _check_resolution_section_membership(
    name: str, locator_kind: str, parsed_path: Any, section: int | None
) -> None:
    if locator_kind in {"labelCell", "bodyAnchor"}:
        first = parsed_path.segments[0]
        if first.kind != "section" or first.index != section:
            raise AgentContractError(
                "invariant_violation",
                "resolution path does not belong to its declared section",
                target=name,
            )


def _check_locator_kind_invariants(
    name: str,
    locator_kind: str,
    node_kind: str,
    section: int | None,
    coordinates: tuple[Any, ...],
    parsed_path: Any,
) -> None:
    _check_label_cell_or_table_coordinates(name, locator_kind, node_kind, section, coordinates)
    _check_native_field_invariant(name, locator_kind, node_kind, section)
    _check_canonical_path_invariant(name, locator_kind, section)
    _check_body_anchor_invariant(name, locator_kind, node_kind, section)
    _check_resolution_section_membership(name, locator_kind, parsed_path, section)


def _validate_one_mixed_form_resolution(index: int, raw_resolution: Any) -> MixedFormResolution:
    name = f"mixedFormPlan.resolutions[{index}]"
    resolution = _object(raw_resolution, name)
    _exact_keys(resolution, required=_RESOLUTION_KEYS, name=name)
    (
        locator_kind, node_kind, stability, section, table_index,
        logical_row, logical_column, physical_row, physical_column, path, parsed_path,
    ) = _parse_mixed_form_resolution_fields(name, resolution)
    coordinates = (table_index, logical_row, logical_column, physical_row, physical_column)
    _check_locator_kind_invariants(name, locator_kind, node_kind, section, coordinates, parsed_path)
    operation_id = str(resolution["operationId"])
    if not COMMAND_ID_PATTERN.fullmatch(operation_id):
        raise AgentContractError("invalid_syntax", "invalid resolution operationId", target=name)
    return MixedFormResolution(
        operation_id=operation_id,
        locator_kind=locator_kind,
        path=path,
        node_kind=node_kind,
        stability=stability,
        section=section,
        table_index=table_index,
        logical_row=logical_row,
        logical_column=logical_column,
        physical_row=physical_row,
        physical_column=physical_column,
    )


def _validate_mixed_form_resolutions(plan: Mapping[str, Any]) -> list[MixedFormResolution]:
    raw_resolutions = _array(plan["resolutions"], "mixedFormPlan.resolutions")
    return [
        _validate_one_mixed_form_resolution(index, raw_resolution)
        for index, raw_resolution in enumerate(raw_resolutions)
    ]


def _validate_mixed_form_batch_alignment(
    plan: Mapping[str, Any], input_revision: str, resolutions: list[MixedFormResolution]
) -> Mapping[str, Any]:
    """Validate the compiled batch matches its resolutions 1:1; return the batch shape."""

    normalized_batch = validate_agent_batch(_object(plan["batch"], "mixedFormPlan.batch"))
    batch = _batch_request_shape(normalized_batch)
    if normalized_batch["expectedRevision"] != input_revision:
        raise AgentContractError(
            "stale_revision", "compiled batch is not bound to inputRevision", target="batch.expectedRevision"
        )
    if len(resolutions) != len(normalized_batch["commands"]):
        raise AgentContractError(
            "invariant_violation", "resolution and command counts differ", target="resolutions"
        )
    if len({resolution.path for resolution in resolutions}) != len(resolutions):
        raise AgentContractError(
            "identity_collision",
            "compiled plan contains duplicate canonical targets",
            target="resolutions",
        )
    for resolution, command in zip(resolutions, normalized_batch["commands"]):
        if (
            command["commandId"] != resolution.operation_id
            or command["op"] != "set"
            or command["path"] != resolution.path
        ):
            raise AgentContractError(
                "invariant_violation",
                "compiled command does not match its resolution",
                target=resolution.operation_id,
            )
        expected_property = "value" if resolution.node_kind == "form-field" else "text"
        if set(command["properties"]) != {expected_property}:
            raise AgentContractError(
                "invariant_violation",
                "compiled command has a non-fill property",
                target=resolution.operation_id,
            )
    return batch


def validate_mixed_form_plan(value: MixedFormPlan | Mapping[str, Any]) -> MixedFormPlan:
    """Validate a detached compiled plan, including its content hash."""

    plan = value.to_dict() if isinstance(value, MixedFormPlan) else _object(value, "mixedFormPlan")
    _exact_keys(plan, required=_COMPILED_PLAN_KEYS, name="mixedFormPlan")
    input_revision, request_hash, plan_hash = _validate_mixed_form_plan_digests(plan)
    resolutions = _validate_mixed_form_resolutions(plan)
    batch = _validate_mixed_form_batch_alignment(plan, input_revision, resolutions)

    hash_payload = deepcopy(plan)
    hash_payload["planHash"] = None
    if _canonical_hash(hash_payload) != plan_hash:
        raise AgentContractError(
            "verification_failed", "mixed-form plan hash mismatch", target="planHash"
        )
    return MixedFormPlan(
        input_revision=input_revision,
        request_hash=request_hash,
        resolutions=tuple(resolutions),
        batch=batch,
        plan_hash=plan_hash,
    )


def apply_mixed_form_plan(
    plan: MixedFormPlan | Mapping[str, Any],
    *,
    idempotency_store: IdempotencyStore | None = None,
    fault_injector: FaultInjector | None = None,
    domain_verifier: DomainVerifier | None = None,
    save_pipeline: SavePipeline | None = None,
) -> AgentBatchResult:
    """Validate a compiled plan and delegate to the sole agent batch executor."""

    normalized = validate_mixed_form_plan(plan)
    _assert_distinct_source_output(
        str(normalized.batch["input"]["filename"]),
        str(normalized.batch["output"]["filename"]),
    )
    executor_store = idempotency_store
    idempotency_key = normalized.batch["idempotencyKey"]
    if idempotency_store is not None and idempotency_key is not None:
        executor_store = _MixedFormIdempotencyStore(
            idempotency_store,
            active_key=str(idempotency_key),
            mixed_form_request_hash=normalized.request_hash,
            batch_request_hash=_canonical_hash(validate_agent_batch(normalized.batch)),
        )
    return apply_document_commands(
        normalized.batch,
        idempotency_store=executor_store,
        fault_injector=fault_injector,
        domain_verifier=domain_verifier,
        save_pipeline=save_pipeline,
    )


def apply_mixed_form_fill(
    request: Mapping[str, Any],
    *,
    idempotency_store: IdempotencyStore | None = None,
    fault_injector: FaultInjector | None = None,
    domain_verifier: DomainVerifier | None = None,
    save_pipeline: SavePipeline | None = None,
) -> AgentBatchResult:
    """Resolve every locator, then execute the resulting single atomic batch."""

    return apply_mixed_form_plan(
        plan_mixed_form_fill(request),
        idempotency_store=idempotency_store,
        fault_injector=fault_injector,
        domain_verifier=domain_verifier,
        save_pipeline=save_pipeline,
    )


def mixed_form_json_schemas() -> dict[str, Any]:
    """Return the three explicit mixed-form contract schemas.

    ``plan`` is the public, human/agent-authored input. ``internalRequest`` is
    the normalized locator envelope used inside the core. ``compiledPlan`` is
    the revision-bound, hash-protected output consumed by
    :func:`apply_mixed_form_plan`.
    """

    agent_schemas = agent_json_schemas()
    locator_variants = [
        {
            "type": "object",
            "required": ["kind", "fieldId"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "nativeField"},
                "fieldId": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
            },
        },
        {
            "type": "object",
            "required": ["kind", "name"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "nativeField"},
                "name": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
            },
        },
        {
            "type": "object",
            "required": ["kind", "section", "tableAnchor", "cellAnchor"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "labelCell"},
                "section": {"type": "integer", "minimum": 1},
                "tableAnchor": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
                "cellAnchor": {"$ref": "#/$defs/cellAnchor"},
            },
        },
        {
            "type": "object",
            "required": ["kind", "section", "tableIndex", "cellAnchor"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "labelCell"},
                "section": {"type": "integer", "minimum": 1},
                "tableIndex": {"type": "integer", "minimum": 0},
                "cellAnchor": {"$ref": "#/$defs/cellAnchor"},
            },
        },
        {
            "type": "object",
            "required": ["kind", "path"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "canonicalPath"},
                "path": {"type": "string", "minLength": 1},
            },
        },
        {
            "type": "object",
            "required": ["kind", "section", "anchor"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "bodyAnchor"},
                "section": {"type": "integer", "minimum": 1},
                "anchor": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
            },
        },
    ]
    request_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "HWPX mixed-form request v1",
        "type": "object",
        "required": [
            "schemaVersion",
            "input",
            "output",
            "operations",
            "expectedRevision",
            "idempotencyKey",
            "dryRun",
            "quality",
            "verificationRequirements",
        ],
        "additionalProperties": False,
        "$defs": {
            "cellAnchor": {
                "type": "object",
                "required": ["label"],
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
                    "direction": {"enum": sorted(_DIRECTIONS)},
                },
            }
        },
        "properties": {
            "schemaVersion": {"const": MIXED_FORM_REQUEST_SCHEMA},
            "input": {
                "type": "object",
                "required": ["filename"],
                "additionalProperties": False,
                "properties": {"filename": {"type": "string", "minLength": 1}},
            },
            "output": {
                "type": "object",
                "required": ["filename", "overwrite"],
                "additionalProperties": False,
                "properties": {
                    "filename": {"type": "string", "minLength": 1},
                    "overwrite": {"type": "boolean"},
                },
            },
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_COMMANDS,
                "items": {
                    "type": "object",
                    "required": ["operationId", "locator", "value"],
                    "additionalProperties": False,
                    "properties": {
                        "operationId": {
                            "type": "string",
                            "pattern": COMMAND_ID_PATTERN.pattern,
                        },
                        "locator": {"oneOf": locator_variants},
                        "value": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                    },
                },
            },
            "expectedRevision": {
                "type": ["string", "null"],
                "pattern": REVISION_PATTERN.pattern,
            },
            "idempotencyKey": {"type": ["string", "null"], "minLength": 1, "maxLength": 128},
            "dryRun": {"type": "boolean"},
            "quality": deepcopy(agent_schemas["batch"]["properties"]["quality"]),
            "verificationRequirements": {
                "type": "array",
                "items": {"enum": list(VERIFICATION_REQUIREMENTS)},
                "uniqueItems": True,
            },
        },
    }
    nullable_coordinate = {"type": ["integer", "null"], "minimum": 0}
    embedded_batch_schema = deepcopy(agent_schemas["batch"])
    embedded_batch_schema.pop("$schema", None)
    embedded_batch_schema.pop("title", None)
    compiled_plan_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "HWPX mixed-form compiled plan v1",
        "type": "object",
        "required": sorted(_COMPILED_PLAN_KEYS),
        "additionalProperties": False,
        "properties": {
            "schemaVersion": {"const": MIXED_FORM_COMPILED_PLAN_SCHEMA},
            "inputRevision": {"type": "string", "pattern": REVISION_PATTERN.pattern},
            "requestHash": {"type": "string", "pattern": REVISION_PATTERN.pattern},
            "planHash": {"type": "string", "pattern": REVISION_PATTERN.pattern},
            "resolutions": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_COMMANDS,
                "items": {
                    "type": "object",
                    "required": sorted(_RESOLUTION_KEYS),
                    "additionalProperties": False,
                    "properties": {
                        "operationId": {"type": "string", "pattern": COMMAND_ID_PATTERN.pattern},
                        "locatorKind": {"enum": list(MIXED_FORM_LOCATOR_KINDS)},
                        "path": {"type": "string", "minLength": 1},
                        "nodeKind": {"enum": sorted(_FILLABLE_NODE_KINDS)},
                        "stability": {"enum": list(STABILITY_LEVELS)},
                        "section": {"type": ["integer", "null"], "minimum": 1},
                        "tableIndex": deepcopy(nullable_coordinate),
                        "logicalRow": deepcopy(nullable_coordinate),
                        "logicalColumn": deepcopy(nullable_coordinate),
                        "physicalRow": deepcopy(nullable_coordinate),
                        "physicalColumn": deepcopy(nullable_coordinate),
                    },
                },
            },
            "batch": embedded_batch_schema,
        },
    }
    public_target_variants = [
        deepcopy(locator_variants[0]),
        deepcopy(locator_variants[1]),
        {
            "type": "object",
            "required": ["kind", "sectionPath", "tableAnchor", "cellAnchor"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "labelCell"},
                "sectionPath": {"type": "string", "pattern": r"^/section\[[1-9][0-9]*\]$"},
                "tableAnchor": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_TEXT_CHARS,
                },
                "cellAnchor": {"$ref": "#/$defs/requiredCellAnchor"},
            },
        },
        {
            "type": "object",
            "required": ["kind", "sectionPath", "tableIndex", "cellAnchor"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "labelCell"},
                "sectionPath": {"type": "string", "pattern": r"^/section\[[1-9][0-9]*\]$"},
                "tableIndex": {"type": "integer", "minimum": 0},
                "cellAnchor": {"$ref": "#/$defs/requiredCellAnchor"},
            },
        },
        deepcopy(locator_variants[4]),
        {
            "type": "object",
            "required": ["kind", "sectionPath", "anchor", "expectedCount"],
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "bodyAnchor"},
                "sectionPath": {"type": "string", "pattern": r"^/section\[[1-9][0-9]*\]$"},
                "anchor": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
                "expectedCount": {"const": 1},
            },
        },
    ]
    public_plan_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "HWPX mixed-form plan v1",
        "type": "object",
        "required": [
            "schemaVersion",
            "source",
            "output",
            "expectedRevision",
            "idempotencyKey",
            "dryRun",
            "overwrite",
            "quality",
            "verificationRequirements",
            "operations",
        ],
        "additionalProperties": False,
        "$defs": {
            "requiredCellAnchor": {
                "type": "object",
                "required": ["label", "direction"],
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS},
                    "direction": {"enum": sorted(_DIRECTIONS)},
                },
            }
        },
        "properties": {
            "schemaVersion": {"const": MIXED_FORM_PLAN_SCHEMA},
            "source": {"type": "string", "minLength": 1},
            "output": {"type": "string", "minLength": 1},
            "expectedRevision": {
                "type": ["string", "null"],
                "pattern": REVISION_PATTERN.pattern,
            },
            "idempotencyKey": {
                "type": ["string", "null"],
                "minLength": 1,
                "maxLength": 128,
            },
            "dryRun": {"type": "boolean"},
            "overwrite": {"type": "boolean"},
            "quality": deepcopy(agent_schemas["batch"]["properties"]["quality"]),
            "verificationRequirements": {
                "type": "array",
                "items": {"enum": list(VERIFICATION_REQUIREMENTS)},
                "uniqueItems": True,
            },
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_COMMANDS,
                "items": {
                    "type": "object",
                    "required": ["operationId", "target", "value"],
                    "additionalProperties": False,
                    "properties": {
                        "operationId": {
                            "type": "string",
                            "pattern": COMMAND_ID_PATTERN.pattern,
                        },
                        "target": {"oneOf": public_target_variants},
                        "value": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                    },
                },
            },
        },
    }
    return {
        "plan": deepcopy(public_plan_schema),
        "compiledPlan": deepcopy(compiled_plan_schema),
        "internalRequest": deepcopy(request_schema),
    }


__all__ = [
    "MIXED_FORM_COMPILED_PLAN_SCHEMA",
    "MIXED_FORM_LOCATOR_KINDS",
    "MIXED_FORM_PLAN_SCHEMA",
    "MIXED_FORM_REQUEST_SCHEMA",
    "MixedFormPlan",
    "MixedFormResolution",
    "apply_mixed_form_fill",
    "apply_mixed_form_plan",
    "mixed_form_json_schemas",
    "plan_mixed_form_fill",
    "validate_mixed_form_plan",
    "validate_mixed_form_request",
]
