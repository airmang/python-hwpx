# SPDX-License-Identifier: Apache-2.0
"""ZIP archives as whole records: read where each entry's bytes are, write an archive from such records.

The engine has one ZIP writer for keeping bytes: :func:`assemble`. A save keeps the *local record* (local
header, compressed data and data descriptor -- every byte from one local header to the next) of an entry it
did not change, so an untouched part keeps the very bytes it was opened with, whatever deflate the running
Python has (zlib, zlib-ng, ...). Only a changed or new entry is compressed again. The package save
(:meth:`hwpx.opc.package.HwpxPackage._assemble_archive`) and the byte-splice primitives
(:func:`hwpx.patch._patch_zip_entries`) both write through here.

:func:`read_records` refuses (:class:`ZipRecordsUnsupported`, with a short reason) an archive whose records it
cannot move one by one without losing or misplacing bytes: ZIP64, more than one disk, encrypted entries,
duplicate names, bytes before the first entry or between the central directory and its end record, local and
central records that disagree. A caller then writes the archive the old way and says so.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace
from typing import Sequence

_LOCAL_SIGNATURE = b"PK\x03\x04"
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_CENTRAL_FIXED = struct.Struct("<IHHHHHHIIIHHHHHII")
_EOCD_FIXED = struct.Struct("<IHHHHIIH")
#: Byte offset of the local header offset inside a central directory record.
_CENTRAL_OFFSET_AT = 42
_UTF8_NAME_FLAG = 0x800
_ENCRYPTED_FLAG = 0x1
_ZIP64_EXTRA_ID = 0x0001


class ZipRecordsUnsupported(ValueError):
    """The archive's records cannot be moved one by one; ``reason`` is a short code for the report."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class CentralEntry:
    """One central directory record and where its local record lies in the archive."""

    raw: bytes
    filename: str
    header_offset: int
    compress_type: int
    flag_bits: int
    crc: int
    compressed_size: int
    file_size: int
    name: bytes
    extra: bytes
    comment: bytes
    fields: tuple[int, ...]
    #: End (exclusive) of the local record: the next local header, or the central directory.
    local_end: int = 0


@dataclass(frozen=True)
class ZipRecords:
    """An archive's records: its bytes, central entries in central order, and the end record."""

    data: bytes
    entries: tuple[CentralEntry, ...]
    cd_offset: int
    cd_size: int
    eocd: bytes
    by_name: dict[str, CentralEntry] = field(default_factory=dict, compare=False)

    def local_record(self, entry: CentralEntry) -> bytes:
        """The entry's whole local record -- header, compressed data and any data descriptor."""

        return self.data[entry.header_offset:entry.local_end]


def _find_eocd(data: bytes) -> tuple[int, bytes]:
    start = max(0, len(data) - (65535 + 22))
    offset = data.rfind(_EOCD_SIGNATURE, start)
    if offset < 0 or offset + 22 > len(data):
        raise ZipRecordsUnsupported("no-end-record", "ZIP EOCD not found")
    comment_length = struct.unpack_from("<H", data, offset + 20)[0]
    end = offset + 22 + comment_length
    if end != len(data):
        raise ZipRecordsUnsupported("bytes-after-end-record", "ZIP EOCD comment is truncated or followed by data")
    return offset, data[offset:end]


def _has_zip64_extra(extra: bytes) -> bool:
    cursor = 0
    while cursor + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, cursor)
        if header_id == _ZIP64_EXTRA_ID:
            return True
        cursor += 4 + size
    return False


