# SPDX-License-Identifier: Apache-2.0
"""Conservative text measurement for FormFit (plan §2 C, task 2).

Everything is in **HWPUNIT** (1 pt = 100 HWPUNIT, 1 inch = 7200 HWPUNIT). Crucially
font height *and* cell width share that unit, so a glyph's advance is just a
fraction of the font height (the "em") — no DPI/point conversion is needed.

The advance fractions below are **calibrated against a real Hancom-saved form**
(``work/formfit_calibrate.py`` over 1492 ``lineSegArray`` caches): full-width
Hangul/CJK is reliably 1.0 em; Latin/digit/space/punct are averaged and therefore
*approximate*. That approximation is the whole reason measurement reports a
**confidence** and the engine refuses to hard-fail a borderline case — Hancom (the
render oracle) is the only authority on the close calls (plan §1 "measure-first",
§2 C acceptance "measurement honesty over false precision").
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

# Advance width as a fraction of the em (font height in HWPUNIT). Hangul/wide are
# exact (full-width cells); the Latin/digit/punct values are conservative class
# averages — slightly generous so "it fits" stays trustworthy, never tight.
_ADVANCE_EM: dict[str, float] = {
    "hangul": 1.0,
    "wide": 1.0,
    "upper": 0.70,
    "lower": 0.52,
    "digit": 0.55,
    "space": 0.32,
    "punct": 0.42,
    "other": 0.62,
}

# Per-class relative measurement uncertainty. Hangul is rock-solid; Latin/punct
# are crude (no per-glyph metrics yet — deferred to the HarfBuzz pass, plan §2 C
# "Deferred (a)"). A value's overall band is the advance-weighted blend.
_CLASS_UNCERTAINTY: dict[str, float] = {
    "hangul": 0.05,
    "wide": 0.05,
    "space": 0.08,
    "digit": 0.12,
    "upper": 0.20,
    "lower": 0.20,
    "punct": 0.22,
    "other": 0.25,
}

# Width left as a safety inset (cell padding/indent Hancom applies beyond the
# explicit cellMargin; empirically ~284 HWPUNIT on small cells). Applied as a
# multiplicative factor so it scales and also buys headroom on the advance error.
DEFAULT_SAFETY = 0.93

Confidence = Literal["high", "low"]


def classify_char(ch: str) -> str:
    """Bucket *ch* into an advance class (see ``_ADVANCE_EM``)."""

    if ch in " \t ":
        return "space"
    code = ord(ch)
    # Hangul syllables, jamo, compatibility jamo.
    if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "hangul"
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return "wide"
    if ch.isdigit():
        return "digit"
    if ch.isalpha():
        return "upper" if ch.isupper() else "lower"
    if not ch.isalnum():
        return "punct"
    return "other"


def char_advance(ch: str, font_pt: float) -> float:
    """Advance of *ch* at *font_pt*, in HWPUNIT."""

    return _ADVANCE_EM[classify_char(ch)] * font_pt * 100.0


def estimate_text_width(text: str, font_pt: float) -> float:
    """Conservative single-line width of *text* at *font_pt*, in HWPUNIT."""

    em = font_pt * 100.0
    return sum(_ADVANCE_EM[classify_char(ch)] for ch in text) * em


def _uncertainty_band(text: str) -> float:
    """Advance-weighted relative measurement error for *text* (0 → certain)."""

    stripped = text.strip()
    if not stripped:
        return _CLASS_UNCERTAINTY["space"]
    weighted = 0.0
    total = 0.0
    for ch in stripped:
        cls = classify_char(ch)
        adv = _ADVANCE_EM[cls]
        weighted += adv * _CLASS_UNCERTAINTY[cls]
        total += adv
    return weighted / total if total else _CLASS_UNCERTAINTY["other"]


# In-word punctuation a Latin run may break *after* (Hancom / UAX #14): an email,
# URL, file path, or hyphenated model number wraps at these — it is NOT one
# unbreakable token. Without this the overflow lint false-positives on such cells.
_LATIN_BREAK_AFTER = frozenset("/\\-.@:_?=&,;")


def _break_opportunities(text: str) -> set[int]:
    """Indices *before which* a soft line break may occur.

    Korean wraps after spaces (word level) and Hancom also allows a break between
    a wide/Hangul glyph and the next character. A pure-Latin run stays whole
    EXCEPT after in-word punctuation (``_LATIN_BREAK_AFTER``), where Hancom wraps.
    """

    opportunities: set[int] = set()
    for index in range(1, len(text)):
        prev, cur = text[index - 1], text[index]
        if prev in " \t ":
            opportunities.add(index)
            continue
        if classify_char(prev) in ("hangul", "wide") or classify_char(cur) in (
            "hangul",
            "wide",
        ):
            opportunities.add(index)
            continue
        if prev in _LATIN_BREAK_AFTER and cur not in (" ", "\t"):
            opportunities.add(index)
    return opportunities


def estimate_lines(text: str, available_width: float, font_pt: float) -> int:
    """Greedy line count for *text* in a slot *available_width* wide (HWPUNIT).

    Greedy packing over-estimates slightly versus a naive width/budget ratio
    (it accounts for wrap waste), which keeps the line count — and therefore an
    overflow verdict — on the conservative side.
    """

    if available_width <= 0:
        return 1_000_000
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    total = 0
    for line in lines:
        total += _wrap_one_logical_line(line, available_width, font_pt)
    return max(total, 1)


def _wrap_one_logical_line(line: str, available_width: float, font_pt: float) -> int:
    if not line:
        return 1
    breaks = _break_opportunities(line)
    em = font_pt * 100.0
    used = 0.0
    count = 1
    last_break: int | None = None
    used_at_break = 0.0
    for index, ch in enumerate(line):
        adv = _ADVANCE_EM[classify_char(ch)] * em
        if index in breaks:
            last_break = index
            used_at_break = used
        if used + adv > available_width and used > 0:
            count += 1
            if last_break is not None and last_break > 0:
                # Rewrap: characters after the last break opportunity move down.
                used = (used - used_at_break) + adv
                last_break = None
            else:
                used = adv
        else:
            used += adv
    return count


@dataclass(slots=True)
class SlotMetrics:
    """Geometry of the box a value must fit into (HWPUNIT + points)."""

    available_width: float          # usable inner width after margins + safety
    font_pt: float
    max_lines: int = 1
    raw_width: float | None = None  # cellSz.width before margins (diagnostics)
    source: str = "cell"

    @property
    def capacity(self) -> float:
        return self.available_width * self.max_lines


@dataclass(slots=True)
class Measurement:
    """Verdict of measuring a value against a :class:`SlotMetrics`."""

    width: float                    # predicted single-line width, HWPUNIT
    lines: int                      # predicted wrapped line count
    fits: bool                      # lines <= slot.max_lines
    confidence: Confidence          # trust in fits/overflow given measurement error
    ratio: float                    # width / single-line available_width
    band: float                     # relative measurement uncertainty used
    notes: list[str] = field(default_factory=list)

    @property
    def overflow(self) -> bool:
        return not self.fits

    def to_dict(self) -> dict[str, object]:
        return {
            "width": round(self.width),
            "lines": self.lines,
            "fits": self.fits,
            "confidence": self.confidence,
            "ratio": round(self.ratio, 4),
            "band": round(self.band, 4),
            "notes": list(self.notes),
        }


def measure(value: str, slot: SlotMetrics) -> Measurement:
    """Measure *value* against *slot* and judge fit + confidence.

    The confidence rule is the honesty contract (plan §2 C): a verdict is *high*
    confidence only when it survives the measurement error band — i.e. the value
    is comfortably inside or comfortably past the slot. Anything within the band
    is *low* confidence, which the engine treats as "defer to the oracle".
    """

    width = estimate_text_width(value, slot.font_pt)
    lines = estimate_lines(value, slot.available_width, slot.font_pt)
    fits = lines <= slot.max_lines
    band = _uncertainty_band(value)
    available_single = slot.available_width or 1.0
    ratio = width / available_single
    capacity = slot.capacity or 1.0

    notes: list[str] = []
    if fits:
        # High confidence only if it clears the band — clearly inside the box.
        confidence: Confidence = "high" if width <= capacity * (1 - band) else "low"
        if confidence == "low":
            notes.append(
                "borderline fit: within the measurement error band; "
                "render oracle should confirm"
            )
    else:
        # Need to overflow the band too, else it is a borderline overflow that a
        # crude advance table must not turn into a hard failure.
        min_lines_high_conf = math.ceil(
            (width * (1 - band)) / available_single - 1e-9
        )
        confidence = "high" if min_lines_high_conf > slot.max_lines else "low"
        if confidence == "low":
            notes.append(
                "borderline overflow: within the measurement error band; "
                "defer the hard fail to the render oracle"
            )
    return Measurement(
        width=width,
        lines=lines,
        fits=fits,
        confidence=confidence,
        ratio=ratio,
        band=band,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Bridge to the document model: resolve a cell's slot geometry.
# --------------------------------------------------------------------------- #
def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _cell_margin(cell_element: object) -> tuple[int, int]:
    """Return (left, right) cellMargin in HWPUNIT, defaulting to 0."""

    for child in cell_element:  # type: ignore[attr-defined]
        if _local_name(child.tag) == "cellMargin":
            return (
                int(child.get("left", "0") or 0),
                int(child.get("right", "0") or 0),
            )
    return (0, 0)


def _first_run_font_pt(cell: object, document: object) -> float:
    """Resolve the cell's first run font size in points (default 10pt)."""

    try:
        paragraphs = cell.paragraphs  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        paragraphs = []
    for paragraph in paragraphs:
        for run in getattr(paragraph, "runs", []):
            ref = getattr(run, "char_pr_id_ref", None)
            pt = _font_pt_from_ref(ref, document)
            if pt is not None:
                return pt
    return 10.0


