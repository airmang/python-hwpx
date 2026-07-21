# SPDX-License-Identifier: Apache-2.0
"""Word/glyph-box geometry oracle for form-fill verification (M2 / rhwp ⑨).

The faithful renderer for HWPX is Hancom (Constitution IV); there is no free
headless one. Rather than drive the Hancom GUI on every check, this module makes
the cost amortizable:

1. Hancom renders a filled ``.hwpx`` to PDF **once** (the faithful capture).
2. PyMuPDF (``fitz``) extracts **per-glyph** boxes (``get_text("rawdict")``) for
   collision detection and **word** boxes for slot-overflow.
3. The boxes are **frozen** as a fixture (:class:`WordBoxFixture`) bound to a
   sha256 of the source document, so a stale or forged fixture **fails closed**.
4. Overlap (two glyph boxes colliding — 글자 겹침) and overflow (a box escaping
   its cell rectangle) are decided **by geometry**, offline, against the frozen
   boxes — corpus-scalable.

Why glyph granularity: a form value (이름/번호/날짜) is usually one whitespace-free
token, so ``get_text("words")`` returns a single box and an *intra-word* collision
(the dominant 글자 겹침 mode, e.g. the 방송신청서 case) would be geometrically
invisible. Collisions are therefore detected per glyph.

``fitz`` is an **oracle-only** dependency. When unavailable, extraction degrades
to an honest ``unverified`` verdict (Constitution V/IX) — it never crashes the
fill path and never asserts a silent pass.

All coordinates are PDF points (the unit ``fitz`` reports), origin top-left
(y grows downward).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Sequence

# A box smaller than this in either dimension is rendering noise, not a glyph.
_MIN_GLYPH_PT = 0.5
# Genuine collision = overlap on both axes whose *area* exceeds this. An area
# gate (not an AND-of-axes gate) dismisses the thin kerning seam between adjacent
# glyphs (one axis ~0 -> area ~0) while still catching a diagonal/partial stack.
_OVERLAP_AREA_EPS_PT2 = 0.20
# Default overflow tolerance (pt). Calibrated on real clean gov forms: glyphs
# owned by a table cell stay inside it with ~1pt slack, so 0 false positives at
# tol=0; 1pt absorbs find_tables border-rounding without masking a real escape.
_OVERFLOW_TOL_PT = 1.0
# A collision is an OVER-PRINT (a 글자 겹침 candidate, not normal flow) when the
# intersection covers at least this fraction of the SMALLER glyph's area. The gate
# is axis-agnostic: normal horizontal flow (a thin advance-axis sliver) AND normal
# vertical flow (edge-to-edge touch) both yield a small fraction and are excluded,
# while a real over-print — collapsed 자간, a punctuation/digit crammed onto a wide
# CJK glyph, a collapsed line — yields a large fraction. Calibrated on a real gov
# form (public_official_table, 2904 glyphs): frac>=0.30 collapses 1371 raw
# collisions to 13 stable over-prints (identical blank vs filled), the identity
# differential then cancels that baseline to 0 on a clean fill, while catching the
# period-in-CJK (frac 1.0) and collapsed-자간 (frac ~0.45) over-prints that a
# center-distance gate missed (adversarial review, 2026-06-25).
_OVERLAP_AREA_FRAC = 0.30
# Fixture schema version (load migrates / rejects unknown majors).
_FIXTURE_VERSION = 1
# Tool stamp recorded in fixture provenance.
_BACKEND_UNKNOWN = "unknown"


def _finite(*vals: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned cell rectangle in PDF points (origin top-left)."""

    x0: float
    y0: float
    x1: float
    y1: float
    label: str | None = None
    page: int = 0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains_center(self, box: "WordBox") -> bool:
        """True when ``box``'s center is inside this rect AND same page."""

        if box.page != self.page:
            return False
        cx = (box.x0 + box.x1) / 2.0
        cy = (box.y0 + box.y1) / 2.0
        return self.x0 <= cx <= self.x1 and self.y0 <= cy <= self.y1

    def overflow_of(self, box: "WordBox") -> float:
        """Max signed escape (pt) of ``box`` beyond any edge; <=0 means inside."""

        return max(
            self.x0 - box.x0,  # escapes left
            box.x1 - self.x1,  # escapes right
            self.y0 - box.y0,  # escapes top
            box.y1 - self.y1,  # escapes bottom
        )


