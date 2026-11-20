# SPDX-License-Identifier: Apache-2.0
"""The ZIP-only readers raise a typed ``HwpxError`` for what is not a readable archive.

``HwpxDocument.open`` says what a non-document is with a ``code`` and a next step. The readers
beside it (``TextExtractor``, ``ObjectFinder``, ``export_text(bytes)``, ``project_document``,
``unpack_hwpx``) let ``zipfile.BadZipFile`` and ``zlib.error`` out for the same input. They now
raise ``HwpxArchiveError`` and ``HwpxCompressedDataError`` in their place, held to one rule: code
written against the exception it replaces cannot tell the difference. The typed error is an
instance of every class the old one was, has the same ``str()`` and ``args``, and pickles back to
itself; ``code``, ``suggestion`` and ``context`` are what is new.

``validate_package`` reports damaged compressed data as an issue instead of raising. Everything
else these tests name is pinned as it was: paths that are not files, malformed XML, the save gate.
"""

from __future__ import annotations

import errno
import io
import json
import pickle
import struct
import sys
import warnings
import zipfile
import zlib
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

import pytest

from hwpx import HwpxDocument
from hwpx.errors import ERROR_CODES, HwpxError
from hwpx.opc.package import HwpxArchiveError, HwpxCompressedDataError, HwpxPackage, _archive_read_error
from hwpx.opc.security import parse_xml_stdlib
from hwpx.patch import paragraph_patch
from hwpx.quality.save_pipeline import SavePipeline
from hwpx.tools import ir_equality
from hwpx.tools.archive_cli import unpack_hwpx, unpack_main
from hwpx.tools.exporter import export_text
from hwpx.tools.object_finder import ObjectFinder
from hwpx.tools.package_validator import (
    _first_unreadable_entry,
    main as validate_package_main,
    validate_editor_open_safety,
    validate_package,
)
from hwpx.tools.text_extractor import TextExtractor

SECTION = "Contents/section0.xml"


# -- inputs ------------------------------------------------------------------------------------


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문 문단입니다. " * 60)
    doc.add_table(2, 2)
    return doc


def _hwpx() -> bytes:
    return _document().to_bytes()


def _hwp() -> bytes:
    """A binary ``.hwp`` (HWP 5.0 compound file), written by the library's own writer."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _document().to_bytes(format="hwp")


def _rewritten(data: bytes, part: str, change: Callable[[bytes], bytes]) -> bytes:
    """*data* with *part* replaced by ``change(part bytes)``; every other entry as it was."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            target.writestr(info, change(payload) if info.filename == part else payload)
    return out.getvalue()


def _with_corrupt_deflate(data: bytes, part: str = SECTION) -> bytes:
    """*data* with the first bytes of *part*'s deflate stream overwritten (the ZIP directory is intact)."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo(part)
        assert info.compress_type == zipfile.ZIP_DEFLATED and info.compress_size > 40
    name_length, extra_length = struct.unpack("<HH", data[info.header_offset + 26 : info.header_offset + 30])
    start = info.header_offset + 30 + name_length + extra_length
    damaged = bytearray(data)
    damaged[start : start + 40] = b"\xff" * 40
    return bytes(damaged)


def _with_failing_crc(data: bytes, part: str = SECTION, which: int = -1) -> bytes:
    """*data* with the CRC its directory records for *part* (the *which*-th entry of that name) changed."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        position, count = archive.start_dir, len(archive.infolist())
    offsets = []
    for _ in range(count):
        name_length, extra_length, comment_length = struct.unpack("<HHH", data[position + 28 : position + 34])
        if data[position + 46 : position + 46 + name_length].decode("utf-8") == part:
            offsets.append(position)
        position += 46 + name_length + extra_length + comment_length
    damaged = bytearray(data)
    damaged[offsets[which] + 16] ^= 0xFF
    return bytes(damaged)


def _with_section_twice(data: bytes) -> bytes:
    """*data* with two entries named as the section; readers read the last one."""

    out = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate name
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == SECTION:
                    target.writestr(info.filename, payload, zipfile.ZIP_DEFLATED)
                    target.writestr(info.filename, payload, zipfile.ZIP_DEFLATED)
                else:
                    target.writestr(info, payload)
    return out.getvalue()


def _with_malformed_section(data: bytes) -> bytes:
    return _rewritten(data, SECTION, lambda _xml: b"<hs:sec xmlns:hs='urn:x'><oops")


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# -- the rule ------------------------------------------------------------------------------------


