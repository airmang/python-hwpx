# SPDX-License-Identifier: Apache-2.0
"""``add_equation`` refuses LaTeX and unpaired braces (7.0 fix).

It stored ``\\frac{1}{2}`` or ``{a over b`` as given; Hancom showed the text as typed. Hancom's own
equation scripts hold no backslash (none in the 175 equations of the Hancom-saved fixtures).
"""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.equation import latex_to_eqedit
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@pytest.mark.parametrize(
    ("script", "code"),
    [
        (r"\frac{1}{2}", "shape-equation-script-latex"),
        (r"x = \sqrt{2}", "shape-equation-script-latex"),
        ("{a} over {b", "shape-equation-script-unbalanced"),
        ("a} over {b", "shape-equation-script-unbalanced"),
    ],
)
def test_latex_and_unpaired_braces_are_refused_before_anything_is_added(script: str, code: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    before = len(doc.paragraphs)
    for call in (lambda: doc.shapes.add_equation(script), lambda: doc.paragraphs[0].add_equation(script)):
        with pytest.raises(ValueError) as excinfo:
            call()
        assert isinstance(excinfo.value, HwpxValueError)
        assert excinfo.value.code == code
        assert excinfo.value.suggestion
    assert len(doc.paragraphs) == before
    assert not list(doc.sections[0].element.iter(f"{HP}equation"))


def test_the_latex_refusal_points_at_the_converter() -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        HwpxDocument.new().shapes.add_equation(r"\frac{1}{2}")
    assert "latex_to_eqedit" in excinfo.value.suggestion


@pytest.mark.parametrize("script", ["{a} over {b}", "sqrt {2}", "x^2 + y^2 = r^2", "lbrace a rbrace"])
def test_hancom_scripts_are_taken(script: str) -> None:
    HwpxDocument.new().shapes.add_equation(script)


def test_converted_latex_is_taken() -> None:
    HwpxDocument.new().shapes.add_equation(str(latex_to_eqedit(r"\frac{1}{2}")))
