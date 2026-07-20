# SPDX-License-Identifier: Apache-2.0
"""Fail-closed rendering of EqEdit equations into preview HTML.

The chain never yields an empty result (Constitution VI, fail-closed):

1. ``EqEdit → LaTeX`` fails  → the original ``<hp:script>`` text in a code block
   labelled ``수식(변환 불가)``.
2. ``latex2mathml`` missing  → the LaTeX in a code block labelled
   ``수식(LaTeX) — MathML 렌더는 python-hwpx[preview] 설치``.
3. ``latex2mathml`` errors   → the LaTeX in a code block labelled
   ``수식(LaTeX) — MathML 변환 실패``.
4. otherwise                 → inline ``<math>`` MathML.
"""

from __future__ import annotations

from dataclasses import dataclass
import html

from .eqedit import EquationConversionError, eqedit_to_latex
from .mathml import MathMLUnavailableError, latex_to_mathml

# Fidelity labels surfaced in the preview (Constitution IX, honest reporting).
LABEL_MATHML = "수식 MathML 렌더"
LABEL_LATEX_NO_LIB = "수식(LaTeX) — MathML 렌더는 python-hwpx[preview] 설치"
LABEL_LATEX_ERROR = "수식(LaTeX) — MathML 변환 실패"
LABEL_SCRIPT = "수식(변환 불가)"


@dataclass(frozen=True)
class EquationRender:
    """Result of rendering one EqEdit script into preview HTML.

    Attributes:
        mode: ``"mathml"``, ``"latex"``, or ``"script"``.
        html: self-contained inline HTML fragment (never empty).
        label: honest fidelity label for the chosen mode.
        latex: the converted LaTeX, when conversion succeeded.
    """

    mode: str
    html: str
    label: str
    latex: str | None = None


def _fallback_block(mode: str, label: str, body: str, *, latex: str | None) -> EquationRender:
    fragment = (
        f'<span class="hwpx-equation-fallback" data-eq-mode="{mode}">'
        f'<span class="hwpx-equation-tag">{html.escape(label)}</span>'
        f"<code>{html.escape(body)}</code>"
        "</span>"
    )
    return EquationRender(mode=mode, html=fragment, label=label, latex=latex)


def render_equation(script: str) -> EquationRender:
    """Render one EqEdit ``<hp:script>`` string into a fail-closed HTML fragment."""

    try:
        latex = eqedit_to_latex(script)
    except EquationConversionError:
        return _fallback_block("script", LABEL_SCRIPT, script, latex=None)

    try:
        mathml = latex_to_mathml(latex)
    except MathMLUnavailableError:
        return _fallback_block("latex", LABEL_LATEX_NO_LIB, latex, latex=latex)
    except ValueError:
        return _fallback_block("latex", LABEL_LATEX_ERROR, latex, latex=latex)

    fragment = f'<span class="hwpx-equation" data-eq-mode="mathml">{mathml}</span>'
    return EquationRender(mode="mathml", html=fragment, label=LABEL_MATHML, latex=latex)


__all__ = [
    "LABEL_LATEX_ERROR",
    "LABEL_LATEX_NO_LIB",
    "LABEL_MATHML",
    "LABEL_SCRIPT",
    "EquationRender",
    "render_equation",
]
