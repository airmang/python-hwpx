from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument, TextExtractor
from hwpx.tools import collect_metrics, compare_metrics, validate_document, validate_package
from hwpx.tools.archive_cli import pack_hwpx
from hwpx.tools.template_analyzer import TemplateAnalysis, analyze_template, extract_template_parts

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class AutomationOperationError(RuntimeError):
    """Raised when an automation step must fail loudly."""


@dataclass(frozen=True)
class ToggleRule:
    from_text: str
    to_text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToggleRule":
        return cls(
            from_text=str(data["from"]),
            to_text=str(data["to"]),
        )


@dataclass(frozen=True)
class PartReplacement:
    path: str
    search: str
    replacement: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PartReplacement":
        return cls(
            path=str(data["path"]),
            search=str(data["search"]),
            replacement=str(data["replacement"]),
        )


@dataclass(frozen=True)
class ScopedTextExpectation:
    section_index: int
    value: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScopedTextExpectation":
        return cls(
            section_index=int(data["section_index"]),
            value=str(data["value"]),
        )


@dataclass(frozen=True)
class OperationSpec:
    kind: str
    scopes: tuple[str, ...] = ()
    search: str | None = None
    replacement: str | None = None
    limit: int | None = None
    strict: bool = False
    section_indexes: tuple[int, ...] = ()
    toggle_rules: tuple[ToggleRule, ...] = ()
    part_replacements: tuple[PartReplacement, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationSpec":
        return cls(
            kind=str(data["type"]),
            scopes=tuple(str(scope) for scope in data.get("scopes", [])),
            search=str(data["search"]) if "search" in data else None,
            replacement=str(data["replacement"]) if "replacement" in data else None,
            limit=int(data["limit"]) if data.get("limit") is not None else None,
            strict=bool(data.get("strict", False)),
            section_indexes=tuple(int(index) for index in data.get("section_indexes", [])),
            toggle_rules=tuple(
                ToggleRule.from_dict(item) for item in data.get("toggle_rules", [])
            ),
            part_replacements=tuple(
                PartReplacement.from_dict(item) for item in data.get("part_replacements", [])
            ),
        )

    def summary(self) -> str:
        parts = [self.kind]
        if self.scopes:
            parts.append(f"scopes={list(self.scopes)}")
        if self.search is not None:
            parts.append(f"search={self.search!r}")
        if self.replacement is not None:
            parts.append(f"replacement={self.replacement!r}")
        if self.limit is not None:
            parts.append(f"limit={self.limit}")
        if self.section_indexes:
            parts.append(f"section_indexes={list(self.section_indexes)}")
        if self.strict:
            parts.append("strict=True")
        return ", ".join(parts)


@dataclass(frozen=True)
class AssertionSpec:
    expected_replacements: int | None = None
    expected_error: str | None = None
    package_valid: bool = True
    schema_valid: bool = True
    page_guard_pass: bool = False
    metric_fields_unchanged: tuple[str, ...] = ()
    body_contains: tuple[str, ...] = ()
    body_absent: tuple[str, ...] = ()
    table_contains: tuple[str, ...] = ()
    table_absent: tuple[str, ...] = ()
    header_contains: tuple[str, ...] = ()
    header_absent: tuple[str, ...] = ()
    footer_contains: tuple[str, ...] = ()
    footer_absent: tuple[str, ...] = ()
    all_text_contains: tuple[str, ...] = ()
    all_text_absent: tuple[str, ...] = ()
    section_contains: tuple[ScopedTextExpectation, ...] = ()
    section_absent: tuple[ScopedTextExpectation, ...] = ()
    analysis_manifest_path: str | None = None
    extract_metadata_exists: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssertionSpec":
        return cls(
            expected_replacements=(
                int(data["expected_replacements"])
                if data.get("expected_replacements") is not None
                else None
            ),
            expected_error=str(data["expected_error"]) if data.get("expected_error") else None,
            package_valid=bool(data.get("package_valid", True)),
            schema_valid=bool(data.get("schema_valid", True)),
            page_guard_pass=bool(data.get("page_guard_pass", False)),
            metric_fields_unchanged=tuple(str(item) for item in data.get("metric_fields_unchanged", [])),
            body_contains=tuple(str(item) for item in data.get("body_contains", [])),
            body_absent=tuple(str(item) for item in data.get("body_absent", [])),
            table_contains=tuple(str(item) for item in data.get("table_contains", [])),
            table_absent=tuple(str(item) for item in data.get("table_absent", [])),
            header_contains=tuple(str(item) for item in data.get("header_contains", [])),
            header_absent=tuple(str(item) for item in data.get("header_absent", [])),
            footer_contains=tuple(str(item) for item in data.get("footer_contains", [])),
            footer_absent=tuple(str(item) for item in data.get("footer_absent", [])),
            all_text_contains=tuple(str(item) for item in data.get("all_text_contains", [])),
            all_text_absent=tuple(str(item) for item in data.get("all_text_absent", [])),
            section_contains=tuple(
                ScopedTextExpectation.from_dict(item)
                for item in data.get("section_contains", [])
            ),
            section_absent=tuple(
                ScopedTextExpectation.from_dict(item)
                for item in data.get("section_absent", [])
            ),
            analysis_manifest_path=(
                str(data["analysis_manifest_path"])
                if data.get("analysis_manifest_path")
                else None
            ),
            extract_metadata_exists=bool(data.get("extract_metadata_exists", False)),
        )


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    description: str
    operation: OperationSpec
    assertions: AssertionSpec

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioSpec":
        return cls(
            scenario_id=str(data["id"]),
            description=str(data["description"]),
            operation=OperationSpec.from_dict(dict(data["operation"])),
            assertions=AssertionSpec.from_dict(dict(data["assertions"])),
        )


@dataclass(frozen=True)
class ScenarioCase:
    fixture_id: str
    category: str
    fixture_description: str
    package_dir: Path
    scenario: ScenarioSpec

    @property
    def pytest_id(self) -> str:
        return f"{self.fixture_id}:{self.scenario.scenario_id}"


@dataclass(frozen=True)
class OperationReport:
    summary: str
    replacements: int
    hits: tuple[str, ...]


@dataclass(frozen=True)
class DocumentSnapshot:
    body_text: str
    table_text: str
    header_text: str
    footer_text: str
    all_text: str
    section_texts: tuple[str, ...]
    metrics: Any
    package_report: Any
    schema_report: Any


@dataclass(frozen=True)
class ScenarioRunResult:
    case: ScenarioCase
    reference_path: Path
    output_path: Path | None
    reference_metrics: Any
    operation_report: OperationReport | None
    snapshot: DocumentSnapshot | None
    page_guard_errors: tuple[str, ...]
    error_message: str | None
    analysis: TemplateAnalysis | None
    extract_metadata_path: Path | None


def normalize_whitespace(value: str) -> str:
    return "".join(value.split())


def find_normalized_range(text: str, query: str) -> tuple[int, int] | None:
    normalized_query = normalize_whitespace(query)
    if not normalized_query:
        raise ValueError("query must contain at least one non-whitespace character")

    normalized_chars: list[str] = []
    index_map: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        normalized_chars.append(char)
        index_map.append(index)

    normalized_text = "".join(normalized_chars)
    start = normalized_text.find(normalized_query)
    if start == -1:
        return None
    end = start + len(normalized_query) - 1
    return index_map[start], index_map[end] + 1


def load_scenario_cases(fixtures_root: Path = FIXTURE_ROOT) -> list[ScenarioCase]:
    cases: list[ScenarioCase] = []
    for scenario_path in sorted(fixtures_root.glob("*/scenario.json")):
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
        fixture_id = str(payload["fixture_id"])
        category = str(payload["category"])
        fixture_description = str(payload["description"])
        package_dir = scenario_path.parent / "package"
        for scenario_payload in payload.get("scenarios", []):
            cases.append(
                ScenarioCase(
                    fixture_id=fixture_id,
                    category=category,
                    fixture_description=fixture_description,
                    package_dir=package_dir,
                    scenario=ScenarioSpec.from_dict(dict(scenario_payload)),
                )
            )
    return cases


def _selected_section_items(document: HwpxDocument, indexes: tuple[int, ...]) -> list[tuple[int, Any]]:
    if not indexes:
        return list(enumerate(document.sections))

    selected: list[tuple[int, Any]] = []
    for index in indexes:
        try:
            selected.append((index, document.sections[index]))
        except IndexError as exc:
            raise AssertionError(f"section index {index} is out of range") from exc
    return selected


def _iter_body_paragraphs(document: HwpxDocument, indexes: tuple[int, ...]) -> list[tuple[str, Any]]:
    targets: list[tuple[str, Any]] = []
    for section_index, section in _selected_section_items(document, indexes):
        for paragraph_index, paragraph in enumerate(section.paragraphs):
            targets.append((f"body[s={section_index},p={paragraph_index}]", paragraph))
    return targets


def _iter_table_paragraphs(document: HwpxDocument, indexes: tuple[int, ...]) -> list[tuple[str, Any]]:
    targets: list[tuple[str, Any]] = []

    def walk_table(table: Any, label_prefix: str) -> None:
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row.cells):
                for paragraph_index, paragraph in enumerate(cell.paragraphs):
                    targets.append(
                        (
                            f"{label_prefix}[r={row_index},c={col_index},p={paragraph_index}]",
                            paragraph,
                        )
                    )
                    for nested_index, nested_table in enumerate(paragraph.tables):
                        walk_table(
                            nested_table,
                            f"{label_prefix}[r={row_index},c={col_index},p={paragraph_index},t={nested_index}]",
                        )

    for section_index, section in _selected_section_items(document, indexes):
        for paragraph_index, paragraph in enumerate(section.paragraphs):
            for table_index, table in enumerate(paragraph.tables):
                walk_table(table, f"table[s={section_index},p={paragraph_index},t={table_index}]")

    return targets


