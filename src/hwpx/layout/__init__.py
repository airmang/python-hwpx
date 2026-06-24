# SPDX-License-Identifier: Apache-2.0
"""LayoutLint — renderer-less structural visual smoke (plan §2 Phase D).

Gives the **structural tier** (no Hancom reachable) teeth: it catches likely
visual defects — stale lineseg caches, ledger/lineseg inconsistency, grossly
over-wide cell values, malformed tables — purely from the serialized bytes, and
the single :class:`~hwpx.quality.SavePipeline` wires it as a (policy-gated) hard
gate. The edit ledger lives in :mod:`hwpx.quality.ledger`; it is re-exported here
for convenience since it is the lint's edit-mask input.
"""
from __future__ import annotations

from hwpx.quality.ledger import DirtyLayoutLedger, DirtyLayoutRange

from .lint import (
    FIELD_OVERFLOW,
    OVERFLOW_RISK,
    REQUIRED_FIELD_MISSING,
    STALE_LINESEG_DETECTED,
    TABLE_STRUCTURE_INVALID,
    lint_layout,
)
from .report import LayoutFinding, LayoutLintReport

__all__ = [
    "lint_layout",
    "LayoutLintReport",
    "LayoutFinding",
    "DirtyLayoutLedger",
    "DirtyLayoutRange",
    "STALE_LINESEG_DETECTED",
    "FIELD_OVERFLOW",
    "REQUIRED_FIELD_MISSING",
    "TABLE_STRUCTURE_INVALID",
    "OVERFLOW_RISK",
]
