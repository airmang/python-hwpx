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

import unicodedata

from ..errors import rejects_removed_arguments
from .eqedit import (
    MAX_GROUP_DEPTH,
    MAX_SOURCE_LENGTH,
    EquationConversionError,
    _needs_literal_quotes,
)
from .tokens import (
    ACCENTS,
    BIG_OPERATORS,
    DELIMITERS,
    FUNCTIONS,
    GREEK,
    OPERATORS,
)


class UnsupportedLatexError(EquationConversionError):
    """Raised when a LaTeX fragment uses commands outside the verified set."""

    default_code = "equation-latex-unsupported"


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
        # ``triangle`` is accepted when reading (observed in real documents) but
        # only the documented uppercase spelling is emitted when authoring: the
        # lowercase form has not been render-verified, and lowercase ``forall``
        # already turned out to render as literal text.
        "\\triangle": "TRIANGLE",
        # A bare ``|`` draws the bar with no space around it; ``~|~`` spaces it as \mid does.
        "\\mid": "~|~",
        # Common LaTeX aliases sharing a verified target.
        "\\le": "leq",
        "\\ge": "geq",
        "\\ne": "neq",
        "\\dots": "cdots",
        # Render-verified on desktop Hangul 2024 (2026-11-13): ``LRARROW`` draws the double two-way
        # arrow (``<=>`` and ``Leftrightarrow`` do not), ``BOT`` the perpendicular sign (``perp`` comes
        # out as letters), ``EXARROW`` the pair of arrows chemistry writes for a reversible reaction.
        "\\Leftrightarrow": "LRARROW",
        "\\iff": "LRARROW",
        "\\perp": "BOT",
        "\\parallel": "parallel",
        "\\varnothing": "emptyset",
        "\\uparrow": "uparrow",
        "\\downarrow": "downarrow",
        "\\Uparrow": "UPARROW",
        "\\rightleftharpoons": "EXARROW",
        "\\rightleftarrows": "EXARROW",
        "\\quad": "~~",
        "\\qquad": "~~~~",
        # Common spellings with the same meaning as a verified one: the long arrows draw the arrow of
        # their short form, ``\colon`` the colon, ``\vert`` the bar.
        "\\longrightarrow": "->",
        "\\longleftarrow": "<-",
        "\\longleftrightarrow": "<->",
        "\\Longrightarrow": "Rightarrow",
        "\\Longleftarrow": "Leftarrow",
        "\\Longleftrightarrow": "LRARROW",
        "\\implies": "Rightarrow",
        "\\impliedby": "Leftarrow",
        "\\gets": "<-",
        "\\colon": ":",
        "\\vert": "|",
        "\\lvert": "|",
        "\\rvert": "|",
        # The double bar (``VERT``, measured on desktop Hangul 2024) and two Hancom symbol names.
        "\\Vert": "VERT",
        "\\lVert": "VERT",
        "\\rVert": "VERT",
        "\\hbar": "hbar",
        "\\ell": "ell",
        # The diagonal arrows as public documents spell them (tables of increase and decrease).
        "\\nearrow": "NEARROW",
        "\\searrow": "SEARROW",
    }
)
# Size and style commands that change only how big LaTeX draws what follows: Hancom sizes the
# equation itself, so they are left out (``\Big[`` is ``[``, ``\displaystyle\sum`` is ``\sum``).
_IGNORED_COMMANDS = frozenset({
    "\\displaystyle", "\\textstyle", "\\scriptstyle", "\\scriptscriptstyle", "\\limits", "\\nolimits",
    "\\big", "\\Big", "\\bigg", "\\Bigg", "\\bigl", "\\bigr", "\\Bigl", "\\Bigr", "\\biggl", "\\biggr",
    "\\Biggl", "\\Biggr", "\\bigm", "\\Bigm", "\\biggm", "\\Biggm",
})
# Characters typed for a symbol, read as the LaTeX command for it (``×`` is ``\times``).
_UNICODE_COMMANDS: dict[str, tuple[str, ...]] = {
    "×": ("\\times",), "÷": ("\\div",), "±": ("\\pm",), "∓": ("\\mp",), "≤": ("\\leq",), "≥": ("\\geq",),
    "≦": ("\\leq",), "≧": ("\\geq",), "≠": ("\\neq",), "→": ("\\rightarrow",), "←": ("\\leftarrow",),
    "↔": ("\\leftrightarrow",), "⇒": ("\\Rightarrow",), "⇐": ("\\Leftarrow",), "⇔": ("\\Leftrightarrow",),
    "↑": ("\\uparrow",), "↓": ("\\downarrow",), "∞": ("\\infty",), "−": ("-",), "·": ("\\cdot",),
    "⋅": ("\\cdot",), "…": ("\\ldots",), "⋯": ("\\cdots",), "⋮": ("\\vdots",), "⋱": ("\\ddots",),
    "△": ("\\triangle",), "∠": ("\\angle",), "⊥": ("\\perp",), "∥": ("\\parallel",), "√": ("\\sqrt",),
    "∈": ("\\in",), "∉": ("\\notin",), "⊂": ("\\subset",), "⊃": ("\\supset",), "⊆": ("\\subseteq",),
    "⊇": ("\\supseteq",), "∪": ("\\cup",), "∩": ("\\cap",), "∅": ("\\emptyset",), "∴": ("\\therefore",),
    "∵": ("\\because",), "≈": ("\\approx",), "≡": ("\\equiv",), "∼": ("\\sim",), "≃": ("\\simeq",),
    "≅": ("\\cong",), "∝": ("\\propto",), "∀": ("\\forall",), "∃": ("\\exists",), "¬": ("\\neg",),
    "∧": ("\\land",), "∨": ("\\lor",), "∂": ("\\partial",), "∇": ("\\nabla",), "∑": ("\\sum",),
    "∏": ("\\prod",), "∫": ("\\int",), "∮": ("\\oint",), "∘": ("\\circ",), "•": ("\\bullet",),
    "°": ("^", "\\circ"), "′": ("'",), "″": ("'", "'"), "*": ("\\ast",), "∗": ("\\ast",),
}


