# SPDX-License-Identifier: Apache-2.0
"""Seed-deterministic HWPX fuzz scenario generation."""

from __future__ import annotations

from random import Random
from typing import Any

from .catalog import SCENARIO_SCHEMA_VERSION, derive_expected, scenario_digest

_COLORS = ("2F5597", "C00000", "1F7A1F", "6A3D9A", "444444")
_PAGE_TYPES = ("BOTH", "EVEN", "ODD")


def _text(seed: int, label: str, index: int, rng: Random) -> str:
    return f"fuzz_s{seed:06d}_{label}_{index:02d}_{rng.randrange(100000):05d}"


def _table_cells(seed: int, table_index: int, rows: int, cols: int, rng: Random) -> list[list[str]]:
    return [
        [
            _text(seed, f"t{table_index}_r{row}_c{col}", row * cols + col, rng)
            for col in range(cols)
        ]
        for row in range(rows)
    ]


def _initial_builder_op(seed: int, rng: Random) -> dict[str, Any]:
    paragraph_count = 1 + rng.randrange(3)
    paragraphs = [_text(seed, "builder_p", index, rng) for index in range(paragraph_count)]
    op: dict[str, Any] = {
        "op": "build_document",
        "paragraphs": paragraphs,
    }
    if rng.random() < 0.65:
        cols = 2 + rng.randrange(3)
        data_rows = 1 + rng.randrange(3)
        op["table"] = {
            "header": [_text(seed, f"builder_h{col}", col, rng) for col in range(cols)],
            "rows": _table_cells(seed, 0, data_rows, cols, rng),
        }
    if rng.random() < 0.5:
        op["header"] = _text(seed, "builder_header", 0, rng)
    if rng.random() < 0.5:
        op["footer"] = _text(seed, "builder_footer", 0, rng)
    return op


def generate_scenario(seed: int, *, max_operations: int = 16) -> dict[str, Any]:
    """Generate a deterministic JSON-serializable scenario for *seed*."""

    if max_operations < 1:
        raise ValueError("max_operations must be at least 1")

    rng = Random(seed)
    operations: list[dict[str, Any]] = [_initial_builder_op(seed, rng)]
    paragraph_count = len(operations[0].get("paragraphs", ()))
    table_shapes: list[tuple[int, int]] = []
    builder_table = operations[0].get("table")
    if builder_table:
        rows = 0
        if builder_table.get("header"):
            rows += 1
        rows += len(builder_table.get("rows") or [])
        cols = len(builder_table.get("header") or (builder_table.get("rows") or [[]])[0])
        table_shapes.append((rows, cols))

    target_operations = 6 + rng.randrange(max(1, max_operations - 5))
    for index in range(1, target_operations):
        choices = ["add_paragraph", "add_table", "set_header_text", "set_footer_text", "set_page_margins"]
        if paragraph_count:
            choices.extend(["add_styled_run", "replace_text", "add_memo"])
        if table_shapes:
            choices.extend(["set_table_cell_text", "merge_table_cells"])

        choice = rng.choice(choices)
        if choice == "add_paragraph":
            operations.append({"op": choice, "text": _text(seed, "para", index, rng)})
            paragraph_count += 1
        elif choice == "add_styled_run":
            operations.append(
                {
                    "op": choice,
                    "paragraph_index": rng.randrange(max(1, paragraph_count)),
                    "text": _text(seed, "run", index, rng),
                    "bold": bool(rng.randrange(2)),
                    "italic": bool(rng.randrange(2)),
                    "underline": bool(rng.randrange(2)),
                    "color": rng.choice(_COLORS) if rng.random() < 0.7 else None,
                }
            )
        elif choice == "add_table":
            rows = 1 + rng.randrange(4)
            cols = 2 + rng.randrange(3)
            table_index = len(table_shapes)
            operations.append(
                {
                    "op": choice,
                    "rows": rows,
                    "cols": cols,
                    "cells": _table_cells(seed, table_index, rows, cols, rng),
                }
            )
            table_shapes.append((rows, cols))
        elif choice == "set_table_cell_text":
            table_index = rng.randrange(len(table_shapes))
            rows, cols = table_shapes[table_index]
            operations.append(
                {
                    "op": choice,
                    "table_index": table_index,
                    "row": rng.randrange(rows),
                    "col": rng.randrange(cols),
                    "text": _text(seed, "cell_set", index, rng),
                }
            )
        elif choice == "merge_table_cells":
            candidates = [
                table_index
                for table_index, (rows, cols) in enumerate(table_shapes)
                if rows >= 1 and cols >= 2
            ]
            if not candidates:
                continue
            operations.append(
                {
                    "op": choice,
                    "table_index": rng.choice(candidates),
                    "range": "A1:B1",
                }
            )
        elif choice == "replace_text":
            expected_so_far = derive_expected(operations)
            candidates = [text for text in expected_so_far["bodyTexts"] if text]
            if not candidates:
                continue
            search = rng.choice(candidates)
            operations.append(
                {
                    "op": choice,
                    "search": search,
                    "replacement": _text(seed, "replace", index, rng),
                    "limit": 1,
                }
            )
        elif choice == "set_header_text":
            operations.append(
                {
                    "op": choice,
                    "text": _text(seed, "header", index, rng),
                    "page_type": rng.choice(_PAGE_TYPES),
                }
            )
        elif choice == "set_footer_text":
            operations.append(
                {
                    "op": choice,
                    "text": _text(seed, "footer", index, rng),
                    "page_type": rng.choice(_PAGE_TYPES),
                }
            )
        elif choice == "set_page_margins":
            base = 5000 + rng.randrange(6000)
            operations.append(
                {
                    "op": choice,
                    "left": base,
                    "right": base + rng.randrange(1000),
                    "top": base + rng.randrange(1000),
                    "bottom": base + rng.randrange(1000),
                }
            )
        elif choice == "add_memo":
            memo_index = sum(1 for op in operations if op.get("op") == "add_memo")
            operations.append(
                {
                    "op": choice,
                    "text": _text(seed, "memo", index, rng),
                    "anchor_text": _text(seed, "memo_anchor", index, rng),
                    "memo_id": f"memo-{seed:06d}-{memo_index:02d}",
                    "field_id": f"field-{seed:06d}-{memo_index:02d}",
                    "created": f"2026-06-{1 + seed % 28:02d} 09:{memo_index:02d}:00",
                    "author": "seed-fuzzer",
                }
            )

    scenario: dict[str, Any] = {
        "schemaVersion": SCENARIO_SCHEMA_VERSION,
        "seed": seed,
        "operations": operations,
        "expected": derive_expected(operations),
    }
    scenario["scenarioDigest"] = scenario_digest(scenario)
    return scenario
