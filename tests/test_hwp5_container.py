# SPDX-License-Identifier: Apache-2.0
"""HWP 5.0 container and record layer: compound file, FileHeader, records, paragraphs."""

from __future__ import annotations

import struct

import pytest

from hwpx.hwp5 import bodytext, cfb, docinfo
from hwpx.hwp5 import records as rec
from hwpx.hwp5.errors import Hwp5Error
from hwpx.hwp5.fileheader import FileHeader, parse_file_header
from hwpx.hwp5.reader import read_hwp5


def _streams() -> list[tuple[str, bytes]]:
    return [
        ("FileHeader", b"h" * 256),
        ("DocInfo", bytes(range(256)) * 20),
        ("BodyText/Section0", b"s" * 4096),
        ("BodyText/Section1", b"t" * 4095),
        ("BodyText/Section10", b""),
        ("BinData/BIN0001.png", b"p" * 70_000),
        ("PrvText", "미리보기".encode("utf-16-le")),
        ("\x05HwpSummaryInformation", b"x" * 63),
        ("Scripts/DefaultJScript", b"j" * 64),
        ("Scripts/JScriptVersion", b"v" * 65),
    ]


def test_compound_file_round_trip_keeps_every_stream() -> None:
    streams = _streams()
    data = cfb.build_compound_file(streams)
    compound = cfb.CompoundFile(data)

    assert compound.stream_paths() == sorted(path for path, _ in streams)
    for path, payload in streams:
        assert compound.read(path) == payload
    assert len(data) % 512 == 0
    assert compound.major_version == 3


def test_compound_file_directory_is_a_valid_red_black_tree() -> None:
    names = [f"S{i}" for i in range(23)] + ["LongerName", "x"]
    compound = cfb.CompoundFile(cfb.build_compound_file([(n, b"1") for n in names]))
    entries = compound.entries

    def key(sid: int) -> tuple[int, str]:
        name = entries[sid].name
        return (len(name), name.upper())

    def check(sid: int, low: tuple[int, str] | None, high: tuple[int, str] | None) -> int:
        if sid == cfb.NOSTREAM:
            return 1
        entry = entries[sid]
        assert low is None or key(sid) > low
        assert high is None or key(sid) < high
        if entry.color == cfb.COLOR_RED:
            for child in (entry.left, entry.right):
                assert child == cfb.NOSTREAM or entries[child].color == cfb.COLOR_BLACK
        left = check(entry.left, low, key(sid))
        right = check(entry.right, key(sid), high)
        assert left == right
        return left + (entry.color == cfb.COLOR_BLACK)

    root = entries[0].child
    assert entries[root].color == cfb.COLOR_BLACK
    check(root, None, None)


