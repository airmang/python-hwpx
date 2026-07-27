# SPDX-License-Identifier: Apache-2.0
"""Failures that reach a user keep their exception type and gain a next step."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx.opc.package import HwpxPackage

HWP_V5_HEAD = HwpxPackage.OLE2_MAGIC + b"\x00" * 512


def test_hwp_v5_payload_keeps_bad_zip_file_and_names_the_conversion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "레거시.hwp"
    source.write_bytes(HWP_V5_HEAD)

    with pytest.raises(zipfile.BadZipFile) as excinfo:
        HwpxPackage.open(source)

    assert "HWPX로 변환" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, zipfile.BadZipFile)


def test_guidance_reaches_the_in_memory_source_forms() -> None:
    with pytest.raises(zipfile.BadZipFile, match="HWPX로 변환"):
        HwpxPackage.open(HWP_V5_HEAD)

    with pytest.raises(zipfile.BadZipFile, match="HWPX로 변환"):
        HwpxPackage.open(io.BytesIO(HWP_V5_HEAD))


def test_a_plain_corrupt_zip_is_not_reported_as_hwp(tmp_path: Path) -> None:
    source = tmp_path / "깨진문서.hwpx"
    source.write_bytes(b"not a zip at all")

    with pytest.raises(zipfile.BadZipFile) as excinfo:
        HwpxPackage.open(source)

    assert "HWPX로 변환" not in str(excinfo.value)


def test_a_missing_file_still_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        HwpxPackage.open(tmp_path / "없는문서.hwpx")


def test_peeking_leaves_a_stream_where_the_caller_left_it() -> None:
    stream = io.BytesIO(HWP_V5_HEAD)
    stream.seek(4)

    assert HwpxPackage._leading_bytes(stream, 8) == HwpxPackage.OLE2_MAGIC
    assert stream.tell() == 4
