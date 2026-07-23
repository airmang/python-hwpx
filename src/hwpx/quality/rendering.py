# SPDX-License-Identifier: Apache-2.0
"""Renderer-neutral contracts for the core save gate.

The core library owns the decision shape and the injection seam, not discovery
of a Hancom installation or an office-automation transport. Companion
applications provide a :class:`RenderBackend`; an unconfigured core-only
installation degrades honestly to ``render_checked=False``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

Rect = tuple[float, float, float, float]
PixelRect = tuple[int, int, int, int]


@dataclass(frozen=True)
class EditMask:
    """Normalized allowed-change regions, keyed by 0-based page index."""

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


@dataclass
class VisualReport:
    """Renderer-neutral judgement for a before/after or single-document check."""

    ok: bool
    render_checked: bool
    original_render: str | None = None
    output_render: str | None = None
    diff_image: str | None = None
    unexpected_diff_outside_mask: bool = False
    overlap_detected: bool = False
    overflow_detected: bool = False
    table_break_detected: bool = False
    page_count_changed: bool | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    max_diff_ratio: float | None = None
    before_page_count: int | None = None
    after_page_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class RenderBackend(Protocol):
    """Injected visual-verification backend used by :class:`SavePipeline`."""

    def available(self) -> bool:
        """Return whether this backend can perform a real render now."""
        ...

    def check(
        self,
        before_hwpx: str | None,
        after_hwpx: str,
        *,
        edit_mask: EditMask | None = None,
        diff_eps: float = 0.005,
        dpi: int = 150,
        work_dir: str | None = None,
        keep_artifacts: bool = False,
    ) -> VisualReport:
        """Render and judge one output without exposing transport details."""
        ...


class UnavailableRenderBackend:
    """Core-only sentinel: renderer discovery belongs to a companion layer."""

    def available(self) -> bool:
        return False

    def check(
        self,
        before_hwpx: str | None,
        after_hwpx: str,
        *,
        edit_mask: EditMask | None = None,
        diff_eps: float = 0.005,
        dpi: int = 150,
        work_dir: str | None = None,
        keep_artifacts: bool = False,
    ) -> VisualReport:
        return VisualReport(
            ok=True,
            render_checked=False,
            warnings=[
                "RENDER_BACKEND_UNAVAILABLE: no renderer was injected; "
                "visual_complete is unverified, not confirmed."
            ],
        )


def unavailable_render_backend(**_options: Any) -> UnavailableRenderBackend:
    """Default factory used by a standalone core installation."""

    return UnavailableRenderBackend()


__all__ = [
    "EditMask",
    "PixelRect",
    "Rect",
    "RenderBackend",
    "UnavailableRenderBackend",
    "VisualReport",
    "unavailable_render_backend",
]
