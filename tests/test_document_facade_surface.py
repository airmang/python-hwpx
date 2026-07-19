"""Characterization lock for the ``HwpxDocument`` public facade surface.

S-084 decomposes ``hwpx/document.py`` into domain owner modules behind the
facade. This test freezes the public API — names, member kinds, and exact
signatures — against a checked-in snapshot so the decomposition provably
changes nothing a caller can see. Private helpers are deliberately excluded:
moving them between modules is the point of the refactor.

Regenerate the snapshot ONLY for an intentional, reviewed API change:

    .venv/bin/python tests/generate_document_facade_surface.py
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument

SNAPSHOT = Path(__file__).parent / "data" / "document_facade_surface.json"

# Dunders that are part of the supported facade contract.
_PUBLIC_DUNDERS = {"__init__", "__repr__", "__enter__", "__exit__"}


def live_surface() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for name, member in vars(HwpxDocument).items():
        if name.startswith("_") and name not in _PUBLIC_DUNDERS:
            continue
        if isinstance(member, property):
            entries[name] = {"kind": "property"}
        elif isinstance(member, staticmethod):
            entries[name] = {
                "kind": "staticmethod",
                "signature": str(inspect.signature(member.__func__)),
            }
        elif isinstance(member, classmethod):
            entries[name] = {
                "kind": "classmethod",
                "signature": str(inspect.signature(member.__func__)),
            }
        elif inspect.isfunction(member):
            entries[name] = {
                "kind": "method",
                "signature": str(inspect.signature(member)),
            }
        else:
            entries[name] = {"kind": type(member).__name__}
    return entries


def test_document_facade_public_surface_is_frozen() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    live = live_surface()
    missing = sorted(set(expected) - set(live))
    added = sorted(set(live) - set(expected))
    changed = sorted(
        name
        for name in set(expected) & set(live)
        if expected[name] != live[name]
    )
    assert (missing, added, changed) == ([], [], []), (
        f"public facade surface drifted: missing={missing} added={added} "
        f"changed={changed}"
    )


def test_document_facade_snapshot_is_not_empty() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    # 124 defs total in the pre-decomposition module; the public subset must
    # stay a substantial lock, not a silently narrowed one.
    assert len(expected) >= 90