@dataclass(frozen=True, slots=True)
class WordBox:
    """One text unit (glyph or word) with its bounding box (PDF points)."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    page: int = 0
    block: int = -1
    line: int = -1
    word_no: int = -1

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def finite(self) -> bool:
        return _finite(self.x0, self.y0, self.x1, self.y1)

    def overlap_area(self, other: "WordBox") -> float:
        """Intersection area (pt²) with ``other``; 0 when on different pages."""

        if self.page != other.page:
            return 0.0
        dx = min(self.x1, other.x1) - max(self.x0, other.x0)
        dy = min(self.y1, other.y1) - max(self.y0, other.y0)
        if dx <= 0.0 or dy <= 0.0:
            return 0.0
        return dx * dy

    def collides(self, other: "WordBox", *, area_eps: float = _OVERLAP_AREA_EPS_PT2) -> bool:
        """True when this box and ``other`` overlap (same page) beyond ``area_eps``.

        Area-gated so the kerning seam between adjacent glyphs (a sliver) does not
        count, but a genuine stack/collision (글자 겹침) does.
        """

        if not (self.finite and other.finite):
            return False
        return self.overlap_area(other) > area_eps

    def to_tuple(self) -> tuple[float, float, float, float, str, int, int, int, int]:
        return (
            self.x0, self.y0, self.x1, self.y1,
            self.text, self.page, self.block, self.line, self.word_no,
        )


class OracleUnavailable(RuntimeError):
    """Raised when the render/extraction backend is not reachable."""


def fitz_available() -> bool:
    """True when PyMuPDF (``fitz``) can be imported (the extraction backend)."""

    try:  # pragma: no cover - trivial import probe
        import fitz  # noqa: F401
    except Exception:
        return False
    return True


def _page_indices(doc: Any, page: int | None) -> list[int]:
    n = len(doc)
    if page is None:
        return list(range(n))
    if not (0 <= page < n):
        raise OracleUnavailable(f"page {page} out of range (0..{n - 1})")
    return [page]


def extract_word_boxes(pdf_path: str, *, page: int | None = None) -> list[WordBox]:
    """Extract whitespace-delimited **word** boxes (for slot-overflow checks)."""

    if not fitz_available():
        raise OracleUnavailable("PyMuPDF (fitz) is not installed")
    import fitz

    boxes: list[WordBox] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # truncated / non-PDF bytes -> degrade, never crash
        raise OracleUnavailable(f"unreadable PDF: {type(exc).__name__}") from exc
    with doc:
        for pno in _page_indices(doc, page):
            try:
                words = doc[pno].get_text("words")  # encrypted -> ValueError
            except Exception as exc:
                raise OracleUnavailable(f"unreadable PDF page: {type(exc).__name__}") from exc
            for w in words if isinstance(words, (list, tuple)) else []:
                if not isinstance(w, (list, tuple)) or len(w) < 8:
                    continue
                x0, y0, x1, y1, text, block, line, word_no = w[:8]
                if not _finite(x0, y0, x1, y1):
                    continue
                if (x1 - x0) < _MIN_GLYPH_PT or (y1 - y0) < _MIN_GLYPH_PT:
                    continue
                try:
                    box = WordBox(
                        x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                        text=str(text), page=int(pno),
                        block=int(block), line=int(line), word_no=int(word_no),
                    )
                except (TypeError, ValueError):
                    continue
                boxes.append(box)
    return boxes


def extract_glyph_boxes(pdf_path: str, *, page: int | None = None) -> list[WordBox]:
    """Extract **per-glyph** boxes via ``get_text("rawdict")`` (for collisions).

    Whitespace glyphs, non-finite coordinates and noise-sized boxes are dropped.
    This is the granularity at which intra-word 글자 겹침 becomes visible.
    """

    if not fitz_available():
        raise OracleUnavailable("PyMuPDF (fitz) is not installed")
    import fitz

    boxes: list[WordBox] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # truncated / non-PDF bytes -> degrade, never crash
        raise OracleUnavailable(f"unreadable PDF: {type(exc).__name__}") from exc
    with doc:
        for pno in _page_indices(doc, page):
            try:
                raw = doc[pno].get_text("rawdict")  # encrypted -> ValueError
            except Exception as exc:
                raise OracleUnavailable(f"unreadable PDF page: {type(exc).__name__}") from exc
            blocks = raw.get("blocks", []) if isinstance(raw, dict) else []
            for bi, block in enumerate(blocks if isinstance(blocks, list) else []):
                if not isinstance(block, dict):
                    continue
                for li, line in enumerate(block.get("lines", []) or []):  # image blocks have none
                    if not isinstance(line, dict):
                        continue
                    for span in line.get("spans", []) or []:
                        if not isinstance(span, dict):
                            continue
                        for ch in span.get("chars", []) or []:
                            if not isinstance(ch, dict):
                                continue
                            c = ch.get("c", "")
                            if not isinstance(c, str) or not c or c.isspace():
                                continue
                            bbox = ch.get("bbox")
                            if not bbox or len(bbox) < 4:
                                continue
                            x0, y0, x1, y1 = bbox[:4]
                            if not _finite(x0, y0, x1, y1):
                                continue
                            if (x1 - x0) < _MIN_GLYPH_PT or (y1 - y0) < _MIN_GLYPH_PT:
                                continue
                            boxes.append(
                                WordBox(
                                    x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                                    text=str(c), page=int(pno), block=int(bi), line=int(li),
                                )
                            )
    return boxes


def detect_overlaps(
    boxes: Sequence[WordBox], *, area_eps: float = _OVERLAP_AREA_EPS_PT2
) -> list[tuple[WordBox, WordBox]]:
    """Pairwise glyph collisions (글자 겹침) among ``boxes`` (same page only)."""

    hits: list[tuple[WordBox, WordBox]] = []
    n = len(boxes)
    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            if a.collides(boxes[j], area_eps=area_eps):
                hits.append((a, boxes[j]))
    return hits


def _overprint_fraction(a: WordBox, b: WordBox) -> float:
    """Intersection area as a fraction of the smaller glyph's area (0..1).

    Axis-agnostic measure of *how much* two glyphs over-print. Normal flow
    (horizontal sliver or vertical edge-touch) is a small fraction; a stack/cram is
    a large one. This succeeds where a center-distance gate fails: it does not
    assume the advance axis (so collapsed 자간, vertical text and collapsed lines
    are all covered) and it is symmetric to glyph size (a tiny glyph fully inside a
    wide CJK glyph scores 1.0, the canonical 글자 겹침 a ``min(width)`` gate missed).
    """

    overlap = a.overlap_area(b)
    if overlap <= 0.0:
        return 0.0
    smaller = min(a.width * a.height, b.width * b.height)
    if smaller <= 0.0:
        return 1.0  # degenerate glyph fully covered: treat as an over-print
    return overlap / smaller


def _overprint_collisions(
    boxes: Sequence[WordBox], *, area_eps: float, area_frac: float
) -> list[tuple[WordBox, WordBox]]:
    return [
        (a, b)
        for a, b in detect_overlaps(boxes, area_eps=area_eps)
        if _overprint_fraction(a, b) >= area_frac
    ]


def _overlap_identity(a: WordBox, b: WordBox) -> tuple:
    """Position-invariant identity of a collision: page + canonical glyph-text pair.

    Keying on glyph identity (not absolute position) makes the differential robust
    to benign intra-page reflow — a baseline over-print that merely translates keeps
    its identity and cancels — while a genuinely new over-print carries a new pair,
    or a higher *count* of an existing pair on the page.
    """

    return (a.page,) + tuple(sorted((a.text, b.text)))


def diff_overlaps(
    blank_boxes: Sequence[WordBox],
    filled_boxes: Sequence[WordBox],
    *,
    area_eps: float = _OVERLAP_AREA_EPS_PT2,
    area_frac: float = _OVERLAP_AREA_FRAC,
) -> list[tuple[WordBox, WordBox]]:
    """Glyph over-prints the *fill* introduces (filled render minus blank baseline).

    Absolute glyph-overlap is unusable on real forms — a clean gov form already
    carries ~1371 benign collisions, almost all normal adjacent CJK flow. Two gates
    isolate the new 글자 겹침 a fill causes:

    1. **over-print gate** (:func:`_overprint_fraction`) — keep only collisions whose
       intersection covers a real fraction (``area_frac``) of the smaller glyph,
       dropping normal horizontal *and* vertical flow. This collapses the ~1371 raw
       collisions to ~13 stable over-prints (identical count blank vs filled).
    2. **identity differential** — cancel each surviving filled over-print against a
       blank one of the *same identity* (page + glyph-text pair), count-aware. A
       filled over-print is new only when its identity is absent from the blank
       baseline or appears more times than in it.

    Identity (not position) keying is deliberate: an earlier position-keyed version
    both masked a real cram landing near a benign seam and flooded false positives
    whenever a benign stack merely translated >tol under an in-page reflow that
    :func:`diff_layout` cannot see (adversarial review, 2026-06-25). On a clean fill
    the result is 0; what remains is the new over-print the fill introduced.
    """

    from collections import Counter

    blank_hits = _overprint_collisions(blank_boxes, area_eps=area_eps, area_frac=area_frac)
    filled_hits = _overprint_collisions(filled_boxes, area_eps=area_eps, area_frac=area_frac)
    baseline = Counter(_overlap_identity(a, b) for a, b in blank_hits)
    seen: "Counter[tuple]" = Counter()
    new: list[tuple[WordBox, WordBox]] = []
    for a, b in filled_hits:
        key = _overlap_identity(a, b)
        seen[key] += 1
        if seen[key] > baseline.get(key, 0):
            new.append((a, b))
    return new


def _owning_clip(box: WordBox, clips: Sequence[Rect]) -> Rect | None:
    """Tightest-area clip on the same page whose interior holds ``box``'s center."""

    best: Rect | None = None
    for clip in clips:
        if not isinstance(clip, Rect):  # tolerate caller type-misuse, never crash
            continue
        if clip.contains_center(box) and (best is None or clip.area < best.area):
            best = clip
    return best


