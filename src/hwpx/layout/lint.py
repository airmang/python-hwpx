# SPDX-License-Identifier: Apache-2.0
"""LayoutLint — renderer-less structural visual smoke (plan §2 Phase D).

Catches *likely* visual problems without a renderer so the **structural tier**
(no Hancom reachable) and fast pre-checks still have teeth. Five checks:

1. **stale lineseg cache** — ``lineseg/@textpos`` beyond the paragraph text length
   (already a ``package_validator`` hard error; surfaced here as a layout finding).
2. **dirty ↔ lineseg consistency** — when an edit ledger is supplied, a paragraph
   a ledger range marked dirty must have had its ``<hp:linesegarray>`` stripped;
   a retained cache is a leak (the exact class of bug the byte path once shipped).
3. **overflow risk** — an un-fitted cell value whose longest unbreakable token is
   grossly wider than the cell (reuses the Phase-C measurement). Gross + an
   ``overflow="fail"`` policy ⇒ a hard error; otherwise a warning.
4. **table structural sanity** — Hancom-required ``tbl``/``tc`` children present
   (reuses ``package_validator``).
5. **table taller than the page** — a body table Hancom does not break across
   pages (inline, or ``pageBreak="NONE"``) whose rows alone are taller than the
   page body, or a row taller than the page body in a table Hancom breaks only
   between rows (``pageBreak="TABLE"``). A row is at least as tall as the lines
   its cells' paragraphs and line breaks force. Rows past the paper's bottom
   edge + an ``overflow="fail"`` policy ⇒ a hard error; otherwise a warning.

Severity discipline (acceptance "stricter, never wronger"): only renderer-less
*provable* defects are errors. Heuristics warn. So the lint never contradicts the
Phase-A oracle — it may flag more, but it does not hard-fail a doc the oracle
would pass.
"""
from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from hwpx.opc.relationships import is_header_part_name, is_section_part_name
from hwpx.tools.package_validator import (
    _check_line_seg_text_positions,
    _check_table_editor_acceptance,
    _local_name,
)

from .report import LayoutFinding, LayoutLintReport
from ..opc.security import guard_zip_file, read_member
from ..oxml.header import parse_char_property, parse_paragraph_property
from ..oxml.section_format import _drawn_page_size
from ..oxml.table_sizes import cell_margins_of

if TYPE_CHECKING:
    from hwpx.quality.ledger import DirtyLayoutLedger
    from hwpx.quality.report import FormReport

# Finding codes the lint actually emits. These line up with the plan's retry-able
# error codes (Appendix A) so the pipeline can surface them verbatim. (The plan's
# LAYOUT_MUTATION_WITHOUT_LEDGER lives in hwpx.quality.report; the lint realises a
# ledger/lineseg leak as STALE_LINESEG_DETECTED rather than a separate code.)
STALE_LINESEG_DETECTED = "STALE_LINESEG_DETECTED"
FIELD_OVERFLOW = "FIELD_OVERFLOW"
REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
TABLE_STRUCTURE_INVALID = "TABLE_STRUCTURE_INVALID"
OVERFLOW_RISK = "OVERFLOW_RISK"
TABLE_TALLER_THAN_PAGE = "TABLE_TALLER_THAN_PAGE"

# A token this many times wider than its cell cannot wrap into it in any renderer
# → a provable horizontal overflow worth a hard error (vs. a borderline guess).
_GROSS_OVERFLOW_FACTOR = 1.5
# ...but only if the absolute spill clears this floor (~3.5mm / a few em). Without
# it a short word in a tiny cell trips a hard fail on a sliver Hancom absorbs —
# the borderline case the measurement-honesty contract defers to the oracle.
_MIN_ABS_OVERFLOW = 2500.0  # HWPUNIT


