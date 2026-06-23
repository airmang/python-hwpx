# SPDX-License-Identifier: Apache-2.0
"""Rasterize Hancom-exported PDFs and turn page pairs into visual signals.

This is the scoring half of the gate: render PDF pages to images (``pymupdf``,
imported lazily) and run the :mod:`hwpx.visual.detectors` over them. The
before/after comparison reproduces the baseline harness's verdict logic
(``diff_ratio`` ≥ eps, relative tall-band overlap, page-count change), extended
with edit-mask awareness for FormFit.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import detectors
from .masks import EditMask

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL import Image

# A page whose tallest ink band is this many times the median line height is a
# collapse signature; only flagged when the *after* page is meaningfully worse
# than the *before* page (relative, like the baseline harness).
_TALL_BAND_ABS = 3.0
_TALL_BAND_REL = 1.0


def pymupdf_available() -> bool:
    try:  # pragma: no cover - trivial import probe
        import fitz  # noqa: F401
    except Exception:
        return False
    return True


def render_pdf_to_images(pdf_path: str | Path, dpi: int = 150) -> list["Image.Image"]:
    """Rasterize every page of ``pdf_path`` to a list of RGB ``PIL.Image``."""

    import fitz  # pymupdf
    from PIL import Image

    pages: list[Image.Image] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return pages


def _page_overlap(before_ov: dict[str, float], after_ov: dict[str, float]) -> bool:
    return (
        after_ov["tall_band_ratio"] >= _TALL_BAND_ABS
        and after_ov["tall_band_ratio"] > before_ov["tall_band_ratio"] + _TALL_BAND_REL
    )


def compare_renders(
    before_pdf: str | Path,
    after_pdf: str | Path,
    *,
    edit_mask: EditMask | None = None,
    diff_eps: float = 0.005,
    dpi: int = 150,
    diff_image_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compare two rendered PDFs and return the visual signal dictionary."""

    before_pages = render_pdf_to_images(before_pdf, dpi)
    after_pages = render_pdf_to_images(after_pdf, dpi)
    page_count = min(len(before_pages), len(after_pages))

    max_full_diff = 0.0
    max_outside_diff = 0.0
    max_new_ink_outside = 0.0
    overlap_flag = False
    worst_page = 0

    for i in range(page_count):
        before_img, after_img = before_pages[i], after_pages[i]
        full = detectors.diff_ratio(before_img, after_img)
        if full > max_full_diff:
            max_full_diff = full
            worst_page = i

        if edit_mask is not None and not edit_mask.is_empty:
            rects = edit_mask.rects_for(i, before_img.size[0], before_img.size[1])
            max_outside_diff = max(
                max_outside_diff, detectors.diff_ratio_outside_mask(before_img, after_img, rects)
            )
            max_new_ink_outside = max(
                max_new_ink_outside,
                detectors.new_ink_ratio_outside_mask(before_img, after_img, rects),
            )

        if _page_overlap(detectors.overlap_score(before_img), detectors.overlap_score(after_img)):
            overlap_flag = True

    page_count_changed = len(before_pages) != len(after_pages)
    has_mask = edit_mask is not None and not edit_mask.is_empty

    effective_diff = max_outside_diff if has_mask else max_full_diff
    unexpected_diff_outside_mask = effective_diff >= diff_eps
    # Overflow: the fill painted ink outside its slot, or content spilled onto
    # extra pages. Without a mask, the page-growth proxy is the available signal.
    overflow_detected = len(after_pages) > len(before_pages)
    if has_mask:
        overflow_detected = overflow_detected or (max_new_ink_outside >= diff_eps)

    diff_image_out: str | None = None
    if diff_image_path is not None and page_count > 0:
        image = detectors.make_diff_image(before_pages[worst_page], after_pages[worst_page])
        image.save(str(diff_image_path))
        diff_image_out = str(diff_image_path)

    return {
        "render_checked": True,
        "page_count": page_count,
        "before_page_count": len(before_pages),
        "after_page_count": len(after_pages),
        "page_count_changed": page_count_changed,
        "max_diff_ratio": round(max_full_diff, 6),
        "max_diff_outside_mask": round(max_outside_diff, 6),
        "max_new_ink_outside_mask": round(max_new_ink_outside, 6),
        "unexpected_diff_outside_mask": unexpected_diff_outside_mask,
        "overlap_detected": overlap_flag,
        "overflow_detected": overflow_detected,
        "diff_image": diff_image_out,
    }


def analyze_single(after_pdf: str | Path, *, dpi: int = 150) -> dict[str, Any]:
    """Single-render structural-visual pass (new-doc generation, no before).

    Without a reference there is no faithful overlap baseline, so this only
    confirms the doc rasterizes and reports its page count. Overlap/overflow
    judgement for new docs is a Phase-E concern; here it stays conservative.
    """

    after_pages = render_pdf_to_images(after_pdf, dpi)
    return {
        "render_checked": True,
        "before_page_count": None,
        "after_page_count": len(after_pages),
        "page_count_changed": None,
        "max_diff_ratio": None,
        "unexpected_diff_outside_mask": False,
        "overlap_detected": False,
        "overflow_detected": False,
        "diff_image": None,
    }


__all__ = ["pymupdf_available", "render_pdf_to_images", "compare_renders", "analyze_single"]
