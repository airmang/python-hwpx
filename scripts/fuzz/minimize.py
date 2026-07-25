# SPDX-License-Identifier: Apache-2.0
"""Failure minimization for seeded HWPX fuzz scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from .catalog import normalize_scenario


def minimize_scenario(
    scenario: Mapping[str, Any],
    fails: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Greedily remove operations while *fails(candidate)* remains true."""

    current = normalize_scenario(scenario)
    changed = True
    while changed:
        changed = False
        operations = list(current.get("operations") or ())
        if len(operations) <= 1:
            break
        for index in range(len(operations) - 1, 0, -1):
            candidate = deepcopy(current)
            candidate["operations"] = operations[:index] + operations[index + 1 :]
            candidate = normalize_scenario(candidate)
            if fails(candidate):
                current = candidate
                changed = True
                break
    return normalize_scenario(current)
