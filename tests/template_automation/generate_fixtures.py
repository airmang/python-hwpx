from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from hwpx import HwpxDocument
from hwpx.tools.archive_cli import unpack_hwpx

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
MIMETYPE = b"application/hwp+zip"
VERSION_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hv:HCFVersion xmlns:hv=\"http://www.hancom.co.kr/hwpml/2011/version\" "
    "targetApplication=\"WORDPROCESSOR\" major=\"5\" minor=\"0\" micro=\"5\" "
    "buildNumber=\"0\" os=\"1\" xmlVersion=\"1.4\" application=\"Hancom Office Hangul\" "
    "appVersion=\"9, 1, 1, 5656 WIN32LEWindows_Unknown_Version\"/>"
).encode("utf-8")
CONTAINER_XML_TEMPLATE = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<ocf:container xmlns:ocf=\"urn:oasis:names:tc:opendocument:xmlns:container\" "
    "xmlns:hpf=\"http://www.hancom.co.kr/schema/2011/hpf\">"
    "<ocf:rootfiles>"
    "<ocf:rootfile full-path=\"{manifest_path}\" media-type=\"application/hwpml-package+xml\"/>"
    "</ocf:rootfiles>"
    "</ocf:container>"
)
MANIFEST_XML_TEMPLATE = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<opf:package xmlns:opf=\"http://www.idpf.org/2007/opf\">"
    "<opf:metadata/>"
    "<opf:manifest>"
    "<opf:item id=\"header\" href=\"{header_href}\" media-type=\"application/xml\"/>"
    "<opf:item id=\"section0\" href=\"{section_href}\" media-type=\"application/xml\"/>"
    "<opf:item id=\"version\" href=\"{version_href}\" media-type=\"application/xml\"/>"
    "</opf:manifest>"
    "<opf:spine>"
    "<opf:itemref idref=\"header\"/>"
    "<opf:itemref idref=\"section0\"/>"
    "</opf:spine>"
    "</opf:package>"
)
HEADER_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hh:head xmlns:hh=\"http://www.hancom.co.kr/hwpml/2011/head\" version=\"1.3.0\" secCnt=\"1\">"
    "<hh:beginNum page=\"1\" footnote=\"1\" endnote=\"1\" pic=\"1\" tbl=\"1\" equation=\"1\"/>"
    "</hh:head>"
).encode("utf-8")
SECTION_XML_TEMPLATE = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>"
    "<hs:sec xmlns:hs=\"http://www.hancom.co.kr/hwpml/2011/section\" "
    "xmlns:hp=\"http://www.hancom.co.kr/hwpml/2011/paragraph\">"
    "<hp:p id=\"1\" paraPrIDRef=\"0\" styleIDRef=\"0\" pageBreak=\"0\" columnBreak=\"0\" merged=\"0\">"
    "<hp:run charPrIDRef=\"0\"><hp:t>{text}</hp:t></hp:run>"
    "</hp:p>"
    "</hs:sec>"
)


def _fixture_package_dir(name: str) -> Path:
    return FIXTURE_ROOT / name / "package"


def _reset_package_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_fixture_package(name: str, payload: bytes) -> None:
    package_dir = _fixture_package_dir(name)
    _reset_package_dir(package_dir)
    with tempfile.TemporaryDirectory() as tmp_dir:
        hwpx_path = Path(tmp_dir) / f"{name}.hwpx"
        hwpx_path.write_bytes(payload)
        unpack_hwpx(hwpx_path, package_dir, overwrite=True)


def _build_simple_placeholder() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Student: {{NAME}}"
    return document.to_bytes()


def _build_repeated_placeholder() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Name A: {{NAME}}"
    document.add_paragraph("Name B: {{NAME}}")
    document.add_paragraph("Name C: {{NAME}}")
    return document.to_bytes()


def _build_split_run_placeholder() -> bytes:
    document = HwpxDocument.new()
    paragraph = document.paragraphs[0]
    paragraph.clear_text()
    paragraph.add_run("Student: ")
    paragraph.add_run("{{NA")
    paragraph.add_run("ME}}")
    return document.to_bytes()


def _build_whitespace_variant() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "School Name: Han   River    High"
    return document.to_bytes()


def _build_table_placeholder() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Roster"
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "Cell token {{CELL}}"
    return document.to_bytes()


def _build_header_footer_placeholder() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Body stays stable"
    document.set_header_text("Header {{HDR1}}")
    document.set_footer_text("Footer {{FTR1}}")
    return document.to_bytes()


def _build_multi_section_placeholder() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Section zero keeps {{SEC0}}"
    second_section = document.add_section()
    second_section.paragraphs[0].text = "Section one updates {{SEC1}}"
    return document.to_bytes()


def _build_checkbox_toggle() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "□ Option A"
    document.add_paragraph("■ Option B")
    return document.to_bytes()


def _build_extract_repack() -> bytes:
    document = HwpxDocument.new()
    document.paragraphs[0].text = "Pack token {{PACK}}"
    return document.to_bytes()


def _zip_parts(parts: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in parts:
            if name == "mimetype":
                archive.writestr(name, payload, compress_type=ZIP_STORED)
            else:
                archive.writestr(name, payload)
    return buffer.getvalue()


def _build_nonstandard_rootfile() -> bytes:
    manifest_path = "CustomRoot/content.hpf"
    header_path = "CustomRoot/header.xml"
    section_path = "CustomRoot/section0.xml"

    parts = [
        ("mimetype", MIMETYPE),
        (
            "META-INF/container.xml",
            CONTAINER_XML_TEMPLATE.format(manifest_path=manifest_path).encode("utf-8"),
        ),
        ("version.xml", VERSION_XML),
        (
            manifest_path,
            MANIFEST_XML_TEMPLATE.format(
                header_href="header.xml",
                section_href="section0.xml",
                version_href="../version.xml",
            ).encode("utf-8"),
        ),
        (header_path, HEADER_XML),
        (section_path, SECTION_XML_TEMPLATE.format(text="Alt root {{ROOT}}").encode("utf-8")),
    ]
    return _zip_parts(parts)


def generate_fixtures() -> None:
    builders = {
        "simple-placeholder": _build_simple_placeholder,
        "repeated-placeholder": _build_repeated_placeholder,
        "split-run-placeholder": _build_split_run_placeholder,
        "whitespace-variant": _build_whitespace_variant,
        "table-placeholder": _build_table_placeholder,
        "header-footer-placeholder": _build_header_footer_placeholder,
        "multi-section-placeholder": _build_multi_section_placeholder,
        "checkbox-toggle": _build_checkbox_toggle,
        "extract-repack": _build_extract_repack,
        "nonstandard-rootfile": _build_nonstandard_rootfile,
    }

    for name, builder in builders.items():
        _write_fixture_package(name, builder())


if __name__ == "__main__":
    generate_fixtures()

