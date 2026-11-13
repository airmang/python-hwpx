# SPDX-License-Identifier: Apache-2.0
"""Input hardening helpers for HWPX OPC/XML readers."""

from __future__ import annotations

import io
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import IO, Any, Iterable, Iterator
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED as _ZIP_DEFLATED
from zipfile import ZIP_STORED as _ZIP_STORED
from zipfile import ZipFile, ZipInfo

MAX_XML_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 256
MAX_ZIP_ENTRIES = 4096
MAX_ZIP_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 1000.0
MAX_ZIP_READ_CHUNK = 64 * 1024
# `mimetype` is a short fixed string in every real package; reading it during
# format sniffing must not be able to cost the full per-member allowance.
MAX_ZIP_MIMETYPE_BYTES = 4 * 1024
# Container/manifest/preview parts are small by construction; reading them
# during discovery should not cost the generic per-member allowance either.
MAX_ZIP_SMALL_PART_BYTES = 4 * 1024 * 1024

# The only methods HWPX uses, and the only ones CPython decompresses under a
# bound: ``ZipExtFile._read1`` passes ``max_length`` to zlib for ZIP_DEFLATED but
# calls ``decompress(data)`` with no limit for every other method, so a bzip2 or
# lzma member inflates in full before the declared size truncates the result.
# Chunked reading cannot bound those, so they are refused outright.
_ALLOWED_METHODS = (_ZIP_STORED, _ZIP_DEFLATED)


class HwpxSecurityError(ValueError):
    """Raised when an HWPX input exceeds safe parsing limits."""


@dataclass(frozen=True)
class ZipGuardLimits:
    max_entries: int = MAX_ZIP_ENTRIES
    max_member_bytes: int = MAX_ZIP_MEMBER_BYTES
    max_total_uncompressed_bytes: int = MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
    max_compression_ratio: float = MAX_ZIP_COMPRESSION_RATIO


def _iter_file_infos(zf: ZipFile) -> list[ZipInfo]:
    return [info for info in zf.infolist() if not info.is_dir()]


def _guard_zip_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    if PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
        raise HwpxSecurityError(f"unsafe ZIP member path: {name!r}")
    # ``PurePosixPath`` reads ``C:/x`` as a relative path, but joining it onto an
    # output directory on Windows discards that directory entirely.
    windows = PureWindowsPath(normalized)
    if windows.drive or windows.is_absolute():
        raise HwpxSecurityError(f"unsafe ZIP member path: {name!r}")


def guard_zip_file(
    zf: ZipFile,
    *,
    limits: ZipGuardLimits | None = None,
) -> None:
    """Validate ZIP metadata before reading member payloads."""

    active_limits = limits or ZipGuardLimits()
    infos = _iter_file_infos(zf)
    if len(infos) > active_limits.max_entries:
        raise HwpxSecurityError(
            "ZIP archive has too many entries: "
            f"{len(infos)} > {active_limits.max_entries}"
        )

    # ``is_dir()`` only tests for a trailing slash in the name, so a member can
    # opt out of the size accounting below just by calling itself a directory
    # while still holding a payload that ``ZipFile.open()`` will read. Check the
    # name of every entry, and require the ones excluded here to be empty.
    for info in zf.infolist():
        _guard_zip_name(info.filename)
        if info.is_dir() and (info.file_size or info.compress_size):
            raise HwpxSecurityError(
                "ZIP directory entry carries data: "
                f"{info.filename}={info.file_size}/{info.compress_size}"
            )

    total = 0
    for info in infos:
        if info.file_size > active_limits.max_member_bytes:
            raise HwpxSecurityError(
                "ZIP member exceeds uncompressed size limit: "
                f"{info.filename}={info.file_size} > {active_limits.max_member_bytes}"
            )
        total += info.file_size
        if total > active_limits.max_total_uncompressed_bytes:
            raise HwpxSecurityError(
                "ZIP archive exceeds total uncompressed size limit: "
                f"{total} > {active_limits.max_total_uncompressed_bytes}"
            )
        if info.compress_type not in _ALLOWED_METHODS:
            raise HwpxSecurityError(
                "ZIP member uses an unsupported compression method: "
                f"{info.filename}={info.compress_type}"
            )
        # Must run before the ``file_size <= 0`` skip below: a member declaring 0
        # would otherwise bypass every remaining check.
        if info.compress_size > info.file_size + info.file_size // 1000 + 64:
            raise HwpxSecurityError(
                "ZIP member declares less data than it stores: "
                f"{info.filename}={info.file_size} < {info.compress_size}"
            )
        if info.file_size <= 0:
            continue
        if info.compress_size <= 0:
            raise HwpxSecurityError(f"ZIP member has invalid compressed size: {info.filename}")
        ratio = info.file_size / info.compress_size
        if ratio > active_limits.max_compression_ratio:
            raise HwpxSecurityError(
                "ZIP member compression ratio exceeds limit: "
                f"{info.filename}={ratio:.1f} > {active_limits.max_compression_ratio:.1f}"
            )


