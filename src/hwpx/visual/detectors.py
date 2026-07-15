# SPDX-License-Identifier: Apache-2.0
"""Pixel-level visual detectors (ported from the baseline measurement harness).

``diff_ratio`` and ``overlap_score`` are byte-for-byte the same heuristics the
one-off ``scripts/visualcomplete-baseline/overlap_detect.py`` used, so the gate
reproduces the harness verdicts on the measured corpus. Added here:

* mask-aware variants (diff / new-ink restricted to outside the edit mask),
* a diff-image generator for report artifacts.

``numpy`` and ``Pillow`` are imported lazily so importing this module (and the
whole :mod:`hwpx.visual` package) never requires the imaging stack; callers must
gate on :func:`imaging_available` and degrade otherwise.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL import Image

# Pixels darker than this (0-255 grayscale) count as "ink".
_INK_THRESHOLD = 160
# Row is "inked" when at least this fraction of its pixels are ink.
_ROW_INK_FRACTION = 0.01


def imaging_available() -> bool:
    """True when numpy + Pillow can be imported (required by every detector)."""

    try:  # pragma: no cover - trivial import probe
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:
        return False
    return True


def _ink_mask(img: "Image.Image", threshold: int = _INK_THRESHOLD):
    import numpy as np

    gray = np.asarray(img.convert("L"))
    return gray < threshold


def _match_size(a: "Image.Image", b: "Image.Image"):
    if a.size != b.size:
        width = min(a.size[0], b.size[0])
        height = min(a.size[1], b.size[1])
        a = a.crop((0, 0, width, height))
        b = b.crop((0, 0, width, height))
    return a, b


def _zero_rects(mask, rects) -> None:
    """In-place: clear the given pixel rectangles in a boolean ink/diff mask."""

    for x0, y0, x1, y1 in rects:
        mask[y0:y1, x0:x1] = False


def diff_ratio(a: "Image.Image", b: "Image.Image") -> float:
    """Fraction of pixels whose ink/no-ink state differs between ``a`` and ``b``."""

    import numpy as np

    a, b = _match_size(a, b)
    diff = np.logical_xor(_ink_mask(a), _ink_mask(b))
    return float(diff.sum()) / float(diff.size or 1)


def diff_ratio_outside_mask(a: "Image.Image", b: "Image.Image", rects) -> float:
    """Like :func:`diff_ratio` but ignoring pixels inside ``rects`` (allowed region)."""

    import numpy as np

    a, b = _match_size(a, b)
    diff = np.logical_xor(_ink_mask(a), _ink_mask(b))
    if rects:
        _zero_rects(diff, rects)
    return float(diff.sum()) / float(diff.size or 1)


def new_ink_ratio_outside_mask(before: "Image.Image", after: "Image.Image", rects) -> float:
    """Fraction of pixels that gained ink in ``after`` *outside* the mask.

    This is the "the fill spilled out of its slot" signal: ink present in the
    output but not the original, in a region the edit was not allowed to paint.
    """


    before, after = _match_size(before, after)
    new_ink = _ink_mask(after) & ~_ink_mask(before)
    if rects:
        _zero_rects(new_ink, rects)
    return float(new_ink.sum()) / float(new_ink.size or 1)


def overlap_score(img: "Image.Image") -> dict[str, float]:
    """Row-band analysis. A band far taller than the median line suggests
    collapsed / overlapping lines (글자 겹침)."""

    import numpy as np

    mask = _ink_mask(img)
    row_density = mask.mean(axis=1)
    inked_rows = row_density > _ROW_INK_FRACTION

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
        "num_bands": float(len(bands)),
        "median_band_height": median_h,
        "max_band_height": max_h,
        "tall_band_ratio": (max_h / median_h) if median_h else 0.0,
    }


def make_diff_image(a: "Image.Image", b: "Image.Image") -> "Image.Image":
    """Render the ink XOR of two pages as a black-on-white diff image."""

    import numpy as np
    from PIL import Image

    a, b = _match_size(a, b)
    diff = np.logical_xor(_ink_mask(a), _ink_mask(b))
    out = np.where(diff, 0, 255).astype("uint8")
    return Image.fromarray(out)  # 2-D uint8 -> mode "L" inferred


__all__ = [
    "imaging_available",
    "diff_ratio",
    "diff_ratio_outside_mask",
    "new_ink_ratio_outside_mask",
    "overlap_score",
    "make_diff_image",
]
