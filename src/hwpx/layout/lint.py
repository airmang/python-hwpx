# SPDX-License-Identifier: Apache-2.0
"""LayoutLint — renderer-less structural visual smoke (plan §2 Phase D).

Catches *likely* visual problems without a renderer so the **structural tier**
(no Hancom reachable) and fast pre-checks still have teeth. Four checks:

1. **stale lineseg cache** — ``lineseg/@textpos`` beyond the paragraph text length
   (already a ``package_validator`` hard error; surfaced here as a layout finding).
2. **dirty ↔ lineseg consistency** — when an edit ledger is supplied, a paragraph
   a ledger range marked dirty must have had its ``<hp:linesegarray>`` stripped;
   a retained cache is a leak (the exact class of bug the byte path once shipped).
3. **overflow risk** — an un-fitted cell value whose longest unbreakable token is
   grossly wider than the cell (reuses the Phase-C measurement). Gross + an
   ``overflow="fail"`` policy ⇒ a hard error; otherwise a warning.
4. **table structural sanity** — Hancom-required ``tbl``/``tc`` children present
   (reuses ``package_validator``).

Severity discipline (acceptance "stricter, never wronger"): only renderer-less
*provable* defects are errors. Heuristics warn. So the lint never contradicts the
Phase-A oracle — it may flag more, but it does not hard-fail a doc the oracle
would pass.
"""
from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from hwpx.opc.relationships import is_section_part_name
from hwpx.tools.package_validator import (
    _check_line_seg_text_positions,
    _check_table_editor_acceptance,
    _local_name,
)

from .report import LayoutFinding, LayoutLintReport

if TYPE_CHECKING:
    from hwpx.quality.ledger import DirtyLayoutLedger
    from hwpx.quality.report import FormReport

# Finding codes the lint actually emits. These line up with the plan's retry-able
# error codes (Appendix A) so the pipeline can surface them verbatim. (The plan's
# LAYOUT_MUTATION_WITHOUT_LEDGER lives in hwpx.quality.report; the lint realises a
# ledger/lineseg leak as STALE_LINESEG_DETECTED rather than a separate code.)
STALE_LINESEG_DETECTED = "STALE_LINESEG_DETECTED"
FIELD_OVERFLOW = "FIELD_OVERFLOW"
REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
TABLE_STRUCTURE_INVALID = "TABLE_STRUCTURE_INVALID"
OVERFLOW_RISK = "OVERFLOW_RISK"

# A token this many times wider than its cell cannot wrap into it in any renderer
# → a provable horizontal overflow worth a hard error (vs. a borderline guess).
_GROSS_OVERFLOW_FACTOR = 1.5
# ...but only if the absolute spill clears this floor (~3.5mm / a few em). Without
# it a short word in a tiny cell trips a hard fail on a sliver Hancom absorbs —
# the borderline case the measurement-honesty contract defers to the oracle.
_MIN_ABS_OVERFLOW = 2500.0  # HWPUNIT


def lint_layout(
    data: bytes,
    *,
    ledger: "DirtyLayoutLedger | None" = None,
    form: "FormReport | None" = None,
    document: Any | None = None,
    overflow_policy: str = "warn",
    check_overflow: bool = True,
    required_fields: "set[str] | None" = None,
) -> LayoutLintReport:
    """Run the renderer-less layout smoke over serialized HWPX *data*.

    *required_fields* (a set of field ids/names) lets the caller declare which
    native form fields must be filled; an empty one is a ``REQUIRED_FIELD_MISSING``
    error. Auto-detecting "required" awaits the Phase-F form schema, so this stays
    caller-driven and never false-positives on plain templates.
    """

    report = LayoutLintReport()
    section_roots = _section_roots(data)
    report.checked = [name for name, _ in section_roots]

    _lint_stale_cache(report, section_roots)
    _lint_table_structure(report, section_roots)
    if ledger is not None:
        _lint_dirty_lineseg(report, section_roots, ledger)

    if check_overflow or required_fields:
        _lint_with_document(report, data, document, overflow_policy, check_overflow, required_fields)

    return report


