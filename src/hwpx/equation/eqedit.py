# SPDX-License-Identifier: Apache-2.0
"""Reader-direction EqEdit → LaTeX converter (clean-room).

The converter is a small tokenizer plus a recursive-descent parser.  It targets
the token set proven against the Hancom render oracle in the P0 spike
(``over`` fractions, ``sqrt``/``root of``, ``_``/``^`` scripts, ``+-`` → ``\\pm``,
Greek letters, large operators such as ``int``/``sum`` with bounds, ``times``,
``leq``/``geq``, and brace grouping) and is structured so coverage can grow by
extending the token maps in :mod:`hwpx.equation.tokens`.

Design notes (matches Hancom EqEdit grouping semantics):

* Tokens are whitespace separated; ``{`` ``}`` ``^`` ``_`` ``&`` ``#`` are also
  token boundaries even without surrounding whitespace, so ``x^2`` and ``b^2``
  tokenise as ``x ^ 2`` / ``b ^ 2``.
* ``over`` is an infix fraction: it binds the *immediately preceding atom* as the
  numerator and the *next atom* as the denominator.  Callers brace multi-token
  operands (``{...} over {...}``) exactly as EqEdit requires.
* ``^`` / ``_`` are postfix scripts binding the preceding atom.

Untrusted input is bounded by :data:`MAX_SOURCE_LENGTH` and
:data:`MAX_GROUP_DEPTH`; exceeding either raises :class:`EquationConversionError`
so the caller can fail closed to the original script text.
"""

from __future__ import annotations

from typing import Any

from .tokens import (
    ACCENTS,
    BIG_OPERATORS,
    DELIMITERS,
    FUNCTIONS,
    GREEK,
    MATRIX_ENVIRONMENTS,
    OPERATORS,
    SYMBOL_OPERATORS,
)

MAX_SOURCE_LENGTH = 10_000
MAX_GROUP_DEPTH = 64

# Characters that always terminate a token even when not whitespace separated.
_BREAK_CHARS = frozenset("{}^_&#()[]|")
# Longest symbolic operators first so "+-" wins over "+".
_SYMBOL_OPS_SORTED = sorted(SYMBOL_OPERATORS, key=len, reverse=True)


class EquationConversionError(ValueError):
    """Raised when an EqEdit script cannot be converted to LaTeX."""


def _lex_quoted_literal(source: str, i: int, tokens: list[str]) -> int:
    """Consume a quoted EqEdit text run; unterminated quotes swallow the rest."""

    j = source.find('"', i + 1)
    if j == -1:
        tokens.append(source[i:])
        return len(source)
    tokens.append(source[i : j + 1])
    return j + 1


def _lex_symbol_operator(source: str, i: int, tokens: list[str]) -> int | None:
    for op in _SYMBOL_OPS_SORTED:
        if source.startswith(op, i):
            tokens.append(op)
            return i + len(op)
    return None


def _lex_run(source: str, i: int, tokens: list[str], predicate: Any) -> int:
    j = i
    while j < len(source) and predicate(source[j]):
        j += 1
    tokens.append(source[i:j])
    return j


