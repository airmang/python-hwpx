# SPDX-License-Identifier: Apache-2.0
"""Helpers for resolving HWPX container and manifest relationships."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Collection, Iterable

CONTAINER_NAMESPACES = (
    "urn:oasis:names:tc:opendocument:xmlns:container",
)
MAIN_ROOTFILE_MEDIA_TYPE = "application/hwpml-package+xml"
OPF_NS = {"opf": "http://www.idpf.org/2007/opf/"}

__all__ = [
    "CONTAINER_NAMESPACES",
    "MAIN_ROOTFILE_MEDIA_TYPE",
    "OPF_NS",
    "ManifestItemRef",
    "ManifestRelationships",
    "RootFileRef",
    "is_header_part_name",
    "is_section_part_name",
    "normalize_part_name",
    "parse_container_rootfiles",
    "parse_manifest_relationships",
    "resolve_part_name",
    "select_main_rootfile",
]


@dataclass(frozen=True)
class RootFileRef:
    full_path: str
    media_type: str | None = None


@dataclass(frozen=True)
class ManifestItemRef:
    item_id: str | None
    href: str
    resolved_path: str
    media_type: str | None = None
    properties: str | None = None


@dataclass(frozen=True)
class ManifestRelationships:
    manifest_path: str
    items: tuple[ManifestItemRef, ...]
    spine_paths: tuple[str, ...]
    dangling_idrefs: tuple[str, ...]
    header_paths: tuple[str, ...]
    master_page_paths: tuple[str, ...]
    history_paths: tuple[str, ...]
    version_path: str | None


def normalize_part_name(path: str) -> str:
    raw = path.replace("\\", "/").strip()
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def resolve_part_name(
    base_part: str,
    href: str,
    *,
    known_parts: Collection[str] | None = None,
) -> str:
    raw_href = href.replace("\\", "/").strip()
    if not raw_href:
        return ""
    if raw_href.startswith("/"):
        return normalize_part_name(raw_href)
    base_dir = PurePosixPath(normalize_part_name(base_part)).parent
    normalized_href = normalize_part_name(raw_href)
    if known_parts is not None:
        normalized_parts = {normalize_part_name(part) for part in known_parts}
        if normalized_href in normalized_parts:
            return normalized_href
        relative_candidate = normalize_part_name(str(base_dir / raw_href))
        if relative_candidate in normalized_parts:
            return relative_candidate
    base_dir_name = normalize_part_name(str(base_dir))
    if base_dir_name and normalized_href.startswith(f"{base_dir_name}/"):
        return normalized_href
    return normalize_part_name(str(base_dir / raw_href))


def parse_container_rootfiles(container_root: Any) -> tuple[RootFileRef, ...]:
    rootfiles: list[RootFileRef] = []
    seen: set[tuple[str, str | None]] = set()
    candidates = list(container_root.findall(".//rootfile"))
    for namespace in CONTAINER_NAMESPACES:
        candidates.extend(container_root.findall(f".//{{{namespace}}}rootfile"))

    for elem in candidates:
            full_path = (
                elem.get("full-path")
                or elem.get("fullPath")
                or elem.get("full_path")
            )
            if not full_path:
                continue
            media_type = (
                elem.get("media-type")
                or elem.get("mediaType")
                or elem.get("media_type")
            )
            root = RootFileRef(
                full_path=normalize_part_name(full_path),
                media_type=media_type,
            )
            key = (root.full_path, root.media_type)
            if key in seen:
                continue
            seen.add(key)
            rootfiles.append(root)
    return tuple(rootfiles)


def select_main_rootfile(rootfiles: Iterable[RootFileRef]) -> tuple[RootFileRef | None, bool]:
    ordered = list(rootfiles)
    if not ordered:
        return None, False
    for rootfile in ordered:
        if rootfile.media_type == MAIN_ROOTFILE_MEDIA_TYPE:
            return rootfile, False
    return ordered[0], True


def is_section_part_name(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.startswith("section") and name.endswith(".xml")


def is_header_part_name(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.startswith("header") and name.endswith(".xml")


def _manifest_matches(item: ManifestItemRef, *candidates: str) -> bool:
    haystack = " ".join(
        part.lower()
        for part in (
            item.item_id or "",
            item.href,
            item.media_type or "",
            item.properties or "",
        )
        if part
    )
    return any(candidate in haystack for candidate in candidates if candidate)


def parse_manifest_relationships(
    manifest_root: Any,
    manifest_path: str,
    *,
    known_parts: Collection[str] | None = None,
) -> ManifestRelationships:
    items: list[ManifestItemRef] = []
    id_to_path: dict[str, str] = {}

    for item in manifest_root.findall(".//opf:item", OPF_NS):
        href = (item.get("href") or "").strip()
        if not href:
            continue
        resolved_path = resolve_part_name(manifest_path, href, known_parts=known_parts)
        item_ref = ManifestItemRef(
            item_id=item.get("id"),
            href=href,
            resolved_path=resolved_path,
            media_type=item.get("media-type"),
            properties=item.get("properties"),
        )
        items.append(item_ref)
        if item_ref.item_id:
            id_to_path[item_ref.item_id] = resolved_path

    spine_paths: list[str] = []
    dangling_idrefs: list[str] = []
    for itemref in manifest_root.findall(".//opf:itemref", OPF_NS):
        idref = (itemref.get("idref") or "").strip()
        if not idref:
            continue
        spine_path = id_to_path.get(idref)
        if spine_path:
            spine_paths.append(spine_path)
        else:
            dangling_idrefs.append(idref)

    header_paths = tuple(path for path in spine_paths if is_header_part_name(path))
    master_page_paths = tuple(
        item.resolved_path
        for item in items
        if _manifest_matches(item, "masterpage", "master-page")
    )
    history_paths = tuple(
        item.resolved_path
        for item in items
        if _manifest_matches(item, "history")
    )
    version_path = next(
        (item.resolved_path for item in items if _manifest_matches(item, "version")),
        None,
    )

    return ManifestRelationships(
        manifest_path=normalize_part_name(manifest_path),
        items=tuple(items),
        spine_paths=tuple(spine_paths),
        dangling_idrefs=tuple(dangling_idrefs),
        header_paths=header_paths,
        master_page_paths=master_page_paths,
        history_paths=history_paths,
        version_path=version_path,
    )
