# SPDX-License-Identifier: Apache-2.0
"""Equation support: EqEdit → LaTeX (reader) and LaTeX → EqEdit (authoring).

Clean-room re-derivation of the HULK-style EqEdit vocabulary; see NOTICE for the
referenced projects. Drawing an equation for a preview (LaTeX → MathML,
``render_equation``) moved to python-hwpx-automation in 7.0
(``hwpx_automation.preview``). :data:`EQEDIT_MATHML_OPERATOR_COMMANDS` stays here for
that renderer: it is part of the EqEdit vocabulary.
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
from .tokens import EQEDIT_MATHML_OPERATOR_COMMANDS

__all__ = [
    "EQEDIT_MATHML_OPERATOR_COMMANDS",
    "MAX_GROUP_DEPTH",
    "MAX_SOURCE_LENGTH",
    "EquationConversionError",
    "UnsupportedLatexError",
    "eqedit_to_latex",
    "estimate_equation_size",
    "latex_to_eqedit",
]
