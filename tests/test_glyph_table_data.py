# SPDX-License-Identifier: Apache-2.0
"""The glyph tables the package ships are the readable source's, value for value.

``hwpx.form_fit._glyph_table`` reads ``_glyph_table.json.gz``; ``scripts/glyph_table_source.py`` is what people
edit and ``scripts/build_glyph_table.py`` writes the one from the other. A table that differs here means the
data file was not rebuilt after an edit: run ``python scripts/build_glyph_table.py``.
"""

from __future__ import annotations

import build_glyph_table
import pytest

from hwpx.form_fit import _glyph_table

SOURCE = build_glyph_table.load_source()
REBUILD = "run python scripts/build_glyph_table.py"


def test_the_module_holds_the_tables_the_source_defines_and_no_others() -> None:
    shipped = {name for name in vars(_glyph_table) if name.isupper() and not name.startswith("_")}
    assert shipped == set(SOURCE) == set(build_glyph_table.TABLES)


@pytest.mark.parametrize("name", list(build_glyph_table.TABLES))
def test_every_value_of_a_table_is_the_sources(name: str) -> None:
    shipped, source = getattr(_glyph_table, name), SOURCE[name]
    assert type(shipped) is dict
    assert list(shipped) == list(source), f"{name}: faces differ or are in another order; {REBUILD}"
    compared = 0
    for face, expected in source.items():
        got = shipped[face]
        assert type(got) is type(expected), f"{name}[{face!r}]"
        if isinstance(expected, dict):
            # Every key and value, in the source's order, with the source's types (an int is not a bool or float).
            assert list(got.items()) == list(expected.items()), f"{name}[{face!r}]; {REBUILD}"
            assert all(type(k) is int and type(v) is type(expected[k]) for k, v in got.items()), f"{name}[{face!r}]"
            compared += len(expected)
        else:
            assert got == expected, f"{name}[{face!r}]; {REBUILD}"
            if isinstance(expected, tuple):
                assert [type(item) for item in got] == [type(item) for item in expected], f"{name}[{face!r}]"
            compared += 1
    assert compared > 0
    assert shipped == source


def test_the_data_file_is_what_the_build_script_writes_from_the_source() -> None:
    assert build_glyph_table.stored() == build_glyph_table.encode(SOURCE), REBUILD
    assert build_glyph_table.main(["--check"]) == 0


def test_the_build_script_refuses_a_value_the_loader_would_not_give_back(tmp_path) -> None:
    for name, face, value in (("UNITS_PER_EM", "바탕", 1024.0), ("VERTICAL_METRICS", "바탕", [879, 145]),
                              ("ADVANCES", "바탕", {"500": "a"}), ("LINE_HEIGHTS", "바탕", {2600: True})):
        broken = {**SOURCE, name: {**SOURCE[name], face: value}}
        with pytest.raises(SystemExit):
            build_glyph_table.encode(broken)