def _assert_stands_in_for_what_it_replaces(error: BaseException, *, code: str) -> None:
    """*error* is typed, and nothing written against the exception it replaces (its cause) can tell."""

    replaced = error.__cause__
    assert type(replaced) in (zipfile.BadZipFile, zlib.error), replaced
    assert isinstance(error, HwpxError)
    for cls in type(replaced).__mro__:
        assert isinstance(error, cls), (cls, type(error).__mro__)
    assert str(error) == str(replaced)
    assert error.args == replaced.args
    assert not hasattr(replaced, "code")  # so `code` is new, not a changed value
    assert error.code == code and code in ERROR_CODES
    assert error.suggestion, "a typed failure says what to do next"
    assert error.to_dict()["code"] == code and error.to_dict()["message"] == str(replaced)

    again = pickle.loads(pickle.dumps(error))  # what a process pool does with it
    assert type(again) is type(error)
    assert (str(again), again.args) == (str(error), error.args)
    assert (again.code, again.suggestion, again.context) == (error.code, error.suggestion, error.context)


# -- 1. given what is not a ZIP --------------------------------------------------------------------

_READERS: dict[str, Callable[[Path], object]] = {
    "TextExtractor.open": lambda path: TextExtractor(path).open(),
    "TextExtractor.extract_text": lambda path: TextExtractor(str(path)).extract_text(),
    "TextExtractor(stream)": lambda path: TextExtractor(io.BytesIO(path.read_bytes())).extract_text(),  # type: ignore[arg-type]
    "ObjectFinder.find_all": lambda path: ObjectFinder(str(path)).find_all(tag="tbl"),
    "export_text(bytes)": lambda path: export_text(path.read_bytes()),
    "project_document": lambda path: ir_equality.project_document(path.read_bytes()),
    "unpack_hwpx": lambda path: unpack_hwpx(path, path.parent / "unpacked"),
}

_NOT_ZIPS: dict[str, tuple[Callable[[], bytes], str]] = {
    "binary .hwp": (_hwp, "open-hwp5-not-package"),
    "truncated": (lambda: _hwpx()[: len(_hwpx()) // 2], "open-archive-damaged"),
    "text": (lambda: "그냥 메모입니다\n".encode() * 5, "open-not-hwpx"),
    "empty": (lambda: b"", "open-empty-file"),
}


@pytest.mark.parametrize("reader", sorted(_READERS))
@pytest.mark.parametrize("kind", sorted(_NOT_ZIPS))
def test_a_reader_given_what_is_not_a_zip_raises_the_typed_bad_zip_file(tmp_path: Path, reader: str, kind: str) -> None:
    make, code = _NOT_ZIPS[kind]
    path = _write(tmp_path, "input.hwpx", make())

    with pytest.raises(zipfile.BadZipFile) as raised:  # what the callers caught before
        _READERS[reader](path)

    assert type(raised.value) is HwpxArchiveError
    _assert_stands_in_for_what_it_replaces(raised.value, code=code)
    assert str(raised.value) == "File is not a zip file"  # zipfile's words, as before
    with pytest.raises(HwpxArchiveError) as opened:  # the same input through the package door
        HwpxPackage.open(path)
    assert (raised.value.code, raised.value.suggestion) == (opened.value.code, opened.value.suggestion)


# -- 2. given an archive one of whose members cannot be read ---------------------------------------


@pytest.mark.parametrize("reader", sorted(set(_READERS) - {"TextExtractor.open"}))
def test_a_reader_given_damaged_compressed_data_raises_the_typed_zlib_error(tmp_path: Path, reader: str) -> None:
    path = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))

    with pytest.raises(zlib.error) as raised:
        _READERS[reader](path)

    assert type(raised.value) is HwpxCompressedDataError
    _assert_stands_in_for_what_it_replaces(raised.value, code="open-archive-damaged")


@pytest.mark.parametrize("reader", sorted(set(_READERS) - {"TextExtractor.open"}))
def test_a_failed_crc_still_names_its_member(tmp_path: Path, reader: str) -> None:
    path = _write(tmp_path, "crc.hwpx", _with_failing_crc(_hwpx()))

    with pytest.raises(zipfile.BadZipFile) as raised:
        _READERS[reader](path)

    _assert_stands_in_for_what_it_replaces(raised.value, code="open-archive-damaged")
    assert str(raised.value) == f"Bad CRC-32 for file {SECTION!r}"


