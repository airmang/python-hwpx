"""A save never loses or misstates what the archive it was opened from held.

Each case is a small archive made here from a new document: two entries under one name, an explicit
directory entry, a central directory listed in another order than the records lie, bytes before the first
record, a ZIP64 end record, an archive comment; a reused stream longer than the document saved into it.
"""
from __future__ import annotations

import io
import warnings
import zipfile
from unittest.mock import patch

import pytest

from hwpx import HwpxDocument
from hwpx.opc.package import HwpxPackageError


def _repacked(*, duplicate: bool = False, directory: bool = False, reverse: bool = False,
              comment: bytes = b"", zip64: bool = False, level: int | None = None) -> bytes:
    out = io.BytesIO()
    limit = 100 if zip64 else zipfile.ZIP64_LIMIT
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate name
        with patch.object(zipfile, "ZIP64_LIMIT", limit), \
                zipfile.ZipFile(io.BytesIO(HwpxDocument.new().to_bytes())) as source, \
                zipfile.ZipFile(out, "w") as target:
            for info in source.infolist():
                target.writestr(info, source.read(info), compresslevel=level)
            if duplicate:
                target.writestr("opaque.bin", b"1")
                target.writestr("opaque.bin", b"2")
            if directory:
                target.mkdir("BinData/")
            if reverse:
                target.filelist[1:] = list(reversed(target.filelist[1:]))
            target.comment = comment
    return out.getvalue()


