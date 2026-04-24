# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, Sequence
from zipfile import ZIP_STORED, BadZipFile, ZipFile

from ..opc.relationships import (
    MAIN_ROOTFILE_MEDIA_TYPE,
    is_section_part_name,
    parse_container_rootfiles,
    parse_manifest_relationships,
    select_main_rootfile,
)

EXPECTED_MIMETYPE = "application/hwp+zip"
MIMETYPE_PATH = "mimetype"
CONTAINER_PATH = "META-INF/container.xml"
HEADER_PATH = "Contents/header.xml"
VERSION_PATH = "version.xml"

IssueLevel = Literal["error", "warning"]

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
    level: IssueLevel = "error"

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.part_name}: {self.message}"


@dataclass(frozen=True)
class PackageValidationReport:
    checked_parts: tuple[str, ...]
    issues: tuple[PackageValidationIssue, ...]

    @property
    def errors(self) -> tuple[PackageValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.is_error)

    @property
    def warnings(self) -> tuple[PackageValidationIssue, ...]:
        return tuple(issue for issue in self.issues if not issue.is_error)

    @property
    def ok(self) -> bool:
        return not self.errors

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


def _error(issues: list[PackageValidationIssue], part_name: str, message: str) -> None:
    issues.append(PackageValidationIssue(part_name, message, "error"))


def _warning(issues: list[PackageValidationIssue], part_name: str, message: str) -> None:
    issues.append(PackageValidationIssue(part_name, message, "warning"))


def _safe_read(zf: ZipFile, part_name: str) -> bytes | None:
    try:
        return zf.read(part_name)
    except (BadZipFile, KeyError, OSError):
        return None


