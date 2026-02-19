"""Simple demonstration of :class:`hwpx.tools.text_extractor.TextExtractor`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hwpx.tools.text_extractor import TextExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print the paragraphs contained in an HWPX file.")
    parser.add_argument("document", type=Path, help="Path to the .hwpx document to inspect")
    parser.add_argument(
        "--include-nested",
        action="store_true",
        help="Include paragraphs stored inside tables, shapes and other objects.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of non-empty paragraphs to display (0 for no limit).",
    )
    parser.add_argument(
        "--object-behavior",
        choices=("skip", "marker", "nested"),
        default="skip",
        help="How to treat embedded objects encountered while reading a paragraph.",
    )
    parser.add_argument(
        "--marker-format",
        default="[object]",
        help="Marker text to use when --object-behavior=marker.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = args.document
    if not document.exists():
        raise SystemExit(f"Document not found: {document}")

    marker = args.marker_format if args.object_behavior == "marker" else None

    with TextExtractor(document) as extractor:
        printed = 0
        for paragraph in extractor.iter_document_paragraphs(include_nested=args.include_nested):
            text = paragraph.text(
                object_behavior=args.object_behavior,
                object_marker_format=marker,
            ).strip()
            if not text:
                continue
            printed += 1
            location = f"{paragraph.section.index}:{paragraph.index}"
            print(f"[{location}] {text}")
            if args.limit and printed >= args.limit:
                break


if __name__ == "__main__":
    main()
