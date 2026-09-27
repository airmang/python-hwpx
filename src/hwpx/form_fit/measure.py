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

A slot with a :class:`TextStyle` (cell and form-field slots carry one) breaks
lines the way Hancom does, with no font file: a space is half an em, 장평 and
자간 scale each advance, the paragraph's break settings decide where a line may
end, spaces at a line end hang past the margin, 최소 공백 lets inner spaces
shrink, indents come off the first or the following lines, closing punctuation
never starts a line, and inline objects on the line take their width off the
first line only (see :func:`hancom_line_starts`).
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

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

# --- Vertical (line-height) model ------------------------------------------- #
# Per-line vertical advance as a multiple of the em (font height in HWPUNIT).
# HWP's application default is 160% line spacing, so a line occupies ~1.6 em; this
# is the advance used when a paragraph declares no explicit lineSpacing, and it
# matches ``layout.lint._LINE_SPACING``. Used as the *expected* pitch for the
# authored vertical budget (the point at which the row is warned it will grow).
DEFAULT_LINE_SPACING_RATIO = 1.6

# Tightest per-line advance Hancom is observed to use (a glyph box with no leading).
# Measured on the M9 wild-form corpus: two soft-wrapped lines render inside cells
# only ~2.0 em tall, so the real pitch bottoms out near 1.0 em. Used to compute the
# *optimistic* (most generous) height budget, so a vertical overflow is only treated
# as high confidence when content overflows even at this tightest pitch.
MIN_LINE_SPACING_RATIO = 1.0

# A vertical overflow is a *hard* balloon (shrink-or-refuse) only when content needs
# at least this multiple of the optimistic authored line budget AND this many extra
# lines in absolute terms. Below the gross threshold the row may grow only modestly
# and the render oracle arbitrates. Measure-first calibration on the M9 corpus: a
# hard cap at the optimistic budget mis-refuses 47% of known-good multi-line cells,
# whereas this gross gate mis-refuses 2% — it fires on page-shifting balloons only.
# (Same balloon philosophy as ``layout.lint._BALLOON_FACTOR``.)
GROSS_ROW_GROWTH_FACTOR = 2.0
MIN_ROW_GROWTH_LINES = 2

Confidence = Literal["high", "low"]

