#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from zipfile import ZipFile

from lxml import etree


def unpack(hwpx_path: str, output_dir: str) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with ZipFile(hwpx_path, "r") as archive:
        for entry in archive.namelist():
            data = archive.read(entry)
            destination = output / entry
            destination.parent.mkdir(parents=True, exist_ok=True)

            if entry.endswith(".xml") or entry.endswith(".hpf"):
                try:
                    tree = etree.fromstring(data)
                    etree.indent(tree, space="  ")
                    data = etree.tostring(
                        tree,
                        pretty_print=True,
                        xml_declaration=True,
                        encoding="UTF-8",
                    )
                except etree.XMLSyntaxError:
                    pass

            destination.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unpack an HWPX file into a directory")
    parser.add_argument("input", help="Input .hwpx path")
    parser.add_argument("output", help="Output directory")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1

    unpack(args.input, args.output)
    print(f"Unpacked: {args.input} -> {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