def _is_drawn_as_itself(char: str) -> bool:
    """A non-ASCII symbol or numbered mark with no command of its own (□, ㉠, ⑴, Ⅰ, ∾): Hancom draws the
    character, as public documents type it. Private-use characters have no meaning to keep."""

    return not char.isascii() and unicodedata.category(char) in ("So", "Sm", "No", "Nl")


# Opening delimiters LaTeX draws at their own size; with their closer they read as ``\left``…``\right``.
_BARE_FENCES = {"\\lfloor": "\\rfloor", "\\lceil": "\\rceil", "\\langle": "\\rangle"}
# What to write instead of a command that has no verified EqEdit spelling.
_ALTERNATIVES = {
    "\\setminus": "write the set difference as A - B",
    "\\rfloor": "use \\left\\lfloor ... \\right\\rfloor",
    "\\rceil": "use \\left\\lceil ... \\right\\rceil",
    "\\rangle": "use \\left\\langle ... \\right\\rangle",
    "\\xrightarrow": "use \\rightarrow (a label over the arrow has no verified spelling)",
    "\\mathbb": "write the set name upright: \\mathrm{R}",
    "\\square": "write an empty answer box as \\boxed{~}",
    "\\widehat": "use \\hat{...}",
    "\\widetilde": "use \\tilde{...}",
    "\\overbrace": "write the label as a script: (a+b)^{n}",
    "\\underbrace": "write the label as a script: (1+\\cdots+1)_{n}",
    "\\ce": "write the formula with \\mathrm{...}: \\mathrm{H_2O}",
    "\\color": "equations take one color; leave the command out",
    "\\cancel": "no strike-through in Hancom equations; leave the command out",
}
_LATEX_ACCENTS: dict[str, str] = {
    latex: eqedit
    for latex, eqedit in _invert(ACCENTS).items()
    if latex not in _RENDER_REJECTED
}
# EqEdit ``vec`` stretches its arrow over the whole argument, as \overrightarrow does.
_LATEX_ACCENTS["\\overrightarrow"] = "vec"
# LaTeX delimiter commands usable after \left / \right.
_LATEX_DELIMITERS: dict[str, str] = {
    latex: eqedit
    for eqedit, latex in DELIMITERS.items()
    if latex.startswith("\\")
    # Prefer the symbol spellings (``{`` not ``LBRACE``) — both read back.
    and eqedit not in {"LBRACE", "RBRACE", "LANGLE", "RANGLE"}
}
_TEXT_COMMANDS = frozenset({"\\text", "\\mathrm", "\\textrm", "\\mbox"})
# Text commands whose body is text, spaces included; the lexer hands it over as one token marked so.
_RAW_TEXT_COMMANDS = frozenset({"\\text", "\\textrm", "\\mbox"})
_RAW_TEXT = "\x00"
# Tokens that cannot start the argument of a command or a script (``x^^2``, ``x_}``).
_NOT_AN_ARGUMENT = frozenset({"}", "^", "_", "&", "\\\\", "\\right", "\\end", "]"})
_TEXT_SYMBOL_COMMANDS = {"\\textbackslash": "\\", "\\textasciicircum": "^", "\\textasciitilde": "~"}
# ``\mathrm`` is upright *math*: scripts and commands inside it keep their meaning (``\mathrm{H_2O}``).
_UPRIGHT_MATH_COMMANDS = frozenset({"\\mathrm"})
# LaTeX environment name → render-verified EqEdit builder word. ``Bmatrix`` /
# ``Vmatrix`` have no verified spelling on the real build (P2 battery R10/R11)
# and refuse; the determinant matrix is EqEdit ``dmatrix`` (R12).
_ENV_TO_EQEDIT: dict[str, str] = {
    "matrix": "matrix",
    "pmatrix": "pmatrix",
    "bmatrix": "bmatrix",
    "vmatrix": "dmatrix",
    "cases": "cases",
    # Lines aligned at ``&`` (render-verified on desktop Hangul 2024, 2026-11-13).
    "aligned": "eqalign",
}

