# SPDX-License-Identifier: Apache-2.0
"""Authoritative HWPX/OWPML attribute defaults and enum domains.

A single audited table of the non-obvious OWPML defaults a generator gets
wrong silently — values that produce a structurally-valid-but-semantically-broken
document if emitted incorrectly. Centralising them here (instead of scattering
magic literals through writer code) makes them reviewable against the Hancom
oracle and test-lockable against accidental edits.

Provenance / clean-room note
----------------------------
The authoritative source for these constants is Hancom's own public OWPML
reference model, ``hancom-io/hwpx-owpml-model`` (Apache-2.0, © Hancom Inc.),
where each value appears in a C++ class constructor initialiser list or
``enumdef.h``. The values here are derived from reading that *specification*;
no third-party code is copied. Where a value is verified against our own
Hancom-captured corpus that is noted inline.

The four "traps" — defaults that are NOT the naive 0/false:
  * ``paraShape/@snapToGrid``  defaults **true**  (the only true-by-default attr)
  * ``cellSpan/@colSpan|@rowSpan`` default **1**   (not 0)
  * ``run/@charPrIDRef`` unset sentinel = **0xFFFFFFFF** (UINT -1, not 0)
  * ``numbering/@start`` defaults **1**            (not 0)
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# Scalar default "traps"                                                       #
# --------------------------------------------------------------------------- #

#: ``hp:run/@charPrIDRef`` unset value. OWPML RunType initialises this to
#: ``(UINT)-1``; an omitted/unset char-shape reference is this sentinel, NOT 0
#: (id 0 is a real char shape). Stored as a string in XML.
CHAR_PR_ID_REF_UNSET: Final[int] = 0xFFFFFFFF  # 4294967295

#: ``hp:cellSpan/@colSpan`` / ``@rowSpan`` default span. OWPML CellSpan defaults
#: both to 1; a 0 span is invalid and corrupts table layout.
CELL_COL_SPAN_DEFAULT: Final[int] = 1
CELL_ROW_SPAN_DEFAULT: Final[int] = 1

#: ``hh:paraShape/@snapToGrid`` default. The *only* OWPML attribute whose
#: default is ``true``; every other boolean defaults ``false``.
PARA_SHAPE_SNAP_TO_GRID_DEFAULT: Final[bool] = True

#: ``hh:numbering/@start`` default first number. OWPML NumberingType defaults to
#: 1, not 0.
NUMBERING_START_DEFAULT: Final[int] = 1


# --------------------------------------------------------------------------- #
# Enum domains (value -> ordinal, per OWPML enumdef.h)                          #
# Useful as a domain check: a generator emitting an out-of-domain enum value    #
# produces a file Hancom may reject or silently misread.                        #
# --------------------------------------------------------------------------- #

#: ``LSTYPE`` — line-spacing type.
LINE_SPACING_TYPES: Final[frozenset[str]] = frozenset(
    {"PERCENT", "FIXED", "BETWEEN_LINES", "AT_LEAST"}
)

#: ``ALIGNHORZ`` — horizontal paragraph alignment.
HORIZONTAL_ALIGNMENTS: Final[frozenset[str]] = frozenset(
    {"JUSTIFY", "LEFT", "RIGHT", "CENTER", "DISTRIBUTE", "DISTRIBUTE_SPACE"}
)

#: ``ALIGNVERT`` — vertical alignment.
VERTICAL_ALIGNMENTS: Final[frozenset[str]] = frozenset(
    {"BASELINE", "TOP", "CENTER", "BOTTOM"}
)

#: ``hh:fontface/@lang`` values, in ``FONTFACELANGTYPE`` ordinal order.
FONTFACE_LANGS: Final[tuple[str, ...]] = (
    "HANGUL",
    "LATIN",
    "HANJA",
    "JAPANESE",
    "OTHER",
    "SYMBOL",
    "USER",
)

__all__ = [
    "CHAR_PR_ID_REF_UNSET",
    "CELL_COL_SPAN_DEFAULT",
    "CELL_ROW_SPAN_DEFAULT",
    "PARA_SHAPE_SNAP_TO_GRID_DEFAULT",
    "NUMBERING_START_DEFAULT",
    "LINE_SPACING_TYPES",
    "HORIZONTAL_ALIGNMENTS",
    "VERTICAL_ALIGNMENTS",
    "FONTFACE_LANGS",
]
