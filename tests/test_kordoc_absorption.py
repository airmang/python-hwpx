from __future__ import annotations

import io
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from hwpx import HwpxDocument
from hwpx.builder import Document, Paragraph, Run, Section
from hwpx.patch import ParagraphTextPatch, paragraph_patch
from hwpx.tools.package_validator import (
    PREVIEW_TEXT_PATH,
    validate_editor_open_safety,
    validate_package,
)


_ROOT = Path(__file__).resolve().parents[1]
_SKELETON = _ROOT / "src" / "hwpx" / "data" / "Skeleton.hwpx"


def _zip_parts(parts: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in parts:
            archive.writestr(
                name,
                payload,
                compress_type=ZIP_STORED if name == "mimetype" else ZIP_DEFLATED,
            )
    return buffer.getvalue()


def _replace_zip_part(package_bytes: bytes, part_name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(package_bytes), "r") as source:
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for info in source.infolist():
                replacement = payload if info.filename == part_name else source.read(info.filename)
                archive.writestr(
                    info.filename,
                    replacement,
                    compress_type=ZIP_STORED if info.filename == "mimetype" else info.compress_type,
                )
    return buffer.getvalue()


def _minimum_editor_package_without_version() -> bytes:
    with ZipFile(_SKELETON, "r") as source:
        header = source.read("Contents/header.xml")
        section = source.read("Contents/section0.xml")
    container = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b"<rootfiles>"
        b'<rootfile full-path="Contents/content.hpf" '
        b'media-type="application/hwpml-package+xml"/>'
        b"</rootfiles>"
        b"</container>"
    )
    manifest = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
        b"<opf:manifest>"
        b'<opf:item id="header" href="header.xml" media-type="application/xml"/>'
        b'<opf:item id="section0" href="section0.xml" media-type="application/xml"/>'
        b"</opf:manifest>"
        b"<opf:spine>"
        b'<opf:itemref idref="header"/>'
        b'<opf:itemref idref="section0"/>'
        b"</opf:spine>"
        b"</opf:package>"
    )
    return _zip_parts(
        [
            ("mimetype", b"application/hwp+zip"),
            ("META-INF/container.xml", container),
            ("Contents/content.hpf", manifest),
            ("Contents/header.xml", header),
            ("Contents/section0.xml", section),
            (PREVIEW_TEXT_PATH, b"minimum package preview"),
        ]
    )


def test_minimum_editor_package_without_version_opens() -> None:
    package_bytes = _minimum_editor_package_without_version()

    report = validate_package(package_bytes)
    assert report.ok
    assert any("version.xml" in str(issue) for issue in report.warnings)

    document = HwpxDocument.open(package_bytes)
    try:
        assert document.package.version_path() is None
        assert document.version is None
    finally:
        document.close()


def test_table_required_part_omission_blocks_package_validation() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "cell"
    package_bytes = document.to_bytes()

    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    broken_section = re.sub(
        rb"<hp:cellMargin\b[^>]*/>",
        b"",
        section_xml,
        count=1,
    )
    broken = _replace_zip_part(package_bytes, "Contents/section0.xml", broken_section)

    report = validate_package(broken)
    assert not report.ok
    assert any("cellMargin" in str(issue) for issue in report.errors)


def test_self_closing_cell_run_receives_text_in_preserve_format_path() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "old"
    package_bytes = document.to_bytes()

    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    section_xml = section_xml.replace(
        b'<hp:run charPrIDRef="0"><hp:t>old</hp:t></hp:run>',
        b'<hp:run charPrIDRef="0"/>',
        1,
    )
    fixture = _replace_zip_part(package_bytes, "Contents/section0.xml", section_xml)

    reopened = HwpxDocument.open(fixture)
    try:
        reopened.paragraphs[-1].tables[0].cell(0, 0).set_text("new", preserve_format=True)
        output = reopened.to_bytes()
    finally:
        reopened.close()

    with ZipFile(io.BytesIO(output), "r") as archive:
        edited_section = archive.read("Contents/section0.xml")
    assert b"<hp:t>new</hp:t>" in edited_section
    assert validate_editor_open_safety(output).ok


def test_builder_bold_run_uses_font_ref_for_mac_hancom_axis(tmp_path: Path) -> None:
    target = tmp_path / "bold-fontref.hwpx"
    Document(
        sections=[
            Section(
                children=[
                    Paragraph(children=[Run("plain "), Run("bold", bold=True)]),
                ]
            )
        ]
    ).save_to_path(target)

    with ZipFile(target, "r") as archive:
        header_xml = archive.read("Contents/header.xml")
    assert b"<hh:bold" in header_xml
    assert b"<hh:fontRef" in header_xml
    assert validate_editor_open_safety(target).ok


def test_byte_preserving_patch_noop_is_byte_identical() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("unchanged")
    package_bytes = document.to_bytes()

    empty = paragraph_patch(package_bytes, [])
    same_text = paragraph_patch(
        package_bytes,
        [ParagraphTextPatch("Contents/section0.xml", 1, "unchanged")],
    )

    assert empty.data == package_bytes
    assert empty.byte_identical is True
    assert same_text.data == package_bytes
    assert same_text.byte_identical is True


def test_byte_preserving_patch_splices_section_text_and_preserves_other_entries() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("before")
    package_bytes = document.to_bytes()

    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        original_mimetype = archive.read("mimetype")
        original_header = archive.read("Contents/header.xml")
    result = paragraph_patch(
        package_bytes,
        [ParagraphTextPatch("Contents/section0.xml", 1, "after")],
    )

    assert result.skipped == ()
    assert result.applied[0].original_text == "before"
    assert result.byte_identical is False
    assert result.zip_method == "partial-local-record-copy"
    assert result.open_safety["ok"] is True

    with ZipFile(io.BytesIO(result.data), "r") as archive:
        assert archive.read("mimetype") == original_mimetype
        assert archive.read("Contents/header.xml") == original_header
        section = archive.read("Contents/section0.xml")
    assert b"<hp:t>after</hp:t>" in section
    assert b"<hp:t>before</hp:t>" not in section


def test_byte_preserving_patch_skips_unsupported_block_edit_without_mutation() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("single line")
    package_bytes = document.to_bytes()

    result = paragraph_patch(
        package_bytes,
        [ParagraphTextPatch("Contents/section0.xml", 1, "line one\nline two")],
    )

    assert result.data == package_bytes
    assert result.byte_identical is True
    assert result.skipped[0].reason == "line break insertion is unsupported"
