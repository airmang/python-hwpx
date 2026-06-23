# SPDX-License-Identifier: Apache-2.0
"""Edit mask: the page regions an edit was *allowed* to change.

Everything outside the mask must stay pixel-stable between the before/after
renders; a diff outside it is "unexpected" and a fill that paints new ink
outside its slot is "overflow". Regions are stored as **normalised** rectangles
(``x0, y0, x1, y1`` in ``[0, 1]`` of page width/height) so they are independent
of the render DPI.

In Phase A the mask is optional; it becomes load-bearing for FormFit (Phase C),
where each field's slot is the mask for its fill.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Rect = tuple[float, float, float, float]
PixelRect = tuple[int, int, int, int]


@dataclass(frozen=True)
class EditMask:
    """Normalised allowed-change regions, keyed by 0-based page index."""

    regions: dict[int, list[Rect]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any(self.regions.values())

    def rects_for(self, page: int, width: int, height: int) -> list[PixelRect]:
        """Return this page's mask rectangles in pixel coordinates."""

        out: list[PixelRect] = []
        for x0, y0, x1, y1 in self.regions.get(page, []):
            px0 = max(0, min(width, int(round(x0 * width))))
            py0 = max(0, min(height, int(round(y0 * height))))
            px1 = max(0, min(width, int(round(x1 * width))))
            py1 = max(0, min(height, int(round(y1 * height))))
            if px1 > px0 and py1 > py0:
                out.append((px0, py0, px1, py1))
        return out

    @classmethod
    def single(cls, page: int, rect: Rect) -> "EditMask":
        """Convenience: a mask with one rectangle on one page."""

        return cls(regions={page: [rect]})


__all__ = ["EditMask", "Rect", "PixelRect"]
