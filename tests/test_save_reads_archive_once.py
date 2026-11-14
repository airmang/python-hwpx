"""One save inflates each member of the archive it wrote once.

The ZIP integrity test, the package check, the reopen, the preservation
measurement and the quality gate all read the archive the save has just built.
They share those reads for the length of the save; the bytes each check sees,
and what it reports, are the same as when each opened the archive for itself.
"""

from __future__ import annotations

import io
import zipfile

import pytest

import hwpx.tools.package_validator as package_validator
from hwpx import HwpxDocument
from hwpx.opc import security
from hwpx.opc.security import (
    is_known_well_formed,
    note_well_formed,
    open_archive,
    register_written_archive,
    sharing_archive_reads,
)
from hwpx.opc.package import HwpxPackage, _names_no_style, _reads_as_utf8
from hwpx.tools.package_validator import validate_package


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 문단")
    doc.add_paragraph("둘째 문단")
    return doc


def _count_inflations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Names of the members ``zipfile`` really opens for reading."""

    opened: list[str] = []
    original = zipfile.ZipExtFile.__init__

    def counting(self, fileobj, mode, zipinfo, *args, **kwargs):
        opened.append(zipinfo.filename)
        original(self, fileobj, mode, zipinfo, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipExtFile, "__init__", counting)
    return opened


def test_a_document_save_inflates_each_member_once(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.open(_document().to_bytes())
    doc.add_paragraph("저장할 문단")
    opened = _count_inflations(monkeypatch)
    buffer = io.BytesIO()

    doc.save_to_stream(buffer)

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        members = sorted(info.filename for info in archive.infolist() if not info.is_dir())
    assert sorted(opened) == members


def test_a_package_save_shares_its_own_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    package = HwpxPackage.open(_document().to_bytes())
    opened = _count_inflations(monkeypatch)

    data = package.save()

    assert isinstance(data, bytes)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = sorted(info.filename for info in archive.infolist() if not info.is_dir())
    assert sorted(opened) == members


def test_nothing_is_shared_once_the_save_is_over() -> None:
    doc = _document()
    data = doc.to_bytes()

    assert security._ACTIVE.get() is None
    with open_archive(data) as archive:
        assert type(archive) is zipfile.ZipFile


def test_only_the_registered_bytes_share_reads() -> None:
    written = _document().to_bytes()
    other_doc = _document()
    other_doc.add_paragraph("다른 문서")
    other = other_doc.to_bytes()

    with sharing_archive_reads():
        with open_archive(written) as archive:
            assert type(archive) is zipfile.ZipFile  # nothing registered yet
        register_written_archive(written)
        with open_archive(written) as first, open_archive(io.BytesIO(bytes(written))) as second:
            assert type(first) is not zipfile.ZipFile
            assert type(second) is not zipfile.ZipFile
            assert first.read("mimetype") == second.read("mimetype") == b"application/hwp+zip"
        with open_archive(other) as archive:
            assert type(archive) is zipfile.ZipFile
        register_written_archive(other)  # a second save inside the same scope starts afresh
        with open_archive(written) as archive:
            assert type(archive) is zipfile.ZipFile


def test_shared_reads_return_what_zipfile_returns() -> None:
    data = _document().to_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as plain:
        expected = {info.filename: plain.read(info) for info in plain.infolist()}

    with sharing_archive_reads():
        register_written_archive(data)
        for _ in range(2):  # the second pass is served from memory
            with open_archive(data) as archive:
                assert archive.testzip() is None
                assert {info.filename: archive.read(info) for info in archive.infolist()} == expected
                with archive.open("mimetype") as handle:
                    assert handle.read(5) == b"appli"


def test_a_member_that_fails_its_crc_is_reported_and_not_remembered() -> None:
    data = bytearray(_document().to_bytes())
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as archive:
        info = archive.getinfo("mimetype")  # stored, so its bytes sit in the file as they are
    start = bytes(data).index(b"application/hwp+zip", info.header_offset)
    data[start] ^= 0xFF
    damaged = bytes(data)

    with sharing_archive_reads():
        register_written_archive(damaged)
        for _ in range(2):
            with open_archive(damaged) as archive:
                assert archive.testzip() == "mimetype"
                with pytest.raises(zipfile.BadZipFile):
                    archive.read("mimetype")


def test_well_formed_notes_belong_to_the_shared_archive_only() -> None:
    data = _document().to_bytes()

    with zipfile.ZipFile(io.BytesIO(data)) as plain:
        note_well_formed(plain, "Contents/header.xml")
        assert not is_known_well_formed(plain, "Contents/header.xml")
    with sharing_archive_reads():
        register_written_archive(data)
        with open_archive(data) as archive:
            assert not is_known_well_formed(archive, "Contents/header.xml")
            note_well_formed(archive, "Contents/header.xml")
        with open_archive(data) as archive:
            assert is_known_well_formed(archive, "Contents/header.xml")
            assert not is_known_well_formed(archive, "Contents/section0.xml")


def test_the_package_check_parses_each_part_once(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _document().to_bytes()
    parsed: list[int] = []
    original = package_validator._parse_xml

    def counting(payload: bytes):
        parsed.append(len(payload))
        return original(payload)

    monkeypatch.setattr(package_validator, "_parse_xml", counting)

    report = validate_package(data)

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml_parts = [name for name in archive.namelist() if name.endswith((".xml", ".hpf"))]
    assert report.ok
    assert len(parsed) == len(xml_parts)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><a/>', True),
        (b"<?xml version='1.0' encoding='utf-8'?><a/>", True),
        (b'<?xml version="1.0"?><a/>', True),
        (b"\xef\xbb\xbf<a/>", True),
        (b"<a/>", True),
        (b'<?xml version="1.0" encoding="EUC-KR"?><a/>', False),
        (b'<?xml version="1.0" encoding="UTF-7"?><a/>', False),
        ('<?xml version="1.0" encoding="UTF-16"?><a/>'.encode("utf-16"), False),
        ("<a/>".encode("utf-16-le"), False),
        (b"\n<a/>", False),
        (b"<?xml version='1.0'", False),
        (b"", False),
    ],
)
def test_reads_as_utf8_is_sure_or_says_no(payload: bytes, expected: bool) -> None:
    assert _reads_as_utf8(payload) is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('<p styleIDRef="0"/><p styleIDRef="12"/>', True),
        ("<p/>", True),
        ('<p styleIDRef="본문"/>', False),
        ('<p styleIDRef="0"/><p styleIDRef="Body"/>', False),
        ("<p styleIDRef='0'/>", False),
        ('<p styleIDRef = "0"/>', False),
        ('<p styleIDRef=" 3 "/>', False),
        ('<p styleIDRef="&#49;"/>', False),
        ('<p styleIDRef="0">styleIDRef</p>', False),
    ],
)
def test_names_no_style_is_sure_or_says_no(body: str, expected: bool) -> None:
    payload = f'<?xml version="1.0" encoding="UTF-8"?><s>{body}</s>'.encode("utf-8")

    assert _names_no_style(payload) is expected


def test_a_part_in_another_encoding_is_never_skipped() -> None:
    payload = '<?xml version="1.0" encoding="UTF-16"?><s><p styleIDRef="본문"/></s>'.encode("utf-16")

    assert not _names_no_style(payload)


def test_a_style_name_reference_is_still_converted_on_save() -> None:
    data = _document().to_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                text = payload.decode("utf-8")
                assert 'styleIDRef="0"' in text
                payload = text.replace('styleIDRef="0"', 'styleIDRef="바탕글"', 1).encode("utf-8")
            target.writestr(info, payload)
    package = HwpxPackage.open(out.getvalue())

    saved = package.save()

    assert isinstance(saved, bytes)
    with zipfile.ZipFile(io.BytesIO(saved)) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert 'styleIDRef="바탕글"' not in section
    assert 'styleIDRef="0"' in section
