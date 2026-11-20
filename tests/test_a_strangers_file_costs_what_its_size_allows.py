# SPDX-License-Identifier: Apache-2.0
"""Opening a stranger's file costs time and memory in proportion to what the limits allow.

Three places let a small file cost far more than its size:

* the namespace rewrite that runs before a part is parsed read parts of its input again for every
  2016 namespace URI in it, so its time grew with the square of the part's size;
* the check for a document type declaration looked at the first 4 KiB of a part, and the parser
  behind ``TextExtractor`` expands the entities a later declaration defines;
* an HWP 5.0 file's streams were each bounded but not their sum, and a directory may name one chain
  of sectors under many streams.

The time tests use sizes at which the old code took tens of seconds and assert a generous bound.
"""

from __future__ import annotations

import io
import struct
import time
import zipfile
import zlib
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.hwp5 import cfb
from hwpx.hwp5.errors import Hwp5Error
from hwpx.opc import xml_utils
from hwpx.opc.security import HwpxSecurityError, guard_xml_bytes, parse_xml_stdlib
from hwpx.tools.text_extractor import TextExtractor

URI_2016 = b"http://www.hancom.co.kr/hwpml/2016/section"
URI_2011 = b"http://www.hancom.co.kr/hwpml/2011/section"


def _timed(data: bytes) -> float:
    started = time.perf_counter()
    xml_utils.normalize_hwpml_namespaces(data)
    return time.perf_counter() - started


# -- the namespace rewrite ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "piece",
    [
        URI_2016 + b" ",  # the URI in text, again and again
        b"<a " + URI_2016 + b" ",  # after a "<" that opens nothing
        b'<a x="' + URI_2016 + b" ",  # after a quote that never closes
    ],
    ids=["in-text", "unclosed-tag", "unclosed-quote"],
)
@pytest.mark.parametrize("prolog", [b"", b"<!-- c -->"], ids=["plain", "with-comment"])
def test_the_namespace_rewrite_takes_time_in_proportion_to_the_part(piece: bytes, prolog: bytes) -> None:
    data = prolog + b"<r>" + piece * 80_000 + b"</r>"
    assert _timed(data) < 5.0  # the old scan: minutes at this size


def test_a_long_run_of_name_characters_in_a_tag_is_read_once() -> None:
    data = b'<r xmlns:hs="' + URI_2016 + b'" ' + b"a" * 400_000 + b">x</r>"
    assert _timed(data) < 5.0  # the old attribute scan: 31 s at 80,000


def test_the_rewrite_changes_namespace_declarations_and_nothing_else() -> None:
    source = (
        b'<?xml version="1.0"?><?pi ' + URI_2016 + b" ?>"
        b"<!-- " + URI_2016 + b" -->"
        b'<hs:sec xmlns:hs="' + URI_2016 + b"\" xmlns='" + URI_2016 + b"'>"
        b'<hp:case hp:required-namespace="' + URI_2016 + b'">text ' + URI_2016 + b"</hp:case>"
        b"<![CDATA[<a xmlns:q=\"" + URI_2016 + b"\">]]>"
        b"</hs:sec>"
    )
    expected = (
        b'<?xml version="1.0"?><?pi ' + URI_2016 + b" ?>"
        b"<!-- " + URI_2016 + b" -->"
        b'<hs:sec xmlns:hs="' + URI_2011 + b"\" xmlns='" + URI_2011 + b"'>"
        b'<hp:case hp:required-namespace="' + URI_2016 + b'">text ' + URI_2016 + b"</hp:case>"
        b"<![CDATA[<a xmlns:q=\"" + URI_2016 + b"\">]]>"
        b"</hs:sec>"
    )
    assert xml_utils.normalize_hwpml_namespaces(source) == expected
    without_markup_declarations = source.replace(b"<!-- " + URI_2016 + b" -->", b"").replace(
        b"<![CDATA[<a xmlns:q=\"" + URI_2016 + b"\">]]>", b""
    )
    assert b"<!" not in without_markup_declarations
    assert xml_utils.normalize_hwpml_namespaces(without_markup_declarations) == expected.replace(
        b"<!-- " + URI_2016 + b" -->", b""
    ).replace(b"<![CDATA[<a xmlns:q=\"" + URI_2016 + b"\">]]>", b"")


