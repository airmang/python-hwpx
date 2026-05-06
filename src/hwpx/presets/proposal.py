# SPDX-License-Identifier: Apache-2.0
"""Agent-first proposal document preset for HWPX generation.

The preset deliberately uses only public ``HwpxDocument`` APIs.  It gives agents
semantic building blocks (proposal title, metadata, sections, budget tables,
callouts) without requiring direct XML manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
import zipfile

from ..document import HwpxDocument

DEFAULT_PROPOSAL_SECTIONS = (
    "추진 배경 및 문제 정의",
    "제안 내용",
    "구축 및 운영 계획",
    "예산 및 자원 계획",
    "기대 효과",
)

_REQUIRED_SECTIONS = (
    "title",
    "metadata",
    "executive_summary",
    "background",
    "proposal",
    "implementation_plan",
    "budget",
    "expected_outcomes",
    "closing",
)

_EMPTY_ASSET_INFO = {"image_count": 0, "image_bytes": 0, "package_bytes": 0}


@dataclass(slots=True)
class ProposalSection:
    """A semantic section in a proposal document."""

    title: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProposalSpec:
    """Structured intent for a Korean proposal/planning HWPX document."""

    title: str
    subtitle: str = ""
    organization: str = ""
    author: str = ""
    date: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    executive_summary: str = ""
    sections: list[ProposalSection] = field(default_factory=list)
    budget_items: list[dict[str, str]] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    closing: str = ""


@dataclass(frozen=True, slots=True)
class ProposalStylePreset:
    """Semantic style-token preset backed by public run-style helpers."""

    name: str = "clean_korean_proposal"
    title_bold: bool = True
    subtitle_italic: bool = True
    heading_bold: bool = True
    heading_underline: bool = True
    table_header_bold: bool = True
    callout_bold: bool = True

    def ensure_tokens(self, document: HwpxDocument) -> dict[str, str]:
        """Create/reuse public char styles and return semantic token IDs."""

        return {
            "title": document.ensure_run_style(bold=self.title_bold),
            "subtitle": document.ensure_run_style(italic=self.subtitle_italic),
            "heading": document.ensure_run_style(bold=self.heading_bold),
            "section_heading": document.ensure_run_style(
                bold=self.heading_bold,
                underline=self.heading_underline,
            ),
            "body": document.ensure_run_style(),
            "table_header": document.ensure_run_style(bold=self.table_header_bold),
            "table_cell": document.ensure_run_style(),
            "callout": document.ensure_run_style(bold=self.callout_bold),
        }


def normalize_proposal_spec(spec: ProposalSpec | Mapping[str, Any]) -> ProposalSpec:
    """Return a :class:`ProposalSpec` from dataclass or dict-like input."""

    if isinstance(spec, ProposalSpec):
        return spec
    if not isinstance(spec, Mapping):
        raise TypeError("proposal spec must be a ProposalSpec or mapping")
    title = str(spec.get("title") or "").strip()
    if not title:
        raise ValueError("proposal spec requires a non-empty title")

    sections: list[ProposalSection] = []
    for raw in spec.get("sections") or []:
        if isinstance(raw, ProposalSection):
            sections.append(raw)
            continue
        if not isinstance(raw, Mapping):
            raise TypeError("sections must contain mappings or ProposalSection objects")
        section_title = str(raw.get("title") or "").strip()
        if not section_title:
            raise ValueError("each section requires a title")
        paragraphs = _string_list(raw.get("paragraphs") or raw.get("body") or [])
        bullets = _string_list(raw.get("bullets") or [])
        sections.append(ProposalSection(section_title, paragraphs=paragraphs, bullets=bullets))

    if not sections:
        sections = [ProposalSection(title=name) for name in DEFAULT_PROPOSAL_SECTIONS]

    metadata = {str(k): str(v) for k, v in dict(spec.get("metadata") or {}).items()}
    budget_items = [
        {str(k): str(v) for k, v in dict(item).items()}
        for item in spec.get("budget_items") or []
        if isinstance(item, Mapping)
    ]

    return ProposalSpec(
        title=title,
        subtitle=str(spec.get("subtitle") or ""),
        organization=str(spec.get("organization") or ""),
        author=str(spec.get("author") or ""),
        date=str(spec.get("date") or ""),
        metadata=metadata,
        executive_summary=str(spec.get("executive_summary") or ""),
        sections=sections,
        budget_items=budget_items,
        expected_outcomes=_string_list(spec.get("expected_outcomes") or []),
        closing=str(spec.get("closing") or ""),
    )


def create_proposal_document(
    spec: ProposalSpec | Mapping[str, Any],
    *,
    preset: ProposalStylePreset | str | None = None,
) -> HwpxDocument:
    """Create a polished proposal HWPX document from structured intent.

    The returned document is unsaved so callers can choose the output path.
    """

    normalized = normalize_proposal_spec(spec)
    style_preset = (
        preset
        if isinstance(preset, ProposalStylePreset)
        else ProposalStylePreset(name=str(preset or "clean_korean_proposal"))
    )
    document = HwpxDocument.new()
    tokens = style_preset.ensure_tokens(document)

    _add_paragraph(document, normalized.title, tokens["title"])
    if normalized.subtitle:
        _add_paragraph(document, normalized.subtitle, tokens["subtitle"])
    _add_paragraph(document, "", tokens["body"])

    metadata = _metadata_rows(normalized)
    if metadata:
        _add_key_value_table(document, metadata, tokens)

    summary = normalized.executive_summary.strip()
    if summary:
        _add_paragraph(document, "핵심 요약", tokens["heading"])
        _add_paragraph(document, summary, tokens["callout"])

    for idx, section in enumerate(normalized.sections, start=1):
        _add_paragraph(document, f"{idx}. {section.title}", tokens["section_heading"])
        for paragraph in section.paragraphs:
            _add_paragraph(document, paragraph, tokens["body"])
        for bullet in section.bullets:
            _add_paragraph(document, f"• {bullet}", tokens["body"])

    if normalized.budget_items:
        _add_paragraph(document, "예산 및 자원 계획", tokens["heading"])
        _add_budget_table(document, normalized.budget_items, tokens)

    if normalized.expected_outcomes:
        _add_paragraph(document, "기대 효과", tokens["heading"])
        for outcome in normalized.expected_outcomes:
            _add_paragraph(document, f"• {outcome}", tokens["body"])

    if normalized.closing:
        _add_paragraph(document, "마무리", tokens["heading"])
        _add_paragraph(document, normalized.closing, tokens["body"])

    return document


def inspect_proposal_quality(source: str | Path | HwpxDocument) -> dict[str, Any]:
    """Return a deterministic proposal-quality report for generated HWPX."""

    path: Path | None = None
    close_doc = False
    if isinstance(source, HwpxDocument):
        document = source
    else:
        path = Path(source)
        document = HwpxDocument.open(path)
        close_doc = True

    try:
        texts = [(paragraph.text or "").strip() for paragraph in document.paragraphs]
        non_empty = [text for text in texts if text]
        joined = "\n".join(non_empty)
        tables = _safe_table_count(document)
        validation = document.validate()
        asset_info = (
            _asset_info(path)
            if path is not None and path.exists()
            else dict(_EMPTY_ASSET_INFO)
        )

        required = {
            "title": bool(non_empty),
            "metadata": tables >= 1,
            "executive_summary": _contains_any(joined, ["핵심 요약", "요약"]),
            "background": _contains_any(joined, ["배경", "문제"]),
            "proposal": _contains_any(joined, ["제안", "내용"]),
            "implementation_plan": _contains_any(joined, ["운영 계획", "구축", "추진"]),
            "budget": _contains_any(joined, ["예산", "자원"]),
            "expected_outcomes": _contains_any(joined, ["기대 효과", "성과"]),
            "closing": _contains_any(joined, ["마무리", "제출", "서명"]),
        }
        scores = _score_rubric(
            required,
            tables=tables,
            validation_ok=validation.ok,
            asset_info=asset_info,
        )
        style_usage = _style_token_usage(document)
        sample_match = _sample_match_report(
            required,
            tables=tables,
            validation_ok=validation.ok,
            asset_info=asset_info,
            style_usage=style_usage,
        )
        average = round(sum(scores.values()) / len(scores), 2)
        passed = (
            average >= 4.0
            and min(scores.values()) >= 3.0
            and sample_match["average"] >= 4.0
            and validation.ok
            and all(required.values())
        )
        return {
            "report_version": "proposal-quality-v2",
            "generated_file": str(path) if path is not None else None,
            "validation": {"ok": validation.ok, "critical_errors": 0 if validation.ok else len(validation.issues)},
            "outline": {"required_sections_present": all(required.values()), "required_sections": required},
            "style_token_usage": style_usage,
            "table_checks": {"table_count": tables, "has_metadata_table": tables >= 1, "has_budget_table": tables >= 2},
            "asset_checks": asset_info,
            "sample_match": sample_match,
            "rubric_scores": scores,
            "rubric_average": average,
            "pass": passed,
            "visual_review_required": True,
            "visual_review_limitations": [
                "No renderer/pixel-diff gate was used in this phase.",
                "Sample matching is based on deterministic package/XML/text proxies only.",
            ],
            "gaps": _quality_gaps(required, scores, validation.ok, sample_match=sample_match),
        }
    finally:
        if close_doc:
            document.close()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


def _add_paragraph(document: HwpxDocument, text: str, char_pr_id_ref: str) -> None:
    document.add_paragraph(text, char_pr_id_ref=char_pr_id_ref, inherit_style=False)


def _metadata_rows(spec: ProposalSpec) -> list[tuple[str, str]]:
    rows = []
    for label, value in (
        ("기관", spec.organization),
        ("작성자", spec.author),
        ("작성일", spec.date),
    ):
        if value:
            rows.append((label, value))
    rows.extend((key, value) for key, value in spec.metadata.items() if value)
    return rows


def _add_key_value_table(document: HwpxDocument, rows: list[tuple[str, str]], tokens: Mapping[str, str]) -> None:
    table = document.add_table(len(rows) + 1, 2, char_pr_id_ref=tokens["table_cell"])
    table.set_cell_text(0, 0, "항목")
    table.set_cell_text(0, 1, "내용")
    _bold_table_row(table, 0)
    for row_index, (key, value) in enumerate(rows, start=1):
        table.set_cell_text(row_index, 0, key)
        table.set_cell_text(row_index, 1, value)


def _add_budget_table(document: HwpxDocument, items: list[dict[str, str]], tokens: Mapping[str, str]) -> None:
    headers = ["항목", "금액", "비고"]
    table = document.add_table(len(items) + 1, len(headers), char_pr_id_ref=tokens["table_cell"])
    for col, header in enumerate(headers):
        table.set_cell_text(0, col, header)
    _bold_table_row(table, 0)
    for row_index, item in enumerate(items, start=1):
        table.set_cell_text(row_index, 0, item.get("item") or item.get("name") or "")
        table.set_cell_text(row_index, 1, item.get("amount") or item.get("cost") or "")
        table.set_cell_text(row_index, 2, item.get("note") or item.get("description") or "")


def _bold_table_row(table: Any, row_index: int) -> None:
    try:
        row = table.rows[row_index]
    except (AttributeError, IndexError):
        return
    for cell in getattr(row, "cells", []):
        for paragraph in getattr(cell, "paragraphs", []):
            for run in paragraph.runs:
                run.bold = True


def _safe_table_count(document: HwpxDocument) -> int:
    table_tag = "{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl"
    count = 0
    for section in getattr(document, "sections", []):
        section_element = getattr(section, "element", None)
        if section_element is None or not hasattr(section_element, "iter"):
            continue
        count += sum(1 for _ in section_element.iter(table_tag))
    return count


def _asset_info(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return dict(_EMPTY_ASSET_INFO)
    image_count = 0
    image_bytes = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.filename.startswith("BinData/"):
                image_count += 1
                image_bytes += int(info.file_size)
    return {
        "image_count": image_count,
        "image_bytes": image_bytes,
        "package_bytes": path.stat().st_size,
    }


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


def _score_rubric(
    required: Mapping[str, bool],
    *,
    tables: int,
    validation_ok: bool,
    asset_info: Mapping[str, int],
) -> dict[str, float]:
    structure = (
        5.0
        if all(required.values())
        else max(2.0, 5.0 * sum(required.values()) / len(required))
    )
    asset_bytes = int(asset_info.get("image_bytes", 0))
    package_bytes = int(asset_info.get("package_bytes", 0))
    return {
        "structure": round(structure, 2),
        "visual_hierarchy": 4.0 if required.get("title") and required.get("executive_summary") else 3.0,
        "style_consistency": 4.0,
        "table_readability": 5.0 if tables >= 2 else (4.0 if tables == 1 else 2.0),
        "asset_weight": 5.0 if package_bytes < 5_000_000 and asset_bytes < 1_000_000 else 3.0,
        "validation_cleanliness": 5.0 if validation_ok else 2.0,
        "agent_reproducibility": 4.0,
    }


def _style_token_usage(document: HwpxDocument) -> dict[str, Any]:
    expected = [
        "title",
        "subtitle",
        "heading",
        "section_heading",
        "body",
        "table_header",
        "table_cell",
        "callout",
    ]
    used_ids: set[str] = set()
    for run in document.iter_runs():
        style_id = run.element.get("charPrIDRef")
        if style_id:
            used_ids.add(str(style_id))
    return {
        "semantic_tokens_expected": expected,
        "semantic_tokens_expected_count": len(expected),
        "unique_run_style_ids": sorted(used_ids),
        "unique_run_style_count": len(used_ids),
        "style_count_available": len(document.char_properties),
        "sample_anchor": {
            "good_samples_style_count_range": [30, 46],
            "bad_sample_style_count": 27,
            "interpretation": "use reusable semantic tokens; do not inflate one-off styles",
        },
    }


def _sample_match_report(
    required: Mapping[str, bool],
    *,
    tables: int,
    validation_ok: bool,
    asset_info: Mapping[str, int],
    style_usage: Mapping[str, Any],
) -> dict[str, Any]:
    package_bytes = int(asset_info.get("package_bytes", 0))
    image_bytes = int(asset_info.get("image_bytes", 0))
    image_ratio = round(image_bytes / package_bytes, 4) if package_bytes else 0.0
    unique_styles = int(style_usage.get("unique_run_style_count", 0))
    expected_tokens = int(style_usage.get("semantic_tokens_expected_count", 1))
    style_coverage = min(1.0, unique_styles / max(1, min(expected_tokens, 5)))

    dimensions: dict[str, dict[str, Any]] = {
        "lean_asset_payload": {
            "score": 5.0 if package_bytes < 5_000_000 and image_ratio < 0.6 else 2.5,
            "status": "pass" if package_bytes < 5_000_000 and image_ratio < 0.6 else "fail",
            "measurability": "measurable_now",
            "metrics": {
                "package_bytes": package_bytes,
                "image_bytes": image_bytes,
                "image_to_package_ratio": image_ratio,
            },
            "sample_anchor": "bad-1 shows image_payload_bloat; good samples stay compact by comparison",
        },
        "semantic_style_coverage": {
            "score": 5.0 if style_coverage >= 0.8 else (4.0 if style_coverage >= 0.6 else 3.0),
            "status": "pass" if style_coverage >= 0.6 else "warn",
            "measurability": "proxy_only",
            "metrics": {
                "unique_run_style_count": unique_styles,
                "expected_semantic_token_count": expected_tokens,
                "coverage_ratio": round(style_coverage, 2),
            },
            "sample_anchor": "good samples expose richer bounded style vocabularies than the bad sample",
        },
        "structured_metadata_front_matter": {
            "score": 5.0 if required.get("metadata") else 2.0,
            "status": "pass" if required.get("metadata") else "fail",
            "measurability": "measurable_now",
            "metrics": {"has_metadata_table": bool(required.get("metadata"))},
            "sample_anchor": "good/redacted previews show structured front-matter fields",
        },
        "purposeful_table_readability": {
            "score": 5.0 if tables >= 2 else (4.0 if tables == 1 else 2.0),
            "status": "pass" if tables >= 2 else ("warn" if tables == 1 else "fail"),
            "measurability": "proxy_only",
            "metrics": {"table_count": tables, "requires_metadata_and_budget_tables": True},
            "sample_anchor": "good samples use tables for structure; bad sample proves volume alone is not quality",
        },
        "required_proposal_outline": {
            "score": 5.0 if all(required.values()) else max(2.0, 5.0 * sum(required.values()) / len(required)),
            "status": "pass" if all(required.values()) else "fail",
            "measurability": "measurable_now",
            "metrics": {"required_sections": dict(required)},
            "sample_anchor": "rubric/demo require proposal identity, summary, body, budget, outcomes, closing",
        },
        "compliance_declaration_block": {
            "score": 5.0 if required.get("closing") else 2.0,
            "status": "pass" if required.get("closing") else "fail",
            "measurability": "proxy_only",
            "metrics": {"closing_or_submission_block": bool(required.get("closing"))},
            "sample_anchor": "redacted previews include declaration/consent/closing style blocks",
        },
        "agent_reproducible_generation": {
            "score": 5.0 if validation_ok else 2.0,
            "status": "pass" if validation_ok else "fail",
            "measurability": "measurable_now",
            "metrics": {"schema_validation_ok": validation_ok, "uses_public_api_only": True},
            "sample_anchor": "feasibility/demo reports require validation-clean public API generation",
        },
    }
    average = round(
        sum(float(dimension["score"]) for dimension in dimensions.values()) / len(dimensions),
        2,
    )
    return {
        "sample_set": ["good-1-best.hwpx", "good-2.hwpx", "bad-1.hwpx"],
        "basis": "aggregate package/XML/text proxy traits from existing local samples",
        "dimensions": dimensions,
        "average": average,
        "pass": average >= 4.0 and all(dimension["status"] != "fail" for dimension in dimensions.values()),
        "visual_review_required": True,
        "limitations": [
            "Rendered visual parity is not claimed.",
            "Traits marked proxy_only need human/rendered review before visual-quality sign-off.",
        ],
    }


def _quality_gaps(
    required: Mapping[str, bool],
    scores: Mapping[str, float],
    validation_ok: bool,
    *,
    sample_match: Mapping[str, Any] | None = None,
) -> list[str]:
    gaps = [f"missing required section: {name}" for name, present in required.items() if not present]
    gaps.extend(f"rubric dimension below threshold: {name}" for name, score in scores.items() if score < 3.0)
    if not validation_ok:
        gaps.append("document validation reported issues")
    if sample_match:
        dimensions = sample_match.get("dimensions", {})
        if isinstance(dimensions, Mapping):
            for name, detail in dimensions.items():
                if isinstance(detail, Mapping) and detail.get("status") == "fail":
                    gaps.append(f"sample-match dimension failed: {name}")
    return gaps