# Bare identifier runs that would collide with EqEdit vocabulary or font prefixes
# must be quoted so Hancom keeps them literal (reserved-word protection).

# ``~`` is a space in both: a LaTeX tie and EqEdit's normal space (``\,`` is the small one, `` ` ``).
_SINGLE_CHAR_PASSTHROUGH = frozenset("+-=<>,.;:!|/()[]'~")


class _LatexLexer:
    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self.tokens: list[str] = []
        #: For each token, whether white space came before it in the source.
        self.spaced: list[bool] = []
        self._lex()
        while len(self.spaced) < len(self.tokens):  # tokens added by _lex_command
            self.spaced.append(False)

    def _lex(self) -> None:
        source = self._source
        i = 0
        n = len(source)
        gap = False
        while i < n:
            ch = source[i]
            while len(self.spaced) < len(self.tokens):
                self.spaced.append(False)
            if ch.isspace():
                gap = True
                i += 1
                continue
            self.spaced.append(gap)
            gap = False
            if ch == "\\":
                i = self._lex_command(i)
                if len(self.spaced) > len(self.tokens):  # an ignored command: no token
                    gap = self.spaced.pop()
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
            elif ch in _UNICODE_COMMANDS:
                self.tokens.extend(_UNICODE_COMMANDS[ch])
                i += 1
            elif _is_drawn_as_itself(ch):
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
        command = source[i:j]
        if command in _IGNORED_COMMANDS:
            return j
        self.tokens.append(command)
        if command in _RAW_TEXT_COMMANDS:
            k = j
            while k < n and source[k].isspace():
                k += 1
            if k < n and source[k] == "{":
                return self._lex_raw_text(k)
        return j

    def _lex_raw_text(self, i: int) -> int:
        """The body of ``\\text{...}`` at *i* (its ``{``) as one token, its spaces kept (``\\text{ 또는 }``)."""

        source = self._source
        n = len(source)
        parts: list[str] = []
        j = i + 1
        while True:
            if j >= n:
                raise UnsupportedLatexError("unterminated \\text{...} literal")
            char = source[j]
            if char == "}":
                break
            if char == "{":
                raise UnsupportedLatexError("\\text{...} supports plain characters only")
            if char in "^_&%#":
                # LaTeX reads these as commands even in text (``%`` starts a comment); written escaped
                # (``\%``) they are characters, which Hancom prints as they are inside quotes.
                raise UnsupportedLatexError(
                    f"\\text{{...}} holds plain characters only; {char!r} needs math mode (\\mathrm{{...}}) "
                    f"or an escape (\\{char})"
                )
            if char == "\\":
                j = self._lex_text_escape(j, parts)
                continue
            parts.append(" " if char.isspace() or char == "~" else char)
            j += 1
        self.tokens.append(_RAW_TEXT + "".join(parts))
        return j + 1

    def _lex_text_escape(self, j: int, parts: list[str]) -> int:
        """One ``\\`` escape inside ``\\text{...}`` at *j*: its character goes to *parts*."""

        source = self._source
        k = j + 1
        while k < len(source) and source[k].isalpha():
            k += 1
        name = source[j:k]
        if name in _TEXT_SYMBOL_COMMANDS:
            parts.append(_TEXT_SYMBOL_COMMANDS[name])
            return k + 2 if source.startswith("{}", k) else k
        if k > j + 1:
            raise UnsupportedLatexError("\\text{...} supports plain characters only")
        escaped = source[j + 1 : j + 2]
        if escaped and escaped in "%$&#_{}":
            parts.append(escaped)
        elif escaped and escaped in " ,;:":
            parts.append(" ")
        else:
            raise UnsupportedLatexError(f"unsupported LaTeX escape in \\text{{...}}: \\{escaped}")
        return j + 2


