# SPDX-License-Identifier: Apache-2.0
"""FormFit — make form values *fit* their slots, not just get inserted.

Phase C of the VisualComplete plan (``docs/2026-06-23-visualcomplete-implementation
-plan.md`` §2 C). Form fill stops being raw insertion: a value is measured against
its cell/field box and wrapped / shrunk / failed per a :class:`FitPolicy`. Success
is "the value sits inside the slot and looks right", verified by the Hancom render
oracle, not "text was inserted".

The package is deliberately layered and pure (no XML side effects):

* :mod:`~hwpx.form_fit.policy`  — :class:`FitPolicy` (the decision rule).
* :mod:`~hwpx.form_fit.measure` — conservative, Hancom-calibrated text measurement
  and the fit/confidence verdict (:class:`SlotMetrics`, :class:`Measurement`).
* :mod:`~hwpx.form_fit.engine`  — :class:`FitEngine`, the keep→wrap→shrink ladder.
* :mod:`~hwpx.form_fit.report`  — :class:`FitResult` and the ``FormReport`` adapter.

Callers (``set_cell_text(fit=...)``, ``fill_form_field(fit_policy=...)``) apply the
returned :class:`FitResult` and fold it into the one ``VisualCompleteReport``.
"""
from __future__ import annotations

from .engine import FitEngine
from .measure import (
    DEFAULT_SAFETY,
    Measurement,
    SlotMetrics,
    TextStyle,
    estimate_lines,
    estimate_text_width,
    hancom_line_starts,
    measure,
    resolve_slot_metrics,
)
from .policy import FitMode, FitPolicy, OverflowAction
from .report import FIELD_OVERFLOW, FitResult, to_form_report

__all__ = [
    "FitPolicy",
    "FitMode",
    "OverflowAction",
    "FitEngine",
    "FitResult",
    "FIELD_OVERFLOW",
    "to_form_report",
    "SlotMetrics",
    "TextStyle",
    "Measurement",
    "measure",
    "estimate_text_width",
    "estimate_lines",
    "hancom_line_starts",
    "resolve_slot_metrics",
    "DEFAULT_SAFETY",
]