def _iter_headers(document: HwpxDocument, indexes: tuple[int, ...]) -> list[tuple[str, Any]]:
    targets: list[tuple[str, Any]] = []
    for section_index, section in _selected_section_items(document, indexes):
        for wrapper in section.properties.headers:
            targets.append(
                (f"header[s={section_index},page={wrapper.apply_page_type}]", wrapper)
            )
    return targets


def _iter_footers(document: HwpxDocument, indexes: tuple[int, ...]) -> list[tuple[str, Any]]:
    targets: list[tuple[str, Any]] = []
    for section_index, section in _selected_section_items(document, indexes):
        for wrapper in section.properties.footers:
            targets.append(
                (f"footer[s={section_index},page={wrapper.apply_page_type}]", wrapper)
            )
    return targets


def _replace_in_paragraph_runs(
    paragraph: Any,
    search: str,
    replacement: str,
    limit: int | None,
) -> int:
    total = 0
    for run in paragraph.runs:
        remaining = None if limit is None else limit - total
        if remaining is not None and remaining <= 0:
            break
        total += run.replace_text(search, replacement, count=remaining)
    return total


def _replace_in_text_container(
    container: Any,
    search: str,
    replacement: str,
    limit: int | None,
) -> int:
    current = container.text
    matches = current.count(search)
    if matches <= 0:
        return 0
    applied = matches if limit is None else min(matches, limit)
    container.text = current.replace(search, replacement, applied)
    return applied


