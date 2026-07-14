# SPDX-License-Identifier: Apache-2.0
"""Deterministic, full-page visual QA over page-only PNG inputs."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .fixture_corpus import FixtureCase, sha256_file
from .qa_contracts import (
    DefectCategory,
    Evidence,
    FindingSeverity,
    NormalizedBBox,
    PageVerdict,
    Provenance,
    VisualFinding,
    VisualVerdict,
)


DETECTOR_VERSION = "1.0.0"
_INK_THRESHOLD = 160


@dataclass(frozen=True)
class _Signal:
    detector_id: str
    category: DefectCategory
    severity: FindingSeverity
    confidence: float
    bbox: NormalizedBBox
    message: str
    details: dict[str, float]


Detector = Callable[[object], _Signal | None]


def _mask(image):
    import numpy as np

    return np.asarray(image.convert("L")) < _INK_THRESHOLD


def _blank_page(image) -> _Signal | None:
    ink_ratio = float(_mask(image).mean())
    if ink_ratio >= 0.0005:
        return None
    return _Signal(
        "blank-page",
        DefectCategory.UNEXPECTED_BLANK_PAGE,
        FindingSeverity.CRITICAL,
        0.99,
        NormalizedBBox.whole_page(),
        "Page contains no meaningful rendered ink.",
        {"inkRatio": ink_ratio},
    )


def _edge_clipping(image) -> _Signal | None:
    import numpy as np

    mask = _mask(image)
    height, width = mask.shape
    margin = max(2, int(round(min(width, height) * 0.002)))
    edge = np.zeros_like(mask)
    edge[:margin, :] = mask[:margin, :]
    edge[-margin:, :] = mask[-margin:, :]
    edge[:, :margin] = mask[:, :margin]
    edge[:, -margin:] = mask[:, -margin:]
    ys, xs = np.where(edge)
    if not len(xs):
        return None
    pad = max(2, margin * 2)
    bbox = _pixel_bbox(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1, width, height, pad)
    return _Signal(
        "edge-clipping",
        DefectCategory.TEXT_CLIPPING_OVERLAP,
        FindingSeverity.CRITICAL,
        0.98,
        bbox,
        "Rendered ink touches the page edge and may be clipped.",
        {"edgeInkPixels": float(len(xs)), "edgeMarginPixels": float(margin)},
    )


def _dense_overlap_band(image) -> _Signal | None:
    import numpy as np

    mask = _mask(image)
    height, width = mask.shape
    density = mask.mean(axis=1)
    dense = density >= 0.20
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for row, value in enumerate(dense):
        if value and start is None:
            start = row
        elif not value and start is not None:
            bands.append((start, row))
            start = None
    if start is not None:
        bands.append((start, height))
    min_height = max(14, int(round(height * 0.018)))
    candidates = [(begin, end) for begin, end in bands if end - begin >= min_height]
    if not candidates:
        return None
    begin, end = max(candidates, key=lambda item: item[1] - item[0])
    band_mask = mask[begin:end, :]
    _ys, xs = np.where(band_mask)
    if not len(xs):
        return None
    bbox = _pixel_bbox(int(xs.min()), begin, int(xs.max()) + 1, end, width, height, 4)
    ratio = (end - begin) / max(1, height)
    return _Signal(
        "dense-overlap-band",
        DefectCategory.TEXT_CLIPPING_OVERLAP,
        FindingSeverity.CRITICAL,
        min(0.99, 0.90 + ratio),
        bbox,
        "Abnormally tall dense ink band suggests collapsed or overlapping text.",
        {"bandHeightRatio": ratio, "maxRowDensity": float(density[begin:end].max())},
    )


def _implausible_density(image) -> _Signal | None:
    ink_ratio = float(_mask(image).mean())
    if ink_ratio <= 0.35:
        return None
    return _Signal(
        "page-density",
        DefectCategory.IMPLAUSIBLE_WHITESPACE_DENSITY,
        FindingSeverity.ERROR,
        min(0.99, 0.75 + ink_ratio / 4),
        NormalizedBBox.whole_page(),
        "Page ink density is visually implausible.",
        {"inkRatio": ink_ratio},
    )


DETECTORS: tuple[Detector, ...] = (
    _blank_page,
    _edge_clipping,
    _dense_overlap_band,
    _implausible_density,
)


def inspect_page_png(path: str | Path, *, page: int) -> PageVerdict:
    """Inspect one entire PNG and return a hash-bound verdict."""

    from PIL import Image

    image_path = Path(path)
    page_hash = sha256_file(image_path)
    with Image.open(image_path) as source:
        source.verify()
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    findings = [_finding_from_signal(signal, image, page, page_hash) for detector in DETECTORS if (signal := detector(image))]
    return PageVerdict.build(page=page, page_sha256=page_hash, findings=findings)


def inspect_page_set(
    pages: dict[int, str | Path],
    *,
    expected_pages: Iterable[int],
    assurance: str,
    render_checked: bool,
) -> VisualVerdict:
    """Inspect all supplied pages; unreadable or absent expected pages fail closed."""

    verdicts: list[PageVerdict] = []
    for page, path in sorted(pages.items()):
        try:
            verdicts.append(inspect_page_png(path, page=page))
        except (OSError, ValueError):
            # Omitting this page makes VisualVerdict mark it missing/unverified.
            continue
    return VisualVerdict.build(
        expected_pages=expected_pages,
        pages=verdicts,
        assurance=assurance,
        render_checked=render_checked,
    )


def inspect_fixture_case(case: FixtureCase) -> VisualVerdict:
    """Inspect a fixture case without ever claiming real-Hancom assurance."""

    return inspect_page_set(
        {page.page: page.path for page in case.pages},
        expected_pages=(page.page for page in case.pages),
        assurance="fixture",
        render_checked=False,
    )


def _pixel_bbox(x0: int, y0: int, x1: int, y1: int, width: int, height: int, pad: int) -> NormalizedBBox:
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width, x1 + pad)
    y1 = min(height, y1 + pad)
    return NormalizedBBox(x0 / width, y0 / height, x1 / width, y1 / height)


def _finding_from_signal(signal: _Signal, image, page: int, page_hash: str) -> VisualFinding:
    width, height = image.size
    box = signal.bbox
    pixel_box = (
        int(box.x0 * width),
        int(box.y0 * height),
        max(1, int(box.x1 * width)),
        max(1, int(box.y1 * height)),
    )
    crop = image.crop(pixel_box)
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG", optimize=False)
    crop_hash = hashlib.sha256(buffer.getvalue()).hexdigest()
    stable = f"{page_hash}:{page}:{signal.detector_id}:{signal.category.value}:{box}"
    finding_id = "vf-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
    return VisualFinding(
        finding_id=finding_id,
        page=page,
        bbox=box,
        category=signal.category,
        severity=signal.severity,
        confidence=round(signal.confidence, 6),
        evidence=Evidence(page_hash, crop_hash, box),
        provenance=Provenance(signal.detector_id, DETECTOR_VERSION, details=signal.details),
        message=signal.message,
    )


__all__ = [
    "DETECTOR_VERSION",
    "DETECTORS",
    "inspect_page_png",
    "inspect_page_set",
    "inspect_fixture_case",
]
