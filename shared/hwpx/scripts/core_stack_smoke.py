#!/usr/bin/env python3
"""Minimal python-hwpx smoke path for the HWPX stack."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwpx import HwpxDocument, ObjectFinder, TextExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and verify a minimal HWPX smoke document.")
    parser.add_argument("output_hwpx", help="Output .hwpx path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output_hwpx).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = HwpxDocument.new()
    doc.add_paragraph("HWPX STACK SMOKE")
    doc.add_paragraph("기준선 검증 문서")

    table = doc.add_table(2, 2)
    table.set_cell_text(0, 0, "키")
    table.set_cell_text(0, 1, "값")
    table.set_cell_text(1, 0, "상태")
    table.set_cell_text(1, 1, "기준선")

    doc.save_to_path(str(output_path))

    with TextExtractor(str(output_path)) as extractor:
        text = extractor.extract_text(include_nested=True)

    tables = ObjectFinder(str(output_path)).find_all(tag="tbl")

    assert "HWPX STACK SMOKE" in text
    assert "기준선 검증 문서" in text
    assert len(tables) == 1

    print(f"[OK] core smoke created: {output_path}")
    print(f"[TEXT_CHARS] {len(text)}")
    print(f"[TABLES] {len(tables)}")


if __name__ == "__main__":
    main()
