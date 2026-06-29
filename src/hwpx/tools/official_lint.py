# SPDX-License-Identifier: Apache-2.0
"""Administrative-document style lint checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from hwpx.document import HwpxDocument

OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION = "official-document-style-v1"
_RULE_SOURCE_DOCUMENT = "hwpx-skill/references/official-document-rules.md"
_RULES_CHECKED = (
    "item-marker-hierarchy",
    "end-marker",
    "attachment-notation",
    "date-notation",
    "amount-notation",
    "colon-question-spacing",
)

_MARKER_PATTERNS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (re.compile(r"^\s*\d+\.\s+"), 0, "1."),
    (re.compile(r"^\s*[가-힣]\.\s+"), 1, "가."),
    (re.compile(r"^\s*\d+\)\s+"), 2, "1)"),
    (re.compile(r"^\s*[가-힣]\)\s+"), 3, "가)"),
    (re.compile(r"^\s*\(\d+\)\s+"), 4, "(1)"),
    (re.compile(r"^\s*\([가-힣]\)\s+"), 5, "(가)"),
)
_BAD_DELIMITED_DATE_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_DOT_DATE_RE = re.compile(r"\b(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?")
_AMOUNT_RE = re.compile(r"(?<![\d,])(\d{4,})(원)")
_ATTACHMENT_PREFIX_RE = re.compile(r"^\s*(붙임|첨부)\b")
_ATTACHMENT_RE = re.compile(r"^\s*(?:붙임|첨부)\s+(?:\d+\.\s*)?.+\s+\d+\s*부\.\s*$")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+[:?？]")


def inspect_official_document_style(
    source: Any, *, document_type: Any = None
) -> dict[str, Any]:
    """Inspect official-document conventions in text, plans, or HWPX files.

    When *document_type* resolves to a 공문 (official outgoing document) the
    structural spine — 두문(수신)·결문(발신명의·시행·공개구분)·끝. — is enforced at
    ERROR severity (the hard-gate, ``structure_pass``). Without *document_type*
    the behaviour is unchanged (backward compatible).
    """

    paragraphs = _paragraphs_from_source(source)
    is_gongmun = _is_gongmun(document_type)
    violations: list[dict[str, Any]] = []
    violations.extend(_inspect_marker_hierarchy(paragraphs))
    if not is_gongmun:
        # A 시행문 places its 결문(발신명의·시행) AFTER the 끝. marker, so the strict
        # "끝. must be the final paragraph" rule does not apply to 공문; the
        # structure gate enforces 끝. presence instead.
        violations.extend(_inspect_end_marker(paragraphs))
    violations.extend(_inspect_attachment_notation(paragraphs))
    violations.extend(_inspect_dates(paragraphs))
    violations.extend(_inspect_amounts(paragraphs))
    violations.extend(_inspect_spacing(paragraphs))
    if is_gongmun:
        violations.extend(_inspect_gongmun_structure(paragraphs))

    violation_count = len(violations)
    error_count = sum(1 for v in violations if v.get("severity") == "error")
    ok = violation_count == 0
    rules = list(_RULES_CHECKED) + (list(_GONGMUN_STRUCTURE_RULES) if is_gongmun else [])
    return {
        "report_version": OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION,
        "pass": ok,
        "structure_pass": error_count == 0,
        "document_type": str(document_type) if document_type else None,
        "score": max(0.0, round(1.0 - (violation_count / 10), 2)),
        "summary": {
            "paragraph_count": len(paragraphs),
            "violation_count": violation_count,
            "error_count": error_count,
            "rules_checked": rules,
        },
        "violations": violations,
        "repair_hints": [
            {
                "rule": violation["rule"],
                "paragraph_index": violation.get("paragraph_index"),
                "suggestion": violation["suggestion"],
            }
            for violation in violations
        ],
    }


_GONGMUN_DOCTYPES = {"공문", "공문서", "official_notice", "시행문"}
_GONGMUN_STRUCTURE_RULES = (
    "missing-susin",
    "missing-balsinmyeongui",
    "missing-sihaeng",
    "missing-disclosure",
    "missing-end-marker",
)
_ISSUER_SUFFIX_RE = re.compile(r"(장|관|감)$")
_DISCLOSURE_RE = re.compile(r"(부분공개|비공개|공개)")


def _is_gongmun(document_type: Any) -> bool:
    return bool(document_type) and str(document_type).strip() in _GONGMUN_DOCTYPES


def _norm_spaces(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _inspect_gongmun_structure(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    """ERROR-severity 공문 spine checks (the hard-gate), anchored by a real 시행문.

    Reliably machine-checkable from real 시행문: 수신(두문), 시행/공개구분(결문),
    끝.(본문 종결), and 발신명의 — detected via the literal label OR a 기관장 명의
    line (space-normalised, ending 장/관/감, not the 수신 recipient line).
    """

    nonempty = [t.strip() for t in paragraphs if t.strip()]
    norm = [_norm_spaces(t) for t in nonempty]
    full_norm = "".join(norm)
    violations: list[dict[str, Any]] = []

    def err(rule: str, message: str, suggestion: str) -> None:
        violations.append(
            _violation(
                rule=rule,
                paragraph_index=0,
                text="",
                message=message,
                suggestion=suggestion,
                severity="error",
            )
        )

    if "수신" not in full_norm:
        err("missing-susin", "공문 두문에 수신(수신자)이 없습니다",
            "두문에 '수신  <수신자>'를 추가하세요.")
    if "시행" not in full_norm:
        err("missing-sihaeng", "공문 결문에 시행 정보가 없습니다",
            "결문에 '시행  <처리과-일련번호> (<시행일자>)'를 추가하세요.")
    if not _DISCLOSURE_RE.search(full_norm):
        err("missing-disclosure", "공문 결문에 공개구분이 없습니다",
            "결문에 공개구분(공개/부분공개/비공개)을 추가하세요.")
    if "끝." not in full_norm:
        err("missing-end-marker", "공문 본문에 끝 표시(끝.)가 없습니다",
            "본문/붙임 마지막에 '끝.'을 두세요.")
    has_label = "발신명의" in full_norm
    has_issuer = any(
        _ISSUER_SUFFIX_RE.search(t) and len(t) >= 3 and "수신" not in t and not t.endswith(")")
        for t in norm
    )
    if not (has_label or has_issuer):
        err("missing-balsinmyeongui", "공문 결문에 발신명의(기관장 명의)가 없습니다",
            "결문에 발신명의(예: ○○교육지원청교육장)를 추가하세요.")
    return violations


def _document_paragraph_texts(paragraphs: Any) -> list[str]:
    """Flatten paragraph text including nested table-cell text.

    Real 시행문 carry the 두문(수신·경유) and 결문(발신명의·시행·공개구분) inside
    tables, which top-level ``document.paragraphs`` does not descend into.
    """

    texts: list[str] = []
    for paragraph in paragraphs:
        texts.append(paragraph.text)
        for table in getattr(paragraph, "tables", ()):
            for row in table.rows:
                for cell in row.cells:
                    texts.extend(_document_paragraph_texts(cell.paragraphs))
    return texts


def _paragraphs_from_source(source: Any) -> list[str]:
    if isinstance(source, HwpxDocument):
        return _document_paragraph_texts(source.paragraphs)
    if isinstance(source, Path):
        return _paragraphs_from_path(source)
    if isinstance(source, str):
        candidate = Path(source)
        if candidate.exists():
            return _paragraphs_from_path(candidate)
        return source.splitlines() or [source]
    if isinstance(source, Mapping):
        if "paragraphs" in source:
            return _paragraphs_from_sequence(source.get("paragraphs"))
        if "text" in source:
            return str(source.get("text") or "").splitlines()
        if "sections" in source:
            return _paragraphs_from_document_plan(source)
    if isinstance(source, Sequence) and not isinstance(source, (bytes, bytearray)):
        return _paragraphs_from_sequence(source)
    raise TypeError("source must be a HWPX path, HwpxDocument, mapping, text, or paragraph sequence")


def _paragraphs_from_path(path: Path) -> list[str]:
    document = HwpxDocument.open(path)
    try:
        return _document_paragraph_texts(document.paragraphs)
    finally:
        document.close()


def _paragraphs_from_sequence(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("paragraphs must be a sequence")
    paragraphs: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            paragraphs.append(str(item.get("text") or ""))
        else:
            paragraphs.append(str(item))
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
            if block_type in {"heading", "paragraph"}:
                text = str(block.get("text") or "").strip()
                if text:
                    paragraphs.append(text)
                for child in block.get("children") or ():
                    if isinstance(child, Mapping) and child.get("text"):
                        paragraphs.append(str(child.get("text") or ""))
            elif block_type in {"bullets", "bullet", "numbered_list", "numberedList"}:
                paragraphs.extend(str(item) for item in block.get("items") or ())
            elif block_type == "table":
                header = block.get("header") or ()
                rows = block.get("rows") or ()
                if header:
                    paragraphs.append(" ".join(str(item) for item in header))
                for row in rows:
                    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
                        paragraphs.append(" ".join(str(item) for item in row))
    return paragraphs


def _violation(
    *,
    rule: str,
    paragraph_index: int,
    text: str,
    message: str,
    suggestion: str,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": severity,
        "paragraph_index": paragraph_index,
        "text": text,
        "message": message,
        "suggestion": suggestion,
        "source": {
            "document": _RULE_SOURCE_DOCUMENT,
            "rule": rule,
        },
    }


def _marker_depth(text: str) -> tuple[int, str] | None:
    for pattern, depth, label in _MARKER_PATTERNS:
        if pattern.search(text):
            return depth, label
    return None


def _inspect_marker_hierarchy(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    previous_depth: int | None = None
    seen_depths: set[int] = set()
    for index, text in enumerate(paragraphs):
        marker = _marker_depth(text)
        if marker is None:
            continue
        depth, label = marker
        if previous_depth is not None and depth > previous_depth + 1:
            violations.append(
                _violation(
                    rule="item-marker-hierarchy",
                    paragraph_index=index,
                    text=text,
                    message=f"item marker {label!r} skips an intermediate hierarchy level",
                    suggestion="Use the order 1. -> 가. -> 1) -> 가) -> (1) -> (가) without skipping levels.",
                )
            )
        if depth > 0 and depth - 1 not in seen_depths:
            violations.append(
                _violation(
                    rule="item-marker-hierarchy",
                    paragraph_index=index,
                    text=text,
                    message=f"item marker {label!r} appears before its parent level",
                    suggestion="Introduce the parent item level before using this marker.",
                )
            )
        seen_depths.add(depth)
        previous_depth = depth
    return violations


def _inspect_end_marker(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    nonempty = [(index, text.rstrip()) for index, text in enumerate(paragraphs) if text.strip()]
    if not nonempty:
        return []
    violations: list[dict[str, Any]] = []
    attachment_indexes = [
        index
        for index, text in nonempty
        if _ATTACHMENT_PREFIX_RE.search(text)
    ]
    end_indexes = [
        index
        for index, text in nonempty
        if text.strip() == "끝." or text.rstrip().endswith("끝.")
    ]
    if not end_indexes:
        index, text = nonempty[-1]
        return [
            _violation(
                rule="end-marker",
                paragraph_index=index,
                text=text,
                message="official documents should close with an end marker",
                suggestion='Add "끝." at the required final position.',
                severity="error",
            )
        ]

    last_index, last_text = nonempty[-1]
    end_index = end_indexes[-1]
    end_text = paragraphs[end_index].rstrip()
    if end_index != last_index:
        violations.append(
            _violation(
                rule="end-marker",
                paragraph_index=end_index,
                text=end_text,
                message='the "끝." marker is not the final non-empty paragraph',
                suggestion='Move "끝." to the final non-empty paragraph.',
            )
        )
    if attachment_indexes:
        if end_text.strip() != "끝.":
            violations.append(
                _violation(
                    rule="end-marker",
                    paragraph_index=end_index,
                    text=end_text,
                    message='when attachments are listed, "끝." should be a standalone final paragraph',
                    suggestion='Place attachment lines first, then a standalone final "끝." paragraph.',
                )
            )
        if max(attachment_indexes) > end_index:
            violations.append(
                _violation(
                    rule="end-marker",
                    paragraph_index=end_index,
                    text=end_text,
                    message='the "끝." marker appears before the attachment notation',
                    suggestion='Place all attachment notation before the final "끝." paragraph.',
                )
            )
    elif end_text.strip() != "끝.":
        if not re.search(r"\s{2}끝\.$", end_text):
            violations.append(
                _violation(
                    rule="end-marker",
                    paragraph_index=end_index,
                    text=end_text,
                    message='inline "끝." should be preceded by two spaces',
                    suggestion='Use two spaces before the inline "끝." marker, for example "본문  끝.".',
                )
            )
    return violations


def _inspect_attachment_notation(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for index, text in enumerate(paragraphs):
        if not _ATTACHMENT_PREFIX_RE.search(text):
            continue
        if not _ATTACHMENT_RE.search(text.strip()):
            violations.append(
                _violation(
                    rule="attachment-notation",
                    paragraph_index=index,
                    text=text,
                    message="attachment notation should include item text, copy count, and a period",
                    suggestion='Use notation such as "붙임 1. 세부계획서 1부.".',
                )
            )
    return violations


def _inspect_dates(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for index, text in enumerate(paragraphs):
        for match in _BAD_DELIMITED_DATE_RE.finditer(text):
            replacement = _date_suggestion(match.group(1), match.group(2), match.group(3))
            violations.append(
                _violation(
                    rule="date-notation",
                    paragraph_index=index,
                    text=text,
                    message=f"date {match.group(0)!r} uses a non-official delimiter style",
                    suggestion=f"Use dotted Korean administrative notation: {replacement}",
                )
            )
        for match in _DOT_DATE_RE.finditer(text):
            replacement = _date_suggestion(match.group(1), match.group(2), match.group(3))
            if match.group(0) != replacement:
                violations.append(
                    _violation(
                        rule="date-notation",
                        paragraph_index=index,
                        text=text,
                        message=f"date {match.group(0)!r} should use spaces and no zero padding",
                        suggestion=f"Use {replacement}",
                    )
                )
    return violations


def _date_suggestion(year: str, month: str, day: str) -> str:
    return f"{int(year)}. {int(month)}. {int(day)}."


def _inspect_amounts(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for index, text in enumerate(paragraphs):
        for match in _AMOUNT_RE.finditer(text):
            formatted = f"{int(match.group(1)):,}원"
            violations.append(
                _violation(
                    rule="amount-notation",
                    paragraph_index=index,
                    text=text,
                    message=f"amount {match.group(0)!r} should use thousands separators",
                    suggestion=f"Use {formatted}.",
                )
            )
    return violations


def _inspect_spacing(paragraphs: Sequence[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for index, text in enumerate(paragraphs):
        if not _SPACE_BEFORE_PUNCTUATION_RE.search(text):
            continue
        violations.append(
            _violation(
                rule="colon-question-spacing",
                paragraph_index=index,
                text=text,
                message="do not insert a space before colons or question marks",
                suggestion="Remove the space before ':' or '?'.",
            )
        )
    return violations


__all__ = [
    "OFFICIAL_DOCUMENT_STYLE_REPORT_VERSION",
    "inspect_official_document_style",
]
