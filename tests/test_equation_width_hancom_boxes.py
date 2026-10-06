# SPDX-License-Identifier: Apache-2.0
"""Equation box widths against the boxes Hancom saved for a synthetic corpus.

``tests/data/equation_hancom_boxes.json`` holds 132 synthetic EqEdit scripts
in 13 kinds (plain text, fractions, roots, scripts, big operators, brackets,
matrices, vectors, overlines, upright text, Greek, degrees and primes, long
equations), each typed into Hancom Office Hangul (macOS) at base sizes 1000,
1100 and 1300 and saved: the values are the ``<hp:sz>`` width and height and
the ``baseLine`` Hancom wrote, read back from the saved documents.

The bounds pin the mean width error the measurer reaches and keep the height
and baseline from getting worse. Hancom's glyph widths do not grow in step
with the base size (a letter is as wide at 1100 as at 1000), while the
measurer scales the whole box with ``baseUnit``; that is why 1100 keeps the
widest error.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import pytest

from hwpx.equation.measure import measure_equation

DATA = Path(__file__).parent / "data" / "equation_hancom_boxes.json"
EQUATIONS = json.loads(DATA.read_text(encoding="utf-8"))["equations"]


def _errors(key: str) -> dict[object, list[tuple[float, float, int]]]:
    groups: dict[object, list[tuple[float, float, int]]] = defaultdict(list)
    for item in EQUATIONS:
        size = measure_equation(item["script"], base_unit=item["base_unit"])
        groups[item[key]].append((
            abs(size.width / item["width"] - 1),
            abs(size.height / item["height"] - 1),
            abs(size.base_line - item["base_line"]),
        ))
    return groups


def test_the_corpus_covers_each_script_at_three_base_sizes() -> None:
    by_script: dict[str, set[int]] = defaultdict(set)
    for item in EQUATIONS:
        by_script[item["script"]].add(item["base_unit"])
    assert len(by_script) == 132
    assert all(sizes == {1000, 1100, 1300} for sizes in by_script.values())


def test_the_mean_width_error_is_small_at_every_base_size() -> None:
    groups = _errors("base_unit")
    widths = {unit: mean(e[0] for e in errors) for unit, errors in groups.items()}
    assert mean(e[0] for errors in groups.values() for e in errors) < 0.04, widths
    assert widths[1000] < 0.035 and widths[1300] < 0.03 and widths[1100] < 0.07, widths


@pytest.mark.parametrize("category", sorted({item["category"] for item in EQUATIONS}))
def test_the_mean_width_error_is_small_for_every_kind_of_equation(category: str) -> None:
    errors = _errors("category")[category]
    assert mean(e[0] for e in errors) < 0.055


def test_no_width_is_far_off() -> None:
    worst = max(e[0] for errors in _errors("base_unit").values() for e in errors)
    assert worst < 0.22


def test_height_and_baseline_stay_close() -> None:
    errors = [e for group in _errors("base_unit").values() for e in group]
    assert mean(e[1] for e in errors) < 0.027
    assert mean(e[2] for e in errors) < 1.0
