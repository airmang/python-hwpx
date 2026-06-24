from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

import hwpx.document as document_module
from hwpx.document import HwpxDocument
from hwpx.opc.package import HwpxPackageError
from hwpx.tools.package_validator import validate_editor_open_safety
from hwpx.tools import validator as validator_module


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _section_xml_with_stale_lineseg(document: HwpxDocument) -> bytes:
    section = etree.fromstring(document._package.read("Contents/section0.xml"))
    paragraph = section.find(f".//{{{_HP_NS}}}p")
    assert paragraph is not None
    line_array = etree.SubElement(paragraph, f"{{{_HP_NS}}}linesegarray")
    etree.SubElement(line_array, f"{{{_HP_NS}}}lineseg", textpos="999")
    return etree.tostring(section, xml_declaration=True, encoding="UTF-8")


def test_to_bytes_returns_hwpx_bytes() -> None:
    document = HwpxDocument.new()

    output = document.to_bytes()

    assert isinstance(output, bytes)
    assert output.startswith(b"PK")


def test_save_to_path_returns_same_path(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    output_path = tmp_path / "saved.hwpx"

    result = document.save_to_path(output_path)

    assert result == output_path
    assert output_path.exists()


def test_public_document_save_apis_do_not_expose_open_safety_bypass() -> None:
    for api in (
        HwpxDocument.to_bytes,
        HwpxDocument.save_to_path,
        HwpxDocument.save_to_stream,
        HwpxDocument.save,
    ):
        parameters = inspect.signature(api).parameters

        assert "verify_open_safety" not in parameters
        assert "_unchecked_token" not in parameters


def test_to_bytes_rejects_generated_package_that_fails_open_safety() -> None:
    document = HwpxDocument.new()
    document._package._mimetype = "application/octet-stream"

    with pytest.raises((ValueError, HwpxPackageError), match="open-safety validation"):
        document.to_bytes()


def test_to_bytes_rejects_document_validation_failure(monkeypatch) -> None:
    document = HwpxDocument.new()

    def fail_validation(_source: object) -> object:
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(validator_module, "validate_document", fail_validation)

    with pytest.raises((ValueError, HwpxPackageError), match="document validation could not run"):
        document.to_bytes()


def test_save_to_path_preserves_existing_file_when_document_validation_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "existing.hwpx"
    original = HwpxDocument.new().to_bytes()
    target.write_bytes(original)
    document = HwpxDocument.new()

    def fail_validation(_source: object) -> object:
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(validator_module, "validate_document", fail_validation)

    with pytest.raises((ValueError, HwpxPackageError), match="document validation could not run"):
        document.save_to_path(target)

    assert target.read_bytes() == original


def test_validate_can_report_unsafe_current_state_without_open_safety_exception() -> None:
    document = HwpxDocument.new()
    document._package._mimetype = "application/octet-stream"

    report = document.validate()

    assert hasattr(report, "ok")


def test_private_document_raw_bytes_api_does_not_accept_open_safety_bypass() -> None:
    document = HwpxDocument.new()
    document._package._mimetype = "application/octet-stream"

    with pytest.raises(TypeError, match="verify_open_safety"):
        document._to_bytes_raw(reset_dirty=False, verify_open_safety=False)


def test_save_to_path_preserves_existing_file_when_open_safety_fails(tmp_path: Path) -> None:
    target = tmp_path / "existing.hwpx"
    original = HwpxDocument.new().to_bytes()
    target.write_bytes(original)

    document = HwpxDocument.new()
    document._package._mimetype = "application/octet-stream"

    with pytest.raises((ValueError, HwpxPackageError), match="open-safety validation"):
        document.save_to_path(target)

    assert target.read_bytes() == original


def test_save_to_path_normalizes_low_level_package_part_mutation_before_replace(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing-low-level.hwpx"
    original = HwpxDocument.new().to_bytes()
    target.write_bytes(original)
    document = HwpxDocument.open(original)
    document._package.set_part(
        "Contents/section0.xml",
        _section_xml_with_stale_lineseg(document),
    )

    result = document.save_to_path(target)

    assert result == target
    assert target.read_bytes() != original
    assert validate_editor_open_safety(target).ok
    with ZipFile(target, "r") as archive:
        section_xml = archive.read("Contents/section0.xml")
    assert b"linesegarray" not in section_xml.lower()


def test_save_to_stream_returns_same_stream() -> None:
    document = HwpxDocument.new()
    stream = BytesIO()

    result = document.save_to_stream(stream)

    assert result is stream
    stream.seek(0)
    assert stream.read(2) == b"PK"


def test_save_to_stream_does_not_write_when_open_safety_fails() -> None:
    document = HwpxDocument.new()
    document._package._mimetype = "application/octet-stream"
    stream = BytesIO(b"sentinel")

    with pytest.raises((ValueError, HwpxPackageError), match="open-safety validation"):
        document.save_to_stream(stream)

    assert stream.getvalue() == b"sentinel"


def test_to_bytes_marks_low_level_version_clean_after_success() -> None:
    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")

    output = document.to_bytes()

    assert isinstance(output, bytes)
    assert not document._package.version_info.dirty


def test_to_bytes_keeps_low_level_version_dirty_when_open_safety_fails(monkeypatch) -> None:
    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")

    def fail_open_safety(_self, _archive_bytes: bytes) -> None:
        raise ValueError("forced reopen failure")

    monkeypatch.setattr(HwpxDocument, "_run_open_safety_validation", fail_open_safety)

    with pytest.raises(ValueError, match="forced reopen failure"):
        document.to_bytes()

    assert document._package.version_info.dirty


def test_save_to_path_keeps_low_level_version_dirty_when_write_fails(tmp_path: Path, monkeypatch) -> None:
    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")

    def fail_write(_path: str | Path, _payload: bytes) -> None:
        raise OSError("disk full")

    # The atomic writer now lives in the single SavePipeline that every write
    # funnels through; patch it there to simulate a write failure.
    monkeypatch.setattr("hwpx.quality.save_pipeline.write_bytes_atomically", fail_write)

    with pytest.raises(OSError, match="disk full"):
        document.save_to_path(tmp_path / "failed.hwpx")

    assert document._package.version_info.dirty


def test_save_to_stream_rejects_short_write_and_keeps_version_dirty() -> None:
    class ShortWriteStream(BytesIO):
        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")
    stream = ShortWriteStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(OSError, match="short write"):
        document.save_to_stream(stream)

    assert document._package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_rolls_back_write_exception_and_keeps_version_dirty() -> None:
    class FailingStream(BytesIO):
        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            raise OSError("stream write failed")

    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")
    stream = FailingStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(OSError, match="stream write failed"):
        document.save_to_stream(stream)

    assert document._package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_rolls_back_unreadable_stream_at_eof() -> None:
    class UnreadableShortWriteStream(BytesIO):
        def read(self, *args: object) -> bytes:  # type: ignore[override]
            raise OSError("not readable")

        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")
    stream = UnreadableShortWriteStream(b"existing output")
    stream.seek(0, 2)

    with pytest.raises(OSError, match="short write"):
        document.save_to_stream(stream)

    assert document._package.version_info.dirty
    assert stream.getvalue() == b"existing output"


def test_save_to_stream_does_not_truncate_unreadable_middle_stream() -> None:
    class UnreadableShortWriteStream(BytesIO):
        def read(self, *args: object) -> bytes:  # type: ignore[override]
            raise OSError("not readable")

        def write(self, payload: bytes) -> int:  # type: ignore[override]
            super().write(payload[:7])
            return 7

    original = b"prefix-middle-tail"
    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")
    stream = UnreadableShortWriteStream(original)
    stream.seek(7)

    with pytest.raises(OSError, match="checkpointable stream"):
        document.save_to_stream(stream)

    assert document._package.version_info.dirty
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

    document = HwpxDocument.new()
    document._package.version_info.set("buildNumber", "42")
    stream = NonSeekableStream()

    with pytest.raises(OSError, match="checkpointable stream"):
        document.save_to_stream(stream)  # type: ignore[arg-type]

    assert document._package.version_info.dirty
    assert stream.writes == []


def test_save_deprecated_wrapper_warns_and_routes_to_new_methods(tmp_path: Path) -> None:
    document = HwpxDocument.new()

    with pytest.deprecated_call(match="deprecated"):
        path_result = document.save(tmp_path / "wrapped-path.hwpx")
    assert path_result == tmp_path / "wrapped-path.hwpx"

    with pytest.deprecated_call(match="deprecated"):
        bytes_result = document.save()
    assert isinstance(bytes_result, bytes)

    stream = BytesIO()
    with pytest.deprecated_call(match="deprecated"):
        stream_result = document.save(stream)
    assert stream_result is stream