def read_records(data: bytes, *, zip64_extra_allowed: bool = False) -> ZipRecords:
    """Read *data*'s central directory and the span of every local record, or refuse.

    *zip64_extra_allowed* reads an entry that carries a ZIP64 extra field but whose sizes and offset are in
    its record (none is 0xFFFFFFFF): what zipfile writes again from a ZIP64 source's ZipInfo."""

    eocd_offset, eocd = _find_eocd(data)
    _sig, disk_no, cd_disk, disk_entries, total_entries, cd_size, cd_offset, _clen = _EOCD_FIXED.unpack_from(eocd)
    if disk_no != 0 or cd_disk != 0 or disk_entries != total_entries:
        raise ZipRecordsUnsupported("multi-disk")
    if total_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ZipRecordsUnsupported("zip64")
    if cd_offset + cd_size != eocd_offset:
        # The directory is not where the end record says. Name why, as the save report shows it.
        if eocd_offset >= 20 and data[eocd_offset - 20:eocd_offset - 16] == _ZIP64_LOCATOR_SIGNATURE:
            raise ZipRecordsUnsupported("zip64")  # a ZIP64 end record and locator come before it
        found_at = eocd_offset - cd_size
        if found_at > cd_offset and data[found_at:found_at + 4] == _CENTRAL_SIGNATURE:
            # The whole archive is shifted: bytes (a stub, a prefix) come before the first record.
            raise ZipRecordsUnsupported("bytes-before-first-entry")
        raise ZipRecordsUnsupported("bytes-before-end-record")

    entries: list[CentralEntry] = []
    cursor, end = cd_offset, cd_offset + cd_size
    while cursor < end:
        if data[cursor:cursor + 4] != _CENTRAL_SIGNATURE:
            raise ZipRecordsUnsupported("central-record-damaged")
        fixed = _CENTRAL_FIXED.unpack_from(data, cursor)
        flag_bits, compress_type = fixed[3], fixed[4]
        name_len, extra_len, comment_len, header_offset = fixed[10], fixed[11], fixed[12], fixed[16]
        entry_end = cursor + 46 + name_len + extra_len + comment_len
        if entry_end > end:
            raise ZipRecordsUnsupported("central-record-damaged")
        name = data[cursor + 46:cursor + 46 + name_len]
        extra = data[cursor + 46 + name_len:cursor + 46 + name_len + extra_len]
        if flag_bits & _ENCRYPTED_FLAG:
            raise ZipRecordsUnsupported("encrypted-entry")
        if (_has_zip64_extra(extra) and not zip64_extra_allowed) or 0xFFFFFFFF in (fixed[8], fixed[9], header_offset):
            raise ZipRecordsUnsupported("zip64")
        try:
            filename = name.decode("utf-8" if flag_bits & _UTF8_NAME_FLAG else "cp437")
        except UnicodeDecodeError as exc:
            raise ZipRecordsUnsupported("entry-name-undecodable") from exc
        entries.append(
            CentralEntry(
                raw=data[cursor:entry_end],
                filename=filename,
                header_offset=header_offset,
                compress_type=compress_type,
                flag_bits=flag_bits,
                crc=fixed[7],
                compressed_size=fixed[8],
                file_size=fixed[9],
                name=name,
                extra=extra,
                comment=data[cursor + 46 + name_len + extra_len:entry_end],
                fields=fixed,
            )
        )
        cursor = entry_end
    if cursor != end or len(entries) != total_entries:
        raise ZipRecordsUnsupported("central-record-damaged", "entry count or size does not add up")
    names = [entry.filename for entry in entries]
    if len(set(names)) != len(names):
        raise ZipRecordsUnsupported("duplicate-entry-names")

    by_offset = sorted(entries, key=lambda entry: entry.header_offset)
    if by_offset and by_offset[0].header_offset != 0:
        raise ZipRecordsUnsupported("bytes-before-first-entry")
    if not by_offset and cd_offset != 0:
        raise ZipRecordsUnsupported("bytes-before-first-entry")
    ends: dict[str, int] = {}
    for index, entry in enumerate(by_offset):
        local_end = by_offset[index + 1].header_offset if index + 1 < len(by_offset) else cd_offset
        start = entry.header_offset
        if start + 30 > local_end or data[start:start + 4] != _LOCAL_SIGNATURE:
            raise ZipRecordsUnsupported("local-record-damaged")
        local_name_len, local_extra_len = struct.unpack_from("<HH", data, start + 26)
        if data[start + 30:start + 30 + local_name_len] != entry.name:
            raise ZipRecordsUnsupported("local-central-name-mismatch")
        data_start = start + 30 + local_name_len + local_extra_len
        if data_start + entry.compressed_size > local_end:
            raise ZipRecordsUnsupported("local-record-damaged")
        ends[entry.filename] = local_end
    placed = tuple(replace(entry, local_end=ends[entry.filename]) for entry in entries)
    return ZipRecords(
        data=data,
        entries=placed,
        cd_offset=cd_offset,
        cd_size=cd_size,
        eocd=eocd,
        by_name={entry.filename: entry for entry in placed},
    )


def assemble(
    records: Sequence[tuple[bytes, bytes]],
    eocd: bytes,
    *,
    central_order: Sequence[int] | None = None,
) -> bytes:
    """Write an archive from ``(local record, central record)`` pairs, local records in this order, ending
    with *eocd*.

    Each local record is written as given; its central record gets the new local header offset. The central
    directory lists the records in *central_order* (indexes into *records*; default: the same order). The end
    record keeps everything of *eocd* (its comment too) but the entry counts and the directory's size and
    offset."""

    output = bytearray()
    offsets: list[int] = []
    for local, _central in records:
        offsets.append(len(output))
        output += local
    if len(output) > 0xFFFFFFFF or len(records) >= 0xFFFF:
        raise ZipRecordsUnsupported("zip64", "the archive would need ZIP64")
    order = range(len(records)) if central_order is None else central_order
    if sorted(order) != list(range(len(records))):
        raise ValueError("central_order must list every record once")
    cd_offset = len(output)
    for index in order:
        record = bytearray(records[index][1])
        struct.pack_into("<I", record, _CENTRAL_OFFSET_AT, offsets[index])
        output += record
    cd_size = len(output) - cd_offset
    end = bytearray(eocd)
    struct.pack_into("<HHII", end, 8, len(records), len(records), cd_size, cd_offset)
    output += end
    return bytes(output)


def lay_out_records(data: bytes, physical: Sequence[str]) -> bytes:
    """*data* with its local records lying in the order *physical* names them (names it does not list go
    after, in the order they lay); the central directory keeps its order and the end record its comment.

    For an archive ``zipfile`` has just written, whose records lie in central order, when the archive it
    was made from had them in another (a ZIP64 or prefixed source cannot keep its records, but it keeps
    where they lay). Raises :class:`ZipRecordsUnsupported` for an archive whose records cannot be moved."""

    archive = read_records(data, zip64_extra_allowed=True)
    rank = {name: index for index, name in enumerate(physical)}
    local = sorted(
        archive.entries,
        key=lambda entry: (0, rank[entry.filename]) if entry.filename in rank else (1, entry.header_offset),
    )
    slot = {entry.filename: index for index, entry in enumerate(local)}
    return assemble(
        [(archive.local_record(entry), entry.raw) for entry in local],
        archive.eocd,
        central_order=[slot[entry.filename] for entry in archive.entries],
    )


__all__ = [
    "CentralEntry",
    "ZipRecords",
    "ZipRecordsUnsupported",
    "assemble",
    "lay_out_records",
    "read_records",
]