def _lint_with_document(
    report: LayoutLintReport,
    data: bytes,
    document: Any | None,
    overflow_policy: str,
    check_overflow: bool,
    required_fields: "set[str] | None",
) -> None:
    """Open the document once for the geometry-aware checks, guarded.

    The gate contract is *degrade, never crash* (cf. SavePipeline's reference
    stage): any unexpected error here is swallowed into a warning rather than
    propagating out of a save.
    """

    doc = document
    close_after = False
    try:
        if doc is None:
            from hwpx.document import HwpxDocument

            doc = HwpxDocument.open(data)
            close_after = True
        if check_overflow:
            _lint_overflow_risk(report, doc, overflow_policy)
        if required_fields:
            _lint_required_fields(report, doc, required_fields)
    except Exception as exc:  # pragma: no cover - defensive: never crash the gate
        report.add(
            LayoutFinding(
                code=OVERFLOW_RISK,
                message=f"layout overflow/field checks skipped: {type(exc).__name__}: {exc}",
                severity="warning",
            )
        )
    finally:
        if close_after and doc is not None:
            try:
                doc.close()
            except Exception:  # pragma: no cover - defensive
                pass


def _lint_required_fields(
    report: LayoutLintReport, doc: Any, required_fields: "set[str]"
) -> None:
    """Flag declared-required native form fields that are empty (plan §2 D)."""

    try:
        fields = doc.list_form_fields()
    except Exception:  # pragma: no cover - defensive
        return
    wanted = {str(f) for f in required_fields}
    for field in fields:
        ids = {str(field.get("field_id") or ""), str(field.get("name") or "")}
        if not (ids & wanted):
            continue
        if not str(field.get("current_value") or "").strip():
            label = field.get("name") or field.get("field_id")
            report.add(
                LayoutFinding(
                    code=REQUIRED_FIELD_MISSING,
                    message=f"required form field {label!r} is empty",
                    severity="error",
                    detail={"field": label},
                )
            )