def _tokenize(source: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif ch == '"':
            i = _lex_quoted_literal(source, i, tokens)
        elif (advanced := _lex_symbol_operator(source, i, tokens)) is not None:
            i = advanced
        elif ch in _BREAK_CHARS:
            tokens.append(ch)
            i += 1
        elif ch.isdigit() or ch == ".":
            i = _lex_run(source, i, tokens, lambda c: c.isdigit() or c == ".")
        elif ch.isalpha():
            i = _lex_run(source, i, tokens, str.isalpha)
        else:
            # Any other single character (operators like + - = < > , ! ; :).
            tokens.append(ch)
            i += 1
    return tokens


def _is_wrapped_group(latex: str) -> bool:
    """True when a single pair of braces wraps the whole span (``{...}``)."""

    if len(latex) < 2 or latex[0] != "{" or latex[-1] != "}":
        return False
    depth = 0
    for index, char in enumerate(latex):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and index != len(latex) - 1:
                return False
    return depth == 0


def _strip_braces(latex: str) -> str:
    """Remove one layer of grouping braces produced by :func:`_group`."""

    inner = latex.strip()
    if _is_wrapped_group(inner):
        return inner[1:-1]
    return inner


def _combine_script(base: str, operator: str, script: str) -> str:
    op = "^" if operator == "^" else "_"
    body = script.strip()
    # Preserve the source's grouping so a braced EqEdit script ({...}) keeps its
    # LaTeX braces while a bare single-character script stays bare -- this mirrors
    # what a hand-written LaTeX author (and the P0 ground truth) produces.
    if not _is_wrapped_group(body) and len(body) != 1:
        body = "{" + body + "}"
    # Guard the LaTeX "double superscript/subscript" error when the same script
    # kind is already present on the base.
    if base and (op + "{") in base:
        base = "{" + base + "}"
    return f"{base}{op}{body}"


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    # -- token helpers ------------------------------------------------------
    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str | None:
        token = self._peek()
        if token is not None:
            self._pos += 1
        return token

    # -- grammar ------------------------------------------------------------
    def parse(self) -> str:
        return self._sequence(depth=0)

    def _sequence(self, *, depth: int, stop: str | None = None) -> str:
        nodes: list[str] = []
        while True:
            token = self._peek()
            if token is None or token == stop:
                break
            if token in ("^", "_"):
                self._next()
                base = nodes.pop() if nodes else ""
                nodes.append(_combine_script(base, token, self._atom(depth)))
                continue
            if token == "over" or token == "atop":
                self._next()
                numerator = _strip_braces(nodes.pop() if nodes else "")
                denominator = _strip_braces(self._atom(depth))
                if token == "over":
                    nodes.append(f"\\frac{{{numerator}}}{{{denominator}}}")
                else:
                    nodes.append(f"{{{numerator} \\atop {denominator}}}")
                continue
            nodes.append(self._atom(depth))
        return " ".join(part for part in nodes if part != "")

    def _atom(self, depth: int) -> str:
        token = self._next()
        if token is None:
            return ""
        if token == "{":
            return "{" + self._group(depth) + "}"
        if token == "sqrt":
            return f"\\sqrt{{{_strip_braces(self._atom(depth))}}}"
        if token == "root":
            index = _strip_braces(self._atom(depth))
            if self._peek() == "of":
                self._next()
            radicand = _strip_braces(self._atom(depth))
            return f"\\sqrt[{index}]{{{radicand}}}"
        if token in ACCENTS:
            return f"{ACCENTS[token]}{{{_strip_braces(self._atom(depth))}}}"
        if token in MATRIX_ENVIRONMENTS:
            return self._matrix(MATRIX_ENVIRONMENTS[token], depth)
        if token in ("LEFT", "left"):
            return self._left_right(depth)
        if token in ("RIGHT", "right"):
            # A bare RIGHT without a matching LEFT: emit the delimiter literally.
            delim = self._next()
            return DELIMITERS.get(delim or "", delim or "")
        return self._map_token(token)

    def _group(self, depth: int) -> str:
        if depth + 1 > MAX_GROUP_DEPTH:
            raise EquationConversionError("equation nesting depth exceeded")
        inner = self._sequence(depth=depth + 1, stop="}")
        if self._peek() == "}":
            self._next()
        return inner

    def _left_right(self, depth: int) -> str:
        open_delim = self._next() or "."
        left = DELIMITERS.get(open_delim, open_delim)
        body = self._sequence(depth=depth, stop="RIGHT")
        # ``right`` may be spelled either case; the sequence stops on "RIGHT".
        if self._peek() != "RIGHT":
            # Try lowercase form by scanning ahead is out of scope; emit as-is.
            return f"\\left{left} {body} \\right."
        self._next()  # consume RIGHT
        close_delim = self._next() or "."
        right = DELIMITERS.get(close_delim, close_delim)
        return f"\\left{left} {body} \\right{right}"

    def _matrix(self, environment: str, depth: int) -> str:
        if self._peek() != "{":
            # Malformed: treat the environment name as a literal identifier.
            return environment
        self._next()  # consume "{"
        rows: list[list[str]] = [[]]
        current: list[str] = []

        def flush_cell() -> None:
            rows[-1].append(" ".join(part for part in current if part != ""))
            current.clear()

        while True:
            token = self._peek()
            if token is None or token == "}":
                self._next() if token == "}" else None
                break
            if token == "&":
                self._next()
                flush_cell()
                continue
            if token == "#":
                self._next()
                flush_cell()
                rows.append([])
                continue
            if token in ("^", "_"):
                self._next()
                base = current.pop() if current else ""
                current.append(_combine_script(base, token, self._atom(depth)))
                continue
            if token == "over":
                self._next()
                numerator = _strip_braces(current.pop() if current else "")
                denominator = _strip_braces(self._atom(depth))
                current.append(f"\\frac{{{numerator}}}{{{denominator}}}")
                continue
            current.append(self._atom(depth))
        flush_cell()
        body = " \\\\ ".join(" & ".join(cell for cell in row) for row in rows if row)
        return f"\\begin{{{environment}}} {body} \\end{{{environment}}}"

    def _map_token(self, token: str) -> str:
        if token in SYMBOL_OPERATORS:
            return SYMBOL_OPERATORS[token]
        if token in GREEK:
            return GREEK[token]
        if token in BIG_OPERATORS:
            return BIG_OPERATORS[token]
        if token in OPERATORS:
            return OPERATORS[token]
        if token in FUNCTIONS:
            return FUNCTIONS[token]
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            return f"\\text{{{token[1:-1]}}}"
        if token == "#":
            return r"\\"
        if token in ("%", "$", "&", "_"):
            return "\\" + token
        return token


def eqedit_to_latex(script: str) -> str:
    """Convert an EqEdit ``<hp:script>`` string to a LaTeX fragment.

    Raises:
        EquationConversionError: if the source exceeds the size/depth guards.
    """

    if len(script) > MAX_SOURCE_LENGTH:
        raise EquationConversionError("equation script exceeds size limit")
    tokens = _tokenize(script)
    latex = _Parser(tokens).parse()
    return latex.strip()


__all__ = [
    "MAX_GROUP_DEPTH",
    "MAX_SOURCE_LENGTH",
    "EquationConversionError",
    "eqedit_to_latex",
]
