#!/usr/bin/env python3
"""Sanitize editor-authored HWPX fixture metadata in-place.

This script rewrites `Contents/content.hpf` inside `.hwpx` archives and normalizes
creator/lastsaveby/date-like metadata so local canonical fixtures can be shared
without leaking personal metadata.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

OPF_NS = "http://www.idpf.org/2007/opf/"
NS = {"opf": OPF_NS}

REPLACEMENTS = {
    "creator": "fixture",
    "lastsaveby": "fixture",
    "CreatedDate": "1970-01-01T00:00:00Z",
    "ModifiedDate": "1970-01-01T00:00:00Z",
    "date": "1970-01-01T00:00:00Z",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sanitize HWPX fixture metadata.")
    parser.add_argument("paths", nargs="+", help=".hwpx files or directories")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    return parser.parse_args()


def iter_hwpx_paths(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            found.extend(sorted(path.rglob("*.hwpx")))
        elif path.suffix.lower() == ".hwpx" and path.exists():
            found.append(path)
    # stable unique order
    uniq: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        if path not in seen:
            uniq.append(path)
            seen.add(path)
    return uniq


def sanitize_manifest_bytes(data: bytes) -> tuple[bytes, dict[str, tuple[str, str]]]:
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(data, parser=parser)
    changes: dict[str, tuple[str, str]] = {}

    metadata_nodes = root.xpath('.//*[local-name()="metadata"]')
    if not metadata_nodes:
        raise ValueError("No metadata node found in manifest")

    for meta in metadata_nodes[0].xpath('./*[local-name()="meta"]'):
        name = meta.get("name", "")
        if name in REPLACEMENTS:
            before = meta.text or ""
            after = REPLACEMENTS[name]
            if before != after:
                meta.text = after
                changes[name] = (before, after)

    serialized = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )
    return serialized, changes


def sanitize_hwpx(path: Path, dry_run: bool) -> tuple[bool, dict[str, tuple[str, str]]]:
    with ZipFile(path, "r") as zin:
        raw_manifest = zin.read("Contents/content.hpf")
        new_manifest, changes = sanitize_manifest_bytes(raw_manifest)
        if not changes:
            return False, {}
        if dry_run:
            return True, changes

        with tempfile.NamedTemporaryFile(delete=False, suffix=".hwpx", dir=str(path.parent)) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with ZipFile(path, "r") as src, ZipFile(tmp_path, "w") as dst:
                for info in src.infolist():
                    payload = new_manifest if info.filename == "Contents/content.hpf" else src.read(info.filename)
                    dst.writestr(info, payload)
            tmp_path.replace(path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    return True, changes


def main() -> int:
    args = parse_args()
    targets = iter_hwpx_paths(args.paths)
    if not targets:
        print("[ERROR] no .hwpx targets found", file=sys.stderr)
        return 2

    changed_any = False
    for target in targets:
        changed, changes = sanitize_hwpx(target, dry_run=args.dry_run)
        if changed:
            changed_any = True
        if not changes:
            print(f"[SKIP] {target}")
            continue
        print(f"[SANITIZED] {target}")
        for name, (before, after) in changes.items():
            print(f"  - {name}: {before!r} -> {after!r}")

    return 0 if changed_any or targets else 1


if __name__ == "__main__":
    raise SystemExit(main())