def test_a_document_in_the_2016_namespaces_still_opens() -> None:
    package = HwpxDocument.new()
    package.add_paragraph("2016 이름공간")
    source = zipfile.ZipFile(io.BytesIO(package.to_bytes()))
    rewritten = io.BytesIO()
    with zipfile.ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith((".xml", ".hpf")):
                data = data.replace(b"hwpml/2011/", b"hwpml/2016/")
            target.writestr(info, data)
    assert "2016 이름공간" in HwpxDocument.open(rewritten.getvalue()).text.plain()


# -- a document type declaration ----------------------------------------------------------------

_DTD = b'<!DOCTYPE r [<!ENTITY a "' + b"A" * 64 + b'">]>'


@pytest.mark.parametrize(
    "prolog",
    [
        b"",
        b"<!--" + b" " * 6000 + b"-->",
        b"\n" * 6000,
        b"<?x " + b"y" * 6000 + b"?>",
    ],
    ids=["at-the-head", "after-a-long-comment", "after-blank-lines", "after-a-long-instruction"],
)
def test_a_declaration_is_refused_wherever_the_prolog_puts_it(prolog: bytes) -> None:
    payload = b"<?xml version='1.0'?>" + prolog + _DTD + b"<r>&a;&a;</r>"
    with pytest.raises(HwpxSecurityError):
        guard_xml_bytes(payload)
    with pytest.raises(HwpxSecurityError):
        parse_xml_stdlib(payload)


def test_a_declaration_in_another_encoding_is_refused() -> None:
    text = "<?xml version='1.0' encoding='UTF-16'?>" + " " * 6000 + "<!DOCTYPE r [<!ENTITY a 'AAAA'>]><r>&a;</r>"
    with pytest.raises(HwpxSecurityError):
        parse_xml_stdlib(text.encode("utf-16"))


def test_the_words_of_a_declaration_in_content_are_not_a_declaration() -> None:
    assert parse_xml_stdlib(b"<?xml version='1.0'?><!-- <!DOCTYPE x> --><r>ok</r>").text == "ok"
    assert "<!ENTITY" in (parse_xml_stdlib(b"<r><![CDATA[<!DOCTYPE x [<!ENTITY a 'b'>]>]]></r>").text or "")
    assert parse_xml_stdlib(b"<r>&lt;!ENTITY</r>").text == "<!ENTITY"


