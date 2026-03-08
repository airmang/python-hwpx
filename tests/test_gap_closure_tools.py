from __future__ import annotations

import io
import json
import struct
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from hwpx import HwpxDocument
from hwpx.opc.package import HwpxPackage
from hwpx.opc.relationships import MAIN_ROOTFILE_MEDIA_TYPE, resolve_part_name
from hwpx.tools import archive_cli
from hwpx.tools.archive_cli import pack_hwpx, unpack_hwpx
from hwpx.tools.package_validator import validate_package
from hwpx.tools.page_guard import collect_metrics, compare_metrics
from hwpx.tools.template_analyzer import analyze_template, extract_template_parts

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MIMETYPE = b"application/hwp+zip"
_VERSION_XML = b'<?xml version="1.0" encoding="UTF-8"?><version appVersion="1.0"/>'
_HEADER_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"/>'
)
_MASTER_PAGE_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<hm:masterPage xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page">'
    b'<hm:masterPageItem id="0" type="BOTH" name="template"/>'
    b"</hm:masterPage>"
)
_HISTORY_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<hhs:history xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history">'
    b'<hhs:historyEntry id="0"><hhs:comment>created</hhs:comment></hhs:historyEntry>'
    b"</hhs:history>"
)


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )


def _build_container_xml(
    rootfile_path: str,
    *,
    media_type: str | None = MAIN_ROOTFILE_MEDIA_TYPE,
) -> bytes:
    media_attr = "" if media_type is None else f' media-type="{media_type}"'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        f'<rootfile full-path="{rootfile_path}"{media_attr}/>'
        "</rootfiles>"
        "</container>"
    ).encode("utf-8")


def _build_manifest_xml(
    items: list[tuple[str, str, str]],
    spine_ids: list[str],
) -> bytes:
    manifest_items = "".join(
        f'<opf:item id="{item_id}" href="{href}" media-type="{media_type}"/>'
        for item_id, href, media_type in items
    )
    spine_items = "".join(f'<opf:itemref idref="{item_id}"/>' for item_id in spine_ids)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
        f"<opf:manifest>{manifest_items}</opf:manifest>"
        f"<opf:spine>{spine_items}</opf:spine>"
        "</opf:package>"
    ).encode("utf-8")


def _build_section_xml(text: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p id="1" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run>'
        "</hp:p>"
        "</hs:sec>"
    ).encode("utf-8")


