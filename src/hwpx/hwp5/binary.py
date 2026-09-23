# SPDX-License-Identifier: Apache-2.0
"""Little-endian field readers and writers for HWP 5.0 record payloads."""

from __future__ import annotations

import struct

from .errors import damaged

_U8 = struct.Struct("<B")
_I8 = struct.Struct("<b")
_U16 = struct.Struct("<H")
_I16 = struct.Struct("<h")
_U32 = struct.Struct("<I")
_I32 = struct.Struct("<i")


class Cursor:
    """Reads fields from a record payload; running past the end is damage."""

    __slots__ = ("data", "pos", "what")

    def __init__(self, data: bytes, what: str = "record") -> None:
        self.data = data
        self.pos = 0
        self.what = what

    def _take(self, size: int) -> int:
        start = self.pos
        if start + size > len(self.data):
            raise damaged(f"{self.what} is shorter than its fields", record=self.what, size=len(self.data))
        self.pos = start + size
        return start

    def u8(self) -> int:
        return int(_U8.unpack_from(self.data, self._take(1))[0])

    def i8(self) -> int:
        return int(_I8.unpack_from(self.data, self._take(1))[0])

    def u16(self) -> int:
        return int(_U16.unpack_from(self.data, self._take(2))[0])

    def i16(self) -> int:
        return int(_I16.unpack_from(self.data, self._take(2))[0])

    def u32(self) -> int:
        return int(_U32.unpack_from(self.data, self._take(4))[0])

    def i32(self) -> int:
        return int(_I32.unpack_from(self.data, self._take(4))[0])

    def raw(self, size: int) -> bytes:
        start = self._take(size)
        return bytes(self.data[start : start + size])

    def wstr(self) -> str:
        """A WORD character count followed by that many UTF-16 code units."""

        count = self.u16()
        return self.raw(count * 2).decode("utf-16-le", errors="surrogatepass")

    @property
    def left(self) -> int:
        return len(self.data) - self.pos

    def rest(self) -> bytes:
        out = bytes(self.data[self.pos :])
        self.pos = len(self.data)
        return out


class Builder:
    """Writes fields in the same order a :class:`Cursor` reads them."""

    __slots__ = ("out",)

    def __init__(self) -> None:
        self.out = bytearray()

    def u8(self, value: int) -> "Builder":
        self.out += _U8.pack(value & 0xFF)
        return self

    def i8(self, value: int) -> "Builder":
        self.out += _I8.pack(value)
        return self

    def u16(self, value: int) -> "Builder":
        self.out += _U16.pack(value & 0xFFFF)
        return self

    def i16(self, value: int) -> "Builder":
        self.out += _I16.pack(value)
        return self

    def u32(self, value: int) -> "Builder":
        self.out += _U32.pack(value & 0xFFFFFFFF)
        return self

    def i32(self, value: int) -> "Builder":
        self.out += _I32.pack(value)
        return self

    def raw(self, value: bytes) -> "Builder":
        self.out += value
        return self

    def wstr(self, value: str) -> "Builder":
        encoded = value.encode("utf-16-le", errors="surrogatepass")
        self.u16(len(encoded) // 2)
        self.out += encoded
        return self

    def bytes(self) -> bytes:
        return bytes(self.out)
