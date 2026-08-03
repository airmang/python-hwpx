"""Characterization lock for the ``HwpxDocument`` public facade surface.

The facade decomposition moves ``hwpx/document.py`` behavior into domain owners behind the
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
    """락이 조용히 좁아지지 않았는지 확인한다.

    6.0 전에는 루트 락 하나뿐이라 하한이 ``>= 90``이었다. 6.0은 루트를 34로
    **의도적으로** 줄이고 나머지 79를 shim 락으로 옮겼다. 그래서 하한은 두
    락의 합에 건다 — 5.x가 공개했던 이름의 총수는 줄지 않았고(이동은 제거가
    아니다), 줄어든다면 그것이 이 검사가 잡아야 할 사건이다.
    """

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    shims = json.loads(
        (SNAPSHOT.parent / "document_legacy_shims.json").read_text(encoding="utf-8")
    )
    assert len(expected) + len(shims) >= 90
    # 루트 자체는 6.0 예산 안에 있어야 한다(설계서 §1.4).
    assert len(expected) <= 35
