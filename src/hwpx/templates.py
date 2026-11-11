# SPDX-License-Identifier: Apache-2.0
"""Embedded templates and sample payloads for HWPX documents."""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from zipfile import ZipFile, ZipInfo


@lru_cache(maxsize=None)
def blank_document_bytes() -> bytes:
    """Return the binary payload for a minimal blank HWPX document."""

    # Prefer a packaged asset when available.
    try:
        data_pkg = resources.files("hwpx.data")
    except (ModuleNotFoundError, AttributeError):  # pragma: no cover - optional dependency
        data_pkg = None
    if data_pkg is not None:
        skeleton = data_pkg / "Skeleton.hwpx"
        if skeleton.is_file():  # type: ignore[call-arg]
            with skeleton.open("rb") as stream:  # type: ignore[call-arg]
                return stream.read()

    # Fall back to the repository examples folder during development.
    root = Path(__file__).resolve().parent.parent.parent
    fallback = root / "examples" / "Skeleton.hwpx"
    if fallback.is_file():
        return fallback.read_bytes()

    raise FileNotFoundError(
        "Could not locate Skeleton.hwpx; ensure the template asset is packaged."
    )


_CONTENT_HPF = "Contents/content.hpf"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# The fields the bundled skeleton carries from the machine it was saved on.
_EMPTIED_META = ("creator", "lastsaveby", "date")
_STAMPED_META = ("CreatedDate", "ModifiedDate")


def _creation_time() -> datetime:
    """Now in UTC, or ``SOURCE_DATE_EPOCH`` when a reproducible build sets it."""

    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    return datetime.now(timezone.utc)


def _meta_pattern(name: str) -> "re.Pattern[bytes]":
    return re.compile(
        rb'<opf:meta name="' + name.encode("ascii") + rb'" content="text"(?:/>|>[^<]*</opf:meta>)'
    )


@lru_cache(maxsize=None)
def _blank_document_members() -> tuple[tuple[ZipInfo, bytes], ...]:
    with ZipFile(io.BytesIO(blank_document_bytes())) as archive:
        return tuple((info, archive.read(info.filename)) for info in archive.infolist())


def new_document_bytes(created: datetime | None = None) -> bytes:
    """Return the blank document with its own metadata instead of the skeleton's.

    The bundled skeleton was saved once and carries that save's author and
    dates. A document made now gets an empty ``creator`` and ``lastsaveby``,
    an empty free-form ``date``, and *created* (default: now, UTC) as both
    ``CreatedDate`` and ``ModifiedDate``. Everything else is the skeleton,
    byte for byte.
    """

    moment = (created or _creation_time()).astimezone(timezone.utc)
    stamp = moment.strftime(_TIMESTAMP_FORMAT).encode("ascii")
    out = io.BytesIO()
    with ZipFile(out, "w") as archive:
        for info, payload in _blank_document_members():
            if info.filename == _CONTENT_HPF:
                for name in _EMPTIED_META:
                    payload = _meta_pattern(name).sub(
                        b'<opf:meta name="' + name.encode("ascii") + b'" content="text"/>', payload
                    )
                for name in _STAMPED_META:
                    payload = _meta_pattern(name).sub(
                        b'<opf:meta name="' + name.encode("ascii") + b'" content="text">'
                        + stamp + b"</opf:meta>",
                        payload,
                    )
            archive.writestr(info, payload, compress_type=info.compress_type)
    return out.getvalue()
