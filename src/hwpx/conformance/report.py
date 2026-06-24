# SPDX-License-Identifier: Apache-2.0
"""Conformance result models (plan §2 Phase G).

A :class:`TierVerdict` is one tier's outcome for one case; a :class:`CaseResult`
bundles the four tiers for a document; a :class:`ConformanceReport` aggregates the
corpus into badge verdicts plus a per-case table. Everything is JSON-serialisable
so a run is comparable against a committed golden (regression = a number, not a
vibe — the Phase-G acceptance).

The status vocabulary keeps the assurance tier explicit (plan §0.0):

* ``pass``       — the tier ran and the case met it.
* ``fail``       — the tier ran and the case missed it.
* ``skip``       — the tier does not apply to this case (not in any denominator).
* ``unverified`` — the tier applies but could not run (no Hancom oracle for
  VisualComplete). **Never** silently counted as a pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from .corpus import BADGE_TIERS, BadgeTier

if TYPE_CHECKING:
    from .badges import Badge

TierStatus = Literal["pass", "fail", "skip", "unverified"]
RunTier = Literal["structural", "oracle"]


@dataclass(slots=True)
class TierVerdict:
    """One badge tier's outcome for one case."""

    tier: BadgeTier
    status: TierStatus
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def counts(self) -> bool:
        """True when this verdict is in the badge denominator (ran pass/fail)."""

        return self.status in ("pass", "fail")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tier": self.tier, "status": self.status}
        if self.detail:
            out["detail"] = self.detail
        if self.metrics:
            out["metrics"] = dict(self.metrics)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TierVerdict":
        return cls(
            tier=data["tier"],
            status=data["status"],
            detail=data.get("detail", ""),
            metrics=dict(data.get("metrics", {})),
        )


@dataclass(slots=True)
class CaseResult:
    """The four tier verdicts for one document."""

    case_id: str
    visibility: str
    verdicts: dict[BadgeTier, TierVerdict]

    @property
    def failed_tiers(self) -> list[BadgeTier]:
        return [t for t, v in self.verdicts.items() if v.status == "fail"]

    @property
    def ok(self) -> bool:
        """No tier failed (skip/unverified are not failures)."""

        return not self.failed_tiers

    def status_map(self) -> dict[str, str]:
        """Flat ``{tier: status}`` used for golden comparison."""

        return {tier: self.verdicts[tier].status for tier in BADGE_TIERS if tier in self.verdicts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "visibility": self.visibility,
            "verdicts": {t: v.to_dict() for t, v in self.verdicts.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseResult":
        return cls(
            case_id=data["caseId"],
            visibility=data.get("visibility", "public"),
            verdicts={
                t: TierVerdict.from_dict(v) for t, v in data.get("verdicts", {}).items()
            },
        )


@dataclass(slots=True)
class ConformanceReport:
    """A corpus run: per-case verdicts + aggregated badges."""

    tier: RunTier
    render_checked: bool
    cases: list[CaseResult]
    badges: "list[Badge]"
    corpus_name: str = "corpus"

    @property
    def ok(self) -> bool:
        """CI-gate verdict: no badge *failed*.

        An ``unverified`` badge (e.g. VisualComplete with no oracle) does not fail
        the gate — structural CI cannot claim docx-grade, only the oracle tier can
        (plan §0.0). Regression against golden is a separate, sharper signal.
        """

        return all(badge.status != "fail" for badge in self.badges)

    def badge(self, tier: BadgeTier) -> "Badge | None":
        return next((b for b in self.badges if b.tier == tier), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus": self.corpus_name,
            "tier": self.tier,
            "renderChecked": self.render_checked,
            "ok": self.ok,
            "badges": [b.to_dict() for b in self.badges],
            "cases": [c.to_dict() for c in self.cases],
        }

    def golden_dict(self) -> dict[str, Any]:
        """A stable, diff-friendly subset for the committed golden baseline.

        Only the per-tier pass rates and per-case statuses — not free-text detail
        or absolute paths — so a golden compares the *measured numbers*, which is
        exactly what a Phase-G regression is.
        """

        return {
            "corpus": self.corpus_name,
            "badges": {
                b.tier: {"status": b.status, "passRate": round(b.pass_rate, 4)}
                for b in self.badges
            },
            "cases": {c.case_id: c.status_map() for c in self.cases},
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Conformance — {self.corpus_name} ({self.tier})",
            "",
            f"render_checked: **{self.render_checked}** · gate: "
            f"**{'PASS' if self.ok else 'FAIL'}**",
            "",
            "| Badge | Status | Pass rate | Applicable | Unverified |",
            "|---|---|---|---|---|",
        ]
        for badge in self.badges:
            rate = "—" if badge.applicable == 0 else f"{badge.pass_rate * 100:.0f}%"
            lines.append(
                f"| {badge.tier} | {badge.status.upper()} | {rate} "
                f"| {badge.applicable} | {badge.unverified} |"
            )
        return "\n".join(lines) + "\n"


def diff_golden(
    golden: dict[str, Any], current: "ConformanceReport"
) -> list[str]:
    """Return human-readable regressions of *current* against *golden*.

    A regression is any case tier that was ``pass`` in golden and is now ``fail``,
    a badge that dropped from ``pass`` to ``fail``, or a badge pass rate that fell.
    New cases / improvements are not regressions (a golden is a floor).
    """

    regressions: list[str] = []
    golden_badges = golden.get("badges", {})
    for badge in current.badges:
        prior = golden_badges.get(badge.tier)
        if not prior:
            continue
        if prior.get("status") == "pass" and badge.status == "fail":
            regressions.append(
                f"badge {badge.tier}: pass -> fail "
                f"(rate {prior.get('passRate')} -> {round(badge.pass_rate, 4)})"
            )
        elif badge.pass_rate + 1e-9 < float(prior.get("passRate", 0.0)):
            regressions.append(
                f"badge {badge.tier}: pass rate dropped "
                f"{prior.get('passRate')} -> {round(badge.pass_rate, 4)}"
            )

    golden_cases = golden.get("cases", {})
    current_cases = {c.case_id: c.status_map() for c in current.cases}
    for case_id, prior_statuses in golden_cases.items():
        now = current_cases.get(case_id)
        if now is None:
            regressions.append(f"case {case_id}: missing from this run")
            continue
        for tier, prior_status in prior_statuses.items():
            if prior_status == "pass" and now.get(tier) == "fail":
                regressions.append(f"case {case_id}/{tier}: pass -> fail")
    return regressions


__all__ = [
    "TierStatus",
    "RunTier",
    "TierVerdict",
    "CaseResult",
    "ConformanceReport",
    "diff_golden",
]
