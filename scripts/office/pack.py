#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def pack(input_dir: str, hwpx_path: str) -> None:
    root = Path(input_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    mimetype_file = root / "mimetype"
    if not mimetype_file.is_file():
        raise FileNotFoundError(f"Missing required 'mimetype' file in {input_dir}")

    all_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )

    with ZipFile(hwpx_path, "w", ZIP_DEFLATED) as archive:
        archive.write(mimetype_file, "mimetype", compress_type=ZIP_STORED)
        for rel_path in all_files:
            if rel_path == "mimetype":
                continue
            archive.write(root / rel_path, rel_path, compress_type=ZIP_DEFLATED)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack a directory into an HWPX archive")
    parser.add_argument("input", help="Input directory")
    parser.add_argument("output", help="Output .hwpx path")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"Error: Directory not found: {args.input}", file=sys.stderr)
        return 1

    pack(args.input, args.output)
    print(f"Packed: {args.input} -> {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
