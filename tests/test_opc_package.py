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
