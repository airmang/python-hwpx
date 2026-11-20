# SPDX-License-Identifier: Apache-2.0
"""Bad input fails with a typed ``HwpxError`` at every public door, not a bare built-in.

``HwpxDocument.open`` already said what a non-document is, with a ``code`` and a next step.
The readers beside it (``TextExtractor``, ``ObjectFinder``, ``export_text``, ``project_document``,
``collect_metrics``, ``validate_package``, ``unpack_hwpx``) and the table object model let the
standard library's own exception out for the same input: ``BadZipFile: File is not a zip file``,
``zlib.error``, ``ValueError('malformed XML')``, ``ElementTree.ParseError``,
``ValueError: invalid literal for int()``, ``OverflowError``. Each test gives one of those inputs
and asks for an ``HwpxError`` that is still the built-in an existing ``except`` names.
"""

from __future__ import annotations

import inspect
import io
import json
import re
import struct
import warnings
import zipfile
import zlib
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import ERROR_CODES, Hwp5Error, HwpxError
from hwpx.opc.package import (
    HwpxArchiveError,
    HwpxCompressedDataError,
    HwpxPackage,
    HwpxPackageError,
    HwpxStructureError,
    HwpxXmlSyntaxError,
)
from hwpx.opc.security import HwpxSecurityError, parse_xml_stdlib
from hwpx.tools import ir_equality, page_guard
from hwpx.tools.archive_cli import unpack_hwpx, unpack_main
from hwpx.tools.exporter import export_text
from hwpx.tools.object_finder import ObjectFinder
from hwpx.tools.package_validator import validate_package
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


def _hwp(tmp_path: Path) -> Path:
    """A binary ``.hwp`` (HWP 5.0 compound file), written by the library's own writer."""

    target = tmp_path / "binary.hwp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _document().save(target)
    return target


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


def _with_malformed_section(data: bytes) -> bytes:
    return _rewritten(data, SECTION, lambda _xml: b"<hs:sec xmlns:hs='urn:x'><oops")


def _with_cell_attribute(attribute: str, value: str) -> bytes:
    """A 2x2 table whose first ``attribute="<number>"`` is rewritten to *value*."""

    def change(xml: bytes) -> bytes:
        text, count = re.subn(rf'{attribute}="\d+"', f'{attribute}="{value}"', xml.decode("utf-8"), count=1)
        assert count == 1
        return text.encode("utf-8")

    return _rewritten(_hwpx(), SECTION, change)


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _assert_typed(error: BaseException, *builtins: type[BaseException], code: str | None = None) -> None:
    assert isinstance(error, HwpxError), type(error).__mro__
    for builtin in builtins:
        assert isinstance(error, builtin), (builtin, type(error).__mro__)
    assert error.code in ERROR_CODES, error.code
    if code is not None:
        assert error.code == code
    assert error.suggestion, "a typed failure says what to do next"
    assert error.to_dict()["code"] == error.code


# -- 1. the text and object readers, given what is not a ZIP -------------------------------------

_READERS: dict[str, Callable[[Path], object]] = {
    "TextExtractor.open": lambda path: TextExtractor(path).open(),
    "TextExtractor.extract_text": lambda path: TextExtractor(str(path)).extract_text(),
    "ObjectFinder.find_all": lambda path: ObjectFinder(str(path)).find_all(tag="tbl"),
}


