from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from hwpx import HwpxDocument
from hwpx.tools import archive_cli
from hwpx.tools.archive_cli import pack_hwpx, unpack_hwpx
from hwpx.tools.package_validator import validate_package
from hwpx.tools.page_guard import collect_metrics, compare_metrics
from hwpx.tools.template_analyzer import analyze_template, extract_template_parts

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTAINER_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b"<rootfiles>"
    b'<rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
    b"</rootfiles>"
    b"</container>"
)
_MANIFEST_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
    b"<opf:manifest>"
    b'<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    b'<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    b"</opf:manifest>"
    b"<opf:spine>"
    b'<opf:itemref idref="section0"/>'
    b"</opf:spine>"
    b"</opf:package>"
)
_VERSION_XML = b'<?xml version="1.0" encoding="UTF-8"?><version/>'
_HEADER_XML = b'<?xml version="1.0" encoding="UTF-8"?><header/>'
_SECTION_XML = b'<?xml version="1.0" encoding="UTF-8"?><section/>'


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )


def _build_invalid_package() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/container.xml", _CONTAINER_XML)
        archive.writestr("Contents/content.hpf", _MANIFEST_XML)
        archive.writestr("Contents/header.xml", _HEADER_XML)
        archive.writestr("Contents/section0.xml", _SECTION_XML)
        archive.writestr("version.xml", _VERSION_XML)
    return buffer.getvalue()


def _document_with_structure() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("Title")
    document.add_bookmark("bookmark-one")
    document.add_rectangle(7200, 3600)
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "Cell"
    return document


def test_package_validator_accepts_valid_document() -> None:
    report = validate_package(_document_with_structure().to_bytes())

    assert report.ok
    assert "Contents/header.xml" in report.checked_parts


def test_package_validator_reports_missing_mimetype() -> None:
    report = validate_package(_build_invalid_package())

    assert not report.ok
    assert any(issue.part_name == "mimetype" for issue in report.issues)


def test_unpack_pack_roundtrip_via_cli(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    unpack_dir = tmp_path / "unpacked"
    repacked = tmp_path / "repacked.hwpx"
    source.write_bytes(_document_with_structure().to_bytes())

    _run_module("hwpx.tools.archive_cli", "unpack", str(source), str(unpack_dir))
    metadata_path = unpack_dir / archive_cli._PACK_METADATA_NAME
    assert metadata_path.is_file()

    _run_module("hwpx.tools.archive_cli", "pack", str(unpack_dir), str(repacked))

    assert validate_package(repacked.read_bytes()).ok
    assert compare_metrics(
        collect_metrics(source.read_bytes()),
        collect_metrics(repacked.read_bytes()),
    ) == []


def test_unpack_refuses_nonempty_output_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output_dir = tmp_path / "out"
    source.write_bytes(_document_with_structure().to_bytes())
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        unpack_hwpx(source, output_dir)


def test_pack_refuses_existing_output_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    unpack_dir = tmp_path / "unpacked"
    repacked = tmp_path / "result.hwpx"
    source.write_bytes(_document_with_structure().to_bytes())
    unpack_hwpx(source, unpack_dir)
    repacked.write_bytes(b"placeholder")

    with pytest.raises(FileExistsError):
        pack_hwpx(unpack_dir, repacked)


def test_page_guard_detects_shape_and_control_drift() -> None:
    reference = _document_with_structure()

    output = HwpxDocument.new()
    output.add_paragraph("Title")
    table = output.add_table(1, 1)
    table.cell(0, 0).text = "Cell"

    errors = compare_metrics(
        collect_metrics(reference.to_bytes()),
        collect_metrics(output.to_bytes()),
    )

    assert any("shape count mismatch" in error for error in errors)
    assert any("control type histogram mismatch" in error for error in errors)


def test_analyze_template_cli_extracts_parts_and_json(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    extract_dir = tmp_path / "extract"
    header_copy = tmp_path / "header.xml"
    section_copy = tmp_path / "section0.xml"
    json_path = tmp_path / "summary.json"
    source.write_bytes(_document_with_structure().to_bytes())

    result = _run_module(
        "hwpx.tools.template_analyzer",
        str(source),
        "--extract-dir",
        str(extract_dir),
        "--extract-header",
        str(header_copy),
        "--extract-section",
        str(section_copy),
        "--output-json",
        str(json_path),
    )

    assert "extracted:" in result.stdout
    assert (extract_dir / "Contents" / "header.xml").is_file()
    assert (extract_dir / "Contents" / "content.hpf").is_file()
    assert header_copy.is_file()
    assert section_copy.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["header_paths"][0] == "Contents/header.xml"
    assert payload["proxy_metrics"]["table_count"] == 1


def test_analyze_template_api_reports_proxy_metrics(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    source.write_bytes(_document_with_structure().to_bytes())

    analysis = analyze_template(source)
    written = extract_template_parts(source, extract_dir=tmp_path / "extract-api")

    assert analysis.proxy_metrics.shape_count >= 1
    assert analysis.proxy_metrics.control_count >= 1
    assert any(path.name == "header.xml" for path in written)


def test_text_extract_cli_smoke(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output_file = tmp_path / "sample.md"
    source.write_bytes(_document_with_structure().to_bytes())

    _run_module(
        "hwpx.tools.text_extract_cli",
        str(source),
        "--format",
        "markdown",
        "--output",
        str(output_file),
    )

    content = output_file.read_text(encoding="utf-8")
    assert "Title" in content
    assert "Cell" in content


def test_validate_preserves_dirty_state() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("dirty paragraph")

    section = document.sections[-1]
    assert section.dirty

    document.validate()

    assert section.dirty