def _fallback_named_parts(names: set[str], *, token: str, extra_token: str | None = None) -> list[str]:
    matches: list[str] = []
    for name in sorted(names):
        part_name = PurePosixPath(name).name.lower()
        if token not in part_name:
            continue
        if extra_token is not None and extra_token not in part_name:
            continue
        matches.append(name)
    return matches


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
        infos = [info for info in zf.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]
        name_set = set(names)
        checked_parts.extend(names)

        if not infos:
            _error(issues, "archive", "empty archive")
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        bad_entry = zf.testzip()
        if bad_entry is not None:
            _error(issues, bad_entry, "ZIP CRC/integrity check failed")

        if MIMETYPE_PATH not in name_set:
            _error(issues, MIMETYPE_PATH, "missing required file")
        else:
            mimetype_bytes = _safe_read(zf, MIMETYPE_PATH)
            if mimetype_bytes is None:
                _error(issues, MIMETYPE_PATH, "unable to read entry for integrity validation")
            else:
                try:
                    mimetype = mimetype_bytes.decode("utf-8").strip()
                except UnicodeDecodeError:
                    mimetype = "<binary>"
                if mimetype != EXPECTED_MIMETYPE:
                    _error(
                        issues,
                        MIMETYPE_PATH,
                        f"expected {EXPECTED_MIMETYPE!r}, got {mimetype!r}",
                    )
                if infos[0].filename != MIMETYPE_PATH:
                    _error(issues, MIMETYPE_PATH, "must be the first ZIP entry")
                if zf.getinfo(MIMETYPE_PATH).compress_type != ZIP_STORED:
                    _error(issues, MIMETYPE_PATH, "must use ZIP_STORED")

        if CONTAINER_PATH not in name_set:
            _error(issues, CONTAINER_PATH, "missing required file")
        if VERSION_PATH not in name_set:
            _error(issues, VERSION_PATH, "missing required file under current engine semantics")

        xml_roots: dict[str, ET.Element] = {}
        for name in names:
            if not (name.endswith(".xml") or name.endswith(".hpf")):
                continue
            payload = _safe_read(zf, name)
            if payload is None:
                _error(issues, name, "unable to read entry for XML parsing")
                continue
            try:
                xml_roots[name] = _parse_xml(payload)
            except ValueError as exc:
                _error(issues, name, str(exc))

        container_root = xml_roots.get(CONTAINER_PATH)
        if container_root is None:
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        rootfiles = parse_container_rootfiles(container_root)
        if not rootfiles:
            _error(issues, CONTAINER_PATH, "declares no rootfile entries")
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        for rootfile in rootfiles:
            if rootfile.full_path not in name_set:
                _error(
                    issues,
                    CONTAINER_PATH,
                    f"rootfile points to missing part {rootfile.full_path!r}",
                )

        selected_rootfile, used_rootfile_fallback = select_main_rootfile(rootfiles)
        if selected_rootfile is None:
            return PackageValidationReport(tuple(checked_parts), tuple(issues))
        if used_rootfile_fallback:
            _warning(
                issues,
                CONTAINER_PATH,
                "no rootfile is marked as "
                f"{MAIN_ROOTFILE_MEDIA_TYPE!r}; engine will use the first declaration "
                f"{selected_rootfile.full_path!r}",
            )

        manifest_root = xml_roots.get(selected_rootfile.full_path)
        if manifest_root is None:
            _error(
                issues,
                selected_rootfile.full_path,
                "selected main rootfile is missing or not well-formed XML",
            )
            return PackageValidationReport(tuple(checked_parts), tuple(issues))

        relationships = parse_manifest_relationships(
            manifest_root,
            selected_rootfile.full_path,
            known_parts=name_set,
        )

        for item in relationships.items:
            if item.resolved_path not in name_set:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    f"manifest href missing from archive: {item.href!r} -> {item.resolved_path!r}",
                )

        for idref in relationships.dangling_idrefs:
            _warning(
                issues,
                selected_rootfile.full_path,
                f"spine itemref references missing manifest id {idref!r}",
            )

        section_paths = [path for path in relationships.spine_paths if is_section_part_name(path)]
        if section_paths:
            for path in section_paths:
                if path not in name_set:
                    _error(
                        issues,
                        selected_rootfile.full_path,
                        f"spine section part missing from archive: {path!r}",
                    )
        else:
            fallback_sections = [name for name in sorted(name_set) if is_section_part_name(name)]
            if fallback_sections:
                _warning(
                    issues,
                    selected_rootfile.full_path,
                    "manifest spine does not resolve any section parts; engine will fall back "
                    "to filename-based section discovery",
                )
            else:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    "no section parts found in manifest spine or archive fallback",
                )

        if not relationships.header_paths and HEADER_PATH in name_set:
            _warning(
                issues,
                selected_rootfile.full_path,
                "manifest spine does not resolve a header part; engine will fall back to "
                f"{HEADER_PATH!r}",
            )

        for path in relationships.header_paths:
            if path not in name_set:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    f"header part missing from archive: {path!r}",
                )

        if not relationships.master_page_paths:
            fallback_master_pages = _fallback_named_parts(name_set, token="master", extra_token="page")
            if fallback_master_pages:
                _warning(
                    issues,
                    selected_rootfile.full_path,
                    "manifest does not reference masterPage parts; engine will fall back to "
                    "filename-based discovery",
                )
        for path in relationships.master_page_paths:
            if path not in name_set:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    f"masterPage part missing from archive: {path!r}",
                )

        if not relationships.history_paths:
            fallback_histories = _fallback_named_parts(name_set, token="history")
            if fallback_histories:
                _warning(
                    issues,
                    selected_rootfile.full_path,
                    "manifest does not reference history parts; engine will fall back to "
                    "filename-based discovery",
                )
        for path in relationships.history_paths:
            if path not in name_set:
                _error(
                    issues,
                    selected_rootfile.full_path,
                    f"history part missing from archive: {path!r}",
                )

        if relationships.version_path is None and VERSION_PATH in name_set:
            _warning(
                issues,
                selected_rootfile.full_path,
                "manifest does not reference a version part; engine will fall back to "
                f"{VERSION_PATH!r}",
            )
        elif relationships.version_path is not None and relationships.version_path not in name_set:
            _error(
                issues,
                selected_rootfile.full_path,
                f"manifest version part missing from archive: {relationships.version_path!r}",
            )

    return PackageValidationReport(tuple(checked_parts), tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate HWPX package structure using engine-aligned ZIP/container/manifest checks"
    )
    parser.add_argument("source", help="Path to the HWPX file")
    args = parser.parse_args(argv)

    report = validate_package(args.source)
    for issue in report.issues:
        prefix = "ERROR" if issue.is_error else "WARN"
        print(f"{prefix}: {issue}")

    if report.errors:
        return 1

    if report.warnings:
        print("Package validation passed with warnings.")
    else:
        print("All package validations passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
