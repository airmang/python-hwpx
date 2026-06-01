from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from hwpx.oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from hwpx.tools.package_validator import validate_package
from hwpx.tools.repair import repair_repack

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIMETYPE = b"application/hwp+zip"
_VERSION_XML = b'<?xml version="1.0" encoding="UTF-8"?><version appVersion="1.0"/>'
_CONTAINER_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b"<rootfiles>"
    b'<rootfile full-path="Contents/content.hpf" '
    b'media-type="application/hwpml-package+xml"/>'
    b"</rootfiles>"
    b"</container>"
)
_CONTENT_HPF = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
    b"<opf:manifest>"
    b'<opf:item id="header" href="header.xml" media-type="application/xml"/>'
    b'<opf:item id="section0" href="section0.xml" media-type="application/xml"/>'
    b'<opf:item id="version" href="../version.xml" media-type="application/xml"/>'
    b"</opf:manifest>"
    b'<opf:spine><opf:itemref idref="section0"/></opf:spine>'
    b"</opf:package>"
)
_HWPML_NS_ATTRS = b" ".join(
    f'xmlns:{prefix}="{uri}"'.encode("utf-8")
    for prefix, uri in HWPML_COMPAT_ROOT_NAMESPACES.items()
)
_HEADER_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b"<hh:head "
    + _HWPML_NS_ATTRS
    + b" />"
)
_SECTION_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b"<hs:sec "
    + _HWPML_NS_ATTRS
    + b">"
    b'<hp:p id="1" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
    b'<hp:run charPrIDRef="0"><hp:t>Repair fixture</hp:t></hp:run>'
    b"</hp:p>"
    b"</hs:sec>"
)


def _write_hwpx(path: Path, parts: list[tuple[str, bytes, int]]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload, compress_type in parts:
            archive.writestr(name, payload, compress_type=compress_type)


def _corrupt_first_entry_payload(path: Path) -> None:
    data = bytearray(path.read_bytes())
    with ZipFile(path, "r") as archive:
        info = archive.infolist()[0]
        payload_offset = info.header_offset + 30 + len(info.filename.encode("utf-8")) + len(info.extra)
    data[payload_offset] = (data[payload_offset] + 1) % 256
    path.write_bytes(data)


def _valid_parts(*, mimetype_compress_type: int = ZIP_STORED) -> list[tuple[str, bytes, int]]:
    return [
        ("Contents/content.hpf", _CONTENT_HPF, ZIP_DEFLATED),
        ("META-INF/container.xml", _CONTAINER_XML, ZIP_DEFLATED),
        ("mimetype", _MIMETYPE, mimetype_compress_type),
        ("version.xml", _VERSION_XML, ZIP_DEFLATED),
        ("Contents/header.xml", _HEADER_XML, ZIP_DEFLATED),
        ("Contents/section0.xml", _SECTION_XML, ZIP_DEFLATED),
        ("BinData/image.bin", b"binary payload", ZIP_STORED),
    ]


def test_repair_repack_moves_mimetype_first_and_stored(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "repaired.hwpx"
    _write_hwpx(source, _valid_parts(mimetype_compress_type=ZIP_DEFLATED))

    result = repair_repack(source, output)

    assert result.output_path == output
    assert result.reordered is True
    assert result.crc_ok is True
    assert result.entries == tuple(name for name, _payload, _compress_type in _valid_parts())
    assert validate_package(output).ok
    with ZipFile(output, "r") as archive:
        infos = archive.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == ZIP_STORED
        assert archive.read("BinData/image.bin") == b"binary payload"
        assert [info.filename for info in infos] == [
            "mimetype",
            "Contents/content.hpf",
            "META-INF/container.xml",
            "version.xml",
            "Contents/header.xml",
            "Contents/section0.xml",
            "BinData/image.bin",
        ]


def test_repair_repack_is_idempotent_when_already_ordered(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "repaired.hwpx"
    _write_hwpx(
        source,
        [
            ("mimetype", _MIMETYPE, ZIP_STORED),
            *[part for part in _valid_parts() if part[0] != "mimetype"],
        ],
    )

    first = repair_repack(source, output)
    second = repair_repack(output, output, overwrite=True)

    assert first.reordered is False
    assert second.reordered is False
    assert second.crc_ok is True
    assert validate_package(output).ok


def test_repair_repack_requires_mimetype_without_touching_output(tmp_path: Path) -> None:
    source = tmp_path / "missing-mimetype.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_hwpx(source, [part for part in _valid_parts() if part[0] != "mimetype"])
    output.write_bytes(b"keep me")

    with pytest.raises(FileNotFoundError):
        repair_repack(source, output, overwrite=True)

    assert output.read_bytes() == b"keep me"


def test_repair_repack_failed_validation_preserves_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "bad-mimetype.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_hwpx(
        source,
        [
            ("mimetype", b"text/plain", ZIP_STORED),
            *[part for part in _valid_parts() if part[0] != "mimetype"],
        ],
    )
    output.write_bytes(b"existing output")

    with pytest.raises(ValueError, match="failed validation"):
        repair_repack(source, output, overwrite=True)

    assert output.read_bytes() == b"existing output"


def test_repair_repack_crc_failure_preserves_output_and_temp_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_hwpx(source, _valid_parts())
    _corrupt_first_entry_payload(source)
    output.write_bytes(b"existing output")

    with pytest.raises(Exception):
        repair_repack(source, output, overwrite=True)

    assert output.read_bytes() == b"existing output"
    assert list(tmp_path.glob("*.hwpx.tmp")) == []


def test_repair_repack_duplicate_mimetype_preserves_output_and_temp_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.hwpx"
    output = tmp_path / "existing.hwpx"
    with pytest.warns(UserWarning, match="Duplicate name"):
        _write_hwpx(source, [("mimetype", _MIMETYPE, ZIP_STORED), *_valid_parts()])
    output.write_bytes(b"existing output")

    with pytest.raises(ValueError, match="duplicate"):
        repair_repack(source, output, overwrite=True)

    assert output.read_bytes() == b"existing output"
    assert list(tmp_path.glob("*.hwpx.tmp")) == []


def test_repair_repack_rejects_oversized_entry_before_output_replace(tmp_path: Path) -> None:
    source = tmp_path / "large.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_hwpx(source, _valid_parts())
    output.write_bytes(b"existing output")

    with pytest.raises(ValueError, match="max_entry_size"):
        repair_repack(source, output, overwrite=True, max_entry_size=4)

    assert output.read_bytes() == b"existing output"


def test_repair_repack_refuses_existing_output_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "existing.hwpx"
    _write_hwpx(source, _valid_parts())
    output.write_bytes(b"existing output")

    with pytest.raises(FileExistsError):
        repair_repack(source, output)

    assert output.read_bytes() == b"existing output"


def test_hwpx_repair_help_is_registered() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "hwpx.tools.repair", "--help"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Repair or recover an HWPX archive" in completed.stdout