# --------------------------------------------------------------------------- #
# Section parsing.
# --------------------------------------------------------------------------- #
def _section_roots(data: bytes) -> list[tuple[str, ET.Element]]:
    roots: list[tuple[str, ET.Element]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir() or not is_section_part_name(info.filename):
                    continue
                try:
                    roots.append((info.filename, ET.fromstring(archive.read(info.filename))))
                except ET.ParseError:
                    # Malformed XML is the pipeline's well-formedness floor, not ours.
                    continue
    except (zipfile.BadZipFile, OSError):
        return []
    return roots


# --------------------------------------------------------------------------- #
# 1 + 4: reuse the package_validator structural checks.
# --------------------------------------------------------------------------- #
def _lint_stale_cache(report: LayoutLintReport, roots: list[tuple[str, ET.Element]]) -> None:
    for part_name, root in roots:
        issues: list[Any] = []
        _check_line_seg_text_positions(issues, part_name, root)
        for issue in issues:
            report.add(
                LayoutFinding(
                    code=STALE_LINESEG_DETECTED,
                    message=issue.message,
                    severity="error" if issue.is_error else "warning",
                    part=part_name,
                )
            )


def _lint_table_structure(report: LayoutLintReport, roots: list[tuple[str, ET.Element]]) -> None:
    for part_name, root in roots:
        issues: list[Any] = []
        _check_table_editor_acceptance(issues, part_name, root)
        for issue in issues:
            report.add(
                LayoutFinding(
                    code=TABLE_STRUCTURE_INVALID,
                    message=issue.message,
                    severity="error" if issue.is_error else "warning",
                    part=part_name,
                )
            )


# --------------------------------------------------------------------------- #
# 2: dirty ↔ lineseg consistency (ledger-gated).
# --------------------------------------------------------------------------- #
def _lint_dirty_lineseg(
    report: LayoutLintReport,
    roots: list[tuple[str, ET.Element]],
    ledger: "DirtyLayoutLedger",
) -> None:
    by_part = {name: root for name, root in roots}
    for entry in ledger.ranges:
        root = by_part.get(entry.part)
        if root is None:
            continue  # part unknown / not a section → cannot locate precisely
        # start_paragraph is the paragraph's index in flat document order
        # (root.iter() over <hp:p>, cell subList paragraphs INCLUDED) — the same
        # numbering package_validator uses. Producers must use that convention.
        paragraphs = [el for el in root.iter() if _local_name(el) == "p"]
        start = entry.start_paragraph
        end = entry.end_paragraph if entry.end_paragraph is not None else start
        if start is None:
            continue  # cell-only entries carry no paragraph index to verify
        for index in range(start, end + 1):
            if 0 <= index < len(paragraphs):
                if _has_lineseg(paragraphs[index]):
                    report.add(
                        LayoutFinding(
                            code=STALE_LINESEG_DETECTED,
                            message=(
                                f"paragraph {index} is marked dirty ({entry.reason}) but "
                                "still carries a <hp:linesegarray> cache (strip leaked)"
                            ),
                            severity="error",
                            part=entry.part,
                            paragraph=index,
                        )
                    )


def _has_lineseg(paragraph: ET.Element) -> bool:
    return any(_local_name(child).lower() == "linesegarray" for child in paragraph)


# --------------------------------------------------------------------------- #
# 3: overflow risk (reuse the Phase-C measurement).
# --------------------------------------------------------------------------- #
# Vertical balloon: content needing this many × the cell's own line budget (and at
# least this many lines) is grossly over-tall — a warning, since Hancom grows the
# row rather than clipping (so it is not a hard, open-unsafe defect).
_BALLOON_FACTOR = 2.5
_BALLOON_MIN_LINES = 6
_LINE_SPACING = 1.6  # approx line advance as a multiple of the em


def _lint_overflow_risk(
    report: LayoutLintReport,
    doc: Any,
    overflow_policy: str,
) -> None:
    from hwpx.form_fit.measure import (
        _break_opportunities,
        estimate_lines,
        estimate_text_width,
        resolve_slot_metrics,
    )

    for _table, cell in _iter_cells(doc):
        try:
            text = (cell.text or "").strip()
            if not text:
                continue
            slot = resolve_slot_metrics(cell, doc, max_lines=1)
            if slot.available_width <= 0:
                continue
            addr = _safe_addr(cell)

            # (a) Horizontal: the longest *unbreakable* run (Hangul/wide and spaces
            # ARE break opportunities, so this is empty for normal Korean text) that
            # is wider than the slot will spill — it cannot wrap.
            longest = _longest_unbreakable_width(
                text, slot.font_pt, _break_opportunities, estimate_text_width
            )
            if longest > slot.available_width:
                ratio = longest / slot.available_width
                over_abs = longest - slot.available_width
                gross = ratio >= _GROSS_OVERFLOW_FACTOR and over_abs >= _MIN_ABS_OVERFLOW
                severity = "error" if (gross and overflow_policy == "fail") else "warning"
                report.add(
                    LayoutFinding(
                        code=FIELD_OVERFLOW if severity == "error" else OVERFLOW_RISK,
                        message=(
                            f"cell {addr} has an unbreakable run ~{ratio:.1f}× wider than "
                            f"the slot ({text[:24]!r}…); it will overflow horizontally"
                        ),
                        severity=severity,
                        detail={"ratio": round(ratio, 3), "addr": addr, "kind": "horizontal"},
                    )
                )

            # (b) Vertical balloon: content needs far more lines than the cell's own
            # height budgets for — the row will balloon (the headline FormFit defect).
            lines = estimate_lines(text, slot.available_width, slot.font_pt)
            budget = _cell_line_budget(cell, slot.font_pt)
            if budget and lines >= _BALLOON_MIN_LINES and lines >= budget * _BALLOON_FACTOR:
                report.add(
                    LayoutFinding(
                        code=OVERFLOW_RISK,
                        message=(
                            f"cell {addr} content needs ~{lines} lines but the cell budgets "
                            f"~{budget}; the row will balloon ({text[:24]!r}…)"
                        ),
                        severity="warning",
                        detail={"lines": lines, "budget": budget, "addr": addr, "kind": "vertical"},
                    )
                )
        except Exception:  # pragma: no cover - defensive: one bad cell never breaks the scan
            continue


def _longest_unbreakable_width(text, font_pt, break_fn, width_fn) -> float:
    boundaries = sorted(set(break_fn(text)) | {0, len(text)})
    widest = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        widest = max(widest, width_fn(text[start:end], font_pt))
    return widest


def _cell_line_budget(cell: Any, font_pt: float) -> int | None:
    height = float(getattr(cell, "height", 0) or 0)
    if height <= 0:
        return None
    line_height = font_pt * 100.0 * _LINE_SPACING
    if line_height <= 0:
        return None
    return max(int(height // line_height), 1)


def _safe_addr(cell: Any):
    try:
        return list(cell.address)
    except Exception:  # pragma: no cover - defensive
        return None


def _iter_cells(doc: Any):
    for section in getattr(doc, "sections", []):
        for paragraph in getattr(section, "paragraphs", []):
            for table in getattr(paragraph, "tables", []):
                try:
                    grid = list(table.iter_grid())
                except Exception:  # pragma: no cover - defensive
                    continue
                seen: set[int] = set()
                for entry in grid:
                    marker = id(entry.cell.element)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    yield table, entry.cell


__all__ = [
    "lint_layout",
    "STALE_LINESEG_DETECTED",
    "FIELD_OVERFLOW",
    "REQUIRED_FIELD_MISSING",
    "TABLE_STRUCTURE_INVALID",
    "OVERFLOW_RISK",
]