def lint_layout(
    data: bytes,
    *,
    ledger: "DirtyLayoutLedger | None" = None,
    form: "FormReport | None" = None,
    document: Any | None = None,
    overflow_policy: str = "warn",
    check_overflow: bool = True,
    required_fields: "set[str] | None" = None,
) -> LayoutLintReport:
    """Run the renderer-less layout smoke over serialized HWPX *data*.

    *required_fields* (a set of field ids/names) lets the caller declare which
    native form fields must be filled; an empty one is a ``REQUIRED_FIELD_MISSING``
    error. Auto-detecting "required" awaits the Phase-F form schema, so this stays
    caller-driven and never false-positives on plain templates.
    """

    report = LayoutLintReport()
    section_roots = _section_roots(data)
    report.checked = [name for name, _ in section_roots]

    _lint_stale_cache(report, section_roots)
    _lint_table_structure(report, section_roots)
    _lint_table_page_fit(report, section_roots, overflow_policy, _header_root(data))
    if ledger is not None:
        _lint_dirty_lineseg(report, section_roots, ledger)

    if check_overflow or required_fields:
        _lint_with_document(report, data, document, overflow_policy, check_overflow, required_fields)

    return report


def _lint_with_document(
    report: LayoutLintReport,
    data: bytes,
    document: Any | None,
    overflow_policy: str,
    check_overflow: bool,
    required_fields: "set[str] | None",
) -> None:
    """Open the document once for the geometry-aware checks, guarded.

    The gate contract is *degrade, never crash* (cf. SavePipeline's reference
    stage): any unexpected error here is swallowed into a warning rather than
    propagating out of a save.
    """

    doc = document
    close_after = False
    try:
        if doc is None:
            from hwpx.document import HwpxDocument

            doc = HwpxDocument.open(data)
            close_after = True
        if check_overflow:
            _lint_overflow_risk(report, doc, overflow_policy)
        if required_fields:
            _lint_required_fields(report, doc, required_fields)
    except Exception as exc:  # pragma: no cover - defensive: never crash the gate
        report.add(
            LayoutFinding(
                code=OVERFLOW_RISK,
                message=f"layout overflow/field checks skipped: {type(exc).__name__}: {exc}",
                severity="warning",
            )
        )
    finally:
        if close_after and doc is not None:
            try:
                doc.close()
            except Exception:  # pragma: no cover - defensive
                pass


def _lint_required_fields(
    report: LayoutLintReport, doc: Any, required_fields: "set[str]"
) -> None:
    """Flag declared-required native form fields that are empty (plan §2 D)."""

    try:
        fields = doc.fields.all
    except Exception:  # pragma: no cover - defensive
        return
    wanted = {str(f) for f in required_fields}
    for field in fields:
        # 6.0: list_form_fields returns FormField objects, not dicts. The old
        # .get() calls raised AttributeError here, and the defensive except in
        # lint_layout swallowed it into a silent "skipped" verdict - exactly
        # the launder-a-crash-into-a-pass shape the save-pipeline repair
        # removed. Attribute access fails loudly if the shape drifts again.
        ids = {str(field.field_id or ""), str(field.name or "")}
        if not (ids & wanted):
            continue
        if not str(field.value or "").strip():
            label = field.name or field.field_id
            report.add(
                LayoutFinding(
                    code=REQUIRED_FIELD_MISSING,
                    message=f"required form field {label!r} is empty",
                    severity="error",
                    detail={"field": label},
                )
            )


