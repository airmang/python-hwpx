# SPDX-License-Identifier: Apache-2.0
"""Conformance badge tiers + thresholds (plan §2 Phase G).

Four tiers, each a ratio over the cases that actually exercised it, judged
against an explicit threshold:

* **Open-Safe** — opens in Hancom (structurally: editor-open-safety passes).
* **Semantic-Safe** — declared content assertions hold.
* **Form-Safe** — declared form values fit their slots (FormFit measurement);
  the form set's overflow rate must be 0.
* **VisualComplete** — open + semantic + form + layout + visual all pass on the
  oracle tier. Off-oracle it is reported ``unverified``, never a silent pass
  (plan §0.0).

Thresholds default to the **strict** docx-grade floor (the option chosen for
Phase G): 100% on the structural tiers, zero overflow on the form set, ≥95% on
VisualComplete when an oracle runs. Override per corpus via ``corpus.json`` or the
CLI if a population needs a softer floor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .corpus import BADGE_TIERS, BadgeTier

if TYPE_CHECKING:
    from .report import CaseResult

BadgeStatus = str  # "pass" | "fail" | "unverified"


@dataclass(frozen=True, slots=True)
class BadgeThresholds:
    """Minimum pass rate per tier (strict docx-grade defaults, plan §2 G)."""

    open_safe: float = 1.0
    semantic_safe: float = 1.0
    form_safe: float = 1.0
    form_overflow_rate_max: float = 0.0
    visual_complete: float = 0.95

    def for_tier(self, tier: BadgeTier) -> float:
        return float(getattr(self, tier))

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BadgeThresholds":
        if not data:
            return cls()
        return cls(
            open_safe=float(data.get("openSafe", data.get("open_safe", 1.0))),
            semantic_safe=float(
                data.get("semanticSafe", data.get("semantic_safe", 1.0))
            ),
            form_safe=float(data.get("formSafe", data.get("form_safe", 1.0))),
            form_overflow_rate_max=float(
                data.get(
                    "formOverflowRateMax", data.get("form_overflow_rate_max", 0.0)
                )
            ),
            visual_complete=float(
                data.get("visualComplete", data.get("visual_complete", 0.95))
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "openSafe": self.open_safe,
            "semanticSafe": self.semantic_safe,
            "formSafe": self.form_safe,
            "formOverflowRateMax": self.form_overflow_rate_max,
            "visualComplete": self.visual_complete,
        }


@dataclass(slots=True)
class Badge:
    """Aggregate verdict for one tier across the corpus."""

    tier: BadgeTier
    status: BadgeStatus
    pass_rate: float
    passed: int
    failed: int
    applicable: int
    unverified: int
    threshold: float
    extra: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tier": self.tier,
            "status": self.status,
            "passRate": round(self.pass_rate, 4),
            "passed": self.passed,
            "failed": self.failed,
            "applicable": self.applicable,
            "unverified": self.unverified,
            "threshold": self.threshold,
        }
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


def _form_overflow_rate(cases: "list[CaseResult]") -> tuple[int, int]:
    """Return ``(overflow_slots, total_slots)`` across Form-Safe verdicts."""

    overflow = 0
    total = 0
    for case in cases:
        verdict = case.verdicts.get("form_safe")
        if verdict is None or not verdict.counts:
            continue
        overflow += int(verdict.metrics.get("overflow_count", 0))
        total += int(verdict.metrics.get("checked", 0))
    return overflow, total


def evaluate_badge(
    tier: BadgeTier, cases: "list[CaseResult]", thresholds: BadgeThresholds
) -> Badge:
    """Aggregate one tier into a :class:`Badge`."""

    passed = failed = unverified = 0
    for case in cases:
        verdict = case.verdicts.get(tier)
        if verdict is None or verdict.status == "skip":
            continue
        if verdict.status == "pass":
            passed += 1
        elif verdict.status == "fail":
            failed += 1
        else:  # unverified
            unverified += 1

    applicable = passed + failed
    threshold = thresholds.for_tier(tier)
    extra: dict[str, Any] = {}

    if applicable == 0:
        # Nothing measured this tier (e.g. VisualComplete with no oracle, or a
        # corpus with no form cases). Honest "not measured", not a pass.
        return Badge(
            tier=tier,
            status="unverified",
            pass_rate=0.0,
            passed=0,
            failed=0,
            applicable=0,
            unverified=unverified,
            threshold=threshold,
            extra=extra,
        )

    pass_rate = passed / applicable
    status = "pass" if pass_rate + 1e-9 >= threshold else "fail"

    if tier == "form_safe":
        overflow, total = _form_overflow_rate(cases)
        rate = overflow / total if total else 0.0
        extra = {"overflowRate": round(rate, 4), "overflowSlots": overflow, "slots": total}
        if rate > thresholds.form_overflow_rate_max + 1e-9:
            status = "fail"

    return Badge(
        tier=tier,
        status=status,
        pass_rate=pass_rate,
        passed=passed,
        failed=failed,
        applicable=applicable,
        unverified=unverified,
        threshold=threshold,
        extra=extra,
    )


def evaluate_badges(
    cases: "list[CaseResult]", thresholds: BadgeThresholds | None = None
) -> list[Badge]:
    """Evaluate all four badge tiers over *cases*."""

    thresholds = thresholds or BadgeThresholds()
    return [evaluate_badge(tier, cases, thresholds) for tier in BADGE_TIERS]


__all__ = [
    "BadgeStatus",
    "BadgeThresholds",
    "Badge",
    "evaluate_badge",
    "evaluate_badges",
]
