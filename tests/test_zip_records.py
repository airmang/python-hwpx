"""A save keeps the ZIP record of every entry it did not change (hwpx.opc.zip_records).

The bytes of an untouched part must not depend on the deflate the running Python has (zlib, zlib-ng): the
save copies the source's local record -- compressed bytes, flags, extra field, data descriptor -- and only a
changed or new entry is compressed again. A save that changed nothing writes the source file again.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.opc.package import HwpxPackage, HwpxPackageError
from hwpx.opc.zip_records import ZipRecordsUnsupported, assemble, read_records

HANCOM = Path(__file__).resolve().parent / "fixtures" / "hancom_saved"


class _OneWay(io.RawIOBase):
    """A write-only, non-seekable stream: ``zipfile`` then writes data descriptors (flag 0x08)."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        self.buffer += data
        return len(data)


def _foreign_archive() -> bytes:
    """The parts of a new document, packed the way no engine save would: deflate level 1, an extra field
    on every entry, data descriptors, an archive comment."""

    parts = HwpxDocument.new().to_bytes()
    out = _OneWay()
    with zipfile.ZipFile(io.BytesIO(parts)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            copy = zipfile.ZipInfo(info.filename, (2020, 2, 2, 2, 2, 2))
            copy.compress_type = info.compress_type
            copy.extra = b"\xfe\xca\x04\x00abcd"
            target.writestr(copy, source.read(info), compresslevel=1)
        target.comment = b"made elsewhere"
    return bytes(out.buffer)


def _local_records(data: bytes) -> dict[str, bytes]:
    records = read_records(data)
    return {entry.filename: records.local_record(entry) for entry in records.entries}


def test_an_unedited_save_writes_the_source_file_again() -> None:
    source = _foreign_archive()
    assert any(entry.flag_bits & 0x08 for entry in read_records(source).entries)  # descriptors present

    document = HwpxDocument.open(source)
    assert document.to_bytes() == source
    report = document.save(io.BytesIO())
    assert report.preservation.whole_package_identical is True
    assert report.preservation.untouched_local_zip_records.changed == 0
    assert "zipRecordsRewritten" not in report.preservation.to_dict()


def test_an_edit_recompresses_only_its_part() -> None:
    source = _foreign_archive()
    document = HwpxDocument.open(source)
    document.add_paragraph("새 문단")
    target = io.BytesIO()
    report = document.save(target)
    edited = target.getvalue()

    before, after = _local_records(source), _local_records(edited)
    changed = {name for name in after if before.get(name) != after[name]}
    assert changed == {"Contents/section0.xml"}
    with zipfile.ZipFile(io.BytesIO(edited)) as archive:
        assert archive.comment == b"made elsewhere"
    assert report.preservation.untouched_local_zip_records.changed == 0
    assert report.preservation.untouched_local_zip_records.verified == len(before) - 1
    assert report.preservation.whole_package_identical is False


def test_a_hancom_document_comes_back_byte_for_byte_after_an_edit_elsewhere() -> None:
    data = (HANCOM / "pages_footnotes_in_table_cells.hwpx").read_bytes()
    assert HwpxDocument.open(data).to_bytes() == data
    document = HwpxDocument.open(data)
    next(p for p in document.paragraphs if p.text.strip()).text = "고친 문단"
    edited = document.to_bytes()
    before, after = _local_records(data), _local_records(edited)
    assert {name for name in after if before.get(name) != after[name]} == {"Contents/section0.xml"}


def test_saving_twice_keeps_the_records_of_the_first_save() -> None:
    document = HwpxDocument.open(_foreign_archive())
    document.add_paragraph("하나")
    first = document.save(io.BytesIO())
    assert first.preservation.untouched_local_zip_records.changed == 0
    target = io.BytesIO()
    document.save(target)
    again = HwpxDocument.open(target.getvalue())
    assert again.to_bytes() == target.getvalue()


def test_a_new_document_has_no_source_records() -> None:
    document = HwpxDocument.new()
    assert document._package._source_archive is None
    document.add_paragraph("x")
    report = document.save(io.BytesIO())
    assert "zipRecordsRewritten" not in report.preservation.to_dict()


def test_an_archive_it_cannot_keep_record_by_record_is_rewritten_and_the_report_says_so() -> None:
    source = b"prefix bytes" + _foreign_archive()  # zipfile still reads it; the records are not where they say
    with pytest.raises(ZipRecordsUnsupported):
        read_records(source)
    document = HwpxDocument.open(source)
    report = document.save(io.BytesIO())
    assert report.preservation.zip_records_rewritten is not None
    assert report.preservation.to_dict()["zipRecordsRewritten"] == report.preservation.zip_records_rewritten
    assert report.preservation.untouched_part_payloads.changed == 0


def test_a_copied_record_that_does_not_hold_the_content_refuses_the_save(monkeypatch: pytest.MonkeyPatch) -> None:
    document = HwpxDocument.open(_foreign_archive())
    document.add_paragraph("바뀐 글")
    # Pretend every entry is unchanged: the source record of section0.xml would then stand for new content.
    monkeypatch.setattr(HwpxPackage, "_entry_unchanged", lambda self, name, source: True)
    target = io.BytesIO(b"kept")
    with pytest.raises(HwpxPackageError) as caught:
        document.save(target)
    assert caught.value.code == "save-archive-content-mismatch"
    assert target.getvalue() == b"kept"


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda data: data + b"x", "bytes-after-end-record"),
        (lambda data: data.replace(b"PK\x05\x06", b"PK\x05\x07"), "no-end-record"),
    ],
)
def test_read_records_names_what_it_cannot_keep(mutate, reason: str) -> None:
    with pytest.raises(ZipRecordsUnsupported) as caught:
        read_records(mutate(_foreign_archive()))
    assert caught.value.reason == reason


def test_duplicate_names_are_refused() -> None:
    buffer = io.BytesIO()
    with pytest.warns(UserWarning), zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a", b"1")
        archive.writestr("a", b"2")
    with pytest.raises(ZipRecordsUnsupported) as caught:
        read_records(buffer.getvalue())
    assert caught.value.reason == "duplicate-entry-names"


def test_assemble_round_trips_an_archive_in_its_own_orders() -> None:
    data = _foreign_archive()
    records = read_records(data)
    local_order = sorted(records.entries, key=lambda entry: entry.header_offset)
    position = {entry.filename: index for index, entry in enumerate(local_order)}
    rebuilt = assemble(
        [(records.local_record(entry), entry.raw) for entry in local_order],
        records.eocd,
        central_order=[position[entry.filename] for entry in records.entries],
    )
    assert rebuilt == data
