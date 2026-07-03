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


# --- table structure primitives (FR-003/FR-004) ------------------------------
#
# A structure edit is performed on the isolated table's *decoded* XML (str), then
# the produced table replaces ONLY that table's byte span in the section, so every
# other byte round-trips identical (Constitution VII). The edited table itself is
# re-serialised (its byte identity is intentionally forfeit -- it is the thing you
# changed). Every op is grid-validated afterwards and refuses (raises) on an
# invalid result (fail-closed, Constitution VI). Nested tables are out of scope:
# a table containing a nested <hp:tbl> refuses structure edits.

_S_TR = re.compile(r"<hp:tr\b.*?</hp:tr>", re.DOTALL)
_S_TC = re.compile(r"<hp:tc\b.*?</hp:tc>", re.DOTALL)


class TableStructureError(ValueError):
    """A structure edit was refused (fail-closed) or is unsupported."""


def _si(chunk: str, tag: str, attr: str) -> int | None:
    m = re.search(rf'<hp:{tag}\b[^>]*\b{attr}="(-?\d+)"', chunk)
    return int(m.group(1)) if m else None


def _ss(chunk: str, tag: str, attr: str, val: int) -> str:
    return re.sub(rf'(<hp:{tag}\b[^>]*\b{attr}=")-?\d+(")', rf"\g<1>{val}\g<2>", chunk, count=1)


def _guard_flat(table: str) -> None:
    # the table's own <hp:tbl> plus any nested ones; >1 open == nested
    if len(re.findall(r"<hp:tbl\b", table)) > 1:
        raise TableStructureError("nested tables are unsupported for structure edits")


def _parse_table(table: str) -> tuple[str, list[str], str]:
    first = table.index("<hp:tr")
    last = table.rindex("</hp:tr>") + len("</hp:tr>")
    return table[:first], _S_TR.findall(table[first:last]), table[last:]


def _rebuild(prefix: str, rows: list[str], suffix: str, *, rowcnt: int | None = None, colcnt: int | None = None) -> str:
    out = prefix + "".join(rows) + suffix
    if rowcnt is not None:
        out = re.sub(r'(<hp:tbl\b[^>]*\browCnt=")\d+(")', rf"\g<1>{rowcnt}\g<2>", out, count=1)
    if colcnt is not None:
        out = re.sub(r'(<hp:tbl\b[^>]*\bcolCnt=")\d+(")', rf"\g<1>{colcnt}\g<2>", out, count=1)
    return out


def _map_cells(row: str, fn) -> str:
    parts, last = [], 0
    for m in _S_TC.finditer(row):
        parts.append(row[last:m.start()])
        r = fn(m.group(0))
        if r is not None:
            parts.append(r)
        last = m.end()
    parts.append(row[last:])
    return "".join(parts)


def _uniform_col_widths(rows: list[str]) -> dict[int, int] | None:
    for row in rows:
        w, ok = {}, True
        for tc in _S_TC.findall(row):
            if (_si(tc, "cellSpan", "colSpan") or 1) != 1:
                ok = False
                break
            w[_si(tc, "cellAddr", "colAddr")] = _si(tc, "cellSz", "width")
        if ok and w and max(w) + 1 == len(w):
            return w
    return None


def _delete_columns(table: str, del_cols: Iterable[int]) -> str:
    _guard_flat(table)
    del_cols = sorted(set(del_cols))
    if not del_cols:
        return table
    dmax = del_cols[-1]
    prefix, rows, suffix = _parse_table(table)
    widths = _uniform_col_widths(rows)
    if widths is None:
        raise TableStructureError("no uniform (all colSpan=1) row to derive column widths")
    ncol = max(widths) + 1
    freed = sum(widths[c] for c in del_cols)
    survivors = [c for c in range(ncol) if c not in del_cols]
    targets = [c for c in survivors if c > dmax and c != survivors[-1]] or survivors
    add, rem = divmod(freed, len(targets))
    nw = {c: widths[c] for c in survivors}
    for i, c in enumerate(targets):
        nw[c] += add + (1 if i < rem else 0)
    newidx = {c: i for i, c in enumerate(survivors)}

    def fix(tc: str):
        ca, cs = _si(tc, "cellAddr", "colAddr"), _si(tc, "cellSpan", "colSpan") or 1
        surv = [c for c in range(ca, ca + cs) if c not in del_cols]
        if not surv:
            return None
        tc = _ss(tc, "cellAddr", "colAddr", newidx[surv[0]])
        tc = _ss(tc, "cellSpan", "colSpan", len(surv))
        tc = _ss(tc, "cellSz", "width", sum(nw[c] for c in surv))
        return tc

    rows = [_map_cells(r, fix) for r in rows]
    return _rebuild(prefix, rows, suffix, colcnt=len(survivors))


