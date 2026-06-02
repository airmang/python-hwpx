# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Any

from hwpx.tools.package_validator import PackageValidationReport
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "metadata": dict(self.metadata or {}),
            "validate_package": {
                "ok": self.validate_package.ok,
                "issues": [str(issue) for issue in self.validate_package.issues],
            },
            "validate_document": {
                "ok": self.validate_document.ok,
                "issues": [str(issue) for issue in self.validate_document.issues],
            },
            "reopened": {
                "ok": self.reopened.ok,
                "error": self.reopened.error,
            },
        }