def detect_overflow(
    boxes: Sequence[WordBox], clips: Sequence[Rect], *, tol: float = 0.0
) -> list[tuple[WordBox, Rect]]:
    """Boxes that escape the (same-page) cell they belong to.

    A box outside every clip is page chrome, not a slot fill, and is ignored.
    """

    out: list[tuple[WordBox, Rect]] = []
    for box in boxes:
        if not box.finite:
            continue
        clip = _owning_clip(box, clips)
        if clip is None:
            continue
        if clip.overflow_of(box) > tol:
            out.append((box, clip))
    return out


def diff_overflow(
    blank_boxes: Sequence[WordBox],
    blank_clips: Sequence[Rect],
    filled_boxes: Sequence[WordBox],
    filled_clips: Sequence[Rect],
    *,
    tol: float = _OVERFLOW_TOL_PT,
) -> list[tuple[WordBox, Rect]]:
    """Cell-escapes the *fill* introduces (filled render minus blank baseline).

    Absolute cell-clip overflow is baseline-prone on dense real forms: ``find_
    tables`` reconstructs cell borders with ~1pt imprecision, so a clean form flags
    a steady population of marginal escapes that exist *identically* in the blank
    render (measured: 171 on a clean ``form_002``, all < 4pt, median 1.25pt). Like
    :func:`diff_overlaps`, this subtracts that baseline by glyph identity (page +
    text), count-aware: a filled escape counts only when its identity is absent from
    the blank baseline or appears more times than in it. On a clean fill the result
    is 0; what remains is the new escape the fill actually caused.
    """

    from collections import Counter

    blank_esc = detect_overflow(blank_boxes, blank_clips, tol=tol)
    filled_esc = detect_overflow(filled_boxes, filled_clips, tol=tol)
    baseline = Counter((b.page, b.text) for b, _r in blank_esc)
    seen: "Counter[tuple]" = Counter()
    new: list[tuple[WordBox, Rect]] = []
    for box, clip in filled_esc:
        key = (box.page, box.text)
        seen[key] += 1
        if seen[key] > baseline.get(key, 0):
            new.append((box, clip))
    return new


# --- frozen fixture (provenance-bound, fail-closed) -------------------------

