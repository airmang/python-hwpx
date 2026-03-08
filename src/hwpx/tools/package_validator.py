from __future__ import annotations

import argparse
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Sequence
from zipfile import ZIP_STORED, BadZipFile, ZipFile

EXPECTED_MIMETYPE = "application/hwp+zip"
CONTAINER_PATH = "META-INF/container.xml"
MANIFEST_PATH = "Contents/content.hpf"
HEADER_PATH = "Contents/header.xml"
VERSION_PATH = "version.xml"
REQUIRED_CORE_FILES = ("mimetype", CONTAINER_PATH, MANIFEST_PATH, HEADER_PATH, VERSION_PATH)
OPF_NS = {"opf": "http://www.idpf.org/2007/opf/"}
CONTAINER_NS = {
    "ct": "urn:oasis:names:tc:opendocument:xmlns:container",
    "ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
}

__all__ = [
    "PackageValidationIssue",
    "PackageValidationReport",
    "validate_package",
    "main",
]


@dataclass(frozen=True)
class PackageValidationIssue:
    part_name: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.part_name}: {self.message}"


@dataclass(frozen=True)
class PackageValidationReport:
    checked_parts: tuple[str, ...]
    issues: tuple[PackageValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def __bool__(self) -> bool:  # pragma: no cover - convenience alias
        return self.ok


def _open_zip(source: str | Path | bytes | BinaryIO) -> ZipFile:
    if isinstance(source, (str, Path)):
        return ZipFile(source, "r")
    if isinstance(source, bytes):
        return ZipFile(io.BytesIO(source), "r")
    return ZipFile(source, "r")


def _parse_xml(payload: bytes) -> ET.Element:
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"malformed XML: {exc}") from exc


def _container_rootfiles(container_root: ET.Element) -> list[str]:
    paths: list[str] = []
    for namespace in CONTAINER_NS.values():
        paths.extend(
            elem.get("full-path")
            or elem.get("fullPath")
            or elem.get("full_path")
            for elem in container_root.findall(f".//{{{namespace}}}rootfile")
        )
    return [path for path in paths if path]


def _manifest_hrefs(manifest_root: ET.Element) -> set[str]:
    hrefs: set[str] = set()
    for item in manifest_root.findall(".//opf:item", OPF_NS):
        href = item.get("href")
        if href:
            hrefs.add(href)
    return hrefs


def _spine_hrefs(manifest_root: ET.Element) -> list[str]:
    hrefs: list[str] = []
    id_to_href: dict[str, str] = {}
    for item in manifest_root.findall(".//opf:item", OPF_NS):
        item_id = item.get("id")
        href = item.get("href")
        if item_id and href:
            id_to_href[item_id] = href

    for itemref in manifest_root.findall(".//opf:itemref", OPF_NS):
        idref = itemref.get("idref")
        if idref and idref in id_to_href:
            hrefs.append(id_to_href[idref])
    return hrefs


def validate_package(source: str | Path | bytes | BinaryIO) -> PackageValidationReport:
    checked_parts: list[str] = []
    issues: list[PackageValidationIssue] = []

    try:
        archive = _open_zip(source)
    except BadZipFile:
        return PackageValidationReport(
            checked_parts=(),
            issues=(PackageValidationIssue("archive", "not a valid ZIP archive"),),
        )

    with archive as zf:
        names = zf.namelist()
        checked_parts.extend(names)

        for required in REQUIRED_CORE_FILES:
            if required not in names:
                issues.append(PackageValidationIssue(required, "missing required file"))

        if not names:
            issues.append(PackageValidationIssue("archive", "empty archive"))
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        if "mimetype" in names:
            try:
                mimetype = zf.read("mimetype").decode("utf-8").strip()
            except UnicodeDecodeError:
                mimetype = "<binary>"
            if mimetype != EXPECTED_MIMETYPE:
                issues.append(
                    PackageValidationIssue(
                        "mimetype",
                        f"expected {EXPECTED_MIMETYPE!r}, got {mimetype!r}",
                    )
                )
            if names[0] != "mimetype":
                issues.append(PackageValidationIssue("mimetype", "must be the first ZIP entry"))
            if zf.getinfo("mimetype").compress_type != ZIP_STORED:
                issues.append(PackageValidationIssue("mimetype", "must use ZIP_STORED"))

        xml_roots: dict[str, ET.Element] = {}
        for name in names:
            if not (name.endswith(".xml") or name.endswith(".hpf")):
                continue
            try:
                xml_roots[name] = _parse_xml(zf.read(name))
            except ValueError as exc:
                issues.append(PackageValidationIssue(name, str(exc)))

        container_root = xml_roots.get(CONTAINER_PATH)
        if container_root is not None:
            rootfiles = _container_rootfiles(container_root)
            if not rootfiles:
                issues.append(PackageValidationIssue(CONTAINER_PATH, "declares no rootfile entries"))
            for rootfile in rootfiles:
                if rootfile not in names:
                    issues.append(
                        PackageValidationIssue(
                            CONTAINER_PATH,
                            f"rootfile points to missing part {rootfile!r}",
                        )
                    )

        manifest_root = xml_roots.get(MANIFEST_PATH)
        if manifest_root is not None:
            hrefs = _manifest_hrefs(manifest_root)
            for href in sorted(hrefs):
                if href not in names:
                    issues.append(
                        PackageValidationIssue(
                            MANIFEST_PATH,
                            f"manifest href missing from archive: {href}",
                        )
                    )

            spine_hrefs = _spine_hrefs(manifest_root)
            if not spine_hrefs:
                issues.append(PackageValidationIssue(MANIFEST_PATH, "spine declares no section parts"))
            for href in spine_hrefs:
                if href not in names:
                    issues.append(
                        PackageValidationIssue(
                            MANIFEST_PATH,
                            f"spine item missing from archive: {href}",
                        )
                    )

            if HEADER_PATH in names and HEADER_PATH not in hrefs:
                issues.append(
                    PackageValidationIssue(MANIFEST_PATH, "header.xml is not referenced in manifest")
                )

    return PackageValidationReport(tuple(checked_parts), tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate HWPX package structure")
    parser.add_argument("source", help="Path to the HWPX file")
    args = parser.parse_args(argv)

    report = validate_package(args.source)
    if report.issues:
        for issue in report.issues:
            print(f"ERROR: {issue}")
        return 1

    print("All package validations passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