def test_compound_file_with_more_fat_sectors_than_the_header_holds() -> None:
    # 109 FAT sectors in the header cover 13,952 sectors; a bigger file needs DIFAT.
    big = bytes(range(251)) * (15_000 * 512 // 251)
    data = cfb.build_compound_file([("Big", big), ("Small", b"s")])
    compound = cfb.CompoundFile(data)

    assert compound.read("Big") == big
    assert compound.read("Small") == b"s"
    assert struct.unpack_from("<I", data, 0x48)[0] >= 1  # DIFAT sector count


@pytest.mark.parametrize("cut", [100, 4096, 12_000])
def test_truncated_compound_file_is_refused_as_damaged(cut: int) -> None:
    data = cfb.build_compound_file([("Stream", b"a" * 20_000), ("Tail", b"t" * 5000)])
    with pytest.raises(Hwp5Error) as info:
        compound = cfb.CompoundFile(data[:-cut])
        compound.read("Stream")
        compound.read("Tail")
    assert info.value.code == "hwp5-damaged"


def test_looping_sector_chain_is_refused_as_damaged() -> None:
    data = bytearray(cfb.build_compound_file([("Stream", b"a" * 20_000)]))
    fat_sector = struct.unpack_from("<I", data, 0x4C)[0]
    fat_offset = (fat_sector + 1) * 512
    # Point the stream's second sector back at its first.
    first = cfb.CompoundFile(bytes(data)).entry("Stream")
    assert first is not None
    struct.pack_into("<I", data, fat_offset + 4 * (first.start + 1), first.start)
    with pytest.raises(Hwp5Error) as info:
        cfb.CompoundFile(bytes(data)).read("Stream")
    assert info.value.code == "hwp5-damaged"


def test_non_compound_bytes_are_refused_as_damaged() -> None:
    with pytest.raises(Hwp5Error) as info:
        cfb.CompoundFile(b"PK\x03\x04" + b"\0" * 600)
    assert info.value.code == "hwp5-damaged"


def test_records_round_trip_with_extended_size_and_levels() -> None:
    records = [
        rec.Record(rec.PARA_HEADER, 0, b"\1" * 24),
        rec.Record(rec.PARA_TEXT, 1, b"\2" * 5000),
        rec.Record(rec.CTRL_HEADER, 1, b"lbt "),
        rec.Record(rec.LIST_HEADER, 2, b"\3" * 0xFFF),
        rec.Record(rec.PARA_HEADER, 0, b""),
    ]
    data = rec.serialize_records(records)
    stream = rec.parse_records(data, "test")

    assert [(r.tag, r.level, r.payload) for r in stream.records] == [
        (r.tag, r.level, r.payload) for r in records
    ]
    assert [r.tag for r in stream.roots] == [rec.PARA_HEADER, rec.PARA_HEADER]
    assert [c.tag for c in stream.roots[0].children] == [rec.PARA_TEXT, rec.CTRL_HEADER]
    assert stream.roots[0].children[1].children[0].tag == rec.LIST_HEADER
    assert rec.serialize_records(stream.records) == data


def test_record_running_past_its_stream_is_damaged() -> None:
    data = rec.serialize_records([rec.Record(rec.PARA_TEXT, 0, b"abcd")])
    with pytest.raises(Hwp5Error) as info:
        rec.parse_records(data[:-1], "Section0")
    assert info.value.code == "hwp5-damaged"


def test_inflate_round_trip_and_garbage() -> None:
    payload = b"record bytes " * 1000
    assert rec.inflate(rec.deflate(payload), "DocInfo") == payload
    with pytest.raises(Hwp5Error) as info:
        rec.inflate(b"\xff\xff\xff\xff not deflate", "DocInfo")
    assert info.value.code == "hwp5-damaged"


def test_file_header_round_trip() -> None:
    header = FileHeader((5, 1, 1, 0), flags=1 | (1 << 14), flags2=0, encrypt_version=4)
    parsed = parse_file_header(header.to_bytes())

    assert parsed == header
    assert parsed.version_text == "5.1.1.0"
    assert parsed.flag_names == ["compressed", "track_changes"]
    assert parsed.version_at_least(5, 0, 3, 2)
    assert not parsed.version_at_least(5, 1, 2)


def _para_text(*units: int | str | bytes) -> bytes:
    out = bytearray()
    for unit in units:
        if isinstance(unit, bytes):
            out += unit
        elif isinstance(unit, str):
            out += unit.encode("utf-16-le")
        else:
            out += struct.pack("<H", unit)
    return bytes(out)


def _extended(code: int, ctrl: str) -> bytes:
    return struct.pack("<HI", code, bodytext.ctrl_word(ctrl)) + b"\0" * 8 + struct.pack("<H", code)


def _hwp(flags: int = 1, *, version: tuple[int, int, int, int] = (5, 1, 1, 0)) -> bytes:
    doc_props = struct.pack("<7H3I", 1, 1, 1, 1, 1, 1, 1, 0, 0, 0)
    id_map = struct.pack("<18i", *([0] * 18))
    docinfo_records = [
        rec.Record(rec.DOCUMENT_PROPERTIES, 0, doc_props),
        rec.Record(rec.ID_MAPPINGS, 0, id_map),
    ]
    tab = struct.pack("<H", 9) + b"\0" * 12 + struct.pack("<H", 9)
    text = _para_text("가나", _extended(11, "tbl "), "𝐀", tab, 13)
    para_header = struct.pack("<IIHBBHHHIH", 21, 0, 0, 0, 0, 1, 0, 0, 0, 0)
    section_records = [
        rec.Record(rec.PARA_HEADER, 0, para_header),
        rec.Record(rec.PARA_TEXT, 1, text),
        rec.Record(rec.PARA_CHAR_SHAPE, 1, struct.pack("<II", 0, 0)),
        rec.Record(rec.CTRL_HEADER, 1, struct.pack("<I", bodytext.ctrl_word("tbl "))),
    ]
    compressed = bool(flags & 1)

    def pack(records: list[rec.Record]) -> bytes:
        raw = rec.serialize_records(records)
        return rec.deflate(raw) if compressed else raw

    header = FileHeader(version, flags)
    return cfb.build_compound_file(
        [
            ("FileHeader", header.to_bytes()),
            ("DocInfo", pack(docinfo_records)),
            ("BodyText/Section0", pack(section_records)),
        ]
    )


@pytest.mark.parametrize("flags", [0, 1])
def test_read_hwp5_builds_the_record_trees(flags: int) -> None:
    doc = read_hwp5(_hwp(flags))

    assert doc.header.version == (5, 1, 1, 0)
    assert len(doc.sections) == 1
    assert docinfo.mapping_mismatches(doc.docinfo) == {}
    [para] = bodytext.iter_paragraphs(doc.sections[0].roots)
    assert para.char_count == para.text_units == 21
    kinds = [(c.kind, c.text or c.code) for c in para.chunks]
    assert kinds == [
        ("text", "가나"),
        ("extended", 11),
        ("text", "𝐀"),
        ("inline", 9),
        ("char", 13),
    ]
    assert para.chunks[1].control_id == "tbl "
    assert bodytext.record_ctrl_id(para.controls[0]) == "tbl "
    assert para.char_shapes == [(0, 0)]


@pytest.mark.parametrize(
    ("bit", "code"),
    [(1, "hwp5-password"), (2, "hwp5-distribution"), (4, "hwp5-drm"), (8, "hwp5-drm"), (10, "hwp5-drm")],
)
def test_protected_documents_are_refused_with_their_code(bit: int, code: str) -> None:
    with pytest.raises(Hwp5Error) as info:
        read_hwp5(_hwp(1 | (1 << bit)))
    assert info.value.code == code
    assert isinstance(info.value, ValueError)


def test_compound_file_without_file_header_is_not_hwp5() -> None:
    data = cfb.build_compound_file([("WordDocument", b"\0" * 100)])
    with pytest.raises(Hwp5Error) as info:
        read_hwp5(data)
    assert info.value.code == "hwp5-not-hwp5"


def test_other_major_versions_are_refused() -> None:
    with pytest.raises(Hwp5Error) as info:
        read_hwp5(_hwp(1, version=(3, 0, 0, 0)))
    assert info.value.code == "hwp5-version-unsupported"


def test_split_text_counts_malformed_controls() -> None:
    chunks, malformed = bodytext.split_text(_para_text(11, "abc"))
    assert malformed == 1
    assert chunks[0].kind == "extended"
