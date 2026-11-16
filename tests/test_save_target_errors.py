# SPDX-License-Identifier: Apache-2.0
"""Save failures name the target and what to do; bad modes and odd extensions are not silent."""

from __future__ import annotations

import os
import stat
import sys
import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx._document import persistence
from hwpx.errors import HwpxError, HwpxValueError, SaveTargetError


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


def test_a_missing_folder_is_named_and_still_a_file_not_found_error(tmp_path: Path) -> None:
    target = tmp_path / "없는폴더" / "out.hwpx"
    with pytest.raises(FileNotFoundError) as excinfo:
        _doc().save(target)

    error = excinfo.value
    assert isinstance(error, SaveTargetError) and isinstance(error, HwpxError)
    assert error.code == "save-target-folder-missing"
    assert str(target.parent) in str(error) and ".tmp" not in str(error)
    assert error.suggestion
    assert not target.parent.exists()


def test_a_folder_at_the_path_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "dir.hwpx"
    target.mkdir()
    with pytest.raises(OSError) as excinfo:
        _doc().save(target)

    assert isinstance(excinfo.value, SaveTargetError)
    assert excinfo.value.code == "save-target-is-folder"
    assert ".tmp" not in str(excinfo.value)


@pytest.mark.skipif(sys.platform != "win32", reason="a read-only file blocks replacing it on Windows only")
def test_a_read_only_target_is_a_permission_error_naming_the_target(tmp_path: Path) -> None:
    target = tmp_path / "ro.hwpx"
    target.write_bytes(b"old")
    os.chmod(target, stat.S_IREAD)
    try:
        with pytest.raises(PermissionError) as excinfo:
            _doc().save(target)
    finally:
        os.chmod(target, stat.S_IWRITE)

    assert isinstance(excinfo.value, SaveTargetError)
    assert excinfo.value.code == "save-target-denied"
    assert str(target) in str(excinfo.value) and ".tmp" not in str(excinfo.value)
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.tmp"))


def test_a_save_with_a_quality_gate_names_a_missing_folder_too(tmp_path: Path) -> None:
    from hwpx import QualityPolicy

    with pytest.raises(SaveTargetError, match="does not exist"):
        _doc().save(tmp_path / "nope" / "out.hwpx", quality=QualityPolicy.transparent())


@pytest.mark.parametrize(
    "kwargs",
    [{"mode": "fast"}, {"mode": None}, {"fallback": "ignore"}],
)
def test_an_unknown_mode_or_fallback_is_refused(tmp_path: Path, kwargs: dict) -> None:
    target = tmp_path / "m.hwpx"
    with pytest.raises(HwpxValueError) as excinfo:
        _doc().save(target, **kwargs)
    assert excinfo.value.code == "save-mode-invalid"
    assert not target.exists()
    with pytest.raises(HwpxValueError):
        _doc().to_bytes(**kwargs)


def test_another_extension_still_writes_hwpx_but_warns(tmp_path: Path) -> None:
    target = tmp_path / "o.docx"
    with pytest.warns(UserWarning, match="o.docx"):
        _doc().save(target)
    assert target.read_bytes()[:2] == b"PK"


def test_hwpx_saves_do_not_warn(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _doc().save(tmp_path / "o.HWPX")


def test_the_first_hwp_save_says_the_writer_is_experimental(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persistence, "_hwp5_write_warned", False)
    with pytest.warns(UserWarning, match="experimental HWP 5.0 writer"):
        _doc().save(tmp_path / "a.hwp")
    assert (tmp_path / "a.hwp").read_bytes()[:4] == b"\xd0\xcf\x11\xe0"  # HWP 5.0 (compound file), not HWPX

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _doc().save(tmp_path / "b.hwp")
