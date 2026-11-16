# SPDX-License-Identifier: Apache-2.0
"""Shared HWPUNIT conversion helpers for the HwpxDocument owner modules."""

from __future__ import annotations

import math


_HWP_UNITS_PER_MM = 7200 / 25.4
_HWP_UNITS_PER_PT = 100


def _mm_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_MM)


def _pt_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_PT)


def _line_width_mm_to_hwp_units(value: object) -> int:
    """A picture or shape line width in mm (``line_width_mm=``, 7.0) as the HWPUNIT the XML holds.

    The default 0.12 mm is the 33 HWPUNIT 6.x wrote for ``line_width=33``: the width is counted
    at 283 HWPUNIT per mm and cut to a whole unit, so the documents 6.x made come out the same.
    A value that is not a finite number of millimetres, or is below 0, is refused
    (``shape-picture-border-value``).
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"line_width_mm must be a width in mm of 0 or more, got {value!r}",
            code="shape-picture-border-value",
            context={"line_width_mm": repr(value)},
            suggestion="Pass the border width in mm, e.g. line_width_mm=0.12 (0 draws no border).",
        )
    return int(value * 283)
