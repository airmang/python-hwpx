# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from typing import Any

from hwpx.tools.id_integrity import IdIntegrityReport, check_id_integrity
from hwpx.tools.package_validator import EditorOpenSafetyReport, PackageValidationReport
from hwpx.tools.validator import ValidationReport


@dataclass(frozen=True)
class ReopenReport:
    """Result of reopening a generated document."""

    ok: bool
    error: str | None = None
    document: Any | None = None


@dataclass(frozen=True)
class BuilderSaveReport:
    """Validation and reopen report returned by builder saves."""

    path: str | PathLike[str]
    validate_package: PackageValidationReport
    validate_document: ValidationReport
    reopened: ReopenReport
    metadata: dict[str, str] | None = None
    hard_gates: dict[str, str] = field(default_factory=dict)
    visual_review_required: bool = False
    feature_flags: dict[str, bool] = field(default_factory=dict)
    id_integrity: IdIntegrityReport | None = None
    editor_open_safety: EditorOpenSafetyReport | None = None

    def __post_init__(self) -> None:
        hard_gates = dict(self.hard_gates)
        if hard_gates.get("id_integrity") in {None, "unavailable"}:
            id_integrity = None
            if self.reopened.ok and self.reopened.document is not None:
                id_integrity = check_id_integrity(self.reopened.document)
                hard_gates["id_integrity"] = "pass" if id_integrity.ok else "fail"
            else:
                hard_gates["id_integrity"] = "fail"
            object.__setattr__(self, "hard_gates", hard_gates)
            object.__setattr__(self, "id_integrity", id_integrity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "metadata": dict(self.metadata or {}),
            "hard_gates": dict(self.hard_gates),
            "visual_review_required": self.visual_review_required,
            "feature_flags": dict(self.feature_flags),
            "editor_open_safety": (
                None
                if self.editor_open_safety is None
                else self.editor_open_safety.to_dict()
            ),
            "validate_package": {
                "ok": self.validate_package.ok,
                "checked_parts": list(self.validate_package.checked_parts),
                "errors": [str(issue) for issue in self.validate_package.errors],
                "warnings": [str(issue) for issue in self.validate_package.warnings],
                "issues": [str(issue) for issue in self.validate_package.issues],
            },
            "validate_document": {
                "ok": self.validate_document.ok,
                "validated_parts": list(self.validate_document.validated_parts),
                "errors": [str(issue) for issue in self.validate_document.errors],
                "warnings": [str(issue) for issue in self.validate_document.warnings],
                "issues": [str(issue) for issue in self.validate_document.issues],
            },
            "reopened": {
                "ok": self.reopened.ok,
                "error": self.reopened.error,
            },
            "id_integrity": (
                None
                if self.id_integrity is None
                else {
                    "ok": self.id_integrity.ok,
                    "dangling": [str(item) for item in self.id_integrity.dangling],
                    "ignored": [
                        {
                            "part": item.part,
                            "element": item.element,
                            "attr": item.attr,
                            "value": item.value,
                            "reason": item.reason,
                        }
                        for item in self.id_integrity.ignored
                    ],
                }
            ),
        }
