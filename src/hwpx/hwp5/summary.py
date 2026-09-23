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
CREATED = 12
LAST_SAVED = 13
DATE_TEXT = 20

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
