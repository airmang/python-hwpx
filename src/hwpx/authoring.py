# SPDX-License-Identifier: Apache-2.0
"""Declarative document-plan authoring for agent-generated HWPX files."""

from __future__ import annotations

import re
from ast import literal_eval as _literal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .builder import (
    Bullet as BuilderBullet,
    Document as BuilderDocument,
    Footer as BuilderFooter,
    Header as BuilderHeader,
    Heading as BuilderHeading,
    Image as BuilderImage,
    Margins as BuilderMargins,
    Metadata as BuilderMetadata,
    NumberedList as BuilderNumberedList,
    PageBreak as BuilderPageBreak,
    PageNumber as BuilderPageNumber,
    PageSize as BuilderPageSize,
    Paragraph as BuilderParagraph,
    Run as BuilderRun,
    Section as BuilderSection,
    Table as BuilderTable,
)
from .builder.core import Toc as BuilderToc
from .document import HwpxDocument
from .tools.package_validator import validate_package
from .tools.table_cleanup import normalize_cell_text
from .tools.report_utils import (
    calculate_age,
    calculate_ratios,
    format_delta,
    format_delta_percent,
    format_krw_hangul,
    format_number_commas,
    normalize_korean_date,
)

DOCUMENT_PLAN_SCHEMA_VERSION = "hwpx.document_plan.v1"
DOCUMENT_PLAN_V2_SCHEMA_VERSION = "hwpx.document_plan.v2"
AUTHORING_REPORT_VERSION = "hwpx-authoring-quality-v1"
OPERATING_PLAN_QUALITY_VERSION = "operating-plan-quality-v1"
DEFAULT_STYLE_PRESET = "standard_korean_business"
_DEFAULT_TABLE_WIDTH = 48_000
_METADATA_LABELS = {
    "organization": "기관",
    "author": "작성자",
    "date": "작성일",
    "document_type": "문서 유형",
}
_SUPPORTED_BLOCK_TYPES = frozenset(
    {"heading", "paragraph", "bullets", "table", "page_break", "memo"}
)
_SUPPORTED_STYLE_TOKENS = frozenset(
    {"body", "title", "subtitle", "heading", "bullet", "table_header", "table_cell"}
)
_SUPPORTED_TABLE_PROFILES = frozenset({"government"})
_BOOLEAN_QUALITY_GATES = frozenset(
    {"validatePackage", "validateDocument", "reopen", "visualReviewRequired"}
)
_INTEGER_QUALITY_GATES = frozenset({"minNonEmptyParagraphs", "minTableCount"})
_LIST_QUALITY_GATES = frozenset({"requiredText"})
_COMPUTED_FIELD_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_COMPUTED_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$", re.DOTALL)


@dataclass(slots=True)
class DocumentBlock:
    """A normalized block in a declarative HWPX document plan."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentPlan:
    """Normalized representation of ``hwpx.document_plan.v1``."""

    title: str
    subtitle: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    blocks: list[DocumentBlock] = field(default_factory=list)
    style_preset: str = DEFAULT_STYLE_PRESET
    quality_gates: dict[str, Any] = field(default_factory=dict)
    schema_version: str = DOCUMENT_PLAN_SCHEMA_VERSION
    builder_document: BuilderDocument | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this plan."""

        return {
            "schemaVersion": self.schema_version,
            "title": self.title,
            "subtitle": self.subtitle,
            "metadata": dict(self.metadata),
            "stylePreset": self.style_preset,
            "blocks": [
                {"type": block.type, **dict(block.data)}
                for block in self.blocks
            ],
            "qualityGates": dict(self.quality_gates),
        }