def _strict_failure_message(operation: OperationSpec, count: int) -> str:
    return f"expected at least 1 replacement for {operation.summary()}, got {count}"


def _apply_token_replace(document: HwpxDocument, operation: OperationSpec) -> OperationReport:
    if not operation.search or operation.replacement is None:
        raise AssertionError("token_replace requires search and replacement")

    total = 0
    hits: list[str] = []
    targets: list[tuple[str, Any]] = []

    if "body" in operation.scopes:
        targets.extend(_iter_body_paragraphs(document, operation.section_indexes))
    if "tables" in operation.scopes:
        targets.extend(_iter_table_paragraphs(document, operation.section_indexes))
    if "headers" in operation.scopes:
        targets.extend(_iter_headers(document, operation.section_indexes))
    if "footers" in operation.scopes:
        targets.extend(_iter_footers(document, operation.section_indexes))

    for label, target in targets:
        remaining = None if operation.limit is None else operation.limit - total
        if remaining is not None and remaining <= 0:
            break
        if hasattr(target, "runs"):
            replaced = _replace_in_paragraph_runs(
                target,
                operation.search,
                operation.replacement,
                remaining,
            )
        else:
            replaced = _replace_in_text_container(
                target,
                operation.search,
                operation.replacement,
                remaining,
            )
        if replaced:
            hits.append(f"{label}:{replaced}")
            total += replaced

    if operation.strict and total == 0:
        raise AutomationOperationError(_strict_failure_message(operation, total))

    return OperationReport(summary=operation.summary(), replacements=total, hits=tuple(hits))


