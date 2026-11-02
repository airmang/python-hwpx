# SPDX-License-Identifier: Apache-2.0
"""Font-command boundaries observed in Hancom Mac 12.30.0 (6446)."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from hwpx.equation import eqedit_to_latex, estimate_equation_size, latex_to_eqedit

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _rows(name: str) -> list[tuple[str, tuple[str | None, ...]]]:
    with ZipFile(FIXTURES / name) as package:
        section = etree.fromstring(package.read("Contents/section0.xml"))
    return [(element.findtext(HP + "script") or "",
             (element.find(HP + "sz").get("width"), element.find(HP + "sz").get("height"),
              element.get("baseLine"))) for element in section.iter(HP + "equation")]


@pytest.mark.parametrize("base,offset", [(1100, 0), (1000, 38)])
@pytest.mark.parametrize("pair", range(14))
def test_attached_commands_match_hancoms_spaced_reference(base: int, offset: int, pair: int) -> None:
    rows = _rows("equation_attached_font_commands.hwpx")
    (attached, actual), (spaced, reference) = rows[offset + 2 * pair:offset + 2 * pair + 2]
    assert actual == reference  # independent saved geometry, not our estimator
    assert eqedit_to_latex(attached) == eqedit_to_latex(spaced)
    assert estimate_equation_size(attached, base_unit=base) == estimate_equation_size(spaced, base_unit=base)


def test_command_case_is_bounded_by_the_saved_hancom_matrix() -> None:
    rows = _rows("equation_font_command_case.hwpx")
    observed_commands = set()
    for (attached, actual), (spaced, reference) in zip(rows[::2], rows[1::2]):
        assert actual == reference
        assert estimate_equation_size(attached) == estimate_equation_size(spaced)
        if actual[0] == "540":  # x alone; all other case spellings draw the command's letters too
            observed_commands.add(attached[:-1])
            assert eqedit_to_latex(attached) == eqedit_to_latex(spaced)
        else:
            assert eqedit_to_latex(attached) == attached
    assert observed_commands == {"rm", "Rm", "RM", "it", "It", "IT", "bold", "Bold", "BOLD"}


@pytest.mark.parametrize("attached,spaced", [
    ("rmitA", "rm it A"), ("rmboldx", "rm bold x"), ("rmrmA", "rm rm A"),
    ("itab fv", "it ab fv"), ("bit + item", "bit + it em"), ("itself", "it self"),
])
def test_sequential_switches_and_word_prefixes(attached: str, spaced: str) -> None:
    rows = dict(_rows("equation_font_command_boundaries.hwpx"))
    assert rows[attached] == rows[spaced]
    assert eqedit_to_latex(attached) == eqedit_to_latex(spaced)
    assert estimate_equation_size(attached) == estimate_equation_size(spaced)


@pytest.mark.parametrize("identifier", ["rmA", "RmA", "RMA", "rmtriangle", "itself", "Itx", "ITx", "boldness", "Boldx", "BOLDx"])
def test_latex_identifiers_with_command_prefixes_are_quoted(identifier: str) -> None:
    assert latex_to_eqedit(identifier) == f'"{identifier}"'
    assert eqedit_to_latex(f'"{identifier}"') == identifier
    assert eqedit_to_latex(latex_to_eqedit(identifier)) == identifier


@pytest.mark.parametrize("identifier", ["armA", "bit", "rMx", "iTx", "bOlDx"])
def test_internal_prefixes_and_unrecognized_case_stay_identifiers(identifier: str) -> None:
    assert eqedit_to_latex(identifier) == identifier
    assert latex_to_eqedit(identifier) == identifier


@pytest.mark.parametrize("identifier", ["rM", "iT", "bOlD"])
@pytest.mark.parametrize("operator", ["+", "-"])
def test_literal_mixed_case_words_remain_operands_before_signs(identifier: str, operator: str) -> None:
    assert estimate_equation_size(f'{identifier} {operator} x') == estimate_equation_size(
        f'"{identifier}" {operator} x')


def test_long_attached_switch_chain_is_iterative() -> None:
    assert eqedit_to_latex("rm" * 3000 + "A") == r"\mathrm{A}"


@pytest.mark.parametrize("attached,braced", [
    ("x^rmA", "x^{rm A}"), ("x_itx", "x_{it x}"), ("x^boldx", "x^{bold x}"), ("x^rmitA", "x^{rm it A}"),
    ("x^rmA_rmB", "x^{rm A}_{rm B}"), ("sqrt rmA", "sqrt {rm A}"), ("root 3 of rmA", "root 3 of {rm A}"),
    ("x over rmA", "x over {rm A}"), ("rmA over rmB", "{rm A} over {rm B}"), ("binom rmA rmB", "binom {rm A} {rm B}"),
])
def test_a_switch_in_an_operand_measures_the_letter_it_switches(attached: str, braced: str) -> None:
    # The switch is not the operand: measuring it alone left the letter on the outer
    # row and the script, radicand or denominator too short (issue #591 review).
    for base in (1000, 1100):
        assert estimate_equation_size(attached, base_unit=base) == estimate_equation_size(braced, base_unit=base)