def read_member(
    zf: ZipFile,
    member: str | ZipInfo,
    *,
    limit: int = MAX_ZIP_MEMBER_BYTES,
) -> bytes:
    """Read one ZIP member without trusting the size it declares.

    ``ZipFile.read()`` calls ``ZipExtFile.read()`` with no argument, which hands
    zlib a 2 GiB ``max_length`` and inflates the whole stream before truncating
    the result to the declared size. Reading in fixed chunks and counting what
    actually arrives keeps the allocation bounded no matter what the central
    directory claims.
    """

    name = member.filename if isinstance(member, ZipInfo) else member
    chunks: list[bytes] = []
    total = 0
    with zf.open(member) as handle:
        while True:
            block = handle.read(MAX_ZIP_READ_CHUNK)
            if not block:
                break
            total += len(block)
            if total > limit:
                raise HwpxSecurityError(
                    "ZIP member exceeds uncompressed size limit: "
                    f"{name} > {limit}"
                )
            chunks.append(block)
    return b"".join(chunks)


def read_zip_members(
    zf: ZipFile,
    *,
    limits: ZipGuardLimits | None = None,
    names: Iterable[str] | None = None,
) -> dict[str, bytes]:
    """Read members with per-member and cumulative bounds on what is produced.

    ``names`` restricts the read to those members; the cumulative budget still
    applies across everything read.
    """

    active_limits = limits or ZipGuardLimits()
    wanted = None if names is None else set(names)
    payloads: dict[str, bytes] = {}
    total = 0
    for info in _iter_file_infos(zf):
        if wanted is not None and info.filename not in wanted:
            continue
        data = read_member(zf, info, limit=active_limits.max_member_bytes)
        total += len(data)
        if total > active_limits.max_total_uncompressed_bytes:
            raise HwpxSecurityError(
                "ZIP archive exceeds total uncompressed size limit: "
                f"{total} > {active_limits.max_total_uncompressed_bytes}"
            )
        payloads[info.filename] = data
    return payloads


def guard_xml_bytes(
    payload: bytes,
    *,
    part_name: str = "XML payload",
    max_xml_bytes: int = MAX_XML_BYTES,
) -> None:
    """Reject XML payloads that should never be parsed from an HWPX package."""

    if len(payload) > max_xml_bytes:
        raise HwpxSecurityError(
            f"{part_name} exceeds XML size limit: {len(payload)} > {max_xml_bytes}"
        )
    lowered = payload[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise HwpxSecurityError(f"{part_name} contains a disallowed DTD/entity declaration")


def guard_xml_depth(
    root: object,
    *,
    part_name: str = "XML payload",
    max_depth: int = MAX_XML_DEPTH,
) -> None:
    """Reject extremely deep XML trees after parsing."""

    # One level at a time: the tree is too deep exactly when a level past
    # ``max_depth`` has a node in it.
    level: list[object] = [root]
    depth = 1
    while level:
        if depth > max_depth:
            raise HwpxSecurityError(
                f"{part_name} exceeds XML depth limit: {depth} > {max_depth}"
            )
        level = [child for element in level for child in element]  # type: ignore[attr-defined]
        depth += 1


def parse_xml_stdlib(
    payload: bytes,
    *,
    part_name: str = "XML payload",
) -> ET.Element:
    """Parse XML with stdlib ElementTree after applying HWPX safety guards."""

    guard_xml_bytes(payload, part_name=part_name)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"malformed XML: {exc}") from exc
    guard_xml_depth(root, part_name=part_name)
    return root


