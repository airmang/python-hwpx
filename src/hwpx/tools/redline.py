# SPDX-License-Identifier: Apache-2.0
"""Redline authoring verification helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from os import PathLike, fspath
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.oxml.body import TrackChangeMark
from hwpx.visual.oracle import RenderBackend, resolve_oracle, visual_check

REDLINE_VERIFY_REPORT_VERSION = "redline-verify-v1"
_DEMO_DATE = "2026-06-30T00:00:00Z"


def verify_redline(
    before_hwpx: str | PathLike[str],
    after_hwpx: str | PathLike[str],
    *,
    oracle: RenderBackend | None = None,
) -> dict[str, Any]:
    """Verify authored redline structure and fold in the VisualComplete report."""

    warnings: list[str] = []
    document: HwpxDocument | None = None
    structural_opens_clean = False
    try:
        document = HwpxDocument.open(after_hwpx)
        structural_opens_clean = True
    except Exception as exc:
        warnings.append(f"after document did not reopen structurally: {exc}")

    change_count = 0
    changes_by_type: dict[str, int] = {}
    marks_linked = False
    display_enabled = False

    if document is not None:
        changes = document.track_changes
        changes_by_id = {
            int(change.id): change
            for change in changes.values()
            if change.id is not None
        }
        change_count = len(changes_by_id)
        type_counter = Counter(_normalise_change_type(change.change_type) for change in changes_by_id.values())
        changes_by_type = dict(sorted(type_counter.items()))

        if not changes_by_id:
            warnings.append("after document has no header trackChanges entries")

        body_marks = _collect_track_change_marks(document)
        marks_linked = _marks_are_linked(body_marks, changes_by_id)
        if not body_marks:
            warnings.append("after document has no body insert/delete track-change marks")
        elif not marks_linked:
            warnings.append("body track-change marks are not fully linked to header trackChanges by TcId")

        display_enabled = _track_change_display_enabled(document)
        if not display_enabled:
            warnings.append("trackChangeConfig display flag is not enabled")

    backend = oracle if oracle is not None else resolve_oracle()
    visual_report = visual_check(
        fspath(before_hwpx),
        fspath(after_hwpx),
        oracle=backend,
    )
    warnings.extend(visual_report.warnings)
    warnings.extend(f"visual error: {error}" for error in visual_report.errors)
    warnings.extend(_visual_signal_warnings(visual_report))

    render_checked = bool(visual_report.render_checked)
    opens_clean: bool | None
    if render_checked:
        opens_clean = True
    elif visual_report.errors:
        opens_clean = False
    else:
        opens_clean = None

    return {
        "report_version": REDLINE_VERIFY_REPORT_VERSION,
        "changeCount": change_count,
        "changesByType": changes_by_type,
        "marksLinked": marks_linked,
        "displayEnabled": display_enabled,
        "opensClean": opens_clean if structural_opens_clean else False,
        "render_checked": render_checked,
        "visual_ok": visual_report.ok if render_checked else None,
        "warnings": warnings,
    }


def author_demo_redline(doc: HwpxDocument) -> HwpxDocument:
    """Apply one tracked insert and one tracked delete to *doc*."""

    paragraph = doc.add_paragraph("redline delete target", char_pr_id_ref="0")
    doc.add_tracked_insert(paragraph, " inserted", date=_DEMO_DATE)
    doc.add_tracked_delete(paragraph, match="delete", date=_DEMO_DATE)
    return doc


def _normalise_change_type(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    lowered = text.lower()
    aliases = {
        "insert": "Insert",
        "delete": "Delete",
        "charshape": "CharShape",
        "parashape": "ParaShape",
    }
    return aliases.get(lowered, text[:1].upper() + text[1:].lower())


def _collect_track_change_marks(document: HwpxDocument) -> list[TrackChangeMark]:
    marks: list[TrackChangeMark] = []
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            model = run.to_model()
            for span in model.text_spans:
                for markup in span.marks:
                    if isinstance(markup.element, TrackChangeMark):
                        marks.append(markup.element)
    return marks


def _marks_are_linked(
    marks: list[TrackChangeMark],
    changes_by_id: dict[int, Any],
) -> bool:
    if not marks or not changes_by_id:
        return False

    mark_names_by_change: dict[int, set[str]] = defaultdict(set)
    for mark in marks:
        if mark.tc_id is None or mark.tc_id not in changes_by_id:
            return False
        mark_type = _normalise_change_type(mark.change_type)
        change_type = _normalise_change_type(changes_by_id[mark.tc_id].change_type)
        if mark_type != change_type:
            return False
        mark_names_by_change[mark.tc_id].add(mark.name)

    for change_id, change in changes_by_id.items():
        change_type = _normalise_change_type(change.change_type)
        if change_type not in {"Insert", "Delete"}:
            continue
        names = mark_names_by_change.get(change_id, set())
        if f"{change_type.lower()}Begin" not in names or f"{change_type.lower()}End" not in names:
            return False
    return True


def _track_change_display_enabled(document: HwpxDocument) -> bool:
    for header in document.headers:
        config = header.to_model().track_change_config
        if config is not None and config.flags is not None and config.flags & 1:
            return True
    return False


def _visual_signal_warnings(report: Any) -> list[str]:
    warnings: list[str] = []
    if report.unexpected_diff_outside_mask:
        warnings.append("visual signal: unexpected_diff_outside_mask")
    if report.overlap_detected:
        warnings.append("visual signal: overlap_detected")
    if report.overflow_detected:
        warnings.append("visual signal: overflow_detected")
    if report.table_break_detected:
        warnings.append("visual signal: table_break_detected")
    if report.page_count_changed:
        warnings.append("visual signal: page_count_changed")
    return warnings


__all__ = [
    "REDLINE_VERIFY_REPORT_VERSION",
    "author_demo_redline",
    "verify_redline",
]
