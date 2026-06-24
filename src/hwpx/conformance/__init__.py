# SPDX-License-Identifier: Apache-2.0
"""Conformance corpus + badges — make "docx-grade" measurable (plan §2 Phase G).

This package turns the VisualComplete quality bar into *numbers*: a corpus of
documents, a runner that scores each across four badge tiers (Open-Safe,
Semantic-Safe, Form-Safe, VisualComplete) against explicit thresholds, and a
golden baseline so a regression shows up as a dropped pass rate rather than a
vibe (the Phase-G acceptance).

The assurance tier is never blurred (plan §0.0): the structural run (any CI, no
Hancom) can claim Open/Semantic/Form but reports VisualComplete ``unverified``;
only the oracle run (a reachable Hancom backend) verifies VisualComplete.

Entry points::

    from hwpx.conformance import ConformanceCorpus, run_conformance
    report = run_conformance(ConformanceCorpus.bundled())
    # or: hwpx-conformance run --tier structural
"""
from __future__ import annotations

from .badges import Badge, BadgeThresholds, evaluate_badge, evaluate_badges
from .corpus import (
    BADGE_TIERS,
    BadgeTier,
    ConformanceCase,
    ConformanceCorpus,
    FormSlot,
)
from .report import (
    CaseResult,
    ConformanceReport,
    TierVerdict,
    diff_golden,
)
from .runner import evaluate_case, run_conformance

__all__ = [
    "BADGE_TIERS",
    "BadgeTier",
    "FormSlot",
    "ConformanceCase",
    "ConformanceCorpus",
    "TierVerdict",
    "CaseResult",
    "ConformanceReport",
    "diff_golden",
    "Badge",
    "BadgeThresholds",
    "evaluate_badge",
    "evaluate_badges",
    "run_conformance",
    "evaluate_case",
]
