# SPDX-License-Identifier: Apache-2.0
"""General table calculation helpers."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

TABLE_COMPUTE_REPORT_VERSION = "table-compute-v1"

_NUMERIC_CLEAN_RE = re.compile(r"[,\s원%]")


@dataclass(frozen=True)
class _Column:
    key: str
    label: str
    index: int


@dataclass(frozen=True)
class _NormalizedTable:
    mode: str
    columns: list[_Column]
    rows: list[dict[str, Any]]
    original: Mapping[str, Any] | Sequence[Any]


def table_compute(
    table: Mapping[str, Any] | Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
    *,
    value_columns: Sequence[str | int] | None = None,
    operations: Sequence[str] | None = None,
    append: str = "rows",
    group_by: str | int | None = None,
    label_column: str | int | None = None,
    labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compute sum, average, and subtotal rows or columns for a general table."""

    normalized = _normalize_table(table)
    operation_names = _normalize_operations(operations)
    append_mode = _normalize_append(append)
    label_map = {
        "sum": "합계",
        "average": "평균",
        "subtotal": "소계",
        **{str(key): str(value) for key, value in (labels or {}).items()},
    }
    label_key = _resolve_column(label_column, normalized.columns) if label_column is not None else normalized.columns[0].key
    group_key = _resolve_column(group_by, normalized.columns) if group_by is not None else None
    numeric_keys = _resolve_value_columns(value_columns, normalized, label_key=label_key, group_key=group_key)

    rows = [dict(row) for row in normalized.rows]
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []

    if append_mode in {"columns", "both"}:
        _append_computed_columns(
            rows,
            columns=normalized.columns,
            numeric_keys=numeric_keys,
            operations=operation_names,
            labels=label_map,
            evidence=evidence,
            warnings=warnings,
        )

    if append_mode in {"rows", "both"}:
        rows = _append_computed_rows(
            rows,
            columns=normalized.columns,
            numeric_keys=numeric_keys,
            operations=operation_names,
            label_key=label_key,
            group_key=group_key,
            labels=label_map,
            evidence=evidence,
            warnings=warnings,
        )

    computed = _restore_table(normalized, rows)
    return {
        "report_version": TABLE_COMPUTE_REPORT_VERSION,
        "ok": not warnings,
        "computedTable": computed,
        "operations": operation_names,
        "append": append_mode,
        "valueColumns": numeric_keys,
        "groupBy": group_key,
        "evidence": evidence,
        "warnings": warnings,
    }


def _normalize_operations(operations: Sequence[str] | None) -> list[str]:
    raw = operations or ("sum",)
    normalized: list[str] = []
    aliases = {"avg": "average", "mean": "average", "total": "sum", "sub_total": "subtotal"}
    for item in raw:
        op = aliases.get(str(item).strip().lower().replace("-", "_"), str(item).strip().lower().replace("-", "_"))
        if op not in {"sum", "average", "subtotal"}:
            raise ValueError(f"unsupported table operation: {item!r}")
        if op not in normalized:
            normalized.append(op)
    return normalized


def _normalize_append(value: str) -> str:
    normalized = str(value or "rows").strip().lower()
    aliases = {"row": "rows", "column": "columns", "cols": "columns"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"rows", "columns", "both"}:
        raise ValueError("append must be rows, columns, or both")
    return normalized


def _normalize_table(
    table: Mapping[str, Any] | Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
) -> _NormalizedTable:
    if isinstance(table, Mapping):
        if "columns" in table:
            columns = [
                _Column(
                    key=str(column.get("key") or column.get("label") or index),
                    label=str(column.get("label") or column.get("key") or index),
                    index=index,
                )
                for index, column in enumerate(table.get("columns") or [])
                if isinstance(column, Mapping)
            ]
            rows = [
                {column.key: row.get(column.key, "") for column in columns}
                for row in table.get("rows") or []
                if isinstance(row, Mapping)
            ]
            return _NormalizedTable("plan_columns", columns, rows, table)
        if "header" in table:
            header = [str(item) for item in table.get("header") or []]
            columns = [_Column(key=label or str(index), label=label or str(index), index=index) for index, label in enumerate(header)]
            rows = [_row_sequence_to_mapping(row, columns) for row in table.get("rows") or []]
            return _NormalizedTable("plan_header", columns, rows, table)
        if "rows" in table:
            return _normalize_table(table.get("rows") or [])
        raise ValueError("table mapping must contain columns, header, or rows")

    rows_list = list(table)
    if not rows_list:
        raise ValueError("table must contain at least one row")
    if all(isinstance(row, Mapping) for row in rows_list):
        keys: OrderedDict[str, None] = OrderedDict()
        for row in rows_list:
            for key in row.keys():  # type: ignore[union-attr]
                keys.setdefault(str(key), None)
        columns = [_Column(key=key, label=key, index=index) for index, key in enumerate(keys)]
        rows = [
            {column.key: row.get(column.key, "") for column in columns}  # type: ignore[union-attr]
            for row in rows_list
        ]
        return _NormalizedTable("rows_mapping", columns, rows, rows_list)

    first = rows_list[0]
    if not isinstance(first, Sequence) or isinstance(first, (str, bytes, bytearray)):
        raise TypeError("table rows must be mappings or sequences")
    width = max(len(row) for row in rows_list if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)))
    columns = [_Column(key=str(index), label=str(index), index=index) for index in range(width)]
    rows = [_row_sequence_to_mapping(row, columns) for row in rows_list]  # type: ignore[arg-type]
    return _NormalizedTable("rows_sequence", columns, rows, rows_list)


