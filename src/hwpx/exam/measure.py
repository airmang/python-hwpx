# SPDX-License-Identifier: Apache-2.0
"""Pure render-geometry helpers for the 문항-split oracle gate.

Lifted from the Phase-0 spike (scripts/exam_spike_keep_together.py) so the
composer's gate and the spike share ONE implementation (DRY)."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from hwpx.form_fit.wordbox import extract_glyph_boxes
from hwpx.visual.oracle import Block, detect_block_splits

DEFAULT_QUESTION_MARKER = re.compile(r"^\s*(\d+)\s*\.")


def column_x_bounds(glyphs) -> list[tuple[float, float]]:
    """Derive two column x-ranges by splitting the body x-extent at mid-gutter.

    Cluster glyph x-centers into a left group and a right group at the page
    mid-line; the bounds are each group's [min x0, max x1].
    """
    if not glyphs:
        return []
    xs0 = min(g.x0 for g in glyphs)
    xs1 = max(g.x1 for g in glyphs)
    mid = (xs0 + xs1) / 2.0
    left = [g for g in glyphs if (g.x0 + g.x1) / 2.0 < mid]
    right = [g for g in glyphs if (g.x0 + g.x1) / 2.0 >= mid]
    bounds: list[tuple[float, float]] = []
    if left:
        bounds.append((min(g.x0 for g in left), max(g.x1 for g in left)))
    if right:
        bounds.append((min(g.x0 for g in right), max(g.x1 for g in right)))
    return bounds


def group_question_blocks(glyphs, *, marker_re: re.Pattern = DEFAULT_QUESTION_MARKER) -> list[Block]:
    """Group glyphs into one Block per question, sliced on *marker_re*.

    A question owns every glyph from its marker's (page, line position) up to
    the next question's marker, in reading order.  The block id is
    ``m.group(1)`` — the captured group from *marker_re*.

    Reading order is (page, column [left before right by page mid], y, x).
    """
    if not glyphs:
        return []

    line_key = lambda g: (g.page, g.block, g.line)
    lines: dict[tuple, list] = defaultdict(list)
    for g in glyphs:
        lines[line_key(g)].append(g)

    records = []
    for gl in lines.values():
        gl_sorted = sorted(gl, key=lambda g: g.x0)
        text = "".join(g.text for g in gl_sorted)
        cx = sum((g.x0 + g.x1) / 2.0 for g in gl_sorted) / len(gl_sorted)
        cy = sum((g.y0 + g.y1) / 2.0 for g in gl_sorted) / len(gl_sorted)
        records.append({"page": gl_sorted[0].page, "cx": cx, "cy": cy, "text": text, "glyphs": gl_sorted})

    by_page: dict[int, list] = defaultdict(list)
    for rec in records:
        by_page[rec["page"]].append(rec)
    ordered: list[dict] = []
    for page in sorted(by_page):
        recs = by_page[page]
        xs0 = min(r["cx"] for r in recs)
        xs1 = max(r["cx"] for r in recs)
        mid = (xs0 + xs1) / 2.0
        recs.sort(key=lambda r: (0 if r["cx"] < mid else 1, r["cy"], r["cx"]))
        ordered.extend(recs)

    blocks: list[Block] = []
    cur_id: str | None = None
    cur_glyphs: list = []
    for rec in ordered:
        m = marker_re.search(rec["text"]) or marker_re.search(rec["text"].replace(" ", ""))
        if m is not None:
            if cur_id is not None:
                blocks.append(Block(id=cur_id, glyphs=cur_glyphs))
            cur_id = m.group(1)
            cur_glyphs = list(rec["glyphs"])
        elif cur_id is not None:
            cur_glyphs.extend(rec["glyphs"])
    if cur_id is not None:
        blocks.append(Block(id=cur_id, glyphs=cur_glyphs))
    return blocks


@dataclass(frozen=True, slots=True)
class SplitReport:
    """Summary of 문항 split detection for one rendered PDF."""

    n_splits: int
    n_blocks: int
    n_glyphs: int
    kinds: dict[str, int]
    split_ids: tuple[str, ...]


def measure_question_splits(pdf_path: str, *, marker_re: re.Pattern = DEFAULT_QUESTION_MARKER) -> SplitReport:
    """Extract glyphs from *pdf_path* and report how many blocks are split.

    Args:
        pdf_path: Path to a rendered PDF.
        marker_re: Compiled regex whose group(1) identifies the question number.
            Defaults to :data:`DEFAULT_QUESTION_MARKER`.

    Returns:
        A :class:`SplitReport` summarising split counts, block counts, and kinds.
    """
    glyphs = extract_glyph_boxes(pdf_path)
    blocks = group_question_blocks(glyphs, marker_re=marker_re)
    page_height = max((g.y1 for g in glyphs), default=0.0)
    bounds = column_x_bounds(glyphs)
    splits = detect_block_splits(blocks, bounds, page_height)
    kinds: dict[str, int] = {}
    for s in splits:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    return SplitReport(len(splits), len(blocks), len(glyphs), kinds, tuple(s.block_id for s in splits))
