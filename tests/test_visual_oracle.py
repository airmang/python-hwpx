# SPDX-License-Identifier: Apache-2.0
"""Tests for the Phase-A VisualComplete gate (``hwpx.visual``).

Two tiers, matching the assurance model:

* **Portable** (run everywhere): the degrade contract, the data models, and the
  pixel detectors on synthetic images. These never need Hancom; the detector
  tests skip only if the imaging stack (numpy/Pillow) is absent.
* **Oracle smoke** (Windows + Hancom + imaging stack): a real COM render of a
  built doc against itself. Skipped automatically off-oracle.

The full corpus-verdict and overflow acceptance run against genuine Hancom-saved
documents (which can't be committed) and are verified out-of-tree on the Windows
box; see ``scripts/visualcomplete-baseline/README.md``.
"""
from __future__ import annotations

import pytest

from hwpx.visual import EditMask, RenderOracle, VisualReport, visual_check
from hwpx.visual import detectors, diff


class _UnavailableOracle:
    """Stand-in for an off-Windows environment (no Hancom)."""

    def available(self) -> bool:
        return False

    def render_many(self, pairs):  # pragma: no cover - must never be called
        raise AssertionError("render_many must not run when oracle is unavailable")


# --------------------------------------------------------------------------- #
# Degrade contract (portable)
# --------------------------------------------------------------------------- #
def test_visual_check_degrades_without_oracle() -> None:
    report = visual_check("before.hwpx", "after.hwpx", oracle=_UnavailableOracle())

    assert isinstance(report, VisualReport)
    assert report.render_checked is False
    assert report.ok is True  # structural degrade: optimistic-but-labelled
    assert report.warnings and "RENDER_ORACLE_UNAVAILABLE" in report.warnings[0]
    assert report.errors == []


def test_visual_check_degrades_when_imaging_stack_missing(monkeypatch) -> None:
    # Oracle reports available, but the scoring deps are absent -> still degrade,
    # never raise, never silently claim a visual pass.
    monkeypatch.setattr(detectors, "imaging_available", lambda: False)
    monkeypatch.setattr(diff, "pymupdf_available", lambda: False)

    class _AvailableOracle(_UnavailableOracle):
        def available(self) -> bool:
            return True

    report = visual_check(None, "after.hwpx", oracle=_AvailableOracle())
    assert report.render_checked is False
    assert report.ok is True
    assert any("dependencies" in w for w in report.warnings)


def test_visual_report_to_dict_has_contract_fields() -> None:
    report = VisualReport(ok=True, render_checked=False)
    data = report.to_dict()
    for key in (
        "ok", "render_checked", "original_render", "output_render", "diff_image",
        "unexpected_diff_outside_mask", "overlap_detected", "overflow_detected",
        "table_break_detected", "page_count_changed", "warnings", "errors",
    ):
        assert key in data


# --------------------------------------------------------------------------- #
# EditMask (portable)
# --------------------------------------------------------------------------- #
def test_edit_mask_normalised_to_pixels() -> None:
    mask = EditMask.single(0, (0.1, 0.2, 0.5, 0.6))
    assert not mask.is_empty
    assert mask.rects_for(0, 200, 100) == [(20, 20, 100, 60)]
    assert mask.rects_for(1, 200, 100) == []  # other pages untouched
    assert EditMask().is_empty


# --------------------------------------------------------------------------- #
# Pixel detectors on synthetic images (portable where numpy/Pillow exist)
# --------------------------------------------------------------------------- #
def _img(array):
    from PIL import Image

    return Image.fromarray(array.astype("uint8")).convert("RGB")


def _lines(heights, *, gap=5, width=100, x0=10, x1=90):
    import numpy as np

    total = sum(heights) + gap * (len(heights) + 1)
    arr = np.full((total, width), 255)
    y = gap
    for h in heights:
        arr[y : y + h, x0:x1] = 0
        y += h + gap
    return _img(arr)


def test_diff_ratio_and_masking() -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    import numpy as np

    white = _img(np.full((100, 100), 255))
    boxed = np.full((100, 100), 255)
    boxed[40:60, 40:60] = 0  # 20x20 ink block = 400/10000 = 0.04
    boxed_img = _img(boxed)

    assert detectors.diff_ratio(white, white) == 0.0
    assert detectors.diff_ratio(white, boxed_img) == pytest.approx(0.04, abs=1e-6)

    rects = [(40, 40, 60, 60)]
    assert detectors.diff_ratio_outside_mask(white, boxed_img, rects) == 0.0
    assert detectors.new_ink_ratio_outside_mask(white, boxed_img, []) == pytest.approx(0.04, abs=1e-6)
    assert detectors.new_ink_ratio_outside_mask(white, boxed_img, rects) == 0.0


def test_overlap_score_flags_collapsed_band() -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")

    normal = detectors.overlap_score(_lines([3, 3, 3, 3, 3]))
    collapsed = detectors.overlap_score(_lines([3, 3, 3, 3, 30]))

    assert normal["tall_band_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert collapsed["tall_band_ratio"] >= 3.0
    assert collapsed["tall_band_ratio"] > normal["tall_band_ratio"] + 1.0


# --------------------------------------------------------------------------- #
# Oracle smoke (Windows + Hancom + imaging stack only)
# --------------------------------------------------------------------------- #
def _oracle_ready() -> bool:
    return (
        RenderOracle().available()
        and detectors.imaging_available()
        and diff.pymupdf_available()
    )


@pytest.mark.skipif(not _oracle_ready(), reason="Hancom COM + imaging stack required")
def test_visual_check_oracle_smoke_identical_doc(tmp_path) -> None:
    from hwpx import HwpxDocument

    document = HwpxDocument.new()
    document.add_paragraph("VisualComplete 스모크 테스트 본문")
    data = document.to_bytes()
    before = tmp_path / "before.hwpx"
    after = tmp_path / "after.hwpx"
    before.write_bytes(data)
    after.write_bytes(data)

    report = visual_check(str(before), str(after), oracle=RenderOracle())

    assert report.render_checked is True
    assert report.ok is True
    assert report.max_diff_ratio == 0.0
    assert report.overlap_detected is False
    assert report.page_count_changed is False
