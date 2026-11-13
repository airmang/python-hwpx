# SPDX-License-Identifier: Apache-2.0
"""Equation box widths against the widths desktop Hangul (Windows) needed.

Hangul on Windows lays a line out with the stored ``<hp:sz>`` width but draws
the equation at its own size: a stored width below what the equation needs lets
the next characters run into it. ``tests/data/equation_windows_needed_widths.json``
holds the needed width of 1,032 synthetic scripts, read off pages drawn by
Hangul 2024 (see the file's description). The estimate must never be narrower.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from hwpx.equation.measure import measure_equation

DATA = Path(__file__).parent / "data" / "equation_windows_needed_widths.json"
EQUATIONS = json.loads(DATA.read_text(encoding="utf-8"))["equations"]


def _ratios() -> dict[str, list[float]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for item in EQUATIONS:
        width = measure_equation(item["script"], base_unit=item["base_unit"]).width
        groups[item["set"]].append(width / item["needed_width"])
    return groups


def test_the_data_covers_the_sets_and_sizes() -> None:
    assert len(EQUATIONS) == 1032
    assert {item["set"] for item in EQUATIONS} == {"glyphs", "pieces", "school", "mac-corpus", "held-out", "sizes"}
    assert {item["base_unit"] for item in EQUATIONS} >= {800, 1000, 1100, 1300, 2000}


def test_no_box_is_narrower_than_hangul_needs() -> None:
    narrow = [
        (item["set"], item["base_unit"], item["script"])
        for item in EQUATIONS
        if measure_equation(item["script"], base_unit=item["base_unit"]).width < item["needed_width"]
    ]
    assert narrow == []


def test_the_boxes_are_not_much_wider_than_needed() -> None:
    groups = _ratios()
    everything = [ratio for ratios in groups.values() for ratio in ratios]
    assert median(everything) < 1.10
    assert mean(everything) < 1.11
    # Equations as long as the ones in a document; single glyphs carry the fixed safety margin.
    for name in ("school", "held-out", "mac-corpus"):
        assert median(groups[name]) < 1.11, name
        assert max(groups[name]) < 1.56, name


def test_the_width_follows_the_stairs_of_the_base_size() -> None:
    # Hangul draws a 1100 equation only 2% wider than a 1000 one, and a 1150 one 13% wider.
    script = "x = {- b +- sqrt {b ^{2} - 4 ac}} over {2 a}"
    at = {unit: measure_equation(script, base_unit=unit).width for unit in (1000, 1100, 1150, 1300)}
    assert at[1000] < at[1100] < at[1000] * 1.05
    assert at[1150] > at[1100] * 1.1
    assert at[1300] > at[1000] * 1.25
