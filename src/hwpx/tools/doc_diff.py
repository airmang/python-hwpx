# SPDX-License-Identifier: Apache-2.0
"""Paragraph diff and semantic reference lint helpers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

from hwpx.document import HwpxDocument

DOC_DIFF_REPORT_VERSION = "doc-diff-v1"
REFERENCE_CONSISTENCY_REPORT_VERSION = "reference-consistency-v1"

_ATTACHMENT_LINE_RE = re.compile(r"^\s*(?:붙임|첨부)\s*(\d+)?[.)]?\s+.+\s+\d+\s*부\.?\s*$")
_ATTACHMENT_REFERENCE_RE = re.compile(r"(?:붙임|첨부)\s*(\d+)\s*(?:참조|관련|확인|의)?")
_TABLE_NUMBER_RE = re.compile(r"(?:표|Table)\s*(\d+)", re.IGNORECASE)
_FIGURE_NUMBER_RE = re.compile(r"(?:그림|Figure|Fig\.)\s*(\d+)", re.IGNORECASE)


def diff_paragraphs(
    old_paragraphs: Sequence[str],
    new_paragraphs: Sequence[str],
) -> list[dict[str, Any]]:
    """Return LCS-aligned paragraph changes."""

    old = [str(item) for item in old_paragraphs]
    new = [str(item) for item in new_paragraphs]
    matcher = SequenceMatcher(a=old, b=new, autojunk=False)
    changes: list[dict[str, Any]] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(old_end - old_start):
                changes.append(
                    _change(
                        "equal",
                        old_index=old_start + offset,
                        new_index=new_start + offset,
                        old_text=old[old_start + offset],
                        new_text=new[new_start + offset],
                    )
                )
            continue
        if tag == "delete":
            for index in range(old_start, old_end):
                changes.append(
                    _change("removed", old_index=index, new_index=None, old_text=old[index], new_text="")
                )
            continue
        if tag == "insert":
            for index in range(new_start, new_end):
                changes.append(
                    _change("added", old_index=None, new_index=index, old_text="", new_text=new[index])
                )
            continue
        old_slice = old[old_start:old_end]
        new_slice = new[new_start:new_end]
        paired = min(len(old_slice), len(new_slice))
        for offset in range(paired):
            changes.append(
                _change(
                    "changed",
                    old_index=old_start + offset,
                    new_index=new_start + offset,
                    old_text=old_slice[offset],
                    new_text=new_slice[offset],
                )
            )
        for offset in range(paired, len(old_slice)):
            changes.append(
                _change(
                    "removed",
                    old_index=old_start + offset,
                    new_index=None,
                    old_text=old_slice[offset],
                    new_text="",
                )
            )
        for offset in range(paired, len(new_slice)):
            changes.append(
                _change(
                    "added",
                    old_index=None,
                    new_index=new_start + offset,
                    old_text="",
                    new_text=new_slice[offset],
                )
            )
    return changes


def doc_diff(old_source: Any, new_source: Any) -> dict[str, Any]:
    """Return a paragraph diff report for two documents or paragraph sources."""

    old_paragraphs = _paragraphs_from_source(old_source)
    new_paragraphs = _paragraphs_from_source(new_source)
    changes = diff_paragraphs(old_paragraphs, new_paragraphs)
    counts: dict[str, int] = {"equal": 0, "added": 0, "removed": 0, "changed": 0}
    for change in changes:
        counts[change["tag"]] += 1
    return {
        "report_version": DOC_DIFF_REPORT_VERSION,
        "summary": {
            "old_paragraph_count": len(old_paragraphs),
            "new_paragraph_count": len(new_paragraphs),
            "change_count": len(changes),
            "counts": counts,
        },
        "changes": changes,
    }


def build_comparison_table_plan(
    old_source: Any,
    new_source: Any,
    *,
    title: str = "신구대조표",
    include_equal: bool = True,
) -> dict[str, Any]:
    """Return a plan-v2 document containing an old/new comparison table."""

    report = doc_diff(old_source, new_source)
    rows = [
        [_change_label(change["tag"]), change.get("old_text") or "", change.get("new_text") or ""]
        for change in report["changes"]
        if include_equal or change["tag"] != "equal"
    ]
    if not rows:
        rows = [["동일", "", ""]]
    return {
        "schemaVersion": "hwpx.document_plan.v2",
        "preset": "government_report",
        "title": title,
        "sections": [
            {
                "blocks": [
                    {"type": "heading", "level": 1, "text": title},
                    {
                        "type": "table",
                        "header": ["구분", "구", "신"],
                        "rows": rows,
                        "columnWidths": [1, 4, 4],
                        "headerShading": "EAF1FB",
                    },
                ]
            }
        ],
    }


def inspect_reference_consistency(source: Any) -> dict[str, Any]:
    """Inspect attachment/table/figure semantic references in document text."""

    paragraphs = _paragraphs_from_source(source)
    violations: list[dict[str, Any]] = []
    attachment_numbers = _attachment_numbers(paragraphs)
    for index, text in enumerate(paragraphs):
        for match in _ATTACHMENT_REFERENCE_RE.finditer(text):
            number = int(match.group(1))
            if number not in attachment_numbers:
                violations.append(
                    _violation(
                        "attachment-reference",
                        index,
                        text,
                        f"attachment reference {number} has no matching attachment line",
                        f'Add "붙임 {number}. ..." or update the reference.',
                    )
                )
    violations.extend(_numbering_violations(paragraphs, kind="table", pattern=_TABLE_NUMBER_RE, label="표"))
    violations.extend(_numbering_violations(paragraphs, kind="figure", pattern=_FIGURE_NUMBER_RE, label="그림"))
    return {
        "report_version": REFERENCE_CONSISTENCY_REPORT_VERSION,
        "pass": not violations,
        "summary": {
            "paragraph_count": len(paragraphs),
            "violation_count": len(violations),
            "attachment_numbers": sorted(attachment_numbers),
        },
        "violations": violations,
        "repair_hints": [
            {
                "rule": violation["rule"],
                "paragraph_index": violation["paragraph_index"],
                "suggestion": violation["suggestion"],
            }
            for violation in violations
        ],
    }


def _change(
    tag: str,
    *,
    old_index: int | None,
    new_index: int | None,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    return {
        "tag": tag,
        "old_index": old_index,
        "new_index": new_index,
        "old_text": old_text,
        "new_text": new_text,
    }


def _change_label(tag: str) -> str:
    return {
        "equal": "동일",
        "added": "추가",
        "removed": "삭제",
        "changed": "변경",
    }.get(tag, tag)


def _paragraphs_from_source(source: Any) -> list[str]:
    if isinstance(source, HwpxDocument):
        return [paragraph.text for paragraph in source.paragraphs if paragraph.text.strip()]
    if isinstance(source, Path):
        return _paragraphs_from_path(source)
    if isinstance(source, str):
        candidate = Path(source)
        if candidate.exists():
            return _paragraphs_from_path(candidate)
        return [line for line in source.splitlines() if line.strip()]
    if isinstance(source, Mapping):
        if "paragraphs" in source:
            return _paragraphs_from_sequence(source.get("paragraphs"))
        if "text" in source:
            return [line for line in str(source.get("text") or "").splitlines() if line.strip()]
        if "sections" in source:
            return _paragraphs_from_document_plan(source)
    if isinstance(source, Sequence) and not isinstance(source, (bytes, bytearray)):
        return _paragraphs_from_sequence(source)
    raise TypeError("source must be a HWPX path, HwpxDocument, mapping, text, or paragraph sequence")


def _paragraphs_from_path(path: Path) -> list[str]:
    document = HwpxDocument.open(path)
    try:
        return [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    finally:
        document.close()


def _paragraphs_from_sequence(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("paragraphs must be a sequence")
    paragraphs: list[str] = []
    for item in value:
        text = str(item.get("text") if isinstance(item, Mapping) else item).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _paragraphs_from_document_plan(plan: Mapping[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    for section in plan.get("sections") or ():
        if not isinstance(section, Mapping):
            continue
        for block in section.get("blocks", section.get("children")) or ():
            if not isinstance(block, Mapping):
                continue
            block_type = str(block.get("type") or "").strip()
            if block_type in {"heading", "paragraph"} and str(block.get("text") or "").strip():
                paragraphs.append(str(block.get("text") or "").strip())
            elif block_type == "table":
                for row in block.get("rows") or ():
                    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
                        text = " ".join(str(cell).strip() for cell in row if str(cell).strip())
                        if text:
                            paragraphs.append(text)
    return paragraphs


def _attachment_numbers(paragraphs: Sequence[str]) -> set[int]:
    numbers: set[int] = set()
    implicit = 1
    for text in paragraphs:
        match = _ATTACHMENT_LINE_RE.search(text)
        if not match:
            continue
        if match.group(1):
            numbers.add(int(match.group(1)))
        else:
            numbers.add(implicit)
        implicit += 1
    return numbers


def _numbering_violations(
    paragraphs: Sequence[str],
    *,
    kind: str,
    pattern: re.Pattern[str],
    label: str,
) -> list[dict[str, Any]]:
    occurrences: list[tuple[int, int, str]] = []
    for index, text in enumerate(paragraphs):
        for match in pattern.finditer(text):
            occurrences.append((int(match.group(1)), index, text))
    if not occurrences:
        return []
    numbers = {number for number, _, _ in occurrences}
    missing = [number for number in range(1, max(numbers) + 1) if number not in numbers]
    if not missing:
        return []
    first_index = occurrences[0][1]
    first_text = occurrences[0][2]
    return [
        _violation(
            f"{kind}-numbering",
            first_index,
            first_text,
            f"{label} numbering is not continuous; missing {missing}",
            f"Renumber {label} references/captions so numbers are continuous from 1.",
        )
    ]


def _violation(
    rule: str,
    paragraph_index: int,
    text: str,
    message: str,
    suggestion: str,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": "warning",
        "paragraph_index": paragraph_index,
        "text": text,
        "message": message,
        "suggestion": suggestion,
    }


__all__ = [
    "DOC_DIFF_REPORT_VERSION",
    "REFERENCE_CONSISTENCY_REPORT_VERSION",
    "build_comparison_table_plan",
    "diff_paragraphs",
    "doc_diff",
    "inspect_reference_consistency",
]
