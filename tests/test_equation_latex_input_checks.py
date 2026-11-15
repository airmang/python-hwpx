# SPDX-License-Identifier: Apache-2.0
"""LaTeX the writer refuses, keeps or newly accepts.

Malformed LaTeX (``\\frac{1}``, ``\\sqrt{}``, ``x^^2``) drew junk in desktop
Hangul 2024 (``{1} over {}``, an empty root), so it is refused. Spaces inside
``\\text{...}`` are kept. Common spellings with a clear meaning are accepted;
those without a verified EqEdit spelling are refused with an alternative.
"""
from __future__ import annotations

import pytest

from hwpx.equation import eqedit_to_latex, latex_to_eqedit
from hwpx.equation.authoring import UnsupportedLatexError


@pytest.mark.parametrize(
    "latex",
    [r"\frac{1}", r"\frac", r"x^^2", r"x^2^3", r"x_1_2", r"\sqrt{}", r"\sqrt[3]{}", r"\vec", r"x_", r"x^",
     r"\frac{}{2}", r"\binom{n}", r"\mathbf{}", r"\text{50%}", r"\text{a_b}"],
)
def test_malformed_latex_is_refused(latex: str) -> None:
    with pytest.raises(UnsupportedLatexError):
        latex_to_eqedit(latex)


@pytest.mark.parametrize(("latex", "script"), [("x^2_3", "x ^{2} _{3}"), ("{}_n C_r", "{} _{n} C _{r}"), (r"\boxed{}", "box {}")])
def test_wellformed_scripts_and_an_empty_box_still_convert(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


@pytest.mark.parametrize(
    ("latex", "script"),
    [
        (r"x \geq 2 \text{ 또는 } x \leq -1", 'x geq 2 {rm " 또는 " it} x leq - 1'),
        (r"\text{단, } a > 0", '{rm "단, " it} a > 0'),
        (r"\text{a  b}", '{rm "a  b" it}'),
        (r"\text{50\%}", '{rm "50%" it}'),
        (r"\text{a\_b}", '{rm "a_b" it}'),
        (r"\text{\$5}", '{rm "$5" it}'),
        (r"\text{a\textasciicircum{}b}", '{rm "a^b" it}'),
    ],
)
def test_text_keeps_its_spaces_and_escaped_characters(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


def test_a_script_after_a_fraction_stays_on_the_fraction() -> None:
    # Hancom sets ``{a} over {b} ^{2}`` as a/b²; LaTeX \frac{a}{b}^2 squares the whole fraction.
    assert latex_to_eqedit(r"\frac{a}{b}^2") == "{{a} over {b}} ^{2}"
    assert latex_to_eqedit(r"\binom{n}{r}_1") == "{{n} choose {r}} _{1}"
    assert latex_to_eqedit(r"\frac{a}{b} + 1") == "{a} over {b} + 1"


@pytest.mark.parametrize(
    ("latex", "script"),
    [
        ("2×3÷4±1", "2 times 3 div 4 +- 1"),
        ("x≤y≥z≠w", "x leq y geq z neq w"),
        ("x→∞", "x -> infty"),
        ("a−b·c", "a - b cdot c"),
        ("1,…,n", "1 , ldots , n"),
        ("△ABC", "TRIANGLE ABC"),
        ("∠A", "angle A"),
        ("l⊥m", "l BOT m"),
        ("√2", "sqrt {2}"),
        ("30°", "30 ^{circ}"),
        ("㉠+⑴", "㉠ + ⑴"),
        (r"\displaystyle\sum\limits_{k=1}^{n} k", "sum _{k = 1} ^{n} k"),
        (r"\Big[ x \Big]", "[ x ]"),
        (r"\ell + \hbar", "ell + hbar"),
        (r"f \colon X \to Y", "f : X -> Y"),
        (r"a \equiv b \pmod{m}", "a equiv b ~~( mod ~{m} )"),
        (r"\operatorname{sgn}(x)", '{rm "sgn" it} ( x )'),
        (r"\operatorname{sin} x", "sin x"),
        (r"p \longrightarrow q", "p -> q"),
        (r"a \not= b", "a neq b"),
        (r"a \not\in A", "a notin A"),
        (r"\lfloor x \rfloor", "LEFT lfloor x RIGHT rfloor"),
        (r"\langle a, b \rangle", "LEFT < a , b RIGHT >"),
        (r"\vert x \vert + \lvert y \rvert", "| x | + | y |"),
        (r"\|v\|", "VERT v VERT"),
        (r"\nearrow", "NEARROW"),
    ],
)
def test_common_spellings_are_accepted(latex: str, script: str) -> None:
    assert latex_to_eqedit(latex) == script


@pytest.mark.parametrize(
    ("latex", "hint"),
    [
        (r"\lfloor x", r"\left\lfloor"),
        (r"x \rfloor", r"\left\lfloor"),
        (r"A \setminus B", "A - B"),
        (r"\not\equiv", r"\neq"),
        (r"\mathbb{R}", r"\mathrm{R}"),
        (r"\widehat{x}", r"\hat"),
        (r"\square", r"\boxed"),
    ],
)
def test_refusals_name_an_alternative(latex: str, hint: str) -> None:
    with pytest.raises(UnsupportedLatexError, match=None) as caught:
        latex_to_eqedit(latex)
    assert hint in str(caught.value)


def test_private_use_characters_are_still_refused() -> None:
    with pytest.raises(UnsupportedLatexError):
        latex_to_eqedit("A  B")


def test_new_spellings_read_back_to_the_same_script() -> None:
    for latex in (r"\ell", r"\hbar", r"\|v\|", r"\nearrow", r"\searrow", "a ≤ b"):
        script = latex_to_eqedit(latex)
        assert latex_to_eqedit(eqedit_to_latex(script)) == script
