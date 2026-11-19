"""The byte patches keep what the archive they read held, as the document save does.

Small archives made here from a new document: two entries under one name; a ZIP64 end record or bytes
before the first record (the records cannot be moved one by one, so every entry is written again), with
``mimetype`` last and deflated, the central directory in another order than the records lie, and an
archive comment; a paragraph holding a table whose cell paragraph has its own layout cache; a stream that
cannot be read back.
"""
from __future__ import annotations

import io
import warnings
import zipfile
from unittest.mock import patch

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.body_patch import strip_runs_by_color
from hwpx.opc.package import HwpxPackageError
from hwpx.patch import paragraph_chunks, paragraph_patch, replace_package_text, rewrite_package_parts
from hwpx.table_patch import fill_cells

SECTION = "Contents/section0.xml"


# -- two entries under one name ---------------------------------------------------------------


def _with_duplicate() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    out = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate name
        with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
            for info in source.infolist():
                target.writestr(info, source.read(info))
            target.writestr("Extra.xml", b"<x>first</x>")
            target.writestr("Extra.xml", b"<x>second</x>")
    return out.getvalue()


_DUPLICATE_CALLS = {
    "replace_package_text": lambda source, out: replace_package_text(source, {"second": "next"}, output_path=out),
    "replace_package_text_no_hit": lambda source, out: replace_package_text(source, {"없는 글": "x"}, output_path=out),
    "paragraph_patch": lambda source, out: paragraph_patch(
        source, [{"paragraphIndex": 0, "text": "새 글"}], output_path=out
    ),
    "paragraph_patch_nothing": lambda source, out: paragraph_patch(source, [], output_path=out),
    "rewrite_package_parts": lambda source, out: rewrite_package_parts(  # takes bytes only
        source if isinstance(source, bytes) else source.read_bytes(), {"Extra.xml": b"<x>third</x>"}
    ),
    "strip_runs_by_color": lambda source, out: strip_runs_by_color(source, "#FF0000", output_path=out),
    "fill_cells": lambda source, out: fill_cells(source, [], output_path=out),
}


@pytest.mark.parametrize("call", list(_DUPLICATE_CALLS), ids=list(_DUPLICATE_CALLS))
def test_every_byte_patch_refuses_two_entries_under_one_name_before_writing(call, tmp_path) -> None:
    out = tmp_path / "out.hwpx"
    out.write_bytes(b"EXISTING")
    for source in (_with_duplicate(), None):
        if source is None:  # the same file given by path
            path = tmp_path / "source.hwpx"
            path.write_bytes(_with_duplicate())
            source = path
        with pytest.raises(HwpxPackageError) as caught:
            _DUPLICATE_CALLS[call](source, out)
        assert caught.value.code == "save-duplicate-entry-names"
        assert caught.value.context["names"] == ["Extra.xml"]
        assert out.read_bytes() == b"EXISTING"


# -- archives whose records cannot be kept one by one ------------------------------------------


def _unmovable(kind: str, *, comment: bytes = b"marker") -> bytes:
    """mimetype last and deflated, the central directory in reverse of where the records lie."""

    document = HwpxDocument.new()
    document.add_paragraph(" old ")
    out = io.BytesIO()
    limit = 100 if kind == "zip64" else zipfile.ZIP64_LIMIT
    with patch.object(zipfile, "ZIP64_LIMIT", limit), \
            zipfile.ZipFile(io.BytesIO(document.to_bytes())) as source, \
            zipfile.ZipFile(out, "w") as target:
        infos = source.infolist()
        for info in infos[1:] + infos[:1]:
            target.writestr(info, source.read(info), compress_type=zipfile.ZIP_DEFLATED)
        target.filelist[:] = list(reversed(target.filelist))
        target.comment = comment
    data = out.getvalue()
    return b"prefix" + data if kind == "prefix" else data


