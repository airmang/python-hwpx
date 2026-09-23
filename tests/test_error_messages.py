# SPDX-License-Identifier: Apache-2.0
"""Failures that reach a user keep their exception type and gain a next step."""
from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
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


# --------------------------------------------------------------------------
# 암호가 걸린 HWPX — 타입은 XMLSyntaxError 그대로, 메시지가 암호 해제를 안내한다
#
# 실측 근거: 한컴오피스 한글 13.0.0.711이 저장한 암호 문서는 ODF 패키지 암호화를
# 쓴다. META-INF/manifest.xml이 파트마다 odf:file-entry > odf:encryption-data
# (AES-256-CBC, PBKDF2 1024회, SHA-256 시작 키, sha256-1k 체크섬)를 선언하고,
# header/section/settings/PrvText 파트 바이트는 암호문(엔트로피 7.98 bit/byte)이다.
# 아래 합성본은 같은 선언 모양에 암호문 대신 결정적 잡음 바이트를 쓴다.

_ODF = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
_ENCRYPTED = ("Contents/header.xml", "Contents/section0.xml")
_CIPHERTEXT = bytes(random.Random(73).randrange(1, 256) for _ in range(2048))


def _odf_manifest(parts: tuple[str, ...]) -> bytes:
    entries = "".join(
        f'<odf:file-entry odf:full-path="{part}" odf:media-type="application/xml" odf:size="4096">'
        f'<odf:encryption-data odf:checksum-type="{_ODF}#sha256-1k" odf:checksum="AAAA">'
        '<odf:algorithm odf:algorithm-name="http://www.w3.org/2001/04/xmlenc#aes256-cbc"'
        ' odf:initialisation-vector="AAAA"/>'
        f'<odf:key-derivation odf:key-derivation-name="{_ODF}#pbkdf2" odf:key-size="32"'
        ' odf:iteration-count="1024" odf:salt="AAAA"/>'
        "<odf:start-key-generation"
        ' odf:start-key-generation-name="http://www.w3.org/2000/09/xmldsig#sha256" odf:key-size="32"/>'
        "</odf:encryption-data></odf:file-entry>"
        for part in parts
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        f'<odf:manifest xmlns:odf="{_ODF}">{entries}</odf:manifest>'
    ).encode()


def _package(tmp_path: Path, *, manifest: bytes | None, garble: tuple[str, ...]) -> Path:
    target = tmp_path / "암호문서.hwpx"
    with zipfile.ZipFile(io.BytesIO(HwpxDocument.new().to_bytes())) as source, zipfile.ZipFile(
        target, "w"
    ) as out:
        for info in source.infolist():
            data = source.read(info)
            if info.filename in garble:
                data = _CIPHERTEXT
            elif info.filename == "META-INF/manifest.xml" and manifest is not None:
                data = manifest
            out.writestr(info, data)
    return target


def test_encrypted_hwpx_keeps_xml_syntax_error_and_names_the_password(tmp_path: Path) -> None:
    source = _package(tmp_path, manifest=_odf_manifest(_ENCRYPTED), garble=_ENCRYPTED)

    with pytest.raises(etree.XMLSyntaxError) as excinfo:
        HwpxDocument.open(source)

    assert "암호" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, etree.XMLSyntaxError)


def test_an_encrypted_package_still_opens_for_inspection(tmp_path: Path) -> None:
    source = _package(tmp_path, manifest=_odf_manifest(_ENCRYPTED), garble=_ENCRYPTED)

    package = HwpxPackage.open(source)

    assert package.get_xml("META-INF/container.xml") is not None
    with pytest.raises(etree.XMLSyntaxError, match="암호"):
        package.get_xml("Contents/section0.xml")


def test_an_undeclared_broken_part_is_not_reported_as_encrypted(tmp_path: Path) -> None:
    source = _package(tmp_path, manifest=None, garble=("Contents/section0.xml",))

    with pytest.raises(etree.XMLSyntaxError) as excinfo:
        HwpxDocument.open(source)

    assert "암호" not in str(excinfo.value)


def test_an_unreadable_odf_manifest_never_blocks_open(tmp_path: Path) -> None:
    source = _package(tmp_path, manifest=b"\x00 not xml", garble=())

    HwpxDocument.open(source).close()
