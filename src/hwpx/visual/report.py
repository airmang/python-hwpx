# SPDX-License-Identifier: Apache-2.0
"""Result model for the VisualComplete render gate (Phase A).

``VisualReport`` is the structured judgement produced by
:func:`hwpx.visual.oracle.visual_check`. It deliberately separates *what was
checked* from *what the verdict is* so the assurance tier is never blurred
(see the implementation plan §0.0):

* ``render_checked`` is ``True`` only when a Hancom render diff actually ran.
  Off-oracle (no Hancom / missing imaging deps) it is ``False`` and the report
  is a *structural degrade*, never a silent visual pass.
* ``ok`` is ``True`` when no visual defect was found. When ``render_checked`` is
  ``False`` it means "nothing could be verified" (optimistic-but-labelled), not
  "verified clean".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VisualReport:
    """Judgement of a before/after (or single new-doc) render comparison."""

    ok: bool
    render_checked: bool
    original_render: str | None = None
    output_render: str | None = None
    diff_image: str | None = None
    unexpected_diff_outside_mask: bool = False
    overlap_detected: bool = False
    overflow_detected: bool = False
    table_break_detected: bool = False
    page_count_changed: bool | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Diagnostics (not part of the binding contract; useful in reports/CLI).
    max_diff_ratio: float | None = None
    before_page_count: int | None = None
    after_page_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["VisualReport"]