def test_the_text_extractor_refuses_a_section_with_a_declaration_past_the_old_window(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    source = zipfile.ZipFile(io.BytesIO(document.to_bytes()))
    path = tmp_path / "declared.hwpx"
    with zipfile.ZipFile(path, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                head, rest = data.split(b"?>", 1)
                data = head + b"?><!--" + b" " * 6000 + b"-->" + _DTD.replace(b"r [", b"sec [") + rest
            target.writestr(info, data)
    with pytest.raises(ValueError):  # HwpxSecurityError is one
        with TextExtractor(str(path)) as extractor:
            extractor.extract_text()


# -- HWP 5.0: the streams of one file together --------------------------------------------------


def _deflated(data: bytes) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def _hwp_with_sections_sharing_one_chain(sections: int, inflated: int) -> bytes:
    """A real .hwp whose Section1..N-1 directory entries all name the one chain that inflates to one
    record of *inflated* bytes."""

    document = HwpxDocument.new()
    document.add_paragraph("hello")
    buffer = io.BytesIO()
    document.save(buffer, format="hwp")
    streams = cfb.read_all_streams(cfb.CompoundFile(buffer.getvalue()))
    record = struct.pack("<I", 0x3FF | (0xFFF << 20)) + struct.pack("<I", inflated) + b"\0" * inflated
    big = _deflated(record)
    streams.append(("BodyText/Section1", big + b"\0" * max(0, 4096 - len(big))))
    for number in range(2, sections):
        streams.append((f"BodyText/Section{number}", b"\0" * 4096))
    data = bytearray(cfb.build_compound_file(streams))

    def entry(name: str) -> int:
        key = name.encode("utf-16-le") + b"\0\0"
        at = data.find(key.ljust(64, b"\0") + struct.pack("<H", len(key)))
        assert at > 0, name
        return at

    start, size = struct.unpack_from("<IQ", data, entry("Section1") + 116)
    for number in range(2, sections):
        struct.pack_into("<IQ", data, entry(f"Section{number}") + 116, start, size)
    return bytes(data)


def test_the_streams_of_an_hwp_file_are_bounded_together(monkeypatch: pytest.MonkeyPatch) -> None:
    one = 600_000
    data = _hwp_with_sections_sharing_one_chain(sections=8, inflated=one)
    assert len(data) < one  # seven sections of 600,000 bytes in a file smaller than one of them

    monkeypatch.setattr(cfb, "MAX_TOTAL_INFLATED_BYTES", 3 * one)
    with pytest.raises(Hwp5Error) as refused:
        HwpxDocument.open(data)
    assert refused.value.code == "hwp5-limit-exceeded"

    monkeypatch.setattr(cfb, "MAX_TOTAL_INFLATED_BYTES", 64 * one)
    assert HwpxDocument.open(data).paragraphs  # within the total it opens as before


def test_reading_a_stream_again_is_counted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("hello")
    buffer = io.BytesIO()
    document.save(buffer, format="hwp")
    compound = cfb.CompoundFile(buffer.getvalue())
    sizes = {path: len(compound.read(path)) for path in compound.stream_paths()}
    monkeypatch.setattr(cfb, "MAX_TOTAL_STREAM_BYTES", sum(sizes.values()))
    for _ in range(3):
        for path in sizes:
            assert len(compound.read(path)) == sizes[path]
    monkeypatch.setattr(cfb, "MAX_TOTAL_STREAM_BYTES", sum(sizes.values()) - 1)
    fresh = cfb.CompoundFile(buffer.getvalue())
    with pytest.raises(Hwp5Error) as refused:
        for path in sizes:
            fresh.read(path)
    assert refused.value.code == "hwp5-limit-exceeded"


def test_real_hwp_files_open_within_the_totals() -> None:
    files = sorted((Path(__file__).parent / "fixtures").rglob("*.hwp"))
    assert files
    for path in files:
        try:
            HwpxDocument.open(str(path))
        except Hwp5Error as error:
            assert error.code != "hwp5-limit-exceeded", path.name  # protected or damaged ones refuse as before


# -- bytes that are no document at all ----------------------------------------------------------


def test_bytes_that_are_no_archive_are_refused_with_the_librarys_error() -> None:
    """7.0 looks at the head of a non-archive to say what it is; random bytes took that look down
    with a bare ``UnicodeError`` four times in ten."""

    import random

    from hwpx.errors import HwpxError

    draw = random.Random(5)
    for _ in range(3000):
        data = bytes(draw.getrandbits(8) for _ in range(draw.choice([4, 16, 64, 600])))
        with pytest.raises(HwpxError):
            HwpxDocument.open(data)
    for data in (b"\xff\xfe" + b"a\0" * 40, b"\xfe\xff" + b"\0a" * 40, b"\xff\xfe", b"\xff"):
        with pytest.raises(HwpxError):
            HwpxDocument.open(data)


# -- a table's grid -----------------------------------------------------------------------------


def _with_section(document: HwpxDocument, change) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(document.to_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                changed = change(data)
                assert changed != data
                data = changed
            target.writestr(info, data)
    return out.getvalue()


def _two_by_two() -> HwpxDocument:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_cell_text(0, 0, "A1")
    return document


def test_a_span_no_table_has_is_refused_before_the_grid_is_laid_out() -> None:
    from hwpx import table_patch
    from hwpx.errors import HwpxValueError

    data = _with_section(
        _two_by_two(),
        lambda xml: xml.replace(
            b'<hp:cellSpan colSpan="1" rowSpan="1"/>', b'<hp:cellSpan colSpan="40000" rowSpan="40000"/>', 1
        ),
    )
    table = HwpxDocument.open(data).tables[0]
    for call in (lambda: table.cell(0, 0), lambda: table.cell_map, lambda: table.set_cell_text(1, 1, "x")):
        started = time.perf_counter()
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == "table-grid-too-large"
        assert time.perf_counter() - started < 2.0  # before: gigabytes and many seconds
    with pytest.raises(HwpxValueError) as refused:
        table_patch.fill_cells(data, [{"table_index": 0, "row": 1, "col": 1, "text": "v"}])
    assert refused.value.code == "table-grid-too-large"


@pytest.mark.parametrize("count", [b"100000", b"999999999999"])
def test_a_row_and_column_count_no_table_has_is_refused(count: bytes) -> None:
    from hwpx.errors import HwpxValueError

    data = _with_section(
        _two_by_two(), lambda xml: xml.replace(b'rowCnt="2"', b'rowCnt="' + count + b'"').replace(b'colCnt="2"', b'colCnt="' + count + b'"')
    )
    with pytest.raises(HwpxValueError) as refused:
        HwpxDocument.open(data).tables[0].cell_map
    assert refused.value.code == "table-grid-too-large"


def test_every_real_table_is_far_inside_the_grid_limit() -> None:
    from hwpx.oxml import table_sizes

    largest = 0
    for folder in ("m2_corpus", "m3_gongmun_gold", "hwpxlib_corpus"):
        for path in sorted((Path(__file__).parent / "fixtures" / folder).glob("*.hwpx")):
            try:
                document = HwpxDocument.open(str(path))
            except Exception:  # the corpus keeps files that do not open
                continue
            for table in document.tables.with_nested:
                largest = max(largest, sum(1 for _ in table.iter_grid()))
    assert 0 < largest * 100 < table_sizes.MAX_TABLE_GRID_POSITIONS


# -- what the ZIP says about itself -------------------------------------------------------------


def test_a_zip_password_entry_and_a_binary_mimetype_are_refused_with_the_librarys_error() -> None:
    from hwpx.errors import HwpxError

    package = HwpxDocument.new().to_bytes()
    encrypted = bytearray(package)
    name = b"Contents/section0.xml"
    local = encrypted.find(b"PK\x03\x04", encrypted.find(name) - 40)
    central = encrypted.find(b"PK\x01\x02", encrypted.rfind(name) - 60)
    assert encrypted[local + 30 : local + 30 + len(name)] == name
    encrypted[local + 6] |= 1  # the "encrypted" bit of the general purpose flags
    encrypted[central + 8] |= 1
    with pytest.raises(HwpxError):  # zipfile itself: RuntimeError "password required"
        HwpxDocument.open(bytes(encrypted))

    source = zipfile.ZipFile(io.BytesIO(package))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(info, b"\xff\xfe\xfa\x80" if info.filename == "mimetype" else source.read(info.filename))
    with pytest.raises(HwpxError) as refused:  # before: UnicodeDecodeError
        HwpxDocument.open(out.getvalue())
    assert refused.value.code == "open-not-hwpx"


def test_the_readers_that_raised_a_parse_error_still_do() -> None:
    """``collect_metrics`` and ``project_section_xml`` gained the declaration check; what they raise for
    XML that is merely malformed stays ElementTree's ``ParseError`` (callers catch ``SyntaxError``)."""

    from xml.etree.ElementTree import ParseError

    from hwpx.tools import page_guard
    from hwpx.tools.ir_equality import project_section_xml

    broken = _with_section(_two_by_two(), lambda xml: b"<hs:sec")
    with pytest.raises(ParseError):
        page_guard.collect_metrics(broken)
    with pytest.raises(ParseError):
        project_section_xml(b"<hs:sec")
    with pytest.raises(HwpxSecurityError):
        project_section_xml(b"<?xml version='1.0'?>" + b"\n" * 6000 + _DTD + b"<r>&a;</r>")


# -- what the second look at these limits found --------------------------------------------------


def test_a_less_than_sign_inside_a_processing_instruction_does_not_stop_the_rewrite() -> None:
    """The fast scan took the ``<`` in the instruction for a tag that never ends and gave up: the root
    stayed in the 2016 namespace and the document read as empty."""

    source = b'<?rule test="price < limit" scope="' + URI_2016 + b'"?><sec xmlns="' + URI_2016 + b'"/>'
    assert xml_utils.normalize_hwpml_namespaces(source) == (
        b'<?rule test="price < limit" scope="' + URI_2016 + b'"?><sec xmlns="' + URI_2011 + b'"/>'
    )
    assert xml_utils.parse_xml(source).tag == "{" + URI_2011.decode() + "}sec"

    document = _two_by_two()
    rewritten = _with_section(
        document,
        lambda xml: xml.replace(b"hwpml/2011/", b"hwpml/2016/").replace(
            b"?>", b'?><?rule test="price < limit" scope="' + URI_2016 + b'"?>', 1
        ),
    )
    opened = HwpxDocument.open(rewritten)
    assert len(opened.tables) == 1 and opened.tables[0].cell(0, 0).text == "A1"


def test_text_given_to_the_section_projection_is_read_as_text() -> None:
    from hwpx.tools.ir_equality import project_section_xml

    for encoding in ("UTF-8", "UTF-16", "ISO-8859-1"):
        text = f'<?xml version="1.0" encoding="{encoding}"?><s><p><run><t>café</t></run></p></s>'
        assert "café" in repr(project_section_xml(text)), encoding
    assert "café" in repr(project_section_xml('<s><p><run><t>café</t></run></p></s>'.encode("utf-8")))


def test_a_declaration_in_another_encoding_is_refused_by_the_lxml_reader_too() -> None:
    text = "<?xml version='1.0' encoding='UTF-16'?><!DOCTYPE r [<!ENTITY a 'AAAA'>]><r>&a;</r>"
    with pytest.raises(HwpxSecurityError):
        xml_utils.parse_xml(text.encode("utf-16"))
    assert xml_utils.parse_xml("<?xml version='1.0' encoding='UTF-16'?><r>가</r>".encode("utf-16")).text == "가"


@pytest.mark.parametrize("name", ["rowCnt", "colCnt"])
def test_a_declared_count_no_table_has_is_refused_wherever_it_is_read(name: str) -> None:
    from hwpx.errors import HwpxValueError

    data = _with_section(_two_by_two(), lambda xml: xml.replace(f'{name}="2"'.encode(), f'{name}="99999999"'.encode()))
    table = HwpxDocument.open(data).tables[0]
    for read in (lambda: table.row_count, lambda: table.column_count, lambda: table.cell_map):
        try:
            read()
        except HwpxValueError as refused:
            assert refused.code == "table-grid-too-large"
    with pytest.raises(HwpxValueError):
        table.row_count if name == "rowCnt" else table.column_count


def test_a_real_table_is_not_refused_by_the_span_limit_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    from hwpx.oxml import table_sizes

    table = HwpxDocument.open(_two_by_two().to_bytes()).tables[0]
    monkeypatch.setattr(table_sizes, "MAX_TABLE_GRID_POSITIONS", 4)
    assert len(table.cell_map) == 2  # exactly at the limit: its cells are 1 by 1


def test_the_scripts_stream_counts_toward_an_hwp_files_total(monkeypatch: pytest.MonkeyPatch) -> None:
    path = next(iter(sorted((Path(__file__).parent / "fixtures").rglob("hancom2024_memo_fields.hwp"))), None)
    if path is None:
        pytest.skip("fixture not present")
    data = path.read_bytes()
    counted: list[int] = []
    original = cfb.CompoundFile.count_inflated

    def spy(self: cfb.CompoundFile, stream: str, size: int) -> None:
        original(self, stream, size)
        counted.append(self._inflated_total)

    monkeypatch.setattr(cfb.CompoundFile, "count_inflated", spy)
    HwpxDocument.open(data)
    total = max(counted)
    monkeypatch.setattr(cfb, "MAX_TOTAL_INFLATED_BYTES", total - 1)
    with pytest.raises(Hwp5Error) as refused:
        HwpxDocument.open(data)
    assert refused.value.code == "hwp5-limit-exceeded"
    monkeypatch.setattr(cfb, "MAX_TOTAL_INFLATED_BYTES", total)
    assert HwpxDocument.open(data).paragraphs
