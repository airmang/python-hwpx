# SPDX-License-Identifier: Apache-2.0
"""``QualityPolicy`` — the knobs that decide how strict a save gate is.

The dataclass defaults are the **aspirational / docx-grade** policy (plan
Appendix A): open-safety required, reference integrity required, and a visual
render demanded (``render_check="auto"`` → use the Hancom oracle when one is
reachable, and require it for ``visual_complete``). On a box with no Hancom that
strict policy can only reach a *structural* pass, so ``visual_complete`` stays
``unverified`` and ``ok`` is ``False`` unless ``allow_expert_unsafe`` is set —
this is the §0.0 contract made operational, not a bug.

:meth:`QualityPolicy.transparent` is the **backward-compatible** policy the legacy
write entry points use by default: it reproduces today's behaviour exactly
(open-safety enforced, nothing rendered, no new hard gates), so the single
SavePipeline is invisible until a caller opts into more.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

RenderCheck = Literal["off", "auto", "required"]
XsdMode = Literal["off", "lint"]
OverflowPolicy = Literal["fail", "warn", "truncate"]
LayoutInvalidation = Literal["none", "paragraph", "following", "story", "document"]
LayoutLint = Literal["off", "warn", "strict"]


@dataclass(frozen=True)
class QualityPolicy:
    """How strict the gate is. Defaults = aspirational docx-grade (plan Appendix A)."""

    require_open_safety: bool = True
    require_visual_complete: bool = True
    # lineseg invalidation is already handled at save (opc/package + patch.py);
    # this knob now mainly scopes the edit mask for the visual gate, not the strip.
    layout_invalidation: LayoutInvalidation = "story"
    render_check: RenderCheck = "auto"  # auto = use the oracle if one is reachable
    xsd_mode: XsdMode = "lint"  # soft by default (plan Appendix C)
    overflow_policy: OverflowPolicy = "fail"
    # Renderer-less layout smoke (plan §2 Phase D). "strict" = errors block (gives
    # the no-Hancom structural tier teeth); "warn" = surface only; "off" = skip.
    layout_lint: LayoutLint = "strict"
    preserve_unmodified_parts: bool = True
    allow_expert_unsafe: bool = False
    # Phase-B additions (beyond the condensed Appendix-A list).
    require_reference_integrity: bool = True  # OPC/content-types/ID ledger
    diff_eps: float = 0.005  # visual diff sensitivity (passed to visual_check)
    dpi: int = 150  # render DPI for the visual oracle

    @classmethod
    def transparent(cls) -> "QualityPolicy":
        """Reproduce today's save behaviour: open-safety only, never render.

        Used by the legacy ``save_to_path`` / ``paragraph_patch`` /
        ``apply_template_formfit`` / builder paths so the gate is a no-op pass for
        already-valid documents and the full suite stays green.
        """

        return cls(
            require_open_safety=True,
            require_visual_complete=False,
            render_check="off",
            xsd_mode="off",
            overflow_policy="warn",
            layout_lint="off",
            require_reference_integrity=False,
        )

    @classmethod
    def strict(cls) -> "QualityPolicy":
        """The full docx-grade gate: structural + reference + Hancom render."""

        return cls()

    def with_(self, **changes: object) -> "QualityPolicy":
        """Return a copy with ``changes`` applied (frozen-dataclass convenience)."""

        return replace(self, **changes)  # type: ignore[arg-type]

    @property
    def renders(self) -> bool:
        """True when this policy may invoke the visual oracle at all."""

        return self.render_check != "off"


__all__ = [
    "QualityPolicy",
    "RenderCheck",
    "XsdMode",
    "OverflowPolicy",
    "LayoutInvalidation",
    "LayoutLint",
]
