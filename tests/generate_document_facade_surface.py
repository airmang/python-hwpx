#!/usr/bin/env python3
"""Generate the frozen ``HwpxDocument`` public-surface snapshot (S-084)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "src"))

_spec = importlib.util.spec_from_file_location(
    "test_document_facade_surface", TESTS / "test_document_facade_surface.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

SNAPSHOT = TESTS / "data" / "document_facade_surface.json"


def main() -> int:
    surface = _module.live_surface()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps(surface, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    kinds: dict[str, int] = {}
    for entry in surface.values():
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    print(f"wrote {SNAPSHOT} ({len(surface)} members: {kinds})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
