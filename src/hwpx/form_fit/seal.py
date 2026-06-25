# SPDX-License-Identifier: Apache-2.0
"""직인/관인 placement compliance (M2 P3 / FR-003).

A Korean official document's seal (직인/관인) is placed *by rule*: its **center**
must sit on the **last glyph of the 발신명의** line (the issuer-name line, e.g.
``"행정안전부장관 홍길동"``). This module decides that rule **geometrically**
against the Hancom render boxes — reusing the word-box oracle
(:mod:`hwpx.form_fit.wordbox`) rather than guessing from the document model, since
the truth is where Hancom *drew* the glyph, not where the XML nominally puts it.

Pure-geometry decision entry points (slice 1), offline-testable:

* :func:`find_seal_anchor` — locate the last glyph of the 발신명의 line in a set of
  glyph boxes (the seal's intended center).
* :func:`check_seal_placement` — given a placed seal's box, decide pass/fail: the
  seal center within ``tol`` of the anchor, and no *unintended* occlusion of other
  text. The check **discriminates** (a centered seal passes, a mis-placed one
  fails) so an evaluator can run it — FR-003 / acceptance #3.

Placement entry points (slice 2) — turn the decision into an actual seal:

* :func:`seal_pos_offsets` — map an anchor center (PDF pt) to the PAPER-relative
  ``<hp:pos>`` offsets (HWPUNIT) that land a seal's *center* on it.
* :func:`place_seal` — embed a seal image and attach it as a **floating** picture
  to the source 발신명의 paragraph (``add_picture`` is inline-only), so it lands on
  that paragraph's page at the computed absolute position.

All render coordinates are PDF points (the unit the wordbox oracle reports), origin
top-left (y grows downward). HWPX positions are HWPUNIT (7200 per inch), so a PDF
point is exactly ``100`` HWPUNIT (``7200 / 72``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from .wordbox import Rect, WordBox

# 1 PDF point = 7200/72 = 100 HWPUNIT (HWPUNIT is 7200 per inch).
_PT_TO_HWPUNIT = 100.0
# 1 mm = 7200/25.4 HWPUNIT.
_MM_TO_HWPUNIT = 7200.0 / 25.4
# A typical 관인/직인 is ~2.5 cm square.
_DEFAULT_SEAL_MM = 25.0

# Default seal-center tolerance (pt). The seal center must land within this of the
# anchor glyph's center to count as "centered on the last glyph".
_SEAL_CENTER_TOL_PT = 6.0
# A glyph counts as occluded by the seal when this fraction of its area is covered.
_OCCLUSION_FRAC = 0.5
# Lines are grouped by y-center proximity within this fraction of glyph height.
_LINE_Y_FRAC = 0.6
# A 발신명의 that wraps in a narrow cell spans at most this many consecutive lines
# (the multi-line anchor fallback window).
_MAX_WRAP_LINES = 3


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
    lines = _group_lines(candidates)

    # Pass 1 — the issuer line on a single visual line (the common case).
    match: SealAnchor | None = None
    for line in lines:
        line_text = "".join(b.text for b in line)
        if needle in _norm(line_text):
            # last glyph that carries ink (skip trailing whitespace glyphs)
            inked = [b for b in line if b.text and not b.text.isspace()]
            if inked:
                match = SealAnchor(glyph=inked[-1], line_text=line_text)
    if match is not None:
        return match

    # Pass 2 (fallback) — a 발신명의 that *wrapped* across consecutive lines in a
    # narrow 발신·결재 cell. Grow a small same-page window; the anchor is the last
    # inked glyph of the line where the needle completes. Bounded window avoids
    # matching a stray first part against a coincidental later completion.
    for start in range(len(lines)):
        acc = ""
        for end in range(start, min(start + _MAX_WRAP_LINES, len(lines))):
            if lines[end][0].page != lines[start][0].page:
                break
            acc += _norm("".join(b.text for b in lines[end]))
            if end > start and needle in acc:
                inked = [b for b in lines[end] if b.text and not b.text.isspace()]
                if inked:
                    match = SealAnchor(glyph=inked[-1], line_text=acc)
                break  # smallest window for this start; later starts (doc order) win
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


# ------------------------------------------------------------------
# Placement (slice 2) — put the seal where slice 1 says it belongs.
# ------------------------------------------------------------------


def seal_pos_offsets(
    anchor_center_pt: tuple[float, float],
    seal_width_hu: int,
    seal_height_hu: int,
    *,
    pt_to_hwpunit: float = _PT_TO_HWPUNIT,
) -> tuple[int, int]:
    """Map a seal-center target (PDF pt) to PAPER ``<hp:pos>`` offsets (HWPUNIT).

    A floating ``<hp:pic>`` positioned ``horzRelTo="PAPER" vertRelTo="PAPER"`` with
    ``horzAlign="LEFT" vertAlign="TOP"`` places its **top-left** corner at
    ``(horzOffset, vertOffset)`` from the paper's top-left. To center a seal of
    ``seal_width_hu × seal_height_hu`` on ``anchor_center_pt`` the offset is the
    anchor (converted to HWPUNIT) minus half the seal. Offsets are clamped to ``≥ 0``
    because the schema types them ``xs:nonNegativeInteger`` (a seal hanging off the
    top/left edge would otherwise be rejected).
    """

    cx_pt, cy_pt = anchor_center_pt
    horz = round(cx_pt * pt_to_hwpunit - seal_width_hu / 2.0)
    vert = round(cy_pt * pt_to_hwpunit - seal_height_hu / 2.0)
    return max(0, horz), max(0, vert)


@dataclass
class SealPlacement:
    """Result of attaching a 직인 image to a document (FR-003, slice 2).

    ``page`` is the render page the caller said the anchor came from (or ``None``);
    a caller can cross-check it against the seal's page from ``extract_image_boxes``.
    ``clamped`` is ``True`` when the seal sat so close to the paper's top/left edge
    that the offset was clamped to 0 — the realized center then differs from the
    requested anchor (honest signal rather than a silent mis-stamp).
    """

    placed: bool
    paragraph_index: int = -1
    binary_item_id: str = ""
    horz_offset: int = 0
    vert_offset: int = 0
    seal_width_hu: int = 0
    seal_height_hu: int = 0
    page: int | None = None
    clamped: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "placed": self.placed,
            "paragraphIndex": self.paragraph_index,
            "binaryItemId": self.binary_item_id,
            "horzOffset": self.horz_offset,
            "vertOffset": self.vert_offset,
            "sealWidthHU": self.seal_width_hu,
            "sealHeightHU": self.seal_height_hu,
            "page": self.page,
            "clamped": self.clamped,
            "note": self.note,
        }


def _iter_all_paragraphs(document: Any) -> "list[Any]":
    """Body paragraphs **and** table-cell paragraphs (recursively), in order.

    ``document.paragraphs`` only surfaces a section's direct-child paragraphs, so a
    발신명의 inside a 발신·결재 table box would be invisible to :func:`place_seal`
    (and the seal silently un-placeable). This descends into ``paragraph.tables`` →
    ``table.cells`` → ``cell.paragraphs`` so the issuer line is found wherever Hancom
    actually renders it. Duck-typed and defensive: any model missing the table API
    simply yields its body paragraphs.
    """

    out: list[Any] = []

    def _walk(paragraph: Any) -> None:
        out.append(paragraph)
        for table in getattr(paragraph, "tables", None) or []:
            for row in getattr(table, "rows", None) or []:
                for cell in getattr(row, "cells", None) or []:
                    for cell_para in getattr(cell, "paragraphs", None) or []:
                        _walk(cell_para)

    for paragraph in document.paragraphs:
        _walk(paragraph)
    return out


def place_seal(
    document: Any,
    *,
    image_data: bytes,
    image_format: str,
    sender_text: str,
    anchor_center_pt: tuple[float, float],
    seal_width_mm: float = _DEFAULT_SEAL_MM,
    seal_height_mm: float | None = None,
    pt_to_hwpunit: float = _PT_TO_HWPUNIT,
    allow_overlap: bool = True,
    page: int | None = None,
) -> SealPlacement:
    """Embed *image_data* and place it as a floating 직인 on the 발신명의 page.

    The seal is attached to the **source paragraph** whose text contains
    ``sender_text`` (last occurrence wins — the issuer line sits near the document
    foot). The search descends into table cells (:func:`_iter_all_paragraphs`) so a
    발신명의 inside a 발신·결재 box is found. Anchoring the floating picture to that
    paragraph makes it land on that paragraph's page; ``anchor_center_pt`` (from the
    render oracle) is the **sole geometric authority** for the position, via
    :func:`seal_pos_offsets` — the paragraph match only selects the page.

    **Single-page / co-located-page assumption.** The PAPER offset is *page-relative*,
    so ``anchor_center_pt`` must come from the same render page the source paragraph
    lands on. For a single-page letter (the common 공문) this holds. For a multi-page
    document, pass ``page`` (the anchor's render page) — it is recorded on the result
    so the caller can cross-check against the seal's page from
    :func:`hwpx.form_fit.wordbox.extract_image_boxes`. ``place_seal`` does not itself
    re-render, so it cannot detect a page mismatch; the oracle verdict is the gate.

    ``add_picture`` is inline-only, so this uses its floating path
    (``treat_as_char=False`` + PAPER ``pos_overrides``). Returns a
    :class:`SealPlacement`; when no 발신명의 paragraph is found it fails **closed**
    (``placed=False``, nothing inserted) rather than guessing a position.
    """

    needle = _norm(sender_text)
    if not needle:
        return SealPlacement(placed=False, note="empty sender_text")

    paragraphs = _iter_all_paragraphs(document)
    target_index: int | None = None
    for index, paragraph in enumerate(paragraphs):
        if needle in _norm(paragraph.text):
            target_index = index  # last occurrence wins
    if target_index is None:
        return SealPlacement(placed=False, note="발신명의 paragraph not found")

    seal_w_hu = round(seal_width_mm * _MM_TO_HWPUNIT)
    height_mm = seal_width_mm if seal_height_mm is None else seal_height_mm
    seal_h_hu = round(height_mm * _MM_TO_HWPUNIT)
    horz, vert = seal_pos_offsets(
        anchor_center_pt, seal_w_hu, seal_h_hu, pt_to_hwpunit=pt_to_hwpunit
    )
    # honest signal: a near-edge anchor whose top-left would be negative is clamped to
    # 0, so the realized center no longer equals the requested anchor.
    raw_h = round(anchor_center_pt[0] * pt_to_hwpunit - seal_w_hu / 2.0)
    raw_v = round(anchor_center_pt[1] * pt_to_hwpunit - seal_h_hu / 2.0)
    clamped = raw_h < 0 or raw_v < 0

    binary_item_id = document.add_image(image_data, image_format)
    paragraphs[target_index].add_picture(
        binary_item_id,
        width=seal_w_hu,
        height=seal_h_hu,
        treat_as_char=False,
        # IN_FRONT_OF_TEXT: the seal is stamped *over* the 발신명의 line; without it
        # Hancom wraps the overlapped glyphs and shoves them aside (oracle-confirmed).
        text_wrap="IN_FRONT_OF_TEXT",
        pos_overrides={
            "horzRelTo": "PAPER",
            "vertRelTo": "PAPER",
            "horzAlign": "LEFT",
            "vertAlign": "TOP",
            "horzOffset": horz,
            "vertOffset": vert,
            "allowOverlap": "1" if allow_overlap else "0",
        },
    )
    return SealPlacement(
        placed=True,
        paragraph_index=target_index,
        binary_item_id=str(binary_item_id),
        horz_offset=horz,
        vert_offset=vert,
        seal_width_hu=seal_w_hu,
        seal_height_hu=seal_h_hu,
        page=page,
        clamped=clamped,
        note="seal clamped to paper edge" if clamped else "",
    )


__all__ = [
    "SealAnchor",
    "SealVerdict",
    "SealPlacement",
    "find_seal_anchor",
    "check_seal_placement",
    "seal_pos_offsets",
    "place_seal",
]
