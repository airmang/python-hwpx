# SPDX-License-Identifier: Apache-2.0
"""The size estimate reads scripts as the converter does, and ``%`` is wide.

A box narrower than Hangul needs lets the next characters overlap the equation.
Hangul saved ``95%`` 1650 wide at baseUnit 900 (36 public equations) where it
saved ``95`` 900 wide; the estimate used to give 1307.
"""
from __future__ import annotations

import pytest

from hwpx.equation import estimate_equation_size
from hwpx.equation.measure import measure_equation
from hwpx.errors import HwpxValueError


def test_percent_is_as_wide_as_hangul_saved_it() -> None:
    assert measure_equation("95%", base_unit=900).width >= 1650
    assert measure_equation("95``%`", base_unit=1100).width >= 2361
    assert measure_equation('"80%"', base_unit=1000).width > measure_equation('"80"', base_unit=1000).width + 700


def test_root_without_of_is_measured_as_a_square_root() -> None:
    assert measure_equation("root5", base_unit=900).width >= 1503
    assert measure_equation("root5").width == measure_equation("sqrt 5").width
    # With ``of`` the first atom is the index: a long one overhangs the sign, a short one sits in its notch.
    assert measure_equation("root {123} of {x}").width > measure_equation("sqrt {x}").width
    assert measure_equation("root {123} of {x}").width < measure_equation("sqrt {123 x}").width


def test_a_script_after_the_denominator_is_measured_on_it() -> None:
    # x²/a² is one fraction, as wide as its numerator or denominator, not a fraction and a script.
    assert measure_equation("x^2 over a^2").width == measure_equation("{x^2} over {a^2}").width


def test_glued_keywords_are_measured_as_symbols() -> None:
    assert measure_equation("1 overa").height == measure_equation("1 over a").height
    assert measure_equation("tantheta").width == measure_equation("tan theta").width


@pytest.mark.parametrize("base_unit", [0, -100, True, 1.5])
def test_a_base_size_that_is_not_a_positive_int_is_refused(base_unit: object) -> None:
    with pytest.raises(HwpxValueError) as caught:
        estimate_equation_size("x", base_unit=base_unit)  # type: ignore[arg-type]
    assert caught.value.code == "shape-equation-base-unit-value"
    assert isinstance(caught.value, ValueError)
