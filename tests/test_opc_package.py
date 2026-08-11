from __future__ import annotations

import binascii
import inspect
import io
import os
import tracemalloc
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from lxml import etree

import hwpx
import hwpx.patch
from hwpx.document import HwpxDocument
from hwpx.opc.package import (
    HwpxPackage,
    HwpxPackageError,
    HwpxStructureError,
    _UNCHECKED_SAVE_TOKEN,
)
from hwpx.opc.security import (
    MAX_ZIP_ENTRIES,
    MAX_ZIP_MEMBER_BYTES,
    HwpxSecurityError,
    guard_zip_file,
    read_member,
)
from hwpx.oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from hwpx.tools.package_validator import (
    is_editor_open_blocking_issue,
    validate_editor_open_safety,
    validate_package,
)
from hwpx.tools import validator as validator_module

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
    b"<opf:manifest>"
    b"<opf:item id='header' href='Contents/header.xml'/>"
    b"<opf:item id='section0' href='Contents/section0.xml'/>"
    b"</opf:manifest>"
    b"<opf:spine><opf:itemref idref='section0'/></opf:spine>"
    b"</opf:package>"
)
_HWPML_ROOT_NAMESPACE_ATTRS = " ".join(
    f"xmlns:{prefix}='{uri}'"
    for prefix, uri in HWPML_COMPAT_ROOT_NAMESPACES.items()
).encode("utf-8")
_HEADER_XML = (
    b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    b"<hh:head " + _HWPML_ROOT_NAMESPACE_ATTRS + b"/>"
)
_HEADER_XML_WITH_TEST_STYLE = (
    b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    b"<hh:head " + _HWPML_ROOT_NAMESPACE_ATTRS + b">"
    b"<hh:refList>"
    b"<hh:styles itemCnt='1'>"
    b"<hh:style id='26' type='PARA' name='TestStyle' engName='TestStyle' "
    b"paraPrIDRef='0' charPrIDRef='0' nextStyleIDRef='26' langID='1042' lockForm='0'/>"
    b"</hh:styles>"
    b"</hh:refList>"
    b"</hh:head>"
)
_SECTION_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' "
    b"xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>"
    b"<hp:p id='1' paraPrIDRef='0' styleIDRef='0' pageBreak='0' columnBreak='0' merged='0'>"
    b"<hp:run charPrIDRef='0'><hp:t>Package save fixture</hp:t></hp:run>"
    b"</hp:p>"
    b"</hs:sec>"
)
_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"


def _build_package(
    *,
    include_mimetype: bool = True,
    include_container: bool = True,
    include_version: bool = True,
    overrides: Mapping[str, bytes] | None = None,
) -> bytes:
    parts: dict[str, bytes] = {
        "Contents/content.hpf": _MANIFEST_XML,
        "Contents/header.xml": _HEADER_XML,
        "Contents/section0.xml": _SECTION_XML,
    }
    parts.update(overrides or {})
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


def test_xml_entity_bomb_is_rejected_before_expansion() -> None:
    entity_payload = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<!DOCTYPE lolz ["
        b"<!ENTITY lol 'lol'>"
        b"<!ENTITY lol1 '&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;'>"
        b"]>"
        b"<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>&lol1;</hs:sec>"
    )
    package_bytes = _build_package(overrides={"Contents/section0.xml": entity_payload})

    package = HwpxPackage.open(package_bytes)
    with pytest.raises(HwpxSecurityError, match="DTD/entity"):
        package.get_xml("Contents/section0.xml")

    report = validate_package(package_bytes)
    assert not report.ok
    assert any("DTD/entity" in str(issue) for issue in report.errors)


def test_zip_compression_bomb_is_rejected_before_member_reads() -> None:
    bomb_payload = b"<root>" + (b"a" * (8 * 1024 * 1024)) + b"</root>"
    package_bytes = _build_package(overrides={"Contents/bomb.xml": bomb_payload})

    with pytest.raises(HwpxSecurityError, match="compression ratio"):
        HwpxPackage.open(package_bytes)

    report = validate_package(package_bytes)
    assert not report.ok
    assert any("compression ratio" in str(issue) for issue in report.errors)


