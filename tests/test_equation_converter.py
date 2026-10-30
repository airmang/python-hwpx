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


@pytest.mark.parametrize(
    "script,expected",
    [
        ("a ` b", r"a \, b"),
        ("dyad {AB}", r"\overleftrightarrow{AB}"),
        ("therefore x", r"\therefore x"),
        ("THEREFORE x", r"\therefore x"),
        ("because x", r"\because x"),
        ("{rm {bold {v}} it} ^{2} w", r"\mathbf{v}^{2} w"),
        ("{rm {bold v} it}", r"\mathbf{v}"),
        # not the authored shape: ``rm`` carries past its braces, so w is upright too (#582)
        ("{rm {bold {v}}} w", r"{\mathbf{v}} \mathrm{w}"),
    ],
)
def test_thin_space_two_headed_arrow_and_conclusion_signs(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


@pytest.mark.parametrize(
    "script,expected",
    [
        ('{rm "km" it}', r"\text{km}"),
        ('{rm "d" it} x', r"\text{d} x"),
        ('T _{{rm "max" it}}', r"T_{\text{max}}"),
        ('{rm "판별식" it} = 0', r"\text{판별식} = 0"),
        ('"d" x', r"\text{d} x"),  # a bare quoted run reads as before
        ('{rm "d"} x', r"{\text{d}} \mathrm{x}"),  # not the authored shape: x is upright too (#582)
        # a quoted reserved word is the writer's identifier protection: plain letters again
        ('T _{"int"}', r"T_{int}"),
        ('e ^{"it"}', r"e^{it}"),  # so with the font switches
        ('x _{"rm"} + a _{"bold"}', r"x_{rm} + a_{bold}"),
        ('"therefore" x', r"therefore x"),
        ('"sin x"', r"\text{sin x}"),  # not a single word: text, as before
    ],
)
def test_upright_text_group_reads_as_text(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


@pytest.mark.parametrize(
    "script,expected",
    [
        ("LBRACE x RBRACE", r"\{ x \}"),  # literal braces, as latex_to_eqedit writes \{ and \}
        ("LEFT LBRACE x RIGHT RBRACE", r"\left\{ x \right\}"),  # as before
    ],
)
def test_brace_words_read_as_braces(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


@pytest.mark.parametrize(
    "script,expected",
    [
        ("x ~|~ x > 0", r"x \mid x > 0"),
        ("a | b", r"a | b"),  # a bare bar stays a bar
        ("{n} choose {r}", r"\binom{n}{r}"),
        ("binom {n} {r}", r"\binom{n}{r}"),
        ("{n + 1} choose {2} x", r"\binom{n + 1}{2} x"),
        ("pmatrix {{n} choose {r} & a}", r"\begin{pmatrix} \binom{n}{r} & a \end{pmatrix}"),
        ('"choose" x', r"choose x"),
    ],
)
def test_set_builder_bar_and_binomial(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


@pytest.mark.parametrize("token", ["triangle", "TRIANGLE"])
def test_triangle_symbol_uses_exact_evidence_backed_tokens(token: str) -> None:
    assert eqedit_to_latex(f"{token} P_1 P_2 Q") == r"\triangle P_1 P_2 Q"


@pytest.mark.parametrize(
    "script",
    [
        "Triangle PQR",
        "triAngle PQR",
        "triangles PQR",
        "mytriangle PQR",
        "triangleidentifier PQR",
        "myrmtriangle PQR",
    ],
)
def test_triangle_support_does_not_split_identifiers(script: str) -> None:
    assert eqedit_to_latex(script) == script


# --- font switches (#582) -----------------------------------------------------
# What Hancom draws (macOS Hancom Office HWP render of a synthetic probe, 2026-10-27): ``rm`` sets the Latin
# letters after it upright until ``it``, past braces, scripts, fractions, roots, LEFT/RIGHT and matrices; Greek
# letters stay as they are. ``bold`` thickens only the next atom, italic or (after ``rm``) upright, and a
# ``rm``/``it`` right after ``bold`` uses it up. Before #582 the switches came back as the words rm/it/bold,
# which latex_to_eqedit quoted, so a re-authored equation drew the letters (``AB = ita``).


@pytest.mark.parametrize(
    "script,expected",
    [
        ("rm A", r"\mathrm{A}"),
        ("rmtriangle PQR", r"\triangle \mathrm{PQR}"),
        ("it a", "a"),
        ("bold x", r"\boldsymbol{x}"),
        ("RM ab IT fv", r"\mathrm{ab} fv"),
        ("BOLD ab fv", r"\boldsymbol{ab} fv"),
        ("5 rm cm", r"5 \mathrm{cm}"),
        ("rm {bar{BC}}", r"{\bar{\mathrm{BC}}}"),
        ("rm {bar{BC}} it", r"{\bar{\mathrm{BC}}}"),
        ("{vec{rm AB}} = it {vec{a}}", r"{\vec{\mathrm{AB}}} = {\vec{a}}"),
        ("rm ab fv", r"\mathrm{ab} \mathrm{fv}"),
        ("x ^{rm ab} fv", r"x^{\mathrm{ab}} \mathrm{fv}"),
        ("{rm ab over cd} fv", r"{\frac{\mathrm{ab}}{\mathrm{cd}}} \mathrm{fv}"),
        ("sqrt {rm ab} fv", r"\sqrt{\mathrm{ab}} \mathrm{fv}"),
        ("LEFT ( rm ab RIGHT ) fv", r"\left( \mathrm{ab} \right) \mathrm{fv}"),
        ("matrix {rm ab & cd} fv", r"\begin{matrix} \mathrm{ab} & \mathrm{cd} \end{matrix} \mathrm{fv}"),
        ("rm alpha beta ab", r"\alpha \beta \mathrm{ab}"),
        ("rm sin x", r"\sin \mathrm{x}"),
        ('rm ab "fv"', r"\mathrm{ab} \text{fv}"),
        ("bold ab fv", r"\boldsymbol{ab} fv"),
        ("bold {ab} fv", r"{\boldsymbol{ab}} fv"),
        ("bold ab + fv", r"\boldsymbol{ab} + fv"),
        ("bold alpha + 2", r"\boldsymbol{\alpha} + 2"),
        ("bold 25", r"\mathbf{25}"),
        ("rm bold ab it fv", r"\mathbf{ab} fv"),
        ("rm ab bold fv", r"\mathrm{ab} \mathbf{fv}"),
        ("rm ab {bold fv} cd", r"\mathrm{ab} \mathbf{fv} \mathrm{cd}"),
        ("bold ab rm fv", r"\boldsymbol{ab} \mathrm{fv}"),
        ("bold rm v", r"\mathrm{v}"),
        ("bold {rm v}", r"{\mathbf{v}}"),
        ("{bold {v}}", r"\boldsymbol{v}"),  # what latex_to_eqedit writes for \boldsymbol
        ("{bold {rm x}} y", r"{{\mathbf{x}}} \mathrm{y}"),  # rm inside goes on past the bold group
        ('rm a {rm "x" it} b', r"\mathrm{a} \text{x} b"),  # the authored upright group ends with it
        ("rm A it ^{2}", r"\mathrm{A}^{2}"),
        ("x ^{rm}", "x^{}"),  # a switch alone in a script draws nothing
        ("a rm", "a"),
    ],
)
def test_font_switches_read_as_latex_fonts(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


@pytest.mark.parametrize(
    "script,expected",
    [
        ('e ^{"it"}', r"e^{it}"),  # a quoted switch word is an identifier (#360), italic as before
        ('rm "it" x', r"\mathrm{it} \mathrm{x}"),  # ... upright after rm
        ("x _{rm}", "x_{}"),
        ("rmA", r"\mathrm{A}"),  # Hancom recognizes switches at the start of a word (#591)
        ("itab fv", "ab fv"),
        ("bit + item", "bit + em"),
    ],
)
def test_font_switch_words_inside_identifiers(script: str, expected: str) -> None:
    assert eqedit_to_latex(script) == expected


def test_font_switch_runs_do_not_recurse() -> None:
    assert eqedit_to_latex("rm " * 3000 + "x") == r"\mathrm{x}"


def test_existing_angle_symbol_remains_distinct_from_triangle() -> None:
    assert eqedit_to_latex("angle ABC") == r"\angle ABC"


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
