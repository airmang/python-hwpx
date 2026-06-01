# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import struct
import zlib
from pathlib import Path

__all__ = [
    "RecoverError",
    "recover_entries",
]

_LFH_SIGNATURE = 0x04034B50
_LFH_STRUCT = struct.Struct("<IHHHHHIIIHH")
_LFH_SIZE = _LFH_STRUCT.size
_METHOD_STORED = 0
_METHOD_DEFLATED = 8
_FLAG_DATA_DESCRIPTOR = 0x08


class RecoverError(ValueError):
    """Raised when a local-header entry is present but unsafe to recover."""


def _decompress_deflate(payload: bytes, *, max_entry_size: int) -> bytes:
    decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    output = decompressor.decompress(payload, max_entry_size + 1)
    if len(output) > max_entry_size:
        raise RecoverError(f"recovered entry exceeds max_entry_size={max_entry_size}")
    if not decompressor.eof:
        raise RecoverError("incomplete DEFLATE stream in local header entry")
    if decompressor.unused_data:
        raise RecoverError("DEFLATE stream has trailing data in local header entry")
    output += decompressor.flush()
    if len(output) > max_entry_size:
        raise RecoverError(f"recovered entry exceeds max_entry_size={max_entry_size}")
    return output


def _recover_payload(
    payload: bytes,
    *,
    compress_type: int,
    crc: int,
    uncompressed_size: int,
    max_entry_size: int,
) -> bytes:
    if uncompressed_size > max_entry_size:
        raise RecoverError(f"recovered entry exceeds max_entry_size={max_entry_size}")
    if compress_type == _METHOD_STORED:
        recovered = payload
    elif compress_type == _METHOD_DEFLATED:
        recovered = _decompress_deflate(payload, max_entry_size=max_entry_size)
    else:
        raise RecoverError(f"unsupported ZIP compression method: {compress_type}")

    if len(recovered) > max_entry_size:
        raise RecoverError(f"recovered entry exceeds max_entry_size={max_entry_size}")
    if len(recovered) != uncompressed_size:
        raise RecoverError("recovered entry size does not match local header")
    if (zlib.crc32(recovered) & 0xFFFFFFFF) != crc:
        raise RecoverError("recovered entry CRC does not match local header")
    return recovered


def recover_entries(
    source: str | Path,
    *,
    max_entry_size: int = 64 * 1024 * 1024,
    max_total_size: int = 512 * 1024 * 1024,
    max_source_size: int = 512 * 1024 * 1024,
    max_entries: int = 10000,
) -> dict[str, bytes]:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"input file not found: {source_path}")
    if source_path.stat().st_size > max_source_size:
        raise RecoverError(f"input file exceeds max_source_size={max_source_size}")

    data = source_path.read_bytes()
    entries: dict[str, bytes] = {}
    seen_names: set[str] = set()
    total_size = 0
    offset = 0
    while offset + _LFH_SIZE <= len(data):
        signature_offset = data.find(b"PK\x03\x04", offset)
        if signature_offset < 0:
            break
        offset = signature_offset
        if offset + _LFH_SIZE > len(data):
            break

        (
            signature,
            _version_needed,
            flags,
            compress_type,
            _mod_time,
            _mod_date,
            crc,
            compressed_size,
            uncompressed_size,
            name_len,
            extra_len,
        ) = _LFH_STRUCT.unpack_from(data, offset)
        if signature != _LFH_SIGNATURE:
            offset += 1
            continue

        name_start = offset + _LFH_SIZE
        name_end = name_start + name_len
        payload_start = name_end + extra_len
        payload_end = payload_start + compressed_size
        if name_end > len(data) or payload_start > len(data):
            break

        try:
            name = data[name_start:name_end].decode("utf-8")
        except UnicodeDecodeError:
            offset += 4
            continue

        if name and not name.endswith("/"):
            if name in seen_names:
                raise RecoverError(f"duplicate ZIP entry is ambiguous: {name}")
            seen_names.add(name)

        if flags & _FLAG_DATA_DESCRIPTOR:
            offset = payload_start
            continue
        if payload_end > len(data):
            break

        if name and not name.endswith("/"):
            if len(entries) >= max_entries:
                raise RecoverError(f"recovered entry count exceeds max_entries={max_entries}")
            recovered = _recover_payload(
                data[payload_start:payload_end],
                compress_type=compress_type,
                crc=crc,
                uncompressed_size=uncompressed_size,
                max_entry_size=max_entry_size,
            )
            total_size += len(recovered)
            if total_size > max_total_size:
                raise RecoverError(f"recovered data exceeds max_total_size={max_total_size}")
            entries[name] = recovered

        offset = payload_end

    return entries
