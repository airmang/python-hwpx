# SPDX-License-Identifier: Apache-2.0
"""Fail-closed equation rendering tests (Constitution VI: never a blank)."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

from hwpx.equation import (
    LABEL_LATEX_ERROR,
    LABEL_LATEX_NO_LIB,
    LABEL_MATHML,
    LABEL_SCRIPT,
    latex2mathml_available,
    render_equation,
)
from hwpx.equation import mathml as mathml_module


def test_success_path_renders_inline_mathml() -> None:
    pytest.importorskip("latex2mathml")
    result = render_equation("{alpha} over {beta} + pi")
    assert result.mode == "mathml"
    assert result.label == LABEL_MATHML
    assert "<math" in result.html
    assert result.latex == r"\frac{\alpha}{\beta} + \pi"


@pytest.mark.parametrize("token", ["triangle", "TRIANGLE"])
def test_triangle_renders_as_mathml_operator_without_changing_latex(token: str) -> None:
    pytest.importorskip("latex2mathml")
    result = render_equation(f"{token} P_1 P_2 Q")
    assert result.mode == "mathml"
    assert result.latex == r"\triangle P_1 P_2 Q"
    root = ElementTree.fromstring(result.html)
    namespace = "{http://www.w3.org/1998/Math/MathML}"
    triangle_operators = [
        operator
        for operator in root.iter(f"{namespace}mo")
        if "△" in "".join(operator.itertext())
    ]
    assert len(triangle_operators) == 1
    assert "triangle" not in "".join(root.itertext()).lower()


def test_eqedit_failure_falls_back_to_original_script_block() -> None:
    # A brace/frac bomb exceeds the depth guard -> EqEdit->LaTeX fails.
    bomb = "{" * 200 + "x" + "}" * 200
    result = render_equation(bomb)
    assert result.mode == "script"
    assert result.label == LABEL_SCRIPT
    assert "<code>" in result.html
    assert result.latex is None
    assert result.html.strip()  # never empty


def test_missing_latex2mathml_falls_back_to_latex_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate the optional dependency being absent (import having failed): the
    # cached converter resolves to the unavailable sentinel.
    monkeypatch.setattr(mathml_module, "_converter", False)
    result = render_equation("{alpha} over {beta}")
    assert result.mode == "latex"
    assert result.label == LABEL_LATEX_NO_LIB
    assert "python-hwpx[preview]" in result.html
    assert r"\frac{\alpha}{\beta}" in result.html


def test_latex2mathml_error_falls_back_to_latex_block(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_latex: str) -> str:
        raise ValueError("bad latex")

    # Present but failing to convert this fragment -> still fail closed to LaTeX.
    monkeypatch.setattr(mathml_module, "_converter", _boom)
    result = render_equation("{alpha} over {beta}")
    assert result.mode == "latex"
    assert result.label == LABEL_LATEX_ERROR
    assert r"\frac{\alpha}{\beta}" in result.html


def test_no_mode_ever_returns_empty_html() -> None:
    for script in ("{alpha} over {beta}", "{" * 200 + "x" + "}" * 200, ""):
        assert render_equation(script).html.strip()


def test_latex2mathml_available_reflects_installation() -> None:
    # In the test extra latex2mathml is installed, so this is True.
    assert latex2mathml_available() is True