@pytest.mark.parametrize("reader", sorted(_READERS))
@pytest.mark.parametrize("kind", ["binary .hwp", "truncated", "not a ZIP"])
def test_the_text_readers_say_what_a_non_zip_is_as_open_does(tmp_path: Path, reader: str, kind: str) -> None:
    if kind == "binary .hwp":
        path = _hwp(tmp_path)
    elif kind == "truncated":
        data = _hwpx()
        path = _write(tmp_path, "cut.hwpx", data[: len(data) // 2])
    else:
        path = _write(tmp_path, "note.hwpx", "그냥 메모입니다\n".encode() * 5)

    with pytest.raises(zipfile.BadZipFile) as raised:  # what the callers caught before
        _READERS[reader](path)

    with pytest.raises(HwpxArchiveError) as opened:  # the same input through the package door
        HwpxPackage.open(path)
    _assert_typed(raised.value, zipfile.BadZipFile, HwpxStructureError, code=opened.value.code)
    assert str(raised.value) == str(opened.value) != "File is not a zip file"
    assert isinstance(raised.value.__cause__, zipfile.BadZipFile)  # zipfile's own error is kept as the cause
    if kind == "binary .hwp":
        assert "HwpxDocument.open" in str(raised.value)  # the door that does read .hwp


@pytest.mark.parametrize("reader", ["TextExtractor.extract_text", "ObjectFinder.find_all"])
def test_the_text_readers_name_damaged_compressed_data(tmp_path: Path, reader: str) -> None:
    path = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))
    with pytest.raises(zlib.error) as raised:
        _READERS[reader](path)
    _assert_typed(raised.value, zlib.error, HwpxCompressedDataError, code="open-archive-damaged")


def test_the_text_reader_refuses_a_folder_and_an_empty_path_as_open_does(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError) as folder:
        TextExtractor(tmp_path).open()
    _assert_typed(folder.value, IsADirectoryError, code="open-is-folder")
    with pytest.raises(FileNotFoundError) as empty:
        TextExtractor("").open()
    _assert_typed(empty.value, FileNotFoundError, code="open-path-empty")


def test_an_archive_the_guard_refused_is_refused_again_and_not_left_open(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("../outside.xml", "<a/>")  # a member path the guard refuses
    extractor = TextExtractor(_write(tmp_path, "unsafe.hwpx", buffer.getvalue()))
    for _attempt in range(2):  # the second open() returned the archive, unchecked
        with pytest.raises(HwpxSecurityError):
            extractor.open()
        assert extractor._zip is None


def test_the_text_readers_still_read_a_document(tmp_path: Path) -> None:
    path = _write(tmp_path, "ok.hwpx", _hwpx())
    assert "본문 문단입니다" in TextExtractor(path).extract_text()
    assert len(ObjectFinder(str(path)).find_all(tag="tbl")) == 1
    with zipfile.ZipFile(path) as archive:  # an archive the caller opened
        assert "본문 문단입니다" in TextExtractor(archive).extract_text()


# -- 2. an empty path ----------------------------------------------------------------------------


@pytest.mark.parametrize("opener", [HwpxDocument.open, HwpxPackage.open], ids=["HwpxDocument", "HwpxPackage"])
def test_an_empty_path_is_refused_as_an_empty_path(opener: Callable[[str], object]) -> None:
    with pytest.raises(HwpxPackageError) as raised:
        opener("")
    error = raised.value
    # a missing file is FileNotFoundError; 7.0.0 raised IsADirectoryError("'.'") for this one
    _assert_typed(error, FileNotFoundError, IsADirectoryError, OSError, code="open-path-empty")
    assert "'.'" not in str(error)


# -- 3. the package check and unpack, given damaged compressed data --------------------------------


@pytest.mark.parametrize("as_path", [False, True], ids=["bytes", "path"])
def test_validate_package_reports_damaged_compressed_data_as_an_issue(tmp_path: Path, as_path: bool) -> None:
    damaged = _with_corrupt_deflate(_hwpx())
    source: bytes | Path = _write(tmp_path, "damaged.hwpx", damaged) if as_path else damaged

    report = validate_package(source)  # it returns a report; it raised zlib.error

    assert not report.ok
    assert any(issue.part_name == SECTION and "compressed data" in issue.message for issue in report.errors), report.errors


def test_validate_package_still_passes_a_sound_document() -> None:
    assert validate_package(_hwpx()).ok


def test_unpack_raises_typed_errors_for_a_damaged_archive(tmp_path: Path) -> None:
    damaged = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))
    with pytest.raises(zlib.error) as compressed:
        unpack_hwpx(damaged, tmp_path / "out-damaged")
    _assert_typed(compressed.value, zlib.error, HwpxCompressedDataError, code="open-archive-damaged")

    not_zip = _write(tmp_path, "note.hwpx", b"plain text, not an archive")
    with pytest.raises(zipfile.BadZipFile) as archive:
        unpack_hwpx(not_zip, tmp_path / "out-note")
    _assert_typed(archive.value, zipfile.BadZipFile, HwpxArchiveError, code="open-not-hwpx")

    with pytest.raises(zipfile.BadZipFile) as binary:
        unpack_hwpx(_hwp(tmp_path), tmp_path / "out-hwp")
    _assert_typed(binary.value, HwpxArchiveError, code="open-hwp5-not-package")


