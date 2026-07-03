# SPDX-License-Identifier: Apache-2.0
"""Byte-preserving form-fill: address a table cell and splice only its text.

S-064 / M10 (spec ``specs/011-byte-preserving-formfill``). The 2026-07-03 case
study failed because the only byte-preserving entry point
(:func:`hwpx.patch.paragraph_patch`) addresses a flat paragraph index that is
ambiguous inside tables, so an agent could not say "fill cell (r,c) of table T"
and fell back to rebuilding tables (destroying formatting). This module adds
cell addressing on top of the same byte machinery:

* locate the ``N``-th ``<hp:tbl>`` (document order) in a section,
* resolve a logical ``(row, col)`` -- merge aware -- to the covering ``<hp:tc>``,
* splice **only** that cell's first paragraph text (reusing
  :func:`hwpx.patch._text_edit_for_paragraph`, which handles empty / self-closing
  ``<hp:run/>`` / ``<hp:t/>`` cells -- the kordoc #4/#30 edge the P0 spike hit),
* strip that paragraph's stale ``<hp:linesegarray>`` so Hancom relayouts,
* rewrite only the changed section parts through the ZIP partial-patch writer, so
  every untouched byte of the document round-trips identical (Constitution VII).

Table structure primitives (delete/insert row/column/table) build on the same
parsing helpers and live alongside this in a follow-up; this file is the cell
fill (FR-001/FR-002) plus the grid validator (FR-004) they share.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .patch import (
    _apply_edits,
    _patch_zip_entries,
    _read_source_bytes,
    _rewrite_zip_entries,
    _strip_paragraph_layout_cache,
    _text_edit_for_paragraph,
    _finalize,
)

# --- byte-level table / row / cell parsing (namespace-prefix agnostic) ---------

def _tag(name: str) -> bytes:
    # match <hp:name  /  <hh:name  /  <name  (any or no prefix)
    return rb"<(?:[A-Za-z_][\w.-]*:)?" + name.encode() + rb"\b"

def _top_spans(xml: bytes, name: str) -> list[tuple[int, int]]:
    """Top-level (depth-0) ``<name ...>...</name>`` spans within *xml*.

    Handles same-name nesting by depth counting. Used to find nested tables so
    they can be masked out before scanning a table's *direct* rows/cells.
    """
    open_re = re.compile(_tag(name))
    close_re = re.compile(rb"</(?:[A-Za-z_][\w.-]*:)?" + name.encode() + rb">")
    events = sorted(
        [(m.start(), 1, m.end()) for m in open_re.finditer(xml)]
        + [(m.start(), -1, m.end()) for m in close_re.finditer(xml)]
    )
    spans: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for pos, delta, end in events:
        if delta == 1:
            if depth == 0:
                start = pos
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, end))
    return spans

def _mask_nested_tables(xml: bytes) -> bytes:
    """Blank nested ``<hp:tbl>...</hp:tbl>`` with same-length spaces (offset-
    preserving), so direct-child row/cell scans never descend into them."""
    out = bytearray(xml)
    for s, e in _top_spans(xml, "tbl"):
        out[s:e] = b" " * (e - s)
    return bytes(out)

_TBL_EVENT_RE = re.compile(_tag("tbl") + rb"|</(?:[A-Za-z_][\w.-]*:)?tbl>")

def _iter_table_spans(section: bytes) -> list[tuple[int, int]]:
    """Byte spans of every ``<hp:tbl>...</hp:tbl>`` in document order (of open
    tags), balanced for nesting -- matching the ``table_index`` convention."""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(_tag("tbl"), section):
        start = m.start()
        depth = 0
        end = None
        for t in _TBL_EVENT_RE.finditer(section, start):
            depth += -1 if t.group().startswith(b"</") else 1
            if depth == 0:
                end = t.end()
                break
        if end is not None:
            spans.append((start, end))
    return spans

def _open_tag_end(table: bytes) -> int:
    return table.index(b">") + 1

def _iattr(chunk: bytes, name: str, attr: str) -> int | None:
    m = re.search(_tag(name) + rb'[^>]*\b' + attr.encode() + rb'="(-?\d+)"', chunk)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class _Cell:
    start: int  # byte offset within the table
    end: int
    row: int
    col: int
    row_span: int
    col_span: int


def _direct_cells(table: bytes) -> list[_Cell]:
    """Direct ``<hp:tc>`` of *table* (skips nested-table cells), with byte spans
    relative to the table and their cellAddr/cellSpan."""
    open_end = _open_tag_end(table)
    body_start = open_end
    body = table[body_start:]
    masked = _mask_nested_tables(body)
    cells: list[_Cell] = []
    for m in re.finditer(rb"<(?:[A-Za-z_][\w.-]*:)?tc\b.*?</(?:[A-Za-z_][\w.-]*:)?tc>", masked, re.DOTALL):
        real = table[body_start + m.start(): body_start + m.end()]
        col = _iattr(real, "cellAddr", "colAddr")
        row = _iattr(real, "cellAddr", "rowAddr")
        cspan = _iattr(real, "cellSpan", "colSpan") or 1
        rspan = _iattr(real, "cellSpan", "rowSpan") or 1
        if row is None or col is None:
            continue
        cells.append(_Cell(body_start + m.start(), body_start + m.end(), row, col, rspan, cspan))
    return cells


@dataclass(frozen=True)
class GridReport:
    ok: bool
    row_count: int
    col_count: int
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "rowCount": self.row_count, "colCount": self.col_count, "issues": list(self.issues)}


def build_grid(table: bytes) -> tuple[dict[tuple[int, int], _Cell], GridReport]:
    """Expand merged cells into a logical grid and check it (FR-004).

    Returns ``{(row, col): cell}`` covering every logical position, plus a report
    flagging overlaps, holes, and out-of-bounds spans against the table's declared
    ``rowCnt``/``colCnt``.
    """
    cells = _direct_cells(table)
    declared_rows = _iattr(table, "tbl", "rowCnt")
    declared_cols = _iattr(table, "tbl", "colCnt")
    grid: dict[tuple[int, int], _Cell] = {}
    issues: list[str] = []
    max_r = max_c = 0
    for c in cells:
        for dr in range(c.row_span):
            for dc in range(c.col_span):
                key = (c.row + dr, c.col + dc)
                if key in grid:
                    issues.append(f"overlap at {key}")
                grid[key] = c
                max_r = max(max_r, key[0])
                max_c = max(max_c, key[1])
    n_rows = max_r + 1
    n_cols = max_c + 1
    for r in range(n_rows):
        for col in range(n_cols):
            if (r, col) not in grid:
                issues.append(f"hole at {(r, col)}")
    if declared_cols is not None and n_cols != declared_cols:
        issues.append(f"colCnt {declared_cols} != observed {n_cols}")
    if declared_rows is not None and n_rows != declared_rows:
        issues.append(f"rowCnt {declared_rows} != observed {n_rows}")
    return grid, GridReport(not issues, n_rows, n_cols, tuple(issues))


def _first_paragraph_span(cell: bytes) -> tuple[int, int] | None:
    """Byte span of the cell's first ``<hp:p>...</hp:p>`` (its own subList's
    first paragraph), skipping any nested table content."""
    masked = _mask_nested_tables(cell)
    m = re.search(rb"<(?:[A-Za-z_][\w.-]*:)?p\b.*?</(?:[A-Za-z_][\w.-]*:)?p>", masked, re.DOTALL)
    if m is None:
        return None
    return m.start(), m.end()


# --- public API ---------------------------------------------------------------

@dataclass(frozen=True)
class CellApplied:
    section_path: str
    table_index: int
    row: int
    col: int
    original_text: str
    replacement_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionPath": self.section_path, "tableIndex": self.table_index,
            "row": self.row, "col": self.col,
            "originalText": self.original_text, "replacementText": self.replacement_text,
        }


@dataclass(frozen=True)
class CellSkipped:
    section_path: str
    table_index: int
    row: int
    col: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionPath": self.section_path, "tableIndex": self.table_index,
            "row": self.row, "col": self.col, "reason": self.reason,
        }


@dataclass(frozen=True)
class CellFillResult:
    data: bytes
    applied: tuple[CellApplied, ...]
    skipped: tuple[CellSkipped, ...]
    changed_parts: tuple[str, ...]
    byte_identical: bool
    zip_method: str
    open_safety: dict[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.open_safety.get("ok")) and not self.skipped

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "applied": [a.to_dict() for a in self.applied],
            "skipped": [s.to_dict() for s in self.skipped],
            "changedParts": list(self.changed_parts),
            "byteIdentical": self.byte_identical,
            "zipMethod": self.zip_method,
            "openSafety": self.open_safety,
        }


def _normalize(cell: Mapping[str, Any] | Any) -> tuple[str, int, int, int, str]:
    get = cell.get if isinstance(cell, Mapping) else (lambda k, d=None: getattr(cell, k, d))
    section = str(get("section_path") or get("sectionPath") or "Contents/section0.xml")
    table_index = get("table_index", get("tableIndex"))
    row = get("row")
    col = get("col")
    text = get("text")
    if table_index is None or row is None or col is None or text is None:
        raise ValueError("cell fill requires table_index, row, col, text")
    return section, int(table_index), int(row), int(col), str(text)


def fill_cells(
    source: str | Path | bytes,
    cells: Sequence[Mapping[str, Any] | Any],
    *,
    output_path: str | Path | None = None,
) -> CellFillResult:
    """Byte-preserving fill of table cells by ``(table_index, row, col)`` address.

    Only the addressed cells' first-paragraph text is spliced; the stale
    ``<hp:linesegarray>`` of each edited paragraph is stripped. Untouched section
    parts and untouched tables round-trip byte-identical. Empty / self-closing
    cells are filled (text inserted), never silently reported as done. An
    unresolvable address is reported in ``skipped`` and mutates nothing.
    """
    source_bytes = _read_source_bytes(source)
    specs = [_normalize(c) for c in cells]
    if not specs:
        open_safety, _ = _finalize(source_bytes, output_path, source=source)
        return CellFillResult(source_bytes, (), (), (), True, "none", open_safety)

    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zf:
        parts = {i.filename: zf.read(i.filename) for i in zf.infolist() if not i.is_dir()}

    applied: list[CellApplied] = []
    skipped: list[CellSkipped] = []
    by_section: dict[str, list[tuple[int, int, int, str]]] = {}
    for section, ti, row, col, text in specs:
        by_section.setdefault(section, []).append((ti, row, col, text))

    changed_parts: dict[str, bytes] = {}
    for section_path, section_specs in by_section.items():
        section_xml = parts.get(section_path)
        if section_xml is None:
            skipped.extend(CellSkipped(section_path, ti, r, c, "section part not found") for ti, r, c, _ in section_specs)
            continue
        table_spans = _iter_table_spans(section_xml)
        # accumulate byte edits over the whole section (table region splices)
        section_edits: list[tuple[int, int, bytes]] = []
        for ti, row, col, text in section_specs:
            if ti < 0 or ti >= len(table_spans):
                skipped.append(CellSkipped(section_path, ti, row, col, "table_index out of range"))
                continue
            ts, te = table_spans[ti]
            table = section_xml[ts:te]
            grid, report = build_grid(table)
            cell = grid.get((row, col))
            if cell is None:
                skipped.append(CellSkipped(section_path, ti, row, col, "cell address out of range"))
                continue
            cell_bytes = table[cell.start:cell.end]
            p_span = _first_paragraph_span(cell_bytes)
            if p_span is None:
                skipped.append(CellSkipped(section_path, ti, row, col, "cell has no paragraph"))
                continue
            para = cell_bytes[p_span[0]:p_span[1]]
            edit = _text_edit_for_paragraph(para, text)
            if edit is None:
                skipped.append(CellSkipped(section_path, ti, row, col, "cell has no patchable hp:run"))
                continue
            _s, _e, replacement, original_text = edit
            if original_text == text:
                continue
            new_para = _strip_paragraph_layout_cache(replacement if (_s, _e) == (0, len(para)) else _apply_edits(para, [(_s, _e, replacement)]))
            # absolute offsets within the SECTION
            abs_start = ts + cell.start + p_span[0]
            abs_end = ts + cell.start + p_span[1]
            section_edits.append((abs_start, abs_end, new_para))
            applied.append(CellApplied(section_path, ti, row, col, original_text, text))
        if section_edits:
            new_section = _apply_edits(section_xml, section_edits)
            if new_section != section_xml:
                changed_parts[section_path] = new_section

    if not changed_parts:
        open_safety, _ = _finalize(source_bytes, output_path, source=source)
        return CellFillResult(source_bytes, tuple(applied), tuple(skipped), (), True, "none", open_safety)

    try:
        output = _patch_zip_entries(source_bytes, changed_parts)
        zip_method = "partial-local-record-copy"
    except ValueError:
        output = _rewrite_zip_entries(source_bytes, changed_parts)
        zip_method = "zipfile-rewrite-fallback"
    open_safety, _ = _finalize(output, output_path, source=source)
    return CellFillResult(
        output, tuple(applied), tuple(skipped), tuple(changed_parts),
        output == source_bytes, zip_method, open_safety,
    )


__all__ = ["fill_cells", "build_grid", "GridReport", "CellFillResult", "CellApplied", "CellSkipped"]