def _font_pt_from_ref(ref: object, document: object) -> float | None:
    if ref is None or document is None:
        return None
    try:
        style = document.char_property(ref)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return None
    if style is None:
        return None
    height = getattr(style, "attributes", {}).get("height")
    if not height:
        return None
    try:
        return int(height) / 100.0
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def resolve_slot_metrics(
    cell: object,
    document: object,
    *,
    max_lines: int = 1,
    font_pt: float | None = None,
    safety: float = DEFAULT_SAFETY,
) -> SlotMetrics:
    """Build :class:`SlotMetrics` from a live table cell.

    ``available_width = (cellSz.width - cellMargin.L - cellMargin.R) * safety`` —
    verified against Hancom's own ``lineSeg/@horzsize`` (±10 HWPUNIT on 82% of
    cells; the safety factor covers the rest plus paragraph indent, which is left
    to the HarfBuzz pass).
    """

    raw_width = float(getattr(cell, "width", 0) or 0)
    element = getattr(cell, "element", None)
    left, right = _cell_margin(element) if element is not None else (0, 0)
    inner = max(raw_width - left - right, 0.0) * safety
    resolved_pt = font_pt if font_pt is not None else _first_run_font_pt(cell, document)
    return SlotMetrics(
        available_width=inner,
        font_pt=resolved_pt,
        max_lines=max(max_lines, 1),
        raw_width=raw_width,
        source="cell",
    )


__all__ = [
    "SlotMetrics",
    "Measurement",
    "Confidence",
    "DEFAULT_SAFETY",
    "classify_char",
    "char_advance",
    "estimate_text_width",
    "estimate_lines",
    "measure",
    "resolve_slot_metrics",
]
