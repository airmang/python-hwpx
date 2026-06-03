from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from hwpx.opc.package import HwpxPackage, HwpxStructureError

_MIMETYPE = b"application/hwp+zip"
_VERSION_XML = b"<?xml version='1.0' encoding='UTF-8'?><version/>"
_CONTAINER_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<container><rootfiles><rootfile full-path='Contents/content.hpf' "
    b"media-type='application/hwpml-package+xml'/></rootfiles></container>"
)
_MANIFEST_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<opf:package xmlns:opf='http://www.idpf.org/2007/opf/'>"
    b"<opf:manifest><opf:item id='header' href='Contents/header.xml'/></opf:manifest>"
    b"<opf:spine><opf:itemref idref='header'/></opf:spine>"
    b"</opf:package>"
)
_HEADER_XML = b"<?xml version='1.0' encoding='UTF-8'?><header/>"


def _build_package(*, include_mimetype: bool = True, include_container: bool = True, include_version: bool = True) -> bytes:
    parts: dict[str, bytes] = {
        "Contents/content.hpf": _MANIFEST_XML,
        "Contents/header.xml": _HEADER_XML,
    }
    if include_mimetype:
        parts["mimetype"] = _MIMETYPE
    if include_container:
        parts["META-INF/container.xml"] = _CONTAINER_XML
    if include_version:
        parts["version.xml"] = _VERSION_XML

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            if name == "mimetype":
                archive.writestr(name, payload, compress_type=ZIP_STORED)
            else:
                archive.writestr(name, payload)
    return buffer.getvalue()


def test_open_and_save_roundtrip() -> None:
    package = HwpxPackage.open(_build_package())

    assert package.main_content.full_path == "Contents/content.hpf"
    assert package.read("Contents/header.xml") == _HEADER_XML

    output = package.save()
    reopened = HwpxPackage.open(output)
    assert reopened.read("Contents/header.xml") == _HEADER_XML


def test_missing_required_files_raise_structure_error() -> None:
    with pytest.raises(HwpxStructureError):
        HwpxPackage.open(_build_package(include_mimetype=False))

    with pytest.raises(HwpxStructureError):
        HwpxPackage.open(_build_package(include_container=False))

    with pytest.raises(HwpxStructureError):
        HwpxPackage.open(_build_package(include_version=False))


def test_save_preserves_expected_compress_type_per_entry() -> None:
    package = HwpxPackage.open(_build_package())

    output = package.save()
    with ZipFile(io.BytesIO(output), "r") as archive:
        infos = archive.infolist()

    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == ZIP_STORED
    for info in infos[1:]:
        assert info.compress_type == ZIP_DEFLATED


def test_save_rewrites_mimetype_as_stored_even_when_source_was_compressed() -> None:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", _MIMETYPE)
        archive.writestr("version.xml", _VERSION_XML)
        archive.writestr("Contents/header.xml", _HEADER_XML)
        archive.writestr("Contents/content.hpf", _MANIFEST_XML)
        archive.writestr("META-INF/container.xml", _CONTAINER_XML)

    package = HwpxPackage.open(buffer.getvalue())
    output = package.save()

    with ZipFile(io.BytesIO(output), "r") as archive:
        assert archive.getinfo("mimetype").compress_type == ZIP_STORED


def test_save_preserves_existing_archive_order_and_entry_metadata() -> None:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", _MIMETYPE, compress_type=ZIP_STORED)
        archive.writestr("version.xml", _VERSION_XML, compress_type=ZIP_STORED)
        archive.writestr("Contents/header.xml", _HEADER_XML)
        archive.writestr("Contents/content.hpf", _MANIFEST_XML)
        archive.writestr("META-INF/container.xml", _CONTAINER_XML)

    source_bytes = buffer.getvalue()
    with ZipFile(io.BytesIO(source_bytes), "r") as archive:
        original_metadata = [
            (info.filename, info.compress_type, info.create_system, info.external_attr)
            for info in archive.infolist()
        ]

    package = HwpxPackage.open(source_bytes)
    package.write("Contents/header.xml", _HEADER_XML + b"<!-- edited -->")

    output = package.save()
    with ZipFile(io.BytesIO(output), "r") as archive:
        roundtrip_metadata = [
            (info.filename, info.compress_type, info.create_system, info.external_attr)
            for info in archive.infolist()
        ]

    assert roundtrip_metadata == original_metadata
