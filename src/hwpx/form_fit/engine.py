# SPDX-License-Identifier: Apache-2.0
"""``FitEngine`` — decide how a value is made to fit its slot (plan §2 C).

The engine is **pure**: it measures a value against a :class:`SlotMetrics`,
walks the :class:`FitPolicy` ladder (keep → wrap → shrink → expand/truncate/fail),
and returns a :class:`FitResult` describing the *decision* (final text, any font
change, line count, overflow/truncate flags). It never touches XML — the caller
(``set_cell_text`` / ``fill_form_field``) applies ``applied_value`` and
``applied_style_changes`` and records the :class:`DirtyLayoutRange`.

The honesty contract (plan §2 C acceptance, confirmed by ``work/formfit_calibrate``):
a hard ``overflow="fail"`` fires **only** when the overflow is *high confidence*
(grossly too long). A borderline overflow, where the crude advance table can't be
trusted, is downgraded to a warning and left for the render oracle to arbitrate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .measure import (
    GROSS_ROW_GROWTH_FACTOR,
    MIN_ROW_GROWTH_LINES,
    SlotMetrics,
    estimate_text_width,
    measure,
)
from .policy import FitPolicy
from .report import FitResult

# Font ladder step (points) used when shrinking.
_SHRINK_STEP_PT = 0.5

# The vertical room could not be measured (merged cell, no height, or an auto-grow
# floor); the fit is width-only and the oracle must confirm the vertical fit.
_HEIGHT_UNAVAILABLE_NOTE = (
    "cell height is not a usable budget (merged/auto-grow); fit is width-only — "
    "render oracle should confirm the vertical fit"
)
# The content needs more vertical room than the authored cell height, but not
# grossly — the row will grow modestly. Reported (never silent), deferred to oracle.
_ROW_GROWTH_NOTE = (
    "value needs more lines than the cell height budgets; the row will grow — "
    "render oracle should confirm no page shift"
)


@dataclass(slots=True)
class FitEngine:
    """Applies a :class:`FitPolicy` to a value/slot, yielding a :class:`FitResult`."""

    def fit(
        self,
        value: str,
        slot: SlotMetrics,
        policy: FitPolicy | None = None,
        *,
        field_id: str | None = None,
    ) -> FitResult:
        policy = policy or FitPolicy()
        value = "" if value is None else str(value)

        # An empty value always "fits"; nothing to measure.
        if value == "":
            return FitResult(
                ok=True,
                value=value,
                applied_value=value,
                lines=0,
                font_pt=slot.font_pt,
                field_id=field_id,
            )

        if policy.mode == "keep":
            return self._keep(value, slot, policy, field_id)
        if policy.mode == "truncate_with_report":
            return self._truncate(value, slot, policy, field_id)
        if policy.mode == "expand_row":
            return self._expand_row(value, slot, policy, field_id)

        # Reshaping ladder: wrap, shrink, or wrap_then_shrink, then fail_on_overflow.
        wrap_lines = policy.effective_max_lines if policy.may_wrap else 1
        wrap_slot = replace(slot, max_lines=wrap_lines)
        measurement = measure(value, wrap_slot)
        if measurement.fits:
            result = FitResult(
                ok=True,
                value=value,
                applied_value=value,
                applied_style_changes=(
                    {"wrapped_lines": measurement.lines}
                    if policy.may_wrap and measurement.lines > 1
                    else {}
                ),
                lines=measurement.lines,
                font_pt=slot.font_pt,
                confidence=measurement.confidence,
                warnings=list(measurement.notes),
                field_id=field_id,
            )
            return self._apply_height_budget(result, value, slot, policy, wrap_lines, field_id)

        if policy.may_shrink:
            shrunk = self._try_shrink(value, slot, policy, wrap_lines)
            if shrunk is not None:
                shrunk = replace(shrunk, field_id=field_id)
                return self._apply_height_budget(
                    shrunk, value, slot, policy, wrap_lines, field_id
                )

        # Still overflowing → terminal overflow action (confidence-gated).
        return self._overflow(value, wrap_slot, policy, field_id, measurement)

    # -- modes ------------------------------------------------------------- #
    def _keep(
        self, value: str, slot: SlotMetrics, policy: FitPolicy, field_id: str | None
    ) -> FitResult:
        m = measure(value, slot)
        warnings = list(m.notes)
        if m.overflow:
            warnings.append(
                "value exceeds the slot but mode=keep leaves it unchanged"
            )
        return FitResult(
            ok=True,
            value=value,
            applied_value=value,
            lines=m.lines,
            font_pt=slot.font_pt,
            overflow_detected=m.overflow,
            confidence=m.confidence,
            warnings=warnings,
            field_id=field_id,
        )

    def _expand_row(
        self, value: str, slot: SlotMetrics, policy: FitPolicy, field_id: str | None
    ) -> FitResult:
        big = replace(slot, max_lines=policy.effective_max_lines)
        m = measure(value, big)
        warnings = list(m.notes)
        # Row-expand fixes vertical room only; a single token wider than the slot
        # still overflows horizontally and the oracle must catch it.
        horizontal_risk = self._longest_token_width(value, slot.font_pt) > slot.available_width
        if horizontal_risk:
            warnings.append(
                "a token is wider than the slot; expand_row cannot fix horizontal "
                "overflow — render oracle should confirm"
            )
        return FitResult(
            ok=True,
            value=value,
            applied_value=value,
            applied_style_changes={"expand_row": True, "lines": m.lines},
            lines=m.lines,
            font_pt=slot.font_pt,
            overflow_detected=horizontal_risk,
            confidence=m.confidence,
            warnings=warnings,
            field_id=field_id,
        )

    def _truncate(
        self, value: str, slot: SlotMetrics, policy: FitPolicy, field_id: str | None
    ) -> FitResult:
        lines = policy.effective_max_lines if policy.may_wrap else 1
        slot_n = replace(slot, max_lines=lines)
        m = measure(value, slot_n)
        if m.fits:
            return FitResult(
                ok=True,
                value=value,
                applied_value=value,
                lines=m.lines,
                font_pt=slot.font_pt,
                confidence=m.confidence,
                warnings=list(m.notes),
                field_id=field_id,
            )
        applied = self._longest_prefix(value, slot_n)
        return FitResult(
            ok=True,
            value=value,
            applied_value=applied,
            applied_style_changes={"truncated_from": len(value)},
            lines=measure(applied, slot_n).lines if applied else 0,
            font_pt=slot.font_pt,
            overflow_detected=True,
            truncated=True,
            confidence=m.confidence,
            warnings=[
                f"value truncated to fit the slot: {len(value)} → {len(applied)} chars"
            ],
            field_id=field_id,
        )

    # -- shrink ladder ----------------------------------------------------- #
    def _try_shrink(
        self, value: str, slot: SlotMetrics, policy: FitPolicy, max_lines: int
    ) -> FitResult | None:
        """Largest font (>= min) that makes *value* fit with high confidence."""

        ceiling = policy.max_font_pt or slot.font_pt
        candidate = min(slot.font_pt, ceiling)
        best: FitResult | None = None
        while candidate >= policy.min_font_pt - 1e-9:
            trial = SlotMetrics(
                available_width=slot.available_width,
                font_pt=candidate,
                max_lines=max_lines,
                raw_width=slot.raw_width,
                source=slot.source,
            )
            m = measure(value, trial)
            if m.fits and m.confidence == "high":
                changes: dict[str, object] = {
                    "font_pt": round(candidate, 2),
                    "from_font_pt": round(slot.font_pt, 2),
                }
                if max_lines > 1 and m.lines > 1:
                    changes["wrapped_lines"] = m.lines
                best = FitResult(
                    ok=True,
                    value=value,
                    applied_value=value,
                    applied_style_changes=changes,
                    lines=m.lines,
                    font_pt=round(candidate, 2),
                    confidence="high",
                    warnings=(
                        [] if candidate == slot.font_pt
                        else [f"font shrunk {slot.font_pt:g}pt → {candidate:g}pt to fit"]
                    ),
                )
                break
            candidate = round(candidate - _SHRINK_STEP_PT, 4)
        return best

    # -- vertical (row-height) budget ------------------------------------- #
    def _apply_height_budget(
        self,
        result: FitResult,
        value: str,
        slot: SlotMetrics,
        policy: FitPolicy,
        wrap_lines: int,
        field_id: str | None,
    ) -> FitResult:
        """Overlay the authored row-height budget on a width-fitting *result*.

        The width ladder decides horizontal fit; this decides whether the value
        also sits inside the cell's *vertical* room, so a filled row does not
        silently grow and shift the page (the dominant M9 form-fill defect).

        Honesty contract (mirrors the width path, grounded in the S-085 P0/P1
        measurement): the authored ``cellSz.height`` is an unreliable proxy in wild
        forms (auto-grow, tiny floors, merges), so a *modest* vertical overflow is
        reported and deferred to the render oracle; only a *gross* balloon shrinks
        or fails closed. ``allow_row_expand`` / ``expand_row`` opt out entirely.
        """

        if slot.available_height is None:
            if slot.height_unavailable and result.ok:
                result.warnings.append(_HEIGHT_UNAVAILABLE_NOTE)
            return result
        if policy.allow_row_expand or policy.mode == "expand_row":
            return result

        font = result.font_pt if result.font_pt is not None else slot.font_pt
        wrapped = result.lines if result.lines is not None else 1
        verdict = self._height_verdict(slot, wrapped, font)
        if verdict == "fits":
            return result
        if verdict == "modest":
            # S-085 P1 calibration round 2 (differential-measured): the modest
            # band is where pages actually shift, so try to shrink INTO the
            # budget first; only defer to the oracle when no font >= min can
            # land the value fully inside the authored height.
            if policy.may_shrink:
                shrunk = self._try_shrink_for_height(
                    value, slot, policy, wrap_lines, field_id, accept_modest=False
                )
                if shrunk is not None:
                    return shrunk
            result.overflow_detected = True
            result.warnings.append(_ROW_GROWTH_NOTE)
            return result

        # Gross vertical balloon: shrink (prefer a full fit, else the least
        # growth), else fail-closed.
        if policy.may_shrink:
            shrunk = self._try_shrink_for_height(
                value, slot, policy, wrap_lines, field_id, accept_modest=True
            )
            if shrunk is not None:
                return shrunk
        return self._overflow_height(value, slot, policy, field_id, wrapped, font)

    def _height_verdict(self, slot: SlotMetrics, wrapped_lines: int, font_pt: float) -> str:
        """Classify vertical fit as ``fits`` / ``modest`` / ``gross``."""

        budget = slot.height_lines(font_pt)
        if budget is None or wrapped_lines <= budget:
            return "fits"
        optimistic = slot.height_lines_optimistic(font_pt) or budget
        if (
            wrapped_lines > optimistic * GROSS_ROW_GROWTH_FACTOR
            and (wrapped_lines - optimistic) >= MIN_ROW_GROWTH_LINES
        ):
            return "gross"
        return "modest"

    def _try_shrink_for_height(
        self,
        value: str,
        slot: SlotMetrics,
        policy: FitPolicy,
        wrap_lines: int,
        field_id: str | None,
        *,
        accept_modest: bool,
    ) -> FitResult | None:
        """Largest font (>= min) that lands the value INSIDE the height budget.

        Walks the shrink ladder preferring a full vertical fit ("fits"). When
        ``accept_modest`` is true and no font achieves a full fit, the largest
        candidate whose growth is merely *modest* (never gross) is returned as
        the least-damage fallback, reported and deferred to the oracle.
        """

        ceiling = policy.max_font_pt or slot.font_pt
        candidate = min(slot.font_pt, ceiling)
        modest_candidate: tuple[float, int] | None = None
        while candidate >= policy.min_font_pt - 1e-9:
            trial = replace(slot, font_pt=candidate, max_lines=wrap_lines)
            m = measure(value, trial)
            if m.fits and m.confidence == "high":
                verdict = self._height_verdict(slot, m.lines, candidate)
                if verdict == "fits":
                    return self._shrunk_result(
                        value, slot, candidate, m.lines, wrap_lines, field_id,
                        modest=False,
                    )
                if verdict == "modest" and modest_candidate is None:
                    modest_candidate = (candidate, m.lines)
            candidate = round(candidate - _SHRINK_STEP_PT, 4)
        if accept_modest and modest_candidate is not None:
            font_pt, lines = modest_candidate
            return self._shrunk_result(
                value, slot, font_pt, lines, wrap_lines, field_id, modest=True
            )
        return None

    def _shrunk_result(
        self,
        value: str,
        slot: SlotMetrics,
        candidate: float,
        lines: int,
        wrap_lines: int,
        field_id: str | None,
        *,
        modest: bool,
    ) -> FitResult:
        changes: dict[str, object] = {}
        warnings: list[str] = []
        if candidate != slot.font_pt:
            changes = {
                "font_pt": round(candidate, 2),
                "from_font_pt": round(slot.font_pt, 2),
            }
            warnings.append(
                f"font shrunk {slot.font_pt:g}pt → {candidate:g}pt to fit the row height"
            )
        if wrap_lines > 1 and lines > 1:
            changes["wrapped_lines"] = lines
        if modest:
            warnings.append(_ROW_GROWTH_NOTE)
        return FitResult(
            ok=True,
            value=value,
            applied_value=value,
            applied_style_changes=changes,
            lines=lines,
            font_pt=round(candidate, 2),
            confidence="high",
            overflow_detected=modest,
            warnings=warnings,
            field_id=field_id,
        )

    def _overflow_height(
        self,
        value: str,
        slot: SlotMetrics,
        policy: FitPolicy,
        field_id: str | None,
        wrapped_lines: int,
        font_pt: float,
    ) -> FitResult:
        """Terminal action for a gross vertical balloon that shrink cannot resolve."""

        budget = slot.height_lines(font_pt)
        action = policy.overflow
        # Line-level truncation is not modelled; keep the value and warn (honest).
        if action == "truncate":
            action = "warn"
        if action == "warn":
            return FitResult(
                ok=True,
                value=value,
                applied_value=value,
                lines=wrapped_lines,
                font_pt=font_pt,
                overflow_detected=True,
                confidence="high",
                warnings=[
                    f"value needs ~{wrapped_lines} lines but the row height holds "
                    f"~{budget}; the row will balloon (overflow=warn)"
                ],
                field_id=field_id,
            )
        return FitResult(
            ok=False,
            value=value,
            applied_value=value,
            lines=wrapped_lines,
            font_pt=font_pt,
            overflow_detected=True,
            confidence="high",
            errors=[
                f"FIELD_OVERFLOW: value needs ~{wrapped_lines} lines but the row height "
                f"holds ~{budget}; shrink/shorten the value or allow row expansion"
            ],
            field_id=field_id,
        )

    # -- terminal overflow action ----------------------------------------- #
    def _overflow(
        self,
        value: str,
        slot: SlotMetrics,
        policy: FitPolicy,
        field_id: str | None,
        measurement,
    ) -> FitResult:
        # Honesty gate: never hard-fail a low-confidence (borderline) overflow —
        # downgrade to a warning and let the render oracle decide (plan §2 C).
        action = policy.overflow
        if action == "fail" and measurement.confidence != "high":
            action = "warn"

        if action == "truncate":
            return self._truncate(value, slot, policy.with_(mode="truncate_with_report"), field_id)

        if action == "warn":
            note = (
                "low-confidence overflow; deferring the hard fail to the render oracle"
                if measurement.confidence != "high"
                else "value overflows the slot (overflow=warn)"
            )
            return FitResult(
                ok=True,
                value=value,
                applied_value=value,
                lines=measurement.lines,
                font_pt=slot.font_pt,
                overflow_detected=True,
                confidence=measurement.confidence,
                warnings=[*measurement.notes, note],
                field_id=field_id,
            )

        # action == "fail", high confidence.
        return FitResult(
            ok=False,
            value=value,
            applied_value=value,
            lines=measurement.lines,
            font_pt=slot.font_pt,
            overflow_detected=True,
            confidence="high",
            errors=[
                f"FIELD_OVERFLOW: value needs ~{measurement.lines} lines but the slot "
                f"holds {slot.max_lines}; shrink/​wrap/​shorten the value"
            ],
            field_id=field_id,
        )

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _longest_token_width(value: str, font_pt: float) -> float:
        widest = 0.0
        for token in value.replace("\t", " ").split(" "):
            widest = max(widest, estimate_text_width(token, font_pt))
        return widest

    @staticmethod
    def _longest_prefix(value: str, slot: SlotMetrics) -> str:
        """Longest prefix of *value* that fits *slot* (conservative, with band)."""

        capacity = slot.capacity
        low, high = 0, len(value)
        best = 0
        while low <= high:
            mid = (low + high) // 2
            prefix = value[:mid]
            m = measure(prefix, slot)
            if estimate_text_width(prefix, slot.font_pt) <= capacity * (1 - m.band) and m.fits:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return value[:best]


__all__ = ["FitEngine"]
