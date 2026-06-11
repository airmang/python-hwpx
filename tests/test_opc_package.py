from __future__ import annotations

import inspect
import io
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.opc.package import (
    HwpxPackage,
    HwpxPackageError,
    HwpxStructureError,
    _UNCHECKED_SAVE_TOKEN,
)
from hwpx.opc.security import HwpxSecurityError
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
        _section_xml_with_stale_lineseg(complex_paragraph=True),
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
        updates={
            "Contents/section0.xml": _section_xml_with_stale_lineseg(
                complex_paragraph=True
            )
        }
    )

    assert isinstance(output, bytes)
    report = validate_package(output)
    assert not any(is_editor_open_blocking_issue(issue) for issue in report.errors)
    with ZipFile(io.BytesIO(output), "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" not in section_xml.lower()


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
