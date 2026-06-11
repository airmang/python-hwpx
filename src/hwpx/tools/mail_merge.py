# SPDX-License-Identifier: Apache-2.0
"""Batch document generation helpers for HWPX templates."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from ..document import HwpxDocument
from .exporter import export_text
from .package_validator import validate_editor_open_safety

MAIL_MERGE_REPORT_VERSION = "mail-merge-v1"

_PLACEHOLDER_RE = re.compile(
    r"(?P<brace>\{\{\s*(?P<brace_key>[A-Za-z_][A-Za-z0-9_.-]*)\s*\}\})"
    r"|(?P<dollar>\$\{\s*(?P<dollar_key>[A-Za-z_][A-Za-z0-9_.-]*)\s*\})"
    r"|(?P<angle><<\s*(?P<angle_key>[A-Za-z_][A-Za-z0-9_.-]*)\s*>>)"
)
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9가-힣._ -]+")


def load_mail_merge_rows(data: str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Load mail-merge rows from CSV, JSON, or in-memory mappings."""

    if isinstance(data, (str, Path)):
        path = Path(data)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                return [dict(row) for row in csv.DictReader(stream)]
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            return load_mail_merge_rows(payload)
        raise ValueError(f"unsupported mail merge data file: {path}")

    if isinstance(data, Mapping):
        rows = data.get("rows", data.get("data"))
        if rows is None:
            raise ValueError("mail merge data mapping must contain rows or data")
        return load_mail_merge_rows(rows)  # type: ignore[arg-type]

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        if not isinstance(row, Mapping):
            raise TypeError(f"mail merge row {index} must be a mapping")
        rows.append({str(key): value for key, value in row.items()})
    return rows


def inspect_mail_merge_placeholders(source: str | Path | HwpxDocument) -> dict[str, Any]:
    """Return placeholders found in a template document."""

    close_doc = False
    if isinstance(source, HwpxDocument):
        document = source
    else:
        document = HwpxDocument.open(source)
        close_doc = True
    try:
        text = export_text(document)
    finally:
        if close_doc:
            document.close()
    placeholders = _find_placeholders(text)
    keys = sorted({item["key"] for item in placeholders})
    return {
        "report_version": MAIL_MERGE_REPORT_VERSION,
        "placeholderCount": len(placeholders),
        "keys": keys,
        "placeholders": placeholders,
    }


