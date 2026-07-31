# SPDX-License-Identifier: Apache-2.0
"""Authoring-direction LaTeX → EqEdit converter (clean-room). **Experimental.**

Reverse of :func:`hwpx.equation.eqedit.eqedit_to_latex`: turns a LaTeX math
fragment into the EqEdit script Hancom's equation editor stores inside
``<hp:script>``.  Coverage is the verified token set only — any LaTeX command
or environment outside it raises :class:`UnsupportedLatexError` (typed
refusal), never a silent approximation, so callers can fail closed.

The token vocabulary is the same clean-room re-derivation used by the reader
(:mod:`hwpx.equation.tokens`); the authoring direction additionally protects
bare identifiers that collide with EqEdit reserved words by quoting them
(``T_{int}`` → ``T _{"int"}``) so Hancom does not typeset them as symbols.

Contract provenance: specs/054-equation-authoring/evidence/p0/equation-contract.md.
"""

from __future__ import annotations

from .eqedit import (
    MAX_GROUP_DEPTH,
    MAX_SOURCE_LENGTH,
    EquationConversionError,
)
from .tokens import (
    ACCENTS,
    BIG_OPERATORS,
    DELIMITERS,
    FUNCTIONS,
    GREEK,
    MATRIX_ENVIRONMENTS,
    OPERATORS,
    STRUCTURAL,
)


class UnsupportedLatexError(EquationConversionError):
    """Raised when a LaTeX fragment uses commands outside the verified set."""


def _invert(*maps: dict[str, str]) -> dict[str, str]:
    """LaTeX command → canonical EqEdit token (first-seen wins per map order)."""

    inverse: dict[str, str] = {}
    for mapping in maps:
        for eqedit_token, latex_command in mapping.items():
            inverse.setdefault(latex_command, eqedit_token)
    return inverse


# Commands whose only EqEdit spellings render as literal text (or wrong glyphs)
# on the real Hancom build — render-verified 2026-07-31, specs/054 P2 token
# battery. Emitting them would silently corrupt output, so they are excluded
# from the inverse maps and refuse with UnsupportedLatexError instead.
_RENDER_REJECTED = frozenset(
    {"\\limsup", "\\liminf", "\\widehat", "\\widetilde"}
)

# Word-token maps first so lowercase word forms win (``times`` over ``TIMES``);
# explicit preferences below override where the render oracle verified a
# different spelling than the reader's first-seen entry.
_LATEX_TO_EQEDIT: dict[str, str] = {
    latex: eqedit
    for latex, eqedit in _invert(GREEK, OPERATORS, FUNCTIONS, BIG_OPERATORS).items()
    if latex not in _RENDER_REJECTED
}
_LATEX_TO_EQEDIT.update(
    {
        # Gold scripts spell these symbolically (equation-contract.md §4).
        "\\pm": "+-",
        "\\mp": "-+",
        # Render-verified spellings (P2 token battery): the word ``to`` kills
        # the rest of the equation, ``leftrightarrow`` draws a plain arrow,
        # lowercase ``forall`` and ``iint``/``iiint`` come out as literal text.
        "\\to": "->",
        "\\rightarrow": "->",
        "\\leftrightarrow": "<->",
        "\\forall": "FORALL",
        "\\iint": "dint",
        "\\iiint": "tint",
        # Common LaTeX aliases sharing a verified target.
        "\\le": "leq",
        "\\ge": "geq",
        "\\ne": "neq",
        "\\dots": "cdots",
    }
)
_LATEX_ACCENTS: dict[str, str] = {
    latex: eqedit
    for latex, eqedit in _invert(ACCENTS).items()
    if latex not in _RENDER_REJECTED
}
# LaTeX delimiter commands usable after \left / \right.
_LATEX_DELIMITERS: dict[str, str] = {
    latex: eqedit
    for eqedit, latex in DELIMITERS.items()
    if latex.startswith("\\")
    # Prefer the symbol spellings (``{`` not ``LBRACE``) — both read back.
    and eqedit not in {"LBRACE", "RBRACE", "LANGLE", "RANGLE"}
}
_TEXT_COMMANDS = frozenset({"\\text", "\\mathrm", "\\textrm", "\\mbox"})
# LaTeX environment name → render-verified EqEdit builder word. ``Bmatrix`` /
# ``Vmatrix`` have no verified spelling on the real build (P2 battery R10/R11)
# and refuse; the determinant matrix is EqEdit ``dmatrix`` (R12).
_ENV_TO_EQEDIT: dict[str, str] = {
    "matrix": "matrix",
    "pmatrix": "pmatrix",
    "bmatrix": "bmatrix",
    "vmatrix": "dmatrix",
    "cases": "cases",
}