def _replace_first_normalized(text: str, search: str, replacement: str) -> tuple[str, int]:
    span = find_normalized_range(text, search)
    if span is None:
        return text, 0
    start, end = span
    return text[:start] + replacement + text[end:], 1


def _apply_normalized_replace(document: HwpxDocument, operation: OperationSpec) -> OperationReport:
    if not operation.search or operation.replacement is None:
        raise AssertionError("normalized_text_replace requires search and replacement")

    total = 0
    hits: list[str] = []
    targets: list[tuple[str, Any]] = []

    if "body" in operation.scopes:
        targets.extend(_iter_body_paragraphs(document, operation.section_indexes))
    if "tables" in operation.scopes:
        targets.extend(_iter_table_paragraphs(document, operation.section_indexes))
    if "headers" in operation.scopes:
        targets.extend(_iter_headers(document, operation.section_indexes))
    if "footers" in operation.scopes:
        targets.extend(_iter_footers(document, operation.section_indexes))

    for label, target in targets:
        remaining = None if operation.limit is None else operation.limit - total
        if remaining is not None and remaining <= 0:
            break
        updated, replaced = _replace_first_normalized(
            target.text,
            operation.search,
            operation.replacement,
        )
        if replaced:
            target.text = updated
            total += replaced
            hits.append(f"{label}:{replaced}")

    if operation.strict and total == 0:
        raise AutomationOperationError(_strict_failure_message(operation, total))

    return OperationReport(summary=operation.summary(), replacements=total, hits=tuple(hits))


def _apply_toggle_rules(document: HwpxDocument, operation: OperationSpec) -> OperationReport:
    if not operation.toggle_rules:
        raise AssertionError("toggle_symbol requires toggle_rules")

    total = 0
    hits: list[str] = []
    targets: list[tuple[str, Any]] = []

    if "body" in operation.scopes:
        targets.extend(_iter_body_paragraphs(document, operation.section_indexes))
    if "tables" in operation.scopes:
        targets.extend(_iter_table_paragraphs(document, operation.section_indexes))
    if "headers" in operation.scopes:
        targets.extend(_iter_headers(document, operation.section_indexes))
    if "footers" in operation.scopes:
        targets.extend(_iter_footers(document, operation.section_indexes))

    for label, target in targets:
        current = target.text
        replaced_here = 0
        for rule in operation.toggle_rules:
            matches = current.count(rule.from_text)
            if matches <= 0:
                continue
            current = current.replace(rule.from_text, rule.to_text)
            replaced_here += matches
        if replaced_here:
            target.text = current
            total += replaced_here
            hits.append(f"{label}:{replaced_here}")

    if operation.strict and total == 0:
        raise AutomationOperationError(_strict_failure_message(operation, total))

    return OperationReport(summary=operation.summary(), replacements=total, hits=tuple(hits))


def _apply_extract_patch_repack(
    reference_path: Path,
    operation: OperationSpec,
    working_dir: Path,
) -> tuple[Path, OperationReport, TemplateAnalysis, Path]:
    if not operation.part_replacements:
        raise AssertionError("extract_patch_repack requires part_replacements")

    analysis = analyze_template(reference_path)
    extract_dir = working_dir / "extract"
    extract_template_parts(reference_path, extract_dir=extract_dir)
    metadata_path = extract_dir / ".hwpx-pack-metadata.json"

    total = 0
    hits: list[str] = []
    for replacement in operation.part_replacements:
        remaining = None if operation.limit is None else operation.limit - total
        if remaining is not None and remaining <= 0:
            break

        target = extract_dir / replacement.path
        payload = target.read_text(encoding="utf-8")
        matches = payload.count(replacement.search)
        if matches <= 0:
            continue
        applied = matches if remaining is None else min(matches, remaining)
        target.write_text(
            payload.replace(replacement.search, replacement.replacement, applied),
            encoding="utf-8",
        )
        total += applied
        hits.append(f"{replacement.path}:{applied}")

    if operation.strict and total == 0:
        raise AutomationOperationError(_strict_failure_message(operation, total))

    output_path = working_dir / "output.hwpx"
    pack_hwpx(extract_dir, output_path, overwrite=True)
    return (
        output_path,
        OperationReport(summary=operation.summary(), replacements=total, hits=tuple(hits)),
        analysis,
        metadata_path,
    )