def mail_merge(
    template: str | Path,
    data: str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
    filename_pattern: str = "{index:03d}.hwpx",
    zip_path: str | Path | None = None,
    strict: bool = False,
    split_newlines: bool = True,
) -> dict[str, Any]:
    """Generate one HWPX per row from a placeholder template.

    Supported placeholder forms are ``{{field}}``, ``${field}``, and
    ``<<field>>``. Missing values are reported per row; by default documents are
    still generated so an operator can inspect the partial output. Set
    ``strict=True`` to skip rows with missing required data.
    """

    template_path = Path(template)
    rows = load_mail_merge_rows(data)
    if not rows:
        raise ValueError("mail merge requires at least one data row")

    output_root = Path(output_dir) if output_dir is not None else template_path.with_suffix("").parent / "mail_merge_out"
    output_root.mkdir(parents=True, exist_ok=True)

    placeholder_report = inspect_mail_merge_placeholders(template_path)
    placeholders = list(placeholder_report["placeholders"])
    required_keys = sorted({str(item["key"]) for item in placeholders})

    row_reports: list[dict[str, Any]] = []
    generated_paths: list[Path] = []
    for index, row in enumerate(rows, start=1):
        missing_keys = [key for key in required_keys if _is_missing(row.get(key))]
        filename = _format_filename(filename_pattern, row=row, index=index)
        out_path = output_root / filename
        if out_path.suffix.lower() != ".hwpx":
            out_path = out_path.with_suffix(".hwpx")

        if strict and missing_keys:
            row_reports.append(
                {
                    "rowIndex": index,
                    "filename": str(out_path),
                    "created": False,
                    "replacedCount": 0,
                    "missingKeys": missing_keys,
                    "unresolvedPlaceholders": [item["token"] for item in placeholders if item["key"] in missing_keys],
                    "openSafety": None,
                    "ok": False,
                }
            )
            continue

        document = HwpxDocument.open(template_path)
        replaced_count = 0
        try:
            for placeholder in placeholders:
                key = str(placeholder["key"])
                value = "" if _is_missing(row.get(key)) else str(row.get(key))
                if not split_newlines:
                    value = value.replace("\r\n", " ").replace("\n", " ")
                replaced_count += document.replace_text_in_runs(str(placeholder["token"]), value)
            document.save_to_path(out_path)
        finally:
            document.close()

        open_safety = validate_editor_open_safety(out_path).to_dict()
        unresolved = _unresolved_placeholders(out_path)
        row_ok = bool(open_safety["ok"]) and not missing_keys and not unresolved
        row_reports.append(
            {
                "rowIndex": index,
                "filename": str(out_path),
                "created": True,
                "replacedCount": replaced_count,
                "missingKeys": missing_keys,
                "unresolvedPlaceholders": unresolved,
                "openSafety": open_safety,
                "ok": row_ok,
            }
        )
        generated_paths.append(out_path)

    zip_result: dict[str, Any] | None = None
    if zip_path is not None:
        zip_file = Path(zip_path)
        zip_file.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(zip_file, "w", compression=ZIP_DEFLATED) as archive:
            for path in generated_paths:
                archive.write(path, arcname=path.name)
        zip_result = {
            "path": str(zip_file),
            "entryCount": len(generated_paths),
            "entries": [path.name for path in generated_paths],
        }

    rows_with_issues = [
        report["rowIndex"]
        for report in row_reports
        if report["missingKeys"] or report["unresolvedPlaceholders"] or not (report["openSafety"] or {}).get("ok", False)
    ]
    open_safety = _open_safety_summary(row_reports, created_count=len(generated_paths))
    return {
        "report_version": MAIL_MERGE_REPORT_VERSION,
        "template": str(template_path),
        "outputDir": str(output_root),
        "filenamePattern": filename_pattern,
        "placeholderKeys": required_keys,
        "rowCount": len(rows),
        "createdCount": len(generated_paths),
        "rowsWithIssues": rows_with_issues,
        "ok": not rows_with_issues and len(generated_paths) == len(rows),
        "openSafety": open_safety,
        "verification": {
            "openSafety": open_safety,
            "createdCount": len(generated_paths),
            "rowCount": len(rows),
            "rowsWithIssues": rows_with_issues,
            "zip": zip_result,
        },
        "rows": row_reports,
        "zip": zip_result,
    }


def _find_placeholders(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _PLACEHOLDER_RE.finditer(text):
        key = match.group("brace_key") or match.group("dollar_key") or match.group("angle_key")
        token = match.group(0)
        if not key or (token, key) in seen:
            continue
        seen.add((token, key))
        found.append({"token": token, "key": key})
    return found


def _unresolved_placeholders(path: Path) -> list[str]:
    document = HwpxDocument.open(path)
    try:
        text = export_text(document)
    finally:
        document.close()
    return [item["token"] for item in _find_placeholders(text)]


def _open_safety_summary(row_reports: Sequence[Mapping[str, Any]], *, created_count: int) -> dict[str, Any]:
    checked = 0
    failures: list[dict[str, Any]] = []
    for row in row_reports:
        open_safety = row.get("openSafety")
        if not isinstance(open_safety, Mapping):
            continue
        checked += 1
        if not bool(open_safety.get("ok")):
            failures.append(
                {
                    "rowIndex": row.get("rowIndex"),
                    "filename": row.get("filename"),
                    "summary": open_safety.get("summary"),
                }
            )
    return {
        "ok": checked == created_count and not failures,
        "checkedCount": checked,
        "failureCount": len(failures),
        "failures": failures,
    }


def _is_missing(value: Any) -> bool:
    return value is None or str(value) == ""


def _format_filename(pattern: str, *, row: Mapping[str, Any], index: int) -> str:
    values = _FormatValues(row, index=index)
    try:
        filename = pattern.format_map(values)
    except (KeyError, ValueError):
        filename = f"{index:03d}.hwpx"
    name = Path(str(filename)).name.strip() or f"{index:03d}.hwpx"
    return _SAFE_FILENAME_RE.sub("_", name)


class _FormatValues(dict[str, Any]):
    def __init__(self, row: Mapping[str, Any], *, index: int) -> None:
        super().__init__({str(key): value for key, value in row.items()})
        self["index"] = index
        self["index0"] = index - 1

    def __missing__(self, key: str) -> str:
        return ""


__all__ = [
    "MAIL_MERGE_REPORT_VERSION",
    "inspect_mail_merge_placeholders",
    "load_mail_merge_rows",
    "mail_merge",
]