@pytest.mark.parametrize("unlinked", [False, pytest.param(True, marks=pytest.mark.skipif(sys.platform == "win32", reason="an open file cannot be removed"))])
def test_a_member_of_the_callers_open_archive_is_judged_by_what_was_read(tmp_path: Path, unlinked: bool) -> None:
    """The archive opened, so its member is damaged: the path it came from is not looked up again."""

    path = _write(tmp_path, "crc.hwpx", _with_failing_crc(_hwpx()))
    with zipfile.ZipFile(path if unlinked else io.BytesIO(path.read_bytes())) as archive:
        if unlinked:
            path.unlink()  # the caller's archive stays readable; its path names nothing now
        for read in (lambda: TextExtractor(archive).extract_text(), lambda: ObjectFinder(archive).find_all(tag="tbl")):
            with pytest.raises(zipfile.BadZipFile) as raised:
                read()
            _assert_stands_in_for_what_it_replaces(raised.value, code="open-archive-damaged")
            assert str(raised.value) == f"Bad CRC-32 for file {SECTION!r}"


def test_a_damaged_member_is_not_judged_by_the_bytes_before_the_archive() -> None:
    """A ZIP may follow other bytes; zipfile opens it. Its damaged member is damage, not 'a text file'."""

    data = b"plain text before the archive\n" * 4 + _with_failing_crc(_hwpx())
    for read in (export_text, ir_equality.project_document):
        with pytest.raises(zipfile.BadZipFile) as raised:
            read(data)
        _assert_stands_in_for_what_it_replaces(raised.value, code="open-archive-damaged")


def test_only_the_two_exact_exceptions_are_replaced() -> None:
    class StrictBadZip(zipfile.BadZipFile):
        """A caller's own subclass: an HwpxArchiveError would not be an instance of it."""

    for untouched in (StrictBadZip("x"), KeyError("x"), EOFError(), HwpxArchiveError("already typed")):
        assert _archive_read_error(untouched) is untouched
        assert _archive_read_error(untouched, b"bytes") is untouched


def test_the_readers_still_read_a_document(tmp_path: Path) -> None:
    data = _hwpx()
    path = _write(tmp_path, "ok.hwpx", data)
    assert "본문 문단입니다" in TextExtractor(path).extract_text()
    assert len(ObjectFinder(str(path)).find_all(tag="tbl")) == 1
    assert "본문 문단입니다" in export_text(data)
    assert ir_equality.project_document(data)
    assert unpack_hwpx(path, tmp_path / "out").entries
    with zipfile.ZipFile(path) as archive:  # an archive the caller opened stays open
        assert "본문 문단입니다" in TextExtractor(archive).extract_text()
        assert archive.fp is not None


def test_the_unpack_command_prints_the_same_line_for_a_damaged_archive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    damaged = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))
    with pytest.raises(zlib.error) as raised:
        unpack_hwpx(damaged, tmp_path / "direct")
    assert unpack_main([str(damaged), str(tmp_path / "out")]) == 1
    assert capsys.readouterr().out == f"ERROR: {raised.value.__cause__}\n"


# -- 3. left as it was -----------------------------------------------------------------------------


def test_a_path_that_is_not_a_file_is_still_the_os_error_python_raises(tmp_path: Path) -> None:
    """Its ``errno`` and ``filename`` are what callers branch on, so these are not replaced."""

    for source in (tmp_path, "", tmp_path / "missing.hwpx"):
        with pytest.raises(OSError) as raised:
            TextExtractor(source).open()
        assert not isinstance(raised.value, HwpxError)
        assert raised.value.errno is not None and raised.value.filename is not None
    if sys.platform != "win32":  # seen on POSIX only: the current folder, read as a file
        no_path = ""
        with pytest.raises(IsADirectoryError) as empty:
            HwpxDocument.open(no_path)
        assert not isinstance(empty.value, HwpxError)
        assert (empty.value.errno, empty.value.filename) == (errno.EISDIR, ".")


def test_malformed_xml_is_still_the_parsers_own_error(tmp_path: Path) -> None:
    """``ParseError.code`` is expat's number, so it cannot also carry an error code."""

    with pytest.raises(ValueError, match=r"^malformed XML: unclosed token: line 1, column 3$") as raised:
        parse_xml_stdlib(b"<a><b", part_name="Contents/header.xml")
    assert type(raised.value) is ValueError
    with pytest.raises(ET.ParseError) as parse_error:
        ir_equality.project_section_xml(b"<a>\n<b></a>")
    assert type(parse_error.value) is ET.ParseError
    assert isinstance(parse_error.value.code, int) and parse_error.value.position == (2, 5)

    path = _write(tmp_path, "malformed.hwpx", _with_malformed_section(_hwpx()))
    with pytest.raises(ValueError) as extracted:
        TextExtractor(path).extract_text()
    assert type(extracted.value) is ValueError


