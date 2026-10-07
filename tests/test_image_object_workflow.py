from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.id_integrity import check_id_integrity
from hwpx.tools.package_validator import validate_package
from hwpx.tools.repair import repair_repack

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
# image1 and image2 fill the page borders; only the header uses them
BORDER_FILL_IMAGES = CORPUS / "error__20251107__test.hwpx"
# a video that embeds its poster (image2, imageIDRef) and links its file by an
# absolute path (image1, fileIDRef, isEmbeded="0")
VIDEO = CORPUS / "reader_writer__SimpleVideo.hwpx"

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
    assert any(item.href == f"BinData/{binary_ref}.png" for item in document.list_images())
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
    assert result.previous_item_id == old_ref
    assert result.item_id == new_ref
    assert result.removed_orphans == (old_ref,)
    assert new_ref != old_ref
    assert _geometry_snapshot(new_picture) == before_geometry
    assert not document.package.has_part(f"BinData/{old_ref}.png")
    assert document.package.has_part(f"BinData/{new_ref}.png")
    assert check_id_integrity(document).ok

    source = tmp_path / "replace-picture.hwpx"
    repaired = tmp_path / "replace-picture.repaired.hwpx"
    document.save_to_path(source)
    _assert_repair_repack_validates(source, repaired)


def test_replace_picture_keeps_an_old_image_the_header_still_uses() -> None:
    document = HwpxDocument.open(BORDER_FILL_IMAGES)
    document.add_paragraph("").add_picture("image1", width=1000, height=1000)

    result = document.media.replace_picture(PNG_1X1, "png", binary_item_id_ref="image1")

    assert result.previous_item_id == "image1"
    assert result.removed_orphans == ()
    assert document.package.has_part("BinData/image1.jpg")
    assert check_id_integrity(document).dangling == []


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

def test_id_integrity_counts_a_video_poster_and_file_as_references() -> None:
    report = check_id_integrity(HwpxDocument.open(VIDEO))

    assert report.orphan_bin_data == []
    assert report.ok


def test_id_integrity_reports_a_video_poster_once_the_video_is_gone() -> None:
    document = HwpxDocument.open(VIDEO)
    section = document.oxml.sections[0]
    for video in list(section.element.iter(f"{HP}video")):
        video.getparent().remove(video)
    section.mark_dirty()

    report = check_id_integrity(document)

    # the linked video file lies outside the package, so it is no BinData asset
    assert [item.item_id for item in report.orphan_bin_data] == ["image2"]


def _assert_in_use_means_not_orphan(source: bytes) -> None:
    orphans: set[str] = set()
    for orphan in check_id_integrity(HwpxDocument.open(source)).orphan_bin_data:
        orphans.update(orphan.aliases)
    items = HwpxDocument.open(source).media.images
    assert items
    for item in items:
        try:
            HwpxDocument.open(source).media.remove_image(item)
            in_use = False
        except HwpxValueError:
            in_use = True
        assert in_use is (item.item_id not in orphans), item.item_id


@pytest.mark.parametrize(
    "name",
    [
        "reader_writer__SimplePicture.hwpx",  # a body picture
        "error__20251107__test.hwpx",  # page border fill images in the header
        "reader_writer__SimpleVideo.hwpx",  # a video poster
        "reader_writer__SimpleOLE.hwpx",  # an OLE object marked isEmbeded="0"
    ],
)
def test_remove_image_and_id_integrity_agree_on_what_is_in_use(name: str) -> None:
    _assert_in_use_means_not_orphan((CORPUS / name).read_bytes())


def test_remove_image_and_id_integrity_agree_on_an_unused_image() -> None:
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png")
    document.media.add_image(PNG_1X1_ALT, "png")  # embedded, but nothing shows it

    _assert_in_use_means_not_orphan(document.to_bytes())


def _picture_paragraph_alignment(document: HwpxDocument) -> str | None:
    paragraph = next(p for p in document.paragraphs if p.element.find(f".//{HP}pic") is not None)
    shape = document._root.paragraph_property(paragraph.para_pr_id_ref)
    return shape.align.horizontal if shape is not None and shape.align is not None else None


def test_an_aligned_inline_picture_takes_the_paragraph_alignment() -> None:
    # An inline picture follows its paragraph's alignment; horzAlign alone
    # leaves it at the left edge.
    for align in ("CENTER", "RIGHT", "left"):
        document = HwpxDocument.new()
        document.add_picture(PNG_1X1, "png", width=7200, height=7200, align=align)
        assert _picture_paragraph_alignment(document) == align.upper()


@pytest.mark.parametrize("align", ["BOGUS", "TOP", "  right ", 1])
def test_a_picture_alignment_outside_the_schema_is_refused_before_anything_is_added(align: object) -> None:
    # Hancom reads a horizontal alignment it does not know as LEFT; the picture was written with it as given.
    document = HwpxDocument.new()
    paragraphs, images = len(document.paragraphs), len(document.list_images())

    with pytest.raises(HwpxValueError) as caught:
        document.add_picture(PNG_1X1, "png", width=7200, height=7200, align=align)  # type: ignore[arg-type]

    assert caught.value.code == "shape-position-frame"
    assert (len(document.paragraphs), len(document.list_images())) == (paragraphs, images)


def test_a_picture_takes_the_inside_and_outside_alignments_too() -> None:
    for align in ("INSIDE", "outside"):
        document = HwpxDocument.new()
        document.add_picture(PNG_1X1, "png", width=7200, height=7200, align=align)
        assert _first_picture(document).find(f"{HP}pos").get("horzAlign") == align.upper()


def test_a_picture_without_align_keeps_the_paragraph_alignment() -> None:
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png", width=7200, height=7200)
    assert _picture_paragraph_alignment(document) == "JUSTIFY"
