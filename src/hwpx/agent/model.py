# SPDX-License-Identifier: Apache-2.0
"""Strict v1 contracts for the semantic HWPX agent interface.

This module intentionally defines only public, JSON-serialisable semantics.  It
does not expose lxml elements, package part paths, namespace URIs, XPath, or a
generic attribute mutation escape hatch.  Projection, path evaluation, query,
and mutation execution are implemented in neighbouring modules after these
contracts are frozen.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..mutation_report import (
    ChangedPart,
    MutationReport,
    PreservationCounts,
    PreservationSummary,
    verification_from_open_safety,
    visual_value_from_status,
)

AGENT_NODE_SCHEMA = "hwpx.agent-node/v1"
AGENT_COMMAND_SCHEMA = "hwpx.agent-command/v1"
AGENT_BATCH_SCHEMA = "hwpx.agent-batch/v1"
AGENT_BATCH_RESULT_SCHEMA = "hwpx.agent-batch-result/v1"
AGENT_ERROR_SCHEMA = "hwpx.agent-error/v1"
AGENT_CATALOG_SCHEMA = "hwpx.agent-catalog/v1"

NODE_KINDS = (
    "document",
    "section",
    "paragraph",
    "run",
    "table",
    "row",
    "cell",
    "form-field",
    "picture",
    "memo",
    "footnote",
    "endnote",
    "shape",
    "unsupported",
)
STABILITY_LEVELS = ("native", "derived", "positional")
AGENT_OPERATIONS = ("set", "add", "remove", "move", "copy")

SELECTOR_KINDS = tuple(kind for kind in NODE_KINDS if kind != "unsupported")
SELECTOR_ATTRIBUTES = ("id", "name", "style", "type")
SELECTOR_FEATURES = (
    "kind",
    "exact-attribute",
    "contains",
    "direct-child",
)

MAX_VIEW_DEPTH = 8
MAX_CHILDREN_PER_NODE = 200
MAX_QUERY_RESULTS = 100
MAX_TEXT_CHARS = 4096
MAX_SELECTOR_CHARS = 512
MAX_COMMANDS = 100
MAX_PROPERTIES_PER_COMMAND = 32
MAX_JSON_DEPTH = 8

REVISION_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
COMMAND_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
COMMAND_REF_PATTERN = re.compile(
    r"^\$([A-Za-z][A-Za-z0-9_-]{0,31})\.(path|parentPath)$"
)
CANONICAL_PATH_PATTERN = re.compile(r"^/(?:[^\x00-\x1f]*)$")

ERROR_CODES = (
    "invalid_syntax",
    "unknown_kind",
    "unknown_property",
    "unsupported_operation",
    "not_found",
    "ambiguous_target",
    "stale_revision",
    "volatile_target",
    "incompatible_parent",
    "identity_collision",
    "invariant_violation",
    "unsupported_content",
    "resource_limit",
    "verification_failed",
    "idempotency_conflict",
)
RECOVERABILITY = ("retryable", "needs-review", "terminal")

VERIFICATION_REQUIREMENTS = (
    "package",
    "reopen",
    "openSafety",
    "semanticDiff",
    "bytePreservation",
    "domain",
    "realHancom",
)
QUALITY_MODES = ("transparent", "strict")
QUALITY_KEYS = frozenset(
    {
        "mode",
        "renderCheck",
        "xsdMode",
        "overflowPolicy",
        "layoutLint",
        "preserveUnmodifiedParts",
        "requireReferenceIntegrity",
    }
)
_QUALITY_ENUM_VALUES = {
    "mode": QUALITY_MODES,
    "renderCheck": ("off", "auto", "required"),
    "xsdMode": ("off", "lint"),
    "overflowPolicy": ("fail", "warn", "truncate"),
    "layoutLint": ("off", "warn", "strict"),
}
_QUALITY_BOOLEAN_KEYS = frozenset(
    {"preserveUnmodifiedParts", "requireReferenceIntegrity"}
)

# The v1 public property vocabulary.  P2's command catalog consumes this exact
# manifest.  A property absent here cannot be set through generic commands.
NODE_PROPERTY_CATALOG_V1: dict[str, dict[str, tuple[str, ...]]] = {
    "document": {
        "readable": ("title", "author", "sectionCount", "paragraphCount", "tableCount"),
        "editable": (),
        "operations": ("add",),
    },
    "section": {
        "readable": ("index", "partId", "paragraphCount", "pageWidthMm", "pageHeightMm"),
        "editable": (),
        "operations": ("add",),
    },
    "paragraph": {
        "readable": (
            "text",
            "style",
            "alignment",
            "breakBefore",
            "keepWithNext",
            "lineSpacingPercent",
        ),
        "editable": (
            "text",
            "style",
            "alignment",
            "breakBefore",
            "keepWithNext",
            "lineSpacingPercent",
        ),
        "operations": AGENT_OPERATIONS,
    },
    "run": {
        "readable": ("text", "bold", "italic", "underline", "fontName", "fontSizePt", "color"),
        "editable": ("text", "bold", "italic", "underline", "fontName", "fontSizePt", "color"),
        "operations": ("set", "add", "remove", "copy"),
    },
    "table": {
        "readable": ("rowCount", "columnCount", "caption", "widthMm", "alignment"),
        "editable": ("caption", "alignment"),
        "operations": AGENT_OPERATIONS,
    },
    "row": {
        "readable": ("index", "cellCount", "heightMm"),
        "editable": ("heightMm",),
        "operations": ("set", "add", "remove", "move", "copy"),
    },
    "cell": {
        "readable": (
            "text",
            "row",
            "column",
            "rowSpan",
            "columnSpan",
            "verticalAlignment",
            "backgroundColor",
        ),
        "editable": ("text", "verticalAlignment", "backgroundColor"),
        "operations": ("set",),
    },
    "form-field": {
        "readable": ("name", "value", "fieldType", "readOnly"),
        "editable": ("value", "readOnly"),
        "operations": ("set",),
    },
    "picture": {
        "readable": ("name", "altText", "widthMm", "heightMm", "mediaType"),
        "editable": ("altText",),
        "operations": ("set", "remove", "move", "copy"),
    },
    "memo": {
        "readable": ("text", "author"),
        "editable": ("text",),
        "operations": ("set", "remove", "copy"),
    },
    "footnote": {
        "readable": ("text",),
        "editable": ("text",),
        "operations": ("set", "remove", "copy"),
    },
    "endnote": {
        "readable": ("text",),
        "editable": ("text",),
        "operations": ("set", "remove", "copy"),
    },
    "shape": {
        "readable": ("shapeType", "name", "altText", "xMm", "yMm", "widthMm", "heightMm"),
        "editable": ("altText",),
        "operations": ("set", "remove", "move", "copy"),
    },
    "unsupported": {"readable": ("localName", "reason"), "editable": (), "operations": ()},
}

_RAW_KEYS = frozenset(
    {"xml", "raw", "rawxml", "xpath", "namespace", "namespaceuri", "packagepath", "partpath"}
)


class AgentContractError(ValueError):
    """A stable-code contract validation error."""

    def __init__(self, code: str, message: str, *, target: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown agent error code: {code}")
        super().__init__(message)
        self.code = code
        self.target = target


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentContractError("invalid_syntax", f"{name} must be an object", target=name)
    return value


def _require_exact_keys(
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


def _validate_json_value(value: object, *, name: str, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise AgentContractError("resource_limit", f"{name} exceeds JSON depth limit", target=name)
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_CHARS:
            raise AgentContractError("resource_limit", f"{name} string is too long", target=name)
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            normalized = re.sub(r"[^a-z]", "", key_text.casefold())
            if normalized in _RAW_KEYS:
                raise AgentContractError(
                    "unknown_property",
                    f"{name} contains forbidden raw/package property {key_text!r}",
                    target=f"{name}.{key_text}",
                )
            _validate_json_value(child, name=f"{name}.{key_text}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, name=f"{name}[{index}]", depth=depth + 1)
        return
    raise AgentContractError(
        "invalid_syntax", f"{name} is not JSON-serialisable", target=name
    )


def _validate_path_or_reference(value: object, name: str) -> str:
    text = str(value or "")
    if COMMAND_REF_PATTERN.fullmatch(text):
        return text
    if not CANONICAL_PATH_PATTERN.fullmatch(text):
        raise AgentContractError(
            "invalid_syntax", f"{name} must be an absolute semantic path or command reference", target=name
        )
    if len(text) > MAX_SELECTOR_CHARS * 2:
        raise AgentContractError("resource_limit", f"{name} is too long", target=name)
    return text


def _validate_properties(value: object, name: str) -> dict[str, Any]:
    props = dict(_require_mapping(value, name))
    if not props:
        raise AgentContractError("invalid_syntax", f"{name} cannot be empty", target=name)
    if len(props) > MAX_PROPERTIES_PER_COMMAND:
        raise AgentContractError("resource_limit", f"{name} has too many properties", target=name)
    _validate_json_value(props, name=name)
    return props


def _validate_position(value: object, name: str = "command.position") -> dict[str, Any]:
    position = dict(_require_mapping(value, name))
    mode = str(position.get("mode", ""))
    if mode in {"append", "prepend"}:
        _require_exact_keys(position, required={"mode"}, name=name)
        return {"mode": mode}
    if mode == "index":
        _require_exact_keys(position, required={"mode", "index"}, name=name)
        index = position["index"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise AgentContractError(
                "invalid_syntax", f"{name}.index must be a one-based integer", target=f"{name}.index"
            )
        return {"mode": mode, "index": index}
    if mode in {"before", "after"}:
        _require_exact_keys(position, required={"mode", "path"}, name=name)
        return {"mode": mode, "path": _validate_path_or_reference(position["path"], f"{name}.path")}
    raise AgentContractError(
        "invalid_syntax", f"{name}.mode must be append, prepend, index, before, or after", target=f"{name}.mode"
    )


def _validate_quality(value: object) -> str | dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value not in QUALITY_MODES:
            raise AgentContractError("invalid_syntax", "batch.quality mode is unsupported", target="batch.quality")
        return value
    quality = dict(_require_mapping(value, "batch.quality"))
    extra = set(quality) - QUALITY_KEYS
    if extra:
        raise AgentContractError(
            "unknown_property",
            f"batch.quality contains unknown fields: {sorted(extra)}",
            target="batch.quality",
        )
    for name, choices in _QUALITY_ENUM_VALUES.items():
        if name in quality and quality[name] not in choices:
            raise AgentContractError(
                "invalid_syntax",
                f"batch.quality.{name} is unsupported",
                target=f"batch.quality.{name}",
            )
    for name in _QUALITY_BOOLEAN_KEYS:
        if name in quality and not isinstance(quality[name], bool):
            raise AgentContractError(
                "invalid_syntax",
                f"batch.quality.{name} must be boolean",
                target=f"batch.quality.{name}",
            )
    _validate_json_value(quality, name="batch.quality")
    return quality


@dataclass(frozen=True, slots=True)
class AgentNode:
    """A bounded semantic node resolved against one document revision."""

    kind: str
    path: str
    stable_id: str | None
    stability: str
    summary: Mapping[str, Any]
    child_count: int
    children: tuple["AgentNode", ...] = ()
    unsupported_child_count: int = 0
    truncated_child_count: int = 0
    readable_properties: tuple[str, ...] = ()
    editable_properties: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    revision: str = ""

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise AgentContractError("unknown_kind", f"unknown node kind: {self.kind}", target="node.kind")
        if not CANONICAL_PATH_PATTERN.fullmatch(self.path):
            raise AgentContractError(
                "invalid_syntax", "node.path must be an absolute canonical path", target="node.path"
            )
        if self.stability not in STABILITY_LEVELS:
            raise AgentContractError("invalid_syntax", "unknown node stability", target="node.stability")
        if self.stability == "positional" and self.stable_id is not None:
            raise AgentContractError(
                "invariant_violation", "positional nodes cannot claim stableId", target="node.stableId"
            )
        if self.stability != "positional" and not self.stable_id:
            raise AgentContractError(
                "invariant_violation", "native/derived nodes require stableId", target="node.stableId"
            )
        if self.stable_id is not None and (not self.stable_id or len(self.stable_id) > 256):
            raise AgentContractError("resource_limit", "node.stableId is invalid", target="node.stableId")
        for name, value in (
            ("childCount", self.child_count),
            ("unsupportedChildCount", self.unsupported_child_count),
            ("truncatedChildCount", self.truncated_child_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError("invalid_syntax", f"node.{name} must be non-negative", target=f"node.{name}")
        if len(self.children) > MAX_CHILDREN_PER_NODE:
            raise AgentContractError("resource_limit", "node children exceed limit", target="node.children")
        if (
            len(self.children)
            + self.unsupported_child_count
            + self.truncated_child_count
            != self.child_count
        ):
            raise AgentContractError(
                "invariant_violation", "node child coverage must equal childCount", target="node.children"
            )
        if not REVISION_PATTERN.fullmatch(self.revision):
            raise AgentContractError("invalid_syntax", "node.revision must be sha256", target="node.revision")
        _validate_json_value(self.summary, name="node.summary")
        catalog = NODE_PROPERTY_CATALOG_V1[self.kind]
        if tuple(self.readable_properties) != tuple(catalog["readable"]):
            raise AgentContractError(
                "invariant_violation", "node readable properties do not match v1 catalog", target="node.readableProperties"
            )
        if tuple(self.editable_properties) != tuple(catalog["editable"]):
            raise AgentContractError(
                "invariant_violation", "node editable properties do not match v1 catalog", target="node.editableProperties"
            )
        if tuple(self.operations) != tuple(catalog["operations"]):
            raise AgentContractError(
                "invariant_violation", "node operations do not match v1 catalog", target="node.operations"
            )

    @property
    def volatile_path(self) -> bool:
        return self.stability == "positional"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": AGENT_NODE_SCHEMA,
            "kind": self.kind,
            "path": self.path,
            "stableId": self.stable_id,
            "stability": self.stability,
            "volatilePath": self.volatile_path,
            "summary": dict(self.summary),
            "childCount": self.child_count,
            "children": [child.to_dict() for child in self.children],
            "coverage": {
                "supportedChildren": len(self.children),
                "unsupportedChildren": self.unsupported_child_count,
                "truncatedChildren": self.truncated_child_count,
            },
            "readableProperties": list(self.readable_properties),
            "editableProperties": list(self.editable_properties),
            "operations": list(self.operations),
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class AgentError:
    code: str
    message: str
    target: str | None = None
    recoverability: str = "terminal"
    suggestion: str | None = None
    valid_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(f"unknown agent error code: {self.code}")
        if self.recoverability not in RECOVERABILITY:
            raise ValueError(f"unknown recoverability: {self.recoverability}")
        if not self.message or len(self.message) > MAX_TEXT_CHARS:
            raise ValueError("agent error message is empty or too long")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": AGENT_ERROR_SCHEMA,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "recoverability": self.recoverability,
            "suggestion": self.suggestion,
            "validValues": list(self.valid_values),
        }


def validate_agent_command(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one strict op-specific command union."""

    raw = dict(_require_mapping(value, "command"))
    command_id = str(raw.get("commandId", ""))
    if not COMMAND_ID_PATTERN.fullmatch(command_id):
        raise AgentContractError("invalid_syntax", "commandId is invalid", target="command.commandId")
    op = str(raw.get("op", ""))
    if op not in AGENT_OPERATIONS:
        raise AgentContractError("unsupported_operation", f"unsupported command op: {op}", target="command.op")

    normalized: dict[str, Any] = {
        "schemaVersion": AGENT_COMMAND_SCHEMA,
        "commandId": command_id,
        "op": op,
    }
    if op == "set":
        _require_exact_keys(raw, required={"commandId", "op", "path", "properties"}, name="command")
        normalized["path"] = _validate_path_or_reference(raw["path"], "command.path")
        normalized["properties"] = _validate_properties(raw["properties"], "command.properties")
    elif op == "add":
        _require_exact_keys(
            raw,
            required={"commandId", "op", "parent", "kind", "properties"},
            optional={"position"},
            name="command",
        )
        kind = str(raw["kind"])
        if kind not in NODE_KINDS or kind in {"document", "unsupported"}:
            raise AgentContractError("unknown_kind", f"cannot add node kind: {kind}", target="command.kind")
        normalized["parent"] = _validate_path_or_reference(raw["parent"], "command.parent")
        normalized["kind"] = kind
        normalized["properties"] = _validate_properties(raw["properties"], "command.properties")
        normalized["position"] = _validate_position(raw.get("position", {"mode": "append"}))
    elif op == "remove":
        _require_exact_keys(raw, required={"commandId", "op", "path"}, name="command")
        normalized["path"] = _validate_path_or_reference(raw["path"], "command.path")
    else:
        _require_exact_keys(
            raw,
            required={"commandId", "op", "path", "parent"},
            optional={"position"},
            name="command",
        )
        normalized["path"] = _validate_path_or_reference(raw["path"], "command.path")
        normalized["parent"] = _validate_path_or_reference(raw["parent"], "command.parent")
        normalized["position"] = _validate_position(raw.get("position", {"mode": "append"}))
    return normalized


