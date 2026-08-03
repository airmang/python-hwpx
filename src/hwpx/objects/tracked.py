# SPDX-License-Identifier: Apache-2.0
"""``TrackedChange``/``TrackedReplacement`` — redline (track-changes) results.

Replaces the bare ``int`` change id ``add_track_change``/``add_tracked_insert``/
``add_tracked_delete`` returned, and the ``tuple[int, int]`` ``add_tracked_replace``
returned, in 5.x (design §2.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..model import Paragraph


@dataclass(frozen=True)
class TrackedChange:
    """One tracked-change (redline) header entry.

    Deliberately has **no** ``__int__``. The 5.x contract returned a bare
    ``int`` change id, and call sites leaned on it flowing straight into
    anything that wanted a number. An implicit ``int(change)`` fallback would
    quietly resurrect that — the same "looks like it worked" shape a prior
    train removed elsewhere — so reading ``.change_id`` is one attribute
    access away and nothing coerces silently.

    ``paragraph`` is ``None`` for a change minted through the low-level
    ``doc.tracking.add_change`` primitive (design table row 39), which only
    registers header metadata and is not yet anchored to any body text; it is
    always set for the redline verbs that anchor a mark (``insert``/``delete``).
    """

    change_id: int
    kind: str
    author: str
    date: str | None
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "changeId": self.change_id,
            "kind": self.kind,
            "author": self.author,
            "date": self.date,
        }


@dataclass(frozen=True)
class TrackedReplacement:
    """The delete+insert pair minted by ``doc.tracking.replace``.

    5.x returned ``tuple[int, int]`` and nothing in the type said which slot
    held which id — callers had to remember the order. Named fields remove
    the guesswork.
    """

    delete: TrackedChange
    insert: TrackedChange

    def to_dict(self) -> dict[str, Any]:
        return {"delete": self.delete.to_dict(), "insert": self.insert.to_dict()}


__all__ = ["TrackedChange", "TrackedReplacement"]
