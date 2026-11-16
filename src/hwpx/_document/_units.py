# SPDX-License-Identifier: Apache-2.0
"""Shared HWPUNIT conversion helpers for the HwpxDocument owner modules."""

from __future__ import annotations


_HWP_UNITS_PER_MM = 7200 / 25.4
_HWP_UNITS_PER_PT = 100


def _mm_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_MM)


def _pt_to_hwp_units(value: float) -> int:
    return round(value * _HWP_UNITS_PER_PT)


def _line_width_mm_to_hwp_units(value: object) -> int:
    """A picture or shape line width in mm (``line_width_mm=``, 7.0) as the HWPUNIT the XML holds.

    The model's conversion (:func:`hwpx.oxml.shape_position.line_width_units`): the default 0.12 mm is
    the 33 HWPUNIT 6.x wrote for ``line_width=33``, counted at 283 HWPUNIT per mm and cut to a whole
    unit, so the documents 6.x made come out the same. A value that is not a finite number of
    millimetres, or is below 0, is refused (``shape-picture-border-value``).
    """

    from ..oxml.shape_position import line_width_units

    return line_width_units(value)


def _border_width_mm_text(value: object, *, argument: str) -> str:
    """A border or column line width in mm (``border_width_mm=``, ``separator_width_mm=``, 7.0) as the
    ``hc:LineWidth`` text the XML holds (0.12 → ``"0.12 mm"``, 1 → ``"1.0 mm"``), as
    ``table.set_borders(border_width_mm=)`` writes it. Only Hancom's widths are taken; any other value --
    a width between two listed ones, a string such as ``"0.12 mm"`` -- is refused before the document
    changes (``style-line-width-invalid``, :func:`hwpx.oxml.utils.line_width_text`)."""

    from ..oxml.utils import line_width_text

    return line_width_text(value, argument=argument)
