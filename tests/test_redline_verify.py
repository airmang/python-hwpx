# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.tools.redline import author_demo_redline, verify_redline
from hwpx.visual import MacHancomOracle, detectors, diff, resolve_oracle


class _UnavailableOracle:
    def available(self) -> bool:
        return False

    def render_many(self, pairs):  # pragma: no cover - must never be called
        raise AssertionError("render_many must not run when oracle is unavailable")


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


def _real_oracle_ready() -> bool:
    oracle = resolve_oracle()
    if isinstance(oracle, MacHancomOracle) and not os.environ.get("HWPX_MAC_ORACLE_SMOKE"):
        return False
    return oracle.available() and detectors.imaging_available() and diff.pymupdf_available()


@pytest.mark.skipif(
    not _real_oracle_ready(),
    reason="Hancom render oracle + imaging stack required",
)
def test_verify_redline_real_render_gate(tmp_path: Path) -> None:
    before, after = _write_demo_pair(tmp_path)

    report = verify_redline(before, after, oracle=resolve_oracle())

    assert report["render_checked"] is True
    assert report["opensClean"] is True
    assert report["visual_ok"] in {True, False}


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
