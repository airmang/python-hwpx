# SPDX-License-Identifier: Apache-2.0
"""Pictures take image bytes of a known format only (7.0 fix).

``add_picture``, ``doc.media.add_image`` and ``replace_picture`` stored any bytes under any format
name; Hancom showed an empty frame and the save did not notice.
"""
from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 40
GIF = b"GIF89a" + b"0" * 40
BMP = b"BM" + b"0" * 40
SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'


def _parts(doc: HwpxDocument) -> set[str]:
    return set(doc.package.part_names())


@pytest.mark.parametrize(
    ("data", "fmt"),
    [(PNG, "png"), (PNG, ".PNG"), (JPEG, "jpg"), (JPEG, "jpeg"), (GIF, "gif"), (BMP, "bmp"), (SVG, "svg"),
     (b"II*\x00" + b"0" * 8, "tif")],
)
def test_images_of_a_known_format_are_taken(data: bytes, fmt: str) -> None:
    doc = HwpxDocument.new()
    item = doc.media.add_image(data, fmt)
    assert item.size == len(data)


@pytest.mark.parametrize(
    ("data", "fmt", "detected"),
    [
        (b"not an image at all", "png", None),
        (b"", "jpg", None),
        (PNG, "jpg", "png"),
        (PNG, "webp", None),
        (PNG, "exe", None),
    ],
)
def test_other_bytes_or_format_names_are_refused_before_anything_is_stored(data, fmt, detected) -> None:
    doc = HwpxDocument.new()
    before = _parts(doc)
    for call in (
        lambda: doc.media.add_image(data, fmt),
        lambda: doc.add_picture(data, fmt),
    ):
        with pytest.raises(ValueError) as excinfo:
            call()
        assert isinstance(excinfo.value, HwpxValueError)
        assert excinfo.value.code == "media-image-invalid"
        assert excinfo.value.suggestion
        if fmt in ("png", "jpg"):
            assert excinfo.value.context["detected"] == detected
    assert _parts(doc) == before
    assert doc.media.images == ()


def test_replace_picture_refuses_garbage_and_keeps_the_picture() -> None:
    doc = HwpxDocument.new()
    doc.add_picture(PNG, "png")
    (ref,) = doc.media.picture_references()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.media.replace_picture(b"garbage", "png")
    assert excinfo.value.code == "media-image-invalid"
    assert doc.media.picture_references() == (ref,)
    assert doc.media.replace_picture(JPEG, "jpg").item_id != ref.binary_item_id_ref
