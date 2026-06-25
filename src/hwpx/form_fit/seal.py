# SPDX-License-Identifier: Apache-2.0
"""직인/관인 placement compliance (M2 P3 / FR-003).

A Korean official document's seal (직인/관인) is placed *by rule*: its **center**
must sit on the **last glyph of the 발신명의** line (the issuer-name line, e.g.
``"행정안전부장관 홍길동"``). This module decides that rule **geometrically**
against the Hancom render boxes — reusing the word-box oracle
(:mod:`hwpx.form_fit.wordbox`) rather than guessing from the document model, since
the truth is where Hancom *drew* the glyph, not where the XML nominally puts it.

Two pure-geometry entry points, offline-testable:

* :func:`find_seal_anchor` — locate the last glyph of the 발신명의 line in a set of
  glyph boxes (the seal's intended center).
* :func:`check_seal_placement` — given a placed seal's box, decide pass/fail: the
  seal center within ``tol`` of the anchor, and no *unintended* occlusion of other
  text. The check **discriminates** (a centered seal passes, a mis-placed one
  fails) so an evaluator can run it — FR-003 / acceptance #3.

All coordinates are PDF points (the unit the wordbox oracle reports), origin
top-left (y grows downward).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from .wordbox import Rect, WordBox

# Default seal-center tolerance (pt). The seal center must land within this of the
# anchor glyph's center to count as "centered on the last glyph".
_SEAL_CENTER_TOL_PT = 6.0
# A glyph counts as occluded by the seal when this fraction of its area is covered.
_OCCLUSION_FRAC = 0.5
# Lines are grouped by y-center proximity within this fraction of glyph height.
_LINE_Y_FRAC = 0.6


def _norm(text: str) -> str:
    """Whitespace-insensitive form for matching a sender line."""

    return "".join(text.split())


def _center(box: WordBox | Rect) -> tuple[float, float]:
    return ((box.x0 + box.x1) / 2.0, (box.y0 + box.y1) / 2.0)


@dataclass(frozen=True, slots=True)
class SealAnchor:
    """Where the seal should be centered: the last glyph of the 발신명의 line."""

    glyph: WordBox
    line_text: str

    @property
    def center(self) -> tuple[float, float]:
        return _center(self.glyph)


def _group_lines(boxes: Sequence[WordBox]) -> list[list[WordBox]]:
    """Group glyph boxes into reading-order lines (same page, shared y-band)."""

    finite = [b for b in boxes if b.finite and b.height > 0]
    # Sort by (page, y-center, x0) so a simple sweep forms lines.
    ordered = sorted(finite, key=lambda b: (b.page, (b.y0 + b.y1) / 2.0, b.x0))
    lines: list[list[WordBox]] = []
    for box in ordered:
        cy = (box.y0 + box.y1) / 2.0
        placed = False
        for line in lines:
            ref = line[-1]
            if ref.page != box.page:
                continue
            ref_cy = (ref.y0 + ref.y1) / 2.0
            if abs(ref_cy - cy) <= _LINE_Y_FRAC * max(ref.height, box.height):
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])
    # Glyphs within a line in x order.
    for line in lines:
        line.sort(key=lambda b: b.x0)
    return lines


def find_seal_anchor(
    boxes: Sequence[WordBox], sender_text: str, *, page: int | None = None
) -> SealAnchor | None:
    """Find the last glyph of the line matching ``sender_text`` (the seal target).

    Lines are reconstructed from the glyph boxes; the line whose whitespace-stripped
    text **contains** the whitespace-stripped ``sender_text`` is the 발신명의 line. If
    several match, the **last** one in document order wins (the issuer line sits near
    the document foot). The returned anchor is that line's last non-space glyph —
    where the seal center belongs. Returns ``None`` when no line matches (so the
    caller reports ``anchor_found=False`` rather than mis-placing a seal).
    """

    needle = _norm(sender_text)
    if not needle:
        return None
    candidates = boxes if page is None else [b for b in boxes if b.page == page]
    match: SealAnchor | None = None
    for line in _group_lines(candidates):
        line_text = "".join(b.text for b in line)
        if needle in _norm(line_text):
            # last glyph that carries ink (skip trailing whitespace glyphs)
            inked = [b for b in line if b.text and not b.text.isspace()]
            if inked:
                match = SealAnchor(glyph=inked[-1], line_text=line_text)
    return match


@dataclass
class SealVerdict:
    """Pass/fail verdict for a placed 직인/관인 (FR-003)."""

    ok: bool
    anchor_found: bool
    centered: bool
    offset_pt: float | None = None
    occluded_glyphs: int = 0
    anchor_text: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "anchorFound": self.anchor_found,
            "centered": self.centered,
            "offsetPt": None if self.offset_pt is None else round(self.offset_pt, 2),
            "occludedGlyphs": self.occluded_glyphs,
            "anchorText": self.anchor_text,
            "note": self.note,
        }


def _occlusion_fraction(seal: Rect, glyph: WordBox) -> float:
    if glyph.page != seal.page:
        return 0.0
    dx = min(seal.x1, glyph.x1) - max(seal.x0, glyph.x0)
    dy = min(seal.y1, glyph.y1) - max(seal.y0, glyph.y0)
    if dx <= 0.0 or dy <= 0.0:
        return 0.0
    area = glyph.width * glyph.height
    if area <= 0.0:
        return 0.0
    return (dx * dy) / area


def check_seal_placement(
    boxes: Sequence[WordBox],
    seal: Rect,
    sender_text: str,
    *,
    tol_pt: float = _SEAL_CENTER_TOL_PT,
    max_occluded: int = 0,
    occlusion_frac: float = _OCCLUSION_FRAC,
) -> SealVerdict:
    """Decide whether a placed seal honors the 직인 rule (FR-003, discriminating).

    Pass requires: (a) the 발신명의 anchor is found; (b) the seal *center* lands within
    ``tol_pt`` of the anchor glyph's center; (c) the seal does not *unintentionally*
    occlude other text — glyphs **on the anchor's own line** are expected under the
    seal and are exempt, but covering ``> max_occluded`` glyphs elsewhere fails.
    """

    anchor = find_seal_anchor(boxes, sender_text, page=seal.page)
    if anchor is None:
        return SealVerdict(
            ok=False, anchor_found=False, centered=False, note="발신명의 anchor not found"
        )

    scx, scy = _center(seal)
    acx, acy = anchor.center
    offset = math.hypot(scx - acx, scy - acy)
    centered = offset <= tol_pt

    # Glyphs the seal sits on top of, excluding the anchor's own line (intended).
    anchor_line = set(_norm(anchor.line_text))  # cheap line-membership proxy by text
    anchor_cy = anchor.center[1]
    occluded = 0
    for g in boxes:
        if g is anchor.glyph:
            continue
        if _occlusion_fraction(seal, g) < occlusion_frac:
            continue
        # exempt glyphs on (approximately) the anchor's baseline — the seal legitimately
        # overlaps the 발신명의 line around the last glyph.
        if g.page == seal.page and abs((g.y0 + g.y1) / 2.0 - anchor_cy) <= _LINE_Y_FRAC * max(
            g.height, anchor.glyph.height
        ):
            continue
        occluded += 1

    occlusion_ok = occluded <= max_occluded
    ok = centered and occlusion_ok
    bits: list[str] = []
    if not centered:
        bits.append(f"seal center {offset:.1f}pt from 발신명의 last glyph (tol {tol_pt}pt)")
    if not occlusion_ok:
        bits.append(f"seal occludes {occluded} non-anchor glyph(s)")
    return SealVerdict(
        ok=ok,
        anchor_found=True,
        centered=centered,
        offset_pt=offset,
        occluded_glyphs=occluded,
        anchor_text=anchor.glyph.text,
        note="; ".join(bits),
    )


__all__ = [
    "SealAnchor",
    "SealVerdict",
    "find_seal_anchor",
    "check_seal_placement",
]
