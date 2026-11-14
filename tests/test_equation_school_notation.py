# SPDX-License-Identifier: Apache-2.0
"""School notation in the LaTeX → EqEdit converter.

Every spelling asserted here was drawn by desktop Hangul 2024 (Windows) on
2026-11-13 and looked at: the symbol comes out as the symbol, not as letters.
"""
from __future__ import annotations

import pytest

from hwpx.equation import eqedit_to_latex
from hwpx.equation.authoring import UnsupportedLatexError, latex_to_eqedit


@pytest.mark.parametrize(
    ("latex", "script"),
    [
        # Upright math keeps its scripts: before, the underscore was printed as a character.
        (r"\mathrm{H_2O}", "{rm H _{2} O it}"),
        (r"\mathrm{SO_4^{2-}}", "{rm SO _{4} ^{2 -} it}"),
        (r"\mathrm{Na^+}", "{rm Na ^{+} it}"),
        (r"9.8\,\mathrm{m/s^2}", "9.8 ` {rm m / s ^{2} it}"),
        (r"2\mathrm{H_2}+\mathrm{O_2}\to 2\mathrm{H_2O}", "2 {rm H _{2} it} + {rm O _{2} it} -> 2 {rm H _{2} O it}"),
        # Plain upright text keeps the spacing of the source instead of a space between every token.
        (r"\mathrm{cm}", '{rm "cm" it}'),
        (r"60\,\mathrm{km/h}", '60 ` {rm "km/h" it}'),
        (r"\mathrm{A'}", "{rm \"A'\" it}"),
        (r"\text{m s}", '{rm "m s" it}'),
        (r"x\le -2\ \text{또는}\ x\ge 3", 'x leq - 2 ~ {rm "또는" it} ~ x geq 3'),
    ],
)
def test_upright_groups(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


@pytest.mark.parametrize("latex", [r"\text{H_2O}", r"\text{m/s^2}", r"\mbox{a&b}"])
def test_text_refuses_what_it_would_print_as_characters(latex: str) -> None:
    with pytest.raises(UnsupportedLatexError, match="plain characters only"):
        latex_to_eqedit(latex)


@pytest.mark.parametrize(
    ("latex", "script"),
    [
        (r"p\Leftrightarrow q", "p LRARROW q"),
        (r"p\iff q", "p LRARROW q"),
        (r"\overline{AB}\perp\overline{CD}", "overline {AB} BOT overline {CD}"),
        (r"l\parallel m", "l parallel m"),
        (r"\varnothing", "emptyset"),
        (r"a\uparrow", "a uparrow"),
        (r"a\downarrow", "a downarrow"),
        (r"\mathrm{N_2}+3\mathrm{H_2}\rightleftharpoons 2\mathrm{NH_3}",
         "{rm N _{2} it} + 3 {rm H _{2} it} EXARROW 2 {rm NH _{3} it}"),
        (r"\overset{\frown}{AB}", "arch {AB}"),
        (r"\wideparen{AB}", "arch {AB}"),
        (r"\boxed{12}", "box {12}"),
        (r"\begin{aligned} 2x+3&=7 \\ x&=2 \end{aligned}", "eqalign {2 x + 3 & = 7 # x & = 2}"),
        (r"a>0,\ b<0", "a > 0 , ~ b < 0"),
        (r"a\;b\quad c", "a ~ b ~~ c"),
        (r"a\!b", "a  b"),
    ],
)
def test_symbols_and_layout(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


@pytest.mark.parametrize("latex", [r"\overset{*}{AB}", r"\mathbb{R}", r"\square ABCD", r"\widehat{AB}"])
def test_what_has_no_verified_spelling_still_refuses(latex: str) -> None:
    with pytest.raises(UnsupportedLatexError):
        latex_to_eqedit(latex)


@pytest.mark.parametrize(
    ("script", "latex"),
    [
        ("p LRARROW q", r"p \Leftrightarrow q"),
        ("a BOT b", r"a \perp b"),
        ("l parallel m", r"l \parallel m"),
        ("a EXARROW b", r"a \rightleftharpoons b"),
        ("arch {AB}", r"\wideparen{AB}"),
        ("box {12}", r"\boxed{12}"),
        ("eqalign {x & = 2 # y & = 3}", r"\begin{aligned} x & = 2 \\ y & = 3 \end{aligned}"),
    ],
)
def test_the_reader_knows_the_same_spellings(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex
    assert latex_to_eqedit(latex) == script


def test_upright_math_reads_back_with_the_same_meaning() -> None:
    back = eqedit_to_latex(latex_to_eqedit(r"\mathrm{H_2O}"))

    assert "_{2}" in back and r"\mathrm" in back and '"' not in back
    assert "_ 2" not in latex_to_eqedit(back)
