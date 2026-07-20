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

from .mutation_report import MutationReport, project_byte_splice
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


_P_SPAN_RE = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?p\b.*?</(?:[A-Za-z_][\w.-]*:)?p>", re.DOTALL)
_SQUEEZE_WRAP_RE = re.compile(
    rb'<(?:[A-Za-z_][\w.-]*:)?subList\b[^>]*?\blineWrap="(?P<value>SQUEEZE)"'
)

def _first_paragraph_span(cell: bytes) -> tuple[int, int] | None:
    """Byte span of the cell's first ``<hp:p>...</hp:p>`` (its own subList's
    first paragraph), skipping any nested table content."""
    m = _P_SPAN_RE.search(_mask_nested_tables(cell))
    return (m.start(), m.end()) if m else None

def _all_paragraph_spans(cell: bytes) -> list[tuple[int, int]]:
    """Byte spans of every direct ``<hp:p>`` of the cell (its own paragraphs,
    not nested-table ones)."""
    masked = _mask_nested_tables(cell)
    return [(m.start(), m.end()) for m in _P_SPAN_RE.finditer(masked)]


def _squeeze_wrap_edit(cell: bytes) -> tuple[int, int, bytes] | None:
    """Return a minimal edit that makes a filled cell wrap instead of squeeze.

    Hancom's ``lineWrap=SQUEEZE`` keeps long replacement text on the existing
    line by compressing glyph advances.  Template placeholders often fit, but
    real filled values can become nearly unreadable even though their charPr
    spacing is normal.  Only the addressed cell's direct subList is considered;
    nested tables remain untouched.
    """

    match = _SQUEEZE_WRAP_RE.search(_mask_nested_tables(cell))
    if match is None:
        return None
    return match.start("value"), match.end("value"), b"BREAK"


# --- font shrink-to-fit helpers (byte-preserving charPr materialisation) ------

def _header_part_name(parts: Mapping[str, bytes]) -> str | None:
    return next((n for n in parts if n.endswith("header.xml")), None)

def _charpr_height(header: bytes, cid: str) -> int | None:
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="' + re.escape(cid.encode()) + rb'"[^>]*?\bheight="(\d+)"', header)
    return int(m.group(1)) if m else None

def _cell_run_charpr(cell: bytes) -> str | None:
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?run\b[^>]*?\bcharPrIDRef="(\d+)"', cell)
    return m.group(1).decode() if m else None

def _cell_inner_width(cell: bytes) -> int:
    w = _iattr(cell, "cellSz", "width") or 0
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?cellMargin\b[^>]*?\bleft="(\d+)"[^>]*?\bright="(\d+)"', cell)
    left, right = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return max(w - left - right, 0)

def _materialize_charpr(header: bytes, base_id: str, new_height: int, cache: dict[tuple[str, int], str]) -> tuple[bytes, str]:
    """Clone charPr *base_id* with *new_height*, append it to the charProperties
    list (itemCnt bumped), return (new_header, new_charpr_id). Deduped via *cache*."""
    key = (base_id, new_height)
    if key in cache:
        return header, cache[key]
    bid = re.escape(base_id.encode())
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="' + bid + rb'".*?</(?:[A-Za-z_][\w.-]*:)?charPr>', header, re.DOTALL)
    if m is None:
        m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="' + bid + rb'"[^>]*/>', header)
    if m is None:
        raise KeyError(f"base charPr {base_id} not found")
    ids = [int(x) for x in re.findall(rb'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="(\d+)"', header)]
    new_id = str((max(ids) + 1) if ids else 0)
    clone = re.sub(rb'(\bid=")\d+(")', rb'\g<1>' + new_id.encode() + rb'\g<2>', m.group(0), count=1)
    if re.search(rb'\bheight="\d+"', clone):
        clone = re.sub(rb'(\bheight=")\d+(")', rb'\g<1>' + str(new_height).encode() + rb'\g<2>', clone, count=1)
    close = re.search(rb'</(?:[A-Za-z_][\w.-]*:)?charProperties>', header)
    if close is None:
        raise KeyError("charProperties close tag not found")
    header = header[:close.start()] + clone + header[close.start():]
    header = re.sub(
        rb'(<(?:[A-Za-z_][\w.-]*:)?charProperties\b[^>]*?\bitemCnt=")(\d+)(")',
        lambda mm: mm.group(1) + str(int(mm.group(2)) + 1).encode() + mm.group(3),
        header, count=1,
    )
    cache[key] = new_id
    return header, new_id

def _shrunk_font_id(header: bytes, cell_bytes: bytes, text: str, target_lines: int, min_font_pt: float,
                    cache: dict[tuple[str, int], str]) -> tuple[bytes, str, str] | None:
    """If *text* needs more than *target_lines* at the cell's base font, decide a
    shrink (form_fit FitEngine) and materialise it. Returns (new_header, base_id,
    new_id) or None (no shrink needed / not resolvable)."""
    from .form_fit.engine import FitEngine
    from .form_fit.measure import SlotMetrics
    from .form_fit.policy import FitPolicy

    base_id = _cell_run_charpr(cell_bytes)
    if base_id is None:
        return None
    inner = _cell_inner_width(cell_bytes)
    base_h = _charpr_height(header, base_id)
    if not inner or not base_h:
        return None
    base_pt = base_h / 100.0
    slot = SlotMetrics(available_width=inner * 0.94, font_pt=base_pt, max_lines=target_lines)
    result = FitEngine().fit(text, slot, FitPolicy(mode="wrap_then_shrink", max_lines=target_lines, min_font_pt=min_font_pt))
    new_pt = result.font_pt
    if not new_pt or new_pt >= base_pt - 1e-6:
        return None
    header, new_id = _materialize_charpr(header, base_id, int(round(new_pt * 100)), cache)
    return header, base_id, new_id


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
class ResolvedCellTarget:
    """One non-mutating, merge-aware table-cell locator resolution.

    ``logical_row``/``logical_col`` record the address selected by the label
    semantics.  ``row``/``col`` are the physical ``cellAddr`` coordinates of
    the covering cell and are therefore the coordinates a semantic document
    projection can bind to exactly, even when the logical address lands inside
    a row/column-spanning cell.
    """

    section_path: str
    table_index: int
    logical_row: int
    logical_col: int
    row: int
    col: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionPath": self.section_path,
            "tableIndex": self.table_index,
            "logicalRow": self.logical_row,
            "logicalColumn": self.logical_col,
            "physicalRow": self.row,
            "physicalColumn": self.col,
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
    # 구조 op별 해석·검증 결과(승인 근거) — dry-run 상의 루프의 기계 증거.
    transcript: tuple[dict[str, Any], ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.open_safety.get("ok")) and not self.skipped

    def to_dict(self) -> dict[str, Any]:
        out = {
            "ok": self.ok,
            "applied": [a.to_dict() for a in self.applied],
            "skipped": [s.to_dict() for s in self.skipped],
            "changedParts": list(self.changed_parts),
            "byteIdentical": self.byte_identical,
            "zipMethod": self.zip_method,
            "openSafety": self.open_safety,
        }
        if self.transcript:
            out["transcript"] = list(self.transcript)
        return out

    def as_mutation_report(self, *, source: bytes | None = None) -> MutationReport:
        """Project this cell-fill result onto ``hwpx.mutation-report/v1`` (specs/032
        §3). Additive — the fields above are untouched. This path never renders,
        so the visual verdict stays ``not_performed``. Pass the original *source*
        for real ranges and a measured preservation summary.
        """

        return project_byte_splice(
            data=self.data,
            changed_part_names=self.changed_parts,
            byte_identical=self.byte_identical,
            open_safety=self.open_safety,
            source=source,
        )