class _LatexParser:
    """Recursive-descent LaTeX → EqEdit token emitter (verified set only)."""

    def __init__(self, tokens: list[str], spaced: list[bool] | None = None) -> None:
        self._tokens = tokens
        self._spaced = spaced if spaced is not None else [False] * len(tokens)
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
        scripts: set[str] = set()  # the scripts already on the last atom
        while True:
            token = self._peek()
            if token is None or token in stop:
                break
            if token in ("^", "_"):
                self._next()
                if token in scripts:
                    kind = "superscript" if token == "^" else "subscript"
                    raise UnsupportedLatexError(
                        f"double {kind} ({token} twice on one atom): group it as x{token}{{a{token}b}} or {{x{token}a}}{token}b"
                    )
                scripts.add(token)
                script = self._group_or_atom(depth, what=f"the script after {token}")
                parts.append(f"{token}{{{script}}}")
                continue
            scripts = set()
            parts.append(self._atom(depth))
        return parts

    def _argument(self, depth: int, command: str) -> str:
        """The required, non-empty argument of *command* (``\\sqrt{}`` and ``\\frac{1}`` draw junk in Hancom)."""

        body = self._group_or_atom(depth, what=f"the argument of {command}")
        if not body.strip():
            raise UnsupportedLatexError(f"{command} needs a non-empty argument")
        return body

    def _group_or_atom(self, depth: int, *, what: str = "an argument") -> str:
        """A script/argument body, brace-stripped (rebraced by the caller)."""

        token = self._peek()
        if token is None or token in _NOT_AN_ARGUMENT:
            found = "the end of the input" if token is None else repr(token)
            raise UnsupportedLatexError(f"missing {what}: found {found}")
        if token == "{":
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
            numerator = self._argument(depth, token)
            denominator = self._argument(depth, token)
            return self._stacked(f"{{{numerator}}} over {{{denominator}}}")
        if token == "\\binom":
            # ``choose`` stretches the parentheses; ``( {n} atop {r} )`` does not.
            top = self._argument(depth, token)
            bottom = self._argument(depth, token)
            return self._stacked(f"{{{top}}} choose {{{bottom}}}")
        if token == "\\sqrt":
            if self._peek() == "[":
                self._next()
                index_parts = self._sequence(depth=depth + 1, stop=frozenset({"]"}))
                self._expect("]")
                radicand = self._argument(depth, token)
                return f"root {{{' '.join(index_parts)}}} of {{{radicand}}}"
            return f"sqrt {{{self._argument(depth, token)}}}"
        if token in _BARE_FENCES:
            return self._bare_fence(token, depth)
        if token == "\\operatorname":
            return self._operator_name()
        if token == "\\not":
            return self._negated()
        if token == "\\pmod":
            # `` (mod m)`` after a space, as LaTeX sets it; ``mod`` is the upright function name.
            return f"~~( mod ~{{{self._argument(depth, token)}}} )"
        if token in ("\\lbrace", "\\rbrace"):  # the command spellings of \{ and \}
            return "LBRACE" if token == "\\lbrace" else "RBRACE"
        if token in _TEXT_COMMANDS:
            if token in _UPRIGHT_MATH_COMMANDS and self._upright_group_is_math():
                # ``rm`` sets what follows upright and goes on past its braces; ``it`` ends it.
                return f"{{rm {self._group_or_atom(depth)} it}}"
            return self._text_literal()
        if token == "\\boxed":
            return f"box {{{self._group_or_atom(depth)}}}"
        if token == "\\wideparen":
            return f"arch {{{self._group_or_atom(depth)}}}"
        if token == "\\overset":
            return self._overset(depth)
        if token == "\\mathbf":
            # ``bold`` alone keeps the letters italic and ``rm`` goes on past its braces: upright bold, then
            # italic again for what follows.
            return f"{{rm {{bold {{{self._argument(depth, token)}}}}} it}}"
        if token == "\\boldsymbol":
            # ``bold`` thickens only the next atom and keeps the letters italic, as ``\boldsymbol`` does.
            return f"{{bold {{{self._argument(depth, token)}}}}}"
        if token == "\\begin":
            return self._environment(depth)
        if token == "\\left":
            return self._left_right(depth)
        if token in ("\\right", "\\end"):
            raise UnsupportedLatexError(f"{token} without a matching opener")
        if token in _LATEX_ACCENTS:
            return f"{_LATEX_ACCENTS[token]} {{{self._argument(depth, token)}}}"
        if token in _LATEX_TO_EQEDIT:
            return _LATEX_TO_EQEDIT[token]
        if token == "\\\\":
            raise UnsupportedLatexError(
                "row break (\\\\) is only supported inside a matrix/cases environment"
            )
        if token.startswith("\\") and len(token) == 2 and not token[1].isalpha():
            return self._escaped_char(token[1])
        if token.startswith("\\"):
            hint = _ALTERNATIVES.get(token)
            raise UnsupportedLatexError(
                f"unsupported LaTeX command: {token}" + (f" -- {hint}" if hint else "")
            )
        if token == "&":
            raise UnsupportedLatexError(
                "alignment (&) is only supported inside a matrix/cases environment"
            )
        return self._plain_token(token)

    def _stacked(self, script: str) -> str:
        """A fraction or binomial, braced when a script follows it: Hancom puts the script of
        ``{a} over {b} ^{2}`` on the denominator, LaTeX ``\\frac{a}{b}^2`` on the whole fraction."""

        return f"{{{script}}}" if self._peek() in ("^", "_") else script

    def _bare_fence(self, opener: str, depth: int) -> str:
        """``\\lfloor x \\rfloor``: the pair as ``LEFT``/``RIGHT`` (a lone opener has no verified spelling)."""

        closer = _BARE_FENCES[opener]
        body = self._sequence(depth=depth + 1, stop=frozenset({closer, "\\right"}))
        if self._peek() != closer:
            raise UnsupportedLatexError(
                f"{opener} needs its {closer} in the same group: use \\left{opener} ... \\right{closer}"
            )
        self._next()
        return f"LEFT {self._delimiter(opener)} {' '.join(body)} RIGHT {self._delimiter(closer)}"

    def _operator_name(self) -> str:
        """``\\operatorname{sgn}``: a known function name as itself, any other name upright."""

        self._expect("{")
        letters: list[str] = []
        while self._peek() not in (None, "}"):
            token = self._next() or ""
            if not token.isalpha():
                raise UnsupportedLatexError("\\operatorname{...} takes letters only")
            letters.append(token)
        self._expect("}")
        name = "".join(letters)
        if not name:
            raise UnsupportedLatexError("\\operatorname needs a non-empty argument")
        command = _LATEX_TO_EQEDIT.get("\\" + name)
        if command is not None and "\\" + name in FUNCTIONS.values():
            return command
        return self._quoted_upright(name)

    def _negated(self) -> str:
        """``\\not=`` and ``\\not\\in``: the verified negated relations. Others have no verified spelling."""

        token = self._next()
        if token == "=":
            return "neq"
        if token == "\\in":
            return "notin"
        raise UnsupportedLatexError(
            f"\\not is supported only before = and \\in (got {token!r}); use \\neq or \\notin"
        )

    def _escaped_char(self, char: str) -> str:
        if char == "|":
            return "VERT"  # \| is the double bar
        if char in "{}":
            # EqEdit spells literal braces as the LBRACE/RBRACE words.
            return "LBRACE" if char == "{" else "RBRACE"
        if char in "%$&":
            return char
        if char in " ;":
            return "~"  # a normal space
        if char == ":":
            return "`"  # a small space
        if char == "!":
            return ""  # a negative thin space: nothing to write
        raise UnsupportedLatexError(f"unsupported LaTeX escape: \\{char}")

    def _plain_token(self, token: str) -> str:
        if _needs_literal_quotes(token):
            # Reserved-word protection: keep the identifier literal in Hancom.
            return f'"{token}"'
        return token

    def _upright_group_is_math(self) -> bool:
        """Whether the ``{...}`` after ``\\mathrm`` holds scripts, groups or commands (not just characters)."""

        if self._peek() != "{":
            return False
        level = 0
        for token in self._tokens[self._pos :]:
            if token == "{":
                level += 1
                if level > 1:
                    return True
            elif token == "}":
                level -= 1
                if level == 0:
                    return False
            elif token in ("^", "_") or (token.startswith("\\") and len(token) > 2):
                return True
        return False

    def _overset(self, depth: int) -> str:
        """``\\overset{\\frown}{AB}``: the arc over a pair of points. Nothing else has a verified spelling."""

        self._expect("{")
        mark = self._next()
        if mark != "\\frown" or self._peek() != "}":
            raise UnsupportedLatexError("\\overset is supported only as \\overset{\\frown}{...} (an arc)")
        self._next()
        return f"arch {{{self._group_or_atom(depth)}}}"

    def _text_literal(self) -> str:
        raw = self._peek()
        if raw is not None and raw.startswith(_RAW_TEXT):
            self._next()
            return self._quoted_upright(raw[len(_RAW_TEXT) :])
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
            if token in ("^", "_", "&"):
                # Inside quotes Hancom prints these as the characters themselves.
                raise UnsupportedLatexError(
                    f"\\text{{...}} holds plain characters only; {token!r} needs math mode (\\mathrm{{...}})"
                )
            if parts and self._spaced[self._pos]:
                parts.append(" ")
            self._next()
            parts.append(token[1] if token.startswith("\\") else token)
        return self._quoted_upright("".join(parts))

    @staticmethod
    def _quoted_upright(literal: str) -> str:
        if '"' in literal:
            raise UnsupportedLatexError('\\text{...} may not contain a quote (")')
        # Hancom draws a bare quoted run in italic. ``rm`` makes it upright and goes on past its braces,
        # so ``it`` turns italic back on for what follows.
        return f'{{rm "{literal}" it}}'

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
        if token in ("\\{", "\\}", "\\lbrace", "\\rbrace"):
            return "LBRACE" if token in ("\\{", "\\lbrace") else "RBRACE"
        if token in DELIMITERS and len(token) == 1:
            return token
        if token in ("\\vert", "\\lvert", "\\rvert"):
            return "|"
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
    if "$" in text.replace("\\$", ""):
        raise UnsupportedLatexError("interior $ math delimiters are not supported")
    if not text:
        raise UnsupportedLatexError("empty LaTeX input")
    lexer = _LatexLexer(text)
    return _LatexParser(lexer.tokens, lexer.spaced).parse()


@rejects_removed_arguments(caller="hwpx.equation.estimate_equation_size")
def estimate_equation_size(script: str, *, font_size: float = 11.0) -> tuple[int, int]:
    """``(width, height)`` in HWPUNIT for ``<hp:sz>``, measured from the script's structure at
    *font_size* (pt, as ``paragraph.add_equation(font_size=)`` takes it; Hancom keeps it to a
    hundredth of a point).

    A reader that lays the page out from the file uses the stored box, so the
    box has to fit the script; Hancom itself was observed (on macOS) to lay the
    equation out again and rewrite the box when it saves the document, while on
    Windows it keeps the stored box and lays the page out with it (see
    :func:`hwpx.equation.measure.measure_equation`). A *font_size* that is not a
    positive number of points is refused (``shape-equation-base-unit-value``).
    """

    from ..oxml.shape_position import equation_base_unit
    from .measure import measure_equation

    size = measure_equation(script, base_unit=equation_base_unit(font_size))
    return size.width, size.height


__all__ = [
    "UnsupportedLatexError",
    "estimate_equation_size",
    "latex_to_eqedit",
]