# Bare identifier runs that would collide with EqEdit vocabulary must be quoted
# so Hancom keeps them literal (reserved-word protection).
_RESERVED_WORDS = (
    frozenset(GREEK)
    | frozenset(OPERATORS)
    | frozenset(FUNCTIONS)
    | frozenset(BIG_OPERATORS)
    | frozenset(ACCENTS)
    | frozenset(MATRIX_ENVIRONMENTS)
    | STRUCTURAL
)

_SINGLE_CHAR_PASSTHROUGH = frozenset("+-=<>,.;:!|/()[]'")


class _LatexLexer:
    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self.tokens: list[str] = []
        self._lex()

    def _lex(self) -> None:
        source = self._source
        i = 0
        n = len(source)
        while i < n:
            ch = source[i]
            if ch.isspace():
                i += 1
            elif ch == "\\":
                i = self._lex_command(i)
            elif ch in "{}^_&":
                self.tokens.append(ch)
                i += 1
            elif ch.isdigit() or ch == ".":
                j = i
                while j < n and (source[j].isdigit() or source[j] == "."):
                    j += 1
                self.tokens.append(source[i:j])
                i = j
            elif ch.isalpha():
                j = i
                while j < n and source[j].isalpha():
                    j += 1
                self.tokens.append(source[i:j])
                i = j
            elif ch in _SINGLE_CHAR_PASSTHROUGH:
                self.tokens.append(ch)
                i += 1
            else:
                raise UnsupportedLatexError(
                    f"unsupported character in LaTeX input: {ch!r}"
                )

    def _lex_command(self, i: int) -> int:
        source = self._source
        n = len(source)
        if i + 1 >= n:
            raise UnsupportedLatexError("dangling backslash at end of input")
        nxt = source[i + 1]
        if nxt == "\\":
            self.tokens.append("\\\\")
            return i + 2
        if not nxt.isalpha():
            # Escaped single character: \{ \} \% \& \$ \| \, ...
            self.tokens.append("\\" + nxt)
            return i + 2
        j = i + 1
        while j < n and source[j].isalpha():
            j += 1
        self.tokens.append(source[i:j])
        return j


