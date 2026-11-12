# SPDX-License-Identifier: Apache-2.0
"""손상된 HWPX를 열 때의 예외 계열(ENG-31).

손상 종류마다 다른 날 예외(``BadZipFile``·``zlib.error``·``XMLSyntaxError``)가
나던 것을 ``HwpxStructureError`` 하위 클래스로 묶었다. 기존 ``except`` 가 깨지지
않도록 각 클래스는 원래 예외도 상속하고, 원래 예외는 ``__cause__`` 에 남는다.
"""

from __future__ import annotations

import io
import zipfile
import zlib
from typing import Callable

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.opc.package import (
    HwpxArchiveError,
    HwpxCompressedDataError,
    HwpxPackage,
    HwpxPackageError,
    HwpxStructureError,
    HwpxXmlSyntaxError,
)


@pytest.fixture(scope="module")
def good() -> bytes:
    with HwpxDocument.new() as document:
        document.add_paragraph("가나다 " * 400)
        return document.to_bytes()


def _rebuild(data: bytes, mutate: Callable[[str, bytes], bytes | None]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = mutate(info.filename, source.read(info.filename))
            if payload is not None:
                target.writestr(info, payload, compress_type=info.compress_type)
    return out.getvalue()


def _break_part(data: bytes, part: str, payload: bytes | None = None) -> bytes:
    return _rebuild(
        data,
        lambda name, body: (payload if payload is not None else body[: len(body) // 2])
        if name == part
        else body,
    )


def _corrupt_deflate(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo("Contents/section0.xml")
        assert info.compress_type == zipfile.ZIP_DEFLATED
    start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    damaged = bytearray(data)
    damaged[start : start + 12] = b"\xff" * 12
    return bytes(damaged)


@pytest.mark.parametrize("opener", [HwpxDocument.open, HwpxPackage.open])
@pytest.mark.parametrize(
    "payload",
    [b"", b"not a zip at all " * 20],
    ids=["empty", "not-zip"],
)
def test_not_a_zip_is_a_structure_error_and_still_bad_zip_file(opener, payload) -> None:
    with pytest.raises(HwpxArchiveError) as caught:
        opener(payload)
    assert isinstance(caught.value, HwpxStructureError)
    assert isinstance(caught.value, zipfile.BadZipFile)
    assert type(caught.value.__cause__) is zipfile.BadZipFile
    # 문구는 zipfile이 쓴 그대로다.
    assert str(caught.value) == str(caught.value.__cause__)


@pytest.mark.parametrize("opener", [HwpxDocument.open, HwpxPackage.open])
def test_truncated_zip_is_an_archive_error(opener, good: bytes) -> None:
    with pytest.raises(zipfile.BadZipFile) as caught:
        opener(good[: len(good) // 2])
    assert isinstance(caught.value, HwpxArchiveError)


@pytest.mark.parametrize("opener", [HwpxDocument.open, HwpxPackage.open])
def test_damaged_compressed_data_is_a_structure_error(opener, good: bytes) -> None:
    with pytest.raises(HwpxCompressedDataError) as caught:
        opener(_corrupt_deflate(good))
    assert isinstance(caught.value, HwpxStructureError)
    assert isinstance(caught.value, zlib.error)
    assert type(caught.value.__cause__) is zlib.error


@pytest.mark.parametrize(
    ("part", "payload"),
    [
        ("Contents/header.xml", None),
        ("Contents/section0.xml", None),
        ("Contents/content.hpf", b"<a><b></a>"),
    ],
)
def test_broken_xml_part_names_the_part(good: bytes, part: str, payload: bytes | None) -> None:
    with pytest.raises(HwpxXmlSyntaxError) as caught:
        HwpxDocument.open(_break_part(good, part, payload))
    error = caught.value
    assert isinstance(error, HwpxStructureError)
    assert isinstance(error, etree.XMLSyntaxError)
    assert type(error.__cause__) is etree.XMLSyntaxError
    assert error.part_name == part
    assert part in str(error)
    assert error.position == error.__cause__.position
    assert error.code == error.__cause__.code


@pytest.mark.parametrize("opener", [HwpxDocument.open, HwpxPackage.open])
@pytest.mark.parametrize("part", ["META-INF/container.xml", "version.xml"])
def test_broken_package_level_xml_is_a_structure_error(opener, good: bytes, part: str) -> None:
    with pytest.raises(HwpxXmlSyntaxError) as caught:
        opener(_break_part(good, part, b"<a><b></a>"))
    assert isinstance(caught.value, etree.XMLSyntaxError)
    assert type(caught.value.__cause__) is etree.XMLSyntaxError


def test_one_except_clause_catches_every_kind_of_damage(good: bytes) -> None:
    damaged = [
        b"",
        good[: len(good) // 2],
        _corrupt_deflate(good),
        _break_part(good, "Contents/header.xml"),
        _rebuild(good, lambda name, body: None if name == "mimetype" else body),
    ]
    for payload in damaged:
        with pytest.raises(HwpxStructureError):
            HwpxDocument.open(payload)


def test_missing_mimetype_stays_a_plain_structure_error(good: bytes) -> None:
    payload = _rebuild(good, lambda name, body: None if name == "mimetype" else body)
    with pytest.raises(HwpxStructureError) as caught:
        HwpxDocument.open(payload)
    assert type(caught.value) is HwpxStructureError


def test_a_declared_preview_that_is_absent_does_not_stop_open_or_save(good: bytes) -> None:
    # container.xml이 Preview/PrvText.txt를 가리키는데 파일이 없는 문서. 한/글 2024는 그대로 연다.
    payload = _rebuild(good, lambda name, body: None if name == "Preview/PrvText.txt" else body)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert b'full-path="Preview/PrvText.txt"' in archive.read("META-INF/container.xml")

    document = HwpxDocument.open(payload)
    assert "가나다" in document.paragraphs[-1].text
    document.add_paragraph("덧붙인 문단")
    saved = document.to_bytes()

    assert "덧붙인 문단" in HwpxDocument.open(saved).paragraphs[-1].text


@pytest.mark.parametrize("part", ["Contents/content.hpf", "META-INF/container.rdf"])
def test_another_declared_root_that_is_absent_is_still_an_error(good: bytes, part: str) -> None:
    payload = _rebuild(good, lambda name, body: None if name == part else body)
    with pytest.raises(HwpxStructureError):
        HwpxDocument.open(payload)


def test_get_xml_after_open_wraps_the_same_way(good: bytes) -> None:
    package = HwpxPackage.open(_break_part(good, "Contents/section0.xml"))
    with pytest.raises(HwpxPackageError) as caught:
        package.get_xml("Contents/section0.xml")
    assert isinstance(caught.value, HwpxXmlSyntaxError)
    assert caught.value.part_name == "Contents/section0.xml"


def test_missing_path_is_still_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        HwpxDocument.open(tmp_path / "없는-파일.hwpx")
