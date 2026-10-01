# SPDX-License-Identifier: Apache-2.0
"""Equation boxes for keyword scripts against the boxes Hancom saved.

Each fixture is one equation paragraph cut out of a document that Hancom
Office Hangul (macOS) saved: the section keeps Hancom's first paragraph and
the equation paragraph byte for byte, so ``<hp:sz>`` and ``baseLine`` are the
values Hancom wrote. The preview image was dropped and author/date metadata
blanked; nothing else was changed. All fixtures use ``baseUnit="1100"``.

The scripts use keyword names (``choose``, ``BINOM``, ``lbrace``, ``dyad``,
``theta``, ``prime``, ``DEG``, ``root``, ``pmatrix``) that the measurer used
to count as their letters. The tolerance is wider than the gap the measurer
leaves on plain text (about 15% wide at this base size), and far tighter than
the 1.4x to 4.3x the letters gave.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from hwpx.equation.measure import measure_equation

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
CASES = {
    "equation_lbrace_set.hwpx": "lbrace x | x > 0 rbrace",
    "equation_choose_n_r.hwpx": "{n} choose {r}",
    "equation_choose_sums.hwpx": "{n+1} choose {k-1}",
    "equation_binom_upper.hwpx": "BINOM {n} {r}",
    "equation_dyad_ab.hwpx": "dyad {AB}",
    "equation_theta.hwpx": "theta",
    "equation_prime_keyword.hwpx": "f prime (x)",
    "equation_degree.hwpx": "30 DEG",
    "equation_root_index.hwpx": "root {3} of {8}",
    "equation_pmatrix.hwpx": "pmatrix {1 & 0 # 0 & 1}",
}
WIDTH_RANGE = (0.9, 1.3)
HEIGHT_RANGE = (0.93, 1.07)
BASE_LINE_SLACK = 3


def _saved_equation(name: str) -> tuple[str, int, int, int, int]:
    with zipfile.ZipFile(FIXTURES / name) as archive:
        version = archive.read("version.xml").decode("utf-8")
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert 'application="Hancom Office Hangul"' in version
    paragraphs = re.findall(r"<hp:p [^>]*>.*?</hp:p>(?=<hp:p |</hs:sec>)", section, re.DOTALL)
    assert paragraphs and all("<hp:linesegarray>" in p for p in paragraphs)
    (equation,) = re.findall(r"<hp:equation [^>]*>.*?</hp:equation>", section, re.DOTALL)
    size = re.search(r'<hp:sz width="(\d+)"[^>]* height="(\d+)"', equation)
    script = re.search(r"<hp:script>(.*?)</hp:script>", equation, re.DOTALL)
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', equation.split(">", 1)[0]))
    assert size and script
    text = script.group(1).replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return text, int(attrs["baseUnit"]), int(size.group(1)), int(size.group(2)), int(attrs["baseLine"])


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_keyword_script_is_measured_close_to_the_box_hancom_saved(name: str) -> None:
    script, base_unit, width, height, base_line = _saved_equation(name)
    assert script == CASES[name]
    measured = measure_equation(script, base_unit=base_unit)
    assert WIDTH_RANGE[0] <= measured.width / width <= WIDTH_RANGE[1], (measured, width)
    assert HEIGHT_RANGE[0] <= measured.height / height <= HEIGHT_RANGE[1], (measured, height)
    assert abs(measured.base_line - base_line) <= BASE_LINE_SLACK, (measured, base_line)


def test_choose_and_binom_are_read_in_any_case() -> None:
    stacked = measure_equation("{n} atop {r}")
    for script in ("{n} choose {r}", "{n} CHOOSE {r}", "binom {n} {r}", "BINOM {n} {r}"):
        assert measure_equation(script) == stacked
    assert stacked.height < measure_equation("{n} over {r}").height


def test_keyword_glyphs_are_one_symbol_wide() -> None:
    bar = measure_equation("x | x").width
    assert measure_equation("x LINE x").width == bar
    assert measure_equation("x vert x").width == bar
    assert measure_equation("x VERT x").width > bar
    assert measure_equation("lbrace x rbrace").width == measure_equation("LBRACE x RBRACE").width
    assert measure_equation("lbrace x rbrace").width < measure_equation("lbracex rbracex").width / 2
    assert measure_equation("f prime").width == measure_equation("f '").width
    assert measure_equation("dyad {AB}") == measure_equation("vec {AB}")


def test_a_short_root_index_sits_in_the_sign() -> None:
    assert measure_equation("root {3} of {8}") == measure_equation("sqrt {8}")
    assert measure_equation("root {n+1} of {8}").width > measure_equation("sqrt {8}").width


def test_delimiters_add_no_height_but_scripts_follow_a_tall_base() -> None:
    assert measure_equation("LEFT ( x RIGHT )").height == measure_equation("x").height
    fraction = measure_equation("{1} over {2}")
    assert measure_equation("LEFT ( {1} over {2} RIGHT )").height == fraction.height
    assert measure_equation("LEFT ( {1} over {2} RIGHT ) ^{n}").height > fraction.height
