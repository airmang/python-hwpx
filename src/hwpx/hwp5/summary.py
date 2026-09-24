# SPDX-License-Identifier: Apache-2.0
"""``\\x05HwpSummaryInformation``: the document properties of an HWP 5.0 file.

The stream is an OLE property set ([MS-OLEPS]). Only the value types HWP
writes are read: strings, 16/32-bit integers and FILETIME timestamps. A
malformed set yields no properties rather than an error, because the
properties are metadata and never content.
"""

from __future__ import annotations

import datetime as _dt
import struct

TITLE = 2
SUBJECT = 3
AUTHOR = 4
KEYWORDS = 5
COMMENTS = 6
LAST_AUTHOR = 8
REVISION = 9
LAST_PRINTED = 11
CREATED = 12
LAST_SAVED = 13
PAGE_COUNT = 14
DATE_TEXT = 20
PARAGRAPH_COUNT = 21

_VT_I2 = 2
_VT_I4 = 3
_VT_LPSTR = 30
_VT_LPWSTR = 31
_VT_FILETIME = 64
_EPOCH = _dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc)


def filetime_text(value: int) -> str:
    """A FILETIME as ``YYYY-MM-DDTHH:MM:SSZ`` (empty for zero)."""

    if not value:
        return ""
    moment = _EPOCH + _dt.timedelta(microseconds=value // 10)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def filetime_value(text: str) -> int:
    """A ``YYYY-MM-DDTHH:MM:SSZ`` timestamp as a FILETIME (0 when empty or unreadable)."""

    try:
        moment = _dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return 0
    return int((moment - _EPOCH).total_seconds()) * 10_000_000


def read_summary(data: bytes) -> dict[int, object]:
    """Property id -> value (``str`` or ``int``); FILETIMEs stay integers."""

    try:
        return _read(data)
    except (struct.error, IndexError, UnicodeDecodeError, ValueError):
        return {}


def _read(data: bytes) -> dict[int, object]:
    if len(data) < 48:
        return {}
    byte_order, _version, _os, _clsid, sets = struct.unpack_from("<HHI16sI", data, 0)
    if byte_order != 0xFFFE or sets < 1:
        return {}
    _fmtid, offset = struct.unpack_from("<16sI", data, 28)
    _size, count = struct.unpack_from("<II", data, offset)
    out: dict[int, object] = {}
    for index in range(min(count, 256)):
        pid, value_offset = struct.unpack_from("<II", data, offset + 8 + index * 8)
        at = offset + value_offset
        (vt,) = struct.unpack_from("<I", data, at)
        vt &= 0xFFFF
        if vt == _VT_LPWSTR:
            (length,) = struct.unpack_from("<I", data, at + 4)
            raw = data[at + 8 : at + 8 + length * 2]
            out[pid] = raw.decode("utf-16-le", errors="replace").split("\0", 1)[0]
        elif vt == _VT_LPSTR:
            (length,) = struct.unpack_from("<I", data, at + 4)
            raw = data[at + 8 : at + 8 + length]
            out[pid] = raw.split(b"\0", 1)[0].decode("cp949", errors="replace")
        elif vt == _VT_FILETIME:
            (out[pid],) = struct.unpack_from("<Q", data, at + 4)
        elif vt == _VT_I4:
            (out[pid],) = struct.unpack_from("<i", data, at + 4)
        elif vt == _VT_I2:
            (out[pid],) = struct.unpack_from("<h", data, at + 4)
    return out


#: The property set's format id, which is also its class id.
FORMAT_ID = bytes.fromhex("60b6a29f6110d411b4c6006097c09d8c")
#: The properties Hancom writes, in its order, with their value types; the set
#: ends with a dictionary (property 0) of one empty name.
_LAYOUT = (
    (TITLE, _VT_LPWSTR),
    (SUBJECT, _VT_LPWSTR),
    (AUTHOR, _VT_LPWSTR),
    (DATE_TEXT, _VT_LPWSTR),
    (KEYWORDS, _VT_LPWSTR),
    (COMMENTS, _VT_LPWSTR),
    (LAST_AUTHOR, _VT_LPWSTR),
    (REVISION, _VT_LPWSTR),
    (CREATED, _VT_FILETIME),
    (LAST_SAVED, _VT_FILETIME),
    (LAST_PRINTED, _VT_FILETIME),
    (PAGE_COUNT, _VT_I4),
    (PARAGRAPH_COUNT, _VT_I4),
)
_DICTIONARY = bytes.fromhex("01000000000000000100000000")


def write_summary(values: dict[int, object]) -> bytes:
    """The stream of *values* (property id -> ``str`` or ``int``, FILETIMEs as
    integers) laid out as Hancom writes it; a property not given is empty or 0."""

    entries: list[tuple[int, bytes]] = []
    for pid, vt in _LAYOUT:
        value = values.get(pid)
        if vt == _VT_LPWSTR:
            text = (value if isinstance(value, str) else "") + "\0"
            body = struct.pack("<II", vt, len(text)) + text.encode("utf-16-le", errors="surrogatepass")
        elif vt == _VT_FILETIME:
            body = struct.pack("<IQ", vt, value if isinstance(value, int) else 0)
        else:
            body = struct.pack("<Ii", vt, value if isinstance(value, int) else 0)
        entries.append((pid, body + b"\0" * (-len(body) % 4)))
    entries.append((0, _DICTIONARY))
    table = 8 + 8 * len(entries)
    offsets: list[bytes] = []
    body = b""
    for pid, value in entries:
        offsets.append(struct.pack("<II", pid, table + len(body)))
        body += value
    section = struct.pack("<II", table + len(body), len(entries)) + b"".join(offsets) + body
    return struct.pack("<HHI16sI16sI", 0xFFFE, 0, 0x0D, FORMAT_ID, 1, FORMAT_ID, 48) + section
