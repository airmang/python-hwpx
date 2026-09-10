# SPDX-License-Identifier: Apache-2.0
"""LaTeX → MathML conversion via the optional ``latex2mathml`` dependency.

MathML keeps the preview self-contained: browsers render ``<math>`` natively, so
no script or font bundle is shipped.  ``latex2mathml`` is an optional extra
(``python-hwpx[preview]``); when it is absent the caller fails closed to a LaTeX
code block rather than dropping the equation.
"""

from __future__ import annotations

import re
from typing import Callable

from .tokens import EQEDIT_MATHML_OPERATOR_COMMANDS

# ``False`` marks a resolved-but-unavailable converter; ``None`` means "not yet
# probed" so the import is attempted lazily on first use.
_converter: Callable[[str], str] | bool | None = None
_LATEX_WORD_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_TEXT_COMMAND = "\\text{"


class MathMLUnavailableError(RuntimeError):
    """Raised when ``latex2mathml`` is not installed."""


def _load_converter() -> Callable[[str], str] | bool:
    global _converter
    cached = _converter
    if cached is not None:
        return cached
    try:
        from latex2mathml.converter import convert
    except ImportError:
        _converter = False
        return False
    _converter = convert
    return convert


def latex2mathml_available() -> bool:
    """Return ``True`` when the optional ``latex2mathml`` extra is importable."""

    return _load_converter() is not False


def latex_to_mathml(latex: str) -> str:
    """Convert a LaTeX fragment to an inline ``<math>`` MathML string.

    Raises:
        MathMLUnavailableError: when ``latex2mathml`` is not installed.
        ValueError: when ``latex2mathml`` cannot parse the fragment.
    """

    convert = _load_converter()
    if convert is False:
        raise MathMLUnavailableError(
            "latex2mathml is required for MathML rendering; install python-hwpx[preview]"
        )
    assert not isinstance(convert, bool)  # narrowed for type-checkers
    try:
        return convert(latex)
    except MathMLUnavailableError:
        raise
    except Exception as exc:  # latex2mathml raises bare Exception on bad input
        raise ValueError(f"latex2mathml could not render fragment: {exc}") from exc


def eqedit_latex_to_mathml(latex: str) -> str:
    """Convert EqEdit-derived LaTeX while preserving known token roles.

    ``latex2mathml`` classifies plain ``\\triangle`` as an identifier. EqEdit's
    token map identifies it as a mathematical symbol, so the MathML-only input
    receives an operator wrapper before conversion. The returned/public LaTeX
    is not rewritten, and serialized MathML is never patched afterward.
    """

    def annotate_role(match: re.Match[str]) -> str:
        command = match.group(0)
        if command in EQEDIT_MATHML_OPERATOR_COMMANDS:
            return rf"\mathop{{{command}}}"
        return command

    return latex_to_mathml(
        "".join(
            segment if literal else _LATEX_WORD_COMMAND_RE.sub(annotate_role, segment)
            for segment, literal in _split_text_literals(latex)
        )
    )


def _split_text_literals(latex: str) -> list[tuple[str, bool]]:
    """Split ``latex`` into ``(segment, is_text_literal)`` pieces.

    Quoted EqEdit literals become ``\\text{...}``; their content is prose, so
    the role annotation must not rewrite a ``\\triangle`` typed inside quotes.
    Braces inside the literal are balanced; an unterminated group is passed
    through untouched so ``latex2mathml`` reports it instead of this splitter.
    """

    pieces: list[tuple[str, bool]] = []
    cursor = 0
    while True:
        start = latex.find(_TEXT_COMMAND, cursor)
        if start < 0:
            break
        depth = 0
        end = -1
        for index in range(start + len(_TEXT_COMMAND) - 1, len(latex)):
            char = latex[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end < 0:
            break
        if start > cursor:
            pieces.append((latex[cursor:start], False))
        pieces.append((latex[start:end], True))
        cursor = end
    if cursor < len(latex):
        pieces.append((latex[cursor:], False))
    return pieces


__all__ = [
    "MathMLUnavailableError",
    "eqedit_latex_to_mathml",
    "latex2mathml_available",
    "latex_to_mathml",
]