def _layout(data: bytes) -> tuple[list[str], list[str], int, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        physical = [info.filename for info in sorted(infos, key=lambda info: info.header_offset)]
        return [info.filename for info in infos], physical, archive.getinfo("mimetype").compress_type, archive.comment


def _document_unedited(source: bytes) -> bytes:
    out = io.BytesIO()
    HwpxDocument.open(source).save(out)
    return out.getvalue()


def _document_edited(source: bytes) -> bytes:
    document = HwpxDocument.open(source)
    document.paragraphs[0].text = " new "
    document.package.set_part("Extra.dat", b"additional")
    return document.to_bytes()


_UNMOVABLE_WRITERS = {
    "document_unedited": _document_unedited,
    "document_edited": _document_edited,
    "replace_package_text": lambda source: replace_package_text(source, {" old ": " new "}).data,
    "paragraph_patch": lambda source: paragraph_patch(source, [{"paragraphIndex": 0, "text": " new "}]).data,
    "rewrite_package_parts": lambda source: rewrite_package_parts(source, {"version.xml": _part(source, "version.xml")}),
}


def _part(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(name)


@pytest.mark.parametrize("writer", list(_UNMOVABLE_WRITERS), ids=list(_UNMOVABLE_WRITERS))
@pytest.mark.parametrize("kind", ["zip64", "prefix", "plain"])
def test_a_rewritten_archive_keeps_both_orders_mimetype_and_the_comment(kind: str, writer: str) -> None:
    source = _unmovable(kind)
    written = _UNMOVABLE_WRITERS[writer](source)
    central, physical, mimetype_compression, comment = _layout(source)
    new_central, new_physical, new_mimetype_compression, new_comment = _layout(written)
    assert new_central[: len(central)] == central
    assert new_physical[: len(physical)] == physical
    assert physical[-1] == "mimetype" and new_physical.index("mimetype") == len(physical) - 1
    assert (mimetype_compression, new_mimetype_compression) == (zipfile.ZIP_DEFLATED, zipfile.ZIP_DEFLATED)
    assert new_comment == comment == b"marker"
    with zipfile.ZipFile(io.BytesIO(written)) as archive:
        assert archive.testzip() is None


def test_the_save_report_still_says_the_records_were_written_again() -> None:
    report = HwpxDocument.open(_unmovable("zip64")).save(io.BytesIO())
    assert report.preservation.zip_records_rewritten == "zip64"
    assert report.preservation.untouched_part_payloads.changed == 0


# -- layout caches: only the paragraph whose text changed loses its own ----------------------


def _cached_table_document() -> bytes:
    """A paragraph holding a 1x1 table; the outer and the cell paragraph each with one layout cache."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("ABC")
    paragraph.add_table(1, 1).cell(0, 0).text = "J"
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info)
            if info.filename == SECTION:
                root = etree.fromstring(payload)
                for p in root.xpath('//*[local-name()="p"]'):
                    if not p.xpath('./*[local-name()="linesegarray"]'):
                        namespace = etree.QName(p).namespace
                        cache = etree.SubElement(p, f"{{{namespace}}}linesegarray")
                        etree.SubElement(cache, f"{{{namespace}}}lineseg", textpos="0")
                payload = etree.tostring(root)
            target.writestr(info, payload)
    return out.getvalue()


def _paragraphs(data: bytes) -> list[tuple[str, int]]:
    """(own text, own cache count) of the paragraph holding the table, then of the cell paragraph."""

    root = etree.fromstring(_part(data, SECTION))
    found = []
    for p in root.xpath('//*[local-name()="p"][.//*[local-name()="tbl"]] | //*[local-name()="tc"]//*[local-name()="p"]'):
        text = "".join(p.xpath('./*[local-name()="run"]/*[local-name()="t"]/text()'))
        caches = len(p.xpath('./*[local-name()="linesegarray"]'))
        found.append((text, caches))
    return found


def _cell_bytes(data: bytes) -> bytes:
    section = _part(data, SECTION)
    start = section.index(b"<hp:tbl")
    return section[start:section.index(b"</hp:tbl>") + len(b"</hp:tbl>")]


def test_replacing_outer_text_keeps_the_untouched_cell_paragraph_cache() -> None:
    source = _cached_table_document()
    assert _paragraphs(source) == [("ABC", 1), ("J", 1)]
    result = replace_package_text(source, {"ABC": "123"})
    assert _paragraphs(result.data) == [("123", 0), ("J", 1)]
    assert result.layout_caches_removed == 1
    assert _cell_bytes(result.data) == _cell_bytes(source)


def test_replacing_cell_text_drops_only_the_cell_paragraph_cache() -> None:
    result = replace_package_text(_cached_table_document(), {"J": "K"})
    assert _paragraphs(result.data) == [("ABC", 1), ("K", 0)]
    assert result.layout_caches_removed == 1


def test_paragraph_patch_changes_only_the_outer_paragraph_and_its_own_cache() -> None:
    source = _cached_table_document()
    index = next(i for i, chunk in enumerate(paragraph_chunks(_part(source, SECTION))) if b"ABC" in chunk)
    result = paragraph_patch(source, [{"paragraphIndex": index, "text": "123"}])
    assert [item.original_text for item in result.applied] == ["ABC"]
    assert _paragraphs(result.data) == [("123", 0), ("J", 1)]
    assert _cell_bytes(result.data) == _cell_bytes(source)


# -- a stream that cannot be read back ---------------------------------------------------------


class _WriteOnly(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        raise io.UnsupportedOperation("write-only")


def test_a_stream_that_cannot_be_read_back_is_not_reported_as_the_source_file() -> None:
    source = HwpxDocument.new().to_bytes()
    report = HwpxDocument.open(source).save(_WriteOnly())
    assert report.preservation.output_read_back is False
    assert report.preservation.whole_package_identical is False
    assert report.preservation.to_dict()["outputReadBack"] is False

    readable = HwpxDocument.open(source).save(io.BytesIO())
    assert readable.preservation.output_read_back is True
    assert readable.preservation.whole_package_identical is True
    assert "outputReadBack" not in readable.preservation.to_dict()
