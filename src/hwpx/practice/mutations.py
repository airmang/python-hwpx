"""Controlled synthetic mutations and exact reverse operations."""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .dossier import validate_synthetic_dossier
from .registry import assert_redacted_payload
from .scenario import TASK_KINDS

CONTROLLED_MUTATION_SCHEMA = "hwpx.controlled-mutation/v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def mutation_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("mutationId", None)
    return hashlib.sha256(_canonical(payload)).hexdigest()


def controlled_mutation(
    task_kind: str,
    dossier: Mapping[str, Any],
    *,
    seed: str,
    index: int,
) -> dict[str, Any]:
    """Create a task-specific mutation using synthetic values only."""
    if task_kind not in TASK_KINDS or not seed or index < 0:
        raise ValueError("unsupported controlled mutation request")
    synthetic = validate_synthetic_dossier(dossier)
    fields = synthetic["fields"]
    token = hashlib.sha256(f"{seed}\n{task_kind}\n{index}".encode()).hexdigest()[:12].upper()
    variants: dict[str, dict[str, Any]] = {
        "reverse_restore": {
            "operation": "append_paragraph_then_remove",
            "target": {"kind": "document_end"},
            "before": {"markerPresent": False},
            "after": {"markerText": f"합성-통제결함-{token}"},
            "reversible": True,
        },
        "constrained_edit": {
            "operation": "append_paragraph",
            "target": {"kind": "document_end"},
            "before": {"markerPresent": False},
            "after": {"markerText": fields["목적"]},
            "reversible": True,
        },
        "known_template_fill": {
            "operation": "fill_known_fields",
            "target": {"kind": "declared_field_map"},
            "before": {"fields": {}},
            "after": {"fields": {key: fields[key] for key in ("담당자", "일자", "문서번호")}},
            "reversible": True,
        },
        "unknown_form_fill": {
            "operation": "map_and_fill_unknown_form",
            "target": {"kind": "recon_confidence_gate", "minimumConfidence": 0.85},
            "before": {"fields": {}},
            "after": {"fields": {key: fields[key] for key in ("기관", "담당자", "목적")}},
            "reversible": True,
        },
        "structural_edit": {
            "operation": "append_table_row",
            "target": {"kind": "first_eligible_table"},
            "before": {"rowPresent": False},
            "after": {"row": [fields["대상"], fields["목적"], fields["금액"]]},
            "reversible": True,
        },
        "typed_authoring": {
            "operation": "author_from_style_profile",
            "target": {"kind": "new_document"},
            "before": {},
            "after": {"brief": {key: fields[key] for key in ("기관", "일자", "목적")}},
            "reversible": False,
        },
        "must_abstain": {
            "operation": "no_mutation",
            "target": {"kind": "unsafe_or_ambiguous_request"},
            "before": {},
            "after": {},
            "reversible": True,
        },
    }
    mutation: dict[str, Any] = {
        "schema": CONTROLLED_MUTATION_SCHEMA,
        "taskKind": task_kind,
        "synthetic": True,
        **variants[task_kind],
    }
    mutation["mutationId"] = f"MUT-{mutation_sha256(mutation)[:20].upper()}"
    return validate_controlled_mutation(mutation)


def validate_controlled_mutation(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    assert_redacted_payload(raw)
    if raw.get("schema") != CONTROLLED_MUTATION_SCHEMA or raw.get("synthetic") is not True:
        raise ValueError("unsupported or non-synthetic controlled mutation")
    if raw.get("taskKind") not in TASK_KINDS:
        raise ValueError("controlled mutation taskKind is invalid")
    if not raw.get("operation") or not isinstance(raw.get("target"), Mapping):
        raise ValueError("controlled mutation operation and target are required")
    if not isinstance(raw.get("before"), Mapping) or not isinstance(raw.get("after"), Mapping):
        raise ValueError("controlled mutation before/after values are required")
    if not isinstance(raw.get("reversible"), bool):
        raise ValueError("controlled mutation reversible flag is required")
    expected = f"MUT-{mutation_sha256(raw)[:20].upper()}"
    if raw.get("mutationId") != expected:
        raise ValueError("controlled mutation ID mismatch")
    return raw


def apply_mutation(model: Mapping[str, Any], mutation: Mapping[str, Any]) -> dict[str, Any]:
    """Apply a mutation to a small synthetic document model for property tests."""
    result = copy.deepcopy(dict(model))
    raw = validate_controlled_mutation(mutation)
    operation = raw["operation"]
    if operation in {"append_paragraph_then_remove", "append_paragraph"}:
        result.setdefault("paragraphs", []).append(raw["after"]["markerText"])
    elif operation in {"fill_known_fields", "map_and_fill_unknown_form"}:
        result.setdefault("fields", {}).update(raw["after"]["fields"])
    elif operation == "append_table_row":
        result.setdefault("rows", []).append(list(raw["after"]["row"]))
    elif operation == "author_from_style_profile":
        result["authored"] = copy.deepcopy(raw["after"]["brief"])
    return result


def reverse_mutation(model: Mapping[str, Any], mutation: Mapping[str, Any]) -> dict[str, Any]:
    """Reverse an allow-listed reversible mutation exactly or fail closed."""
    result = copy.deepcopy(dict(model))
    raw = validate_controlled_mutation(mutation)
    if raw["reversible"] is not True:
        raise ValueError("controlled mutation is not reversible")
    operation = raw["operation"]
    if operation in {"append_paragraph_then_remove", "append_paragraph"}:
        marker = raw["after"]["markerText"]
        if not result.get("paragraphs") or result["paragraphs"][-1] != marker:
            raise ValueError("controlled paragraph mutation cannot be reversed exactly")
        result["paragraphs"].pop()
    elif operation in {"fill_known_fields", "map_and_fill_unknown_form"}:
        for key in raw["after"]["fields"]:
            result.setdefault("fields", {}).pop(key, None)
    elif operation == "append_table_row":
        row = raw["after"]["row"]
        if not result.get("rows") or result["rows"][-1] != row:
            raise ValueError("controlled row mutation cannot be reversed exactly")
        result["rows"].pop()
    return result


__all__ = [
    "CONTROLLED_MUTATION_SCHEMA",
    "apply_mutation",
    "controlled_mutation",
    "mutation_sha256",
    "reverse_mutation",
    "validate_controlled_mutation",
]
