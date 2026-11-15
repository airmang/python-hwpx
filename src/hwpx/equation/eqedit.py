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
* Font switches follow what Hancom draws (render probe, issue #582): ``rm``
  sets the Latin letters after it upright -- past closing braces, scripts,
  fractions, roots and ``LEFT``/``RIGHT`` -- until ``it``; Greek letters stay as
  they are.  ``bold`` makes only the next atom bold (italic bold, or upright
  bold after ``rm``), and a ``rm``/``it`` right after it uses it up.  Letter runs
  read as ``\\mathrm``/``\\mathbf``/``\\boldsymbol`` so a switch never comes
  back as a word that re-authoring would draw as letters. A switch at the start
  of a word also applies without a space (``rmA``), as observed in Hancom.

Untrusted input is bounded by :data:`MAX_SOURCE_LENGTH` and
:data:`MAX_GROUP_DEPTH`; exceeding either raises :class:`EquationConversionError`
so the caller can fail closed to the original script text.
"""

from __future__ import annotations

from typing import Any

from ..errors import HwpxError

from .tokens import (
    ACCENTS,
    BIG_OPERATORS,
    CASE_SENSITIVE,
    DELIMITERS,
    FUNCTIONS,
    GREEK,
    LEFT_SCRIPTS,
    MATRIX_ENVIRONMENTS,
    OPERATORS,
    PILES,
    READ_MARKS,
    READ_SYMBOLS,
    STRUCTURAL,
    SYMBOL_OPERATORS,
)

MAX_SOURCE_LENGTH = 10_000
MAX_GROUP_DEPTH = 64

# Words EqEdit reads as symbols, structure or font switches. The writer quotes a bare identifier that collides
# with one (``T_{int}`` → ``T _{"int"}``, ``e^{it}`` → ``e ^{"it"}``: a lone ``it`` in a superscript switches to
# italic and draws nothing); the reader turns such a quoted word back into plain letters.
_FONT_PREFIXES = ("bold", "Bold", "BOLD", "rm", "Rm", "RM", "it", "It", "IT")
_FONT_SWITCHES = frozenset(_FONT_PREFIXES)
# Tokens that end the current atom: a font switch right before one switches and draws nothing.
_ATOM_END = frozenset({"}", "&", "#", "RIGHT", "^", "_", "over", "atop", "choose"})
_RESERVED_WORDS = (
    frozenset(GREEK)
    | frozenset(OPERATORS)
    | frozenset(FUNCTIONS)
    | frozenset(BIG_OPERATORS)
    | frozenset(ACCENTS)
    | frozenset(MATRIX_ENVIRONMENTS)
    | STRUCTURAL
    | _FONT_SWITCHES
)

# Every symbol or structure name the reader knows, as spelled, and the lower-case form of those whose
# case Hancom ignores (``ANGLE``, ``CDOT``, ``In``).
_KEYWORDS = (
    _RESERVED_WORDS - _FONT_SWITCHES
    | frozenset(READ_SYMBOLS)
    | frozenset(READ_MARKS)
    | PILES
    | frozenset(LEFT_SCRIPTS)
    | frozenset(name for name in DELIMITERS if name.isalpha())
    | {"from"}
)
_CASELESS = frozenset(
    name.lower() for name in _KEYWORDS if name.lower() not in CASE_SENSITIVE and name.lower() in _KEYWORDS
)
# Hancom reads a keyword name at the front of a letter run as the keyword (``sinx`` is ``sin x``,
# ``1 overa`` is ``1 over a``, ``F _{net}`` draws F≠t), then reads the rest the same way. Desktop Hangul
# 2024 drew ``E _{total}`` as letters, and ``a ll b``/``a gg b`` as letters, so these do not split a word.
_NO_PREFIX = frozenset({"to", "from", "of", "ll", "gg"})
_LONGEST_KEYWORD = max(len(name) for name in _KEYWORDS)
# Lower-case names a written identifier must not start with (any case): the writer quotes such a word.
_QUOTE_PREFIXES = tuple(
    sorted({name.lower() for name in _KEYWORDS if len(name) >= 2} - _NO_PREFIX, key=len, reverse=True)
)


def _keyword(word: str) -> str | None:
    """The name the reader knows *word* as (``ANGLE`` → ``angle``), or ``None`` for an ordinary word."""

    if word in _KEYWORDS:
        return word
    lower = word.lower()
    if lower in _CASELESS and (word.isupper() or word.istitle()):
        return lower
    return None


def _split_word(run: str) -> list[str]:
    """An ASCII letter run as Hancom reads it: keyword names at its front split off, the rest read again."""

    if not run.isascii():
        return [run]
    parts: list[str] = []
    while run:
        name = _keyword(run)
        if name is not None:
            parts.append(name)
            break
        for size in range(min(len(run) - 1, _LONGEST_KEYWORD), 1, -1):
            name = _keyword(run[:size])
            if name is not None and name not in _NO_PREFIX:
                break
        else:
            parts.append(run)
            break
        parts.append(name)
        run = run[size:]
    return parts

# The LaTeX of the operators that take limits (``sum from {i=1} to n``).
_LIMIT_COMMANDS = tuple(BIG_OPERATORS.values())
# Characters LaTeX reads as commands inside ``\text{...}``, and how to write them there.
_TEXT_ESCAPES = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "$": r"\$", "&": r"\&", "#": r"\#",
    "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
}


def _escape_text(text: str) -> str:
    """Quoted EqEdit text as the body of ``\\text{...}``: ``50%`` → ``50\\%``."""
    return "".join(_TEXT_ESCAPES.get(char, char) for char in text)


# Characters that always terminate a token even when not whitespace separated.
_BREAK_CHARS = frozenset("{}^_&#()[]|")
# Longest symbolic operators first so "+-" wins over "+".
_SYMBOL_OPS_SORTED = sorted(SYMBOL_OPERATORS, key=len, reverse=True)


class EquationConversionError(HwpxError, ValueError):
    """Raised when an EqEdit script cannot be converted to LaTeX."""

    default_code = "equation-conversion"


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


def _needs_literal_quotes(word: str) -> bool:
    """Whether Hancom would read *word* as something other than its letters: a keyword or font switch, or
    a word that starts with one in any case (``net`` starts with ``ne``, ``In`` is ``in``)."""
    if not word.isalpha():
        return False
    if word in _RESERVED_WORDS or word.startswith(_FONT_PREFIXES):
        return True
    return word.isascii() and word.lower().startswith(_QUOTE_PREFIXES)


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
            for switch in _FONT_PREFIXES:
                if source.startswith(switch, i):
                    tokens.append(switch)
                    i += len(switch)
                    break
            else:
                i = _lex_run(source, i, tokens, str.isalpha)
                tokens.extend(_split_word(tokens.pop()))
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
    if base and _has_outer_script(base, op):
        base = "{" + base + "}"
    return f"{base}{op}{body}"


def _has_outer_script(latex: str, op: str) -> bool:
    """Whether *latex* already carries an *op* script of its own (not one inside braces or ``\\left``…``\\right``,
    which wrapping again would only pile braces on: ``\\left( x^2 \\right)^n`` stays as it is)."""

    depth = fence = 0
    i = 0
    while i < len(latex):
        char = latex[i]
        if char == "\\":
            if latex.startswith("\\left", i) and not latex[i + 5 : i + 6].isalpha():
                fence += 1
            elif latex.startswith("\\right", i) and not latex[i + 6 : i + 7].isalpha():
                fence -= 1
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == op and depth == 0 and fence == 0:
            return True
        i += 1
    return False


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._upright = False  # after ``rm``, until ``it`` -- braces do not end it
        self._bold = False  # while reading the atom right after ``bold``

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

    def _sequence(self, *, depth: int, stop: str | tuple[str, ...] | None = None) -> str:
        stops = (stop,) if isinstance(stop, str) else stop or ()
        nodes: list[str] = []
        while True:
            token = self._peek()
            if token is None or token in stops:
                break
            if token == "}" and depth == 0:
                # A closing brace with nothing open (``{4!}over3!}``): Hancom draws nothing for it.
                self._next()
                continue
            if token in ("from", "to") and nodes and nodes[-1].startswith(_LIMIT_COMMANDS):
                # ``sum from {i=1} to n``: the limits of a big operator, as ``_`` and ``^`` set them.
                token = "_" if token == "from" else "^"
                self._tokens[self._pos] = token
            if token in ("^", "_"):
                self._next()
                base = nodes.pop() if nodes else ""
                nodes.append(_combine_script(base, token, self._atom(depth)))
                continue
            if token in READ_MARKS:
                self._next()
                base = nodes.pop() if nodes else ""
                mark = READ_MARKS[token]
                nodes.append(_combine_script(base, "^", "{\\circ}") + mark[len("^{\\circ}") :])
                continue
            if token in LEFT_SCRIPTS:
                # ``C LSUB {3}``: the script goes before the atom it follows (₃C).
                self._next()
                base = nodes.pop() if nodes else ""
                nodes.append(_combine_script("{}", LEFT_SCRIPTS[token], self._atom(depth)))
                nodes.append(base)
                continue
            if token in ("over", "atop", "choose"):
                self._next()
                numerator = _strip_braces(nodes.pop() if nodes else "")
                denominator = _strip_braces(self._operand(depth))
                if token == "over":
                    nodes.append(f"\\frac{{{numerator}}}{{{denominator}}}")
                elif token == "choose":
                    nodes.append(f"\\binom{{{numerator}}}{{{denominator}}}")
                else:
                    nodes.append(f"{{{numerator} \\atop {denominator}}}")
                continue
            atom = self._atom(depth)
            if atom:  # a font switch with nothing after it is not an operand
                nodes.append(atom)
        return " ".join(part for part in nodes if part != "")

    def _operand(self, depth: int) -> str:
        """The atom after ``over``/``atop``/``choose`` with the scripts that follow it: Hancom sets
        ``x^2 over a^2 - y^2`` as x²/a² − y², the ``^2`` on the denominator."""

        operand = self._atom(depth)
        while self._peek() in ("^", "_"):
            operator = self._next() or "^"
            operand = _combine_script(operand, operator, self._atom(depth))
        return operand

    def _atom(self, depth: int) -> str:
        token = self._next()
        bold = False
        while token in _FONT_SWITCHES:
            if token.lower() == "bold":
                bold = True
            else:  # ``bold rm v`` is upright, not bold: the switch is the atom ``bold`` applies to
                self._upright, bold = token.lower() == "rm", False
            if self._peek() is None or self._peek() in _ATOM_END:
                return ""
            token = self._next()
        if token is None:
            return ""
        if not bold:
            return self._atom_from(token, depth)
        outer, self._bold = self._bold, True
        try:
            return self._atom_from(token, depth)
        finally:
            self._bold = outer

    def _atom_from(self, token: str, depth: int) -> str:
        if token == "{":
            upright = self._upright_text()
            if upright is not None:
                return upright
            bold = self._upright_bold(depth)
            if bold is None:
                bold = self._bold_group(depth)
            if bold is not None:
                return bold
            return "{" + self._group(depth) + "}"
        if token == "sqrt":
            return f"\\sqrt{{{_strip_braces(self._atom(depth))}}}"
        if token == "binom":
            top = _strip_braces(self._atom(depth))
            return f"\\binom{{{top}}}{{{_strip_braces(self._atom(depth))}}}"
        if token == "root":
            # ``root {n} of {x}`` is the n-th root; without ``of`` Hancom draws a square root
            # (``root3`` is √3, ``{root3 a}`` √(3a)), as ``sqrt`` does.
            index = _strip_braces(self._atom(depth))
            if self._peek() != "of":
                return f"\\sqrt{{{index}}}"
            self._next()
            radicand = _strip_braces(self._atom(depth))
            return f"\\sqrt[{index}]{{{radicand}}}"
        if token in ACCENTS:
            return f"{ACCENTS[token]}{{{_strip_braces(self._atom(depth))}}}"
        if token in MATRIX_ENVIRONMENTS:
            return self._matrix(MATRIX_ENVIRONMENTS[token], depth)
        if token in PILES:
            # Rows stacked without delimiters. An empty ``pile{#}`` only props a bracket up: it reads as nothing.
            pile = self._matrix("matrix", depth)
            cells = pile.replace("\\\\", " ").replace("\\,", " ").replace("~", " ").replace("&", " ").split()
            return "" if cells == ["\\begin{matrix}", "\\end{matrix}"] else pile
        if token in ("LEFT", "left"):
            return self._left_right(depth)
        if token in ("RIGHT", "right"):
            # A bare RIGHT without a matching LEFT: emit the delimiter literally.
            delim = self._next()
            return DELIMITERS.get(delim or "", delim or "")
        return self._map_token(token)

    def _upright_text(self) -> str | None:
        """``\\text{...}`` for the group ``{rm "..." it}`` just opened (upright text, italic again after it),
        else ``None`` with nothing consumed."""

        start = self._pos
        window = self._tokens[start : start + 4]
        if len(window) == 4 and window[0] == "rm" and window[2:] == ["it", "}"]:
            literal = window[1]
            if len(literal) >= 2 and literal.startswith('"') and literal.endswith('"'):
                self._pos = start + 4
                self._upright = False
                return f"\\text{{{_escape_text(literal[1:-1])}}}"
        return None

    def _upright_bold(self, depth: int) -> str | None:
        """``\\mathbf{X}`` for the group ``{rm {bold X} it}`` just opened (upright bold, italic again after
        it), else ``None`` with nothing consumed."""

        start = self._pos
        if self._tokens[start : start + 3] == ["rm", "{", "bold"]:
            self._pos = start + 3
            body = self._plain_body(depth)
            if body is not None and self._tokens[self._pos : self._pos + 3] == ["}", "it", "}"]:
                self._pos += 3
                self._upright = False
                return f"\\mathbf{{{_strip_braces(body)}}}"
        self._pos = start
        return None

    def _bold_group(self, depth: int) -> str | None:
        """``\\boldsymbol{X}`` for the group ``{bold {X}}`` just opened (italic bold, what
        ``latex_to_eqedit`` writes for ``\\boldsymbol``), ``\\mathbf{X}`` while ``rm`` is on, else
        ``None`` with nothing consumed."""

        start = self._pos
        if self._tokens[start : start + 1] == ["bold"] and start + 1 < len(self._tokens):
            self._pos = start + 1
            body = self._plain_body(depth)
            if body is not None and self._peek() == "}":
                self._next()
                command = "\\mathbf" if self._upright else "\\boldsymbol"
                return f"{command}{{{_strip_braces(body)}}}"
        self._pos = start
        return None

    def _plain_body(self, depth: int) -> str | None:
        """The next atom without font styling for the caller to wrap in one command, or ``None`` when a
        font switch inside it would carry past the wrapper."""

        upright, bold = self._upright, self._bold
        self._upright = self._bold = False
        start = self._pos
        try:
            body = self._atom(depth + 1)
        finally:
            self._upright, self._bold = upright, bold
        if _FONT_SWITCHES.intersection(self._tokens[start : self._pos]):
            return None
        return body

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
        body = self._sequence(depth=depth, stop=("RIGHT", "right"))
        if self._peek() not in ("RIGHT", "right"):
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
            if token in ("over", "choose"):
                self._next()
                numerator = _strip_braces(current.pop() if current else "")
                denominator = _strip_braces(self._operand(depth))
                command = "\\frac" if token == "over" else "\\binom"
                current.append(f"{command}{{{numerator}}}{{{denominator}}}")
                continue
            current.append(self._atom(depth))
        flush_cell()
        body = " \\\\ ".join(" & ".join(cell for cell in row) for row in rows if row)
        return f"\\begin{{{environment}}} {body} \\end{{{environment}}}"

    def _map_token(self, token: str) -> str:
        if token in SYMBOL_OPERATORS:
            return SYMBOL_OPERATORS[token]
        if token in GREEK:
            # ``rm`` leaves Greek letters as they are; ``bold`` thickens them.
            return f"\\boldsymbol{{{GREEK[token]}}}" if self._bold else GREEK[token]
        if token in BIG_OPERATORS:
            return BIG_OPERATORS[token]
        if token in OPERATORS:
            return OPERATORS[token]
        if token in FUNCTIONS:
            return FUNCTIONS[token]
        if token in READ_SYMBOLS:
            return READ_SYMBOLS[token]
        if token in ("LBRACE", "RBRACE"):  # a literal brace outside LEFT/RIGHT
            return r"\{" if token == "LBRACE" else r"\}"
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            literal = token[1:-1]
            if _needs_literal_quotes(literal):
                # A quoted reserved word is an identifier kept from turning into a symbol; Hancom draws it in
                # italic, as LaTeX draws plain letters. Upright text is the ``{rm "..." it}`` group.
                return self._styled(literal)
            return f"\\text{{{_escape_text(literal)}}}"
        if token == "#":
            return r"\\"
        if token in ("%", "$", "&", "_"):
            return "\\" + token
        return self._styled(token)

    def _styled(self, token: str) -> str:
        """A Latin letter run or a number in the font the switches before it set."""

        if token.isascii() and token.isalpha():
            if self._bold:
                command = "\\mathbf" if self._upright else "\\boldsymbol"
            elif self._upright:
                command = "\\mathrm"
            else:
                return token
            return f"{command}{{{token}}}"
        if self._bold and token[:1].isdigit():
            return f"\\mathbf{{{token}}}"
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
