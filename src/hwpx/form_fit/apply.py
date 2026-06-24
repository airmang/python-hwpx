# SPDX-License-Identifier: Apache-2.0
"""Apply a :class:`FitResult` to the live document model (plan §2 C, task 4).

The :class:`~hwpx.form_fit.engine.FitEngine` only *decides*; this module is the
thin glue that carries the decision into the XML: it sets the (possibly truncated)
text, materialises a font shrink as a **real** ``charPr`` via ``ensure_run_style``
so the change is visible to the render oracle, and records a
:class:`DirtyLayoutRange` on the ledger whenever the fit changed style.

Everything here is duck-typed against the ``HwpxOxml*`` objects so ``form_fit``
stays a leaf package with no import cycle into the document implementation.
"""
from __future__ import annotations

from typing import Any

from .engine import FitEngine
from .measure import resolve_slot_metrics
from .policy import FitPolicy
from .report import FitResult


def fit_cell_text(
    cell: Any,
    value: str,
    policy: FitPolicy,
    *,
    document: Any | None = None,
    ledger: Any | None = None,
    part_name: str | None = None,
    field_id: str | None = None,
    preserve_format: bool = True,
) -> FitResult:
    """Measure, decide, and apply *value* to *cell* under *policy*."""

    # Resolve geometry from the cell as it stands (its template font is the slot's
    # intended size) BEFORE we overwrite the text.
    slot = resolve_slot_metrics(cell, document, max_lines=policy.effective_max_lines)
    result = FitEngine().fit(value, slot, policy, field_id=field_id)

    cell.set_text(result.applied_value, preserve_format=preserve_format)

    font_pt = result.applied_style_changes.get("font_pt")
    if font_pt and document is not None:
        applied = _apply_font(cell, document, float(font_pt))
        if not applied:
            result.warnings.append(
                "requested font shrink could not be materialised (no header); "
                "value left at original size — render oracle should confirm"
            )

    if ledger is not None and (result.style_changed or result.overflow_detected):
        _note_ledger(ledger, cell, part_name, result)

    return result


def _apply_font(cell: Any, document: Any, font_pt: float) -> bool:
    """Point the cell's text runs at a ``charPr`` of *font_pt* (a real change)."""

    applied = False
    for paragraph in getattr(cell, "paragraphs", []):
        for run in getattr(paragraph, "runs", []):
            base_ref = getattr(run, "char_pr_id_ref", None)
            try:
                new_ref = document.ensure_run_style(
                    size=font_pt, base_char_pr_id=base_ref
                )
            except Exception:  # pragma: no cover - defensive: never break the fill
                return applied
            run.char_pr_id_ref = new_ref
            applied = True
    return applied


def _note_ledger(ledger: Any, cell: Any, part_name: str | None, result: FitResult) -> None:
    from hwpx.quality.ledger import DirtyLayoutRange

    try:
        row, col = cell.address
        cell_path = [(int(row), int(col))]
    except Exception:  # pragma: no cover - defensive
        cell_path = None
    reason = "style_changed" if result.style_changed else "form_filled"
    ledger.note(
        DirtyLayoutRange(
            part=part_name or "unknown",
            story_type="table_cell",
            cell_path=cell_path,
            reason=reason,  # type: ignore[arg-type]
            policy="story",
        )
    )


__all__ = ["fit_cell_text"]