def _collapse_empty_rows(table: str) -> str:
    """Cascade: drop physical rows left with 0 cells (e.g. a row that existed only
    for a now-deleted column block), collapsing rowSpans that crossed them."""
    prefix, rows, suffix = _parse_table(table)
    while True:
        empty = next((i for i, r in enumerate(rows) if not _S_TC.findall(r)), None)
        if empty is None:
            break
        heights = []
        for r in rows:
            for tc in _S_TC.findall(r):
                ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
                if ra < empty < ra + rs:
                    h = _si(tc, "cellSz", "height")
                    if h:
                        heights.append(h // rs)
        drop_h = min(heights) if heights else 0

        def fix(tc: str):
            ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
            if ra < empty < ra + rs:
                tc = _ss(tc, "cellSpan", "rowSpan", rs - 1)
                h = _si(tc, "cellSz", "height")
                if h and drop_h:
                    tc = _ss(tc, "cellSz", "height", max(1, h - drop_h))
            elif ra > empty:
                tc = _ss(tc, "cellAddr", "rowAddr", ra - 1)
            return tc

        rows = [_map_cells(r, fix) for i, r in enumerate(rows) if i != empty]
    rowcnt = len(rows)
    return _rebuild(prefix, rows, suffix, rowcnt=rowcnt)


def _delete_rows(table: str, del_rows: Iterable[int]) -> str:
    """Delete physical rows by index, reconciling rowAddr/rowSpan and covering
    cells' height."""
    _guard_flat(table)
    del_rows = sorted(set(del_rows), reverse=True)
    prefix, rows, suffix = _parse_table(table)
    for empty in del_rows:
        if empty >= len(rows):
            raise TableStructureError(f"row index {empty} out of range")
        heights = []
        for r in rows:
            for tc in _S_TC.findall(r):
                ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
                if ra <= empty < ra + rs and rs > 1:
                    h = _si(tc, "cellSz", "height")
                    if h:
                        heights.append(h // rs)
        drop_h = min(heights) if heights else 0

        def fix(tc: str):
            ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
            if ra <= empty < ra + rs:
                if rs > 1:
                    tc = _ss(tc, "cellSpan", "rowSpan", rs - 1)
                    h = _si(tc, "cellSz", "height")
                    if h and drop_h:
                        tc = _ss(tc, "cellSz", "height", max(1, h - drop_h))
                    return tc
                return None  # single-row cell in the deleted row -> drop
            if ra > empty:
                tc = _ss(tc, "cellAddr", "rowAddr", ra - 1)
            return tc

        rows = [_map_cells(r, fix) for i, r in enumerate(rows)]
        rows = [r for i, r in enumerate(rows) if i != empty]
    return _rebuild(prefix, rows, suffix, rowcnt=len(rows))


_PARA_ID_RE = re.compile(r'(<hp:p\b[^>]*\bid=")(\d+)(")')


def _refresh_ids(row: str, bump: int) -> str:
    return _PARA_ID_RE.sub(lambda m: m.group(1) + str((int(m.group(2)) + bump) & 0x7FFFFFFF) + m.group(3), row)


def _insert_row_by_clone(table: str, ref_row: int, count: int = 1) -> str:
    """Insert *count* rows after physical row *ref_row* by cloning it (formatting
    preserved, paragraph ids refreshed). Rows below shift; cells spanning across
    the insertion grow their rowSpan."""
    _guard_flat(table)
    if count < 1:
        return table
    prefix, rows, suffix = _parse_table(table)
    if ref_row >= len(rows):
        raise TableStructureError(f"ref row {ref_row} out of range")

    def shift(tc: str):
        ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
        if ra > ref_row:
            return _ss(tc, "cellAddr", "rowAddr", ra + count)
        if ra <= ref_row < ra + rs and ra + rs - 1 > ref_row:
            # cell spans across the insertion point -> extend
            return _ss(tc, "cellSpan", "rowSpan", rs + count)
        return tc

    shifted = [_map_cells(r, shift) for r in rows]
    # build the clones from the ORIGINAL ref row (single-row cells only; a ref row
    # whose cells are all rowSpan==1 is the safe clone source)
    ref = rows[ref_row]
    if any((_si(tc, "cellSpan", "rowSpan") or 1) != 1 for tc in _S_TC.findall(ref)):
        raise TableStructureError("clone source row must have rowSpan==1 cells")
    clones = []
    for k in range(1, count + 1):
        clone = _map_cells(ref, lambda tc: _ss(tc, "cellAddr", "rowAddr", ref_row + k))
        clone = _refresh_ids(clone, 1000 + k)
        clones.append(clone)
    new_rows = shifted[: ref_row + 1] + clones + shifted[ref_row + 1:]
    return _rebuild(prefix, new_rows, suffix, rowcnt=len(new_rows))


def _validate_or_raise(table: str) -> None:
    _grid, rep = build_grid(table.encode("utf-8"))
    if not rep.ok:
        raise TableStructureError(f"invalid table grid after edit: {rep.issues}")


# --- section-level application (byte-region splice back) ----------------------

_STRUCT_OPS = {
    "delete_column": lambda t, o: _collapse_empty_rows(_delete_columns(t, o["cols"] if "cols" in o else [o["col"]])),
    "delete_row": lambda t, o: _delete_rows(t, o["rows"] if "rows" in o else [o["row"]]),
    "insert_row_by_clone": lambda t, o: _insert_row_by_clone(t, o["ref_row"], int(o.get("count", 1))),
}


def _p_wrapper_span(section: bytes, table_start: int) -> tuple[int, int]:
    """Byte span of the <hp:p> paragraph that wraps the table starting at
    *table_start* (used by delete_table)."""
    p_open = section.rfind(b"<hp:p", 0, table_start)
    if p_open < 0:
        raise TableStructureError("could not find wrapping <hp:p> for table")
    # balanced close from p_open
    depth = 0
    for t in re.finditer(rb"<(?:[A-Za-z_][\w.-]*:)?p\b|</(?:[A-Za-z_][\w.-]*:)?p>", section[p_open:]):
        depth += -1 if t.group().startswith(b"</") else 1
        if depth == 0:
            return p_open, p_open + t.end()
    raise TableStructureError("unbalanced wrapping paragraph")


def _sections(data: bytes) -> dict[str, bytes]:
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist() if re.search(r"section\d+\.xml$", n)}


def apply_table_ops(
    source: str | Path | bytes,
    ops: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
) -> CellFillResult:
    """Apply structure ops (then cell fills) to a document, byte-region splicing
    each changed table back so untouched bytes stay identical.

    Op dicts: ``{op: 'delete_column'|'delete_row'|'delete_table'|
    'insert_row_by_clone'|'fill_cell', section_path?, table_index, ...}``.
    Structure ops run first, in order; ``delete_table`` shifts later table indices,
    so sequence table deletes in reverse index order (as the recipe does). Every
    structure edit is grid-validated and refuses on an invalid result
    (fail-closed). Cell fills are then applied on the restructured document via
    :func:`fill_cells`.
    """
    source_bytes = _read_source_bytes(source)
    struct_ops = [o for o in ops if o.get("op") != "fill_cell"]
    fill_ops = [{**o, "section_path": o.get("section_path") or o.get("sectionPath") or "Contents/section0.xml"}
                for o in ops if o.get("op") == "fill_cell"]

    sections = _sections(source_bytes)
    skipped: list[CellSkipped] = []
    changed: set[str] = set()

    for op in struct_ops:
        name = op.get("op")
        sp = str(op.get("section_path") or op.get("sectionPath") or "Contents/section0.xml")
        section = sections.get(sp)
        if section is None:
            skipped.append(CellSkipped(sp, -1, -1, -1, "section part not found"))
            continue
        try:
            ti = int(op.get("table_index", op.get("tableIndex")))
        except (TypeError, ValueError):
            skipped.append(CellSkipped(sp, -1, -1, -1, f"{name}: table_index required"))
            continue
        spans = _iter_table_spans(section)
        if ti < 0 or ti >= len(spans):
            skipped.append(CellSkipped(sp, ti, -1, -1, "table_index out of range"))
            continue
        ts, te = spans[ti]
        try:
            if name == "delete_table":
                ps, pe = _p_wrapper_span(section, ts)
                new_section = section[:ps] + section[pe:]
            elif name in _STRUCT_OPS:
                new_table = _STRUCT_OPS[name](section[ts:te].decode("utf-8"), op)
                _validate_or_raise(new_table)
                new_section = section[:ts] + new_table.encode("utf-8") + section[te:]
            else:
                skipped.append(CellSkipped(sp, ti, -1, -1, f"unknown op {name!r}"))
                continue
        except TableStructureError as exc:
            skipped.append(CellSkipped(sp, ti, -1, -1, f"{name}: {exc}"))
            continue
        sections[sp] = new_section
        changed.add(sp)

    intermediate = source_bytes
    if changed:
        try:
            intermediate = _patch_zip_entries(source_bytes, {sp: sections[sp] for sp in changed})
        except ValueError:
            intermediate = _rewrite_zip_entries(source_bytes, {sp: sections[sp] for sp in changed})

    if fill_ops:
        fres = fill_cells(intermediate, fill_ops, output_path=output_path)
        return CellFillResult(
            fres.data, fres.applied, tuple(skipped) + fres.skipped,
            tuple(sorted(changed | set(fres.changed_parts))),
            fres.data == source_bytes,
            "partial-local-record-copy" if (changed or fres.changed_parts) else "none",
            fres.open_safety,
        )

    open_safety, _ = _finalize(intermediate, output_path, source=source)
    return CellFillResult(
        intermediate, (), tuple(skipped), tuple(sorted(changed)),
        intermediate == source_bytes,
        "partial-local-record-copy" if changed else "none", open_safety,
    )


# --- P3: real-Hancom oracle gate for form-fill (FR-005) -----------------------

class RenderCheckRequired(RuntimeError):
    """``verify_fill(require=True)`` but no real Hancom oracle rendered."""


def verify_fill(
    before: str | Path | bytes | None,
    after: str | Path | bytes,
    *,
    oracle: Any = None,
    require: bool = False,
    edit_mask: Any = None,
    work_dir: str | None = None,
):
    """Render *before*/*after* in **real Hancom** and judge the fill.

    Wires the real oracle (:func:`hwpx.visual.oracle.resolve_oracle` /
    :func:`~hwpx.visual.oracle.visual_check`) into the form-fill verdict so a
    caller never mistakes structural validity (open-safety) or a lenient HTML
    preview for Hancom acceptance -- the exact 2026-07-03 overclaim. Returns a
    ``VisualReport`` carrying ``render_checked`` plus ``overflow_detected`` /
    ``overlap_detected`` (글자겹침) / ``page_count_changed``.

    Honest degrade (Constitution V): with no reachable Hancom / imaging stack the
    report is ``render_checked=False, ok=True`` and nothing raises -- **unless**
    ``require=True``, which fails closed with :class:`RenderCheckRequired`.
    """
    import os
    import shutil
    import tempfile

    from .visual.oracle import resolve_oracle, visual_check

    after_bytes = _read_source_bytes(after)
    before_bytes = _read_source_bytes(before) if before is not None else None
    if oracle is None:
        oracle = resolve_oracle()

    tmp = tempfile.mkdtemp(prefix="hwpx-verify-")
    try:
        after_path = os.path.join(tmp, "after.hwpx")
        Path(after_path).write_bytes(after_bytes)
        before_path = None
        if before_bytes is not None:
            before_path = os.path.join(tmp, "before.hwpx")
            Path(before_path).write_bytes(before_bytes)
        report = visual_check(before_path, after_path, oracle=oracle, edit_mask=edit_mask, work_dir=work_dir)
    finally:
        if work_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)

    if require and not report.render_checked:
        raise RenderCheckRequired(
            "render_check='required' but no Hancom oracle rendered: "
            + "; ".join(list(report.warnings) + list(report.errors))
        )
    return report


__all__ = [
    "fill_cells", "build_grid", "GridReport", "CellFillResult", "CellApplied", "CellSkipped",
    "apply_table_ops", "TableStructureError", "verify_fill", "RenderCheckRequired",
]