# --------------------------------------------------------------------------- #
# Section parsing.
# --------------------------------------------------------------------------- #
def _section_roots(data: bytes) -> list[tuple[str, ET.Element]]:
    roots: list[tuple[str, ET.Element]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            guard_zip_file(archive)
            for info in archive.infolist():
                if info.is_dir() or not is_section_part_name(info.filename):
                    continue
                try:
                    roots.append((info.filename, ET.fromstring(read_member(archive, info))))
                except ET.ParseError:
                    # Malformed XML is the pipeline's well-formedness floor, not ours.
                    continue
    except (zipfile.BadZipFile, OSError):
        return []
    return roots


def _header_root(data: bytes) -> ET.Element | None:
    """The header part: its character and paragraph shapes size a cell's lines."""

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            guard_zip_file(archive)
            for info in archive.infolist():
                if info.is_dir() or not is_header_part_name(info.filename):
                    continue
                try:
                    return ET.fromstring(read_member(archive, info))
                except ET.ParseError:
                    return None
    except (zipfile.BadZipFile, OSError):
        return None
    return None


# --------------------------------------------------------------------------- #
# 1 + 4: reuse the package_validator structural checks.
# --------------------------------------------------------------------------- #
def _lint_stale_cache(report: LayoutLintReport, roots: list[tuple[str, ET.Element]]) -> None:
    for part_name, root in roots:
        issues: list[Any] = []
        _check_line_seg_text_positions(issues, part_name, root)
        for issue in issues:
            report.add(
                LayoutFinding(
                    code=STALE_LINESEG_DETECTED,
                    message=issue.message,
                    severity="error" if issue.is_error else "warning",
                    part=part_name,
                )
            )


def _lint_table_structure(report: LayoutLintReport, roots: list[tuple[str, ET.Element]]) -> None:
    for part_name, root in roots:
        issues: list[Any] = []
        _check_table_editor_acceptance(issues, part_name, root)
        for issue in issues:
            report.add(
                LayoutFinding(
                    code=TABLE_STRUCTURE_INVALID,
                    message=issue.message,
                    severity="error" if issue.is_error else "warning",
                    part=part_name,
                )
            )


# --------------------------------------------------------------------------- #
# 2: dirty ↔ lineseg consistency (ledger-gated).
# --------------------------------------------------------------------------- #
def _lint_dirty_lineseg(
    report: LayoutLintReport,
    roots: list[tuple[str, ET.Element]],
    ledger: "DirtyLayoutLedger",
) -> None:
    by_part = {name: root for name, root in roots}
    for entry in ledger.ranges:
        root = by_part.get(entry.part)
        if root is None:
            continue  # part unknown / not a section → cannot locate precisely
        # start_paragraph is the paragraph's index in flat document order
        # (root.iter() over <hp:p>, cell subList paragraphs INCLUDED) — the same
        # numbering package_validator uses. Producers must use that convention.
        paragraphs = [el for el in root.iter() if _local_name(el) == "p"]
        start = entry.start_paragraph
        end = entry.end_paragraph if entry.end_paragraph is not None else start
        if start is None:
            continue  # cell-only entries carry no paragraph index to verify
        for index in range(start, end + 1):
            if 0 <= index < len(paragraphs):
                if _has_lineseg(paragraphs[index]):
                    report.add(
                        LayoutFinding(
                            code=STALE_LINESEG_DETECTED,
                            message=(
                                f"paragraph {index} is marked dirty ({entry.reason}) but "
                                "still carries a <hp:linesegarray> cache (strip leaked)"
                            ),
                            severity="error",
                            part=entry.part,
                            paragraph=index,
                        )
                    )


def _has_lineseg(paragraph: ET.Element) -> bool:
    return any(_local_name(child).lower() == "linesegarray" for child in paragraph)


# --------------------------------------------------------------------------- #
# 3: overflow risk (reuse the Phase-C measurement).
# --------------------------------------------------------------------------- #
# Vertical balloon: content needing this many × the cell's own line budget (and at
# least this many lines) is grossly over-tall — a warning, since Hancom grows the
# row rather than clipping (so it is not a hard, open-unsafe defect).
_BALLOON_FACTOR = 2.5
_BALLOON_MIN_LINES = 6
_LINE_SPACING = 1.6  # approx line advance as a multiple of the em


def _lint_overflow_risk(
    report: LayoutLintReport,
    doc: Any,
    overflow_policy: str,
) -> None:
    from hwpx.form_fit.measure import (
        _break_opportunities,
        estimate_lines,
        estimate_text_width,
        resolve_slot_metrics,
    )

    for _table, cell in _iter_cells(doc):
        try:
            text = (cell.text or "").strip()
            if not text:
                continue
            slot = resolve_slot_metrics(cell, doc, max_lines=1)
            if slot.available_width <= 0:
                continue
            addr = _safe_addr(cell)

            # (a) Horizontal: the longest *unbreakable* run (Hangul/wide and spaces
            # ARE break opportunities, so this is empty for normal Korean text) that
            # is wider than the slot will spill — it cannot wrap.
            longest = _longest_unbreakable_width(
                text, slot.font_pt, _break_opportunities, estimate_text_width
            )
            if longest > slot.available_width:
                ratio = longest / slot.available_width
                over_abs = longest - slot.available_width
                gross = ratio >= _GROSS_OVERFLOW_FACTOR and over_abs >= _MIN_ABS_OVERFLOW
                severity = "error" if (gross and overflow_policy == "fail") else "warning"
                report.add(
                    LayoutFinding(
                        code=FIELD_OVERFLOW if severity == "error" else OVERFLOW_RISK,
                        message=(
                            f"cell {addr} has an unbreakable run ~{ratio:.1f}× wider than "
                            f"the slot ({text[:24]!r}…); it will overflow horizontally"
                        ),
                        severity=severity,
                        detail={"ratio": round(ratio, 3), "addr": addr, "kind": "horizontal"},
                    )
                )

            # (b) Vertical balloon: content needs far more lines than the cell's own
            # height budgets for — the row will balloon (the headline FormFit defect).
            lines = estimate_lines(text, slot.available_width, slot.font_pt)
            budget = _cell_line_budget(cell, slot.font_pt)
            if budget and lines >= _BALLOON_MIN_LINES and lines >= budget * _BALLOON_FACTOR:
                report.add(
                    LayoutFinding(
                        code=OVERFLOW_RISK,
                        message=(
                            f"cell {addr} content needs ~{lines} lines but the cell budgets "
                            f"~{budget}; the row will balloon ({text[:24]!r}…)"
                        ),
                        severity="warning",
                        detail={"lines": lines, "budget": budget, "addr": addr, "kind": "vertical"},
                    )
                )
        except Exception:  # pragma: no cover - defensive: one bad cell never breaks the scan
            continue


def _longest_unbreakable_width(text, font_pt, break_fn, width_fn) -> float:
    boundaries = sorted(set(break_fn(text)) | {0, len(text)})
    widest = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        widest = max(widest, width_fn(text[start:end], font_pt))
    return widest


def _cell_line_budget(cell: Any, font_pt: float) -> int | None:
    height = float(getattr(cell, "height", 0) or 0)
    if height <= 0:
        return None
    line_height = font_pt * 100.0 * _LINE_SPACING
    if line_height <= 0:
        return None
    return max(int(height // line_height), 1)


def _safe_addr(cell: Any):
    try:
        return list(cell.address)
    except Exception:  # pragma: no cover - defensive
        return None


def _iter_cells(doc: Any):
    for section in getattr(doc, "sections", []):
        for paragraph in getattr(section, "paragraphs", []):
            for table in getattr(paragraph, "tables", []):
                try:
                    grid = list(table.iter_grid())
                except Exception:  # pragma: no cover - defensive
                    continue
                seen: set[int] = set()
                for entry in grid:
                    marker = id(entry.cell.element)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    yield table, entry.cell


# --------------------------------------------------------------------------- #
# 5: a table (or a row) Hancom does not break across pages, taller than the page.
# --------------------------------------------------------------------------- #
_HWPUNIT_PER_MM = 7200 / 25.4


def _lint_table_page_fit(
    report: LayoutLintReport,
    roots: list[tuple[str, ET.Element]],
    overflow_policy: str,
    header: ET.Element | None = None,
) -> None:
    """Flag body tables that cannot break across pages yet are taller than one.

    Hancom never breaks an inline table (``treatAsChar="1"``, the ``add_table``
    default) across pages, nor a table whose ``pageBreak`` is ``NONE``. Such a
    table taller than the page body is drawn on one page (the next one unless it
    starts at the top of a page) and runs on into the bottom margin; rows past
    the paper's bottom edge are not drawn at all. A table whose ``pageBreak`` is
    ``TABLE`` breaks only between rows, so one of its rows taller than the page
    body is drawn the same way; ``CELL`` also breaks a row between its lines.

    The heights are lower bounds: every row is at least its tallest single-row
    cell, and a cell at least the lines its text takes (see :class:`_LineHeights`).
    Lines text wraps into count only as many as the text takes even with every
    character narrower by its measurement error, so a finding never rests on a
    line Hancom may not draw.
    """

    lines = _LineHeights(header)
    for part_name, root in roots:
        page = _page_heights(root)
        if page is None:
            continue
        body, to_edge = page
        numbers = {id(el): i for i, el in enumerate(el for el in root.iter() if _local_name(el) == "p")}
        for paragraph, table in _body_tables(root):
            position = next((child for child in table if _local_name(child) == "pos"), None)
            inline = position is not None and position.get("treatAsChar", "1") == "1"
            page_break = table.get("pageBreak", "CELL")
            if not inline and page_break not in ("NONE", "TABLE"):
                continue  # Hancom breaks it between rows and inside them (CELL)
            rows = _row_min_heights(table, lines)
            whole = inline or page_break == "NONE"
            height = sum(rows) if whole else max(rows, default=0)
            if height > body:
                report.add(
                    _table_page_finding(
                        part_name, numbers.get(id(paragraph)), inline, height, body, to_edge,
                        overflow_policy, row=None if whole else rows.index(height),
                    )
                )


def _table_page_finding(
    part_name: str,
    paragraph: int | None,
    inline: bool,
    height: int,
    body: int,
    to_edge: int,
    overflow_policy: str,
    row: int | None = None,
) -> LayoutFinding:
    cut = height > to_edge
    detail: dict[str, Any] = {"min_height": height, "page_body": body, "to_paper_edge": to_edge,
                              "inline": inline, "rows_cut": cut}
    if row is None:
        kind = "an inline table" if inline else 'a table with pageBreak="NONE"'
        fix = "Table.set_treat_as_char(False)" if inline else 'pageBreak="CELL"'
        outcome = "rows past the paper's bottom edge are not drawn" if cut else "it runs into the bottom margin"
        message = (
            f"{kind} at least {height / _HWPUNIT_PER_MM:.0f} mm tall does not fit the "
            f"{body / _HWPUNIT_PER_MM:.0f} mm page body, and Hancom does not break it across pages: "
            f"it is drawn on one page (the next one unless it starts at the top) and {outcome} "
            f"(use {fix} to let it flow across pages)"
        )
    else:
        detail["row"] = row
        outcome = "lines past the paper's bottom edge are not drawn" if cut else "it runs into the bottom margin"
        message = (
            f'a row of a table with pageBreak="TABLE" at least {height / _HWPUNIT_PER_MM:.0f} mm tall does '
            f"not fit the {body / _HWPUNIT_PER_MM:.0f} mm page body, and Hancom breaks this table only "
            f"between rows: the row is drawn on one page and {outcome} "
            f'(use pageBreak="CELL" to let the row break across pages)'
        )
    return LayoutFinding(
        code=TABLE_TALLER_THAN_PAGE,
        message=message,
        severity="error" if (cut and overflow_policy == "fail") else "warning",
        part=part_name,
        paragraph=paragraph,
        detail=detail,
    )


def _page_heights(root: ET.Element) -> tuple[int, int] | None:
    """(page body height, body top to the paper's bottom edge) of a section.

    Hancom puts the header area below the top margin and the footer area above
    the bottom margin, so the body is the drawn page height less all four.
    """

    page = next((el for el in root.iter() if _local_name(el) == "pagePr"), None)
    if page is None:
        return None
    margin = next((el for el in page if _local_name(el) == "margin"), None)
    if margin is None:
        return None
    try:
        _, height = _drawn_page_size(
            int(page.get("width", "")), int(page.get("height", "")), page.get("landscape")
        )
        top, bottom, header, footer = (
            int(margin.get(key, "0")) for key in ("top", "bottom", "header", "footer")
        )
    except ValueError:
        return None
    to_edge = height - top - header
    return to_edge - bottom - footer, to_edge


def _body_tables(root: ET.Element) -> Iterator[tuple[ET.Element, ET.Element]]:
    """Tables anchored in the section's own paragraphs (not in cells or boxes)."""

    for paragraph in root:
        if _local_name(paragraph) != "p":
            continue
        for run in paragraph:
            if _local_name(run) != "run":
                continue
            for child in run:
                if _local_name(child) == "tbl":
                    yield paragraph, child


def _row_min_heights(table: ET.Element, lines: "_LineHeights") -> list[int]:
    """Lower bounds of the drawn row heights: each row is at least its tallest
    single-row cell, and a cell at least its declared height and the lines its text takes."""

    heights_by_row = []
    for row in table:
        if _local_name(row) != "tr":
            continue
        heights = [0]
        for cell in row:
            if _local_name(cell) == "tc" and _cell_int(cell, "cellSpan", "rowSpan", 1) == 1:
                heights.append(max(_cell_int(cell, "cellSz", "height", 0), lines.cell_height(cell, table)))
        heights_by_row.append(max(heights))
    return heights_by_row


class _LineHeights:
    """How tall Hancom draws, at least, the lines of a cell's text, from the header's shapes.

    A paragraph has at least one line, plus one per line break (``hp:lineBreak``,
    or a newline in its text, which Hancom shows as one). Text in a single
    character shape also takes the lines it wraps into at the cell's inner width
    (FormFit's line breaking), counted with every character narrower by its
    measurement error so that the count never exceeds what Hancom draws. A
    paragraph with a tab, an object or text in more than one character shape
    counts its forced lines only. Its n lines take n - 1 line pitches and one
    line's size, and the next paragraph starts one pitch below the last line. A
    line is at least as tall as the smallest character shape of its paragraph,
    and the spacing before and after paragraphs is left out, so the sum is a
    lower bound. A cell with a paragraph whose shapes are unknown, sized from the
    font (``fontLineHeight``) or set vertically adds nothing to its declared height.
    """

    def __init__(self, header: ET.Element | None) -> None:
        self._sizes: dict[str, int] = {}
        self._spacings: dict[str, tuple[str, float]] = {}
        for element in header.iter() if header is not None else ():
            name = _local_name(element)
            if name == "charPr":
                try:
                    self._sizes[element.get("id", "")] = int(element.get("height", ""))
                except ValueError:
                    continue
            elif name == "paraPr":
                shape = parse_paragraph_property(element)
                spacing = shape.line_spacing
                if shape.font_line_height or spacing is None or spacing.value is None:
                    continue
                self._spacings[element.get("id", "")] = (spacing.spacing_type or "PERCENT", spacing.value)
        self._shapes = _HeaderShapes(header) if header is not None else None
        self._styles: dict[tuple[str, str], Any] = {}

    def cell_height(self, cell: ET.Element, table: ET.Element) -> int:
        sub_list = next((el for el in cell if _local_name(el) == "subList"), None)
        if sub_list is None or sub_list.get("textDirection", "HORIZONTAL") != "HORIZONTAL":
            return 0
        margins = cell_margins_of(cell, table)
        width = _cell_int(cell, "cellSz", "width", 0) - (margins.left + margins.right if margins is not None else 0)
        content = self._paragraphs_height([el for el in sub_list if _local_name(el) == "p"], width)
        if content is None:
            return 0
        return content + (margins.top + margins.bottom if margins is not None else 0)

    def _paragraphs_height(self, paragraphs: list[ET.Element], width: int) -> int | None:
        from hwpx.form_fit.measure import _line_pitch

        if not paragraphs:
            return None
        total = 0
        for index, paragraph in enumerate(paragraphs):
            spacing = self._spacings.get(paragraph.get("paraPrIDRef", ""))
            sizes = [self._sizes.get(run.get("charPrIDRef", "")) for run in paragraph if _local_name(run) == "run"]
            if spacing is None or not sizes or None in sizes:
                return None
            size = min(size for size in sizes if size is not None)
            pitch = int(_line_pitch(spacing[0], spacing[1], size))
            total += max(_forced_lines(paragraph), self._wrapped_lines(paragraph, width)) * pitch
            if index == len(paragraphs) - 1:
                total += size - pitch  # the last line takes its size, not a pitch
        return total

    def _wrapped_lines(self, paragraph: ET.Element, width: int) -> int:
        """Lines single-shape text takes at *width*, never more than Hancom draws (0 when not counted)."""

        from hwpx.form_fit.measure import MIN_LINE_WIDTH, _uncertainty_band, hancom_line_starts, text_style_from_refs

        text, shapes = _measurable_text(paragraph)
        size = self._sizes.get(next(iter(shapes), ""))
        if self._shapes is None or not text or len(shapes) != 1 or size is None:
            return 0
        key = (paragraph.get("paraPrIDRef", ""), next(iter(shapes)))
        if key not in self._styles:
            self._styles[key] = text_style_from_refs(self._shapes, key[0], [key[1]])
        style = self._styles[key]
        # Every advance narrower by the measurement error: the line holds at least as much as Hancom's.
        line = max(width - style.margin_left - style.margin_right, MIN_LINE_WIDTH) / (1.0 - _uncertainty_band(text))
        return sum(len(hancom_line_starts(part, [line], size / 100, style)) if part else 1 for part in text.split("\n"))


class _HeaderShapes:
    """The character and paragraph shapes of a raw ``header.xml``, as FormFit reads them from a document."""

    def __init__(self, header: ET.Element) -> None:
        self.headers = [SimpleNamespace(element=header)]
        self._chars = {el.get("id", ""): el for el in header.iter() if _local_name(el) == "charPr"}
        self._paras = {el.get("id", ""): el for el in header.iter() if _local_name(el) == "paraPr"}

    def char_property(self, char_pr_id_ref: object) -> Any:
        element = self._chars.get(str(char_pr_id_ref))
        return parse_char_property(element) if element is not None else None  # type: ignore[arg-type]

    def paragraph_property(self, para_pr_id_ref: object) -> Any:
        element = self._paras.get(str(para_pr_id_ref))
        return parse_paragraph_property(element) if element is not None else None


#: Run children with no width of their own: field start and end marks.
_ZERO_WIDTH_CONTROLS = frozenset({"fieldBegin", "fieldEnd"})


def _measurable_text(paragraph: ET.Element) -> tuple[str | None, set[str]]:
    """The paragraph's text (line breaks as newlines) and the character shapes of the runs holding it;
    no text when anything but plain text, line breaks and field marks is in it."""

    parts: list[str] = []
    shapes: set[str] = set()
    for run in paragraph:
        if _local_name(run) != "run":
            continue
        for child in run:
            name = _local_name(child)
            if name == "ctrl" and all(_local_name(mark) in _ZERO_WIDTH_CONTROLS for mark in child):
                continue
            text = _plain_text(child) if name == "t" else None
            if text is None:
                return None, set()
            if text:
                parts.append(text)
                shapes.add(run.get("charPrIDRef", ""))
    return "".join(parts), shapes


def _plain_text(text_element: ET.Element) -> str | None:
    """An ``hp:t``'s text with ``hp:lineBreak`` as a newline; None when it holds anything else."""

    parts = [text_element.text or ""]
    for child in text_element:
        if _local_name(child) != "lineBreak":
            return None
        parts.append("\n" + (child.tail or ""))
    return "".join(parts)


def _forced_lines(paragraph: ET.Element) -> int:
    """One line, plus one per ``hp:lineBreak`` or newline in the paragraph's text."""

    lines = 1
    for run in paragraph:
        if _local_name(run) != "run":
            continue
        for text in run:
            if _local_name(text) != "t":
                continue
            lines += (text.text or "").count("\n")
            for child in text:
                lines += (_local_name(child) == "lineBreak") + (child.tail or "").count("\n")
    return lines


def _cell_int(cell: ET.Element, child_name: str, attribute: str, default: int) -> int:
    child = next((el for el in cell if _local_name(el) == child_name), None)
    if child is None:
        return default
    try:
        return int(child.get(attribute, default))
    except ValueError:
        return default

__all__ = [
    "lint_layout",
    "STALE_LINESEG_DETECTED",
    "FIELD_OVERFLOW",
    "REQUIRED_FIELD_MISSING",
    "TABLE_STRUCTURE_INVALID",
    "OVERFLOW_RISK",
    "TABLE_TALLER_THAN_PAGE",
]
