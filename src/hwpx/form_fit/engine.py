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

from .measure import SlotMetrics, estimate_text_width, measure
from .policy import FitPolicy
from .report import FitResult

# Font ladder step (points) used when shrinking.
_SHRINK_STEP_PT = 0.5


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
            return FitResult(
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

        if policy.may_shrink:
            shrunk = self._try_shrink(value, slot, policy, wrap_lines)
            if shrunk is not None:
                return replace(shrunk, field_id=field_id)

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
