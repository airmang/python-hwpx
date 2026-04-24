# SPDX-License-Identifier: Apache-2.0
"""Utilities for reading and writing HWPX OPC packages."""

from __future__ import annotations

import logging
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable, Iterator, Mapping, MutableMapping
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from .relationships import (
    MAIN_ROOTFILE_MEDIA_TYPE,
    OPF_NS,
    is_header_part_name,
    is_section_part_name,
    normalize_part_name,
    parse_container_rootfiles,
    parse_manifest_relationships,
)
from .xml_utils import (
    extract_xml_declaration,
    iter_declared_namespaces,
    parse_xml,
    serialize_xml,
)

__all__ = ["HwpxPackage", "HwpxPackageError", "HwpxStructureError", "RootFile", "VersionInfo"]

logger = logging.getLogger(__name__)


class HwpxPackageError(Exception):
    """Base error raised for issues related to :class:`HwpxPackage`."""


class HwpxStructureError(HwpxPackageError):
    """Raised when the underlying HWPX package violates the required structure."""


@dataclass(frozen=True)
class RootFile:
    """Represents a ``rootfile`` entry from ``META-INF/container.xml``."""

    full_path: str
    media_type: str | None = None

    def ensure_exists(self, files: Mapping[str, bytes]) -> None:
        """Ensure that the referenced root file actually exists in ``files``."""

        if self.full_path not in files:
            raise HwpxStructureError(
                f"Root content '{self.full_path}' declared in container.xml is missing."
            )


class VersionInfo:
    """Model for the ``version.xml`` document."""

    def __init__(
        self,
        element: etree._Element,
        namespaces: Mapping[str, str],
        xml_declaration: bytes | None,
    ) -> None:
        self._element = element
        self._namespaces = dict(namespaces)
        self._xml_declaration = xml_declaration
        self._dirty = False

    @classmethod
    def from_bytes(cls, data: bytes) -> VersionInfo:
        element = parse_xml(data)
        namespaces = cls._collect_namespaces(data)
        declaration = cls._extract_declaration(data)
        return cls(element, namespaces, declaration)

    @staticmethod
    def _collect_namespaces(data: bytes) -> Mapping[str, str]:
        return iter_declared_namespaces(data)

    @staticmethod
    def _extract_declaration(data: bytes) -> bytes | None:
        return extract_xml_declaration(data)

    @property
    def attributes(self) -> Mapping[str, str]:
        return dict(self._element.attrib)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._element.attrib.get(key, default)

    def set(self, key: str, value: str) -> None:
        self._element.attrib[key] = value
        self._dirty = True

    @property
    def tag(self) -> str:
        return self._element.tag

    def to_bytes(self) -> bytes:
        xml_body = serialize_xml(self._element, xml_declaration=False)
        if self._xml_declaration:
            return self._xml_declaration + xml_body
        return xml_body

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False


