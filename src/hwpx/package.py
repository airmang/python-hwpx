"""Utilities for working with the container format used by HWPX files."""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, Mapping, MutableMapping
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

_OPF_NS = "http://www.idpf.org/2007/opf/"


def _ensure_bytes(value: bytes | str | ET.Element) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, ET.Element):
        return ET.tostring(value, encoding="utf-8", xml_declaration=True)
    raise TypeError(f"unsupported part payload type: {type(value)!r}")


class HwpxPackage:
    """Represents the OPC-style package that stores HWPX parts."""

    MANIFEST_PATH = "Contents/content.hpf"
    HEADER_PATH = "Contents/header.xml"

    def __init__(
        self,
        parts: MutableMapping[str, bytes],
        source_path: Path | None = None,
    ):
        self._parts: MutableMapping[str, bytes] = dict(parts)
        self._source_path = source_path
        self._manifest_tree: ET.Element | None = None
        self._spine_cache: list[str] | None = None
        self._section_paths_cache: list[str] | None = None
        self._header_paths_cache: list[str] | None = None

    # -- construction ----------------------------------------------------
    @classmethod
    def open(cls, source: str | Path | bytes | BinaryIO) -> "HwpxPackage":
        if isinstance(source, (str, Path)):
            path = Path(source)
            with ZipFile(path) as archive:
                parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
            return cls(parts, source_path=path)

        if isinstance(source, (bytes, bytearray)):
            buffer = io.BytesIO(source)
            with ZipFile(buffer) as archive:
                parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
            return cls(parts)

        if hasattr(source, "read"):
            data = source.read()
            buffer = io.BytesIO(data)
            with ZipFile(buffer) as archive:
                parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
            package = cls(parts)
            package._source_path = None
            return package

        raise TypeError("unsupported source type for HwpxPackage")

    # -- accessors -------------------------------------------------------
    def part_names(self) -> Iterable[str]:
        return list(self._parts.keys())

    def has_part(self, part_name: str) -> bool:
        return part_name in self._parts

    def get_part(self, part_name: str) -> bytes:
        try:
            return self._parts[part_name]
        except KeyError as exc:
            raise KeyError(f"package does not contain part '{part_name}'") from exc

    def set_part(self, part_name: str, payload: bytes | str | ET.Element) -> None:
        self._parts[part_name] = _ensure_bytes(payload)
        if part_name == self.MANIFEST_PATH:
            self._manifest_tree = None
            self._spine_cache = None
            self._section_paths_cache = None
            self._header_paths_cache = None

    def get_xml(self, part_name: str) -> ET.Element:
        return ET.fromstring(self.get_part(part_name))

    def set_xml(self, part_name: str, element: ET.Element) -> None:
        self.set_part(part_name, element)

    def get_text(self, part_name: str, encoding: str = "utf-8") -> str:
        return self.get_part(part_name).decode(encoding)

    # -- manifest helpers ------------------------------------------------
    def manifest_tree(self) -> ET.Element:
        if self._manifest_tree is None:
            self._manifest_tree = self.get_xml(self.MANIFEST_PATH)
        return self._manifest_tree

    def _resolve_spine_paths(self) -> list[str]:
        if self._spine_cache is None:
            manifest = self.manifest_tree()
            ns = {"opf": _OPF_NS}
            manifest_items: Dict[str, str] = {}
            for item in manifest.findall("./opf:manifest/opf:item", ns):
                item_id = item.attrib.get("id")
                href = item.attrib.get("href", "")
                if item_id and href:
                    manifest_items[item_id] = href
            spine_paths: list[str] = []
            for itemref in manifest.findall("./opf:spine/opf:itemref", ns):
                idref = itemref.attrib.get("idref")
                if not idref:
                    continue
                href = manifest_items.get(idref)
                if href:
                    spine_paths.append(href)
            self._spine_cache = spine_paths
        return self._spine_cache

    def section_paths(self) -> list[str]:
        if self._section_paths_cache is None:
            from pathlib import PurePosixPath

            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and PurePosixPath(path).name.startswith("section")
            ]
            if not paths:
                # Fallback: include known section files if they exist.
                paths = [
                    name
                    for name in self._parts.keys()
                    if PurePosixPath(name).name.startswith("section")
                ]
            self._section_paths_cache = paths
        return list(self._section_paths_cache)

    def header_paths(self) -> list[str]:
        if self._header_paths_cache is None:
            from pathlib import PurePosixPath

            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and PurePosixPath(path).name.startswith("header")
            ]
            if not paths and self.has_part(self.HEADER_PATH):
                paths = [self.HEADER_PATH]
            self._header_paths_cache = paths
        return list(self._header_paths_cache)

    # -- saving ----------------------------------------------------------
    def save(
        self,
        path_or_stream: str | Path | BinaryIO | None = None,
        updates: Mapping[str, bytes | str | ET.Element] | None = None,
    ) -> str | Path | BinaryIO | bytes | None:
        if updates:
            for part_name, payload in updates.items():
                self.set_part(part_name, payload)

        destination = path_or_stream or self._source_path

        if destination is None:
            buffer = io.BytesIO()
            self._write_to_stream(buffer)
            return buffer.getvalue()

        if isinstance(destination, (str, Path)):
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(dest_path, "w", compression=ZIP_DEFLATED) as archive:
                self._write_archive(archive)
            self._source_path = dest_path
            return dest_path

        stream = destination
        if hasattr(stream, "seek"):
            stream.seek(0)
        if hasattr(stream, "truncate"):
            stream.truncate(0)
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            self._write_archive(archive)
        if hasattr(stream, "seek"):
            stream.seek(0)
        return stream

    # -- internals -------------------------------------------------------
    def _write_to_stream(self, stream: BinaryIO) -> None:
        with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
            self._write_archive(archive)
        stream.seek(0)

    def _write_archive(self, archive: ZipFile) -> None:
        for part_name in sorted(self._parts.keys()):
            archive.writestr(part_name, self._parts[part_name])
