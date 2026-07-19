# SPDX-License-Identifier: Apache-2.0
"""Shared HWPUNIT conversion helpers for the HwpxDocument owner modules (S-084)."""

from __future__ import annotations


_HWP_UNITS_PER_MM = 7200 / 25.4
_HWP_UNITS_PER_PT = 100


def _mm_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_MM)


def _pt_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_PT)