def sha256_file(path: str) -> str:
    """sha256 hex of a file's bytes (the fixture<->source binding)."""

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class WordBoxFixture:
    """Frozen Hancom-render glyph boxes for offline regression.

    Faithfulness is *not* a bare boolean: ``checked`` is True only for a real
    faithful capture, ``source_sha256``/``backend`` record provenance, and a
    consumer rebinds the fixture to its source by hash. A fixture missing
    ``checked`` or provenance loads **fail-closed** (``checked=False``), so a
    forged or schema-drifted file cannot masquerade as a faithful render.
    """

    boxes: list[WordBox]
    page_sizes: list[tuple[float, float]] = field(default_factory=list)
    source: str = ""
    checked: bool = False
    source_sha256: str | None = None
    backend: str = _BACKEND_UNKNOWN

    def freeze(self, path: str) -> None:
        payload = {
            "version": _FIXTURE_VERSION,
            "source": self.source,
            "checked": self.checked,
            "sourceSha256": self.source_sha256,
            "backend": self.backend,
            "pageSizes": [list(p) for p in self.page_sizes],
            "boxes": [b.to_tuple() for b in self.boxes],
        }
        # Atomic write: a crash mid-serialization must not leave a torn fixture.
        directory = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: str) -> "WordBoxFixture":
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        version = payload.get("version", 0)
        if version > _FIXTURE_VERSION:
            raise ValueError(f"fixture version {version} is newer than supported {_FIXTURE_VERSION}")
        boxes = [
            WordBox(t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8])
            for t in payload.get("boxes", [])
            if isinstance(t, (list, tuple)) and len(t) >= 9
        ]
        sizes = [tuple(p) for p in payload.get("pageSizes", [])]
        # Strict: only a real JSON bool true means faithful. A non-bool (e.g. the
        # STRING "false", which is truthy) or a missing key fails closed.
        raw_checked = payload.get("checked", False)
        checked = raw_checked if isinstance(raw_checked, bool) else False
        raw_sha = payload.get("sourceSha256")
        source_sha = raw_sha if isinstance(raw_sha, str) and raw_sha else None
        return cls(
            boxes=boxes,
            page_sizes=sizes,
            source=payload.get("source", ""),
            checked=checked,
            source_sha256=source_sha,
            backend=payload.get("backend", _BACKEND_UNKNOWN),
        )


# --- verdict ---------------------------------------------------------------

@dataclass
class FormFillVerdict:
    """Geometry verdict for a filled form (rides onto ``FitResult``/``FormReport``).

    ``render_checked`` is the Constitution V contract: True only when backed by a
    real render (or a faithful, source-bound frozen fixture). ``overflow_checked``
    distinguishes "no overflow" from "overflow not evaluated" (no clips). A verdict
    that is not ``render_checked`` is ``unverified`` — never a silent pass.
    """

    render_checked: bool
    overflow_detected: bool
    overlap_detected: bool
    overflow_checked: bool = False
    layout_stable: bool | None = None
    overflow: list[dict[str, Any]] = field(default_factory=list)
    overlap: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        """A pass requires a faithful check AND no overflow/overlap detected."""

        return (
            self.render_checked
            and not self.overflow_detected
            and not self.overlap_detected
            and self.layout_stable is not False
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderChecked": self.render_checked,
            "ok": self.ok,
            "overflowDetected": self.overflow_detected,
            "overflowChecked": self.overflow_checked,
            "overlapDetected": self.overlap_detected,
            "layoutStable": self.layout_stable,
            "overflow": self.overflow,
            "overlap": self.overlap,
            "note": self.note,
        }


def _box_brief(box: WordBox) -> dict[str, Any]:
    return {
        "text": box.text,
        "page": box.page,
        "bbox": [round(box.x0, 2), round(box.y0, 2), round(box.x1, 2), round(box.y1, 2)],
    }


def verdict_from_boxes(
    boxes: Sequence[WordBox],
    clips: Sequence[Rect] | None = None,
    *,
    render_checked: bool = False,
    layout_stable: bool | None = None,
    area_eps: float = _OVERLAP_AREA_EPS_PT2,
    tol: float = 0.0,
) -> FormFillVerdict:
    """Build a :class:`FormFillVerdict` from glyph boxes (+ optional clips).

    ``render_checked`` defaults **False** (fail-closed): the caller must assert a
    faithful capture explicitly.
    """

    overlaps = detect_overlaps(boxes, area_eps=area_eps)
    overflow = detect_overflow(boxes, clips or [], tol=tol)
    return FormFillVerdict(
        render_checked=render_checked,
        overflow_detected=bool(overflow),
        overflow_checked=bool(clips),
        overlap_detected=bool(overlaps),
        layout_stable=layout_stable,
        overflow=[
            {"box": _box_brief(b), "clip": r.label, "escapePt": round(r.overflow_of(b), 2)}
            for b, r in overflow
        ],
        overlap=[{"a": _box_brief(a), "b": _box_brief(b)} for a, b in overlaps],
        note="" if render_checked else "unverified",
    )


def unverified_verdict(reason: str) -> FormFillVerdict:
    """The honest degrade: no faithful capture was reachable (Constitution V/IX)."""

    return FormFillVerdict(
        render_checked=False,
        overflow_detected=False,
        overlap_detected=False,
        overflow_checked=False,
        layout_stable=None,
        note=f"unverified: {reason}",
    )


# --- end-to-end capture (the one place Hancom is touched) -------------------

def render_glyph_boxes(
    hwpx_path: str,
    *,
    oracle: Any = None,
    page: int | None = None,
    out_pdf: str | None = None,
) -> tuple[list[WordBox], list[tuple[float, float]], str]:
    """Render *hwpx_path* via the Hancom oracle and extract per-glyph boxes.

    Returns ``(glyph_boxes, page_sizes, backend_name)``. Raises
    :class:`OracleUnavailable` for ANY backend/parse failure — resolution,
    ``available()``/``render_pdf()`` raising (the real ``MacHancomOracle`` does
    ``shutil.copyfile`` which throws on a directory/unreadable path), an empty or
    unparseable PDF — so the caller degrades honestly instead of crashing the fill
    path (Constitution V/VI/IX: the fill path must never crash).
    """

    try:
        if oracle is None:
            from hwpx.visual.oracle import resolve_oracle

            oracle = resolve_oracle()
        if not oracle.available():
            raise OracleUnavailable("no reachable Hancom render backend")
        pdf = oracle.render_pdf(hwpx_path, out_pdf)
        if not pdf or not os.path.exists(pdf) or os.path.getsize(pdf) == 0:
            raise OracleUnavailable("Hancom render produced no PDF")
        boxes = extract_glyph_boxes(pdf, page=page)
        import fitz

        with fitz.open(pdf) as doc:
            if len(doc) == 0:  # a 0-page render is a failed render, not a clean pass
                raise OracleUnavailable("Hancom render produced an empty (0-page) PDF")
            sizes = [(float(p.rect.width), float(p.rect.height)) for p in doc]
        return boxes, sizes, type(oracle).__name__
    except OracleUnavailable:
        raise
    except Exception as exc:  # backend/copyfile/subprocess/parse -> degrade, never crash
        raise OracleUnavailable(f"render backend failed: {type(exc).__name__}") from exc