def _collect_table_texts(table: Any, sink: list[str]) -> None:
    for row in table.rows:
        for cell in row.cells:
            if cell.text.strip():
                sink.append(cell.text)
            for paragraph in cell.paragraphs:
                for nested in paragraph.tables:
                    _collect_table_texts(nested, sink)


def _collect_snapshot(path: Path) -> DocumentSnapshot:
    document = HwpxDocument.open(path)
    with TextExtractor(path) as extractor:
        body_text = extractor.extract_text(include_nested=False)
        nested_text = extractor.extract_text(include_nested=True)

    table_texts: list[str] = []
    header_texts: list[str] = []
    footer_texts: list[str] = []
    section_texts: list[str] = []

    for section in document.sections:
        section_texts.append(
            "\n".join(paragraph.text for paragraph in section.paragraphs if paragraph.text.strip())
        )
        for paragraph in section.paragraphs:
            for table in paragraph.tables:
                _collect_table_texts(table, table_texts)
        header_texts.extend(
            wrapper.text for wrapper in section.properties.headers if wrapper.text.strip()
        )
        footer_texts.extend(
            wrapper.text for wrapper in section.properties.footers if wrapper.text.strip()
        )

    header_text = "\n".join(header_texts)
    footer_text = "\n".join(footer_texts)
    table_text = "\n".join(table_texts)
    all_text = "\n".join(
        part for part in (nested_text, header_text, footer_text) if part.strip()
    )

    return DocumentSnapshot(
        body_text=body_text,
        table_text=table_text,
        header_text=header_text,
        footer_text=footer_text,
        all_text=all_text,
        section_texts=tuple(section_texts),
        metrics=collect_metrics(path),
        package_report=validate_package(path),
        schema_report=validate_document(path),
    )


def execute_scenario(case: ScenarioCase, tmp_path: Path) -> ScenarioRunResult:
    reference_path = tmp_path / f"{case.fixture_id}-reference.hwpx"
    pack_hwpx(case.package_dir, reference_path, overwrite=True)

    reference_package_report = validate_package(reference_path)
    if not reference_package_report.ok:
        raise AssertionError(
            f"fixture {case.fixture_id} packed into an invalid package: "
            + "; ".join(str(issue) for issue in reference_package_report.issues)
        )

    reference_schema_report = validate_document(reference_path)
    if not reference_schema_report.ok:
        raise AssertionError(
            f"fixture {case.fixture_id} failed schema validation: "
            + "; ".join(str(issue) for issue in reference_schema_report.issues)
        )

    reference_metrics = collect_metrics(reference_path)
    operation = case.scenario.operation
    expected_error = case.scenario.assertions.expected_error

    operation_report: OperationReport | None = None
    output_path: Path | None = None
    analysis: TemplateAnalysis | None = None
    extract_metadata_path: Path | None = None

    try:
        if operation.kind == "extract_patch_repack":
            output_path, operation_report, analysis, extract_metadata_path = _apply_extract_patch_repack(
                reference_path,
                operation,
                tmp_path / "extract-workflow",
            )
        else:
            document = HwpxDocument.open(reference_path)
            if operation.kind == "token_replace":
                operation_report = _apply_token_replace(document, operation)
            elif operation.kind == "normalized_text_replace":
                operation_report = _apply_normalized_replace(document, operation)
            elif operation.kind == "toggle_symbol":
                operation_report = _apply_toggle_rules(document, operation)
            else:
                raise AssertionError(f"unsupported operation kind: {operation.kind}")

            output_path = tmp_path / f"{case.fixture_id}-{case.scenario.scenario_id}.hwpx"
            document.save_to_path(output_path)
    except AutomationOperationError as exc:
        if expected_error is None:
            raise
        return ScenarioRunResult(
            case=case,
            reference_path=reference_path,
            output_path=None,
            reference_metrics=reference_metrics,
            operation_report=operation_report,
            snapshot=None,
            page_guard_errors=(),
            error_message=str(exc),
            analysis=analysis,
            extract_metadata_path=extract_metadata_path,
        )

    snapshot = _collect_snapshot(output_path)
    page_guard_errors: tuple[str, ...] = ()
    if case.scenario.assertions.page_guard_pass:
        page_guard_errors = tuple(compare_metrics(reference_metrics, snapshot.metrics))

    return ScenarioRunResult(
        case=case,
        reference_path=reference_path,
        output_path=output_path,
        reference_metrics=reference_metrics,
        operation_report=operation_report,
        snapshot=snapshot,
        page_guard_errors=page_guard_errors,
        error_message=None,
        analysis=analysis,
        extract_metadata_path=extract_metadata_path,
    )