def _section_xml_with_stale_lineseg(*, complex_paragraph: bool = False) -> bytes:
    section = etree.fromstring(_SECTION_XML)
    paragraph = section.find(f".//{{{_HP_NS}}}p")
    assert paragraph is not None
    if complex_paragraph:
        run = etree.SubElement(paragraph, f"{{{_HP_NS}}}run", charPrIDRef="0")
        etree.SubElement(run, f"{{{_HP_NS}}}ctrl", id="field")
    line_array = etree.SubElement(paragraph, f"{{{_HP_NS}}}linesegarray")
    etree.SubElement(line_array, f"{{{_HP_NS}}}lineseg", textpos="999")
    return etree.tostring(section, xml_declaration=True, encoding="UTF-8")


def _section_xml_with_named_style_ref() -> bytes:
    return _SECTION_XML.replace(b"styleIDRef='0'", b"styleIDRef='TestStyle'", 1)


def _package_with_stale_lineseg() -> HwpxPackage:
    package = HwpxPackage.open(_build_package())
    package._files["Contents/section0.xml"] = _section_xml_with_stale_lineseg()
    return package


def test_section_set_part_strips_layout_cache_before_save() -> None:
    package = HwpxPackage.open(_build_package())
    package.set_part(
        "Contents/section0.xml",
        _section_xml_with_stale_lineseg(),
    )

    stored_section = package.read("Contents/section0.xml")
    assert b"linesegarray" not in stored_section.lower()
    assert b"standalone='yes'" in stored_section or b'standalone="yes"' in stored_section
    assert b"xmlns:ha=" in stored_section
    assert b"xmlns:hp10=" in stored_section
    output = package.save()

    report = validate_package(output)
    assert not any(is_editor_open_blocking_issue(issue) for issue in report.errors)
    assert not any("standalone" in issue.message for issue in report.errors)
    assert not any("namespace" in issue.message for issue in report.errors)
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" not in section_xml.lower()


def test_save_updates_strips_section_layout_cache() -> None:
    package = HwpxPackage.open(_build_package())

    output = package.save(
        updates={"Contents/section0.xml": _section_xml_with_stale_lineseg()}
    )

    assert isinstance(output, bytes)
    report = validate_package(output)
    assert not any(is_editor_open_blocking_issue(issue) for issue in report.errors)
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" not in section_xml.lower()


def test_section_set_part_preserves_unjudgeable_layout_cache() -> None:
    # A paragraph carrying controls cannot be judged at the byte boundary, so
    # its cache is preserved: the mutating APIs upstream own invalidation.
    # Blanket stripping forced whole-document re-layout (specs/031 P0).
    package = HwpxPackage.open(_build_package())
    package.set_part(
        "Contents/section0.xml",
        _section_xml_with_stale_lineseg(complex_paragraph=True),
    )

    stored_section = package.read("Contents/section0.xml")
    assert b"linesegarray" in stored_section.lower()


def test_section_set_part_preserves_valid_layout_cache() -> None:
    # textpos within the paragraph text length: the authored layout is valid
    # and must survive the write untouched.
    section = etree.fromstring(_SECTION_XML)
    paragraph = section.find(f".//{{{_HP_NS}}}p")
    assert paragraph is not None
    line_array = etree.SubElement(paragraph, f"{{{_HP_NS}}}linesegarray")
    etree.SubElement(line_array, f"{{{_HP_NS}}}lineseg", textpos="0")
    payload = etree.tostring(section, xml_declaration=True, encoding="UTF-8")

    package = HwpxPackage.open(_build_package())
    package.set_part("Contents/section0.xml", payload)

    stored_section = package.read("Contents/section0.xml")
    assert b"linesegarray" in stored_section.lower()

    output = package.save()
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" in section_xml.lower()


def test_save_updates_normalizes_named_section_style_reference() -> None:
    package = HwpxPackage.open(_build_package())

    output = package.save(
        updates={
            "Contents/header.xml": _HEADER_XML_WITH_TEST_STYLE,
            "Contents/section0.xml": _section_xml_with_named_style_ref(),
        }
    )

    assert isinstance(output, bytes)
    assert validate_editor_open_safety(output).ok
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"styleIDRef=\"TestStyle\"" not in section_xml
    assert b"styleIDRef=\"26\"" in section_xml


def test_save_normalizes_existing_named_section_style_reference() -> None:
    package = HwpxPackage.open(_build_package())
    package._files["Contents/header.xml"] = _HEADER_XML_WITH_TEST_STYLE
    package._files["Contents/section0.xml"] = _section_xml_with_named_style_ref()

    output = package.save()

    assert isinstance(output, bytes)
    assert validate_editor_open_safety(output).ok
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"styleIDRef=\"TestStyle\"" not in section_xml
    assert b"styleIDRef=\"26\"" in section_xml