# --- Hancom line layout rules (no font file needed) --------------------------- #
#: Spaces that hang past the right margin at a line end; a line never starts
#: with one.
_HANGING_SPACES = " " + chr(0xA0)
#: Closing punctuation that never starts a line; it moves down with the
#: character before it.
_NO_LINE_START = frozenset("!%),.:;?]}¢°’”‰′″℃〉》」』】〕…·、。")
#: Opening punctuation that never ends a line.
_NO_LINE_END = frozenset("([{‘“〈《「『【〔")


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Character and paragraph settings Hancom lays a line out with.

    ``ratio`` (장평, %) and ``spacing`` (자간, % of each glyph's own width)
    scale every advance, and a space is half an em unless ``use_font_space``.
    ``break_non_latin_word`` works the reverse of its name in Hancom:
    ``BREAK_WORD`` (the default) keeps Hangul words whole and ``KEEP_WORD``
    breaks between any two syllables; ``break_latin_word`` works as named.
    ``condense`` (최소 공백, %) lets the spaces inside a line shrink by that
    share. ``indent`` is the first-line indent in HWPUNIT; a negative value is
    a hanging indent taken off every line after the first.
    """

    ratio: float = 100.0
    spacing: float = 0.0
    use_font_space: bool = False
    break_latin_word: str = "KEEP_WORD"
    break_non_latin_word: str = "BREAK_WORD"
    condense: int = 0
    indent: int = 0


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


def char_advance(ch: str, font_pt: float, style: TextStyle | None = None) -> float:
    """Advance of *ch* at *font_pt*, in HWPUNIT."""

    if style is None:
        return _ADVANCE_EM[classify_char(ch)] * font_pt * 100.0
    base = 0.5 if ch == " " and not style.use_font_space else _ADVANCE_EM[classify_char(ch)]
    return base * font_pt * 100.0 * style.ratio / 100.0 * (1 + style.spacing / 100.0)


def estimate_text_width(text: str, font_pt: float, style: TextStyle | None = None) -> float:
    """Conservative single-line width of *text* at *font_pt*, in HWPUNIT.

    With *style* the advances follow Hancom's rules (see :class:`TextStyle`).
    """

    if style is not None:
        return sum(char_advance(ch, font_pt, style) for ch in text)
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


# In-word punctuation a Latin run may break *after* in the class-average model
# (no TextStyle): an email, URL, file path, or hyphenated model number wraps at
# these. Hancom itself keeps such a word whole unless it is longer than the
# line, which is what the TextStyle path (``hancom_line_starts``) follows.
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


def _hancom_break_opportunities(text: str, style: TextStyle) -> set[int]:
    """Indices before which Hancom may start a new line under *style*."""

    opportunities: set[int] = set()
    for index in range(1, len(text)):
        prev, cur = text[index - 1], text[index]
        if cur in _HANGING_SPACES:
            continue
        if prev in _HANGING_SPACES:
            opportunities.add(index)
            continue
        if classify_char(prev) in ("hangul", "wide") or classify_char(cur) in ("hangul", "wide"):
            if style.break_non_latin_word == "KEEP_WORD":
                opportunities.add(index)
            continue
        if style.break_latin_word == "BREAK_WORD":
            opportunities.add(index)
    return opportunities


def hancom_line_starts(
    text: str, widths: list[float], font_pt: float, style: TextStyle
) -> list[int]:
    """Where Hancom starts each line of the one-line *text* (no newlines).

    ``widths[k]`` is the width of line ``k`` in HWPUNIT (the last one repeats).
    A line takes characters while they fit; spaces at its end hang past the
    margin and, with ``style.condense``, the spaces inside it may shrink to
    make room. The line then ends at the last break opportunity that fits —
    never before a closing or after an opening punctuation mark — or mid-word
    when no opportunity is left.
    """

    breaks = _hancom_break_opportunities(text, style)
    space = char_advance(" ", font_pt, style)
    starts = [0]
    length = len(text)
    start = 0
    while True:
        width = widths[min(len(starts) - 1, len(widths) - 1)]
        end, used, inner, pending = start, 0.0, 0, 0
        while end < length:
            ch = text[end]
            advance = char_advance(ch, font_pt, style)
            if ch in _HANGING_SPACES:
                used += advance
                pending += 1
                end += 1
                continue
            shrink = (inner + pending) * space * style.condense / 100.0
            if used + advance - shrink > width and end > start:
                break
            used += advance
            inner += pending
            pending = 0
            end += 1
        if end >= length:
            return starts
        options = [
            index for index in breaks
            if start < index <= end
            and text[index] not in _NO_LINE_START
            and text[index - 1] not in _NO_LINE_END
        ]
        start = max(options) if options else end
        while start < length and text[start] in _HANGING_SPACES:
            start += 1
        if start >= length:
            return starts
        starts.append(start)


def _hancom_line_count(
    text: str, first_width: float, rest_width: float, font_pt: float, style: TextStyle
) -> int:
    if first_width <= 0 or rest_width <= 0:
        return 1_000_000
    total = 0
    logical = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(logical):
        if not line:
            total += 1
            continue
        widths = [first_width, rest_width] if index == 0 else [rest_width]
        total += len(hancom_line_starts(line, widths, font_pt, style))
    return max(total, 1)


def estimate_lines(
    text: str, available_width: float, font_pt: float, style: TextStyle | None = None
) -> int:
    """Greedy line count for *text* in a slot *available_width* wide (HWPUNIT).

    Greedy packing over-estimates slightly versus a naive width/budget ratio
    (it accounts for wrap waste), which keeps the line count — and therefore an
    overflow verdict — on the conservative side. With *style* the lines follow
    Hancom's rules (see :func:`hancom_line_starts`), and ``style.indent`` comes
    off the first line (or, when negative, off the others).
    """

    if style is not None:
        return _hancom_line_count(
            text,
            available_width - max(style.indent, 0),
            available_width - max(-style.indent, 0),
            font_pt,
            style,
        )
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
    # Vertical budget. ``available_height`` is the usable inner height (HWPUNIT)
    # after top/bottom cell margins + the safety inset. ``None`` means the vertical
    # room was not (or could not be) measured, and the fit stays width-only.
    available_height: float | None = None
    # Per-line advance as a multiple of the em, from the cell's declared paragraph
    # line spacing (PERCENT). ``None`` falls back to ``DEFAULT_LINE_SPACING_RATIO``.
    line_spacing_ratio: float | None = None
    # Width already consumed on the line by inline treat-as-char objects
    # (checkboxes, form controls, pictures) that share the target paragraph.
    # Their declared ``hp:sz/@width`` is subtracted from the usable width —
    # ignoring them made the engine call "fits" on a fill that real Hancom
    # wrapped, growing the row and repaginating a 10-page form.
    inline_object_width: float = 0.0
    inline_object_count: int = 0
    # A cell height existed but was unusable (merged row-span fragment, or an
    # auto-grow floor shorter than one line). Records "height budget unavailable"
    # so the fit reports width-only honestly rather than guessing a vertical fit.
    height_unavailable: bool = False
    # Hancom's layout settings for the slot's text. ``None`` keeps the class
    # average model; with a style, lines follow Hancom's rules and the inline
    # objects take their width off the first line only.
    text_style: TextStyle | None = None

    @property
    def capacity(self) -> float:
        return self.available_width * self.max_lines

    def _line_ratio(self) -> float:
        ratio = self.line_spacing_ratio
        return ratio if ratio and ratio > 0 else DEFAULT_LINE_SPACING_RATIO

    def line_height(self, font_pt: float | None = None) -> float:
        """Expected per-line vertical advance in HWPUNIT at *font_pt*."""

        pt = self.font_pt if font_pt is None else font_pt
        return pt * 100.0 * self._line_ratio()

    def height_lines(self, font_pt: float | None = None) -> int | None:
        """Expected vertical line budget at *font_pt* (declared/default pitch).

        ``None`` when the vertical room is unmeasured. Never less than 1 — a cell
        always accommodates its first line; the risk we guard is *growth* past it.
        """

        if self.available_height is None:
            return None
        line_h = self.line_height(font_pt)
        if line_h <= 0:
            return None
        return max(int(self.available_height // line_h), 1)

    def height_lines_optimistic(self, font_pt: float | None = None) -> int | None:
        """Most-generous vertical budget (tightest plausible pitch).

        This is the basis for the *confidence* of a vertical overflow: content that
        overflows even this budget is grossly too tall regardless of pitch error.
        """

        if self.available_height is None:
            return None
        pt = self.font_pt if font_pt is None else font_pt
        ratio = min(self._line_ratio(), MIN_LINE_SPACING_RATIO)
        line_h = pt * 100.0 * ratio
        if line_h <= 0:
            return None
        return max(int(self.available_height // line_h), 1)


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

    style = slot.text_style
    width = estimate_text_width(value, slot.font_pt, style)
    band = _uncertainty_band(value)
    available_single = slot.available_width or 1.0
    ratio = width / available_single
    if style is None:
        lines = estimate_lines(value, slot.available_width, slot.font_pt)
        capacity = slot.capacity or 1.0
    else:
        # Inline objects share the first line only; indents come off the first
        # line or, when hanging, off the others.
        first = slot.available_width - max(style.indent, 0)
        rest = slot.available_width + slot.inline_object_width - max(-style.indent, 0)
        lines = _hancom_line_count(value, first, rest, slot.font_pt, style)
        capacity = (first + rest * (slot.max_lines - 1)) or 1.0
    fits = lines <= slot.max_lines

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
        if style is None:
            min_lines_high_conf = math.ceil(
                (width * (1 - band)) / available_single - 1e-9
            )
        else:
            optimistic = width * (1 - band)
            min_lines_high_conf = 1 if optimistic <= first else 1 + math.ceil(
                (optimistic - first) / max(rest, 1.0) - 1e-9
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


def _cell_margin_vertical(cell_element: object) -> tuple[int, int]:
    """Return (top, bottom) cellMargin in HWPUNIT, defaulting to 0."""

    for child in cell_element:  # type: ignore[attr-defined]
        if _local_name(child.tag) == "cellMargin":
            return (
                int(child.get("top", "0") or 0),
                int(child.get("bottom", "0") or 0),
            )
    return (0, 0)


def _effective_cell_margins(cell: object) -> tuple[int, int, int, int]:
    """Respect explicit table-margin inheritance instead of inactive cell zeros."""
    element = getattr(cell, "element", None)
    if element is None:
        return (0, 0, 0, 0)
    if element.get("hasMargin") in {"0", "false", "False"}:
        table_element = getattr(getattr(cell, "table", None), "element", None)
        if table_element is not None:
            for child in table_element:
                if _local_name(child.tag) == "inMargin":
                    return (
                        int(child.get("left", "0") or 0),
                        int(child.get("right", "0") or 0),
                        int(child.get("top", "0") or 0),
                        int(child.get("bottom", "0") or 0),
                    )
    left, right = _cell_margin(element)
    top, bottom = _cell_margin_vertical(element)
    return left, right, top, bottom


def _document_root(document: object) -> Any:
    """The OXML document root: ``HwpxDocument._root``, or *document* itself.

    Callers pass either; the root's own ``paragraph_property``/``char_property``
    do not raise the 6.0 move warnings that the ``HwpxDocument`` names do.
    """

    return getattr(document, "_root", document)


def _first_para_line_spacing_ratio(cell: object, document: object) -> float | None:
    """Per-line em multiple from the cell's first paragraph line spacing (PERCENT).

    Only PERCENT spacing maps cleanly onto the em-relative line-height model; FIXED
    / ATLEAST / BETWEENLINES are left to the conservative default so we never invent
    a font-independent pitch (the shrink ladder varies the font).
    """

    try:
        paragraphs = cell.paragraphs  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return None
    for paragraph in paragraphs:
        ref = getattr(paragraph, "para_pr_id_ref", None)
        if ref is None or document is None:
            continue
        try:
            prop = _document_root(document).paragraph_property(ref)
        except Exception:  # pragma: no cover - defensive
            prop = None
        spacing = getattr(prop, "line_spacing", None) if prop is not None else None
        if spacing is None or not getattr(spacing, "value", None):
            continue
        if (getattr(spacing, "spacing_type", None) or "PERCENT").upper() != "PERCENT":
            return None
        try:
            return int(spacing.value) / 100.0
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return None


def _style_number(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def text_style_from_refs(
    document: object, para_pr_id_ref: object, char_pr_id_refs: "list[object]"
) -> TextStyle:
    """Hancom layout settings of a paragraph shape and the first resolvable
    character shape among *char_pr_id_refs*."""

    ratio, spacing, use_font_space = 100.0, 0.0, False
    for ref in char_pr_id_refs:
        try:
            run_style = document.char_property(ref)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            run_style = None
        if run_style is None:
            continue
        children = getattr(run_style, "child_attributes", {}) or {}
        ratio = _style_number((children.get("ratio") or {}).get("hangul"), 100.0)
        spacing = _style_number((children.get("spacing") or {}).get("hangul"), 0.0)
        use_font_space = (getattr(run_style, "attributes", {}) or {}).get("useFontSpace") in {"1", "true"}
        break
    try:
        prop = document.paragraph_property(para_pr_id_ref)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        prop = None
    if prop is None:
        return TextStyle(ratio=ratio, spacing=spacing, use_font_space=use_font_space)
    breaks = getattr(prop, "break_setting", None)
    # hp:case carries the HWPUNIT values Hancom lays out with; hp:default doubles them.
    switch = getattr(prop, "version_switch", None)
    case = getattr(switch, "case", None) if switch is not None else None
    margin = getattr(case, "margin", None) if case is not None else None
    if margin is None:
        margin = getattr(prop, "margin", None)
    return TextStyle(
        ratio=ratio,
        spacing=spacing,
        use_font_space=use_font_space,
        break_latin_word=getattr(breaks, "break_latin_word", None) or "KEEP_WORD",
        break_non_latin_word=getattr(breaks, "break_non_latin_word", None) or "BREAK_WORD",
        condense=int(_style_number(getattr(prop, "condense", 0), 0.0)),
        indent=int(_style_number(getattr(margin, "intent", 0), 0.0)),
    )


def _cell_text_style(cell: object, document: object) -> TextStyle:
    """Hancom layout settings of the cell's first paragraph and first run."""

    try:
        paragraphs = list(cell.paragraphs)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        paragraphs = []
    if not paragraphs or document is None:
        return TextStyle()
    paragraph = paragraphs[0]
    refs = [getattr(run, "char_pr_id_ref", None) for run in getattr(paragraph, "runs", [])]
    return text_style_from_refs(document, getattr(paragraph, "para_pr_id_ref", None), refs)


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
        style = _document_root(document).char_property(ref)
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

    ``text_style`` carries the Hancom layout settings of the cell's first
    paragraph and run (break settings, 최소 공백, indent, 장평, 자간), so the
    fit follows Hancom's line breaking rules.

    ``available_height`` follows the same philosophy — ``(cellSz.height - top -
    bottom margin) * safety`` — but is recorded as *unavailable* (``None`` +
    ``height_unavailable``) whenever the authored height is not a real ceiling:
    a merged cell (its ``cellSz.height`` is a single-row fragment, not the spanned
    height), a cell with no height, or an auto-grow floor shorter than one line
    (Hancom simply grows the row past it). The fit then stays width-only rather
    than guess a vertical fit.
    """

    raw_width = float(getattr(cell, "width", 0) or 0)
    element = getattr(cell, "element", None)
    left, right, top, bottom = _effective_cell_margins(cell)
    inner = max(raw_width - left - right, 0.0) * safety
    inline_width, inline_count = (
        _inline_object_width(element) if element is not None else (0.0, 0)
    )
    if inline_width:
        inner = max(inner - inline_width, 0.0)
    resolved_pt = font_pt if font_pt is not None else _first_run_font_pt(cell, document)
    line_ratio = _first_para_line_spacing_ratio(cell, document)

    available_height: float | None = None
    height_unavailable = False
    raw_height = float(getattr(cell, "height", 0) or 0)
    try:
        row_span = int(getattr(cell, "span", (1, 1))[0])
    except Exception:  # pragma: no cover - defensive
        row_span = 1
    inner_h = max(raw_height - top - bottom, 0.0) * safety if raw_height > 0 else 0.0
    # A cell authored shorter than one line at the tightest pitch is an auto-grow
    # floor, not a ceiling (Hancom grows the row past it); a merged row-span's
    # cellSz.height is only one of the spanned rows. Neither is a usable budget.
    one_line = resolved_pt * 100.0 * MIN_LINE_SPACING_RATIO
    if row_span <= 1 and inner_h >= one_line:
        available_height = inner_h
    else:
        height_unavailable = True

    return SlotMetrics(
        available_width=inner,
        font_pt=resolved_pt,
        max_lines=max(max_lines, 1),
        raw_width=raw_width,
        source="cell",
        available_height=available_height,
        line_spacing_ratio=line_ratio,
        height_unavailable=height_unavailable,
        inline_object_width=inline_width,
        inline_object_count=inline_count,
        text_style=_cell_text_style(cell, document),
    )


def _inline_object_width(cell_element: object) -> tuple[float, int]:
    """Total declared width of inline treat-as-char objects in the cell.

    Checkboxes and similar form controls flow on the text line
    (``hp:pos/@treatAsChar='1'``) and consume their ``hp:sz/@width``; a fill
    value shares whatever width remains. Objects without a declared size are
    counted but contribute 0 width (the count still signals reduced trust).
    """

    total = 0.0
    count = 0
    iter_fn = getattr(cell_element, "iter", None)
    if iter_fn is None:
        return 0.0, 0
    for node in iter_fn():
        tag = getattr(node, "tag", "")
        if not isinstance(tag, str):
            continue
        local = tag.rsplit("}", 1)[-1].lower()
        if local != "pos":
            continue
        if (node.get("treatAsChar") or "").strip() not in {"1", "true", "TRUE"}:
            continue
        holder = node.getparent() if hasattr(node, "getparent") else None
        if holder is None:
            continue
        count += 1
        for sibling in holder:
            sib_local = str(getattr(sibling, "tag", "")).rsplit("}", 1)[-1].lower()
            if sib_local == "sz":
                try:
                    total += float(sibling.get("width") or 0)
                except (TypeError, ValueError):
                    pass
                break
    return total, count


__all__ = [
    "SlotMetrics",
    "TextStyle",
    "Measurement",
    "Confidence",
    "DEFAULT_SAFETY",
    "DEFAULT_LINE_SPACING_RATIO",
    "MIN_LINE_SPACING_RATIO",
    "GROSS_ROW_GROWTH_FACTOR",
    "MIN_ROW_GROWTH_LINES",
    "classify_char",
    "char_advance",
    "estimate_text_width",
    "estimate_lines",
    "hancom_line_starts",
    "measure",
    "resolve_slot_metrics",
]
