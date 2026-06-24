# SPDX-License-Identifier: Apache-2.0
"""LayoutLint result types (plan §2 Phase D).

A :class:`LayoutLintReport` is the structured outcome of the renderer-less
structural visual smoke. :meth:`LayoutLintReport.to_quality_report` folds it into
the ``LayoutReport`` that rides the one ``VisualCompleteReport`` from the single
:class:`~hwpx.quality.SavePipeline` (plan §2 B/D), and ``error_codes`` lets the
pipeline surface retry-able :class:`~hwpx.quality.report.QualityError` codes.

Severity discipline (acceptance "lint may be stricter, never wronger"): only a
renderer-less-PROVABLE defect is an ``error`` (it blocks under a strict policy).
A heuristic guess — e.g. an un-fitted long cell that *might* overflow — is a
``warning``: it surfaces the risk without risking a false hard-fail that would
contradict the Phase-A oracle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # avoid an import cycle (quality imports visual, etc.)
    from hwpx.quality.report import LayoutReport

Severity = Literal["error", "warning"]


@dataclass(slots=True)
class LayoutFinding:
    """One renderer-less layout observation."""

    code: str
    message: str
    severity: Severity = "error"
    part: str | None = None
    paragraph: int | None = None
    detail: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:
        where = self.part or "?"
        if self.paragraph is not None:
            where += f" ¶{self.paragraph}"
        return f"{self.code} [{where}]: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "part": self.part,
            "paragraph": self.paragraph,
            "detail": self.detail,
        }


@dataclass(slots=True)
class LayoutLintReport:
    """Structured verdict of :func:`hwpx.layout.lint.lint_layout`."""

    findings: list[LayoutFinding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[LayoutFinding]:
        return [f for f in self.findings if f.is_error]

    @property
    def warnings(self) -> list[LayoutFinding]:
        return [f for f in self.findings if not f.is_error]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def error_codes(self) -> list[str]:
        # Stable, de-duplicated order for retry hints.
        seen: dict[str, None] = {}
        for finding in self.errors:
            seen.setdefault(finding.code, None)
        return list(seen)

    def add(self, finding: LayoutFinding) -> None:
        self.findings.append(finding)

    def demote_errors(self) -> "LayoutLintReport":
        """Return a copy with every error softened to a warning (warn mode)."""

        softened = [
            LayoutFinding(
                code=f.code, message=f.message, severity="warning",
                part=f.part, paragraph=f.paragraph, detail=f.detail,
            )
            if f.is_error else f
            for f in self.findings
        ]
        return LayoutLintReport(findings=softened, checked=list(self.checked))

    def to_quality_report(self) -> "LayoutReport":
        """Fold into the quality-layer ``LayoutReport`` (one-gate report)."""

        from hwpx.quality.report import LayoutReport

        return LayoutReport(
            ok=self.ok,
            warnings=[str(f) for f in self.warnings],
            errors=[str(f) for f in self.errors],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": list(self.checked),
            "findings": [f.to_dict() for f in self.findings],
        }


__all__ = ["LayoutFinding", "LayoutLintReport", "Severity"]