def test_public_package_save_api_does_not_expose_open_safety_bypass() -> None:
    parameters = inspect.signature(HwpxPackage.save).parameters

    assert "verify_open_safety" not in parameters
    assert "_unchecked_token" not in parameters


def test_header_set_part_normalizes_hwpml_root_namespace_surface() -> None:
    package = HwpxPackage.open(_build_package())
    package.set_part(
        "Contents/header.xml",
        (
            b"<?xml version='1.0' encoding='UTF-8'?>"
            + f"<hh:head xmlns:hh='{_HH_NS}' version='1.5' secCnt='1'/>".encode()
        ),
    )

    stored_header = package.read("Contents/header.xml")
    assert b"standalone='yes'" in stored_header or b'standalone="yes"' in stored_header
    assert b"xmlns:ha=" in stored_header
    assert b"xmlns:hp10=" in stored_header


def test_save_rejects_editor_unsafe_low_level_package_edit() -> None:
    package = _package_with_stale_lineseg()

    with pytest.raises(HwpxPackageError, match="open-safety validation"):
        package.save()


def test_save_rejects_document_validation_failure(monkeypatch) -> None:
    package = HwpxPackage.open(_build_package())

    def fail_validation(_source: object) -> object:
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(validator_module, "validate_document", fail_validation)

    with pytest.raises(HwpxPackageError, match="document validation could not run"):
        package.save()


def test_save_rejects_open_safety_bypass_parameter() -> None:
    package = _package_with_stale_lineseg()

    with pytest.raises(TypeError, match="verify_open_safety"):
        package.save(verify_open_safety=False)


def test_save_to_path_rejects_open_safety_bypass_parameter(tmp_path) -> None:
    target = tmp_path / "unsafe.hwpx"
    package = _package_with_stale_lineseg()

    with pytest.raises(TypeError, match="verify_open_safety"):
        package.save(target, verify_open_safety=False)

    assert not target.exists()


def test_internal_unchecked_snapshot_is_diagnostic_only() -> None:
    package = _package_with_stale_lineseg()
    package.version_info.set("buildNumber", "42")

    with pytest.raises(HwpxPackageError, match="internal diagnostic path"):
        package._save_bytes_unchecked()

    with pytest.raises(HwpxPackageError, match="internal diagnostic path"):
        package._save_to_bytes(verify_open_safety=False, mark_clean=False)

    with pytest.raises(HwpxPackageError, match="internal diagnostic path"):
        package._save_to_zip(io.BytesIO(), verify_open_safety=False)

    with pytest.raises(HwpxPackageError, match="cannot write to caller-provided"):
        package._save_to_zip(
            io.BytesIO(),
            verify_open_safety=False,
            _unchecked_token=_UNCHECKED_SAVE_TOKEN,
        )

    output = package._save_bytes_unchecked(
        _unchecked_token=_UNCHECKED_SAVE_TOKEN
    )

    assert isinstance(output, bytes)
    assert not validate_package(output).ok
    assert package.version_info.dirty


def test_internal_unchecked_save_cannot_write_to_path(tmp_path) -> None:
    target = tmp_path / "unsafe.hwpx"
    package = _package_with_stale_lineseg()

    with pytest.raises(HwpxPackageError, match="cannot write to caller-provided"):
        package._save_to_zip(
            target,
            verify_open_safety=False,
            _unchecked_token=_UNCHECKED_SAVE_TOKEN,
        )

    assert not target.exists()


def test_raw_archive_writer_is_internal_save_path_only() -> None:
    package = _package_with_stale_lineseg()
    buffer = io.BytesIO()

    with ZipFile(buffer, "w") as archive:
        with pytest.raises(HwpxPackageError, match="internal save path"):
            package._write_archive(archive)

        with pytest.raises(HwpxPackageError, match="internal save path"):
            package._write_mimetype(archive)

        with pytest.raises(HwpxPackageError, match="internal save path"):
            package._write_zip_entry(
                archive,
                "Contents/section0.xml",
                package.read("Contents/section0.xml"),
                ZIP_DEFLATED,
            )


def test_save_to_path_preserves_target_when_low_level_package_edit_is_unsafe(tmp_path) -> None:
    target = tmp_path / "safe.hwpx"
    original = HwpxDocument.new().to_bytes()
    target.write_bytes(original)
    package = _package_with_stale_lineseg()

    with pytest.raises(HwpxPackageError, match="open-safety validation"):
        package.save(target)

    assert target.read_bytes() == original
    assert validate_package(target).ok


