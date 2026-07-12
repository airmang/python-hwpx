# SPDX-License-Identifier: Apache-2.0
"""Frozen contracts for full-page visual quality assurance.

The contracts in this module deliberately make two unsafe states impossible to
serialize as a pass:

* a document with a missing page verdict; and
* a document containing a critical finding.

Coordinates are normalized to the rendered page, making findings stable across
render DPI.  Fixture provenance is represented elsewhere and can never be
promoted to real-Hancom evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


TAXONOMY_VERSION = "hwpx-visual-defects/1.0"


class DefectCategory(str, Enum):
    TEXT_CLIPPING_OVERLAP = "text_clipping_overlap"
    CELL_OVERFLOW = "cell_overflow"
    UNEXPECTED_BLANK_PAGE = "unexpected_blank_page"
    LEFTOVER_GUIDANCE_PLACEHOLDER_SAMPLE = "leftover_guidance_placeholder_sample"
    EMPTY_REQUIRED_FIELD = "empty_required_field"
    ORPHAN_BULLET_HEADING = "orphan_bullet_heading"
    TABLE_GRID_BORDER_ANOMALY = "table_grid_border_anomaly"
    FONT_COLOR_ALIGNMENT_INCONSISTENCY = "font_color_alignment_inconsistency"
    IMAGE_SEAL_MISPLACEMENT = "image_seal_misplacement"
    HEADER_FOOTER_PAGE_NUMBER_LOSS = "header_footer_page_number_loss"
    IMPLAUSIBLE_WHITESPACE_DENSITY = "implausible_whitespace_density"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class VerdictStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class NormalizedBBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        values = (self.x0, self.y0, self.x1, self.y1)
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ValueError("normalized bbox coordinates must be in [0, 1]")
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError("normalized bbox must have positive area")

    @classmethod
    def whole_page(cls) -> "NormalizedBBox":
        return cls(0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class Evidence:
    page_sha256: str
    crop_sha256: str
    crop_bbox: NormalizedBBox
    mime_type: str = "image/png"

    def __post_init__(self) -> None:
        for name, value in (("page_sha256", self.page_sha256), ("crop_sha256", self.crop_sha256)):
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError(f"{name} must be a lowercase sha256 hex digest")


@dataclass(frozen=True)
class Provenance:
    detector_id: str
    detector_version: str
    kind: str = "deterministic"
    model: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.detector_id or not self.detector_version:
            raise ValueError("detector id and version are required")
        if self.kind not in {"deterministic", "vision_provider", "human"}:
            raise ValueError("unsupported provenance kind")


@dataclass(frozen=True)
class DocumentTarget:
    kind: str
    target_id: str
    revision: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    row: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"page", "paragraph", "cell", "object", "header", "footer"}:
            raise ValueError("unsupported document target kind")
        if not self.target_id:
            raise ValueError("document target id is required")


@dataclass(frozen=True)
class VisualFinding:
    finding_id: str
    page: int
    bbox: NormalizedBBox
    category: DefectCategory
    severity: FindingSeverity
    confidence: float
    evidence: Evidence
    provenance: Provenance
    message: str
    target: DocumentTarget | None = None

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise ValueError("finding id is required")
        if self.page < 0:
            raise ValueError("page is zero-based and must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not self.message:
            raise ValueError("finding message is required")

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(frozen=True)
class PageVerdict:
    page: int
    page_sha256: str
    status: VerdictStatus
    findings: tuple[VisualFinding, ...] = ()
    coverage_complete: bool = True

    def __post_init__(self) -> None:
        if self.page < 0:
            raise ValueError("page is zero-based and must be non-negative")
        if len(self.page_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.page_sha256):
            raise ValueError("page_sha256 must be a lowercase sha256 hex digest")
        if any(item.page != self.page for item in self.findings):
            raise ValueError("all findings must belong to the page verdict")
        if not self.coverage_complete and self.status is not VerdictStatus.UNVERIFIED:
            raise ValueError("incomplete page coverage must be unverified")
        if any(
            item.severity in {FindingSeverity.ERROR, FindingSeverity.CRITICAL}
            for item in self.findings
        ) and self.status is not VerdictStatus.FAIL:
            raise ValueError("error or critical finding must fail the page verdict")

    @classmethod
    def build(
        cls,
        *,
        page: int,
        page_sha256: str,
        findings: Iterable[VisualFinding],
        coverage_complete: bool = True,
    ) -> "PageVerdict":
        items = tuple(findings)
        if any(item.page != page for item in items):
            raise ValueError("all findings must belong to the page verdict")
        if not coverage_complete:
            status = VerdictStatus.UNVERIFIED
        elif any(item.severity in {FindingSeverity.ERROR, FindingSeverity.CRITICAL} for item in items):
            status = VerdictStatus.FAIL
        elif items:
            status = VerdictStatus.NEEDS_REVIEW
        else:
            status = VerdictStatus.PASS
        return cls(page, page_sha256, status, items, coverage_complete)

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


@dataclass(frozen=True)
class VisualVerdict:
    taxonomy_version: str
    status: VerdictStatus
    expected_pages: tuple[int, ...]
    pages: tuple[PageVerdict, ...]
    missing_pages: tuple[int, ...]
    unexpected_pages: tuple[int, ...]
    findings: tuple[VisualFinding, ...]
    critical_count: int
    needs_review: bool
    render_checked: bool
    assurance: str

    def __post_init__(self) -> None:
        if self.assurance == "fixture" and self.render_checked:
            raise ValueError("fixture evidence can never set render_checked=true")
        if self.assurance in {"real_hancom", "provider"} and not self.render_checked:
            raise ValueError("non-fixture assurance requires render_checked=true")
        if self.critical_count and self.status is not VerdictStatus.FAIL:
            raise ValueError("critical findings cannot be hidden by document status")
        if (self.missing_pages or self.unexpected_pages) and self.status is not VerdictStatus.UNVERIFIED:
            raise ValueError("incomplete document page coverage must be unverified")

    @classmethod
    def build(
        cls,
        *,
        expected_pages: Iterable[int],
        pages: Iterable[PageVerdict],
        assurance: str,
        render_checked: bool,
    ) -> "VisualVerdict":
        expected = tuple(sorted(set(expected_pages)))
        if not expected:
            raise ValueError("expected_pages must not be empty")
        if assurance not in {"fixture", "real_hancom", "provider"}:
            raise ValueError("unsupported visual assurance")
        if assurance == "fixture" and render_checked:
            raise ValueError("fixture evidence can never set render_checked=true")
        if assurance in {"real_hancom", "provider"} and not render_checked:
            raise ValueError("non-fixture assurance requires render_checked=true")
        page_items = tuple(sorted(pages, key=lambda item: item.page))
        actual = tuple(item.page for item in page_items)
        if len(actual) != len(set(actual)):
            raise ValueError("duplicate page verdict")
        missing = tuple(page for page in expected if page not in actual)
        unexpected = tuple(page for page in actual if page not in expected)
        findings = tuple(finding for page in page_items for finding in page.findings)
        critical_count = sum(item.severity is FindingSeverity.CRITICAL for item in findings)
        incomplete = bool(missing or unexpected) or any(not page.coverage_complete for page in page_items)
        failing = critical_count > 0 or any(page.status is VerdictStatus.FAIL for page in page_items)
        review = any(page.status is VerdictStatus.NEEDS_REVIEW for page in page_items)
        if incomplete:
            status = VerdictStatus.UNVERIFIED
        elif failing:
            status = VerdictStatus.FAIL
        elif review:
            status = VerdictStatus.NEEDS_REVIEW
        else:
            status = VerdictStatus.PASS
        return cls(
            taxonomy_version=TAXONOMY_VERSION,
            status=status,
            expected_pages=expected,
            pages=page_items,
            missing_pages=missing,
            unexpected_pages=unexpected,
            findings=findings,
            critical_count=critical_count,
            needs_review=incomplete or failing or review,
            render_checked=render_checked,
            assurance=assurance,
        )

    def to_dict(self) -> dict[str, Any]:
        return _enum_values(asdict(self))


def _enum_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_enum_values(item) for item in value]
    return value


__all__ = [
    "TAXONOMY_VERSION",
    "DefectCategory",
    "FindingSeverity",
    "VerdictStatus",
    "NormalizedBBox",
    "Evidence",
    "Provenance",
    "DocumentTarget",
    "VisualFinding",
    "PageVerdict",
    "VisualVerdict",
]