def extract_cell_clips(pdf_path: str, *, page: int | None = None) -> list[Rect]:
    """Extract table cell rectangles (PDF points) via ``fitz.find_tables()``.

    These are the overflow clips — same coordinate space as the glyph boxes — so
    no HWPX→PDF transform is needed. ``find_tables`` can raise on odd pages; such
    a page contributes no clips rather than crashing.

    Borders-only (``strategy="lines_strict"``): a cell rectangle is defined by its
    *drawn borders*, not by the text inside it. The ``find_tables`` default snaps
    edges to glyph positions, so a filled value can appear to *escape* a clip that
    was mis-sized around the very text it holds — a false overflow. S-094 P3
    measured this: the only 3 corpus pairs that flagged ``newOverflow`` (the nts
    forms) all had the fill value escaping a text-snapped clip under the default,
    and 0 escapes under ``lines_strict``; there were no real escapes to mask.
    """

    if not fitz_available():
        raise OracleUnavailable("PyMuPDF (fitz) is not installed")
    import fitz

    clips: list[Rect] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise OracleUnavailable(f"unreadable PDF: {type(exc).__name__}") from exc
    with doc:
        for pno in _page_indices(doc, page):
            try:
                tables = doc[pno].find_tables(strategy="lines_strict").tables
            except Exception:
                continue  # layout analysis failed on this page -> no clips, no crash
            for ti, table in enumerate(tables):
                for ci, cell in enumerate(getattr(table, "cells", []) or []):
                    if not cell or len(cell) < 4 or not _finite(*cell[:4]):
                        continue
                    clips.append(
                        Rect(
                            float(cell[0]), float(cell[1]), float(cell[2]), float(cell[3]),
                            label=f"p{pno}t{ti}c{ci}", page=int(pno),
                        )
                    )
    return clips


def extract_image_boxes(pdf_path: str, *, page: int | None = None) -> list[Rect]:
    """Extract embedded-image rectangles (PDF points) from a render.

    A placed 직인/관인 is a *picture*, so it never appears in the ``get_text`` glyph
    boxes; ``page.get_image_info()`` reports each image's ``bbox`` in the same
    top-left PDF-point space as the glyph boxes, so the seal rect feeds straight into
    :func:`hwpx.form_fit.seal.check_seal_placement` with no transform. A page whose
    image analysis raises contributes no boxes rather than crashing the check.
    """

    if not fitz_available():
        raise OracleUnavailable("PyMuPDF (fitz) is not installed")
    import fitz

    boxes: list[Rect] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise OracleUnavailable(f"unreadable PDF: {type(exc).__name__}") from exc
    with doc:
        for pno in _page_indices(doc, page):
            try:
                infos = doc[pno].get_image_info()
            except Exception:
                continue  # image analysis failed on this page -> no boxes, no crash
            for ii, info in enumerate(infos):
                bbox = info.get("bbox") if isinstance(info, dict) else None
                if not bbox or len(bbox) < 4 or not _finite(*bbox[:4]):
                    continue
                boxes.append(
                    Rect(
                        float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]),
                        label=f"p{pno}i{ii}", page=int(pno),
                    )
                )
    return boxes


def render_form_geometry(
    hwpx_path: str, *, oracle: Any = None, page: int | None = None
) -> tuple[list[WordBox], list[Rect], list[tuple[float, float]], str]:
    """Render once via Hancom and return ``(glyph_boxes, cell_clips, sizes, backend)``.

    The whole leg is wrapped: any backend/parse/IO failure degrades to
    :class:`OracleUnavailable` (the fill path never crashes).
    """

    try:
        if oracle is None:
            from hwpx.visual.oracle import resolve_oracle

            oracle = resolve_oracle()
        if not oracle.available():
            raise OracleUnavailable("no reachable Hancom render backend")
        fd, pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            rendered = oracle.render_pdf(hwpx_path, pdf)
            if not rendered or not os.path.exists(rendered) or os.path.getsize(rendered) == 0:
                raise OracleUnavailable("Hancom render produced no PDF")
            glyphs = extract_glyph_boxes(rendered, page=page)
            clips = extract_cell_clips(rendered, page=page)
            import fitz

            with fitz.open(rendered) as doc:
                if len(doc) == 0:
                    raise OracleUnavailable("Hancom render produced an empty (0-page) PDF")
                sizes = [(float(p.rect.width), float(p.rect.height)) for p in doc]
            return glyphs, clips, sizes, type(oracle).__name__
        finally:
            try:
                os.remove(pdf)
            except OSError:
                pass
    except OracleUnavailable:
        raise
    except Exception as exc:
        raise OracleUnavailable(f"render backend failed: {type(exc).__name__}") from exc