# --- FR-002: anchor / heading addressing (byte-level, unique-or-skip) ---------
#
# A table can be addressed by the text of its preceding section heading/label
# ("[6] 평가의 종류와 반영비율", "나. 학기 단위 성취수준") instead of a table_index
# that delete_table shifts; a cell by an adjacent label ("담당교사" -> right). An
# anchor that resolves to 0 or >1 targets is SKIPPED with a reason (fail-closed,
# Constitution VI), never guessed. Resolution is byte-level (no re-serialization).

def _norm_anchor(s: str) -> str:
    return re.sub(r"[\s\[\]().·,:/\-]+", "", str(s)).lower()

_ANCHOR_T = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?t>(.*?)</(?:[A-Za-z_][\w.-]*:)?t>", re.DOTALL)
_ANCHOR_TR = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?tr\b")

def _text_of(chunk: bytes) -> str:
    txt = "".join(m.group(1).decode("utf-8", "replace") for m in _ANCHOR_T.finditer(chunk))
    return re.sub(r"<[^>]+>", "", txt)  # strip inline run markup (markpenEnd, tab, ...)

def _phys_row_count(table: bytes) -> int:
    return len(_ANCHOR_TR.findall(_mask_nested_tables(table[_open_tag_end(table):])))

def _find_tables_by_anchor(section: bytes, anchor: str, spans: list[tuple[int, int]] | None = None) -> list[int]:
    """Indices of tables whose preceding-heading window contains *anchor*.

    A table's window runs from the end of the nearest preceding **data** table
    (>=2 physical rows) up to its own start, so it captures the numbered
    header-box tables (1-row) and heading paragraphs between them, but not the
    table's own cells. Bounded to 8 KiB of lookback."""
    if spans is None:
        spans = _iter_table_spans(section)
    na = _norm_anchor(anchor)
    if not na:
        return []
    is_data = [_phys_row_count(section[s:e]) >= 2 for (s, e) in spans]
    matches: list[int] = []
    for ti, (s, _e) in enumerate(spans):
        w_start = 0
        for j in range(ti - 1, -1, -1):
            if is_data[j]:
                w_start = spans[j][1]
                break
        w_start = max(w_start, s - 8000)
        if na in _norm_anchor(_text_of(section[w_start:s])):
            matches.append(ti)
    return matches

def _resolve_cell_anchor(
    table: bytes,
    label: str,
    direction: str,
    *,
    exact: bool = False,
) -> list[tuple[int, int]]:
    """Logical (row, col) of the cell *direction* of the unique cell containing
    *label*. ``exact=True`` requires normalized equality for canonical planning;
    the compatibility default retains normalized substring matching. direction
    in {right,left,below,above}."""
    grid, _rep = build_grid(table)
    nl = _norm_anchor(label)
    if not nl:
        return []
    seen: set[tuple[int, int]] = set()
    targets: list[tuple[int, int]] = []
    for _key, cell in grid.items():
        span_id = (cell.start, cell.end)
        if span_id in seen:
            continue
        seen.add(span_id)
        normalized_cell_text = _norm_anchor(_text_of(table[cell.start:cell.end]))
        label_matches = normalized_cell_text == nl if exact else nl in normalized_cell_text
        if label_matches:
            if direction == "left":
                tr, tc = cell.row, cell.col - 1
            elif direction == "below":
                tr, tc = cell.row + cell.row_span, cell.col
            elif direction == "above":
                tr, tc = cell.row - 1, cell.col
            else:  # right (default)
                tr, tc = cell.row, cell.col + cell.col_span
            if (tr, tc) in grid:
                targets.append((tr, tc))
    return targets

def _resolve_anchor_cells(
    parts: Mapping[str, bytes],
    cells: Sequence[Any],
    *,
    exact_cell_labels: bool = False,
) -> tuple[list[Any], list[CellSkipped]]:
    """Turn anchor-bearing cell specs into concrete (table_index,row,col) specs.
    Coordinate specs pass through untouched; unresolvable anchors -> CellSkipped."""
    out: list[Any] = []
    skips: list[CellSkipped] = []
    span_cache: dict[str, list[tuple[int, int]]] = {}
    for cell in cells:
        get = cell.get if isinstance(cell, Mapping) else (lambda k, d=None: getattr(cell, k, d))
        section = str(get("section_path") or get("sectionPath") or "Contents/section0.xml")
        ti = get("table_index", get("tableIndex"))
        row, col = get("row"), get("col")
        tanchor = get("table_anchor") or get("tableAnchor")
        canchor = get("cell_anchor") or get("cellAnchor")
        if tanchor is None and canchor is None:
            out.append(cell)
            continue
        sec = parts.get(section)
        if sec is None:
            skips.append(CellSkipped(section, -1, -1, -1, "section part not found"))
            continue
        spans = span_cache.setdefault(section, _iter_table_spans(sec))
        if ti is None and tanchor is not None:
            m = _find_tables_by_anchor(sec, str(tanchor), spans)
            if len(m) == 1:
                ti = m[0]
            elif not m:
                skips.append(CellSkipped(section, -1, -1, -1, f"table anchor {tanchor!r} matched no table"))
                continue
            else:
                skips.append(CellSkipped(section, -1, -1, -1, f"table anchor {tanchor!r} ambiguous ({len(m)} tables)"))
                continue
        if ti is None:
            skips.append(CellSkipped(section, -1, -1, -1, "cell needs table_index or table_anchor"))
            continue
        ti = int(ti)
        if (row is None or col is None) and canchor is not None:
            if not (0 <= ti < len(spans)):
                skips.append(CellSkipped(section, ti, -1, -1, "table out of range for cell anchor"))
                continue
            s, e = spans[ti]
            cget = canchor.get if isinstance(canchor, Mapping) else (lambda k, d=None: getattr(canchor, k, d))
            label = cget("label") or ""
            direction = str(cget("dir") or cget("direction") or "right")
            m2 = _resolve_cell_anchor(
                sec[s:e],
                str(label),
                direction,
                exact=exact_cell_labels,
            )
            if len(m2) == 1:
                row, col = m2[0]
            elif not m2:
                skips.append(CellSkipped(section, ti, -1, -1, f"cell anchor {label!r}/{direction} matched no cell"))
                continue
            else:
                skips.append(CellSkipped(section, ti, -1, -1, f"cell anchor {label!r}/{direction} ambiguous ({len(m2)})"))
                continue
        nd: dict[str, Any] = {"section_path": section, "table_index": ti, "row": row, "col": col, "text": get("text")}
        mx = get("max_lines", get("maxLines"))
        if mx is not None:
            nd["max_lines"] = mx
        out.append(nd)
    return out, skips


