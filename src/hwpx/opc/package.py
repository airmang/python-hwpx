# SPDX-License-Identifier: Apache-2.0
"""Utilities for reading and writing HWPX OPC packages."""

from __future__ import annotations

import logging
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable, Iterator, Mapping, MutableMapping, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from ..oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES
from .relationships import (
    MAIN_ROOTFILE_MEDIA_TYPE,
    OPF_NS,
    is_header_part_name,
    is_section_part_name,
    normalize_part_name,
    parse_container_rootfiles,
    parse_manifest_relationships,
)
from .security import guard_zip_file
from .xml_utils import (
    extract_xml_declaration,
    iter_declared_namespaces,
    parse_xml,
    serialize_xml,
)

__all__ = ["HwpxPackage", "HwpxPackageError", "HwpxStructureError", "RootFile", "VersionInfo"]

logger = logging.getLogger(__name__)
_UNCHECKED_SAVE_TOKEN = object()
_LAYOUT_CACHE_ELEMENT_NAMES = {"linesegarray"}


class _UncheckedSaveBuffer(io.BytesIO):
    """Internal buffer marker for diagnostic snapshots that skip open-safety."""


def _is_integer_literal(value: str | None) -> bool:
    if value is None:
        return False
    try:
        int(value.strip())
    except (TypeError, ValueError):
        return False
    return True


class HwpxPackageError(Exception):
    """Base error raised for issues related to :class:`HwpxPackage`."""


class HwpxStructureError(HwpxPackageError):
    """Raised when the underlying HWPX package violates the required structure."""


def _summarize_validation_issues(issues: Sequence[object], *, limit: int = 5) -> str:
    selected = [str(issue) for issue in issues[:limit]]
    remaining = len(issues) - len(selected)
    summary = "; ".join(selected)
    if remaining > 0:
        summary += f" ... and {remaining} more"
    return summary


def _require_unchecked_save_token(token: object | None) -> None:
    if token is not _UNCHECKED_SAVE_TOKEN:
        raise HwpxPackageError(
            "unchecked HWPX save is an internal diagnostic path and requires "
            "the package-private unchecked save token"
        )


def _require_unchecked_save_buffer(destination: object) -> None:
    if not isinstance(destination, _UncheckedSaveBuffer):
        raise HwpxPackageError(
            "unchecked HWPX save is diagnostic-only and cannot write to "
            "caller-provided file paths or streams"
        )


def _capture_stream_checkpoint(stream: BinaryIO) -> tuple[int, bytes] | None:
    try:
        position = stream.tell()
    except (AttributeError, OSError):
        return None
    try:
        tail = stream.read()
    except (AttributeError, OSError):
        try:
            end_position = stream.seek(0, os.SEEK_END)
        except (AttributeError, OSError):
            return None
        try:
            stream.seek(position)
        except (AttributeError, OSError):
            return None
        if end_position == position:
            return position, b""
        return None
    try:
        stream.seek(position)
    except (AttributeError, OSError):
        return None
    return position, tail


def _rollback_stream(stream: BinaryIO, checkpoint: tuple[int, bytes] | None) -> None:
    if checkpoint is None:
        return
    position, tail = checkpoint
    try:
        stream.seek(position)
        if tail:
            stream.write(tail)
            stream.truncate(position + len(tail))
        else:
            stream.truncate(position)
        stream.seek(position)
    except (AttributeError, OSError):
        return


def _write_stream_or_rollback(stream: BinaryIO, data: bytes) -> None:
    checkpoint = _capture_stream_checkpoint(stream)
    if checkpoint is None:
        raise HwpxPackageError(
            "HWPX package stream save requires a checkpointable stream; "
            "use save(path) with a filesystem path for non-seekable outputs"
        )
    try:
        written = stream.write(data)
        if written is not None and written != len(data):
            raise HwpxPackageError(
                "short write while saving HWPX package stream: "
                f"wrote {written} of {len(data)} bytes"
            )
    except BaseException:
        _rollback_stream(stream, checkpoint)
        raise


