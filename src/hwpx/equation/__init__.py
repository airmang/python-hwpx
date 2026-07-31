# SPDX-License-Identifier: Apache-2.0
"""Equation support: EqEdit → LaTeX → MathML (reader) and LaTeX → EqEdit (authoring).

Clean-room re-derivation of the HULK-style EqEdit vocabulary; see NOTICE for the
referenced projects.  ``latex2mathml`` is an optional dependency
(``python-hwpx[preview]``); without it the pipeline fails closed to a LaTeX code
block rather than dropping the equation.
"""

from __future__ import annotations

from .authoring import (
    UnsupportedLatexError,
    estimate_equation_size,
    latex_to_eqedit,
)
from .eqedit import (
    MAX_GROUP_DEPTH,
    MAX_SOURCE_LENGTH,
    EquationConversionError,
    eqedit_to_latex,
)
from .mathml import (
    MathMLUnavailableError,
    latex2mathml_available,
    latex_to_mathml,
)
from .render import (
    LABEL_LATEX_ERROR,
    LABEL_LATEX_NO_LIB,
    LABEL_MATHML,
    LABEL_SCRIPT,
    EquationRender,
    render_equation,
)

__all__ = [
    "LABEL_LATEX_ERROR",
    "LABEL_LATEX_NO_LIB",
    "LABEL_MATHML",
    "LABEL_SCRIPT",
    "MAX_GROUP_DEPTH",
    "MAX_SOURCE_LENGTH",
    "EquationConversionError",
    "EquationRender",
    "MathMLUnavailableError",
    "UnsupportedLatexError",
    "eqedit_to_latex",
    "estimate_equation_size",
    "latex2mathml_available",
    "latex_to_eqedit",
    "latex_to_mathml",
    "render_equation",
]