def _row_sequence_to_mapping(row: Sequence[Any], columns: Sequence[_Column]) -> dict[str, Any]:
    return {
        column.key: row[column.index] if column.index < len(row) else ""
        for column in columns
    }


def _resolve_value_columns(
    value_columns: Sequence[str | int] | None,
    table: _NormalizedTable,
    *,
    label_key: str,
    group_key: str | None,
) -> list[str]:
    if value_columns:
        return [_resolve_column(column, table.columns) for column in value_columns]
    skipped = {label_key}
    if group_key:
        skipped.add(group_key)
    detected: list[str] = []
    for column in table.columns:
        if column.key in skipped:
            continue
        if any(_to_decimal(row.get(column.key)) is not None for row in table.rows):
            detected.append(column.key)
    if not detected:
        raise ValueError("no numeric value columns were found")
    return detected


def _resolve_column(value: str | int, columns: Sequence[_Column]) -> str:
    if isinstance(value, int):
        for column in columns:
            if column.index == value:
                return column.key
        raise ValueError(f"column index out of range: {value}")
    text = str(value)
    for column in columns:
        if text in {column.key, column.label, str(column.index)}:
            return column.key
    raise ValueError(f"unknown table column: {value!r}")


def _append_computed_columns(
    rows: list[dict[str, Any]],
    *,
    columns: list[_Column],
    numeric_keys: Sequence[str],
    operations: Sequence[str],
    labels: Mapping[str, str],
    evidence: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    for op in operations:
        if op == "subtotal":
            continue
        key = _unique_column_key(labels[op], columns, rows)
        columns.append(_Column(key=key, label=labels[op], index=len(columns)))
        for row_index, row in enumerate(rows):
            values = _numeric_values(row, numeric_keys, row_index=row_index, warnings=warnings)
            result = _calculate(op, values)
            row[key] = _format_decimal(result) if result is not None else ""
            evidence.append(
                {
                    "operation": op,
                    "axis": "columns",
                    "rowIndex": row_index,
                    "sourceColumns": list(numeric_keys),
                    "resultColumn": key,
                    "sourceValueCount": len(values),
                    "result": row[key],
                }
            )


def _append_computed_rows(
    source_rows: list[dict[str, Any]],
    *,
    columns: Sequence[_Column],
    numeric_keys: Sequence[str],
    operations: Sequence[str],
    label_key: str,
    group_key: str | None,
    labels: Mapping[str, str],
    evidence: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    rows = list(source_rows)
    if "subtotal" in operations and group_key:
        rows = _insert_subtotal_rows(
            rows,
            columns=columns,
            numeric_keys=numeric_keys,
            label_key=label_key,
            group_key=group_key,
            label=labels["subtotal"],
            evidence=evidence,
            warnings=warnings,
        )
    elif "subtotal" in operations:
        warnings.append("subtotal requested without group_by")

    summary_rows: list[dict[str, Any]] = []
    for op in operations:
        if op == "subtotal":
            continue
        summary_rows.append(
            _summary_row(
                source_rows,
                columns=columns,
                numeric_keys=numeric_keys,
                operation=op,
                label_key=label_key,
                label=labels[op],
                evidence=evidence,
                warnings=warnings,
            )
        )
    return [*rows, *summary_rows]


def _insert_subtotal_rows(
    rows: list[dict[str, Any]],
    *,
    columns: Sequence[_Column],
    numeric_keys: Sequence[str],
    label_key: str,
    group_key: str,
    label: str,
    evidence: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current_group: Any = object()
    group_rows: list[dict[str, Any]] = []
    group_start = 0

    def flush(group: Any) -> None:
        if not group_rows:
            return
        subtotal = _blank_row(columns)
        subtotal[label_key] = f"{group} {label}".strip()
        if group_key != label_key:
            subtotal[group_key] = group
        for key in numeric_keys:
            values = _numeric_values(group_rows, [key], row_index=group_start, warnings=warnings)
            value = _calculate("sum", values)
            subtotal[key] = _format_decimal(value) if value is not None else ""
            evidence.append(
                {
                    "operation": "subtotal",
                    "axis": "rows",
                    "groupBy": group_key,
                    "group": group,
                    "column": key,
                    "sourceRowStart": group_start,
                    "sourceRowCount": len(group_rows),
                    "sourceValueCount": len(values),
                    "result": subtotal[key],
                }
            )
        result.append(subtotal)

    for row_index, row in enumerate(rows):
        group = row.get(group_key, "")
        if group_rows and group != current_group:
            flush(current_group)
            group_rows = []
            group_start = row_index
        if not group_rows:
            current_group = group
            group_start = row_index
        result.append(row)
        group_rows.append(row)
    flush(current_group)
    return result


def _summary_row(
    rows: list[dict[str, Any]],
    *,
    columns: Sequence[_Column],
    numeric_keys: Sequence[str],
    operation: str,
    label_key: str,
    label: str,
    evidence: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    row = _blank_row(columns)
    row[label_key] = label
    for key in numeric_keys:
        values = _numeric_values(rows, [key], row_index=0, warnings=warnings)
        value = _calculate(operation, values)
        row[key] = _format_decimal(value) if value is not None else ""
        evidence.append(
            {
                "operation": operation,
                "axis": "rows",
                "column": key,
                "sourceRowStart": 0,
                "sourceRowCount": len(rows),
                "sourceValueCount": len(values),
                "result": row[key],
            }
        )
    return row


def _blank_row(columns: Sequence[_Column]) -> dict[str, Any]:
    return {column.key: "" for column in columns}


def _numeric_values(
    rows_or_row: list[dict[str, Any]] | dict[str, Any],
    keys: Sequence[str],
    *,
    row_index: int,
    warnings: list[str],
) -> list[Decimal]:
    rows = rows_or_row if isinstance(rows_or_row, list) else [rows_or_row]
    values: list[Decimal] = []
    for offset, row in enumerate(rows):
        for key in keys:
            value = _to_decimal(row.get(key))
            if value is None:
                if row.get(key) not in (None, ""):
                    warnings.append(f"non-numeric value skipped at row {row_index + offset}, column {key}")
                continue
            values.append(value)
    return values


def _calculate(operation: str, values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    total = sum(values, Decimal("0"))
    if operation == "sum":
        return total
    if operation == "average":
        return total / Decimal(len(values))
    raise ValueError(f"unsupported calculation: {operation}")


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    text = _NUMERIC_CLEAN_RE.sub("", str(value))
    if text == "":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return f"{int(normalized):,}"
    text = format(normalized, "f").rstrip("0").rstrip(".")
    integer, fraction = text.split(".", 1)
    return f"{int(integer):,}.{fraction}"


def _unique_column_key(label: str, columns: Sequence[_Column], rows: Sequence[Mapping[str, Any]]) -> str:
    base = label or "computed"
    existing = {column.key for column in columns}
    for row in rows:
        existing.update(str(key) for key in row.keys())
    key = base
    counter = 2
    while key in existing:
        key = f"{base}_{counter}"
        counter += 1
    return key


def _restore_table(normalized: _NormalizedTable, rows: list[dict[str, Any]]) -> Any:
    if normalized.mode == "plan_columns":
        original = dict(normalized.original)
        original["columns"] = [
            {"key": column.key, "label": column.label}
            for column in normalized.columns
        ]
        original["rows"] = rows
        return original
    if normalized.mode == "plan_header":
        original = dict(normalized.original)
        original["header"] = [column.label for column in normalized.columns]
        original["rows"] = [[row.get(column.key, "") for column in normalized.columns] for row in rows]
        return original
    if normalized.mode == "rows_sequence":
        return [[row.get(column.key, "") for column in normalized.columns] for row in rows]
    return rows


__all__ = [
    "TABLE_COMPUTE_REPORT_VERSION",
    "table_compute",
]
