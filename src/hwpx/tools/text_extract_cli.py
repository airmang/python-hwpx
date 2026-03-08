from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .text_extractor import TextExtractor

__all__ = [
    "extract_plain",
    "extract_markdown",
    "main",
]


def extract_plain(hwpx_path: str, *, include_tables: bool = False) -> str:
    with TextExtractor(hwpx_path) as extractor:
        return extractor.extract_text(
            include_nested=include_tables,
            object_behavior="skip",
            skip_empty=True,
        )


def extract_markdown(hwpx_path: str) -> str:
    lines: list[str] = []
    with TextExtractor(hwpx_path) as extractor:
        for section in extractor.iter_sections():
            if lines:
                lines.extend(["", "---", ""])
            for paragraph in extractor.iter_paragraphs(section, include_nested=True):
                text = paragraph.text(object_behavior="skip")
                if not text.strip():
                    continue
                lines.append(f"  {text}" if paragraph.is_nested else text)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract text from an HWPX document")
    parser.add_argument("input", help="Path to the .hwpx file")
    parser.add_argument("--format", "-f", choices=["plain", "markdown"], default="plain")
    parser.add_argument("--include-tables", action="store_true", help="Include nested table text")
    parser.add_argument("--output", "-o", help="Write output to a file instead of stdout")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 1

    if args.format == "markdown":
        result = extract_markdown(str(input_path))
    else:
        result = extract_plain(str(input_path), include_tables=args.include_tables)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
    else:
        print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    raise SystemExit(main())
