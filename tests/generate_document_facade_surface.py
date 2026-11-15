#!/usr/bin/env python3
"""Generate the frozen ``HwpxDocument`` surface snapshots.

Two locks, on purpose (062-engine-surface §8.2):

- ``document_facade_surface.json`` — the **root** surface. 6.0 shrank it from
  102 to 34 by moving 79 names into domain namespaces.
- ``document_legacy_shims.json`` — the 79 moved/demoted names that 6.0 still
  answers from :class:`hwpx._document._legacy._LegacyFacade`, each with its
  replacement and removal version.

The root lock alone would let the move look like a deletion, because its
generator reads ``vars(HwpxDocument)`` and inherited shims never appear there.
The second lock is what keeps the shims counted instead of hidden — it is a
ratchet that may only shrink, and it reaches zero in 7.0.
"""

from __future__ import annotations

import importlib.util
import inspect
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


def legacy_shim_surface() -> dict[str, dict[str, str]]:
    """Every ``_LegacyFacade`` member with the destination it forwards to."""

    from hwpx._document._legacy import _LegacyFacade

    entries: dict[str, dict[str, str]] = {}
    for name, member in vars(_LegacyFacade).items():
        if name.startswith("__"):
            continue
        func = member.fget if isinstance(member, property) else member
        replacement = getattr(func, "__hwpx_moved_to__", None)
        if replacement is None:
            continue
        entry = {
            "kind": "property" if isinstance(member, property) else "method",
            "replacement": replacement,
            "removedIn": getattr(func, "__hwpx_removed_in__", "7.0"),
        }
        if entry["kind"] == "method":
            entry["signature"] = str(inspect.signature(func))
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
    print(f"wrote {SHIM_SNAPSHOT} ({len(shims)} shims, all removed in 7.0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
