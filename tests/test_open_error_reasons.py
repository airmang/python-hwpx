# SPDX-License-Identifier: Apache-2.0
"""Opening something that is not a document says what it is, with a code and a next step."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError, HwpxTypeError
from hwpx.opc.package import HwpxArchiveError, HwpxPackageError, HwpxStructureError


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _valid_hwpx() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc.to_bytes()


@pytest.mark.parametrize(
    "name,data,code,words",
    [
        ("empty.hwpx", b"", "open-empty-file", "빈 파일"),
        ("empty.hwp", b"", "open-empty-file", "빈 파일"),
        ("note.hwpx", "그냥 메모입니다\n".encode() * 5, "open-not-hwpx", "텍스트 파일"),
        ("note.hwp", "그냥 메모입니다\n".encode() * 5, "open-not-hwp", "HWP 문서가 아닙니다"),
    ],
)
def test_each_reason_has_its_own_message_and_code(tmp_path: Path, name: str, data: bytes, code: str, words: str) -> None:
    with pytest.raises(HwpxArchiveError) as excinfo:
        HwpxDocument.open(_write(tmp_path, name, data))

    error = excinfo.value
    assert isinstance(error, zipfile.BadZipFile)  # the old except still catches it
    assert error.code == code and error.suggestion
    assert words in str(error)
    assert "File is not a zip file" not in str(error)
    if name.endswith(".hwp"):
        assert "ZIP" not in str(error).upper()


def test_a_truncated_hwpx_says_it_is_damaged(tmp_path: Path) -> None:
    data = _valid_hwpx()
    with pytest.raises(HwpxArchiveError) as excinfo:
        HwpxDocument.open(_write(tmp_path, "cut.hwpx", data[: len(data) // 2]))
    assert excinfo.value.code == "open-archive-damaged"
    assert "잘렸거나 손상" in str(excinfo.value)


def test_a_docx_renamed_to_hwpx_is_named(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    with pytest.raises(HwpxStructureError) as excinfo:
        HwpxDocument.open(_write(tmp_path, "report.hwpx", buffer.getvalue()))
    assert excinfo.value.code == "open-not-hwpx"
    assert "Office Open XML" in str(excinfo.value)


def test_a_folder_is_refused_as_a_folder(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError) as excinfo:
        HwpxDocument.open(tmp_path)
    assert isinstance(excinfo.value, HwpxPackageError)
    assert excinfo.value.code == "open-is-folder"
    assert str(tmp_path) in str(excinfo.value)


@pytest.mark.parametrize("value", [123, None, 1.5, ["a.hwpx"]])
def test_a_value_that_is_not_a_source_is_a_type_error(value: object) -> None:
    with pytest.raises(HwpxTypeError) as excinfo:
        HwpxDocument.open(value)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, HwpxError) and isinstance(excinfo.value, TypeError)
    assert excinfo.value.code == "open-invalid-type"


def test_an_encrypted_hwpx_has_a_string_code(tmp_path: Path) -> None:
    from lxml import etree

    from tests.test_error_messages import _ENCRYPTED, _odf_manifest, _package

    source = _package(tmp_path, manifest=_odf_manifest(_ENCRYPTED), garble=_ENCRYPTED)
    with pytest.raises(etree.XMLSyntaxError) as excinfo:
        HwpxDocument.open(source)

    error = excinfo.value
    assert error.code == "open-encrypted"  # not lxml's number
    assert isinstance(error.lxml_code, int)  # type: ignore[attr-defined]
    assert error.suggestion  # type: ignore[attr-defined]


def test_paths_bytes_and_streams_still_open(tmp_path: Path) -> None:
    data = _valid_hwpx()
    path = _write(tmp_path, "ok.hwpx", data)
    for source in (path, str(path), data, io.BytesIO(data)):
        HwpxDocument.open(source).close()