def test_save_updates_normalizes_editor_unsafe_section_before_replacing_target(tmp_path) -> None:
    target = tmp_path / "safe-updates.hwpx"
    original = HwpxDocument.new().to_bytes()
    target.write_bytes(original)
    package = HwpxPackage.open(_build_package())

    result = package.save(
        target,
        updates={"Contents/section0.xml": _section_xml_with_stale_lineseg()},
    )

    assert result == target
    assert target.read_bytes() != original
    assert validate_editor_open_safety(target).ok
    with ZipFile(target, "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" not in section_xml.lower()


def test_failed_open_safety_save_keeps_version_dirty() -> None:
    package = _package_with_stale_lineseg()
    package.version_info.set("buildNumber", "42")

    with pytest.raises(HwpxPackageError, match="open-safety validation"):
        package.save()

    assert package.version_info.dirty


def test_successful_open_safety_save_marks_version_clean() -> None:
    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")

    output = package.save()

    assert isinstance(output, bytes)
    assert not package.version_info.dirty


def test_save_to_stream_rejects_short_write_and_keeps_version_dirty() -> None:
    class ShortWriteStream(io.BytesIO):
        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")
    stream = ShortWriteStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(HwpxPackageError, match="short write"):
        package.save(stream)

    assert package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_rolls_back_write_exception_and_keeps_version_dirty() -> None:
    class FailingStream(io.BytesIO):
        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            raise OSError("stream write failed")

    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")
    stream = FailingStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(OSError, match="stream write failed"):
        package.save(stream)

    assert package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_rolls_back_unreadable_stream_at_eof() -> None:
    class UnreadableShortWriteStream(io.BytesIO):
        def read(self, *args: object) -> bytes:  # type: ignore[override]
            raise OSError("not readable")

        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")
    stream = UnreadableShortWriteStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(HwpxPackageError, match="short write"):
        package.save(stream)

    assert package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_does_not_truncate_unreadable_middle_stream() -> None:
    class UnreadableShortWriteStream(io.BytesIO):
        def read(self, *args: object) -> bytes:  # type: ignore[override]
            raise OSError("not readable")

        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    original = b"prefix-middle-tail"
    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")
    stream = UnreadableShortWriteStream(original)
    stream.seek(7)

    with pytest.raises(HwpxPackageError, match="checkpointable stream"):
        package.save(stream)

    assert package.version_info.dirty
    assert stream.getvalue() == original


def test_save_to_stream_rejects_non_seekable_stream_before_writing() -> None:
    class NonSeekableStream:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def tell(self) -> int:
            raise OSError("not seekable")

        def write(self, payload: bytes) -> int:
            self.writes.append(payload)
            return len(payload)

    package = HwpxPackage.open(_build_package())
    package.version_info.set("buildNumber", "42")
    stream = NonSeekableStream()

    with pytest.raises(HwpxPackageError, match="checkpointable stream"):
        package.save(stream)  # type: ignore[arg-type]

    assert package.version_info.dirty
    assert stream.writes == []


def test_missing_required_files_raise_structure_error() -> None:
    with pytest.raises(HwpxStructureError):
        HwpxPackage.open(_build_package(include_mimetype=False))

    with pytest.raises(HwpxStructureError):
        HwpxPackage.open(_build_package(include_container=False))

    package = HwpxPackage.open(_build_package(include_version=False))
    assert package.version_path() is None
    assert package.version_info.get("tagetApplication") == "WORDPROCESSOR"


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
        archive.writestr("Contents/section0.xml", _SECTION_XML)
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
        archive.writestr("Contents/section0.xml", _SECTION_XML)
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


def test_first_run_on_builtin_template_emits_no_warnings(caplog, tmp_path) -> None:
    """새 사용자의 첫 프로그램(new→add→save→open)이 경고 없이 조용해야 한다.

    빈 문서에 masterPage/history가 없는 것, version.xml이 manifest에 선언되지
    않고 고정 경로에 있는 것은 실제 한컴 산출물과 동일한 정상 상태다.
    """
    import logging

    caplog.set_level(logging.WARNING)

    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    target = tmp_path / "first.hwpx"
    document.save_to_path(target)

    reopened = HwpxDocument.open(target)
    package = reopened.package
    assert package.master_page_paths() == []
    assert package.history_paths() == []
    assert package.version_path() == "version.xml"

    assert [record for record in caplog.records if record.name.startswith("hwpx")] == []


def test_manifest_missing_master_page_with_real_file_still_warns(caplog) -> None:
    """manifest가 실재 masterPage 파일을 놓친 경우는 여전히 경고한다."""
    import logging

    caplog.set_level(logging.WARNING)
    package = HwpxPackage.open(
        _build_package(
            overrides={"MasterPages/MasterPage0.xml": b"<m/>"},
        )
    )
    paths = package.master_page_paths()
    assert paths == ["MasterPages/MasterPage0.xml"]
    assert "masterPage" in caplog.text


MB = 1024 * 1024


def _bomb(stored: int, declared: int | None = None) -> bytes:
    """A valid package with one oversized unreferenced member.

    ``declared`` rewrites the central directory's uncompressed size for that
    member, leaving the compressed bytes alone.
    """

    buffer = io.BytesIO()
    HwpxDocument.new().save_to_stream(buffer)
    with ZipFile(buffer, "a", ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("BinData/x.bin", b"\0" * stored)
    raw = bytearray(buffer.getvalue())
    if declared is None:
        return bytes(raw)
    at = raw.rindex(b"PK\x01\x02")
    raw[at + 16 : at + 20] = binascii.crc32(b"\0" * declared).to_bytes(4, "little")
    raw[at + 24 : at + 28] = declared.to_bytes(4, "little")
    return bytes(raw)


def test_forged_member_size_is_rejected() -> None:
    """A member may not declare less data than it stores."""

    with pytest.raises(HwpxSecurityError, match="declares less data"):
        HwpxPackage.open(_bomb(200 * MB, declared=16))


def test_forged_member_size_zero_is_rejected() -> None:
    """Declaring zero must not skip the remaining metadata checks."""

    with pytest.raises(HwpxSecurityError, match="declares less data"):
        HwpxPackage.open(_bomb(200 * MB, declared=0))


def test_paragraph_patch_rejects_compression_bomb(tmp_path) -> None:
    """The byte-splice patch path reaches guard_zip_file like the reader does."""

    source = tmp_path / "bomb.hwpx"
    source.write_bytes(_bomb(200 * MB))
    patches = [{"section_path": "Contents/section0.xml", "paragraph_index": 0, "text": "x"}]

    with pytest.raises(HwpxSecurityError):
        hwpx.paragraph_patch(str(source), patches)


def test_declaration_within_limits_cannot_over_allocate() -> None:
    """A declared size inside every limit must still bound what is decompressed.

    10 MB declared is under the per-member limit and the ratio is under the
    ceiling, so no metadata check can reject this package. Only counting the
    bytes that actually arrive keeps the read proportional to the declaration
    rather than to the 100 MB the member really stores.
    """

    package = _bomb(100 * MB, declared=10 * MB)

    with ZipFile(io.BytesIO(package)) as archive:
        guard_zip_file(archive)  # nothing to reject: the declaration is legal
        info = next(i for i in archive.infolist() if i.filename == "BinData/x.bin")
        tracemalloc.start()
        try:
            payload = read_member(archive, info)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    assert len(payload) == 10 * MB
    assert len(payload) <= MAX_ZIP_MEMBER_BYTES
    # An unbounded read inflates all 100 MB before truncating; ~210 MB peak.
    assert peak < 64 * MB, f"read was not bounded: peak {peak / MB:.1f} MB"


def test_format_sniffing_does_not_read_an_oversized_mimetype() -> None:
    """`accepts()` must reject a hostile archive without expanding `mimetype`.

    A 4 MiB `mimetype` deflates to about 4 KB, so the archive is small enough to
    look harmless while the member itself trips the compression-ratio limit.
    """

    from hwpx.ingest.base import DocumentSourceInfo
    from hwpx.ingest.hwpx_converter import HwpxMarkdownConverter

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("mimetype", b"\0" * (4 * MB))
        archive.writestr("Contents/section0.xml", b"<x/>")
    package = buffer.getvalue()
    source = DocumentSourceInfo(extension=".bin", mimetype=None, filename="x.bin")

    tracemalloc.start()
    try:
        accepted = HwpxMarkdownConverter().accepts(io.BytesIO(package), source)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert accepted is False
    assert peak < 1 * MB, f"mimetype was expanded: peak {peak / MB:.1f} MB"


def test_rewrite_package_parts_rejects_excess_members() -> None:
    """The public rewrite entry point applies the archive-wide limits too."""

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for index in range(MAX_ZIP_ENTRIES + 1):
            archive.writestr(f"p{index}.xml", b"<x/>")
    package = buffer.getvalue()

    with pytest.raises(HwpxSecurityError, match="too many entries"):
        hwpx.patch.rewrite_package_parts(package, {})


def _archive(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_directory_named_member_cannot_carry_data() -> None:
    """`is_dir()` is only a trailing-slash test, so such entries must be empty.

    Otherwise a member opts out of every archive-wide limit just by naming
    itself a directory, while `ZipFile.open()` still reads its payload.
    """

    package = _archive({f"d{index}/": b"\0" * (8 * MB) for index in range(4)})

    with pytest.raises(HwpxSecurityError, match="directory entry carries data"):
        with ZipFile(io.BytesIO(package)) as archive:
            guard_zip_file(archive)


def test_directory_named_entries_count_towards_nothing_but_are_checked() -> None:
    """Directory-named entries must not be a way past the entry-count limit."""

    package = _archive({f"d{index}/": b"x" for index in range(MAX_ZIP_ENTRIES + 1)})

    with pytest.raises(HwpxSecurityError):
        with ZipFile(io.BytesIO(package)) as archive:
            guard_zip_file(archive)


def test_save_pipeline_guards_untrusted_bytes() -> None:
    """`SavePipeline` is a public entry point and takes bytes from the caller."""

    from hwpx.quality import SavePipeline

    package = _archive({"Contents/section0.xml": b"<r>" + b"<a/>" * (2 * MB) + b"</r>"})

    with pytest.raises(HwpxSecurityError):
        SavePipeline().run(package)


def test_empty_patch_list_still_guards_the_source(tmp_path) -> None:
    """The early return hands the source to the save pipeline, so it must guard."""

    source = tmp_path / "bomb.hwpx"
    source.write_bytes(_archive({"Contents/section0.xml": b"<r>" + b"<a/>" * (2 * MB) + b"</r>"}))

    with pytest.raises(HwpxSecurityError):
        hwpx.paragraph_patch(str(source), [])


def test_known_small_parts_are_read_under_a_tight_limit() -> None:
    """`mimetype` and friends must not cost the generic per-member allowance."""

    from hwpx.tools.package_validator import validate_package

    # Incompressible, so the archive-wide ratio limit has nothing to catch and
    # the read limit is the only thing between the caller and 16 MiB.
    package = _archive(
        {"mimetype": os.urandom(16 * MB), "Contents/section0.xml": b"<x/>"}
    )

    tracemalloc.start()
    try:
        validate_package(package)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 8 * MB, f"mimetype was expanded: peak {peak / MB:.1f} MB"


@pytest.mark.parametrize("method", [12, 14], ids=["bzip2", "lzma"])
def test_unsupported_compression_methods_are_refused(method: int) -> None:
    """CPython only bounds ZIP_DEFLATED.

    ``ZipExtFile._read1`` passes ``max_length`` to zlib for deflate but calls
    ``decompress(data)`` with no limit for every other method, so a chunked read
    cannot bound bzip2 or lzma: the member inflates in full and is only then
    truncated to the declared size. HWPX uses stored and deflate only.
    """

    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("BinData/x.bin", b"\0" * (8 * MB), compress_type=method)

    with pytest.raises(HwpxSecurityError, match="unsupported compression method"):
        with ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            guard_zip_file(archive)


@pytest.mark.parametrize(
    "name", ["C:/Windows/pwned.txt", "D:\\pwned.txt", "//server/share/pwned.txt"]
)
def test_drive_relative_member_names_are_refused(name: str) -> None:
    """A drive-qualified name escapes the output directory when joined on Windows."""

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(name, b"x")

    with pytest.raises(HwpxSecurityError, match="unsafe ZIP member path"):
        with ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            guard_zip_file(archive)


def test_pretty_unpack_does_not_amplify_through_indentation(tmp_path) -> None:
    """Indenting deeply nested XML must not be allowed to inflate the output."""

    from hwpx.tools.archive_cli import unpack_hwpx

    depth = 250
    payload = (
        b"<?xml version='1.0'?>"
        + b"".join(b"<n%d>" % index for index in range(depth))
        + b"<c/>" * 20000
        + b"".join(b"</n%d>" % index for index in reversed(range(depth)))
    )
    source = tmp_path / "deep.hwpx"
    source.write_bytes(
        _archive({"mimetype": b"application/hwp+zip", "Contents/section0.xml": payload})
    )

    unpack_hwpx(source, tmp_path / "out", pretty_xml=True)

    written = sum(f.stat().st_size for f in (tmp_path / "out").rglob("*") if f.is_file())
    assert written < 4 * len(payload), f"indentation amplified to {written} bytes"