def verify_form_overflow(
    hwpx_path: str,
    *,
    oracle: Any = None,
    tol: float = _OVERFLOW_TOL_PT,
    layout_stable: bool | None = None,
) -> FormFillVerdict:
    """Live overflow verdict for a filled form (P2 primary signal).

    Renders once, auto-extracts table cell clips, and flags any glyph escaping
    its owning cell. Absolute glyph-*overlap* is intentionally NOT gated here — it
    is unreliable on real forms (punctuation-after-CJK, Hancom PUA symbols); the
    overlap signal is computed *differentially* (blank vs filled) elsewhere. With
    no detectable table cells, overflow is reported as not-evaluated (honest),
    not a silent clean pass.
    """

    try:
        glyphs, clips, _sizes, _backend = render_form_geometry(hwpx_path, oracle=oracle)
    except OracleUnavailable as exc:
        return unverified_verdict(str(exc))
    overflow = detect_overflow(glyphs, clips, tol=tol)
    return FormFillVerdict(
        render_checked=True,
        overflow_detected=bool(overflow),
        overflow_checked=bool(clips),
        overlap_detected=False,
        layout_stable=layout_stable,
        overflow=[
            {"box": _box_brief(b), "clip": r.label, "escapePt": round(r.overflow_of(b), 2)}
            for b, r in overflow
        ],
        note="" if clips else "no table cells detected (overflow not evaluated)",
    )


# --- layout stability (differential: blank render vs filled render) ---------

@dataclass(frozen=True, slots=True)
class LayoutSignature:
    """Structural fingerprint of a rendered form: page count + per-table shape.

    The layout-stability signal is **differential** — a fill must not change the
    document's structure, so we compare the blank render's signature against the
    filled render's and never assert an absolute (Constitution V; mirrors the P1
    lesson that absolute glyph-overlap is unusable on real forms). Page count is
    the dominant, high-confidence signal — a fill that spills onto a new page is
    the canonical layout collapse. Per-table ``(rows, cols)`` is the finer
    row/column signal, extracted from *drawn table borders only*
    (``find_tables(strategy="lines_strict")``): a structural fingerprint must be
    text-independent, so it is judged as a multiset *delta* (blank vs filled),
    not an absolute count.

    Why ``lines_strict`` and not the ``find_tables`` default (``"lines"``): the
    default snaps table edges to *text* positions, so injecting a value into a
    previously-empty cell makes it hallucinate a phantom ``(2,2)``/``(1,2)`` table
    or wobble a real one by ±1 row/col even when the drawn grid and page count are
    unchanged. S-094 P3 measured this on the frozen corpus (all 6 "table-shape"
    differential failures were page-stable phantoms; under ``lines_strict`` blank
    and filled agree, 0 regressions across 31 pairs; ``sen-24`` has byte-identical
    drawn rectangles yet the default strategy still invented a ``(1,2)`` table from
    the 3 added glyphs). Borders-only detection measures the grid the fill did not
    touch.
    """

    page_count: int
    table_shapes: tuple[tuple[int, int], ...] = ()
    page_sizes: tuple[tuple[float, float], ...] = ()

    @property
    def table_shape_multiset(self) -> tuple[tuple[int, int], ...]:
        """Order-independent ``(rows, cols)`` multiset — table *order* is not structure."""

        return tuple(sorted(self.table_shapes))

    @property
    def row_total(self) -> int:
        return sum(rows for rows, _cols in self.table_shapes)


def extract_layout_signature(pdf_path: str) -> LayoutSignature:
    """Extract the structural signature (page count + per-table shape) of a PDF.

    Per-page ``find_tables`` failures contribute no tables rather than crashing
    (same tolerance as :func:`extract_cell_clips`).
    """

    if not fitz_available():
        raise OracleUnavailable("PyMuPDF (fitz) is not installed")
    import fitz

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # truncated / non-PDF bytes -> degrade, never crash
        raise OracleUnavailable(f"unreadable PDF: {type(exc).__name__}") from exc
    shapes: list[tuple[int, int]] = []
    sizes: list[tuple[float, float]] = []
    with doc:
        for page in doc:
            sizes.append((float(page.rect.width), float(page.rect.height)))
            try:
                # Borders-only ("lines_strict"): a *structural* fingerprint must
                # not react to cell text. The default strategy snaps to glyph
                # positions and invents phantom tables from a fill's added text
                # (S-094 P3). Bordered form grids are detected identically either
                # way; the text-sensitivity is the only difference we drop.
                tables = page.find_tables(strategy="lines_strict").tables
            except Exception:
                continue  # layout analysis failed on this page -> no tables, no crash
            for table in tables:
                rows = getattr(table, "row_count", None)
                cols = getattr(table, "col_count", None)
                if isinstance(rows, int) and isinstance(cols, int) and rows >= 0 and cols >= 0:
                    shapes.append((rows, cols))
        page_count = len(doc)
    return LayoutSignature(
        page_count=page_count, table_shapes=tuple(shapes), page_sizes=tuple(sizes)
    )


@dataclass(frozen=True, slots=True)
class LayoutDiff:
    """Differential layout-stability verdict (blank render vs filled render)."""

    stable: bool
    page_count_stable: bool
    table_shapes_stable: bool
    blank: LayoutSignature
    filled: LayoutSignature
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable": self.stable,
            "pageCountStable": self.page_count_stable,
            "tableShapesStable": self.table_shapes_stable,
            "blankPages": self.blank.page_count,
            "filledPages": self.filled.page_count,
            "reasons": list(self.reasons),
        }


