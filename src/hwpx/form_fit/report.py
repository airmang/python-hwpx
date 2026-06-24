# SPDX-License-Identifier: Apache-2.0
"""FormFit result types (plan §2 C / Appendix A).

:class:`FitResult` is what the :class:`~hwpx.form_fit.engine.FitEngine` returns
for one filled value. :func:`to_form_report` folds a batch of them into the
``FormReport`` that rides on the ``VisualCompleteReport`` produced by the single
:class:`~hwpx.quality.SavePipeline` (plan §2 B/C), so a form fill reports through
the same one gate as every other write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a hard dependency cycle (quality imports visual, etc.)
    from hwpx.quality.report import FormReport

# Structured, retry-able error code (mirrors hwpx.quality.report.FIELD_OVERFLOW).
FIELD_OVERFLOW = "FIELD_OVERFLOW"


@dataclass(slots=True)
class FitResult:
    """Outcome of fitting one value into one slot (plan Appendix A)."""

    ok: bool
    value: str
    applied_value: str
    applied_style_changes: dict[str, Any] = field(default_factory=dict)
    lines: int | None = None
    font_pt: float | None = None
    overflow_detected: bool = False
    truncated: bool = False
    confidence: str = "high"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Optional locator so a FormReport entry can point at the field/cell.
    field_id: str | None = None

    @property
    def style_changed(self) -> bool:
        return bool(self.applied_style_changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fieldId": self.field_id,
            "value": self.value,
            "appliedValue": self.applied_value,
            "appliedStyleChanges": dict(self.applied_style_changes),
            "lines": self.lines,
            "fontPt": self.font_pt,
            "overflowDetected": self.overflow_detected,
            "truncated": self.truncated,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    def suggested_retry(self) -> dict[str, Any] | None:
        """A structured hint a model can act on after a hard overflow."""

        if self.ok:
            return None
        return {
            "code": FIELD_OVERFLOW,
            "fieldId": self.field_id,
            "value": self.value,
            "options": [
                {"fitPolicy": {"mode": "wrap_then_shrink", "overflow": "warn"}},
                {"fitPolicy": {"mode": "shrink", "minFontPt": 7.0}},
                {"fitPolicy": {"mode": "truncate_with_report"}},
                {"action": "shortenValue"},
            ],
        }


def to_form_report(results: list[FitResult]) -> "FormReport":
    """Fold *results* into the quality-layer ``FormReport`` (one-gate report)."""

    from hwpx.quality.report import FormReport

    fields = [result.to_dict() for result in results]
    warnings: list[str] = []
    errors: list[str] = []
    for result in results:
        warnings.extend(result.warnings)
        errors.extend(result.errors)
    ok = all(result.ok for result in results)
    return FormReport(ok=ok, fields=fields, warnings=warnings, errors=errors)


__all__ = ["FitResult", "FIELD_OVERFLOW", "to_form_report"]