def _zip_parts(parts: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in parts:
            if name == "mimetype":
                archive.writestr(name, payload, compress_type=ZIP_STORED)
            else:
                archive.writestr(name, payload)
    return buffer.getvalue()


def _build_manual_package(
    *,
    manifest_path: str = "Contents/content.hpf",
    header_href: str = "header.xml",
    section_href: str = "section0.xml",
    version_href: str = "../version.xml",
    text: str = "Fixture text",
    rootfile_media_type: str | None = MAIN_ROOTFILE_MEDIA_TYPE,
    extra_items: list[tuple[str, str, str]] | None = None,
    extra_parts: dict[str, bytes] | None = None,
) -> tuple[bytes, dict[str, str]]:
    header_path = resolve_part_name(manifest_path, header_href)
    section_path = resolve_part_name(manifest_path, section_href)
    items = [
        ("header", header_href, "application/xml"),
        ("section0", section_href, "application/xml"),
        ("version", version_href, "application/xml"),
    ]
    if extra_items:
        items.extend(extra_items)

    manifest_xml = _build_manifest_xml(items, ["header", "section0"])
    parts: list[tuple[str, bytes]] = [
        ("mimetype", _MIMETYPE),
        ("META-INF/container.xml", _build_container_xml(manifest_path, media_type=rootfile_media_type)),
        ("version.xml", _VERSION_XML),
        (manifest_path, manifest_xml),
        (header_path, _HEADER_XML),
        (section_path, _build_section_xml(text)),
    ]
    if extra_parts:
        parts.extend(extra_parts.items())

    paths = {
        "manifest": manifest_path,
        "header": header_path,
        "section": section_path,
        "version": "version.xml",
    }
    if extra_parts:
        for name in extra_parts:
            paths[name] = name

    return _zip_parts(parts), paths


def _build_asset_rich_package() -> tuple[bytes, dict[str, str]]:
    extra_items = [
        ("master-page-0", "masterPages/masterPage0.xml", "application/xml"),
        ("history-0", "history/history0.xml", "application/xml"),
        ("bindata-0", "../BinData/BIN0001.png", "image/png"),
    ]
    extra_parts = {
        "Contents/masterPages/masterPage0.xml": _MASTER_PAGE_XML,
        "Contents/history/history0.xml": _HISTORY_XML,
        "BinData/BIN0001.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    }
    return _build_manual_package(extra_items=extra_items, extra_parts=extra_parts)


def _corrupt_first_entry_crc(archive_bytes: bytes) -> bytes:
    corrupted = bytearray(archive_bytes)
    (
        signature,
        _version,
        _flags,
        _compression,
        _mtime,
        _mdate,
        _crc,
        _compressed_size,
        _uncompressed_size,
        name_len,
        extra_len,
    ) = struct.unpack("<IHHHHHIIIHH", corrupted[:30])
    assert signature == 0x04034B50
    payload_offset = 30 + name_len + extra_len
    corrupted[payload_offset] = (corrupted[payload_offset] + 1) % 256
    return bytes(corrupted)


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
    package_bytes, _ = _build_manual_package()
    with ZipFile(io.BytesIO(package_bytes), "r") as source:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for info in source.infolist():
                if info.filename == "mimetype":
                    continue
                archive.writestr(info.filename, source.read(info.filename))

    report = validate_package(buffer.getvalue())

    assert not report.ok
    assert any(issue.part_name == "mimetype" for issue in report.issues)


def test_package_validator_rejects_malformed_xml() -> None:
    package_bytes, _ = _build_manual_package()
    with ZipFile(io.BytesIO(package_bytes), "r") as source:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == "META-INF/container.xml":
                    payload = b"<container"
                if info.filename == "mimetype":
                    archive.writestr(info.filename, payload, compress_type=ZIP_STORED)
                else:
                    archive.writestr(info.filename, payload)

    report = validate_package(buffer.getvalue())

    assert not report.ok
    assert any(issue.part_name == "META-INF/container.xml" for issue in report.errors)


def test_package_validator_detects_crc_corruption() -> None:
    package_bytes, _ = _build_manual_package()

    report = validate_package(_corrupt_first_entry_crc(package_bytes))

    assert not report.ok
    assert any("CRC" in issue.message for issue in report.errors)


def test_package_validator_accepts_nondefault_rootfile_fixture() -> None:
    package_bytes, paths = _build_manual_package(
        manifest_path="Alt/content.hpf",
        header_href="parts/header-main.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Nondefault fixture",
    )

    package = HwpxPackage.open(package_bytes)
    report = validate_package(package_bytes)

    assert report.ok
    assert not report.warnings
    assert package.main_content.full_path == paths["manifest"]
    assert package.header_paths() == [paths["header"]]
    assert package.section_paths() == [paths["section"]]


def test_package_validator_warns_for_engine_fallback_rootfile_selection() -> None:
    package_bytes, paths = _build_manual_package(
        manifest_path="Alt/content.hpf",
        header_href="parts/header-main.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Fallback fixture",
        rootfile_media_type=None,
    )

    package = HwpxPackage.open(package_bytes)
    report = validate_package(package_bytes)

    assert package.main_content.full_path == paths["manifest"]
    assert report.ok
    assert any(issue.level == "warning" for issue in report.warnings)
    assert any(issue.part_name == "META-INF/container.xml" for issue in report.warnings)


def test_validator_and_engine_do_not_disagree_on_engine_valid_fixture() -> None:
    package_bytes, paths = _build_manual_package(
        manifest_path="Nested/content.hpf",
        header_href="parts/header.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Aligned fixture",
    )

    package = HwpxPackage.open(package_bytes)
    report = validate_package(package_bytes)

    assert report.ok
    assert package.main_content.full_path == paths["manifest"]
    assert package.header_paths() == [paths["header"]]
    assert package.section_paths() == [paths["section"]]


def test_document_roundtrip_preserves_nondefault_manifest_path() -> None:
    package_bytes, paths = _build_manual_package(
        manifest_path="Alt/content.hpf",
        header_href="parts/header-main.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Document roundtrip",
    )

    document = HwpxDocument.open(package_bytes)
    roundtrip = document.to_bytes()
    reopened = HwpxPackage.open(roundtrip)

    assert reopened.main_content.full_path == paths["manifest"]
    assert paths["manifest"] in reopened.part_names()
    assert validate_package(roundtrip).ok


def test_unpack_preserves_xml_bytes_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output_dir = tmp_path / "unpacked"
    package_bytes, paths = _build_manual_package(text="Raw XML")
    source.write_bytes(package_bytes)

    unpack_hwpx(source, output_dir)

    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        assert (output_dir / paths["manifest"]).read_bytes() == archive.read(paths["manifest"])
        assert (output_dir / paths["header"]).read_bytes() == archive.read(paths["header"])
        assert (output_dir / paths["section"]).read_bytes() == archive.read(paths["section"])
        assert (output_dir / "META-INF" / "container.xml").read_bytes() == archive.read(
            "META-INF/container.xml"
        )


def test_unpack_pretty_xml_reformats_payloads(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output_dir = tmp_path / "unpacked"
    package_bytes, paths = _build_manual_package(text="Pretty XML")
    source.write_bytes(package_bytes)

    _run_module(
        "hwpx.tools.archive_cli",
        "unpack",
        str(source),
        str(output_dir),
        "--pretty-xml",
    )

    with ZipFile(io.BytesIO(package_bytes), "r") as archive:
        original = archive.read(paths["manifest"])
    rewritten = (output_dir / paths["manifest"]).read_bytes()

    assert rewritten != original
    assert b"\n" in rewritten


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


def test_page_guard_collects_metrics_for_nondefault_rootfile_package() -> None:
    package_bytes, _ = _build_manual_package(
        manifest_path="Alt/content.hpf",
        header_href="parts/header-main.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Page guard fixture",
    )

    metrics = collect_metrics(package_bytes)

    assert metrics.section_count == 1
    assert metrics.paragraph_count == 1
    assert metrics.text_char_total_nospace > 0


def test_analyze_template_extract_dir_is_pack_ready(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    extract_dir = tmp_path / "extract"
    repacked = tmp_path / "repacked.hwpx"
    package_bytes, paths = _build_asset_rich_package()
    source.write_bytes(package_bytes)

    written = extract_template_parts(source, extract_dir=extract_dir)

    assert (extract_dir / "mimetype").is_file()
    assert (extract_dir / "META-INF" / "container.xml").is_file()
    assert (extract_dir / paths["manifest"]).is_file()
    assert (extract_dir / paths["header"]).is_file()
    assert (extract_dir / paths["section"]).is_file()
    assert (extract_dir / "Contents" / "masterPages" / "masterPage0.xml").is_file()
    assert (extract_dir / "Contents" / "history" / "history0.xml").is_file()
    assert (extract_dir / "BinData" / "BIN0001.png").is_file()
    assert (extract_dir / archive_cli._PACK_METADATA_NAME).is_file()
    assert any(path.name == archive_cli._PACK_METADATA_NAME for path in written)

    pack_hwpx(extract_dir, repacked)

    assert validate_package(repacked).ok
    reopened = HwpxPackage.open(repacked)
    assert "Contents/masterPages/masterPage0.xml" in reopened.master_page_paths()
    assert "Contents/history/history0.xml" in reopened.history_paths()


def test_analyze_template_reports_assets_and_json(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    extract_dir = tmp_path / "extract"
    header_copy = tmp_path / "header.xml"
    section_copy = tmp_path / "section0.xml"
    json_path = tmp_path / "summary.json"
    package_bytes, _ = _build_asset_rich_package()
    source.write_bytes(package_bytes)

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
    assert header_copy.is_file()
    assert section_copy.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "BinData/BIN0001.png" in payload["bin_data_paths"]
    assert "Contents/masterPages/masterPage0.xml" in payload["master_page_paths"]
    assert "Contents/history/history0.xml" in payload["history_paths"]


def test_analyze_template_api_reports_proxy_metrics(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    source.write_bytes(_document_with_structure().to_bytes())

    analysis = analyze_template(source)
    written = extract_template_parts(source, extract_dir=tmp_path / "extract-api")

    assert analysis.proxy_metrics.shape_count >= 1
    assert analysis.proxy_metrics.control_count >= 1
    assert analysis.manifest_path == "Contents/content.hpf"
    assert any(path.name == "header.xml" for path in written)


def test_text_extract_cli_smoke_on_nondefault_rootfile_package(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output_file = tmp_path / "sample.md"
    package_bytes, _ = _build_manual_package(
        manifest_path="Alt/content.hpf",
        header_href="parts/header-main.xml",
        section_href="parts/section0.xml",
        version_href="../version.xml",
        text="Custom Extract Text",
    )
    source.write_bytes(package_bytes)

    _run_module(
        "hwpx.tools.text_extract_cli",
        str(source),
        "--format",
        "markdown",
        "--output",
        str(output_file),
    )

    content = output_file.read_text(encoding="utf-8")
    assert "Custom Extract Text" in content


def test_validate_preserves_dirty_state() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("dirty paragraph")

    section = document.sections[-1]
    assert section.dirty

    document.validate()

    assert section.dirty
