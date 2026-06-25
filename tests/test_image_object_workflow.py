from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.id_integrity import check_id_integrity
from hwpx.tools.package_validator import validate_package
from hwpx.tools.repair import repair_repack

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)

PNG_1X1_ALT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgwJ/l8EydgAAAABJRU5ErkJggg=="
)


def _first_picture(document: HwpxDocument):
    picture = document.oxml.sections[0].element.find(f".//{HP}pic")
    assert picture is not None
    return picture


def _first_picture_image(document: HwpxDocument):
    image = _first_picture(document).find(f"{HC}img")
    assert image is not None
    return image


def _geometry_snapshot(picture) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for name in ("sz", "pos", "imgRect", "imgClip", "curSz", "orgSz", "flip", "rotationInfo"):
        element = picture.find(f"{HP}{name}")
        if element is not None:
            snapshot[name] = ET.tostring(element, encoding="unicode")
    return snapshot


def _assert_repair_repack_validates(source: Path, output: Path) -> None:
    repair_repack(source, output)
    assert validate_package(output).ok


def test_add_picture_updates_section_manifest_and_bindata_then_validates(tmp_path: Path) -> None:
    document = HwpxDocument.new()

    document.add_picture(PNG_1X1, "png", width=12345, height=6789)

    binary_ref = _first_picture_image(document).get("binaryItemIDRef")
    assert binary_ref == "BIN0001"
    assert document.package.has_part(f"BinData/{binary_ref}.png")
    assert any(item.get("BinData") == f"{binary_ref}.png" for item in document.list_images())
    assert any(
        item.get("id") == binary_ref
        and item.get("href") == f"BinData/{binary_ref}.png"
        and item.get("media-type") == "image/png"
        for item in document.package._manifest_items()
    )
    assert check_id_integrity(document).ok

    source = tmp_path / "insert-picture.hwpx"
    repaired = tmp_path / "insert-picture.repaired.hwpx"
    document.save_to_path(source)
    _assert_repair_repack_validates(source, repaired)


def test_add_picture_manifest_item_marks_embedded(tmp_path: Path) -> None:
    """The image's ``<opf:item>`` must carry ``isEmbeded="1"`` — without it real
    Hancom does NOT render the embedded picture (oracle-confirmed 2026-06-25; real
    Hancom files mark every embedded BinData image this way)."""
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png", width=7200, height=7200)

    items = [i for i in document.package._manifest_items() if i.get("id") == "BIN0001"]
    assert len(items) == 1
    assert items[0].get("isEmbeded") == "1"


def test_replace_picture_preserves_geometry_and_replaces_only_asset_graph(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png", width=11111, height=22222)

    old_picture = _first_picture(document)
    old_ref = _first_picture_image(document).get("binaryItemIDRef")
    before_geometry = _geometry_snapshot(old_picture)

    result = document.replace_picture(PNG_1X1_ALT, "png", picture_index=0)

    new_picture = _first_picture(document)
    new_ref = _first_picture_image(document).get("binaryItemIDRef")
    assert result["old_binaryItemIDRef"] == old_ref
    assert result["new_binaryItemIDRef"] == new_ref
    assert result["removedOldImage"] is True
    assert new_ref != old_ref
    assert _geometry_snapshot(new_picture) == before_geometry
    assert not document.package.has_part(f"BinData/{old_ref}.png")
    assert document.package.has_part(f"BinData/{new_ref}.png")
    assert check_id_integrity(document).ok

    source = tmp_path / "replace-picture.hwpx"
    repaired = tmp_path / "replace-picture.repaired.hwpx"
    document.save_to_path(source)
    _assert_repair_repack_validates(source, repaired)


def test_id_integrity_detects_dangling_binary_item_ref() -> None:
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png")
    _first_picture_image(document).set("binaryItemIDRef", "MISSING_BIN")

    report = check_id_integrity(document)

    assert report.ok is False
    assert any(
        item.attr == "binaryItemIDRef"
        and item.value == "MISSING_BIN"
        and item.table == "bin_data"
        for item in report.dangling
    )


def test_id_integrity_detects_orphan_bindata() -> None:
    document = HwpxDocument.new()
    document.add_image(PNG_1X1, "png")

    report = check_id_integrity(document)

    assert report.ok is False
    assert report.dangling == []
    assert any(item.item_id == "BIN0001" for item in report.orphan_bin_data)
