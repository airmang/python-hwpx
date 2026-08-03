# SPDX-License-Identifier: Apache-2.0
"""``BinaryItem``/``PictureRef`` — BinData manifest and body-picture references.

``BinaryItem`` replaces the bare ``str`` item id ``add_image`` returned in 5.x
(design §2.6). ``PictureRef`` replaces the ``list[dict]`` ``picture_references``
returned (design §2.5's list-of-dict table); it is a plain read-only reference
(never settable), so — unlike ``BinaryItem``, a living view without ``to_dict()``
— it follows the pure-result-payload convention (frozen + ``to_dict()``,
``objects/results.py``'s house style) despite living in this module for
domain cohesion with ``BinaryItem``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BinaryItem:
    """Metadata for one embedded binary asset (image, OLE object, …) in ``BinData/``.

    ``str(item)`` is the manifest item id (``"BIN0001"``) — the same string
    ``add_image`` returned directly in 5.x — so ``f"BinData/{item}.png"``-style
    call sites and ``binaryItemIDRef=str(item)`` assignments keep working
    unmodified across the migration window (design §2.6, "이주 완충").
    """

    item_id: str
    format: str
    href: str
    size: int

    def __str__(self) -> str:
        return self.item_id


@dataclass(frozen=True)
class PictureRef:
    """One body ``<hp:pic>``'s reference into ``BinData/``, in document order."""

    picture_index: int
    section_index: int
    binary_item_id_ref: str | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pictureIndex": self.picture_index,
            "sectionIndex": self.section_index,
            "binaryItemIDRef": self.binary_item_id_ref,
            "width": self.width,
            "height": self.height,
        }


__all__ = ["BinaryItem", "PictureRef"]