def diff_layout(
    blank: LayoutSignature,
    filled: LayoutSignature,
    *,
    require_table_shapes: bool = True,
) -> LayoutDiff:
    """Compare a blank render's signature to the filled render's.

    ``page_count`` must match (the hard signal). ``table_shapes`` must match as a
    multiset when ``require_table_shapes`` (default): a fill that grows or splits a
    row changes a table's ``(rows, cols)``. A corpus where ``find_tables`` proves
    too content-sensitive to bind can pass ``require_table_shapes=False`` to keep
    table shapes *advisory* (still reported in ``reasons``, but not gating
    ``stable``) — the calibration knob, decided by measurement, not assumption.
    """

    page_count_stable = blank.page_count == filled.page_count
    table_shapes_stable = blank.table_shape_multiset == filled.table_shape_multiset
    reasons: list[str] = []
    if not page_count_stable:
        reasons.append(f"page count {blank.page_count}->{filled.page_count}")
    if not table_shapes_stable:
        reasons.append(
            f"table shapes {list(blank.table_shape_multiset)}"
            f"->{list(filled.table_shape_multiset)}"
        )
    stable = page_count_stable and (table_shapes_stable or not require_table_shapes)
    return LayoutDiff(
        stable=stable,
        page_count_stable=page_count_stable,
        table_shapes_stable=table_shapes_stable,
        blank=blank,
        filled=filled,
        reasons=tuple(reasons),
    )


def render_form_layout(
    hwpx_path: str, *, oracle: Any = None, page: int | None = None
) -> tuple[list[WordBox], list[Rect], LayoutSignature, str]:
    """Render once via Hancom and return ``(glyphs, clips, signature, backend)``.

    One render feeds all three offline checks (overflow, overlap, layout). Any
    backend/parse/IO failure degrades to :class:`OracleUnavailable` (the fill path
    never crashes), exactly like :func:`render_form_geometry`.
    """

    try:
        if oracle is None:
            from hwpx.visual.oracle import resolve_oracle

            oracle = resolve_oracle()
        if not oracle.available():
            raise OracleUnavailable("no reachable Hancom render backend")
        fd, pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            rendered = oracle.render_pdf(hwpx_path, pdf)
            if not rendered or not os.path.exists(rendered) or os.path.getsize(rendered) == 0:
                raise OracleUnavailable("Hancom render produced no PDF")
            glyphs = extract_glyph_boxes(rendered, page=page)
            clips = extract_cell_clips(rendered, page=page)
            signature = extract_layout_signature(rendered)
            if signature.page_count == 0:  # a 0-page render is a failed render
                raise OracleUnavailable("Hancom render produced an empty (0-page) PDF")
            return glyphs, clips, signature, type(oracle).__name__
        finally:
            try:
                os.remove(pdf)
            except OSError:
                pass
    except OracleUnavailable:
        raise
    except Exception as exc:  # backend/copyfile/subprocess/parse -> degrade, never crash
        raise OracleUnavailable(f"render backend failed: {type(exc).__name__}") from exc


def verify_form_layout_stability(
    filled_hwpx: str,
    *,
    blank_hwpx: str | None = None,
    blank_signature: LayoutSignature | None = None,
    oracle: Any = None,
    tol: float = _OVERFLOW_TOL_PT,
    require_table_shapes: bool = True,
) -> FormFillVerdict:
    """Differential overflow + layout-stability verdict for a filled form (P2).

    The blank baseline is ``blank_signature`` when given (template-once / frozen,
    so a corpus pays the blank render only once), else a one-time render of
    ``blank_hwpx``. The filled form is rendered once for overflow + its own
    signature, and ``layout_stable`` becomes the REAL :func:`diff_layout` verdict
    (no longer a passthrough). Honest-degrades to ``unverified`` when no baseline is
    available or any render fails (Constitution V/IX) — never a silent pass.
    """

    if blank_signature is None:
        if not blank_hwpx:
            return unverified_verdict(
                "no blank baseline (need blank_hwpx or blank_signature)"
            )
        try:
            _bg, _bc, blank_signature, _bb = render_form_layout(blank_hwpx, oracle=oracle)
        except OracleUnavailable as exc:
            return unverified_verdict(f"blank baseline render failed: {exc}")
    try:
        glyphs, clips, filled_sig, _backend = render_form_layout(filled_hwpx, oracle=oracle)
    except OracleUnavailable as exc:
        return unverified_verdict(f"filled render failed: {exc}")
    diff = diff_layout(blank_signature, filled_sig, require_table_shapes=require_table_shapes)
    overflow = detect_overflow(glyphs, clips, tol=tol)
    note_bits: list[str] = []
    if not clips:
        note_bits.append("no table cells detected (overflow not evaluated)")
    if not diff.stable:
        note_bits.append("layout unstable: " + "; ".join(diff.reasons))
    return FormFillVerdict(
        render_checked=True,
        overflow_detected=bool(overflow),
        overflow_checked=bool(clips),
        overlap_detected=False,  # differential overlap is the next P2 slice
        layout_stable=diff.stable,
        overflow=[
            {"box": _box_brief(b), "clip": r.label, "escapePt": round(r.overflow_of(b), 2)}
            for b, r in overflow
        ],
        note="; ".join(note_bits),
    )


