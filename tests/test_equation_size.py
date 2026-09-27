# SPDX-License-Identifier: Apache-2.0
"""Equation boxes are measured from the script's structure.

Hancom lays a page out with the stored ``<hp:sz>`` and ``baseLine`` of an
equation and does not measure it again, so the box has to fit the script.
"""
from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.equation import estimate_equation_size

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
BASE = 1000


def _em(script: str, base: int = BASE) -> tuple[float, float]:
    width, height = estimate_equation_size(script, base_unit=base)
    return width / base, height / base


def _written(script: str, base: int = BASE, size: tuple[int, int] | None = None) -> tuple[int, int, int]:
    doc = HwpxDocument.new()
    doc.shapes.add_equation(script, base_unit=base, size=size)
    (equation,) = [el for section in doc.sections for el in section.element.iter(f"{HP}equation")]
    sz = equation.find(f"{HP}sz")
    return int(sz.get("width")), int(sz.get("height")), int(equation.get("baseLine"))


def test_a_one_line_equation_is_one_base_size_high_with_the_baseline_near_the_bottom() -> None:
    width, height, base_line = _written("x + 1")
    assert 0.9 <= height / BASE <= 1.1
    assert 84 <= base_line <= 88


def test_width_follows_the_characters() -> None:
    assert 0.4 <= _em("7")[0] <= 0.8
    assert 2.8 <= _em("777777")[0] <= 3.6
    assert _em("x = y + z")[0] > _em("xyz")[0]


def test_a_short_equation_is_not_padded_to_a_minimum_width() -> None:
    assert _em("x")[0] < 1.0


def test_a_fraction_is_as_wide_as_its_wider_part_and_two_lines_high() -> None:
    width, height = _em("{a+b} over {2}")
    assert _em("a+b")[0] <= width <= _em("a+b")[0] + 0.8
    assert 2.0 <= height <= 2.6
    assert _written("{a+b} over {2}")[2] < 75


def test_a_superscript_raises_the_top_and_a_subscript_lowers_the_bottom() -> None:
    plain, upper, lower = _written("x"), _written("x^2"), _written("x_1")
    assert upper[1] > plain[1] and lower[1] > plain[1]
    assert upper[2] > lower[2]
    assert upper[0] < plain[0] + 0.6 * BASE


def test_rows_stack() -> None:
    one = _em("a")[1]
    assert _em("pile{a # b # c}")[1] >= 3 * one
    assert _em("matrix{a & b # c & d}")[1] >= 2 * one
    assert _em("a = 1 # b = 2")[1] >= 2 * one


def test_limits_go_under_lim_and_around_sum() -> None:
    width, height, base_line = _written("lim _{x -> 0} f(x)")
    assert height > 1.5 * BASE and base_line < 70
    assert _em("sum _{k=1} ^{n} k")[1] > 2


def test_hancom_symbol_names_count_as_one_symbol() -> None:
    assert _em("A SMALLINTER B")[0] < _em("A SMALLINTR B")[0]


def test_the_box_scales_with_the_base_size() -> None:
    small = _written("{a} over {b}", base=1000)
    large = _written("{a} over {b}", base=2000)
    assert large[0] == pytest.approx(2 * small[0], rel=0.02)
    assert large[1] == pytest.approx(2 * small[1], rel=0.02)
    assert large[2] == small[2]


@pytest.mark.parametrize("script", ["{{{a", "x ^", "over", "matrix{", "left ( a", "}}}", "root 3 of"])
def test_a_script_that_does_not_parse_still_gets_a_box(script: str) -> None:
    width, height, base_line = _written(script)
    assert width > 0 and height > 0 and 1 <= base_line <= 100


def test_an_explicit_size_is_kept_and_the_baseline_still_follows_the_script() -> None:
    measured = _written("{a} over {b}", base=1200)
    width, height, base_line = _written("{a} over {b}", base=1200, size=(18100, 3010))
    assert (width, height) == (18100, 3010)
    assert base_line == measured[2]
    assert estimate_equation_size("{a} over {b}", base_unit=1200) == measured[:2]
