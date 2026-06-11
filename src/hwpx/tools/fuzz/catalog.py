# SPDX-License-Identifier: Apache-2.0
"""Operation catalog and scenario normalization for seeded HWPX fuzzing."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCENARIO_SCHEMA_VERSION = "hwpx.fuzz.scenario.v1"
REPORT_SCHEMA_VERSION = "hwpx.fuzz.report.v1"
REGRESSION_META_SCHEMA_VERSION = "hwpx.fuzz.regression-meta.v1"


@dataclass(frozen=True)
class OperationSpec:
    """A public operation surface exercised by the seeded fuzz runner."""

    name: str
    surface: str
    description: str
    parameters: Mapping[str, str]
    preconditions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "surface": self.surface,
            "description": self.description,
            "parameters": dict(self.parameters),
            "preconditions": list(self.preconditions),
        }


_OPERATION_CATALOG: tuple[OperationSpec, ...] = (
    OperationSpec(
        name="build_document",
        surface="hwpx.builder.Document",
        description="Create the initial document with builder paragraphs, optional table, header, and footer.",
        parameters={
            "paragraphs": "list[str]",
            "table": "optional row-major table spec",
            "header": "optional header text",
            "footer": "optional footer text",
        },
    ),
    OperationSpec(
        name="add_paragraph",
        surface="HwpxDocument.add_paragraph",
        description="Append a body paragraph.",
        parameters={"text": "str"},
    ),
    OperationSpec(
        name="add_styled_run",
        surface="HwpxOxmlParagraph.add_run",
        description="Append a styled run to an existing paragraph.",
        parameters={
            "paragraph_index": "int",
            "text": "str",
            "bold": "bool",
            "italic": "bool",
            "underline": "bool",
            "color": "optional RGB hex",
        },
        preconditions=("at least one body paragraph exists",),
    ),
    OperationSpec(
        name="add_table",
        surface="HwpxDocument.add_table",
        description="Append a table and fill every generated cell.",
        parameters={"rows": "int", "cols": "int", "cells": "list[list[str]]"},
    ),
    OperationSpec(
        name="set_table_cell_text",
        surface="HwpxOxmlTable.set_cell_text",
        description="Replace text in an existing table cell.",
        parameters={
            "table_index": "int",
            "row": "int",
            "col": "int",
            "text": "str",
        },
        preconditions=("at least one table exists",),
    ),
    OperationSpec(
        name="merge_table_cells",
        surface="HwpxDocument.merge_table_cells",
        description="Merge a spreadsheet-style rectangular cell range.",
        parameters={"table_index": "int", "range": "str"},
        preconditions=("target table has at least two columns",),
    ),
    OperationSpec(
        name="replace_text",
        surface="HwpxDocument.replace_text_in_runs",
        description="Replace a generated text token in runs.",
        parameters={"search": "str", "replacement": "str", "limit": "optional int"},
        preconditions=("search text exists in at least one run",),
    ),
    OperationSpec(
        name="set_header_text",
        surface="HwpxDocument.set_header_text",
        description="Set section header text.",
        parameters={"text": "str", "page_type": "BOTH|EVEN|ODD"},
    ),
    OperationSpec(
        name="set_footer_text",
        surface="HwpxDocument.set_footer_text",
        description="Set section footer text.",
        parameters={"text": "str", "page_type": "BOTH|EVEN|ODD"},
    ),
    OperationSpec(
        name="set_page_margins",
        surface="HwpxDocument.set_page_margins",
        description="Set deterministic page margins in HWP units.",
        parameters={"left": "int", "right": "int", "top": "int", "bottom": "int"},
    ),
    OperationSpec(
        name="add_memo",
        surface="HwpxDocument.add_memo_with_anchor",
        description="Add a memo with deterministic anchor, memo id, field id, and creation date.",
        parameters={
            "text": "str",
            "anchor_text": "str",
            "memo_id": "str",
            "field_id": "str",
            "created": "YYYY-MM-DD HH:MM:SS",
        },
    ),
)


def operation_catalog() -> tuple[OperationSpec, ...]:
    """Return the immutable operation catalog."""

    return _OPERATION_CATALOG


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return deterministic UTF-8 JSON bytes for *value*."""

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def scenario_digest(scenario: Mapping[str, Any]) -> str:
    """Return a stable digest for the canonical scenario JSON."""

    payload = dict(scenario)
    payload.pop("scenarioDigest", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _text_values(cells: Sequence[Sequence[Any]]) -> list[str]:
    values: list[str] = []
    for row in cells:
        for cell in row:
            text = str(cell)
            if text:
                values.append(text)
    return values


def _replace_all(values: list[str], search: str, replacement: str, limit: int | None) -> list[str]:
    replaced: list[str] = []
    remaining = limit
    for value in values:
        if remaining is not None and remaining <= 0:
            replaced.append(value)
            continue
        count = value.count(search)
        if count <= 0:
            replaced.append(value)
            continue
        if remaining is None:
            replaced.append(value.replace(search, replacement))
            continue
        replacements_here = min(count, remaining)
        replaced.append(value.replace(search, replacement, replacements_here))
        remaining -= replacements_here
    return replaced


def derive_expected(operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive observable text expectations from a scenario operation sequence."""

    body_texts: list[str] = []
    table_cells: list[list[list[str]]] = []
    merged_cells: dict[int, set[tuple[int, int]]] = {}

    for raw_op in operations:
        op = dict(raw_op)
        name = str(op.get("op", ""))
        if name == "build_document":
            for text in op.get("paragraphs") or []:
                if text:
                    body_texts.append(str(text))
            table = op.get("table") or {}
            if table:
                rows: list[list[str]] = []
                header = [str(value) for value in table.get("header") or []]
                if header:
                    rows.append(header)
                for row in table.get("rows") or []:
                    rows.append([str(value) for value in row])
                if rows:
                    table_cells.append(rows)
                    merged_cells[len(table_cells) - 1] = set()
            continue

        if name == "add_paragraph":
            text = str(op.get("text", ""))
            if text:
                body_texts.append(text)
            continue

        if name == "add_styled_run":
            text = str(op.get("text", ""))
            if text:
                body_texts.append(text)
            continue

        if name == "add_table":
            cells = [
                [str(value) for value in row]
                for row in (op.get("cells") or [])
            ]
            if cells:
                table_cells.append(cells)
                merged_cells[len(table_cells) - 1] = set()
            continue

        if name == "set_table_cell_text":
            table_index = int(op.get("table_index", 0))
            row = int(op.get("row", 0))
            col = int(op.get("col", 0))
            if (row, col) in merged_cells.get(table_index, set()):
                row, col = 0, 0
            if (
                0 <= table_index < len(table_cells)
                and 0 <= row < len(table_cells[table_index])
                and 0 <= col < len(table_cells[table_index][row])
            ):
                table_cells[table_index][row][col] = str(op.get("text", ""))
            continue

        if name == "merge_table_cells":
            table_index = int(op.get("table_index", 0))
            cell_range = str(op.get("range", ""))
            if 0 <= table_index < len(table_cells) and cell_range == "A1:B1":
                rows = table_cells[table_index]
                if rows and len(rows[0]) >= 2:
                    rows[0][1] = ""
                    merged_cells.setdefault(table_index, set()).add((0, 1))
            continue

        if name == "replace_text":
            search = str(op.get("search", ""))
            replacement = str(op.get("replacement", ""))
            limit_value = op.get("limit")
            limit = int(limit_value) if limit_value is not None else None
            if search:
                body_texts = _replace_all(body_texts, search, replacement, limit)
            continue

        if name == "add_memo":
            anchor_text = str(op.get("anchor_text", ""))
            if anchor_text:
                body_texts.append(anchor_text)
            continue

    body_expected = [text for text in body_texts if text]
    table_expected: list[str] = []
    for cells in table_cells:
        table_expected.extend(_text_values(cells))

    return {
        "texts": body_expected + table_expected,
        "bodyTexts": body_expected,
        "tableTexts": table_expected,
        "table_count": len(table_cells),
        "catalog_operations": sorted({str(op.get("op", "")) for op in operations if op.get("op")}),
    }


def normalize_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized scenario mapping with expected observations filled in."""

    normalized = deepcopy(dict(scenario))
    normalized.setdefault("schemaVersion", SCENARIO_SCHEMA_VERSION)
    operations = [dict(op) for op in normalized.get("operations") or []]
    normalized["operations"] = operations
    normalized["expected"] = derive_expected(operations)
    return normalized