def _normalize(cell: Mapping[str, Any] | Any) -> tuple[str, int, int, int, str, int | None]:
    get = cell.get if isinstance(cell, Mapping) else (lambda k, d=None: getattr(cell, k, d))
    section = str(get("section_path") or get("sectionPath") or "Contents/section0.xml")
    table_index = get("table_index", get("tableIndex"))
    row = get("row")
    col = get("col")
    text = get("text")
    max_lines = get("max_lines", get("maxLines"))
    if table_index is None or row is None or col is None or text is None:
        raise ValueError("cell fill requires table_index, row, col, text")
    return section, int(table_index), int(row), int(col), str(text), (int(max_lines) if max_lines else None)


def resolve_cell_target(
    source: str | Path | bytes,
    locator: Mapping[str, Any],
) -> ResolvedCellTarget:
    """Resolve one existing table/cell locator without mutating the package.

    This is the narrow public planning seam for the same heading/table semantics
    used by :func:`fill_cells`, with stricter normalized-exact adjacent labels.
    It deliberately raises instead of returning a guessed target: zero/multiple
    anchor matches, absent sections, invalid table indices, and out-of-range
    cells all fail closed.
    """

    source_bytes = _read_source_bytes(source)
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as archive:
        parts = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if not info.is_dir()
        }

    # _resolve_anchor_cells also accepts concrete coordinates.  A placeholder
    # text value is supplied only because its historical fill-cell record shape
    # includes text; no edit or serialization occurs here.
    spec = dict(locator)
    spec.setdefault("text", "")
    # Mixed-form planning is a canonical, fail-closed path: after whitespace
    # and punctuation normalization, a cell label must be exactly equal.  The
    # older fill_cells compatibility path deliberately keeps substring matching.
    resolved, skipped = _resolve_anchor_cells(parts, [spec], exact_cell_labels=True)
    if skipped:
        raise ValueError(skipped[0].reason)
    if len(resolved) != 1:
        raise ValueError("cell locator did not resolve exactly one target")

    section_path, table_index, logical_row, logical_col, _text, _max_lines = _normalize(
        resolved[0]
    )
    section = parts.get(section_path)
    if section is None:
        raise ValueError("section part not found")
    spans = _iter_table_spans(section)
    if not 0 <= table_index < len(spans):
        raise ValueError("table_index out of range")
    start, end = spans[table_index]
    grid, report = build_grid(section[start:end])
    if not report.ok:
        raise ValueError("table grid is invalid: " + "; ".join(report.issues[:5]))
    cell = grid.get((logical_row, logical_col))
    if cell is None:
        raise ValueError("cell address out of range")
    return ResolvedCellTarget(
        section_path=section_path,
        table_index=table_index,
        logical_row=logical_row,
        logical_col=logical_col,
        row=cell.row,
        col=cell.col,
    )


def fill_cells(
    source: str | Path | bytes,
    cells: Sequence[Mapping[str, Any] | Any],
    *,
    output_path: str | Path | None = None,
    fit_max_lines: int | None = None,
    min_font_pt: float = 8.0,
) -> CellFillResult:
    """Byte-preserving fill of table cells by ``(table_index, row, col)`` address.

    Only the addressed cells' first-paragraph text is spliced; the stale
    ``<hp:linesegarray>`` of each edited paragraph is stripped. Untouched section
    parts and untouched tables round-trip byte-identical. Empty / self-closing
    cells are filled (text inserted), never silently reported as done. An
    unresolvable address is reported in ``skipped`` and mutates nothing.

    **Font shrink-to-fit** (optional): when ``fit_max_lines`` is set (or a cell
    carries ``max_lines``), a cell whose text would wrap past that many lines at
    its template font is shrunk — the smallest font ``>= min_font_pt`` that fits
    (form_fit FitEngine) is materialised as a real ``charPr`` and the cell's run
    points at it. Column widths and the rest of the document are untouched.
    """
    source_bytes = _read_source_bytes(source)
    if not cells:
        open_safety, _ = _finalize(source_bytes, output_path, source=source)
        return CellFillResult(source_bytes, (), (), (), True, "none", open_safety)

    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zf:
        parts = {i.filename: zf.read(i.filename) for i in zf.infolist() if not i.is_dir()}

    # FR-002: resolve table/cell anchors to concrete (table_index,row,col) first.
    resolved_cells, anchor_skips = _resolve_anchor_cells(parts, cells)
    specs = [_normalize(c) for c in resolved_cells]

    header_name = _header_part_name(parts)
    header_xml = parts.get(header_name) if header_name else None
    charpr_cache: dict[tuple[str, int], str] = {}
    header_changed = False

    applied: list[CellApplied] = []
    skipped: list[CellSkipped] = list(anchor_skips)
    by_section: dict[str, list[tuple[int, int, int, str, int | None]]] = {}
    for section, ti, row, col, text, mx in specs:
        by_section.setdefault(section, []).append((ti, row, col, text, mx))

    if not by_section:
        # every spec was an unresolvable anchor -> source unchanged, skips reported.
        open_safety, _ = _finalize(source_bytes, output_path, source=source)
        return CellFillResult(source_bytes, tuple(applied), tuple(skipped), (), True, "none", open_safety)

    changed_parts: dict[str, bytes] = {}
    for section_path, section_specs in by_section.items():
        section_xml = parts.get(section_path)
        if section_xml is None:
            skipped.extend(CellSkipped(section_path, ti, r, c, "section part not found") for ti, r, c, _t, _m in section_specs)
            continue
        table_spans = _iter_table_spans(section_xml)
        # accumulate byte edits over the whole section (table region splices)
        section_edits: list[tuple[int, int, bytes]] = []
        occupied: list[tuple[int, int]] = []  # filled paragraph spans (merge-collision guard)
        for ti, row, col, text, mx in section_specs:
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
            p_spans = _all_paragraph_spans(cell_bytes)
            if not p_spans:
                skipped.append(CellSkipped(section_path, ti, row, col, "cell has no paragraph"))
                continue
            # Font shrink-to-fit: a cell with a max-lines target whose text would
            # wrap past it gets its run pointed at a smaller (materialised) charPr.
            shrink: tuple[str, str] | None = None
            target = mx or fit_max_lines
            if target and header_xml is not None and text.strip():
                res = _shrunk_font_id(header_xml, cell_bytes, text, target, min_font_pt, charpr_cache)
                if res is not None:
                    header_xml, base_id, new_id = res
                    header_changed = True
                    shrink = (base_id, new_id)
            # Replace the WHOLE cell's visible text with `text`: line k -> paragraph k,
            # trailing paragraphs are emptied (so stale multi-line template content —
            # e.g. stacked 성취기준 codes — does not survive). newline-separated text
            # fills successive paragraphs.
            lines = text.split("\n")
            cell_edits: list[tuple[int, int, bytes]] = []
            first_orig: str | None = None
            collided = False
            for idx, (ps, pe) in enumerate(p_spans):
                para = cell_bytes[ps:pe]
                line = lines[idx] if idx < len(lines) else ""
                edit = _text_edit_for_paragraph(para, line)
                if edit is None:
                    continue
                _s, _e, replacement, original_text = edit
                if idx == 0:
                    first_orig = original_text
                if original_text == line:
                    continue
                a0, a1 = ts + cell.start + ps, ts + cell.start + pe
                if any(a0 < oe and os < a1 for os, oe in occupied):
                    collided = True
                    break
                new_para = _strip_paragraph_layout_cache(replacement if (_s, _e) == (0, len(para)) else _apply_edits(para, [(_s, _e, replacement)]))
                if shrink is not None:
                    base_id, new_id = shrink
                    new_para = re.sub(rb'(charPrIDRef=")' + re.escape(base_id.encode()) + rb'(")', rb"\g<1>" + new_id.encode() + rb"\g<2>", new_para)
                occupied.append((a0, a1))
                cell_edits.append((a0, a1, new_para))
            if collided:
                skipped.append(CellSkipped(section_path, ti, row, col, "cell shares a merged region already filled by an earlier address"))
                continue
            if not cell_edits:
                continue
            # A template's short placeholder may legitimately fit under
            # lineWrap=SQUEEZE, while a real filled value is compressed until
            # glyphs appear to overlap.  Changed non-empty values must wrap and
            # reflow; preserve SQUEEZE for no-op/clear operations.
            if text.strip():
                wrap_edit = _squeeze_wrap_edit(cell_bytes)
                if wrap_edit is not None:
                    ws, we, replacement = wrap_edit
                    section_edits.append(
                        (ts + cell.start + ws, ts + cell.start + we, replacement)
                    )
            section_edits.extend(cell_edits)
            applied.append(CellApplied(section_path, ti, row, col, first_orig or "", text))
        if section_edits:
            new_section = _apply_edits(section_xml, section_edits)
            if new_section != section_xml:
                changed_parts[section_path] = new_section

    if header_changed and header_name and header_xml is not None:
        changed_parts[header_name] = header_xml

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


