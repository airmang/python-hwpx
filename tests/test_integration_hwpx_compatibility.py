from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from hwpx.document import HwpxDocument
from hwpx.package import HwpxPackage
from hwpx.tools import load_default_schemas, validate_document

_MIMETYPE = b"application/hwp+zip"
_VERSION_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hv:HCFVersion xmlns:hv=\"http://www.hancom.co.kr/hwpml/2011/version\" "
    "targetApplication=\"WORDPROCESSOR\" major=\"5\" minor=\"0\" micro=\"5\" "
    "buildNumber=\"0\" os=\"1\" xmlVersion=\"1.4\" application=\"Hancom Office Hangul\" "
    "appVersion=\"9, 1, 1, 5656 WIN32LEWindows_Unknown_Version\"/>"
).encode("utf-8")
_CONTAINER_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<ocf:container xmlns:ocf=\"urn:oasis:names:tc:opendocument:xmlns:container\" "
    "xmlns:hpf=\"http://www.hancom.co.kr/schema/2011/hpf\">"
    "<ocf:rootfiles>"
    "<ocf:rootfile full-path=\"Contents/content.hpf\" media-type=\"application/hwpml-package+xml\"/>"
    "</ocf:rootfiles>"
    "</ocf:container>"
).encode("utf-8")
_MANIFEST_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<opf:package xmlns:opf=\"http://www.idpf.org/2007/opf\">"
    "<opf:metadata/>"
    "<opf:manifest>"
    "<opf:item id=\"header\" href=\"Contents/header.xml\" media-type=\"application/xml\"/>"
    "<opf:item id=\"section0\" href=\"Contents/section0.xml\" media-type=\"application/xml\"/>"
    "</opf:manifest>"
    "<opf:spine>"
    "<opf:itemref idref=\"header\"/>"
    "<opf:itemref idref=\"section0\"/>"
    "</opf:spine>"
    "</opf:package>"
).encode("utf-8")
_HEADER_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hh:head xmlns:hh=\"http://www.hancom.co.kr/hwpml/2011/head\" version=\"1.3.0\" secCnt=\"1\">"
    "<hh:beginNum page=\"1\" footnote=\"1\" endnote=\"1\" pic=\"1\" tbl=\"1\" equation=\"1\"/>"
    "</hh:head>"
).encode("utf-8")
_SECTION_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hs:sec xmlns:hs=\"http://www.hancom.co.kr/hwpml/2011/section\" "
    "xmlns:hp=\"http://www.hancom.co.kr/hwpml/2011/paragraph\">"
    "<hp:p id=\"1\" paraPrIDRef=\"0\" styleIDRef=\"0\" pageBreak=\"0\" columnBreak=\"0\" merged=\"0\">"
    "<hp:run charPrIDRef=\"0\"><hp:t>통합 테스트</hp:t></hp:run>"
    "</hp:p>"
    "</hs:sec>"
).encode("utf-8")


def _build_sample_document() -> bytes:
    parts: dict[str, bytes] = {
        "mimetype": _MIMETYPE,
        "version.xml": _VERSION_XML,
        "META-INF/container.xml": _CONTAINER_XML,
        "Contents/content.hpf": _MANIFEST_XML,
        "Contents/header.xml": _HEADER_XML,
        "Contents/section0.xml": _SECTION_XML,
    }

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            if name == "mimetype":
                archive.writestr(name, payload, compress_type=ZIP_STORED)
            else:
                archive.writestr(name, payload)
    return buffer.getvalue()


_SAMPLE_DOCUMENT_BYTES = _build_sample_document()


@pytest.fixture(scope="module")
def sample_document_bytes() -> bytes:
    return _SAMPLE_DOCUMENT_BYTES


@pytest.fixture(scope="module")
def sample_document_path(tmp_path_factory, sample_document_bytes: bytes) -> Path:
    path = tmp_path_factory.mktemp("hwpx") / "sample_compatibility.hwpx"
    path.write_bytes(sample_document_bytes)
    return path


@pytest.fixture(scope="module")
def default_schemas():
    return load_default_schemas()


def _package_contents(package: HwpxPackage) -> dict[str, bytes]:
    return {name: package.get_part(name) for name in package.part_names()}


def test_round_trip_preserves_package_parts(
    sample_document_bytes: bytes, default_schemas
) -> None:
    document = HwpxDocument.open(sample_document_bytes)
    original_parts = _package_contents(document.package)

    buffer = io.BytesIO()
    document.package.save(buffer)
    buffer.seek(0)

    roundtrip_document = HwpxDocument.open(buffer.getvalue())
    assert _package_contents(roundtrip_document.package) == original_parts

    roundtrip_report = validate_document(
        buffer.getvalue(),
        header_schema=default_schemas.header,
        section_schema=default_schemas.section,
    )
    assert roundtrip_report.ok, \
        "Round-trip document failed schema validation: " + \
        "; ".join(str(issue) for issue in roundtrip_report.issues)


def test_fixture_validates_against_reference_schemas(
    sample_document_path: Path, sample_document_bytes: bytes
) -> None:
    path_report = validate_document(sample_document_path)
    assert path_report.ok, "Generated sample failed schema validation from path"

    validated = set(path_report.validated_parts)
    assert "Contents/header.xml" in validated
    assert any(name.startswith("Contents/section") for name in validated)

    bytes_report = validate_document(sample_document_bytes)
    assert bytes_report.ok, "Generated sample failed schema validation from bytes"