def _records(data: bytes) -> list[tuple[str, bytes]]:
    """Every local record (header to the next header or the central directory), in physical order."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = sorted(archive.infolist(), key=lambda info: info.header_offset)
        ends = [info.header_offset for info in entries[1:]] + [archive.start_dir]
        return [(info.filename, data[info.header_offset:end]) for info, end in zip(entries, ends)]


# -- two entries under one name --------------------------------------------------------------


def test_two_entries_under_one_name_open_for_reading_but_a_save_is_refused() -> None:
    source = _repacked(duplicate=True)
    with pytest.warns(UserWarning, match=r"'opaque.bin' x2.*the last of each is read"):
        document = HwpxDocument.open(source)
    assert document.paragraphs is not None  # reading works

    target = io.BytesIO(b"kept")
    with pytest.raises(HwpxPackageError) as caught:
        document.save(target)
    assert caught.value.code == "save-duplicate-entry-names"
    assert caught.value.context["names"] == ["opaque.bin"]
    assert target.getvalue() == b"kept"
    with pytest.raises(HwpxPackageError):
        document.to_bytes()


def test_the_package_check_and_the_text_tool_say_which_names_repeat(tmp_path, capsys) -> None:
    from hwpx.tools.package_validator import validate_package
    from hwpx.tools.text_extract_cli import main as extract_main

    source = _repacked(duplicate=True)
    report = validate_package(source)
    assert report.ok  # an advisory, not an error
    assert any("'opaque.bin' x2" in issue.message for issue in report.warnings)

    path = tmp_path / "repeated.hwpx"
    path.write_bytes(source)
    assert extract_main([str(path)]) == 0
    assert "'opaque.bin' x2" in capsys.readouterr().err


# -- a reused stream ------------------------------------------------------------------------


def test_a_shorter_document_saved_into_a_longer_stream_leaves_nothing_after_it() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("가" * 20000)
    stream = io.BytesIO()
    document.save(stream)
    long_size = len(stream.getvalue())

    paragraph.text = "Z"
    stream.seek(0)
    document.save(stream)
    data = stream.getvalue()
    assert len(data) < long_size and stream.tell() == len(data)
    assert HwpxDocument.open(data).paragraphs[-1].text == "Z"


def test_the_package_stream_save_also_truncates() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("Z")
    stream = io.BytesIO(b"\0" * 200000)  # held something longer before
    document.package.save(stream)
    assert stream.tell() == len(stream.getvalue())
    HwpxDocument.open(stream.getvalue())


class _NoTruncate(io.BytesIO):
    def truncate(self, size=None):  # type: ignore[override]
        raise io.UnsupportedOperation("truncate")


def test_a_stream_that_cannot_be_cut_short_is_refused_and_left_as_it_was() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("가" * 20000)
    first = io.BytesIO()
    document.save(first)
    stream = _NoTruncate(first.getvalue())
    paragraph.text = "Z"
    with pytest.raises(OSError):
        document.save(stream)
    assert stream.getvalue() == first.getvalue()


# -- what the report says the save kept -------------------------------------------------------


@pytest.mark.parametrize("kind", ["zip64", "prefix"])
def test_the_report_counts_only_records_it_compared_byte_for_byte(kind: str) -> None:
    source = _repacked(zip64=kind == "zip64", level=1, comment=b"marker")
    if kind == "prefix":
        source = b"prefix" + source
    out = io.BytesIO()
    report = HwpxDocument.open(source).save(out)
    written = out.getvalue()

    before, after = dict(_records(source)), dict(_records(written))
    same = sum(before[name] == after.get(name) for name in before)
    records = report.preservation.untouched_local_zip_records
    assert records.verified == same
    assert records.verified + records.changed == len(before)
    assert report.preservation.zip_records_rewritten == {"zip64": "zip64", "prefix": "bytes-before-first-entry"}[kind]
    assert zipfile.ZipFile(io.BytesIO(written)).comment == b"marker"


# -- directory entries and record order -------------------------------------------------------


def test_an_unedited_save_keeps_a_directory_entry() -> None:
    source = _repacked(directory=True)
    out = io.BytesIO()
    report = HwpxDocument.open(source).save(out)
    assert out.getvalue() == source
    assert report.preservation.whole_package_identical


def test_an_unedited_save_keeps_records_where_they_lay() -> None:
    source = _repacked(reverse=True)
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        assert [info.filename for info in archive.infolist()] != [name for name, _ in _records(source)]
    out = io.BytesIO()
    HwpxDocument.open(source).save(out)
    assert out.getvalue() == source


def test_an_edit_keeps_both_orders_of_the_other_records() -> None:
    source = _repacked(reverse=True)
    document = HwpxDocument.open(source)
    document.add_paragraph("더한 글")
    out = io.BytesIO()
    document.save(out)
    written = out.getvalue()
    with zipfile.ZipFile(io.BytesIO(source)) as a, zipfile.ZipFile(io.BytesIO(written)) as b:
        assert [i.filename for i in a.infolist()] == [i.filename for i in b.infolist()]
    assert [name for name, _ in _records(source)] == [name for name, _ in _records(written)]


# -- mimetype where and how the file has it ---------------------------------------------------


def _mimetype_variant(*, last: bool = False, deflated: bool = False) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(HwpxDocument.new().to_bytes())) as source, \
            zipfile.ZipFile(out, "w") as target:
        infos = source.infolist()
        if last:
            infos = infos[1:] + infos[:1]
        for info in infos:
            if info.filename == "mimetype" and deflated:
                copy = zipfile.ZipInfo("mimetype", info.date_time)
                copy.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(copy, source.read(info))
            else:
                target.writestr(info, source.read(info))
    return out.getvalue()


@pytest.mark.parametrize("variant", [{"last": True}, {"deflated": True}, {"last": True, "deflated": True}])
def test_an_unedited_save_keeps_mimetype_where_and_how_the_file_has_it(variant) -> None:
    source = _mimetype_variant(**variant)
    out = io.BytesIO()
    report = HwpxDocument.open(source).save(out)
    assert out.getvalue() == source
    assert report.preservation.whole_package_identical


def test_an_edit_keeps_mimetype_where_and_how_the_file_has_it() -> None:
    source = _mimetype_variant(last=True, deflated=True)
    document = HwpxDocument.open(source)
    document.add_paragraph("더한 글")
    out = io.BytesIO()
    document.save(out)
    written = out.getvalue()
    assert dict(_records(source))["mimetype"] == dict(_records(written))["mimetype"]
    with zipfile.ZipFile(io.BytesIO(written)) as archive:
        assert archive.infolist()[-1].filename == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_DEFLATED
    assert HwpxDocument.open(written).paragraphs[-1].text == "더한 글"


def test_a_new_document_writes_mimetype_first_and_stored() -> None:
    with zipfile.ZipFile(io.BytesIO(HwpxDocument.new().to_bytes())) as archive:
        first = archive.infolist()[0]
        assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)


# -- the archive comment ------------------------------------------------------------------------


def _commented_template() -> bytes:
    base = HwpxDocument.new()
    base.add_paragraph("본문")
    base.add_table(2, 2)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base.to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info))
        target.comment = b"template marker"
    return out.getvalue()


_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000000020001e221bc330000000049454e44ae426082"
)


def _saved(document: HwpxDocument, **kwargs) -> bytes:
    out = io.BytesIO()
    document.save(out, **kwargs)
    return out.getvalue()


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: _saved(d),
        lambda d: d.to_bytes(),
        lambda d: (d.add_paragraph("더함"), _saved(d))[1],
        lambda d: (setattr(d.tables[0].cell(0, 0), "text", "칸"), _saved(d))[1],
        lambda d: (d.add_section(), _saved(d))[1],
        lambda d: (d.media.add_image(_PNG, "png"), _saved(d))[1],
        lambda d: (setattr(d.tables[0].cell(0, 0), "text", "칸"), _saved(d, mode="patch", fallback="rebuild"))[1],
        lambda d: (d.parts.set_document_metadata(title="제목"), _saved(d))[1],
        lambda d: (_saved(d), d.add_paragraph("둘째"), _saved(d))[2],
    ],
    ids=["unedited", "to_bytes", "paragraph", "cell", "section", "image", "patch", "metadata", "twice"],
)
def test_every_save_path_keeps_the_archive_comment(edit) -> None:
    written = edit(HwpxDocument.open(_commented_template()))
    assert zipfile.ZipFile(io.BytesIO(written)).comment == b"template marker"


def test_the_byte_splice_keeps_the_archive_comment() -> None:
    from hwpx.patch import replace_package_text

    result = replace_package_text(_commented_template(), {"본문": "바뀐"})
    assert zipfile.ZipFile(io.BytesIO(result.data)).comment == b"template marker"