def verify_form_fill_differential(
    blank_hwpx: str,
    filled_hwpx: str,
    *,
    oracle: Any = None,
    tol: float = _OVERFLOW_TOL_PT,
    require_table_shapes: bool = True,
    area_eps: float = _OVERLAP_AREA_EPS_PT2,
    area_frac: float = _OVERLAP_AREA_FRAC,
) -> FormFillVerdict:
    """Full P2 verdict for a filled form: overflow + layout-stability + overlap.

    Renders blank and filled once each, then decides all three offline against the
    same captures:

    * **overflow** — NEW cell-escapes the fill introduced (:func:`diff_overflow`
      subtracts the blank baseline; absolute overflow is baseline-prone — a dense
      clean form carries ~171 find_tables border-noise escapes identical in both
      renders);
    * **layout_stable** — the blank→filled structural diff (page count + table
      shapes), the signal that catches a reflow overflow alone misses;
    * **overlap_detected** — the NEW glyph collisions the fill introduced
      (:func:`diff_overlaps` subtracts the blank baseline), the reliable 글자 겹침
      signal — absolute overlap is not used (P2 calibration: a clean form has
      ~1371 benign collisions).

    Honest-degrades to ``unverified`` if either render fails (Constitution V/IX) —
    never a silent pass.
    """

    try:
        blank_glyphs, blank_clips, blank_sig, _bb = render_form_layout(
            blank_hwpx, oracle=oracle
        )
    except OracleUnavailable as exc:
        return unverified_verdict(f"blank render failed: {exc}")
    try:
        filled_glyphs, clips, filled_sig, _fb = render_form_layout(
            filled_hwpx, oracle=oracle
        )
    except OracleUnavailable as exc:
        return unverified_verdict(f"filled render failed: {exc}")

    diff = diff_layout(blank_sig, filled_sig, require_table_shapes=require_table_shapes)
    # overflow is DIFFERENTIAL (blank baseline subtracted): dense real forms carry a
    # steady find_tables border-noise population of marginal escapes identical in both
    # renders (171 on a clean form_002) — absolute overflow would false-fail them.
    overflow = diff_overflow(blank_glyphs, blank_clips, filled_glyphs, clips, tol=tol)
    new_overlaps = diff_overlaps(
        blank_glyphs, filled_glyphs, area_eps=area_eps, area_frac=area_frac
    )
    note_bits: list[str] = []
    if not clips:
        note_bits.append("no table cells detected (overflow not evaluated)")
    if not diff.stable:
        note_bits.append("layout unstable: " + "; ".join(diff.reasons))
    if new_overlaps:
        note_bits.append(f"{len(new_overlaps)} new glyph overlap(s) introduced by fill")
    return FormFillVerdict(
        render_checked=True,
        overflow_detected=bool(overflow),
        overflow_checked=bool(clips),
        overlap_detected=bool(new_overlaps),
        layout_stable=diff.stable,
        overflow=[
            {"box": _box_brief(b), "clip": r.label, "escapePt": round(r.overflow_of(b), 2)}
            for b, r in overflow
        ],
        overlap=[{"a": _box_brief(a), "b": _box_brief(b)} for a, b in new_overlaps],
        note="; ".join(note_bits),
    )


def verify_form_fill(
    hwpx_path: str,
    *,
    clips: Sequence[Rect] | None = None,
    oracle: Any = None,
    frozen_path: str | None = None,
    freeze_to: str | None = None,
    layout_stable: bool | None = None,
) -> FormFillVerdict:
    """End-to-end glyph-box verdict for a filled form (the P1 oracle path).

    Resolution order (Constitution IV/V/VI — fail closed):

    1. ``frozen_path`` exists → load the frozen capture. The fixture is **rebound
       to ``hwpx_path`` by sha256**: a mismatch (stale/forged/edited source) or
       missing provenance degrades to ``unverified``. A corrupt fixture degrades
       too (never crashes). Otherwise decide offline (no Hancom call).
    2. else a faithful oracle renders once → ``render_checked = True``; optionally
       ``freeze_to`` persists the provenance-bound capture for later regression.
    3. else → :func:`unverified_verdict`.
    """

    if frozen_path and os.path.exists(frozen_path):
        try:
            fixture = WordBoxFixture.load(frozen_path)
        except Exception as exc:  # corrupt/unreadable -> honest degrade, never crash
            return unverified_verdict(f"unreadable frozen fixture: {exc}")
        if not fixture.checked:
            return unverified_verdict("frozen fixture is not a faithful capture (checked=false)")
        if not fixture.source_sha256:
            return unverified_verdict("frozen fixture has no render provenance")
        if not (hwpx_path and os.path.exists(hwpx_path)):
            return unverified_verdict("source document unavailable to bind frozen fixture")
        try:
            src_hash = sha256_file(hwpx_path)  # directory/unreadable -> OSError
        except OSError as exc:
            return unverified_verdict(f"source document unreadable to bind frozen fixture: {type(exc).__name__}")
        if src_hash != fixture.source_sha256:
            return unverified_verdict("frozen fixture does not match source document (stale)")
        return verdict_from_boxes(
            fixture.boxes, clips, render_checked=True, layout_stable=layout_stable
        )

    try:
        boxes, sizes, backend = render_glyph_boxes(hwpx_path, oracle=oracle)
    except OracleUnavailable as exc:
        return unverified_verdict(str(exc))
    if freeze_to:  # persisting the regression fixture is best-effort: never sink a faithful verdict
        try:
            src_sha = sha256_file(hwpx_path) if os.path.exists(hwpx_path) else None
            WordBoxFixture(
                boxes=boxes,
                page_sizes=sizes,
                source=os.path.basename(hwpx_path),
                checked=True,
                source_sha256=src_sha,
                backend=backend,
            ).freeze(freeze_to)
        except Exception:  # any persistence failure (OSError, ValueError on NUL path, ...) is non-fatal
            pass
    return verdict_from_boxes(boxes, clips, render_checked=True, layout_stable=layout_stable)


__all__ = [
    "Rect",
    "WordBox",
    "WordBoxFixture",
    "FormFillVerdict",
    "OracleUnavailable",
    "fitz_available",
    "sha256_file",
    "extract_word_boxes",
    "extract_glyph_boxes",
    "detect_overlaps",
    "diff_overlaps",
    "detect_overflow",
    "diff_overflow",
    "verdict_from_boxes",
    "unverified_verdict",
    "render_glyph_boxes",
    "verify_form_fill",
    "extract_cell_clips",
    "render_form_geometry",
    "verify_form_overflow",
    "LayoutSignature",
    "LayoutDiff",
    "extract_layout_signature",
    "diff_layout",
    "render_form_layout",
    "verify_form_layout_stability",
    "verify_form_fill_differential",
]