def test_a_patch_that_would_write_malformed_xml_raises_and_leaves_the_original(tmp_path: Path) -> None:
    path = tmp_path / "original.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("valid")
    doc.save(path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="^malformed XML: "):
        paragraph_patch(path, [{"paragraph_index": 0, "text": "\0"}], output_path=path)

    assert path.read_bytes() == before


# -- 4. the package check, given damaged compressed data -------------------------------------------


@pytest.mark.parametrize("as_path", [False, True], ids=["bytes", "path"])
def test_validate_package_reports_damaged_compressed_data_as_an_issue(tmp_path: Path, as_path: bool) -> None:
    damaged = _with_corrupt_deflate(_hwpx())
    source: bytes | Path = _write(tmp_path, "damaged.hwpx", damaged) if as_path else damaged

    report = validate_package(source)  # it returns a report; it raised zlib.error

    assert not report.ok
    assert any(issue.part_name == SECTION and "compressed data is damaged" in issue.message for issue in report.errors), report.errors


@pytest.mark.parametrize("part", ["mimetype", "META-INF/container.xml", "Contents/content.hpf", "Contents/header.xml", SECTION])
def test_validate_package_never_passes_an_archive_with_a_damaged_member(part: str) -> None:
    data = _hwpx()
    damaged = _with_failing_crc(data, part) if part == "mimetype" else _with_corrupt_deflate(data, part)  # mimetype is stored
    report = validate_package(damaged)
    assert not report.ok
    assert report.errors[0].part_name == part


def test_validate_package_answers_for_a_failed_crc_as_testzip_does() -> None:
    """The same entries, read by name: of two entries with one name the last is the one read."""

    twice = _with_section_twice(_hwpx())
    archives = {
        "sound": _hwpx(),
        "failed CRC": _with_failing_crc(_hwpx()),
        "first of two failed": _with_failing_crc(twice, which=0),
        "last of two failed": _with_failing_crc(twice, which=-1),
    }
    answers = {}
    for label, data in archives.items():
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            answers[label] = archive.testzip()
            found = _first_unreadable_entry(archive)
        assert (None if found is None else found[0]) == answers[label], label
        assert found is None or found[1] == "ZIP CRC/integrity check failed"
    assert answers == {"sound": None, "failed CRC": SECTION, "first of two failed": None, "last of two failed": SECTION}
    assert validate_package(archives["sound"]).ok
    assert not validate_package(archives["failed CRC"]).ok


def test_the_save_gate_and_the_open_safety_check_still_raise_on_damaged_data() -> None:
    """They check through the same code. A save that raised here never got as far as writing."""

    damaged = _with_corrupt_deflate(_hwpx(), "Contents/content.hpf")
    for check in (SavePipeline().run, validate_editor_open_safety):
        with pytest.raises(zlib.error) as raised:
            check(damaged)
        assert type(raised.value) is zlib.error


def test_the_package_check_command_prints_the_issue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    damaged = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))
    assert validate_package_main([str(damaged)]) == 1
    assert f"ERROR: {SECTION}: ZIP compressed data is damaged" in capsys.readouterr().out


# -- 5. what the empty extras provide --------------------------------------------------------------


def test_capabilities_do_not_report_the_empty_extras_as_installed() -> None:
    from hwpx.capabilities import contract_json_schema, describe_capabilities

    caps = describe_capabilities()
    # visual/xlsx/preview pull nothing in: `pip install "python-hwpx[visual]"` resolves and adds no feature
    assert caps["extras"] == {"visual": False, "xlsx": False, "preview": False}
    assert "python-hwpx-automation" in caps["extrasNote"]
    for name in caps["extras"]:
        assert name in caps["extrasNote"]
    # the public shape: the same keys, booleans, as the schema says
    schema = contract_json_schema("hwpx.capabilities/v1")
    assert schema["properties"]["extras"] == {"type": "object", "additionalProperties": {"type": "boolean"}}
    assert schema["properties"]["extrasNote"] == {"type": "string"}
    assert "extrasNote" not in schema["required"]


def test_the_capabilities_command_prints_the_same_report(capsys: pytest.CaptureFixture[str]) -> None:
    from hwpx.capabilities import _verify_main  # what `python -m hwpx.capabilities` runs

    assert _verify_main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["extras"] == {"visual": False, "xlsx": False, "preview": False}
