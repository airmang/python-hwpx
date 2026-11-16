# SPDX-License-Identifier: Apache-2.0
"""Paragraph diff of two documents (or paragraph sources).

The reference consistency lint (``inspect_reference_consistency``: 붙임·표·그림 번호
규칙) judges a document genre's conventions and moved to python-hwpx-automation in
7.0 (``hwpx_automation.office.compliance``).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping, Sequence

from hwpx.document import HwpxDocument

DOC_DIFF_REPORT_VERSION = "doc-diff-v1"


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


def _paragraphs_from_source(source: Any) -> list[str]:
    # The released diff API keeps its document-plan compatibility.
    if isinstance(source, Mapping) and "sections" in source and "paragraphs" not in source and "text" not in source:
        return _paragraphs_from_document_plan(source)
    return paragraph_texts(source)


def paragraph_texts(source: Any) -> list[str]:
    """Read paragraph texts from a document, path, text, sequence or mapping.

    Mappings support ``paragraphs`` (first priority) or ``text``. Application
    document plans are intentionally excluded: normalize them into a paragraph
    sequence before calling this format-neutral reader. :func:`doc_diff` keeps
    accepting its legacy plan input without warnings.
    """
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


__all__ = [
    "DOC_DIFF_REPORT_VERSION",
    "diff_paragraphs",
    "paragraph_texts",
    "doc_diff",
]


def __getattr__(name: str) -> object:
    """참조 일관성 검사(7.0에서 ``hwpx_automation.office.compliance``로 옮김)면 새 자리를 알려 준다."""

    from .._moved_modules import moved_name_error

    moved = moved_name_error(__name__, name)
    if moved is not None:
        raise moved
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
