# SPDX-License-Identifier: Apache-2.0
"""The ``FileHeader`` stream of an HWP 5.0 document (256 bytes)."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import Hwp5Error

SIGNATURE = b"HWP Document File".ljust(32, b"\0")
SIZE = 256

#: Bits of the first property word, by name.
FLAG_BITS: dict[str, int] = {
    "compressed": 0,
    "password": 1,
    "distribution": 2,
    "script": 3,
    "drm": 4,
    "xml_template": 5,
    "history": 6,
    "signature": 7,
    "cert_encrypted": 8,
    "signature_spare": 9,
    "cert_drm": 10,
    "ccl": 11,
    "mobile": 12,
    "privacy_protected": 13,
    "track_changes": 14,
    "kogl": 15,
    "video_control": 16,
    "toc_field": 17,
}

_BODY = struct.Struct("<32sIIIIB")


@dataclass(frozen=True)
class FileHeader:
    """Version, property flags and encryption fields of an HWP 5.0 file."""

    version: tuple[int, int, int, int]
    flags: int
    flags2: int = 0
    encrypt_version: int = 0
    kogl_country: int = 0

    def has(self, name: str) -> bool:
        return bool(self.flags & (1 << FLAG_BITS[name]))

    @property
    def flag_names(self) -> list[str]:
        return [name for name, bit in FLAG_BITS.items() if self.flags & (1 << bit)]

    @property
    def compressed(self) -> bool:
        return self.has("compressed")

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)

    def version_at_least(self, *version: int) -> bool:
        return self.version >= tuple(version) + (0,) * (4 - len(version))

    def to_bytes(self) -> bytes:
        major, minor, build, revision = self.version
        word = (major << 24) | (minor << 16) | (build << 8) | revision
        body = _BODY.pack(
            SIGNATURE, word, self.flags, self.flags2, self.encrypt_version, self.kogl_country
        )
        return body.ljust(SIZE, b"\0")


def parse_file_header(data: bytes) -> FileHeader:
    """Parse the ``FileHeader`` stream; a stream without the signature is not HWP 5.0."""

    if len(data) < _BODY.size or data[:32] != SIGNATURE:
        raise Hwp5Error(
            "The compound file has no HWP 5.0 file header.",
            code="hwp5-not-hwp5",
            suggestion="Only HWP 5.0 documents (.hwp) and HWPX packages can be opened.",
        )
    _sig, word, flags, flags2, encrypt_version, kogl = _BODY.unpack_from(data, 0)
    version = ((word >> 24) & 0xFF, (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)
    return FileHeader(version, flags, flags2, encrypt_version, kogl)
