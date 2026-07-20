# SPDX-License-Identifier: Apache-2.0
"""EqEdit -> LaTeX converter unit tests.

The three P0 equations are pinned to the exact ``<hp:script>`` strings from the
render-oracle fixture (``tests/fixtures/equation_preview/equation_p0.hwpx``) and
their LaTeX is proven equivalent to the P0 ground-truth MathML.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.equation import MAX_GROUP_DEPTH, MAX_SOURCE_LENGTH, eqedit_to_latex
from hwpx.equation.eqedit import EquationConversionError

FIXTURE = Path(__file__).parent / "fixtures" / "equation_preview" / "equation_p0.hwpx"

# (EqEdit script, expected LaTeX) for the three P0 equations.
P0_EQUATIONS = [
    ("x = {-b +- sqrt{b^2 -4ac}} over {2a}", r"x = \frac{- b \pm \sqrt{b^2 - 4 ac}}{2 a}"),
    ("{alpha} over {beta} + pi", r"\frac{\alpha}{\beta} + \pi"),
    ("int _{0} ^{1} x^2 dx = {1} over {3}", r"\int_{0}^{1} x^2 dx = \frac{1}{3}"),
]


def _fixture_scripts() -> list[str]:
    scripts: list[str] = []
    with zipfile.ZipFile(FIXTURE) as archive:
        for name in archive.namelist():
            if name.startswith("Contents/section") and name.endswith(".xml"):
                text = archive.read(name).decode("utf-8")
                import re

                scripts.extend(re.findall(r"<hp:script>(.*?)</hp:script>", text, re.S))
    return scripts


def test_fixture_scripts_match_pinned_p0() -> None:
    # The pinned test inputs are exactly the oracle fixture's scripts.
    assert _fixture_scripts() == [script for script, _ in P0_EQUATIONS]


@pytest.mark.parametrize("script,expected", P0_EQUATIONS, ids=["quadratic", "fraction-greek", "integral"])
def test_p0_equations_convert_to_expected_latex(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


def test_p0_latex_matches_ground_truth_mathml() -> None:
    # latex2mathml of our converter output must byte-match the P0 evidence MathML
    # (which passed the Hancom render-oracle comparison).
    convert = pytest.importorskip("latex2mathml.converter").convert
    p0_ground_truth_latex = [
        r"x = \frac{-b \pm \sqrt{b^2 -4ac}}{2a}",
        r"\frac{\alpha}{\beta} + \pi",
        r"\int _{0} ^{1} x^2 dx = \frac{1}{3}",
    ]
    for (script, _expected), truth in zip(P0_EQUATIONS, p0_ground_truth_latex):
        assert convert(eqedit_to_latex(script)) == convert(truth)


# --- token classes ---------------------------------------------------------


def test_over_produces_balanced_brace_frac() -> None:
    assert eqedit_to_latex("{a} over {b}") == r"\frac{a}{b}"


def test_sqrt_and_nth_root() -> None:
    assert eqedit_to_latex("sqrt{x}") == r"\sqrt{x}"
    assert eqedit_to_latex("root {3} of {x}") == r"\sqrt[3]{x}"


def test_scripts_subscript_and_superscript() -> None:
    assert eqedit_to_latex("x^2") == "x^2"
    assert eqedit_to_latex("x_i") == "x_i"
    assert eqedit_to_latex("x _{ij} ^{2}") == "x_{ij}^{2}"


def test_pm_and_mp_symbols() -> None:
    assert eqedit_to_latex("a +- b") == r"a \pm b"
    assert eqedit_to_latex("a -+ b") == r"a \mp b"


@pytest.mark.parametrize(
    "script,expected",
    [
        ("alpha", r"\alpha"),
        ("beta", r"\beta"),
        ("pi", r"\pi"),
        ("GAMMA", r"\Gamma"),
        ("OMEGA", r"\Omega"),
    ],
)
def test_greek_letters(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


def test_large_operators_with_bounds() -> None:
    assert eqedit_to_latex("int _{0} ^{1}") == r"\int_{0}^{1}"
    assert eqedit_to_latex("sum _{i=1} ^{n} i") == r"\sum_{i = 1}^{n} i"


def test_times_and_relations() -> None:
    assert eqedit_to_latex("a times b") == r"a \times b"
    assert eqedit_to_latex("a TIMES b") == r"a \times b"
    assert eqedit_to_latex("a leq b") == r"a \leq b"
    assert eqedit_to_latex("a geq b") == r"a \geq b"
    assert eqedit_to_latex("a <= b") == r"a \leq b"
    assert eqedit_to_latex("a >= b") == r"a \geq b"


def test_parentheses_and_braces_passthrough() -> None:
    assert eqedit_to_latex("( a + b )") == "( a + b )"
    assert eqedit_to_latex("LEFT ( x RIGHT )") == r"\left( x \right)"


# --- untrusted-input guards ------------------------------------------------


def test_source_length_guard() -> None:
    with pytest.raises(EquationConversionError):
        eqedit_to_latex("x" * (MAX_SOURCE_LENGTH + 1))


def test_group_depth_guard() -> None:
    bomb = "{" * (MAX_GROUP_DEPTH + 2) + "x" + "}" * (MAX_GROUP_DEPTH + 2)
    with pytest.raises(EquationConversionError):
        eqedit_to_latex(bomb)


def test_all_p0_latex_is_parseable_by_latex2mathml() -> None:
    convert = pytest.importorskip("latex2mathml.converter").convert
    for script, _ in P0_EQUATIONS:
        mathml = convert(eqedit_to_latex(script))
        assert mathml.startswith("<math")
        assert "</math>" in mathml
