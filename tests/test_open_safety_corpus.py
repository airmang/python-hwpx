from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools.repair import repair_repack

_ROOT = Path(__file__).resolve().parents[1]
_THINKFIRST_REGRESSION = (
    Path.home()
    / "Code"
    / "projects"
    / "ThinkFirst-Studio"
    / "docs"
    / "생각먼저_윤문.hwpx"
)
_SAMPLE_DIRS = (
    _ROOT / "tests" / "fixtures" / "hwpxlib_corpus",
    _ROOT / "shared" / "hwpx" / "fixtures",
    _ROOT / "examples",
)


def _sample_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for directory in _SAMPLE_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.hwpx")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


@pytest.mark.parametrize("sample_path", _sample_paths(), ids=lambda path: path.name)
def test_corpus_sample_save_and_edit_preserve_editor_open_safety(
    sample_path: Path,
    tmp_path: Path,
) -> None:
    initial = validate_editor_open_safety(sample_path)
    assert initial.ok, initial.summary

    document = HwpxDocument.open(sample_path)
    try:
        roundtrip_path = tmp_path / "roundtrip.hwpx"
        document.save_to_path(roundtrip_path)
    finally:
        document.close()

    roundtrip = validate_editor_open_safety(roundtrip_path)
    assert roundtrip.ok, roundtrip.summary

    edited_document = HwpxDocument.open(sample_path)
    try:
        edited_document.add_paragraph("corpus open-safety smoke")
        edited_path = tmp_path / "edited.hwpx"
        edited_document.save_to_path(edited_path)
    finally:
        edited_document.close()

    edited = validate_editor_open_safety(edited_path)
    assert edited.ok, edited.summary


@pytest.mark.skipif(
    not _THINKFIRST_REGRESSION.exists(),
    reason="ThinkFirst-Studio regression fixture is local to the release workspace",
)
def test_thinkfirst_stale_lineseg_regression_repairs_to_editor_open_safe(
    tmp_path: Path,
) -> None:
    initial = validate_editor_open_safety(_THINKFIRST_REGRESSION)

    assert not initial.ok
    assert "stale lineseg textpos" in initial.summary

    repaired_path = tmp_path / "thinkfirst-repaired.hwpx"
    repair_repack(_THINKFIRST_REGRESSION, repaired_path, overwrite=True)

    repaired = validate_editor_open_safety(repaired_path)
    assert repaired.ok, repaired.summary
