# SPDX-License-Identifier: Apache-2.0
"""``BinaryItem`` — one BinData manifest entry.

``BinaryItem`` replaces the bare ``str`` item id ``add_image`` returned in 5.x
(design §2.6). The body pictures that use an item are read as model objects
(``doc.media.pictures`` → ``Picture``, its ``item_id``); 6.x's ``PictureRef``
for them is gone in 7.0.
"""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["BinaryItem"]
