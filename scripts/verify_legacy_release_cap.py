#!/usr/bin/env python3
"""Verify the published 5.1.1 compatibility release before core 5 publishes."""

from __future__ import annotations

import argparse
import importlib
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from importlib.metadata import metadata, version
from pathlib import Path

EXPECTED_CORE_VERSION = "4.2.0"
EXPECTED_LEGACY_VERSION = "5.1.1"
EXPECTED_SPECIFIERS = frozenset({">=4.2.0", "<5"})
EXPECTED_MARKERS = frozenset({"", 'extra=="oracle"', 'extra=="vision"'})
ROOT = Path(__file__).resolve().parents[1]


def _core_requirement_parts(raw: str) -> tuple[frozenset[str], str, str] | None:
    """Return exact specifiers, extras, and marker for a core requirement."""

    requirement, separator, marker = raw.partition(";")
    match = re.fullmatch(
        r"\s*python[-_.]hwpx(?:\[(?P<extras>[^\]]+)\])?"
        r"(?P<specifiers>.*)",
        requirement,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    specifiers = frozenset(
        item
        for item in match.group("specifiers").replace(" ", "").split(",")
        if item
    )
    extras = ",".join(
        sorted(
            item.strip().casefold()
            for item in (match.group("extras") or "").split(",")
            if item.strip()
        )
    )
    normalized_marker = (
        marker.replace(" ", "").replace("'", '"').casefold()
        if separator
        else ""
    )
    return specifiers, extras, normalized_marker


def validate_legacy_cap(
    *,
    core_version: str,
    legacy_version: str,
    requirements: list[str],
) -> list[str]:
    """Return failures for anything weaker or different from the safe pair."""

    failures: list[str] = []
    if core_version != EXPECTED_CORE_VERSION:
        failures.append(
            f"python-hwpx version {core_version!r} != {EXPECTED_CORE_VERSION!r}"
        )
    if legacy_version != EXPECTED_LEGACY_VERSION:
        failures.append(
            f"hwpx-mcp-server version {legacy_version!r} "
            f"!= {EXPECTED_LEGACY_VERSION!r}"
        )

    parsed = [
        parts
        for raw in requirements
        if (parts := _core_requirement_parts(raw)) is not None
    ]
    if len(parsed) != 3:
        failures.append(f"expected 3 python-hwpx requirements, got {len(parsed)}")
        return failures

    for specifiers, _, marker in parsed:
        if specifiers != EXPECTED_SPECIFIERS:
            failures.append(
                f"unsafe python-hwpx specifiers for {marker or 'base'}: "
                f"{sorted(specifiers)!r}"
            )
    markers = frozenset(marker for _, _, marker in parsed)
    if markers != EXPECTED_MARKERS:
        failures.append(f"unexpected python-hwpx markers: {sorted(markers)!r}")
    extras_by_marker = {marker: extras for _, extras, marker in parsed}
    if extras_by_marker.get("", None) != "":
        failures.append("base python-hwpx requirement must not request extras")
    for marker in ('extra=="oracle"', 'extra=="vision"'):
        if extras_by_marker.get(marker) != "visual":
            failures.append(f"{marker} must request python-hwpx[visual]")
    return failures


def inspect_installed_pair() -> int:
    """Validate the interpreter's installed pair and import the legacy facade."""

    legacy_metadata = metadata("hwpx-mcp-server")
    failures = validate_legacy_cap(
        core_version=version("python-hwpx"),
        legacy_version=version("hwpx-mcp-server"),
        requirements=legacy_metadata.get_all("Requires-Dist") or [],
    )
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    importlib.import_module("hwpx_mcp_server")
    importlib.import_module("hwpx_mcp_server.server")
    print(
        "[OK] public legacy cap: "
        "python-hwpx==4.2.0 + hwpx-mcp-server==5.1.1 "
        "with exact >=4.2.0,<5 requirements"
    )
    return 0


def _venv_executable(venv: Path, name: str) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return venv / directory / f"{name}{suffix}"


def install_and_verify(venv: Path) -> None:
    """Resolve beside core 5 in a closed wheelhouse and propagate all failures."""

    wheelhouse = venv.parent / f"{venv.name}-wheelhouse"
    if wheelhouse.exists() and any(wheelhouse.iterdir()):
        raise RuntimeError(f"wheelhouse must start empty: {wheelhouse}")
    wheelhouse.mkdir(parents=True, exist_ok=True)
    commands = (
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
            str(ROOT),
        ),
        (
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--dest",
            str(wheelhouse),
            f"python-hwpx=={EXPECTED_CORE_VERSION}",
            f"hwpx-mcp-server=={EXPECTED_LEGACY_VERSION}",
        ),
        (sys.executable, "-m", "venv", str(venv)),
        (
            str(_venv_executable(venv, "python")),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--only-binary=:all:",
            "--find-links",
            str(wheelhouse),
            f"hwpx-mcp-server=={EXPECTED_LEGACY_VERSION}",
        ),
        (str(_venv_executable(venv, "python")), "-m", "pip", "check"),
        (
            str(_venv_executable(venv, "python")),
            str(Path(__file__).resolve()),
            "--inspect-installed",
        ),
        (str(_venv_executable(venv, "hwpx-mcp-server")), "--help"),
    )
    for command in commands:
        subprocess.run(command, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--venv", type=Path)
    mode.add_argument("--inspect-installed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.inspect_installed:
        return inspect_installed_pair()
    install_and_verify(args.venv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
