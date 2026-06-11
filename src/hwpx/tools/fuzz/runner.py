# SPDX-License-Identifier: Apache-2.0
"""Seeded HWPX fuzz scenario runner and O1/O2 oracle pipeline."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Iterable, Iterator, Mapping, Sequence
from uuid import UUID

from hwpx.builder import Document as BuilderDocument
from hwpx.builder import Footer, Header, Paragraph, Section, Table
from hwpx.document import HwpxDocument
from hwpx.tools.id_integrity import check_id_integrity
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools.roundtrip_diff import roundtrip_report

from .catalog import (
    REPORT_SCHEMA_VERSION,
    REGRESSION_META_SCHEMA_VERSION,
    canonical_json_bytes,
    derive_expected,
    normalize_scenario,
    scenario_digest,
)
from .generator import generate_scenario


@dataclass(frozen=True)
class FuzzRunResult:
    """Result of one scenario replay and oracle run."""

    seed: int | None
    scenario_digest: str
    output_path: Path
    ok: bool
    classification: str | None
    oracle_report: dict[str, Any]
    scenario: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "scenarioDigest": self.scenario_digest,
            "outputPath": str(self.output_path),
            "ok": self.ok,
            "classification": self.classification,
            "oracleReport": self.oracle_report,
            "error": self.error,
        }


@contextmanager
def _deterministic_oxml_ids(seed: int | None) -> Iterator[None]:
    import hwpx.oxml.document as oxml_document

    if seed is None:
        yield
        return

    rng = Random(seed)
    original_uuid4 = oxml_document.uuid4

    def deterministic_uuid4() -> UUID:
        return UUID(int=rng.getrandbits(128))

    oxml_document.uuid4 = deterministic_uuid4
    try:
        yield
    finally:
        oxml_document.uuid4 = original_uuid4


@contextmanager
def _quiet_package_fallback_warnings() -> Iterator[None]:
    logger = logging.getLogger("hwpx.opc.package")
    old_level = logger.level
    if old_level < logging.ERROR:
        logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(old_level)


def _body_tables(document: HwpxDocument) -> list[Any]:
    tables: list[Any] = []
    for paragraph in document.paragraphs:
        tables.extend(paragraph.tables)
    return tables


def _builder_document(op: Mapping[str, Any]) -> HwpxDocument:
    children: list[Any] = [Paragraph(text=str(text)) for text in op.get("paragraphs") or []]
    table = op.get("table") or {}
    if table:
        children.append(
            Table(
                header=tuple(str(value) for value in table.get("header") or ()),
                rows=tuple(
                    tuple(str(value) for value in row)
                    for row in table.get("rows") or ()
                ),
            )
        )
    header_text = op.get("header")
    footer_text = op.get("footer")
    section = Section(
        children=tuple(children),
        header=Header(children=(Paragraph(text=str(header_text)),)) if header_text else None,
        footer=Footer(children=(Paragraph(text=str(footer_text)),)) if footer_text else None,
    )
    return BuilderDocument(sections=(section,)).lower()


def _apply_operation(document: HwpxDocument | None, op: Mapping[str, Any]) -> HwpxDocument:
    name = str(op.get("op", ""))
    if name == "build_document":
        return _builder_document(op)

    if document is None:
        document = HwpxDocument.new()

    if name == "add_paragraph":
        document.add_paragraph(str(op.get("text", "")))
    elif name == "add_styled_run":
        paragraphs = document.paragraphs
        if not paragraphs:
            raise ValueError("add_styled_run requires at least one paragraph")
        index = int(op.get("paragraph_index", 0)) % len(paragraphs)
        paragraphs[index].add_run(
            str(op.get("text", "")),
            bold=bool(op.get("bold", False)),
            italic=bool(op.get("italic", False)),
            underline=bool(op.get("underline", False)),
            color=op.get("color"),
        )
    elif name == "add_table":
        rows = int(op.get("rows", 0))
        cols = int(op.get("cols", 0))
        table = document.add_table(rows, cols)
        cells = op.get("cells") or []
        for row_index, row in enumerate(cells[:rows]):
            for col_index, text in enumerate(row[:cols]):
                table.set_cell_text(row_index, col_index, str(text))
    elif name == "set_table_cell_text":
        tables = _body_tables(document)
        if not tables:
            raise ValueError("set_table_cell_text requires at least one table")
        table = tables[int(op.get("table_index", 0)) % len(tables)]
        table.set_cell_text(
            int(op.get("row", 0)),
            int(op.get("col", 0)),
            str(op.get("text", "")),
        )
    elif name == "merge_table_cells":
        tables = _body_tables(document)
        if not tables:
            raise ValueError("merge_table_cells requires at least one table")
        table = tables[int(op.get("table_index", 0)) % len(tables)]
        document.merge_table_cells(table, str(op.get("range", "A1:B1")))
    elif name == "replace_text":
        document.replace_text_in_runs(
            str(op.get("search", "")),
            str(op.get("replacement", "")),
            limit=op.get("limit"),
        )
    elif name == "set_header_text":
        document.set_header_text(str(op.get("text", "")), page_type=str(op.get("page_type", "BOTH")))
    elif name == "set_footer_text":
        document.set_footer_text(str(op.get("text", "")), page_type=str(op.get("page_type", "BOTH")))
    elif name == "set_page_margins":
        document.set_page_margins(
            left=int(op.get("left", 0)),
            right=int(op.get("right", 0)),
            top=int(op.get("top", 0)),
            bottom=int(op.get("bottom", 0)),
        )
    elif name == "add_memo":
        document.add_memo_with_anchor(
            str(op.get("text", "")),
            paragraph_text=str(op.get("anchor_text", "")),
            memo_id=str(op.get("memo_id", "")),
            field_id=str(op.get("field_id", "")),
            created=str(op.get("created", "2026-06-11 09:00:00")),
            author=str(op.get("author", "seed-fuzzer")),
        )
    else:
        raise ValueError(f"unknown fuzz operation: {name!r}")
    return document


def _write_scenario(path: Path, scenario: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(scenario) + b"\n")


def _id_integrity_dict(document: HwpxDocument) -> dict[str, Any]:
    report = check_id_integrity(document)
    return {
        "ok": report.ok,
        "dangling": [str(item) for item in report.dangling],
        "orphanBinData": [str(item) for item in report.orphan_bin_data],
        "ignored": [str(item) for item in report.ignored],
    }


def _run_o1_o2(path: Path, scenario: Mapping[str, Any]) -> tuple[bool, str | None, dict[str, Any]]:
    open_safety = validate_editor_open_safety(path)
    reopened_document = HwpxDocument.open(path)
    try:
        id_integrity = _id_integrity_dict(reopened_document)
        exported_text = reopened_document.export_text()
        roundtrip = roundtrip_report(path)
    finally:
        reopened_document.close()

    expected = dict(scenario.get("expected") or derive_expected(scenario.get("operations") or ()))
    missing_texts = [
        str(text)
        for text in expected.get("texts") or []
        if str(text) and str(text) not in exported_text
    ]
    roundtrip_ok = (
        bool(roundtrip.get("reopened"))
        and not roundtrip.get("lost_elements")
        and not roundtrip.get("added_elements")
    )
    intent_ok = not missing_texts
    o1_ok = bool(open_safety.ok and id_integrity["ok"])
    o2_ok = bool(roundtrip_ok and intent_ok)
    ok = o1_ok and o2_ok
    classification = None
    if not o1_ok:
        classification = "O1"
    elif not o2_ok:
        classification = "F3"
    return ok, classification, {
        "o1": {
            "ok": o1_ok,
            "openSafety": open_safety.to_dict(),
            "idIntegrity": id_integrity,
            "reopen": {"ok": True},
        },
        "o2": {
            "ok": o2_ok,
            "roundtrip": {
                "ok": roundtrip_ok,
                "lostElements": roundtrip.get("lost_elements", {}),
                "addedElements": roundtrip.get("added_elements", {}),
            },
            "intent": {
                "ok": intent_ok,
                "missingTexts": missing_texts,
                "expectedTextCount": len(expected.get("texts") or ()),
            },
        },
    }


def run_scenario(
    scenario: Mapping[str, Any],
    output_path: str | Path,
    *,
    write_scenario_path: str | Path | None = None,
) -> FuzzRunResult:
    """Replay *scenario*, save the HWPX, and apply O1/O2 oracles."""

    normalized = normalize_scenario(scenario)
    seed = normalized.get("seed")
    seed_value = int(seed) if seed is not None else None
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if write_scenario_path is not None:
        _write_scenario(Path(write_scenario_path), normalized)

    digest = scenario_digest(normalized)
    try:
        with _quiet_package_fallback_warnings(), _deterministic_oxml_ids(seed_value):
            document: HwpxDocument | None = None
            for op in normalized.get("operations") or ():
                document = _apply_operation(document, op)
            if document is None:
                document = HwpxDocument.new()
            try:
                document.save_to_path(output)
            finally:
                document.close()
            ok, classification, oracle_report = _run_o1_o2(output, normalized)
        return FuzzRunResult(
            seed=seed_value,
            scenario_digest=digest,
            output_path=output,
            ok=ok,
            classification=classification,
            oracle_report=oracle_report,
            scenario=normalized,
        )
    except Exception as exc:  # noqa: BLE001 - classified and surfaced as evidence
        return FuzzRunResult(
            seed=seed_value,
            scenario_digest=digest,
            output_path=output,
            ok=False,
            classification="F0",
            oracle_report={"o1": {"ok": False}, "o2": {"ok": False}},
            scenario=normalized,
            error=f"{type(exc).__name__}: {exc}",
        )


def _failure_id(result: FuzzRunResult) -> str:
    seed = "unknown" if result.seed is None else f"{result.seed:06d}"
    classification = result.classification or "unknown"
    return f"seed-{seed}-{classification}-{result.scenario_digest[:12]}"


def fossilize_failure(
    result: FuzzRunResult,
    regression_dir: str | Path,
    *,
    resolved: bool = False,
    resolution: str = "",
) -> dict[str, Path]:
    """Write scenario, snapshot, and metadata for a failed run."""

    directory = Path(regression_dir)
    directory.mkdir(parents=True, exist_ok=True)
    failure_id = _failure_id(result)
    scenario_path = directory / f"{failure_id}.scenario.json"
    snapshot_path = directory / f"{failure_id}.hwpx"
    meta_path = directory / f"{failure_id}.meta.json"

    _write_scenario(scenario_path, result.scenario)
    if result.output_path.exists():
        shutil.copyfile(result.output_path, snapshot_path)
    meta = {
        "schemaVersion": REGRESSION_META_SCHEMA_VERSION,
        "id": failure_id,
        "seed": result.seed,
        "scenarioDigest": result.scenario_digest,
        "classification": result.classification,
        "resolved": resolved,
        "resolution": resolution,
        "error": result.error,
        "oracleReport": result.oracle_report,
        "snapshot": snapshot_path.name if snapshot_path.exists() else None,
    }
    meta_path.write_bytes(canonical_json_bytes(meta) + b"\n")
    return {"scenario": scenario_path, "snapshot": snapshot_path, "meta": meta_path}


def select_visual_review_samples(
    results: Sequence[FuzzRunResult],
    *,
    sample_count: int = 20,
) -> list[FuzzRunResult]:
    """Select O1/O2-passing results while spreading operation signatures."""

    passing = [result for result in results if result.ok and result.output_path.exists()]
    by_signature: dict[tuple[str, ...], FuzzRunResult] = {}
    for result in passing:
        operations = tuple(
            sorted({str(op.get("op", "")) for op in result.scenario.get("operations") or ()})
        )
        by_signature.setdefault(operations, result)

    selected: list[FuzzRunResult] = list(by_signature.values())[:sample_count]
    selected_digests = {item.scenario_digest for item in selected}
    for result in passing:
        if len(selected) >= sample_count:
            break
        if result.scenario_digest in selected_digests:
            continue
        selected.append(result)
        selected_digests.add(result.scenario_digest)
    return selected


def _copy_visual_samples(
    selected: Sequence[FuzzRunResult],
    sample_dir: Path,
) -> list[dict[str, Any]]:
    sample_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for result in selected:
        seed = "unknown" if result.seed is None else f"{result.seed:06d}"
        target = sample_dir / f"seed-{seed}-{result.scenario_digest[:12]}.hwpx"
        shutil.copyfile(result.output_path, target)
        scenario_path = sample_dir / f"seed-{seed}-{result.scenario_digest[:12]}.scenario.json"
        _write_scenario(scenario_path, result.scenario)
        rows.append(
            {
                "seed": result.seed,
                "scenarioDigest": result.scenario_digest,
                "file": str(target),
                "scenario": str(scenario_path),
                "operations": [op.get("op") for op in result.scenario.get("operations") or ()],
            }
        )
    return rows


def run_seed_range(
    *,
    start: int,
    count: int,
    output_dir: str | Path,
    report_path: str | Path | None = None,
    regression_dir: str | Path | None = None,
    max_operations: int = 16,
    write_regressions: bool = False,
    sample_count: int = 20,
    sample_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a deterministic seed window and return/write a compact report."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[FuzzRunResult] = []
    failures: list[dict[str, Any]] = []
    for seed in range(start, start + count):
        scenario = generate_scenario(seed, max_operations=max_operations)
        scenario_path = output_root / f"seed-{seed:06d}.scenario.json"
        output_path = output_root / f"seed-{seed:06d}.hwpx"
        result = run_scenario(scenario, output_path, write_scenario_path=scenario_path)
        results.append(result)
        if not result.ok:
            failure = result.to_dict()
            if write_regressions and regression_dir is not None:
                from .minimize import minimize_scenario

                with tempfile.TemporaryDirectory(prefix="hwpx-fuzz-min-") as tmp:
                    minimized = minimize_scenario(
                        result.scenario,
                        lambda candidate: not run_scenario(
                            candidate,
                            Path(tmp) / "candidate.hwpx",
                        ).ok,
                    )
                    minimized_result = run_scenario(
                        minimized,
                        Path(tmp) / "minimized.hwpx",
                    )
                    paths = fossilize_failure(minimized_result, regression_dir)
                    failure["regressionFixture"] = {key: str(value) for key, value in paths.items()}
            failures.append(failure)

    selected = select_visual_review_samples(results, sample_count=sample_count)
    sample_rows: list[dict[str, Any]] = []
    if sample_dir is not None:
        sample_rows = _copy_visual_samples(selected, Path(sample_dir))

    classification_counts: dict[str, int] = {}
    for result in results:
        if result.ok:
            continue
        key = result.classification or "unknown"
        classification_counts[key] = classification_counts.get(key, 0) + 1

    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "seedStart": start,
        "seedCount": count,
        "maxOperations": max_operations,
        "outputDir": str(output_root),
        "okCount": sum(1 for result in results if result.ok),
        "failureCount": len(failures),
        "failureClassifications": classification_counts,
        "failures": failures,
        "visualReviewSampleCount": len(selected),
        "visualReviewSamples": sample_rows
        or [
            {
                "seed": result.seed,
                "scenarioDigest": result.scenario_digest,
                "file": str(result.output_path),
                "operations": [op.get("op") for op in result.scenario.get("operations") or ()],
            }
            for result in selected
        ],
    }
    if report_path is not None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(report) + b"\n")
    return report


def load_scenario(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_regression_scenarios(regression_dir: str | Path) -> Iterable[Path]:
    return sorted(Path(regression_dir).glob("*.scenario.json"))
