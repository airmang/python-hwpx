"""Heuristic visual detectors for the baseline measurement.

Two signals, in priority order:

  1. ``diff_ratio(a, b)`` — fraction of ink pixels that differ between two page
     renders (lineseg ON vs OFF). This is the PRIMARY signal. If Hancom always
     re-layouts on open, the ON and OFF pages render identically and
     ``diff_ratio`` ~ 0, which means retaining a stale ``lineSegArray`` is
     HARMLESS (the engine's blanket strip is belt-and-braces). A large diff
     means the cache actually changed what Hancom drew.

  2. ``overlap_score(img)`` — cheap corroboration that looks for collapsed text
     bands (contiguous ink rows with no separating whitespace), a signature of
     overlapping glyphs. Heuristic, not authoritative; use it to explain a diff,
     not to replace it.

Requires Pillow + numpy. On macOS run via:
    uv run --with pillow --with numpy python ...
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def _ink_mask(img: Image.Image, threshold: int = 160) -> np.ndarray:
    """Boolean mask, True where the pixel is dark (ink)."""
    gray = np.asarray(img.convert("L"))
    return gray < threshold


def _match_size(a: Image.Image, b: Image.Image) -> tuple[Image.Image, Image.Image]:
    if a.size != b.size:
        width = min(a.size[0], b.size[0])
        height = min(a.size[1], b.size[1])
        a = a.crop((0, 0, width, height))
        b = b.crop((0, 0, width, height))
    return a, b


def diff_ratio(a: Image.Image, b: Image.Image) -> float:
    """Fraction of pixels whose ink/no-ink state differs between a and b."""
    a, b = _match_size(a, b)
    mask_a = _ink_mask(a)
    mask_b = _ink_mask(b)
    diff = np.logical_xor(mask_a, mask_b)
    return float(diff.sum()) / float(diff.size or 1)


def overlap_score(img: Image.Image) -> dict:
    """Row-band analysis. A band much taller than the median text line suggests
    collapsed / overlapping lines."""
    mask = _ink_mask(img)
    row_density = mask.mean(axis=1)
    inked_rows = row_density > 0.01

    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, inked in enumerate(inked_rows):
        if inked and start is None:
            start = i
        elif not inked and start is not None:
            bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, len(inked_rows)))

    heights = [end - begin for begin, end in bands]
    median_h = float(np.median(heights)) if heights else 0.0
    max_h = float(max(heights)) if heights else 0.0
    return {
        "ink_ratio": float(mask.mean()),
        "num_bands": len(bands),
        "median_band_height": median_h,
        "max_band_height": max_h,
        # >~3 means one band is far taller than a normal line of text.
        "tall_band_ratio": (max_h / median_h) if median_h else 0.0,
    }
