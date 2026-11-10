#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write FormFit's glyph tables as the data file the package ships.

The tables are kept as readable Python in ``scripts/glyph_table_source.py`` (about 450 KiB and growing), which
does not ship. The package carries them as ``src/hwpx/form_fit/_glyph_table.json.gz`` (gzip-compressed JSON,
about 65 KiB) so that no shipped file passes 256 KiB, the most a Claude plugin directory reads of one file
(hwpx-plugins issue 66). ``hwpx.form_fit._glyph_table`` reads the data file when it is imported.

    python scripts/build_glyph_table.py           # after editing the source: rewrite the data file
    python scripts/build_glyph_table.py --check   # exit 1 when the data file does not hold the source's tables

The data file is compared by content, not by bytes (zlib builds compress differently), and is rewritten only
when its content differs. ``tests/test_glyph_table_data.py`` compares every table with the source.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "glyph_table_source.py"
DATA = ROOT / "src" / "hwpx" / "form_fit" / "_glyph_table.json.gz"
SCHEMA = "python-hwpx.glyph-table/v1"
#: The tables, in the order the data file holds them, and the shape of each face's value.
TABLES: dict[str, str] = {
    "UNITS_PER_EM": "int",
    "FALLBACK": "str",
    "VERTICAL_METRICS": "pair",
    "LINE_HEIGHTS": "int-by-int",
    "HANGUL_ADVANCES": "str-by-int",
    "ADVANCES": "str-by-int",
    "ITALIC_ADVANCES": "str-by-int",
    "BOLD_ITALIC_ADVANCES": "str-by-int",
}


def load_source(path: pathlib.Path = SOURCE) -> dict[str, dict[str, Any]]:
    """The tables of the source module, by name."""

    spec = importlib.util.spec_from_file_location("_glyph_table_source", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {name for name in vars(module) if name.isupper() and not name.startswith("_")}
    if names != set(TABLES):
        raise SystemExit(f"{path.name} defines {sorted(names)}; build_glyph_table.TABLES lists {sorted(TABLES)}")
    return {name: getattr(module, name) for name in TABLES}


def _checked(name: str, kind: str, face: object, value: object) -> Any:
    """*value* as the data file holds it, refusing anything the loader would not give back the same."""

    def fail() -> SystemExit:
        return SystemExit(f"{name}[{face!r}] = {value!r:.80} is not {kind}")

    if type(face) is not str:
        raise fail()
    if kind in ("int", "str"):
        if type(value) is not (int if kind == "int" else str):
            raise fail()
        return value
    if kind == "pair":
        if type(value) is not tuple or len(value) != 2 or any(type(item) is not int for item in value):
            raise fail()
        return list(value)
    inner = int if kind == "int-by-int" else str
    if type(value) is not dict or any(type(k) is not int or type(v) is not inner for k, v in value.items()):
        raise fail()
    return [[k, v] for k, v in value.items()]


def encode(tables: dict[str, dict[str, Any]]) -> bytes:
    """The JSON text of *tables*: every table a list of ``[face, value]`` in the source's order."""

    payload = {
        "schema": SCHEMA,
        "tables": {name: [[face, _checked(name, kind, face, value)] for face, value in tables[name].items()]
                   for name, kind in TABLES.items()},
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def stored(path: pathlib.Path = DATA) -> bytes | None:
    """The JSON text the data file holds, or None when it is missing or unreadable."""

    try:
        return gzip.decompress(path.read_bytes())
    except (OSError, EOFError, gzip.BadGzipFile):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only compare the data file with the source")
    args = parser.parse_args(argv)
    text = encode(load_source())
    if stored() == text:
        print(f"[OK] {DATA.relative_to(ROOT).as_posix()} holds the source's tables ({DATA.stat().st_size} bytes)")
        return 0
    if args.check:
        print(f"[FAIL] {DATA.relative_to(ROOT).as_posix()} differs from {SOURCE.relative_to(ROOT).as_posix()}; "
              "run python scripts/build_glyph_table.py")
        return 1
    DATA.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
    print(f"[OK] wrote {DATA.relative_to(ROOT).as_posix()} ({DATA.stat().st_size} bytes, {len(text)} of JSON)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