class _LatexParser:
    """Recursive-descent LaTeX → EqEdit token emitter (verified set only)."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> str | None:
        token = self._peek()
        if token is not None:
            self._pos += 1
        return token

    def _expect(self, expected: str) -> None:
        token = self._next()
        if token != expected:
            raise UnsupportedLatexError(
                f"expected {expected!r}, found {token!r} — unbalanced LaTeX group"
            )

    # -- grammar -------------------------------------------------------------
    def parse(self) -> str:
        parts = self._sequence(depth=0, stop=frozenset())
        if self._peek() is not None:
            raise UnsupportedLatexError(
                f"unbalanced LaTeX group near {self._peek()!r}"
            )
        return " ".join(parts)

    def _sequence(self, *, depth: int, stop: frozenset[str]) -> list[str]:
        if depth > MAX_GROUP_DEPTH:
            raise EquationConversionError("equation nesting depth exceeded")
        parts: list[str] = []
        while True:
            token = self._peek()
            if token is None or token in stop:
                break
            if token in ("^", "_"):
                self._next()
                script = self._group_or_atom(depth)
                parts.append(f"{token}{{{script}}}")
                continue
            parts.append(self._atom(depth))
        return parts

    def _group_or_atom(self, depth: int) -> str:
        """A script/argument body, brace-stripped (rebraced by the caller)."""

        if self._peek() == "{":
            self._next()
            inner = self._sequence(depth=depth + 1, stop=frozenset({"}"}))
            self._expect("}")
            return " ".join(inner)
        return self._atom(depth)

    def _atom(self, depth: int) -> str:
        token = self._next()
        if token is None:
            return ""
        if token == "{":
            inner = self._sequence(depth=depth + 1, stop=frozenset({"}"}))
            self._expect("}")
            return "{" + " ".join(inner) + "}"
        if token == "}":
            raise UnsupportedLatexError("unbalanced closing brace in LaTeX input")
        if token == "\\frac" or token == "\\dfrac" or token == "\\tfrac":
            numerator = self._group_or_atom(depth)
            denominator = self._group_or_atom(depth)
            return f"{{{numerator}}} over {{{denominator}}}"
        if token == "\\sqrt":
            if self._peek() == "[":
                self._next()
                index_parts = self._sequence(depth=depth + 1, stop=frozenset({"]"}))
                self._expect("]")
                radicand = self._group_or_atom(depth)
                return f"root {{{' '.join(index_parts)}}} of {{{radicand}}}"
            return f"sqrt {{{self._group_or_atom(depth)}}}"
        if token in _TEXT_COMMANDS:
            return self._text_literal()
        if token == "\\begin":
            return self._environment(depth)
        if token == "\\left":
            return self._left_right(depth)
        if token in ("\\right", "\\end"):
            raise UnsupportedLatexError(f"{token} without a matching opener")
        if token in _LATEX_ACCENTS:
            return f"{_LATEX_ACCENTS[token]} {{{self._group_or_atom(depth)}}}"
        if token in _LATEX_TO_EQEDIT:
            return _LATEX_TO_EQEDIT[token]
        if token == "\\\\":
            raise UnsupportedLatexError(
                "row break (\\\\) is only supported inside a matrix/cases environment"
            )
        if token.startswith("\\") and len(token) == 2 and not token[1].isalpha():
            return self._escaped_char(token[1])
        if token.startswith("\\"):
            raise UnsupportedLatexError(f"unsupported LaTeX command: {token}")
        if token == "&":
            raise UnsupportedLatexError(
                "alignment (&) is only supported inside a matrix/cases environment"
            )
        return self._plain_token(token)

    def _escaped_char(self, char: str) -> str:
        if char in "{}":
            # EqEdit spells literal braces as the LBRACE/RBRACE words.
            return "LBRACE" if char == "{" else "RBRACE"
        if char in "%$&":
            return char
        raise UnsupportedLatexError(f"unsupported LaTeX escape: \\{char}")

    def _plain_token(self, token: str) -> str:
        if token.isalpha() and token in _RESERVED_WORDS:
            # Reserved-word protection: keep the identifier literal in Hancom.
            return f'"{token}"'
        return token

    def _text_literal(self) -> str:
        self._expect("{")
        parts: list[str] = []
        while True:
            token = self._peek()
            if token is None:
                raise UnsupportedLatexError("unterminated \\text{...} literal")
            if token == "}":
                self._next()
                break
            if token in ("{", "\\\\") or (
                isinstance(token, str) and token.startswith("\\") and len(token) > 2
            ):
                raise UnsupportedLatexError(
                    "\\text{...} supports plain characters only"
                )
            self._next()
            parts.append(token[1] if token.startswith("\\") else token)
        literal = " ".join(parts)
        if '"' in literal:
            raise UnsupportedLatexError('\\text{...} may not contain a quote (")')
        return f'"{literal}"'

    def _environment(self, depth: int) -> str:
        self._expect("{")
        name = self._next()
        if name == "}":
            raise UnsupportedLatexError("empty \\begin{} environment name")
        self._expect("}")
        builder = _ENV_TO_EQEDIT.get(name or "")
        if builder is None:
            raise UnsupportedLatexError(f"unsupported LaTeX environment: {name}")
        rows: list[list[str]] = [[]]
        current: list[str] = []

        def flush_cell() -> None:
            rows[-1].append(" ".join(current))
            current.clear()

        while True:
            token = self._peek()
            if token is None:
                raise UnsupportedLatexError(f"unterminated environment: {name}")
            if token == "\\end":
                self._next()
                self._expect("{")
                end_name = self._next()
                self._expect("}")
                if end_name != name:
                    raise UnsupportedLatexError(
                        f"environment mismatch: \\begin{{{name}}} closed by "
                        f"\\end{{{end_name}}}"
                    )
                break
            if token == "&":
                self._next()
                flush_cell()
                continue
            if token == "\\\\":
                self._next()
                flush_cell()
                rows.append([])
                continue
            if token in ("^", "_"):
                self._next()
                current.append(f"{token}{{{self._group_or_atom(depth)}}}")
                continue
            current.append(self._atom(depth))
        flush_cell()
        body = " # ".join(
            " & ".join(cell for cell in row) for row in rows if any(row)
        )
        return f"{builder} {{{body}}}"

    def _left_right(self, depth: int) -> str:
        open_token = self._next()
        open_delim = self._delimiter(open_token)
        body = self._sequence(depth=depth + 1, stop=frozenset({"\\right"}))
        if self._peek() != "\\right":
            raise UnsupportedLatexError("\\left without a matching \\right")
        self._next()
        close_token = self._next()
        close_delim = self._delimiter(close_token)
        inner = " ".join(body)
        return f"LEFT {open_delim} {inner} RIGHT {close_delim}"

    def _delimiter(self, token: str | None) -> str:
        if token is None:
            raise UnsupportedLatexError("missing \\left/\\right delimiter")
        if token in _LATEX_DELIMITERS:
            return _LATEX_DELIMITERS[token]
        if token in ("\\{", "\\}"):
            return "LBRACE" if token == "\\{" else "RBRACE"
        if token in DELIMITERS and len(token) == 1:
            return token
        raise UnsupportedLatexError(f"unsupported \\left/\\right delimiter: {token}")


def _strip_math_delimiters(latex: str) -> str:
    text = latex.strip()
    for fence in ("$$", "$"):
        if text.startswith(fence) and text.endswith(fence) and len(text) > 2 * len(fence):
            return text[len(fence) : -len(fence)].strip()
    return text


def latex_to_eqedit(latex: str) -> str:
    """Convert a LaTeX math fragment to an EqEdit ``<hp:script>`` string.

    Surrounding ``$...$`` / ``$$...$$`` fences are stripped for convenience.
    Anything outside the verified token set raises
    :class:`UnsupportedLatexError` — no silent approximation.

    Raises:
        UnsupportedLatexError: unsupported command/environment/character.
        EquationConversionError: size or nesting-depth guard exceeded.
    """

    if len(latex) > MAX_SOURCE_LENGTH:
        raise EquationConversionError("LaTeX input exceeds size limit")
    text = _strip_math_delimiters(latex)
    if "$" in text:
        raise UnsupportedLatexError("interior $ math delimiters are not supported")
    if not text:
        raise UnsupportedLatexError("empty LaTeX input")
    tokens = _LatexLexer(text).tokens
    return _LatexParser(tokens).parse()


def estimate_equation_size(script: str, *, base_unit: int = 1100) -> tuple[int, int]:
    """Heuristic ``(width, height)`` in HWPUNIT for ``<hp:sz>``.

    Hancom re-measures the shape when the document is opened (P0 evidence:
    a fixed size rendered correctly), so this only needs to be a sane
    placeholder, mirroring the gold documents' proportions.
    """

    visible = len(script.replace("{", "").replace("}", "").replace(" ", ""))
    rows = 1 + script.count("#")
    tall = any(word in script for word in ("over", "sqrt", "int", "sum", "prod", "lim"))
    width = int(base_unit * 0.45 * max(6, visible))
    height = int(base_unit * (2.5 if tall else 1.6) * max(1, rows))
    return width, height


__all__ = [
    "UnsupportedLatexError",
    "estimate_equation_size",
    "latex_to_eqedit",
]
