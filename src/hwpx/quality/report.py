# SPDX-License-Identifier: Apache-2.0
"""Composite quality report for the single :class:`~hwpx.quality.SavePipeline`.

``VisualCompleteReport`` is the one shape every write path returns (implementation
plan §2 Phase B / Appendix A). It bundles the per-stage sub-reports and a single
``ok`` verdict so callers never have to re-assemble the picture from scattered
validators.

The assurance tier is **never blurred** (plan §0.0): ``visual_complete`` may be
``True`` only when the Hancom render actually ran (``render_checked is True``).
Off-oracle the top achievable result is a labelled *structural* pass —
``visual_complete is False`` with ``visual_complete_status == "unverified"`` — not
a silent visual pass. ``visual_complete_status`` is the explicit tri-state:

* ``"verified"`` — render ran, no visual defect → ``visual_complete is True``.
* ``"failed"``   — render ran, a defect was found → ``visual_complete is False``.
* ``"unverified"`` — render did not run (no oracle / not requested / deps absent)
  → ``visual_complete is False``, but **not** a defect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from hwpx.visual.report import VisualReport

# Structured, retry-able error codes (plan Appendix A). Carried as plain strings
# on :class:`QualityError` so the report stays JSON-serialisable.
VISUAL_COMPLETE_FAILED = "VISUAL_COMPLETE_FAILED"
STALE_LINESEG_DETECTED = "STALE_LINESEG_DETECTED"
LAYOUT_MUTATION_WITHOUT_LEDGER = "LAYOUT_MUTATION_WITHOUT_LEDGER"
FIELD_OVERFLOW = "FIELD_OVERFLOW"
REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
OPEN_SAFETY_FAILED = "OPEN_SAFETY_FAILED"
REFERENCE_INTEGRITY_FAILED = "REFERENCE_INTEGRITY_FAILED"
CAPABILITY_SKEW = "CAPABILITY_SKEW"
RENDER_ORACLE_UNAVAILABLE = "RENDER_ORACLE_UNAVAILABLE"
PROFILE_REQUIRED = "PROFILE_REQUIRED"
STYLE_COVERAGE_TOO_LOW = "STYLE_COVERAGE_TOO_LOW"

ERROR_CODES = frozenset(
    {
        VISUAL_COMPLETE_FAILED,
        STALE_LINESEG_DETECTED,
        LAYOUT_MUTATION_WITHOUT_LEDGER,
        FIELD_OVERFLOW,
        REQUIRED_FIELD_MISSING,
        OPEN_SAFETY_FAILED,
        REFERENCE_INTEGRITY_FAILED,
        CAPABILITY_SKEW,
        RENDER_ORACLE_UNAVAILABLE,
        PROFILE_REQUIRED,
        STYLE_COVERAGE_TOO_LOW,
    }
)

VisualCompleteStatus = Literal["verified", "unverified", "failed"]


@dataclass
class QualityError:
    """A structured, retry-able failure (plan Appendix A error codes)."""

    code: str
    message: str
    suggested_retry: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "suggestedRetry": self.suggested_retry,
        }


@dataclass
class OpenSafetyReport:
    """Editor-open safety verdict (whether Hancom/an editor opens it cleanly)."""

    ok: bool
    summary: str = ""
    detail: dict[str, Any] | None = None

    @classmethod
    def passed(cls, summary: str = "open-safety not evaluated") -> "OpenSafetyReport":
        return cls(ok=True, summary=summary)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "summary": self.summary, "detail": self.detail}


@dataclass
class SemanticReport:
    """Content/assertion verdict (the right text ended up in the right place)."""

    ok: bool = True
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> "SemanticReport":
        return cls(ok=True)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FormReport:
    """Form fill / fit verdict (FormFit lands in Phase C; passthrough here)."""

    ok: bool = True
    fields: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> "FormReport":
        return cls(ok=True)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayoutReport:
    """Renderer-less layout lint verdict (LayoutLint lands in Phase D)."""

    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> "LayoutReport":
        return cls(ok=True)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AestheticReport:
    """New-doc aesthetic verdict (profiled aesthetics land in Phase E)."""

    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> "AestheticReport":
        return cls(ok=True)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualCompleteReport:
    """The single shape every SavePipeline write returns (plan Appendix A)."""

    ok: bool
    output_path: str | None
    visual_complete: bool
    open_safety: OpenSafetyReport
    semantic: SemanticReport
    form: FormReport
    layout: LayoutReport
    visual: VisualReport
    aesthetic: AestheticReport
    warnings: list[str] = field(default_factory=list)
    errors: list[QualityError] = field(default_factory=list)
    # Phase-B additions (beyond the condensed Appendix-A list) that keep the
    # assurance tier explicit and the report self-describing.
    visual_complete_status: VisualCompleteStatus = "unverified"
    render_checked: bool = False
    debug_path: str | None = None
    policy: dict[str, Any] | None = None

    @property
    def error_codes(self) -> list[str]:
        return [error.code for error in self.errors]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "outputPath": self.output_path,
            "visualComplete": self.visual_complete,
            "visualCompleteStatus": self.visual_complete_status,
            "renderChecked": self.render_checked,
            "openSafety": self.open_safety.to_dict(),
            "semantic": self.semantic.to_dict(),
            "form": self.form.to_dict(),
            "layout": self.layout.to_dict(),
            "visual": self.visual.to_dict(),
            "aesthetic": self.aesthetic.to_dict(),
            "warnings": list(self.warnings),
            "errors": [error.to_dict() for error in self.errors],
            "debugPath": self.debug_path,
            "policy": self.policy,
        }


__all__ = [
    "VisualCompleteReport",
    "VisualCompleteStatus",
    "QualityError",
    "OpenSafetyReport",
    "SemanticReport",
    "FormReport",
    "LayoutReport",
    "AestheticReport",
    "ERROR_CODES",
    "VISUAL_COMPLETE_FAILED",
    "STALE_LINESEG_DETECTED",
    "LAYOUT_MUTATION_WITHOUT_LEDGER",
    "FIELD_OVERFLOW",
    "REQUIRED_FIELD_MISSING",
    "OPEN_SAFETY_FAILED",
    "REFERENCE_INTEGRITY_FAILED",
    "CAPABILITY_SKEW",
    "RENDER_ORACLE_UNAVAILABLE",
    "PROFILE_REQUIRED",
    "STYLE_COVERAGE_TOO_LOW",
]
