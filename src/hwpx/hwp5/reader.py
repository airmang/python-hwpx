# SPDX-License-Identifier: Apache-2.0
"""Open an HWP 5.0 document into its header, DocInfo and section record trees."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from . import records as rec
from .cfb import CompoundFile
from .errors import Hwp5Error, damaged
from .fileheader import FileHeader, parse_file_header

_SECTION = re.compile(r"^BodyText/Section(\d+)$")
_VIEW_SECTION = re.compile(r"^ViewText/Section(\d+)$")

_REFUSED_FLAGS: tuple[tuple[str, str, str], ...] = (
    (
        "password",
        "hwp5-password",
        "The HWP document is password-protected.",
    ),
    (
        "distribution",
        "hwp5-distribution",
        "The HWP document is a distribution (read-only) document; its body is encrypted.",
    ),
    (
        "drm",
        "hwp5-drm",
        "The HWP document is DRM-protected.",
    ),
    (
        "cert_encrypted",
        "hwp5-drm",
        "The HWP document is encrypted with a certificate.",
    ),
    (
        "cert_drm",
        "hwp5-drm",
        "The HWP document is certificate-DRM-protected.",
    ),
)


@dataclass
class Hwp5File:
    """The parsed parts of an HWP 5.0 document."""

    header: FileHeader
    compound: CompoundFile
    docinfo: rec.RecordStream
    sections: list[rec.RecordStream]
    notes: dict[str, int] = field(default_factory=dict)

    def stream(self, path: str, *, compressed: bool | None = None) -> bytes:
        """The bytes of *path*, inflated when the document compresses that stream."""

        data = self.compound.read(path)
        if compressed is None:
            compressed = self.header.compressed
        return rec.inflate(data, path) if compressed else data


def refuse_protected(header: FileHeader) -> None:
    """Raise for documents whose body cannot be read without a key."""

    for flag, code, message in _REFUSED_FLAGS:
        if header.has(flag):
            raise Hwp5Error(
                message,
                code=code,
                context={"flags": header.flag_names},
                suggestion="Remove the protection in Hancom Office and save the document again.",
            )


def section_count(docinfo: rec.RecordStream) -> int | None:
    for record in docinfo.roots:
        if record.tag == rec.DOCUMENT_PROPERTIES and len(record.payload) >= 2:
            return int(struct.unpack_from("<H", record.payload, 0)[0])
    return None


def read_hwp5(data: bytes) -> Hwp5File:
    """Parse *data* (the bytes of a ``.hwp`` file) into record trees.

    Raises :class:`~hwpx.hwp5.errors.Hwp5Error` with a stable ``code`` for a
    protected, damaged or foreign file.
    """

    compound = CompoundFile(data)
    if not compound.has_stream("FileHeader"):
        raise Hwp5Error(
            "The compound file has no HWP 5.0 file header.",
            code="hwp5-not-hwp5",
            suggestion="Only HWP 5.0 documents (.hwp) and HWPX packages can be opened.",
        )
    header = parse_file_header(compound.read("FileHeader"))
    if header.version[0] != 5:
        raise Hwp5Error(
            f"HWP file format version {header.version_text} is not supported.",
            code="hwp5-version-unsupported",
            context={"version": header.version_text},
        )
    refuse_protected(header)
    if not compound.has_stream("DocInfo"):
        raise damaged("The HWP document has no DocInfo stream.")
    notes: dict[str, int] = {}
    docinfo = rec.parse_records(
        rec.inflate(compound.read("DocInfo"), "DocInfo") if header.compressed else compound.read("DocInfo"),
        "DocInfo",
    )
    if docinfo.level_jumps:
        notes["docinfo_level_jumps"] = docinfo.level_jumps
    present = sorted(
        (int(m.group(1)), path)
        for path in compound.stream_paths()
        if (m := _SECTION.match(path)) is not None
    )
    declared = section_count(docinfo)
    if not present:
        raise damaged("The HWP document has no BodyText section stream.")
    numbers = [n for n, _ in present]
    if numbers != list(range(len(numbers))):
        raise damaged("The HWP document's section streams are not numbered 0..n-1.", sections=numbers)
    if declared is not None and declared != len(present):
        notes["section_count_mismatch"] = 1
    # A document that tracks changes keeps its body, with the change marks, in
    # ViewText; BodyText holds a stand-in without them.
    if header.has("track_changes"):
        views = sorted(
            (int(m.group(1)), path)
            for path in compound.stream_paths()
            if (m := _VIEW_SECTION.match(path)) is not None
        )
        if [n for n, _ in views] == numbers:
            present = views
            notes["view_text"] = 1
    sections: list[rec.RecordStream] = []
    for _, path in present:
        raw = compound.read(path)
        payload = rec.inflate(raw, path) if header.compressed else raw
        stream = rec.parse_records(payload, path)
        if stream.level_jumps:
            notes["section_level_jumps"] = notes.get("section_level_jumps", 0) + stream.level_jumps
        sections.append(stream)
    return Hwp5File(header, compound, docinfo, sections, notes)
