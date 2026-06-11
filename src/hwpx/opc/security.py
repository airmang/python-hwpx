# SPDX-License-Identifier: Apache-2.0
"""Input hardening helpers for HWPX OPC/XML readers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZipInfo

MAX_XML_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 256
MAX_ZIP_ENTRIES = 4096
MAX_ZIP_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 1000.0


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
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
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

    total = 0
    for info in infos:
        _guard_zip_name(info.filename)
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

    stack: list[tuple[object, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        if depth > max_depth:
            raise HwpxSecurityError(
                f"{part_name} exceeds XML depth limit: {depth} > {max_depth}"
            )
        children: Iterable[object] = list(element)  # type: ignore[arg-type]
        for child in children:
            stack.append((child, depth + 1))


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
