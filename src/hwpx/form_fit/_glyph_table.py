# SPDX-License-Identifier: Apache-2.0
"""Design advances of glyphs beyond ``measure._GLYPHS``, per face, and the faces' line metrics.

The tables are data: the KS X 1001 symbols, the full-width forms and the common Unicode blocks of each face,
read from the fonts' ``hmtx`` and ``cmap`` tables or measured as Hancom Office 2024 lays them out. They are
kept beside this module as ``_glyph_table.json.gz`` (gzip-compressed JSON, read once when this module is
imported), because as Python source they pass the size a plugin directory reads of one file. The readable
source, with where every face's values come from, is ``scripts/glyph_table_source.py`` in the python-hwpx
repository; ``scripts/build_glyph_table.py`` writes the data file from it and
``tests/test_glyph_table_data.py`` compares the two table by table.
"""

from __future__ import annotations

import gzip
import json
from importlib import resources
from typing import Any

_DATA = "_glyph_table.json.gz"
_SCHEMA = "python-hwpx.glyph-table/v1"


def _load() -> dict[str, list[list[Any]]]:
    """The tables of the data file: every one a list of ``[face, value]`` in the source's order."""

    raw = resources.files(__package__).joinpath(_DATA).read_bytes()
    payload = json.loads(gzip.decompress(raw).decode("utf-8"))
    if payload.get("schema") != _SCHEMA:
        raise ImportError(f"{_DATA} has schema {payload.get('schema')!r}, not {_SCHEMA!r}")
    tables: dict[str, list[list[Any]]] = payload["tables"]
    return tables


def _by_key(table: list[list[Any]]) -> dict[str, dict[int, Any]]:
    """A table whose faces each hold ``[key, value]`` rows, as a dictionary of dictionaries."""

    return {face: {key: value for key, value in rows} for face, rows in table}


_TABLES = _load()

#: Units per em of each face below.
UNITS_PER_EM: dict[str, int] = {face: units for face, units in _TABLES["UNITS_PER_EM"]}

#: The face Hancom takes a glyph from when a face does not have it.
FALLBACK: dict[str, str] = {face: other for face, other in _TABLES["FALLBACK"]}

#: Each text face's ascent and descent (OS/2 usWinAscent, usWinDescent) in its units per em: a paragraph
#: taking its line height from the font (``hh:paraPr@fontLineHeight``) makes its lines that tall.
VERTICAL_METRICS: dict[str, tuple[int, int]] = {
    face: (ascent, descent) for face, (ascent, descent) in _TABLES["VERTICAL_METRICS"]
}

#: The line heights Hancom Office 2024 lays a line of one face and height out at, in a paragraph taking its line
#: height from the font, where they differ from its ascent and descent each rounded up: height -> line height.
#: Other heights take the formula.
LINE_HEIGHTS: dict[str, dict[int, int]] = _by_key(_TABLES["LINE_HEIGHTS"])

#: Per face, the Hangul syllables whose design advance differs from the face's other syllables
#: (``measure._DESIGN``): design advance -> those syllables.
HANGUL_ADVANCES: dict[str, dict[int, str]] = _by_key(_TABLES["HANGUL_ADVANCES"])

#: Per face, design advance -> the glyphs the face lays out at that advance.
ADVANCES: dict[str, dict[int, str]] = _by_key(_TABLES["ADVANCES"])

#: Advances Hancom Office 2024 lays italic glyphs out at in the faces it draws italic in faces of their own
#: (in each face's units per em), where they differ from the regular ones.
ITALIC_ADVANCES: dict[str, dict[int, str]] = _by_key(_TABLES["ITALIC_ADVANCES"])

#: Advances Hancom Office 2024 lays bold italic glyphs out at where they differ from the italic ones and a bold
#: italic glyph is not widened as a bold one is (see ``measure._BOLD_WIDER_FACES``).
BOLD_ITALIC_ADVANCES: dict[str, dict[int, str]] = _by_key(_TABLES["BOLD_ITALIC_ADVANCES"])

del _TABLES