def test_unpack_names_the_entry_it_could_not_write(tmp_path: Path) -> None:
    long_name = "a" * 300 + ".xml"  # longer than any file system's name limit
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr(long_name, "<a/>")
    source = _write(tmp_path, "long.hwpx", buffer.getvalue())

    with pytest.raises(OSError) as raised:
        unpack_hwpx(source, tmp_path / "out-long")

    _assert_typed(raised.value, OSError, code="save-target-unwritable")
    assert raised.value.context["entry"] == long_name  # type: ignore[attr-defined]


def test_the_unpack_command_prints_one_line_for_a_damaged_archive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    damaged = _write(tmp_path, "damaged.hwpx", _with_corrupt_deflate(_hwpx()))
    assert unpack_main([str(damaged), str(tmp_path / "out")]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("ERROR: ") and "압축 데이터가 손상" in printed and "Traceback" not in printed


# -- 4. the stdlib-parser readers, given malformed XML ---------------------------------------------

_XML_READERS: dict[str, Callable[[bytes, Path], object]] = {
    "TextExtractor.extract_text": lambda data, path: TextExtractor(path).extract_text(),
    "ObjectFinder.find_all": lambda data, path: ObjectFinder(path).find_all(tag="tbl"),
    "export_text(bytes)": lambda data, path: export_text(data),
    "project_document": lambda data, path: ir_equality.project_document(data),
    "collect_metrics(bytes)": lambda data, path: page_guard.collect_metrics(data),
    "collect_metrics(path)": lambda data, path: page_guard.collect_metrics(path),
}


@pytest.mark.parametrize("reader", sorted(_XML_READERS))
def test_malformed_xml_is_a_typed_error_every_old_except_still_catches(tmp_path: Path, reader: str) -> None:
    data = _with_malformed_section(_hwpx())
    path = _write(tmp_path, "malformed.hwpx", data)

    with pytest.raises(HwpxError) as raised:
        _XML_READERS[reader](data, path)

    error = raised.value
    # ValueError: what parse_xml_stdlib's callers catch. ParseError/SyntaxError: what
    # collect_metrics and project_section_xml raised (a downstream package catches those).
    _assert_typed(error, ValueError, ET.ParseError, SyntaxError, HwpxXmlSyntaxError, code="package-xml-invalid")
    assert error.part_name == SECTION  # type: ignore[attr-defined]
    assert error.context["part"] == SECTION
    assert error.position == (1, 25)  # type: ignore[attr-defined]  # line and column, as ParseError gives them
    assert error.position == error.__cause__.position  # type: ignore[attr-defined,union-attr]
    assert str(error).startswith("malformed XML: ")  # the sentence, without SyntaxError's "(line 1)" tail


@pytest.mark.parametrize("xml", [b"<hs:sec", "<hs:sec"], ids=["bytes", "str"])
def test_project_section_xml_keeps_raising_what_except_parse_error_catches(xml: bytes | str) -> None:
    for expected in (ET.ParseError, SyntaxError, ValueError, HwpxError):
        with pytest.raises(expected) as raised:
            ir_equality.project_section_xml(xml)
        _assert_typed(raised.value, ET.ParseError, code="package-xml-invalid")


def test_parse_xml_stdlib_keeps_its_signature_and_its_value_error() -> None:
    assert str(inspect.signature(parse_xml_stdlib)) == "(payload: 'bytes', *, part_name: 'str' = 'XML payload') -> 'ET.Element'"
    assert parse_xml_stdlib(b"<a><b/></a>").tag == "a"
    with pytest.raises(ValueError, match=r"^malformed XML: unclosed token: line 1, column 3$") as raised:
        parse_xml_stdlib(b"<a><b", part_name="Contents/header.xml")
    _assert_typed(raised.value, ValueError, ET.ParseError, etree.XMLSyntaxError, code="package-xml-invalid")
    assert raised.value.part_name == "Contents/header.xml"  # type: ignore[attr-defined]
    assert isinstance(raised.value.__cause__, ET.ParseError)
    with pytest.raises(HwpxSecurityError):  # a declaration is still refused as unsafe, not as malformed
        parse_xml_stdlib(b"<!DOCTYPE a [<!ENTITY e 'x'>]><a>&e;</a>")


def test_validate_package_still_reports_malformed_xml_as_an_issue() -> None:
    report = validate_package(_with_malformed_section(_hwpx()))
    assert any(issue.part_name == SECTION and issue.message.startswith("malformed XML: ") for issue in report.errors)


def test_the_save_gate_reports_malformed_xml_instead_of_raising() -> None:
    """Its ``except ET.ParseError`` never matched the ``ValueError`` ``parse_xml_stdlib`` raised."""

    from hwpx.quality.save_pipeline import SavePipeline

    report = SavePipeline().run(_with_malformed_section(_hwpx()))

    assert not report.ok
    assert f"malformed XML in {SECTION}: unclosed token: line 1, column 25" in [error.message for error in report.errors]


# -- 5. table numbers that are not numbers ---------------------------------------------------------

_TABLE_READS: dict[str, Callable[[HwpxDocument], object]] = {
    "cell": lambda doc: doc.tables[0].cell(0, 0),
    "cell_map": lambda doc: doc.tables[0].cell_map,
    "set_cell_text": lambda doc: doc.tables[0].set_cell_text(0, 0, "값"),
    "iter_grid": lambda doc: list(doc.tables[0].iter_grid()),
}

_BAD_CELL_NUMBERS = [
    ("rowSpan", "x", "table-number-invalid"),
    ("colSpan", "-5", "table-number-invalid"),
    ("rowSpan", "1.5", "table-number-invalid"),
    ("colAddr", "", "table-number-invalid"),
    ("rowAddr", "x", "table-number-invalid"),
    ("rowSpan", "9" * 5000, "table-grid-too-large"),  # past int()'s 4300-digit limit
    ("colAddr", "9" * 5000, "table-grid-too-large"),
    ("rowSpan", "70000", "table-grid-too-large"),
]


@pytest.mark.parametrize("read", sorted(_TABLE_READS))
@pytest.mark.parametrize(("attribute", "value", "code"), _BAD_CELL_NUMBERS, ids=lambda v: str(v)[:12])
def test_a_cell_number_that_is_not_a_number_is_a_typed_refusal(read: str, attribute: str, value: str, code: str) -> None:
    doc = HwpxDocument.open(_with_cell_attribute(attribute, value))  # it opens: reading the table is what refuses

    with pytest.raises(ValueError) as raised:  # int() raised ValueError; the refusal is one still
        _TABLE_READS[read](doc)

    _assert_typed(raised.value, ValueError, code=code)
    assert "invalid literal" not in str(raised.value) and "4300" not in str(raised.value)
    if code == "table-number-invalid":
        assert raised.value.context["attribute"] == attribute  # type: ignore[attr-defined]
        assert raised.value.context["value"] == value  # type: ignore[attr-defined]


@pytest.mark.parametrize("attribute", ["width", "height"])
@pytest.mark.parametrize("value", ["x", "9" * 5000])
def test_a_cell_size_that_is_not_a_number_is_a_typed_refusal(attribute: str, value: str) -> None:
    doc = HwpxDocument.open(_hwpx())
    cell = doc.tables[0].cell(0, 0)
    cell.element.find("{*}cellSz").set(attribute, value)
    with pytest.raises(ValueError) as raised:
        getattr(cell, attribute)
    _assert_typed(raised.value, ValueError, code="table-number-invalid")


def test_a_row_count_written_in_other_digits_does_not_reach_int() -> None:
    doc = HwpxDocument.open(_hwpx())
    table = doc.tables[0]
    table.element.set("rowCnt", "²")  # str.isdigit() is true for it; int() refuses it
    assert table.row_count == 2  # counted from the rows, as any rowCnt that is not a number is


@pytest.mark.parametrize("value", ["2", "02", " 2 ", "+2"])
def test_cell_numbers_written_as_numbers_still_read(value: str) -> None:
    doc = HwpxDocument.open(_hwpx())
    table = doc.tables[0]
    table.merge_cells(0, 0, 1, 0)
    span = table.cell(0, 0).element.find("{*}cellSpan")
    assert span.get("rowSpan") == "2"
    span.set("rowSpan", value)
    assert table.cell(0, 0).span == (2, 1)
    assert table.cell(1, 0).element is table.cell(0, 0).element


@pytest.mark.parametrize(("attribute", "value", "_code"), _BAD_CELL_NUMBERS, ids=lambda v: str(v)[:12])
def test_saving_such_a_table_as_hwp_is_a_typed_refusal(tmp_path: Path, attribute: str, value: str, _code: str) -> None:
    doc = HwpxDocument.open(_with_cell_attribute(attribute, value))
    target = tmp_path / "out.hwp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(Hwp5Error) as raised:  # the 5,000-digit one raised OverflowError
            doc.save(target)
    _assert_typed(raised.value, ValueError, code="hwp5-write-unsupported")
    assert "table/cell-number" in raised.value.context["unsupported"]
    assert not target.exists()


@pytest.mark.parametrize("value", ["9" * 5000, "inf", "1e999"])
def test_an_endless_number_elsewhere_does_not_overflow_the_hwp_writer(tmp_path: Path, value: str) -> None:
    """The .hwp writer reads a number it cannot parse as the attribute's default ("x" already did);
    one that parses as an infinite float raised OverflowError instead."""

    def change(xml: bytes) -> bytes:
        text, count = re.subn(r'(<hp:cellSz [^>]*height=")\d+"', rf'\g<1>{value}"', xml.decode("utf-8"), count=1)
        assert count == 1
        return text.encode("utf-8")

    doc = HwpxDocument.open(_rewritten(_hwpx(), SECTION, change))
    target = tmp_path / "out.hwp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc.save(target)
        reopened = HwpxDocument.open(target)
    assert len(reopened.tables) == 1


@pytest.mark.parametrize("value", ["x", "9" * 5000, "inf"])
def test_a_header_number_that_is_not_a_number_is_a_typed_refusal_of_the_hwp_save(tmp_path: Path, value: str) -> None:
    """The header writer raised ``ValueError: could not convert string to float`` or ``OverflowError``."""

    def change(xml: bytes) -> bytes:
        text, count = re.subn(r'(<hh:charPr [^>]*height=")\d+"', rf'\g<1>{value}"', xml.decode("utf-8"), count=1)
        assert count == 1
        return text.encode("utf-8")

    doc = HwpxDocument.open(_rewritten(_hwpx(), "Contents/header.xml", change))
    target = tmp_path / "out.hwp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ValueError) as raised:
            doc.save(target)
    _assert_typed(raised.value, Hwp5Error, ValueError, code="hwp5-write-unsupported")
    assert raised.value.context["attribute"] == "height"  # type: ignore[attr-defined]
    assert not target.exists()


# -- 6. what the empty extras provide --------------------------------------------------------------


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
