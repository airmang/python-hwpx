from __future__ import annotations

import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

import pytest

import hwpx.tools.repair as repair_module
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package
from hwpx.tools.recover import RecoverError, recover_entries
from hwpx.tools.repair import repair_from_recovered
from tests.test_repair_repack import _valid_parts

_MIMETYPE = b"application/hwp+zip"


def _write_zip(path: Path, parts: list[tuple[str, bytes, int]]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload, compress_type in parts:
            archive.writestr(name, payload, compress_type=compress_type)


def _truncate_before_central_directory(path: Path) -> None:
    marker = b"PK\x01\x02"
    data = path.read_bytes()
    offset = data.index(marker)
    path.write_bytes(data[:offset])


def _local_header(
    name: str,
    payload: bytes,
    *,
    compression: int,
    crc: int,
    compressed_size: int | None = None,
    uncompressed_size: int,
) -> bytes:
    name_bytes = name.encode("utf-8")
    compressed_size = len(payload) if compressed_size is None else compressed_size
    return (
        struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0,
            compression,
            0,
            0,
            crc,
            compressed_size,
            uncompressed_size,
            len(name_bytes),
            0,
        )
        + name_bytes
        + payload
    )


def _raw_deflate(payload: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return compressor.compress(payload) + compressor.flush()


def test_recover_entries_scans_local_file_headers_when_central_directory_missing(tmp_path: Path) -> None:
    source = tmp_path / "broken.hwpx"
    _write_zip(
        source,
        [
            ("mimetype", _MIMETYPE, ZIP_STORED),
            ("META-INF/container.xml", b"<container/>", ZIP_DEFLATED),
            ("Contents/content.hpf", b"<package/>", ZIP_DEFLATED),
            ("BinData/raw.bin", b"\x00\x01stored payload", ZIP_STORED),
        ],
    )
    _truncate_before_central_directory(source)

    with pytest.raises(BadZipFile):
        ZipFile(source, "r").infolist()

    entries = recover_entries(source)

    assert entries["mimetype"] == _MIMETYPE
    assert entries["META-INF/container.xml"] == b"<container/>"
    assert entries["Contents/content.hpf"] == b"<package/>"
    assert entries["BinData/raw.bin"] == b"\x00\x01stored payload"
    assert tuple(entries) == (
        "mimetype",
        "META-INF/container.xml",
        "Contents/content.hpf",
        "BinData/raw.bin",
    )


def test_recover_entries_bounds_deflated_output(tmp_path: Path) -> None:
    source = tmp_path / "broken.hwpx"
    _write_zip(
        source,
        [
            ("mimetype", _MIMETYPE, ZIP_STORED),
            ("Contents/large.xml", b"a" * 128, ZIP_DEFLATED),
        ],
    )
    _truncate_before_central_directory(source)

    with pytest.raises(RecoverError, match="exceeds"):
        recover_entries(source, max_entry_size=64)


def test_recover_entries_skips_ambiguous_data_descriptor_entries(tmp_path: Path) -> None:
    source = tmp_path / "streamed.zip"
    source.write_bytes(
        b"PK\x03\x04"
        b"\x14\x00"
        b"\x08\x00"
        b"\x00\x00"
        b"\x00\x00"
        b"\x00\x00"
        b"\x00\x00\x00\x00"
        b"\x00\x00\x00\x00"
        b"\x00\x00\x00\x00"
        b"\x0a\x00"
        b"\x00\x00"
        b"mimetype"
        b"ignored"
    )

    assert recover_entries(source) == {}


def test_recover_entries_rejects_duplicate_names(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.hwpx"
    with pytest.warns(UserWarning, match="Duplicate name"):
        _write_zip(
            source,
            [
                ("mimetype", _MIMETYPE, ZIP_STORED),
                ("mimetype", b"application/other", ZIP_STORED),
            ],
        )
    _truncate_before_central_directory(source)

    with pytest.raises(RecoverError, match="duplicate"):
        recover_entries(source)


def test_recover_entries_rejects_truncated_deflate_stream_with_zero_crc(tmp_path: Path) -> None:
    source = tmp_path / "truncated.zip"
    compressed = _raw_deflate(b"abc")[:1]
    source.write_bytes(
        _local_header(
            "Contents/bad.xml",
            compressed,
            compression=8,
            crc=0,
            uncompressed_size=3,
        )
    )

    with pytest.raises(RecoverError, match="incomplete DEFLATE"):
        recover_entries(source)


def test_recover_entries_rejects_uncompressed_size_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "size-mismatch.zip"
    payload = b"abc"
    compressed = _raw_deflate(payload)
    source.write_bytes(
        _local_header(
            "Contents/bad.xml",
            compressed,
            compression=8,
            crc=zlib.crc32(payload) & 0xFFFFFFFF,
            uncompressed_size=999,
        )
    )

    with pytest.raises(RecoverError, match="size does not match"):
        recover_entries(source)


def test_recover_entries_enforces_total_size_and_entry_count_limits(tmp_path: Path) -> None:
    source = tmp_path / "limits.hwpx"
    _write_zip(
        source,
        [
            ("mimetype", _MIMETYPE, ZIP_STORED),
            ("Contents/a.xml", b"a" * 4, ZIP_STORED),
        ],
    )
    _truncate_before_central_directory(source)

    with pytest.raises(RecoverError, match="max_total_size"):
        recover_entries(source, max_total_size=len(_MIMETYPE) + 1)
    with pytest.raises(RecoverError, match="max_entries"):
        recover_entries(source, max_entries=1)


def test_repair_from_recovered_preserves_output_when_mimetype_missing(tmp_path: Path) -> None:
    source = tmp_path / "missing.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_zip(source, [("Contents/content.hpf", b"<package/>", ZIP_DEFLATED)])
    _truncate_before_central_directory(source)
    output.write_bytes(b"existing output")

    with pytest.raises(FileNotFoundError):
        repair_from_recovered(source, output, overwrite=True)

    assert output.read_bytes() == b"existing output"
    assert list(tmp_path.glob("*.hwpx.tmp")) == []


def test_repair_from_recovered_refuses_existing_output_without_force(tmp_path: Path) -> None:
    source = tmp_path / "broken.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_zip(source, _valid_parts())
    _truncate_before_central_directory(source)
    output.write_bytes(b"existing output")

    with pytest.raises(FileExistsError):
        repair_from_recovered(source, output)

    assert output.read_bytes() == b"existing output"


def test_repair_from_recovered_writes_valid_mimetype_first_package(tmp_path: Path) -> None:
    source = tmp_path / "broken.hwpx"
    output = tmp_path / "repaired.hwpx"
    _write_zip(source, _valid_parts(mimetype_compress_type=ZIP_DEFLATED))
    _truncate_before_central_directory(source)

    result = repair_from_recovered(source, output)

    assert result.recovered is True
    assert result.reordered is True
    assert result.crc_ok is True
    assert result.open_safety["ok"] is True
    assert validate_package(output).ok
    with ZipFile(output, "r") as archive:
        infos = archive.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == ZIP_STORED


def test_repair_from_recovered_removes_stale_lineseg_layout_cache(tmp_path: Path) -> None:
    source = tmp_path / "broken-stale-lineseg.hwpx"
    output = tmp_path / "repaired.hwpx"
    stale_parts = [
        (
            name,
            payload.replace(
                b"</hp:p>",
                b'<hp:linesegarray><hp:lineseg textpos="999"/></hp:linesegarray></hp:p>',
                1,
            ),
            compress_type,
        )
        if name == "Contents/section0.xml"
        else (name, payload, compress_type)
        for name, payload, compress_type in _valid_parts()
    ]
    _write_zip(source, stale_parts)
    _truncate_before_central_directory(source)

    result = repair_from_recovered(source, output)

    assert result.recovered is True
    assert result.crc_ok is True
    assert validate_editor_open_safety(output).ok
    with ZipFile(output, "r") as archive:
        section_xml = archive.read("Contents/section0.xml").lower()
    assert b"linesegarray" not in section_xml


def test_repair_from_recovered_removes_complex_paragraph_layout_cache(tmp_path: Path) -> None:
    source = tmp_path / "broken-complex-lineseg.hwpx"
    output = tmp_path / "repaired.hwpx"
    stale_parts = [
        (
            name,
            payload.replace(
                b"</hp:p>",
                b'<hp:run charPrIDRef="0"><hp:ctrl id="field"/></hp:run>'
                b'<hp:linesegarray><hp:lineseg textpos="999"/></hp:linesegarray></hp:p>',
                1,
            ),
            compress_type,
        )
        if name == "Contents/section0.xml"
        else (name, payload, compress_type)
        for name, payload, compress_type in _valid_parts()
    ]
    _write_zip(source, stale_parts)
    _truncate_before_central_directory(source)

    result = repair_from_recovered(source, output)

    assert result.recovered is True
    assert result.crc_ok is True
    assert validate_editor_open_safety(output).ok
    with ZipFile(output, "r") as archive:
        section_xml = archive.read("Contents/section0.xml").lower()
    assert b"linesegarray" not in section_xml


def test_repair_from_recovered_open_safety_failure_preserves_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailedOpenSafety:
        ok = False
        summary = "forced reopen failure"

    source = tmp_path / "broken.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_zip(source, _valid_parts())
    _truncate_before_central_directory(source)
    output.write_bytes(b"existing output")
    monkeypatch.setattr(
        repair_module,
        "validate_editor_open_safety",
        lambda _path: _FailedOpenSafety(),
    )

    with pytest.raises(ValueError, match="editor-open safety"):
        repair_from_recovered(source, output, overwrite=True)

    assert output.read_bytes() == b"existing output"
    assert list(tmp_path.glob("*.hwpx.tmp")) == []
