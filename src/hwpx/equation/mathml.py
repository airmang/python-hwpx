# SPDX-License-Identifier: Apache-2.0
"""LaTeX → MathML conversion via the optional ``latex2mathml`` dependency.

MathML keeps the preview self-contained: browsers render ``<math>`` natively, so
no script or font bundle is shipped.  ``latex2mathml`` is an optional extra
(``python-hwpx[preview]``); when it is absent the caller fails closed to a LaTeX
code block rather than dropping the equation.
"""

from __future__ import annotations

from typing import Callable

# ``False`` marks a resolved-but-unavailable converter; ``None`` means "not yet
# probed" so the import is attempted lazily on first use.
_converter: Callable[[str], str] | bool | None = None


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


__all__ = [
    "MathMLUnavailableError",
    "latex2mathml_available",
    "latex_to_mathml",
]
