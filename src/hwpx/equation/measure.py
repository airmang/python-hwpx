# SPDX-License-Identifier: Apache-2.0
"""Measure an EqEdit script the way Hancom sizes an equation box.

Hancom stores an equation's box as ``<hp:sz>`` and its baseline as
``baseLine`` (the share of the box height above the baseline, in percent).
A reader that lays the page out from the file uses the stored box, so a box
that is too wide leaves a gap after the equation and one that is too narrow
lets the next characters overlap it. Hancom itself was observed (on macOS)
to lay the equation out again and rewrite ``<hp:sz>`` when it saves the
document, whatever size was stored; the stored box still matters until then
and for every other reader. On Windows Hancom keeps the stored box and
``baseLine`` when it saves, and lays the page out with them.

This module lays the script out as boxes (width, ascent, descent) by its
structure -- characters by glyph, ``over`` and ``atop`` fractions, ``choose``/
``binom`` binomials (two rows in stretched parentheses), ``^``/``_`` scripts,
``sqrt``/``root``, decorations such as ``vec`` and ``dyad``, big operators
with their limits, ``lim`` with the limit below, matrices and ``pile``, and
``#`` line breaks. Keyword names that stand
for one symbol (Greek letters, ``lbrace``, ``prime``, ``DEG``, ...) count as
that symbol, not as their letters. ``rm`` sets the letters after it upright
until ``it`` or the end of the group, and a ``+`` or ``-`` with nothing before
it is a sign, with space only after it.

The widths are in em of the base size for the ``HYhwpEQ`` equation font
python-hwpx writes, at base size 1100. Since 2026-11 they are fitted to what
desktop Hangul 2024 on Windows needs, because that is the reader that lays the
line out with the stored box: each of 1,032 synthetic scripts was set alone in
a box far wider than itself, the page drawn, and the distance from the start
of the box to the right edge of the ink taken as the needed width (see
``tests/data/equation_windows_needed_widths.json``). The estimate is meant
never to fall below that, so it runs a little wide (about 7% at the median).
Windows needs a few percent more than the boxes macOS saved
(``tests/data/equation_hancom_boxes.json``), which the tables were fitted to
before; heights and baselines still come from those.

The width does not grow in step with ``baseUnit``: Hangul draws a 1100
equation 2% wider than a 1000 one and a 1150 one 13% wider. ``_SIZE_FACTORS``
holds the correction seen at fourteen sizes from 800 to 2000; between two
measured sizes the wider neighbour is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .eqedit import _ATOM_END, _FONT_SWITCHES, MAX_GROUP_DEPTH, MAX_SOURCE_LENGTH, _tokenize
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
_DIGIT = 0.48
_LOWER = 0.57  # italic lowercase letters not listed in _LETTER_WIDTHS
_UPPER = 0.81  # italic capitals not listed in _LETTER_WIDTHS
_UPRIGHT_LOWER = 0.54  # upright lowercase (function names, ``rm``) not listed in _UPRIGHT_WIDTHS
_UPRIGHT_UPPER = 0.74
_GREEK = 0.57  # lowercase Greek letters not listed in _GREEK_WIDTHS
_GREEK_UPPER = 0.78
_HANGUL = 0.96
_PUNCT = 0.18
_COMMA_SPACE = 0.17  # after a comma
_BRACKET = 0.35  # ( ) and a stretched delimiter not listed in _STRETCHED
_SQUARE_BRACKET = 0.26  # [ ]
_SAFETY = 0.05  # added once to every box: the widths were read off page images, a pixel or two coarse
_ALONE_TRIM = 0.2  # a relation or symbol with nothing on either side loses its spacing
_ALONE = {"circ": 0.58}  # the degree sign written as ^{circ}
_BRACE = 0.56  # { } drawn by lbrace / rbrace
_BAR = 0.45  # | drawn by LINE / vert
_DOUBLE_BAR = 1.3  # VERT: the double bar with a space on each side
_PRIME = 0.12  # ' and prime
_DEGREE = 0.47  # DEG
_OPERATOR_GLYPH = 1.03  # an operator or relation not listed in _OPERATOR_GLYPHS
_OPERATOR_SPACE = 0.18  # on each side of an operator or relation
_FUNCTION_PAD = 0.16
_LIMIT_WORD_PAD = 0.32  # after lim, max, min
_CALL_GAP = 0.1  # before a ( that follows an operand: f ( x )
_ACCENT_PAD = 0.06  # a bar, arrow or arc reaches a little past what it covers
_CAPITAL_BASE_SCRIPT = 0.12  # a script after an italic capital stands clear of its slant
_CAPITAL_SCRIPT = 0.06  # a script that starts with a capital
_AFTER_SCRIPT = 0.19  # between a script and what follows it on the line
_BEFORE_FUNCTION = 0.08  # between an operand and a function name: ab sin C
_EMPTY_BASE = 0.12  # the room of an empty base that only carries scripts: {} _{n}
_SPACE = 0.52  # ~
_THIN_SPACE = 0.15  # `
_OTHER = 0.36
_SYMBOL = 1.05
_SCRIPT_SCALE = 0.55
_SCRIPT_WIDTH = 0.66  # a script's glyphs are drawn this wide, relative to the base size
_SCRIPT_RAISE = 0.48
_SUBSCRIPT_DROP = -0.2
_FRACTION_PAD = 0.25
_FRACTION_GAP = 0.34
_FRACTION_AXIS = 0.37
_ATOP_GAP = 0.14  # atop stacks like over without the rule
_ROOT_SIGN = 1.21
_ROOT_INDEX_ROOM = 0.41  # a root's index sits in the sign's left notch up to this width
_ROOT_TOP = 0.14
_BIG_OPERATOR = 1.24
_BIG_OPERATOR_HEIGHT = 1.25
_INTEGRAL_SIGN = 0.88
_INTEGRAL_SPACE = 0.36
_INTEGRAL_HEIGHT = 2.27
_INTEGRAL_LIMIT_EXTRA = 0.2
_LIMIT_SCALE = 0.75
_LIMIT_WIDTH = 0.67  # a limit's glyphs are drawn this wide, relative to the base size
_LIMIT_GAP = 0.035
_ACCENT_TOP = 0.25
_COLUMN_GAP = 0.2
_ROW_GAP = 0.25
_LINE_GAP = 0.3
_ASCENT = 0.85
_DESCENT = 0.14

_MATRICES = frozenset(MATRIX_ENVIRONMENTS) | {"pile", "lpile", "rpile"}
_INTEGRALS = {"int": 1, "oint": 1, "dint": 2, "tint": 3}
#: Delimiters a matrix environment draws around its cells, as the opening delimiter and how many.
_MATRIX_DELIMITERS = {
    "pmatrix": ("(", 2), "bmatrix": ("[", 2), "Bmatrix": ("{", 2), "vmatrix": ("|", 2),
    "Vmatrix": ("|", 2), "dmatrix": ("|", 2), "cases": ("{", 1),
}
#: Italic Latin letters whose glyph is narrower or wider than the default for their case.
_LETTER_WIDTHS = {
    "a": 0.48, "b": 0.40, "c": 0.41, "d": 0.49, "e": 0.46, "f": 0.55, "g": 0.40, "h": 0.54, "i": 0.32,
    "j": 0.40, "k": 0.48, "l": 0.35, "m": 0.82, "n": 0.55, "o": 0.48, "p": 0.48, "q": 0.42, "r": 0.41,
    "s": 0.46, "t": 0.33, "u": 0.54, "v": 0.48, "w": 0.68, "x": 0.54, "y": 0.48, "z": 0.48, "A": 0.74,
    "B": 0.71, "C": 0.74, "D": 0.77, "E": 0.72, "F": 0.66, "G": 0.51, "H": 0.79, "I": 0.39, "J": 0.53,
    "K": 0.80, "L": 0.45, "M": 0.94, "N": 0.80, "O": 0.78, "P": 0.71, "Q": 0.78, "R": 0.70, "S": 0.58,
    "T": 0.74, "U": 0.79, "V": 0.80, "W": 1.02, "X": 0.79, "Y": 0.80, "Z": 0.65,
}
#: Upright lowercase letters whose glyph is narrower or wider than ``_UPRIGHT_LOWER``.
_UPRIGHT_WIDTHS = {
    "a": 0.48, "b": 0.52, "c": 0.46, "d": 0.53, "e": 0.52, "f": 0.34, "g": 0.54, "h": 0.53, "i": 0.26,
    "j": 0.25, "k": 0.54, "l": 0.26, "m": 0.81, "n": 0.53, "o": 0.52, "p": 0.52, "q": 0.53, "r": 0.39,
    "s": 0.46, "t": 0.33, "u": 0.53, "v": 0.54, "w": 0.75, "x": 0.54, "y": 0.54, "z": 0.40, "A": 0.74,
    "B": 0.61, "C": 0.61, "D": 0.67, "E": 0.61, "F": 0.60, "G": 0.68, "H": 0.73, "I": 0.33, "J": 0.40,
    "K": 0.73, "L": 0.60, "M": 0.88, "N": 0.74, "O": 0.67, "P": 0.60, "Q": 0.68, "R": 0.61, "S": 0.60,
    "T": 0.73, "U": 0.74, "V": 0.68, "W": 0.90, "X": 0.61, "Y": 0.61, "Z": 0.60,
}
#: Delimiters that ``LEFT``/``RIGHT`` and matrices stretch, by the opening or closing glyph.
_STRETCHED = {"(": 0.39, ")": 0.39, "[": 0.44, "]": 0.44, "|": 0.44, "{": 0.58, "}": 0.58}
_STRETCHED_NAMES = {"lbrace": "{", "rbrace": "}", "langle": "(", "rangle": ")", "lfloor": "[", "rfloor": "]",
                    "lceil": "[", "rceil": "]", "line": "|", "vert": "|"}
#: Operator and relation glyphs; each also gets ``_OPERATOR_SPACE`` on both sides.
_OPERATOR_GLYPHS = {"+": 0.65, "-": 0.69, "=": 0.71, "<": 0.8, ">": 0.8, "times": 0.61}
#: The room an operator, relation, symbol or punctuation mark takes between two operands, spacing
#: included: what desktop Hangul needed for ``a T b`` beyond ``ab``.
_TOKEN_ROOM = {
    "pm": 1.30, "mp": 1.30, "times": 1.04, "TIMES": 1.04, "cdot": 1.02, "div": 1.04,
    "ast": 1.24, "star": 1.24, "circ": 1.30, "bullet": 1.24, "oplus": 0.97, "otimes": 0.97,
    "leq": 1.39, "LEQ": 1.39, "geq": 1.39, "GEQ": 1.39, "neq": 1.24, "NEQ": 1.24,
    "equiv": 1.24, "approx": 1.24, "sim": 1.24, "simeq": 1.24, "cong": 1.24, "propto": 0.97,
    "prop": 1.85, "ll": 0.56, "gg": 0.97, "in": 0.49, "notin": 1.24, "subset": 1.39,
    "subseteq": 1.39, "supset": 1.39, "supseteq": 1.39, "cup": 0.97, "cap": 0.97, "emptyset": 0.97,
    "FORALL": 0.97, "exists": 0.97, "neg": 0.63, "land": 0.97, "lor": 0.97, "infty": 0.97,
    "inf": 0.97, "infinity": 0.97, "partial": 0.49, "nabla": 0.97, "angle": 0.97, "triangle": 0.62,
    "TRIANGLE": 0.62, "therefore": 0.97, "THEREFORE": 0.97, "because": 0.97, "cdots": 1.39, "ldots": 0.91,
    "vdots": 1.39, "ddots": 1.39, "dots": 0.49, "rightarrow": 0.97, "leftarrow": 0.97, "leftrightarrow": 0.97,
    "Rightarrow": 0.97, "Leftarrow": 0.97, "mapsto": 0.97, "LRARROW": 0.97, "uparrow": 0.97, "downarrow": 0.97,
    "UPARROW": 0.97, "EXARROW": 0.49, "BOT": 0.97, "bot": 0.97, "parallel": 0.49, "PARALLEL": 0.49,
    "+-": 1.04, "-+": 1.24, "<=": 1.39, ">=": 1.39, "!=": 1.24, "==": 1.24,
    "->": 0.97, "<-": 0.97, "<->": 0.97, "=>": 2.00, "~=": 1.67, "~|~": 1.21,
    "+": 1.04, "-": 1.04, "=": 1.19, "<": 1.26, ">": 1.26, ":": 0.71,
    ",": 0.36, ";": 0.28, "!": 0.28, "/": 0.49, "|": 0.21, "LINE": 0.21, "vert": 0.21,
    "VERT": 0.49,
}
#: Signs that, with nothing before them, mark the sign of what follows.
_SIGNS = frozenset({"+", "-", "+-", "-+", "pm", "mp"})
#: Greek letters whose glyph is narrower or wider than the default for their case.
_GREEK_WIDTHS = {
    "alpha": 0.61, "beta": 0.55, "gamma": 0.49, "delta": 0.42, "epsilon": 0.39, "varepsilon": 0.41,
    "zeta": 0.42, "eta": 0.48, "theta": 0.47, "vartheta": 0.55, "iota": 0.33, "kappa": 0.54,
    "lambda": 0.54, "mu": 0.55, "nu": 0.49, "xi": 0.42, "omicron": 0.48, "pi": 0.55,
    "varpi": 0.82, "rho": 0.48, "varrho": 0.27, "sigma": 0.55, "varsigma": 0.36, "tau": 0.43,
    "upsilon": 0.54, "phi": 0.55, "varphi": 0.61, "chi": 0.60, "psi": 0.61, "omega": 0.60,
    "GAMMA": 0.63, "DELTA": 0.81, "THETA": 0.74, "LAMBDA": 0.68, "XI": 0.70, "PI": 0.83,
    "SIGMA": 0.76, "UPSILON": 0.60, "PHI": 0.62, "PSI": 0.63, "OMEGA": 0.75,
}
#: Keyword names (any case) drawn as one glyph of the given width.
_KEYWORD_GLYPHS = {
    "lbrace": _BRACE, "rbrace": _BRACE, "langle": _BRACKET, "rangle": _BRACKET, "lfloor": _BRACKET,
    "rfloor": _BRACKET, "lceil": _BRACKET, "rceil": _BRACKET, "prime": _PRIME, "deg": _DEGREE,
}
#: Keyword names whose case picks the glyph: ``LINE``/``vert`` draw |, ``VERT`` draws a double bar.
_CASED_KEYWORD_GLYPHS = {"LINE": _BAR, "vert": _BAR, "VERT": _DOUBLE_BAR}
_LIMIT_WORDS = frozenset({"lim", "limsup", "liminf", "max", "min"})
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
    "inf", "infinity", "angle", "triangle", "partial", "nabla", "hbar", "emptyset",
    "aleph", "forall", "exists", "neg", "cdots", "ldots", "vdots", "ddots", "dagger", "box", "diamond",
    "centigrade",
})


#: Desktop Hangul does not widen an equation in step with its base size: the width climbs in stairs
#: (a 1100 equation is 2% wider than a 1000 one, a 1150 one 13%). The glyph tables above are for 1100;
#: this is the widest ``needed width / (table width scaled to the size)`` seen at each measured size.
_SIZE_FACTORS = (
    (800, 1.05), (900, 1.06), (950, 1.03), (1000, 1.08), (1050, 1.05), (1100, 1.0), (1150, 1.09),
    (1200, 1.06), (1250, 1.04), (1300, 1.09), (1400, 1.04), (1500, 1.09), (1600, 1.11), (2000, 1.08),
)
_SIZE_FACTOR_OUTSIDE = 1.11


def _size_factor(base_unit: int) -> float:
    """How much wider than the 1100 tables say an equation at *base_unit* has to be."""
    if base_unit < _SIZE_FACTORS[0][0] or base_unit > _SIZE_FACTORS[-1][0]:
        return _SIZE_FACTOR_OUTSIDE
    for (low, low_factor), (high, high_factor) in zip(_SIZE_FACTORS, _SIZE_FACTORS[1:]):
        if low <= base_unit <= high:
            if base_unit in (low, high):
                return low_factor if base_unit == low else high_factor
            # Between two measured sizes the stairs are unknown: take the wider neighbour.
            return max(low_factor, high_factor)
    return _SIZE_FACTOR_OUTSIDE


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


def _fraction(numerator: _Box, denominator: _Box, gap: float = _FRACTION_GAP) -> _Box:
    return _Box(
        max(numerator.width, denominator.width) + 2 * _FRACTION_PAD,
        numerator.height + gap / 2 + _FRACTION_AXIS,
        denominator.height + gap / 2 - _FRACTION_AXIS,
    )


def _grid(rows: list[list[_Box]]) -> _Box:
    """Rows of cells in columns, centred on the fraction axis."""
    if not rows:
        return _row([])
    columns = max(len(row) for row in rows)
    widths = [max((row[c].width for row in rows if c < len(row)), default=0.0) for c in range(columns)]
    height = sum(max(cell.height for cell in row) for row in rows) + _ROW_GAP * (len(rows) - 1)
    return _Box(sum(widths) + _COLUMN_GAP * (columns - 1), height / 2 + _FRACTION_AXIS, height / 2 - _FRACTION_AXIS)


def _binomial(top: _Box, bottom: _Box) -> _Box:
    """``{n} choose {r}`` and ``binom {n} {r}``: Hancom draws them as ``pmatrix {n # r}``."""
    box = _grid([[top], [bottom]])
    return _Box(box.width + 2 * _STRETCHED["("], box.ascent, box.descent)


def _script(box: _Box) -> _Box:
    """*box* set as a script or an integral's limit.

    Hancom draws a script's glyphs ``_SCRIPT_WIDTH`` as wide as at full size;
    the height keeps ``_SCRIPT_SCALE``, which the raise and drop are set for.
    """
    return _Box(box.width * _SCRIPT_WIDTH, box.ascent * _SCRIPT_SCALE, box.descent * _SCRIPT_SCALE)


def _limit(box: _Box) -> _Box:
    """*box* set as the limit under ``lim`` or on a big operator."""
    return _Box(box.width * _LIMIT_WIDTH, box.ascent * _LIMIT_SCALE, box.descent * _LIMIT_SCALE)


def _char_width(ch: str, upright: bool = False) -> float:
    if "가" <= ch <= "힣":
        return _HANGUL
    if ch.isdigit():
        return _DIGIT
    if ch == " ":
        return _SPACE
    if not ch.isalnum():
        return _TOKEN_ROOM.get(ch, 0.3) if ch in ",.;:!'/|" else 0.6
    if upright:
        return _UPRIGHT_WIDTHS.get(ch, _UPRIGHT_UPPER if ch.isupper() else _UPRIGHT_LOWER)
    return _LETTER_WIDTHS.get(ch, _UPPER if ch.isupper() else _LOWER)


def _upright_word(word: str) -> float:
    return sum(_char_width(ch, upright=True) for ch in word)


def _is_operator(token: str) -> bool:
    return token in OPERATORS or token in _RELATIONS or token.lower() in _SYMBOL_RELATIONS


def _token_width(token: str, upright: bool = False, sign: bool = False, alone: bool = False) -> float:
    lower = token.lower()
    if token.startswith('"'):
        return sum(_char_width(ch, upright) for ch in token.strip('"'))
    if alone and token in _ALONE:
        return _ALONE[token]
    if alone and token in _TOKEN_ROOM and _is_operator(token) and token not in _SIGNS:
        return max(_TOKEN_ROOM[token] - _ALONE_TRIM, 0.3)
    if token in _TOKEN_ROOM:
        # A sign with nothing before it to operate on keeps only the space after it.
        return _TOKEN_ROOM[token] - (_OPERATOR_SPACE if sign and token in _SIGNS else 0.0)
    if token in GREEK:
        return _GREEK_WIDTHS.get(token, _GREEK_UPPER if token.isupper() else _GREEK)
    if token in _CASED_KEYWORD_GLYPHS:
        return _CASED_KEYWORD_GLYPHS[token]
    if lower in _KEYWORD_GLYPHS:
        return _KEYWORD_GLYPHS[lower]
    if _is_operator(token):
        glyph = _OPERATOR_GLYPHS.get(token, _OPERATOR_GLYPH)
        # A sign with nothing before it to operate on keeps only the space after it.
        return glyph + (1 if sign else 2) * _OPERATOR_SPACE
    if lower in _SYMBOL_ORDINARY:
        return _SYMBOL
    if token.replace(".", "").isdigit():
        return sum(_DIGIT if ch.isdigit() else _PUNCT for ch in token)
    if token.isalpha():
        return sum(_char_width(ch, upright) for ch in token)
    if token in ("(", ")"):
        return _BRACKET
    if token in ("[", "]"):
        return _SQUARE_BRACKET
    if token == "|":
        return _BAR
    if token == "'":
        return _PRIME
    if token == ",":
        return _PUNCT + _COMMA_SPACE
    if token in (".", ";", ":", "!"):
        return _PUNCT
    return _OTHER


def _follows_operand(token: str, operand: bool) -> bool:
    """Whether a sign after *token* has an operand before it (*operand*: before *token*)."""
    if token in _FONT_SWITCHES:
        return operand
    return not (_is_operator(token) or token in ("(", "[", ","))


def _stretched(token: str | None) -> float:
    """The width of a delimiter that ``LEFT``/``RIGHT`` stretch."""
    if token is None:
        return 0.0
    name = token if token == "VERT" else token.lower()
    return _STRETCHED.get(_STRETCHED_NAMES.get(name, token), _BRACKET)


class _Measurer:
    """Recursive descent over EqEdit tokens, mirroring the LaTeX converter's grammar."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0
        self.too_deep = False
        self._upright = False  # after ``rm``, until ``it`` or the end of the group
        self._last = ""  # the token before the one being read, for spacing that depends on it
        self._alone = False  # the token being read has nothing before it and nothing after it
        self._empty_base = False

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
        operand = False  # whether a sign here has something before it to operate on
        while True:
            token = self._peek()
            if token is None or token == stop or (stop == "RIGHT" and token in ("RIGHT", "right")):
                break
            self._next()
            if token == "#":
                lines.append(_row(items))
                items, operand = [], False
            elif token == "&":
                operand = False
            elif not self._infix(token, items, depth):
                if token == "(" and operand:
                    items.append(_Box(_CALL_GAP, 0.0, 0.0))
                elif operand and token in FUNCTIONS:
                    items.append(_Box(_BEFORE_FUNCTION, 0.0, 0.0))
                self._alone = not items and self._peek() in (None, "}", stop)
                items.append(self._dispatch(token, depth, sign=not operand and token in _SIGNS))
                self._alone = False
                operand = _follows_operand(token, operand)
            if token not in ("^", "_"):
                self._last = token
        if not lines:
            return _row(items)
        return _stack([*lines, _row(items)], _LINE_GAP)

    def _infix(self, token: str, items: list[_Box], depth: int) -> bool:
        """Apply a script or a two-part stack to the item before it; False if *token* is neither."""
        if token in ("^", "_"):
            items.append(self._scripts(items.pop() if items else _Box(0.0, 0.0, 0.0), token, depth))
        elif token == "over" or token.lower() == "atop":
            numerator = items.pop() if items else _row([])
            items.append(_fraction(numerator, self._atom(depth), _FRACTION_GAP if token == "over" else _ATOP_GAP))
        elif token.lower() == "choose":
            top = items.pop() if items else _row([])
            items.append(_binomial(top, self._atom(depth)))
        else:
            return False
        return True

    def _atom(self, depth: int) -> _Box:
        # A font switch is not the atom: ``x^rmA`` scripts the ``A`` as the converter
        # reads it, so the switch applies and the next token is measured instead.
        token = self._next()
        while token in _FONT_SWITCHES:
            self._symbol(token)
            if self._peek() is None or self._peek() in _ATOM_END:
                return _Box(0.0, 0.0, 0.0)
            token = self._next()
        return _Box(0.0, 0.0, 0.0) if token is None else self._dispatch(token, depth)

    def _group(self, depth: int) -> _Box:
        if depth + 1 > MAX_GROUP_DEPTH:
            self.too_deep = True
            return _Box(0.0, 0.0, 0.0)
        upright = self._upright
        inner = self.sequence(depth + 1, stop="}")
        self._upright = upright
        if self._peek() == "}":
            self._next()
        return inner

    def _script_extra(self) -> float:
        """Room a script needs beyond its glyphs, from the base before it and its own first glyph."""
        extra = 0.0
        last = self._last.strip('"')
        if last[-1:].isupper() and last.isalpha() and not self._upright:
            extra += _CAPITAL_BASE_SCRIPT
        elif self._last in ("}", "") and self._empty_base:
            extra += _EMPTY_BASE
        first = self._peek()
        if first == "{" and self._pos + 1 < len(self._tokens):
            first = self._tokens[self._pos + 1]
        if first and first[:1].isupper() and first.isalpha() and first not in GREEK:
            extra += _CAPITAL_SCRIPT
        return extra

    def _scripts(self, base: _Box, operator: str, depth: int) -> _Box:
        self._empty_base = base.width == 0.0
        extra = self._script_extra()
        scripts = {operator: _script(self._atom(depth))}
        following = self._peek()
        if following in ("^", "_") and following != operator:
            self._next()
            scripts[following] = _script(self._atom(depth))
        upper, lower = scripts.get("^"), scripts.get("_")
        if self._peek() not in (None, "}", "&", "#", "RIGHT", "right", ")", "]", "over", "atop", "choose"):
            extra += _AFTER_SCRIPT
        width = base.width + extra + max(upper.width if upper else 0.0, lower.width if lower else 0.0)
        # Scripts sit against the base's own top and bottom, so a base taller than a
        # line (a LEFT/RIGHT group, a fraction) carries its scripts out with it.
        top, bottom = max(base.ascent - _ASCENT, 0.0), max(base.descent - _DESCENT, 0.0)
        ascent = max(base.ascent, top + _SCRIPT_RAISE + upper.height) if upper else base.ascent
        descent = max(base.descent, bottom + _SUBSCRIPT_DROP + lower.height) if lower else base.descent
        return _Box(width, ascent, descent)

    def _dispatch(self, token: str, depth: int, sign: bool = False) -> _Box:
        if token == "{":
            return self._group(depth)
        if token in ("sqrt", "root"):
            return self._root(token, depth)
        if token in ACCENTS:
            inner = self._atom(depth)
            return _Box(inner.width + _ACCENT_PAD, inner.ascent + _ACCENT_TOP, inner.descent)
        if token.lower() == "binom":
            top = self._atom(depth)
            return _binomial(top, self._atom(depth))
        if token in _MATRICES:
            box = self._matrix(depth)
            delimiter, count = _MATRIX_DELIMITERS.get(token, ("", 0))
            return _Box(box.width + count * _STRETCHED.get(delimiter, _BRACKET), box.ascent, box.descent)
        if token in ("LEFT", "left"):
            return self._delimited(depth)
        if token in ("RIGHT", "right"):
            return _Box(_stretched(self._next()), _ASCENT, _DESCENT)
        if token in _INTEGRALS:
            return self._integral(token, depth)
        if token.lower() in _LIMIT_WORDS and self._peek() in ("_", "from"):
            return self._limit(token, depth)
        if token in BIG_OPERATORS and token.lower() not in _LIMIT_WORDS and token not in ("iint", "iiint"):
            return self._big_operator(depth)
        return self._symbol(token, sign)

    def _symbol(self, token: str, sign: bool = False) -> _Box:
        if token in FUNCTIONS or token.lower() in _LIMIT_WORDS:
            pad = _LIMIT_WORD_PAD if token.lower() in _LIMIT_WORDS else _FUNCTION_PAD
            return _Box(_upright_word(token) + pad, _ASCENT, _DESCENT)
        if token in _FONT_SWITCHES or token in ("of", "&"):
            if token.lower() in ("rm", "it"):
                self._upright = token.lower() == "rm"
            return _Box(0.0, 0.0, 0.0)
        if token == "~":
            return _Box(_SPACE, 0.0, 0.0)
        if token == "`":
            return _Box(_THIN_SPACE, 0.0, 0.0)
        alone = self._alone
        self._alone = False
        return _Box(_token_width(token, self._upright, sign, alone), _ASCENT, _DESCENT)

    def _root(self, token: str, depth: int) -> _Box:
        index = _Box(0.0, 0.0, 0.0)
        if token == "root":
            index = self._atom(depth)
            if self._peek() == "of":
                self._next()
        inner = self._atom(depth)
        overhang = max(0.0, _script(index).width - _ROOT_INDEX_ROOM)
        return _Box(inner.width + _ROOT_SIGN + overhang, inner.ascent + _ROOT_TOP, inner.descent)

    def _delimited(self, depth: int) -> _Box:
        """``LEFT``/``RIGHT`` delimiters grow with the body but add no height of their own."""
        opening = _stretched(self._next())
        body = self.sequence(depth, stop="RIGHT")
        closing = 0.0
        if self._peek() in ("RIGHT", "right"):
            self._next()
            closing = _stretched(self._next())
        return _Box(body.width + opening + closing, body.ascent, body.descent)

    def _integral(self, token: str, depth: int) -> _Box:
        """Hancom draws an integral tall, with its limits at the sign's corners."""
        width = _INTEGRAL_SIGN * _INTEGRALS[token]
        ascent, descent = _INTEGRAL_HEIGHT * 0.6, _INTEGRAL_HEIGHT * 0.4
        limit_width = 0.0
        while self._peek() in ("_", "^", "from", "to"):
            upper = self._next() in ("^", "to")
            limit = _script(self._atom(depth))
            limit_width = max(limit_width, limit.width)
            if upper:
                ascent += _INTEGRAL_LIMIT_EXTRA
            else:
                descent += _INTEGRAL_LIMIT_EXTRA
        return _Box(width + limit_width + _INTEGRAL_SPACE, ascent, descent)

    def _limit(self, token: str, depth: int) -> _Box:
        self._next()  # _ or from
        limit = _limit(self._atom(depth))
        width = _upright_word(token) + _LIMIT_WORD_PAD
        return _Box(max(width, limit.width), _ASCENT, _DESCENT + limit.height + _LIMIT_GAP)

    def _big_operator(self, depth: int) -> _Box:
        box = _Box(_BIG_OPERATOR, _BIG_OPERATOR_HEIGHT * 0.6, _BIG_OPERATOR_HEIGHT * 0.4)
        limits: list[_Box] = []
        while self._peek() in ("_", "^", "from", "to"):
            self._next()
            limits.append(_limit(self._atom(depth)))
        if not limits:
            return box
        extra = sum(limit.height for limit in limits) / 2
        return _Box(max([box.width] + [limit.width for limit in limits]), box.ascent + extra, box.descent + extra)

    def _matrix(self, depth: int) -> _Box:
        if self._peek() != "{":
            return _Box(_LOWER * 6, _ASCENT, _DESCENT)
        self._next()
        rows: list[list[_Box]] = [[]]
        upright = self._upright
        while self._peek() not in (None, "}"):
            rows[-1].append(self._cell(depth))
            if self._peek() == "#":
                self._next()
                rows.append([])
            elif self._peek() == "&":
                self._next()
        if self._peek() == "}":
            self._next()
        self._upright = upright
        return _grid([row for row in rows if row])

    def _cell(self, depth: int) -> _Box:
        items: list[_Box] = []
        operand = False
        while self._peek() not in (None, "}", "&", "#"):
            token = self._next() or ""
            if not self._infix(token, items, depth + 1):
                if token == "(" and operand:
                    items.append(_Box(_CALL_GAP, 0.0, 0.0))
                elif operand and token in FUNCTIONS:
                    items.append(_Box(_BEFORE_FUNCTION, 0.0, 0.0))
                items.append(self._dispatch(token, depth + 1, sign=not operand and token in _SIGNS))
                operand = _follows_operand(token, operand)
            if token not in ("^", "_"):
                self._last = token
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
        width=max(1, round((box.width + _SAFETY) * base_unit * _size_factor(base_unit))),
        height=max(1, round(height * base_unit)),
        base_line=max(1, min(100, round(100 * box.ascent / height))),
    )