@dataclass(frozen=True, slots=True)
class PlanValidationIssue:
    """Machine-readable issue from validating a declarative document plan."""

    code: str
    path: str
    message: str
    severity: str = "error"
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this issue."""

        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.path}: {self.message}"


@dataclass(frozen=True, slots=True)
class PlanValidationReport:
    """Validation result for a declarative document plan."""

    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str | None = None
    issues: tuple[PlanValidationIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""

        issues = _report_plan_issues(self)
        return {
            "ok": self.ok,
            "schemaVersion": self.schema_version,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in issues],
            "repairHints": _plan_repair_hints(issues),
        }


@dataclass(frozen=True, slots=True)
class DocumentStylePreset:
    """Semantic style-token preset for generated HWPX documents."""

    name: str = DEFAULT_STYLE_PRESET
    title_bold: bool = True
    subtitle_italic: bool = True
    heading_bold: bool = True
    heading_underline: bool = True
    table_header_bold: bool = True

    def ensure_tokens(self, document: HwpxDocument) -> dict[str, str]:
        """Create/reuse run styles and return semantic token IDs."""

        return {
            "title": document.ensure_run_style(bold=self.title_bold),
            "subtitle": document.ensure_run_style(italic=self.subtitle_italic),
            "heading": document.ensure_run_style(
                bold=self.heading_bold,
                underline=self.heading_underline,
            ),
            "body": document.ensure_run_style(),
            "bullet": document.ensure_run_style(),
            "table_header": document.ensure_run_style(bold=self.table_header_bold),
            "table_cell": document.ensure_run_style(),
        }


def _plan_issue(
    code: str,
    path: str,
    message: str,
    *,
    severity: str = "error",
    suggestion: str = "",
) -> PlanValidationIssue:
    return PlanValidationIssue(
        code=code,
        path=path,
        message=message,
        severity=severity,
        suggestion=suggestion,
    )


def _plan_validation_report(
    issues: list[PlanValidationIssue],
    *,
    schema_version: str | None,
) -> PlanValidationReport:
    errors = tuple(issue.message for issue in issues if issue.severity == "error")
    warnings = tuple(issue.message for issue in issues if issue.severity != "error")
    return PlanValidationReport(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        schema_version=schema_version,
        issues=tuple(issues),
    )


_COMPUTED_FUNCTIONS = {
    "krw_hangul": format_krw_hangul,
    "commas": format_number_commas,
    "age": calculate_age,
    "delta": format_delta,
    "delta_percent": format_delta_percent,
    "ratio": calculate_ratios,
    "date": normalize_korean_date,
}


class _ComputedFieldError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def replace_computed_fields(text: str) -> str:
    """Replace safe ``{{ function(args) }}`` report utility placeholders."""

    def replacement(match: re.Match[str]) -> str:
        return _evaluate_computed_field(match.group(1))

    result = _COMPUTED_FIELD_RE.sub(replacement, text)
    if "{{" in result or "}}" in result:
        raise _ComputedFieldError(
            "invalid_computed_field",
            "computed field marker is malformed or unresolved",
        )
    return result


def _evaluate_computed_field(expression: str) -> str:
    match = _COMPUTED_CALL_RE.match(expression.strip())
    if not match:
        raise _ComputedFieldError(
            "invalid_computed_field",
            f"computed field must be a function call: {expression!r}",
        )
    function_name, raw_args = match.groups()
    function = _COMPUTED_FUNCTIONS.get(function_name)
    if function is None:
        raise _ComputedFieldError(
            "unknown_computed_field",
            f"unknown computed field function: {function_name}",
        )
    args = [_parse_computed_arg(arg) for arg in _split_computed_args(raw_args)]
    try:
        return str(function(*args))
    except Exception as exc:
        raise _ComputedFieldError(
            "invalid_computed_field",
            f"computed field failed: {expression!r}",
        ) from exc


def _split_computed_args(raw_args: str) -> list[str]:
    if not raw_args.strip():
        return []
    args: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(raw_args):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == ",":
            args.append(raw_args[start:index].strip())
            start = index + 1
    if quote:
        raise _ComputedFieldError("invalid_computed_field", "unterminated string argument")
    args.append(raw_args[start:].strip())
    return args


def _parse_computed_arg(token: str) -> object:
    if not token:
        raise _ComputedFieldError("invalid_computed_field", "empty computed field argument")
    if token[0] in {"'", '"'}:
        try:
            value = _literal(token)
        except (SyntaxError, ValueError) as exc:
            raise _ComputedFieldError("invalid_computed_field", "invalid string argument") from exc
        if not isinstance(value, str):
            raise _ComputedFieldError("invalid_computed_field", "only string literals are supported")
        return value
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    if re.fullmatch(r"[+-]?\d+\.\d+", token):
        return float(token)
    raise _ComputedFieldError(
        "invalid_computed_field",
        f"unsupported computed field argument: {token!r}",
    )


def _computed_field_issues(text: Any, *, path: str) -> list[PlanValidationIssue]:
    value = str(text or "")
    if "{{" not in value and "}}" not in value:
        return []
    issues: list[PlanValidationIssue] = []
    for match in _COMPUTED_FIELD_RE.finditer(value):
        try:
            _evaluate_computed_field(match.group(1))
        except _ComputedFieldError as exc:
            issues.append(
                _plan_issue(
                    exc.code,
                    path,
                    str(exc),
                    suggestion="Use a supported computed function such as krw_hangul, commas, delta, ratio, or date.",
                )
            )
    residue = _COMPUTED_FIELD_RE.sub("", value)
    if "{{" in residue or "}}" in residue:
        issues.append(
            _plan_issue(
                "invalid_computed_field",
                path,
                "computed field marker is malformed or unresolved",
                suggestion="Use balanced computed field delimiters such as {{ commas(1234) }}.",
            )
        )
    return issues


def _report_plan_issues(report: PlanValidationReport) -> tuple[PlanValidationIssue, ...]:
    if report.issues:
        return report.issues
    issues: list[PlanValidationIssue] = []
    issues.extend(
        _plan_issue("validation_error", "$", message)
        for message in report.errors
    )
    issues.extend(
        _plan_issue("validation_warning", "$", message, severity="warning")
        for message in report.warnings
    )
    return tuple(issues)


def _plan_repair_hints(issues: tuple[PlanValidationIssue, ...]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for issue in issues:
        if not issue.suggestion:
            continue
        hints.append(
            {
                "path": issue.path,
                "code": issue.code,
                "action": "fix" if issue.severity == "error" else "review",
                "message": issue.suggestion,
            }
        )
    return hints


def validate_document_plan(plan: Mapping[str, Any]) -> PlanValidationReport:
    """Return validation errors for a ``hwpx.document_plan.v1`` mapping."""

    issues: list[PlanValidationIssue] = []
    schema_version: str | None = None
    if not isinstance(plan, Mapping):
        return _plan_validation_report(
            [
                _plan_issue(
                    "plan_not_object",
                    "$",
                    "document plan must be a mapping",
                    suggestion=(
                        "Send a JSON object with schemaVersion, title, blocks, "
                        "and optional metadata or qualityGates."
                    ),
                )
            ],
            schema_version=None,
        )

    schema_version = str(plan.get("schemaVersion") or "").strip()
    if schema_version not in {DOCUMENT_PLAN_SCHEMA_VERSION, DOCUMENT_PLAN_V2_SCHEMA_VERSION}:
        issues.append(
            _plan_issue(
                "invalid_schema_version",
                "schemaVersion",
                (
                    f"schemaVersion must be {DOCUMENT_PLAN_SCHEMA_VERSION!r} "
                    f"or {DOCUMENT_PLAN_V2_SCHEMA_VERSION!r}"
                ),
                suggestion=f"Set schemaVersion to {DOCUMENT_PLAN_SCHEMA_VERSION!r}.",
            )
        )
    elif schema_version == DOCUMENT_PLAN_V2_SCHEMA_VERSION:
        return _validate_document_plan_v2(plan, schema_version=schema_version)

    title = str(plan.get("title") or "").strip()
    if not title:
        issues.append(
            _plan_issue(
                "empty_title",
                "title",
                "title is empty; generated document will start with blocks",
                severity="warning",
                suggestion="Add a title or accept that generation starts with the first content block.",
            )
        )

    blocks = plan.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        issues.append(
            _plan_issue(
                "missing_blocks",
                "blocks",
                "blocks must be a non-empty list",
                suggestion=(
                    "Add at least one heading, paragraph, bullets, table, "
                    "page_break, or memo block."
                ),
            )
        )
    else:
        for index, raw_block in enumerate(blocks):
            issues.extend(_validate_block(raw_block, index=index))

    metadata = plan.get("metadata", {})
    if metadata is not None and not isinstance(metadata, Mapping):
        issues.append(
            _plan_issue(
                "invalid_metadata",
                "metadata",
                "metadata must be a mapping when provided",
                suggestion="Use an object such as {'organization': '...', 'date': '...'} or omit metadata.",
            )
        )

    quality_gates = plan.get("qualityGates", {})
    if quality_gates is not None and not isinstance(quality_gates, Mapping):
        issues.append(
            _plan_issue(
                "invalid_quality_gates",
                "qualityGates",
                "qualityGates must be a mapping when provided",
                suggestion="Use a JSON object with boolean quality gates, or omit qualityGates.",
            )
        )
    elif isinstance(quality_gates, Mapping):
        issues.extend(_validate_quality_gates(quality_gates))

    return _plan_validation_report(issues, schema_version=schema_version or None)


def normalize_document_plan(plan: Mapping[str, Any] | DocumentPlan) -> DocumentPlan:
    """Normalize and validate a document-plan mapping.

    Raises:
        ValueError: if the plan does not conform to ``hwpx.document_plan.v1``.
    """

    if isinstance(plan, DocumentPlan):
        return plan
    report = validate_document_plan(plan)
    if not report.ok:
        raise ValueError("; ".join(report.errors))

    schema_version = str(plan.get("schemaVersion") or "").strip()
    if schema_version == DOCUMENT_PLAN_V2_SCHEMA_VERSION:
        return DocumentPlan(
            schema_version=DOCUMENT_PLAN_V2_SCHEMA_VERSION,
            title="",
            subtitle="",
            metadata={},
            blocks=[],
            style_preset=str(plan.get("stylePreset") or DEFAULT_STYLE_PRESET).strip()
            or DEFAULT_STYLE_PRESET,
            quality_gates=dict(_default_quality_gates() | dict(plan.get("qualityGates") or {})),
            builder_document=_normalize_v2_builder_document(plan),
        )

    blocks = [
        _normalize_block(raw_block, index=index)
        for index, raw_block in enumerate(plan.get("blocks") or [])
    ]
    return DocumentPlan(
        schema_version=DOCUMENT_PLAN_SCHEMA_VERSION,
        title=str(plan.get("title") or "").strip(),
        subtitle=str(plan.get("subtitle") or "").strip(),
        metadata=_string_mapping(plan.get("metadata") or {}),
        blocks=blocks,
        style_preset=str(plan.get("stylePreset") or DEFAULT_STYLE_PRESET).strip()
        or DEFAULT_STYLE_PRESET,
        quality_gates=dict(_default_quality_gates() | dict(plan.get("qualityGates") or {})),
    )


def _validate_document_plan_v2(
    plan: Mapping[str, Any],
    *,
    schema_version: str,
) -> PlanValidationReport:
    issues: list[PlanValidationIssue] = []
    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        issues.append(
            _plan_issue(
                "missing_sections",
                "sections",
                "sections must be a non-empty list",
                suggestion="Add at least one section with a blocks array.",
            )
        )
        return _plan_validation_report(issues, schema_version=schema_version)

    for section_index, raw_section in enumerate(sections):
        section_path = f"sections[{section_index}]"
        if not isinstance(raw_section, Mapping):
            issues.append(
                _plan_issue(
                    "section_not_object",
                    section_path,
                    f"{section_path} must be a mapping",
                    suggestion="Use an object with optional header/footer and a blocks array.",
                )
            )
            continue
        blocks = raw_section.get("blocks", raw_section.get("children"))
        if not isinstance(blocks, list) or not blocks:
            issues.append(
                _plan_issue(
                    "missing_section_blocks",
                    f"{section_path}.blocks",
                    f"{section_path}.blocks must be a non-empty list",
                    suggestion="Add builder blocks such as heading, paragraph, table, image, or page_break.",
                )
            )
            continue
        for block_index, raw_block in enumerate(blocks):
            issues.extend(
                _validate_v2_block(
                    raw_block,
                    path=f"{section_path}.blocks[{block_index}]",
                )
            )

    metadata = plan.get("metadata", {})
    if metadata is not None and not isinstance(metadata, Mapping):
        issues.append(
            _plan_issue(
                "invalid_metadata",
                "metadata",
                "metadata must be a mapping when provided",
                suggestion="Use an object with title, author, and organization fields or omit metadata.",
            )
        )
    return _plan_validation_report(issues, schema_version=schema_version)


def _validate_v2_block(raw_block: Any, *, path: str) -> list[PlanValidationIssue]:
    if not isinstance(raw_block, Mapping):
        return [
            _plan_issue(
                "block_not_object",
                path,
                f"{path} must be a mapping",
                suggestion="Replace this block with a JSON object containing a supported builder type.",
            )
        ]
    block_type = str(raw_block.get("type") or "").strip()
    supported = {
        "heading",
        "paragraph",
        "bullets",
        "bullet",
        "numbered_list",
        "numberedList",
        "table",
        "image",
        "toc",
        "page_break",
        "pageBreak",
    }
    if block_type not in supported:
        return [
            _plan_issue(
                "unsupported_block_type",
                f"{path}.type",
                f"{path}.type is unsupported: {block_type!r}",
                suggestion="Use a public builder block type.",
            )
        ]
    if block_type in {"heading", "image"}:
        text_key = "text" if block_type == "heading" else "path"
        if not str(raw_block.get(text_key) or "").strip():
            return [
                _plan_issue(
                    "missing_text",
                    f"{path}.{text_key}",
                    f"{path}.{text_key} is required",
                    suggestion=f"Add non-empty {text_key}.",
                )
            ]
    if block_type in {"bullets", "bullet", "numbered_list", "numberedList"}:
        if not _string_list(raw_block.get("items")):
            return [
                _plan_issue(
                    "missing_list_items",
                    f"{path}.items",
                    f"{path}.items must be a non-empty list",
                    suggestion="Add one or more list items.",
                )
            ]
    if block_type == "table":
        header = raw_block.get("header")
        rows = raw_block.get("rows")
        if not isinstance(header, list) and not isinstance(rows, list):
            return [
                _plan_issue(
                    "missing_table_content",
                    path,
                    f"{path} must define header or rows",
                    suggestion="Add a header array or rows array.",
                )
            ]
    issues: list[PlanValidationIssue] = []
    if block_type == "heading":
        issues.extend(_computed_field_issues(raw_block.get("text"), path=f"{path}.text"))
    elif block_type == "paragraph":
        issues.extend(_computed_field_issues(raw_block.get("text"), path=f"{path}.text"))
        for child_index, child in enumerate(raw_block.get("children") or []):
            if isinstance(child, Mapping):
                issues.extend(
                    _computed_field_issues(
                        child.get("text"),
                        path=f"{path}.children[{child_index}].text",
                    )
                )
    elif block_type in {"bullets", "bullet", "numbered_list", "numberedList"}:
        for item_index, item in enumerate(_string_list(raw_block.get("items"))):
            issues.extend(_computed_field_issues(item, path=f"{path}.items[{item_index}]"))
    elif block_type == "table":
        for header_index, header_value in enumerate(raw_block.get("header") or []):
            issues.extend(_computed_field_issues(header_value, path=f"{path}.header[{header_index}]"))
        for row_index, row in enumerate(raw_block.get("rows") or []):
            if isinstance(row, (list, tuple)):
                for col_index, value in enumerate(row):
                    issues.extend(_computed_field_issues(value, path=f"{path}.rows[{row_index}][{col_index}]"))
    elif block_type == "toc":
        issues.extend(_computed_field_issues(raw_block.get("title"), path=f"{path}.title"))
        for entry_index, entry in enumerate(raw_block.get("entries") or []):
            if isinstance(entry, Mapping):
                issues.extend(_computed_field_issues(entry.get("text"), path=f"{path}.entries[{entry_index}].text"))
    return issues


def create_document_from_plan(
    plan: Mapping[str, Any] | DocumentPlan,
    *,
    preset: str | DocumentStylePreset | None = None,
) -> HwpxDocument:
    """Create a formatted HWPX document from a declarative document plan."""

    normalized = normalize_document_plan(plan)
    if normalized.builder_document is not None:
        return normalized.builder_document.lower()
    style_preset = (
        preset
        if isinstance(preset, DocumentStylePreset)
        else DocumentStylePreset(name=str(preset or normalized.style_preset or DEFAULT_STYLE_PRESET))
    )
    document = HwpxDocument.new()
    tokens = style_preset.ensure_tokens(document)
    builder_document = _lower_plan_to_builder_document(normalized)

    if normalized.title:
        document.add_paragraph(
            normalized.title,
            char_pr_id_ref=tokens["title"],
            inherit_style=False,
        )
    if normalized.subtitle:
        document.add_paragraph(
            normalized.subtitle,
            char_pr_id_ref=tokens["subtitle"],
            inherit_style=False,
        )

    if normalized.metadata:
        document.add_paragraph(
            "문서 정보",
            char_pr_id_ref=tokens["heading"],
            inherit_style=False,
        )
        _add_key_value_table(document, normalized.metadata, tokens)

    for block in builder_document.sections[0].children:
        _render_block(document, block, tokens)

    return document


def inspect_document_authoring_quality(
    source: str | Path | HwpxDocument,
    *,
    plan: Mapping[str, Any] | DocumentPlan | None = None,
    quality_profile: str | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic structural quality evidence for generated HWPX."""

    normalized_plan: DocumentPlan | None = None
    plan_validation: dict[str, Any] | None = None
    if plan is not None:
        validation = (
            PlanValidationReport(ok=True, schema_version=DOCUMENT_PLAN_SCHEMA_VERSION)
            if isinstance(plan, DocumentPlan)
            else validate_document_plan(plan)
        )
        plan_validation = validation.to_dict()
        if validation.ok:
            normalized_plan = normalize_document_plan(plan)

    path: Path | None = None
    close_doc = False
    if isinstance(source, HwpxDocument):
        document = source
    else:
        path = Path(source)
        document = HwpxDocument.open(path)
        close_doc = True

    try:
        package_payload = document.to_bytes()
        package_report = validate_package(path if path is not None else package_payload)
        document_report = document.validate()
        reopened = _can_reopen(path, package_payload)
        non_empty_texts = [
            (paragraph.text or "").strip()
            for paragraph in document.paragraphs
            if (paragraph.text or "").strip()
        ]
        full_text = document.export_text()
        table_count = len(_iter_tables(document))
        page_break_count = sum(
            1
            for paragraph in document.paragraphs
            if paragraph.element.get("pageBreak") == "1"
        )
        gates = (
            normalized_plan.quality_gates
            if normalized_plan is not None
            else _default_quality_gates()
        )
        gate_results = _evaluate_quality_gates(
            gates,
            package_ok=bool(getattr(package_report, "ok", False)),
            document_ok=bool(getattr(document_report, "ok", False)),
            reopened=reopened,
            non_empty_paragraph_count=len(non_empty_texts),
            table_count=table_count,
            full_text=full_text,
        )
        gaps = [
            f"quality gate failed: {name}"
            for name, passed in gate_results.items()
            if name != "visualReviewRequired" and not passed
        ]
        if plan_validation is not None and not plan_validation["ok"]:
            gaps.append("document plan validation failed")

        style_usage = _style_usage(document)
        package_issues = _report_issue_dicts(package_report, kind="package")
        document_issues = _report_issue_dicts(document_report, kind="schema")
        recovery = _recovery_summary(
            plan_validation=plan_validation,
            package_issues=package_issues,
            document_issues=document_issues,
            gate_results=gate_results,
        )
        profiles = _profile_reports(
            document,
            normalized_plan=normalized_plan,
            quality_profile=quality_profile,
        )
        if (
            "operating_plan" in profiles
            and not profiles["operating_plan"].get("pass", False)
        ):
            gaps.append("operating plan quality failed")
        return {
            "report_version": AUTHORING_REPORT_VERSION,
            "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
            "plan_validation": plan_validation,
            "pass": not gaps,
            "block_counts": _block_counts(normalized_plan),
            "document": {
                "paragraph_count": len(document.paragraphs),
                "non_empty_paragraph_count": len(non_empty_texts),
                "table_count": table_count,
                "page_break_count": page_break_count,
            },
            "validation": {
                "reopened": reopened,
                "validate_package": {
                    "ok": bool(getattr(package_report, "ok", False)),
                    "errors": _report_errors(package_report),
                    "issues": package_issues,
                },
                "validate_document": {
                    "ok": bool(getattr(document_report, "ok", False)),
                    "errors": _report_errors(document_report),
                    "issues": document_issues,
                },
            },
            "content_evidence": _content_evidence(gates, full_text=full_text),
            "quality_gates": gate_results,
            "style_token_usage": style_usage,
            "recovery": recovery,
            "profiles": profiles,
            "visual_review_required": bool(gates.get("visualReviewRequired", True)),
            "gaps": gaps,
        }
    finally:
        if close_doc:
            document.close()


