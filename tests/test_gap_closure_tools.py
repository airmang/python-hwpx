from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_package
from hwpx.tools.page_guard import collect_metrics, compare_metrics
from hwpx.tools.text_extract_cli import extract_markdown, extract_plain

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


def _build_invalid_package() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/container.xml", _CONTAINER_XML)
        archive.writestr("Contents/content.hpf", _MANIFEST_XML)
        archive.writestr("Contents/header.xml", _HEADER_XML)
        archive.writestr("Contents/section0.xml", _SECTION_XML)
        archive.writestr("version.xml", _VERSION_XML)
    return buffer.getvalue()


def test_package_validator_accepts_valid_document() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("validator smoke test")

    report = validate_package(document.to_bytes())

    assert report.ok
    assert "Contents/header.xml" in report.checked_parts


def test_package_validator_reports_missing_mimetype() -> None:
    report = validate_package(_build_invalid_package())

    assert not report.ok
    assert any(issue.part_name == "mimetype" for issue in report.issues)


def test_page_guard_detects_text_drift() -> None:
    reference = HwpxDocument.new()
    reference.add_paragraph("alpha")
    reference.add_paragraph("beta")

    output = HwpxDocument.new()
    output.add_paragraph("alpha" * 12)
    output.add_paragraph("beta" * 12)

    errors = compare_metrics(
        collect_metrics(reference.to_bytes()),
        collect_metrics(output.to_bytes()),
        max_text_delta_ratio=0.05,
        max_paragraph_delta_ratio=0.05,
    )

    assert any("total text length drift exceeded" in error for error in errors)


def test_text_extract_cli_functions_include_table_text(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("Title")
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "Cell"

    source = tmp_path / "sample.hwpx"
    source.write_bytes(document.to_bytes())

    plain = extract_plain(str(source), include_tables=True)
    markdown = extract_markdown(str(source))

    assert "Title" in plain
    assert "Cell" in plain
    assert "Title" in markdown
    assert "Cell" in markdown


def test_validate_preserves_dirty_state() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("dirty paragraph")

    section = document.sections[-1]
    assert section.dirty

    document.validate()

    assert section.dirty


def test_office_pack_unpack_roundtrip(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("Roundtrip")
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "A1"

    source = tmp_path / "source.hwpx"
    unpack_dir = tmp_path / "unpacked"
    repacked = tmp_path / "repacked.hwpx"
    source.write_bytes(document.to_bytes())

    subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "office" / "unpack.py"), str(source), str(unpack_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "office" / "pack.py"), str(unpack_dir), str(repacked)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert validate_package(repacked.read_bytes()).ok
    assert compare_metrics(
        collect_metrics(source.read_bytes()),
        collect_metrics(repacked.read_bytes()),
    ) == []


def test_analyze_template_script_smoke(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    source.write_bytes(HwpxDocument.new().to_bytes())

    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "analyze_template.py"), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "== header summary ==" in result.stdout
    assert "== section summary ==" in result.stdout
