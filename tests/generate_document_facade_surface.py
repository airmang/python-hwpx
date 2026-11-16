#!/usr/bin/env python3
"""Generate ``document_legacy_shims.json``: the table of the root names 7.0 removed.

6.0 moved 79 root names into domain namespaces. 6.x answered them with a warning;
7.0 removed them, and the lock is now the **guide table**
(:data:`hwpx._document._legacy.REMOVED_NAMES`): each removed name with where it
went and a one-line example — what the error a caller gets says.

The root surface itself (the old ``document_facade_surface.json``) is part of the
public-surface lock since 7.0: ``python scripts/public_surface_lock.py check --update``
(``tests/data/public_surface.json``, ``root`` layer).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "src"))

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
    shims = legacy_shim_surface()
    SHIM_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SHIM_SNAPSHOT.write_text(
        json.dumps(shims, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {SHIM_SNAPSHOT} ({len(shims)} removed names, guide table)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
