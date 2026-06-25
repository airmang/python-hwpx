# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from typing import Any

from hwpx.quality import VisualCompleteReport
from hwpx.tools.id_integrity import IdIntegrityReport, check_id_integrity
from hwpx.tools.idempotence import IdempotenceReport
from hwpx.tools.package_validator import EditorOpenSafetyReport, PackageValidationReport
from hwpx.tools.validator import ValidationReport


# Explicit scope of what the builder's automated gates prove vs. don't, so a
# green ``hard_gates`` is never mistaken for full Hancom/visual fidelity. The
# gates answer "will Hancom likely open this", NOT "did every authored element
# round-trip". Surfaced in every report's ``to_dict()``.
FIDELITY_CONTRACT: dict[str, list[str]] = {
    "proves": [
        "package opens as a valid HWPX (mimetype/OPC structure, required entries)",
        "no dangling id references or orphan BinData (id_integrity)",
        "no known editor-open breakage patterns (editor_open_safety)",
        "re-saving reproduces identical part contents (idempotent serialization)",
        "the document reopens with our reader (reopen)",
    ],
    "does_not_prove": [
        "visual layout fidelity in Hancom (line/page breaks, overlap) — needs the "
        "visual oracle / ComputerUse",
        "every authored element round-tripped byte-for-byte: merges, shapes, BinData "
        "bytes, and equation script are not value-diffed",
        "macOS Hancom acceptance for untested element combinations",
    ],
}


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
    # The uniform Phase-B report from the SavePipeline the builder save funnelled
    # through (plan §2 Phase B). Additive: ``None`` only if a caller builds a
    # report by hand without going through ``Document.save_to_path``.
    visual_complete: VisualCompleteReport | None = None

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
            "fidelity_contract": {
                "proves": list(FIDELITY_CONTRACT["proves"]),
                "does_not_prove": list(FIDELITY_CONTRACT["does_not_prove"]),
            },
            "visual_review_required": self.visual_review_required,
            "feature_flags": dict(self.feature_flags),
            "visual_complete": (
                None if self.visual_complete is None else self.visual_complete.to_dict()
            ),
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
                    "orphan_bin_data": [
                        {
                            "item_id": item.item_id,
                            "path": item.path,
                            "aliases": list(item.aliases),
                            "sources": list(item.sources),
                            "severity": item.severity,
                        }
                        for item in self.id_integrity.orphan_bin_data
                    ],
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


@dataclass(frozen=True)
class BuilderVerifyReport:
    """Compact, no-disk pre-write verification signal from ``Document.verify()``.

    Lowers the built document to bytes in memory and runs the same hard gates as
    a real save plus a two-round idempotence check — without writing a file — so
    a caller (agent, fuzz loop) can branch on ``ok`` before committing a path.
    See :data:`FIDELITY_CONTRACT` for what these gates prove vs. don't.
    """

    ok: bool
    reopen_ok: bool
    package_ok: bool
    document_ok: bool
    editor_open_safety_ok: bool
    id_integrity_ok: bool
    idempotent: bool
    section_count: int = 0
    paragraph_count: int = 0
    byte_length: int = 0
    reopen_error: str | None = None
    serialize_error: str | None = None
    idempotence: IdempotenceReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reopen_ok": self.reopen_ok,
            "package_ok": self.package_ok,
            "document_ok": self.document_ok,
            "editor_open_safety_ok": self.editor_open_safety_ok,
            "id_integrity_ok": self.id_integrity_ok,
            "idempotent": self.idempotent,
            "section_count": self.section_count,
            "paragraph_count": self.paragraph_count,
            "byte_length": self.byte_length,
            "reopen_error": self.reopen_error,
            "serialize_error": self.serialize_error,
            "idempotence": (
                None if self.idempotence is None else self.idempotence.to_dict()
            ),
            "fidelity_contract": {
                "proves": list(FIDELITY_CONTRACT["proves"]),
                "does_not_prove": list(FIDELITY_CONTRACT["does_not_prove"]),
            },
        }
