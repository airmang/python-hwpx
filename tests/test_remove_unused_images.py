"""``doc.media.remove_unused_images()`` drops the binary items nothing points at, as Hancom does on save.

``unused_image_saved.hwpx``: Hancom saved a document holding a picture and a second image that no
picture uses. It kept the picture's image, byte for byte, and dropped the other one.
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib
from pathlib import Path

from hwpx import HwpxDocument

HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "unused_image_saved.hwpx"


def _png(red: int, green: int, blue: int) -> bytes:
    rows = b"".join(b"\x00" + bytes([red, green, blue]) * 8 for _ in range(8))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


USED, UNUSED = _png(200, 30, 30), _png(30, 30, 200)


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("그림 앞")
    document.add_picture(USED, "png", width=3000, height=3000)
    document.media.add_image(UNUSED, "png")
    return document


def _bin_data(data: bytes) -> list[bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [archive.read(name) for name in archive.namelist() if name.startswith("BinData/")]


def test_an_image_nothing_uses_is_removed_and_a_used_one_kept() -> None:
    document = _document()

    removed = document.media.remove_unused_images()

    assert [str(item) for item in removed] == ["BIN0002"]
    assert [str(item) for item in document.media.images] == ["BIN0001"]
    assert _bin_data(document.to_bytes()) == [USED]


def test_it_leaves_the_images_hancom_keeps() -> None:
    document = _document()
    document.media.remove_unused_images()

    assert _bin_data(document.to_bytes()) == _bin_data(HANCOM_SAVED.read_bytes()) == [USED]


def test_the_images_of_a_cleared_body_are_removed() -> None:
    document = _document()
    document.sections[0].clear_body()

    removed = document.media.remove_unused_images()

    assert len(removed) == 2
    assert document.media.images == ()
    assert document.media.remove_unused_images() == ()


def test_the_image_of_a_removed_paragraph_stays_in_the_file_until_it_is_removed() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("그림 앞")
    picture = document.add_picture(USED, "png", width=3000, height=3000)
    document.add_paragraph("그림 뒤")

    picture.paragraph.remove()

    assert _bin_data(document.to_bytes()) == [USED]
    assert [str(item) for item in document.media.remove_unused_images()] == ["BIN0001"]
    assert _bin_data(document.to_bytes()) == []
