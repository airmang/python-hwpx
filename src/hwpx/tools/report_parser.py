"""Parse pasted government-report text into a document-plan v2 mapping."""

from __future__ import annotations

import re
from typing import Any

from hwpx.authoring import DOCUMENT_PLAN_V2_SCHEMA_VERSION
from hwpx.tools.table_cleanup import normalize_cell_text

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_ROMAN_HEADING_RE = re.compile(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.\s*.+$")
_NUMBER_HEADING_RE = re.compile(r"^\d+\.\s+.+$")
_HANGUL_HEADING_RE = re.compile(r"^[가-힣]\.\s+.+$")
_BULLET_RE = re.compile(r"^(□|○|-|※)\s*(.+)$")


def parse_government_report_text(text: str, *, title: str = "") -> dict[str, Any]:
    """Return a ``hwpx.document_plan.v2`` dict from pasted report text."""

    blocks: list[dict[str, Any]] = []
    bullet_items: list[str] = []
    table_lines: list[list[str]] = []
    table_kind: str | None = None

    def flush_bullets() -> None:
        nonlocal bullet_items
        if bullet_items:
            blocks.append({"type": "bullets", "items": bullet_items})
            bullet_items = []

    def flush_table() -> None:
        nonlocal table_lines, table_kind
        if table_lines:
            blocks.append(
                {
                    "type": "table",
                    "header": table_lines[0],
                    "rows": table_lines[1:],
                }
            )
            table_lines = []
            table_kind = None

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            flush_bullets()
            flush_table()
            continue

        parsed_table = _parse_table_line(line)
        if parsed_table is not None:
            kind, cells = parsed_table
            flush_bullets()
            if table_kind is not None and table_kind != kind:
                flush_table()
            table_kind = kind
            table_lines.append(cells)
            continue

        flush_table()

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            bullet_items.append(normalize_cell_text(bullet_match.group(2)))
            continue

        flush_bullets()

        heading = _parse_heading(line)
        if heading is not None:
            level, heading_text = heading
            blocks.append({"type": "heading", "level": level, "text": heading_text})
            continue

        blocks.append({"type": "paragraph", "text": normalize_cell_text(line)})

    flush_bullets()
    flush_table()

    if not blocks:
        fallback = normalize_cell_text(title) or "본문"
        blocks.append({"type": "paragraph", "text": fallback})

    metadata: dict[str, str] = {}
    normalized_title = normalize_cell_text(title)
    if normalized_title:
        metadata["title"] = normalized_title

    return {
        "schemaVersion": DOCUMENT_PLAN_V2_SCHEMA_VERSION,
        "title": normalized_title,
        "metadata": metadata,
        "sections": [{"blocks": blocks}],
    }


def _parse_heading(line: str) -> tuple[int, str] | None:
    markdown_match = _MARKDOWN_HEADING_RE.match(line)
    if markdown_match:
        return min(len(markdown_match.group(1)), 3), normalize_cell_text(markdown_match.group(2))
    if _ROMAN_HEADING_RE.match(line):
        return 1, normalize_cell_text(line)
    if _NUMBER_HEADING_RE.match(line):
        return 2, normalize_cell_text(line)
    if _HANGUL_HEADING_RE.match(line):
        return 3, normalize_cell_text(line)
    return None


def _parse_table_line(line: str) -> tuple[str, list[str]] | None:
    if "\t" in line:
        cells = [normalize_cell_text(cell) for cell in line.split("\t")]
        cells = _trim_empty_edge_cells(cells)
        return ("tab", cells) if len(cells) >= 2 else None
    if "|" not in line:
        return None
    cells = [normalize_cell_text(cell) for cell in line.split("|")]
    cells = _trim_empty_edge_cells(cells)
    if len(cells) < 2 or _is_markdown_table_separator(cells):
        return None
    return "pipe", cells


def _trim_empty_edge_cells(cells: list[str]) -> list[str]:
    while cells and not cells[0]:
        cells.pop(0)
    while cells and not cells[-1]:
        cells.pop()
    return cells


def _is_markdown_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)