def validate_agent_batch(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete atomic batch envelope without touching a document."""

    raw = dict(_require_mapping(value, "batch"))
    required = {
        "schemaVersion",
        "input",
        "output",
        "commands",
        "expectedRevision",
        "idempotencyKey",
        "dryRun",
        "quality",
        "verificationRequirements",
    }
    _require_exact_keys(raw, required=required, name="batch")
    if raw["schemaVersion"] != AGENT_BATCH_SCHEMA:
        raise AgentContractError("invalid_syntax", "unsupported batch schemaVersion", target="batch.schemaVersion")

    input_ref = dict(_require_mapping(raw["input"], "batch.input"))
    _require_exact_keys(input_ref, required={"filename"}, name="batch.input")
    if not str(input_ref["filename"]).strip():
        raise AgentContractError("invalid_syntax", "batch.input.filename is required", target="batch.input.filename")

    output_ref = dict(_require_mapping(raw["output"], "batch.output"))
    _require_exact_keys(output_ref, required={"filename", "overwrite"}, name="batch.output")
    if not str(output_ref["filename"]).strip() or not isinstance(output_ref["overwrite"], bool):
        raise AgentContractError("invalid_syntax", "batch.output is invalid", target="batch.output")

    commands_value = raw["commands"]
    if isinstance(commands_value, (str, bytes)) or not isinstance(commands_value, Sequence):
        raise AgentContractError("invalid_syntax", "batch.commands must be an array", target="batch.commands")
    if not commands_value or len(commands_value) > MAX_COMMANDS:
        raise AgentContractError("resource_limit", "batch.commands count is out of bounds", target="batch.commands")
    commands = [validate_agent_command(_require_mapping(item, "command")) for item in commands_value]
    command_ids = [command["commandId"] for command in commands]
    if len(command_ids) != len(set(command_ids)):
        raise AgentContractError("invariant_violation", "batch commandId values must be unique", target="batch.commands")
    for index, command in enumerate(commands):
        for key in ("path", "parent"):
            target = command.get(key)
            match = COMMAND_REF_PATTERN.fullmatch(str(target or ""))
            if not match:
                continue
            referenced = match.group(1)
            if referenced not in command_ids[:index]:
                raise AgentContractError(
                    "invalid_syntax",
                    f"command reference {referenced!r} must name an earlier command",
                    target=f"batch.commands[{index}].{key}",
                )

    expected_revision = raw["expectedRevision"]
    if expected_revision is not None and not REVISION_PATTERN.fullmatch(str(expected_revision)):
        raise AgentContractError("invalid_syntax", "expectedRevision must be sha256 or null", target="batch.expectedRevision")
    idempotency_key = raw["idempotencyKey"]
    if idempotency_key is not None and not (1 <= len(str(idempotency_key)) <= 128):
        raise AgentContractError("resource_limit", "idempotencyKey length is invalid", target="batch.idempotencyKey")
    if not isinstance(raw["dryRun"], bool):
        raise AgentContractError("invalid_syntax", "dryRun must be boolean", target="batch.dryRun")

    requirements = raw["verificationRequirements"]
    if isinstance(requirements, (str, bytes)) or not isinstance(requirements, Sequence):
        raise AgentContractError(
            "invalid_syntax", "verificationRequirements must be an array", target="batch.verificationRequirements"
        )
    unknown_requirements = sorted(set(requirements) - set(VERIFICATION_REQUIREMENTS))
    if unknown_requirements:
        raise AgentContractError(
            "invalid_syntax",
            f"unknown verification requirements: {unknown_requirements}",
            target="batch.verificationRequirements",
        )

    return {
        "schemaVersion": AGENT_BATCH_SCHEMA,
        "input": {"filename": str(input_ref["filename"])},
        "output": {"filename": str(output_ref["filename"]), "overwrite": output_ref["overwrite"]},
        "commands": commands,
        "expectedRevision": None if expected_revision is None else str(expected_revision),
        "idempotencyKey": None if idempotency_key is None else str(idempotency_key),
        "dryRun": raw["dryRun"],
        "quality": _validate_quality(raw["quality"]),
        "verificationRequirements": list(dict.fromkeys(str(item) for item in requirements)),
    }


@dataclass(frozen=True, slots=True)
class AgentBatchResult:
    ok: bool
    rolled_back: bool
    dry_run: bool
    input_revision: str
    document_revision: str
    output_filename: str
    command_results: tuple[Mapping[str, Any], ...] = ()
    semantic_diff: Mapping[str, Any] = field(default_factory=dict)
    verification_report: Mapping[str, Any] = field(default_factory=dict)
    error: AgentError | None = None

    def __post_init__(self) -> None:
        for name, revision in (
            ("inputRevision", self.input_revision),
            ("documentRevision", self.document_revision),
        ):
            if not REVISION_PATTERN.fullmatch(revision):
                raise ValueError(f"{name} must be sha256")
        if self.ok and self.rolled_back:
            raise ValueError("successful batch cannot be rolled back")
        if not self.ok and self.error is None:
            raise ValueError("failed batch requires a structured error")
        if len(self.command_results) > MAX_COMMANDS:
            raise ValueError("too many command results")
        _validate_json_value(self.command_results, name="result.commandResults")
        _validate_json_value(self.semantic_diff, name="result.semanticDiff")
        _validate_json_value(self.verification_report, name="result.verificationReport")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": AGENT_BATCH_RESULT_SCHEMA,
            "ok": self.ok,
            "rolledBack": self.rolled_back,
            "dryRun": self.dry_run,
            "inputRevision": self.input_revision,
            "documentRevision": self.document_revision,
            "output": {"filename": self.output_filename},
            "commandResults": [dict(item) for item in self.command_results],
            "semanticDiff": dict(self.semantic_diff),
            "verificationReport": dict(self.verification_report),
            "error": None if self.error is None else self.error.to_dict(),
        }

    def as_mutation_report(self) -> MutationReport:
        """Project this transaction result onto ``hwpx.mutation-report/v1`` (specs/032
        §3). Additive — the fields above are untouched.

        The agent write is a family-A rebuild (``document.to_bytes()``), so
        ``actualMode`` is ``"rebuild"`` and changed parts carry no ranges (a rebuilt
        part is re-serialized whole). Preservation and verification are read from the
        already-measured ``verification_report`` (``bytePreservation`` = the shared
        ``_member_diff``, ``openSafety``, ``realHancom``); layers that report never
        measured — local ZIP records, an absent oracle — stay zero-verified /
        ``not_performed`` rather than being promoted to a pass.
        """

        report = self.verification_report
        byte = report.get("bytePreservation") or {}
        changed_names = [
            *byte.get("changedMembers", ()),
            *byte.get("addedMembers", ()),
            *byte.get("removedMembers", ()),
        ]
        changed_parts = tuple(
            ChangedPart(path=str(name), reason="dirty-part", ranges=None)
            for name in changed_names
        )
        unchanged = byte.get("unchangedMemberCount")
        preservation = PreservationSummary(
            untouched_part_payloads=PreservationCounts(
                verified=unchanged if isinstance(unchanged, int) else 0, changed=0
            ),
            untouched_local_zip_records=PreservationCounts(verified=0, changed=0),
            whole_package_identical=bool(byte) and not changed_names,
        )
        real_hancom = report.get("realHancom") or {}
        verification = verification_from_open_safety(
            report.get("openSafety"),
            visual=visual_value_from_status(real_hancom.get("status")),
        )
        return MutationReport(
            requested_mode="rebuild",
            actual_mode="rebuild",
            fallback_used=False,
            changed_parts=changed_parts,
            preservation=preservation,
            verification=verification,
            path=self.output_filename,
        )


def agent_contract_manifest() -> dict[str, Any]:
    """Return the deterministic, inspectable v1 contract manifest."""

    return {
        "schemaVersion": AGENT_CATALOG_SCHEMA,
        "schemas": {
            "node": AGENT_NODE_SCHEMA,
            "command": AGENT_COMMAND_SCHEMA,
            "batch": AGENT_BATCH_SCHEMA,
            "batchResult": AGENT_BATCH_RESULT_SCHEMA,
            "error": AGENT_ERROR_SCHEMA,
        },
        "limits": {
            "maxViewDepth": MAX_VIEW_DEPTH,
            "maxChildrenPerNode": MAX_CHILDREN_PER_NODE,
            "maxQueryResults": MAX_QUERY_RESULTS,
            "maxTextChars": MAX_TEXT_CHARS,
            "maxSelectorChars": MAX_SELECTOR_CHARS,
            "maxCommands": MAX_COMMANDS,
            "maxPropertiesPerCommand": MAX_PROPERTIES_PER_COMMAND,
        },
        "path": {
            "root": "/",
            "externalIndexBase": 1,
            "stabilityLevels": list(STABILITY_LEVELS),
            "commandReference": "$<commandId>.path",
        },
        "selector": {
            "features": list(SELECTOR_FEATURES),
            "kinds": list(SELECTOR_KINDS),
            "attributes": list(SELECTOR_ATTRIBUTES),
            "resultOrder": "document",
            "xpath": False,
            "regex": False,
            "rawXml": False,
        },
        "operations": list(AGENT_OPERATIONS),
        "nodeKinds": {
            kind: {
                "readableProperties": list(NODE_PROPERTY_CATALOG_V1[kind]["readable"]),
                "editableProperties": list(NODE_PROPERTY_CATALOG_V1[kind]["editable"]),
                "operations": list(NODE_PROPERTY_CATALOG_V1[kind]["operations"]),
            }
            for kind in NODE_KINDS
        },
        "verificationRequirements": list(VERIFICATION_REQUIREMENTS),
        "qualityModes": list(QUALITY_MODES),
        "errorCodes": list(ERROR_CODES),
        "recoverability": list(RECOVERABILITY),
    }


__all__ = [
    "AGENT_BATCH_RESULT_SCHEMA",
    "AGENT_BATCH_SCHEMA",
    "AGENT_CATALOG_SCHEMA",
    "AGENT_COMMAND_SCHEMA",
    "AGENT_ERROR_SCHEMA",
    "AGENT_NODE_SCHEMA",
    "AGENT_OPERATIONS",
    "AgentBatchResult",
    "AgentContractError",
    "AgentError",
    "AgentNode",
    "ERROR_CODES",
    "MAX_CHILDREN_PER_NODE",
    "MAX_COMMANDS",
    "MAX_PROPERTIES_PER_COMMAND",
    "MAX_QUERY_RESULTS",
    "MAX_SELECTOR_CHARS",
    "MAX_TEXT_CHARS",
    "MAX_VIEW_DEPTH",
    "NODE_KINDS",
    "NODE_PROPERTY_CATALOG_V1",
    "SELECTOR_ATTRIBUTES",
    "SELECTOR_FEATURES",
    "STABILITY_LEVELS",
    "VERIFICATION_REQUIREMENTS",
    "agent_contract_manifest",
    "validate_agent_batch",
    "validate_agent_command",
]
