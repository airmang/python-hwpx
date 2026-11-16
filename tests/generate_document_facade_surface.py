#!/usr/bin/env python3
"""Generate the frozen ``HwpxDocument`` surface snapshots.

Two locks, on purpose (062-engine-surface §8.2):

- ``document_facade_surface.json`` — the **root** surface. 6.0 shrank it from
  102 to 34 by moving 79 names into domain namespaces.
- ``document_legacy_shims.json`` — the 79 moved/demoted names. 6.x answered
  them with a warning; 7.0 removed them, and the lock is now the **guide table**
  (:data:`hwpx._document._legacy.REMOVED_NAMES`): each removed name with where it
  went and a one-line example — what the error a caller gets says.
"""

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
SHIM_SNAPSHOT = TESTS / "data" / "document_legacy_shims.json"


def legacy_shim_surface() -> dict[str, dict[str, object]]:
    """Every removed root name with where it went (the 7.0 guide table)."""

    from hwpx._document._legacy import LEGACY_REMOVED_IN, REMOVED_NAMES

    entries: dict[str, dict[str, object]] = {}
    for name, removed in REMOVED_NAMES.items():
        entry: dict[str, object] = {
            "kind": removed.kind,
            "replacement": removed.replacement,
            "example": removed.example,
            "removedIn": LEGACY_REMOVED_IN,
        }
        if removed.returns:
            entry["returns"] = removed.returns
        if removed.moving:
            entry["movingToAutomation"] = True
        entries[name] = entry
    return entries


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

    shims = legacy_shim_surface()
    SHIM_SNAPSHOT.write_text(
        json.dumps(shims, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {SHIM_SNAPSHOT} ({len(shims)} removed names, guide table)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
