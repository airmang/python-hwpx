# SPDX-License-Identifier: Apache-2.0
"""Deterministic and fail-closed ``.hwpxbp`` bundle I/O."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..model import AgentContractError
from .model import (
    ASSET_PATH_PATTERN,
    MAX_ASSETS,
    MAX_ASSET_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_ASSET_BYTES,
    canonical_manifest_bytes,
    validate_blueprint_manifest,
    with_blueprint_hash,
)

MANIFEST_PATH = "blueprint.json"
MAX_BUNDLE_BYTES = MAX_MANIFEST_BYTES + MAX_TOTAL_ASSET_BYTES + 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

ALLOWED_MEDIA_TYPES: dict[str, tuple[str, ...]] = {
    "image/png": ("png",),
    "image/jpeg": ("jpg", "jpeg"),
    "image/gif": ("gif",),
    "image/bmp": ("bmp",),
    "image/tiff": ("tif", "tiff"),
    "image/webp": ("webp",),
}


@dataclass(frozen=True, slots=True)
class BlueprintBundle:
    """A fully validated manifest and detached content-addressed assets."""

    manifest: Mapping[str, Any]
    assets: Mapping[str, bytes]
    bundle_sha256: str
    size: int


def _error(code: str, message: str, *, target: str = "bundle") -> AgentContractError:
    return AgentContractError(code, message, target=target)


def _json_without_duplicate_keys(data: bytes) -> dict[str, Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _error("invariant_violation", f"duplicate JSON field: {key}", target=MANIFEST_PATH)
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs_hook)
    except AgentContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("invalid_syntax", "blueprint.json is not strict UTF-8 JSON", target=MANIFEST_PATH) from exc
    if not isinstance(value, dict):
        raise _error("invalid_syntax", "blueprint.json must contain one object", target=MANIFEST_PATH)
    return value


def _validate_entry_name(name: str) -> None:
    if not name or "\\" in name or "\x00" in name:
        raise _error("verification_failed", "bundle entry path is not normalized", target=name or "bundle")
    path = PurePosixPath(name)
    if path.is_absolute() or name.startswith("/") or any(part in {"", ".", ".."} for part in path.parts):
        raise _error("verification_failed", "bundle entry path is unsafe", target=name)
    if name != MANIFEST_PATH and not ASSET_PATH_PATTERN.fullmatch(name):
        raise _error("unsupported_content", "bundle contains an unknown or forbidden entry", target=name)


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    _validate_entry_name(info.filename)
    if info.is_dir():
        raise _error("unsupported_content", "directory entries are forbidden", target=info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and stat.S_ISLNK(mode):
        raise _error("unsupported_content", "symlink entries are forbidden", target=info.filename)
    if info.flag_bits & 0x1:
        raise _error("unsupported_content", "encrypted bundle entries are forbidden", target=info.filename)
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise _error("unsupported_content", "bundle compression method is forbidden", target=info.filename)
    limit = MAX_MANIFEST_BYTES if info.filename == MANIFEST_PATH else MAX_ASSET_BYTES
    if info.file_size > limit:
        raise _error("resource_limit", "bundle entry exceeds its byte limit", target=info.filename)
    if info.file_size and info.compress_size == 0:
        raise _error("resource_limit", "bundle entry has an invalid compression ratio", target=info.filename)
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise _error("resource_limit", "bundle entry exceeds the decompression-ratio limit", target=info.filename)


def _sniff_media_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validated_assets(
    manifest: Mapping[str, Any], assets: Mapping[str, bytes]
) -> dict[str, bytes]:
    declared = {str(item["assetPath"]): dict(item) for item in manifest["resources"]}
    if set(assets) != set(declared):
        raise _error(
            "invariant_violation",
            "bundle assets do not exactly match manifest resources",
            target="resources",
        )
    if len(assets) > MAX_ASSETS:
        raise _error("resource_limit", "asset count exceeds limit", target="resources")
    total = 0
    detached: dict[str, bytes] = {}
    for path in sorted(assets):
        _validate_entry_name(path)
        payload = assets[path]
        if not isinstance(payload, bytes):
            raise _error("invalid_syntax", "asset payload must be bytes", target=path)
        total += len(payload)
        if len(payload) > MAX_ASSET_BYTES or total > MAX_TOTAL_ASSET_BYTES:
            raise _error("resource_limit", "asset bytes exceed limit", target=path)
        record = declared[path]
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if digest != record["sha256"] or len(payload) != record["size"]:
            raise _error("verification_failed", "asset hash or size mismatch", target=path)
        media_type = str(record["mediaType"])
        suffix = path.rsplit(".", 1)[-1]
        if media_type not in ALLOWED_MEDIA_TYPES or suffix not in ALLOWED_MEDIA_TYPES[media_type]:
            raise _error("unsupported_content", "asset extension/MIME is not allow-listed", target=path)
        if _sniff_media_type(payload) != media_type:
            raise _error("verification_failed", "asset bytes do not match declared MIME", target=path)
        detached[path] = bytes(payload)
    return detached


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 0
    info.external_attr = 0
    info.internal_attr = 0
    info.flag_bits = 0
    return info


def build_blueprint_bundle(
    manifest: Mapping[str, Any], assets: Mapping[str, bytes] | None = None
) -> bytes:
    """Return canonical bundle bytes for an already hashed manifest."""

    checked = validate_blueprint_manifest(manifest)
    checked_assets = _validated_assets(checked, assets or {})
    manifest_bytes = canonical_manifest_bytes(checked, include_hash=True)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", allowZip64=False) as archive:
        archive.writestr(_zip_info(MANIFEST_PATH), manifest_bytes)
        for name, payload in checked_assets.items():
            archive.writestr(_zip_info(name), payload)
    result = stream.getvalue()
    if len(result) > MAX_BUNDLE_BYTES:
        raise _error("resource_limit", "blueprint bundle exceeds total byte limit")
    return result


def write_blueprint_bundle(
    destination: str | os.PathLike[str],
    manifest: Mapping[str, Any],
    assets: Mapping[str, bytes] | None = None,
    *,
    overwrite: bool = False,
) -> BlueprintBundle:
    """Atomically write one deterministic bundle and return its validated view."""

    path = Path(destination)
    if path.suffix.casefold() != ".hwpxbp":
        raise _error("invalid_syntax", "blueprint output must use .hwpxbp", target="output")
    if path.exists() and not overwrite:
        raise _error("identity_collision", "blueprint output already exists", target=str(path))
    data = build_blueprint_bundle(manifest, assets)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and not overwrite:
            raise _error("identity_collision", "blueprint output already exists", target=str(path))
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return read_blueprint_bundle(data)


def read_blueprint_bundle(source: str | os.PathLike[str] | bytes) -> BlueprintBundle:
    """Validate a complete bundle in memory before returning any materialized data."""

    data = bytes(source) if isinstance(source, bytes) else Path(source).read_bytes()
    if len(data) > MAX_BUNDLE_BYTES:
        raise _error("resource_limit", "blueprint bundle exceeds total byte limit")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise _error("invariant_violation", "bundle contains duplicate entry paths")
            if names.count(MANIFEST_PATH) != 1:
                raise _error("invariant_violation", "bundle must contain exactly one blueprint.json")
            if len(infos) > MAX_ASSETS + 1:
                raise _error("resource_limit", "bundle entry count exceeds limit")
            for info in infos:
                _validate_zip_info(info)
            if sum(info.file_size for info in infos if info.filename != MANIFEST_PATH) > MAX_TOTAL_ASSET_BYTES:
                raise _error("resource_limit", "bundle assets exceed total byte limit", target="resources")
            manifest_data = archive.read(MANIFEST_PATH)
            manifest = validate_blueprint_manifest(_json_without_duplicate_keys(manifest_data))
            asset_names = sorted(name for name in names if name != MANIFEST_PATH)
            assets = {name: archive.read(name) for name in asset_names}
    except AgentContractError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
        raise _error("invalid_syntax", "invalid .hwpxbp ZIP container") from exc
    checked_assets = _validated_assets(manifest, assets)
    return BlueprintBundle(
        manifest=manifest,
        assets=checked_assets,
        bundle_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def repack_blueprint_bundle(
    source: str | os.PathLike[str] | bytes,
    destination: str | os.PathLike[str],
    manifest: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> BlueprintBundle:
    """Safely repack edited typed JSON while preserving only validated assets."""

    original = read_blueprint_bundle(source)
    rehashed = with_blueprint_hash(manifest)
    return write_blueprint_bundle(destination, rehashed, original.assets, overwrite=overwrite)


__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "BlueprintBundle",
    "MANIFEST_PATH",
    "build_blueprint_bundle",
    "read_blueprint_bundle",
    "repack_blueprint_bundle",
    "write_blueprint_bundle",
]
