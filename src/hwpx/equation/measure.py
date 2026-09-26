# SPDX-License-Identifier: Apache-2.0
"""Measure an EqEdit script the way Hancom sizes an equation box.

Hancom measures an equation when it is made and stores the box as ``<hp:sz>``
and the baseline as ``baseLine`` (the share of the box height above the
baseline, in percent). It does not measure it again when a document is
opened: the page is laid out with the stored box, so a box that is too wide
leaves a gap after the equation and one that is too narrow lets the next
characters overlap it.

This module lays the script out as boxes (width, ascent, descent) by its
structure -- characters by kind, ``over`` fractions, ``^``/``_`` scripts,
``sqrt``/``root``, big operators with their limits, ``lim`` with the limit
below, matrices and ``pile``, and ``#`` line breaks. The widths are in em of
the base size for the ``HYhwpEQ`` equation font python-hwpx writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .eqedit import MAX_GROUP_DEPTH, MAX_SOURCE_LENGTH, _tokenize
from .tokens import (
    ACCENTS,
    BIG_OPERATORS,
    FUNCTIONS,
    GREEK,
    MATRIX_ENVIRONMENTS,
    OPERATORS,
    SYMBOL_OPERATORS,
)

__all__ = ["EquationSize", "measure_equation"]

# Widths and gaps in em of the base size.
_DIGIT = 0.53
_LOWER = 0.51
_UPPER = 0.67
_GREEK = 0.6
_HANGUL = 0.83
_PUNCT = 0.29
_BRACKET = 0.52
_OPERATOR = 0.69 + 2 * 0.2  # glyph and the space on each side
_FUNCTION_CHAR = 0.48
_FUNCTION_PAD = 0.15
_SPACE = 0.25  # ~
_THIN_SPACE = 0.09  # `
_OTHER = 0.36
_SYMBOL = 1.05
_SCRIPT_SCALE = 0.55
_SCRIPT_RAISE = 0.48
_SUBSCRIPT_DROP = -0.2
_FRACTION_PAD = 0.29
_FRACTION_GAP = 0.34
_FRACTION_AXIS = 0.37
_ROOT_SIGN = 1.49
_ROOT_TOP = 0.14
_BIG_OPERATOR = 1.0
_BIG_OPERATOR_HEIGHT = 1.25
_INTEGRAL_SIGN = 1.0
_INTEGRAL_SPACE = 0.4
_INTEGRAL_HEIGHT = 2.27
_INTEGRAL_LIMIT_EXTRA = 0.2
_LIMIT_SCALE = 0.75
_LIMIT_GAP = 0.035
_ACCENT_TOP = 0.25
_DELIMITER_EXTRA = 0.1
_COLUMN_GAP = 0.25
_ROW_GAP = 0.25
_LINE_GAP = 0.3
_ASCENT = 0.85
_DESCENT = 0.14
_BOX_PAD = 0.055

_MATRICES = frozenset(MATRIX_ENVIRONMENTS) | {"pile", "lpile", "rpile"}
_INTEGRALS = {"int": 1, "oint": 1, "dint": 2, "tint": 3}
#: Delimiters a matrix environment draws around its cells (count of bracket widths).
_MATRIX_DELIMITERS = {"pmatrix": 2, "bmatrix": 2, "Bmatrix": 2, "vmatrix": 2, "Vmatrix": 2, "dmatrix": 2, "cases": 1}
_LIMIT_WORDS = frozenset({"lim", "limsup", "liminf", "max", "min"})
_FONT_WORDS = frozenset({"rm", "it", "bold"})
_RELATIONS = frozenset({"=", "<", ">", "+", "-", "×", "÷"}) | frozenset(SYMBOL_OPERATORS)
#: Hancom symbol names (any case) drawn with operator spacing.
_SYMBOL_RELATIONS = frozenset({
    "sim", "simeq", "approx", "cong", "equiv", "in", "ni", "notin", "subset", "supset", "nsubset",
    "nsupset", "subseteq", "supseteq", "cup", "cap", "smallinter", "smallunion", "perp", "parallel",
    "propto", "prop", "le", "ge", "leq", "geq", "ne", "neq", "times", "div", "divide", "pm", "mp",
    "cdot", "circ", "bullet", "rarrow", "larrow", "lrarrow", "rightarrow", "leftarrow", "therefore",
    "because", "vee", "wedge", "oplus", "otimes", "ll", "gg", "lsub", "rsub",
})
#: Hancom symbol names (any case) drawn as one symbol.
_SYMBOL_ORDINARY = frozenset({
    "inf", "infinity", "deg", "angle", "triangle", "prime", "partial", "nabla", "hbar", "emptyset",
    "aleph", "forall", "exists", "neg", "cdots", "ldots", "vdots", "ddots", "dagger", "box", "diamond",
    "centigrade",
})


class EquationSize(NamedTuple):
    """An equation box in HWPUNIT and its ``baseLine`` (percent of the height)."""

    width: int
    height: int
    base_line: int


@dataclass
class _Box:
    width: float
    ascent: float
    descent: float

    @property
    def height(self) -> float:
        return self.ascent + self.descent

    def scaled(self, factor: float) -> "_Box":
        return _Box(self.width * factor, self.ascent * factor, self.descent * factor)


def _row(boxes: list[_Box]) -> _Box:
    row = _Box(0.0, _ASCENT, _DESCENT)
    for box in boxes:
        row = _Box(row.width + box.width, max(row.ascent, box.ascent), max(row.descent, box.descent))
    return row


def _stack(lines: list[_Box], gap: float) -> _Box:
    height = sum(line.height for line in lines) + gap * (len(lines) - 1)
    return _Box(max(line.width for line in lines), lines[0].ascent, height - lines[0].ascent)


def _fraction(numerator: _Box, denominator: _Box) -> _Box:
    return _Box(
        max(numerator.width, denominator.width) + 2 * _FRACTION_PAD,
        numerator.height + _FRACTION_GAP / 2 + _FRACTION_AXIS,
        denominator.height + _FRACTION_GAP / 2 - _FRACTION_AXIS,
    )


def _token_width(token: str) -> float:
    lower = token.lower()
    if token.startswith('"'):
        return sum(_HANGUL if "가" <= ch <= "힣" else (_SPACE if ch == " " else _LOWER) for ch in token.strip('"'))
    if token in GREEK:
        return _GREEK
    if token in OPERATORS or token in _RELATIONS or lower in _SYMBOL_RELATIONS:
        return _OPERATOR
    if lower in _SYMBOL_ORDINARY:
        return _SYMBOL
    if token.replace(".", "").isdigit():
        return sum(_DIGIT if ch.isdigit() else _PUNCT for ch in token)
    if token.isalpha():
        return sum(_UPPER if ch.isupper() else (_HANGUL if "가" <= ch <= "힣" else _LOWER) for ch in token)
    if token in "()[]|":
        return _BRACKET
    if token in ",.;:!'":
        return _PUNCT
    return _OTHER


class _Measurer:
    """Recursive descent over EqEdit tokens, mirroring the LaTeX converter's grammar."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0
        self.too_deep = False

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str | None:
        token = self._peek()
        if token is not None:
            self._pos += 1
        return token

    def sequence(self, depth: int, stop: str | None = None) -> _Box:
        lines: list[_Box] = []
        items: list[_Box] = []
        while True:
            token = self._peek()
            if token is None or token == stop or (stop == "RIGHT" and token in ("RIGHT", "right")):
                break
            self._next()
            if token == "#":
                lines.append(_row(items))
                items = []
            elif token in ("^", "_"):
                items.append(self._scripts(items.pop() if items else _Box(0.0, 0.0, 0.0), token, depth))
            elif token in ("over", "atop"):
                numerator = items.pop() if items else _row([])
                items.append(_fraction(numerator, self._atom(depth)))
            elif token != "&":
                items.append(self._dispatch(token, depth))
        if not lines:
            return _row(items)
        return _stack([*lines, _row(items)], _LINE_GAP)

    def _atom(self, depth: int) -> _Box:
        token = self._next()
        return _Box(0.0, 0.0, 0.0) if token is None else self._dispatch(token, depth)

    def _group(self, depth: int) -> _Box:
        if depth + 1 > MAX_GROUP_DEPTH:
            self.too_deep = True
            return _Box(0.0, 0.0, 0.0)
        inner = self.sequence(depth + 1, stop="}")
        if self._peek() == "}":
            self._next()
        return inner

    def _scripts(self, base: _Box, operator: str, depth: int) -> _Box:
        scripts = {operator: self._atom(depth).scaled(_SCRIPT_SCALE)}
        following = self._peek()
        if following in ("^", "_") and following != operator:
            self._next()
            scripts[following] = self._atom(depth).scaled(_SCRIPT_SCALE)
        upper, lower = scripts.get("^"), scripts.get("_")
        width = base.width + max(upper.width if upper else 0.0, lower.width if lower else 0.0)
        ascent = max(base.ascent, _SCRIPT_RAISE + upper.height) if upper else base.ascent
        descent = max(base.descent, _SUBSCRIPT_DROP + lower.height) if lower else base.descent
        return _Box(width, ascent, descent)

    def _dispatch(self, token: str, depth: int) -> _Box:
        if token == "{":
            return self._group(depth)
        if token in ("sqrt", "root"):
            return self._root(token, depth)
        if token in ACCENTS:
            inner = self._atom(depth)
            return _Box(inner.width, inner.ascent + _ACCENT_TOP, inner.descent)
        if token in _MATRICES:
            box = self._matrix(depth)
            return _Box(box.width + _MATRIX_DELIMITERS.get(token, 0) * _BRACKET, box.ascent, box.descent)
        if token in ("LEFT", "left"):
            return self._delimited(depth)
        if token in ("RIGHT", "right"):
            self._next()
            return _Box(_BRACKET, _ASCENT, _DESCENT)
        if token in _INTEGRALS:
            return self._integral(token, depth)
        if token.lower() in _LIMIT_WORDS and self._peek() in ("_", "from"):
            return self._limit(token, depth)
        if token in BIG_OPERATORS and token.lower() not in _LIMIT_WORDS and token not in ("iint", "iiint"):
            return self._big_operator(depth)
        return self._symbol(token)

    def _symbol(self, token: str) -> _Box:
        if token in FUNCTIONS or token.lower() in _LIMIT_WORDS:
            return _Box(len(token) * _FUNCTION_CHAR + _FUNCTION_PAD, _ASCENT, _DESCENT)
        if token.lower() in _FONT_WORDS or token in ("of", "&"):
            return _Box(0.0, 0.0, 0.0)
        if token == "~":
            return _Box(_SPACE, 0.0, 0.0)
        if token == "`":
            return _Box(_THIN_SPACE, 0.0, 0.0)
        return _Box(_token_width(token), _ASCENT, _DESCENT)

    def _root(self, token: str, depth: int) -> _Box:
        index = _Box(0.0, 0.0, 0.0)
        if token == "root":
            index = self._atom(depth)
            if self._peek() == "of":
                self._next()
        inner = self._atom(depth)
        return _Box(inner.width + _ROOT_SIGN + index.width * _SCRIPT_SCALE / 2, inner.ascent + _ROOT_TOP, inner.descent)

    def _delimited(self, depth: int) -> _Box:
        self._next()  # the opening delimiter
        body = self.sequence(depth, stop="RIGHT")
        if self._peek() in ("RIGHT", "right"):
            self._next()
            self._next()  # the closing delimiter
        return _Box(body.width + 2 * _BRACKET, body.ascent + _DELIMITER_EXTRA, body.descent + _DELIMITER_EXTRA)

    def _integral(self, token: str, depth: int) -> _Box:
        """Hancom draws an integral tall, with its limits at the sign's corners."""
        width = _INTEGRAL_SIGN * _INTEGRALS[token]
        ascent, descent = _INTEGRAL_HEIGHT * 0.6, _INTEGRAL_HEIGHT * 0.4
        limit_width = 0.0
        while self._peek() in ("_", "^", "from", "to"):
            upper = self._next() in ("^", "to")
            limit = self._atom(depth).scaled(_SCRIPT_SCALE)
            limit_width = max(limit_width, limit.width)
            if upper:
                ascent += _INTEGRAL_LIMIT_EXTRA
            else:
                descent += _INTEGRAL_LIMIT_EXTRA
        return _Box(width + limit_width + _INTEGRAL_SPACE, ascent, descent)

    def _limit(self, token: str, depth: int) -> _Box:
        self._next()  # _ or from
        limit = self._atom(depth).scaled(_LIMIT_SCALE)
        width = len(token) * _FUNCTION_CHAR + _FUNCTION_PAD
        return _Box(max(width, limit.width), _ASCENT, _DESCENT + limit.height + _LIMIT_GAP)

    def _big_operator(self, depth: int) -> _Box:
        box = _Box(_BIG_OPERATOR, _BIG_OPERATOR_HEIGHT * 0.6, _BIG_OPERATOR_HEIGHT * 0.4)
        limits: list[_Box] = []
        while self._peek() in ("_", "^", "from", "to"):
            self._next()
            limits.append(self._atom(depth).scaled(_LIMIT_SCALE))
        if not limits:
            return box
        extra = sum(limit.height for limit in limits) / 2
        return _Box(max([box.width] + [limit.width for limit in limits]), box.ascent + extra, box.descent + extra)

    def _matrix(self, depth: int) -> _Box:
        if self._peek() != "{":
            return _Box(_LOWER * 6, _ASCENT, _DESCENT)
        self._next()
        rows: list[list[_Box]] = [[]]
        while self._peek() not in (None, "}"):
            rows[-1].append(self._cell(depth))
            if self._peek() == "#":
                self._next()
                rows.append([])
            elif self._peek() == "&":
                self._next()
        if self._peek() == "}":
            self._next()
        rows = [row for row in rows if row]
        if not rows:
            return _row([])
        columns = max(len(row) for row in rows)
        widths = [max((row[c].width for row in rows if c < len(row)), default=0.0) for c in range(columns)]
        height = sum(max(cell.height for cell in row) for row in rows) + _ROW_GAP * (len(rows) - 1)
        return _Box(sum(widths) + _COLUMN_GAP * (columns - 1), height / 2 + _FRACTION_AXIS, height / 2 - _FRACTION_AXIS)

    def _cell(self, depth: int) -> _Box:
        items: list[_Box] = []
        while self._peek() not in (None, "}", "&", "#"):
            token = self._next() or ""
            if token in ("^", "_"):
                items.append(self._scripts(items.pop() if items else _Box(0.0, 0.0, 0.0), token, depth + 1))
            elif token in ("over", "atop"):
                numerator = items.pop() if items else _row([])
                items.append(_fraction(numerator, self._atom(depth + 1)))
            else:
                items.append(self._dispatch(token, depth + 1))
        return _row(items)


def measure_equation(script: str, *, base_unit: int = 1100) -> EquationSize:
    """Return the box and baseline Hancom gives *script* at *base_unit* (1/100 pt).

    A script the measurer cannot follow gets a box from its visible length,
    one line high.
    """

    text = script.strip()
    box: _Box | None = None
    if len(text) <= MAX_SOURCE_LENGTH:
        measurer = _Measurer(_tokenize(text))
        try:
            box = measurer.sequence(0)
        except RecursionError:
            box = None
        if measurer.too_deep:
            box = None
    if box is None:
        visible = len(text.replace("{", "").replace("}", "").replace(" ", ""))
        box = _Box(max(1, visible) * _LOWER, _ASCENT, _DESCENT)
    height = max(box.height, _ASCENT + _DESCENT)
    return EquationSize(
        width=max(1, round((box.width + _BOX_PAD) * base_unit)),
        height=max(1, round(height * base_unit)),
        base_line=max(1, min(100, round(100 * box.ascent / height))),
    )