def _issues_summary(report: Any) -> str:
    issues = getattr(report, "issues", ())
    if not issues:
        return "none"
    return "; ".join(str(issue) for issue in issues)


def _result_context(result: ScenarioRunResult) -> str:
    operation_summary = (
        result.operation_report.summary if result.operation_report is not None else "(none)"
    )
    replacements = (
        str(result.operation_report.replacements)
        if result.operation_report is not None
        else "(none)"
    )
    hits = (
        ", ".join(result.operation_report.hits)
        if result.operation_report is not None and result.operation_report.hits
        else "none"
    )
    package_summary = (
        _issues_summary(result.snapshot.package_report) if result.snapshot is not None else "n/a"
    )
    schema_summary = (
        _issues_summary(result.snapshot.schema_report) if result.snapshot is not None else "n/a"
    )
    page_guard_summary = ", ".join(result.page_guard_errors) if result.page_guard_errors else "pass"
    return (
        f"fixture={result.case.fixture_id} ({result.case.category})\n"
        f"scenario={result.case.scenario.scenario_id}: {result.case.scenario.description}\n"
        f"operation={operation_summary}\n"
        f"replacements={replacements}\n"
        f"hits={hits}\n"
        f"reference={result.reference_path}\n"
        f"output={result.output_path}\n"
        f"error={result.error_message}\n"
        f"package_issues={package_summary}\n"
        f"schema_issues={schema_summary}\n"
        f"page_guard={page_guard_summary}"
    )


def assert_run_result(result: ScenarioRunResult) -> None:
    assertions = result.case.scenario.assertions
    context = _result_context(result)

    if assertions.expected_error is not None:
        assert result.error_message is not None, context
        assert assertions.expected_error in result.error_message, context
        return

    assert result.error_message is None, context
    assert result.output_path is not None, context
    assert result.operation_report is not None, context
    assert result.snapshot is not None, context

    if assertions.expected_replacements is not None:
        assert result.operation_report.replacements == assertions.expected_replacements, context

    assert result.snapshot.package_report.ok is assertions.package_valid, context
    assert result.snapshot.schema_report.ok is assertions.schema_valid, context

    if assertions.page_guard_pass:
        assert not result.page_guard_errors, context

    for field in assertions.metric_fields_unchanged:
        assert getattr(result.reference_metrics, field) == getattr(result.snapshot.metrics, field), (
            f"{context}\nmetric field {field!r} changed: "
            f"ref={getattr(result.reference_metrics, field)!r}, "
            f"out={getattr(result.snapshot.metrics, field)!r}"
        )

    for value in assertions.body_contains:
        assert value in result.snapshot.body_text, context
    for value in assertions.body_absent:
        assert value not in result.snapshot.body_text, context
    for value in assertions.table_contains:
        assert value in result.snapshot.table_text, context
    for value in assertions.table_absent:
        assert value not in result.snapshot.table_text, context
    for value in assertions.header_contains:
        assert value in result.snapshot.header_text, context
    for value in assertions.header_absent:
        assert value not in result.snapshot.header_text, context
    for value in assertions.footer_contains:
        assert value in result.snapshot.footer_text, context
    for value in assertions.footer_absent:
        assert value not in result.snapshot.footer_text, context
    for value in assertions.all_text_contains:
        assert value in result.snapshot.all_text, context
    for value in assertions.all_text_absent:
        assert value not in result.snapshot.all_text, context

    for scoped in assertions.section_contains:
        assert scoped.value in result.snapshot.section_texts[scoped.section_index], context
    for scoped in assertions.section_absent:
        assert scoped.value not in result.snapshot.section_texts[scoped.section_index], context

    if assertions.analysis_manifest_path is not None:
        assert result.analysis is not None, context
        assert result.analysis.manifest_path == assertions.analysis_manifest_path, context

    if assertions.extract_metadata_exists:
        assert result.extract_metadata_path is not None, context
        assert result.extract_metadata_path.is_file(), context