def _grid_col_widths(table: str) -> dict[int, int] | None:
    """Per-column widths derived from the *merged* grid (FR-003) — for tables that
    have no single uniform ``colSpan==1`` row (e.g. the 반영비율 반영표).

    Every ``colSpan==1`` cell gives its column's width exactly; a remaining column
    that is only ever spanned takes an even split of a covering cell's width across
    its still-unknown columns. Returns ``None`` (fail-closed) if any logical column
    stays underivable, so :func:`_delete_columns` refuses rather than guessing.
    """
    tb = table.encode("utf-8")
    _grid, rep = build_grid(tb)
    ncol = rep.col_count
    cells = _direct_cells(tb)
    widths: dict[int, int] = {}
    for c in cells:
        w = _iattr(tb[c.start:c.end], "cellSz", "width")
        if c.col_span == 1 and w:
            widths[c.col] = w
    for c in cells:  # fill columns only ever covered by a spanning cell
        w = _iattr(tb[c.start:c.end], "cellSz", "width")
        if c.col_span > 1 and w:
            span = range(c.col, c.col + c.col_span)
            unknown = [x for x in span if x not in widths]
            if unknown:
                known = sum(widths[x] for x in span if x in widths)
                each = max(1, (w - known) // len(unknown))
                for i, x in enumerate(unknown):
                    widths[x] = each + ((w - known) - each * len(unknown) if i == len(unknown) - 1 else 0)
    if any(c not in widths for c in range(ncol)):
        return None
    return widths


def _delete_columns(table: str, del_cols: Iterable[int]) -> str:
    _guard_flat(table)
    del_cols = sorted(set(del_cols))
    if not del_cols:
        return table
    dmax = del_cols[-1]
    prefix, rows, suffix = _parse_table(table)
    widths = _uniform_col_widths(rows)
    if widths is None:
        # FR-003: no uniform colSpan==1 row -> derive widths from the merged grid.
        widths = _grid_col_widths(table)
    if widths is None:
        raise TableStructureError(
            "delete_column: no uniform (all colSpan=1) row and merged grid widths "
            "are underivable -- refusing (fail-closed). Fallback: split the merged "
            "header cell that straddles the dropped column manually, then retry."
        )
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


def _physical_row_height(rows: Sequence[str], row: int) -> int | None:
    """Return the exact height of a physical row when direct cells expose it.

    A physical row can contain several ``rowSpan==1`` cells with different
    ``cellSz`` heights.  Hancom uses the tallest direct cell as the row height;
    shorter values can belong to sparse/covered-looking cells.  ``None`` means
    the row is covered entirely by vertical merges and remains underivable.
    """
    heights: list[int] = []
    for physical_row in rows:
        for tc in _S_TC.findall(physical_row):
            ra = _si(tc, "cellAddr", "rowAddr")
            rs = _si(tc, "cellSpan", "rowSpan") or 1
            height = _si(tc, "cellSz", "height")
            if ra == row and rs == 1 and height is not None and height > 0:
                heights.append(height)
    return max(heights) if heights else None


def _delete_rows(table: str, del_rows: Iterable[int]) -> str:
    """Delete physical rows by index, reconciling rowAddr/rowSpan and covering
    cells' height."""
    _guard_flat(table)
    del_rows = sorted(set(del_rows), reverse=True)
    prefix, rows, suffix = _parse_table(table)
    for empty in del_rows:
        if empty >= len(rows):
            raise TableStructureError(f"row index {empty} out of range")
        exact_height = _physical_row_height(rows, empty)
        heights = []
        for r in rows:
            for tc in _S_TC.findall(r):
                ra, rs = _si(tc, "cellAddr", "rowAddr"), _si(tc, "cellSpan", "rowSpan") or 1
                if ra <= empty < ra + rs and rs > 1:
                    h = _si(tc, "cellSz", "height")
                    if h:
                        heights.append(h // rs)
        # Prefer the exact physical-row height.  Fully merged rows expose no
        # rowSpan==1 cell, so preserve the previous conservative estimate there.
        drop_h = exact_height if exact_height is not None else (min(heights) if heights else 0)

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


def _blank_cell_text(tc: str) -> str:
    """Empty every ``<hp:t>`` in a cell + drop stale linesegarray (keep formatting).

    The layout cache references text positions of the OLD text; leaving it on an
    emptied paragraph makes Hangul reject the file ("stale lineseg beyond text
    length"). Stripping it forces recomputation."""
    tc = re.sub(r"(<hp:t\b[^>]*>).*?(</hp:t>)", r"\1\2", tc, flags=re.S)
    tc = re.sub(
        r"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
        "", tc, flags=re.S,
    )
    return tc


def _insert_tc_in_order(row: str, new_tc: str, col: int) -> str:
    """Insert *new_tc* into a ``<hp:tr>`` keeping tcs in ascending colAddr order."""
    at = None
    for m in _S_TC.finditer(row):
        if (_si(m.group(0), "cellAddr", "colAddr") or 0) > col:
            at = m.start()
            break
    if at is None:
        at = row.rindex("</hp:tr>")
    return row[:at] + new_tc + row[at:]


def _split_cell_vertical(table: str, row: int, col: int, sizes: Sequence[int]) -> str:
    """Split the rowSpan cell at (row, col) into ``len(sizes)`` stacked cells with
    the given rowSpans (``sum(sizes)`` must equal the current rowSpan). The first
    keeps (row, col); each subsequent boundary gets a NEW cell cloned from the
    original (borderFill/cellSz/paraPr inherited, text blanked, ids refreshed)
    inserted in colAddr order. Grid-validated; fail-closed."""
    _guard_flat(table)
    sizes = [int(s) for s in sizes]
    if len(sizes) < 2 or any(s < 1 for s in sizes):
        raise TableStructureError("split_cell_vertical: sizes must be >=2 positive integers")
    prefix, rows, suffix = _parse_table(table)
    if not 0 <= row < len(rows):
        raise TableStructureError(f"split_cell_vertical: row {row} out of range")
    target = None
    for tc in _S_TC.findall(rows[row]):
        if _si(tc, "cellAddr", "rowAddr") == row and _si(tc, "cellAddr", "colAddr") == col:
            target = tc
            break
    if target is None:
        raise TableStructureError(f"split_cell_vertical: no cell at (row={row}, col={col})")
    cur = _si(target, "cellSpan", "rowSpan") or 1
    if sum(sizes) != cur:
        raise TableStructureError(f"split_cell_vertical: sizes sum {sum(sizes)} != current rowSpan {cur}")

    rows[row] = rows[row].replace(target, _ss(target, "cellSpan", "rowSpan", sizes[0]), 1)
    boundary = row
    for i in range(1, len(sizes)):
        boundary += sizes[i - 1]
        if boundary >= len(rows):
            raise TableStructureError("split_cell_vertical: boundary beyond table rows")
        new_tc = _ss(target, "cellSpan", "rowSpan", sizes[i])
        new_tc = _ss(new_tc, "cellAddr", "rowAddr", boundary)
        new_tc = _refresh_ids(_blank_cell_text(new_tc), 7000 + i)
        rows[boundary] = _insert_tc_in_order(rows[boundary], new_tc, col)
    out = _rebuild(prefix, rows, suffix)
    _validate_or_raise(out)
    return out


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


def _insert_block_by_clone(table: str, r0: int, r1: int, count: int = 1) -> str:
    """Clone a contiguous **vertical-merge block** (physical rows ``r0..r1``) *count*
    times, preserving the block's internal span pattern (FR-001).

    The 성취기준 A~E unit is one such block: a leading cell with ``rowSpan=N`` plus
    ``N`` rows of ``rowSpan==1`` cells. :func:`_insert_row_by_clone` refuses it (its
    ref row carries the row-spanning anchor); this clones the whole unit, offsets the
    clones' ``rowAddr`` by the block height, shifts every row below, refreshes
    paragraph ids, and grows ``rowCnt``. Fail-closed (Constitution VI): the block must
    be a clean merge unit — no cell inside spans out of ``[r0,r1]`` and no cell
    outside straddles the boundary — else it raises. Formatting (borderFill/paraPr/
    charPr/cellSz) is carried verbatim from the reference block.
    """
    _guard_flat(table)
    if count < 1:
        return table
    prefix, rows, suffix = _parse_table(table)
    if not (0 <= r0 <= r1 < len(rows)):
        raise TableStructureError(f"insert_block_by_clone: ref_rows [{r0},{r1}] out of range (nrows={len(rows)})")
    block_h = r1 - r0 + 1
    for i, row in enumerate(rows):
        for tc in _S_TC.findall(row):
            ra = _si(tc, "cellAddr", "rowAddr")
            rs = _si(tc, "cellSpan", "rowSpan") or 1
            top, bot = ra, ra + rs - 1
            inside = r0 <= i <= r1
            if inside and (top < r0 or bot > r1):
                raise TableStructureError(
                    f"insert_block_by_clone: cell at row{top} rowSpan{rs} crosses the block "
                    f"[{r0},{r1}] boundary -- ref_rows is not a clean vertical-merge unit"
                )
            if not inside and (top < r0 <= bot or top <= r1 < bot):
                raise TableStructureError(
                    f"insert_block_by_clone: outside cell at row{top} rowSpan{rs} straddles the "
                    f"block [{r0},{r1}] -- refusing (fail-closed)"
                )

    def shift(tc: str):
        ra = _si(tc, "cellAddr", "rowAddr")
        if ra > r1:
            return _ss(tc, "cellAddr", "rowAddr", ra + count * block_h)
        return tc

    shifted = [_map_cells(r, shift) for r in rows]
    block = rows[r0:r1 + 1]
    clones: list[str] = []
    for k in range(1, count + 1):
        for row in block:
            clone = _map_cells(row, lambda tc: _ss(tc, "cellAddr", "rowAddr", (_si(tc, "cellAddr", "rowAddr")) + k * block_h))
            clone = _refresh_ids(clone, 100003 * k + 7)
            clones.append(clone)
    new_rows = shifted[: r1 + 1] + clones + shifted[r1 + 1:]
    return _rebuild(prefix, new_rows, suffix, rowcnt=len(new_rows))


def _set_column_widths(table: str, new_widths: dict[int, int]) -> str:
    """Set logical column widths (HWPUNIT). Each cell's cellSz.width = sum of its
    spanned columns' new widths. Byte-preserving cellSz edits; grid unchanged."""
    _guard_flat(table)
    prefix, rows, suffix = _parse_table(table)

    def fix(tc: str):
        ca = _si(tc, "cellAddr", "colAddr")
        cs = _si(tc, "cellSpan", "colSpan") or 1
        w = sum(int(new_widths.get(c, 0)) for c in range(ca, ca + cs))
        if w > 0:
            tc = _ss(tc, "cellSz", "width", w)
        return tc

    rows = [_map_cells(r, fix) for r in rows]
    return _rebuild(prefix, rows, suffix)


def _autofit_columns(table: str, *, min_frac: float = 0.06, damp: float = 0.5) -> str:
    """Rebalance column widths to content: content-heavy columns widen, light ones
    narrow, table total width preserved. Demand = longest single-span cell's text
    width (form_fit advance model), sqrt-damped so a paragraph column doesn't run
    away; every column keeps a floor of *min_frac* of the total."""
    from .form_fit.measure import estimate_text_width

    prefix, rows, suffix = _parse_table(table)
    cur = _uniform_col_widths(rows)
    if cur is None:
        raise TableStructureError("no uniform (all colSpan=1) row to autofit widths")
    ncol = max(cur) + 1
    total = sum(cur.values())
    demand = {c: 0.0 for c in range(ncol)}
    for r in rows:
        for tc in _S_TC.findall(r):
            if (_si(tc, "cellSpan", "colSpan") or 1) != 1:
                continue
            ca = _si(tc, "cellAddr", "colAddr")
            txt = "".join(re.findall(r"<hp:t>(.*?)</hp:t>", tc, re.DOTALL))
            demand[ca] = max(demand[ca], estimate_text_width(txt, 10.0))
    weight = {c: max(demand[c], 1.0) ** damp for c in range(ncol)}
    sw = sum(weight.values()) or 1.0
    floor = total * min_frac
    raw = {c: max(floor, total * weight[c] / sw) for c in range(ncol)}
    scale = total / (sum(raw.values()) or 1.0)
    new = {c: int(round(raw[c] * scale)) for c in range(ncol)}
    # absorb rounding drift into the widest column so the total is exact
    drift = total - sum(new.values())
    new[max(new, key=lambda c: new[c])] += drift
    return _set_column_widths(table, new)


def _validate_or_raise(table: str) -> None:
    _grid, rep = build_grid(table.encode("utf-8"))
    if not rep.ok:
        raise TableStructureError(f"invalid table grid after edit: {rep.issues}")


# --- section-level application (byte-region splice back) ----------------------

def _widths_arg(o: Mapping[str, Any]) -> dict[int, int]:
    w = o["widths"]
    return {int(k): int(v) for k, v in w.items()} if isinstance(w, Mapping) else {i: int(v) for i, v in enumerate(w)}


_STRUCT_OPS = {
    "delete_column": lambda t, o: _collapse_empty_rows(_delete_columns(t, o["cols"] if "cols" in o else [o["col"]])),
    "delete_row": lambda t, o: _delete_rows(t, o["rows"] if "rows" in o else [o["row"]]),
    "insert_row_by_clone": lambda t, o: _insert_row_by_clone(t, o["ref_row"], int(o.get("count", 1))),
    "insert_block_by_clone": lambda t, o: _insert_block_by_clone(t, int(o["ref_rows"][0]), int(o["ref_rows"][1]), int(o.get("count", 1))),
    "set_column_widths": lambda t, o: _set_column_widths(t, _widths_arg(o)),
    "autofit_columns": lambda t, o: _autofit_columns(t, min_frac=float(o.get("min_frac", 0.06)), damp=float(o.get("damp", 0.5))),
    "set_row_heights": lambda t, o: _set_row_heights(
        t, {int(k): int(v) for k, v in dict(o["heights"]).items()}),
    "split_cell_vertical": lambda t, o: _split_cell_vertical(
        t, int(o["row"]), int(o["col"]), o["sizes"]),
}


def _set_row_heights(table: str, heights: Mapping[int, int]) -> str:
    """행높이 명시 설정(HWPUNIT, 1pt=100) — Stage 3 간격 프리미티브.

    rowSpan==1 셀은 해당 행 높이로, 병합 셀은 덮는 행들의 (새/현재) 높이 합으로
    cellSz height를 재계산한다. 현재 행높이를 유도할 수 없는 행이 끼면 refuse
    (fail-closed). 사람 편집자의 "행높이 늘리고/줄여 페이지 안 재배분"에 해당."""
    if len(re.findall(r"<hp:tbl\b", table)) > 1:
        raise TableStructureError("set_row_heights: nested table inside — refuse")
    m_rows = re.search(r'<hp:tbl\b[^>]*\browCnt="(\d+)"', table)
    row_cnt = int(m_rows.group(1)) if m_rows else 0
    for r in heights:
        if not 0 <= r < row_cnt:
            raise TableStructureError(f"set_row_heights: row {r} out of range (0..{row_cnt - 1})")
    cells: list[tuple[int, int, int, int, int]] = []
    for m in re.finditer(r"<hp:tc\b.*?</hp:tc>", table, re.S):
        blk = m.group(0)
        ra = re.search(r'<hp:cellAddr\b[^>]*\browAddr="(\d+)"', blk)
        rs = re.search(r'<hp:cellSpan\b[^>]*\browSpan="(\d+)"', blk)
        hz = re.search(r'<hp:cellSz\b[^>]*\bheight="(\d+)"', blk)
        if ra is None or hz is None:
            raise TableStructureError("set_row_heights: cell without cellAddr/cellSz")
        cells.append((m.start(), m.end(), int(ra.group(1)),
                      int(rs.group(1)) if rs else 1, int(hz.group(1))))
    current: dict[int, int] = {}
    for _, _, ra, rs, h in cells:
        if rs == 1 and ra not in current:
            current[ra] = h

    def _new_height(ra: int, rs: int) -> int:
        total = 0
        for r in range(ra, ra + rs):
            if r in heights:
                total += heights[r]
            elif r in current:
                total += current[r]
            else:
                raise TableStructureError(
                    f"set_row_heights: row {r} current height underivable (no rowSpan==1 cell)")
        return total

    out = table
    for start, end, ra, rs, h in sorted(cells, reverse=True):
        if not any(r in heights for r in range(ra, ra + rs)):
            continue
        nh = _new_height(ra, rs)
        if nh == h:
            continue
        blk = out[start:end]
        blk = re.sub(r'(<hp:cellSz\b[^>]*\bheight=")\d+(")',
                     lambda mm: mm.group(1) + str(nh) + mm.group(2), blk, count=1)
        out = out[:start] + blk + out[end:]
    return out


def _materialize_parapr(header: bytes, base_id: str, line_spacing: int,
                        cache: dict[tuple[str, int], str]) -> tuple[bytes, str]:
    """paraPr *base_id*를 lineSpacing만 바꾼 변형으로 복제(header 추가·itemCnt 범프).

    lineSpacing은 hp:switch/hp:case 분기 안에도 중복 존재하므로 클론 내 전부 치환."""
    key = (base_id, line_spacing)
    if key in cache:
        return header, cache[key]
    bid = re.escape(base_id.encode())
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?paraPr\b[^>]*?\bid="' + bid + rb'".*?</(?:[A-Za-z_][\w.-]*:)?paraPr>', header, re.DOTALL)
    if m is None:
        raise KeyError(f"base paraPr {base_id} not found")
    ids = [int(x) for x in re.findall(rb'<(?:[A-Za-z_][\w.-]*:)?paraPr\b[^>]*?\bid="(\d+)"', header)]
    new_id = str(max(ids) + 1 if ids else 0)
    clone = re.sub(rb'(\bid=")\d+(")', rb'\g<1>' + new_id.encode() + rb'\g<2>', m.group(0), count=1)
    clone = re.sub(rb'(<(?:[A-Za-z_][\w.-]*:)?lineSpacing\b[^>]*?\bvalue=")\d+(")',
                   lambda mm: mm.group(1) + str(line_spacing).encode() + mm.group(2), clone)
    close = re.search(rb'</(?:[A-Za-z_][\w.-]*:)?paraProperties>', header)
    if close is None:
        raise KeyError("paraProperties close tag not found")
    header = header[:close.start()] + clone + header[close.start():]
    header = re.sub(
        rb'(<(?:[A-Za-z_][\w.-]*:)?paraProperties\b[^>]*?\bitemCnt=")(\d+)(")',
        lambda mm: mm.group(1) + str(int(mm.group(2)) + 1).encode() + mm.group(3),
        header, count=1,
    )
    cache[key] = new_id
    return header, new_id


def _apply_cell_line_spacing(
    source_bytes: bytes, ops: Sequence[Mapping[str, Any]],
) -> tuple[bytes, list[dict[str, Any]], list[CellSkipped]]:
    """셀 내부 문단 줄간격 조정 패스 — Stage 3 간격 프리미티브(사람 편집 1순위 수단).

    op: {op:'set_cell_line_spacing', section_path?, table_index|table_anchor,
    cells:[[r,c],...] 또는 rows:[r,...], line_spacing:int(PERCENT)}. 대상 셀의
    각 문단 paraPr을 lineSpacing 변형으로 재매핑하고 linesegarray를 제거한다
    (stale 캐시 줄겹침 방지). 중첩 표를 품은 셀은 refuse."""
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zf:
        parts = {i.filename: zf.read(i.filename) for i in zf.infolist() if not i.is_dir()}
    header_name = _header_part_name(parts)
    header = parts.get(header_name)
    transcript: list[dict[str, Any]] = []
    skipped: list[CellSkipped] = []
    cache: dict[tuple[str, int], str] = {}
    changed_parts: set[str] = set()

    for op in ops:
        sp = str(op.get("section_path") or op.get("sectionPath") or "Contents/section0.xml")
        entry: dict[str, Any] = {"op": "set_cell_line_spacing", "sectionPath": sp}
        section = parts.get(sp)
        spacing = int(op.get("line_spacing", op.get("lineSpacing", 0)))
        if section is None or header is None or spacing <= 0:
            skipped.append(CellSkipped(sp, -1, -1, -1, "set_cell_line_spacing: bad section/header/line_spacing"))
            entry["status"] = "refused: bad section/header/line_spacing"
            transcript.append(entry)
            continue
        spans = _iter_table_spans(section)
        ti_raw = op.get("table_index", op.get("tableIndex"))
        tanchor = op.get("table_anchor") or op.get("tableAnchor")
        if ti_raw is None and tanchor is not None:
            m = _find_tables_by_anchor(section, str(tanchor), spans)
            if len(m) != 1:
                skipped.append(CellSkipped(sp, -1, -1, -1, f"set_cell_line_spacing: anchor {tanchor!r} → {len(m)} tables"))
                entry["status"] = f"refused: anchor → {len(m)} tables"
                transcript.append(entry)
                continue
            ti = m[0]
        else:
            ti = int(ti_raw)
        if not 0 <= ti < len(spans):
            skipped.append(CellSkipped(sp, ti, -1, -1, "set_cell_line_spacing: table_index out of range"))
            entry["status"] = "refused: table_index out of range"
            transcript.append(entry)
            continue
        ts, te = spans[ti]
        table = section[ts:te].decode("utf-8")
        want_cells = {(int(r), int(c)) for r, c in op.get("cells", [])}
        want_rows = {int(r) for r in op.get("rows", [])}
        touched = 0
        out_table = table
        for m in sorted(re.finditer(r"<hp:tc\b.*?</hp:tc>", table, re.S), key=lambda x: -x.start()):
            blk = m.group(0)
            ra = re.search(r'<hp:cellAddr\b[^>]*\browAddr="(\d+)"', blk)
            ca = re.search(r'<hp:cellAddr\b[^>]*\bcolAddr="(\d+)"', blk)
            if ra is None or ca is None:
                continue
            r, c = int(ra.group(1)), int(ca.group(1))
            if not ((r, c) in want_cells or r in want_rows):
                continue
            if "<hp:tbl" in blk:
                skipped.append(CellSkipped(sp, ti, r, c, "set_cell_line_spacing: nested table in cell — refuse"))
                continue
            new_blk = blk
            for pm in sorted(re.finditer(r"<hp:p\b.*?</hp:p>", new_blk, re.S), key=lambda x: -x.start()):
                pblk = pm.group(0)
                pid = re.search(r'\bparaPrIDRef="(\d+)"', pblk)
                if pid is None:
                    continue
                header, new_id = _materialize_parapr(header, pid.group(1), spacing, cache)
                pblk2 = pblk.replace(f'paraPrIDRef="{pid.group(1)}"', f'paraPrIDRef="{new_id}"', 1)
                pblk2 = _strip_paragraph_layout_cache(pblk2.encode("utf-8")).decode("utf-8")
                new_blk = new_blk[: pm.start()] + pblk2 + new_blk[pm.end():]
            if new_blk != blk:
                out_table = out_table[: m.start()] + new_blk + out_table[m.end():]
                touched += 1
        if out_table != table:
            parts[sp] = section[:ts] + out_table.encode("utf-8") + section[te:]
            changed_parts.add(sp)
        entry.update({"tableIndex": ti, "lineSpacing": spacing, "cellsTouched": touched,
                      "status": "applied" if touched else "refused: no matching cells"})
        if not touched:
            skipped.append(CellSkipped(sp, ti, -1, -1, "set_cell_line_spacing: no matching cells"))
        transcript.append(entry)

    if changed_parts and header_name:
        parts[header_name] = header
        payload = {n: parts[n] for n in changed_parts | {header_name}}
        try:
            out = _patch_zip_entries(source_bytes, payload)
        except ValueError:
            out = _rewrite_zip_entries(source_bytes, payload)
        return out, transcript, skipped
    return source_bytes, transcript, skipped


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
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist() if re.search(r"section\d+\.xml$", n)}


def _table_dims(table: str | bytes) -> str:
    """``"RxC"`` from the table's own rowCnt/colCnt attributes (transcript용)."""
    text = table.decode("utf-8", "ignore") if isinstance(table, bytes) else table
    m = re.search(r'rowCnt="(\d+)"[^>]*colCnt="(\d+)"|colCnt="(\d+)"[^>]*rowCnt="(\d+)"', text)
    if not m:
        return "?"
    if m.group(1) is not None:
        return f"{m.group(1)}x{m.group(2)}"
    return f"{m.group(4)}x{m.group(3)}"


def apply_table_ops(
    source: str | Path | bytes,
    ops: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> CellFillResult:
    """Apply structure ops (then cell fills) to a document, byte-region splicing
    each changed table back so untouched bytes stay identical.

    Op dicts: ``{op: 'delete_column'|'delete_row'|'delete_table'|
    'insert_row_by_clone'|'insert_block_by_clone'|'fill_cell', section_path?,
    table_index, ...}``. ``insert_block_by_clone`` takes ``ref_rows: [r0, r1]``
    (a vertical-merge block) + ``count``; ``delete_column`` derives widths from the
    merged grid when no uniform ``colSpan==1`` row exists (FR-003).
    Structure ops run first, in order; ``delete_table`` shifts later table indices,
    so sequence table deletes in reverse index order (as the recipe does). Every
    structure edit is grid-validated and refuses on an invalid result
    (fail-closed). Cell fills are then applied on the restructured document via
    :func:`fill_cells`.

    ``dry_run=True`` runs the identical pipeline (resolution·validation·fail-closed
    전부 실제) but never writes ``output_path`` — 상의 루프에서 "이 계획이 무엇을
    바꾸는지"를 transcript(구조 op별 해석·전후 dims)와 applied(old→new 텍스트)로
    보여주는 승인 근거용.
    """
    source_bytes = _read_source_bytes(source)
    struct_ops = [o for o in ops if o.get("op") not in ("fill_cell", "set_cell_line_spacing")]
    spacing_ops = [o for o in ops if o.get("op") == "set_cell_line_spacing"]
    fill_ops = [{**o, "section_path": o.get("section_path") or o.get("sectionPath") or "Contents/section0.xml"}
                for o in ops if o.get("op") == "fill_cell"]

    sections = _sections(source_bytes)
    skipped: list[CellSkipped] = []
    changed: set[str] = set()
    transcript: list[dict[str, Any]] = []

    def _log(name, sp, ti, status, **extra) -> None:
        transcript.append({"op": name, "sectionPath": sp, "tableIndex": ti, "status": status, **extra})

    for op in struct_ops:
        name = op.get("op")
        sp = str(op.get("section_path") or op.get("sectionPath") or "Contents/section0.xml")
        section = sections.get(sp)
        if section is None:
            skipped.append(CellSkipped(sp, -1, -1, -1, "section part not found"))
            _log(name, sp, -1, "refused: section part not found")
            continue
        spans = _iter_table_spans(section)
        ti_raw = op.get("table_index", op.get("tableIndex"))
        tanchor = op.get("table_anchor") or op.get("tableAnchor")
        resolved_by = "index"
        if ti_raw is None and tanchor is not None:
            resolved_by = f"anchor:{tanchor}"
            m = _find_tables_by_anchor(section, str(tanchor), spans)
            if len(m) == 1:
                ti = m[0]
            elif not m:
                skipped.append(CellSkipped(sp, -1, -1, -1, f"{name}: table anchor {tanchor!r} matched no table"))
                _log(name, sp, -1, "refused: anchor matched no table", resolvedBy=resolved_by)
                continue
            else:
                skipped.append(CellSkipped(sp, -1, -1, -1, f"{name}: table anchor {tanchor!r} ambiguous ({len(m)} tables)"))
                _log(name, sp, -1, f"refused: anchor ambiguous ({len(m)} tables)", resolvedBy=resolved_by)
                continue
        else:
            try:
                ti = int(ti_raw)
            except (TypeError, ValueError):
                skipped.append(CellSkipped(sp, -1, -1, -1, f"{name}: table_index or table_anchor required"))
                _log(name, sp, -1, "refused: table_index or table_anchor required")
                continue
        if ti < 0 or ti >= len(spans):
            skipped.append(CellSkipped(sp, ti, -1, -1, "table_index out of range"))
            _log(name, sp, ti, "refused: table_index out of range", resolvedBy=resolved_by)
            continue
        ts, te = spans[ti]
        dims_before = _table_dims(section[ts:te])
        try:
            if name == "delete_table":
                ps, pe = _p_wrapper_span(section, ts)
                new_section = section[:ps] + section[pe:]
                dims_after = "deleted"
            elif name == "clone_table":
                ps, pe = _p_wrapper_span(section, ts)
                block = section[ps:pe].decode("utf-8")
                count = int(op.get("count", 1))
                if count < 1:
                    raise TableStructureError("clone_table: count must be >= 1")
                clones = "".join(
                    _PARA_ID_RE.sub(
                        lambda m, k=k: m.group(1)
                        + str((int(m.group(2)) + 900000 + k * 7919) & 0x7FFFFFFF)
                        + m.group(3),
                        block,
                    )
                    for k in range(1, count + 1)
                )
                new_section = section[:pe] + clones.encode("utf-8") + section[pe:]
                dims_after = f"cloned x{count}"
            elif name in _STRUCT_OPS:
                new_table = _STRUCT_OPS[name](section[ts:te].decode("utf-8"), op)
                _validate_or_raise(new_table)
                new_section = section[:ts] + new_table.encode("utf-8") + section[te:]
                dims_after = _table_dims(new_table)
            else:
                skipped.append(CellSkipped(sp, ti, -1, -1, f"unknown op {name!r}"))
                _log(name, sp, ti, f"refused: unknown op {name!r}", resolvedBy=resolved_by)
                continue
        except TableStructureError as exc:
            skipped.append(CellSkipped(sp, ti, -1, -1, f"{name}: {exc}"))
            _log(name, sp, ti, f"refused: {exc}", resolvedBy=resolved_by, dims=dims_before)
            continue
        sections[sp] = new_section
        changed.add(sp)
        _log(name, sp, ti, "would_apply" if dry_run else "applied",
             resolvedBy=resolved_by, dims=f"{dims_before}→{dims_after}")

    intermediate = source_bytes
    if changed:
        try:
            intermediate = _patch_zip_entries(source_bytes, {sp: sections[sp] for sp in changed})
        except ValueError:
            intermediate = _rewrite_zip_entries(source_bytes, {sp: sections[sp] for sp in changed})

    if spacing_ops:
        intermediate, sp_transcript, sp_skips = _apply_cell_line_spacing(intermediate, spacing_ops)
        if dry_run:
            for e in sp_transcript:
                if e.get("status") == "applied":
                    e["status"] = "would_apply"
        transcript.extend(sp_transcript)
        skipped.extend(sp_skips)
        if intermediate != source_bytes:
            changed.update(e["sectionPath"] for e in sp_transcript if "would_apply" in e.get("status", "") or e.get("status") == "applied")

    effective_output = None if dry_run else output_path
    if fill_ops:
        fres = fill_cells(intermediate, fill_ops, output_path=effective_output)
        return CellFillResult(
            fres.data, fres.applied, tuple(skipped) + fres.skipped,
            tuple(sorted(changed | set(fres.changed_parts))),
            fres.data == source_bytes,
            "partial-local-record-copy" if (changed or fres.changed_parts) else "none",
            fres.open_safety,
            tuple(transcript),
        )

    open_safety, _ = _finalize(intermediate, effective_output, source=source)
    return CellFillResult(
        intermediate, (), tuple(skipped), tuple(sorted(changed)),
        intermediate == source_bytes,
        "partial-local-record-copy" if changed else "none", open_safety,
        tuple(transcript),
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


# --- FR-006: compact document map (summary, no per-cell dump) -----------------

def table_summary(source: str | Path | bytes) -> list[dict[str, Any]]:
    """Compact per-table map (FR-006) — bounded output for a whole form in one read.

    For each table: ``{tableIndex, sectionPath, rows, cols (logical), merges,
    heading (preceding section heading/label), firstRow (first logical row
    preview)}`` — **no per-cell paragraph dump**, so a 37-table form fits well
    under the token limit. ``tableIndex``/``sectionPath`` match the addressing
    :func:`apply_table_ops`/:func:`fill_cells` accept; ``heading`` is the same
    text :func:`_find_tables_by_anchor` resolves. The heavy full map stays.
    """
    data = _read_source_bytes(source)
    out: list[dict[str, Any]] = []
    for sp, section in sorted(_sections(data).items()):
        spans = _iter_table_spans(section)
        is_data = [_phys_row_count(section[s:e]) >= 2 for (s, e) in spans]
        for ti, (s, e) in enumerate(spans):
            table = section[s:e]
            grid, rep = build_grid(table)
            merges = sum(1 for c in _direct_cells(table) if c.row_span > 1 or c.col_span > 1)
            w_start = 0
            for j in range(ti - 1, -1, -1):
                if is_data[j]:
                    w_start = spans[j][1]
                    break
            w_start = max(w_start, s - 8000)
            heading = " ".join(_text_of(section[w_start:s]).split())[-70:]
            first: list[str] = []
            for col in range(rep.col_count):
                c = grid.get((0, col))
                cell_txt = " ".join(_text_of(table[c.start:c.end]).split())[:22] if c else ""
                if not first or first[-1] != cell_txt:
                    first.append(cell_txt)
            out.append({
                "tableIndex": ti, "sectionPath": sp,
                "rows": rep.row_count, "cols": rep.col_count, "merges": merges,
                "heading": heading, "firstRow": " | ".join(first)[:90],
            })
    return out


__all__ = [
    "fill_cells", "build_grid", "GridReport", "CellFillResult", "CellApplied", "CellSkipped",
    "ResolvedCellTarget", "resolve_cell_target",
    "apply_table_ops", "TableStructureError", "verify_fill", "RenderCheckRequired", "table_summary",
]