def inspect_operating_plan_quality(
    source: str | Path | HwpxDocument,
    *,
    plan: Mapping[str, Any] | DocumentPlan | None = None,
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic operating-plan quality report for generated HWPX."""

    normalized_plan: DocumentPlan | None = None
    if plan is not None:
        if isinstance(plan, DocumentPlan):
            normalized_plan = plan
        else:
            validation = validate_document_plan(plan)
            if validation.ok:
                normalized_plan = normalize_document_plan(plan)

    path: Path | None = None
    close_doc = False
    if isinstance(source, HwpxDocument):
        document = source
    else:
        path = Path(source)
        document = HwpxDocument.open(path)
        close_doc = True

    try:
        return _inspect_operating_plan_quality(
            document,
            normalized_plan=normalized_plan,
            profile=profile,
        )
    finally:
        if close_doc:
            document.close()


def _validate_block(raw_block: Any, *, index: int) -> list[PlanValidationIssue]:
    path = f"blocks[{index}]"
    if not isinstance(raw_block, Mapping):
        return [
            _plan_issue(
                "block_not_object",
                path,
                f"{path} must be a mapping",
                suggestion="Replace this block with a JSON object containing a supported type.",
            )
        ]

    issues: list[PlanValidationIssue] = []
    block_type = str(raw_block.get("type") or "").strip()
    if block_type not in _SUPPORTED_BLOCK_TYPES:
        return [
            _plan_issue(
                "unsupported_block_type",
                f"{path}.type",
                f"{path}.type is unsupported: {block_type!r}",
                suggestion=(
                    "Use one of: heading, paragraph, bullets, table, "
                    "page_break, memo."
                ),
            )
        ]

    if block_type == "heading":
        issues.extend(_validate_heading_block(raw_block, path=path))
        issues.extend(_computed_field_issues(raw_block.get("text"), path=f"{path}.text"))
    elif block_type == "paragraph":
        issues.extend(_validate_paragraph_block(raw_block, path=path))
        issues.extend(_computed_field_issues(raw_block.get("text"), path=f"{path}.text"))
    elif block_type == "bullets":
        items = _string_list(raw_block.get("items") or raw_block.get("bullets"))
        if not items:
            issues.append(
                _plan_issue(
                    "missing_bullet_items",
                    f"{path}.items",
                    f"{path}.items must be a non-empty list",
                    suggestion="Add a non-empty items array, or use a paragraph block instead.",
                )
            )
        for item_index, item in enumerate(items):
            issues.extend(_computed_field_issues(item, path=f"{path}.items[{item_index}]"))
    elif block_type == "table":
        column_keys, column_issues = _validate_table_columns(raw_block.get("columns"), path=path)
        issues.extend(column_issues)
        issues.extend(_validate_table_rows(raw_block.get("rows"), column_keys, path=path))
        issues.extend(_computed_field_issues(raw_block.get("caption"), path=f"{path}.caption"))
        issues.extend(_computed_field_issues(raw_block.get("unit"), path=f"{path}.unit"))
        table_profile = str(raw_block.get("tableProfile") or "").strip()
        if table_profile and table_profile not in _SUPPORTED_TABLE_PROFILES:
            issues.append(
                _plan_issue(
                    "unknown_table_profile",
                    f"{path}.tableProfile",
                    f"{path}.tableProfile is unknown: {table_profile!r}",
                    severity="warning",
                    suggestion="Use tableProfile='government' or omit tableProfile.",
                )
            )
        for column_index, column in enumerate(raw_block.get("columns") or []):
            if isinstance(column, Mapping):
                issues.extend(
                    _computed_field_issues(
                        column.get("label"),
                        path=f"{path}.columns[{column_index}].label",
                    )
                )
        for row_index, row in enumerate(raw_block.get("rows") or []):
            if isinstance(row, Mapping):
                for key, value in row.items():
                    if isinstance(value, Mapping):
                        value = value.get("text", value.get("value"))
                    issues.extend(
                        _computed_field_issues(
                            value,
                            path=f"{path}.rows[{row_index}].{key}",
                        )
                    )
    elif block_type == "memo":
        issues.extend(_validate_required_text_fields(raw_block, path=path, fields=("text", "memo")))
        issues.extend(_computed_field_issues(raw_block.get("text"), path=f"{path}.text"))
        issues.extend(_computed_field_issues(raw_block.get("memo"), path=f"{path}.memo"))

    return issues


def _validate_heading_block(raw_block: Mapping[str, Any], *, path: str) -> list[PlanValidationIssue]:
    issues = _validate_required_text_fields(raw_block, path=path, fields=("text",))
    if "level" not in raw_block or raw_block.get("level") in (None, ""):
        return issues
    try:
        level = int(raw_block.get("level"))
    except (TypeError, ValueError):
        issues.append(
            _plan_issue(
                "invalid_heading_level",
                f"{path}.level",
                f"{path}.level must be between 1 and 3",
                suggestion="Use level 1, 2, or 3.",
            )
        )
        return issues
    if level < 1 or level > 3:
        issues.append(
            _plan_issue(
                "invalid_heading_level",
                f"{path}.level",
                f"{path}.level must be between 1 and 3",
                suggestion="Use level 1, 2, or 3.",
            )
        )
    return issues


def _validate_paragraph_block(raw_block: Mapping[str, Any], *, path: str) -> list[PlanValidationIssue]:
    issues = _validate_required_text_fields(raw_block, path=path, fields=("text",))
    style = str(raw_block.get("style") or "body").strip() or "body"
    if style not in _SUPPORTED_STYLE_TOKENS:
        issues.append(
            _plan_issue(
                "unknown_style_token",
                f"{path}.style",
                f"{path}.style is unknown: {style!r}",
                severity="warning",
                suggestion=(
                    "Use body, title, subtitle, heading, bullet, "
                    "table_header, table_cell, or omit style."
                ),
            )
        )
    return issues


def _validate_required_text_fields(
    raw_block: Mapping[str, Any],
    *,
    path: str,
    fields: tuple[str, ...],
) -> list[PlanValidationIssue]:
    issues: list[PlanValidationIssue] = []
    for field_name in fields:
        value = str(raw_block.get(field_name) or "").strip()
        if value:
            continue
        issues.append(
            _plan_issue(
                "missing_text",
                f"{path}.{field_name}",
                f"{path}.{field_name} is required",
                suggestion=f"Add non-empty {field_name} text.",
            )
        )
    return issues


def _validate_table_columns(
    value: Any,
    *,
    path: str,
) -> tuple[list[str], list[PlanValidationIssue]]:
    issues: list[PlanValidationIssue] = []
    if not isinstance(value, list) or not value:
        return [], [
            _plan_issue(
                "missing_table_columns",
                f"{path}.columns",
                f"{path}.columns must be a non-empty list",
                suggestion="Add column objects with unique key values and optional labels.",
            )
        ]

    column_keys: list[str] = []
    seen: set[str] = set()
    for col_index, raw_column in enumerate(value):
        column_path = f"{path}.columns[{col_index}]"
        if not isinstance(raw_column, Mapping):
            issues.append(
                _plan_issue(
                    "invalid_table_column",
                    column_path,
                    f"{column_path} must be a mapping",
                    suggestion="Use an object such as {'key': 'item', 'label': 'Item'}.",
                )
            )
            continue

        key = str(raw_column.get("key") or "").strip()
        if not key:
            issues.append(
                _plan_issue(
                    "missing_table_column_key",
                    f"{column_path}.key",
                    f"{column_path}.key is required",
                    suggestion="Add a stable, unique key such as 'item' or 'amount'.",
                )
            )
        elif key in seen:
            issues.append(
                _plan_issue(
                    "duplicate_table_column_key",
                    f"{column_path}.key",
                    f"{path}.columns contains duplicate key: {key!r}",
                    suggestion=f"Rename or remove the duplicate column key {key!r}.",
                )
            )
        else:
            seen.add(key)
            column_keys.append(key)

        if "widthWeight" in raw_column:
            try:
                width_weight = int(raw_column.get("widthWeight"))
            except (TypeError, ValueError):
                width_weight = 0
            if width_weight <= 0:
                issues.append(
                    _plan_issue(
                        "invalid_width_weight",
                        f"{column_path}.widthWeight",
                        f"{column_path}.widthWeight should be a positive integer",
                        severity="warning",
                        suggestion="Use a positive integer; the current value will be coerced to 1.",
                    )
                )
    return column_keys, issues


def _validate_table_rows(
    value: Any,
    column_keys: list[str],
    *,
    path: str,
) -> list[PlanValidationIssue]:
    if not isinstance(value, list) or not value:
        return [
            _plan_issue(
                "missing_table_rows",
                f"{path}.rows",
                f"{path}.rows must be a non-empty list",
                suggestion="Add at least one row object whose keys match the table columns.",
            )
        ]

    issues: list[PlanValidationIssue] = []
    for row_index, raw_row in enumerate(value):
        row_path = f"{path}.rows[{row_index}]"
        if not isinstance(raw_row, Mapping):
            issues.append(
                _plan_issue(
                    "invalid_table_row",
                    row_path,
                    f"{row_path} must be a mapping",
                    suggestion="Use a row object whose keys match the table columns.",
                )
            )
            continue
        if not column_keys:
            continue
        row_keys = {str(key) for key in raw_row.keys()}
        missing_keys = [key for key in column_keys if key not in row_keys]
        if missing_keys:
            issues.append(
                _plan_issue(
                    "table_row_missing_cells",
                    row_path,
                    f"{row_path} is missing cells for columns: {', '.join(missing_keys)}",
                    severity="warning",
                    suggestion=(
                        "Add keys "
                        + ", ".join(repr(key) for key in missing_keys)
                        + " or accept blank generated cells."
                    ),
                )
            )
        extra_keys = sorted(row_keys - set(column_keys))
        if extra_keys:
            issues.append(
                _plan_issue(
                    "table_row_extra_cells",
                    row_path,
                    f"{row_path} has cells that do not match columns: {', '.join(extra_keys)}",
                    severity="warning",
                    suggestion=(
                        "Remove ignored keys: "
                        + ", ".join(repr(key) for key in extra_keys)
                        + "."
                    ),
                )
            )
    return issues


def _validate_quality_gates(gates: Mapping[str, Any]) -> list[PlanValidationIssue]:
    issues: list[PlanValidationIssue] = []
    for key, value in gates.items():
        gate = str(key)
        path = f"qualityGates.{gate}"
        if gate in _BOOLEAN_QUALITY_GATES:
            if not isinstance(value, bool):
                issues.append(
                    _plan_issue(
                        "invalid_quality_gate_type",
                        path,
                        f"{path} must be a boolean",
                        suggestion=f"Use true or false for {gate}.",
                    )
                )
            continue
        if gate in _INTEGER_QUALITY_GATES:
            try:
                minimum = int(value)
            except (TypeError, ValueError):
                minimum = 0
            if minimum < 1:
                issues.append(
                    _plan_issue(
                        "invalid_quality_gate_minimum",
                        path,
                        f"{path} must be a positive integer",
                        suggestion=f"Use a positive integer for {gate}.",
                    )
                )
            continue
        if gate in _LIST_QUALITY_GATES:
            values = _string_list(value)
            raw_count = len(value) if isinstance(value, list) else 0
            if not values or len(values) != raw_count:
                issues.append(
                    _plan_issue(
                        "invalid_required_text",
                        path,
                        f"{path} must be a non-empty list of non-empty strings",
                        suggestion="Provide required text snippets such as section headings.",
                    )
                )
            continue
    return issues


def _normalize_block(raw_block: Any, *, index: int) -> DocumentBlock:
    if not isinstance(raw_block, Mapping):
        raise TypeError(f"blocks[{index}] must be a mapping")
    block_type = str(raw_block.get("type") or "").strip()
    if block_type not in {"heading", "paragraph", "bullets", "table", "page_break", "memo"}:
        raise ValueError(f"blocks[{index}].type is unsupported: {block_type!r}")

    if block_type == "heading":
        level = _int_value(raw_block.get("level", 1), default=1)
        if level < 1 or level > 3:
            raise ValueError(f"blocks[{index}].level must be between 1 and 3")
        text = _required_text(raw_block, "text", index)
        return DocumentBlock("heading", {"level": level, "text": replace_computed_fields(text)})

    if block_type == "paragraph":
        return DocumentBlock(
            "paragraph",
            {
                "text": replace_computed_fields(_required_text(raw_block, "text", index)),
                "style": str(raw_block.get("style") or "body").strip() or "body",
            },
        )

    if block_type == "bullets":
        items = _string_list(raw_block.get("items") or raw_block.get("bullets"))
        if not items:
            raise ValueError(f"blocks[{index}].items must be a non-empty list")
        return DocumentBlock(
            "bullets",
            {"items": [replace_computed_fields(item) for item in items]},
        )

    if block_type == "table":
        columns = _normalize_columns(raw_block.get("columns"), index=index)
        rows = _normalize_rows(raw_block.get("rows"), columns, index=index)
        caption = replace_computed_fields(normalize_cell_text(raw_block.get("caption")))
        unit = replace_computed_fields(normalize_cell_text(raw_block.get("unit")))
        table_profile = str(raw_block.get("tableProfile") or "").strip()
        columns = [
            {**column, "label": replace_computed_fields(normalize_cell_text(column["label"]))}
            for column in columns
        ]
        rows = [
            {key: replace_computed_fields(value) for key, value in row.items()}
            for row in rows
        ]
        data: dict[str, Any] = {"caption": caption, "columns": columns, "rows": rows}
        if unit:
            data["unit"] = unit
        if table_profile:
            data["tableProfile"] = table_profile
        return DocumentBlock("table", data)

    if block_type == "memo":
        return DocumentBlock(
            "memo",
            {
                "text": replace_computed_fields(_required_text(raw_block, "text", index)),
                "memo": replace_computed_fields(_required_text(raw_block, "memo", index)),
            },
        )

    return DocumentBlock("page_break", {})


def _normalize_v2_builder_document(plan: Mapping[str, Any]) -> BuilderDocument:
    metadata = plan.get("metadata") or {}
    builder_metadata = None
    if isinstance(metadata, Mapping):
        title = str(metadata.get("title") or plan.get("title") or "").strip()
        author = str(metadata.get("author") or "").strip()
        organization = str(metadata.get("organization") or "").strip()
        if title or author or organization:
            builder_metadata = BuilderMetadata(
                title=title,
                author=author,
                organization=organization,
            )
    return BuilderDocument(
        sections=tuple(
            _normalize_v2_section(raw_section, index=index)
            for index, raw_section in enumerate(plan.get("sections") or [])
        ),
        metadata=builder_metadata,
        visual_review_required=_optional_bool(plan.get("visualReviewRequired")),
        preset=str(plan.get("preset") or plan.get("stylePreset") or DEFAULT_STYLE_PRESET).strip()
        or DEFAULT_STYLE_PRESET,
    )


def _normalize_v2_section(raw_section: Any, *, index: int) -> BuilderSection:
    if not isinstance(raw_section, Mapping):
        raise TypeError(f"sections[{index}] must be a mapping")
    raw_blocks = raw_section.get("blocks", raw_section.get("children"))
    return BuilderSection(
        children=tuple(
            _normalize_v2_block(raw_block, path=f"sections[{index}].blocks[{block_index}]")
            for block_index, raw_block in enumerate(raw_blocks or [])
        ),
        page=_normalize_v2_page(raw_section.get("page")),
        margins=_normalize_v2_margins(raw_section.get("margins")),
        header=_normalize_v2_header_footer(raw_section.get("header"), kind="header"),
        footer=_normalize_v2_header_footer(raw_section.get("footer"), kind="footer"),
    )


def _normalize_v2_page(value: Any) -> BuilderPageSize | None:
    if not isinstance(value, Mapping):
        return None
    preset = str(value.get("preset") or "").strip().upper()
    if preset == "A4":
        return BuilderPageSize.A4
    width = _float_value(value.get("widthMm", value.get("width_mm")), default=210)
    height = _float_value(value.get("heightMm", value.get("height_mm")), default=297)
    orientation = str(value.get("orientation") or "PORTRAIT").strip() or "PORTRAIT"
    return BuilderPageSize(width_mm=width, height_mm=height, orientation=orientation)


def _normalize_v2_margins(value: Any) -> BuilderMargins | None:
    if not isinstance(value, Mapping):
        return None
    return BuilderMargins(
        top_mm=_float_value(value.get("topMm", value.get("top_mm")), default=20),
        right_mm=_float_value(value.get("rightMm", value.get("right_mm")), default=20),
        bottom_mm=_float_value(value.get("bottomMm", value.get("bottom_mm")), default=20),
        left_mm=_float_value(value.get("leftMm", value.get("left_mm")), default=20),
        header_mm=_float_value(value.get("headerMm", value.get("header_mm")), default=10),
        footer_mm=_float_value(value.get("footerMm", value.get("footer_mm")), default=10),
        gutter_mm=_float_value(value.get("gutterMm", value.get("gutter_mm")), default=0),
    )


def _normalize_v2_header_footer(value: Any, *, kind: str) -> BuilderHeader | BuilderFooter | None:
    if not isinstance(value, Mapping):
        return None
    children = tuple(_normalize_v2_header_footer_child(child) for child in value.get("children") or [])
    if kind == "header":
        return BuilderHeader(children=children)
    return BuilderFooter(children=children)


def _normalize_v2_header_footer_child(value: Any) -> BuilderParagraph | BuilderPageNumber:
    if not isinstance(value, Mapping):
        raise TypeError("header/footer children must be mappings")
    child_type = str(value.get("type") or "paragraph").strip()
    if child_type == "page_number":
        return BuilderPageNumber(format=str(value.get("format") or "page"))
    if child_type != "paragraph":
        raise ValueError(f"unsupported header/footer child type: {child_type!r}")
    children = tuple(_normalize_v2_paragraph_child(child) for child in value.get("children") or [])
    return BuilderParagraph(
        text=replace_computed_fields(str(value.get("text") or "")),
        children=children,
        align=_optional_str(value.get("align")),
    )


def _normalize_v2_paragraph_child(value: Any) -> BuilderRun | BuilderPageNumber:
    if not isinstance(value, Mapping):
        raise TypeError("paragraph children must be mappings")
    child_type = str(value.get("type") or "run").strip()
    if child_type == "page_number":
        return BuilderPageNumber(format=str(value.get("format") or "page"))
    if child_type != "run":
        raise ValueError(f"unsupported paragraph child type: {child_type!r}")
    return BuilderRun(
        text=replace_computed_fields(str(value.get("text") or "")),
        bold=bool(value.get("bold", False)),
        italic=bool(value.get("italic", False)),
        underline=bool(value.get("underline", False)),
        color=_optional_str(value.get("color")),
        font=_optional_str(value.get("font")),
        size=_optional_number(value.get("size")),
        highlight=_optional_str(value.get("highlight")),
        strike=bool(value.get("strike", False)),
    )


def _normalize_v2_block(raw_block: Any, *, path: str) -> Any:
    if not isinstance(raw_block, Mapping):
        raise TypeError(f"{path} must be a mapping")
    block_type = str(raw_block.get("type") or "").strip()
    if block_type == "heading":
        return BuilderHeading(
            level=_int_value(raw_block.get("level", 1), default=1),
            text=replace_computed_fields(str(raw_block.get("text") or "")),
        )
    if block_type == "paragraph":
        children = tuple(
            child
            for child in (_normalize_v2_paragraph_child(child) for child in raw_block.get("children") or [])
            if isinstance(child, BuilderRun)
        )
        return BuilderParagraph(
            text=replace_computed_fields(str(raw_block.get("text") or "")),
            children=children,
            align=_optional_str(raw_block.get("align")),
            style=_optional_str(raw_block.get("style")),
        )
    if block_type in {"bullets", "bullet"}:
        return BuilderBullet(
            items=tuple(replace_computed_fields(item) for item in _string_list(raw_block.get("items"))),
            level=_int_value(raw_block.get("level", 0), default=0),
            style=_optional_str(raw_block.get("style")),
        )
    if block_type in {"numbered_list", "numberedList"}:
        return BuilderNumberedList(
            items=tuple(replace_computed_fields(item) for item in _string_list(raw_block.get("items"))),
            level=_int_value(raw_block.get("level", 0), default=0),
        )
    if block_type == "table":
        return BuilderTable(
            header=tuple(replace_computed_fields(str(item)) for item in raw_block.get("header") or ()),
            rows=tuple(
                tuple(replace_computed_fields(str(cell)) for cell in row)
                for row in raw_block.get("rows") or ()
            ),
            merges=tuple(str(item) for item in raw_block.get("merges") or ()),
            header_shading=_optional_str(raw_block.get("headerShading", raw_block.get("header_shading"))),
            column_widths=tuple(
                _optional_number(item) or 0
                for item in raw_block.get("columnWidths", raw_block.get("column_widths")) or ()
            ),
        )
    if block_type == "image":
        return BuilderImage(
            path=str(raw_block.get("path") or ""),
            width_mm=_optional_number(raw_block.get("widthMm", raw_block.get("width_mm"))),
            align=_optional_str(raw_block.get("align")),
            caption=(
                replace_computed_fields(str(raw_block.get("caption")))
                if raw_block.get("caption") is not None
                else None
            ),
            image_format=_optional_str(raw_block.get("imageFormat", raw_block.get("image_format"))),
        )
    if block_type == "toc":
        return BuilderToc(
            title=replace_computed_fields(str(raw_block.get("title") or "목차")),
            entries=tuple(
                {**entry, "text": replace_computed_fields(str(entry.get("text") or ""))}
                for entry in raw_block.get("entries") or ()
                if isinstance(entry, Mapping)
            ),
        )
    if block_type in {"page_break", "pageBreak"}:
        return BuilderPageBreak()
    raise ValueError(f"{path}.type is unsupported: {block_type!r}")


def _lower_plan_to_builder_document(plan: DocumentPlan) -> BuilderDocument:
    """Lower a normalized document plan to builder nodes.

    v1 authoring keeps its historical title, metadata, style-token, and memo
    rendering contracts, so this helper lowers the body blocks into public
    builder nodes while ``create_document_from_plan`` supplies the existing
    document-level framing.
    """

    if plan.builder_document is not None:
        return plan.builder_document
    children: list[Any] = []
    for block in plan.blocks:
        children.extend(_block_to_builder_nodes(block))
    return BuilderDocument(sections=(BuilderSection(children=tuple(children)),))


def _block_to_builder_nodes(block: DocumentBlock) -> tuple[Any, ...]:
    if block.type == "heading":
        return (
            BuilderHeading(
                level=int(block.data["level"]),
                text=str(block.data["text"]),
            ),
        )
    if block.type == "paragraph":
        return (
            BuilderParagraph(
                text=str(block.data["text"]),
                style=str(block.data.get("style") or "body"),
            ),
        )
    if block.type == "bullets":
        return (BuilderBullet(items=tuple(str(item) for item in block.data["items"])),)
    if block.type == "table":
        columns = list(block.data["columns"])
        rows = list(block.data["rows"])
        nodes: list[Any] = []
        caption = str(block.data.get("caption") or "").strip()
        if caption:
            nodes.append(BuilderParagraph(text=caption, style="heading"))
        nodes.append(
            BuilderTable(
                header=tuple(str(column["label"]) for column in columns),
                rows=tuple(
                    tuple(str(row.get(column["key"], "")) for column in columns)
                    for row in rows
                ),
                column_widths=tuple(_plan_table_column_widths(columns)),
            ),
        )
        unit = str(block.data.get("unit") or "").strip()
        if unit:
            nodes.append(BuilderParagraph(text=unit, style="body"))
        return tuple(nodes)
    if block.type == "memo":
        return (block,)
    if block.type == "page_break":
        return (BuilderPageBreak(),)
    raise ValueError(f"unsupported block type: {block.type!r}")


def _plan_table_column_widths(columns: list[dict[str, Any]]) -> list[int]:
    total = sum(max(int(column.get("widthWeight", 1)), 1) for column in columns)
    if total <= 0:
        return []
    widths = [
        round(_DEFAULT_TABLE_WIDTH * max(int(column.get("widthWeight", 1)), 1) / total)
        for column in columns
    ]
    if widths:
        widths[-1] += _DEFAULT_TABLE_WIDTH - sum(widths)
    return widths


def _normalize_columns(value: Any, *, index: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"blocks[{index}].columns must be a non-empty list")
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for col_index, raw_column in enumerate(value):
        if not isinstance(raw_column, Mapping):
            raise ValueError(f"blocks[{index}].columns[{col_index}] must be a mapping")
        key = str(raw_column.get("key") or "").strip()
        if not key:
            raise ValueError(f"blocks[{index}].columns[{col_index}].key is required")
        if key in seen:
            raise ValueError(f"blocks[{index}].columns contains duplicate key: {key!r}")
        seen.add(key)
        label = normalize_cell_text(raw_column.get("label") or key)
        width_weight = _int_value(raw_column.get("widthWeight", 1), default=1)
        columns.append(
            {
                "key": key,
                "label": label,
                "widthWeight": max(width_weight, 1),
            }
        )
    return columns


def _normalize_rows(
    value: Any,
    columns: list[dict[str, Any]],
    *,
    index: int,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"blocks[{index}].rows must be a non-empty list")
    column_keys = [column["key"] for column in columns]
    rows: list[dict[str, str]] = []
    for row_index, raw_row in enumerate(value):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"blocks[{index}].rows[{row_index}] must be a mapping")
        rows.append({key: _normalize_table_cell_value(raw_row.get(key, "")) for key in column_keys})
    return rows


def _normalize_table_cell_value(value: Any) -> str:
    if isinstance(value, Mapping):
        text = value.get("text", value.get("value", ""))
        if bool(value.get("preserveWhitespace", False)):
            return str(text or "")
        return normalize_cell_text(text)
    return normalize_cell_text(value)


def _render_block(
    document: HwpxDocument,
    block: Any,
    tokens: Mapping[str, str],
) -> None:
    if isinstance(block, BuilderHeading):
        document.add_paragraph(
            block.text,
            char_pr_id_ref=tokens["heading"],
            inherit_style=False,
        )
        return
    if isinstance(block, BuilderParagraph):
        style = str(block.style or "body")
        document.add_paragraph(
            block.text,
            char_pr_id_ref=tokens.get(style, tokens["body"]),
            inherit_style=False,
        )
        return
    if isinstance(block, BuilderBullet):
        for item in block.items:
            document.add_paragraph(
                f"• {item}",
                char_pr_id_ref=tokens["bullet"],
                inherit_style=False,
            )
        return
    if isinstance(block, BuilderTable):
        _add_builder_table(document, block, tokens)
        return
    if isinstance(block, DocumentBlock) and block.type == "memo":
        paragraph = document.add_paragraph(
            str(block.data["text"]),
            char_pr_id_ref=tokens["body"],
            inherit_style=False,
        )
        document.add_memo_with_anchor(str(block.data["memo"]), paragraph=paragraph)
        return
    if isinstance(block, BuilderPageBreak):
        document.add_paragraph("", pageBreak="1", inherit_style=False)
        return
    raise ValueError(f"unsupported builder block: {type(block).__name__}")


def _add_key_value_table(
    document: HwpxDocument,
    metadata: Mapping[str, str],
    tokens: Mapping[str, str],
) -> None:
    rows = [
        {"key": _metadata_label(key), "value": value}
        for key, value in metadata.items()
    ]
    block = {
        "caption": "",
        "columns": [
            {"key": "key", "label": "항목", "widthWeight": 1},
            {"key": "value", "label": "내용", "widthWeight": 2},
        ],
        "rows": rows,
    }
    _add_plan_table(document, block, tokens)


def _metadata_label(key: str) -> str:
    return _METADATA_LABELS.get(key, key)


def _add_plan_table(
    document: HwpxDocument,
    block: Mapping[str, Any],
    tokens: Mapping[str, str],
) -> None:
    caption = str(block.get("caption") or "").strip()
    if caption:
        document.add_paragraph(
            caption,
            char_pr_id_ref=tokens["heading"],
            inherit_style=False,
        )
    columns = list(block["columns"])
    rows = list(block["rows"])
    table = document.add_table(
        len(rows) + 1,
        len(columns),
        width=_DEFAULT_TABLE_WIDTH,
        char_pr_id_ref=tokens["table_cell"],
    )
    _apply_column_widths(table, columns)
    for col_index, column in enumerate(columns):
        _set_table_cell_text(
            table,
            0,
            col_index,
            str(column["label"]),
            char_pr_id_ref=tokens["table_header"],
        )
    for row_index, row in enumerate(rows, start=1):
        for col_index, column in enumerate(columns):
            _set_table_cell_text(
                table,
                row_index,
                col_index,
                str(row.get(column["key"], "")),
                char_pr_id_ref=tokens["table_cell"],
            )


def _add_builder_table(
    document: HwpxDocument,
    table_node: BuilderTable,
    tokens: Mapping[str, str],
) -> None:
    rows = [list(table_node.header), *(list(row) for row in table_node.rows)]
    if not rows:
        raise ValueError("table must contain a header or at least one row")
    column_count = max(len(row) for row in rows)
    table = document.add_table(
        len(rows),
        column_count,
        width=_DEFAULT_TABLE_WIDTH,
        char_pr_id_ref=tokens["table_cell"],
    )
    if table_node.column_widths:
        for row in table.rows:
            for col_index, cell in enumerate(row.cells):
                if col_index < len(table_node.column_widths):
                    cell.set_size(width=int(table_node.column_widths[col_index]))
    for col_index, label in enumerate(table_node.header):
        _set_table_cell_text(
            table,
            0,
            col_index,
            str(label),
            char_pr_id_ref=tokens["table_header"],
        )
    row_offset = 1 if table_node.header else 0
    for row_index, row in enumerate(table_node.rows, start=row_offset):
        for col_index, value in enumerate(row):
            _set_table_cell_text(
                table,
                row_index,
                col_index,
                str(value),
                char_pr_id_ref=tokens["table_cell"],
            )


def _set_table_cell_text(
    table: Any,
    row_index: int,
    col_index: int,
    text: str,
    *,
    char_pr_id_ref: str,
) -> None:
    table.set_cell_text(row_index, col_index, text)
    cell = table.cell(row_index, col_index)
    for paragraph in cell.paragraphs:
        paragraph.char_pr_id_ref = char_pr_id_ref


def _apply_column_widths(table: Any, columns: list[dict[str, Any]]) -> None:
    total = sum(max(int(column.get("widthWeight", 1)), 1) for column in columns)
    if total <= 0:
        return
    widths = [
        round(_DEFAULT_TABLE_WIDTH * max(int(column.get("widthWeight", 1)), 1) / total)
        for column in columns
    ]
    if widths:
        widths[-1] += _DEFAULT_TABLE_WIDTH - sum(widths)
    for row in table.rows:
        for col_index, cell in enumerate(row.cells):
            if col_index < len(widths):
                cell.set_size(width=widths[col_index])


def _default_quality_gates() -> dict[str, Any]:
    return {
        "validatePackage": True,
        "validateDocument": True,
        "reopen": True,
        "minNonEmptyParagraphs": 1,
        "minTableCount": 0,
        "requiredText": [],
        "visualReviewRequired": True,
    }


def _evaluate_quality_gates(
    gates: Mapping[str, Any],
    *,
    package_ok: bool,
    document_ok: bool,
    reopened: bool,
    non_empty_paragraph_count: int,
    table_count: int,
    full_text: str,
) -> dict[str, bool]:
    min_paragraphs = _int_value(gates.get("minNonEmptyParagraphs", 1), default=1)
    min_tables = _int_value(gates.get("minTableCount", 0), default=0)
    required_text = _string_list(gates.get("requiredText") or [])
    return {
        "validatePackage": (not gates.get("validatePackage", True)) or package_ok,
        "validateDocument": (not gates.get("validateDocument", True)) or document_ok,
        "reopen": (not gates.get("reopen", True)) or reopened,
        "minNonEmptyParagraphs": non_empty_paragraph_count >= min_paragraphs,
        "minTableCount": table_count >= min_tables,
        "requiredText": all(text in full_text for text in required_text),
        "visualReviewRequired": bool(gates.get("visualReviewRequired", True)),
    }


def _block_counts(plan: DocumentPlan | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if plan is None:
        return counts
    for block in plan.blocks:
        counts[block.type] = counts.get(block.type, 0) + 1
    return counts


def _style_usage(document: HwpxDocument) -> dict[str, Any]:
    used_ids: set[str] = set()
    for run in _iter_runs_deep(document):
        value = getattr(run, "char_pr_id_ref", None)
        if value is not None:
            used_ids.add(str(value))
    return {
        "used_run_style_ids": sorted(used_ids),
        "used_run_style_count": len(used_ids),
        "available_char_style_count": len(document.char_properties),
    }


def _content_evidence(gates: Mapping[str, Any], *, full_text: str) -> dict[str, Any]:
    required_text = _string_list(gates.get("requiredText") or [])
    return {
        "text_char_count": len(full_text),
        "required_text": [
            {"text": text, "present": text in full_text}
            for text in required_text
        ],
    }


def _profile_reports(
    document: HwpxDocument,
    *,
    normalized_plan: DocumentPlan | None,
    quality_profile: str | Mapping[str, Any] | None,
) -> dict[str, Any]:
    profile_name = _requested_profile_name(
        quality_profile,
        normalized_plan=normalized_plan,
    )
    if profile_name != "operating_plan":
        return {}

    profile_options = quality_profile if isinstance(quality_profile, Mapping) else None
    return {
        "operating_plan": _inspect_operating_plan_quality(
            document,
            normalized_plan=normalized_plan,
            profile=profile_options,
        )
    }


def _requested_profile_name(
    quality_profile: str | Mapping[str, Any] | None,
    *,
    normalized_plan: DocumentPlan | None,
) -> str | None:
    if isinstance(quality_profile, str):
        value = quality_profile.strip().lower().replace("-", "_")
        return value or None
    if isinstance(quality_profile, Mapping):
        value = str(
            quality_profile.get("name")
            or quality_profile.get("profile")
            or quality_profile.get("profileName")
            or "operating_plan"
        )
        return value.strip().lower().replace("-", "_") or None
    if normalized_plan is None:
        return None

    document_type = normalized_plan.metadata.get("document_type", "")
    title = normalized_plan.title
    haystack = f"{document_type} {title}".lower()
    if "operating_plan" in haystack or "운영계획서" in haystack:
        return "operating_plan"
    return None


def _inspect_operating_plan_quality(
    document: HwpxDocument,
    *,
    normalized_plan: DocumentPlan | None,
    profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    options = _operating_plan_profile(profile)
    full_text = document.export_text()
    table_text = _table_text(document)
    plan_text = _plan_text(normalized_plan)
    all_text = "\n".join(text for text in (full_text, table_text, plan_text) if text)
    file_lines = _document_text_lines(document)
    table_blocks = (
        _plan_table_blocks(normalized_plan)
        if normalized_plan is not None
        else _document_table_blocks(document)
    )
    non_empty_paragraphs = [
        (paragraph.text or "").strip()
        for paragraph in document.paragraphs
        if (paragraph.text or "").strip()
    ]
    amount_count = len(re.findall(r"\d[\d,]*(?:\.\d+)?\s*(?:원|만원|천원|%)", all_text))

    section_results = {
        name: _contains_any(all_text, values)
        for name, values in options["required_sections"].items()
    }
    front_matter = (
        _front_matter_dimension(normalized_plan, options)
        if normalized_plan is not None
        else _front_matter_from_file_text(file_lines, options)
    )
    dimensions = {
        "front_matter": front_matter,
        "required_outline": _dimension(
            present=all(section_results.values()),
            score=5.0 if all(section_results.values()) else max(
                2.0,
                5.0 * sum(section_results.values()) / len(section_results),
            ),
            metrics={"required_sections": section_results},
            fail_reason="missing required operating-plan sections",
            repair_hint=(
                "Add the missing operating-plan headings and body content: "
                + ", ".join(name for name, present in section_results.items() if not present)
                + "."
            ),
        ),
        "content_density": _dimension(
            present=(
                len(all_text) >= int(options["min_text_chars"])
                and len(non_empty_paragraphs) >= int(options["min_non_empty_paragraphs"])
            ),
            score=5.0
            if len(all_text) >= int(options["min_text_chars"])
            and len(non_empty_paragraphs) >= int(options["min_non_empty_paragraphs"])
            else 3.0,
            metrics={
                "text_char_count": len(all_text),
                "non_empty_paragraph_count": len(non_empty_paragraphs),
                "min_text_chars": int(options["min_text_chars"]),
                "min_non_empty_paragraphs": int(options["min_non_empty_paragraphs"]),
            },
            fail_reason="operating-plan content is too sparse",
            repair_hint="Expand section body text with school context, implementation detail, evidence, and review criteria.",
        ),
        "schedule_table": _schedule_table_dimension(all_text, table_blocks, options),
        "budget_resource_evidence": _budget_dimension(
            all_text,
            table_blocks,
            amount_count=amount_count,
            options=options,
        ),
        "expected_outcomes": _dimension(
            present=_contains_any(all_text, options["expected_outcome_terms"]),
            score=5.0 if _contains_any(all_text, options["expected_outcome_terms"]) else 2.0,
            metrics={"terms": options["expected_outcome_terms"]},
            fail_reason="missing expected outcomes or performance-management evidence",
            repair_hint="Add a 기대 효과/성과 관리 section with measurable outcomes and review evidence.",
        ),
        "closing_material": _dimension(
            present=_contains_any(all_text, options["closing_terms"]),
            score=5.0 if _contains_any(all_text, options["closing_terms"]) else 2.0,
            metrics={"terms": options["closing_terms"]},
            fail_reason="missing closing, submission, review, or confirmation material",
            repair_hint="Add a closing/submission block that states review, confirmation, submission, or signature context.",
        ),
        "placeholder_residue": _placeholder_dimension(all_text, options),
    }
    average = round(
        sum(float(dimension["score"]) for dimension in dimensions.values()) / len(dimensions),
        2,
    )
    gaps = [
        f"{name}: {dimension['reason']}"
        for name, dimension in dimensions.items()
        if dimension["status"] == "fail"
    ]
    repair_hints = [
        {
            "dimension": name,
            "action": "revise",
            "message": str(dimension["repair_hint"]),
        }
        for name, dimension in dimensions.items()
            if dimension["status"] == "fail" and dimension.get("repair_hint")
    ]
    passed = average >= 4.0 and not gaps
    status = "ready" if passed else "needs_revision"
    return {
        "report_version": OPERATING_PLAN_QUALITY_VERSION,
        "profile_version": OPERATING_PLAN_QUALITY_VERSION,
        "profile_name": "operating_plan",
        "status": status,
        "pass": passed,
        "score": average,
        "dimensions": dimensions,
        "gaps": gaps,
        "repair_hints": repair_hints,
        "visual_review_required": True,
        "limitations": [
            "This profile checks deterministic text/table/package proxies only.",
            "Submission-quality form fit still requires rendered or human visual review.",
        ],
    }


def _document_text_lines(document: HwpxDocument) -> list[str]:
    full_text = document.export_text()
    table_text = _table_text(document)
    lines: list[str] = []
    for chunk in (full_text, table_text):
        for line in str(chunk or "").splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _front_matter_from_file_text(
    lines: list[str],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_lines = lines[:20]
    required_labels = {
        "organization": ["기관", "신청 기관", "신청기관", "소속 기관", "소속기관", "학교명", "학 교 명"],
        "date": ["작성일", "작성 일", "일자", "날짜"],
        "document_type": ["문서 유형", "문서유형", "문서 종류", "문서종류"],
    }
    required_metadata = set(_string_list(options.get("required_metadata") or []))
    metrics = {
        key: _has_front_matter_label_value(evidence_lines, labels)
        for key, labels in required_labels.items()
        if key in required_metadata
    }
    present = bool(metrics) and all(metrics.values())
    return _dimension(
        present=present,
        score=5.0 if present else 2.5,
        metrics={"required_metadata": metrics},
        fail_reason="missing front matter metadata evidence",
        repair_hint="Add visible document metadata near the beginning: 기관, 작성일, and 문서 유형.",
    )


def _has_front_matter_label_value(lines: list[str], labels: list[str]) -> bool:
    return any(_line_starts_with_label_value(line, labels) for line in lines)


def _line_starts_with_label_value(line: str, labels: list[str]) -> bool:
    for label in labels:
        if re.search(rf"^\s*{re.escape(label)}\s*[:：\t -]+\S", line):
            return True
    return False


def _operating_plan_profile(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "required_metadata": ["organization", "date", "document_type"],
        "required_sections": {
            "purpose": ["신청 목적", "운영 목적", "목적"],
            "operating_plan": ["운영 계획", "운영과제", "추진 전략"],
            "schedule_budget": ["추진 일정", "사업비 사용 계획", "예산"],
            "curriculum": ["교육과정", "편제표", "교과"],
            "expected_outcomes": ["기대 효과", "성과 관리", "성과"],
            "closing": ["제출", "확인", "검토", "서명", "마무리"],
        },
        "schedule_terms": ["추진 일정", "기간", "단계", "월"],
        "budget_terms": ["사업비", "예산", "금액", "산출근거", "자원"],
        "expected_outcome_terms": ["기대 효과", "성과 관리", "성과"],
        "closing_terms": ["제출", "확인", "검토", "서명", "마무리"],
        "placeholder_patterns": [
            r"TODO",
            r"TBD",
            r"작성\s*필요",
            r"입력하세요",
            r"□□□□",
            r"○○",
            r"\.\.\.",
            r"\(학교상황",
            r"\(운영\s*목표\)",
        ],
        "min_text_chars": 900,
        "min_non_empty_paragraphs": 12,
        "min_schedule_rows": 3,
        "min_budget_rows": 2,
        "min_amount_mentions": 2,
    }
    if profile:
        for key, value in profile.items():
            if key in {"name", "profile", "profileName"}:
                continue
            normalized_key = _camel_to_snake(str(key))
            if normalized_key in options:
                options[normalized_key] = value
            elif key in options:
                options[str(key)] = value
    return options


def _front_matter_dimension(
    normalized_plan: DocumentPlan | None,
    options: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = normalized_plan.metadata if normalized_plan is not None else {}
    required = _string_list(options.get("required_metadata") or [])
    present = {key: bool(str(metadata.get(key, "")).strip()) for key in required}
    passed = all(present.values()) if present else True
    return _dimension(
        present=passed,
        score=5.0 if passed else max(2.0, 5.0 * sum(present.values()) / max(1, len(present))),
        metrics={"required_metadata": present},
        fail_reason="missing required front-matter metadata",
        repair_hint="Fill operating-plan metadata such as organization, date, and document_type before generation.",
    )


def _schedule_table_dimension(
    all_text: str,
    table_blocks: list[Mapping[str, Any]],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    min_rows = int(options["min_schedule_rows"])
    matching_table = _find_plan_table(table_blocks, options["schedule_terms"])
    row_count = len(matching_table.get("rows", [])) if matching_table is not None else 0
    fallback_present = _contains_any(all_text, options["schedule_terms"])
    passed = matching_table is not None and row_count >= min_rows
    return _dimension(
        present=passed,
        score=5.0 if passed else (3.0 if fallback_present else 2.0),
        metrics={
            "has_schedule_terms": fallback_present,
            "table_row_count": row_count,
            "plan_table_row_count": row_count,
            "min_schedule_rows": min_rows,
        },
        fail_reason="missing schedule table with enough execution rows",
        repair_hint="Add a 추진 일정 table with preparation, operation, and evaluation rows including period/activity/owner.",
    )


def _budget_dimension(
    all_text: str,
    table_blocks: list[Mapping[str, Any]],
    *,
    amount_count: int,
    options: Mapping[str, Any],
) -> dict[str, Any]:
    min_rows = int(options["min_budget_rows"])
    min_amounts = int(options["min_amount_mentions"])
    matching_table = _find_plan_table(table_blocks, options["budget_terms"])
    row_count = len(matching_table.get("rows", [])) if matching_table is not None else 0
    has_terms = _contains_any(all_text, options["budget_terms"])
    passed = matching_table is not None and row_count >= min_rows and amount_count >= min_amounts
    return _dimension(
        present=passed,
        score=5.0 if passed else (3.0 if matching_table is not None or has_terms else 2.0),
        metrics={
            "has_budget_terms": has_terms,
            "table_row_count": row_count,
            "plan_table_row_count": row_count,
            "amount_mentions": amount_count,
            "min_budget_rows": min_rows,
            "min_amount_mentions": min_amounts,
        },
        fail_reason="missing budget/resource evidence with amounts and calculation basis",
        repair_hint="Add a 사업비/예산 table with item, amount, ratio or calculation-basis rows.",
    )


def _placeholder_dimension(
    all_text: str,
    options: Mapping[str, Any],
) -> dict[str, Any]:
    patterns = _string_list(options.get("placeholder_patterns") or [])
    hits = [
        pattern
        for pattern in patterns
        if re.search(pattern, all_text, flags=re.IGNORECASE)
    ]
    return _dimension(
        present=not hits,
        score=5.0 if not hits else 1.5,
        metrics={"matched_patterns": hits},
        fail_reason="template placeholders or drafting markers remain",
        repair_hint="Replace placeholder text with final school-specific content before handoff.",
    )


def _dimension(
    *,
    present: bool,
    score: float,
    metrics: Mapping[str, Any],
    fail_reason: str,
    repair_hint: str,
) -> dict[str, Any]:
    return {
        "status": "pass" if present else "fail",
        "score": round(score, 2),
        "metrics": dict(metrics),
        "reason": "" if present else fail_reason,
        "repair_hint": "" if present else repair_hint,
    }


def _plan_table_blocks(normalized_plan: DocumentPlan | None) -> list[Mapping[str, Any]]:
    if normalized_plan is None:
        return []
    return [
        block.data
        for block in normalized_plan.blocks
        if block.type == "table"
    ]


def _find_plan_table(
    table_blocks: list[Mapping[str, Any]],
    terms: Any,
) -> Mapping[str, Any] | None:
    for block in table_blocks:
        blob = _table_block_text(block)
        if _contains_any(blob, terms):
            return block
    return None


def _table_block_text(block: Mapping[str, Any]) -> str:
    parts = [str(block.get("caption") or "")]
    for column in block.get("columns", []):
        if isinstance(column, Mapping):
            parts.extend([str(column.get("key") or ""), str(column.get("label") or "")])
    for row in block.get("rows", []):
        if isinstance(row, Mapping):
            parts.extend(str(value) for value in row.values())
    parts.append(str(block.get("unit") or ""))
    return "\n".join(parts)


def _plan_text(normalized_plan: DocumentPlan | None) -> str:
    if normalized_plan is None:
        return ""
    parts = [normalized_plan.title, normalized_plan.subtitle]
    parts.extend(normalized_plan.metadata.values())
    for block in normalized_plan.blocks:
        if block.type in {"heading", "paragraph", "memo"}:
            parts.extend(str(value) for value in block.data.values())
        elif block.type == "bullets":
            parts.extend(str(item) for item in block.data.get("items", []))
        elif block.type == "table":
            parts.append(_table_block_text(block.data))
    return "\n".join(part for part in parts if part)


def _document_table_blocks(document: HwpxDocument) -> list[Mapping[str, Any]]:
    blocks: list[Mapping[str, Any]] = []
    previous_text = ""
    for paragraph in document.paragraphs:
        tables = list(getattr(paragraph, "tables", []))
        if tables:
            for table in tables:
                text_rows = [
                    [
                        _document_table_cell_text(cell)
                        for cell in getattr(row, "cells", [])
                    ]
                    for row in getattr(table, "rows", [])
                ]
                text_rows = [row for row in text_rows if any(cell.strip() for cell in row)]
                max_column_count = max((len(row) for row in text_rows), default=0)
                header_row = text_rows[0] if _looks_like_table_header_row(text_rows) else []
                data_rows = text_rows[1:] if header_row else text_rows
                columns = [
                    {
                        "key": f"col{index}",
                        "label": (
                            header_row[index]
                            if index < len(header_row)
                            else f"col{index}"
                        ),
                    }
                    for index in range(max_column_count)
                ]
                rows = [
                    {f"col{index}": text for index, text in enumerate(row)}
                    for row in data_rows
                ]
                blocks.append(
                    {
                        "caption": previous_text,
                        "columns": columns,
                        "rows": rows,
                    }
                )
            previous_text = ""
            continue

        text = str(getattr(paragraph, "text", "") or "").strip()
        if text:
            if _looks_like_unit_text(text):
                previous_text = ""
                continue
            previous_text = text
    return blocks


def _looks_like_unit_text(text: str) -> bool:
    return text.startswith(("단위:", "단위："))


def _looks_like_table_header_row(text_rows: list[list[str]]) -> bool:
    if not text_rows:
        return False
    header_terms = {
        "단계",
        "기간",
        "세부 추진 내용",
        "담당",
        "월",
        "추진 내용",
        "항목",
        "금액",
        "비율",
        "비율(%)",
        "산출근거",
        "내용",
        "구분",
    }
    cells = [cell.strip() for cell in text_rows[0] if cell.strip()]
    hits = sum(
        1
        for cell in cells
        if any(cell == term or (len(term) > 1 and term in cell) for term in header_terms)
    )
    return hits >= 2 or (len(cells) == 1 and hits == 1)


def _document_table_cell_text(cell: Any) -> str:
    parts = [str(getattr(cell, "text", "") or "").strip()]
    for paragraph in getattr(cell, "paragraphs", []):
        text = str(getattr(paragraph, "text", "") or "").strip()
        if text:
            parts.append(text)
    return " ".join(part for part in parts if part)


def _table_text(document: HwpxDocument) -> str:
    parts: list[str] = []
    for table in _iter_tables(document):
        for row in getattr(table, "rows", []):
            for cell in getattr(row, "cells", []):
                parts.append(str(getattr(cell, "text", "") or ""))
                for paragraph in getattr(cell, "paragraphs", []):
                    text = str(getattr(paragraph, "text", "") or "").strip()
                    if text:
                        parts.append(text)
    return "\n".join(parts)


def _contains_any(text: str, terms: Any) -> bool:
    return any(term in text for term in _string_list(terms))


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _iter_runs_deep(document: HwpxDocument) -> list[Any]:
    runs = list(document.iter_runs())
    for table in _iter_tables(document):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    runs.extend(paragraph.runs)
    return runs


def _iter_tables(document: HwpxDocument) -> list[Any]:
    tables = []
    for paragraph in document.paragraphs:
        tables.extend(getattr(paragraph, "tables", []))
    return tables


def _can_reopen(path: Path | None, package_payload: bytes) -> bool:
    try:
        doc = HwpxDocument.open(path if path is not None else package_payload)
        doc.close()
        return True
    except Exception:
        return False


def _report_errors(report: Any) -> list[str]:
    for attr in ("errors", "issues", "messages"):
        value = getattr(report, attr, None)
        if value is None:
            continue
        try:
            return [str(item) for item in value]
        except TypeError:
            return [str(value)]
    return []


def _report_issue_dicts(report: Any, *, kind: str) -> list[dict[str, Any]]:
    value = getattr(report, "issues", None)
    if value is None:
        value = getattr(report, "errors", None)
    if value is None:
        value = getattr(report, "messages", None)
    if value is None:
        return []

    try:
        items = list(value)
    except TypeError:
        items = [value]

    issue_dicts: list[dict[str, Any]] = []
    for item in items:
        message = str(getattr(item, "message", item))
        part = (
            getattr(item, "part_name", None)
            or getattr(item, "part", None)
            or "$"
        )
        entry: dict[str, Any] = {
            "part": str(part),
            "message": message,
            "level": str(getattr(item, "level", "error")),
            "suggestion": _validation_issue_suggestion(
                kind=kind,
                part=str(part),
                message=message,
            ),
        }
        line = getattr(item, "line", None)
        column = getattr(item, "column", None)
        if line is not None:
            entry["line"] = line
        if column is not None:
            entry["column"] = column
        issue_dicts.append(entry)
    return issue_dicts


def _validation_issue_suggestion(*, kind: str, part: str, message: str) -> str:
    haystack = f"{part} {message}".lower()
    if "mimetype" in haystack or "zip_stored" in haystack or "first zip entry" in haystack:
        return "Re-save with python-hwpx or repack so mimetype is first and stored."
    if "manifest" in haystack or "version" in haystack or "content.hpf" in haystack:
        return "Inspect Contents/content.hpf and version.xml references."
    if kind == "schema":
        return "Inspect the reported part and regenerate the affected block from the document plan."
    return "Reopen and save with python-hwpx, then rerun validation."


def _recovery_summary(
    *,
    plan_validation: dict[str, Any] | None,
    package_issues: list[dict[str, Any]],
    document_issues: list[dict[str, Any]],
    gate_results: Mapping[str, bool],
) -> dict[str, Any]:
    repair_hints: list[dict[str, str]] = []
    next_actions: list[str] = []

    if plan_validation is not None:
        repair_hints.extend(plan_validation.get("repairHints", []))
        if not plan_validation.get("ok", False):
            next_actions.append(
                "Repair document_plan using repairHints, then rerun validate_document_plan."
            )

    for issue in package_issues:
        suggestion = str(issue.get("suggestion") or "")
        if suggestion:
            level = str(issue.get("level") or "error")
            repair_hints.append(
                {
                    "path": str(issue.get("part") or "$"),
                    "code": "package_validation_issue",
                    "action": "fix" if level == "error" else "review",
                    "message": suggestion,
                }
            )
    package_error_issues = [
        issue for issue in package_issues if str(issue.get("level") or "error") == "error"
    ]
    package_warning_issues = [
        issue for issue in package_issues if str(issue.get("level") or "error") != "error"
    ]
    if package_error_issues:
        next_actions.append(
            "Resolve package validation issues and rerun inspect_document_authoring_quality."
        )
    elif package_warning_issues:
        next_actions.append("Review package validation warnings before handoff.")

    for issue in document_issues:
        suggestion = str(issue.get("suggestion") or "")
        if suggestion:
            repair_hints.append(
                {
                    "path": str(issue.get("part") or "$"),
                    "code": "schema_validation_issue",
                    "action": "fix",
                    "message": suggestion,
                }
            )
    if document_issues:
        next_actions.append(
            "Resolve schema validation issues by regenerating the affected plan block, then rerun inspection."
        )

    failed_gates = [
        name
        for name, passed in gate_results.items()
        if name != "visualReviewRequired" and not passed
    ]
    if failed_gates:
        next_actions.append(
            "Fix failed quality gates: " + ", ".join(failed_gates) + "."
        )
    if not next_actions:
        next_actions.append(
            "Structural checks passed; complete visual review before handoff if required."
        )

    return {
        "repair_hints": repair_hints,
        "next_actions": next_actions,
    }


def _required_text(raw: Mapping[str, Any], key: str, index: int) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"blocks[{index}].{key} is required")
    return value


def _string_mapping(value: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(item) for key, item in value.items()}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


__all__ = [
    "AUTHORING_REPORT_VERSION",
    "DEFAULT_STYLE_PRESET",
    "DOCUMENT_PLAN_SCHEMA_VERSION",
    "DOCUMENT_PLAN_V2_SCHEMA_VERSION",
    "DocumentBlock",
    "DocumentPlan",
    "DocumentStylePreset",
    "PlanValidationIssue",
    "PlanValidationReport",
    "create_document_from_plan",
    "inspect_document_authoring_quality",
    "inspect_operating_plan_quality",
    "normalize_document_plan",
    "validate_document_plan",
]
