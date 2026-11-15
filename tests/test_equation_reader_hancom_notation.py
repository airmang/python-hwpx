# SPDX-License-Identifier: Apache-2.0
"""Hancom notation in real documents that the reader used to turn into wrong LaTeX.

Checked against desktop Hangul 2024: ``root3`` draws √3 (``root`` is an n-th
root only with ``of``), ``x^2 over a^2 -y^2`` draws x²/a² − y² (a script after
the denominator belongs to it), ``rarrow`` →, ``ANGLE`` ∠, ``CDOT``/``CDOTS``
· and ⋯, ``BOX{}`` a frame.
"""
from __future__ import annotations

import pytest

from hwpx.equation import eqedit_to_latex, latex_to_eqedit


@pytest.mark.parametrize(
    ("script", "latex"),
    [
        ("root3", r"\sqrt{3}"),
        ("a> root5", r"a > \sqrt{5}"),
        ("{root3 a}", r"{\sqrt{3} a}"),
        ("{2} over {root3 a}", r"\frac{2}{\sqrt{3} a}"),
        ("root {3} of {x}", r"\sqrt[3]{x}"),
        ("rootx", r"\sqrt{x}"),
    ],
)
def test_root_without_of_is_a_square_root(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex


@pytest.mark.parametrize(
    ("script", "latex"),
    [
        ("x^2 over a^2 -y^2", r"\frac{x^2}{a^2} - y^2"),
        ("a over b^2", r"\frac{a}{b^2}"),
        ("a over b_1^2", r"\frac{a}{b_1^2}"),
        ("n choose r^2", r"\binom{n}{r^2}"),
        ("matrix{a over b^2 & c}", r"\begin{matrix} \frac{a}{b^2} & c \end{matrix}"),
    ],
)
def test_a_script_after_the_denominator_belongs_to_it(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex


@pytest.mark.parametrize(
    ("script", "latex"),
    [
        ("x rarrow y", r"x \rightarrow y"),
        ("lim _{n rarrow INF} a_n", r"\lim_{n \rightarrow \infty} a_n"),
        ("ANGLE ABC", r"\angle ABC"),
        ("a CDOT b CDOTS", r"a \cdot b \cdots"),
        ("BOX{3}", r"\boxed{3}"),
        ("SEARROW", r"\searrow"),
        ("A SMALLINTER B", r"A \cap B"),
        ("90DEG", r"90^{\circ}"),
        ("25 CENTIGRADE", r"25^{\circ}\mathrm{C}"),
        ("a BULLET b", r"a \bullet b"),
        ("a `not= `0", r"a \, \not = \, 0"),
        ("a ne b le c ge d", r"a \neq b \leq c \geq d"),
        ("rm C LSUB {3} _{1}", r"{}_{3} \mathrm{C}_{1}"),
        ("pile{a # b}", r"\begin{matrix} a \\ b \end{matrix}"),
        ("LEFT [ pile{`#`} t ^{3} RIGHT ] _{2}^{3}", r"\left[ t^{3} \right]_{2}^{3}"),
        ("sum from {i=1} to n a_i", r"\sum_{i = 1}^n a_i"),
        ("int from 0 to 1 x dx", r"\int_0^1 x dx"),
        ("x to y", r"x \to y"),
        ("f left( x right)", r"f \left( x \right)"),
        ("{4!}over3!}=4", r"\frac{4 !}{3} ! = 4"),
    ],
)
def test_hancom_words_read_as_latex(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex


@pytest.mark.parametrize(
    ("script", "latex"),
    [('"50%"', r"\text{50\%}"), ('"a_b"', r"\text{a\_b}"), ('"}"', r"\text{\}}"), ('"a^b~c"', r"\text{a\textasciicircum{}b\textasciitilde{}c}")],
)
def test_quoted_text_escapes_latex_specials(script: str, latex: str) -> None:
    assert eqedit_to_latex(script) == latex
    assert eqedit_to_latex(latex_to_eqedit(eqedit_to_latex(script))) == latex


@pytest.mark.parametrize(
    "script",
    [
        "LEFT ( x ^{2} RIGHT ) ^{n}",
        "LEFT ( {a} over {b} RIGHT ) ^{2} + LEFT [ x RIGHT ] _{0} ^{1}",
        "x^2^3",
        "1 overa + root3",
    ],
)
def test_a_second_round_trip_changes_nothing(script: str) -> None:
    once = latex_to_eqedit(eqedit_to_latex(script))
    assert latex_to_eqedit(eqedit_to_latex(once)) == once


def test_a_script_on_a_fenced_group_is_not_braced_again() -> None:
    assert eqedit_to_latex("LEFT ( x ^{2} RIGHT ) ^{n}") == r"\left( x^{2} \right)^{n}"
    assert eqedit_to_latex("x^2^3") == "{x^2}^3"
