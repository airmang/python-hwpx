"""Embedded templates and sample payloads for HWPX documents."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path


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