def _local_name(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    try:
        return etree.QName(element).localname
    except ValueError:
        if "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag


def _paragraph_plain_text_length(paragraph: etree._Element) -> int | None:
    """Plain text length of a simple paragraph, or ``None`` when unjudgeable.

    Mirrors the oxml-side stale detector: only paragraphs made purely of runs
    with text/tab-like children can be judged at the byte boundary; anything
    else (controls, tables, fields) returns ``None`` so its cache is kept.
    """
    total = 0
    for child in paragraph:
        child_name = _local_name(child).lower()
        if child_name in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        if child_name != "run":
            return None
        for run_child in child:
            run_child_name = _local_name(run_child).lower()
            if run_child_name == "t":
                total += len("".join(run_child.itertext()))
            elif run_child_name in {"tab", "linebreak", "hyphen", "nbspace"}:
                total += 1
            else:
                return None
    return total


def _paragraph_layout_cache_is_stale(paragraph: etree._Element) -> bool:
    text_length = _paragraph_plain_text_length(paragraph)
    if text_length is None:
        return False
    for child in paragraph:
        if _local_name(child).lower() not in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        for line_seg in child:
            if _local_name(line_seg).lower() != "lineseg":
                continue
            textpos = line_seg.get("textpos")
            if textpos is None:
                continue
            try:
                if int(textpos) > text_length:
                    return True
            except ValueError:
                return True
    return False


def _strip_section_layout_caches(payload: bytes) -> bytes:
    """Drop only *stale* paragraph layout caches from a section payload.

    Valid caches are the authored layout of untouched paragraphs; removing
    them forces the editor to re-lay-out entire multi-page documents, which
    shifted page counts and stacked glyphs in the wild form-fill differential
    (specs/031 P0 receipt). The mutating APIs upstream clear the caches of
    exactly the paragraphs they touch, so this byte-boundary sweep only
    guards against writers that left a provably stale cache behind.
    """
    root = parse_xml(payload)
    removed = False
    for parent in root.iter():
        if _local_name(parent).lower() != "p":
            continue
        if not _paragraph_layout_cache_is_stale(parent):
            continue
        for child in list(parent):
            if _local_name(child).lower() in _LAYOUT_CACHE_ELEMENT_NAMES:
                parent.remove(child)
                removed = True
    return _serialize_hwpml_root(root) if removed else payload


def _serialize_hwpml_root(root: etree._Element) -> bytes:
    local_name = _local_name(root)
    if local_name not in {"sec", "head"}:
        return serialize_xml(root, xml_declaration=True)

    wrapped = etree.Element(root.tag, nsmap=HWPML_COMPAT_ROOT_NAMESPACES)
    wrapped.attrib.update(root.attrib)
    wrapped.text = root.text
    wrapped.tail = root.tail
    for child in root:
        wrapped.append(child)
    return etree.tostring(
        wrapped,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def _normalize_hwpml_root_payload(path: str, payload: bytes) -> bytes:
    if not (is_section_part_name(path) or is_header_part_name(path) or path == HwpxPackage.HEADER_PATH):
        return payload
    root = parse_xml(payload)
    if _local_name(root) not in {"sec", "head"}:
        return payload
    return _serialize_hwpml_root(root)


def _sanitize_part_for_write(path: str, payload: bytes) -> bytes:
    if is_section_part_name(path):
        payload = _strip_section_layout_caches(payload)
    return _normalize_hwpml_root_payload(path, payload)


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

    @classmethod
    def default(cls) -> VersionInfo:
        return cls.from_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
            b'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0"/>'
        )

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
        *,
        zip_infos: Mapping[str, ZipInfo] | None = None,
        zip_order: Sequence[str] | None = None,
    ) -> None:
        self._files = files
        # Open-time baseline for the Safe Write Contract: preservation must be
        # measured against what was actually opened, or a low-level set_part
        # applied before save() would count as "already there" and slip past a
        # mode="patch" grade unnoticed. Values are immutable bytes, so this
        # holds references, not copies.
        self._opened_members: dict[str, bytes] = dict(files)
        self._rootfiles = list(rootfiles)
        self._version = version_info
        self._mimetype = mimetype
        self._zip_infos = dict(zip_infos or {})
        self._opened_zip_infos: dict[str, ZipInfo] = dict(zip_infos or {})
        self._zip_order = list(zip_order or files.keys())
        self._manifest_tree: etree._Element | None = None
        self._spine_cache: list[str] | None = None
        self._section_paths_cache: list[str] | None = None
        self._header_paths_cache: list[str] | None = None
        self._master_page_paths_cache: list[str] | None = None
        self._history_paths_cache: list[str] | None = None
        self._version_path_cache: str | None = None
        self._version_path_cache_resolved = False
        self._archive_write_depth = 0
        self._validate_structure()

    @classmethod
    def open(cls, pkg_file: str | Path | bytes | bytearray | BinaryIO) -> HwpxPackage:
        if isinstance(pkg_file, (bytes, bytearray)):
            stream: str | Path | BinaryIO = io.BytesIO(pkg_file)
        else:
            stream = pkg_file

        with ZipFile(stream, "r") as zf:
            guard_zip_file(zf)
            infos = [info for info in zf.infolist() if not info.is_dir()]
            files = {info.filename: zf.read(info.filename) for info in infos}
            zip_infos = {info.filename: info for info in infos}
            zip_order = [info.filename for info in infos]
        logger.debug("HWPX 패키지 파일 목록 %d개를 로드했습니다.", len(files))
        if cls.MIMETYPE_PATH not in files:
            raise HwpxStructureError("HWPX package is missing the mandatory 'mimetype' file.")
        mimetype = files[cls.MIMETYPE_PATH].decode("utf-8")
        rootfiles = cls._parse_container(files.get(cls.CONTAINER_PATH))
        version_info = cls._parse_version(files.get(cls.VERSION_PATH))
        package = cls(
            files,
            rootfiles,
            version_info,
            mimetype,
            zip_infos=zip_infos,
            zip_order=zip_order,
        )
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
            logger.warning("HWPX package is missing optional 'version.xml'; using defaults.")
            return VersionInfo.default()
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
        data = _sanitize_part_for_write(norm_path, data)
        pending_rootfiles: list[RootFile] | None = None
        pending_version: VersionInfo | None = None
        if norm_path == self.MIMETYPE_PATH:
            mimetype = data.decode("utf-8")
        elif norm_path == self.CONTAINER_PATH:
            pending_rootfiles = self._parse_container(data)
        elif norm_path == self.VERSION_PATH:
            pending_version = self._parse_version(data)
        self._files[norm_path] = data
        if norm_path not in self._zip_order:
            self._zip_order.append(norm_path)
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
        self._zip_infos.pop(norm_path, None)
        self._zip_order = [name for name in self._zip_order if name != norm_path]
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
        *,
        extra_attrs: dict[str, str] | None = None,
    ) -> None:
        """Add an ``<opf:item>`` to the manifest if *item_id* is not present.

        ``extra_attrs`` carries item-specific manifest attributes — notably
        ``isEmbeded="1"`` for embedded BinData images (OWPML's single-d spelling),
        which real Hancom requires to render an embedded picture.
        """
        manifest_el = self._manifest_element()
        if manifest_el is None:
            raise HwpxStructureError("Manifest does not contain an <opf:manifest> element.")

        for existing in manifest_el.findall("opf:item", OPF_NS):
            if existing.get("id") == item_id:
                return  # already present

        attrs = {"id": item_id, "href": href, "media-type": media_type}
        if extra_attrs:
            attrs.update(extra_attrs)
        new_item = manifest_el.makeelement(f"{{{OPF_NS['opf']}}}item", attrs)
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

    def _iter_header_part_paths_for_safety_normalization(self) -> list[str]:
        paths: list[str] = []
        try:
            paths.extend(self.header_paths())
        except Exception:
            logger.debug("failed to resolve header paths for safety normalization", exc_info=True)
        paths.extend(
            path
            for path in self._files
            if is_header_part_name(path) or path == self.HEADER_PATH
        )
        return list(dict.fromkeys(path for path in paths if path in self._files))

    def _iter_section_part_paths_for_safety_normalization(self) -> list[str]:
        paths: list[str] = []
        try:
            paths.extend(self.section_paths())
        except Exception:
            logger.debug("failed to resolve section paths for safety normalization", exc_info=True)
        paths.extend(path for path in self._files if is_section_part_name(path))
        return list(dict.fromkeys(path for path in paths if path in self._files))

    def _style_name_id_map_for_safety_normalization(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        conflicts: set[str] = set()
        for path in self._iter_header_part_paths_for_safety_normalization():
            try:
                root = parse_xml(self._files[path])
            except Exception:
                continue
            for style in root.iter():
                if _local_name(style) != "style":
                    continue
                style_id = style.get("id")
                if not _is_integer_literal(style_id):
                    continue
                resolved_id = style_id.strip()
                for attr_name in ("name", "engName"):
                    alias = (style.get(attr_name) or "").strip()
                    if not alias:
                        continue
                    existing = aliases.get(alias)
                    if existing is not None and existing != resolved_id:
                        conflicts.add(alias)
                        continue
                    aliases[alias] = resolved_id

        for alias in conflicts:
            aliases.pop(alias, None)
        return aliases

    def _normalize_named_style_references_for_safety(self) -> None:
        style_ids_by_name = self._style_name_id_map_for_safety_normalization()
        if not style_ids_by_name:
            return

        for path in self._iter_section_part_paths_for_safety_normalization():
            try:
                root = parse_xml(self._files[path])
            except Exception:
                continue
            changed = False
            for paragraph in root.iter():
                if _local_name(paragraph) != "p":
                    continue
                style_id_ref = paragraph.get("styleIDRef")
                if style_id_ref is None or _is_integer_literal(style_id_ref):
                    continue
                replacement = style_ids_by_name.get(style_id_ref.strip())
                if replacement is None or replacement == style_id_ref:
                    continue
                paragraph.set("styleIDRef", replacement)
                changed = True
            if changed:
                self._files[path] = _serialize_hwpml_root(root)

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
            return self._save_to_bytes(verify_open_safety=True, mark_clean=True)

        self._save_to_zip(destination, verify_open_safety=True)
        return destination

    def _save_bytes_unchecked(
        self,
        updates: Mapping[str, bytes | str | etree._Element] | None = None,
        *,
        _unchecked_token: object | None = None,
    ) -> bytes:
        """Return archive bytes without editor-open validation for internal diagnostics."""

        _require_unchecked_save_token(_unchecked_token)
        if updates:
            for part_name, payload in updates.items():
                self.set_part(part_name, payload)
        return self._save_to_bytes(
            verify_open_safety=False,
            mark_clean=False,
            _unchecked_token=_UNCHECKED_SAVE_TOKEN,
        )

    def _save_to_bytes(
        self,
        *,
        verify_open_safety: bool,
        mark_clean: bool,
        _unchecked_token: object | None = None,
    ) -> bytes:
        if not verify_open_safety:
            _require_unchecked_save_token(_unchecked_token)
        buffer: io.BytesIO = (
            _UncheckedSaveBuffer() if not verify_open_safety else io.BytesIO()
        )
        self._save_to_zip(
            buffer,
            verify_open_safety=verify_open_safety,
            mark_clean=mark_clean,
            _unchecked_token=_unchecked_token,
        )
        return buffer.getvalue()

    def _save_to_zip(
        self,
        pkg_file: str | Path | BinaryIO,
        *,
        verify_open_safety: bool,
        mark_clean: bool = True,
        _unchecked_token: object | None = None,
    ) -> None:
        if not verify_open_safety:
            _require_unchecked_save_token(_unchecked_token)
            _require_unchecked_save_buffer(pkg_file)
        self._files[self.MIMETYPE_PATH] = self._mimetype.encode("utf-8")
        version_was_dirty = self._version.dirty
        if self._version.dirty:
            self._files[self.VERSION_PATH] = self._version.to_bytes()
        self._normalize_named_style_references_for_safety()
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
                        self._write_archive_from_save(zf)
                # Verify archive integrity before replacing the original.
                with ZipFile(tmp_path, "r") as zf_check:
                    bad = zf_check.testzip()
                    if bad is not None:
                        raise HwpxPackageError(
                            f"ZIP integrity check failed for entry '{bad}'"
                        )
                if verify_open_safety:
                    self._verify_editor_open_safe_archive(Path(tmp_path))
                os.replace(tmp_path, str(target))
                if mark_clean and version_was_dirty:
                    self._version.mark_clean()
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
                self._write_archive_from_save(zf)
            buffer.seek(0)
            with ZipFile(buffer, "r") as zf_check:
                bad = zf_check.testzip()
                if bad is not None:
                    raise HwpxPackageError(
                        f"ZIP integrity check failed for entry '{bad}'"
                    )
            if verify_open_safety:
                self._verify_editor_open_safe_archive(buffer.getvalue())
            buffer.seek(0)
            payload = buffer.read()
            _write_stream_or_rollback(pkg_file, payload)
            if mark_clean and version_was_dirty:
                self._version.mark_clean()

    @classmethod
    def _verify_editor_open_safe_archive(cls, source: str | Path | bytes) -> None:
        from ..tools.package_validator import validate_editor_open_safety

        report = validate_editor_open_safety(source)
        if not report.ok:
            raise HwpxPackageError(
                "Generated HWPX package failed open-safety validation: "
                + report.summary
            )

    def _write_archive_from_save(self, zf: ZipFile) -> None:
        self._archive_write_depth += 1
        try:
            self._write_archive(zf)
        finally:
            self._archive_write_depth -= 1

    def _write_archive(self, zf: ZipFile) -> None:
        if self._archive_write_depth <= 0:
            raise HwpxPackageError(
                "raw HWPX archive writing is an internal save path; use "
                "HwpxPackage.save() so editor-open safety validation runs"
            )
        self._write_mimetype(zf)
        written = {self.MIMETYPE_PATH}
        ordered_names = [
            name
            for name in self._zip_order
            if name != self.MIMETYPE_PATH and name in self._files
        ]
        new_names = sorted(
            name for name in self._files if name not in written and name not in ordered_names
        )
        for name in [*ordered_names, *new_names]:
            self._write_zip_entry(zf, name, self._files[name], ZIP_DEFLATED)
            written.add(name)

    def _zip_info_for_write(self, path: str, compress_type: int) -> ZipInfo:
        original = self._zip_infos.get(path)
        if original is None:
            info = ZipInfo(path)
            info.compress_type = compress_type
            return info

        info = ZipInfo(path, original.date_time)
        info.compress_type = (
            compress_type
            if path == self.MIMETYPE_PATH
            else original.compress_type
        )
        info.comment = original.comment
        info.extra = original.extra
        info.create_system = original.create_system
        info.create_version = original.create_version
        info.extract_version = original.extract_version
        info.flag_bits = original.flag_bits
        info.volume = original.volume
        info.internal_attr = original.internal_attr
        info.external_attr = original.external_attr
        return info

    def _write_zip_entry(
        self,
        zf: ZipFile,
        path: str,
        payload: bytes,
        compress_type: int,
    ) -> None:
        if self._archive_write_depth <= 0:
            raise HwpxPackageError(
                "raw HWPX ZIP entry writing is an internal save path; use "
                "HwpxPackage.save() so editor-open safety validation runs"
            )
        info = self._zip_info_for_write(path, compress_type)
        zf.writestr(info, payload)

    def _write_mimetype(self, zf: ZipFile) -> None:
        self._write_zip_entry(
            zf,
            self.MIMETYPE_PATH,
            self._files[self.MIMETYPE_PATH],
            ZIP_STORED,
        )