class HwpxPackage:
    """Represents an HWPX package backed by an Open Packaging Convention container."""

    CONTAINER_PATH = "META-INF/container.xml"
    VERSION_PATH = "version.xml"
    MIMETYPE_PATH = "mimetype"
    DEFAULT_MIMETYPE = "application/hwp+zip"
    MANIFEST_PATH = "Contents/content.hpf"
    HEADER_PATH = "Contents/header.xml"

    def __init__(
        self,
        files: MutableMapping[str, bytes],
        rootfiles: Iterable[RootFile],
        version_info: VersionInfo,
        mimetype: str,
    ) -> None:
        self._files = files
        self._rootfiles = list(rootfiles)
        self._version = version_info
        self._mimetype = mimetype
        self._manifest_tree: etree._Element | None = None
        self._spine_cache: list[str] | None = None
        self._section_paths_cache: list[str] | None = None
        self._header_paths_cache: list[str] | None = None
        self._master_page_paths_cache: list[str] | None = None
        self._history_paths_cache: list[str] | None = None
        self._version_path_cache: str | None = None
        self._version_path_cache_resolved = False
        self._validate_structure()

    @classmethod
    def open(cls, pkg_file: str | Path | bytes | bytearray | BinaryIO) -> HwpxPackage:
        if isinstance(pkg_file, (bytes, bytearray)):
            stream: str | Path | BinaryIO = io.BytesIO(pkg_file)
        else:
            stream = pkg_file

        with ZipFile(stream, "r") as zf:
            files = {info.filename: zf.read(info.filename) for info in zf.infolist()}
        logger.debug("HWPX 패키지 파일 목록 %d개를 로드했습니다.", len(files))
        if cls.MIMETYPE_PATH not in files:
            raise HwpxStructureError("HWPX package is missing the mandatory 'mimetype' file.")
        mimetype = files[cls.MIMETYPE_PATH].decode("utf-8")
        rootfiles = cls._parse_container(files.get(cls.CONTAINER_PATH))
        version_info = cls._parse_version(files.get(cls.VERSION_PATH))
        package = cls(files, rootfiles, version_info, mimetype)
        return package

    @staticmethod
    def _parse_container(data: bytes | None) -> list[RootFile]:
        if data is None:
            raise HwpxStructureError(
                "HWPX package is missing 'META-INF/container.xml'."
            )
        try:
            root = parse_xml(data)
        except Exception:
            logger.exception("container.xml 파싱에 실패했습니다.")
            raise
        rootfiles = [
            RootFile(ref.full_path, ref.media_type)
            for ref in parse_container_rootfiles(root)
        ]
        if not rootfiles:
            raise HwpxStructureError("container.xml does not declare any rootfiles.")
        return rootfiles

    @staticmethod
    def _parse_version(data: bytes | None) -> VersionInfo:
        if data is None:
            raise HwpxStructureError("HWPX package is missing 'version.xml'.")
        return VersionInfo.from_bytes(data)

    def _validate_structure(self) -> None:
        for rootfile in self._rootfiles:
            rootfile.ensure_exists(self._files)

    @property
    def mimetype(self) -> str:
        return self._mimetype

    @property
    def rootfiles(self) -> tuple[RootFile, ...]:
        return tuple(self._rootfiles)

    def iter_rootfiles(self) -> Iterator[RootFile]:
        yield from self._rootfiles

    @property
    def main_content(self) -> RootFile:
        for rootfile in self._rootfiles:
            if rootfile.media_type == MAIN_ROOTFILE_MEDIA_TYPE:
                return rootfile
        selected = self._rootfiles[0]
        logger.warning(
            "표준 media_type 메인 rootfile이 없어 첫 항목으로 대체합니다: path=%s",
            selected.full_path,
        )
        return selected

    @property
    def version_info(self) -> VersionInfo:
        return self._version

    def read(self, path: str) -> bytes:
        norm_path = self._normalize_path(path)
        try:
            return self._files[norm_path]
        except KeyError as exc:
            logger.warning("파트 누락: path=%s", norm_path)
            raise HwpxPackageError(f"File '{norm_path}' is not present in the package.") from exc

    def write(self, path: str, data: bytes | str) -> None:
        norm_path = self._normalize_path(path)
        if isinstance(data, str):
            data = data.encode("utf-8")
        pending_rootfiles: list[RootFile] | None = None
        pending_version: VersionInfo | None = None
        if norm_path == self.MIMETYPE_PATH:
            mimetype = data.decode("utf-8")
        elif norm_path == self.CONTAINER_PATH:
            pending_rootfiles = self._parse_container(data)
        elif norm_path == self.VERSION_PATH:
            pending_version = self._parse_version(data)
        self._files[norm_path] = data
        if norm_path == self.MIMETYPE_PATH:
            self._mimetype = mimetype
        elif norm_path == self.CONTAINER_PATH:
            assert pending_rootfiles is not None
            self._rootfiles = pending_rootfiles
        elif norm_path == self.VERSION_PATH:
            assert pending_version is not None
            self._version = pending_version
        self._invalidate_caches(norm_path)
        self._validate_structure()

    def delete(self, path: str) -> None:
        norm_path = self._normalize_path(path)
        if norm_path not in self._files:
            raise HwpxPackageError(f"File '{norm_path}' is not present in the package.")
        if norm_path in {self.MIMETYPE_PATH, self.CONTAINER_PATH, self.VERSION_PATH}:
            raise HwpxStructureError(
                "Cannot remove mandatory files ('mimetype', 'container.xml', 'version.xml')."
            )
        del self._files[norm_path]
        self._invalidate_caches(norm_path)
        self._validate_structure()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return normalize_part_name(path)

    def files(self) -> list[str]:
        return sorted(self._files)

    def part_names(self) -> list[str]:
        return self.files()

    def has_part(self, part_name: str) -> bool:
        return self._normalize_path(part_name) in self._files

    def get_part(self, part_name: str) -> bytes:
        return self.read(part_name)

    def set_part(self, part_name: str, payload: bytes | str | etree._Element) -> None:
        if isinstance(payload, etree._Element):
            data = serialize_xml(payload, xml_declaration=True)
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        elif isinstance(payload, bytes):
            data = payload
        else:
            raise TypeError(f"unsupported part payload type: {type(payload)!r}")
        self.write(part_name, data)

    def get_xml(self, part_name: str) -> etree._Element:
        return parse_xml(self.read(part_name))

    def set_xml(self, part_name: str, element: etree._Element) -> None:
        self.set_part(part_name, element)

    def get_text(self, part_name: str, encoding: str = "utf-8") -> str:
        return self.read(part_name).decode(encoding)

    def manifest_tree(self) -> etree._Element:
        if self._manifest_tree is None:
            self._manifest_tree = self.get_xml(self.main_content.full_path)
        return self._manifest_tree

    def _manifest_items(self) -> list[etree._Element]:
        manifest = self.manifest_tree()
        return list(manifest.findall("./opf:manifest/opf:item", OPF_NS))

    @staticmethod
    def _normalized_manifest_value(element: etree._Element) -> str:
        values = [
            element.attrib.get("id", ""),
            element.attrib.get("href", ""),
            element.attrib.get("media-type", ""),
            element.attrib.get("properties", ""),
        ]
        return " ".join(part.lower() for part in values if part)

    @classmethod
    def _manifest_matches(cls, element: etree._Element, *candidates: str) -> bool:
        normalized = cls._normalized_manifest_value(element)
        return any(candidate in normalized for candidate in candidates if candidate)

    def _resolve_spine_paths(self) -> list[str]:
        if self._spine_cache is None:
            relationships = parse_manifest_relationships(
                self.manifest_tree(),
                self.main_content.full_path,
                known_parts=self._files.keys(),
            )
            self._spine_cache = list(relationships.spine_paths)
        return self._spine_cache

    def section_paths(self) -> list[str]:
        if self._section_paths_cache is None:
            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and is_section_part_name(path)
            ]
            if not paths:
                logger.warning("manifest spine에서 section 경로를 찾지 못해 파일명 기반 fallback을 사용합니다.")
                paths = [
                    name
                    for name in self._files.keys()
                    if is_section_part_name(name)
                ]
            self._section_paths_cache = paths
        return list(self._section_paths_cache)

    def header_paths(self) -> list[str]:
        if self._header_paths_cache is None:
            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and is_header_part_name(path)
            ]
            if not paths and self.has_part(self.HEADER_PATH):
                logger.warning(
                    "manifest spine에서 header 경로를 찾지 못해 기본 header 경로 fallback을 사용합니다: %s",
                    self.HEADER_PATH,
                )
                paths = [self.HEADER_PATH]
            self._header_paths_cache = paths
        return list(self._header_paths_cache)

    def master_page_paths(self) -> list[str]:
        if self._master_page_paths_cache is None:
            paths = list(
                parse_manifest_relationships(
                    self.manifest_tree(),
                    self.main_content.full_path,
                    known_parts=self._files.keys(),
                ).master_page_paths
            )
            if not paths:
                logger.warning("manifest에서 masterPage를 찾지 못해 파일명 탐색 fallback을 사용합니다.")
                paths = [
                    name
                    for name in self._files.keys()
                    if "master" in PurePosixPath(name).name.lower()
                    and "page" in PurePosixPath(name).name.lower()
                ]
            self._master_page_paths_cache = paths
        return list(self._master_page_paths_cache)

    def history_paths(self) -> list[str]:
        if self._history_paths_cache is None:
            paths = list(
                parse_manifest_relationships(
                    self.manifest_tree(),
                    self.main_content.full_path,
                    known_parts=self._files.keys(),
                ).history_paths
            )
            if not paths:
                logger.warning("manifest에서 history를 찾지 못해 파일명 탐색 fallback을 사용합니다.")
                paths = [
                    name
                    for name in self._files.keys()
                    if "history" in PurePosixPath(name).name.lower()
                ]
            self._history_paths_cache = paths
        return list(self._history_paths_cache)

    def version_path(self) -> str | None:
        if not self._version_path_cache_resolved:
            path = parse_manifest_relationships(
                self.manifest_tree(),
                self.main_content.full_path,
                known_parts=self._files.keys(),
            ).version_path
            if path is None and self.has_part(self.VERSION_PATH):
                logger.warning(
                    "manifest에서 version 파트를 찾지 못해 기본 경로 fallback을 사용합니다: %s",
                    self.VERSION_PATH,
                )
                path = self.VERSION_PATH
            self._version_path_cache = path
            self._version_path_cache_resolved = True
        return self._version_path_cache

    # ------------------------------------------------------------------
    # Manifest item helpers (for BinData / images)
    # ------------------------------------------------------------------

    def _manifest_element(self) -> etree._Element | None:
        """Return the ``<opf:manifest>`` element."""
        manifest = self.manifest_tree()
        return manifest.find("opf:manifest", OPF_NS)

    def add_manifest_item(
        self,
        item_id: str,
        href: str,
        media_type: str,
    ) -> None:
        """Add an ``<opf:item>`` to the manifest if *item_id* is not present."""
        manifest_el = self._manifest_element()
        if manifest_el is None:
            raise HwpxStructureError("Manifest does not contain an <opf:manifest> element.")

        for existing in manifest_el.findall("opf:item", OPF_NS):
            if existing.get("id") == item_id:
                return  # already present

        new_item = manifest_el.makeelement(
            f"{{{OPF_NS['opf']}}}item",
            {"id": item_id, "href": href, "media-type": media_type},
        )
        manifest_el.append(new_item)
        self._persist_manifest()

    def remove_manifest_item(self, item_id: str) -> bool:
        """Remove an ``<opf:item>`` by id.  Returns ``True`` on success."""
        manifest_el = self._manifest_element()
        if manifest_el is None:
            return False

        for existing in manifest_el.findall("opf:item", OPF_NS):
            if existing.get("id") == item_id:
                manifest_el.remove(existing)
                self._persist_manifest()
                return True
        return False

    def _persist_manifest(self) -> None:
        """Write the in-memory manifest tree back to the package."""
        tree = self._manifest_tree
        if tree is not None:
            self.set_part(self.main_content.full_path, tree)

    def _invalidate_caches(self, changed_path: str) -> None:
        if changed_path in {self.CONTAINER_PATH, self.main_content.full_path}:
            self._manifest_tree = None
        self._spine_cache = None
        self._section_paths_cache = None
        self._header_paths_cache = None
        self._master_page_paths_cache = None
        self._history_paths_cache = None
        self._version_path_cache = None
        self._version_path_cache_resolved = False

    def save(
        self,
        pkg_file: str | Path | BinaryIO | None = None,
        updates: Mapping[str, bytes | str | etree._Element] | None = None,
    ) -> str | Path | BinaryIO | bytes | None:
        if updates:
            for part_name, payload in updates.items():
                self.set_part(part_name, payload)

        destination = pkg_file
        if destination is None:
            buffer = io.BytesIO()
            self._save_to_zip(buffer)
            return buffer.getvalue()

        self._save_to_zip(destination)
        return destination

    def _save_to_zip(self, pkg_file: str | Path | BinaryIO) -> None:
        self._files[self.MIMETYPE_PATH] = self._mimetype.encode("utf-8")
        if self._version.dirty:
            self._files[self.VERSION_PATH] = self._version.to_bytes()
            self._version.mark_clean()
        self._validate_structure()

        if isinstance(pkg_file, (str, Path)):
            # Atomic write: write to a temp file first, verify, then rename.
            target = Path(pkg_file)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), suffix=".hwpx.tmp"
            )
            try:
                with os.fdopen(fd, "wb") as tmp_fh:
                    with ZipFile(tmp_fh, "w") as zf:
                        self._write_archive(zf)
                # Verify archive integrity before replacing the original.
                with ZipFile(tmp_path, "r") as zf_check:
                    bad = zf_check.testzip()
                    if bad is not None:
                        raise HwpxPackageError(
                            f"ZIP integrity check failed for entry '{bad}'"
                        )
                os.replace(tmp_path, str(target))
            except BaseException:
                # Clean up the temp file on any error.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        else:
            # Stream target: write to a BytesIO first, verify, then copy.
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as zf:
                self._write_archive(zf)
            buffer.seek(0)
            with ZipFile(buffer, "r") as zf_check:
                bad = zf_check.testzip()
                if bad is not None:
                    raise HwpxPackageError(
                        f"ZIP integrity check failed for entry '{bad}'"
                    )
            buffer.seek(0)
            pkg_file.write(buffer.read())

    def _write_archive(self, zf: ZipFile) -> None:
        self._write_mimetype(zf)
        for name in sorted(self._files):
            if name == self.MIMETYPE_PATH:
                continue
            self._write_zip_entry(zf, name, self._files[name], ZIP_DEFLATED)

    @staticmethod
    def _write_zip_entry(zf: ZipFile, path: str, payload: bytes, compress_type: int) -> None:
        info = ZipInfo(path)
        info.compress_type = compress_type
        zf.writestr(info, payload)

    def _write_mimetype(self, zf: ZipFile) -> None:
        self._write_zip_entry(
            zf,
            self.MIMETYPE_PATH,
            self._files[self.MIMETYPE_PATH],
            ZIP_STORED,
        )
