# SPDX-License-Identifier: Apache-2.0
"""Words that start with a Hancom keyword name.

Hancom reads a keyword name at the front of a letter run as the keyword and reads
the rest again: desktop Hangul 2024 drew ``F _{net}`` as F≠t, ``v _{initial}`` as
∈itial, ``pix`` as πx, ``sinx`` as sin x, ``1 overa`` as 1/a, ``tantheta`` as
tan θ, and ``{rm In _{2} O _{3} it}`` as ∈₂O₃ (``In`` is ``in``). ``E _{total}``
drew as letters. The writer quotes such identifiers; the reader splits them.
"""
from __future__ import annotations

import pytest

from hwpx.equation import eqedit_to_latex, latex_to_eqedit


@pytest.mark.parametrize(
    ("latex", "script"),
    [
        (r"F_{net}", 'F _{"net"}'),
        (r"x_{new}", 'x _{"new"}'),
        (r"v_{initial}", 'v _{"initial"}'),
        (r"T_{inside}", 'T _{"inside"}'),
        (r"n_{index}", 'n _{"index"}'),
        (r"a_{ne}", 'a _{"ne"}'),
        (r"x_{le} + y_{ge}", 'x _{"le"} + y _{"ge"}'),
        ("pix", '"pix"'),
        ("sinx", '"sinx"'),
        (r"\mathrm{In_2O_3}", '{rm "In" _{2} O _{3} it}'),
        (r"\vec{F}_{net}", 'vec {F} _{"net"}'),
    ],
)
def test_an_identifier_starting_with_a_keyword_is_quoted(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


@pytest.mark.parametrize("latex", [r"E_{total}", r"x_{1}", "ab", r"T_{out}", "dx"])
def test_an_ordinary_identifier_is_not_quoted(latex: str) -> None:
    assert '"' not in latex_to_eqedit(latex)


@pytest.mark.parametrize("latex", [r"F_{net}", "pix", "sinx", r"v_{initial}", r"\mathrm{In_2O_3}"])
def test_a_quoted_identifier_reads_back_as_its_letters(latex: str) -> None:
    script = latex_to_eqedit(latex)
    again = latex_to_eqedit(eqedit_to_latex(script))
    assert latex_to_eqedit(eqedit_to_latex(again)) == again
    for written in (script, again):
        read = eqedit_to_latex(written)
        assert "\\in" not in read and "\\neq" not in read and "\\pi" not in read and "\\sin" not in read


@pytest.mark.parametrize(
    ("script", "latex"),
    [
        ("F _{net}", r"F_{\neq t}"),
        ("v _{initial}", r"v_{\in itial}"),
        ("pix", r"\pi x"),
        ("sinx", r"\sin x"),
        ("tantheta", r"\tan \theta"),
        ("1 overa", r"\frac{1}{a}"),
        ("{rm In _{2} O _{3} it}", r"{\in_{2} \mathrm{O}_{3}}"),
        ("cdotscdots", r"\cdots \cdots"),
        ("LEQm", r"\leq m"),
        ("BARX", r"\bar{X}"),
        ("E _{total}", r"E_{total}"),
        ("dx", "dx"),
    ],
)
def test_the_reader_splits_a_keyword_off_the_front_of_a_word(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex


@pytest.mark.parametrize(("script", "latex"), [("ANGLE A", r"\angle A"), ("a CDOT b", r"a \cdot b"), ("x ROOT 2", r"x \sqrt{2}")])
def test_the_reader_ignores_the_case_of_symbol_names(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex


def test_greek_and_arrows_keep_their_case() -> None:
    assert eqedit_to_latex("PI") == r"\Pi"
    assert eqedit_to_latex("a rarrow b RARROW c") == r"a \rightarrow b \Rightarrow c"
