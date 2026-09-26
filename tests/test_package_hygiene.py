# SPDX-License-Identifier: Apache-2.0
"""Package hygiene primitives — what a caller clears before sharing a template.

- ``doc.parts.clear_document_metadata`` empties every ``opf:metadata`` field
  outside *keep*, including ``opf:meta`` names the library does not know.
- ``doc.parts.clear_preview`` empties the preview text and replaces the
  preview image with a 1x1 white PNG; neither part is deleted.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.opc.package import HwpxPackage

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
TITLED = CORPUS / "error__20251107__test.hwpx"
PICTURE = CORPUS / "reader_writer__SimplePicture.hwpx"
TEXT_PREVIEW_ONLY = CORPUS / "error__20241104__mot.hwpx"


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
