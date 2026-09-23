# SPDX-License-Identifier: Apache-2.0
"""Compound File Binary ([MS-CFB]) reader and writer for HWP 5.0 documents.

An HWP 5.0 document is a compound file: a small FAT file system of storages
(directories) and streams inside one file. :class:`CompoundFile` reads every
stream by following the sector chains and refuses a file whose chains leave
the file, loop, or end before the stream does. :func:`build_compound_file`
writes a version 3 compound file (512-byte sectors, 64-byte mini sectors and a
4,096-byte mini stream cutoff) with a red-black directory tree per storage.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping, Sequence

from .errors import damaged, limit_exceeded, write_unsupported

SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

MAXREGSECT = 0xFFFFFFFA
DIFSECT = 0xFFFFFFFC
FATSECT = 0xFFFFFFFD
ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF
NOSTREAM = 0xFFFFFFFF

TYPE_EMPTY = 0
TYPE_STORAGE = 1
TYPE_STREAM = 2
TYPE_ROOT = 5

COLOR_RED = 0
COLOR_BLACK = 1

MAX_DIRECTORY_ENTRIES = 65536
MAX_STREAM_BYTES = 256 * 1024 * 1024

_HEADER = struct.Struct("<8s16sHHHHH6sIIIIIIIII")
_DIFAT_IN_HEADER = 109
_DIRENT = struct.Struct("<64sHBBIII16sIQQIQ")
_DIRENT_SIZE = 128
_V3_SECTOR = 512
_MINI_SECTOR = 64
_MINI_CUTOFF = 4096


@dataclass(frozen=True)
class DirectoryEntry:
    """One directory entry: a storage, a stream or the root."""

    sid: int
    name: str
    kind: int
    color: int
    left: int
    right: int
    child: int
    clsid: bytes
    state: int
    created: int
    modified: int
    start: int
    size: int


class CompoundFile:
    """A parsed compound file held in memory.

    Paths use ``/`` between storage and stream names, for example
    ``"BodyText/Section0"``. The root storage has no name in a path.
    """

    def __init__(self, data: bytes) -> None:
        self._data = memoryview(data)
        if len(data) < _V3_SECTOR or bytes(data[:8]) != SIGNATURE:
            raise damaged("not a compound file (signature mismatch)")
        (
            _sig,
            _clsid,
            _minor,
            major,
            byte_order,
            sector_shift,
            mini_shift,
            _reserved,
            _dir_sector_count,
            fat_sector_count,
            first_dir_sector,
            _transaction,
            mini_cutoff,
            first_minifat_sector,
            minifat_sector_count,
            first_difat_sector,
            difat_sector_count,
        ) = _HEADER.unpack_from(data, 0)
        if byte_order != 0xFFFE:
            raise damaged("compound file byte order mark is not little-endian", byte_order=byte_order)
        if (major, sector_shift) not in ((3, 9), (4, 12)) or mini_shift != 6:
            raise damaged(
                "unsupported compound file sector size",
                major=major,
                sector_shift=sector_shift,
                mini_shift=mini_shift,
            )
        self.major_version = major
        self.sector_size = 1 << sector_shift
        self.mini_cutoff = mini_cutoff
        self._per_sector = self.sector_size // 4
        body = len(data) - self.sector_size
        self._sector_count = max(0, (body + self.sector_size - 1) // self.sector_size)
        self._fat = self._read_fat(data, fat_sector_count, first_difat_sector, difat_sector_count)
        self.entries = self._read_directory(first_dir_sector)
        root = self.entries[0]
        if root.kind != TYPE_ROOT:
            raise damaged("compound file directory does not start with the root entry")
        self._minifat = self._read_minifat(first_minifat_sector, minifat_sector_count)
        self._mini_stream = (
            self._read_chain(root.start, root.size, "root mini stream") if root.size else b""
        )
        self._paths = self._walk_tree()

    # -- container structure -------------------------------------------------

    def _sector(self, index: int) -> memoryview:
        offset = (index + 1) * self.sector_size
        return self._data[offset : offset + self.sector_size]

    def _read_fat(
        self, data: bytes, fat_sector_count: int, first_difat: int, difat_count: int
    ) -> list[int]:
        difat = list(struct.unpack_from(f"<{_DIFAT_IN_HEADER}I", data, 0x4C))
        sector = first_difat
        steps = 0
        while sector not in (ENDOFCHAIN, FREESECT) and steps < difat_count:
            if sector >= self._sector_count:
                raise damaged("DIFAT chain points outside the file", sector=sector)
            chunk = self._sector(sector)
            if len(chunk) < self.sector_size:
                raise damaged("DIFAT sector is cut short", sector=sector)
            entries = struct.unpack(f"<{self._per_sector}I", chunk)
            difat.extend(entries[:-1])
            sector = entries[-1]
            steps += 1
            if steps > self._sector_count:
                raise damaged("DIFAT chain loops")
        fat_sectors = [s for s in difat if s <= MAXREGSECT][:fat_sector_count]
        if len(fat_sectors) < fat_sector_count:
            raise damaged(
                "compound file lists fewer FAT sectors than its header declares",
                declared=fat_sector_count,
                found=len(fat_sectors),
            )
        fat: list[int] = []
        for sector in fat_sectors:
            chunk = self._sector(sector)
            if sector >= self._sector_count or len(chunk) < self.sector_size:
                raise damaged("FAT sector lies outside the file", sector=sector)
            fat.extend(struct.unpack(f"<{self._per_sector}I", chunk))
        return fat

    def _chain(self, start: int, what: str) -> list[int]:
        chain: list[int] = []
        seen: set[int] = set()
        sector = start
        fat = self._fat
        limit = self._sector_count
        while sector != ENDOFCHAIN:
            if sector > MAXREGSECT or sector >= limit or sector >= len(fat):
                raise damaged(f"{what} chain points outside the file", sector=sector)
            if sector in seen:
                raise damaged(f"{what} chain loops", sector=sector)
            seen.add(sector)
            chain.append(sector)
            sector = fat[sector]
        return chain

    def _read_chain(self, start: int, size: int, what: str) -> bytes:
        if size > MAX_STREAM_BYTES:
            raise limit_exceeded(f"{what} is larger than the stream limit", size=size)
        needed = (size + self.sector_size - 1) // self.sector_size
        chain = self._chain_prefix(start, needed, what)
        payload = b"".join(self._sector(s) for s in chain)
        if len(payload) < size:
            raise damaged(f"{what} ends before its declared size", size=size, read=len(payload))
        return payload[:size]

    def _chain_prefix(self, start: int, count: int, what: str) -> list[int]:
        """The first *count* sectors of a chain; a shorter chain is damage."""

        chain: list[int] = []
        seen: set[int] = set()
        sector = start
        fat = self._fat
        limit = self._sector_count
        while len(chain) < count:
            if sector == ENDOFCHAIN:
                raise damaged(f"{what} chain ends before its declared size", sectors=len(chain))
            if sector > MAXREGSECT or sector >= limit or sector >= len(fat):
                raise damaged(f"{what} chain points outside the file", sector=sector)
            if sector in seen:
                raise damaged(f"{what} chain loops", sector=sector)
            seen.add(sector)
            chain.append(sector)
            sector = fat[sector]
        return chain

    def _read_directory(self, first_sector: int) -> list[DirectoryEntry]:
        raw = b"".join(self._sector(s) for s in self._chain(first_sector, "directory"))
        count = len(raw) // _DIRENT_SIZE
        if count == 0:
            raise damaged("compound file has no directory entries")
        if count > MAX_DIRECTORY_ENTRIES:
            raise limit_exceeded("compound file has too many directory entries", count=count)
        entries: list[DirectoryEntry] = []
        for sid in range(count):
            (
                raw_name,
                name_len,
                kind,
                color,
                left,
                right,
                child,
                clsid,
                state,
                created,
                modified,
                start,
                size,
            ) = _DIRENT.unpack_from(raw, sid * _DIRENT_SIZE)
            if self.major_version == 3:
                size &= 0xFFFFFFFF
            if kind in (TYPE_STORAGE, TYPE_STREAM, TYPE_ROOT):
                if name_len < 2 or name_len > 64 or name_len % 2:
                    raise damaged("directory entry has an invalid name length", sid=sid)
                name = raw_name[: name_len - 2].decode("utf-16-le", errors="replace")
            else:
                name = ""
            entries.append(
                DirectoryEntry(
                    sid, name, kind, color, left, right, child, clsid, state, created, modified, start, size
                )
            )
        return entries

    def _read_minifat(self, first_sector: int, count: int) -> list[int]:
        if first_sector == ENDOFCHAIN or count == 0:
            return []
        chain = self._chain(first_sector, "mini FAT")
        return list(
            struct.unpack(
                f"<{len(chain) * self._per_sector}I",
                b"".join(self._sector(s) for s in chain),
            )
        )

    def _read_mini(self, start: int, size: int, what: str) -> bytes:
        needed = (size + _MINI_SECTOR - 1) // _MINI_SECTOR
        parts: list[bytes] = []
        seen: set[int] = set()
        sector = start
        minifat = self._minifat
        stream = self._mini_stream
        for _ in range(needed):
            if sector == ENDOFCHAIN:
                raise damaged(f"{what} mini chain ends before its declared size")
            offset = sector * _MINI_SECTOR
            if sector >= len(minifat) or offset >= len(stream):
                raise damaged(f"{what} mini chain points outside the mini stream", sector=sector)
            if sector in seen:
                raise damaged(f"{what} mini chain loops", sector=sector)
            seen.add(sector)
            parts.append(stream[offset : offset + _MINI_SECTOR])
            sector = minifat[sector]
        payload = b"".join(parts)
        if len(payload) < size:
            raise damaged(f"{what} ends before its declared size", size=size, read=len(payload))
        return payload[:size]

    def _walk_tree(self) -> dict[str, DirectoryEntry]:
        paths: dict[str, DirectoryEntry] = {}
        seen: set[int] = {0}
        stack: list[tuple[int, str]] = [(self.entries[0].child, "")]
        while stack:
            current, prefix = stack.pop()
            if current == NOSTREAM:
                continue
            if current >= len(self.entries) or current in seen:
                raise damaged("compound file directory tree is malformed", sid=current)
            seen.add(current)
            entry = self.entries[current]
            if entry.kind not in (TYPE_STORAGE, TYPE_STREAM):
                raise damaged("directory tree reaches an unused entry", sid=current)
            path = f"{prefix}{entry.name}"
            paths[path] = entry
            stack.append((entry.left, prefix))
            stack.append((entry.right, prefix))
            if entry.kind == TYPE_STORAGE:
                stack.append((entry.child, path + "/"))
        return paths

    # -- public reading API --------------------------------------------------

    def iter_paths(self) -> Iterator[str]:
        """Every storage and stream path, sorted."""

        return iter(sorted(self._paths))

    def stream_paths(self) -> list[str]:
        """Every stream path, sorted."""

        return sorted(p for p, e in self._paths.items() if e.kind == TYPE_STREAM)

    def entry(self, path: str) -> DirectoryEntry | None:
        return self._paths.get(path)

    def has_stream(self, path: str) -> bool:
        entry = self._paths.get(path)
        return entry is not None and entry.kind == TYPE_STREAM

    def read(self, path: str) -> bytes:
        """The bytes of the stream at *path*; a missing stream is damage."""

        entry = self._paths.get(path)
        if entry is None or entry.kind != TYPE_STREAM:
            raise damaged(f"the compound file has no {path!r} stream", stream=path)
        if entry.size == 0:
            return b""
        if entry.size < self.mini_cutoff:
            return self._read_mini(entry.start, entry.size, path)
        return self._read_chain(entry.start, entry.size, path)

    @property
    def root(self) -> DirectoryEntry:
        return self.entries[0]


# -- writing ---------------------------------------------------------------------


@dataclass
class _Node:
    name: str
    kind: int
    data: bytes = b""
    children: dict[str, "_Node"] | None = None
    sid: int = -1
    left: int = NOSTREAM
    right: int = NOSTREAM
    child: int = NOSTREAM
    color: int = COLOR_BLACK
    start: int = 0
    created: int = 0
    modified: int = 0


def _cfb_key(name: str) -> tuple[int, str]:
    # [MS-CFB] 2.6.4: shorter names sort first, equal lengths compare the
    # upper-cased UTF-16 code units.
    return (len(name.encode("utf-16-le")) // 2, name.upper())


def _balanced_tree(nodes: list[_Node]) -> int:
    """Link *nodes* (already sorted) as a red-black tree; return the root sid.

    A middle-split tree keeps every null link at depth H or H+1, so colouring
    the deepest level red (unless that level is full) gives every path the
    same number of black nodes.
    """

    if not nodes:
        return NOSTREAM
    depth: dict[int, int] = {}

    def build(lo: int, hi: int, level: int) -> int:
        if lo > hi:
            return NOSTREAM
        mid = (lo + hi + 1) // 2
        node = nodes[mid]
        depth[node.sid] = level
        node.left = build(lo, mid - 1, level + 1)
        node.right = build(mid + 1, hi, level + 1)
        return node.sid

    root = build(0, len(nodes) - 1, 0)
    deepest = max(depth.values())
    perfect = len(nodes) == (1 << (deepest + 1)) - 1
    for node in nodes:
        node.color = COLOR_RED if (not perfect and depth[node.sid] == deepest) else COLOR_BLACK
    return root


def _encode_name(name: str) -> tuple[bytes, int]:
    encoded = name.encode("utf-16-le")
    if len(encoded) > 62:
        raise write_unsupported("compound file entry names are limited to 31 characters", name=name)
    return encoded.ljust(64, b"\0"), len(encoded) + 2


def build_compound_file(
    streams: Iterable[tuple[str, bytes]],
    *,
    storage_times: Mapping[str, tuple[int, int]] | None = None,
    root_modified: int = 0,
) -> bytes:
    """Write *streams* (``(path, bytes)`` pairs) as a version 3 compound file.

    Storages are created from the path prefixes. ``storage_times`` optionally
    gives ``(created, modified)`` FILETIME values per storage path.
    """

    root = _Node("Root Entry", TYPE_ROOT, children={})
    root.modified = root_modified
    order: list[_Node] = [root]
    times = dict(storage_times or {})
    for path, data in streams:
        parts = [p for p in path.split("/") if p]
        if not parts:
            raise write_unsupported("empty compound file path", path=path)
        parent = root
        prefix = ""
        for part in parts[:-1]:
            prefix = f"{prefix}{part}"
            assert parent.children is not None
            node = parent.children.get(part)
            if node is None:
                node = _Node(part, TYPE_STORAGE, children={})
                node.created, node.modified = times.get(prefix, (0, 0))
                parent.children[part] = node
                order.append(node)
            elif node.kind != TYPE_STORAGE:
                raise write_unsupported("compound file path runs through a stream", path=path)
            parent = node
            prefix += "/"
        assert parent.children is not None
        if parts[-1] in parent.children:
            raise write_unsupported("duplicate compound file path", path=path)
        node = _Node(parts[-1], TYPE_STREAM, data=bytes(data))
        parent.children[parts[-1]] = node
        order.append(node)
    for sid, node in enumerate(order):
        node.sid = sid
    for node in order:
        if node.children is not None:
            siblings = sorted(node.children.values(), key=lambda n: _cfb_key(n.name))
            node.child = _balanced_tree(siblings)
    root.color = COLOR_BLACK

    sector = _V3_SECTOR
    per = sector // 4
    small = [n for n in order if n.kind == TYPE_STREAM and 0 < len(n.data) < _MINI_CUTOFF]
    large = [n for n in order if n.kind == TYPE_STREAM and len(n.data) >= _MINI_CUTOFF]

    mini_chunks: list[bytes] = []
    minifat: list[int] = []
    for node in small:
        count = (len(node.data) + _MINI_SECTOR - 1) // _MINI_SECTOR
        node.start = len(minifat)
        minifat.extend(range(len(minifat) + 1, len(minifat) + count))
        minifat.append(ENDOFCHAIN)
        mini_chunks.append(node.data.ljust(count * _MINI_SECTOR, b"\0"))
    mini_stream = b"".join(mini_chunks)

    sectors: list[bytes] = []
    fat: list[int] = []

    def place(payload: bytes) -> int:
        if not payload:
            return ENDOFCHAIN
        count = (len(payload) + sector - 1) // sector
        first = len(fat)
        fat.extend(range(first + 1, first + count))
        fat.append(ENDOFCHAIN)
        padded = payload.ljust(count * sector, b"\0")
        sectors.extend(padded[i : i + sector] for i in range(0, len(padded), sector))
        return first

    for node in large:
        node.start = place(node.data)
    for node in order:
        if node.kind == TYPE_STREAM and not node.data:
            node.start = ENDOFCHAIN
    root.start = place(mini_stream)
    minifat_bytes = b"".join(struct.pack("<I", v) for v in minifat)
    if minifat_bytes:
        minifat_bytes = minifat_bytes.ljust(
            ((len(minifat_bytes) + sector - 1) // sector) * sector, b"\xff"
        )
    first_minifat = place(minifat_bytes)
    minifat_count = len(minifat_bytes) // sector

    dirents: list[bytes] = []
    for node in order:
        raw_name, name_len = _encode_name(node.name)
        if node.kind == TYPE_ROOT:
            size = len(mini_stream)
        elif node.kind == TYPE_STREAM:
            size = len(node.data)
        else:
            size = 0
        dirents.append(
            _DIRENT.pack(
                raw_name,
                name_len,
                node.kind,
                node.color,
                node.left,
                node.right,
                node.child,
                b"\0" * 16,
                0,
                node.created,
                node.modified,
                node.start if node.kind != TYPE_STORAGE else 0,
                size,
            )
        )
    empty = _DIRENT.pack(b"\0" * 64, 0, TYPE_EMPTY, 0, NOSTREAM, NOSTREAM, NOSTREAM, b"\0" * 16, 0, 0, 0, 0, 0)
    per_dir_sector = sector // _DIRENT_SIZE
    while len(dirents) % per_dir_sector:
        dirents.append(empty)
    first_dir = place(b"".join(dirents))

    # FAT and DIFAT sectors describe every sector, themselves included.
    used = len(sectors)
    fat_count = 1
    difat_count = 0
    while True:
        difat_count = max(0, (fat_count - _DIFAT_IN_HEADER + per - 2) // (per - 1))
        needed = (used + fat_count + difat_count + per - 1) // per
        if needed <= fat_count:
            break
        fat_count = needed
    fat_sectors = list(range(used, used + fat_count))
    difat_sectors = list(range(used + fat_count, used + fat_count + difat_count))
    fat.extend([FATSECT] * fat_count)
    fat.extend([DIFSECT] * difat_count)
    fat.extend([FREESECT] * (fat_count * per - len(fat)))
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    sectors.extend(fat_bytes[i : i + sector] for i in range(0, len(fat_bytes), sector))
    overflow = fat_sectors[_DIFAT_IN_HEADER:]
    for index, difat_sector in enumerate(difat_sectors):
        chunk = overflow[index * (per - 1) : (index + 1) * (per - 1)]
        chunk += [FREESECT] * (per - 1 - len(chunk))
        following = difat_sectors[index + 1] if index + 1 < len(difat_sectors) else ENDOFCHAIN
        sectors.append(struct.pack(f"<{per}I", *chunk, following))

    header_difat = fat_sectors[:_DIFAT_IN_HEADER]
    header_difat += [FREESECT] * (_DIFAT_IN_HEADER - len(header_difat))
    header = _HEADER.pack(
        SIGNATURE,
        b"\0" * 16,
        0x003E,
        3,
        0xFFFE,
        9,
        6,
        b"\0" * 6,
        0,
        fat_count,
        first_dir,
        0,
        _MINI_CUTOFF,
        first_minifat if minifat_count else ENDOFCHAIN,
        minifat_count,
        difat_sectors[0] if difat_sectors else ENDOFCHAIN,
        difat_count,
    ) + struct.pack(f"<{_DIFAT_IN_HEADER}I", *header_difat)
    return header + b"".join(sectors)


def storage_times(compound: CompoundFile) -> dict[str, tuple[int, int]]:
    """``(created, modified)`` FILETIME values of every storage in *compound*."""

    return {
        path: (entry.created, entry.modified)
        for path in compound.iter_paths()
        if (entry := compound.entry(path)) is not None and entry.kind == TYPE_STORAGE
    }


def read_all_streams(compound: CompoundFile) -> list[tuple[str, bytes]]:
    """Every stream of *compound* as ``(path, bytes)`` pairs, sorted by path."""

    return [(path, compound.read(path)) for path in compound.stream_paths()]


__all__: Sequence[str] = (
    "CompoundFile",
    "DirectoryEntry",
    "SIGNATURE",
    "build_compound_file",
    "read_all_streams",
    "storage_times",
)
