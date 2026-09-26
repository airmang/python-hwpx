# SPDX-License-Identifier: Apache-2.0
"""Colour reasoning over HWPX ``textColor`` values.

Documents mark meaning with colour — red for an instruction, grey for a hint —
and matching that needs families rather than exact hex, because the same intent
appears as ``#FF0000`` in one file and ``#C00000`` in the next. Deciding *what a
family means* is genre knowledge and belongs to a companion layer; deciding
*which family a hex value falls in* is arithmetic over the colour the format
stores, and belongs here.

It lives in core because two sides need the same answer: ``body_patch`` matches
``charPr`` entries by family when rewriting runs, and the form-guidance scanner
in the application layer classifies instruction text the same way. One
implementation, so a run rewritten as red is the same red the scanner found.
"""

from __future__ import annotations

import re

__all__ = ["color_family", "normalize_color", "rgb_color"]

_HEX_RE = re.compile(r"#([0-9A-Fa-f]{6})")

#: Thresholds are deliberately coarse. They were fitted against real documents
#: where the same semantic colour varies between authors and Hancom versions, so
#: tightening them would split families that readers see as one.
_NEAR_BLACK = 0x30
_NEAR_WHITE = 0xE0
_STRONG = 0x96
_WEAK = 0x78
_GRAY_SPREAD = 0x18


def rgb_color(value: object) -> str:
    """*value* as the ``#RRGGBB`` Hancom writes: the ``#`` may be left out, the digits lower case.

    Anything else is refused with :class:`~hwpx.errors.HwpxValueError`. Hancom reads a colour
    as one hexadecimal number and does not reject the rest, so ``#ABC`` would show as
    ``#000ABC`` (not CSS's ``#AABBCC``), ``red`` as black and ``#12345`` as ``#012345``.
    """
    text = str(value).strip()
    if not _HEX_RE.fullmatch(text if text.startswith("#") else "#" + text):
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"colour {text!r} is not #RRGGBB",
            code="style-color-invalid",
            context={"color": text},
            suggestion="Pass six hexadecimal digits after '#', e.g. '#FF0000'.",
        )
    return "#" + text.lstrip("#").upper()


def normalize_color(value: str | None) -> str | None:
    """:func:`rgb_color`, but ``"none"`` stays ``"none"`` and an empty value is ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "none":
        return "none"
    return rgb_color(text)


def color_family(hex_color: str) -> str:
    """Return the approximate colour family of ``#RRGGBB``.

    Returns one of ``black``, ``white``, ``red``, ``blue``, ``green``, ``gray``,
    or ``other``. Anything unparseable is ``other`` rather than an error: colour
    attributes are frequently absent or malformed in real documents, and a
    classifier that raises would turn a cosmetic gap into a failed edit.
    """

    match = _HEX_RE.fullmatch(hex_color or "")
    if not match:
        return "other"
    red, green, blue = (int(match.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    if red <= _NEAR_BLACK and green <= _NEAR_BLACK and blue <= _NEAR_BLACK:
        return "black"
    if red >= _NEAR_WHITE and green >= _NEAR_WHITE and blue >= _NEAR_WHITE:
        return "white"
    if red >= _STRONG and green <= _WEAK and blue <= _WEAK:
        return "red"
    if blue >= _STRONG and red <= _WEAK:
        return "blue"
    if green >= _STRONG and red <= _WEAK and blue <= _WEAK:
        return "green"
    if abs(red - green) <= _GRAY_SPREAD and abs(green - blue) <= _GRAY_SPREAD:
        return "gray"
    return "other"
