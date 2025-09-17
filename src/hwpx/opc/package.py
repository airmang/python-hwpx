"""Utilities for reading and writing HWPX OPC packages."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Iterable, Iterator, Mapping, MutableMapping
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

__all__ = ["HwpxPackage", "HwpxPackageError", "HwpxStructureError", "RootFile", "VersionInfo"]


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
        element: ET.Element,
        namespaces: Mapping[str, str],
        xml_declaration: bytes | None,
    ) -> None:
        self._element = element
        self._namespaces = dict(namespaces)
        self._xml_declaration = xml_declaration
        self._dirty = False

    @classmethod
    def from_bytes(cls, data: bytes) -> VersionInfo:
        element = ET.fromstring(data)
        namespaces = cls._collect_namespaces(data)
        declaration = cls._extract_declaration(data)
        return cls(element, namespaces, declaration)

    @staticmethod
    def _collect_namespaces(data: bytes) -> Mapping[str, str]:
        namespaces: dict[str, str] = {}
        for event, elem in ET.iterparse(BytesIO(data), events=("start-ns",)):
            prefix, uri = elem
            namespaces[prefix or ""] = uri
        return namespaces

    @staticmethod
    def _extract_declaration(data: bytes) -> bytes | None:
        data = data.lstrip()
        if not data.startswith(b"<?xml"):
            return None
        end = data.find(b"?>")
        if end == -1:
            return None
        return data[: end + 2]

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
        for prefix, uri in self._namespaces.items():
            ET.register_namespace(prefix, uri)
        stream = BytesIO()
        tree = ET.ElementTree(self._element)
        tree.write(stream, encoding="utf-8", xml_declaration=False)
        xml_body = stream.getvalue()
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
        self._validate_structure()

    @classmethod
    def open(cls, pkg_file: str | BinaryIO) -> HwpxPackage:
        with ZipFile(pkg_file, "r") as zf:
            files = {info.filename: zf.read(info) for info in zf.infolist()}
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
        root = ET.fromstring(data)
        rootfiles = []
        for elem in root.findall(".//{*}rootfile"):
            full_path = (
                elem.get("full-path")
                or elem.get("fullPath")
                or elem.get("full_path")
            )
            if not full_path:
                raise HwpxStructureError("container.xml contains a rootfile without 'full-path'.")
            media_type = (
                elem.get("media-type")
                or elem.get("mediaType")
                or elem.get("media_type")
            )
            rootfiles.append(RootFile(full_path, media_type))
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
        if not any(path.startswith(("Contents/", "Content/")) for path in self._files):
            raise HwpxStructureError(
                "HWPX package does not contain a 'Contents' directory."
            )

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
            if rootfile.media_type == "application/hwpml-package+xml":
                return rootfile
        return self._rootfiles[0]

    @property
    def version_info(self) -> VersionInfo:
        return self._version

    def read(self, path: str) -> bytes:
        norm_path = self._normalize_path(path)
        try:
            return self._files[norm_path]
        except KeyError as exc:
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
        self._validate_structure()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return path.replace("\\", "/")

    def files(self) -> list[str]:
        return sorted(self._files)

    def save(self, pkg_file: str | BinaryIO) -> None:
        self._files[self.MIMETYPE_PATH] = self._mimetype.encode("utf-8")
        if self._version.dirty:
            self._files[self.VERSION_PATH] = self._version.to_bytes()
            self._version.mark_clean()
        self._validate_structure()
        with ZipFile(pkg_file, "w") as zf:
            self._write_mimetype(zf)
            for name in sorted(self._files):
                if name == self.MIMETYPE_PATH:
                    continue
                data = self._files[name]
                info = ZipInfo(name)
                info.compress_type = ZIP_DEFLATED
                zf.writestr(info, data)

    def _write_mimetype(self, zf: ZipFile) -> None:
        info = ZipInfo(self.MIMETYPE_PATH)
        info.compress_type = ZIP_STORED
        zf.writestr(info, self._files[self.MIMETYPE_PATH])

