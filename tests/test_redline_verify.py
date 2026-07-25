# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.quality.rendering import RenderBackend, UnavailableRenderBackend, VisualReport
from hwpx.tools.redline import author_demo_redline, verify_redline


class _UnavailableOracle:
    """A backend that reports itself unusable and must never be asked to render."""

    def available(self) -> bool:
        return False

    def check(self, before_hwpx, after_hwpx, **_kwargs) -> VisualReport:
        return VisualReport(
            ok=True,
            render_checked=False,
            warnings=["test backend is unavailable; nothing was rendered"],
        )


class _RenderingOracle:
    """A backend that reports a successful render, without owning a renderer.

    Core no longer discovers or drives Hancom, so its own suite cannot produce a
    real render. What core still owns, and what this asserts, is the contract:
    given a backend that renders, the report says so. The real-Hancom gate lives
    in the MCP suite, which owns the transport.
    """

    def available(self) -> bool:
        return True

    def check(self, before_hwpx, after_hwpx, **_kwargs) -> VisualReport:
        return VisualReport(ok=True, render_checked=True, before_page_count=1, after_page_count=1)


def _write_demo_pair(tmp_path: Path) -> tuple[Path, Path]:
    document = HwpxDocument.new()
    document.add_paragraph("baseline")
    before = tmp_path / "before.hwpx"
    after = tmp_path / "after.hwpx"
    document.save_to_path(before)

    author_demo_redline(document)
    document.save_to_path(after)
    return before, after


def test_verify_redline_reports_authored_change_tracking_structure(tmp_path: Path) -> None:
    before, after = _write_demo_pair(tmp_path)

    report = verify_redline(before, after, oracle=_UnavailableOracle())

    assert report["changeCount"] == 2
    assert report["changesByType"]["Insert"] == 1
    assert report["changesByType"]["Delete"] == 1
    assert report["marksLinked"] is True
    assert report["displayEnabled"] is True


def test_verify_redline_degrades_honestly_without_oracle(tmp_path: Path) -> None:
    before, after = _write_demo_pair(tmp_path)

    report = verify_redline(before, after, oracle=_UnavailableOracle())

    assert report["render_checked"] is False
    assert report["opensClean"] is None
    assert report["visual_ok"] is None
    assert report["warnings"]


def test_verify_redline_degrades_honestly_with_no_backend_at_all(tmp_path: Path) -> None:
    """The core-only default: no injected backend means unverified, not passed."""

    before, after = _write_demo_pair(tmp_path)

    report = verify_redline(before, after)

    assert report["render_checked"] is False
    assert report["opensClean"] is None
    assert report["visual_ok"] is None
    assert any("RENDER_BACKEND_UNAVAILABLE" in warning for warning in report["warnings"])


def test_verify_redline_reports_a_render_when_a_backend_performs_one(tmp_path: Path) -> None:
    before, after = _write_demo_pair(tmp_path)

    report = verify_redline(before, after, oracle=_RenderingOracle())

    assert report["render_checked"] is True
    assert report["opensClean"] is True
    assert report["visual_ok"] in {True, False}


def test_core_sentinel_satisfies_the_injected_backend_protocol() -> None:
    assert isinstance(UnavailableRenderBackend(), RenderBackend)
    assert isinstance(_RenderingOracle(), RenderBackend)


def test_verify_redline_corpus_acceptance_scaffold(tmp_path: Path) -> None:
    fixture_paths = [
        Path("tests/fixtures/hwpxlib_corpus/tool__blank.hwpx"),
        Path("tests/fixtures/hwpxlib_corpus/tool__textextractor__multipara.hwpx"),
        Path("tests/fixtures/hwpxlib_corpus/reader_writer__SimpleTable.hwpx"),
    ]
    existing = [path for path in fixture_paths if path.exists()]
    if not existing:
        pytest.skip("no clean HWPX corpus fixtures available")

    for index, source in enumerate(existing):
        document = HwpxDocument.open(source)
        before = tmp_path / f"corpus-{index}-before.hwpx"
        after = tmp_path / f"corpus-{index}-after.hwpx"
        before.write_bytes(source.read_bytes())

        author_demo_redline(document)
        document.save_to_path(after)

        report = verify_redline(before, after, oracle=_UnavailableOracle())
        assert report["changeCount"] >= 2
        assert report["changesByType"]["Insert"] >= 1
        assert report["changesByType"]["Delete"] >= 1
        assert report["marksLinked"] is True
        assert report["displayEnabled"] is True