# --------------------------------------------------------------------------- #
# Reading the archive a save has just written once, for every check of that save
# --------------------------------------------------------------------------- #
# A save writes the archive and then checks it several times over: the ZIP
# integrity test, the package check, the reopen, the preservation measurement
# and the quality gate each open the same bytes and inflate the same members.
# Inside ``sharing_archive_reads`` the save registers the bytes it wrote, and
# every check that opens exactly those bytes through ``open_archive`` is handed
# the members that were already inflated.
#
# Nothing is shared by accident: the bytes must equal the registered ones, byte
# for byte, and the registration ends with the save. Outside a save, and for any
# other bytes, ``open_archive`` is ``ZipFile(io.BytesIO(data))``.

_SHARED_READ_CHUNK = 1 << 20


class _Shared:
    """The archive of the save in progress and the members read from it so far."""

    __slots__ = ("data", "members", "well_formed")

    def __init__(self) -> None:
        self.data: bytes | None = None
        self.members: dict[str, bytes] = {}
        #: Members ``parse_xml_stdlib`` has already read without an error.
        self.well_formed: set[str] = set()


_ACTIVE: ContextVar[_Shared | None] = ContextVar("hwpx_shared_archive_reads", default=None)


class _SharedReadZipFile(ZipFile):
    """A read-only ``ZipFile`` whose members are inflated once per save.

    The first read of a member goes through ``zipfile`` to the end of the
    member, so its CRC is checked exactly as before; a member that fails it
    raises ``BadZipFile`` and is not remembered. Later reads get the same bytes
    from memory.
    """

    def __init__(self, data: bytes, members: dict[str, bytes], well_formed: set[str]) -> None:
        super().__init__(io.BytesIO(data), "r")
        self._shared_members = members
        self._shared_well_formed = well_formed

    def open(  # type: ignore[override]
        self,
        name: str | ZipInfo,
        mode: str = "r",
        pwd: bytes | None = None,
        *,
        force_zip64: bool = False,
    ) -> IO[bytes]:
        if mode != "r" or pwd is not None:
            return super().open(name, mode, pwd, force_zip64=force_zip64)
        filename = name.filename if isinstance(name, ZipInfo) else name
        payload = self._shared_members.get(filename)
        if payload is None:
            chunks: list[bytes] = []
            with super().open(name, "r") as handle:
                while True:
                    block = handle.read(_SHARED_READ_CHUNK)
                    if not block:
                        break
                    chunks.append(block)
            payload = b"".join(chunks)
            self._shared_members[filename] = payload
        return io.BytesIO(payload)


@contextmanager
def sharing_archive_reads() -> Iterator[None]:
    """Let the checks of one save share what they read from the archive it wrote.

    Nested uses join the outer one, so a package save inside a document save
    shares with the document's own checks.
    """

    if _ACTIVE.get() is not None:
        yield
        return
    token = _ACTIVE.set(_Shared())
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def register_written_archive(data: bytes) -> None:
    """Name *data* as the archive the save in progress wrote; a no-op outside one."""

    shared = _ACTIVE.get()
    if shared is None:
        return
    if shared.data is not None and _same_bytes(shared.data, data):
        return
    shared.data = data
    shared.members = {}
    shared.well_formed = set()


def open_archive(source: Any) -> ZipFile:
    """Open *source* (bytes, or a ``BytesIO``) for reading.

    Bytes equal to the archive registered by the save in progress share its
    member reads; anything else opens as ``zipfile`` always did.
    """

    stream = source if isinstance(source, io.BytesIO) else None
    shared = _ACTIVE.get()
    if shared is not None and shared.data is not None:
        data = stream.getvalue() if stream is not None else source
        if isinstance(data, bytes) and _same_bytes(shared.data, data):
            return _SharedReadZipFile(shared.data, shared.members, shared.well_formed)
    return ZipFile(stream if stream is not None else io.BytesIO(source), "r")


def note_well_formed(archive: ZipFile, name: str) -> None:
    """Record that ``parse_xml_stdlib`` read member *name* of *archive* without an error."""

    if isinstance(archive, _SharedReadZipFile):
        archive._shared_well_formed.add(name)


def is_known_well_formed(archive: ZipFile, name: str) -> bool:
    """Whether an earlier check of this save already parsed member *name* with ``parse_xml_stdlib``."""

    return isinstance(archive, _SharedReadZipFile) and name in archive._shared_well_formed


def _same_bytes(left: bytes, right: bytes) -> bool:
    return left is right or (len(left) == len(right) and left == right)
