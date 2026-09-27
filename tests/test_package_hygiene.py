# SPDX-License-Identifier: Apache-2.0
"""Package hygiene primitives — what a caller clears before sharing a template.

- ``doc.parts.clear_document_metadata`` empties every ``opf:metadata`` field
  outside *keep*, including ``opf:meta`` names the library does not know.
- ``doc.parts.clear_preview`` empties the preview text and replaces the
  preview image with a 1x1 white PNG; neither part is deleted.
- ``doc.media.images``/``remove_image`` see binary items that only the
  ``content.hpf`` manifest lists (the usual case for Hancom-saved files).
- ``remove_image`` refuses an item the document still points at (a picture,
  a header image fill, a master page, a video, an OLE object) unless
  ``force=True``, and never removes a manifest item that is not a binary item.
- ``doc.validate()`` warns about manifest items with no part and ``BinData/``
  parts with no manifest item.
"""

from __future__ import annotations

import copy
import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import BinaryItem
from hwpx.opc.package import HwpxPackage
from hwpx.tools.id_integrity import check_id_integrity

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
TITLED = CORPUS / "error__20251107__test.hwpx"
PICTURE = CORPUS / "reader_writer__SimplePicture.hwpx"
TEXT_PREVIEW_ONLY = CORPUS / "error__20241104__mot.hwpx"
# links a video by absolute path (isEmbeded="0"), so the part is absent by design
LINKED_VIDEO = CORPUS / "reader_writer__SimpleVideo.hwpx"
OLE = CORPUS / "reader_writer__SimpleOLE.hwpx"

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def _rewrite(source: Path, part: str, edit) -> bytes:
    """Return *source*'s bytes with *part* passed through ``edit(str) -> str``."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(buffer, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == part:
                data = edit(data.decode("utf-8")).encode("utf-8")
            dst.writestr(info, data)
    return buffer.getvalue()


def _with_unknown_meta(source: Path) -> bytes:
    return _rewrite(
        source,
        "Contents/content.hpf",
        lambda text: text.replace(
            "</opf:metadata>",
            '<opf:meta name="companyName" content="text">ACME</opf:meta></opf:metadata>',
        ),
    )


def _metadata_xml(archive: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        text = zf.read("Contents/content.hpf").decode("utf-8")
    match = re.search(r"<opf:metadata>.*?</opf:metadata>", text, re.S)
    assert match is not None
    return match.group(0)


def _read_part(archive: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return zf.read(name)


def _names(archive: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return zf.namelist()


# ---------------------------------------------------------------------------
# clear_document_metadata
# ---------------------------------------------------------------------------


def test_clear_document_metadata_clears_unknown_names_and_keeps_title() -> None:
    document = HwpxDocument.open(_with_unknown_meta(TITLED))

    cleared = document.parts.clear_document_metadata()

    assert cleared == [
        "creator",
        "subject",
        "description",
        "lastsaveby",
        "CreatedDate",
        "ModifiedDate",
        "date",
        "keyword",
        "companyName",
    ]
    assert _metadata_xml(document.to_bytes()) == (
        "<opf:metadata>"
        '<opf:title xml:space="preserve">■ 3월 </opf:title>'
        "<opf:language>ko</opf:language>"
        '<opf:meta name="creator" content="text"/>'
        '<opf:meta name="subject" content="text"/>'
        '<opf:meta name="description" content="text"/>'
        '<opf:meta name="lastsaveby" content="text"/>'
        '<opf:meta name="CreatedDate" content="text">1970-01-01T00:00:00Z</opf:meta>'
        '<opf:meta name="ModifiedDate" content="text">1970-01-01T00:00:00Z</opf:meta>'
        '<opf:meta name="date" content="text"/>'
        '<opf:meta name="keyword" content="text"/>'
        '<opf:meta name="companyName" content="text"/>'
        "</opf:metadata>"
    )


def test_clear_document_metadata_with_empty_keep_clears_title_and_language() -> None:
    document = HwpxDocument.open(TITLED)

    cleared = document.parts.clear_document_metadata(keep=(), timestamp="2000-01-01T00:00:00Z")

    assert cleared[:2] == ["title", "language"]
    metadata = document.parts.metadata
    assert metadata is not None
    assert metadata.title is None
    assert metadata.language is None
    assert metadata.creator is None
    assert metadata.lastsaveby is None
    assert metadata.created_date == "2000-01-01T00:00:00Z"
    assert metadata.modified_date == "2000-01-01T00:00:00Z"
    # the free-form ``date`` field is emptied, never given the ISO timestamp
    assert metadata.date is None

    reopened = HwpxDocument.open(document.to_bytes())
    again = reopened.parts.metadata
    assert again is not None
    assert again.title is None
    assert again.date is None
    assert again.created_date == "2000-01-01T00:00:00Z"


def test_clear_document_metadata_without_a_metadata_block_returns_nothing() -> None:
    archive = _rewrite(
        TITLED,
        "Contents/content.hpf",
        lambda text: re.sub(r"<opf:metadata>.*?</opf:metadata>", "", text, flags=re.S),
    )
    document = HwpxDocument.open(archive)

    assert document.parts.clear_document_metadata() == []
    assert document.parts.metadata is None
    assert "<opf:metadata" not in _read_part(document.to_bytes(), "Contents/content.hpf").decode()


def test_package_clear_document_metadata_is_the_same_primitive() -> None:
    package = HwpxPackage.open(_with_unknown_meta(PICTURE))

    cleared = package.clear_document_metadata(keep=("title", "language", "creator"))

    assert "creator" not in cleared
    assert "companyName" in cleared
    metadata = package.document_metadata()
    assert metadata is not None
    assert metadata.creator == "fff"
    assert metadata.lastsaveby is None
    assert metadata.created_date == "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# clear_preview
# ---------------------------------------------------------------------------


def _chunk(tag: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body))
        + tag
        + body
        + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    )


WHITE_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + _chunk(b"IDAT", zlib.compress(b"\x00" + b"\xff\xff\xff"))
    + _chunk(b"IEND", b"")
)


def test_clear_preview_empties_text_and_neutralizes_image() -> None:
    document = HwpxDocument.open(PICTURE)
    assert _read_part(PICTURE.read_bytes(), "Preview/PrvText.txt") != b""

    changed = document.parts.clear_preview()

    assert changed == ["Preview/PrvText.txt", "Preview/PrvImage.png"]
    archive = document.to_bytes()
    assert _read_part(archive, "Preview/PrvText.txt") == b""
    assert _read_part(archive, "Preview/PrvImage.png") == WHITE_1X1_PNG
    reopened = HwpxDocument.open(archive)
    assert reopened.validate().ok


def test_clear_preview_only_touches_the_parts_that_exist() -> None:
    document = HwpxDocument.open(TEXT_PREVIEW_ONLY)

    assert document.parts.clear_preview() == ["Preview/PrvText.txt"]
    assert "Preview/PrvImage.png" not in _names(document.to_bytes())


# ---------------------------------------------------------------------------
# manifest-only binary items
# ---------------------------------------------------------------------------


def test_images_lists_manifest_only_items() -> None:
    document = HwpxDocument.open(PICTURE)
    size = len(_read_part(PICTURE.read_bytes(), "BinData/image1.jpg"))

    assert document.media.images == (
        BinaryItem(item_id="image1", format="jpg", href="BinData/image1.jpg", size=size),
    )


def test_images_lists_header_items_first_without_duplicates() -> None:
    document = HwpxDocument.new()
    listed = document.media.add_image(PNG, "png")
    document.package.write("BinData/extra.png", PNG)
    document.package.add_manifest_item("extra", "BinData/extra.png", "image/png")

    images = document.media.images

    assert [item.item_id for item in images] == [listed.item_id, "extra"]
    assert images[1] == BinaryItem(item_id="extra", format="png", href="BinData/extra.png", size=len(PNG))


def test_images_leaves_out_linked_items_but_keeps_embedded_ones_without_a_part() -> None:
    document = HwpxDocument.open(LINKED_VIDEO)
    size = len(_read_part(LINKED_VIDEO.read_bytes(), "BinData/image2.bmp"))

    assert document.media.images == (
        BinaryItem(item_id="image2", format="bmp", href="BinData/image2.bmp", size=size),
    )

    document.package.delete("BinData/image2.bmp")
    assert document.media.images == (
        BinaryItem(item_id="image2", format="bmp", href="BinData/image2.bmp", size=0),
    )


def _drop_pictures(document: HwpxDocument) -> None:
    """Delete the body pictures, so the images they showed are no longer used."""

    for section in document.oxml.sections:
        for picture in list(section.element.iter(f"{HP}pic")):
            picture.getparent().remove(picture)
        section.mark_dirty()


def test_removing_every_listed_image_keeps_linked_items() -> None:
    document = HwpxDocument.open(LINKED_VIDEO)

    for item in document.media.images:
        # the video still names image2 as its poster
        assert document.media.remove_image(item, force=True) is True

    hpf = _read_part(document.to_bytes(), "Contents/content.hpf").decode()
    assert 'id="image1"' in hpf
    assert 'id="image2"' not in hpf


@pytest.mark.parametrize("how", ["id", "href", "item"])
def test_remove_image_removes_manifest_only_items(how: str) -> None:
    document = HwpxDocument.open(PICTURE)
    _drop_pictures(document)
    (item,) = document.media.images
    target = {"id": "image1", "href": "BinData/image1.jpg", "item": item}[how]

    assert document.media.remove_image(target) is True

    assert document.media.images == ()
    assert not document.package.has_part("BinData/image1.jpg")
    hpf = _read_part(document.to_bytes(), "Contents/content.hpf").decode()
    assert 'id="image1"' not in hpf
    assert document.media.remove_image(target) is False


def test_remove_image_does_not_match_a_longer_id_with_the_same_prefix() -> None:
    document = HwpxDocument.new()
    document.media.add_image(PNG, "png", item_id="image10")
    document.media.add_image(PNG + b"1", "png", item_id="image1")

    assert document.media.remove_image("image1") is True

    assert [item.item_id for item in document.media.images] == ["image10"]
    assert document.package.has_part("BinData/image10.png")
    assert not document.package.has_part("BinData/image1.png")
    header = document.oxml.headers[0]
    assert [item.get("BinData") for item in header.list_bin_items()] == ["image10.png"]


@pytest.mark.parametrize(
    ("source", "target", "reference"),
    [
        (PICTURE, "image1", "Contents/section0.xml: img@binaryItemIDRef"),
        (PICTURE, "BinData/image1.jpg", "Contents/section0.xml: img@binaryItemIDRef"),
        # a page border fill image, used only by the header
        (TITLED, "image1", "Contents/header.xml: img@binaryItemIDRef"),
        (LINKED_VIDEO, "image2", "Contents/section0.xml: video@imageIDRef"),
        (LINKED_VIDEO, "image1", "Contents/section0.xml: video@fileIDRef"),
        (OLE, "ole1", "Contents/section0.xml: ole@binaryItemIDRef"),
    ],
)
def test_remove_image_refuses_an_item_the_document_still_uses(
    source: Path, target: str, reference: str
) -> None:
    document = HwpxDocument.open(source)
    images = document.media.images
    parts = document.package.part_names()
    hpf = document.package.get_text("Contents/content.hpf")

    with pytest.raises(HwpxValueError) as caught:
        document.media.remove_image(target)

    assert caught.value.code == "media-item-in-use"
    assert caught.value.context == {"itemId": target, "references": [reference]}
    assert document.media.images == images
    assert document.package.part_names() == parts
    assert document.package.get_text("Contents/content.hpf") == hpf


def test_remove_image_refuses_an_item_a_master_page_uses() -> None:
    document = HwpxDocument.new()
    item = document.media.add_image(PNG, "png")
    document.add_picture(PNG, "png")
    document.parts.add_master_page(text="master")
    master_page = document.oxml.master_pages[0]
    picture = next(document.oxml.sections[0].element.iter(f"{HP}pic"))
    next(master_page.element.iter(f"{HP}run")).append(copy.deepcopy(picture))
    _drop_pictures(document)
    # the master page's copy shows the image add_picture embedded
    shown = document.media.images[1]

    with pytest.raises(HwpxValueError) as caught:
        document.media.remove_image(shown)

    assert caught.value.context["references"] == [
        "Contents/masterpage0.xml: img@binaryItemIDRef"
    ]
    assert document.media.remove_image(item) is True


def test_remove_image_with_force_removes_an_item_in_use() -> None:
    document = HwpxDocument.open(PICTURE)

    assert document.media.remove_image("image1", force=True) is True

    assert document.media.images == ()
    assert not document.package.has_part("BinData/image1.jpg")
    assert [(ref.attr, ref.value) for ref in check_id_integrity(document).dangling] == [
        ("binaryItemIDRef", "image1")
    ]


@pytest.mark.parametrize("target", ["section0", "Contents/section0.xml", "header", "settings"])
def test_remove_image_leaves_manifest_items_that_are_not_binary(target: str) -> None:
    document = HwpxDocument.open(PICTURE)
    parts = document.package.part_names()
    hpf = document.package.get_text("Contents/content.hpf")

    assert document.media.remove_image(target) is False
    assert document.media.remove_image(target, force=True) is False

    assert document.package.part_names() == parts
    assert document.package.get_text("Contents/content.hpf") == hpf


def test_remove_manifest_item_matches_id_then_href() -> None:
    package = HwpxPackage.open(PICTURE)

    assert package.remove_manifest_item("BinData/missing.jpg") is False
    assert package.remove_manifest_item("image1.jpg") is False
    assert package.remove_manifest_item("./BinData/image1.jpg") is True
    assert 'id="image1"' not in package.get_text("Contents/content.hpf")

    package = HwpxPackage.open(PICTURE)
    assert package.remove_manifest_item("image1") is True
    assert package.remove_manifest_item("image1") is False


# ---------------------------------------------------------------------------
# validate() — manifest drift
# ---------------------------------------------------------------------------


def _drift(document: HwpxDocument) -> list[str]:
    return [
        issue.message
        for issue in document.validate().warnings
        if "manifest" in issue.message
    ]


def test_validate_warns_about_a_manifest_item_without_a_part() -> None:
    document = HwpxDocument.open(PICTURE)
    document.package.delete("BinData/image1.jpg")

    report = document.validate()

    assert report.ok
    drift = [issue for issue in report.warnings if "image1" in issue.message]
    assert len(drift) == 1
    assert drift[0].part_name == "Contents/content.hpf"
    assert "'BinData/image1.jpg'" in drift[0].message


def test_validate_warns_about_a_bindata_part_without_a_manifest_item() -> None:
    document = HwpxDocument.open(PICTURE)
    document.package.write("BinData/stray.png", PNG)

    report = document.validate()

    assert report.ok
    drift = [issue for issue in report.warnings if issue.part_name == "BinData/stray.png"]
    assert len(drift) == 1
    assert "'BinData/stray.png'" in drift[0].message


@pytest.mark.parametrize("source", [None, PICTURE, TITLED, LINKED_VIDEO])
def test_validate_reports_no_drift_on_clean_documents(source: Path | None) -> None:
    document = HwpxDocument.new() if source is None else HwpxDocument.open(source)
    if source is None:
        document.media.add_image(PNG, "png")

    assert _drift(document) == []


# Hancom marks OLE objects isEmbeded="0" too, but keeps their file in BinData/.
OLE = CORPUS / "reader_writer__SimpleOLE.hwpx"


def test_validate_warns_about_a_missing_ole_part_marked_not_embedded() -> None:
    document = HwpxDocument.open(OLE)
    assert _drift(document) == []
    document.package.delete("BinData/ole1.ole")

    drift = [issue for issue in document.validate().warnings if "ole1" in issue.message]

    assert len(drift) == 1
    assert "'BinData/ole1.ole'" in drift[0].message


def test_validate_still_skips_a_linked_file_outside_the_package() -> None:
    # SimpleVideo links a video by absolute path (isEmbeded="0", href outside BinData/)
    assert _drift(HwpxDocument.open(LINKED_VIDEO)) == []
