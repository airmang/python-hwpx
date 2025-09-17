"""Use :class:`hwpx.tools.object_finder.ObjectFinder` to locate XML nodes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hwpx.tools.object_finder import AttrMatcher, ObjectFinder


def _parse_attribute_filters(raw_filters: list[str]) -> Dict[str, AttrMatcher]:
    filters: Dict[str, AttrMatcher] = {}
    for raw in raw_filters:
        if "=" not in raw:
            raise ValueError(f"Invalid attribute filter: {raw!r}; expected name=value")
        name, value = raw.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("Attribute name cannot be empty")
        value = value.strip()
        if len(value) >= 2 and value.startswith("/") and value.endswith("/"):
            matcher: AttrMatcher = re.compile(value[1:-1])
        else:
            matcher = value
        if name in filters:
            current = filters[name]
            if isinstance(current, list) and isinstance(matcher, str):
                current.append(matcher)
            elif isinstance(current, str) and isinstance(matcher, str):
                filters[name] = [current, matcher]
            else:
                raise ValueError(
                    "Multiple filters for a single attribute must all be plain strings",
                )
        else:
            filters[name] = matcher
    return filters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the XML payload for specific objects.")
    parser.add_argument("document", type=Path, help="Path to the .hwpx file to inspect")
    parser.add_argument("--tag", help="Element tag (e.g. hp:tbl or hp:rect)")
    parser.add_argument(
        "--xpath",
        help="Optional XPath expression evaluated inside each section document.",
    )
    parser.add_argument(
        "--attribute",
        "-a",
        action="append",
        default=[],
        help="Attribute filter in the form name=value. Surround the value with / to use a regex.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results to display (0 for unlimited).",
    )
    parser.add_argument(
        "--show-text",
        action="store_true",
        help="Display the element text content alongside its location.",
    )
    parser.add_argument(
        "--show-attributes",
        action="store_true",
        help="Print matching element attributes for additional context.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = args.document
    if not document.exists():
        raise SystemExit(f"Document not found: {document}")

    try:
        attribute_filters = _parse_attribute_filters(args.attribute)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    finder = ObjectFinder(document)
    limit = None if args.limit == 0 else args.limit

    for found in finder.iter(
        tag=args.tag,
        attrs=attribute_filters or None,
        xpath=args.xpath,
        limit=limit,
    ):
        print(f"{found.section.name}:{found.path} <{found.tag}>")
        if args.show_attributes and found.element.attrib:
            for key, value in sorted(found.element.attrib.items()):
                print(f"  @{key}={value}")
        if args.show_text:
            text = (found.text or "").strip()
            if text:
                print(f"  text={text}")


def _main() -> None:  # pragma: no cover - console script helper
    main()


if __name__ == "__main__":
    main()
