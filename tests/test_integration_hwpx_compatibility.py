from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.opc.package import HwpxPackage
from hwpx.tools import load_default_schemas, validate_document
from hwpx.templates import blank_document_bytes

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


def test_master_page_history_and_version_round_trip(tmp_path: Path) -> None:
    package = HwpxPackage.open(blank_document_bytes())

    manifest = package.manifest_tree()
    ns = {"opf": "http://www.idpf.org/2007/opf/"}
    manifest_list = manifest.find(f"{{{ns['opf']}}}manifest")
    assert manifest_list is not None

    def add_manifest_item(item_id: str, href: str) -> None:
        etree.SubElement(
            manifest_list,
            f"{{{ns['opf']}}}item",
            {"id": item_id, "href": href, "media-type": "application/xml"},
        )

    add_manifest_item("master-page-0", "Contents/masterPages/masterPage0.xml")
    add_manifest_item("history", "Contents/history.xml")
    add_manifest_item("version", "version.xml")
    package.set_xml(package.MANIFEST_PATH, manifest)

    hm_ns = "http://www.hancom.co.kr/hwpml/2011/master-page"
    master_root = etree.Element(f"{{{hm_ns}}}masterPage")
    etree.SubElement(
        master_root,
        f"{{{hm_ns}}}masterPageItem",
        {"id": "0", "type": "BOTH", "name": "초기 바탕쪽"},
    )
    package.set_xml("Contents/masterPages/masterPage0.xml", master_root)

    hhs_ns = "http://www.hancom.co.kr/hwpml/2011/history"
    history_root = etree.Element(f"{{{hhs_ns}}}history")
    history_entry = etree.SubElement(history_root, f"{{{hhs_ns}}}historyEntry", {"id": "0"})
    comment = etree.SubElement(history_entry, f"{{{hhs_ns}}}comment")
    comment.text = "초기 내역"
    package.set_xml("Contents/history.xml", history_root)

    document = HwpxDocument.from_package(package)

    assert len(document.master_pages) == 1
    assert len(document.histories) == 1
    version_part = document.version
    assert version_part is not None

    master_page = document.master_pages[0]
    master_item = master_page.element.find(f"{{{hm_ns}}}masterPageItem")
    assert master_item is not None
    master_item.set("name", "검토용 바탕쪽")
    master_page.mark_dirty()

    history_part = document.histories[0]
    history_comment = history_part.element.find(
        f"{{{hhs_ns}}}historyEntry/{{{hhs_ns}}}comment"
    )
    assert history_comment is not None
    history_comment.text = "업데이트된 변경 기록"
    history_part.mark_dirty()

    version_part.element.set("appVersion", "15.0.0.100 WIN32")
    version_part.mark_dirty()

    output_path = tmp_path / "master_history_roundtrip.hwpx"
    document.save_to_path(output_path)

    reopened = HwpxDocument.open(output_path)
    assert reopened.master_pages
    assert reopened.histories
    reopened_version = reopened.version
    assert reopened_version is not None

    reopened_master_item = reopened.master_pages[0].element.find(
        f"{{{hm_ns}}}masterPageItem"
    )
    assert reopened_master_item is not None
    assert reopened_master_item.get("name") == "검토용 바탕쪽"

    reopened_history_comment = reopened.histories[0].element.find(
        f"{{{hhs_ns}}}historyEntry/{{{hhs_ns}}}comment"
    )
    assert reopened_history_comment is not None
    assert reopened_history_comment.text == "업데이트된 변경 기록"

    assert reopened_version.element.get("appVersion") == "15.0.0.100 WIN32"
    assert "Contents/masterPages/masterPage0.xml" in reopened.package.master_page_paths()
    assert "Contents/history.xml" in reopened.package.history_paths()
    assert reopened.package.version_path() == "version.xml"
