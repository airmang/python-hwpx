# SPDX-License-Identifier: Apache-2.0
"""``FitPolicy`` — how a value is made to sit inside its slot (plan §2 C / App. A).

The policy is the *decision rule* the :class:`~hwpx.form_fit.engine.FitEngine`
follows when a value is measured against a cell/field box. It never mutates a
document itself; it only describes the intent. Defaults match Appendix A.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# How an over-long value is reshaped to fit (Appendix A modes).
FitMode = Literal[
    "keep",                 # insert as-is; measure + report only, never reshape
    "wrap",                 # allow wrapping up to max_lines
    "shrink",               # reduce font (>= min_font_pt) to fit on max_lines
    "wrap_then_shrink",     # try wrap first, then shrink (the default)
    "expand_row",           # let the row grow vertically (needs allow_row_expand)
    "truncate_with_report", # cut to fit and report the truncation
    "fail_on_overflow",     # never reshape; overflow is a hard failure
]

# What happens when, after the mode is applied, the value still does not fit.
OverflowAction = Literal["fail", "warn", "truncate"]


@dataclass(frozen=True)
class FitPolicy:
    """The fit decision rule for one value (plan Appendix A)."""

    mode: FitMode = "wrap_then_shrink"
    max_lines: int | None = None
    min_font_pt: float = 8.0
    max_font_pt: float | None = None
    allow_row_expand: bool = False
    overflow: OverflowAction = "fail"

    def __post_init__(self) -> None:
        if self.min_font_pt <= 0:
            raise ValueError("min_font_pt must be positive")
        if self.max_font_pt is not None and self.max_font_pt < self.min_font_pt:
            raise ValueError("max_font_pt must be >= min_font_pt")
        if self.max_lines is not None and self.max_lines < 1:
            raise ValueError("max_lines must be >= 1 when set")

    @property
    def effective_max_lines(self) -> int:
        """Resolve ``max_lines`` to a concrete cap for measurement.

        ``None`` means "the mode decides": single-line modes default to 1, while
        wrap/expand modes allow generous wrapping. ``expand_row`` is effectively
        unbounded (the row grows to fit).
        """

        if self.max_lines is not None:
            return self.max_lines
        if self.mode == "expand_row":
            return 1_000
        if self.mode in ("wrap", "wrap_then_shrink"):
            return 100
        return 1

    @property
    def may_wrap(self) -> bool:
        return self.mode in ("wrap", "wrap_then_shrink", "expand_row")

    @property
    def may_shrink(self) -> bool:
        return self.mode in ("shrink", "wrap_then_shrink")

    @classmethod
    def keep(cls) -> "FitPolicy":
        """Insert verbatim; measure and report but never reshape."""

        return cls(mode="keep", overflow="warn")

    def with_(self, **changes: object) -> "FitPolicy":
        from dataclasses import replace

        return replace(self, **changes)  # type: ignore[arg-type]


__all__ = ["FitPolicy", "FitMode", "OverflowAction"]
